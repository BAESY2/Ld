#!/usr/bin/env python3
"""두 독립 경로의 *합의*가 침묵실패를 줄이는 신호인지 측정(코드 변경 없이 분석만).

realworld 코퍼스(benchmarks/real_world_ko.jsonl)의 각 문장에 대해 *서로 독립적인*
두 경로의 확신(confident)을 구한다:

  (a) nlmatch.analyze  — 키워드/BM25 경로(현 단독 라우팅). 침묵실패가 0 이 아니다.
  (b) compile_frame.frame_to_spec — 의미타입 가드를 가진 결정론 컴파일러(더 정직).

그리고 *합의 규칙*(둘 다 confident 일 때만 '신뢰')을 적용했을 때 침묵실패(범위밖인데
신뢰, 또는 기대 밖 레시피를 신뢰)가 nlmatch 단독 대비 얼마나 주는지 측정한다. 동시에
합의가 정답 인식(recall)을 얼마나 희생하는지도 *정직히* 보고한다(트레이드오프).

침묵실패 정의는 run_realworld_bench.evaluate 와 동일하게 맞춘다:
  · kind=out_of_scope : confident 이면 침묵실패(범위밖인데 자신있게 매칭).
  · kind=recipe|multi : confident 인데 top 레시피가 기대 밖이면 침묵실패.

이 스크립트는 *측정만* 한다(라우팅 변경 없음·키 불필요·100% 결정론). 합의를 라우팅에
채택할지는 부모가 이 수치를 보고 결정한다.

실행:  python scripts/consensus_bench.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.compile_frame import frame_to_spec  # noqa: E402
from app.nlmatch import analyze  # noqa: E402

# run_realworld_bench 의 코퍼스 로더를 재사용(채점 정의 일관성 — 중복 정의 금지).
from scripts.run_realworld_bench import Case, load_corpus  # noqa: E402


@dataclass(frozen=True)
class ConsensusOutcome:
    case: Case
    top: str
    nl_confident: bool       # (a) nlmatch 경로의 확신
    compile_confident: bool  # (b) frame_to_spec 경로의 확신
    consensus_confident: bool  # 둘 다 confident 일 때만 True
    nl_silent_fail: bool     # nlmatch 단독 라우팅의 침묵실패
    consensus_silent_fail: bool  # 합의 라우팅의 침묵실패
    nl_recognized: bool      # nlmatch 단독이 정답 인식(정답 신뢰 / 범위밖 거절)
    consensus_recognized: bool  # 합의가 정답 인식
    is_positive: bool        # 신뢰가 정답인 케이스(recipe|multi)


def _is_silent_fail(case: Case, confident: bool, top: str) -> bool:
    """run_realworld_bench.evaluate 와 동일한 침묵실패 정의."""
    if case.kind == "out_of_scope":
        return confident  # 범위밖인데 자신있게 매칭
    return confident and top not in case.recipes  # 기대 밖 레시피를 신뢰


def _is_recognized(case: Case, confident: bool, top: str) -> bool:
    """정답 인식: 양성(recipe|multi)은 기대 레시피를 신뢰, 범위밖은 정직 거절."""
    if case.kind == "out_of_scope":
        return not confident
    return confident and top in case.recipes


def evaluate(case: Case) -> ConsensusOutcome:
    nl = analyze(case.text, allow_llm=False)
    cr = frame_to_spec(case.text)
    top = nl.recipe_id
    nl_conf = nl.confident
    cmp_conf = cr.confident
    consensus = nl_conf and cmp_conf  # 합의 규칙: 둘 다 신뢰할 때만 신뢰
    return ConsensusOutcome(
        case=case,
        top=top,
        nl_confident=nl_conf,
        compile_confident=cmp_conf,
        consensus_confident=consensus,
        nl_silent_fail=_is_silent_fail(case, nl_conf, top),
        consensus_silent_fail=_is_silent_fail(case, consensus, top),
        nl_recognized=_is_recognized(case, nl_conf, top),
        consensus_recognized=_is_recognized(case, consensus, top),
        is_positive=case.kind in ("recipe", "multi"),
    )


def _pct(n: int, d: int) -> str:
    return f"{(100.0 * n / d):5.1f}%" if d else "  n/a"


def _bar(title: str) -> str:
    return f"\n{'=' * 4} {title} {'=' * max(0, 60 - len(title))}"


def run() -> dict[str, object]:
    cases = load_corpus()
    outs = [evaluate(c) for c in cases]
    n = len(outs)

    nl_sf = sum(o.nl_silent_fail for o in outs)
    cons_sf = sum(o.consensus_silent_fail for o in outs)
    nl_rec = sum(o.nl_recognized for o in outs)
    cons_rec = sum(o.consensus_recognized for o in outs)

    pos = [o for o in outs if o.is_positive]
    npos = len(pos)
    nl_pos_rec = sum(o.nl_recognized for o in pos)
    cons_pos_rec = sum(o.consensus_recognized for o in pos)

    nl_cov = sum(o.nl_confident for o in outs)
    cons_cov = sum(o.consensus_confident for o in outs)

    lines: list[str] = []
    lines.append(_bar("CONSENSUS BENCH (nlmatch AND frame_to_spec) — 측정만"))
    lines.append(f"코퍼스: {n}건  ·  파일: real_world_ko.jsonl")
    lines.append(
        "합의 규칙: nlmatch.analyze.confident AND frame_to_spec.confident 일 때만 '신뢰'."
    )

    lines.append(_bar("침묵실패(자신있게 틀림) — 단독 vs 합의"))
    lines.append(f"   nlmatch 단독 침묵실패        : {nl_sf}건  ({_pct(nl_sf, n)})")
    lines.append(f"   합의 라우팅 침묵실패         : {cons_sf}건  ({_pct(cons_sf, n)})")
    lines.append(
        f"   감소량                       : {nl_sf - cons_sf}건  "
        f"(합의는 침묵실패를 늘리지 않는다 — 단조)"
    )

    lines.append(_bar("커버리지(자신있게 진행한 비율) — 합의의 대가"))
    lines.append(f"   nlmatch 단독 confident       : {nl_cov}건  ({_pct(nl_cov, n)})")
    lines.append(f"   합의 confident               : {cons_cov}건  ({_pct(cons_cov, n)})")
    lines.append(
        f"   커버리지 손실                : {nl_cov - cons_cov}건  "
        f"(둘 중 하나라도 보류하면 보류)"
    )

    lines.append(_bar("정답 인식(recall) — 합의가 희생하는 정답"))
    lines.append(
        f"   전체 인식(거절 포함)         : "
        f"nlmatch {nl_rec}/{n} ({_pct(nl_rec, n)}) -> "
        f"합의 {cons_rec}/{n} ({_pct(cons_rec, n)})"
    )
    lines.append(
        f"   양성 인식(recipe|multi)      : "
        f"nlmatch {nl_pos_rec}/{npos} ({_pct(nl_pos_rec, npos)}) -> "
        f"합의 {cons_pos_rec}/{npos} ({_pct(cons_pos_rec, npos)})"
    )
    lines.append(
        f"   양성 recall 손실             : {nl_pos_rec - cons_pos_rec}건  "
        f"(컴파일러가 보류하면 합의도 보류)"
    )

    lines.append(_bar("불일치 케이스(두 경로가 갈린 곳) — 신호의 출처"))
    disagree = [o for o in outs if o.nl_confident != o.compile_confident]
    lines.append(f"   두 경로 확신 불일치          : {len(disagree)}건")
    for o in disagree:
        if o.nl_silent_fail and not o.consensus_silent_fail:
            tag = "침묵실패 제거"
        elif o.is_positive and o.nl_recognized and not o.consensus_recognized:
            tag = "recall 손실"
        else:
            tag = "중립"
        lines.append(
            f"   [{o.case.kind:12}] {o.case.id}: "
            f"nl={int(o.nl_confident)} cmp={int(o.compile_confident)} "
            f"top={o.top}  -> {tag}"
        )

    lines.append(_bar("정직한 결론"))
    if nl_sf == 0:
        verdict = (
            "이 코퍼스에서 nlmatch 단독 침묵실패가 이미 0 이라 합의의 침묵실패 *감소*는 "
            "관측되지 않는다. 합의는 침묵을 늘리지 않지만 정답 recall 만 깎는다 -> "
            "이 코퍼스 기준 라우팅 채택 *비권고*."
        )
    elif cons_sf < nl_sf:
        verdict = (
            f"합의는 침묵실패를 {nl_sf}->{cons_sf}건으로 줄인다(가장 위험한 실패 제거). "
            f"대가는 양성 recall {nl_pos_rec}->{cons_pos_rec}건 손실로 *크다*. "
            "안전(침묵0)을 최우선하고 recall 손실을 '후보제시/개별합성'으로 메울 수 "
            "있다면 합의 라우팅이 정당하다 — 무조건 신뢰가 아니라 *게이트*로 쓸 것."
        )
    else:
        verdict = "합의가 침묵실패를 줄이지 못함 — 신호로서 가치 없음(비권고)."
    lines.append(verdict)

    report = "\n".join(lines)
    print(report)

    return {
        "n": n,
        "nl_silent_fail": nl_sf,
        "consensus_silent_fail": cons_sf,
        "silent_fail_reduction": nl_sf - cons_sf,
        "nl_coverage": nl_cov,
        "consensus_coverage": cons_cov,
        "nl_recognized": nl_rec,
        "consensus_recognized": cons_rec,
        "positive_total": npos,
        "nl_positive_recall": nl_pos_rec,
        "consensus_positive_recall": cons_pos_rec,
        "positive_recall_loss": nl_pos_rec - cons_pos_rec,
        "disagreements": len(disagree),
        "report": report,
    }


def main() -> None:
    run()


if __name__ == "__main__":
    main()
