"""변이(mutation) 가드 테스트 — 코퍼스+기존 스위트가 놓치던 결정론/안전 회귀를 잡는다.

``scripts/targeted_mutation.py`` 로 4개 결정론 코어(synth/simulator/verifier/bootstrap)에
주입한 안전-관련 결함을 돌려본 결과, 기존 스위트(코퍼스 리플레이 포함)가 **죽이지 못한**
생존 변이 4종을 확인했다. 이 파일의 각 테스트는 그 결함이 주입되면 RED 가 되도록
판별(discriminating) 단언을 둔다 — 즉 회귀를 잡는 그물을 보강한다.

원칙(과제 제약 준수):
  * 공개 API(synthesize_st / simulate / verify / check_interlocks_* / generate)만 사용.
  * 결정론·키 불필요·빠름. 현재(정상) 소스에서 전부 GREEN.

생존 변이 → 가드 매핑:
  counter_edge_to_level      → test_counter_counts_on_edge_not_level
  kind_step_assume_negate    → test_kinduction_step_hypothesis_is_assumed_true
  interlock_st_drop_guard    → test_interlock_st_uses_mutual_exclusion_assumption
  bootstrap_verify_gate_vacuous → test_every_corpus_sample_independently_passes_verify
추가로, 죽었지만 안전상 핵심인 결함(seal-in AND↔OR, interlock NOT 누락,
타이머 off-by-one)에도 명시적 가드를 둬 영구 회귀망으로 남긴다.
"""

from __future__ import annotations

import pytest

from app.dataset.bootstrap import generate
from app.models import (
    Interlock,
    IODirection,
    IOPoint,
    SfcState,
    StateMachineSpec,
    Transition,
)
from app.simulator import simulate
from app.synth import synthesize_st
from app.verifier import (
    _HAS_Z3,
    check_interlocks_kinduction,
    check_interlocks_st,
    verify,
)
from app.wizard import build_spec

z3_only = pytest.mark.skipif(not _HAS_Z3, reason="z3 미설치")


def _ab_interlock_spec(*inputs: str) -> StateMachineSpec:
    """출력 A/B 가 인터락된 최소 명세(직접 ST 를 먹이는 검증 테스트용)."""
    io: list[IOPoint] = [IOPoint(symbol=s, direction=IODirection.INPUT) for s in inputs]
    io += [
        IOPoint(symbol="A", direction=IODirection.OUTPUT),
        IOPoint(symbol="B", direction=IODirection.OUTPUT),
    ]
    return StateMachineSpec(
        title="ab",
        io_points=io,
        interlocks=[Interlock(output_a="A", output_b="B", reason="A/B 동시 ON 금지")],
    )


# ── 생존 변이 #1: counter_edge_to_level (app/simulator.py) ──────────────────
def test_counter_counts_on_edge_not_level() -> None:
    """카운터는 *상승 엣지* 마다 1 만 센다 — 레벨(매 스캔)로 세면 안 된다.

    PART_SENSOR 를 길게 ON 으로 유지하면 상승 엣지는 **단 1회** 뿐이므로
    PV=3 카운터는 절대 발화하지 못한다(EJECT 는 끝까지 False). 레벨 카운팅
    변이(``if cu:`` 로 바뀜)는 매 스캔 +1 해 3을 넘겨 EJECT 를 켜므로 RED 가 된다.
    """
    st = synthesize_st(build_spec("count_eject", {"count": "3"}))
    # RESET_PB 는 기본 False 로 두어 카운트가 리셋되지 않게 한다.
    r = simulate(st, [(0, {"PART_SENSOR": True})], duration_ms=1000, step_ms=100)
    trace = r.output_trace("EJECT")
    assert not any(trace), (
        "지속 ON(엣지 1회)만으로 EJECT 가 켜졌다 — 카운터가 엣지가 아닌 레벨로 세고 있다."
    )


# ── 생존 변이 #2: kind_step_assume_negate (app/verifier.py) ─────────────────
@z3_only
def test_kinduction_step_hypothesis_is_assumed_true() -> None:
    """k-귀납 STEP 의 귀납가설(P 가 성립)이 *참으로 가정* 되어야 한다.

    step-증명이 불가능하지만 base 는 안전한 ST 에서 정상 코어는 보수적
    ``INTERLOCK_KIND`` 경고를 남긴다. 가설을 부정(``Not(prop_ok)``)하는 변이는
    step 솔버를 공허하게 unsat 으로 만들어 '증명됨'(None)으로 오판 → 경고가 사라진다.
    k=1 에서 정상 코어가 경고를 내는 ST 로 그 사라짐을 잡는다.
    """
    spec = _ab_interlock_spec()
    # A 는 자기참조 자체-홀드(파트너 가드 없음), B 는 NOT B 만. base 는 안전하나
    # 1-귀납으로는 증명되지 않아 정상 코어가 INTERLOCK_KIND 경고를 남긴다.
    st = "A := (A OR A) AND A;\nB := (A OR A) AND NOT B;"
    issues = check_interlocks_kinduction(spec, st, k=1)
    codes = {i.code for i in issues}
    # 정상: base 안전(INTERLOCK error 없음) + step 미증명(INTERLOCK_KIND 경고 존재).
    assert "INTERLOCK" not in codes, "base 가 안전해야 한다(이 ST 는 도달가능 위반 없음)."
    assert "INTERLOCK_KIND" in codes, (
        "step 미증명 경고가 사라졌다 — 귀납가설이 참으로 가정되지 않는다(부정 변이)."
    )


# ── 생존 변이 #3: interlock_st_drop_guard (app/verifier.py) ─────────────────
@z3_only
def test_interlock_st_uses_mutual_exclusion_assumption() -> None:
    """1-스텝 ST 인터락 검사는 '현재 ¬(A∧B)' 라는 귀납가정을 써야 한다.

    순수 자체-홀드 ``A:=A; B:=B`` 는 현재 상호배타면 다음에도 그대로라 안전하다.
    정상 코어는 가정 ``¬(A∧B)`` 하에 ``A'∧B'`` 가 unsat → 위반 없음.
    가정을 ``A∨B`` 로 뒤집는 변이는 A=B=True 를 허용해 거짓 INTERLOCK 을 보고 → RED.
    """
    spec = _ab_interlock_spec()
    st = "A := A;\nB := B;"
    issues = check_interlocks_st(spec, st)
    assert [i.code for i in issues] == [], (
        "자체-홀드 ST 에서 거짓 인터락 위반이 보고됐다 — "
        "1-스텝 검사의 귀납가정(현재 동시 ON 아님)이 잘못됐다."
    )


# ── 생존 변이 #4: bootstrap_verify_gate_vacuous (app/dataset/bootstrap.py) ──
def test_every_corpus_sample_independently_passes_verify() -> None:
    """누적 코퍼스의 *모든* 샘플은 정형검증을 error 0 으로 독립 통과해야 한다.

    bootstrap 의 'verified' 게이트가 무력화(공허화)되면 검증 실패 명세가 코퍼스에
    새어든다. 각 샘플을 재합성해 ``verify`` 로 다시 검사함으로써 그 누수를 잡는다.
    """
    rep = generate()
    assert rep.samples, "코퍼스가 비어있다(부트스트랩이 아무 샘플도 만들지 못함)."
    offenders: list[str] = []
    for s in rep.samples:
        spec = build_spec(s.recipe_id, s.answers)
        report = verify(spec, s.st)
        if report.has_errors:
            errs = sorted({i.code for i in report.issues if i.severity == "error"})
            offenders.append(f"{s.sample_id}:{errs}")
    assert not offenders, f"검증 실패 샘플이 코퍼스에 존재한다(게이트 누수): {offenders}"


# ── 추가 가드: 죽었지만 안전상 핵심인 결함의 영구 회귀망 ─────────────────────
def test_seal_in_releases_on_turn_off() -> None:
    """seal-in 자기유지는 turn-off 조건에서 *반드시 해제* 된다(AND NOT, OR 아님).

    합성식 ``(on OR OUT) AND NOT (off)`` 의 AND 를 OR 로 바꾸면 STOP 후에도
    출력이 영원히 ON 으로 고착된다. STOP 후 트레이스가 OFF 임을 단언해 잡는다.
    """
    st = synthesize_st(build_spec("motor_start_stop"))
    r = simulate(
        st,
        [(0, {"START": True}), (100, {"START": False}), (300, {"STOP": True})],
        duration_ms=600,
        step_ms=100,
    )
    trace = r.output_trace("MOTOR")
    assert trace[0] is True, "시동 직후 MOTOR 가 켜져야 한다."
    assert trace[-1] is False, (
        "STOP 후에도 MOTOR 가 꺼지지 않는다 — seal-in turn-off 가 OR 로 누설."
    )


def test_interlock_partner_term_is_sole_protection() -> None:
    """합성 ``AND NOT <partner>`` 항이 *유일한* 상호배제 보호인 명세로 그 누락을 잡는다.

    두 출력 LA/LB 의 *진입 조건이 동일*(둘 다 ``GO`` 로 켜짐)하므로, 진입 조건만으로는
    상호배제가 보장되지 않는다. 오직 합성기가 덧붙이는 ``AND NOT partner`` 항만이
    동시 ON 을 막는다. 그 항을 빼는 변이는 시뮬레이션에서 LA·LB 동시 ON 으로 드러난다.
    (실제 레시피들은 진입조건이 이미 상호배타라 이 결함을 가리므로 전용 명세가 필요하다.)
    """
    spec = StateMachineSpec(
        title="overlap-entry",
        io_points=[
            IOPoint(symbol="GO", direction=IODirection.INPUT),
            IOPoint(symbol="LA", direction=IODirection.OUTPUT),
            IOPoint(symbol="LB", direction=IODirection.OUTPUT),
        ],
        states=[
            SfcState(name="IDLE", is_initial=True),
            SfcState(name="SA", on_entry=["LA := TRUE;"]),
            SfcState(name="SB", on_entry=["LB := TRUE;"]),
        ],
        transitions=[
            Transition(from_state="IDLE", to_state="SA", condition="GO"),
            Transition(from_state="IDLE", to_state="SB", condition="GO"),
        ],
        interlocks=[Interlock(output_a="LA", output_b="LB", reason="LA/LB 동시 금지")],
    )
    st = synthesize_st(spec)
    r = simulate(st, [(0, {"GO": True})], duration_ms=300, step_ms=50)
    for s in r.samples:
        assert not (s.outputs.get("LA") and s.outputs.get("LB")), (
            f"@ {s.t_ms}ms LA·LB 동시 ON — 인터락 'AND NOT partner' 항이 누락됐다."
        )


def test_on_delay_timer_not_off_by_one() -> None:
    """TON 은 acc >= preset 에서 발화한다(> 로 바뀌면 1스캔 늦거나 미발화).

    프리셋과 스텝을 맞물려, preset 시점 정확히 도달하는 스캔에서 출력이 ON 임을 단언.
    ``>`` 로 바뀐 off-by-one 변이는 그 스캔에 아직 OFF 라 RED 가 된다.
    """
    st = synthesize_st(build_spec("on_delay", {"delay_sec": "1"}))
    # step 이 preset(1000ms)을 정확히 나누도록 250ms → t=1000ms 샘플에서 acc==preset.
    r = simulate(st, [(0, {"START": True})], duration_ms=1200, step_ms=250)
    trace = r.output_trace("OUTPUT")
    assert trace[0] is False, "즉시 발화하면 안 된다."
    # t=1000ms (index 4) 에서 acc==preset → ON 이어야 한다.
    assert trace[4] is True, "preset 도달 스캔에 출력이 OFF — 타이머 비교가 off-by-one(>= 대신 >)."


def test_ctu_fires_exactly_at_preset() -> None:
    """CTU 는 정확히 PV 번째 엣지에서 발화한다(>= preset). off-by-one 가드."""
    st = synthesize_st(build_spec("count_eject", {"count": "3"}))
    ev: list[tuple[int, dict[str, bool]]] = []
    for i in range(3):  # 정확히 3개의 상승 엣지
        t = i * 200
        ev += [(t, {"PART_SENSOR": True}), (t + 100, {"PART_SENSOR": False})]
    r = simulate(st, ev, duration_ms=800, step_ms=100)
    assert r.output_trace("EJECT")[-1] is True, (
        "정확히 PV(3) 개 엣지 후에도 EJECT 가 OFF — 카운터 비교가 off-by-one(>= 대신 >)."
    )
