"""아날로그 비교기 수치 평가 시뮬레이터 테스트 (W1.3).

합성기가 만든 비교기 원자('SIG op NUM' → Var("SIG>=5"))를 시뮬레이터가 *수치 신호값*
으로 평가해 비교 플래그/출력을 정확히 켜는지 검증한다. 또한 기존 불리언 전용 호출이
100% 그대로 동작하는지(하위호환)도 함께 본다. LLM 호출 없음 → 키 불필요·CI 안전.
"""

from __future__ import annotations

import pytest

from app.compile_frame import frame_to_spec
from app.simulator import (
    _Compare,
    _eval_compare,
    _parse_compare,
    simulate,
)
from app.synth import synthesize_st

# ── 비교 원자 파서(이름 → signal/op/threshold) ──────────────────────────────


def test_parse_compare_all_ops() -> None:
    assert _parse_compare("PRESSURE>=5") == _Compare("PRESSURE", ">=", 5.0)
    assert _parse_compare("TEMP<=3.2") == _Compare("TEMP", "<=", 3.2)
    assert _parse_compare("X>10") == _Compare("X", ">", 10.0)
    assert _parse_compare("X<10") == _Compare("X", "<", 10.0)
    assert _parse_compare("X=7") == _Compare("X", "=", 7.0)
    assert _parse_compare("X<>7") == _Compare("X", "<>", 7.0)
    # 점표기 멤버(아날로그가 FB 멤버일 가능성)도 신호로 인정
    assert _parse_compare("AI.VAL>=5") == _Compare("AI.VAL", ">=", 5.0)


def test_parse_compare_rejects_non_comparison() -> None:
    # 일반 불리언 변수는 비교 원자가 아니다 → None (하위호환의 핵심)
    assert _parse_compare("START") is None
    assert _parse_compare("MOTOR") is None
    assert _parse_compare("T1.Q") is None


def test_op_does_not_swallow() -> None:
    # ">" 가 ">=" 를 가로채면 안 된다(길이순 매칭).
    c = _parse_compare("P>=5")
    assert c is not None and c.op == ">=" and c.threshold == 5.0


def test_eval_compare_numeric() -> None:
    tbl = {"PRESSURE": 6.0}
    assert _eval_compare(_Compare("PRESSURE", ">=", 5.0), tbl) is True
    assert _eval_compare(_Compare("PRESSURE", "<", 5.0), tbl) is False
    # 미지정 신호는 0 으로 간주
    assert _eval_compare(_Compare("LEVEL", ">=", 1.0), {}) is False
    # 불리언 입력이 비교 신호로 쓰이면 True→1.0
    assert _eval_compare(_Compare("FLAG", ">=", 1.0), {"FLAG": True}) is True


# ── 핵심 시나리오: 압력 0→6→2 → 플래그 ON@6, OFF@2 ─────────────────────────


def test_pressure_threshold_flag_on_off() -> None:
    st = "PRESSURE_GE5 := PRESSURE >= 5;"
    r = simulate(
        st,
        [(0, {"PRESSURE": 0.0}), (100, {"PRESSURE": 6.0}), (200, {"PRESSURE": 2.0})],
        duration_ms=200,
        step_ms=100,
    )
    assert r.signals == ["PRESSURE"]
    assert r.inputs == []  # 비교 원자는 입력 심볼로 노출되지 않는다
    assert r.output_trace("PRESSURE_GE5") == [False, True, False]
    assert r.signal_trace("PRESSURE") == [0.0, 6.0, 2.0]


def test_integer_timeline_values_accepted() -> None:
    # int 도 수치 입력으로 받는다(float 강제 변환).
    st = "HOT := TEMP > 80;"
    r = simulate(
        st,
        [(0, {"TEMP": 20}), (100, {"TEMP": 90})],
        duration_ms=100,
        step_ms=100,
    )
    assert r.output_trace("HOT") == [False, True]


def test_threshold_boundary_ge_vs_gt() -> None:
    # 임계 정확히 같을 때: GE 는 ON, GT 는 OFF.
    r_ge = simulate("F := S >= 5;", [(0, {"S": 5.0})], duration_ms=0, step_ms=100)
    r_gt = simulate("F := S > 5;", [(0, {"S": 5.0})], duration_ms=0, step_ms=100)
    assert r_ge.output_trace("F") == [True]
    assert r_gt.output_trace("F") == [False]


def test_le_comparison() -> None:
    # 하한: 수위가 2 이하면 ON.
    st = "LOW := LEVEL <= 2;"
    r = simulate(
        st,
        [(0, {"LEVEL": 5.0}), (100, {"LEVEL": 1.0})],
        duration_ms=100,
        step_ms=100,
    )
    assert r.output_trace("LOW") == [False, True]


# ── end-to-end: 컴파일러(frame_to_spec) 산출 아날로그 프로그램을 수치로 가동 ──


def test_e2e_pressure_pump_off() -> None:
    """'버튼 누르면 펌프 켜고 압력 5바 넘으면 펌프 꺼' → 6바에서 펌프 OFF.

    불리언 입력(START)과 아날로그 신호(PRESSURE)가 한 프로그램에 섞인 혼합 시나리오.
    """
    res = frame_to_spec("버튼 누르면 펌프 켜고 압력이 5바 넘으면 펌프 꺼")
    assert res.unresolved == []
    spec = res.spec
    # 컴파일러가 PRESSURE 비교기와 PUMP 출력을 만들었는지
    assert any(c.signal == "PRESSURE" and c.threshold == 5.0 for c in spec.comparators)
    st = synthesize_st(spec)

    r = simulate(
        st,
        [
            (0, {"START": True}),       # 펌프 시동
            (100, {"START": False}),    # 버튼 떼도 자기유지
            (300, {"PRESSURE": 6.0}),   # 5바 초과 → 비교 플래그 ON → 펌프 OFF
        ],
        duration_ms=500,
        step_ms=100,
    )
    flag = next(c.flag for c in spec.comparators if c.signal == "PRESSURE")
    pump = r.output_trace("PUMP")
    # 시동 후 자기유지(START 떼도 ON)
    assert pump[0] is True and pump[1] is True and pump[2] is True
    # 6바 도달 시점부터 펌프 OFF
    assert pump[3] is False and pump[-1] is False
    # 비교 플래그가 6바부터 켜짐
    assert r.output_trace(flag) == [False, False, False, True, True, True]


def test_e2e_pump_stays_on_below_threshold() -> None:
    """압력이 임계 미만으로만 변하면 펌프는 계속 ON(거짓 트립 없음)."""
    spec = frame_to_spec("버튼 누르면 펌프 켜고 압력이 5바 넘으면 펌프 꺼").spec
    st = synthesize_st(spec)
    r = simulate(
        st,
        [(0, {"START": True}), (100, {"START": False, "PRESSURE": 4.0})],
        duration_ms=300,
        step_ms=100,
    )
    assert all(r.output_trace("PUMP")), "임계 미만 압력에서 펌프가 트립되면 안 된다"


# ── 하위호환: 불리언 전용 호출은 100% 그대로 ─────────────────────────────────


def test_backward_compat_bool_only() -> None:
    """수치 신호가 없는 순수 불리언 프로그램은 기존과 동일하게 동작한다."""
    st = "X := A AND NOT B;"
    r = simulate(
        st,
        [(0, {"A": True}), (100, {"B": True}), (200, {"B": False})],
        duration_ms=200,
        step_ms=100,
    )
    assert r.signals == []  # 아날로그 신호 없음
    assert r.inputs == ["A", "B"]
    assert r.output_trace("X") == [True, False, True]
    # 수치 신호 트레이스는 비어 있다(샘플당 빈 dict)
    assert all(s.signals == {} for s in r.samples)


def test_determinism_numeric() -> None:
    """수치 타임라인도 결정론적(5회 반복 트레이스 동일)."""
    st = "PRESSURE_GE5 := PRESSURE >= 5;"
    ev: list[tuple[int, dict[str, bool | float]]] = [
        (0, {"PRESSURE": 0.0}),
        (100, {"PRESSURE": 6.0}),
        (200, {"PRESSURE": 2.0}),
    ]
    runs = [
        simulate(st, ev, duration_ms=300, step_ms=50).output_trace("PRESSURE_GE5")
        for _ in range(5)
    ]
    assert all(run == runs[0] for run in runs)


@pytest.mark.parametrize("step_ms", [1, 50, 100])
def test_numeric_eval_step_invariant(step_ms: int) -> None:
    """비교 평가는 스캔 step 에 무관(조합 로직, 시간 상태 없음)."""
    st = "F := S >= 5;"
    r = simulate(
        st,
        [(0, {"S": 0.0}), (200, {"S": 9.0})],
        duration_ms=400,
        step_ms=step_ms,
    )
    # 200ms 이후 샘플은 모두 ON, 그 이전은 OFF
    for s in r.samples:
        assert s.outputs["F"] is (s.t_ms >= 200)
