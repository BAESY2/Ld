"""타이머/카운터 결정론 합성 테스트 (FB 콜 → ST → 래더)."""

from __future__ import annotations

import json
from pathlib import Path

from app.emit import emit
from app.memory_map import detect_double_coils
from app.models import (
    CounterSpec,
    ElementType,
    IODirection,
    IOPoint,
    SfcState,
    StateMachineSpec,
    TimerSpec,
    Transition,
)
from app.synth import _ms_to_iec_time, synthesize_fb_calls, synthesize_st
from app.transpiler import transpile_st
from app.vendors import LS_XGK, MITSUBISHI_FX
from app.verifier import check_timers_counters, verify

_GOLDEN = Path(__file__).resolve().parent / "fixtures" / "golden"


def test_ms_to_iec_time() -> None:
    assert _ms_to_iec_time(500) == "T#500ms"
    assert _ms_to_iec_time(5000) == "T#5s"


def test_timer_fb_call_emitted() -> None:
    spec = StateMachineSpec(timers=[TimerSpec(name="T1", preset_ms=500, enable_condition="GO")])
    lines = synthesize_fb_calls(spec)
    assert "T1(IN := GO, PT := T#500ms);" in lines


def test_counter_fb_call_emitted() -> None:
    spec = StateMachineSpec(
        counters=[CounterSpec(name="C1", preset=10, count_condition="PULSE", reset_condition="R")]
    )
    lines = synthesize_fb_calls(spec)
    assert "C1(CU := PULSE, R := R, PV := 10);" in lines  # IEC 표준 R(리셋)


def _timer_spec() -> StateMachineSpec:
    return StateMachineSpec(
        io_points=[
            IOPoint(symbol="START", direction=IODirection.INPUT),
            IOPoint(symbol="STOP", direction=IODirection.INPUT),
            IOPoint(symbol="LAMP", direction=IODirection.OUTPUT),
        ],
        timers=[TimerSpec(name="T1", preset_ms=5000, enable_condition="START")],
        states=[
            SfcState(name="IDLE", is_initial=True),
            SfcState(name="ON", on_entry=["LAMP := TRUE;"]),
        ],
        transitions=[
            Transition(from_state="IDLE", to_state="ON", condition="T1.Q AND NOT STOP"),
            Transition(from_state="ON", to_state="IDLE", condition="STOP"),
        ],
    )


def test_synth_with_timer_no_double_coil() -> None:
    st = synthesize_st(_timer_spec())
    assert "T1(IN := START, PT := T#5s);" in st
    assert "T1.Q" in st
    assert detect_double_coils(st) == {}  # FB 호출은 코일이 아님


def test_timer_transpiles_to_timer_element() -> None:
    prog = transpile_st(synthesize_st(_timer_spec()))
    timer_outs = [
        el for r in prog.rungs for el in r.outputs if el.element_type == ElementType.TIMER
    ]
    assert any(el.symbol == "T1" and "T#5s" in el.description for el in timer_outs)


def test_timer_emits_vendor_mnemonic() -> None:
    prog = transpile_st(synthesize_st(_timer_spec()))
    assert "TON T1 T#5s" in emit(prog, LS_XGK)
    assert "OUT T T1 T#5s" in emit(prog, MITSUBISHI_FX)


def test_check_timers_counters_warns() -> None:
    spec = StateMachineSpec(
        timers=[TimerSpec(name="T1", preset_ms=0)],
        counters=[CounterSpec(name="C1", preset=5)],
    )
    codes = {i.code for i in check_timers_counters(spec)}
    assert {"TIMER_PRESET", "TIMER_ENABLE", "COUNTER_RESET"} <= codes


def test_golden_star_delta_uses_real_timer() -> None:
    spec = StateMachineSpec(**json.loads(
        (_GOLDEN / "08_star_delta_timer.json").read_text(encoding="utf-8")
    )["spec"])
    st = synthesize_st(spec)
    assert "T1(IN := STAR_CON, PT := T#5s);" in st
    assert "NOT T1.Q" in st
    report = verify(spec, st)
    assert not any(i.code == "INTERLOCK" and i.severity == "error" for i in report.issues)
