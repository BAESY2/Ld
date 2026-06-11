"""식음료·이차전지 산업팩 레시피 — 아날로그 임계 제어 전 경로."""

from __future__ import annotations

from app.simulator import simulate
from app.synth import synthesize_st
from app.verifier import verify
from app.wizard import build_spec


class TestFnbFillCutoff:
    def test_synth_and_verify(self) -> None:
        spec = build_spec("fnb_fill_cutoff", {})
        st = synthesize_st(spec)
        assert "NET_WEIGHT < 500" in st and "NET_WEIGHT >= 500" in st
        assert verify(spec, st).passed is True

    def test_fills_until_target_then_cuts(self) -> None:
        st = synthesize_st(build_spec("fnb_fill_cutoff", {}))
        res = simulate(
            st,
            [(0, {"BOTTLE_PRESENT": True, "NET_WEIGHT": 0}),
             (200, {"NET_WEIGHT": 250}), (400, {"NET_WEIGHT": 505}),
             (600, {"BOTTLE_PRESENT": False, "NET_WEIGHT": 0})],
            duration_ms=800, step_ms=100,
        )
        tr = res.output_trace("FILL_VALVE")
        assert tr[0] is True and tr[2] is True   # 충전 중
        assert tr[4] is False                    # 목표 도달 차단
        assert tr[6] is False                    # 용기 없음 — 재충전 금지

    def test_no_fill_without_bottle(self) -> None:
        st = synthesize_st(build_spec("fnb_fill_cutoff", {}))
        res = simulate(st, [(0, {"BOTTLE_PRESENT": False, "NET_WEIGHT": 0})],
                       duration_ms=300, step_ms=100)
        assert res.output_trace("FILL_VALVE") == [False, False, False, False]


class TestBatteryFormation:
    def test_cv_cutoff(self) -> None:
        spec = build_spec("battery_formation", {})
        st = synthesize_st(spec)
        assert verify(spec, st).passed is True
        res = simulate(
            st,
            [(0, {"CHG_START": True, "CELL_V": 3600, "CELL_TEMP": 30}),
             (300, {"CELL_V": 4100}), (600, {"CELL_V": 4205})],
            duration_ms=800, step_ms=100,
        )
        tr = res.output_trace("CHARGER")
        assert tr[1] is True and tr[4] is True
        assert tr[7] is False  # CV 도달 차단

    def test_overtemp_cuts_even_below_cv(self) -> None:
        st = synthesize_st(build_spec("battery_formation", {}))
        res = simulate(
            st,
            [(0, {"CHG_START": True, "CELL_V": 3800, "CELL_TEMP": 30}),
             (300, {"CELL_TEMP": 52})],
            duration_ms=600, step_ms=100,
        )
        tr = res.output_trace("CHARGER")
        assert tr[1] is True
        assert tr[4] is False  # 과열 즉시 차단(전압 미달이어도)

    def test_custom_thresholds(self) -> None:
        st = synthesize_st(build_spec("battery_formation", {"cv": "3650", "ot": "40"}))
        assert "CELL_V >= 3650" in st and "CELL_TEMP > 40" in st
