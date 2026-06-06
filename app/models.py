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
    enable_condition: str = Field(
        default="", description="타이머 IN(인에이블) 불리언식 (예: 'MOTOR_RUN')"
    )
    description: str = ""

    @property
    def done_ref(self) -> str:
        """다운스트림에서 참조할 완료비트 (예: 'T1.Q')."""
        return f"{self.name}.Q"


class CounterSpec(BaseModel):
    name: str
    counter_type: CounterType = CounterType.CTU
    preset: int = Field(..., ge=0)
    count_condition: str = Field(default="", description="CU(증가) 펄스 불리언식")
    reset_condition: str = Field(default="", description="R(리셋) 불리언식")
    description: str = ""

    @property
    def done_ref(self) -> str:
        """완료비트 참조 (CV >= PV), 예: 'C1.Q'."""
        return f"{self.name}.Q"


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


class DerivedOutput(BaseModel):
    """on_entry 로 구동되지 않는 조합(파생) 출력.

    예: 경음기 ``HORN := (LATCH_A OR LATCH_B) AND NOT ALM_ACK``.
    expression 은 boolexpr 가 파싱 가능한 불리언식(AND/OR/NOT/괄호/심볼).
    이 필드 덕분에 합성기가 상태구동이 아닌 출력도 결정론적으로 덮을 수 있다.
    """

    output: str
    expression: str = Field(..., description="불리언식 RHS (예: '(A OR B) AND NOT C')")
    description: str = ""


class StateMachineSpec(BaseModel):
    """analyst(A1) 산출물 — 전체 상태머신 명세."""

    title: str = ""
    io_points: list[IOPoint] = Field(default_factory=list)
    timers: list[TimerSpec] = Field(default_factory=list)
    counters: list[CounterSpec] = Field(default_factory=list)
    states: list[SfcState] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)
    interlocks: list[Interlock] = Field(default_factory=list)
    derived_outputs: list[DerivedOutput] = Field(
        default_factory=list,
        description="상태구동이 아닌 조합 출력(예: 알람 경음기)을 불리언식으로 정의",
    )


# ---------------------------------------------------------------------------
# 프로젝트 합성 (다중 서브시스템 → 하나의 명세)
# ---------------------------------------------------------------------------
class ModuleInstance(BaseModel):
    """프로젝트 안의 서브시스템 인스턴스 1개.

    한 레시피(recipe)를 answers 로 파라미터화해 만든 명세를, ``name`` 네임스페이스로
    감싸 전역 프로젝트에 합성한다. 같은 레시피를 이름만 달리해 여러 번 인스턴스화하면
    (예: conv1/conv2/conv3) 주소·심볼 충돌 없이 나란히 놓인다.

    shared: 이 모듈의 *로컬 심볼* → *프로젝트 전역 심볼* 매핑. 여기 들어간 심볼은
    네임스페이스 프리픽스를 붙이지 않고 전역 이름으로 공유된다(예: 공통 비상정지
    ``{"ESTOP": "MASTER_ESTOP"}``). 주로 공유 입력에 쓴다 — 공유 출력에 두 모듈이
    대입하면 검증기가 이중코일로 잡는다(은닉 병합 금지).
    """

    name: str = Field(..., description="모듈 인스턴스 이름(네임스페이스, 예: conv1)")
    recipe: str = Field(..., description="레시피 id (wizard.RECIPES 의 키)")
    answers: dict[str, str] = Field(default_factory=dict, description="레시피 빈칸 답변")
    shared: dict[str, str] = Field(
        default_factory=dict, description="로컬 심볼→전역 공유 심볼(프리픽스 면제)"
    )


class CrossInterlock(BaseModel):
    """서브시스템 *사이* 의 상호배타. 예: 탱크A 배출 중엔 펌프2 금지.

    출력 참조는 ``"모듈이름.로컬심볼"`` 형식(예: ``"pump2.MOTOR"``) 또는 공유 전역
    심볼(점 없음)을 쓴다. 합성 시 실제 렌더 심볼로 해석돼 spec.interlocks 에 합쳐진다.
    """

    output_a: str = Field(..., description="'모듈.심볼' 또는 공유 심볼")
    output_b: str = Field(..., description="'모듈.심볼' 또는 공유 심볼")
    reason: str = Field(default="", description="교차 인터락 사유")


class Project(BaseModel):
    """대규모 설계 단위 — 서브시스템 N개를 하나의 프로그램으로 합성하는 명세."""

    title: str = ""
    modules: list[ModuleInstance] = Field(default_factory=list)
    cross_interlocks: list[CrossInterlock] = Field(default_factory=list)


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
