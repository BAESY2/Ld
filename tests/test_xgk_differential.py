"""XGK 니모닉 인터프리터 ↔ ST 시뮬레이터 차분(differential) 검증.

각 레시피에 대해 synthesize_st → transpile_st → emit(LS_XGK) 로 XGK 니모닉을
뽑고, **같은 입력 타임라인**으로 XGK 인터프리터와 검증된 ST 시뮬레이터를 함께
돌려, 출력 트레이스가 샘플 단위로 일치함을 단언한다. 이로써 에미트된 XGK 가
검증된 ST 와 동치임을 증명한다.

추가:
  (a) NEGATIVE — 니모닉 한 줄을 변조하면 차분이 발산을 *검출*한다(검사 비공허성).
  (b) TIMING — 타이머 발화 샘플이 두 엔진에서 동일(타이밍 패리티).
  (c) DETERMINISM — 같은 입력 두 번 실행이 동일.
"""

from __future__ import annotations

import pytest

from app.emit import emit
from app.simulator import SimResult, simulate
from app.synth import synthesize_st
from app.transpiler import transpile_st
from app.vendors import LS_XGK
from app.wizard import build_spec
from app.xgk import XgkResult, simulate_xgk

RECIPES = [
    "motor_start_stop",
    "fwd_rev",
    "on_delay",
    "count_eject",
    "star_delta",
    "car_wash",
    "jog_run",
]

DURATION_MS = 12_000
STEP_MS = 100


def _emit_xgk(recipe: str) -> tuple[str, str]:
    """레시피 → (ST 코드, XGK 니모닉 텍스트)."""
    st = synthesize_st(build_spec(recipe))
    xgk = emit(transpile_st(st), LS_XGK)
    return st, xgk


def _input_symbols(st: str) -> list[str]:
    """ST 시뮬레이터가 인식하는 입력 심볼 목록."""
    return simulate(st, [], duration_ms=0, step_ms=STEP_MS).inputs


def _all_on_timeline(st: str) -> list[tuple[int, dict[str, bool]]]:
    return [(0, {s: True for s in _input_symbols(st)})]


def _staggered_timeline(st: str) -> list[tuple[int, dict[str, bool]]]:
    """입력을 시차로 켜고 끄는 자극(seal-in/엣지 경로를 폭넓게 친다)."""
    tl: list[tuple[int, dict[str, bool]]] = []
    for i, s in enumerate(_input_symbols(st)):
        tl.append((300 * i + 100, {s: True}))
        tl.append((300 * i + 1100, {s: False}))
    return tl


def _pulse_all_timeline(st: str) -> list[tuple[int, dict[str, bool]]]:
    """모든 입력을 주기적으로 펄스(카운터 엣지 누적용·리셋 포함).

    에미터가 이제 CTU RESET 을 ``RST C`` 별도 렁으로 내보내므로 리셋 입력도 펄스해
    충실히 비교한다(과거엔 RESET 누락으로 제외했었다).
    """
    tl: list[tuple[int, dict[str, bool]]] = []
    syms = _input_symbols(st)
    for k in range(20):
        tl.append((200 * k + 100, {s: True for s in syms}))
        tl.append((200 * k + 200, {s: False for s in syms}))
    return tl


def _run_both(
    st: str, xgk: str, tl: list[tuple[int, dict[str, bool]]]
) -> tuple[SimResult, XgkResult]:
    sres = simulate(st, tl, duration_ms=DURATION_MS, step_ms=STEP_MS)
    xres = simulate_xgk(xgk, tl, duration_ms=DURATION_MS, step_ms=STEP_MS)
    return sres, xres


def _first_divergence(
    sres: SimResult, xres: XgkResult
) -> tuple[str, int, bool, bool] | None:
    """최초 발산 (출력, 샘플, ST값, XGK값) 을 돌려준다(없으면 None)."""
    for o in sres.outputs:
        a = sres.output_trace(o)
        b = xres.output_trace(o)
        for k, (x, y) in enumerate(zip(a, b, strict=False)):
            if x != y:
                return (o, k, x, y)
    return None


# ---------------------------------------------------------------------------
# 차분 대조 — 핵심 페이로드
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("recipe", RECIPES)
@pytest.mark.parametrize(
    "make_tl",
    [_all_on_timeline, _staggered_timeline, _pulse_all_timeline],
    ids=["all_on", "staggered", "pulse_all"],
)
def test_xgk_matches_st(recipe: str, make_tl) -> None:  # type: ignore[no-untyped-def]
    """에미트된 XGK 출력 트레이스가 검증된 ST 와 샘플 단위로 일치한다."""
    st, xgk = _emit_xgk(recipe)
    tl = make_tl(st)
    sres, xres = _run_both(st, xgk, tl)

    # 출력 집합 자체가 일치해야 한다.
    assert sorted(xres.outputs) == sorted(sres.outputs), (
        f"{recipe}: 출력 심볼 불일치 ST={sres.outputs} XGK={xres.outputs}"
    )

    div = _first_divergence(sres, xres)
    assert div is None, (
        f"{recipe}: 발산 출력={div[0]} 샘플={div[1]} "  # type: ignore[index]
        f"(t={div[1] * STEP_MS}ms) ST={div[2]} XGK={div[3]}"  # type: ignore[index]
    )


# ---------------------------------------------------------------------------
# (a) NEGATIVE — 변조 검출(검사 비공허성)
# ---------------------------------------------------------------------------
def test_negative_corrupt_operand_detected() -> None:
    """LOAD 피연산자를 뒤집으면 차분이 발산을 검출한다."""
    st, xgk = _emit_xgk("motor_start_stop")
    # 'LOAD START' → 'LOAD STOP' 로 변조(논리 의미 변경).
    corrupt = xgk.replace("LOAD START", "LOAD STOP", 1)
    assert corrupt != xgk
    tl = [(0, {"START": True}), (3000, {"STOP": True})]
    sres = simulate(st, tl, duration_ms=DURATION_MS, step_ms=STEP_MS)
    xres = simulate_xgk(corrupt, tl, duration_ms=DURATION_MS, step_ms=STEP_MS)
    assert _first_divergence(sres, xres) is not None, (
        "변조된 니모닉인데도 차분이 발산을 검출하지 못함(검사 공허)."
    )


def test_negative_dropped_orb_detected() -> None:
    """ORB 한 줄을 떨어뜨리면(병렬 OR 결합 손실) 차분이 발산을 검출한다."""
    st, xgk = _emit_xgk("motor_start_stop")
    lines = xgk.splitlines()
    assert "ORB" in lines
    lines.remove("ORB")  # 첫 ORB 제거 → seal-in 브랜치 결합 깨짐
    corrupt = "\n".join(lines) + "\n"
    tl = [(0, {"START": True}), (3000, {"START": False})]
    sres = simulate(st, tl, duration_ms=DURATION_MS, step_ms=STEP_MS)
    xres = simulate_xgk(corrupt, tl, duration_ms=DURATION_MS, step_ms=STEP_MS)
    assert _first_divergence(sres, xres) is not None, (
        "ORB 누락인데도 차분이 발산을 검출하지 못함(검사 공허)."
    )


# ---------------------------------------------------------------------------
# 회귀 가드 — 차분이 잡아냈던 REAL 에미터 결함(CTU RESET 누락)이 고쳐졌다
# ---------------------------------------------------------------------------
def test_ctu_reset_emitted_as_rst_rung_and_agrees() -> None:
    """CTU RESET 이 ``RST C`` 별도 렁으로 에미트되고 ST 와 일치한다.

    과거 결함: LS_XGK 에미터가 ``C1(CU:=PART_SENSOR, RESET:=RESET_PB, PV:=10)`` 의
    RESET 을 텍스트로 내지 않아(``CTU C1 10`` 만), 실기 카운터가 리셋되지 않았다 —
    XGK↔ST 차분이 이 발산을 잡아냈다. 이제 transpiler 가 ``LOAD RESET_PB / RST C1``
    렁을 내고 인터프리터가 RST→카운터 리셋을 처리하므로, PART_SENSOR/RESET_PB 가
    동시에 펄스돼도 XGK 와 ST 가 샘플 단위로 일치한다(리셋 우선 → 누적 안 됨).
    """
    st, xgk = _emit_xgk("count_eject")
    assert "RST C1" in xgk, "리셋 렁(RST C1)이 텍스트로 존재해야 한다"
    tl: list[tuple[int, dict[str, bool]]] = []
    for k in range(20):
        tl.append((200 * k + 100, {"PART_SENSOR": True, "RESET_PB": True}))
        tl.append((200 * k + 200, {"PART_SENSOR": False, "RESET_PB": False}))
    sres = simulate(st, tl, duration_ms=DURATION_MS, step_ms=STEP_MS)
    xres = simulate_xgk(xgk, tl, duration_ms=DURATION_MS, step_ms=STEP_MS)
    assert xres.output_trace("EJECT") == sres.output_trace("EJECT")
    assert _first_divergence(sres, xres) is None  # 이제 발산 없음
    assert True not in xres.output_trace("EJECT")  # 동시 리셋 → 누적 못 함


# ---------------------------------------------------------------------------
# (b) TIMING — 타이머/카운터 발화 샘플 패리티
# ---------------------------------------------------------------------------
def test_timing_on_delay_fires_same_sample() -> None:
    """on_delay TON 이 ST·XGK 에서 같은 샘플에 발화한다(5000ms = 샘플 50)."""
    st, xgk = _emit_xgk("on_delay")
    tl = [(0, {"START": True})]
    sres, xres = _run_both(st, xgk, tl)
    s_trace = sres.output_trace("OUTPUT")
    x_trace = xres.output_trace("OUTPUT")
    assert s_trace == x_trace
    assert True in s_trace, "ST 에서 타이머가 발화하지 않음"
    assert s_trace.index(True) == x_trace.index(True)
    assert s_trace.index(True) == 5000 // STEP_MS  # 정확히 프리셋 경계


def test_timing_star_delta_transition_parity() -> None:
    """star_delta 타이머가 STAR→DELTA 전이를 두 엔진에서 같은 샘플에 일으킨다."""
    st, xgk = _emit_xgk("star_delta")
    tl = [(0, {"START_PB": True}), (100, {"START_PB": False})]
    sres, xres = _run_both(st, xgk, tl)
    for o in sres.outputs:
        assert sres.output_trace(o) == xres.output_trace(o), f"{o} 트레이스 불일치"
    delta = sres.output_trace("DELTA_CON")
    assert True in delta, "DELTA_CON 이 켜지지 않음(타이머 전이 없음)"


# ---------------------------------------------------------------------------
# (c) DETERMINISM — 두 번 실행 동일
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("recipe", RECIPES)
def test_determinism_two_runs_identical(recipe: str) -> None:
    """같은 입력으로 두 번 돌리면 XGK 트레이스가 비트 동일하다."""
    st, xgk = _emit_xgk(recipe)
    tl = _staggered_timeline(st)
    r1 = simulate_xgk(xgk, tl, duration_ms=DURATION_MS, step_ms=STEP_MS)
    r2 = simulate_xgk(xgk, tl, duration_ms=DURATION_MS, step_ms=STEP_MS)
    assert r1.outputs == r2.outputs
    for o in r1.outputs:
        assert r1.output_trace(o) == r2.output_trace(o)


def test_program_parse_reuses_devices() -> None:
    """파서가 타이머/카운터/코일을 올바르게 식별한다(스모크)."""
    from app.xgk import XgkProgram

    _, xgk = _emit_xgk("car_wash")
    prog = XgkProgram(xgk)
    assert sorted(o.operand for o in prog.fb_outputs()) == ["T0", "T1", "T2"]
    assert prog.coil_operands() == ["SOAP", "RINSE", "DRY"]
