"""키 없는 자연어→레시피 매칭 테스트 (결정론, 키 불필요)."""

from __future__ import annotations

import pytest

from app.nlmatch import (
    RECIPE_KEYWORDS,
    _match_score,
    analyze,
    detect_multi_intent,
    disambiguation_question,
    extract_slots,
    is_confident,
    match_recipe,
)
from app.rag import _tokenize
from app.synth import synthesize_st
from app.verifier import verify
from app.wizard import RECIPES, build_spec
from app.wizard import RECIPES as _RECIPES

_CASES = [
    ("버튼 누르면 모터 돌고 정지 누르면 멈추게", "motor_start_stop"),
    ("5초 뒤에 램프 켜기", "on_delay"),
    ("정방향 역방향 버튼으로 모터 돌리고 동시에 못 돌게", "fwd_rev"),
    ("물 차면 펌프 끄고 줄면 켜기", "hi_lo_level"),
    ("부품 10개 세면 배출", "count_eject"),
    ("자동 수동 모드 전환해서 밸브 열기", "auto_manual"),
    ("비전검사 NG면 리젝트하고 불량 누적되면 알람", "vision_reject"),
    ("분류신호 따라 세갈래로 선별 배출", "multiway_sort"),
    ("인덱싱 테이블 회전하고 스테이션 작업 순환", "index_table"),
]


@pytest.mark.parametrize("text,expected", _CASES)
def test_match_recipe_picks_right_one(text: str, expected: str) -> None:
    assert match_recipe(text)[0][0] == expected


def test_keyword_table_parity() -> None:
    """모든 레시피에 키워드 항목이 있어야 한다(신규 레시피 NL 도달성 보장)."""
    assert set(RECIPE_KEYWORDS) == set(RECIPES)


def test_extract_seconds_and_count() -> None:
    assert extract_slots("5초 뒤에 켜기", RECIPES["on_delay"]).get("delay_sec") == "5"
    assert extract_slots("부품 10개", RECIPES["count_eject"]).get("count") == "10"
    assert extract_slots("3 초", RECIPES["on_delay"]).get("delay_sec") == "3"


@pytest.mark.parametrize("text", [
    "버튼 누르면 모터 돌고 정지 누르면 멈추게",
    "라인 기동하면 컨베이어 돌고 부품 50개 차면 배출하고 잼 생기면 상류 정지",
    "히터 200도까지 올리고 유지한 다음 식혀",
    "도금 라인에서 탈지하고 수세하고 도금",
    "안녕하세요 아무 관련 없는 문장",
])
def test_inverted_index_scores_match_single_path(text: str) -> None:
    """BM25 역색인(일괄) 점수가 단건 _match_score 와 일치해야 한다(최적화 정합성)."""
    q = _tokenize(text)
    q_joined = " ".join(set(q))
    fast = dict(match_recipe(text))
    for rid, recipe in _RECIPES.items():
        ref = _match_score(q, recipe, q_joined)
        assert fast[rid] == pytest.approx(ref, abs=1e-9), rid


def test_match_is_deterministic() -> None:
    a = match_recipe("5초 뒤 램프")
    b = match_recipe("5초 뒤 램프")
    assert a == b


def test_empty_text_scores_zero() -> None:
    scores = match_recipe("   ")
    assert all(s == 0.0 for _, s in scores)
    assert not is_confident(scores)


def test_garbage_not_confident() -> None:
    assert not is_confident(match_recipe("안녕하세요 반갑습니다"))


@pytest.mark.parametrize("text,expected", _CASES)
def test_analyze_answers_build_valid_design(text: str, expected: str) -> None:
    """매칭→슬롯 결과가 그대로 build_spec→synth→verify 통과해야 한다."""
    res = analyze(text, allow_llm=False)
    assert res.recipe_id == expected
    assert res.used_llm is False
    spec = build_spec(res.recipe_id, res.answers)
    report = verify(spec, synthesize_st(spec))
    assert report.passed


def test_missing_numeric_slot_asks_question() -> None:
    """초를 안 말하면 지연 기동에서 '몇 초' 질문이 나온다."""
    res = analyze("지연 기동 시켜줘", allow_llm=False)
    assert res.recipe_id == "on_delay"
    assert any("초" in q for q in res.questions)


def test_confident_match_no_symbol_questions() -> None:
    """확신 매칭 + 숫자 슬롯 충족이면 불필요한 심볼 질문을 안 한다."""
    res = analyze("부품 10개 세면 배출", allow_llm=False)
    assert res.answers.get("count") == "10"
    assert res.questions == []


_ROBUST_CASES = [
    ("조그로 잠깐만 돌리기", "jog_run"),
    ("점동으로 살짝 움직이기", "jog_run"),
    ("스타델타로 모터 기동", "star_delta"),
    ("와이델타 기동시키기", "star_delta"),
    ("정방향으로 돌리다가 역방향으로", "fwd_rev"),
    ("정역운전 하고싶어요", "fwd_rev"),
    ("전진했다가 후진하기", "fwd_rev"),
    ("모터를 버튼으로 켜고 끄기", "motor_start_stop"),
    ("버튼 누르면 돌고 정지누르면 멈추기", "motor_start_stop"),
    ("기동하고 5초 뒤에 켜기", "on_delay"),
    ("잠시 기다렸다가 램프 켜기", "on_delay"),
    ("탱크에 물이 차면 펌프 끄기", "hi_lo_level"),
    ("저수위면 급수하고 고수위면 정지", "hi_lo_level"),
    ("부품 10개 세면 배출하기", "count_eject"),
    ("카운트해서 배출시키기", "count_eject"),
    ("자동이랑 수동 모드 전환", "auto_manual"),
    ("이상 생기면 경보 래치", "latch_alarm"),
    ("먼저 난 고장만 표시하기", "first_out_alarm"),
    ("주펌프랑 예비펌프 교번운전", "duty_standby"),
    ("양손으로 눌러야 프레스 동작", "two_hand_safety"),
    # 신규 뿌리산업/메카피온 레시피의 한국어 표현
    ("열처리 승온하고 유지했다가 냉각하기", "heat_treat"),
    ("히터로 가열하고 식히는 열처리로", "heat_treat"),
    ("도금 라인에서 탈지하고 수세하고 도금", "plating_line"),
    ("표면처리 침지 시퀀스", "plating_line"),
    ("용접 셀에서 클램프하고 용접하고 해제", "weld_cell"),
    ("스폿용접 지그 클램프 사이클", "weld_cell"),
    ("컨베이어를 A B로 분기시키기", "conveyor_divert"),
    ("벨트 라인 선별 분기 게이트", "conveyor_divert"),
    ("서보 원점복귀하고 이동해서 정위치", "motion_home_move"),
    ("메카피온 모션 원점 잡고 위치결정", "motion_home_move"),
    ("프레스에 뮤팅 적용해서 양손 허가", "press_muting"),
    ("뮤팅 구간 자동공급", "press_muting"),
]


@pytest.mark.parametrize("text,expected", _ROBUST_CASES)
def test_match_survives_particles(text: str, expected: str) -> None:
    """조사·활용형이 붙어도(조그로/정방향으로/카운트해서) 매칭된다."""
    assert match_recipe(text)[0][0] == expected


def test_nl_design_endpoint() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.server import app

    c = TestClient(app)
    r = c.post("/api/nl-design", json={"text": "5초 뒤에 램프 켜기"})
    assert r.status_code == 200
    d = r.json()
    assert d["recipe"] == "on_delay"
    assert d["filled_answers"].get("delay_sec") == "5"
    assert d["design"]["ok"] is True
    assert d["design"]["ladder"]["rungs"]
    assert "하드와이어" in d["safety_notice"]


def test_nl_add_builds_verified_scaffold_for_compound() -> None:
    """다중 서브시스템 요청 → nl-add 가 검증 통과한 다중모듈 골격을 돌려준다(침묵 누락 방지)."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.server import app

    c = TestClient(app)
    r = c.post("/api/project/nl-add", json={
        "text": "용접 클램프하고 용접하고 풀어주는데 안전문 열려있으면 시작 안되게",
        "existing_names": [],
    })
    assert r.status_code == 200
    d = r.json()
    assert d["multi_intent"]
    assert len(d["scaffold"]) >= 2
    assert d["scaffold_verified"] is True  # 골격이 compose→verify 통과
    # 안전 레시피 모듈은 안전경고를 달고 온다(가드 인터락).
    assert any("⛔" in m["safety_note"] for m in d["scaffold"])


def test_nl_design_surfaces_multi_intent() -> None:
    """다중 서브시스템 요청은 API 에서 multi_intent 안내 + 설계 보류로 나온다."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.server import app

    c = TestClient(app)
    r = c.post("/api/nl-design", json={
        "text": "라인 기동하면 컨베이어 돌고 부품 50개 차면 배출하고 잼 생기면 상류 정지",
        "autobuild": True,
    })
    assert r.status_code == 200
    d = r.json()
    assert d["confident"] is False
    assert d["design"] is None  # 침묵 부분생성 금지
    assert d["multi_intent"]
    assert len(d["multi_intent_ids"]) >= 2


def test_estop_lowers_confidence_and_warns() -> None:
    """'비상정지' 표현은 자신만만 매칭을 막고 하드와이어 경고를 띄운다(P3 가드)."""
    res = analyze("비상정지 누르면 모터 정지")
    assert res.confident is False
    assert "하드와이어" in res.extras.get("safety_warning", "")


def test_normal_stop_has_no_safety_warning() -> None:
    """일반 정지 표현은 안전경고를 띄우지 않는다(오탐 방지)."""
    res = analyze("정지 버튼 누르면 모터 정지")
    assert "safety_warning" not in res.extras


def test_nl_design_surfaces_safety_warning() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.server import app

    c = TestClient(app)
    r = c.post("/api/nl-design", json={"text": "emergency stop 시 정지"})
    assert r.status_code == 200
    d = r.json()
    assert d["confident"] is False
    assert "하드와이어" in d["safety_warning"]


# --- Part 2: 동의어/활용형 확장 (안 헷갈리게) ---
@pytest.mark.parametrize("text", [
    "전동기 켜고 끄기",          # 전동기=모터
    "모타 시동 걸고 멈춤",        # 모타=모터, 시동=기동, 멈춤=정지
    "스타트 누르면 가동 정지하면 멈춤",  # 스타트=기동, 가동=운전, 멈춤=정지
])
def test_motor_synonyms_match(text: str) -> None:
    """기동=시동=스타트=가동, 모터=전동기=모타, 정지=멈춤 동의어가 모터 기동/정지로 간다."""
    assert match_recipe(text)[0][0] == "motor_start_stop"


def test_synonyms_dont_break_distinct_recipes() -> None:
    """동의어 확장이 분명한 다른 레시피 매칭을 망가뜨리지 않는다(회귀)."""
    assert match_recipe("스타델타로 전동기 감압기동")[0][0] == "star_delta"
    assert match_recipe("정방향 역방향 전환")[0][0] == "fwd_rev"


# --- Part 2: 헷갈림(confusable) 디스앰비규에이션 ---
def test_jog_vs_run_ambiguous_asks_distinguishing_question() -> None:
    """조그/연속이 근소차로 다투면 confident=False + 구분 질문(누르는 동안/계속)."""
    res = analyze("모터 운전하기", allow_llm=False)
    assert {res.scores[0][0], res.scores[1][0]} == {"motor_start_stop", "jog_run"}
    assert res.confident is False
    q = res.extras.get("disambiguation", "")
    assert "조그" in q and "연속" in q
    assert res.questions and res.questions[0] == q  # 구분 질문이 맨 앞


def test_disambiguation_question_helper_is_deterministic() -> None:
    """disambiguation_question 은 동일 입력에 동일 출력(결정론)."""
    s = match_recipe("모터 운전하기")
    assert disambiguation_question(s) == disambiguation_question(s)


def test_clear_request_not_flagged_ambiguous() -> None:
    """충분히 분명한 요청은 디스앰비규에이션을 띄우지 않는다(오탐 방지)."""
    res = analyze("정방향 역방향 버튼으로 모터 돌리고 동시에 못 돌게", allow_llm=False)
    assert "disambiguation" not in res.extras


def test_confusable_pair_guard_press_vs_two_hand() -> None:
    """양수조작 vs 프레스 뮤팅이 가까우면 둘을 가르는 질문이 나온다."""
    res = analyze("프레스에 뮤팅 적용해서 양손 허가", allow_llm=False)
    pair = {res.scores[0][0], res.scores[1][0]}
    assert pair == {"press_muting", "two_hand_safety"}
    assert res.confident is False
    assert "뮤팅" in res.extras.get("disambiguation", "")


def test_analyze_is_fully_deterministic() -> None:
    """analyze 를 두 번 호출하면 동일 결과(레시피·점수·질문·extras)."""
    a = analyze("모터 운전하기", allow_llm=False)
    b = analyze("모터 운전하기", allow_llm=False)
    assert a == b


# --- Part 3: 다중의도(compound) 자각 — 침묵 누락 방지 ---
_COMPOUND_CASES = [
    "버튼 누르면 모터 돌고 5초 뒤 두번째 모터도 돌고 고장나면 둘다 정지하고 경광등",
    "프레스는 양손 동시에 눌러야 동작하고 가드 열리면 멈추고 비상스위치 누르면 전체 정지",
    "라인 기동하면 컨베이어 돌고 부품 50개 차면 배출하고 잼 생기면 상류 정지",
    "용접 클램프하고 용접하고 풀어주는데 안전문 열려있으면 시작 안되게",
]


@pytest.mark.parametrize("text", _COMPOUND_CASES)
def test_compound_request_is_flagged_not_silently_partial(text: str) -> None:
    """다중 서브시스템 요청은 확신을 강등하고 multi_intent 안내를 띄운다(침묵 누락 방지)."""
    res = analyze(text, allow_llm=False)
    assert res.confident is False
    assert "multi_intent" in res.extras
    ids = res.extras["multi_intent_ids"].split(",")
    assert len(ids) >= 2


# 단일의도(흔한 패턴)는 compound 로 오인하면 안 된다(precision 우선 — 침묵실패율 0 유지).
_SINGLE_INTENT_CASES = [
    "버튼 누르면 모터 돌고 정지 누르면 선다",
    "기동 버튼 누르면 컨베이어 모터 돌고 정지 누르면 멈추게",  # 단일↔다단 변형(오인 금지)
    "물탱크 저수위 되면 펌프 켜고 만수위 되면 꺼줘",
    "셔터 열림 닫힘 버튼으로 올리고 내리는데 끝까지 가면 리밋으로 정지",
    "여러 고장 중 제일 먼저 난 것만 표시하고 부저 확인하면 소거",  # first-out↔래치 변형(오인 금지)
    "세차기 비누 뿌리고 헹구고 건조까지 순서대로",
]


@pytest.mark.parametrize("text", _SINGLE_INTENT_CASES)
def test_single_intent_not_flagged_compound(text: str) -> None:
    res = analyze(text, allow_llm=False)
    assert "multi_intent" not in res.extras
    assert detect_multi_intent(text, match_recipe(text)) == []


# --- Part 4: 아날로그 설정값(숫자+물리단위)은 정직히 범위밖 거절 ---
@pytest.mark.parametrize("text", [
    "탱크 수위 80%면 펌프1 끄고 펌프2 켜",      # 백분율
    "히터 200도까지 올리고 그 온도 유지",        # 온도 설정값
    "컨베이어 속도 30Hz로 돌리다가 10Hz로 줄여",  # 주파수(VFD)
    "압력 5바 넘으면 밸브 닫고 3바 밑이면 열어",  # 압력 설정값
])
def test_analog_setpoint_is_out_of_scope(text: str) -> None:
    """숫자+물리단위(도/바/Hz/%) 설정값은 불리언 템플릿 밖 → 확신 강등 + 범위밖 안내."""
    res = analyze(text, allow_llm=False)
    assert res.confident is False
    assert "out_of_scope" in res.extras


@pytest.mark.parametrize("text,expected", [
    ("기동하고 5초 뒤에 램프 켜기", "on_delay"),       # 초는 아날로그 아님
    ("부품 100개마다 검사 게이트 열어", "count_eject"),  # 개는 아날로그 아님
    ("8시간 가동하면 자동 정지하고 정비 알람", "runtime_maint"),  # 시간(누적)은 아날로그 아님
])
def test_count_time_slots_not_flagged_analog(text: str, expected: str) -> None:
    """초/개/시간 슬롯은 아날로그 설정값으로 오인되면 안 된다(in-template 보호)."""
    res = analyze(text, allow_llm=False)
    assert "out_of_scope" not in res.extras
    assert res.recipe_id == expected


def test_alternating_pumps_match_duty_standby() -> None:
    """'번갈아 돌리는' 펌프는 duty_standby(교번/리드-래그)로 — fwd_rev 침묵실패 방지."""
    res = analyze("펌프 두대 번갈아 돌리고 동시기동은 금지", allow_llm=False)
    assert res.recipe_id == "duty_standby"


# --- Part 5: 다중 기계 상호배제(교차인터락) 자각 ---
def test_mutex_instances_detected_and_degrades_confidence() -> None:
    """'모터 두 대 동시 금지'는 단일 레시피로 자신있게 안 만들고 상호배제 골격을 안내."""
    res = analyze(
        "모터 두대가 있는데 1번 도는 동안엔 2번 절대 못 돌게 인터락 걸어", allow_llm=False
    )
    assert res.confident is False
    assert res.extras.get("mutex_recipe") == "motor_start_stop"
    assert res.extras.get("mutex_count") == "2"
    assert "multi_intent" in res.extras


@pytest.mark.parametrize("text", [
    "모타 정역 운전 시키고 싶은데 정방향 역방향 동시에 못 돌게",  # 단일 모터 정역(대수 없음)
    "버튼 누르면 모터 돌고 정지 누르면 선다",                    # 단일 기동/정지
    "정방향 역방향 버튼으로 모터 돌리고 동시에 못 돌게",          # fwd_rev 단일
])
def test_single_machine_not_flagged_mutex(text: str) -> None:
    """대수 카운트가 없는 단일 기계 상호배제(정역 등)는 mutex 로 오인하지 않는다(precision)."""
    from app.nlmatch import detect_mutex_instances
    assert detect_mutex_instances(text) is None


def test_nl_add_mutex_returns_verified_interlock_scaffold() -> None:
    """다중 기계 상호배제 요청 → nl-add 가 교차인터락 포함 검증 골격을 돌려준다."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.server import app

    c = TestClient(app)
    r = c.post("/api/project/nl-add", json={
        "text": "모터 두대 중 1번 도는 동안 2번 절대 못 돌게 인터락", "existing_names": [],
    })
    d = r.json()
    assert d["multi_intent"]
    assert len(d["scaffold"]) == 2
    assert len(d["scaffold_cross_interlocks"]) == 1
    assert d["scaffold_verified"] is True


def test_detect_multi_intent_deterministic() -> None:
    t = "버튼 누르면 모터 돌고 고장나면 경광등 켜고 알람"
    assert detect_multi_intent(t, match_recipe(t)) == detect_multi_intent(t, match_recipe(t))


def test_new_root_industry_recipes_build_valid_design() -> None:
    """신규 뿌리산업/모션 레시피의 NL 매칭 결과가 build→synth→verify 통과."""
    for text in (
        "열처리 승온 유지 냉각", "도금 침지 시퀀스", "용접 셀 클램프 사이클",
        "컨베이어 분기", "서보 원점복귀 이동 정위치", "프레스 뮤팅 양손",
    ):
        res = analyze(text, allow_llm=False)
        spec = build_spec(res.recipe_id, res.answers)
        report = verify(spec, synthesize_st(spec))
        assert report.passed, f"{text} -> {res.recipe_id}: {report.issues}"
