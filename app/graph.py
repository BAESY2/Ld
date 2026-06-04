"""파이프라인 오케스트레이션: analyst → architect → verifier → (renderer | loop | give_up).

PLAN 은 LangGraph 를 권하지만, 1차는 의존성 없는 결정론 루프로 구현한다
(키 없이 mock 테스트 가능, 무한루프 방지 게이트 내장). 추후 동일 인터페이스로
LangGraph StateGraph 로 교체할 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app import agents
from app.config import settings
from app.models import LadderProgram, StateMachineSpec, VerificationReport


@dataclass
class PipelineState:
    user_request: str
    spec: StateMachineSpec | None = None
    st_code: str = ""
    ladder: LadderProgram | None = None
    verification: VerificationReport | None = None
    revision_count: int = 0
    error: str | None = None
    history: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.verification is not None and self.verification.passed and self.error is None


def _feedback_from_report(report: VerificationReport) -> str:
    lines = [f"- [{i.severity}] {i.code}: {i.message}" for i in report.issues]
    if report.suggested_fix:
        lines.append(f"수정 제안: {report.suggested_fix}")
    return "\n".join(lines)


def run_pipeline(request: str, max_revisions: int | None = None) -> PipelineState:
    """자연어 요구를 받아 ST + 래더 + 검증 리포트까지 흘린다."""
    limit = settings.max_revisions if max_revisions is None else max_revisions
    state = PipelineState(user_request=request)

    try:
        state.spec = agents.run_analyst(request)
    except Exception as exc:  # noqa: BLE001
        state.error = f"분석가(analyst) 실패: {exc}"
        return state

    feedback: str | None = None
    while True:
        try:
            st_code, allocator = agents.run_architect(state.spec, feedback)
        except Exception as exc:  # noqa: BLE001
            state.error = f"아키텍트(architect) 실패: {exc}"
            return state
        state.st_code = st_code

        report = agents.run_verifier(state.spec, st_code)
        state.verification = report
        state.history.append(f"rev {state.revision_count}: passed={report.passed}")

        if report.passed:
            state.ladder = agents.run_renderer(state.spec, st_code, allocator)
            return state

        if state.revision_count >= limit:
            state.error = f"검증 실패가 {limit}회 수정 후에도 남았습니다(give_up)."
            return state

        state.revision_count += 1
        feedback = _feedback_from_report(report)
