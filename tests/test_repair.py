"""검증 게이트 자동 수리 테스트 (M4 — 검증기가 해자).

실패하는 임의 ST 를 *건전한* 수리(이중코일 병합·인터락 가드 주입)로 통과시키고,
구조적 결함은 정직 거절함을 단정. 수리는 의미를 안전측으로만 바꾼다.
"""

from __future__ import annotations

from app.models import Interlock, IODirection, IOPoint, SfcState, StateMachineSpec, Transition
from app.repair import (
    inject_interlock_guards,
    is_structurally_unrepairable,
    repair_iterative,
)
from app.verifier import verify


def _io(sym: str, out: bool) -> IOPoint:
    return IOPoint(symbol=sym, direction=IODirection.OUTPUT if out else IODirection.INPUT)


def test_repair_double_coil_merges_and_passes() -> None:
    st = "MOTOR := A;\nMOTOR := B;\nPUMP := REQUEST;"
    spec = StateMachineSpec(io_points=[
        _io("MOTOR", True), _io("PUMP", True), _io("A", False), _io("B", False),
        _io("REQUEST", False)])
    assert not verify(spec, st).passed  # 수리 전: 이중코일 실패
    o = repair_iterative(spec, st)
    assert o.repaired and o.report.passed
    assert "double_coil" in o.strategies
    assert "MOTOR := M" in o.st_code and " OR " in o.st_code  # M릴레이 OR 병합


def test_repair_interlock_violation_injects_guards() -> None:
    st = "MOTOR_FWD := FWD;\nMOTOR_REV := REV;"
    spec = StateMachineSpec(
        io_points=[_io("MOTOR_FWD", True), _io("MOTOR_REV", True),
                   _io("FWD", False), _io("REV", False)],
        interlocks=[Interlock(output_a="MOTOR_FWD", output_b="MOTOR_REV")])
    assert not verify(spec, st).passed  # 수리 전: 인터락 위반
    o = repair_iterative(spec, st)
    assert o.repaired and o.report.passed
    assert "AND NOT MOTOR_REV" in o.st_code and "AND NOT MOTOR_FWD" in o.st_code


def test_inject_guards_is_idempotent() -> None:
    """이미 가드된 식에 중복 주입하지 않는다(멱등 → 루프 종료 보장)."""
    spec = StateMachineSpec(
        io_points=[_io("A", True), _io("B", True), _io("X", False)],
        interlocks=[Interlock(output_a="A", output_b="B")])
    st = "A := X AND NOT B;\nB := X AND NOT A;"
    assert inject_interlock_guards(st, spec) == st  # 무변경


def test_structural_defect_is_honestly_rejected() -> None:
    """초기상태 없는(데드락) 명세는 수리 대상이 아니라 정직 거절."""
    spec = StateMachineSpec(
        io_points=[_io("M", True)],
        states=[SfcState(name="RUN", on_entry=["M := TRUE;"])],  # is_initial 없음
        transitions=[Transition(from_state="RUN", to_state="RUN", condition="M")],
    )
    st = "M := M;"
    o = repair_iterative(spec, st)
    assert o.rejected and not o.repaired
    assert is_structurally_unrepairable(o.report)


def test_design_loop_auto_repairs_fixable_llm_output() -> None:
    """LLM(mock) 결함을 design_and_verify 가 재요청 전에 수리해 통과시킨다(M3↔M4)."""
    from app.design import design_and_verify
    from app.models import DerivedOutput, PlannedModule, ProjectPlan

    spec = StateMachineSpec(
        io_points=[_io("A", True), _io("B", True), _io("X", False)],
        derived_outputs=[DerivedOutput(output="A", expression="X OR A"),
                         DerivedOutput(output="B", expression="X OR B")],
        interlocks=[Interlock(output_a="A", output_b="B")],  # 가드 누락 → 위반
    )

    class _Fake:
        def invoke(self, _msgs: object) -> ProjectPlan:
            return ProjectPlan(title="t", modules=[PlannedModule(name="m", spec=spec)])

    repaired = design_and_verify("x", model=_Fake(), repair=True)
    assert repaired.report is not None and repaired.report.passed
    assert "AND NOT" in repaired.st_code  # 가드가 주입됨
    not_repaired = design_and_verify("x", model=_Fake(), repair=False, max_revisions=0)
    assert not_repaired.report is not None and not not_repaired.report.passed


def test_already_passing_is_noop() -> None:
    from app.models import DerivedOutput
    spec = StateMachineSpec(
        io_points=[_io("OUT", True), _io("IN", False)],
        derived_outputs=[DerivedOutput(output="OUT", expression="IN OR OUT")])
    st = "OUT := IN OR OUT;"
    o = repair_iterative(spec, st)
    assert not o.repaired and not o.rejected and o.report.passed
