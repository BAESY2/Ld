"""검증 게이트 자기증식 데이터셋 테스트 — 축적된 데이터로 결정론 강화.

핵심 보장: 누적된 모든 샘플은 5개 결정론 게이트를 통과하며, 코퍼스 생성 자체가
완전 결정론(같은 입력 → 같은 지문)이고, 모든 레시피의 baseline 이 살아남는다.
"""

from __future__ import annotations

import json

from app.dataset import generate, write_dataset
from app.dataset.bootstrap import _GATE_NAMES, _canonical_st, _numeric_variants
from app.wizard import RECIPES


def test_numeric_variants_deterministic() -> None:
    assert _numeric_variants("5") == ["1", "2", "5"]
    assert _numeric_variants("1") == ["1", "2"]
    assert _numeric_variants("garbage") == ["1", "2"]


def test_every_accepted_sample_passes_all_gates() -> None:
    """누적된 샘플은 예외 없이 5개 게이트를 모두 통과한다(코퍼스 무결성)."""
    rep = generate()
    assert rep.samples, "샘플이 하나도 누적되지 않음"
    for s in rep.samples:
        assert set(s.gates) == set(_GATE_NAMES)
        assert all(s.gates.values()), f"{s.sample_id}: 게이트 미통과 {s.gates}"


def test_all_recipes_baseline_survive() -> None:
    """모든 레시피의 기본값(baseline)이 게이트를 통과해 코퍼스에 들어온다."""
    rep = generate()
    assert rep.recipe_ids == set(RECIPES), (
        f"누락 레시피: {set(RECIPES) - rep.recipe_ids}"
    )


def test_corpus_generation_is_deterministic() -> None:
    """같은 입력으로 두 번 생성하면 지문 집합이 바이트 동일(결정론 엔진의 증명)."""
    a = generate()
    b = generate()
    fa = [(s.sample_id, s.fingerprint, s.trace_fingerprint) for s in a.samples]
    fb = [(s.sample_id, s.fingerprint, s.trace_fingerprint) for s in b.samples]
    assert fa == fb


def test_fingerprints_are_unique() -> None:
    """중복(near-dup) 제거가 동작 — 지문이 겹치는 샘플은 없다."""
    rep = generate()
    fps = [s.fingerprint for s in rep.samples]
    assert len(fps) == len(set(fps))


def test_counts_are_consistent() -> None:
    rep = generate()
    # 통과 + 거절은 후보 수 이하(중복제거로 통과<후보 가능)
    assert rep.passed + rep.rejected <= rep.total_candidates
    assert rep.passed == len(rep.samples)
    assert rep.unique == rep.passed


def test_write_dataset_roundtrips(tmp_path) -> None:
    rep = generate(["motor_start_stop", "fwd_rev"])
    out = write_dataset(rep, tmp_path / "ds.json")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["summary"]["passed"] == rep.passed
    assert set(data["summary"]["recipes"]) == rep.recipe_ids
    assert len(data["samples"]) == rep.passed
    # 직렬화된 샘플은 ST 와 게이트를 보존한다
    first = data["samples"][0]
    assert first["st"] and first["fingerprint"]
    assert all(first["gates"].values())


def test_canonical_st_strips_comments_and_whitespace() -> None:
    raw = "// 주석\nMOTOR  :=   START ;\n\n// 또 주석\n"
    assert _canonical_st(raw) == "MOTOR := START ;"


def test_non_vacuity_gate_rejects_constant_output() -> None:
    """상수 출력(OUT := FALSE)은 검증을 공허하게 통과해도 코퍼스에서 제외된다."""
    from app.dataset.bootstrap import _run_gates
    from app.models import (
        DerivedOutput,
        IODirection,
        IOPoint,
        SfcState,
        StateMachineSpec,
    )

    spec = StateMachineSpec(
        io_points=[
            IOPoint(symbol="GO", direction=IODirection.INPUT),
            IOPoint(symbol="OUT", direction=IODirection.OUTPUT),
        ],
        states=[SfcState(name="IDLE", is_initial=True)],
        derived_outputs=[DerivedOutput(output="OUT", expression="FALSE")],
    )
    gates, _st, fp, reason = _run_gates(spec)
    assert gates["verified"] is True       # 형식 검증은 공허하게 통과하지만
    assert gates["non_vacuous"] is False   # 비공허성 게이트가 잡아낸다
    assert fp == ""
    assert "non_vacuous" in reason
