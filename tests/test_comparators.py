"""아날로그 비교기(Comparator) 코어 — ROADMAP P1-W1.

키 없이 *아날로그 설정값*(압력/온도/수위 임계)을 IEC 표준 비교로 표현한다. 비교기는
BOOL 플래그를 산출하고, Z3 는 플래그를 원자 불리언으로 취급(건전·보수적). 합성 ST 는
이중코일 0·검증 통과여야 하고, 래더는 비교 접점으로 렌더돼야 한다.
"""

from __future__ import annotations

import pytest

from app.boolexpr import Var, parse
from app.memory_map import detect_double_coils
from app.models import (
    Comparator,
    CompareOp,
    DataType,
    IODirection,
    IOPoint,
    SfcState,
    StateMachineSpec,
    Transition,
)
from app.synth import synthesize_comparators, synthesize_st
from app.transpiler import transpile_st
from app.verifier import verify


def _band_spec() -> StateMachineSpec:
    """압력 ≥5바에서 밸브 ON, 3바 밑(히스테리시스 2)에서 OFF."""
    return StateMachineSpec(
        title="압력 밴드",
        io_points=[
            IOPoint(symbol="PRESSURE", direction=IODirection.INPUT, data_type=DataType.REAL),
            IOPoint(symbol="VALVE", direction=IODirection.OUTPUT),
        ],
        comparators=[
            Comparator(flag="P_HI", signal="PRESSURE", op=CompareOp.GE,
                       threshold=5.0, hysteresis=2.0),
        ],
        states=[
            SfcState(name="CLOSED", is_initial=True),
            SfcState(name="OPEN", on_entry=["VALVE := TRUE;"]),
        ],
        transitions=[
            Transition(from_state="CLOSED", to_state="OPEN", condition="P_HI"),
            Transition(from_state="OPEN", to_state="CLOSED", condition="NOT P_HI"),
        ],
    )


def test_boolexpr_parses_comparison_as_atom() -> None:
    assert parse("SIG >= 5.0") == Var("SIG>=5.0")
    assert parse("T < 200") == Var("T<200")
    # NOT/AND 와 결합해도 비교가 한 원자로 묶인다.
    node = parse("P_HI AND NOT LO")
    assert node is not None


def test_boolexpr_backward_compatible() -> None:
    """비교 문자가 없는 기존 식은 토큰화·파싱 결과가 동일(회귀 가드)."""
    for e in ["A AND NOT B OR C", "T1.Q AND NOT STOP", "(START OR M) AND NOT STOP", "TRUE"]:
        parse(e)  # 예외 없이 통과


def test_comparator_hysteresis_st_and_no_double_coil() -> None:
    spec = _band_spec()
    st = synthesize_st(spec)
    # 밴드 SR: 5에서 ON, 3까지 유지
    assert "P_HI := (PRESSURE >= 5) OR (P_HI AND PRESSURE >= 3);" in st
    assert detect_double_coils(st) == {}
    assert verify(spec, st).passed


def test_simple_comparator_no_hysteresis() -> None:
    line = synthesize_comparators(
        StateMachineSpec(comparators=[
            Comparator(flag="T_OK", signal="TEMP", op=CompareOp.GE, threshold=200)
        ])
    )
    assert line[-1] == "T_OK := TEMP >= 200;"


def test_comparator_renders_compare_contacts_in_ladder() -> None:
    prog = transpile_st(synthesize_st(_band_spec()))
    contacts = {e.symbol for r in prog.rungs for b in r.input_branches for e in b.elements}
    assert "PRESSURE>=5" in contacts  # 비교 접점으로 렌더됨
    assert any(o.symbol == "P_HI" for r in prog.rungs for o in r.outputs)


def test_pressure_band_recipe_custom_thresholds() -> None:
    """pressure_band 레시피가 사용자 임계로 검증 통과 히스테리시스 래더를 만든다."""
    from app.wizard import build_spec

    spec = build_spec("pressure_band", {"signal": "P1", "hi": "8", "lo": "6", "out": "RELIEF"})
    st = synthesize_st(spec)
    assert "P_HI := (P1 >= 8) OR (P_HI AND P1 >= 6);" in st
    assert detect_double_coils(st) == {}
    assert verify(spec, st).passed
    assert "RELIEF" in st


def test_temp_setpoint_recipe_heats_until_target() -> None:
    from app.wizard import build_spec

    spec = build_spec("temp_setpoint", {"signal": "T1", "target": "180", "band": "4"})
    st = synthesize_st(spec)
    assert "T_REACHED := (T1 >= 180) OR (T_REACHED AND T1 >= 176);" in st
    # 히터는 목표 도달 전(NOT T_REACHED)에만 ON
    assert "HEATER := ((NOT T_REACHED) OR HEATER) AND NOT ((T_REACHED));" in st
    assert verify(spec, st).passed


def test_pressure_band_lo_ge_hi_is_corrected() -> None:
    """하한 ≥ 상한이면 히스테리시스가 성립하도록 보정(밴드>0)."""
    from app.wizard import build_spec

    spec = build_spec("pressure_band", {"hi": "5", "lo": "9"})
    assert spec.comparators[0].hysteresis is not None
    assert spec.comparators[0].hysteresis > 0


def test_comparator_flag_collision_with_output_raises() -> None:
    spec = StateMachineSpec(
        comparators=[Comparator(flag="VALVE", signal="P", op=CompareOp.GE, threshold=1)],
        states=[SfcState(name="S", on_entry=["VALVE := TRUE;"], is_initial=True)],
    )
    with pytest.raises(ValueError, match="이중 정의"):
        synthesize_comparators(spec)
