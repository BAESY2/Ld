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

import re
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
    # 확장 어휘(G1) — 더 많은 액추에이터/기기
    "부저": "BUZZER", "버저": "BUZZER", "사이렌": "SIREN", "혼": "HORN",
    "팬": "FAN", "송풍기": "FAN", "블로워": "BLOWER", "진공": "VACUUM",
    "클램프": "CLAMP", "척": "CHUCK", "지그": "JIG", "도어": "DOOR", "문": "DOOR",
    "호퍼": "HOPPER", "피더": "FEEDER", "공급기": "FEEDER", "노즐": "NOZZLE",
    "스프레이": "SPRAY", "분사기": "SPRAY", "드릴": "DRILL", "로봇": "ROBOT",
    "솔레노이드": "SOLENOID", "솔밸브": "SOLENOID",
    "쿨러": "COOLER", "냉각기": "COOLER", "컴프레서": "COMPRESSOR",
    "리밋": "LIMIT", "리미트": "LIMIT", "근접센서": "PROX", "광센서": "PHOTO",
    "적색등": "LAMP_R", "녹색등": "LAMP_G", "황색등": "LAMP_Y", "경보": "ALARM",
    "저수위": "LEVEL_LO", "하한": "LEVEL_LO", "만수위": "LEVEL_HI",
    "고수위": "LEVEL_HI", "상한": "LEVEL_HI", "고장": "FAULT", "이상": "FAULT",
    # 방향(정/역) — fwd_rev 의 구조 변별자
    "정방향": "DIR_FWD", "정회전": "DIR_FWD", "전진": "DIR_FWD",
    "역방향": "DIR_REV", "역회전": "DIR_REV", "후진": "DIR_REV",
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
    # BECOME(상태 도달/발생) — '저수위 되면', '감지되면', '고장 나면', '이상 생기면'
    "되": ("되다", "BECOME"), "돼": ("되다", "BECOME"), "된": ("되다", "BECOME"),
    "됐": ("되다", "BECOME"), "나면": ("나다", "BECOME"), "났": ("나다", "BECOME"),
    "나서": ("나다", "BECOME"), "생기": ("생기다", "BECOME"), "생겨": ("생기다", "BECOME"),
    "발생": ("발생하다", "BECOME"),
    # 확장 동작·조건 용언(G1)
    "도착": ("도착하다", "ARRIVE"), "완료": ("완료하다", "DONE"), "끝나": ("끝나다", "DONE"),
    "비": ("비다", "EMPTY"), "막히": ("막히다", "JAM"), "걸리": ("걸리다", "JAM"),
    "클램프": ("클램프하다", "CLAMP_ON"), "고정": ("고정하다", "CLAMP_ON"),
    "해제": ("해제하다", "CLAMP_OFF"), "풀": ("풀다", "CLAMP_OFF"),
    "올리": ("올리다", "UP"), "올려": ("올리다", "UP"), "상승": ("상승하다", "UP"),
    "내리": ("내리다", "DOWN"), "내려": ("내리다", "DOWN"), "하강": ("하강하다", "DOWN"),
    "분사": ("분사하다", "SPRAY_ON"), "흡착": ("흡착하다", "VAC_ON"),
    "울리": ("울리다", "TURN_ON"), "울려": ("울리다", "TURN_ON"), "이동": ("이동하다", "RUN"),
    # 하한(아날로그가 임계 아래로) — 히스테리시스 OFF 측
    "떨어지": ("떨어지다", "DROP"), "떨어져": ("떨어지다", "DROP"),
    "낮아지": ("낮아지다", "DROP"), "미만": ("미만", "DROP"),
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
    instance_idx: str = ""      # 기기 인스턴스 마커(예: 펌프1→'1', 게이트A→'A')


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


# ── 띄어쓰기-무관 최장일치 분절 (한국어 NLP 1순위 난점: 띄어쓰기 오류/STT/현장메모) ──
_DEVICE_SORTED = sorted(DEVICES, key=len, reverse=True)
_ACTION_SORTED = sorted(ACTIONS, key=len, reverse=True)
_PARTICLE_SORTED = sorted(_PARTICLES, key=lambda p: len(p[0]), reverse=True)
_ENDING_SORTED = sorted(_ENDINGS, key=lambda e: len(e[0]), reverse=True)
_PASSIVE = ("되", "돼", "된", "됐", "하", "해")
_QTY_RE = re.compile(r"(\d+)\s*(" + "|".join(map(re.escape, _CLASSIFIERS)) + r")")


def _m_quantity(s: str) -> tuple[int, Morpheme] | None:
    m = _QTY_RE.match(s)
    if m:
        return m.end(), Morpheme(surface=m.group(0), pos=Pos.NUM,
                                 value=int(m.group(1)), category=m.group(2))
    for ko, val in _KO_NUM.items():
        for cls in ("개", "대", "번", "회"):
            if s.startswith(ko + cls):
                return len(ko + cls), Morpheme(surface=ko + cls, pos=Pos.NUM,
                                               value=val, category=cls)
    return None


def _m_device(s: str) -> tuple[int, Morpheme] | None:
    for dev in _DEVICE_SORTED:
        if not s.startswith(dev):
            continue
        rest = s[len(dev):]
        consumed = len(dev)
        inst = ""
        # 인스턴스 마커: 기기 직후 숫자+번/대/호, 또는 뒤에 계수단위가 *없는* 숫자(펌프1),
        # 또는 단일 대문자(게이트A). '부품10개'의 10 은 계수단위(개)가 뒤따르므로 인스턴스 아님.
        mi = re.match(r"(\d+)(?:번|대|호)", rest)
        if mi:
            inst, consumed, rest = mi.group(1), consumed + mi.end(), rest[mi.end():]
        elif (md := re.match(r"(\d+)", rest)) and not any(
            rest[md.end():].startswith(cl) for cl in _CLASSIFIERS
        ):
            inst, consumed, rest = md.group(1), consumed + md.end(), rest[md.end():]
        elif rest[:1].isascii() and rest[:1].isalpha() and rest[:1].isupper():
            inst, consumed, rest = rest[0], consumed + 1, rest[1:]
        for surf, role, need_final in _PARTICLE_SORTED:
            if rest.startswith(surf) and (
                need_final is None or has_batchim(dev) == need_final
            ):
                return consumed + len(surf), Morpheme(
                    surface=s[:consumed + len(surf)], pos=Pos.NOUN, lemma=dev,
                    category=DEVICES[dev], role=role, particle=surf, instance_idx=inst)
        return consumed, Morpheme(surface=s[:consumed], pos=Pos.NOUN, lemma=dev,
                                  category=DEVICES[dev], instance_idx=inst)
    return None


def _m_verb(s: str) -> tuple[int, Morpheme] | None:
    best: tuple[int, Morpheme] | None = None
    for surf in _ACTION_SORTED:
        if not s.startswith(surf):
            continue
        lemma, cat = ACTIONS[surf]
        rest = s[len(surf):]
        consumed = len(surf)
        # 피동/'하' 접미 흡수(감지되면→감지, 단 '되' 자체 동사는 BECOME 으로 이미 처리)
        if surf not in ("되", "돼", "된", "됐") and rest[:1] in _PASSIVE:
            rest = rest[1:]
            consumed += 1
        # 표면 자체가 '-면'으로 끝나면(예: '나면') 조건절로 본다(어미가 lemma 에 흡수된 경우).
        is_cond = surf.endswith("면")
        for end, cond in _ENDING_SORTED:
            if rest.startswith(end):
                consumed += len(end)
                is_cond = is_cond or cond
                break
        if best is None or consumed > best[0]:
            best = (consumed, Morpheme(surface=s[:consumed], pos=Pos.VERB,
                                       lemma=lemma, category=cat, is_condition=is_cond))
    return best


def _m_neg(s: str) -> tuple[int, Morpheme] | None:
    for neg in ("안", "못"):
        if s == neg or s.startswith(neg + " "):
            return len(neg), Morpheme(surface=neg, pos=Pos.NEG, category="NEG")
    if s.startswith(("않", "말")):
        return 1, Morpheme(surface=s[0], pos=Pos.NEG, category="NEG")
    return None


# 절 간 순차 마커(다음/그다음/순서대로/후에/뒤에). 동작 사이의 '순서 진행' 신호.
_SEQ_MARKERS = (
    "그다음", "다음으로", "다음", "순서대로", "이후에", "이후", "후에", "뒤에", "후", "뒤",
)


def _m_seq(s: str) -> tuple[int, Morpheme] | None:
    for mk in sorted(_SEQ_MARKERS, key=len, reverse=True):
        if s.startswith(mk):
            return len(mk), Morpheme(surface=mk, pos=Pos.VERB, category="__SEQ__")
    return None


def _segment(token: str) -> list[Morpheme]:
    """한 어절(또는 붙여쓴 run-on)을 최장일치로 형태소 열로 분절(띄어쓰기 무관)."""
    out: list[Morpheme] = []
    i, n = 0, len(token)
    unknown = ""
    while i < n:
        s = token[i:]
        cand = [
            m for m in (_m_quantity(s), _m_device(s), _m_verb(s), _m_seq(s), _m_neg(s)) if m
        ]
        if cand:
            if unknown:
                out.append(Morpheme(surface=unknown, pos=Pos.UNKNOWN))
                unknown = ""
            consumed, morph = max(cand, key=lambda c: c[0])
            out.append(morph)
            i += consumed
        else:
            unknown += token[i]
            i += 1
    if unknown:
        out.append(Morpheme(surface=unknown, pos=Pos.UNKNOWN))
    return out


def analyze(text: str) -> Analysis:
    """한국어 제어 지시를 형태소 단위로 분석한다(결정론·키 불필요).

    어절 단위로 분석하되, 부정 부사(안/못)는 바로 뒤 용언에 부정 자질을 전파한다.
    """
    morphs: list[Morpheme] = []
    for token in text.replace(",", " ").split():
        morphs.extend(_segment(token))

    def _set_negated(idx: int) -> None:
        nm = morphs[idx]
        morphs[idx] = Morpheme(
            surface=nm.surface, pos=nm.pos, lemma=nm.lemma, category=nm.category,
            role=nm.role, particle=nm.particle, is_condition=nm.is_condition,
            negated=True, value=nm.value,
        )

    for i, m in enumerate(morphs):
        if m.pos != Pos.NEG:
            continue
        # 부정 부사 '안/못'은 *뒤* 용언, 보조용언 '않/말'은 *앞* 용언에 부정을 전파.
        rng = range(i + 1, len(morphs)) if m.surface in ("안", "못") else range(i - 1, -1, -1)
        for j in rng:
            if morphs[j].pos == Pos.VERB:
                _set_negated(j)
                break
    return Analysis(text=text, morphemes=morphs)
