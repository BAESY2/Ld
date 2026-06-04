"""파이프라인 오케스트레이션 테스트 — mock 에이전트, 무한루프 방지."""

from __future__ import annotations

import pytest

from app import graph
from app.memory_map import DeviceAllocator
from app.models import (
    LadderProgram,
    StateMachineSpec,
    VerificationIssue,
    VerificationReport,
)


def _patch_common(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(graph.agents, "run_analyst", lambda req: StateMachineSpec(title="t"))
    monkeypatch.setattr(
        graph.agents, "run_architect", lambda spec, fb=None: ("ST_CODE", DeviceAllocator())
    )
    monkeypatch.setattr(
        graph.agents, "run_renderer", lambda spec, st, alloc: LadderProgram(title="t")
    )


def test_loop_runs_once_then_renders(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(monkeypatch)
    reports = [
        VerificationReport(
            passed=False,
            issues=[VerificationIssue(code="INTERLOCK", severity="error", message="x")],
            suggested_fix="고쳐라",
        ),
        VerificationReport(passed=True),
    ]
    monkeypatch.setattr(graph.agents, "run_verifier", lambda spec, st: reports.pop(0))

    state = graph.run_pipeline("요구", max_revisions=3)

    assert state.passed is True
    assert state.revision_count == 1  # 정확히 1회 재시도
    assert state.ladder is not None
    assert state.error is None


def test_always_fails_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        graph.agents,
        "run_verifier",
        lambda spec, st: VerificationReport(
            passed=False,
            issues=[VerificationIssue(code="INTERLOCK", severity="error", message="x")],
        ),
    )

    state = graph.run_pipeline("요구", max_revisions=2)

    assert state.passed is False
    assert state.error is not None
    assert "give_up" in state.error
    assert state.revision_count == 2  # 무한루프 없이 한계에서 종료
    assert state.ladder is None


def test_analyst_failure_is_captured(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(req: str) -> StateMachineSpec:
        raise RuntimeError("API 키 없음")

    monkeypatch.setattr(graph.agents, "run_analyst", boom)
    state = graph.run_pipeline("요구")
    assert state.error is not None
    assert "analyst" in state.error
