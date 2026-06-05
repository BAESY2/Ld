"""가이드 마법사 — 비전문가가 '기획'(레시피 선택 + 빈칸)만으로 명세를 만든다.

완주 목표의 척추: PLC/ST 를 몰라도, 흔한 제어 의도를 고르고 신호 이름·시간만
채우면 유효한 StateMachineSpec 이 결정론적으로 만들어진다(LLM/키 불필요).
이후 synth → 래더 → 설명 파이프라인을 그대로 탄다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.models import (
    CounterSpec,
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


def _io(sym: str, d: IODirection, desc: str = "") -> IOPoint:
    return IOPoint(symbol=sym, direction=d, description=desc)


def _tr(frm: str, to: str, cond: str) -> Transition:
    return Transition(from_state=frm, to_state=to, condition=cond)


def _val(a: Answers, key: str, default: str) -> str:
    return (a.get(key) or "").strip() or default


def _pint(a: Answers, key: str, default: int, lo: int = 0) -> int:
    try:
        return max(lo, int(a.get(key) or default))
    except (ValueError, TypeError):
        return default


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
    return StateMachineSpec(
        title="자동/수동 모드 제어",
        io_points=[
            _io(mode, _IN, "모드(자동=ON)"),
            _io(ac, _IN, "자동 명령"),
            _io(mc, _IN, "수동 명령"),
            _io(stop, _IN, "정지"),
            _io(valve, _OUT, "밸브"),
        ],
        states=[
            SfcState(name="CLOSED", is_initial=True),
            SfcState(name="OPEN_A", on_entry=[f"{valve} := TRUE;"]),
            SfcState(name="OPEN_M", on_entry=[f"{valve} := TRUE;"]),
        ],
        transitions=[
            _tr("CLOSED", "OPEN_A", f"{mode} AND {ac} AND NOT {stop}"),
            _tr("CLOSED", "OPEN_M", f"NOT {mode} AND {mc} AND NOT {stop}"),
            _tr("OPEN_A", "CLOSED", f"{stop} OR NOT {ac}"),
            _tr("OPEN_M", "CLOSED", f"{stop} OR NOT {mc}"),
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
        ),
        Recipe(
            "fwd_rev", "정역 운전", "정방향/역방향, 동시 구동 금지(인터락).", "기본",
            (_f("fwd", "정방향 버튼", "FWD_PB"), _f("rev", "역방향 버튼", "REV_PB"),
             _f("stop", "정지", "STOP"), _f("motor_fwd", "정방향 모터", "MOTOR_FWD"),
             _f("motor_rev", "역방향 모터", "MOTOR_REV")),
            _fwd_rev,
        ),
        Recipe(
            "on_delay", "지연 기동", "기동 후 N초 뒤 출력 ON(타이머).", "타이머",
            (_f("start", "기동", "START"), _f("stop", "정지", "STOP"),
             _f("output", "출력", "OUTPUT"), _f("delay_sec", "지연(초)", "5", "time_sec")),
            _on_delay,
        ),
        Recipe(
            "hi_lo_level", "수위 제어", "저수위에서 펌프 ON, 고수위에서 OFF.", "공정",
            (_f("lo", "저수위 스위치", "LO_LS"), _f("hi", "고수위 스위치", "HI_LS"),
             _f("pump", "펌프", "PUMP")),
            _hi_lo_level,
        ),
        Recipe(
            "count_eject", "부품 카운터", "N개 세면 배출(카운터).", "카운터",
            (_f("sensor", "감지 센서", "PART_SENSOR"), _f("reset", "리셋", "RESET_PB"),
             _f("eject", "배출 출력", "EJECT"), _f("count", "개수", "10", "int")),
            _count_eject,
        ),
        Recipe(
            "auto_manual", "자동/수동 모드", "모드 선택으로 자동/수동 구동.", "모드",
            (_f("mode", "모드(자동=ON)", "MODE_AUTO"), _f("auto_cmd", "자동 명령", "AUTO_CMD"),
             _f("man_cmd", "수동 명령", "MAN_CMD"), _f("stop", "정지", "SYS_STOP"),
             _f("valve", "밸브", "VALVE")),
            _auto_manual,
        ),
    ]
}


def list_recipes() -> list[dict[str, object]]:
    """프론트용 레시피 메타데이터."""
    return [
        {
            "id": r.id, "title": r.title, "description": r.description, "category": r.category,
            "fields": [
                {"key": f.key, "label": f.label, "default": f.default, "kind": f.kind}
                for f in r.fields
            ],
        }
        for r in RECIPES.values()
    ]


def build_spec(recipe_id: str, answers: Answers | None = None) -> StateMachineSpec:
    """레시피 + 답변으로 결정론적 명세를 만든다(없는 레시피면 KeyError)."""
    return RECIPES[recipe_id].build(answers or {})
