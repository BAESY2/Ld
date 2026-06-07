"""설계 경로(LLM) 정확도 채점 — "21개 밖 자유요청을 검증통과 래더로 바꾸는가".

결정론 매처(nl_accuracy)가 *키워드 천장*을 재는 반면, 본 모듈은 **LLM 설계 폐루프**
(``app.design.design_and_verify``)가 자유 한국어 요청을 받아 **결정론 게이트(compose→
verify)를 통과하는 명세**로 바꾸는 비율을 잰다. 이것이 근간 재설계의 핵심 지표다.

정직성 원칙:
- LLM 의 *실제* 출력 품질은 키가 있어야 측정된다. 본 채점기는 ``model_factory`` 주입을
  받으므로, 키 없이도 mock 으로 **하니스 자체**를 CI 에서 고정 검증한다(키 꽂으면 실측).
- 게이트가 차단한 설계(gate_blocked)는 실패로 **정직 집계**한다(불량 은닉 금지).
- 아날로그/모션/PID 등은 BOOL-only 명세로 표현 불가하므로 게이트가 막는 것이 *정상*이다.
  따라서 pass_rate 는 "표현 가능한 범위에서 LLM 이 검증통과 설계를 낸 비율"로 읽는다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.design import design_and_verify
from app.memory_map import detect_double_coils

# model_factory: 호출 시 with_structured_output(ProjectPlan) 호환 모델을 반환.
# None 이면 실제 LLM 시드를 쓴다(키 필요). 테스트는 가짜 모델 팩토리를 주입한다.
ModelFactory = Callable[[], Any]


@dataclass(frozen=True)
class DesignBenchResult:
    n: int
    gate_pass: int                  # 설계가 결정론 게이트 통과(채택 가능)
    gate_blocked: int               # 생성됐으나 verify 실패(폐루프 포기) — 게이트가 차단
    synth_error: int                # compose/synth 자체 실패(표현 불가 등)
    llm_error: int                  # LLM 호출 실패(키 없음/네트워크 등)
    total_revisions: int            # 폐루프가 돈 총 횟수(낮을수록 1발 성공)
    double_coil_total: int          # 채택분의 이중코일 — 게이트 보장상 0이어야 함
    interlock_violation_total: int  # 채택분의 인터락 error — 0이어야 함

    @property
    def pass_rate(self) -> float:
        return self.gate_pass / self.n if self.n else 0.0

    @property
    def mean_revisions(self) -> float:
        return self.total_revisions / self.n if self.n else 0.0

    def report(self) -> str:
        return (
            "── 설계 경로(LLM) 정확도 ──\n"
            f"n={self.n}: 게이트 통과 {self.gate_pass} ({self.pass_rate:.0%}) · "
            f"게이트 차단 {self.gate_blocked} · 합성불가 {self.synth_error} · "
            f"LLM실패 {self.llm_error}\n"
            f"평균 재설계 {self.mean_revisions:.2f}회 · "
            f"채택분 이중코일 {self.double_coil_total}건 · "
            f"인터락위반 {self.interlock_violation_total}건\n"
            f"→ 게이트 통과율 {self.pass_rate:.0%} "
            "(자유요청→검증통과 BOOL 래더 전환율; 채택분 위반은 항상 0이어야 함)"
        )


def score_design(
    corpus: list[tuple[str, str | None, str]],
    *,
    model_factory: ModelFactory | None = None,
    max_revisions: int = 2,
) -> DesignBenchResult:
    """코퍼스의 각 자유요청을 설계 폐루프로 돌려 게이트 통과 여부를 집계한다.

    ``model_factory`` 가 None 이면 실제 LLM 을 쓴다(키 필요). 케이스마다 새 모델을
    뽑아(상태 없는) ``design_and_verify`` 에 주입한다.
    """
    gate_pass = gate_blocked = synth_error = llm_error = 0
    total_revisions = dbl_total = ilk_total = 0
    for text, _expected, _why in corpus:
        model = model_factory() if model_factory is not None else None
        try:
            result = design_and_verify(text, model=model, max_revisions=max_revisions)
        except Exception:  # noqa: BLE001 - 키 없음/네트워크 등은 정직히 llm_error 로 집계
            llm_error += 1
            continue
        total_revisions += result.revisions
        if result.spec is None:
            synth_error += 1
            continue
        report = result.report
        if report is not None and report.passed:
            gate_pass += 1
            dbl_total += len(detect_double_coils(result.st_code))
            ilk_total += sum(
                1 for i in report.issues if i.code == "INTERLOCK" and i.severity == "error"
            )
        else:
            gate_blocked += 1
    return DesignBenchResult(
        n=len(corpus),
        gate_pass=gate_pass,
        gate_blocked=gate_blocked,
        synth_error=synth_error,
        llm_error=llm_error,
        total_revisions=total_revisions,
        double_coil_total=dbl_total,
        interlock_violation_total=ilk_total,
    )
