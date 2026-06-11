"""단일 파일 데모 빌더 — twin-engine.js 를 investor-demo.html 에 인라인.

GitHub Pages(docs/demo/index.html)는 오프라인 단일 파일 원칙을 유지한다.
소스(frontend/investor-demo.html + frontend/twin-engine.js)를 수정한 뒤
``python scripts/build_demo.py`` 로 산출물을 갱신한다(테스트가 동기화를 강제).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_HTML = ROOT / "frontend" / "investor-demo.html"
ENGINE_JS = ROOT / "frontend" / "twin-engine.js"
OUT_HTML = ROOT / "docs" / "demo" / "index.html"
TAG = '<script src="twin-engine.js"></script>'


def build(html: str, engine: str) -> str:
    """src 태그를 엔진 본문 인라인으로 치환한 단일 파일 HTML 을 돌려준다."""
    if TAG not in html:
        raise ValueError(f"인라인 마커가 없습니다: {TAG}")
    return html.replace(TAG, "<script>\n" + engine + "</script>", 1)


ASSETS = [
    (ROOT / "frontend" / "vendor" / "three.min.js", OUT_HTML.parent / "three.min.js"),
    (ROOT / "frontend" / "twin3d.js", OUT_HTML.parent / "twin3d.js"),
]


def main() -> None:
    out = build(SRC_HTML.read_text(encoding="utf-8"), ENGINE_JS.read_text(encoding="utf-8"))
    OUT_HTML.write_text(out, encoding="utf-8")
    for src, dst in ASSETS:
        dst.write_bytes(src.read_bytes())
    print(f"built {OUT_HTML} ({len(out):,} bytes) + assets {len(ASSETS)}")


if __name__ == "__main__":
    main()
