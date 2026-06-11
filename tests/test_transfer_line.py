"""차체 트랜스퍼 라인 레시피 — 합성·검증·인터록·시뮬 게이트."""

from __future__ import annotations

from app.simulator import simulate
from app.synth import synthesize_st
from app.verifier import verify
from app.wizard import build_spec


def _st() -> tuple[str, object]:
    spec = build_spec("transfer_line", {})
    return synthesize_st(spec), spec


def test_transfer_line_verifies() -> None:
    st, spec = _st()
    report = verify(spec, st)
    assert report.passed, [c.detail for c in report.checks if not c.passed]


def test_transfer_line_body_interlock() -> None:
    """차체 재석 없이는 어떤 출력도 켜지지 않는다(허공 용접 차단)."""
    st, _ = _st()
    res = simulate(
        st,
        [(0, {"BODY_PRESENT": False, "LINE_START": True}),
         (1000, {"LINE_START": False})],
        duration_ms=4000, step_ms=100,
    )
    for s in res.samples:
        assert not any(s.outputs.values()), s.outputs


def test_transfer_line_sequence_one_hot() -> None:
    """사이클 중 어느 시점에도 출력은 동시에 1개만 켜진다(one-hot)."""
    st, _ = _st()
    res = simulate(
        st,
        [(0, {"BODY_PRESENT": True, "LINE_START": True}),
         (500, {"LINE_START": False})],
        duration_ms=16000, step_ms=100,
    )
    seen: set[str] = set()
    for s in res.samples:
        on = [k for k, v in s.outputs.items() if v]
        assert len(on) <= 1, s.outputs
        seen.update(on)
    assert seen == {"CLAMP", "WELD_A", "WELD_B", "TRANSFER"}
