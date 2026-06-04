"""에러코드 KB 테스트."""

from __future__ import annotations

from app.error_codes import DB, ErrorCode, ErrorCodeDB, Vendor


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
