"""결정론 명세→ST 합성기(app/synth.py) 테스트 — 래더 생성 난제 해법.

핵심 보장: 합성 결과는 모든 골든 명세에서 이중코일 0 · 인터락 0 이며,
상태구동 명세는 출력을 100% 덮는다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.memory_map import detect_double_coils
from app.models import ElementType, IODirection, StateMachineSpec
from app.synth import (
    covers_all_outputs,
    synthesizable_outputs,
    synthesize_st,
)
from app.transpiler import transpile_st
from app.verifier import verify

_GOLDEN_DIR = Path(__file__).resolve().parent / "fixtures" / "golden"


def _load_specs() -> list[tuple[str, StateMachineSpec]]:
    specs: list[tuple[str, StateMachineSpec]] = []
    for path in sorted(_GOLDEN_DIR.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        specs.append((case["name"], StateMachineSpec(**case["spec"])))
    return specs


_SPECS = _load_specs()


@pytest.mark.parametrize("name,spec", _SPECS, ids=[n for n, _ in _SPECS])
def test_synth_is_clean_for_all_golden(name: str, spec: StateMachineSpec) -> None:
    """합성 ST 는 어떤 골든 명세에서도 이중코일 0 · 인터락 위반 0."""
    st = synthesize_st(spec)
    assert detect_double_coils(st) == {}, f"{name}: 이중코일 발생"
    report = verify(spec, st)
    interlock_errors = [
        i for i in report.issues if i.code == "INTERLOCK" and i.severity == "error"
    ]
    assert interlock_errors == [], f"{name}: 인터락 위반"


@pytest.mark.parametrize("name,spec", _SPECS, ids=[n for n, _ in _SPECS])
def test_synth_covers_state_driven_outputs(name: str, spec: StateMachineSpec) -> None:
    """상태구동 출력은 합성 ST 에서 코일로 100% 등장한다."""
    st = synthesize_st(spec)
    prog = transpile_st(st)
    coils = {
        el.symbol
        for rung in prog.rungs
        for el in rung.outputs
        if el.element_type == ElementType.COIL
    }
    assert synthesizable_outputs(spec) <= coils, f"{name}: 상태구동 출력 누락"


def test_seal_in_synthesis_shape() -> None:
    """자기유지 형태로 합성되는지(기동 OR 자기 접점 AND NOT 정지)."""
    spec = StateMachineSpec(**json.loads(
        (_GOLDEN_DIR / "02_motor_self_hold.json").read_text(encoding="utf-8")
    )["spec"])
    st = synthesize_st(spec)
    # 출력이 자기 접점으로 유지(OR <output>)
    assert any(":=" in line and "OR" in line for line in st.splitlines())


def test_interlock_adds_partner_not() -> None:
    """인터락 쌍은 상대 출력의 NOT 이 합성식에 들어간다."""
    spec = StateMachineSpec(**json.loads(
        (_GOLDEN_DIR / "01_conveyor_fwd_rev.json").read_text(encoding="utf-8")
    )["spec"])
    st = synthesize_st(spec)
    assert "NOT MOTOR_REV" in st
    assert "NOT MOTOR_FWD" in st


def test_derived_output_now_covered() -> None:
    """derived_outputs 로 정의된 조합 출력(HORN)은 이제 합성으로 덮인다."""
    spec = StateMachineSpec(**json.loads(
        (_GOLDEN_DIR / "18_first_out_alarm.json").read_text(encoding="utf-8")
    )["spec"])
    assert "HORN" in synthesizable_outputs(spec)
    assert covers_all_outputs(spec)
    st = synthesize_st(spec)
    assert "HORN := (LATCH_A OR LATCH_B) AND NOT ALM_ACK;" in st


def test_combinational_output_without_derived_not_covered() -> None:
    """derived_outputs 가 없는 조합 출력은 여전히 합성 불가(LLM 폴백 대상)."""
    from app.models import IOPoint, SfcState

    spec = StateMachineSpec(
        io_points=[
            IOPoint(symbol="A", direction=IODirection.INPUT),
            IOPoint(symbol="LAMP", direction=IODirection.OUTPUT),  # 어디서도 구동 안 됨
        ],
        states=[SfcState(name="IDLE", is_initial=True)],
    )
    assert "LAMP" not in synthesizable_outputs(spec)
    assert not covers_all_outputs(spec)


def test_derived_collision_with_on_entry_raises() -> None:
    """파생 출력이 on_entry 로도 구동되면(이중 정의) 합성이 거부된다."""
    import pytest

    from app.models import DerivedOutput, IOPoint, SfcState, Transition

    spec = StateMachineSpec(
        io_points=[
            IOPoint(symbol="GO", direction=IODirection.INPUT),
            IOPoint(symbol="OUT", direction=IODirection.OUTPUT),
        ],
        states=[
            SfcState(name="IDLE", is_initial=True),
            SfcState(name="ON", on_entry=["OUT := TRUE;"]),
        ],
        transitions=[Transition(from_state="IDLE", to_state="ON", condition="GO")],
        derived_outputs=[DerivedOutput(output="OUT", expression="GO")],
    )
    with pytest.raises(ValueError, match="이중 정의"):
        synthesize_st(spec)


def test_fully_state_driven_spec_is_covered() -> None:
    spec = StateMachineSpec(**json.loads(
        (_GOLDEN_DIR / "01_conveyor_fwd_rev.json").read_text(encoding="utf-8")
    )["spec"])
    assert covers_all_outputs(spec)


def test_invalid_transition_condition_raises() -> None:
    """파싱 불가한 전이 조건은 합성 시 ValueError(다운스트림 크래시 방지)."""
    import pytest

    from app.models import IOPoint, SfcState, Transition

    spec = StateMachineSpec(
        io_points=[
            IOPoint(symbol="GO", direction=IODirection.INPUT),
            IOPoint(symbol="OUT", direction=IODirection.OUTPUT),
        ],
        states=[
            SfcState(name="IDLE", is_initial=True),
            SfcState(name="ON", on_entry=["OUT := TRUE;"]),
        ],
        transitions=[Transition(from_state="IDLE", to_state="ON", condition="GO +")],
    )
    with pytest.raises(ValueError):
        synthesize_st(spec)
