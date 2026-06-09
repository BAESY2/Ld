"""형식증명 커버리지(검증기 완전성) 정직 단정 — 키 불필요·결정론·빠름.

scripts/proof_coverage.py 가 측정하는 '선언된 상호배제 속성 중 형식 증명된 비율'을
단정한다. 세 축:
  (a) 리포트가 예외 없이 돌고 결정론(같은 입력 → 같은 수치).
  (b) 증명 커버리지가 합리적 하한 이상(시퀀서/인스턴스/인터락 레시피의 mutex 가
      대부분 형식 증명됨 — 측정값에 기반한 보수적 하한).
  (c) false-proof 0 — 증명된 mutex 를 실행오라클(시뮬레이터)이 반증 못함(작은 표본).

빠르게: 코퍼스가 작고(수십 건) k=3 귀납이므로 1~2초 내 완료(전체 스위트 부담 최소).
"""

from __future__ import annotations

from scripts.proof_coverage import (
    PropTally,
    build_corpus,
    format_report,
    run,
)


def test_report_runs_without_exception() -> None:
    """리포트가 예외 없이 돌고, 검사 대상(상호배제 선언 프로그램)이 존재한다."""
    res = run()
    assert res.reports, "상호배제를 선언한 컴파일/레시피 산출물이 없습니다."
    text = format_report(res)
    assert "형식증명 커버리지" in text
    assert "선언된 상호배제 속성 중 형식 증명된 비율" in text


def test_deterministic() -> None:
    """결정론: 같은 입력 → 같은 집계(증명/미증명/위반 수치 동일)."""
    a, b = run(), run()
    ta, tb = a.total, b.total
    assert (ta.proven, ta.unproven, ta.violated) == (tb.proven, tb.unproven, tb.violated)
    assert len(a.reports) == len(b.reports)


def test_corpus_has_all_categories() -> None:
    """코퍼스가 네 카테고리(단서/인스턴스/시퀀스/레시피)를 모두 포함한다."""
    cats = {p.category for p in build_corpus()}
    assert {"mutex_cue", "multi_instance", "sequence", "interlock_recipe"} <= cats


def test_declared_properties_present() -> None:
    """선언된 상호배제 속성(쌍·그룹)이 충분히 모였다 — 측정의 의미를 보장."""
    res = run()
    tot = res.total
    # 측정값(쌍 67·그룹 4·합 71)에 기반한 보수적 하한.
    assert tot.declared >= 40, f"선언 속성이 너무 적음: {tot.declared}"
    assert res.pairs.declared >= 30
    assert res.groups.declared >= 1  # 시퀀서/다분류 one-hot 그룹(>=3)


def test_proof_coverage_lower_bound() -> None:
    """증명 커버리지 합리적 하한 — 가드가 박힌 구조라 대부분 형식 증명되어야 한다.

    측정값은 71/71 = 100%. 회귀에 견디게 보수적으로 0.90 하한을 단정한다
    (k-귀납이 닫히지 않아 일부가 미증명으로 떨어져도 90% 이상은 유지되어야 한다).
    """
    res = run()
    assert res.coverage >= 0.90, f"증명 커버리지 회귀: {res.coverage:.3f}"
    # 위반(error)은 없어야 한다(컴파일러/레시피가 가드를 박으므로).
    assert res.total.violated == 0, "선언 mutex 가 위반으로 잡힘(가드 회귀 의심)."


def test_per_category_coverage() -> None:
    """카테고리별로도 mutex 가 대부분 증명된다(특정 부류만 미증명으로 새지 않음)."""
    res = run()
    cats = res.by_category()
    for cat in ("sequence", "interlock_recipe"):
        t = cats[cat]
        assert t.declared >= 1
        assert t.proven == t.declared, f"{cat}: 일부 미증명({t.proven}/{t.declared})"


def test_no_false_proof() -> None:
    """false-proof 0 — 증명된 mutex 를 디지털 트윈이 반증하지 못한다(건전성 교차확인)."""
    res = run()
    assert res.false_proofs == [], f"false-proof 발견: {res.false_proofs[:3]}"
    # 증명된 게 실제로 존재해야 점검이 의미 있다(공허한 통과 방지).
    assert res.total.proven >= 1


def test_prop_tally_arithmetic() -> None:
    """PropTally 누적·declared 산술이 일관적이다(집계 신뢰성)."""
    a = PropTally(proven=2, unproven=1, violated=0)
    b = PropTally(proven=3, unproven=0, violated=1)
    a.add(b)
    assert a.proven == 5 and a.unproven == 1 and a.violated == 1
    assert a.declared == 7
