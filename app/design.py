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
from typing import Any

from app.agents import _llm, _retry
from app.config import settings
from app.models import ModuleInstance, Project, ProjectPlan
from app.prompts import PROJECT_DESIGNER_SYSTEM

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


def design_project(text: str, *, model: Any | None = None) -> Project:
    """자유 한국어 요구 → 다중 서브시스템 Project(LLM).

    model 을 주입하면 그 구조화-출력 모델을 그대로 쓴다(테스트의 가짜 모델). 없으면
    단일 ``_llm`` 시드에서 ProjectPlan 구조화 출력 모델을 만든다(키 필요).
    """
    if not text.strip():
        raise ValueError("설계 요구 텍스트가 비어 있습니다.")
    structured = model if model is not None else _llm(
        settings.analyst_model
    ).with_structured_output(ProjectPlan)
    result = _retry(
        lambda: structured.invoke(
            [("system", PROJECT_DESIGNER_SYSTEM), ("human", text)]
        )
    )
    plan = result if isinstance(result, ProjectPlan) else ProjectPlan.model_validate(result)
    if not plan.modules:
        raise ValueError("설계 결과에 서브시스템이 없습니다(요구가 너무 모호할 수 있음).")
    return plan_to_project(plan)
