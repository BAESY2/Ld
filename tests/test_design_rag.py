"""검증예제 RAG 회귀 가드 — 키 없이 결정론 검색·주입을 고정한다.

verified-only 규율(검증 통과 레시피만 저장소 admit)과 BM25-lite 랭킹의 정확성을 박는다.
실제 LLM 설계 향상은 키가 있어야 발현되지만, 검색·포맷·주입은 여기서 결정론으로 고정.
"""

from __future__ import annotations

from app.design_rag import (
    format_examples_for_prompt,
    retrieve_design_examples,
    verified_examples,
)
from app.wizard import RECIPES


def test_store_is_verified_only_and_covers_all_recipes() -> None:
    ex = verified_examples()
    # 모든 레시피가 기본값으로 검증 통과(test_wizard 와 일관) → 전부 admit.
    assert {e.recipe_id for e in ex} == set(RECIPES)
    assert all(e.st.strip() for e in ex)             # 예제마다 비지 않은 ST
    assert len({e.recipe_id for e in ex}) == len(ex)  # 중복 없음


def test_retrieval_ranks_relevant_recipe_top_k() -> None:
    cases = [
        ("버튼 누르면 모터 돌고 정지 누르면 멈추게", "motor_start_stop"),
        ("비전검사 NG면 리젝트하고 불량 누적되면 알람", "vision_reject"),
        ("분류신호 따라 세갈래로 선별 배출", "multiway_sort"),
        ("인덱싱 테이블 회전하고 스테이션 작업", "index_table"),
    ]
    for text, expected in cases:
        ids = [e.recipe_id for e in retrieve_design_examples(text, k=3)]
        assert expected in ids, f"{text} → {ids}"


def test_retrieval_count_and_determinism() -> None:
    a = retrieve_design_examples("모터 기동 정지", k=2)
    b = retrieve_design_examples("모터 기동 정지", k=2)
    assert len(a) == 2
    assert [e.recipe_id for e in a] == [e.recipe_id for e in b]


def test_empty_query_returns_some_without_error() -> None:
    assert len(retrieve_design_examples("", k=3)) == 3


def test_format_renders_st_blocks() -> None:
    shots = format_examples_for_prompt(retrieve_design_examples("모터 기동", k=2))
    assert "```st" in shots and "## 의도:" in shots
    assert format_examples_for_prompt([]) == ""
