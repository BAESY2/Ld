"""전 레시피 데모 데이터 — 생성 불변식 + 배포 동기화 가드."""

from __future__ import annotations

import json

from app.wizard import RECIPES
from scripts.gen_demo_data import OUT_JS, build_payload, render_js


class TestGenDemoData:
    def test_payload_covers_all_recipes_and_verified(self) -> None:
        payload = build_payload()
        assert set(payload) == set(RECIPES)
        for rid, d in payload.items():
            assert d["passed"] is True, rid
            assert d["ladder"]["rungs"], rid
            assert d["addr"], rid
            assert d["sim"]["outputs"], rid

    def test_committed_js_in_sync(self) -> None:
        """frontend/demo-data.js == 엔진 산출물 (어긋나면 gen_demo_data.py 실행)."""
        assert OUT_JS.read_text(encoding="utf-8") == render_js(build_payload())

    def test_js_is_valid_payload(self) -> None:
        txt = OUT_JS.read_text(encoding="utf-8")
        body = txt.split("window.DEMO_ALL=", 1)[1].rstrip().rstrip(";")
        data = json.loads(body)
        assert len(data) == len(RECIPES)
