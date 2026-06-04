"""FastAPI 서버 엔드포인트 테스트."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from app.server import app  # noqa: E402

client = TestClient(app)


def test_healthz() -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_transpile_ok() -> None:
    r = client.post("/api/transpile", json={"st_code": "MOTOR := START AND NOT STOP;"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert len(data["ladder"]["rungs"]) == 1
    assert data["ladder"]["rungs"][0]["outputs"][0]["symbol"] == "MOTOR"


def test_transpile_detects_double_coil() -> None:
    r = client.post("/api/transpile", json={"st_code": "L := A;\nL := B;\n"})
    data = r.json()
    assert data["ok"] is False
    assert any(i["code"] == "DOUBLE_COIL" for i in data["issues"])


def test_transpile_parse_error_is_graceful() -> None:
    r = client.post("/api/transpile", json={"st_code": "X := A AND ;"})
    assert r.status_code == 200
    data = r.json()
    assert any(i["code"] == "PARSE_ERROR" for i in data["issues"])
