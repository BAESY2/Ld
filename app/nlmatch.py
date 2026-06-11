"""키 없는 자연어 → 레시피 매칭 + 슬롯 채우기 (비전문가 진입로).

자연어(한국어)를 받아 (1) BM25-lite 로 레시피를 랭킹하고 (2) 텍스트에서 숫자
슬롯(초/개수)을 추출하고 (3) 빠진/모호한 슬롯에 1~3개의 확인 질문을 만든다.
모든 경로는 키 불필요·결정론. 산출 answers 는 그대로 wizard.build_spec 에 투입 가능.

rag.py 의 _tokenize / _bm25_lite_score 를 재사용한다(랭킹 수식 중복 금지).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.rag import _bm25_lite_score, _tokenize
from app.wizard import RECIPES, Recipe

# recipe_id -> 한국어 키워드/동의어 (랭킹 부스트용; 토큰 중복 = 가중치)
RECIPE_KEYWORDS: dict[str, list[str]] = {
    "motor_start_stop": ["모터", "모타", "전동기", "기동", "시동", "스타트", "정지", "멈춤",
                         "스톱", "시작", "켜", "꺼", "버튼", "자기유지",
                         "운전", "구동", "돌리", "멈추", "가동", "start", "stop"],
    "fwd_rev": ["정역", "정방향", "역방향", "전진", "후진", "정회전", "역회전", "돌리",
                "양방향", "방향", "좌우", "인터락", "모터", "forward", "reverse"],
    "on_delay": ["지연", "딜레이", "초", "뒤", "후", "타이머", "시간", "기다",
                 "대기", "잠시", "delay", "램프", "켜기"],
    "pill_inspect": ["정제", "알약", "중량", "선별", "mg", "제약", "이탈"],
    "tablet_count_bottle": ["병입", "보틀", "정", "충전 카운트", "인덱서", "제약"],
    "analog_level": ["아날로그", "수위", "레벨", "임계", "비교", "센서값", "수치"],
    "hi_lo_level": ["수위", "물", "탱크", "급수", "배수", "펌프", "저수위", "고수위",
                    "상한", "하한", "레벨", "채우", "비우", "level"],
    "count_eject": ["카운트", "개수", "갯수", "세", "배출", "부품", "감지", "센서",
                    "리셋", "카운터", "수량", "토출", "count"],
    "auto_manual": ["자동", "수동", "모드", "전환", "선택", "밸브", "오토", "매뉴얼",
                    "auto", "manual", "mode"],
    "jog_run": ["조그", "점동", "촌동", "잠깐", "살짝", "누를", "연속", "운전", "모터",
                "수동운전", "jog", "inch"],
    "star_delta": ["스타", "델타", "와이", "기동", "전동기", "감압", "감압기동", "모터",
                   "star", "delta", "와이델타", "스타델타"],
    "latch_alarm": ["알람", "경보", "고장", "래치", "경고", "이상", "alarm", "fault", "트립",
                    "경광등", "점등", "표시등", "비상등", "에러", "error", "유지"],
    "first_out_alarm": ["최초", "퍼스트아웃", "first", "최초고장", "선행", "경음기", "혼",
                        "어느", "먼저", "원인"],
    "duty_standby": ["리드", "래그", "예비", "교번", "주펌프", "듀티", "스탠바이", "펌프",
                     "lead", "lag", "standby"],
    "two_hand_safety": ["양수", "양손", "두손", "프레스", "가드", "안전", "허가", "two",
                        "hand", "press"],
    "car_wash": ["세차", "세척", "비누", "헹굼", "건조", "단계", "순차", "carwash", "wash"],
    "timed_traffic": ["신호등", "신호", "적색", "녹색", "황색", "교통", "순환", "traffic",
                      "신호기"],
    "batch_fill_mix_drain": ["배치", "충전", "교반", "배출", "혼합", "탱크", "공정", "batch",
                             "급수", "교반기"],
    "heat_treat": ["열처리", "승온", "가열", "히터", "노", "유지", "소킹", "냉각", "냉각수",
                   "퀜칭", "주조", "금형", "단조", "어닐링", "템퍼링", "열처리로",
                   "heat", "anneal", "soak", "quench"],
    "plating_line": ["도금", "표면처리", "침지", "탈지", "수세", "헹굼", "도금조", "건조",
                     "전기도금", "아연도금", "크롬도금", "도장", "전처리", "표면",
                     "plating", "rinse", "degrease", "dip"],
    "weld_cell": ["용접", "용접셀", "클램프", "고정", "해제", "언클램프", "용접기", "스폿용접",
                  "점용접", "지그", "셀", "weld", "welding", "clamp"],
    "conveyor_divert": ["컨베이어", "벨트", "분기", "병합", "갈래", "선별", "분류", "게이트",
                        "라인", "이송", "디버트", "푸셔", "conveyor", "divert", "merge", "sort"],
    "motion_home_move": ["모션", "서보", "메카피온", "원점", "원점복귀", "홈", "호밍", "이동",
                         "위치결정", "정위치", "축", "엔코더", "포지션", "위치제어",
                         "motion", "servo", "homing", "home", "move", "position"],
    # 뮤팅 중심 키워드(양손/프레스 같은 일반어는 two_hand_safety 와 공유돼 충돌하므로
    # 넣지 않는다 — '뮤팅'이 명시될 때만 press_muting 이 이기고, 그 외 일반 양수조작은
    # two_hand_safety 가 기본이 되게 한다. 둘은 CONFUSABLE_QUESTIONS 로 가른다).
    "press_muting": ["뮤팅", "뮤트", "muting", "mute", "자동공급", "뮤팅모듈", "뮤팅구간"],
    "three_wire": ["3선식", "삼선식", "표준", "기동정지", "정지우선", "자기유지회로",
                   "푸시버튼", "전동기", "마그네트", "전자접촉기", "3-wire", "seal"],
    "cascade_conveyor": ["다단", "컨베이어", "캐스케이드", "순차기동", "하류", "상류",
                         "시간차", "라인", "이송", "벨트", "cascade", "conveyor"],
    "overload_latch": ["과부하", "트립", "이오씨알", "전자식과부하", "과전류", "차단",
                       "과부하트립", "래치리셋", "overload", "trip", "eocr"],
    "guard_interlock": ["안전문", "가드", "도어", "방호문", "문열림", "인터락",
                        "안전스위치", "방호", "guard", "interlock", "door"],
    "tower_lamp": ["타워램프", "신호탑", "표시등", "삼색등", "패트라이트", "상태표시",
                   "녹색등", "적색등", "황색등", "tower", "lamp", "stack"],
    "flasher": ["점멸", "플래셔", "깜빡", "깜박", "점멸등", "블링크", "명멸",
                "주기점등", "flash", "blink", "flasher"],
    "one_shot": ["원샷", "펄스", "상승에지", "에지", "한번만", "단발", "트리거",
                 "원펄스", "oneshot", "pulse", "edge"],
    "conveyor_jam": ["적체", "잼", "막힘", "걸림", "정체", "상류정지", "병목",
                     "쌓임", "jam", "block", "pileup"],
    "retry_alarm": ["재시도", "리트라이", "재시도횟수", "실패누적", "n회", "횟수초과",
                    "재시도알람", "retry", "attempt", "재시도후알람"],
    "shutter_gate": ["셔터", "게이트", "개폐", "도어개폐", "열림닫힘", "리밋",
                     "올림내림", "셔터문", "shutter", "gate", "개폐기"],
    "runtime_maint": ["운전시간", "적산", "정비", "정비알람", "가동시간", "메인터넌스",
                      "누적시간", "점검주기", "runtime", "maintenance", "hour"],
}

_SEC_RE = re.compile(r"(\d+(?:\.\d+)?)\s*초")
_COUNT_RE = re.compile(r"(\d+)\s*(?:개|번|회|ea|EA)")

# ── 시간/개수 정규화 (한국어 단위·수사·범위) — 슬롯 추출 강건성 ───────────
_KO_NUM = {
    "한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7,
    "여덟": 8, "아홉": 9, "열": 10, "스물": 20, "서른": 30, "마흔": 40, "쉰": 50,
    "일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8,
    "구": 9, "십": 10,
}
_KO_ALT = "|".join(sorted(_KO_NUM, key=len, reverse=True))  # 긴 토큰 우선 매칭
_UNIT_TO_SEC: dict[str, float] = {
    "시간": 3600, "시": 3600, "hr": 3600, "분": 60, "min": 60,
    "초": 1, "sec": 1, "ms": 0.001,
}
_UNIT_RANK = {"시간": 3, "시": 3, "hr": 3, "분": 2, "min": 2, "초": 1, "sec": 1, "ms": 0}
_TIME_UNIT = "시간|분|초|sec|min|ms|hr|시"
_COUNT_UNIT = "개수|갯수|개|매|장|본|회|번|사이클|ea|pcs|pc"

_RANGE_RE = re.compile(
    rf"(\d+)\s*[~\-]\s*\d+\s*(?=(?:{_TIME_UNIT}|{_COUNT_UNIT}))", re.IGNORECASE
)
_TIME_TOKEN = re.compile(rf"(\d+(?:\.\d+)?|{_KO_ALT})\s*({_TIME_UNIT})", re.IGNORECASE)
_COUNT_DIGIT = re.compile(rf"(\d+)\s*(?:{_COUNT_UNIT})", re.IGNORECASE)
_COUNT_KO = re.compile(rf"({_KO_ALT})\s*(?:{_COUNT_UNIT})")


def _num_of(tok: str) -> float:
    return float(_KO_NUM[tok]) if tok in _KO_NUM else float(tok)


def _collapse_ranges(text: str) -> str:
    """'5~10초' → '5초'(하한)으로 정규화."""
    return _RANGE_RE.sub(r"\1", text)


def _extract_durations(text: str) -> list[int]:
    """문장의 시간 표현들을 초(int) 리스트로(등장 순서 유지).

    단위가 큰→작(시간>분>초)으로 인접하면 한 값으로 합산('1시간30분'=5400),
    같거나 커지는 단위면 새 값('30초 60초'=[30,60]). 각 값은 ≥1 로 클램프.
    이로써 단계별 시퀀서(승온/유지/냉각 등)의 슬롯도 각각 채워진다.
    """
    grouped: list[float] = []
    prev_rank: int | None = None
    for m in _TIME_TOKEN.finditer(_collapse_ranges(text)):
        unit = m.group(2).lower()
        rank = _UNIT_RANK[unit]
        val = _num_of(m.group(1)) * _UNIT_TO_SEC[unit]
        if prev_rank is not None and rank < prev_rank:
            grouped[-1] += val  # 복합 지속(내림차순) → 합산
        else:
            grouped.append(val)
        prev_rank = rank
    return [max(1, int(g)) for g in grouped]


def _extract_count(text: str) -> str | None:
    """개수 표현(숫자/한글수사 + 단위, 범위는 하한)을 문자열로."""
    collapsed = _collapse_ranges(text)
    m = _COUNT_DIGIT.search(collapsed)
    if m:
        return m.group(1)
    km = _COUNT_KO.search(collapsed)
    if km:
        return str(_KO_NUM[km.group(1)])
    return None

_MIN_SCORE = 0.6
_MARGIN = 1.25  # 1위가 2위의 이 배수 이상이면 확신
_AMBIG_MARGIN = 1.6  # 헷갈림(confusable) 쌍은 이 배수 미만이면 모호로 본다(더 엄격)

# 자주 헷갈리는(confusable) 레시피 쌍 → 둘을 가르는 한국어 확인 질문.
# 무순서 frozenset 키로 매칭한다. 상위 2개가 이 쌍이고 점수가 가까우면
# (1) confident=False 로 낮추고 (2) 구분 질문을 맨 앞에 띄운다(결정론·키 불필요).
CONFUSABLE_QUESTIONS: dict[frozenset[str], str] = {
    frozenset({"jog_run", "motor_start_stop"}):
        "버튼을 누르는 동안만 도나요(조그/점동), 한 번 누르면 계속 도나요(연속 운전)?",
    frozenset({"fwd_rev", "motor_start_stop"}):
        "한 방향으로만 도나요(기동/정지), 정·역 두 방향으로 도나요(정역 운전)?",
    frozenset({"auto_manual", "motor_start_stop"}):
        "자동/수동 모드를 전환하나요(모드 선택), 그냥 버튼으로 켜고 끄나요(기동/정지)?",
    frozenset({"jog_run", "fwd_rev"}):
        "방향을 바꾸는 건가요(정역), 누르는 동안만 도는 건가요(조그/점동)?",
    frozenset({"press_muting", "two_hand_safety"}):
        "뮤팅(자동공급 구간 양손면제)이 필요한가요(프레스 뮤팅), 순수 양수조작만인가요(양수 허가)?",
    frozenset({"star_delta", "motor_start_stop"}):
        "Y-Δ 감압기동인가요(스타-델타), 단순 기동/정지인가요?",
    frozenset({"heat_treat", "batch_fill_mix_drain"}):
        "온도 승온-유지-냉각 공정인가요(열처리), 충전-교반-배출 공정인가요(배치)?",
    frozenset({"weld_cell", "two_hand_safety"}):
        "용접 클램프→용접→해제 사이클인가요(용접 셀), 양손 기동 허가만인가요(양수)?",
    frozenset({"hi_lo_level", "duty_standby"}):
        "수위(저수위/만수위)로 펌프를 켜고 끄나요(수위 제어), "
        "펌프 여러 대를 번갈아/예비로 돌리나요(교번/리드-래그)?",
    frozenset({"count_eject", "batch_fill_mix_drain"}):
        "센서로 개수를 세서 배출하나요(부품 카운터), "
        "충전→교반→배출을 시간대로 진행하나요(배치)?",
    frozenset({"car_wash", "plating_line"}):
        "세차(비누→헹굼→건조)인가요, 표면처리(탈지→수세→도금→건조) 침지 라인인가요?",
    frozenset({"conveyor_divert", "fwd_rev"}):
        "컨베이어를 A/B 갈래로 분기하나요(분기 게이트), "
        "모터를 정·역 두 방향으로 돌리나요(정역)?",
    frozenset({"heat_treat", "plating_line"}):
        "온도 승온-유지-냉각 공정인가요(열처리), 약품조 침지(탈지-수세-도금) 공정인가요(도금)?",
    frozenset({"motion_home_move", "jog_run"}):
        "서보 원점복귀→이동→정위치 사이클인가요(모션), "
        "모터를 조그(누름)/연속으로 돌리나요(조그/연속)?",
}


@dataclass(frozen=True)
class NLResult:
    recipe_id: str
    scores: list[tuple[str, float]]
    answers: dict[str, str]
    missing: list[str]
    questions: list[str]
    confident: bool
    used_llm: bool = False
    extras: dict[str, str] = field(default_factory=dict)


_SUB_W = 0.7  # 부분포함(파티클/활용형 흡수) 가중 — 정확매치(BM25)보다 낮게

# 안전필수(비상정지 등) 표현: 소프트 정지로 절대 대체 불가 → 신뢰도 강등 + 경고.
_SAFETY_TERMS = (
    "비상정지", "비상 정지", "비상스위치", "비상 스위치", "이머전시", "이머젼시",
    "긴급정지", "긴급 정지", "안전문", "라이트커튼", "안전커튼", "안전스캐너",
    "e-stop", "estop", "emergency", "safety relay", "안전릴레이",
)
_SAFETY_WARNING = (
    "⚠ '비상정지'·안전기능은 PLC 소프트 로직으로 구현하면 안 됩니다. "
    "반드시 안전릴레이/안전PLC 등 하드와이어 회로로 구성하세요. "
    "아래 생성물은 일반(소프트) 정지일 뿐 안전기능이 아닙니다."
)


def _has_safety_term(text: str) -> bool:
    low = text.lower()
    return any(term in low for term in _SAFETY_TERMS)


def _recipe_doc_tokens(recipe: Recipe) -> list[str]:
    toks = _tokenize(f"{recipe.title} {recipe.description} {recipe.category}")
    for kw in RECIPE_KEYWORDS.get(recipe.id, []):
        t = _tokenize(kw)
        toks.extend(t)
        toks.extend(t)  # 키워드 2배 가중
    return toks


def _recipe_kw_tokens(recipe: Recipe) -> set[str]:
    """부분포함 채점용 distinct 키워드 토큰(2글자 이상)."""
    toks = set(_tokenize(f"{recipe.title} {recipe.description} {recipe.category}"))
    for kw in RECIPE_KEYWORDS.get(recipe.id, []):
        toks.update(_tokenize(kw))
    return {t for t in toks if len(t) >= 2}


def _match_score(q: list[str], recipe: Recipe) -> float:
    """BM25(정확) + 부분포함(조사/활용형 흡수) 블렌드. 키 불필요·결정론."""
    bm = _bm25_lite_score(q, _recipe_doc_tokens(recipe)) if q else 0.0
    qset = set(q)
    sub = 0.0
    for kt in _recipe_kw_tokens(recipe):
        if kt in qset:
            continue  # 이미 BM25가 셈
        if any(kt in qt for qt in qset):  # 키워드가 쿼리 토큰의 부분문자열
            sub += _SUB_W
    return bm + sub


def match_recipe(text: str, k: int | None = None) -> list[tuple[str, float]]:
    """자연어를 레시피와 비교해 (id, score) 내림차순 반환(BM25+부분포함)."""
    q = _tokenize(text)
    scored = [(rid, _match_score(q, r)) for rid, r in RECIPES.items()]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k] if k else scored


def extract_slots(text: str, recipe: Recipe) -> dict[str, str]:
    """텍스트에서 숫자 슬롯(초/개수)을 채운다(심볼은 기본값이 안전하므로 생략).

    시간은 분/시간/한글수사/범위를 정규화하고, **단계별 시퀀서**는 등장한 시간
    값을 k번째 time_sec 필드에 순서대로 배정한다. 개수도 단위·한글수사·범위 지원.
    """
    answers: dict[str, str] = {}
    durations = _extract_durations(text)
    time_fields = [f for f in recipe.fields if f.kind == "time_sec"]
    for i, f in enumerate(time_fields):
        if i < len(durations):
            answers[f.key] = str(durations[i])
    count = _extract_count(text)
    if count is not None:
        for f in recipe.fields:
            if f.kind == "int":
                answers[f.key] = count
    return answers


def missing_slots(answers: dict[str, str], recipe: Recipe) -> list[str]:
    """채워지지 않은 Field.key 목록(레시피 정의 순서)."""
    return [f.key for f in recipe.fields if not answers.get(f.key)]


def clarifying_questions(missing: list[str], recipe: Recipe, limit: int = 3) -> list[str]:
    """누락 슬롯에 대해 답하기 쉬운 한국어 질문(값 슬롯 먼저, 최대 limit)."""
    by_key = {f.key: f for f in recipe.fields}
    fields = [by_key[k] for k in missing if k in by_key]
    fields.sort(key=lambda f: 0 if f.kind in ("time_sec", "int") else 1)
    qs: list[str] = []
    for f in fields[:limit]:
        if f.kind == "time_sec":
            qs.append(f"{f.label}? 몇 초로 할까요? (기본 {f.default})")
        elif f.kind == "int":
            qs.append(f"{f.label}? 몇 개로 할까요? (기본 {f.default})")
        else:
            qs.append(f"{f.label}의 신호 이름을 정해줄까요? (기본 {f.default})")
    return qs


def is_confident(scores: list[tuple[str, float]]) -> bool:
    if not scores or scores[0][1] < _MIN_SCORE:
        return False
    if len(scores) == 1:
        return True
    second = scores[1][1]
    return second <= 0 or scores[0][1] >= _MARGIN * second


def _close_top2(scores: list[tuple[str, float]], margin: float) -> bool:
    """상위 2개가 margin 배수 안쪽으로 가까운가(둘 다 의미있는 점수일 때만)."""
    if len(scores) < 2:
        return False
    top, second = scores[0][1], scores[1][1]
    if top < _MIN_SCORE or second <= 0:
        return False
    return top < margin * second


def disambiguation_question(scores: list[tuple[str, float]]) -> str | None:
    """상위 2개가 '헷갈리는 쌍'이고 점수가 가까우면 둘을 가르는 질문을 반환.

    결정론·키 불필요. confusable 가드: 자동/수동 vs 조그/연속 vs 정역 등이 점수만
    근소차로 1·2위를 다툴 때 조용히 오답하지 않도록 명시 질문으로 끌어올린다.
    """
    if not _close_top2(scores, _AMBIG_MARGIN):
        return None
    pair = frozenset({scores[0][0], scores[1][0]})
    return CONFUSABLE_QUESTIONS.get(pair)


# 21개 결정론 템플릿(불리언 상태머신/타이머/카운터)으로 *표현 불가*한 능력의 단서.
# 이런 요청은 가장 가까운 템플릿에 자신있게 매칭하면 '침묵 실패'(자신있게 틀림)가 된다.
# → 감지되면 확신을 강등하고 "범위 밖" 안내를 띄운다(자신있게 거짓 금지).
_OUT_OF_SCOPE_CUES = (
    "pid", "아날로그", "비례 제어", "비례제어", "폐루프", "클로즈드루프", "closed loop",
    "setpoint", "셋포인트", "인버터", "vfd", "주파수", "속도지령", "토크", "압력 프로파일",
    "압력프로파일", "전류 프로파일", "프로파일", "보간", "티칭", "6축", "다관절", "팔레타이징",
    "좌표", "마이크로스텝", "스텝모터", "펄스열", "전자캠", "대수제어", "통신으로", "데이터를",
    "집계", "리포트", "mes", "배합비", "레시피 ", "레시피를", "로드셀", "무게 피드백",
    "농도", "압입", "비전", "색 구분", "색구분", "마이크로", "엔코더", "전자캠",
)
_OUT_OF_SCOPE_MSG = (
    "이 요청은 아날로그·모션(보간/다축)·통신·PID·레시피 등 21개 결정론 템플릿으로는 "
    "표현할 수 없습니다. 가까운 템플릿으로 자신있게 잘못 만들지 않도록 보류합니다 — "
    "LLM 합성 경로(키 필요) 또는 전문가 설계가 필요합니다."
)


def _out_of_scope(text: str) -> bool:
    low = text.lower()
    return any(cue in low for cue in _OUT_OF_SCOPE_CUES)


def analyze(text: str, allow_llm: bool = True) -> NLResult:
    """자연어 → 레시피+슬롯+질문. 키 불필요(BM25). LLM 폴백은 미연결(키 없을 때 동일)."""
    scores = match_recipe(text)
    confident = is_confident(scores)
    recipe = RECIPES[scores[0][0]]
    answers = extract_slots(text, recipe)
    miss = missing_slots(answers, recipe)
    # 심볼은 기본값이 그대로 동작하므로 묻지 않는다. 비어있는 '숫자' 슬롯만 질문.
    kinds = {f.key: f.kind for f in recipe.fields}
    value_missing = [k for k in miss if kinds.get(k) in ("time_sec", "int")]
    qs = clarifying_questions(value_missing, recipe)
    extras: dict[str, str] = {}
    # 헷갈리는 쌍이 근소차로 1·2위면: 신뢰도 강등 + 구분 질문을 맨 앞에 띄운다.
    disambig = disambiguation_question(scores)
    if disambig is not None:
        confident = False
        extras["disambiguation"] = disambig
        qs = [disambig, *qs]
    # 범위 밖(아날로그/모션/통신/PID 등)이면 자신있게 틀린 템플릿에 매칭하지 않는다.
    if _out_of_scope(text):
        confident = False
        extras["out_of_scope"] = _OUT_OF_SCOPE_MSG
    # 안전필수 표현이 보이면 자신만만한 매칭을 막고 하드와이어 경고를 띄운다.
    if _has_safety_term(text):
        confident = False
        extras["safety_warning"] = _SAFETY_WARNING
    return NLResult(
        recipe_id=recipe.id, scores=scores, answers=answers,
        missing=miss, questions=qs, confident=confident, used_llm=False,
        extras=extras,
    )
