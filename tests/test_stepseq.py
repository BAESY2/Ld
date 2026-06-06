"""정수 스텝-레지스터 시퀀서 합성기(app/stepseq.py) 테스트.

핵심 보장(시뮬레이터로 가동·검증):
  - one-hot 불변: 어떤 스캔에서도 동시에 2개 이상 스텝이 활성이 아니다.
  - 출력 정합성: 각 출력은 그 출력을 켜는 on_entry 스텝에서만 ON.
  - 이중코일 0: 합성 ST 의 detect_double_coils 결과가 비어있다.
  - 결정론: 같은 명세 → 동일 ST(반복 2회).
"""

from __future__ import annotations

from app.memory_map import detect_double_coils
from app.models import (
    IODirection,
    IOPoint,
    SfcState,
    StateMachineSpec,
    Transition,
)
from app.simulator import simulate
from app.stepseq import (
    is_sequential,
    step_driven_outputs,
    synthesize_step_st,
)

# 모든 STEP_Sx one-hot 플래그를 시뮬레이터 출력에서 추려낼 접두사.
_STEP_PREFIX = "STEP_S"


def _three_step_spec() -> StateMachineSpec:
    """3-스텝 순차 명세: IDLE → A → B → IDLE.

    A 에서 OUT_A, B 에서 OUT_B 가 켜진다(IDLE 은 출력 없음).
    """
    return StateMachineSpec(
        title="3-step sequential fixture",
        io_points=[
            IOPoint(symbol="GO", direction=IODirection.INPUT),
            IOPoint(symbol="NEXT", direction=IODirection.INPUT),
            IOPoint(symbol="DONE", direction=IODirection.INPUT),
            IOPoint(symbol="OUT_A", direction=IODirection.OUTPUT),
            IOPoint(symbol="OUT_B", direction=IODirection.OUTPUT),
        ],
        states=[
            SfcState(name="IDLE", is_initial=True),
            SfcState(name="A", on_entry=["OUT_A := TRUE;"]),
            SfcState(name="B", on_entry=["OUT_B := TRUE;"]),
        ],
        transitions=[
            Transition(from_state="IDLE", to_state="A", condition="GO"),
            Transition(from_state="A", to_state="B", condition="NEXT"),
            Transition(from_state="B", to_state="IDLE", condition="DONE"),
        ],
    )


def _step_flags_on(sample_outputs: dict[str, bool]) -> list[str]:
    return [
        k
        for k, v in sample_outputs.items()
        if v and k.startswith(_STEP_PREFIX) and not k.startswith("STEP_PREV")
    ]


def test_is_sequential_detects_linear_chain() -> None:
    assert is_sequential(_three_step_spec()) is True


def test_is_sequential_rejects_branch() -> None:
    """같은 from 에서 2개 출구(분기) → 시퀀서 부적합."""
    spec = StateMachineSpec(
        io_points=[
            IOPoint(symbol="X", direction=IODirection.INPUT),
            IOPoint(symbol="Y", direction=IODirection.INPUT),
        ],
        states=[
            SfcState(name="S0", is_initial=True),
            SfcState(name="S1"),
            SfcState(name="S2"),
        ],
        transitions=[
            Transition(from_state="S0", to_state="S1", condition="X"),
            Transition(from_state="S0", to_state="S2", condition="Y"),
        ],
    )
    assert is_sequential(spec) is False


def test_is_sequential_rejects_single_state() -> None:
    spec = StateMachineSpec(states=[SfcState(name="ONLY", is_initial=True)])
    assert is_sequential(spec) is False


def test_one_hot_invariant_over_timeline() -> None:
    """가동 타임라인 전 구간에서 동시에 2개 이상 스텝이 활성이 아니다."""
    st = synthesize_step_st(_three_step_spec())
    r = simulate(
        st,
        [
            (0, {"GO": True}),
            (100, {"GO": False}),
            (300, {"NEXT": True}),
            (400, {"NEXT": False}),
            (600, {"DONE": True}),
            (700, {"DONE": False}),
        ],
        duration_ms=1000,
        step_ms=50,
    )
    for s in r.samples:
        on = _step_flags_on(s.outputs)
        assert len(on) <= 1, f"@ {s.t_ms}ms 동시 다중 스텝: {on}"
    # 시퀀스가 실제로 한 스텝 이상 진행했는지(자명한 통과 방지)
    assert any(_step_flags_on(s.outputs) for s in r.samples)


def test_initial_step_active_at_powerup() -> None:
    """첫 스캔(입력 없음)에서 초기 스텝이 정확히 1개 활성이다."""
    st = synthesize_step_st(_three_step_spec())
    r = simulate(st, [], duration_ms=200, step_ms=100)
    first = r.samples[0]
    on = _step_flags_on(first.outputs)
    assert on == ["STEP_S0"], f"부팅 시 초기 스텝 단일 활성 기대, 실제={on}"


def test_output_matches_on_entry_steps() -> None:
    """OUT_A 는 스텝 A 구간에서만, OUT_B 는 스텝 B 구간에서만 ON."""
    st = synthesize_step_st(_three_step_spec())
    r = simulate(
        st,
        [
            (0, {"GO": True}),
            (100, {"GO": False}),
            (300, {"NEXT": True}),
            (400, {"NEXT": False}),
            (600, {"DONE": True}),
            (700, {"DONE": False}),
        ],
        duration_ms=1000,
        step_ms=50,
    )
    saw_a = saw_b = False
    for s in r.samples:
        on = _step_flags_on(s.outputs)
        active = on[0] if on else None
        # OUT_A 는 STEP_S1(=A), OUT_B 는 STEP_S2(=B) 일 때만 켜져야 한다.
        assert s.outputs.get("OUT_A", False) == (active == "STEP_S1")
        assert s.outputs.get("OUT_B", False) == (active == "STEP_S2")
        saw_a = saw_a or s.outputs.get("OUT_A", False)
        saw_b = saw_b or s.outputs.get("OUT_B", False)
    assert saw_a and saw_b, "OUT_A/OUT_B 둘 다 한 번씩은 켜져야 한다(시퀀스 진행 확인)"


def test_zero_double_coils() -> None:
    st = synthesize_step_st(_three_step_spec())
    assert detect_double_coils(st) == {}


def test_determinism_identical_st() -> None:
    spec = _three_step_spec()
    assert synthesize_step_st(spec) == synthesize_step_st(spec)


def test_step_driven_outputs() -> None:
    assert step_driven_outputs(_three_step_spec()) == {"OUT_A", "OUT_B"}


def test_traffic_light_three_phase_one_hot() -> None:
    """신호등(GREEN→YELLOW→RED→GREEN) 도 one-hot·출력정합 유지."""
    spec = StateMachineSpec(
        title="traffic light",
        io_points=[
            IOPoint(symbol="T_G", direction=IODirection.INPUT),
            IOPoint(symbol="T_Y", direction=IODirection.INPUT),
            IOPoint(symbol="T_R", direction=IODirection.INPUT),
            IOPoint(symbol="GREEN", direction=IODirection.OUTPUT),
            IOPoint(symbol="YELLOW", direction=IODirection.OUTPUT),
            IOPoint(symbol="RED", direction=IODirection.OUTPUT),
        ],
        states=[
            SfcState(name="G", is_initial=True, on_entry=["GREEN := TRUE;"]),
            SfcState(name="Y", on_entry=["YELLOW := TRUE;"]),
            SfcState(name="R", on_entry=["RED := TRUE;"]),
        ],
        transitions=[
            Transition(from_state="G", to_state="Y", condition="T_G"),
            Transition(from_state="Y", to_state="R", condition="T_Y"),
            Transition(from_state="R", to_state="G", condition="T_R"),
        ],
    )
    assert is_sequential(spec)
    st = synthesize_step_st(spec)
    assert detect_double_coils(st) == {}
    r = simulate(
        st,
        [
            (0, {"T_G": True}),
            (100, {"T_G": False}),
            (300, {"T_Y": True}),
            (400, {"T_Y": False}),
        ],
        duration_ms=600,
        step_ms=50,
    )
    for s in r.samples:
        lights = [
            k for k in ("GREEN", "YELLOW", "RED") if s.outputs.get(k, False)
        ]
        assert len(lights) == 1, f"@ {s.t_ms}ms 신호등 동시 점등: {lights}"
