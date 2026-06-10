"""에러코드 지식베이스(브랜드별 자료화) 테스트 — 충실도·출처·문서 동기."""

from __future__ import annotations

from app.error_codes import DB, Vendor


def test_kb_breadth_per_vendor() -> None:
    """브랜드별 최소 충실도 — 4사 + 공통 수칙이 모두 자료화돼 있다."""
    assert len(DB.search("", Vendor.LS_ELECTRIC)) >= 18
    assert len(DB.search("", Vendor.MITSUBISHI)) >= 22
    assert len(DB.search("", Vendor.SIEMENS)) >= 14
    assert len(DB.search("", Vendor.OMRON)) >= 8
    assert len(DB.search("")) >= 100


def test_kb_entries_have_substance_and_source() -> None:
    """확장 항목은 원인·조치(자체 작성)와 근거 출처를 갖춘다(빈 껍데기 금지)."""
    from app.error_kb import KB_ENTRIES

    for e in KB_ENTRIES:
        assert e.likely_cause and e.suggested_action, e.code
        assert len(e.suggested_action) >= 30, f"{e.code}: 조치가 너무 빈약"
        assert e.license == "SELF_AUTHORED"
        if e.vendor != Vendor.GENERIC:
            assert e.source_url, f"{e.code}: 출처 누락"


def test_kb_search_finds_practical_items() -> None:
    """실무 검색 시나리오 — 키워드로 곧장 해결 항목에 닿는다."""
    assert any(e.code == "6706" for e in DB.search("인덱스"))
    assert any("진단버퍼" in e.suggested_action for e in DB.search("SF", Vendor.SIEMENS))
    assert any(e.code == "BAT-LED" for e in DB.search("배터리", Vendor.LS_ELECTRIC))


def test_errorcodes_doc_in_sync() -> None:
    """docs/ERRORCODES.md 는 DB 에서 결정론 생성 — 재생성 결과와 일치해야 한다."""
    from pathlib import Path

    from scripts.build_errorcodes_doc import build

    committed = (Path(__file__).resolve().parent.parent / "docs" / "ERRORCODES.md")
    assert committed.read_text(encoding="utf-8") == build()


def test_error_kb_importable_first() -> None:
    """회귀(순환 임포트): app.error_kb 를 먼저 import 해도 안전해야 한다."""
    import subprocess
    import sys

    code = "import app.error_kb; import app.error_codes; " \
           "print(len(app.error_codes.DB.search('')))"
    out = subprocess.run([sys.executable, "-c", code],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert int(out.stdout.strip()) >= 100
