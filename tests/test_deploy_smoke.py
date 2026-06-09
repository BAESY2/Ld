"""배포 스모크 테스트 — Docker 불필요(CI 안전).

배포 이미지가 실제로 떠서 동작할지의 최소 보증을:
앱 임포트 → /healthz → 정적 프론트(/) → /api/recipes(키 불필요 경로)로 확인한다.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from app.server import app  # noqa: E402

client = TestClient(app)


def test_healthz_ok() -> None:
    """헬스체크가 ok 를 반환(Dockerfile HEALTHCHECK 가 노리는 엔드포인트)."""
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_root_serves_frontend_index() -> None:
    """루트가 정적 프론트(라이브 페이지)를 서빙한다."""
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<html" in r.text.lower() or "<!doctype" in r.text.lower()


def test_root_is_live_landing_page() -> None:
    """루트가 라이브 입력 페이지(/api/compile 호출 + 시뮬 엔진)를 서빙한다."""
    r = client.get("/")
    assert r.status_code == 200
    assert "/api/compile" in r.text       # 아무 한국어나 라이브 컴파일
    assert "sim-engine.js" in r.text      # 브라우저 내 가상 PLC 가동
    assert "ladder-render.js" in r.text   # 살아 움직이는 래더


def test_live_static_assets_served() -> None:
    """라이브 페이지가 의존하는 정적 JS 가 실제로 서빙된다(404 아님)."""
    for asset in ("/sim-engine.js", "/ladder-render.js", "/live.html"):
        r = client.get(asset)
        assert r.status_code == 200, asset


def test_recipes_keyfree_path_nonempty() -> None:
    """LLM 키 없이도 동작하는 마법사 레시피가 0개보다 많다(키-프리 기본 동작 보증)."""
    r = client.get("/api/recipes")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) > 0
