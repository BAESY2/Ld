"""PLC 기종 카탈로그·설계 적합성 검사 테스트."""

from __future__ import annotations

from app.catalog import CATALOG, check_fit, estimate_steps, list_models, suggest
from app.synth import synthesize_st
from app.transpiler import transpile_st
from app.wizard import build_spec


def _design(rid: str = "car_wash"):  # type: ignore[no-untyped-def]
    spec = build_spec(rid, {})
    ladder = transpile_st(synthesize_st(spec), title=spec.title)
    return spec, ladder


class TestCatalog:
    def test_four_vendors_present(self) -> None:
        vendors = {m.vendor for m in CATALOG}
        assert vendors == {"LS", "MITSUBISHI", "SIEMENS", "OMRON"}
        for v in vendors:
            assert len(list_models(v)) >= 3 or v == "SIEMENS"

    def test_every_model_has_source_and_capacity(self) -> None:
        for m in CATALOG:
            assert m.source.startswith("https://")
            assert m.capacity
            assert m.dio_max > 0

    def test_small_design_fits_smallest_ls(self) -> None:
        spec, ladder = _design()
        small = next(m for m in CATALOG if m.model == "XBC-DR32H")
        assert check_fit(spec, ladder, small) == []

    def test_io_overflow_detected(self) -> None:
        spec, ladder = _design()
        tiny = type(CATALOG[0])(
            vendor="LS", series="T", model="TINY-2", dio_max=2, steps_k=1,
            capacity="1K 스텝", timers_max=0, counters_max=0, comm=(),
            profile=None, source="https://example.com",
        )
        issues = check_fit(spec, ladder, tiny)
        assert any("I/O" in i for i in issues)
        assert any("타이머" in i for i in issues)  # car_wash 는 TON 3개

    def test_suggest_returns_fitting_model(self) -> None:
        spec, ladder = _design()
        m = suggest(spec, ladder, vendor="LS")
        assert m is not None and m.vendor == "LS"
        assert check_fit(spec, ladder, m) == []

    def test_estimate_steps_positive_and_counts_fb(self) -> None:
        spec, ladder = _design()
        est = estimate_steps(ladder)
        assert est > 0
        spec2, ladder2 = _design("motor_start_stop")
        assert estimate_steps(ladder2) < est  # 단순 설계가 더 작아야 함


class TestCatalogApi:
    def test_catalog_endpoints(self) -> None:
        from fastapi.testclient import TestClient

        from app.server import app

        c = TestClient(app)
        data = c.get("/api/catalog", params={"vendor": "LS"}).json()
        assert len(data) >= 3 and all(d["vendor"] == "LS" for d in data)
        fit = c.get("/api/catalog/fit", params={"recipe": "car_wash"}).json()
        assert fit["ok"] is True and fit["suggest"]
        assert c.get("/api/catalog/fit", params={"recipe": "nope"}).json()["ok"] is False
