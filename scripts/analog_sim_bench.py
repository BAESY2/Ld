#!/usr/bin/env python3
"""아날로그 비교기 컴파일 프로그램의 *수치 시뮬* 행동 검증 벤치 (W1.3 활용).

자연어(한국어) 아날로그 지시를 ``frame_to_spec`` → ``synthesize_st`` 로 컴파일한 뒤,
*수치 타임라인*(신호를 0→상승→하강 스윕)으로 ``simulate`` 해서 출력/플래그 트레이스가
*기대 행동*과 정확히 일치하는지 대조한다. LLM 호출 없음(전부 결정론).

검증 대상 행동:
  - 단일 GE/LE: 신호가 임계를 넘/밑돌면 비교 플래그(및 그에 묶인 출력)가 켜진다.
  - 히스테리시스 밴드: '3바 밑으로 떨어지면 켜고 5바 넘으면 꺼'
    → 3바 이하에서 ON, 5바 이상에서 OFF, *그 사이(밴드)에서는 직전 상태 유지*.
    상승/하강 스윕으로 같은 4바에서 출력이 *진행 방향에 따라* 달라짐을 확인한다.

각 케이스는 기대 트레이스를 코드에 명시하고(아래 CASES), 실제 시뮬 트레이스와 대조한다.
전부 통과면 0, 하나라도 불일치면 1을 반환한다(직접 실행 가능).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from app.compile_frame import frame_to_spec
from app.simulator import simulate
from app.synth import synthesize_st

# 한 케이스의 입력 타임라인 한 점: (시각ms, {심볼: 불리언|수치}).
Event = tuple[int, Mapping[str, bool | float]]


@dataclass(frozen=True)
class AnalogCase:
    """아날로그 시뮬 검증 케이스 — 한국어 지시 → 기대 출력 트레이스."""

    name: str
    text: str  # 한국어 아날로그 지시
    timeline: Sequence[Event]
    duration_ms: int
    # {출력심볼: 기대 불리언 트레이스} — 비교 플래그·구동 출력 모두 가능.
    expected: Mapping[str, list[bool]]
    step_ms: int = 100
    note: str = ""
    # (선택) 기대 수치 신호 트레이스 — 아날로그 입력이 의도대로 흐르는지 확인.
    expected_signals: Mapping[str, list[float]] = field(default_factory=dict)


# ── 코퍼스: 단일 임계(GE/LE) + 히스테리시스 밴드(압력/온도) ────────────────────
CASES: list[AnalogCase] = [
    # 1) 단일 GE: 온도가 200도 되면 팬 ON(자기유지).
    AnalogCase(
        name="single_ge_temp_fan",
        text="온도 200도 되면 팬 켜",
        timeline=[(0, {"TEMP": 100.0}), (100, {"TEMP": 250.0})],
        duration_ms=100,
        expected={"TEMP_GE200": [False, True], "FAN": [False, True]},
        note="임계(200) 도달 시 비교 플래그 ON → 팬 ON.",
    ),
    # 2) 단일 GE 플래그 자기유지: 압력 5바 넘으면 경광등 ON, 떨어져도 유지.
    AnalogCase(
        name="single_ge_beacon_latch",
        text="압력 5바 넘으면 경광등 켜",
        timeline=[(0, {"PRESSURE": 2.0}), (100, {"PRESSURE": 6.0}),
                  (200, {"PRESSURE": 1.0})],
        duration_ms=200,
        expected={
            "PRESSURE_GE5": [False, True, False],  # 플래그는 조합(신호 따라감)
            "BEACON": [False, True, True],          # 출력은 OFF 트리거 없어 래치
        },
        note="플래그는 신호를 따라가지만, OFF 트리거 없는 출력은 한 번 켜지면 유지.",
    ),
    # 3) 단일 GE 임계 경계: 정확히 5.0 이면 GE(>=) 는 ON.
    AnalogCase(
        name="single_ge_boundary_on",
        text="압력 5바 넘으면 경광등 켜",
        timeline=[(0, {"PRESSURE": 4.9}), (100, {"PRESSURE": 5.0})],
        duration_ms=100,
        expected={"PRESSURE_GE5": [False, True]},
        note="경계값 5.0 에서 GE 플래그 ON(>= 의미).",
    ),
    # 4) 단일 LE: 압력 3바 밑으로 떨어지면 밸브 열림.
    AnalogCase(
        name="single_le_valve",
        text="압력 3바 밑으로 떨어지면 밸브 열어",
        timeline=[(0, {"PRESSURE": 5.0}), (100, {"PRESSURE": 2.0})],
        duration_ms=100,
        expected={"PRESSURE_LE3": [False, True], "VALVE": [False, True]},
        note="신호가 임계(3) 이하로 떨어지면 LE 플래그 ON → 밸브 OPEN.",
    ),
    # 5) 혼합(불리언+아날로그): 버튼으로 펌프 시동(자기유지), 5바 넘으면 OFF.
    AnalogCase(
        name="mixed_button_pump_pressure_off",
        text="버튼 누르면 펌프 켜고 압력이 5바 넘으면 펌프 꺼",
        timeline=[(0, {"START": True}), (100, {"START": False}),
                  (300, {"PRESSURE": 6.0})],
        duration_ms=500,
        expected={
            "PUMP": [True, True, True, False, False, False],
            "PRESSURE_GE5": [False, False, False, True, True, True],
        },
        note="START 자기유지, 압력 5바 초과 시 트립(OFF).",
    ),
    # 6) 혼합 거짓트립 없음: 임계 미만 압력만 변하면 펌프 계속 ON.
    AnalogCase(
        name="mixed_no_false_trip",
        text="버튼 누르면 펌프 켜고 압력이 5바 넘으면 펌프 꺼",
        timeline=[(0, {"START": True}),
                  (100, {"START": False, "PRESSURE": 4.0})],
        duration_ms=300,
        expected={"PUMP": [True, True, True, True]},
        note="임계(5) 미만 압력에서는 트립되면 안 된다.",
    ),
    # 7) 혼합 온도: 버튼 누르면 히터 켜고 80도 되면 OFF.
    AnalogCase(
        name="mixed_button_heater_temp_off",
        text="버튼 누르면 히터 켜고 온도 80도 되면 히터 꺼",
        timeline=[(0, {"START": True}), (100, {"START": False}),
                  (200, {"TEMP": 85.0})],
        duration_ms=300,
        expected={
            "HEATER": [True, True, False, False],
            "TEMP_GE80": [False, False, True, True],
        },
        note="히터 자기유지, 목표온도 도달 시 OFF.",
    ),
    # 8) 히스테리시스 밴드(압력) — 하강 스윕: 6→4→2.
    #    6: GE5 로 OFF, 4: 밴드(직전 OFF 유지), 2: LE3 로 ON.
    AnalogCase(
        name="hysteresis_pressure_falling",
        text="압력 3바 밑으로 떨어지면 펌프 켜고 압력 5바 넘으면 펌프 꺼",
        timeline=[(0, {"PRESSURE": 6.0}), (100, {"PRESSURE": 4.0}),
                  (200, {"PRESSURE": 2.0})],
        duration_ms=200,
        expected={
            "PUMP": [False, False, True],
            "PRESSURE_LE3": [False, False, True],
            "PRESSURE_GE5": [True, False, False],
        },
        note="하강 스윕: 4바(밴드)에서는 직전 OFF 를 유지, 3바 이하에서 ON.",
    ),
    # 9) 히스테리시스 밴드(압력) — 상승 스윕: 2→4→6.
    #    2: LE3 로 ON, 4: 밴드(직전 ON 유지), 6: GE5 로 OFF.
    AnalogCase(
        name="hysteresis_pressure_rising",
        text="압력 3바 밑으로 떨어지면 펌프 켜고 압력 5바 넘으면 펌프 꺼",
        timeline=[(0, {"PRESSURE": 2.0}), (100, {"PRESSURE": 4.0}),
                  (200, {"PRESSURE": 6.0})],
        duration_ms=200,
        expected={
            "PUMP": [True, True, False],
            "PRESSURE_LE3": [True, False, False],
            "PRESSURE_GE5": [False, False, True],
        },
        note="상승 스윕: 4바(밴드)에서는 직전 ON 을 유지, 5바 이상에서 OFF.",
    ),
    # 10) 히스테리시스 밴드(압력) — 풀 스윕으로 밴드의 방향성 직접 대조.
    #     6(OFF)→4(OFF,하강)→2(ON)→4(ON,상승)→6(OFF). 같은 4바, 다른 출력.
    AnalogCase(
        name="hysteresis_pressure_band_sweep",
        text="압력 3바 밑으로 떨어지면 펌프 켜고 압력 5바 넘으면 펌프 꺼",
        timeline=[(0, {"PRESSURE": 6.0}), (100, {"PRESSURE": 4.0}),
                  (200, {"PRESSURE": 2.0}), (300, {"PRESSURE": 4.0}),
                  (400, {"PRESSURE": 6.0})],
        duration_ms=400,
        expected={"PUMP": [False, False, True, True, False]},
        expected_signals={"PRESSURE": [6.0, 4.0, 2.0, 4.0, 6.0]},
        note="동일 4바에서 하강 시 OFF(idx1)·상승 시 ON(idx3) → 진정한 밴드(방향 의존).",
    ),
    # 11) 히스테리시스 밴드(온도) — 풀 스윕: 130→110→90→110→130.
    AnalogCase(
        name="hysteresis_temp_band_sweep",
        text="온도 100도 밑으로 떨어지면 히터 켜고 온도 120도 넘으면 히터 꺼",
        timeline=[(0, {"TEMP": 130.0}), (100, {"TEMP": 110.0}),
                  (200, {"TEMP": 90.0}), (300, {"TEMP": 110.0}),
                  (400, {"TEMP": 130.0})],
        duration_ms=400,
        expected={
            "HEATER": [False, False, True, True, False],
            "TEMP_LE100": [False, False, True, False, False],
            "TEMP_GE120": [True, False, False, False, True],
        },
        note="온도 밴드(100~120): 110도에서 하강 OFF·상승 ON 으로 방향 의존.",
    ),
    # 12) 히스테리시스 밴드 경계: 임계 정확히 같은 값에서의 ON/OFF.
    #     3.0 → LE3 ON, 5.0 → GE5 OFF.
    AnalogCase(
        name="hysteresis_boundary",
        text="압력 3바 밑으로 떨어지면 펌프 켜고 압력 5바 넘으면 펌프 꺼",
        timeline=[(0, {"PRESSURE": 4.0}), (100, {"PRESSURE": 3.0}),
                  (200, {"PRESSURE": 4.0}), (300, {"PRESSURE": 5.0})],
        duration_ms=300,
        expected={"PUMP": [False, True, True, False]},
        note="경계: 정확히 3바(<=)에서 ON, 정확히 5바(>=)에서 OFF.",
    ),
]


@dataclass
class CaseReport:
    name: str
    ok: bool
    detail: str


def _run_case(case: AnalogCase) -> CaseReport:
    """한 케이스를 컴파일→합성→수치 시뮬 후 기대 트레이스와 대조."""
    res = frame_to_spec(case.text)
    if res.unresolved:
        return CaseReport(case.name, False, f"미해결 절: {res.unresolved}")
    st = synthesize_st(res.spec)
    sim = simulate(st, case.timeline, duration_ms=case.duration_ms,
                   step_ms=case.step_ms)
    mismatches: list[str] = []
    for sym, want in case.expected.items():
        got = sim.output_trace(sym)
        if got != want:
            mismatches.append(f"{sym}: 기대 {want} != 실제 {got}")
    for sym, want_sig in case.expected_signals.items():
        got_sig = sim.signal_trace(sym)
        if got_sig != want_sig:
            mismatches.append(f"{sym}(신호): 기대 {want_sig} != 실제 {got_sig}")
    if mismatches:
        return CaseReport(case.name, False, "; ".join(mismatches))
    return CaseReport(case.name, True, case.note)


def run_bench() -> list[CaseReport]:
    """전 케이스를 결정론적으로 실행해 케이스별 보고를 돌려준다."""
    return [_run_case(c) for c in CASES]


def main() -> int:
    reports = run_bench()
    passed = sum(1 for r in reports if r.ok)
    print(f"아날로그 수치 시뮬 벤치 — {passed}/{len(reports)} 통과\n")
    for r in reports:
        mark = "OK " if r.ok else "FAIL"
        print(f"[{mark}] {r.name}: {r.detail}")
    print()
    if passed == len(reports):
        print("모든 아날로그 비교기/히스테리시스 밴드 행동이 기대와 일치합니다.")
        return 0
    print(f"{len(reports) - passed}건 불일치 — 위 FAIL 항목 확인 요망.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
