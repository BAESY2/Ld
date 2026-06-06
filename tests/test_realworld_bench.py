"""실세계 한국어 벤치마크의 *경량 스모크* — 코퍼스 정합성 + 하니스 무결성.

이 테스트는 점수를 *고정(lock)* 하지 않는다(측정용이라 수치는 변할 수 있음).
대신 (1) 코퍼스가 잘 짜였는지, (2) 하니스가 키 없이 끝까지 도는지, (3) 측정
지표가 정직한 자기일관성을 갖는지(예: compound 전체캡처는 0)만 보증한다.
모든 경로는 키 불필요·결정론.
"""

from __future__ import annotations

from pathlib import Path

from scripts.run_realworld_bench import (
    CORPUS,
    Case,
    evaluate,
    load_corpus,
    run,
)

_VALID_KINDS = {"recipe", "multi", "out_of_scope"}
_VALID_DIFF = {"easy", "compound", "quantified", "out_of_scope"}


def test_corpus_exists_and_nonempty() -> None:
    assert CORPUS.exists(), CORPUS
    cases = load_corpus()
    assert len(cases) >= 40, f"실세계 코퍼스가 너무 작음: {len(cases)}"


def test_corpus_well_formed() -> None:
    cases = load_corpus()
    ids = [c.id for c in cases]
    assert len(ids) == len(set(ids)), "케이스 id 중복"
    for c in cases:
        assert isinstance(c, Case)
        assert c.id and c.text.strip(), c
        assert c.difficulty in _VALID_DIFF, c
        assert c.kind in _VALID_KINDS, c
        assert c.notes, f"{c.id}: notes 가 비어있음"
        # recipe/multi 는 기대 레시피 목록이 있어야 채점 가능.
        if c.kind in ("recipe", "multi"):
            assert c.recipes, f"{c.id}: recipe/multi 인데 기대 레시피 없음"


def test_corpus_spans_all_difficulties() -> None:
    diffs = {c.difficulty for c in load_corpus()}
    assert diffs == _VALID_DIFF, f"네 난이도를 모두 포함해야 함: {diffs}"


def test_expected_recipes_are_real_recipe_ids() -> None:
    from app.wizard import RECIPES

    for c in load_corpus():
        for rid in c.recipes:
            assert rid in RECIPES, f"{c.id}: 알 수 없는 레시피 id {rid!r}"


def test_evaluate_is_deterministic_and_keyfree() -> None:
    from app.nlmatch import analyze

    cases = load_corpus()
    a = [evaluate(c) for c in cases]
    b = [evaluate(c) for c in cases]
    # 키 없는 결정론 경로 — 두 번 돌려 동일해야 한다.
    assert [o.top for o in a] == [o.top for o in b]
    assert [o.confident for o in a] == [o.confident for o in b]
    # 어떤 분석도 LLM 을 쓰지 않는다(allow_llm=False, 키 불필요).
    assert all(not analyze(c.text, allow_llm=False).used_llm for c in cases)


def test_harness_runs_and_reports_metrics() -> None:
    metrics = run()
    assert metrics["n"] >= 40
    # 측정 지표가 자기일관적인가(부풀림 방지의 시금석).
    for key in (
        "overall_recognition",
        "overall_coverage",
        "overall_silent_fail",
        "quant_fail_rate",
        "oos_refusal_rate",
    ):
        v = metrics[key]
        assert isinstance(v, float) and 0.0 <= v <= 1.0, (key, v)
    # 다중 서브시스템 요청의 '전체 의도 캡처'는 구조적으로 0 이어야 한다(정직성).
    assert metrics["compound_full_capture_rate"] == 0.0
    # 산출물에 이중코일은 절대 없어야 한다(CLAUDE.md 절대규칙 #3).
    assert metrics["double_coil_violations"] == 0


def test_out_of_scope_cases_not_confidently_produced_wrong() -> None:
    """범위밖 요청은 자신있게 산출물을 내지 않아야 한다(정직 거절)."""
    oos = [c for c in load_corpus() if c.difficulty == "out_of_scope"]
    for c in oos:
        o = evaluate(c)
        assert not o.confident, f"{c.id}: 범위밖인데 자신있게 매칭({o.top})"
        assert not o.produced, c.id


def test_harness_does_not_create_files() -> None:
    """하니스는 측정만 한다 — 디스크에 산출물을 남기지 않는다."""
    before = {p.name for p in Path(CORPUS).parent.iterdir()}
    run()
    after = {p.name for p in Path(CORPUS).parent.iterdir()}
    assert before == after
