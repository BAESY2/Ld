"""에이전트 프롬프트 테스트 — 포맷 슬롯 + 한국 현장 관행 주입 확인."""

from __future__ import annotations

from app.prompts import REQUIREMENTS_ANALYST_SYSTEM, ST_ARCHITECT_SYSTEM


def test_architect_format_slots_work() -> None:
    """instruction_context/feedback 슬롯이 깨지지 않고 채워진다."""
    out = ST_ARCHITECT_SYSTEM.format(instruction_context="규격X", feedback="피드백Y")
    assert "규격X" in out
    assert "피드백Y" in out


def test_analyst_has_relay_sequence_guidance() -> None:
    """분석기 프롬프트가 한국 현장 관행(자기유지/접점) 지침을 포함한다."""
    p = REQUIREMENTS_ANALYST_SYSTEM
    assert "자기유지" in p
    assert "a접점" in p and "b접점" in p
    assert "비상정지" in p
    assert "정역" in p


def test_analyst_mandates_interlocks() -> None:
    assert "interlock" in REQUIREMENTS_ANALYST_SYSTEM
    assert "상호배타" in REQUIREMENTS_ANALYST_SYSTEM


def test_common_rules_present_in_both() -> None:
    for p in (REQUIREMENTS_ANALYST_SYSTEM, ST_ARCHITECT_SYSTEM):
        assert "IEC 61131-3" in p
        assert "이중 코일" in p
