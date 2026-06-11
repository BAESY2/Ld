"""변형관계(metamorphic / oracle-free) 테스트 — 명세 정답 없이 스캔 결정성을 강화.

ICS 변형테스트 문헌의 관계들을 실제 레시피 위에서 검사한다:
  #1 멈춤불변(stutter-invariant) 고정점 — 입력·FB(.Q) 고정 시 코일 블록 재평가가
     1패스에 수렴(top-to-bottom seal-in 이면 성립).
  #2 입력순열 불변 — 한 스캔 안에서 동시 입력을 읽어 들이는 순서가 출력을 안 바꾼다.
  #3 STOP 지배(옵트인·보수적) — 정지 입력 TRUE 면 모터/밸브류 seal-in 출력이 1스캔에 OFF.
또한 손수 만든 스캔순서 의존 ST 를 게이트가 잡아내는지(음성 테스트) 확인한다.
"""

from __future__ import annotations

import itertools

from app.dataset.bootstrap import _check_metamorphic, _run_gates
from app.models import IODirection
from app.simulator import (
    _Program,
    coil_block_is_idempotent,
    coil_outputs,
    permutation_invariant_outputs,
    stop_dominates,
)
from app.synth import synthesize_st
from app.wizard import build_spec

# 문헌의 핵심 레시피들 — 모터(seal-in)·인터락·타이머 시퀀서·카운터·신호등.
_RECIPES = ["motor_start_stop", "fwd_rev", "car_wash", "count_eject", "timed_traffic"]


def _probe_vars(rid: str) -> tuple[str, list[str], list[str]]:
    """(ST, 입력 심볼, FB .Q 심볼) — 코일 블록이 의존하는 비코일 자유변수."""
    spec = build_spec(rid, {})
    st = synthesize_st(spec)
    inputs = [p.symbol for p in spec.io_points if p.direction == IODirection.INPUT]
    prog = _Program(st)
    fb_q = [f"{n}.Q" for n in prog.timers] + [f"{n}.Q" for n in prog.counters]
    return st, sorted(inputs), sorted(fb_q)


def _all_tables(probe: list[str]) -> list[dict[str, bool]]:
    return [
        {v: bool(mask & (1 << i)) for i, v in enumerate(probe)}
        for mask in range(1 << len(probe))
    ]


# ── 관계 #1: 멈춤불변(stutter-invariant) 고정점 ───────────────────────────────


def test_idempotent_scan_holds_on_real_recipes() -> None:
    """입력·FB(.Q) 의 모든 상태에서 코일 블록 재평가가 1패스에 고정점에 닿는다."""
    for rid in _RECIPES:
        st, inputs, fb_q = _probe_vars(rid)
        probe = inputs + fb_q
        assert len(probe) <= 10, f"{rid}: 진리표 완전탐색 변수 과다"
        for table in _all_tables(probe):
            assert coil_block_is_idempotent(st, table), (
                f"{rid}: 코일 블록이 1패스에 수렴하지 못함 @ {table}"
            )


def test_idempotence_catches_forward_reference_scan_order_bug() -> None:
    """음성: 뒤에 정의된 코일을 읽는 ST 는 1패스에 수렴하지 못해 잡힌다.

    `A := B; B := GO;` 에서 GO=TRUE 면 첫 패스의 A 는 낡은 B(FALSE)를 보고,
    같은 패스에서 B 가 TRUE 가 되어 두 번째 패스에서 A 가 뒤집힌다(스캔순서 의존).
    """
    bad = "A := B;\nB := GO;"
    assert coil_block_is_idempotent(bad, {"GO": False, "A": False, "B": False})
    assert not coil_block_is_idempotent(bad, {"GO": True, "A": False, "B": False})


# ── 관계 #2: 입력순열 불변 ────────────────────────────────────────────────────


def test_input_permutation_invariance_on_real_recipes() -> None:
    """한 스캔 안에서 동시 입력을 적용하는 순서를 바꿔도 출력이 동일하다."""
    for rid in _RECIPES:
        st, inputs, fb_q = _probe_vars(rid)
        orders = (
            [list(p) for p in itertools.permutations(inputs)]
            if len(inputs) <= 4
            else [list(inputs), list(reversed(inputs))]
        )
        for table in _all_tables(inputs + fb_q):
            snapshot = {s: table[s] for s in inputs}
            base = {s: table[s] for s in fb_q}
            assert permutation_invariant_outputs(st, base, snapshot, orders), (
                f"{rid}: 입력순열에 따라 출력이 달라짐 @ {table}"
            )


def test_permutation_invariance_is_independent_of_order_list_size() -> None:
    """빈 순서 목록은 공허 참(검사할 비교 대상 없음)."""
    st, _inputs, _fb = _probe_vars("motor_start_stop")
    assert permutation_invariant_outputs(st, {}, {"START": True, "STOP": False}, [])


# ── 관계 #3: STOP 지배(옵트인·보수적) ────────────────────────────────────────


def test_stop_dominance_on_recipes_with_stop_input() -> None:
    """STOP 같은 정지 입력이 있는 레시피에서, STOP=TRUE 가 모든 seal-in 출력을 1스캔에 끈다.

    정지 입력이 모호하면 검사를 건너뛴다(보수적 — 정당한 레시피를 거짓 기각하지 않음).
    """
    checked = []
    for rid in _RECIPES:
        spec = build_spec(rid, {})
        st = synthesize_st(spec)
        inputs = [p.symbol for p in spec.io_points if p.direction == IODirection.INPUT]
        outs = [p.symbol for p in spec.io_points if p.direction == IODirection.OUTPUT]
        stops = [s for s in inputs if "STOP" in s.upper() or "정지" in s]
        if not stops:  # 보수적으로 건너뜀(예: count_eject 는 RESET 뿐)
            continue
        assert stop_dominates(st, stops[0], outs), f"{rid}: STOP 이 출력을 지배하지 못함"
        checked.append(rid)
    assert checked, "STOP 입력을 가진 레시피가 하나도 없음(테스트 무력화)"


def test_stop_dominance_catches_non_dominant_latch() -> None:
    """음성: 정지를 무시하는 래치는 STOP=TRUE 에도 켜진 채로 남아 잡힌다."""
    non_dominant = "MOTOR := (START OR MOTOR);"
    dominant = "MOTOR := (START OR MOTOR) AND NOT STOP;"
    assert not stop_dominates(non_dominant, "STOP", ["MOTOR"])
    assert stop_dominates(dominant, "STOP", ["MOTOR"])


def test_stop_dominance_is_vacuous_true_when_no_target_output() -> None:
    """대상 출력이 없으면 공허 참(검사 대상 없음 → 거짓 기각 방지)."""
    assert stop_dominates("MOTOR := START AND NOT STOP;", "STOP", ["NONEXISTENT"])


# ── 게이트 통합: metamorphic 게이트가 레시피를 거짓 기각하지 않음 ──────────────


def test_metamorphic_gate_passes_all_recipes() -> None:
    """모든 레시피(baseline)가 새 metamorphic 게이트를 통과한다(거짓 기각 0)."""
    from app.wizard import RECIPES

    for rid in RECIPES:
        spec = build_spec(rid, {})
        st = synthesize_st(spec)
        assert _check_metamorphic(st, spec) == "", f"{rid}: metamorphic 위반"
        gates, _st, fp, reason = _run_gates(spec)
        assert gates["metamorphic"] is True, f"{rid}: {reason}"
        assert fp, f"{rid}: 지문이 비어 게이트 미통과"


def test_metamorphic_appended_to_gate_names() -> None:
    """게이트 이름 목록 끝에 metamorphic 이 추가됐다."""
    from app.dataset.bootstrap import _GATE_NAMES

    assert _GATE_NAMES[-1] == "metamorphic"
    assert "metamorphic" in _GATE_NAMES


def test_coil_outputs_match_program_driven() -> None:
    """coil_outputs 헬퍼가 시뮬레이터 _Program.driven 과 일치한다(파서 재사용 확인)."""
    st, _i, _f = _probe_vars("fwd_rev")
    assert coil_outputs(st) == list(_Program(st).driven)
