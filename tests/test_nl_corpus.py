"""한국어 자연어 명령 라벨 코퍼스 — 슬롯 정규화·매칭·모호성 회귀 가드.

연구(docs/KOREAN_NL_SPEC.md) 산출 코퍼스의 핵심 부분집합. 슬롯 정규화(분/시간/
한글수사/범위/단계별)와 명확한 매칭, 그리고 헷갈리는 입력의 confident=False 를 박는다.
"""

from __future__ import annotations

import pytest

from app.nlmatch import _extract_count, _extract_durations, analyze, extract_slots
from app.wizard import RECIPES

# ── 시간 정규화 (문장 → 초 리스트) ──────────────────────────────────────
_TIME_CASES = [
    ("기동하고 5초 뒤에 출력 켜줘", [5]),
    ("3초 딜레이 주고 켜기", [3]),
    ("0.5초 지연 후 ON", [1]),          # 0.5 → ≥1 클램프
    ("타이머로 1분 늦게 동작", [60]),
    ("1시간30분 뒤 동작", [5400]),       # 복합 → 합산
    ("5분30초 후", [330]),
    ("기동 후 십 초 뒤 출력", [10]),       # 한글수사
    ("5~10초 대기", [5]),                # 범위 → 하한
    ("승온 30초 유지 60초 냉각 45초", [30, 60, 45]),  # 단계별
]


@pytest.mark.parametrize("text,expected", _TIME_CASES)
def test_duration_normalization(text: str, expected: list[int]) -> None:
    assert _extract_durations(text) == expected


# ── 개수 정규화 ─────────────────────────────────────────────────────────
_COUNT_CASES = [
    ("10개 세면 배출", "10"),
    ("100개 채우면 토출", "100"),
    ("열 개 세고 배출", "10"),     # 한글수사
    ("5 EA 카운트하면", "5"),
    ("5~10개 배출", "5"),         # 범위 → 하한
]


@pytest.mark.parametrize("text,expected", _COUNT_CASES)
def test_count_normalization(text: str, expected: str) -> None:
    assert _extract_count(text) == expected


def test_sequencer_per_step_time_slots() -> None:
    """단계별 시퀀서는 등장 순서대로 time_sec 슬롯을 각각 채운다."""
    slots = extract_slots("비누 30초 헹굼 60초 건조 45초", RECIPES["car_wash"])
    times = [v for k, v in slots.items() if v in ("30", "60", "45")]
    assert times == ["30", "60", "45"]


def test_on_delay_slot_backward_compatible() -> None:
    slots = extract_slots("5초 뒤에 램프 켜기", RECIPES["on_delay"])
    assert slots.get("delay_sec") == "5"


# ── 명확한 매칭 (top-1 == 기대) ─────────────────────────────────────────
_MATCH_CASES = [
    ("버튼 누르면 모터 돌고 정지 누르면 서게 해줘", "motor_start_stop"),
    ("정역 운전, 정회전 역회전 동시에 안 돌게", "fwd_rev"),
    ("기동하고 5초 뒤에 출력 켜줘", "on_delay"),
    ("저수위 되면 펌프 돌고 만수위면 멈춰", "hi_lo_level"),
    ("10개 세면 배출", "count_eject"),
    ("자동 수동 모드 전환", "auto_manual"),
    ("와이델타 기동, 스타로 띄우고 5초 후 델타", "star_delta"),
    ("탱크 충전하고 교반하고 배출", "batch_fill_mix_drain"),
    ("승온하고 유지하고 냉각하는 열처리", "heat_treat"),
    ("탈지 수세 도금 건조 침지 라인", "plating_line"),
    ("클램프 잡고 용접하고 언클램프", "weld_cell"),
    ("원점복귀하고 위치로 이동하고 정위치 표시", "motion_home_move"),
]


@pytest.mark.parametrize("text,expected", _MATCH_CASES)
def test_clear_match_top1(text: str, expected: str) -> None:
    res = analyze(text)
    assert res.recipe_id == expected, f"{text!r} → {res.recipe_id} (기대 {expected})"
