"""데모 빌드 동기화 가드 — docs/demo 는 항상 소스에서 재현 가능해야 한다."""

from __future__ import annotations

from scripts.build_demo import ENGINE_JS, OUT_HTML, SRC_HTML, TAG, build


class TestBuildDemo:
    def test_engine_extracted_and_referenced(self) -> None:
        html = SRC_HTML.read_text(encoding="utf-8")
        assert TAG in html
        engine = ENGINE_JS.read_text(encoding="utf-8")
        assert "const DEMO" in engine and "function makePLC" in engine

    def test_build_inlines_engine(self) -> None:
        out = build(SRC_HTML.read_text(encoding="utf-8"), ENGINE_JS.read_text(encoding="utf-8"))
        assert TAG not in out
        assert "function makePLC" in out

    def test_published_copy_is_up_to_date(self) -> None:
        """docs/demo/index.html == 소스 빌드 산출물 (어긋나면 build_demo.py 실행)."""
        expected = build(
            SRC_HTML.read_text(encoding="utf-8"), ENGINE_JS.read_text(encoding="utf-8")
        )
        assert OUT_HTML.read_text(encoding="utf-8") == expected
