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
    power_kw: float | None = Field(
        default=None, description="전동기 정격출력(kW) — 차단기/접촉기/EOCR 산식 선정의 입력"
    )


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


class CompareOp(StrEnum):
    """아날로그 비교 연산자(IEC 61131-3 ST 표기)."""

    GT = ">"
    GE = ">="
    LT = "<"
    LE = "<="
    EQ = "="
    NE = "<>"


class Comparator(BaseModel):
    """아날로그 신호(REAL/INT) 비교로 BOOL 플래그를 만드는 비교기.

    ``flag := signal op threshold`` 의 불리언 플래그를 산출한다. 정형검증(Z3)은 플래그를
    *원자 불리언* 으로 취급한다 — 산술을 모델링하지 않으므로 인터락 증명은 보수적·건전하다.
    hysteresis 가 있으면 밴드 SR 래치로 합성한다(예: 5바에서 ON, 3바에서 OFF). 이로써
    압력/온도/수위 *설정값* 같은 아날로그 임계를 IEC 표준으로 표현한다(불리언 밖→안).
    """

    flag: str = Field(..., description="산출 BOOL 플래그 심볼")
    signal: str = Field(..., description="비교 대상 아날로그 입력 심볼(REAL/INT)")
    op: CompareOp = CompareOp.GE
    threshold: float = Field(..., description="비교 임계값(리터럴)")
    hysteresis: float | None = Field(
        default=None,
        description="밴드 폭(있으면 SR 히스테리시스). GT/GE 는 threshold-h 에서, "
        "LT/LE 는 threshold+h 에서 해제된다. 0 또는 None 이면 단순 비교.",
    )
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
    comparators: list[Comparator] = Field(
        default_factory=list,
        description="아날로그 신호 비교 → BOOL 플래그(압력/온도/수위 설정값). "
        "플래그는 transitions/derived/interlocks 에서 원자 불리언으로 참조된다.",
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
    recipe: str = Field(default="", description="레시피 id(wizard.RECIPES). spec 을 주면 무시")
    answers: dict[str, str] = Field(default_factory=dict, description="레시피 빈칸 답변")
    spec: StateMachineSpec | None = Field(
        default=None,
        description="레시피 대신 직접 주는 명세(LLM 설계 산출물 등). 있으면 recipe 무시 — "
        "32개 템플릿을 넘어 임의 로직을 합성 파이프라인에 태우는 일반 IR 경로.",
    )
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
# LLM 설계 에이전트 산출물 — 자유 한국어 문단 → 다중 서브시스템 분해(템플릿 不제약)
# ---------------------------------------------------------------------------
class PlannedModule(BaseModel):
    """설계 에이전트가 만든 모듈 1개 — 이름 + (템플릿이 아닌) 직접 명세."""

    name: str = Field(..., description="모듈 이름(영문 식별자, 예: conv1/tankA)")
    spec: StateMachineSpec = Field(..., description="이 서브시스템의 상태머신 명세")


class ProjectPlan(BaseModel):
    """LLM 설계 에이전트의 구조화 출력 — 복합 요구를 서브시스템들로 분해한 계획.

    각 모듈은 32개 템플릿에 묶이지 않은 임의 명세를 가지며, 모듈 사이 상호배타는
    cross_interlocks 로 선언한다. 이 계획은 ``app.design`` 에서 ``Project`` 로 변환돼
    결정론 합성·검증 파이프라인(compose→verify)을 그대로 탄다(LLM 생성 / 코어 검증).
    """

    title: str = ""
    modules: list[PlannedModule] = Field(default_factory=list)
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
