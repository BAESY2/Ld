"""평문 설명 레이어 테스트 — 비전문가용 한국어 설명."""

from __future__ import annotations

import json
from pathlib import Path

from app.explain import explain_all, explain_issues, explain_ladder, explain_spec
from app.models import StateMachineSpec, VerificationReport
from app.synth import synthesize_st
from app.transpiler import transpile_st
from app.verifier import verify

_GOLDEN = Path(__file__).resolve().parent / "fixtures" / "golden"


def _spec(name: str) -> StateMachineSpec:
    return StateMachineSpec(**json.loads((_GOLDEN / name).read_text(encoding="utf-8"))["spec"])


def test_explain_spec_lists_io() -> None:
    text = explain_spec(_spec("01_conveyor_fwd_rev.json"))
    assert "입력" in text and "출력" in text
    assert "로직 잠금" in text  # 인터락이 평문으로(소프트웨어 잠금임을 명시)
    assert "MOTOR_FWD" in text


def test_explain_ladder_seal_in_note() -> None:
    spec = _spec("02_motor_self_hold.json")
    rungs = explain_ladder(transpile_st(synthesize_st(spec)))
    assert rungs
    assert any("자기유지" in r for r in rungs)


def test_explain_ladder_describes_contacts() -> None:
    spec = _spec("01_conveyor_fwd_rev.json")
    rungs = explain_ladder(transpile_st(synthesize_st(spec)))
    joined = "\n".join(rungs)
    assert "켜져 있" in joined or "꺼져 있" in joined
    assert "켜집니다" in joined


def test_explain_issues_pass() -> None:
    msgs = explain_issues(VerificationReport(passed=True, issues=[]))
    assert any("통과" in m for m in msgs)


def test_explain_issues_plain_language() -> None:
    # 인터락 에러가 사유 + 고치는 법으로 평문화되는지
    from app.models import VerificationIssue

    rep = VerificationReport(
        passed=False,
        issues=[VerificationIssue(code="INTERLOCK", severity="error", message="x")],
    )
    msgs = explain_issues(rep)
    assert any("동시에 켜" in m and "→" in m for m in msgs)  # 사유 + 고치는 법


def test_explain_all_for_all_golden() -> None:
    """모든 골든에서 설명 문서가 예외 없이 생성된다."""
    for path in sorted(_GOLDEN.glob("*.json")):
        spec = StateMachineSpec(**json.loads(path.read_text(encoding="utf-8"))["spec"])
        st = synthesize_st(spec)
        ladder = transpile_st(st)
        text = explain_all(spec, ladder, verify(spec, st))
        assert "이 장치는 무엇을 하나요" in text
        assert "동작 설명" in text


def test_branch_phrase_handles_contradiction() -> None:
    """모순(빈 입력 브랜치) 렁도 크래시 없이 설명된다(QA P0 #4/#5)."""
    from app.models import ElementType, LadderElement, LadderProgram, LadderRung

    rung = LadderRung(
        input_branches=[],
        outputs=[LadderElement(element_type=ElementType.COIL, symbol="OUT")],
    )
    out = explain_ladder(LadderProgram(rungs=[rung]))
    assert out and "OUT" in out[0]
