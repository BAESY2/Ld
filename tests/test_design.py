"""LLM 설계 에이전트 테스트 — 자유 한국어 → 다중 서브시스템 → 결정론 검증.

CLAUDE.md: LLM 호출은 mock(키 없이 CI 통과). 여기서는 구조화-출력 모델을 주입해
design_project 가 ProjectPlan→Project 로 바꾸고, 생성된 임의 명세가 compose→verify
결정론 게이트를 통과(이중코일0·인터락 강제)함을 검증한다 — 근간 재설계의 핵심 계약.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.design import design_project, plan_to_project
from app.models import (
    CrossInterlock,
    IODirection,
    IOPoint,
    PlannedModule,
    Project,
    ProjectPlan,
    SfcState,
    StateMachineSpec,
    Transition,
)
from app.project import compose
from app.synth import synthesize_st
from app.verifier import verify


def _motor_spec(start: str, stop: str, motor: str) -> StateMachineSpec:
    return StateMachineSpec(
        title="모터 기동/정지",
        io_points=[
            IOPoint(symbol=start, direction=IODirection.INPUT),
            IOPoint(symbol=stop, direction=IODirection.INPUT),
            IOPoint(symbol=motor, direction=IODirection.OUTPUT),
        ],
        states=[
            SfcState(name="IDLE", is_initial=True),
            SfcState(name="RUN", on_entry=[f"{motor} := TRUE;"]),
        ],
        transitions=[
            Transition(from_state="IDLE", to_state="RUN", condition=f"{start} AND NOT {stop}"),
            Transition(from_state="RUN", to_state="IDLE", condition=stop),
        ],
    )


def _two_pump_plan() -> ProjectPlan:
    return ProjectPlan(
        title="펌프 2대 라인",
        modules=[
            PlannedModule(name="pump1", spec=_motor_spec("P1_START", "P1_STOP", "MOTOR")),
            PlannedModule(name="pump2", spec=_motor_spec("P2_START", "P2_STOP", "MOTOR")),
        ],
        cross_interlocks=[
            CrossInterlock(output_a="pump1.MOTOR", output_b="pump2.MOTOR", reason="동시 금지")
        ],
    )


class _FakeStructuredModel:
    """with_structured_output 모델 대역 — 고정 ProjectPlan 을 돌려준다(키 불필요)."""

    def __init__(self, plan: ProjectPlan) -> None:
        self._plan = plan
        self.seen: list[object] = []

    def invoke(self, messages: object) -> ProjectPlan:
        self.seen.append(messages)
        return self._plan


def test_design_project_builds_inline_spec_modules() -> None:
    model = _FakeStructuredModel(_two_pump_plan())
    project = design_project("펌프 두 대, 동시에 돌면 안 돼", model=model)
    assert isinstance(project, Project)
    assert [m.name for m in project.modules] == ["pump1", "pump2"]
    # 인라인 명세 경로(템플릿 아님)
    assert all(m.spec is not None and m.recipe == "" for m in project.modules)
    assert model.seen, "설계 모델이 호출되어야 한다"


def test_designed_project_composes_verifies_and_enforces_cross_interlock() -> None:
    project = design_project("아무거나", model=_FakeStructuredModel(_two_pump_plan()))
    spec = compose(project)
    # 네임스페이스로 두 모듈의 동일 로컬 심볼(MOTOR)이 충돌 없이 분리된다.
    outs = [io.symbol for io in spec.io_points if io.direction == IODirection.OUTPUT]
    assert "pump1__MOTOR" in outs and "pump2__MOTOR" in outs
    st = synthesize_st(spec)
    # 교차 인터락이 합성식에 강제된다.
    assert "AND NOT pump2__MOTOR" in st and "AND NOT pump1__MOTOR" in st
    report = verify(spec, st)
    assert report.passed, report.issues
    assert not any(i.code == "DOUBLE_COIL" for i in report.issues)


def test_plan_to_project_sanitizes_duplicate_and_bad_names() -> None:
    plan = ProjectPlan(
        modules=[
            PlannedModule(name="conv", spec=_motor_spec("A", "B", "M")),
            PlannedModule(name="conv", spec=_motor_spec("C", "D", "M")),  # 중복
            PlannedModule(name="1 bad", spec=_motor_spec("E", "F", "M")),  # 비식별자
        ]
    )
    project = plan_to_project(plan)
    names = [m.name for m in project.modules]
    assert len(names) == len(set(names))  # 충돌 제거
    assert all(n.replace("_", "a").isalnum() for n in names)  # 영문 식별자화


def test_design_project_empty_text_raises() -> None:
    with pytest.raises(ValueError):
        design_project("   ", model=_FakeStructuredModel(_two_pump_plan()))


def test_design_project_empty_plan_raises() -> None:
    empty = _FakeStructuredModel(ProjectPlan(title="x", modules=[]))
    with pytest.raises(ValueError):
        design_project("뭔가", model=empty)


# ── /api/design 엔드포인트 (LLM 은 monkeypatch 로 대체) ───────────────────────
def test_api_design_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.server as server

    monkeypatch.setattr(
        server, "design_project", lambda text: plan_to_project(_two_pump_plan())
    )
    client = TestClient(server.app)
    j = client.post("/api/design", json={"text": "펌프 두 대 동시 금지"}).json()
    assert j["ok"] is True, j.get("verification")
    assert len(j["ladder"]["rungs"]) >= 2
    assert {m["name"] for m in j["modules"]} == {"pump1", "pump2"}
    assert not any(
        i["code"] == "DOUBLE_COIL" for i in j["verification"]["issues"]
    )


def test_api_design_without_llm_is_friendly(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.server as server

    def _boom(text: str) -> Project:
        raise RuntimeError("no api key")

    monkeypatch.setattr(server, "design_project", _boom)
    client = TestClient(server.app)
    j = client.post("/api/design", json={"text": "뭔가"}).json()
    assert j["ok"] is False
    assert "LLM" in (j["error"] or "")
