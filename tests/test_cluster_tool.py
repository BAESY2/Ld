"""클러스터 툴 레시피 — 검증·웨이퍼 인터록·one-hot 게이트."""

from __future__ import annotations

from app.simulator import simulate
from app.synth import synthesize_st
from app.verifier import verify
from app.wizard import build_spec


def _st() -> str:
    spec = build_spec("cluster_tool", {})
    st = synthesize_st(spec)
    report = verify(spec, st)
    assert report.passed, [c.detail for c in report.checks if not c.passed]
    return st


def test_wafer_interlock_blocks_empty_cycle() -> None:
    st = _st()
    res = simulate(
        st,
        [(0, {"WAFER_PRESENT": False, "CT_START": True}),
         (800, {"CT_START": False})],
        duration_ms=4000, step_ms=100,
    )
    for s in res.samples:
        assert not any(s.outputs.values()), s.outputs


def test_cycle_one_hot_and_full_sequence() -> None:
    st = _st()
    res = simulate(
        st,
        [(0, {"WAFER_PRESENT": True, "CT_START": True}),
         (500, {"CT_START": False})],
        duration_ms=20000, step_ms=100,
    )
    seen: set[str] = set()
    for s in res.samples:
        on = [k for k, v in s.outputs.items() if v]
        assert len(on) <= 1, s.outputs
        seen.update(on)
    assert seen == {"LL_PUMP", "TM_PICK", "PM_PROCESS", "TM_RETURN", "LL_VENT"}
