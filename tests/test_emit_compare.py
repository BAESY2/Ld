"""비교 접점 → 벤더 IL 비교명령 출력 테스트 (아날로그 최종 조각)."""

from __future__ import annotations

from app.emit import emit
from app.synth import synthesize_st
from app.transpiler import transpile_st
from app.vendors.profiles import get_profile
from app.wizard import build_spec


def _ladder():  # type: ignore[no-untyped-def]
    spec = build_spec("analog_level", {})
    return transpile_st(synthesize_st(spec), title=spec.title)


class TestCompareIL:
    def test_ls_xgk_compare_instructions(self) -> None:
        text = emit(_ladder(), get_profile("LS_XGK"))
        assert "LOAD< LEVEL 300" in text or "LD< LEVEL 300" in text
        assert "< LEVEL 700" in text  # 자기유지 브랜치의 AND< LEVEL 700

    def test_melsec_uses_k_literal(self) -> None:
        text = emit(_ladder(), get_profile("MITSUBISHI_FX"))
        assert "LD< LEVEL K300" in text
        assert "AND< LEVEL K700" in text

    def test_xgi_iec_il_uses_lt_blocks(self) -> None:
        text = emit(_ladder(), get_profile("LS_XGI"))
        assert "LT 300" in text
        assert "LT 700" in text

    def test_scl_passthrough_parenthesized(self) -> None:
        text = emit(_ladder(), get_profile("SIEMENS_S7_SCL"))
        assert "(LEVEL < 300)" in text
        assert "(LEVEL < 700)" in text
