"""명세 → 3D 가상 공장 설비 레이아웃 컴파일러 (결정론, 키 불필요).

검증된 StateMachineSpec 의 입출력·비교기를 *설비 배치도*로 컴파일한다:
기기 종류(모터/펌프/밸브/히터/컨베이어/경광등…)를 심볼에서 추론하고, 공장 바닥
그리드 위 결정론 좌표에 배치하며, 수위 신호가 있으면 탱크를, 아날로그 비교기는
계기(게이지)를 세운다. 프론트(plant3d.js)가 이 레이아웃을 Three.js 3D 공장으로
렌더하고, 검증된 ST 스캔 루프(SimEngine)와 동기해 실시간 가동한다.

좌표계: x=가로(기기 나열), z=세로(열: 계기/탱크 -2.6 · 구동기 0 · 조작반 +2.8), y=높이.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

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


class PlantDevice(BaseModel):
    """공장 바닥 위 기기 1대 — 심볼·종류·위치·한국어 라벨."""

    symbol: str
    kind: str
    role: str = Field(..., description="output | input | gauge | tank")
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    label: str = ""
    # gauge: 임계값 목록(표시용) / tank: 채우는 기기 심볼(수위 연출용)
    thresholds: list[float] = Field(default_factory=list)
    fed_by: list[str] = Field(default_factory=list)


class PlantLayout(BaseModel):
    """3D 가상 공장 설비 배치도 — 결정론 좌표·종류·연결."""

    devices: list[PlantDevice] = Field(default_factory=list)
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


def plant_from_spec(spec: StateMachineSpec) -> PlantLayout:
    """검증 가능한 명세를 3D 설비 배치도로 컴파일한다(같은 명세 → 같은 배치)."""
    outs = [p.symbol for p in spec.io_points if p.direction == IODirection.OUTPUT]
    ins = [p.symbol for p in spec.io_points if p.direction == IODirection.INPUT]
    devices: list[PlantDevice] = []

    # 구동기 열(중앙) — 모터·펌프·밸브…
    for x, sym in zip(_centered_xs(len(outs), _SPACING_OUT), outs, strict=True):
        kind = output_kind(sym)
        devices.append(PlantDevice(
            symbol=sym, kind=kind, role="output", x=x, z=_ROW_OUT,
            label=_label(kind, sym),
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
            label=_KIND_KO["tank"], fed_by=feeders,
        ))
        bi += 1
    for sig in gauge_syms:
        devices.append(PlantDevice(
            symbol=sig, kind="gauge", role="gauge", x=back_xs[bi], z=_ROW_GAUGE,
            label=_label("gauge", sig), thresholds=sorted(signals[sig]),
        ))
        bi += 1

    # 조작반 열(앞) — 버튼·센서 스위치. 아날로그 신호는 이미 계기로 섰으니 중복 제외.
    ins = [s for s in ins if s not in signals]
    for x, sym in zip(_centered_xs(len(ins), _SPACING_IN), ins, strict=True):
        kind = input_kind(sym)
        devices.append(PlantDevice(
            symbol=sym, kind=kind, role="input", x=x, z=_ROW_IN,
            label=_label(kind, sym),
        ))

    span_x = max(
        [abs(d.x) for d in devices] or [0.0]
    ) * 2 + 4.0
    return PlantLayout(
        devices=devices,
        floor_w=max(10.0, span_x),
        floor_d=10.0,
        title=spec.title,
    )
