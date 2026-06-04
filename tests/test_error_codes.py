"""에러코드 KB 테스트."""

from __future__ import annotations

from app.error_codes import (
    DB,
    ErrorCode,
    ErrorCodeDB,
    Vendor,
)

# ── 기존 호환성 테스트 ─────────────────────────────────────────────────────────

def test_seed_lookup() -> None:
    entry = DB.lookup(Vendor.GENERIC, "WDT")
    assert entry is not None
    assert entry.category == "WATCHDOG"


def test_add_and_lookup() -> None:
    db = ErrorCodeDB()
    db.add(ErrorCode(vendor=Vendor.LS_ELECTRIC, code="E1", title="t", license="SELF_AUTHORED"))
    assert db.lookup(Vendor.LS_ELECTRIC, "E1") is not None
    assert db.lookup(Vendor.MITSUBISHI, "E1") is None


def test_default_license_is_unclear() -> None:
    e = ErrorCode(vendor=Vendor.OMRON, code="X", title="t")
    assert e.license == "UNCLEAR"


# ── 새 필드 후방 호환 테스트 ───────────────────────────────────────────────────

def test_new_fields_have_defaults() -> None:
    """severity, keywords 필드가 기본값으로 잘 생성되는지 확인."""
    e = ErrorCode(vendor=Vendor.GENERIC, code="TST", title="test")
    assert e.severity == ""
    assert e.keywords == []


def test_existing_entry_has_optional_new_fields() -> None:
    """기존 SEED 항목이 새 필드를 포함해도 올바르게 동작하는지 확인."""
    entry = DB.lookup(Vendor.GENERIC, "WDT")
    assert entry is not None
    # severity 와 keywords 필드가 존재하고 값이 있어야 함
    assert isinstance(entry.severity, str)
    assert isinstance(entry.keywords, list)
    assert entry.severity == "FATAL"
    assert "watchdog" in entry.keywords


# ── search() 메서드 테스트 ─────────────────────────────────────────────────────

def test_search_by_title_keyword() -> None:
    """title에 포함된 단어로 검색."""
    results = DB.search("배터리")
    assert len(results) >= 1
    codes = [r.code for r in results]
    assert "BATT_LOW" in codes


def test_search_case_insensitive() -> None:
    """대소문자 무관 검색."""
    lower = DB.search("watchdog")
    upper = DB.search("WATCHDOG")
    mixed = DB.search("WatchDog")
    assert len(lower) > 0
    assert set(r.code for r in lower) == set(r.code for r in upper) == set(r.code for r in mixed)


def test_search_by_category() -> None:
    """category 값으로 검색."""
    results = DB.search("WATCHDOG")
    assert all(r.category == "WATCHDOG" for r in results)
    assert len(results) >= 3


def test_search_by_code() -> None:
    """code 값으로 검색."""
    results = DB.search("WDT")
    assert len(results) >= 1
    assert all("WDT" in r.code.upper() for r in results)


def test_search_by_vendor_filter() -> None:
    """vendor 필터 적용 시 해당 vendor 항목만 반환."""
    all_wdt = DB.search("watchdog")
    mitsubishi_wdt = DB.search("watchdog", vendor=Vendor.MITSUBISHI)
    assert all(r.vendor == Vendor.MITSUBISHI for r in mitsubishi_wdt)
    assert len(all_wdt) >= len(mitsubishi_wdt)


def test_search_vendor_filter_excludes_others() -> None:
    """다른 vendor의 항목이 필터에서 제외되는지 확인."""
    results = DB.search("WDT", vendor=Vendor.OMRON)
    assert all(r.vendor == Vendor.OMRON for r in results)


def test_search_by_keywords() -> None:
    """keywords 필드로 검색 가능 여부 확인."""
    results = DB.search("lithium")
    assert len(results) >= 1
    assert any("lithium" in r.keywords for r in results)


def test_search_no_match_returns_empty() -> None:
    """매칭 없을 때 빈 리스트 반환."""
    results = DB.search("ZZZNOMATCH_XYZ_9999")
    assert results == []


def test_search_vendor_only_no_query_match() -> None:
    """vendor 필터는 일치하지만 query가 없는 경우."""
    results = DB.search("ZZZNOMATCH", vendor=Vendor.SIEMENS)
    assert results == []


# ── SEED 데이터 품질 테스트 ────────────────────────────────────────────────────

def test_all_seed_entries_have_vendor_and_code_and_title() -> None:
    """모든 SEED 항목이 vendor, code, title을 가져야 함."""
    for entry in DB.all():
        assert isinstance(entry.vendor, Vendor), f"Invalid vendor: {entry}"
        assert entry.code, f"Empty code: {entry}"
        assert entry.title, f"Empty title: {entry}"


def test_no_fabricated_source_urls() -> None:
    """source_url이 있는 항목은 모두 유효한 vendor/code/title을 가져야 함.
    (URL 자체를 온라인으로 검증할 수 없으므로 기본 무결성만 확인)"""
    for entry in DB.all():
        if entry.source_url:
            assert isinstance(entry.vendor, Vendor)
            assert entry.code
            assert entry.title
            # source_url이 있으면 http/https로 시작하는지 확인
            assert entry.source_url.startswith("http"), (
                f"source_url does not start with http: {entry.source_url}"
            )


def test_self_authored_entries_have_license() -> None:
    """license=SELF_AUTHORED인 항목은 code와 title이 비어 있지 않아야 함."""
    self_authored = [e for e in DB.all() if e.license == "SELF_AUTHORED"]
    assert len(self_authored) >= 10, "SEED에 SELF_AUTHORED 항목이 10개 이상이어야 함"
    for entry in self_authored:
        assert entry.code
        assert entry.title


def test_seed_covers_multiple_vendors() -> None:
    """SEED가 복수의 vendor를 포함하는지 확인."""
    vendors_in_seed = {e.vendor for e in DB.all()}
    assert Vendor.GENERIC in vendors_in_seed
    assert Vendor.LS_ELECTRIC in vendors_in_seed
    assert Vendor.MITSUBISHI in vendors_in_seed


def test_seed_minimum_count() -> None:
    """SEED에 최소 25개 항목이 있는지 확인."""
    assert len(DB.all()) >= 25


def test_severity_values_are_valid() -> None:
    """severity 값이 허용된 집합 또는 빈 문자열인지 확인."""
    allowed = {"FATAL", "WARNING", "INFO", ""}
    for entry in DB.all():
        assert entry.severity in allowed, (
            f"Unexpected severity '{entry.severity}' in entry {entry.code}"
        )


def test_keywords_are_lists_of_strings() -> None:
    """keywords 필드가 문자열 리스트인지 확인."""
    for entry in DB.all():
        assert isinstance(entry.keywords, list)
        for kw in entry.keywords:
            assert isinstance(kw, str)
