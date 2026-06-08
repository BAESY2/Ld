"""아날로그 컴파일 프로그램의 수치 시뮬 *행동* 검증 (end-to-end, 히스테리시스 밴드).

frame_to_spec → synthesize_st 로 컴파일한 아날로그 비교기 프로그램을, simulator 의
수치 신호 평가로 가동(0→상승→하강 스윕)해 출력 트레이스가 기대 행동과 일치함을 단정한다.
LLM 호출 없음(전부 결정론) → API 키 불필요·CI 안전.

scripts/analog_sim_bench.py 의 코퍼스도 함께 게이트로 묶어 전 케이스가 통과함을 본다.
"""

from __future__ import annotations

from app.compile_frame import frame_to_spec
from app.simulator import simulate
from app.synth import synthesize_st
from scripts.analog_sim_bench import run_bench


def _trace(text: str, timeline: list[tuple[int, dict[str, bool | float]]],
           *, duration_ms: int, sym: str, step_ms: int = 100) -> list[bool]:
    res = frame_to_spec(text)
    assert res.unresolved == [], f"미해결 절: {res.unresolved}"
    st = synthesize_st(res.spec)
    return simulate(st, timeline, duration_ms=duration_ms,
                    step_ms=step_ms).output_trace(sym)


def test_single_ge_flag_turns_on_above_threshold() -> None:
    """단일 GE: 압력이 임계(5)를 넘는 순간 비교 플래그가 켜진다."""
    trace = _trace(
        "압력 5바 넘으면 경광등 켜",
        [(0, {"PRESSURE": 2.0}), (100, {"PRESSURE": 6.0})],
        duration_ms=100, sym="PRESSURE_GE5",
    )
    assert trace == [False, True]


def test_pressure_hysteresis_band_full_sweep() -> None:
    """히스테리시스 밴드: 펌프가 3바에서 ON, 5바에서 OFF, 4바에서는 직전상태 유지.

    풀 스윕 6→4→2→4→6 으로 *같은 4바*에서 출력이 진행 방향에 따라 달라짐을 본다:
      - 하강 중 4바(idx1): 직전 OFF 유지 → OFF
      - 상승 중 4바(idx3): 직전 ON 유지  → ON
    이것이 밴드(이력) 동작의 핵심 증거다.
    """
    text = "압력 3바 밑으로 떨어지면 펌프 켜고 압력 5바 넘으면 펌프 꺼"
    timeline: list[tuple[int, dict[str, bool | float]]] = [
        (0, {"PRESSURE": 6.0}),    # 5바 이상 → OFF
        (100, {"PRESSURE": 4.0}),  # 밴드(하강) → 직전 OFF 유지
        (200, {"PRESSURE": 2.0}),  # 3바 이하 → ON
        (300, {"PRESSURE": 4.0}),  # 밴드(상승) → 직전 ON 유지
        (400, {"PRESSURE": 6.0}),  # 5바 이상 → OFF
    ]
    pump = _trace(text, timeline, duration_ms=400, sym="PUMP")
    assert pump == [False, False, True, True, False]
    # 밴드 방향성: 같은 4바인데 하강(idx1)=OFF, 상승(idx3)=ON.
    assert pump[1] is False and pump[3] is True


def test_temp_hysteresis_heater_band() -> None:
    """온도 히스테리시스: 히터가 100도 이하에서 ON, 120도 이상에서 OFF, 사이 유지."""
    text = "온도 100도 밑으로 떨어지면 히터 켜고 온도 120도 넘으면 히터 꺼"
    timeline: list[tuple[int, dict[str, bool | float]]] = [
        (0, {"TEMP": 130.0}),   # 120 이상 → OFF
        (100, {"TEMP": 110.0}),  # 밴드(하강) → OFF 유지
        (200, {"TEMP": 90.0}),   # 100 이하 → ON
        (300, {"TEMP": 110.0}),  # 밴드(상승) → ON 유지
        (400, {"TEMP": 130.0}),  # 120 이상 → OFF
    ]
    heater = _trace(text, timeline, duration_ms=400, sym="HEATER")
    assert heater == [False, False, True, True, False]


def test_hysteresis_boundary_values() -> None:
    """경계: 정확히 3바(<=)에서 ON, 정확히 5바(>=)에서 OFF."""
    text = "압력 3바 밑으로 떨어지면 펌프 켜고 압력 5바 넘으면 펌프 꺼"
    timeline: list[tuple[int, dict[str, bool | float]]] = [
        (0, {"PRESSURE": 4.0}),   # 밴드, 초기 OFF
        (100, {"PRESSURE": 3.0}),  # 정확히 3 → ON
        (200, {"PRESSURE": 4.0}),  # 밴드 → ON 유지
        (300, {"PRESSURE": 5.0}),  # 정확히 5 → OFF
    ]
    pump = _trace(text, timeline, duration_ms=300, sym="PUMP")
    assert pump == [False, True, True, False]


def test_determinism_hysteresis() -> None:
    """동일 입력 스윕은 5회 반복해도 같은 트레이스(결정론)."""
    text = "압력 3바 밑으로 떨어지면 펌프 켜고 압력 5바 넘으면 펌프 꺼"
    timeline: list[tuple[int, dict[str, bool | float]]] = [
        (0, {"PRESSURE": 6.0}), (100, {"PRESSURE": 4.0}),
        (200, {"PRESSURE": 2.0}), (300, {"PRESSURE": 4.0}),
    ]
    runs = [_trace(text, timeline, duration_ms=300, sym="PUMP") for _ in range(5)]
    assert all(r == runs[0] for r in runs)


def test_analog_sim_bench_all_pass() -> None:
    """scripts/analog_sim_bench.py 의 전 코퍼스 케이스가 기대 행동과 일치한다."""
    reports = run_bench()
    failed = [(r.name, r.detail) for r in reports if not r.ok]
    assert not failed, f"불일치 케이스: {failed}"
    assert len(reports) >= 10
