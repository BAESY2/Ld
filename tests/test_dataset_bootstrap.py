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


# ── RED-TEAM 라운드4 회귀 잠금 테스트 ────────────────────────────────────────

def _const_output_spec(expr: str):
    """단일 입력 GO 로만 구동되는 파생 출력 OUT := <expr> 명세."""
    from app.models import (
        DerivedOutput,
        IODirection,
        IOPoint,
        SfcState,
        StateMachineSpec,
    )

    return StateMachineSpec(
        io_points=[
            IOPoint(symbol="GO", direction=IODirection.INPUT),
            IOPoint(symbol="OUT", direction=IODirection.OUTPUT),
        ],
        states=[SfcState(name="IDLE", is_initial=True)],
        derived_outputs=[DerivedOutput(output="OUT", expression=expr)],
    )


def test_non_vacuity_rejects_tautology_and_contradiction() -> None:
    """입력에 무감(無感)한 자명/죽은 코일(항상 ON / 항상 OFF)은 제외된다.

    구버그: 식이 변수를 '참조만' 하면(예: GO AND NOT GO) 비공허로 통과 → 죽은
    출력이 '검증된 안전 샘플'로 코퍼스에 들어왔다.
    """
    from app.dataset.bootstrap import _run_gates

    for expr in ("GO AND NOT GO", "GO OR NOT GO"):
        gates, _st, fp, reason = _run_gates(_const_output_spec(expr))
        assert gates["non_vacuous"] is False, f"{expr} 가 비공허로 잘못 통과"
        assert fp == ""
        assert "non_vacuous" in reason


def test_determinism_gate_catches_comment_nondeterminism(monkeypatch) -> None:
    """주석에 심긴 비결정성(난수 nonce)도 determinism 게이트가 잡아야 한다.

    구버그: 게이트가 _canonical_st(주석 제거) 비교만 해서, 주석 nonce 가 매 실행
    달라져도 통과 → 비결정 ST 가 그대로 지속 산출물에 새어 들어갔다.
    """
    import random

    import app.dataset.bootstrap as B
    from app.synth import synthesize_st as real_synth
    from app.wizard import build_spec

    monkeypatch.setattr(
        B, "synthesize_st", lambda spec: real_synth(spec) + f"\n// nonce {random.random()}"
    )
    gates, _st, fp, reason = B._run_gates(build_spec("motor_start_stop", {}))
    assert gates["determinism"] is False
    assert fp == ""
    assert "determinism" in reason


def test_canonical_preserves_timer_type_no_fingerprint_collision() -> None:
    """타이머 타입(TON/TOF)만 다른 두 ST 는 시뮬 의미가 달라 지문이 달라야 한다.

    구버그: 정규화가 `// 타이머 T1 (TON/TOF...)` 주석을 제거 → TON·TOF 가 같은
    지문으로 충돌해 의미가 다른 샘플이 'near-dup' 으로 잘못 제거됐다.
    """
    from app.dataset.bootstrap import _canonical_st, _hash
    from app.models import (
        IODirection,
        IOPoint,
        SfcState,
        StateMachineSpec,
        TimerSpec,
        Transition,
    )
    from app.synth import synthesize_st

    def mk(ttype: str) -> StateMachineSpec:
        return StateMachineSpec(
            io_points=[
                IOPoint(symbol="GO", direction=IODirection.INPUT),
                IOPoint(symbol="OUT", direction=IODirection.OUTPUT),
            ],
            timers=[TimerSpec(name="T1", preset_ms=1000, enable_condition="GO",
                              timer_type=ttype)],
            states=[SfcState(name="IDLE", is_initial=True),
                    SfcState(name="ON", on_entry=["OUT := TRUE;"])],
            transitions=[
                Transition(from_state="IDLE", to_state="ON", condition="T1.Q"),
                Transition(from_state="ON", to_state="IDLE", condition="NOT T1.Q"),
            ],
        )

    fp_ton = _hash(_canonical_st(synthesize_st(mk("TON"))))
    fp_tof = _hash(_canonical_st(synthesize_st(mk("TOF"))))
    assert fp_ton != fp_tof, "TON/TOF 가 같은 지문으로 충돌(의미 손실)"


def test_mutex_gate_actually_energizes_interlock_recipes() -> None:
    """인터락 레시피의 출력이 실제로 켜지는 트레이스로 mutex 가 검사돼야 한다.

    구버그: mutex 자극이 '모든 입력 동시 ON' 스냅샷이라 STOP/REV 까지 켜져 기계가
    IDLE 에 갇혀 어떤 출력도 안 켜졌다 → 인터락 검사가 공허하게 통과했다.
    """
    from app.dataset.bootstrap import _exercise
    from app.synth import synthesize_st
    from app.wizard import build_spec

    for rid in ("fwd_rev", "jog_run", "star_delta"):
        spec = build_spec(rid, {})
        res = _exercise(synthesize_st(spec), spec)
        outs = [p.symbol for p in spec.io_points if p.direction.name == "OUTPUT"]
        ever_on = {o for s in res.samples for o in outs if s.outputs.get(o)}
        assert ever_on, f"{rid}: 자극으로 어떤 출력도 켜지지 않음(mutex 공허)"


def test_generate_rejects_unknown_recipe_id_clearly() -> None:
    """알 수 없는 레시피 id 는 명확한 KeyError 로 거른다(원시 dict KeyError 아님)."""
    import pytest

    from app.dataset import generate

    with pytest.raises(KeyError, match="알 수 없는 레시피"):
        generate(["motor_start_stop", "__does_not_exist__"])
