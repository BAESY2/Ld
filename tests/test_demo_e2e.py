"""end-to-end 데모 파이프라인 회귀 테스트 (키 불필요·결정론).

데모가 예외 없이 돌고, 명확한 문장은 confident + verify passed + 이중코일0,
비확신/도메인 밖 문장은 정직하게 '보류'로 표시됨을 단정한다.
"""

from __future__ import annotations

import pytest

from scripts.demo_e2e import (
    DEMO_SENTENCES,
    DemoResult,
    print_transcript,
    run_one,
)


def test_pipeline_runs_without_exception() -> None:
    """전 문장이 예외 없이 파이프라인을 통과한다(전사 출력 포함)."""
    results = print_transcript()
    assert len(results) == len(DEMO_SENTENCES)
    assert all(isinstance(r, DemoResult) for r in results)


@pytest.mark.parametrize(
    "text",
    [
        "모터를 돌려",
        "컨베이어를 멈춰",
        "부품10개세면배출해",
        "저수위가 되면 펌프를 켜고 고수위가 되면 꺼라",
        "압력이 5바 넘으면 펌프 켜",
        "셔터 열고 닫아",
    ],
)
def test_confident_sentences_synthesize_and_verify(text: str) -> None:
    """명확한 현장 문장: confident + 레시피 매핑 + 이중코일0 + verify passed."""
    r = run_one(text)
    assert r.confident is True
    assert r.held is False
    assert r.recipe_id is not None
    assert r.double_coils == 0          # 이중코일 0 불변식
    assert r.verify_passed is True      # 정형검증 통과
    assert r.rung_count >= 1            # 래더 렁이 생성됨


def test_spacing_free_variant_matches_spaced() -> None:
    """띄어쓰기 없는 run-on 이 띄어쓴 문장과 같은 레시피로 이해된다(엔진의 강건성)."""
    spaced = run_one("부품 10개 세면 배출해")
    runon = run_one("부품10개세면배출해")
    assert spaced.recipe_id == runon.recipe_id == "count_eject"
    assert runon.confident and not runon.held


def test_interlock_pair_is_machine_proven() -> None:
    """셔터 개·폐는 k-귀납으로 상호배제가 *증명된* 인터락 쌍을 가진다."""
    r = run_one("셔터 열고 닫아")
    assert r.recipe_id == "shutter_gate"
    assert r.verify_passed is True
    # (a,b)·(b,a) 양방향이 증명 집합에 들어간다.
    assert ("MTR_OPEN", "MTR_CLOSE") in r.proven_pairs
    assert ("MTR_CLOSE", "MTR_OPEN") in r.proven_pairs


@pytest.mark.parametrize(
    "text",
    [
        "데이터를 통신으로 모아서 리포트 만들어",  # 도메인 밖(통신/리포트)
        "오늘 점심 뭐 먹지",       # 도메인 밖
    ],
)
def test_uncertain_or_out_of_domain_is_held(text: str) -> None:
    """비확신/도메인 밖 문장은 거짓 래더 생성 없이 '보류'로 표시된다(환각 0)."""
    r = run_one(text)
    assert r.held is True
    assert r.hold_reason != ""
    # 보류 문장은 합성·검증 산출물을 만들지 않는다.
    assert r.rung_count == 0
    assert r.proven_pairs == ()


def test_determinism() -> None:
    """결정론: 같은 입력은 같은 결과(키·랜덤 없음)."""
    first = run_one("압력이 5바 넘으면 펌프 켜")
    second = run_one("압력이 5바 넘으면 펌프 켜")
    assert first == second


def test_demo_summary_invariants_hold() -> None:
    """확신 문장 전원이 이중코일0·verify passed 라는 데모의 핵심 주장을 단정."""
    results = [run_one(s) for s in DEMO_SENTENCES]
    confident = [r for r in results if not r.held]
    assert len(confident) >= 1
    assert all(r.double_coils == 0 for r in confident)
    assert all(r.verify_passed for r in confident)
