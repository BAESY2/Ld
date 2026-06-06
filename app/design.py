"""LLM 설계 에이전트 — 자유 한국어 문단 → 다중 서브시스템 Project.

근간 재설계의 심장: 32개 템플릿/키워드 매칭의 천장을 넘어, LLM 이 복합·다절 요구를
**여러 서브시스템으로 분해**하고 각 서브시스템의 임의 명세를 *생성*한다. 생성물은
``app.project.compose`` → ``app.verifier.verify`` 결정론 게이트를 그대로 통과해야
채택된다(LLM=생성, 결정론 코어=검증/차단 — Agents4PLC 루프의 역전 구조).

설계 원칙(CLAUDE.md):
- 프로바이더 결정은 ``app.agents._llm`` 단일 지점만 쓴다(vendor-agnostic, 규칙 7).
- LLM 호출은 테스트에서 mock 한다(API 키 없이 CI 통과). ``model`` 주입으로 가능.
- 생성된 명세는 코어가 검증하므로, 모델이 틀려도 결정론 게이트가 불량을 거른다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.agents import _llm, _retry
from app.config import settings
from app.models import ModuleInstance, Project, ProjectPlan, StateMachineSpec, VerificationReport
from app.project import ProjectError, compose
from app.prompts import PROJECT_DESIGNER_SYSTEM
from app.synth import synthesize_st
from app.verifier import verify

_NAME_RE = re.compile(r"^[A-Za-z_]\w*$")


def _sanitize_name(name: str, taken: set[str], idx: int) -> str:
    """모듈 이름을 합성기가 받는 영문 식별자로 정규화(중복/비식별자 방어)."""
    base = name.strip()
    if not _NAME_RE.match(base):
        base = "mod"
    candidate = base
    i = idx
    while candidate in taken or not _NAME_RE.match(candidate):
        candidate = f"{base}{i}"
        i += 1
    return candidate


def plan_to_project(plan: ProjectPlan) -> Project:
    """ProjectPlan(LLM 산출) → Project(인라인 명세 모듈). 모듈명 정규화·충돌 제거."""
    modules: list[ModuleInstance] = []
    taken: set[str] = set()
    for i, pm in enumerate(plan.modules, start=1):
        name = _sanitize_name(pm.name, taken, i)
        taken.add(name)
        modules.append(ModuleInstance(name=name, spec=pm.spec))
    return Project(
        title=plan.title,
        modules=modules,
        cross_interlocks=list(plan.cross_interlocks),
    )


def design_project(text: str, *, model: Any | None = None, feedback: str | None = None) -> Project:
    """자유 한국어 요구 → 다중 서브시스템 Project(LLM).

    model 을 주입하면 그 구조화-출력 모델을 그대로 쓴다(테스트의 가짜 모델). 없으면
    단일 ``_llm`` 시드에서 ProjectPlan 구조화 출력 모델을 만든다(키 필요).
    feedback 이 있으면(재생성 루프) 검증 실패 사유를 human 컨텍스트로 덧붙인다.
    """
    if not text.strip():
        raise ValueError("설계 요구 텍스트가 비어 있습니다.")
    structured = model if model is not None else _llm(
        settings.analyst_model
    ).with_structured_output(ProjectPlan)
    human = text
    if feedback:
        human = f"{text}\n\n[직전 설계의 검증 실패 — 반드시 고칠 것]\n{feedback}"
    result = _retry(
        lambda: structured.invoke([("system", PROJECT_DESIGNER_SYSTEM), ("human", human)])
    )
    plan = result if isinstance(result, ProjectPlan) else ProjectPlan.model_validate(result)
    if not plan.modules:
        raise ValueError("설계 결과에 서브시스템이 없습니다(요구가 너무 모호할 수 있음).")
    return plan_to_project(plan)


@dataclass
class DesignResult:
    """설계+검증 폐루프 산출물. report.passed 가 최종 합격 여부."""

    project: Project
    spec: StateMachineSpec | None
    st_code: str
    report: VerificationReport | None
    revisions: int
    error: str | None = None


def _feedback_from(report: VerificationReport) -> str:
    errs = [f"[{i.code}] {i.message}" for i in report.issues if i.severity == "error"]
    fix = report.suggested_fix
    return (fix + " " if fix else "") + " / ".join(errs)


def design_and_verify(
    text: str, *, model: Any | None = None, max_revisions: int = 2
) -> DesignResult:
    """설계 → compose → verify 폐루프(Agents4PLC). 실패 시 사유를 LLM 에 되먹여 재생성.

    합격하면 즉시 반환. max_revisions 까지 못 고치면 마지막 결과를 그대로 반환하되
    report.passed=False 로 둔다(불량을 합격으로 숨기지 않음 — 결정론 게이트가 최종 판정).
    """
    feedback: str | None = None
    last: DesignResult | None = None
    for attempt in range(max_revisions + 1):
        project = design_project(text, model=model, feedback=feedback)
        try:
            spec = compose(project)
            st = synthesize_st(spec)
        except (ProjectError, ValueError) as exc:
            feedback = f"합성 실패: {exc}"
            last = DesignResult(project, None, "", None, attempt, error=str(exc))
            continue
        report = verify(spec, st)
        last = DesignResult(project, spec, st, report, attempt)
        if report.passed:
            return last
        feedback = _feedback_from(report)
    assert last is not None
    return last
