"""결정론 ST → 래더 트랜스파일러 테스트."""

from __future__ import annotations

from app.memory_map import DeviceAllocator
from app.models import ElementType, IODirection, IOPoint, StateMachineSpec
from app.transpiler import transpile_st


def test_single_and_rung() -> None:
    prog = transpile_st("MOTOR := START AND NOT STOP;")
    assert len(prog.rungs) == 1
    rung = prog.rungs[0]
    # 하나의 AND 항 = 하나의 직렬 브랜치
    assert len(rung.input_branches) == 1
    elems = rung.input_branches[0].elements
    types = {(e.symbol, e.element_type) for e in elems}
    assert ("START", ElementType.CONTACT_NO) in types
    assert ("STOP", ElementType.CONTACT_NC) in types
    # 출력 코일
    assert rung.outputs[0].symbol == "MOTOR"
    assert rung.outputs[0].element_type == ElementType.COIL


def test_or_creates_parallel_branches() -> None:
    prog = transpile_st("PUMP := A OR B;")
    rung = prog.rungs[0]
    assert len(rung.input_branches) == 2
    syms = {b.elements[0].symbol for b in rung.input_branches}
    assert syms == {"A", "B"}


def test_self_hold_circuit() -> None:
    # (START OR MOTOR) AND NOT STOP → 2개 직렬 브랜치, 각각 NOT STOP 포함
    prog = transpile_st("MOTOR := (START OR MOTOR) AND NOT STOP;")
    rung = prog.rungs[0]
    assert len(rung.input_branches) == 2
    for b in rung.input_branches:
        syms = {e.symbol for e in b.elements}
        assert "STOP" in syms
        assert "START" in syms or "MOTOR" in syms


def test_comment_attached_to_rung() -> None:
    prog = transpile_st("// 기동\nMOTOR := START;")
    assert prog.rungs[0].comment == "기동"


def test_multiple_rungs() -> None:
    prog = transpile_st("A := X;\nB := Y;\n")
    assert [r.outputs[0].symbol for r in prog.rungs] == ["A", "B"]


def test_addresses_filled_from_allocator() -> None:
    spec = StateMachineSpec(
        io_points=[
            IOPoint(symbol="START", direction=IODirection.INPUT),
            IOPoint(symbol="MOTOR", direction=IODirection.OUTPUT),
        ]
    )
    alloc = DeviceAllocator().build_from_spec(spec)
    prog = transpile_st("MOTOR := START;", allocator=alloc)
    rung = prog.rungs[0]
    assert rung.input_branches[0].elements[0].address == alloc.address_of("START")
    assert rung.outputs[0].address == alloc.address_of("MOTOR")


def test_deterministic_output() -> None:
    code = "OUT := (A AND B) OR (C AND NOT D);"
    assert transpile_st(code).model_dump() == transpile_st(code).model_dump()
