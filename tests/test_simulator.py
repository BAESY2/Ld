"""결정론 스캔 시뮬레이터 테스트 — 가상환경 1:1 가동 검증."""

from __future__ import annotations

from app.simulator import _parse_time_ms, simulate
from app.synth import synthesize_st
from app.wizard import build_spec


def test_parse_time() -> None:
    assert _parse_time_ms("T#5s") == 5000
    assert _parse_time_ms("T#500ms") == 500
    assert _parse_time_ms("T#1s") == 1000


def test_seal_in_holds_and_releases() -> None:
    st = synthesize_st(build_spec("motor_start_stop"))
    r = simulate(
        st,
        [(0, {"START": True}), (100, {"START": False}), (500, {"STOP": True})],
        duration_ms=700, step_ms=100,
    )
    trace = r.output_trace("MOTOR")
    assert trace[0] is True            # 시동 즉시 ON
    assert trace[2] is True            # START 떼도 자기유지
    assert trace[-1] is False          # STOP 후 해제


def test_interlock_never_both_on() -> None:
    """정역: 어떤 입력 조합에도 두 모터가 동시에 켜지지 않는다."""
    st = synthesize_st(build_spec("fwd_rev"))
    r = simulate(
        st,
        [(0, {"FWD_PB": True}), (100, {"FWD_PB": False}),
         (300, {"REV_PB": True}), (400, {"REV_PB": False})],
        duration_ms=600, step_ms=50,
    )
    for s in r.samples:
        assert not (s.outputs.get("MOTOR_FWD") and s.outputs.get("MOTOR_REV"))


def test_on_delay_timer_fires_after_preset() -> None:
    st = synthesize_st(build_spec("on_delay", {"delay_sec": "1"}))
    r = simulate(st, [(0, {"START": True})], duration_ms=1500, step_ms=250)
    assert r.output_trace("OUTPUT")[0] is False   # 즉시는 아님
    assert r.output_trace("OUTPUT")[-1] is True    # 1초 이후 ON


def test_counter_fires_after_n_pulses() -> None:
    st = synthesize_st(build_spec("count_eject", {"count": "3"}))
    ev: list[tuple[int, dict[str, bool]]] = []
    for t in (0, 200, 400):
        ev += [(t, {"PART_SENSOR": True}), (t + 100, {"PART_SENSOR": False})]
    r = simulate(st, ev, duration_ms=800, step_ms=100)
    assert r.output_trace("EJECT")[0] is False
    assert r.output_trace("EJECT")[-1] is True     # 3개 후 배출


def test_timed_sequencer_one_hot() -> None:
    """세차 시퀀스: 항상 한 단계 출력만 켜져 있다(one-hot)."""
    st = synthesize_st(build_spec("car_wash", {"t1": "1", "t2": "1", "t3": "1"}))
    r = simulate(st, [(0, {"START": True}), (100, {"START": False})],
                 duration_ms=4000, step_ms=100)
    for s in r.samples:
        on = [k for k, v in s.outputs.items() if v]
        assert len(on) <= 1, f"동시 다중 출력 @ {s.t_ms}ms: {on}"
    # 마지막 단계까지 도달
    assert any(s.outputs.get("DRY") for s in r.samples)


def test_estop_drops_output() -> None:
    st = synthesize_st(build_spec("motor_start_stop"))
    r = simulate(st, [(0, {"START": True}), (100, {"START": False})],
                 duration_ms=300, step_ms=100)
    assert all(s.outputs.get("MOTOR") for s in r.samples)  # STOP 없으면 계속 ON
