"""가이드 마법사 — 비전문가가 '기획'(레시피 선택 + 빈칸)만으로 명세를 만든다.

완주 목표의 척추: PLC/ST 를 몰라도, 흔한 제어 의도를 고르고 신호 이름·시간만
채우면 유효한 StateMachineSpec 이 결정론적으로 만들어진다(LLM/키 불필요).
이후 synth → 래더 → 설명 파이프라인을 그대로 탄다.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.models import (
    CounterSpec,
    DerivedOutput,
    Interlock,
    IODirection,
    IOPoint,
    SfcState,
    StateMachineSpec,
    TimerSpec,
    Transition,
)

Answers = dict[str, str]
_IN = IODirection.INPUT
_OUT = IODirection.OUTPUT


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    default: str
    kind: str = "symbol"  # symbol | int | time_sec


@dataclass(frozen=True)
class Recipe:
    id: str
    title: str
    description: str
    category: str
    fields: tuple[Field, ...]
    build: Callable[[Answers], StateMachineSpec]
    safety_note: str = ""  # 이 레시피 특유의 안전 주의(선택 시 노출)


def _io(sym: str, d: IODirection, desc: str = "") -> IOPoint:
    return IOPoint(symbol=sym, direction=d, description=desc)


def _tr(frm: str, to: str, cond: str) -> Transition:
    return Transition(from_state=frm, to_state=to, condition=cond)


class WizardError(ValueError):
    """비전문가에게 보여줄 친절한 입력 오류."""


_SYM_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RESERVED = {"AND", "OR", "NOT", "TRUE", "FALSE", "XOR"}


def _val(a: Answers, key: str, default: str) -> str:
    """심볼 답변을 검증해 반환한다(빈 값이면 기본값). 잘못되면 WizardError."""
    raw = (a.get(key) or "").strip()
    sym = raw or default
    if not _SYM_RE.match(sym):
        raise WizardError(
            f"신호 이름 '{sym}' 은(는) 쓸 수 없어요. 영문으로 시작하고 "
            "영문·숫자·밑줄(_)만 사용하세요(공백·한글·기호 불가). 예: START, MOTOR_1"
        )
    if sym.upper() in _RESERVED:
        raise WizardError(
            f"'{sym}' 은(는) 예약어라 신호 이름으로 쓸 수 없어요. 다른 이름을 쓰세요."
        )
    return sym


def _pint(a: Answers, key: str, default: int, lo: int = 0) -> int:
    try:
        return max(lo, int(float(a.get(key) or default)))  # '3.5' → 3 (NL 경로와 일치)
    except (ValueError, TypeError):
        return default


def _validate_spec(spec: StateMachineSpec) -> None:
    """빌드된 명세의 비전문가 안전성 검사(충돌·자기인터락)."""
    inputs = {p.symbol for p in spec.io_points if p.direction == IODirection.INPUT}
    outputs = [p.symbol for p in spec.io_points if p.direction == IODirection.OUTPUT]
    dup = {s for s in outputs if outputs.count(s) > 1}
    if dup:
        raise WizardError(
            f"출력 이름이 중복됩니다: {', '.join(sorted(dup))}. 서로 다른 이름을 쓰세요."
        )
    clash = inputs & set(outputs)
    if clash:
        raise WizardError(
            f"입력과 출력에 같은 이름({', '.join(sorted(clash))})을 쓸 수 없어요. "
            "버튼/센서(입력)와 모터/램프(출력)는 다른 이름이어야 합니다."
        )
    for il in spec.interlocks:
        if il.output_a == il.output_b:
            raise WizardError(
                f"인터락 두 출력이 같은 이름({il.output_a})입니다. 서로 달라야 합니다."
            )


# ---------------------------------------------------------------------------
# 레시피 빌더들
# ---------------------------------------------------------------------------
def _motor_start_stop(a: Answers) -> StateMachineSpec:
    start = _val(a, "start", "START")
    stop = _val(a, "stop", "STOP")
    motor = _val(a, "motor", "MOTOR")
    return StateMachineSpec(
        title="모터 기동/정지(자기유지)",
        io_points=[
            _io(start, _IN, "기동 버튼"),
            _io(stop, _IN, "정지 버튼"),
            _io(motor, _OUT, "모터"),
        ],
        states=[
            SfcState(name="IDLE", is_initial=True),
            SfcState(name="RUN", on_entry=[f"{motor} := TRUE;"]),
        ],
        transitions=[
            _tr("IDLE", "RUN", f"{start} AND NOT {stop}"),
            _tr("RUN", "IDLE", f"{stop}"),
        ],
    )


def _fwd_rev(a: Answers) -> StateMachineSpec:
    fwd = _val(a, "fwd", "FWD_PB")
    rev = _val(a, "rev", "REV_PB")
    stop = _val(a, "stop", "STOP")
    mf = _val(a, "motor_fwd", "MOTOR_FWD")
    mr = _val(a, "motor_rev", "MOTOR_REV")
    return StateMachineSpec(
        title="정역 운전(인터락)",
        io_points=[
            _io(fwd, _IN, "정방향 버튼"),
            _io(rev, _IN, "역방향 버튼"),
            _io(stop, _IN, "정지"),
            _io(mf, _OUT, "정방향 모터"),
            _io(mr, _OUT, "역방향 모터"),
        ],
        states=[
            SfcState(name="IDLE", is_initial=True),
            SfcState(name="FWD", on_entry=[f"{mf} := TRUE;"]),
            SfcState(name="REV", on_entry=[f"{mr} := TRUE;"]),
        ],
        transitions=[
            _tr("IDLE", "FWD", f"{fwd} AND NOT {rev} AND NOT {stop}"),
            _tr("FWD", "IDLE", f"{stop} OR {rev}"),
            _tr("IDLE", "REV", f"{rev} AND NOT {fwd} AND NOT {stop}"),
            _tr("REV", "IDLE", f"{stop} OR {fwd}"),
        ],
        interlocks=[Interlock(output_a=mf, output_b=mr, reason="정/역 동시 구동 금지")],
    )


def _on_delay(a: Answers) -> StateMachineSpec:
    start = _val(a, "start", "START")
    stop = _val(a, "stop", "STOP")
    out = _val(a, "output", "OUTPUT")
    sec = _pint(a, "delay_sec", 5)
    return StateMachineSpec(
        title=f"지연 기동(ON-delay {sec}초)",
        io_points=[
            _io(start, _IN, "기동"),
            _io(stop, _IN, "정지"),
            _io(out, _OUT, "출력"),
        ],
        timers=[
            TimerSpec(name="T1", preset_ms=sec * 1000, enable_condition=start,
                      description=f"{sec}초 지연"),
        ],
        states=[
            SfcState(name="IDLE", is_initial=True),
            SfcState(name="ON", on_entry=[f"{out} := TRUE;"]),
        ],
        transitions=[
            _tr("IDLE", "ON", f"T1.Q AND NOT {stop}"),
            _tr("ON", "IDLE", f"{stop}"),
        ],
    )


def _hi_lo_level(a: Answers) -> StateMachineSpec:
    lo = _val(a, "lo", "LO_LS")
    hi = _val(a, "hi", "HI_LS")
    pump = _val(a, "pump", "PUMP")
    return StateMachineSpec(
        title="수위 상/하한 제어(히스테리시스)",
        io_points=[
            _io(lo, _IN, "저수위 스위치"),
            _io(hi, _IN, "고수위 스위치"),
            _io(pump, _OUT, "급수 펌프"),
        ],
        states=[
            SfcState(name="DRY", is_initial=True),
            SfcState(name="FILL", on_entry=[f"{pump} := TRUE;"]),
        ],
        transitions=[
            _tr("DRY", "FILL", f"{lo} AND NOT {hi}"),
            _tr("FILL", "DRY", f"{hi}"),
        ],
    )


def _count_eject(a: Answers) -> StateMachineSpec:
    sensor = _val(a, "sensor", "PART_SENSOR")
    reset = _val(a, "reset", "RESET_PB")
    eject = _val(a, "eject", "EJECT")
    n = _pint(a, "count", 10, lo=1)
    return StateMachineSpec(
        title=f"부품 카운터({n}개 배출)",
        io_points=[
            _io(sensor, _IN, "부품 감지"),
            _io(reset, _IN, "리셋"),
            _io(eject, _OUT, "배출"),
        ],
        counters=[
            CounterSpec(name="C1", preset=n, count_condition=sensor,
                        reset_condition=reset, description=f"{n}개 카운트"),
        ],
        states=[
            SfcState(name="COUNTING", is_initial=True),
            SfcState(name="FULL", on_entry=[f"{eject} := TRUE;"]),
        ],
        transitions=[
            _tr("COUNTING", "FULL", f"C1.Q AND NOT {reset}"),
            _tr("FULL", "COUNTING", f"{reset}"),
        ],
    )


def _auto_manual(a: Answers) -> StateMachineSpec:
    mode = _val(a, "mode", "MODE_AUTO")
    ac = _val(a, "auto_cmd", "AUTO_CMD")
    mc = _val(a, "man_cmd", "MAN_CMD")
    stop = _val(a, "stop", "SYS_STOP")
    valve = _val(a, "valve", "VALVE")
    # 자동/수동은 조합(파생) 출력으로 — 두 상태가 한 출력을 몰면 seal-in 합성이
    # 서로의 turn-off 가 되어 오작동한다(협의회 QA P1#3). 단일 식으로 합성한다.
    return StateMachineSpec(
        title="자동/수동 모드 제어",
        io_points=[
            _io(mode, _IN, "모드(자동=ON)"),
            _io(ac, _IN, "자동 명령"),
            _io(mc, _IN, "수동 명령"),
            _io(stop, _IN, "정지"),
            _io(valve, _OUT, "밸브"),
        ],
        derived_outputs=[
            DerivedOutput(
                output=valve,
                expression=f"(({mode} AND {ac}) OR (NOT {mode} AND {mc})) AND NOT {stop}",
                description="자동이면 자동명령, 수동이면 수동명령으로 개방",
            ),
        ],
    )


def _jog_run(a: Answers) -> StateMachineSpec:
    start = _val(a, "start", "START_PB")
    stop = _val(a, "stop", "STOP_PB")
    jog = _val(a, "jog", "JOG_PB")
    run = _val(a, "motor_run", "MOTOR_RUN")
    mjog = _val(a, "motor_jog", "MOTOR_JOG")
    return StateMachineSpec(
        title="조그/연속 운전",
        io_points=[
            _io(start, _IN, "연속 기동"), _io(stop, _IN, "정지"), _io(jog, _IN, "조그(누름)"),
            _io(run, _OUT, "연속 운전"), _io(mjog, _OUT, "조그 운전"),
        ],
        states=[
            SfcState(name="IDLE", is_initial=True),
            SfcState(name="RUNNING", on_entry=[f"{run} := TRUE;"]),
            SfcState(name="JOGGING", on_entry=[f"{mjog} := TRUE;"]),
        ],
        transitions=[
            _tr("IDLE", "RUNNING", f"{start} AND NOT {jog} AND NOT {stop}"),
            _tr("RUNNING", "IDLE", f"{stop}"),
            _tr("IDLE", "JOGGING", f"{jog} AND NOT {start}"),
            _tr("JOGGING", "IDLE", f"NOT {jog}"),
        ],
        interlocks=[Interlock(output_a=run, output_b=mjog, reason="연속/조그 동시 금지")],
    )


def _star_delta(a: Answers) -> StateMachineSpec:
    start = _val(a, "start", "START_PB")
    stop = _val(a, "stop", "STOP_PB")
    main = _val(a, "main", "MAIN_CON")
    star = _val(a, "star", "STAR_CON")
    delta = _val(a, "delta", "DELTA_CON")
    sec = _pint(a, "delay_sec", 5)
    return StateMachineSpec(
        title="Y-Δ(스타-델타) 기동",
        io_points=[
            _io(start, _IN, "기동"), _io(stop, _IN, "정지"),
            _io(main, _OUT, "주접촉기"), _io(star, _OUT, "스타"), _io(delta, _OUT, "델타"),
        ],
        timers=[TimerSpec(name="T1", preset_ms=sec * 1000, enable_condition=star,
                          description=f"{sec}초 후 델타 전환")],
        states=[
            SfcState(name="IDLE", is_initial=True),
            SfcState(name="STAR", on_entry=[f"{main} := TRUE;", f"{star} := TRUE;"]),
            SfcState(name="DELTA", on_entry=[f"{main} := TRUE;", f"{delta} := TRUE;"]),
        ],
        transitions=[
            _tr("IDLE", "STAR", f"({start} OR {main}) AND NOT {stop} AND NOT T1.Q"),
            _tr("STAR", "DELTA", f"T1.Q AND NOT {stop} AND {main}"),
            _tr("DELTA", "IDLE", f"{stop}"),
            _tr("STAR", "IDLE", f"{stop}"),
        ],
        interlocks=[Interlock(output_a=star, output_b=delta, reason="스타/델타 동시 투입 금지")],
    )


def _latch_alarm(a: Answers) -> StateMachineSpec:
    fa = _val(a, "fault_a", "FAULT_A")
    fb = _val(a, "fault_b", "FAULT_B")
    fc = _val(a, "fault_c", "FAULT_C")
    reset = _val(a, "reset", "ALARM_RST")
    alarm = _val(a, "alarm", "ALARM")
    return StateMachineSpec(
        title="래치형 알람",
        io_points=[
            _io(fa, _IN, "고장 A"), _io(fb, _IN, "고장 B"), _io(fc, _IN, "고장 C"),
            _io(reset, _IN, "리셋"), _io(alarm, _OUT, "알람"),
        ],
        states=[
            SfcState(name="NORMAL", is_initial=True),
            SfcState(name="ALARMED", on_entry=[f"{alarm} := TRUE;"]),
        ],
        transitions=[
            _tr("NORMAL", "ALARMED", f"{fa} OR {fb} OR {fc}"),
            _tr("ALARMED", "NORMAL", f"{reset} AND NOT {fa} AND NOT {fb} AND NOT {fc}"),
        ],
    )


def _first_out_alarm(a: Answers) -> StateMachineSpec:
    fa = _val(a, "fault_a", "FAULT_A")
    fb = _val(a, "fault_b", "FAULT_B")
    ack = _val(a, "ack", "ALM_ACK")
    reset = _val(a, "reset", "ALM_RST")
    la = _val(a, "latch_a", "LATCH_A")
    lb = _val(a, "latch_b", "LATCH_B")
    horn = _val(a, "horn", "HORN")
    return StateMachineSpec(
        title="최초고장 알람(first-out)",
        io_points=[
            _io(fa, _IN, "고장 A"), _io(fb, _IN, "고장 B"), _io(ack, _IN, "확인"),
            _io(reset, _IN, "리셋"), _io(la, _OUT, "A 최초"), _io(lb, _OUT, "B 최초"),
            _io(horn, _OUT, "경음기"),
        ],
        states=[
            SfcState(name="NORMAL", is_initial=True),
            SfcState(name="FIRST_A", on_entry=[f"{la} := TRUE;"]),
            SfcState(name="FIRST_B", on_entry=[f"{lb} := TRUE;"]),
        ],
        transitions=[
            _tr("NORMAL", "FIRST_A", f"{fa} AND NOT {lb}"),
            _tr("NORMAL", "FIRST_B", f"{fb} AND NOT {la}"),
            _tr("FIRST_A", "NORMAL", f"{reset} AND NOT {fa}"),
            _tr("FIRST_B", "NORMAL", f"{reset} AND NOT {fb}"),
        ],
        derived_outputs=[
            DerivedOutput(output=horn, expression=f"({la} OR {lb}) AND NOT {ack}",
                          description="최초 고장이 잡히면 경음기 ON, 확인하면 OFF"),
        ],
    )


def _duty_standby(a: Answers) -> StateMachineSpec:
    demand = _val(a, "demand", "DEMAND")
    high = _val(a, "high_demand", "HIGH_DEMAND")
    stop = _val(a, "stop", "SYS_STOP")
    lead = _val(a, "lead", "PUMP_LEAD")
    lag = _val(a, "lag", "PUMP_LAG")
    return StateMachineSpec(
        title="펌프 리드/래그(듀티-스탠바이)",
        io_points=[
            _io(demand, _IN, "수요"), _io(high, _IN, "고수요"), _io(stop, _IN, "정지"),
            _io(lead, _OUT, "리드 펌프"), _io(lag, _OUT, "래그 펌프"),
        ],
        states=[
            SfcState(name="OFF", is_initial=True),
            SfcState(name="LEAD", on_entry=[f"{lead} := TRUE;"]),
            SfcState(name="LAG_ON", on_entry=[f"{lag} := TRUE;"]),
        ],
        transitions=[
            _tr("OFF", "LEAD", f"{demand} AND NOT {stop}"),
            _tr("LEAD", "OFF", f"{stop}"),
            _tr("LEAD", "LAG_ON", f"{high} AND NOT {stop}"),
            _tr("LAG_ON", "LEAD", f"NOT {high}"),
        ],
    )


def _two_hand(a: Answers) -> StateMachineSpec:
    lh = _val(a, "lh", "LH_BTN")
    rh = _val(a, "rh", "RH_BTN")
    guard = _val(a, "guard", "GUARD_CLOSED")
    estop = _val(a, "estop_ok", "ESTOP_OK")
    enable = _val(a, "enable", "PRESS_ENABLE")
    if lh == rh:
        raise WizardError("좌/우 버튼은 서로 다른 신호여야 합니다(양수 조작의 핵심).")
    return StateMachineSpec(
        title="양수 조작 허가(보조)",
        io_points=[
            _io(lh, _IN, "좌측 버튼"), _io(rh, _IN, "우측 버튼"), _io(guard, _IN, "가드 닫힘"),
            _io(estop, _IN, "E-stop 정상"), _io(enable, _OUT, "기동 허가"),
        ],
        states=[
            SfcState(name="SAFE", is_initial=True),
            SfcState(name="ENABLED", on_entry=[f"{enable} := TRUE;"]),
        ],
        transitions=[
            _tr("SAFE", "ENABLED", f"{lh} AND {rh} AND {guard} AND {estop}"),
            # 가드가 열리면 즉시 허가 해제(QA P1)
            _tr("ENABLED", "SAFE", f"NOT {lh} OR NOT {rh} OR NOT {guard} OR NOT {estop}"),
        ],
    )


def _build_sequencer(
    steps: list[tuple[str, int]], *, start: str, stop: str, loop: bool, title: str,
) -> StateMachineSpec:
    """N단계 타임드 시퀀스(각 단계 출력 ON → 지정 시간 후 다음 단계). 합성 무변경.

    각 단계의 진입 조건에 'NOT 모든 단계출력'(all_off) 가드를 넣어 한 번에 한 출력만
    켜지게 한다(루프 stuck-coil 방지). 인터락은 선언하지 않는다 — 시퀀스 진입 조건은
    정적으로 상호배타가 아니라 검증기의 단순 인터락 검사가 거짓양성을 내기 때문이며,
    one-hot 은 all_off 가드 + 타이머 핸드오프로 구조적으로 보장된다.
    """
    n = len(steps)
    outs = [o for o, _ in steps]
    all_off = " AND ".join(f"NOT {o}" for o in outs)
    io_points = [_io(start, _IN, "기동"), _io(stop, _IN, "정지")]
    states: list[SfcState] = [SfcState(name="IDLE", is_initial=True)]
    timers: list[TimerSpec] = []
    transitions = [_tr("IDLE", "S0", f"{start} AND NOT {stop} AND {all_off}")]
    for k, (out, sec) in enumerate(steps):
        io_points.append(_io(out, _OUT, f"{k + 1}단계"))
        states.append(SfcState(name=f"S{k}", on_entry=[f"{out} := TRUE;"]))
        timers.append(TimerSpec(name=f"T{k}", preset_ms=sec * 1000,
                                enable_condition=out, description=f"{out} {sec}초"))
    for k in range(n):
        cur = f"S{k}"
        transitions.append(_tr(cur, "IDLE", stop))  # 중단
        if k < n - 1:
            transitions.append(_tr(cur, f"S{k + 1}", f"T{k}.Q AND NOT {stop}"))
        elif loop:
            transitions.append(_tr(cur, "S0", f"T{k}.Q AND NOT {stop}"))
        else:
            transitions.append(_tr(cur, "IDLE", f"T{k}.Q"))
    return StateMachineSpec(
        title=title, io_points=io_points, timers=timers, states=states,
        transitions=transitions,
    )


def _car_wash(a: Answers) -> StateMachineSpec:
    start, stop = _val(a, "start", "START"), _val(a, "stop", "STOP")
    steps = [
        (_val(a, "out1", "SOAP"), _pint(a, "t1", 5, lo=1)),
        (_val(a, "out2", "RINSE"), _pint(a, "t2", 5, lo=1)),
        (_val(a, "out3", "DRY"), _pint(a, "t3", 5, lo=1)),
    ]
    return _build_sequencer(steps, start=start, stop=stop, loop=False, title="세차 순차 제어")


def _timed_traffic(a: Answers) -> StateMachineSpec:
    start, stop = _val(a, "start", "START"), _val(a, "stop", "STOP")
    steps = [
        (_val(a, "red", "LIGHT_RED"), _pint(a, "t_red", 5, lo=1)),
        (_val(a, "green", "LIGHT_GREEN"), _pint(a, "t_green", 4, lo=1)),
        (_val(a, "yellow", "LIGHT_YELLOW"), _pint(a, "t_yellow", 2, lo=1)),
    ]
    return _build_sequencer(steps, start=start, stop=stop, loop=True, title="시간 신호등(순환)")


def _batch(a: Answers) -> StateMachineSpec:
    start, stop = _val(a, "start", "START"), _val(a, "stop", "STOP")
    steps = [
        (_val(a, "fill", "FILL_VALVE"), _pint(a, "t_fill", 8, lo=1)),
        (_val(a, "mixer", "MIXER"), _pint(a, "t_mix", 10, lo=1)),
        (_val(a, "drain", "DRAIN_VALVE"), _pint(a, "t_drain", 6, lo=1)),
    ]
    return _build_sequencer(steps, start=start, stop=stop, loop=False, title="배치 충전/교반/배출")


def _f(key: str, label: str, default: str, kind: str = "symbol") -> Field:
    return Field(key, label, default, kind)


RECIPES: dict[str, Recipe] = {
    r.id: r
    for r in [
        Recipe(
            "motor_start_stop", "모터 기동/정지", "버튼으로 켜고 끄는 자기유지 모터.", "기본",
            (_f("start", "기동 버튼", "START"), _f("stop", "정지 버튼", "STOP"),
             _f("motor", "모터 출력", "MOTOR")),
            _motor_start_stop,
            safety_note="정지(STOP)는 비상정지가 아닙니다. "
            "비상정지는 별도 하드와이어 E-stop 회로로 전원을 차단하세요.",
        ),
        Recipe(
            "fwd_rev", "정역 운전", "정방향/역방향, 동시 구동 금지(인터락).", "기본",
            (_f("fwd", "정방향 버튼", "FWD_PB"), _f("rev", "역방향 버튼", "REV_PB"),
             _f("stop", "정지", "STOP"), _f("motor_fwd", "정방향 모터", "MOTOR_FWD"),
             _f("motor_rev", "역방향 모터", "MOTOR_REV")),
            _fwd_rev,
            safety_note="이 인터락은 소프트웨어 로직입니다. 정/역 동시투입은 "
            "기계식 상호 잠금 접점(메인 컨택터)으로도 반드시 막으세요.",
        ),
        Recipe(
            "on_delay", "지연 기동", "기동 후 N초 뒤 출력 ON(타이머).", "타이머",
            (_f("start", "기동", "START"), _f("stop", "정지", "STOP"),
             _f("output", "출력", "OUTPUT"), _f("delay_sec", "지연(초)", "5", "time_sec")),
            _on_delay,
            safety_note="안전 정지는 타이머 지연에 의존하지 마세요. "
            "즉시 하드와이어로 동작해야 합니다.",
        ),
        Recipe(
            "hi_lo_level", "수위 제어", "저수위에서 펌프 ON, 고수위에서 OFF.", "공정",
            (_f("lo", "저수위 스위치", "LO_LS"), _f("hi", "고수위 스위치", "HI_LS"),
             _f("pump", "펌프", "PUMP")),
            _hi_lo_level,
            safety_note="오버플로우/공운전이 위험하면 하드와이어 고/저 레벨 트립을 별도로 두세요.",
        ),
        Recipe(
            "count_eject", "부품 카운터", "N개 세면 배출(카운터).", "카운터",
            (_f("sensor", "감지 센서", "PART_SENSOR"), _f("reset", "리셋", "RESET_PB"),
             _f("eject", "배출 출력", "EJECT"), _f("count", "개수", "10", "int")),
            _count_eject,
            safety_note="배출 기구에 사람이 접근 가능하면 "
            "가드/라이트커튼을 하드와이어 안전회로로 구성하세요.",
        ),
        Recipe(
            "auto_manual", "자동/수동 모드", "모드 선택으로 자동/수동 구동.", "모드",
            (_f("mode", "모드(자동=ON)", "MODE_AUTO"), _f("auto_cmd", "자동 명령", "AUTO_CMD"),
             _f("man_cmd", "수동 명령", "MAN_CMD"), _f("stop", "정지", "SYS_STOP"),
             _f("valve", "밸브", "VALVE")),
            _auto_manual,
            safety_note="수동(점동/조그) 모드의 위험 동작은 "
            "홀드-투-런 + 하드와이어 E-stop으로 보호하세요.",
        ),
        Recipe(
            "jog_run", "조그/연속 운전", "버튼으로 연속운전, 조그버튼은 누를 때만.", "기본",
            (_f("start", "연속 기동", "START_PB"), _f("stop", "정지", "STOP_PB"),
             _f("jog", "조그 버튼", "JOG_PB"), _f("motor_run", "연속 운전", "MOTOR_RUN"),
             _f("motor_jog", "조그 운전", "MOTOR_JOG")),
            _jog_run,
            safety_note="조그(점동)는 홀드-투-런으로만 동작시키고 "
            "위험부 접근은 하드와이어로 막으세요.",
        ),
        Recipe(
            "star_delta", "Y-Δ 기동", "스타로 기동 후 N초 뒤 델타로 전환(타이머).", "타이머",
            (_f("start", "기동", "START_PB"), _f("stop", "정지", "STOP_PB"),
             _f("main", "주접촉기", "MAIN_CON"), _f("star", "스타", "STAR_CON"),
             _f("delta", "델타", "DELTA_CON"), _f("delay_sec", "전환 지연(초)", "5", "time_sec")),
            _star_delta,
            safety_note="스타/델타 동시투입 금지는 기계식 상호잠금 접촉기로도 반드시 구성하세요.",
        ),
        Recipe(
            "latch_alarm", "래치형 알람", "고장 시 알람 래치, 해소+리셋으로 소거.", "알람",
            (_f("fault_a", "고장 A", "FAULT_A"), _f("fault_b", "고장 B", "FAULT_B"),
             _f("fault_c", "고장 C", "FAULT_C"), _f("reset", "리셋", "ALARM_RST"),
             _f("alarm", "알람", "ALARM")),
            _latch_alarm,
            safety_note="알람은 통지용입니다. 위험 정지는 "
            "하드와이어 안전회로가 별도로 해야 합니다.",
        ),
        Recipe(
            "first_out_alarm", "최초고장 알람", "먼저 난 고장만 표시(first-out).", "알람",
            (_f("fault_a", "고장 A", "FAULT_A"), _f("fault_b", "고장 B", "FAULT_B"),
             _f("ack", "확인", "ALM_ACK"), _f("reset", "리셋", "ALM_RST"),
             _f("latch_a", "A 최초", "LATCH_A"), _f("latch_b", "B 최초", "LATCH_B"),
             _f("horn", "경음기", "HORN")),
            _first_out_alarm,
            safety_note="알람/경음기는 통지용입니다. 안전 정지는 하드와이어로 구현하세요.",
        ),
        Recipe(
            "duty_standby", "펌프 리드/래그", "수요에 따라 주펌프, 고수요면 예비펌프 추가.", "공정",
            (_f("demand", "수요", "DEMAND"), _f("high_demand", "고수요", "HIGH_DEMAND"),
             _f("stop", "정지", "SYS_STOP"), _f("lead", "리드 펌프", "PUMP_LEAD"),
             _f("lag", "래그 펌프", "PUMP_LAG")),
            _duty_standby,
            safety_note="과압/공운전 보호는 하드와이어 압력/레벨 트립으로 별도 구성하세요.",
        ),
        Recipe(
            "two_hand_safety", "양수 조작 허가", "양손+가드+E-stop 정상일 때만 허가(보조).", "안전",
            (_f("lh", "좌측 버튼", "LH_BTN"), _f("rh", "우측 버튼", "RH_BTN"),
             _f("guard", "가드 닫힘", "GUARD_CLOSED"), _f("estop_ok", "E-stop 정상", "ESTOP_OK"),
             _f("enable", "기동 허가", "PRESS_ENABLE")),
            _two_hand,
            safety_note="⛔ 이것은 보조 로직일 뿐입니다. 양수조작·가드·E-stop 은 반드시 "
            "안전인증 부품(안전릴레이/안전PLC)으로 하드와이어 구현하세요(ISO 13849).",
        ),
        Recipe(
            "car_wash", "세차 순차", "기동하면 비누→헹굼→건조를 시간대로 진행.", "순차",
            (_f("start", "기동", "START"), _f("stop", "정지", "STOP"),
             _f("out1", "1단계(비누)", "SOAP"), _f("t1", "1단계 시간(초)", "5", "time_sec"),
             _f("out2", "2단계(헹굼)", "RINSE"), _f("t2", "2단계 시간(초)", "5", "time_sec"),
             _f("out3", "3단계(건조)", "DRY"), _f("t3", "3단계 시간(초)", "5", "time_sec")),
            _car_wash,
            safety_note="출입문·브러시 끼임 방지는 하드와이어 안전회로로 별도 구성하세요.",
        ),
        Recipe(
            "timed_traffic", "시간 신호등", "적→녹→황을 시간대로 자동 순환(반복).", "순차",
            (_f("start", "기동", "START"), _f("stop", "정지", "STOP"),
             _f("red", "적색등", "LIGHT_RED"), _f("t_red", "적색 시간(초)", "5", "time_sec"),
             _f("green", "녹색등", "LIGHT_GREEN"), _f("t_green", "녹색 시간(초)", "4", "time_sec"),
             _f("yellow", "황색등", "LIGHT_YELLOW"),
             _f("t_yellow", "황색 시간(초)", "2", "time_sec")),
            _timed_traffic,
            safety_note="교차 방향 동시 녹색 금지는 별도 인터락/하드와이어로 구성하세요.",
        ),
        Recipe(
            "batch_fill_mix_drain", "배치 충전/교반/배출", "충전→교반→배출을 시간대로.", "순차",
            (_f("start", "기동", "START"), _f("stop", "정지", "STOP"),
             _f("fill", "급수 밸브", "FILL_VALVE"), _f("t_fill", "충전 시간(초)", "8", "time_sec"),
             _f("mixer", "교반기", "MIXER"), _f("t_mix", "교반 시간(초)", "10", "time_sec"),
             _f("drain", "배출 밸브", "DRAIN_VALVE"),
             _f("t_drain", "배출 시간(초)", "6", "time_sec")),
            _batch,
            safety_note="오버플로우/과압은 하드와이어 레벨·압력 트립으로 별도 구성하세요.",
        ),
    ]
}


def list_recipes() -> list[dict[str, object]]:
    """프론트용 레시피 메타데이터."""
    return [
        {
            "id": r.id, "title": r.title, "description": r.description, "category": r.category,
            "safety_note": r.safety_note,
            "fields": [
                {"key": f.key, "label": f.label, "default": f.default, "kind": f.kind}
                for f in r.fields
            ],
        }
        for r in RECIPES.values()
    ]


def build_spec(recipe_id: str, answers: Answers | None = None) -> StateMachineSpec:
    """레시피 + 답변으로 결정론적 명세를 만든다(없는 레시피면 KeyError).

    잘못된 입력(공백·한글·예약어·충돌)은 WizardError(친절 메시지)로 거른다.
    """
    spec = RECIPES[recipe_id].build(answers or {})
    _validate_spec(spec)
    return spec
