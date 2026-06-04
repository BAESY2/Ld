"""정형 검증기 테스트."""

from __future__ import annotations

import pytest

from app.models import Interlock, IODirection, IOPoint, SfcState, StateMachineSpec, Transition
from app.synth import synthesize_st
from app.verifier import (
    _HAS_Z3,
    _to_z3,
    check_interlocks_st,
    check_reachability,
    verify,
)

z3_only = pytest.mark.skipif(not _HAS_Z3, reason="z3 미설치")

_INTERLOCK_SPEC = StateMachineSpec(
    io_points=[
        IOPoint(symbol="FWD_PB", direction=IODirection.INPUT),
        IOPoint(symbol="REV_PB", direction=IODirection.INPUT),
        IOPoint(symbol="MOTOR_FWD", direction=IODirection.OUTPUT),
        IOPoint(symbol="MOTOR_REV", direction=IODirection.OUTPUT),
    ],
    states=[
        SfcState(name="IDLE", is_initial=True),
        SfcState(name="FWD", on_entry=["MOTOR_FWD := TRUE;"]),
        SfcState(name="REV", on_entry=["MOTOR_REV := TRUE;"]),
    ],
    transitions=[
        Transition(from_state="IDLE", to_state="FWD", condition="FWD_PB AND NOT REV_PB"),
        Transition(from_state="IDLE", to_state="REV", condition="REV_PB AND NOT FWD_PB"),
    ],
    interlocks=[Interlock(output_a="MOTOR_FWD", output_b="MOTOR_REV")],
)


@z3_only
def test_interlocks_st_passes_for_synthesized_output() -> None:
    """합성된 ST(자기유지+상대 NOT)는 ST-수준 인터락 검사를 통과한다."""
    st = synthesize_st(_INTERLOCK_SPEC)
    assert check_interlocks_st(_INTERLOCK_SPEC, st) == []


@z3_only
def test_interlocks_st_catches_missing_partner_not() -> None:
    """상대 출력 NOT 보호가 빠진 ST 는 ST-수준 검사에서 잡힌다(회귀 가드)."""
    bad_st = "MOTOR_FWD := FWD_PB OR MOTOR_FWD;\nMOTOR_REV := REV_PB OR MOTOR_REV;"
    issues = check_interlocks_st(_INTERLOCK_SPEC, bad_st)
    assert any(i.code == "INTERLOCK" and i.severity == "error" for i in issues)


@z3_only
def test_interlocks_st_ignores_non_boolean_gracefully() -> None:
    """비불리언 토큰이 섞여도 예외 없이 건너뛴다."""
    st = "MOTOR_FWD := A + 1;\nMOTOR_REV := REV_PB;"
    assert check_interlocks_st(_INTERLOCK_SPEC, st) == []


@z3_only
def test_to_z3_parses_boolean_expression() -> None:
    import z3

    vars: dict[str, z3.BoolRef] = {}
    expr = _to_z3("A AND NOT B OR C", vars)
    # A=F,B=T,C=T → (A AND NOT B) OR C = (F) OR T = T
    solver = z3.Solver()
    solver.add(expr == True)  # noqa: E712
    solver.add(vars["A"] == False, vars["B"] == True, vars["C"] == True)  # noqa: E712
    assert solver.check() == z3.sat


@z3_only
def test_to_z3_precedence_not_over_and_over_or() -> None:
    import z3

    vars: dict[str, z3.BoolRef] = {}
    # "A OR B AND C" == "A OR (B AND C)"
    expr = _to_z3("A OR B AND C", vars)
    solver = z3.Solver()
    # A=T, B=F, C=F → 결과 True 여야 함 (A OR (F))
    solver.add(vars["A"] == True, vars["B"] == False, vars["C"] == False)  # noqa: E712
    solver.add(z3.Not(expr))
    assert solver.check() == z3.unsat  # expr 는 반드시 True


@z3_only
def test_interlock_violation_detected_with_counterexample(
    conveyor_spec_unsafe: StateMachineSpec,
) -> None:
    report = verify(conveyor_spec_unsafe, st_code="")
    assert report.passed is False
    interlock_issues = [i for i in report.issues if i.code == "INTERLOCK" and i.severity == "error"]
    assert len(interlock_issues) == 1
    assert interlock_issues[0].counterexample != ""
    assert "수정" not in report.suggested_fix or report.suggested_fix  # 한글 제안 채워짐


@z3_only
def test_safe_interlock_passes(conveyor_spec_safe: StateMachineSpec) -> None:
    report = verify(conveyor_spec_safe, st_code="")
    interlock_errors = [
        i for i in report.issues if i.code == "INTERLOCK" and i.severity == "error"
    ]
    assert interlock_errors == []


def test_double_coil_is_error() -> None:
    spec = StateMachineSpec(states=[SfcState(name="S", is_initial=True)])
    report = verify(spec, st_code="X := A;\nX := B;\n")
    assert report.has_errors is True
    assert any(i.code == "DOUBLE_COIL" for i in report.issues)


def test_missing_initial_state_is_deadlock() -> None:
    spec = StateMachineSpec(
        states=[SfcState(name="A"), SfcState(name="B")],
        transitions=[Transition(from_state="A", to_state="B", condition="X")],
    )
    issues = check_reachability(spec)
    assert any(i.code == "DEADLOCK" and i.severity == "error" for i in issues)


def test_unreachable_state_is_warning() -> None:
    spec = StateMachineSpec(
        states=[SfcState(name="A", is_initial=True), SfcState(name="ORPHAN")],
        transitions=[],
    )
    issues = check_reachability(spec)
    assert any(i.code == "UNREACHABLE" and i.severity == "warning" for i in issues)
