"""독립 백엔드 교차 실행 동치 — '자가채점' 약점 타파(교차검증).

같은 컴파일 산출물(한국어 지시 -> 검증된 ST)을 *서로 다른 독립 실행기*에 동일
입력 타임라인으로 돌려 출력 트레이스가 일치함을 단정한다:

  (1) 파이썬 스캔 시뮬레이터   app.simulator.simulate          — 기준
  (2) XGK IL 인터프리터        app.xgk.simulate_xgk            — 에미트된 LS_XGK 니모닉
  (3) OpenPLC 트윈(시뮬백)     app.twin.openplc_adapter        — IEC 런타임 차분 머신

단일 시뮬레이터의 자기검증을 넘어, 두(가능하면 세) 독립 백엔드가 *같은 트레이스*를
낸다는 사실로 신뢰도를 끌어올린다. 코퍼스 규율: 불리언 지시만(아날로그 비교기 제외 —
백엔드별 수치 지원 차이 회피). scripts.cross_backend_bench 의 헬퍼/코퍼스를 그대로
import 해 재사용한다(중복 로직 금지).

비공허성(NEGATIVE): 니모닉 한 줄을 변조하면 교차 동치가 발산을 *검출*함을 단정해,
검사가 공허(언제나 통과)하지 않음을 보인다.
"""

from __future__ import annotations

import pytest

from app.simulator import simulate
from app.xgk import simulate_xgk
from scripts.cross_backend_bench import (
    DURATION_MS,
    STEP_MS,
    CaseResult,
    _build,
    _input_symbols,
    run_bench,
    run_case,
    staggered_timeline,
)

# 대표 컴파일 프로그램(불리언). 각 카테고리를 최소 1건씩 덮는다.
REPRESENTATIVE = {
    "motor_start_stop": "시작 버튼을 누르면 모터가 돌고 정지 버튼을 누르면 멈춘다",
    "sensor_self_hold": "센서가 감지되면 컨베이어를 돌리고 정지하면 멈춘다",
    "interlock": (
        "게이트 A와 게이트 B는 동시에 열 수 없다. "
        "시작하면 게이트 A를 연다. 누르면 게이트 B를 연다."
    ),
    "sequencer": "시작하면 모터를 돌리고 2초 후 펌프를 돌리고 다음 밸브를 연다",
}


# ---------------------------------------------------------------------------
# 핵심: 대표 프로그램의 PySim <-> XGK 트레이스 동치(샘플 단위)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(REPRESENTATIVE))
def test_representative_sim_matches_xgk(name: str) -> None:
    """대표 컴파일 프로그램에서 파이썬 시뮬 ↔ XGK 인터프리터 트레이스가 일치한다."""
    text = REPRESENTATIVE[name]
    st, xgk = _build(text)
    inputs = _input_symbols(st)
    tl = staggered_timeline(inputs)

    sres = simulate(st, tl, duration_ms=DURATION_MS, step_ms=STEP_MS)
    xres = simulate_xgk(xgk, tl, duration_ms=DURATION_MS, step_ms=STEP_MS)

    # 출력 집합이 같고(에미터가 출력을 빠뜨리지 않음), 트레이스가 비트 동일해야 한다.
    assert sres.outputs, f"{name}: 구동 출력이 없다(컴파일 실패 의심)"
    assert sorted(sres.outputs) == sorted(xres.outputs), (
        f"{name}: 출력 심볼 불일치 ST={sres.outputs} XGK={xres.outputs}"
    )
    for o in sres.outputs:
        assert sres.output_trace(o) == xres.output_trace(o), (
            f"{name}: 출력 '{o}' 트레이스가 PySim 과 XGK 에서 갈라짐"
        )


# ---------------------------------------------------------------------------
# 비공허성(NEGATIVE) — 변조하면 교차 동치가 발산을 검출
# ---------------------------------------------------------------------------
def test_cross_check_is_not_vacuous() -> None:
    """LOAD 피연산자를 뒤집으면(논리 변경) PySim ↔ XGK 가 발산을 검출한다.

    교차 동치가 '언제나 통과'하는 공허한 검사가 아님을 보증한다.
    """
    st, xgk = _build(REPRESENTATIVE["motor_start_stop"])
    assert "LOAD START" in xgk, "전제: 모터 기동 렁이 'LOAD START' 를 포함"
    corrupt = xgk.replace("LOAD START", "LOAD STOP", 1)
    assert corrupt != xgk

    tl = [(0, {"START": True}), (3000, {"STOP": True})]
    sres = simulate(st, tl, duration_ms=DURATION_MS, step_ms=STEP_MS)
    xres = simulate_xgk(corrupt, tl, duration_ms=DURATION_MS, step_ms=STEP_MS)

    diverged = any(
        sres.output_trace(o) != xres.output_trace(o) for o in sres.outputs
    )
    assert diverged, "변조된 니모닉인데도 교차 동치가 발산을 못 잡음(검사 공허)"


# ---------------------------------------------------------------------------
# 결정론 — 같은 케이스 두 번 실행이 동일
# ---------------------------------------------------------------------------
def test_run_case_is_deterministic() -> None:
    """run_case 를 두 번 돌리면 동일한 동치 결과(발산 없음)를 낸다."""
    r1 = run_case(REPRESENTATIVE["sequencer"])
    r2 = run_case(REPRESENTATIVE["sequencer"])
    assert r1.compiled and r2.compiled
    assert r1.outputs == r2.outputs
    assert r1.divergences == r2.divergences
    assert r1.agrees("sim_vs_xgk") and r1.agrees("sim_vs_openplc")


# ---------------------------------------------------------------------------
# 전 코퍼스 교차 동치 — 두(세) 백엔드 일치율
# ---------------------------------------------------------------------------
def test_full_corpus_cross_equivalence() -> None:
    """벤치 코퍼스(불리언 15~25건) 전체에서 컴파일 케이스가 모든 쌍에서 일치한다.

    PySim ↔ XGK(독립 IL 인터프리터)와 PySim ↔ OpenPLC(트윈 IEC 런타임)를 모두
    확인한다 — 두 독립 백엔드 교차검증으로 자가채점을 넘어선다.
    """
    summary = run_bench()
    compiled: list[CaseResult] = summary.compiled
    # 코퍼스가 실질적이어야 한다(최소 15건 컴파일).
    assert len(compiled) >= 15, f"컴파일 케이스가 너무 적다: {len(compiled)}"

    for pair in ("sim_vs_xgk", "sim_vs_openplc"):
        agree, total = summary.pair_agree_rate(pair)
        bad = [
            (c.text, c.divergences[pair]) for c in compiled if not c.agrees(pair)
        ]
        assert agree == total, (
            f"[{pair}] 일치 {agree}/{total} — 발산: {bad}"
        )


def test_corpus_excludes_analog_comparators() -> None:
    """코퍼스 규율: 어떤 케이스도 아날로그 비교기(REAL 비교)를 만들지 않는다.

    백엔드별 수치 지원 차이를 회피해 불리언 동치만 비교하기 위함이다. 비교기가
    섞이면 ST 에 'SIG op NUM' 비교 원자가 생기므로, 입력이 전부 BOOL 인지로 검사한다.
    """
    from scripts.cross_backend_bench import CORPUS

    for text in CORPUS:
        result = run_case(text)
        if not result.compiled:
            continue
        st, _ = _build(text)
        # 비교 원자가 있으면 simulate 가 signals(아날로그 신호)를 노출한다.
        sres = simulate(st, [], duration_ms=0, step_ms=STEP_MS)
        assert not sres.signals, (
            f"불리언 코퍼스에 아날로그 비교기 혼입: {text!r} signals={sres.signals}"
        )
