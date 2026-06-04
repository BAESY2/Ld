"""파이프라인 공유 Pydantic 데이터 계약.

흐름:
  자연어 → StateMachineSpec (analyst, A1)
         → ST 코드 + DeviceAllocator (architect, A3)
         → VerificationReport (verifier)
         → LadderProgram (renderer, A4)

래더 스키마는 1차로 Sum-of-Products(직렬 안의 병렬)로 한정한다.
다중 중첩 브랜치(재귀 모델)는 Phase H2에서 확장한다.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 열거형
# ---------------------------------------------------------------------------
class DataType(StrEnum):
    """IEC 61131-3 표준 타입."""

    BOOL = "BOOL"
    INT = "INT"
    DINT = "DINT"
    REAL = "REAL"
    TIME = "TIME"
    WORD = "WORD"


class DeviceClass(StrEnum):
    """LS 체계 디바이스 클래스."""

    P = "P"  # 입출력
    M = "M"  # 내부 릴레이
    T = "T"  # 타이머
    C = "C"  # 카운터
    D = "D"  # 데이터
    L = "L"  # 링크 릴레이
    K = "K"  # 킵 릴레이


class IODirection(StrEnum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"


class TimerType(StrEnum):
    TON = "TON"  # On-delay
    TOF = "TOF"  # Off-delay
    TP = "TP"  # Pulse


class CounterType(StrEnum):
    CTU = "CTU"  # Up
    CTD = "CTD"  # Down
    CTUD = "CTUD"  # Up/Down


class ElementType(StrEnum):
    """래더 접점/코일 요소 종류."""

    CONTACT_NO = "CONTACT_NO"  # 평상시 열린 접점 (-| |-)
    CONTACT_NC = "CONTACT_NC"  # 평상시 닫힌 접점 (-|/|-)
    COIL = "COIL"  # 출력 코일 (-( )-)
    COIL_SET = "COIL_SET"  # 셋 코일 (-(S)-)
    COIL_RESET = "COIL_RESET"  # 리셋 코일 (-(R)-)
    TIMER = "TIMER"
    COUNTER = "COUNTER"


# ---------------------------------------------------------------------------
# A1 산출물: StateMachineSpec
# ---------------------------------------------------------------------------
class IOPoint(BaseModel):
    """입출력 한 점."""

    symbol: str = Field(..., description="심볼명 (예: START_PB)")
    direction: IODirection
    data_type: DataType = DataType.BOOL
    device_class: DeviceClass = DeviceClass.P
    description: str = ""
    fixed_address: str | None = Field(default=None, description="고정 주소 (예: P0001)")


class TimerSpec(BaseModel):
    name: str
    timer_type: TimerType = TimerType.TON
    preset_ms: int = Field(..., ge=0, description="프리셋 시간(ms)")
    description: str = ""


class CounterSpec(BaseModel):
    name: str
    counter_type: CounterType = CounterType.CTU
    preset: int = Field(..., ge=0)
    description: str = ""


class Transition(BaseModel):
    """상태 전이."""

    from_state: str
    to_state: str
    condition: str = Field(..., description="불리언식 (예: START_PB AND NOT STOP_PB)")
    description: str = ""


class SfcState(BaseModel):
    """SFC 상태(스텝)."""

    name: str
    is_initial: bool = False
    on_entry: list[str] = Field(
        default_factory=list,
        description="진입 시 동작 ST 문장 목록 (예: ['MOTOR_FWD := TRUE;'])",
    )
    description: str = ""


class Interlock(BaseModel):
    """상호배타(동시에 켜지면 안 되는) 출력 쌍."""

    output_a: str
    output_b: str
    reason: str = Field(default="", description="인터락 사유 (예: 정/역 동시 구동 금지)")


class StateMachineSpec(BaseModel):
    """analyst(A1) 산출물 — 전체 상태머신 명세."""

    title: str = ""
    io_points: list[IOPoint] = Field(default_factory=list)
    timers: list[TimerSpec] = Field(default_factory=list)
    counters: list[CounterSpec] = Field(default_factory=list)
    states: list[SfcState] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)
    interlocks: list[Interlock] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# A3 산출물: VerificationReport
# ---------------------------------------------------------------------------
class VerificationIssue(BaseModel):
    code: str = Field(..., description="이슈 코드 (예: DOUBLE_COIL, INTERLOCK, DEADLOCK)")
    severity: str = Field(..., description="error | warning")
    message: str
    counterexample: str = Field(default="", description="Z3 반례 등")


class VerificationReport(BaseModel):
    passed: bool = True
    issues: list[VerificationIssue] = Field(default_factory=list)
    suggested_fix: str = Field(default="", description="한글 수정 제안 (피드백 루프용)")

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)


# ---------------------------------------------------------------------------
# A4 산출물: LadderProgram (Sum-of-Products)
# ---------------------------------------------------------------------------
class LadderElement(BaseModel):
    """접점/코일 한 요소."""

    element_type: ElementType
    symbol: str
    address: str = ""
    description: str = ""


class LadderBranch(BaseModel):
    """직렬(AND) 요소들의 묶음 — input_branches 안에서 OR 된다."""

    elements: list[LadderElement] = Field(default_factory=list)


class LadderRung(BaseModel):
    """렁(가로줄). input_branches(OR) → outputs(코일).

    각 branch 내부 elements 는 AND(직렬). branch 간은 OR(병렬). = Sum-of-Products.
    """

    comment: str = ""
    input_branches: list[LadderBranch] = Field(default_factory=list)
    outputs: list[LadderElement] = Field(default_factory=list)


class LadderProgram(BaseModel):
    """renderer(A4) 산출물 — 래더 전체."""

    title: str = ""
    rungs: list[LadderRung] = Field(default_factory=list)
