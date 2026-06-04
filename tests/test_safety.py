"""안전 경계 고지(K3) 테스트."""

from __future__ import annotations

import pytest

from app.safety import SAFETY_INLINE_HINT, SAFETY_NOTICE, safety_payload


def test_notice_mentions_estop_and_hardwire() -> None:
    """고지문이 E-stop과 하드와이어 안전회로를 명시해야 한다."""
    assert "E-stop" in SAFETY_NOTICE
    assert "하드와이어" in SAFETY_NOTICE


def test_notice_references_standards() -> None:
    """고지문이 안전 표준(ISO 13849 / IEC 62061)을 인용해야 한다."""
    assert "ISO 13849" in SAFETY_NOTICE
    assert "IEC 62061" in SAFETY_NOTICE


def test_notice_disclaims_safety_certification() -> None:
    """검증이 안전을 보장하지 않음을 분명히 해야 한다."""
    assert "보장하지 않" in SAFETY_NOTICE
    assert "SIL2+" in SAFETY_NOTICE


def test_inline_hint_is_comment() -> None:
    """인라인 힌트는 ST 주석(//) 형태여야 한다."""
    assert SAFETY_INLINE_HINT.startswith("//")


def test_safety_payload_shape() -> None:
    payload = safety_payload()
    assert payload == {"notice": SAFETY_NOTICE}


def test_safety_endpoint() -> None:
    """GET /api/safety 가 고지문을 반환해야 한다."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.server import app

    client = TestClient(app)
    r = client.get("/api/safety")
    assert r.status_code == 200
    assert r.json()["notice"] == SAFETY_NOTICE
