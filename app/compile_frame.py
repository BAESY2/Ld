"""의도 프레임 → 검증 가능한 명세 *컴파일러* (레시피 없는 조합적 합성 — 천장 돌파).

37개 템플릿(레시피)에 스냅시키는 대신, 파싱된 의도(IntentFrame)를 직접 StateMachineSpec
으로 *컴파일*한다. 표현 공간이 조합적이다: 임의의 (조건 × 동작 × 기기) 조합이 — 어떤
레시피에도 없던 것이라도 — 검증 가능한 ST 로 합성된다. 산출물은 그대로 synth→verify
게이트를 통과해야 채택된다(LLM·환각 없음, 100% 결정론).

컴파일 모델(한국어 SOV·조건절): 조건절은 다음 동작(들)을 지배하는 트리거가 되고, 각
동작은 출력의 ON/OFF 트리거가 된다. 출력마다 자기유지식
``OUT := (ON OR OUT) AND NOT (OFF)`` 로 컴파일하고, 아날로그 조건은 비교기, 계수 조건은
카운터로 푼다. 미해결 절은 unresolved 로 보고해 확신을 낮춘다(거짓 합성 방지).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.intent import ClauseKind, IntentClause, IntentFrame, extract
from app.korean import Analysis
from app.models import (
    Comparator,
    CompareOp,
    CounterSpec,
    DataType,
    DerivedOutput,
    Interlock,
    IODirection,
    IOPoint,
    StateMachineSpec,
)

_ON = {"RUN", "TURN_ON", "OPEN", "EJECT", "CLAMP_ON", "UP", "SPRAY_ON", "VAC_ON"}
_OFF = {"STOP", "TURN_OFF", "CLOSE", "CLAMP_OFF", "DOWN"}
# 출력 액추에이터 기기 → 출력 심볼.
_DEV_OUT = {
    "MOTOR": "MOTOR", "PUMP": "PUMP", "VALVE": "VALVE", "LAMP": "LAMP",
    "BEACON": "BEACON", "HEATER": "HEATER", "CONVEYOR": "CONVEYOR",
    "GATE": "GATE", "SHUTTER": "SHUTTER", "BUZZER": "BUZZER", "SIREN": "SIREN",
    "HORN": "HORN", "FAN": "FAN", "BLOWER": "BLOWER", "VACUUM": "VACUUM",
    "CLAMP": "CLAMP", "CHUCK": "CHUCK", "DOOR": "DOOR", "HOPPER": "HOPPER",
    "FEEDER": "FEEDER", "NOZZLE": "NOZZLE", "SPRAY": "SPRAY", "DRILL": "DRILL",
    "ROBOT": "ROBOT", "SOLENOID": "SOLENOID", "CYLINDER": "CYLINDER",
    "COOLER": "COOLER", "COMPRESSOR": "COMPRESSOR",
    "LAMP_R": "LAMP_R", "LAMP_G": "LAMP_G", "LAMP_Y": "LAMP_Y",
}
# 조건 기기 → (트리거 입력 심볼). 아날로그/계수는 별도(비교기/카운터)로 푼다.
_DEV_TRIG = {
    "LEVEL_LO": "LO_LS", "LEVEL_HI": "HI_LS", "LEVEL": "LEVEL_SW",
    "FAULT": "FAULT", "SENSOR": "SENSOR", "SWITCH": "SWITCH",
    "LIMIT": "LIMIT_SW", "PROX": "PROX_SW", "PHOTO": "PHOTO_SW",
}
# 센서/상태 조건 술어(기기 없이도 입력 신호로 푼다).
_SENSOR_PRED = {"ARRIVE", "DONE", "EMPTY", "JAM", "DETECT"}
_ANALOG = {"PRESSURE": "PRESSURE", "TEMP": "TEMP"}


@dataclass
class _Builder:
    inputs: dict[str, DataType] = field(default_factory=dict)  # 심볼→타입(BOOL/REAL)
    comparators: list[Comparator] = field(default_factory=list)
    counters: list[CounterSpec] = field(default_factory=list)
    _cmp_n: int = 0
    _cnt_n: int = 0

    def add_input(self, sym: str, dt: DataType = DataType.BOOL) -> str:
        self.inputs.setdefault(sym, dt)
        return sym

    def analog_flag(self, signal: str, value: float) -> str:
        self.add_input(signal, DataType.REAL)
        self._cmp_n += 1
        flag = f"{signal}_HI"
        self.comparators.append(
            Comparator(flag=flag, signal=signal, op=CompareOp.GE, threshold=value)
        )
        return flag

    def counter_q(self, preset: int) -> str:
        self._cnt_n += 1
        name = f"C{self._cnt_n}"
        sensor = self.add_input("PART_SENSOR")
        self.add_input("RESET")
        self.counters.append(
            CounterSpec(name=name, count_condition=sensor, reset_condition="RESET",
                        preset=max(1, preset))
        )
        return f"{name}.Q"


# 조건절 → 트리거 식(또는 None=미해결). 버튼/누름은 동작 극성으로 결정되니 PRESS 표지를 둔다.
def _resolve_cond(c: IntentClause, b: _Builder) -> str | None:
    if c.predicate == "PRESS" or c.device == "BUTTON":
        return "PRESS"  # 동작 극성에 따라 START/STOP 으로 후처리
    if c.device in _DEV_TRIG:
        return b.add_input(_DEV_TRIG[c.device])
    if c.device in _ANALOG and c.value is not None:
        return b.analog_flag(_ANALOG[c.device], float(c.value))
    if c.predicate in ("COUNT", "FILL") and c.value is not None:
        return b.counter_q(c.value)
    if c.device == "PART" and c.value is not None:
        return b.counter_q(c.value)
    if c.device:  # 일반 기기 → 입력 신호(피드백/센서). 커버리지 확장.
        return b.add_input(f"{c.device}_SIG")
    if c.predicate in _SENSOR_PRED:
        return b.add_input(f"{c.predicate}_SIG")
    return None


def _out_symbol(c: IntentClause) -> str:
    if c.device in _DEV_OUT:
        return _DEV_OUT[c.device]
    if c.predicate == "EJECT":
        return "EJECT"
    return "OUT"


@dataclass
class CompileResult:
    spec: StateMachineSpec
    unresolved: list[str] = field(default_factory=list)  # 컴파일 못한 절(설명)
    confident: bool = False

    def explain(self) -> str:
        if self.unresolved:
            return "미해결: " + "; ".join(self.unresolved)
        return "전 절 컴파일됨"


def frame_to_spec(source: IntentFrame | Analysis | str) -> CompileResult:
    """의도 프레임을 검증 가능한 StateMachineSpec 으로 컴파일한다(레시피 비의존)."""
    frame = (
        source if isinstance(source, IntentFrame)
        else extract(source)
    )
    b = _Builder()
    # 출력별 ON/OFF 트리거 수집(삽입순 유지).
    on_trig: dict[str, list[str]] = {}
    off_trig: dict[str, list[str]] = {}
    order: list[str] = []
    pending: list[str | None] = []
    last_action = False
    unresolved: list[str] = []

    for c in frame.clauses:
        if c.kind == ClauseKind.COND:
            if last_action:
                pending = []
            pending.append(_resolve_cond(c, b))
            last_action = False
        else:  # ACTION
            out = _out_symbol(c)
            if out not in order:
                order.append(out)
                on_trig[out] = []
                off_trig[out] = []
            on = c.predicate in _ON
            off = c.predicate in _OFF
            if not (on or off):
                unresolved.append(f"동작 '{c.predicate}' 해석 불가")
                last_action = True
                continue
            # 부정 동작('못 돌게')은 조건이 그 출력을 *억제*하도록 OFF 로 돌린다.
            if c.negated:
                on, off = False, True
            trigs = pending or ["PRESS"]  # 조건 없으면 기본 버튼 트리거
            for t in trigs:
                if t is None:
                    unresolved.append("조건 해석 불가")
                    continue
                if t == "PRESS":  # 버튼: ON 동작=START, OFF 동작=STOP
                    t = b.add_input("START" if on else "STOP")
                (on_trig if on else off_trig)[out].append(t)
            last_action = True

    # 출력별 자기유지 파생식 생성.
    derived: list[DerivedOutput] = []
    for out in order:
        ons = list(dict.fromkeys(on_trig[out]))
        offs = list(dict.fromkeys(off_trig[out]))
        if ons and offs:
            expr = f"({' OR '.join(ons)} OR {out}) AND NOT ({' OR '.join(offs)})"
        elif ons:
            expr = f"({' OR '.join(ons)} OR {out})"
        elif offs:
            expr = f"{out} AND NOT ({' OR '.join(offs)})"
        else:
            unresolved.append(f"출력 '{out}' 트리거 없음")
            continue
        derived.append(DerivedOutput(output=out, expression=expr))

    io: list[IOPoint] = [
        IOPoint(symbol=s, direction=IODirection.INPUT, data_type=dt)
        for s, dt in b.inputs.items()
    ]
    io += [IOPoint(symbol=o, direction=IODirection.OUTPUT) for o in order]
    spec = StateMachineSpec(
        title=(frame.text[:40] or "컴파일된 명세"),
        io_points=io, comparators=b.comparators, counters=b.counters,
        derived_outputs=derived, interlocks=_infer_interlocks(off_trig, on_trig, order),
    )
    confident = frame.confident and not unresolved and bool(derived)
    return CompileResult(spec=spec, unresolved=unresolved, confident=confident)


def _infer_interlocks(
    off_trig: dict[str, list[str]], on_trig: dict[str, list[str]], order: list[str]
) -> list[Interlock]:
    """두 출력이 서로의 ON 트리거를 OFF 로 가지면 상호배제로 본다(현재는 보수적 빈 목록)."""
    return []  # v1: 명시 인터락 추론은 보류(거짓 인터락 방지). 추후 확장.
