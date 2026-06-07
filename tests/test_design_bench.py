"""설계 경로 벤치 하니스 회귀 가드 — 키 없이 mock 모델 팩토리로 채점 로직을 고정한다.

실제 LLM 품질은 키가 있어야 측정되지만, *하니스가 올바로 집계하는지*(게이트 통과/차단/
폐루프 횟수/위반 집계)는 여기서 결정론적으로 박아둔다. 키를 꽂으면 동일 채점기가 실측한다.
"""

from __future__ import annotations

from app.bench import score_design
from app.models import IODirection, IOPoint, PlannedModule, ProjectPlan, SfcState, StateMachineSpec

# (text, expected, why) — score_design 은 expected/why 를 쓰지 않으므로 더미로 채운다.
_CORPUS: list[tuple[str, str | None, str]] = [
    ("모터 돌리기", None, ""),
    ("펌프 제어", None, ""),
    ("경고등", None, ""),
]


def _good_plan() -> ProjectPlan:
    spec = StateMachineSpec(
        io_points=[
            IOPoint(symbol="START", direction=IODirection.INPUT),
            IOPoint(symbol="STOP", direction=IODirection.INPUT),
            IOPoint(symbol="MOTOR", direction=IODirection.OUTPUT),
        ],
        states=[
            SfcState(name="IDLE", is_initial=True),
            SfcState(name="RUN", on_entry=["MOTOR := TRUE;"]),
        ],
        transitions=[
            {"from_state": "IDLE", "to_state": "RUN", "condition": "START AND NOT STOP"},
            {"from_state": "RUN", "to_state": "IDLE", "condition": "STOP"},
        ],
    )
    return ProjectPlan(title="ok", modules=[PlannedModule(name="m", spec=spec)])


def _bad_plan() -> ProjectPlan:
    # 초기 상태 없음 → verify DEADLOCK error → 게이트 차단(폐루프가 못 고침).
    spec = StateMachineSpec(
        io_points=[
            IOPoint(symbol="BTN", direction=IODirection.INPUT),
            IOPoint(symbol="M", direction=IODirection.OUTPUT),
        ],
        states=[SfcState(name="RUN", on_entry=["M := TRUE;"])],
        transitions=[],
    )
    return ProjectPlan(title="bad", modules=[PlannedModule(name="m", spec=spec)])


class _FixedModel:
    def __init__(self, plan: ProjectPlan) -> None:
        self._plan = plan

    def invoke(self, _messages: object) -> ProjectPlan:
        return self._plan


def test_all_pass_tally() -> None:
    r = score_design(_CORPUS, model_factory=lambda: _FixedModel(_good_plan()))
    assert r.n == 3
    assert r.gate_pass == 3
    assert r.pass_rate == 1.0
    assert r.gate_blocked == 0 and r.synth_error == 0 and r.llm_error == 0
    assert r.total_revisions == 0          # 1발에 통과 → 재설계 0
    assert r.double_coil_total == 0        # 채택분 위반은 항상 0이어야
    assert r.interlock_violation_total == 0


def test_all_gate_blocked_counts_loop_revisions() -> None:
    r = score_design(
        _CORPUS, model_factory=lambda: _FixedModel(_bad_plan()), max_revisions=2
    )
    assert r.gate_blocked == 3 and r.gate_pass == 0
    assert r.pass_rate == 0.0
    # 케이스마다 폐루프가 max_revisions 까지 돌고 포기 → 총 3*2.
    assert r.total_revisions == 6
    assert r.mean_revisions == 2.0


def test_llm_error_is_counted_honestly() -> None:
    class _Boom:
        def invoke(self, _messages: object) -> ProjectPlan:
            raise RuntimeError("no key")

    r = score_design(_CORPUS, model_factory=lambda: _Boom())
    assert r.llm_error == 3 and r.gate_pass == 0


def test_score_design_is_deterministic() -> None:
    f = lambda: _FixedModel(_good_plan())  # noqa: E731
    assert score_design(_CORPUS, model_factory=f) == score_design(_CORPUS, model_factory=f)


def test_report_renders_key_metrics() -> None:
    r = score_design(_CORPUS, model_factory=lambda: _FixedModel(_good_plan()))
    txt = r.report()
    assert "게이트 통과" in txt and "100%" in txt
