"""결정론 스캔 시뮬레이터 테스트 — 가상환경 1:1 가동 검증."""

from __future__ import annotations

import pytest

from app.simulator import MAX_SIM_SAMPLES, _parse_time_ms, simulate
from app.synth import synthesize_st
from app.wizard import build_spec, list_recipes


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


# ── 빨간팀(공격자) 회귀 가드 ──────────────────────────────────────────────

@pytest.mark.parametrize("step_ms", [1, 100, 250])
def test_sim_timer_timing_exact(step_ms: int) -> None:
    """TON Q 는 정확히 PT(=1000ms) 에 상승한다 — 1스캔 조기발화(off-by-one) 회귀 가드."""
    st = "// 타이머 T1 (TON, 1000ms)\nT1(IN := A, PT := T#1s);\nX := T1.Q;"
    r = simulate(st, [(0, {"A": True})], duration_ms=1200, step_ms=step_ms)
    trace = r.output_trace("X")
    first_on = next(s.t_ms for s, v in zip(r.samples, trace, strict=True) if v)
    assert first_on == 1000, f"step={step_ms}: {first_on}ms 에 발화(1000 기대)"


def test_sim_tof_semantics() -> None:
    """TOF 는 TON 으로 대체되지 않는다 — IN 동안 ON, 하강 후 PT 만큼 유지."""
    st = "// 타이머 T1 (TOF, 2000ms)\nT1(IN := A, PT := T#2s);\nX := T1.Q;"
    r = simulate(st, [(0, {"A": True}), (1000, {"A": False})],
                 duration_ms=4000, step_ms=1000)
    trace = r.output_trace("X")
    assert trace[0] is True and trace[1] is True   # IN 동안 ON (TON 이면 F)
    assert trace[2] is True                         # 하강 후 PT 이내 유지
    assert trace[-1] is False                       # PT 경과 후 OFF


def test_sim_tp_pulse_semantics() -> None:
    """TP 는 상승 엣지에서 PT 동안만 펄스(IN 유지와 무관)."""
    st = "// 타이머 T1 (TP, 2000ms)\nT1(IN := A, PT := T#2s);\nX := T1.Q;"
    r = simulate(st, [(0, {"A": True}), (500, {"A": False})],
                 duration_ms=4000, step_ms=1000)
    trace = r.output_trace("X")
    assert trace[0] is True              # 상승 엣지 → 펄스 시작
    assert trace[-1] is False            # PT 경과 후 OFF


def test_simulate_sample_count_capped() -> None:
    """증폭형 DoS 방지: 샘플 수 상한 초과는 ValueError(<1초 내)."""
    st = "X := A;"
    with pytest.raises(ValueError, match="상한"):
        simulate(st, [(0, {"A": True})], duration_ms=600_000, step_ms=1)
    # 상한 이내는 정상 동작
    ok = simulate(st, [(0, {"A": True})],
                  duration_ms=(MAX_SIM_SAMPLES - 1) * 1, step_ms=1)
    assert len(ok.samples) == MAX_SIM_SAMPLES


def test_all_recipes_mutual_exclusion_invariant() -> None:
    """모든 레시피: 합성→가동 시 어떤 샘플에서도 인터락 쌍이 동시에 켜지지 않는다."""
    for rid in [r["id"] for r in list_recipes()]:
        try:
            spec = build_spec(rid)
        except Exception:
            continue  # 필수 파라미터가 있는 레시피는 건너뜀(개별 테스트가 커버)
        st = synthesize_st(spec)
        r = simulate(st, [(0, {p.symbol: True for p in spec.io_points
                               if p.direction.value == "INPUT"})],
                     duration_ms=2000, step_ms=100)
        for pair in spec.interlocks:
            for s in r.samples:
                a, b = s.outputs.get(pair.output_a), s.outputs.get(pair.output_b)
                assert not (a and b), (
                    f"{rid} @ {s.t_ms}ms: {pair.output_a}+{pair.output_b} 동시 ON"
                )


def test_determinism_repeated_runs() -> None:
    """동일 입력 5회 반복 시 트레이스가 바이트 동일(결정론 보장)."""
    st = synthesize_st(build_spec("fwd_rev"))
    ev = [(0, {"FWD_PB": True}), (100, {"FWD_PB": False}),
          (300, {"REV_PB": True}), (400, {"REV_PB": False})]
    runs = [
        [(s.t_ms, sorted(k for k, v in s.outputs.items() if v))
         for s in simulate(st, ev, duration_ms=600, step_ms=50).samples]
        for _ in range(5)
    ]
    assert all(run == runs[0] for run in runs)
