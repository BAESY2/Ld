"""정형 검증기 테스트."""

from __future__ import annotations

import pytest

from app.models import Interlock, IODirection, IOPoint, SfcState, StateMachineSpec, Transition
from app.synth import synthesize_st
from app.verifier import (
    _HAS_Z3,
    _to_z3,
    check_interlocks_kinduction,
    check_interlocks_st,
    check_reachability,
    proven_safe_pairs,
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


@z3_only
def test_kinduction_proves_synthesized_interlock() -> None:
    """합성 ST 의 상호배제를 k-귀납이 모든 도달 스캔에 대해 증명한다(이슈 0)."""
    st = synthesize_st(_INTERLOCK_SPEC)
    assert check_interlocks_kinduction(_INTERLOCK_SPEC, st, k=3) == []


@z3_only
def test_kinduction_catches_missing_partner_not_reachable() -> None:
    """상대 NOT 보호가 빠진 ST 는 k-귀납 base 에서 도달가능 위반(error+반례)으로 잡힌다."""
    bad_st = (
        "MOTOR_FWD := (FWD_PB OR MOTOR_FWD) AND NOT (STOP);\n"
        "MOTOR_REV := (REV_PB OR MOTOR_REV) AND NOT (STOP);"
    )
    issues = check_interlocks_kinduction(_INTERLOCK_SPEC, bad_st, k=3)
    errs = [i for i in issues if i.code == "INTERLOCK" and i.severity == "error"]
    assert len(errs) == 1
    assert errs[0].counterexample != ""


@z3_only
def test_kinduction_counterexample_is_deterministic() -> None:
    """반례 문자열은 정렬되어 재실행 간 동일하다(비결정성 누출 금지)."""
    bad_st = (
        "MOTOR_FWD := (FWD_PB OR MOTOR_FWD) AND NOT (STOP);\n"
        "MOTOR_REV := (REV_PB OR MOTOR_REV) AND NOT (STOP);"
    )
    ce1 = check_interlocks_kinduction(_INTERLOCK_SPEC, bad_st, k=3)[0].counterexample
    ce2 = check_interlocks_kinduction(_INTERLOCK_SPEC, bad_st, k=3)[0].counterexample
    assert ce1 == ce2
    assert ce1 == ", ".join(sorted(ce1.split(", ")))


@z3_only
def test_kinduction_at_least_as_strong_as_one_step() -> None:
    """k-귀납은 1-스텝 검사가 거부하는 ST 를 절대 '통과(증명)'시키지 않는다.

    1-스텝이 error 를 내는 모든 케이스에서 k-귀납도 반드시 error 를 내야 한다
    (강도 약화 금지). 안전 케이스에선 둘 다 통과.
    """
    cases = [
        synthesize_st(_INTERLOCK_SPEC),  # 안전
        "MOTOR_FWD := FWD_PB OR MOTOR_FWD;\nMOTOR_REV := REV_PB OR MOTOR_REV;",  # 위반
        (
            "MOTOR_FWD := (FWD_PB OR MOTOR_FWD) AND NOT (STOP);\n"
            "MOTOR_REV := (REV_PB OR MOTOR_REV) AND NOT (STOP);"
        ),  # 위반
    ]
    for st in cases:
        one_err = any(
            i.code == "INTERLOCK" and i.severity == "error"
            for i in check_interlocks_st(_INTERLOCK_SPEC, st)
        )
        kind = check_interlocks_kinduction(_INTERLOCK_SPEC, st, k=3)
        kind_err = any(i.code == "INTERLOCK" and i.severity == "error" for i in kind)
        if one_err:
            assert kind_err, f"1-스텝이 거부한 ST 를 k-귀납이 통과시킴: {st!r}"


@z3_only
def test_kinduction_step_only_failure_is_warning_then_proves_at_higher_k() -> None:
    """base 안전·작은 k 미증명 → error 아닌 warning. k 를 키우면 증명(이슈 0).

    원-핫 회전(A:=C; B:=A; C:=B)은 초기 전부 OFF 에서 A,B 가 절대 동시 ON 이 아니지만
    (base 안전), 단순경로 길이가 짧으면 1-귀납으로 증명 불가하다. k 를 키우면
    simple-path 제약이 비도달 순환을 배제해 증명된다 — k-귀납이 1-스텝보다 강함을 증명.
    """
    spec = StateMachineSpec(
        io_points=[
            IOPoint(symbol="GO", direction=IODirection.INPUT),
            IOPoint(symbol="A", direction=IODirection.OUTPUT),
            IOPoint(symbol="B", direction=IODirection.OUTPUT),
            IOPoint(symbol="C", direction=IODirection.OUTPUT),
        ],
        interlocks=[Interlock(output_a="A", output_b="B")],
    )
    st = "A := C;\nB := A;\nC := B;"
    small = check_interlocks_kinduction(spec, st, k=1)
    assert small != []
    assert all(i.severity != "error" for i in small)  # base 안전 → 절대 error 아님
    assert any(i.code == "INTERLOCK_KIND" and i.severity == "warning" for i in small)
    # k 를 키우면 simple-path 강화로 증명 완료(이슈 0).
    assert check_interlocks_kinduction(spec, st, k=3) == []


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


# ── 스펙수준 거짓양성 억제: 코일 가드가 증명되면(proof) 스펙수준 INTERLOCK 제외 ──
# 기동 조건이 겹치는(독립 입력으로 둘 다 켜질 수 있는) 두 출력 — 교차 인터락 패턴.
_OVERLAP_SPEC = StateMachineSpec(
    io_points=[
        IOPoint(symbol="X", direction=IODirection.INPUT),
        IOPoint(symbol="A", direction=IODirection.OUTPUT),
        IOPoint(symbol="B", direction=IODirection.OUTPUT),
    ],
    states=[
        SfcState(name="S0", is_initial=True),
        SfcState(name="SA", on_entry=["A := TRUE;"]),
        SfcState(name="SB", on_entry=["B := TRUE;"]),
    ],
    transitions=[
        Transition(from_state="S0", to_state="SA", condition="X"),
        Transition(from_state="S0", to_state="SB", condition="X"),
    ],
    interlocks=[Interlock(output_a="A", output_b="B")],
)
_GUARDED_ST = "A := (X OR A) AND NOT B;\nB := (X OR B) AND NOT A;"
_UNGUARDED_ST = "A := X OR A;\nB := X OR B;"


@z3_only
def test_proven_safe_pairs_includes_guarded_pair() -> None:
    proven = proven_safe_pairs(_OVERLAP_SPEC, _GUARDED_ST, k=3)
    assert ("A", "B") in proven and ("B", "A") in proven


@z3_only
def test_proven_safe_pairs_excludes_unguarded_pair() -> None:
    # 가드 없는 ST 는 증명 불가/위반이므로 proven 집합에 들지 않는다.
    assert proven_safe_pairs(_OVERLAP_SPEC, _UNGUARDED_ST, k=3) == frozenset()


@z3_only
def test_verify_suppresses_spec_level_false_positive_when_proven() -> None:
    # 선언 조건은 겹치지만(스펙수준 z3 단독이면 거짓양성) 코일이 상대를 가드 →
    # k-귀납이 상호배제를 증명 → 스펙수준 INTERLOCK 을 억제하고 통과.
    report = verify(_OVERLAP_SPEC, _GUARDED_ST)
    assert report.passed, report.issues
    assert not any(i.code == "INTERLOCK" and i.severity == "error" for i in report.issues)


@z3_only
def test_verify_keeps_interlock_error_when_unguarded() -> None:
    # 억제는 '증명된 쌍' 에만 적용 — 가드 없는 도달가능 위반은 여전히 error.
    report = verify(_OVERLAP_SPEC, _UNGUARDED_ST)
    assert not report.passed
    assert any(i.code == "INTERLOCK" and i.severity == "error" for i in report.issues)
