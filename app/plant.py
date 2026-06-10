"""명세 → 공장 설비 설계(CAD 도면·3D) 컴파일러 (결정론, 키 불필요).

검증된 StateMachineSpec 의 입출력·비교기를 *설비 설계도*로 컴파일한다:
기기 종류(모터/펌프/밸브/히터/컨베이어/경광등…)를 심볼에서 추론하고, 결정론 좌표에
배치하며, 수위 신호가 있으면 탱크를, 아날로그 비교기는 계기(트랜스미터)를 세운다.
설계 세분화를 위해 기기마다 **CAD 태그번호**(P-101/TK-101/PT-101, KS/ISA 계열),
**부품 명세(BOM)**, **PLC 디바이스 주소**(LS P/M/T/C), **배관·신호 연결**을 함께
컴파일한다. 프론트는 이것으로 P&ID 풍 CAD 도면(blueprint.js)과 3D(plant3d.js)를
그리고, 검증된 ST 스캔 루프(SimEngine)와 동기해 실가동·클릭 정밀테스트한다.

좌표계: x=가로(기기 나열), z=세로(열: 계기/탱크 -2.6 · 구동기 0 · 조작반 +2.8), y=높이.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.memory_map import DeviceAllocator
from app.models import IODirection, StateMachineSpec

# 출력 심볼 접두 → 기기 종류 (앞에서부터 최장일치, 결정론 순서)
_OUT_KINDS: tuple[tuple[str, str], ...] = (
    ("CONVEYOR", "conveyor"), ("CONV", "conveyor"),
    ("COMPRESSOR", "pump"), ("VACUUM", "pump"), ("PUMP", "pump"),
    ("MOTOR", "motor"), ("DRILL", "motor"), ("MIXER", "mixer"), ("AGITATOR", "mixer"),
    ("VALVE", "valve"), ("SOL", "valve"),
    ("HEATER", "heater"), ("WELDER", "heater"),
    ("COOLER", "cooler"), ("FAN", "fan"), ("BLOWER", "fan"),
    ("BEACON", "beacon"), ("LAMP", "beacon"), ("LIGHT", "beacon"),
    ("ALARM", "beacon"), ("BUZZER", "beacon"), ("SIREN", "beacon"),
    ("EJECT", "ejector"), ("PUSHER", "ejector"), ("CYL", "ejector"),
    ("GATE", "gate"), ("DOOR", "gate"),
)

# 입력 심볼 단서 → 기기 종류
_ESTOP_CUES = ("ESTOP", "EMG", "EMERGENCY")
_BUTTON_CUES = ("START", "STOP", "BTN", "BUTTON", "SW", "RESET", "RUN")
_FAULT_CUES = ("FAULT", "ERROR", "ERR", "FLT", "TRIP", "OVERLOAD")
_LEVEL_CUES = ("_LS", "LEVEL", "LO_", "HI_", "FLOAT")

_KIND_KO: dict[str, str] = {
    "motor": "모터", "pump": "펌프", "valve": "밸브", "heater": "히터",
    "cooler": "쿨러", "fan": "팬", "conveyor": "컨베이어", "beacon": "경광등",
    "ejector": "배출기", "gate": "게이트", "mixer": "믹서", "actuator": "구동기",
    "button": "버튼", "estop": "비상정지", "level": "수위센서", "fault": "고장신호",
    "sensor": "센서", "gauge": "계기", "tank": "탱크",
}

_SPACING_OUT = 2.4   # 구동기 간격(m)
_SPACING_IN = 1.5    # 조작반 간격(m)
_ROW_GAUGE = -2.6
_ROW_OUT = 0.0
_ROW_IN = 2.8

# CAD 태그 접두(KS/ISA 계열) — 종류별 일련번호 101부터.
_TAG_PREFIX: dict[str, str] = {
    "motor": "M", "pump": "P", "valve": "XV", "heater": "H", "cooler": "F",
    "fan": "F", "conveyor": "CV", "beacon": "XL", "ejector": "CY", "gate": "GT",
    "mixer": "MX", "actuator": "A", "tank": "TK",
    "button": "HS", "estop": "ES", "level": "LSH", "fault": "XA", "sensor": "XS",
}
_GAUGE_TAG = {"PRESSURE": "PT", "TEMP": "TT", "LEVEL": "LT", "FLOW": "FT"}

# 기기 종류별 부품 명세(BOM) — 설계 세분화의 결정론 기본값(현장 표준 구성).
# 전동기 계열은 동력 회로 전 체인(MCCB→인버터→MC→EOCR)을 갖춰 제어반 단선도의
# 단일 원천이 된다(프론트 panel.js 가 이 BOM 으로 분기 회로를 그린다).
_MOTOR_POWER_CHAIN = ["배선용차단기(MCCB)", "인버터(VFD)", "전자접촉기(MC)", "열동계전기(EOCR)"]
_BOM: dict[str, list[str]] = {
    "motor": ["3상 유도전동기", *_MOTOR_POWER_CHAIN],
    "pump": ["원심펌프", *_MOTOR_POWER_CHAIN, "메커니컬 씰", "체크밸브"],
    "valve": ["솔레노이드 밸브(2포트)", "배선용차단기(MCB)", "구동 릴레이", "개도 리밋스위치"],
    "heater": [
        "시즈히터", "배선용차단기(MCCB)", "전자접촉기(MC)", "SSR 릴레이", "과열방지 서모스탯",
    ],
    "cooler": ["축류팬", *_MOTOR_POWER_CHAIN, "방진 마운트"],
    "fan": ["축류팬", *_MOTOR_POWER_CHAIN, "방진 마운트"],
    "conveyor": ["기어드모터", *_MOTOR_POWER_CHAIN, "구동/종동 롤러", "벨트"],
    "beacon": ["LED 경광등", "배선용차단기(MCB)", "구동 릴레이", "부저"],
    "ejector": [
        "공압 실린더", "배선용차단기(MCB)", "5포트 솔밸브", "스피드 컨트롤러", "리드 스위치 2점",
    ],
    "gate": ["공압 실린더", "배선용차단기(MCB)", "구동 릴레이", "가이드 레일", "리밋 스위치 2점"],
    "mixer": ["교반 전동기", *_MOTOR_POWER_CHAIN, "감속기", "임펠러"],
    "actuator": ["범용 액추에이터", "배선용차단기(MCB)", "구동 릴레이"],
    "tank": ["저장탱크(SUS304)", "레벨 스위치 2점", "드레인 밸브", "오버플로 배관"],
    "gauge": ["트랜스미터(4-20mA)", "신호 변환기", "게이지 콕"],
    "button": ["푸시버튼(1a)", "단자대"],
    "estop": ["비상정지 푸시버튼(머시룸·1b)", "안전릴레이"],
    "level": ["플로트 레벨스위치", "단자대"],
    "fault": ["고장 알람 접점", "단자대"],
    "sensor": ["근접센서(PNP)", "센서 브래킷", "단자대"],
}


class PlantDevice(BaseModel):
    """설비 1대 — 심볼·종류·위치·CAD 태그·부품(BOM)·PLC 주소."""

    symbol: str
    kind: str
    role: str = Field(..., description="output | input | gauge | tank")
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    label: str = ""
    tag: str = ""        # CAD 도면 태그번호 (P-101, TK-101, PT-101 …)
    address: str = ""    # PLC 디바이스 주소 (LS P/M/T/C — IO 가 아니면 빈 값)
    parts: list[str] = Field(default_factory=list)  # 부품 명세(BOM, 설계 세분화)
    # gauge: 임계값 목록(표시용) / tank: 채우는 기기 심볼(수위 연출용)
    thresholds: list[float] = Field(default_factory=list)
    fed_by: list[str] = Field(default_factory=list)


class PlantConnection(BaseModel):
    """설비 간 연결 — 배관(pipe: 펌프→탱크) 또는 제어 신호(signal: 기기↔PLC)."""

    src: str
    dst: str
    kind: str = Field(..., description="pipe | signal")


class PlantLayout(BaseModel):
    """공장 설비 설계도 — 결정론 좌표·종류·태그·BOM·주소·연결(CAD/3D 공용)."""

    devices: list[PlantDevice] = Field(default_factory=list)
    connections: list[PlantConnection] = Field(default_factory=list)
    floor_w: float = 10.0
    floor_d: float = 10.0
    title: str = ""


def output_kind(symbol: str) -> str:
    """출력 심볼 → 기기 종류(접두 최장일치, 미지정은 actuator)."""
    s = symbol.upper()
    for prefix, kind in _OUT_KINDS:
        if s.startswith(prefix):
            return kind
    return "actuator"


def input_kind(symbol: str) -> str:
    """입력 심볼 → 센서/버튼 종류(비상정지 > 버튼 > 고장 > 수위 > 센서)."""
    s = symbol.upper()
    if any(c in s for c in _ESTOP_CUES):
        return "estop"
    if any(c in s for c in _BUTTON_CUES):
        return "button"
    if any(c in s for c in _FAULT_CUES):
        return "fault"
    if any(c in s for c in _LEVEL_CUES):
        return "level"
    return "sensor"


def _label(kind: str, symbol: str) -> str:
    return f"{_KIND_KO.get(kind, kind)} {symbol}"


def _centered_xs(n: int, spacing: float) -> list[float]:
    return [(i - (n - 1) / 2) * spacing for i in range(n)]


class _TagCounter:
    """종류별 일련 태그(P-101, P-102…) — 결정론(부여 순서 = 배치 순서)."""

    def __init__(self) -> None:
        self._n: dict[str, int] = {}

    def take(self, prefix: str) -> str:
        self._n[prefix] = self._n.get(prefix, 0) + 1
        return f"{prefix}-{100 + self._n[prefix]}"


def plant_from_spec(spec: StateMachineSpec) -> PlantLayout:
    """검증 가능한 명세를 설비 설계도로 컴파일한다(같은 명세 → 같은 설계).

    태그·BOM·PLC 주소·배관/신호 연결까지 함께 — 도면(CAD)·3D·정밀테스트의 단일 원천.
    """
    outs = [p.symbol for p in spec.io_points if p.direction == IODirection.OUTPUT]
    ins = [p.symbol for p in spec.io_points if p.direction == IODirection.INPUT]
    devices: list[PlantDevice] = []
    tags = _TagCounter()
    try:
        alloc: DeviceAllocator | None = DeviceAllocator().build_from_spec(spec)
    except ValueError:
        alloc = None  # 주소 충돌 등 — 설계도는 주소 없이도 선다

    def addr(sym: str) -> str:
        if alloc is None:
            return ""
        return alloc.address_of(sym) or ""

    # 구동기 열(중앙) — 모터·펌프·밸브…
    for x, sym in zip(_centered_xs(len(outs), _SPACING_OUT), outs, strict=True):
        kind = output_kind(sym)
        devices.append(PlantDevice(
            symbol=sym, kind=kind, role="output", x=x, z=_ROW_OUT,
            label=_label(kind, sym), tag=tags.take(_TAG_PREFIX.get(kind, "A")),
            address=addr(sym), parts=list(_BOM.get(kind, [])),
        ))

    # 계기 열(뒤) — 아날로그 비교기 신호별 게이지(임계값 함께)
    signals: dict[str, list[float]] = {}
    for c in spec.comparators:
        signals.setdefault(c.signal, []).append(float(c.threshold))
    gauge_syms = sorted(signals)
    # 수위 단서(수위센서 입력 or LEVEL 신호) → 탱크 1기 (펌프/밸브가 채움)
    has_level = any(input_kind(s) == "level" for s in ins) or any(
        s.upper().startswith("LEVEL") for s in gauge_syms
    )
    back_count = len(gauge_syms) + (1 if has_level else 0)
    back_xs = _centered_xs(back_count, _SPACING_OUT)
    bi = 0
    if has_level:
        feeders = [d.symbol for d in devices if d.kind in ("pump", "valve")]
        devices.append(PlantDevice(
            symbol="TANK", kind="tank", role="tank", x=back_xs[bi], z=_ROW_GAUGE,
            label=_KIND_KO["tank"], tag=tags.take(_TAG_PREFIX["tank"]),
            parts=list(_BOM["tank"]), fed_by=feeders,
        ))
        bi += 1
    for sig in gauge_syms:
        prefix = next(
            (t for k, t in _GAUGE_TAG.items() if sig.upper().startswith(k)), "AT"
        )
        devices.append(PlantDevice(
            symbol=sig, kind="gauge", role="gauge", x=back_xs[bi], z=_ROW_GAUGE,
            label=_label("gauge", sig), tag=tags.take(prefix),
            address=addr(sig), parts=list(_BOM["gauge"]),
            thresholds=sorted(signals[sig]),
        ))
        bi += 1

    # 조작반 열(앞) — 버튼·센서 스위치. 아날로그 신호는 이미 계기로 섰으니 중복 제외.
    ins = [s for s in ins if s not in signals]
    for x, sym in zip(_centered_xs(len(ins), _SPACING_IN), ins, strict=True):
        kind = input_kind(sym)
        devices.append(PlantDevice(
            symbol=sym, kind=kind, role="input", x=x, z=_ROW_IN,
            label=_label(kind, sym), tag=tags.take(_TAG_PREFIX.get(kind, "XS")),
            address=addr(sym), parts=list(_BOM.get(kind, [])),
        ))

    # 연결 컴파일 — 배관(공급기→탱크), 제어 신호(입력/계기→PLC, PLC→구동기).
    conns: list[PlantConnection] = []
    for d in devices:
        if d.role == "tank":
            conns += [PlantConnection(src=f, dst=d.symbol, kind="pipe") for f in d.fed_by]
        elif d.role == "output":
            conns.append(PlantConnection(src="PLC", dst=d.symbol, kind="signal"))
        else:  # input/gauge → PLC
            conns.append(PlantConnection(src=d.symbol, dst="PLC", kind="signal"))

    span_x = max(
        [abs(d.x) for d in devices] or [0.0]
    ) * 2 + 4.0
    return PlantLayout(
        devices=devices,
        connections=conns,
        floor_w=max(10.0, span_x),
        floor_d=10.0,
        title=spec.title,
    )
