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
from app.korean import Analysis, Pos, analyze
from app.models import (
    Comparator,
    CompareOp,
    CounterSpec,
    DataType,
    DerivedOutput,
    DeviceClass,
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
    # 보틀링/포장 라인
    "FILLER": "FILLER", "CAPPER": "CAPPER", "LABELER": "LABELER",
    "WASHER": "WASHER", "PACKER": "PACKER",
    # 정역 운전(전동기 방향)
    "DIR_FWD": "MOTOR_FWD", "DIR_REV": "MOTOR_REV",
}
# 조건 기기 → (트리거 입력 심볼). 아날로그/계수는 별도(비교기/카운터)로 푼다.
_DEV_TRIG = {
    "LEVEL_LO": "LO_LS", "LEVEL_HI": "HI_LS", "LEVEL": "LEVEL_SW",
    "FAULT": "FAULT", "SENSOR": "SENSOR", "SWITCH": "SWITCH",
    "LIMIT": "LIMIT_SW", "PROX": "PROX_SW", "PHOTO": "PHOTO_SW",
    "VISION": "VISION_NG", "NG": "NG_SENSOR",
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

    def analog_flag(self, signal: str, value: float, op: CompareOp = CompareOp.GE) -> str:
        """비교기 플래그 — (신호·연산·임계)별로 *고유* 이름(같은 신호 다중 임계의 이중코일 방지).

        같은 (신호,연산,임계) 재요청이면 기존 플래그를 재사용(중복 비교기 생성 안 함).
        """
        self.add_input(signal, DataType.REAL)
        tag = "GE" if op in (CompareOp.GE, CompareOp.GT) else "LE"
        flag = f"{signal}_{tag}{int(value) if value == int(value) else value}"
        if not any(c.flag == flag for c in self.comparators):
            self.comparators.append(
                Comparator(flag=flag, signal=signal, op=op, threshold=value)
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
        op = CompareOp.LE if c.predicate == "DROP" else CompareOp.GE
        return b.analog_flag(_ANALOG[c.device], float(c.value), op)
    if c.predicate in ("COUNT", "FILL") and c.value is not None:
        return b.counter_q(int(c.value))
    if c.device in ("PART", "BOTTLE") and c.value is not None:
        return b.counter_q(int(c.value))
    if c.device:  # 일반 기기 → 입력 신호(피드백/센서). 커버리지 확장.
        return b.add_input(f"{c.device}_SIG")
    if c.predicate in _SENSOR_PRED:
        return b.add_input(f"{c.predicate}_SIG")
    return None


# 측정/신호/용기·소재 — 구동(켜기/돌리기/열기) 대상이 아니다(센서·물리량은 액추에이터가 아님).
# 이들이 ACTION 의 대상이면 의미 난센스("온도 올려"·"탱크 켜"·"압력 켜")로 보고 정직 거절한다.
_NON_ACTUATABLE = {
    "PRESSURE", "TEMP", "LEVEL", "LEVEL_LO", "LEVEL_HI", "FAULT", "BUTTON",
    "SENSOR", "SWITCH", "LIMIT", "PROX", "PHOTO", "PART", "TANK", "BOTTLE",
    "VISION", "NG",
}
# 물리 구동을 뜻하는 동작 술어(이것이 비액추에이터에 걸리면 부적합).
_ACTUATION_PREDS = _ON | _OFF


def _action_valid(c: IntentClause) -> bool:
    """ACTION 절의 (기기, 동작)이 물리적으로 말이 되는가(측정/신호 기기 구동 거절)."""
    if c.device in _NON_ACTUATABLE and c.predicate in _ACTUATION_PREDS:
        return False
    return True


def _out_symbol(c: IntentClause) -> str | None:
    """동작 절의 출력 심볼. 기기 미상(무주어)은 None — 호출부가 직전 기기로 해소(anaphora)
    하거나 정직 미해결 처리한다(유령 'OUT' 코일 합성 금지)."""
    if not c.device and c.predicate != "EJECT":
        return None
    base = _DEV_OUT.get(c.device or "")
    if base is None:
        # 미등록 기기 — 카테고리명을 심볼로 그대로 쓴다(예: JIG).
        # 과거엔 무엇이든 'EJECT' 로 합성되는 잘못된 폴백이었다(기기 뒤바뀜).
        base = "EJECT" if (not c.device and c.predicate == "EJECT") else (c.device or "EJECT")
    # 인스턴스 마커가 있으면 고유 심볼(PUMP1/PUMP2/GATE_A) — 인스턴스별로 분리된다.
    if c.instance and base != "EJECT":
        return f"{base}{c.instance.upper()}"
    return base


def _is_button_name(clauses: list[IntentClause], i: int) -> bool:
    """'기동/정지 *누르면*' 의 선두 무주어 동작은 동작이 아니라 *버튼 이름*이다.

    무주어 ACTION 바로 뒤에 PRESS 조건이 오면 그 ACTION 은 버튼 라벨(기동→START,
    정지→STOP)일 뿐이므로 건너뛴다 — 극성은 뒤따르는 실제 동작이 결정한다.
    """
    c = clauses[i]
    if c.kind != ClauseKind.ACTION or _out_symbol(c) is not None:
        return False
    nxt = clauses[i + 1] if i + 1 < len(clauses) else None
    return nxt is not None and nxt.kind == ClauseKind.COND and (
        nxt.predicate == "PRESS" or nxt.device == "BUTTON"
    )


@dataclass
class CompileResult:
    spec: StateMachineSpec
    unresolved: list[str] = field(default_factory=list)  # 컴파일 못한 절(설명)
    confident: bool = False

    def explain(self) -> str:
        if self.unresolved:
            return "미해결: " + "; ".join(self.unresolved)
        return "전 절 컴파일됨"


def _seq_steps(frame: IntentFrame) -> list[tuple[str, int]]:
    """순차 동작 단계 [(출력, 드웰초)]. 단계 드웰 = '다음 단계 진입 지연'(없으면 기본 2초).

    무주어 단계는 직전 기기로 해소(anaphora) — 그러면 출력 중복이 되어 호출부의
    중복 검사("시퀀스 부적합")로 정직 거절된다. 선행 기기조차 없으면 빈 목록(부적합).
    """
    acts = [
        c for i, c in enumerate(frame.clauses)
        if c.kind == ClauseKind.ACTION and not _is_button_name(frame.clauses, i)
    ]
    steps: list[tuple[str, int]] = []
    last: str | None = None
    for i, c in enumerate(acts):
        sym = _out_symbol(c) or last
        if sym is None:
            return []
        last = sym
        nxt = acts[i + 1] if i + 1 < len(acts) else None
        sec = (nxt.delay_ms // 1000) if (nxt and nxt.delay_ms) else 2
        steps.append((sym, max(1, sec)))
    return steps


def _compile_sequence(frame: IntentFrame) -> CompileResult:
    """순차/타이밍 의도 → 검증된 one-hot 타임드 시퀀서(wizard._build_sequencer 재사용)."""
    from app.wizard import _build_sequencer

    steps = _seq_steps(frame)
    outs = [o for o, _ in steps]
    if len(steps) < 2 or len(set(outs)) != len(outs):  # 단계<2 또는 출력 중복 → 시퀀스 부적합
        return CompileResult(StateMachineSpec(), unresolved=["시퀀스 부적합"], confident=False)
    spec = _build_sequencer(
        steps, start="START", stop="STOP", loop=False,
        title=(frame.text[:40] or "순차 제어"),
    )
    # 단계 출력을 상호배제 그룹으로 선언 → verify 가 'at-most-one 단계 활성'(one-hot)을
    # k-귀납으로 *증명*한다(시퀀스 안전성을 형식 보장으로 격상; 구조적 보장의 기계검증).
    spec.interlocks = [
        Interlock(output_a=outs[i], output_b=outs[j])
        for i in range(len(outs)) for j in range(i + 1, len(outs))
    ]
    return CompileResult(spec=spec, unresolved=[], confident=frame.confident)



# 동력 단위 → kW 환산 (마력=0.746kW). 산식 선정(plant)의 입력이 된다.
_POWER_UNITS = {"킬로와트": 1.0, "키로와트": 1.0, "키로": 1.0, "kw": 1.0, "마력": 0.746}


def _clause_power_kw(c: IntentClause) -> float | None:
    if c.value is None:
        return None
    factor = _POWER_UNITS.get(c.unit.lower())
    return round(float(c.value) * factor, 2) if factor else None


def _compile_star_delta(frame: IntentFrame) -> CompileResult:
    """'스타델타 기동' → 표준 Y-Δ 기동 회로를 컴파일한다(현업 표준 패턴).

    회로 의미(380V 3상 기동전류 저감 — 기동시 권선을 Y 로 묶어 전류 1/3, 가속 후 Δ):
      MOTOR  := (START OR MOTOR) AND NOT STOP;       ← 주접촉기(MC-M) 자기유지
      T1(IN := MOTOR, PT := T#7s);                   ← 전환 타이머(가속 시간)
      MOTOR_D := (MOTOR AND T1.Q) AND NOT MOTOR_Y;   ← Δ접촉기 — *Y 보다 먼저 평가*
      MOTOR_Y := MOTOR AND NOT T1.Q AND NOT MOTOR_D; ← Y접촉기
    Δ 렁을 Y 보다 먼저 두면 전환 스캔에서 Δ 가 직전 Y(아직 참)를 보고 1스캔 쉬어
    **개방전환 데드타임**이 생기고, 상호 'AND NOT' 가드로 Y⊥Δ 동시투입(상간단락)이
    구조적으로 불가능하다 — 인터락으로 선언해 k-귀납으로 *증명*한다.
    """
    from app.models import TimerSpec

    kw = None
    for c in frame.clauses:
        kw = kw or _clause_power_kw(c)
    io = [
        IOPoint(symbol="START", direction=IODirection.INPUT),
        IOPoint(symbol="STOP", direction=IODirection.INPUT),
        IOPoint(symbol="MOTOR", direction=IODirection.OUTPUT, power_kw=kw,
                description="주접촉기 MC-M"),
        IOPoint(symbol="MOTOR_D", direction=IODirection.OUTPUT,
                description="델타접촉기 MC-D"),
        IOPoint(symbol="MOTOR_Y", direction=IODirection.OUTPUT,
                description="와이접촉기 MC-Y"),
    ]
    spec = StateMachineSpec(
        title=(frame.text[:40] or "스타델타 기동"),
        io_points=io,
        timers=[TimerSpec(name="T1", preset_ms=7000, enable_condition="MOTOR",
                          description="Y→Δ 전환(가속) 타이머")],
        derived_outputs=[
            DerivedOutput(output="MOTOR", expression="(START OR MOTOR) AND NOT (STOP)"),
            DerivedOutput(output="MOTOR_D",
                          expression="(MOTOR AND T1.Q) AND NOT MOTOR_Y"),
            DerivedOutput(output="MOTOR_Y",
                          expression="MOTOR AND NOT T1.Q AND NOT MOTOR_D"),
        ],
        interlocks=[Interlock(output_a="MOTOR_Y", output_b="MOTOR_D",
                              reason="Y-Δ 동시투입(상간단락) 금지")],
    )
    return CompileResult(spec=spec, unresolved=[], confident=frame.confident)


def _alternation_base(frame: IntentFrame) -> str:
    """교번 대상 기기의 출력 심볼 베이스(미상이면 PUMP — 현업 교번의 기본은 펌프 2대).

    절(clause)은 동사에 가장 가까운 체언만 남기므로('펌프 교대로'의 펌프가 ALTERNATE
    에 덮인다), 원문을 다시 형태소 분석해 첫 액추에이터 체언을 찾는다(결정론·키 불필요).
    """
    for m in analyze(frame.text).morphemes:
        if m.pos == Pos.NOUN and m.category in _DEV_OUT:
            return _DEV_OUT[m.category]
    return "PUMP"


def _compile_alternator(frame: IntentFrame) -> CompileResult:
    """'교대/교번 운전' → 펌프 2대 교번(alternation) 표준회로를 컴파일한다(현업 패턴).

    회로(렁 순서가 의미를 만든다 — 자기참조·아래 렁 참조 = 직전 스캔 값):
      EDGE       := (START AND NOT START_PREV) AND NOT RUN;   ← 정지 중 기동 엣지만
      START_PREV := START;                                    ← EDGE *다음* 렁(직전값 공급)
      TGL        := (EDGE AND NOT TGL) OR (TGL AND NOT EDGE); ← 기동 엣지마다 토글
      RUN        := (START OR RUN) AND NOT STOP;              ← 운전 자기유지
      PUMP1      := RUN AND TGL;                              ← 첫 기동 스캔에 TGL 이
      PUMP2      := RUN AND NOT TGL;                             0→1 토글 → TGL=1 이 1호기
    EDGE 의 'AND NOT RUN' 가드(직전 스캔 RUN 참조)로 운전 *중* 재기동 누름이 펌프를
    갈아타지 않는다. PUMP1/PUMP2 는 같은 스캔의 TGL 한 값에서 상보로 갈리므로 동시
    ON 이 구조적으로 불가능하다 — 인터락으로 선언해 k-귀납으로 *증명*한다.
    """
    base = _alternation_base(frame)
    p1, p2 = f"{base}1", f"{base}2"
    aux: list[tuple[str, str, str]] = [
        ("EDGE", "(START AND NOT START_PREV) AND NOT RUN", "기동 상승엣지(1스캔 펄스)"),
        ("START_PREV", "START", "START 직전 스캔 값(엣지 검출용)"),
        ("TGL", "(EDGE AND NOT TGL) OR (TGL AND NOT EDGE)", "교번 선택 토글(1=1호기)"),
        ("RUN", "(START OR RUN) AND NOT STOP", "운전 자기유지"),
    ]
    io = [
        IOPoint(symbol="START", direction=IODirection.INPUT, description="기동 버튼"),
        IOPoint(symbol="STOP", direction=IODirection.INPUT, description="정지 버튼"),
        *[
            IOPoint(symbol=s, direction=IODirection.OUTPUT,
                    device_class=DeviceClass.M, description=d)
            for s, _, d in aux
        ],
        IOPoint(symbol=p1, direction=IODirection.OUTPUT, description="교번 1호기"),
        IOPoint(symbol=p2, direction=IODirection.OUTPUT, description="교번 2호기"),
    ]
    derived = [DerivedOutput(output=s, expression=e) for s, e, _ in aux]
    derived += [
        DerivedOutput(output=p1, expression="RUN AND TGL"),
        DerivedOutput(output=p2, expression="RUN AND NOT TGL"),
    ]
    spec = StateMachineSpec(
        title=(frame.text[:40] or "펌프 2대 교번 운전"),
        io_points=io,
        derived_outputs=derived,
        interlocks=[Interlock(output_a=p1, output_b=p2,
                              reason="교번 운전 — 2대 동시 기동 금지")],
    )
    return CompileResult(spec=spec, unresolved=[], confident=frame.confident)


def frame_to_spec(source: IntentFrame | Analysis | str) -> CompileResult:
    """의도 프레임을 검증 가능한 StateMachineSpec 으로 컴파일한다(레시피 비의존).

    순차 마커(다음/N초 후)가 있으면 타임드 시퀀서로, 아니면 조건→자기유지로 컴파일한다.
    """
    frame = (
        source if isinstance(source, IntentFrame)
        else extract(source)
    )
    if any(c.device == "STAR_DELTA" for c in frame.clauses):
        return _compile_star_delta(frame)
    if any(c.device == "ALTERNATE" for c in frame.clauses):
        return _compile_alternator(frame)
    if any(c.seq for c in frame.clauses):
        return _compile_sequence(frame)
    b = _Builder()
    # 출력별 ON/OFF 트리거 수집(삽입순 유지).
    on_trig: dict[str, list[str]] = {}
    off_trig: dict[str, list[str]] = {}
    order: list[str] = []
    pending: list[str | None] = []
    last_action = False
    last_out: str | None = None  # 직전 동작의 출력 — 무주어 동작의 지시 해소(anaphora)
    unresolved: list[str] = []

    for i, c in enumerate(frame.clauses):
        if c.kind == ClauseKind.COND:
            if last_action:
                pending = []
            pending.append(_resolve_cond(c, b))
            last_action = False
        elif _is_button_name(frame.clauses, i):
            continue  # '기동/정지 누르면' — 버튼 라벨이지 동작이 아니다(건너뜀)
        else:  # ACTION
            if not _action_valid(c):
                # 의미 부적합(예: '온도 올려'·'탱크 켜') — 측정/신호 기기는 구동 대상이 아니다.
                dev_ko = c.device or "?"
                unresolved.append(f"'{dev_ko}'는 구동할 수 없는 대상(센서/측정/용기)")
                last_action = True
                continue
            # '동시에 안 *되게*' — 부정 BECOME 은 상호배제 단서 문구의 일부다(동작 아님).
            if c.predicate == "BECOME" and c.negated and _has_mutex_cue(frame.text):
                last_action = True
                continue
            # 무주어 동작('… 꺼'·'멈춰')은 직전 기기를 가리킨다 — 선행 기기가 없으면
            # 유령 출력(OUT)을 지어내지 않고 정직 미해결로 강등한다.
            sym = _out_symbol(c)
            if sym is None:
                sym = last_out
            if sym is None:
                unresolved.append("동작의 대상 기기를 찾지 못함")
                last_action = True
                continue
            out = sym
            last_out = sym
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

    # 명시적 '동시 금지' 단서가 있고 출력이 ≥2면 상호배제로 본다(가드를 식에 박아 검증 통과).
    mutex = _has_mutex_cue(frame.text) and len(order) >= 2
    # 출력별 자기유지 파생식 생성.
    derived: list[DerivedOutput] = []
    built: list[str] = []
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
        built.append(out)
        derived.append(DerivedOutput(output=out, expression=expr))
    if mutex:  # 각 출력식에 '상대 출력 NOT' 가드를 박는다(상호배제 강제 — 검증 통과 보장).
        guarded = {o for o in built}
        for d in derived:
            others = [o for o in guarded if o != d.output]
            if others:
                d.expression = f"({d.expression}) AND NOT ({' OR '.join(others)})"

    io: list[IOPoint] = [
        IOPoint(symbol=s, direction=IODirection.INPUT, data_type=dt)
        for s, dt in b.inputs.items()
    ]
    io += [IOPoint(symbol=o, direction=IODirection.OUTPUT) for o in order]
    interlocks = (
        [Interlock(output_a=a, output_b=bo) for i, a in enumerate(built) for bo in built[i + 1:]]
        if mutex else []
    )
    spec = StateMachineSpec(
        title=(frame.text[:40] or "컴파일된 명세"),
        io_points=io, comparators=b.comparators, counters=b.counters,
        derived_outputs=derived, interlocks=interlocks,
    )
    confident = frame.confident and not unresolved and bool(derived)
    return CompileResult(spec=spec, unresolved=unresolved, confident=confident)


# '동시에 못/안/금지', '같이 …안', '인터락' = 상호배제 의도.
_MUTEX_CUE = ("인터락", "인터록", "동시에 안", "동시에 못", "동시 금지", "동시에 금지", "같이 안")


def _has_mutex_cue(text: str) -> bool:
    t = text.replace(" ", "")
    return any(cue.replace(" ", "") in t for cue in _MUTEX_CUE)
