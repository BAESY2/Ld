"""키 없는 자연어→레시피 매칭 테스트 (결정론, 키 불필요)."""

from __future__ import annotations

import pytest

from app.nlmatch import (
    RECIPE_KEYWORDS,
    analyze,
    extract_slots,
    is_confident,
    match_recipe,
)
from app.synth import synthesize_st
from app.verifier import verify
from app.wizard import RECIPES, build_spec

_CASES = [
    ("버튼 누르면 모터 돌고 정지 누르면 멈추게", "motor_start_stop"),
    ("5초 뒤에 램프 켜기", "on_delay"),
    ("정방향 역방향 버튼으로 모터 돌리고 동시에 못 돌게", "fwd_rev"),
    ("물 차면 펌프 끄고 줄면 켜기", "hi_lo_level"),
    ("부품 10개 세면 배출", "count_eject"),
    ("자동 수동 모드 전환해서 밸브 열기", "auto_manual"),
]


@pytest.mark.parametrize("text,expected", _CASES)
def test_match_recipe_picks_right_one(text: str, expected: str) -> None:
    assert match_recipe(text)[0][0] == expected


def test_keyword_table_parity() -> None:
    """모든 레시피에 키워드 항목이 있어야 한다(신규 레시피 NL 도달성 보장)."""
    assert set(RECIPE_KEYWORDS) == set(RECIPES)


def test_extract_seconds_and_count() -> None:
    assert extract_slots("5초 뒤에 켜기", RECIPES["on_delay"]).get("delay_sec") == "5"
    assert extract_slots("부품 10개", RECIPES["count_eject"]).get("count") == "10"
    assert extract_slots("3 초", RECIPES["on_delay"]).get("delay_sec") == "3"


def test_match_is_deterministic() -> None:
    a = match_recipe("5초 뒤 램프")
    b = match_recipe("5초 뒤 램프")
    assert a == b


def test_empty_text_scores_zero() -> None:
    scores = match_recipe("   ")
    assert all(s == 0.0 for _, s in scores)
    assert not is_confident(scores)


def test_garbage_not_confident() -> None:
    assert not is_confident(match_recipe("안녕하세요 반갑습니다"))


@pytest.mark.parametrize("text,expected", _CASES)
def test_analyze_answers_build_valid_design(text: str, expected: str) -> None:
    """매칭→슬롯 결과가 그대로 build_spec→synth→verify 통과해야 한다."""
    res = analyze(text, allow_llm=False)
    assert res.recipe_id == expected
    assert res.used_llm is False
    spec = build_spec(res.recipe_id, res.answers)
    report = verify(spec, synthesize_st(spec))
    assert report.passed


def test_missing_numeric_slot_asks_question() -> None:
    """초를 안 말하면 지연 기동에서 '몇 초' 질문이 나온다."""
    res = analyze("지연 기동 시켜줘", allow_llm=False)
    assert res.recipe_id == "on_delay"
    assert any("초" in q for q in res.questions)


def test_confident_match_no_symbol_questions() -> None:
    """확신 매칭 + 숫자 슬롯 충족이면 불필요한 심볼 질문을 안 한다."""
    res = analyze("부품 10개 세면 배출", allow_llm=False)
    assert res.answers.get("count") == "10"
    assert res.questions == []


def test_nl_design_endpoint() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.server import app

    c = TestClient(app)
    r = c.post("/api/nl-design", json={"text": "5초 뒤에 램프 켜기"})
    assert r.status_code == 200
    d = r.json()
    assert d["recipe"] == "on_delay"
    assert d["filled_answers"].get("delay_sec") == "5"
    assert d["design"]["ok"] is True
    assert d["design"]["ladder"]["rungs"]
    assert "하드와이어" in d["safety_notice"]
