"""의도 프레임 추출 — 한국어 형태소 분석 → 구조적 제어 의도 (설명가능·결정론).

korean.analyze 의 형태소 열을 받아, 한국어 SOV·조건절(-면) 문법에 따라 절(clause)을
나누고 **(조건 → 동작·대상·극성·수량)** 의도 프레임으로 구조화한다. AI/LLM 없이 "무슨
지시인지"를 *설명 가능하게* 알아내고, 파스 커버리지로 *보정된 확신도*를 낸다.

핵심: 인식 못 한 형태소는 coverage 를 떨어뜨려 확신을 낮춘다 → 거짓 이해를 막는다.
이해 결과(IntentFrame)는 상위에서 레시피 매핑·확신 강등의 *설명가능한 근거*가 된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.korean import Analysis, Pos, Role, analyze

# 동작(액추에이터) vs 트리거(센서/상태) 의미범주 — 설명·매핑 시 역할 구분.
_ACTUATOR = {"RUN", "STOP", "TURN_ON", "TURN_OFF", "OPEN", "CLOSE", "EJECT"}
_TRIGGER_PRED = {"PRESS", "DETECT", "FILL", "EXCEED", "BECOME", "COUNT"}

# 의미범주 → 한국어 설명 라벨(이해 내용을 사람에게 보여줄 때).
_PRED_KO: dict[str, str] = {
    "RUN": "가동", "STOP": "정지", "TURN_ON": "켬", "TURN_OFF": "끔",
    "OPEN": "열기", "CLOSE": "닫기", "EJECT": "배출", "PRESS": "누름",
    "DETECT": "감지", "FILL": "참", "EXCEED": "초과", "BECOME": "도달", "COUNT": "계수",
}
_DEV_KO: dict[str, str] = {
    "MOTOR": "모터", "PUMP": "펌프", "VALVE": "밸브", "CONVEYOR": "컨베이어",
    "LAMP": "램프", "BEACON": "경광등", "BUTTON": "버튼", "SENSOR": "센서",
    "HEATER": "히터", "TANK": "탱크", "GATE": "게이트", "SHUTTER": "셔터",
    "PART": "부품", "PRESSURE": "압력", "TEMP": "온도", "LEVEL": "수위",
    "LEVEL_LO": "저수위", "LEVEL_HI": "고수위", "FAULT": "고장", "VALVE2": "밸브",
    "ALARM": "알람", "CYLINDER": "실린더", "COUNTER": "카운터", "TIMER": "타이머",
    "SWITCH": "스위치",
}


class ClauseKind:
    COND = "COND"      # 조건(트리거) — '-면'
    ACTION = "ACTION"  # 동작 — 출력 구동


@dataclass(frozen=True)
class IntentClause:
    kind: str               # COND | ACTION
    predicate: str          # 의미범주(RUN/STOP/EXCEED ...)
    device: str | None      # 대상 기기 카테고리
    negated: bool = False
    value: int | None = None
    unit: str = ""          # 분류사(개/초/바 ...)

    def explain(self) -> str:
        dev = _DEV_KO.get(self.device or "", self.device or "")
        pred = _PRED_KO.get(self.predicate, self.predicate)
        qty = f" {self.value}{self.unit}" if self.value is not None else ""
        neg = "안/못 " if self.negated else ""
        head = "조건" if self.kind == ClauseKind.COND else "동작"
        body = f"{dev}{qty} {neg}{pred}".strip()
        return f"{head}: {body}"


@dataclass
class IntentFrame:
    text: str
    clauses: list[IntentClause] = field(default_factory=list)
    coverage: float = 0.0

    @property
    def actions(self) -> list[IntentClause]:
        return [c for c in self.clauses if c.kind == ClauseKind.ACTION]

    @property
    def conditions(self) -> list[IntentClause]:
        return [c for c in self.clauses if c.kind == ClauseKind.COND]

    @property
    def certainty(self) -> float:
        """설명가능 확신도: 동작이 하나도 없으면 0(명령 아님). 그 외 coverage 기반."""
        if not self.actions:
            return 0.0
        return round(self.coverage, 2)

    @property
    def confident(self) -> bool:
        return self.certainty >= 0.8 and bool(self.actions)

    def explain(self) -> str:
        """사람이 읽는 '이해 내용' — 무엇을 지시한 것으로 이해했는지 설명가능하게."""
        if not self.clauses:
            return "이해한 지시가 없습니다."
        return " / ".join(c.explain() for c in self.clauses)


def extract(source: Analysis | str) -> IntentFrame:
    """형태소 분석(또는 원문) → 의도 프레임. 한국어 SOV·조건절 문법으로 절을 나눈다.

    버퍼링: 용언이 나오기 전의 체언(기기)·수량을 모았다가, 용언을 만나면 한 절을 닫는다
    (한국어는 목적어가 동사 앞 — SOV). 용언의 조건(-면) 여부로 COND/ACTION 을 가른다.
    """
    a = source if isinstance(source, Analysis) else analyze(source)
    clauses: list[IntentClause] = []
    dev: str | None = None
    val: int | None = None
    unit = ""
    for m in a.morphemes:
        if m.pos == Pos.NOUN:
            # 대상 후보(목적격 우선, 아니면 최근 체언). 상태성 체언(저수위 등)도 대상.
            if dev is None or m.role == Role.OBJ:
                dev = m.category
        elif m.pos == Pos.NUM:
            val, unit = m.value, m.category
        elif m.pos == Pos.VERB:
            kind = ClauseKind.COND if m.is_condition else ClauseKind.ACTION
            clauses.append(IntentClause(
                kind=kind, predicate=m.category, device=dev,
                negated=m.negated, value=val, unit=unit,
            ))
            dev, val, unit = None, None, ""  # 버퍼 소비
    return IntentFrame(text=a.text, clauses=clauses, coverage=a.coverage)
