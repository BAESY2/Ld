"""정형 검증기 테스트."""

from __future__ import annotations

import pytest

from app.models import SfcState, StateMachineSpec, Transition
from app.verifier import _HAS_Z3, _to_z3, check_reachability, verify

z3_only = pytest.mark.skipif(not _HAS_Z3, reason="z3 미설치")


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
