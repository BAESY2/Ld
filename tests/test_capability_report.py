"""통합 능력 스코어카드의 무결성·핵심 불변 단정(키 불필요·결정론).

리포트가 예외 없이 돌고, 무엇보다 *침묵실패 0류*와 *검증기 건전성(false-proof/miss=0)*
같은 핵심 안전 불변이 성립함을 단정한다. 건전성은 빠른 작은 규모(n=24)로 돈다 —
규모를 키워도 false-proof/miss=0 은 변하지 않는 불변이다(scripts.soundness_study).
"""

from __future__ import annotations

import json

from scripts.capability_report import (
    Scorecard,
    build_scorecard,
    format_report,
    main,
)

# 테스트 전용 작은 규모(건전성 z3 비용 절감 — 불변은 규모 불변).
_SMALL_N = 24


def _card() -> Scorecard:
    return build_scorecard(soundness_n=_SMALL_N)


def test_build_runs_without_exception() -> None:
    """스코어카드 빌드가 예외 없이 끝나고 모든 항목을 채운다."""
    card = _card()
    # 8개 항목(이해·실세계·컴파일·적대·생성성·교차백엔드·수리·건전성).
    assert len(card.metrics) == 8
    for m in card.metrics:
        assert m.name and m.value and m.limit  # 모든 줄에 측정+한계가 있다


def test_invariant_no_silent_failures() -> None:
    """침묵실패 0류: 컴파일·적대 벤치에서 범위밖을 자신있게 컴파일하지 않는다."""
    card = _card()
    assert card.compile_silent_failures == 0
    assert card.adversarial_silent_failures == 0


def test_invariant_confident_compiles_safe() -> None:
    """confident 컴파일은 전부 verify 통과 + 이중코일 0."""
    card = _card()
    assert card.compile_all_confident_safe is True
    assert card.adversarial_all_confident_safe is True


def test_invariant_verifier_soundness() -> None:
    """검증기 건전성: 쌍·그룹 모두 false-proof=0, miss=0(작은 규모에서도)."""
    card = _card()
    assert card.soundness_ran is True, "z3 가 있어야 건전성을 단정한다"
    assert card.soundness_pair_false_proof == 0
    assert card.soundness_pair_miss == 0
    assert card.soundness_group_false_proof == 0
    assert card.soundness_group_miss == 0


def test_all_invariants_hold_property() -> None:
    """집계 불변 플래그가 True 다(스코어카드 통과 조건)."""
    assert _card().all_invariants_hold is True


def test_format_report_contains_sections() -> None:
    """사람용 리포트에 핵심 섹션과 정직한 한계 표기가 들어간다."""
    text = format_report(_card())
    assert "정직한 통합 능력 스코어카드" in text
    assert "할 수 있는 것" in text
    assert "못 하는 것" in text
    assert "한계:" in text
    assert "모든 불변 성립: True" in text


def test_main_returns_zero_when_invariants_hold(capsys) -> None:  # type: ignore[no-untyped-def]
    """CLI 진입점이 불변 성립 시 0 을 반환하고 사람용 표를 찍는다."""
    rc = main(["--soundness-n", str(_SMALL_N)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "통합 능력 스코어카드" in out


def test_main_json_is_valid(capsys) -> None:  # type: ignore[no-untyped-def]
    """--json 출력이 유효 JSON 이며 핵심 불변 키를 담는다."""
    rc = main(["--json", "--soundness-n", str(_SMALL_N)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    inv = payload["invariants"]
    assert inv["all_invariants_hold"] is True
    assert inv["compile_silent_failures"] == 0
    assert inv["adversarial_silent_failures"] == 0
    assert inv["soundness_pair_false_proof"] == 0
    assert inv["soundness_group_miss"] == 0
    assert len(payload["metrics"]) == 8


def test_deterministic_same_numbers() -> None:
    """두 번 빌드해도 핵심 수치가 비트 동일하다(결정론)."""
    a, b = _card(), _card()
    assert a.compile_silent_failures == b.compile_silent_failures
    assert a.adversarial_silent_failures == b.adversarial_silent_failures
    assert [m.value for m in a.metrics] == [m.value for m in b.metrics]
