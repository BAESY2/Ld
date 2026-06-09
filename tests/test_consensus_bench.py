"""consensus_bench 측정의 건전성·결정론 테스트(빠르게).

핵심 불변: (a) 예외 없이 실행, (b) 합의 규칙의 침묵실패 ≤ nlmatch 단독 침묵실패
(합의가 침묵을 *늘리지 않음*), (c) 수치 결정론.
"""

from __future__ import annotations

from scripts.consensus_bench import run


def test_runs_without_exception() -> None:
    """벤치가 예외 없이 끝나고 기대한 키들을 낸다."""
    res = run()
    for key in (
        "n", "nl_silent_fail", "consensus_silent_fail", "silent_fail_reduction",
        "nl_positive_recall", "consensus_positive_recall", "positive_recall_loss",
    ):
        assert key in res
    assert isinstance(res["n"], int) and res["n"] > 0


def test_consensus_does_not_increase_silent_fail() -> None:
    """합의 규칙(둘 다 confident)의 침묵실패 ≤ nlmatch 단독 침묵실패.

    합의는 nlmatch 가 confident 인 부분집합에서만 confident 하므로(AND 단조),
    침묵실패는 절대 늘 수 없다 — 이 코퍼스에서 그 단조성을 *수치로* 못박는다.
    """
    res = run()
    nl_sf = res["consensus_silent_fail"]
    base_sf = res["nl_silent_fail"]
    assert isinstance(nl_sf, int) and isinstance(base_sf, int)
    assert nl_sf <= base_sf
    assert res["silent_fail_reduction"] == base_sf - nl_sf
    assert nl_sf >= 0


def test_consensus_coverage_subset_of_nlmatch() -> None:
    """합의 confident 는 nlmatch confident 의 부분집합(AND 규칙의 구조적 귀결)."""
    res = run()
    cons_cov = res["consensus_coverage"]
    nl_cov = res["nl_coverage"]
    assert isinstance(cons_cov, int) and isinstance(nl_cov, int)
    assert cons_cov <= nl_cov
    # recall 손실은 음수가 아니다(합의가 정답을 *더* 인식할 수는 없다 — 부분집합).
    assert isinstance(res["positive_recall_loss"], int)
    assert res["positive_recall_loss"] >= 0


def test_deterministic_numbers() -> None:
    """두 번 돌려 모든 수치가 동일(결정론·키 불필요)."""
    a = run()
    b = run()
    for key in (
        "n", "nl_silent_fail", "consensus_silent_fail", "silent_fail_reduction",
        "nl_coverage", "consensus_coverage", "nl_recognized", "consensus_recognized",
        "positive_total", "nl_positive_recall", "consensus_positive_recall",
        "positive_recall_loss", "disagreements",
    ):
        assert a[key] == b[key], f"비결정: {key}"
