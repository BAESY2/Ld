"""신규 산업 레시피 6종(도장·랩핑·OHT·파레타이저·집진·2액혼합) 게이트."""

from __future__ import annotations

import pytest

from app.simulator import simulate
from app.synth import synthesize_st
from app.verifier import verify
from app.wizard import RECIPES, build_spec

NEW_IDS = ["paint_booth", "stretch_wrap", "oht_transport",
           "palletizer", "dust_collector", "dosing_mix"]


@pytest.mark.parametrize("rid", NEW_IDS)
def test_recipe_registered_and_verifies(rid: str) -> None:
    assert rid in RECIPES
    spec = build_spec(rid, {})
    st = synthesize_st(spec)
    report = verify(spec, st)
    assert report.passed, [c.detail for c in report.checks if not c.passed]


def test_oht_carrier_interlock() -> None:
    """캐리어 미파지 시 어떤 출력도 켜지지 않는다(낙하 방지)."""
    spec = build_spec("oht_transport", {})
    st = synthesize_st(spec)
    res = simulate(
        st,
        [(0, {"CARRIER_PRESENT": False, "OHT_START": True}),
         (800, {"OHT_START": False})],
        duration_ms=4000, step_ms=100,
    )
    for s in res.samples:
        assert not any(s.outputs.values()), s.outputs


def test_dust_collector_hysteresis() -> None:
    """차압 상한에서 펄스 ON, 하한 복귀에서 OFF — 히스테리시스."""
    spec = build_spec("dust_collector", {})
    st = synthesize_st(spec)
    res = simulate(
        st,
        [(0, {"FILTER_DP": 50}), (500, {"FILTER_DP": 200}),
         (1500, {"FILTER_DP": 120}), (2500, {"FILTER_DP": 60})],
        duration_ms=3500, step_ms=100,
    )
    by_t = {s.t_ms: s.outputs["PULSE_VALVE"] for s in res.samples}
    assert by_t[400] is False          # 상한 전
    assert by_t[1000] is True          # 상한 도달 → ON
    assert by_t[2000] is True          # 중간값(하한 미만 아님) → 유지
    assert by_t[3000] is False         # 하한 복귀 → OFF


def test_dosing_mix_pumps_mutually_exclusive() -> None:
    """A/B 펌프는 어떤 시점에도 동시에 켜지지 않는다(인터락)."""
    spec = build_spec("dosing_mix", {})
    st = synthesize_st(spec)
    res = simulate(
        st,
        [(0, {"DOSE_START": True, "VOL_A": 0, "VOL_B": 0}),
         (1000, {"VOL_A": 700}), (2000, {"VOL_B": 500})],
        duration_ms=3000, step_ms=100,
    )
    seen: set[str] = set()
    for s in res.samples:
        assert not (s.outputs["PUMP_A"] and s.outputs["PUMP_B"]), s.outputs
        seen.update(k for k, v in s.outputs.items() if v)
    assert seen == {"PUMP_A", "PUMP_B"}
