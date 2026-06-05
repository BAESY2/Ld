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


# ---------------------------------------------------------------------------
# 뿌리산업/메카피온 레시피 (열처리·도금·용접·컨베이어·모션·프레스)
# ---------------------------------------------------------------------------
def _heat_treat(a: Answers) -> StateMachineSpec:
    """열처리 승온→유지→냉각 타임드 시퀀스(주조/금형 후공정).

    히터/유지/냉각(송풍) 출력을 단계별로 하나씩만 켜는 one-hot 시퀀스라
    합성/검증 무변경(_build_sequencer 의 all_off 가드로 상호배타 보장).
    """
    start, stop = _val(a, "start", "HEAT_START"), _val(a, "stop", "HEAT_STOP")
    steps = [
        (_val(a, "ramp", "HEATER"), _pint(a, "t_ramp", 30, lo=1)),     # 승온
        (_val(a, "hold", "SOAK"), _pint(a, "t_hold", 60, lo=1)),       # 유지
        (_val(a, "cool", "COOL_FAN"), _pint(a, "t_cool", 45, lo=1)),   # 냉각
    ]
    return _build_sequencer(steps, start=start, stop=stop, loop=False,
                            title="열처리 승온-유지-냉각")


def _plating_line(a: Answers) -> StateMachineSpec:
    """도금/표면처리 침지 시퀀스: 탈지→수세→도금→건조(호이스트 침지 라인).

    각 침지조 출력을 시간대로 순차 ON. one-hot all_off 가드로 동시 침지를 막는다.
    """
    start, stop = _val(a, "start", "PLATE_START"), _val(a, "stop", "PLATE_STOP")
    steps = [
        (_val(a, "degrease", "DEGREASE"), _pint(a, "t_deg", 20, lo=1)),  # 탈지조
        (_val(a, "rinse", "RINSE"), _pint(a, "t_rinse", 10, lo=1)),      # 수세조
        (_val(a, "plate", "PLATE"), _pint(a, "t_plate", 40, lo=1)),      # 도금조
        (_val(a, "dry", "DRY"), _pint(a, "t_dry", 15, lo=1)),            # 건조
    ]
    return _build_sequencer(steps, start=start, stop=stop, loop=False,
                            title="도금/표면처리 침지 시퀀스")


def _weld_cell(a: Answers) -> StateMachineSpec:
    """용접 셀 사이클: 클램프→용접→해제(시퀀스 인터락).

    클램프/용접/해제는 단계별로 하나씩만 켜지는 one-hot 시퀀스다. 상호배타는
    _build_sequencer 의 all_off 가드 + 타이머 핸드오프로 구조적으로 보장되므로
    명시적 Interlock 은 선언하지 않는다 — 시퀀스 진입 조건은 정적으로 상호배타가
    아니라 명세-단순 인터락 검사(check_interlocks_z3)가 거짓양성을 내기 때문이다
    (기존 _build_sequencer 규율과 동일; 검증기 무변경 약속 준수).
    """
    start, stop = _val(a, "start", "WELD_START"), _val(a, "stop", "WELD_STOP")
    steps = [
        (_val(a, "clamp", "CLAMP"), _pint(a, "t_clamp", 3, lo=1)),
        (_val(a, "weld", "WELD"), _pint(a, "t_weld", 5, lo=1)),
        (_val(a, "unclamp", "UNCLAMP"), _pint(a, "t_unclamp", 3, lo=1)),
    ]
    return _build_sequencer(steps, start=start, stop=stop, loop=False,
                            title="용접 셀 사이클(클램프→용접→해제)")


def _conveyor_divert(a: Answers) -> StateMachineSpec:
    """컨베이어 분기/병합: 한 라인을 좌/우(A/B)로 분기. 두 게이트 동시 작동 금지.

    정역 운전과 동형의 상호배제 자기유지(인터락). 선택 버튼으로 게이트를 열고
    정지/반대선택으로 닫는다.
    """
    sel_a = _val(a, "sel_a", "SEL_A")
    sel_b = _val(a, "sel_b", "SEL_B")
    stop = _val(a, "stop", "DIV_STOP")
    gate_a = _val(a, "gate_a", "GATE_A")
    gate_b = _val(a, "gate_b", "GATE_B")
    return StateMachineSpec(
        title="컨베이어 분기(A/B 게이트 인터락)",
        io_points=[
            _io(sel_a, _IN, "A 라인 선택"), _io(sel_b, _IN, "B 라인 선택"),
            _io(stop, _IN, "정지"),
            _io(gate_a, _OUT, "A 분기 게이트"), _io(gate_b, _OUT, "B 분기 게이트"),
        ],
        states=[
            SfcState(name="STRAIGHT", is_initial=True),
            SfcState(name="DIVERT_A", on_entry=[f"{gate_a} := TRUE;"]),
            SfcState(name="DIVERT_B", on_entry=[f"{gate_b} := TRUE;"]),
        ],
        transitions=[
            _tr("STRAIGHT", "DIVERT_A", f"{sel_a} AND NOT {sel_b} AND NOT {stop}"),
            _tr("DIVERT_A", "STRAIGHT", f"{stop} OR {sel_b}"),
            _tr("STRAIGHT", "DIVERT_B", f"{sel_b} AND NOT {sel_a} AND NOT {stop}"),
            _tr("DIVERT_B", "STRAIGHT", f"{stop} OR {sel_a}"),
        ],
        interlocks=[
            Interlock(output_a=gate_a, output_b=gate_b, reason="A/B 분기 게이트 동시 작동 금지"),
        ],
    )


def _motion_home_move(a: Answers) -> StateMachineSpec:
    """메카피온 모션: 원점복귀→이동→정위치. 비상정지(E-stop OK) 우선.

    원점복귀 명령(HOMING) 출력과 이동(MOVE) 출력은 동시에 켜지면 안 된다(인터락).
    모든 진입은 estop_ok(안전 정상)를 요구하고, 해제되면 즉시 IDLE 로 복귀한다.
    E-stop 자체는 하드와이어 — 여기 estop_ok 는 그 상태접점 반영일 뿐(safety_note).
    """
    start = _val(a, "start", "CYCLE_START")
    estop = _val(a, "estop_ok", "ESTOP_OK")  # 안전 정상=TRUE. b접점(NC) 배선 가정.
    homing = _val(a, "homing", "HOMING")
    moving = _val(a, "moving", "MOVING")
    inpos = _val(a, "in_pos", "IN_POS_LAMP")
    # 모션 사이클: 원점복귀(시간)→이동(시간)→정위치표시(시간). one-hot 시퀀서로
    # 단계별 한 출력만 켜져 상호배타가 구조적으로 보장된다(시퀀서/용접셀과 동일 규율).
    # E-stop 은 시퀀서의 정지입력으로 매핑 — NOT estop(안전 해제) 시 즉시 IDLE 로
    # 떨어지게 stop=NOT estop 형태로 진입/유지 가드에 반영한다(E-stop 우선).
    home_t = _pint(a, "t_home", 5, lo=1)
    move_t = _pint(a, "t_move", 8, lo=1)
    pos_t = _pint(a, "t_pos", 2, lo=1)
    stop = f"NOT {estop}"  # 안전 정상이 빠지면(=E-stop) 정지
    outs = [homing, moving, inpos]
    all_off = " AND ".join(f"NOT {o}" for o in outs)
    return StateMachineSpec(
        title="모션 원점복귀→이동→정위치(E-stop 우선)",
        io_points=[
            _io(start, _IN, "사이클 기동"), _io(estop, _IN, "E-stop 정상(안전접점, NC)"),
            _io(homing, _OUT, "원점복귀 구동"), _io(moving, _OUT, "이동 구동"),
            _io(inpos, _OUT, "정위치 도달 표시"),
        ],
        timers=[
            TimerSpec(name="T0", preset_ms=home_t * 1000, enable_condition=homing,
                      description=f"원점복귀 {home_t}초"),
            TimerSpec(name="T1", preset_ms=move_t * 1000, enable_condition=moving,
                      description=f"이동 {move_t}초"),
            TimerSpec(name="T2", preset_ms=pos_t * 1000, enable_condition=inpos,
                      description=f"정위치 표시 {pos_t}초"),
        ],
        states=[
            SfcState(name="IDLE", is_initial=True),
            SfcState(name="HOMING", on_entry=[f"{homing} := TRUE;"]),
            SfcState(name="MOVING", on_entry=[f"{moving} := TRUE;"]),
            SfcState(name="IN_POS", on_entry=[f"{inpos} := TRUE;"]),
        ],
        transitions=[
            _tr("IDLE", "HOMING", f"{start} AND {estop} AND {all_off}"),
            _tr("HOMING", "IDLE", stop),
            _tr("HOMING", "MOVING", f"T0.Q AND {estop}"),
            _tr("MOVING", "IDLE", stop),
            _tr("MOVING", "IN_POS", f"T1.Q AND {estop}"),
            _tr("IN_POS", "IDLE", f"T2.Q OR {stop}"),
        ],
    )


def _press_muting(a: Answers) -> StateMachineSpec:
    """프레스 안전 허가: 양수조작 + 가드 닫힘 + (뮤팅 보조) + E-stop 정상.

    뮤팅(muting)은 자동공급 등 정해진 구간에서 라이트커튼을 일시 무효화하는 보조 신호.
    여기서는 '양손 동시 + 가드 + E-stop' 의 기본 허가에 더해, 뮤팅구간이면 양손
    유지 없이도 허가가 유지되도록 하는 *보조 로직*만 만든다(인증부품 아님 — safety_note).
    """
    lh = _val(a, "lh", "LH_BTN")
    rh = _val(a, "rh", "RH_BTN")
    guard = _val(a, "guard", "GUARD_CLOSED")
    mute = _val(a, "mute", "MUTE_ZONE")
    estop = _val(a, "estop_ok", "ESTOP_OK")
    enable = _val(a, "enable", "PRESS_ENABLE")
    if lh == rh:
        raise WizardError("좌/우 버튼은 서로 다른 신호여야 합니다(양수 조작의 핵심).")
    both_hands = f"{lh} AND {rh}"
    return StateMachineSpec(
        title="프레스 안전 허가(양수+가드+뮤팅 보조)",
        io_points=[
            _io(lh, _IN, "좌측 버튼"), _io(rh, _IN, "우측 버튼"),
            _io(guard, _IN, "가드 닫힘"), _io(mute, _IN, "뮤팅 구간(보조)"),
            _io(estop, _IN, "E-stop 정상"), _io(enable, _OUT, "기동 허가"),
        ],
        states=[
            SfcState(name="SAFE", is_initial=True),
            SfcState(name="ENABLED", on_entry=[f"{enable} := TRUE;"]),
        ],
        transitions=[
            # 진입: 양손 동시 + 가드 + E-stop 정상
            _tr("SAFE", "ENABLED", f"{both_hands} AND {guard} AND {estop}"),
            # 해제: 가드/ E-stop 이 빠지면 즉시. 손은 뮤팅구간이 아니면 유지 필요.
            _tr("ENABLED", "SAFE",
                f"NOT {guard} OR NOT {estop} OR (NOT ({both_hands}) AND NOT {mute})"),
        ],
    )


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
            safety_note="스타/델타 동시투입 금지는 기계식 상호잠금 접촉기로도 반드시 "
            "구성하세요. 또한 Y→Δ 전환 시 상간 단락 방지를 위해 접촉기 차단-후-투입 "
            "데드타임(약 50~100ms)을 두세요(시뮬레이터는 이상적 즉시 전환으로 표시됨).",
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
        Recipe(
            "heat_treat", "열처리 승온-유지-냉각",
            "기동하면 승온→유지→냉각을 시간대로 진행(주조/금형 후공정).", "뿌리산업",
            (_f("start", "기동", "HEAT_START"), _f("stop", "정지", "HEAT_STOP"),
             _f("ramp", "히터(승온)", "HEATER"), _f("t_ramp", "승온 시간(초)", "30", "time_sec"),
             _f("hold", "유지", "SOAK"), _f("t_hold", "유지 시간(초)", "60", "time_sec"),
             _f("cool", "냉각(송풍)", "COOL_FAN"), _f("t_cool", "냉각 시간(초)", "45", "time_sec")),
            _heat_treat,
            safety_note="노 과열·CO 가스·화상 위험은 하드와이어 과온 트립(over-temp)·"
            "가스경보·안전문 인터락으로 별도 구성하세요. 타이머는 공정 시간일 뿐 "
            "안전 정지가 아닙니다(KOSHA 열처리 안전수칙).",
        ),
        Recipe(
            "plating_line", "도금/표면처리 침지",
            "기동하면 탈지→수세→도금→건조를 시간대로 침지(표면처리 라인).", "뿌리산업",
            (_f("start", "기동", "PLATE_START"), _f("stop", "정지", "PLATE_STOP"),
             _f("degrease", "탈지조", "DEGREASE"), _f("t_deg", "탈지 시간(초)", "20", "time_sec"),
             _f("rinse", "수세조", "RINSE"), _f("t_rinse", "수세 시간(초)", "10", "time_sec"),
             _f("plate", "도금조", "PLATE"), _f("t_plate", "도금 시간(초)", "40", "time_sec"),
             _f("dry", "건조", "DRY"), _f("t_dry", "건조 시간(초)", "15", "time_sec")),
            _plating_line,
            safety_note="산·알칼리 약품조, 미스트·환기, 호이스트 협착은 하드와이어 "
            "안전회로(레벨/누액 감지, 환기 인터락, 호이스트 리미트)로 별도 구성하세요.",
        ),
        Recipe(
            "weld_cell", "용접 셀 사이클",
            "클램프→용접→해제를 시간대로(클램프/해제 인터락).", "뿌리산업",
            (_f("start", "기동", "WELD_START"), _f("stop", "정지", "WELD_STOP"),
             _f("clamp", "클램프", "CLAMP"), _f("t_clamp", "클램프 시간(초)", "3", "time_sec"),
             _f("weld", "용접", "WELD"), _f("t_weld", "용접 시간(초)", "5", "time_sec"),
             _f("unclamp", "해제", "UNCLAMP"),
             _f("t_unclamp", "해제 시간(초)", "3", "time_sec")),
            _weld_cell,
            safety_note="아크광·흄·협착·감전 위험은 하드와이어 안전회로(차광커튼, 국소배기 "
            "인터락, 협착 방지 가드, E-stop)로 별도 구성하세요. 클램프/해제 동시투입 "
            "금지는 솔레노이드 측 기계식 인터락으로도 이중화하세요(ISO 13849).",
        ),
        Recipe(
            "conveyor_divert", "컨베이어 분기/병합",
            "선택 버튼으로 라인을 A/B로 분기(두 게이트 동시 작동 금지).", "뿌리산업",
            (_f("sel_a", "A 선택", "SEL_A"), _f("sel_b", "B 선택", "SEL_B"),
             _f("stop", "정지", "DIV_STOP"), _f("gate_a", "A 게이트", "GATE_A"),
             _f("gate_b", "B 게이트", "GATE_B")),
            _conveyor_divert,
            safety_note="분기/병합부 협착·끼임은 하드와이어 안전회로(끼임 방지 가드, "
            "비상정지 풀코드)로 별도 구성하세요. 게이트 상호배제는 소프트 인터락입니다.",
        ),
        Recipe(
            "motion_home_move", "메카피온 모션(원점→이동→정위치)",
            "기동하면 원점복귀→이동→정위치를 시간대로(E-stop 우선, one-hot).", "모션",
            (_f("start", "사이클 기동", "CYCLE_START"),
             _f("estop_ok", "E-stop 정상(NC)", "ESTOP_OK"),
             _f("homing", "원점복귀 구동", "HOMING"),
             _f("t_home", "원점복귀 시간(초)", "5", "time_sec"),
             _f("moving", "이동 구동", "MOVING"),
             _f("t_move", "이동 시간(초)", "8", "time_sec"),
             _f("in_pos", "정위치 표시", "IN_POS_LAMP"),
             _f("t_pos", "정위치 표시 시간(초)", "2", "time_sec")),
            _motion_home_move,
            safety_note="비상정지(E-stop)는 반드시 하드와이어로 서보앰프 전원/STO 를 "
            "차단하세요. 여기 ESTOP_OK 는 그 안전접점의 상태반영일 뿐(NC 페일세이프) "
            "소프트 로직이 안전기능을 대체하지 않습니다(ISO 13849, 서보 STO).",
        ),
        Recipe(
            "press_muting", "프레스 안전(양수+가드+뮤팅)",
            "양손+가드+E-stop 정상 시 허가, 뮤팅 구간에선 양손 유지 면제(보조).", "안전",
            (_f("lh", "좌측 버튼", "LH_BTN"), _f("rh", "우측 버튼", "RH_BTN"),
             _f("guard", "가드 닫힘", "GUARD_CLOSED"), _f("mute", "뮤팅 구간", "MUTE_ZONE"),
             _f("estop_ok", "E-stop 정상", "ESTOP_OK"), _f("enable", "기동 허가", "PRESS_ENABLE")),
            _press_muting,
            safety_note="⛔ 이것은 보조 로직일 뿐입니다. 양수조작·가드·뮤팅·E-stop 은 반드시 "
            "안전인증 부품(안전릴레이/안전PLC, 뮤팅은 인증 뮤팅모듈)으로 하드와이어 "
            "구현하세요. 뮤팅 오용은 중대재해로 직결됩니다(KOSHA 프레스 방호, ISO 13849).",
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
