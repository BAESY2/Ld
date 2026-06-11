"""제약 팩 레시피 — 정제 중량 선별·병입 카운트 전 경로."""

from __future__ import annotations

from app.simulator import simulate
from app.synth import synthesize_st
from app.verifier import verify
from app.wizard import build_spec


class TestPillInspect:
    def test_synth_and_verify(self) -> None:
        spec = build_spec("pill_inspect", {})
        st = synthesize_st(spec)
        assert "WEIGHT < 450" in st and "WEIGHT > 550" in st
        assert verify(spec, st).passed is True

    def test_out_of_range_rejected_and_recovers(self) -> None:
        st = synthesize_st(build_spec("pill_inspect", {}))
        res = simulate(
            st,
            [(0, {"WEIGHT": 500}), (200, {"WEIGHT": 420}), (500, {"WEIGHT": 505}),
             (800, {"WEIGHT": 580})],
            duration_ms=1000, step_ms=100,
        )
        tr = res.output_trace("REJECT")
        assert tr[0] is False and tr[2] is True and tr[5] is False and tr[8] is True

    def test_custom_band(self) -> None:
        st = synthesize_st(build_spec("pill_inspect", {"lo": "95", "hi": "105"}))
        assert "WEIGHT < 95" in st and "WEIGHT > 105" in st


class TestTabletCountBottle:
    def test_counts_to_preset_then_indexes(self) -> None:
        spec = build_spec("tablet_count_bottle", {"count": "3"})
        st = synthesize_st(spec)
        assert verify(spec, st).passed is True
        tl = []
        for k in range(3):  # 정제 3정 낙하 펄스
            tl += [(200 + k * 200, {"TAB_SENSOR": True}),
                   (300 + k * 200, {"TAB_SENSOR": False})]
        tl += [(1200, {"BOTTLE_ACK": True}), (1300, {"BOTTLE_ACK": False})]
        res = simulate(st, tl, duration_ms=1500, step_ms=100)
        tr = res.output_trace("INDEXER")
        assert tr[5] is False          # 2정까지 미동작
        assert tr[8] is True           # 3정 도달 → 인덱싱
        assert tr[14] is False         # ACK 후 해제(다음 보틀)
