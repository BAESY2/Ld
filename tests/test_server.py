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


def test_emit_mitsubishi() -> None:
    r = client.post(
        "/api/emit",
        json={"st_code": "MOTOR := (START OR MOTOR) AND NOT STOP;", "vendor": "MITSUBISHI_FX"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "ORB" in data["text"]
    assert "LD " in data["text"]


def test_emit_unknown_vendor() -> None:
    r = client.post("/api/emit", json={"st_code": "Y := A;", "vendor": "NOPE"})
    data = r.json()
    assert data["ok"] is False
    assert "알 수 없는 벤더" in data["error"]


def test_safety_endpoint_returns_notice() -> None:
    r = client.get("/api/safety")
    assert r.status_code == 200
    assert "하드와이어" in r.json()["notice"]


def test_export_plcopen() -> None:
    r = client.post(
        "/api/export/plcopen",
        json={"st_code": "MOTOR := (START OR MOTOR) AND NOT STOP;", "title": "t"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "http://www.plcopen.org/xml/tc6_0201" in data["content"]
    assert "MOTOR" in data["content"]


def test_generate_files_stream(tmp_path, monkeypatch) -> None:
    # 서버 출력 디렉터리를 tmp 로, LLM 호출 차단
    import dataclasses

    import app.server as srv
    from app import agents

    new_settings = dataclasses.replace(srv.settings, gen_out_dir=str(tmp_path))
    monkeypatch.setattr(srv, "settings", new_settings)
    monkeypatch.setattr(
        agents, "_llm", lambda m: (_ for _ in ()).throw(AssertionError("no LLM"))
    )
    r = client.post(
        "/api/generate/files",
        json={"st_code": "MOTOR := (START OR MOTOR) AND NOT STOP;", "name": "web",
              "vendors": ["LS_XGK"]},
    )
    assert r.status_code == 200
    body = r.text
    assert "event: progress" in body
    assert "event: manifest" in body
    assert "program.st" in body


def test_read_generated_file(tmp_path, monkeypatch) -> None:
    import dataclasses

    import app.server as srv
    from app import agents

    new_settings = dataclasses.replace(srv.settings, gen_out_dir=str(tmp_path))
    monkeypatch.setattr(srv, "settings", new_settings)
    monkeypatch.setattr(
        agents, "_llm", lambda m: (_ for _ in ()).throw(AssertionError("no LLM"))
    )
    client.post(
        "/api/generate/files",
        json={"st_code": "MOTOR := START AND NOT STOP;", "name": "web2", "vendors": ["LS_XGK"]},
    )
    r = client.get("/api/generated/web2/program.st")
    assert r.status_code == 200
    assert "MOTOR" in r.text
    # 경로 탈출 차단
    bad = client.get("/api/generated/web2/../../etc/passwd")
    assert bad.status_code in (400, 404)


def test_responses_carry_safety_notice() -> None:
    """코드를 내보내는 응답에 안전 경계 고지가 포함된다(K3)."""
    t = client.post("/api/transpile", json={"st_code": "M := A;"}).json()
    assert "하드와이어" in t["safety_notice"]
    e = client.post("/api/emit", json={"st_code": "M := A;", "vendor": "LS_XGK"}).json()
    assert "하드와이어" in e["safety_notice"]
    x = client.post("/api/export/plcopen", json={"st_code": "M := A;"}).json()
    assert "하드와이어" in x["safety_notice"]


def test_garbage_st_is_not_ok() -> None:
    """대입문이 아닌 입력은 NO_LOGIC 으로 ok=False (가짜 통과 방지)."""
    t = client.post("/api/transpile", json={"st_code": "이건 ST 가 아님"}).json()
    assert t["ok"] is False
    assert any(i["code"] == "NO_LOGIC" for i in t["issues"])
    e = client.post("/api/emit", json={"st_code": "이건 ST 가 아님", "vendor": "LS_XGK"}).json()
    assert e["ok"] is False
