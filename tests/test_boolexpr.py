"""불리언 AST + DNF 변환 테스트."""

from __future__ import annotations

from app.boolexpr import parse, to_dnf


def _terms_as_sets(expr: str) -> set[frozenset[tuple[str, bool]]]:
    return set(to_dnf(parse(expr)))


def test_simple_and() -> None:
    terms = _terms_as_sets("A AND B")
    assert terms == {frozenset({("A", False), ("B", False)})}


def test_simple_or_splits_terms() -> None:
    terms = _terms_as_sets("A OR B")
    assert terms == {frozenset({("A", False)}), frozenset({("B", False)})}


def test_not_literal() -> None:
    terms = _terms_as_sets("NOT A")
    assert terms == {frozenset({("A", True)})}


def test_distribution() -> None:
    # A AND (B OR C) == (A AND B) OR (A AND C)
    terms = _terms_as_sets("A AND (B OR C)")
    assert terms == {
        frozenset({("A", False), ("B", False)}),
        frozenset({("A", False), ("C", False)}),
    }


def test_de_morgan() -> None:
    # NOT (A AND B) == NOT A OR NOT B
    terms = _terms_as_sets("NOT (A AND B)")
    assert terms == {frozenset({("A", True)}), frozenset({("B", True)})}


def test_contradiction_term_removed() -> None:
    # A AND NOT A → 항상 거짓 → 항 제거
    assert to_dnf(parse("A AND NOT A")) == []


def test_const_true_is_empty_term() -> None:
    assert to_dnf(parse("TRUE")) == [frozenset()]


def test_precedence_or_of_and() -> None:
    # A OR B AND C == A OR (B AND C)
    terms = _terms_as_sets("A OR B AND C")
    assert terms == {
        frozenset({("A", False)}),
        frozenset({("B", False), ("C", False)}),
    }
