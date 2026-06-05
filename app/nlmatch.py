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
    "motor_start_stop": ["모터", "기동", "정지", "시작", "켜", "꺼", "버튼", "자기유지",
                         "운전", "구동", "돌리", "멈추", "start", "stop"],
    "fwd_rev": ["정역", "정방향", "역방향", "전진", "후진", "정회전", "역회전", "돌리",
                "양방향", "방향", "좌우", "인터락", "모터", "forward", "reverse"],
    "on_delay": ["지연", "딜레이", "초", "뒤", "후", "타이머", "시간", "기다",
                 "대기", "잠시", "delay", "램프", "켜기"],
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
    "latch_alarm": ["알람", "경보", "고장", "래치", "경고", "이상", "alarm", "fault", "트립"],
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
}

_SEC_RE = re.compile(r"(\d+(?:\.\d+)?)\s*초")
_COUNT_RE = re.compile(r"(\d+)\s*(?:개|번|회|ea|EA)")

_MIN_SCORE = 0.6
_MARGIN = 1.25  # 1위가 2위의 이 배수 이상이면 확신


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
    """텍스트에서 숫자 슬롯(초/개수)을 채운다(심볼은 기본값이 안전하므로 생략)."""
    answers: dict[str, str] = {}
    for f in recipe.fields:
        if f.kind == "time_sec":
            m = _SEC_RE.search(text)
            if m:
                answers[f.key] = str(int(float(m.group(1))))
        elif f.kind == "int":
            m = _COUNT_RE.search(text)
            if m:
                answers[f.key] = m.group(1)
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
    # 안전필수 표현이 보이면 자신만만한 매칭을 막고 하드와이어 경고를 띄운다.
    if _has_safety_term(text):
        confident = False
        extras["safety_warning"] = _SAFETY_WARNING
    return NLResult(
        recipe_id=recipe.id, scores=scores, answers=answers,
        missing=miss, questions=qs, confident=confident, used_llm=False,
        extras=extras,
    )
