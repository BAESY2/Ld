"""결정론 한국어 형태소 엔진 테스트 (발명 핵심 — AI 없이 한국어 문법 이해).

제가(엔진이) 인코딩한 한국어 문법 규칙의 *정확성*을 테스트로 보증한다: 한글 자모 산술,
조사 이형태(받침 검증), 용언 활용 정규화, 조건/부정/수량/피동 태깅, 설명가능 coverage.
"""

from __future__ import annotations

import pytest

from app.korean import (
    Pos,
    Role,
    analyze,
    decompose,
    ends_with_rieul,
    has_batchim,
    strip_particle,
)


# ── 1. 한글 자모 산술 ──────────────────────────────────────────────────────
def test_decompose_syllable() -> None:
    assert decompose("각") == ("ㄱ", "ㅏ", "ㄱ")
    assert decompose("가") == ("ㄱ", "ㅏ", "")
    assert decompose("물") == ("ㅁ", "ㅜ", "ㄹ")
    assert decompose("A") is None  # 비한글


@pytest.mark.parametrize("word,expected", [
    ("물", True), ("각", True), ("판", True),     # 받침 있음
    ("모", False), ("모터", False), ("가", False),  # 받침 없음
])
def test_has_batchim(word: str, expected: bool) -> None:
    assert has_batchim(word) is expected


def test_ends_with_rieul() -> None:
    assert ends_with_rieul("물") is True
    assert ends_with_rieul("불") is True
    assert ends_with_rieul("각") is False


# ── 2. 조사 이형태(받침 검증) ──────────────────────────────────────────────
@pytest.mark.parametrize("word,stem,role", [
    ("모터를", "모터", Role.OBJ), ("버튼을", "버튼", Role.OBJ),
    ("버튼이", "버튼", Role.SUBJ), ("모터가", "모터", Role.SUBJ),
    ("펌프는", "펌프", Role.TOPIC), ("밸브로", "밸브", Role.DIR),
    ("탱크에서", "탱크", Role.LOC),
])
def test_strip_particle_correct(word: str, stem: str, role: Role) -> None:
    s, r, _ = strip_particle(word)
    assert (s, r) == (stem, role)


def test_strip_particle_rejects_wrong_allomorph() -> None:
    """이형태 위반은 분절하지 않는다(거짓 분절 방지) — '가'는 무받침 뒤만 주격."""
    # '물가'의 '가'는 받침(물) 뒤라 주격 조사로 분절하면 안 된다.
    s, r, _ = strip_particle("물가")
    assert r == Role.NONE
    # 조사 없는 순수 체언
    assert strip_particle("모터") == ("모터", Role.NONE, "")


# ── 3. 용언 활용 정규화(같은 동작의 여러 표면 → 한 표제어/범주) ──────────────
@pytest.mark.parametrize("surface,lemma,cat", [
    ("돌고", "돌다", "RUN"), ("돌리고", "돌리다", "RUN"), ("돌려", "돌리다", "RUN"),
    ("돌면", "돌다", "RUN"), ("가동하면", "가동하다", "RUN"),
    ("정지하면", "정지하다", "STOP"), ("멈추게", "멈추다", "STOP"),
    ("세우면", "세우다", "STOP"), ("세워", "세우다", "STOP"),
    ("켜고", "켜다", "TURN_ON"), ("켜지면", "켜지다", "TURN_ON"),
    ("꺼줘", "끄다", "TURN_OFF"), ("끄면", "끄다", "TURN_OFF"),
    ("누르면", "누르다", "PRESS"), ("눌러", "누르다", "PRESS"),
    ("열어", "열다", "OPEN"), ("닫아", "닫다", "CLOSE"),
    ("넘으면", "넘다", "EXCEED"), ("배출하고", "배출하다", "EJECT"),
])
def test_verb_lemmatization(surface: str, lemma: str, cat: str) -> None:
    m = analyze(surface).morphemes[0]
    assert m.pos == Pos.VERB
    assert (m.lemma, m.category) == (lemma, cat)


def test_count_vs_stop_disambiguation() -> None:
    """'세면'(세다=count) vs '세우면'(세우다=stop) — 최장 스템으로 정확 구분."""
    assert analyze("세면").morphemes[0].category == "COUNT"
    assert analyze("세우면").morphemes[0].category == "STOP"


def test_passive_become_absorption() -> None:
    """'감지되면'(피동) → DETECT, '저수위 되면' → BECOME."""
    assert analyze("감지되면").morphemes[0].category == "DETECT"
    m = analyze("저수위 되면").morphemes
    assert m[0].category == "LEVEL_LO"
    assert m[1].category == "BECOME" and m[1].is_condition


# ── 4. 조건·부정·수량 ──────────────────────────────────────────────────────
def test_condition_marker() -> None:
    assert analyze("누르면").morphemes[0].is_condition is True
    assert analyze("누르고").morphemes[0].is_condition is False


def test_negation_propagates_to_verb() -> None:
    a = analyze("동시에 못 돌게")
    verbs = a.by_pos(Pos.VERB)
    assert verbs and verbs[0].category == "RUN" and verbs[0].negated is True


def test_negation_suffix_form() -> None:
    assert analyze("돌리지 않게").morphemes[0].negated is True


@pytest.mark.parametrize("word,val,cls", [
    ("10개", 10, "개"), ("3번", 3, "번"), ("5초", 5, "초"),
    ("두대", 2, "대"), ("세개", 3, "개"), ("200도", 200, "도"), ("80%", 80, "%"),
])
def test_quantity_extraction(word: str, val: int, cls: str) -> None:
    m = analyze(word).morphemes[0]
    assert m.pos == Pos.NUM
    assert (m.value, m.category) == (val, cls)


# ── 5. 설명가능 coverage(확신도 기반) ──────────────────────────────────────
def test_coverage_full_vs_partial() -> None:
    full = analyze("버튼 누르면 모터 돌고 정지 누르면 멈추게")
    assert full.coverage == 1.0
    # 도메인 밖 어휘는 정직하게 UNKNOWN → coverage 하락(확신 강등의 근거)
    partial = analyze("비전검사 불량 리젝트")
    assert partial.coverage < 0.5


def test_analysis_is_deterministic() -> None:
    t = "압력 5바 넘으면 밸브 닫아"
    assert [m.surface for m in analyze(t).morphemes] == [
        m.surface for m in analyze(t).morphemes
    ]
    assert analyze(t).coverage == analyze(t).coverage
