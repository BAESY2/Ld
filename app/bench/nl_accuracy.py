"""NL→명세 정확도 채점 — 결정론(키 없음) 경로의 정직한 측정.

측정 항목(키 불필요·결정론):
  in-template  : 21개로 표현 가능한 요청을 *자신있게 올바른* 템플릿으로 맞히는 비율.
  out-of-tmpl  : 21개로 표현 불가한 요청을, 매처가
                 (a) 자신있게 *틀린* 템플릿에 매칭(=침묵 실패, 위험) vs
                 (b) 확신 없음으로 정직하게 보류(=올바른 거동).
'침묵 실패율'이 이 제품의 천장을 결정한다 — 높으면 21개 밖에서 *자신있게 거짓*.

LLM 경로(임의 로직 실제 합성)는 키가 있어야 하므로 여기서 측정하지 않는다
(scripts/run_nl_bench.py 의 env-guard 경로 참조). 본 모듈은 *결정론 바닥값*이다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.nlmatch import analyze


@dataclass(frozen=True)
class BenchResult:
    n_in_template: int
    in_confident_correct: int       # 자신있게 올바른 템플릿
    in_confident_wrong: int         # 자신있게 *틀린* 템플릿(위험)
    in_not_confident: int           # 보류(맞을 수 있었는데 확신 못 함)
    n_out_template: int
    out_silent_fail: int            # 표현불가인데 자신있게 매칭(침묵 실패, 위험)
    out_honest_refusal: int         # 확신 없음으로 정직 보류

    @property
    def in_template_accuracy(self) -> float:
        return self.in_confident_correct / self.n_in_template if self.n_in_template else 0.0

    @property
    def out_silent_fail_rate(self) -> float:
        return self.out_silent_fail / self.n_out_template if self.n_out_template else 0.0

    @property
    def out_honest_rate(self) -> float:
        return self.out_honest_refusal / self.n_out_template if self.n_out_template else 0.0

    def report(self) -> str:
        return (
            "── NL→명세 정확도 (결정론 경로, 키 없음) ──\n"
            f"IN-TEMPLATE  n={self.n_in_template}: "
            f"자신있게 정답 {self.in_confident_correct} "
            f"({self.in_template_accuracy:.0%}) · "
            f"자신있게 오답 {self.in_confident_wrong} · 보류 {self.in_not_confident}\n"
            f"OUT-OF-TMPL  n={self.n_out_template}: "
            f"침묵 실패(자신있게 틀림) {self.out_silent_fail} "
            f"({self.out_silent_fail_rate:.0%}) · "
            f"정직 보류 {self.out_honest_refusal} ({self.out_honest_rate:.0%})\n"
            f"→ 천장 지표: 21개 밖 침묵 실패율 {self.out_silent_fail_rate:.0%} "
            f"(낮을수록 정직), in-template 정확도 {self.in_template_accuracy:.0%}"
        )


def score_keyless(corpus: list[tuple[str, str | None, str]]) -> BenchResult:
    """코퍼스를 결정론 매처로 채점한다(키 불필요)."""
    in_correct = in_wrong = in_unsure = 0
    out_fail = out_honest = 0
    for text, expected, _why in corpus:
        res = analyze(text)
        if expected is not None:  # in-template
            if not res.confident:
                in_unsure += 1
            elif res.recipe_id == expected:
                in_correct += 1
            else:
                in_wrong += 1
        else:  # out-of-template (표현 불가)
            if res.confident:
                out_fail += 1   # 자신있게 (반드시 부적합한) 템플릿에 매칭 = 침묵 실패
            else:
                out_honest += 1
    n_in = sum(1 for _, e, _ in corpus if e is not None)
    n_out = sum(1 for _, e, _ in corpus if e is None)
    return BenchResult(
        n_in_template=n_in,
        in_confident_correct=in_correct,
        in_confident_wrong=in_wrong,
        in_not_confident=in_unsure,
        n_out_template=n_out,
        out_silent_fail=out_fail,
        out_honest_refusal=out_honest,
    )
