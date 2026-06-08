"""의도 프레임 추출 테스트 (MASTERPLAN M1 — AI 없는 한국어 제어 이해).

형태소 → (조건→동작·대상·극성·수량) 구조화와 설명가능 확신도(coverage 보정)를 검증.
핵심 안전속성: 도메인 밖/명령 아님은 *비확신*으로 떨어져 거짓 이해를 막는다.
"""

from __future__ import annotations

import pytest

from app.intent import ClauseKind, extract


def test_condition_action_structure() -> None:
    f = extract("버튼 누르면 모터 돌고")
    kinds = [(c.kind, c.predicate, c.device) for c in f.clauses]
    assert (ClauseKind.COND, "PRESS", "BUTTON") in kinds
    assert (ClauseKind.ACTION, "RUN", "MOTOR") in kinds
    assert f.confident is True


def test_hi_lo_level_intent_recovered() -> None:
    """'저수위 되면 펌프 켜고 만수위 되면 꺼' → 조건/동작 4절을 정확히 구조화."""
    f = extract("저수위 되면 펌프 켜고 만수위 되면 꺼")
    conds = [c.predicate for c in f.conditions]
    acts = [(c.predicate, c.device) for c in f.actions]
    assert "BECOME" in conds  # 도달(되다)
    assert ("TURN_ON", "PUMP") in acts
    assert ("TURN_OFF", None) in acts or any(p == "TURN_OFF" for p, _ in acts)


def test_value_and_unit_extraction() -> None:
    f = extract("압력 5바 넘으면 밸브 닫아")
    cond = f.conditions[0]
    assert cond.predicate == "EXCEED" and cond.value == 5 and cond.unit == "바"
    assert any(c.predicate == "CLOSE" and c.device == "VALVE" for c in f.actions)


def test_negation_flag_in_frame() -> None:
    f = extract("동시에 못 돌게")
    runs = [c for c in f.actions if c.predicate == "RUN"]
    assert runs and runs[0].negated is True


def test_runon_no_space_frame() -> None:
    f = extract("버튼누르면모터돌고")
    assert f.confident is True
    assert any(c.kind == ClauseKind.ACTION and c.predicate == "RUN" for c in f.clauses)


def test_out_of_domain_is_not_confident() -> None:
    """도메인 밖 문장은 낮은 확신 → 거짓 이해 금지(핵심 안전속성)."""
    f = extract("안녕하세요 오늘 날씨 정말 좋네요")
    assert f.certainty < 0.5
    assert f.confident is False


def test_no_action_means_zero_certainty() -> None:
    """동작 절이 없으면(명령 아님) 확신 0."""
    f = extract("버튼")  # 체언만, 동작 없음
    assert f.actions == []
    assert f.certainty == 0.0


def test_explanation_is_human_readable_korean() -> None:
    f = extract("압력 5바 넘으면 밸브 닫아")
    e = f.explain()
    assert "조건" in e and "동작" in e and "압력" in e and "밸브" in e


def test_extract_is_deterministic() -> None:
    t = "저수위 되면 펌프 켜고 만수위 되면 꺼"
    a, b = extract(t), extract(t)
    assert a.explain() == b.explain()
    assert a.certainty == b.certainty


@pytest.mark.parametrize("text", [
    "버튼 누르면 모터 돌고 정지 누르면 멈추게",
    "온도가 200도 되면 히터 꺼",
    "부품 10개 차면 배출",
])
def test_clear_commands_are_confident(text: str) -> None:
    assert extract(text).confident is True
