"""아날로그 수위 레시피 — NL 레시피 → 비교식 ST → 검증 → 래더 → 시뮬 전 경로."""

from __future__ import annotations

from app.simulator import simulate
from app.synth import synthesize_st
from app.transpiler import transpile_st
from app.verifier import verify
from app.wizard import build_spec


class TestAnalogLevelRecipe:
    def test_synth_emits_comparisons_and_verifies(self) -> None:
        spec = build_spec("analog_level", {})
        st = synthesize_st(spec)
        assert "LEVEL < 300" in st and "LEVEL >= 700" in st
        assert verify(spec, st).passed is True

    def test_ladder_has_comparison_contacts(self) -> None:
        spec = build_spec("analog_level", {})
        lad = transpile_st(synthesize_st(spec), title=spec.title)
        syms = {e.symbol for r in lad.rungs for b in r.input_branches for e in b.elements}
        assert "LEVEL < 300" in syms and "LEVEL < 700" in syms  # NOT(>=700) 정규화

    def test_custom_thresholds(self) -> None:
        spec = build_spec("analog_level", {"lo": "100", "hi": "900"})
        st = synthesize_st(spec)
        assert "LEVEL < 100" in st and "LEVEL >= 900" in st

    def test_simulates_with_int_timeline(self) -> None:
        spec = build_spec("analog_level", {})
        st = synthesize_st(spec)
        res = simulate(
            st,
            [(0, {"LEVEL": 500}), (200, {"LEVEL": 250}), (600, {"LEVEL": 750})],
            duration_ms=800,
            step_ms=100,
        )
        tr = res.output_trace("PUMP")
        assert tr[0] is False and tr[2] is True and tr[6] is False
