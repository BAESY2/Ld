"""결정론 한국어 형태소·구문 분석 엔진 (AI/LLM 없이 산업 제어 지시 이해).

발명의 핵심: BM25 '키워드 겹침'이 아니라 *실제 한국어 문법*(한글 자모·조사·어미·용언
활용)으로 제어 지시를 구조적으로 분석한다. "돌리고/돌면/돌려/돌게"가 모두 동작 RUN 임을,
"모터를/모터가/모터는"이 각각 목적격/주격/주제격임을 *문법적으로* 안다.

설계 원칙
---------
* 도메인 한정(산업 제어 어휘) — 범용 한국어 NLP 가 아니라 *제어 의도*에 정밀한 규칙 엔진.
* 100% 결정론·키 불필요·환각 0. 분석은 '소비한 형태소'를 남겨 *설명 가능*하다.
* 한글 음절은 유니코드 산술로 자모 분해(0xAC00 기반) — 받침 유무로 조사 이형태를 가른다.

이 모듈은 형태소 *분석*까지 책임진다. 절(clause)·의도 프레임 추출과 레시피 매핑은
상위 계층(다음 단계)에서 이 분석 결과를 소비한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# ---------------------------------------------------------------------------
# 1. 한글 자모 산술 (받침 판정 = 조사 이형태 선택의 근거)
# ---------------------------------------------------------------------------
_HANGUL_BASE = 0xAC00  # '가'
_HANGUL_LAST = 0xD7A3  # '힣'
_LEAD = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
_VOWEL = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")
_TAIL = ["", *list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")]


def is_hangul_syllable(ch: str) -> bool:
    return len(ch) == 1 and _HANGUL_BASE <= ord(ch) <= _HANGUL_LAST


def decompose(ch: str) -> tuple[str, str, str] | None:
    """한글 음절 → (초성, 중성, 종성). 종성 없으면 ''. 음절이 아니면 None."""
    if not is_hangul_syllable(ch):
        return None
    idx = ord(ch) - _HANGUL_BASE
    lead, rem = divmod(idx, 588)
    vowel, tail = divmod(rem, 28)
    return _LEAD[lead], _VOWEL[vowel], _TAIL[tail]


def has_batchim(word: str) -> bool:
    """단어의 *마지막 음절*에 받침(종성)이 있는가. 조사 이형태(을/를·이/가) 판정의 핵심."""
    if not word:
        return False
    d = decompose(word[-1])
    return d is not None and d[2] != ""


def ends_with_rieul(word: str) -> bool:
    """마지막 음절 받침이 ㄹ 인가('으' 매개모음 예외 — ㄹ 받침은 '면'을 그대로 쓴다)."""
    if not word:
        return False
    d = decompose(word[-1])
    return d is not None and d[2] == "ㄹ"


# ---------------------------------------------------------------------------
# 2. 품사·역할 태그
# ---------------------------------------------------------------------------
class Pos(StrEnum):
    NOUN = "NOUN"      # 체언(기기/대상)
    VERB = "VERB"      # 용언(동작)
    NUM = "NUM"        # 수량(수사+분류사)
    NEG = "NEG"        # 부정(안/못)
    UNKNOWN = "UNKNOWN"


class Role(StrEnum):
    OBJ = "OBJ"        # 목적격 을/를
    SUBJ = "SUBJ"      # 주격 이/가
    TOPIC = "TOPIC"    # 주제격 은/는
    LOC = "LOC"        # 처소 에/에서
    DIR = "DIR"        # 방향/도구 로/으로
    CONJ = "CONJ"      # 접속 와/과/랑/하고
    AUX = "AUX"        # 보조사 도/만/까지/부터/마다
    NONE = "NONE"


# ---------------------------------------------------------------------------
# 3. 조사 테이블 (이형태 = 받침 유무로 검증 → 거짓 분절 방지)
# ---------------------------------------------------------------------------
# (조사표면, 역할, 받침요구)  받침요구: True=받침뒤만, False=무받침뒤만, None=무관
_PARTICLES: tuple[tuple[str, Role, bool | None], ...] = (
    ("으로", Role.DIR, True), ("로", Role.DIR, False),
    ("에서", Role.LOC, None), ("에", Role.LOC, None),
    ("이랑", Role.CONJ, True), ("랑", Role.CONJ, False),
    ("하고", Role.CONJ, None), ("과", Role.CONJ, True), ("와", Role.CONJ, False),
    ("을", Role.OBJ, True), ("를", Role.OBJ, False),
    ("이", Role.SUBJ, True), ("가", Role.SUBJ, False),
    ("은", Role.TOPIC, True), ("는", Role.TOPIC, False),
    ("까지", Role.AUX, None), ("부터", Role.AUX, None), ("마다", Role.AUX, None),
    ("도", Role.AUX, None), ("만", Role.AUX, None), ("의", Role.NONE, None),
)

# ---------------------------------------------------------------------------
# 4. 도메인 어휘 — 기기(체언) / 동작(용언 활용표면 → 의미범주)
# ---------------------------------------------------------------------------
# 기기 체언: 표면 → 정규 카테고리(영문 키)
DEVICES: dict[str, str] = {
    "모터": "MOTOR", "모타": "MOTOR", "전동기": "MOTOR",
    "펌프": "PUMP", "밸브": "VALVE", "컨베이어": "CONVEYOR", "벨트": "CONVEYOR",
    "램프": "LAMP", "등": "LAMP", "표시등": "LAMP", "경광등": "BEACON",
    "버튼": "BUTTON", "스위치": "SWITCH", "센서": "SENSOR",
    "실린더": "CYLINDER", "히터": "HEATER", "탱크": "TANK", "게이트": "GATE",
    "셔터": "SHUTTER", "부품": "PART", "압력": "PRESSURE", "온도": "TEMP",
    "수위": "LEVEL", "타이머": "TIMER", "카운터": "COUNTER", "알람": "ALARM",
    "저수위": "LEVEL_LO", "하한": "LEVEL_LO", "만수위": "LEVEL_HI",
    "고수위": "LEVEL_HI", "상한": "LEVEL_HI", "고장": "FAULT", "이상": "FAULT",
}

# 동작 용언: 활용 표면(스템 또는 단축형) → (대표동사, 의미범주). 르-/ㅓ축약 등은 표면 열거로 처리.
ACTIONS: dict[str, tuple[str, str]] = {
    # RUN(가동/회전)
    "돌": ("돌다", "RUN"), "돌리": ("돌리다", "RUN"), "돌려": ("돌리다", "RUN"),
    "돌아": ("돌다", "RUN"), "가동": ("가동하다", "RUN"), "운전": ("운전하다", "RUN"),
    "구동": ("구동하다", "RUN"), "기동": ("기동하다", "RUN"), "시동": ("시동하다", "RUN"),
    "작동": ("작동하다", "RUN"), "동작": ("동작하다", "RUN"),
    # STOP(정지)
    "정지": ("정지하다", "STOP"), "멈추": ("멈추다", "STOP"), "멈춰": ("멈추다", "STOP"),
    "멈춤": ("멈추다", "STOP"), "서": ("서다", "STOP"), "선": ("서다", "STOP"),
    "세우": ("세우다", "STOP"), "세워": ("세우다", "STOP"),
    # TURN_ON / TURN_OFF
    "켜": ("켜다", "TURN_ON"), "켜지": ("켜지다", "TURN_ON"), "점등": ("점등하다", "TURN_ON"),
    "끄": ("끄다", "TURN_OFF"), "꺼": ("끄다", "TURN_OFF"), "소등": ("소등하다", "TURN_OFF"),
    # PRESS
    "누르": ("누르다", "PRESS"), "눌러": ("누르다", "PRESS"), "눌리": ("눌리다", "PRESS"),
    "누름": ("누르다", "PRESS"),
    # OPEN / CLOSE
    "열": ("열다", "OPEN"), "열어": ("열다", "OPEN"), "열리": ("열리다", "OPEN"),
    "닫": ("닫다", "CLOSE"), "닫아": ("닫다", "CLOSE"), "닫히": ("닫히다", "CLOSE"),
    # DETECT / FILL / EXCEED / EJECT / COUNT
    "감지": ("감지하다", "DETECT"), "검지": ("검지하다", "DETECT"),
    "차": ("차다", "FILL"), "찼": ("차다", "FILL"), "채우": ("채우다", "FILL"),
    "넘": ("넘다", "EXCEED"), "넘어": ("넘다", "EXCEED"), "초과": ("초과하다", "EXCEED"),
    "배출": ("배출하다", "EJECT"), "토출": ("토출하다", "EJECT"),
    "세": ("세다", "COUNT"), "카운트": ("카운트하다", "COUNT"),
    # BECOME(상태 도달) — '저수위 되면', '감지되면' 등 매우 빈번한 상태변화 용언
    "되": ("되다", "BECOME"), "돼": ("되다", "BECOME"), "된": ("되다", "BECOME"),
    "됐": ("되다", "BECOME"),
}

# 용언 어미(긴 것 우선). is_cond=조건절('-면'류) 표지.
_ENDINGS: tuple[tuple[str, bool], ...] = (
    ("으면서", False), ("면서", False), ("으면", True), ("면", True),
    ("으니까", False), ("니까", False), ("는데", False), ("ㄴ데", False),
    ("다가", False), ("거나", False), ("어서", False), ("아서", False), ("여서", False),
    ("시켜", False), ("시키", False), ("시켜서", False),
    ("세요", False), ("어요", False), ("아요", False), ("여요", False),
    ("어라", False), ("아라", False), ("자", False), ("줘", False), ("줄", False),
    ("게", False), ("고", False), ("며", False), ("지", False), ("기", False),
    ("는", False), ("ㄴ다", False), ("는다", False), ("다", False),
    ("어", False), ("아", False), ("여", False),
)

_NEGATIONS = ("안", "못")
_NEG_ENDINGS = ("지 않", "지않", "지 마", "지마", "지 말")

# 분류사(수량 단위) — 이산 단위 + 아날로그 공학단위(바/도/% 등; 상위에서 아날로그로 라우팅)
_CLASSIFIERS = (
    "개", "대", "번", "회", "초", "분", "시간", "매", "장", "본", "사이클",
    "바", "도", "퍼센트", "%", "헤르츠",
)
_KO_NUM = {
    "한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7,
    "여덟": 8, "아홉": 9, "열": 10,
}


# ---------------------------------------------------------------------------
# 5. 형태소
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Morpheme:
    surface: str          # 원형(어절)
    pos: Pos
    lemma: str = ""       # 표제어(동사 대표형/기기 카테고리)
    category: str = ""    # 의미범주(RUN/STOP/MOTOR ...)
    role: Role = Role.NONE
    particle: str = ""    # 분리된 조사
    is_condition: bool = False  # 조건절 표지(-면)
    negated: bool = False
    value: int | None = None    # 수량 값


@dataclass
class Analysis:
    text: str
    morphemes: list[Morpheme] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        """인식된(UNKNOWN 아님) 어절 비율 — 설명가능 확신도의 기반."""
        if not self.morphemes:
            return 0.0
        known = sum(1 for m in self.morphemes if m.pos != Pos.UNKNOWN)
        return known / len(self.morphemes)

    def by_pos(self, pos: Pos) -> list[Morpheme]:
        return [m for m in self.morphemes if m.pos == pos]

    @property
    def actions(self) -> list[Morpheme]:
        return self.by_pos(Pos.VERB)

    @property
    def objects(self) -> list[Morpheme]:
        return [m for m in self.morphemes if m.pos == Pos.NOUN]


# ---------------------------------------------------------------------------
# 6. 분절기
# ---------------------------------------------------------------------------
def strip_particle(word: str) -> tuple[str, Role, str]:
    """체언+조사 → (체언, 역할, 조사). 조사 없으면 (word, NONE, '').

    이형태(받침요구)를 검증해 거짓 분절을 막는다(예: '가'는 무받침 뒤에서만 주격).
    """
    for surf, role, need_final in _PARTICLES:
        if len(word) > len(surf) and word.endswith(surf):
            stem = word[: -len(surf)]
            if need_final is None or has_batchim(stem) == need_final:
                return stem, role, surf
    return word, Role.NONE, ""


def _strip_ending(word: str) -> tuple[str, bool]:
    """용언 어미 제거 → (스템후보, 조건절여부). 어미 없으면 (word, False)."""
    for end, is_cond in _ENDINGS:
        if len(word) > len(end) and word.endswith(end):
            return word[: -len(end)], is_cond
    return word, False


def _lookup_action(stem: str) -> tuple[str, str] | None:
    """스템(또는 부분)을 동작 어휘에서 찾는다. 정확 일치 우선, 없으면 최장 접두 일치."""
    if stem in ACTIONS:
        return ACTIONS[stem]
    # '-하-'(감지하면→감지) / '-되-'(감지되면→감지, 피동) 접미 흡수 후 재시도
    if stem and stem[-1] in ("하", "되", "돼") and stem[:-1] in ACTIONS:
        return ACTIONS[stem[:-1]]
    return None


def _lookup_device(word: str) -> tuple[str, str] | None:
    """어절을 기기 어휘에서 찾는다(정확 일치 → 최장 접두 일치)."""
    if word in DEVICES:
        return word, DEVICES[word]
    best: str | None = None
    for surf in DEVICES:
        if word.startswith(surf) and (best is None or len(surf) > len(best)):
            best = surf
    return (best, DEVICES[best]) if best else None


def _parse_quantity(word: str) -> tuple[int, str] | None:
    """수량 어절(숫자/한글수사 + 분류사) → (값, 분류사). 아니면 None."""
    for cls in sorted(_CLASSIFIERS, key=len, reverse=True):
        if cls in word:
            head = word.split(cls)[0]
            digits = "".join(c for c in head if c.isdigit())
            if digits:
                return int(digits), cls
            for ko, val in _KO_NUM.items():
                if head.endswith(ko):
                    return val, cls
    return None


def _analyze_eojeol(word: str) -> Morpheme:
    """한 어절을 형태소 분석한다(수량→기기+조사→용언 순으로 시도)."""
    qty = _parse_quantity(word)
    if qty is not None:
        return Morpheme(surface=word, pos=Pos.NUM, value=qty[0], category=qty[1])

    if word in _NEGATIONS:
        return Morpheme(surface=word, pos=Pos.NEG, category="NEG")

    # 기기 체언(+조사)
    stem, role, particle = strip_particle(word)
    dev = _lookup_device(stem)
    if dev is not None:
        return Morpheme(
            surface=word, pos=Pos.NOUN, lemma=dev[0], category=dev[1],
            role=role, particle=particle,
        )

    # 용언(활용)
    vstem, is_cond = _strip_ending(word)
    act = _lookup_action(vstem) or _lookup_action(word)
    if act is not None:
        negated = word.endswith(_NEG_ENDINGS) or any(n in word for n in _NEG_ENDINGS)
        return Morpheme(
            surface=word, pos=Pos.VERB, lemma=act[0], category=act[1],
            is_condition=is_cond, negated=negated,
        )

    return Morpheme(surface=word, pos=Pos.UNKNOWN)


def analyze(text: str) -> Analysis:
    """한국어 제어 지시를 형태소 단위로 분석한다(결정론·키 불필요).

    어절 단위로 분석하되, 부정 부사(안/못)는 바로 뒤 용언에 부정 자질을 전파한다.
    """
    eojeols = text.replace(",", " ").split()
    morphs = [_analyze_eojeol(w) for w in eojeols]

    def _set_negated(idx: int) -> None:
        nm = morphs[idx]
        morphs[idx] = Morpheme(
            surface=nm.surface, pos=nm.pos, lemma=nm.lemma, category=nm.category,
            role=nm.role, particle=nm.particle, is_condition=nm.is_condition,
            negated=True, value=nm.value,
        )

    for i, m in enumerate(morphs):
        # (1) 부정 부사 '안/못' → 뒤의 첫 용언에 전파.
        if m.pos == Pos.NEG:
            for j in range(i + 1, len(morphs)):
                if morphs[j].pos == Pos.VERB:
                    _set_negated(j)
                    break
        # (2) 보조용언 부정 '-지 않-/-지 말-'(별도 어절: 않게/않으면/말고…) → 앞 용언에 전파.
        elif m.pos == Pos.UNKNOWN and (m.surface.startswith(("않", "말"))):
            morphs[i] = Morpheme(surface=m.surface, pos=Pos.NEG, category="NEG")
            for j in range(i - 1, -1, -1):
                if morphs[j].pos == Pos.VERB:
                    _set_negated(j)
                    break
    return Analysis(text=text, morphemes=morphs)
