"""NL→명세 정확도 벤치마크 회귀 가드 — "21개 밖에서 몇 %" 시금석을 박는다.

핵심 보장(결정론·키 없음):
  · in-template 요청은 자신있게 *올바른* 템플릿으로 높은 비율 매칭(≥0.8).
  · in-template 에서 '자신있게 틀린' 매칭은 0(범위 안 침묵 실패 금지).
  · out-of-template(표현 불가) 요청의 '침묵 실패율'(자신있게 틀린 매칭)은 낮게(≤0.1)
    유지 — 엔진이 범위 밖을 자각하고 정직하게 거절해야 한다.
"""

from __future__ import annotations

from app.bench import score_keyless
from app.nlmatch import analyze
from benchmarks.nl_bench_corpus import BENCH


def test_benchmark_metrics_locked() -> None:
    r = score_keyless(BENCH)
    # in-template: 높은 정확도, 자신있게 틀린 건 0.
    assert r.in_template_accuracy >= 0.80, r.report()
    assert r.in_confident_wrong == 0, r.report()
    # out-of-template: 범위 밖 침묵 실패(자신있게 틀림)는 거의 0 이어야 한다.
    assert r.out_silent_fail_rate <= 0.10, r.report()
    assert r.out_honest_rate >= 0.90, r.report()


def test_out_of_scope_examples_refused() -> None:
    """대표적 범위 밖 요청은 확신 강등 + out_of_scope 안내."""
    for text in (
        "항온조를 PID로 60도 ±0.5도로 유지",
        "다관절 로봇 6축 경로를 티칭점 따라 보간",
        "PLC끼리 생산수량 데이터를 통신으로 주고받기",
    ):
        res = analyze(text)
        assert res.confident is False, text
        assert "out_of_scope" in res.extras, text


def test_in_template_not_false_flagged_out_of_scope() -> None:
    """정상 템플릿 요청(전동기/서보 원점복귀 등)은 범위 밖으로 오탐되지 않는다."""
    for text, expected, _why in BENCH:
        if expected is not None:
            assert "out_of_scope" not in analyze(text).extras, text


def test_score_keyless_is_deterministic() -> None:
    a, b = score_keyless(BENCH), score_keyless(BENCH)
    assert a == b
