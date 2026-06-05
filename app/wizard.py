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
        return max(lo, int(a.get(key) or default))
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
