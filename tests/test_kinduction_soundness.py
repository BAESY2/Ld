"""k-귀납 인터락 증명의 건전성 잠금 — 시뮬레이터(디지털 트윈)와 교차검증.

빨간팀 라운드6 P0: 검증기는 코일 참조를 '동시 갱신(직전 스캔값)'으로 모델링했으나
시뮬레이터는 위→아래 '순차 평가'(이후 코일이 갱신된 앞 코일을 읽음)라서 의미가
어긋났다 → 거짓 증명(안전하다고 증명했으나 시뮬은 동시 ON)과 거짓 양성이 발생.
수정: 전이관계를 스캔 순서대로 구성. 이 테스트들이 회귀를 영구 차단한다.
"""

from __future__ import annotations

import itertools

import pytest

from app.models import Interlock, StateMachineSpec
from app.simulator import simulate
from app.verifier import _HAS_Z3, check_interlocks_kinduction, verify

z3_only = pytest.mark.skipif(not _HAS_Z3, reason="z3 미설치")


def _sim_reaches_both_on(
    st: str, inputs: list[str], a: str, b: str, scans: int = 6
) -> bool:
    """입력 타임라인을 (작게) 전수 탐색해 시뮬레이터가 a∧b 에 도달하는지."""
    if not inputs:
        r = simulate(st, [(0, {})], duration_ms=scans * 100, step_ms=100)
        return any(s.outputs.get(a) and s.outputs.get(b) for s in r.samples)
    # 각 스캔마다 입력 조합을 바꾸는 전수 타임라인(상태폭 제한 위해 입력≤3, scans 제한)
    use = inputs[:3]
    for combo in itertools.product([False, True], repeat=len(use) * scans):
        ev: list[tuple[int, dict[str, bool]]] = []
        for i in range(scans):
            snap = {use[j]: combo[i * len(use) + j] for j in range(len(use))}
            ev.append((i * 100, snap))
        r = simulate(st, ev, duration_ms=scans * 100, step_ms=100)
        if any(s.outputs.get(a) and s.outputs.get(b) for s in r.samples):
            return True
    return False


# 라운드6 반례 ST 들 (a,b,inputs)
_F1 = (
    "A := NOT M1;\nB := (NOT R AND A);\n"
    "M0 := (NOT M0 OR NOT (R AND B));\nM1 := NOT B;",
    "A", "B", ["R"],
)
_F2 = (
    "A := NOT (NOT B OR P);\nB := (((R OR B) AND P) OR A);\n"
    "M0 := NOT NOT (R AND M0);\nM1 := (M0 AND NOT (M1 AND M0));",
    "A", "B", ["P", "R"],
)
_F3_SAFE = (
    "A := M3 AND NOT B;\nB := M3 AND NOT A;\n"
    "M3 := M2; M2 := M1; M1 := M0; M0 := TRIG;",
    "A", "B", ["TRIG"],
)


@z3_only
@pytest.mark.parametrize("st,a,b,inputs", [_F1, _F2, _F3_SAFE])
def test_kinduction_agrees_with_simulator(
    st: str, a: str, b: str, inputs: list[str]
) -> None:
    """핵심 잠금: k-귀납이 '증명(빈 결과)'이면 시뮬레이터도 절대 동시 ON 아니어야 한다."""
    spec = StateMachineSpec(interlocks=[Interlock(output_a=a, output_b=b)])
    proven_safe = check_interlocks_kinduction(spec, st, k=4) == []
    sim_unsafe = _sim_reaches_both_on(st, inputs, a, b)
    assert not (proven_safe and sim_unsafe), (
        "거짓 증명: k-귀납은 안전하다는데 시뮬레이터는 동시 ON 도달"
    )


@z3_only
def test_f1_false_proof_now_caught() -> None:
    """F1: 과거 거짓 증명 ST 는 이제 INTERLOCK error 로 잡힌다."""
    st, a, b, _ = _F1
    spec = StateMachineSpec(interlocks=[Interlock(output_a=a, output_b=b)])
    issues = check_interlocks_kinduction(spec, st, k=3)
    assert any(i.code == "INTERLOCK" and i.severity == "error" for i in issues)


@z3_only
def test_f2_full_verify_no_longer_false_green() -> None:
    """F2: verify() 전체 파이프라인이 더 이상 거짓 통과(passed=True)하지 않는다."""
    st, a, b, _ = _F2
    spec = StateMachineSpec(interlocks=[Interlock(output_a=a, output_b=b)])
    assert verify(spec, st).passed is False


@z3_only
def test_f3_no_false_positive_on_correctly_interlocked() -> None:
    """F3: 올바르게 인터락된 ST 는 k=3..6 어디서도 거짓 error 를 내지 않는다."""
    st, a, b, _ = _F3_SAFE
    spec = StateMachineSpec(interlocks=[Interlock(output_a=a, output_b=b)])
    for k in (3, 4, 5, 6):
        issues = check_interlocks_kinduction(spec, st, k=k)
        assert not any(i.severity == "error" for i in issues), f"k={k} 거짓 양성"


@z3_only
def test_kinduction_counterexample_deterministic() -> None:
    """반례 문자열은 결정론적(이름 정렬)이라 재실행해도 동일하다."""
    st, a, b, _ = _F1
    spec = StateMachineSpec(interlocks=[Interlock(output_a=a, output_b=b)])
    ce1 = [i.counterexample for i in check_interlocks_kinduction(spec, st, k=3)]
    ce2 = [i.counterexample for i in check_interlocks_kinduction(spec, st, k=3)]
    assert ce1 == ce2
