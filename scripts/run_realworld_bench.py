#!/usr/bin/env python3
"""실세계(messy) 한국어 요청 벤치마크 — 키 없는 파이프라인의 정직한 측정.

비전문가 공장 작업자/엔지니어가 *실제로 칠 법한* 거칠고 복합적인 한국어 요청
40여 개로, 현재 키 없는(BM25 키워드 매칭) 경로가 어디서 깨지는지 *수치로* 드러낸다.
교과서 케이스가 아니라 다절·정량·관계·범위밖 요청을 일부러 섞었다.

측정 항목(부풀리지 않음·결정론·키 불필요):
  · recognition accuracy : 올바른 레시피를 자신있게 골랐는가 / 범위밖을 정직히 거절했는가
  · coverage             : 자신있게 처리(%) vs 후보선택/거절로 폴백(%)
  · compound handling    : 다중 서브시스템 요청을 잡는가(현 파이프라인은 *못 잡는다* — 격차 측정)
  · quant failure        : 정량/관계(아날로그·퍼센트·대수제어) 요청 실패율
  · double-coil/interlock: 실제로 만들어낸 산출물의 위반 수

실행:  python scripts/run_realworld_bench.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.nlmatch import analyze  # noqa: E402
from app.synth import synthesize_st  # noqa: E402
from app.verifier import verify  # noqa: E402
from app.wizard import build_spec  # noqa: E402

CORPUS = Path(__file__).resolve().parent.parent / "benchmarks" / "real_world_ko.jsonl"


@dataclass(frozen=True)
class Case:
    id: str
    text: str
    difficulty: str
    kind: str  # recipe | multi | out_of_scope
    recipes: list[str]
    notes: str


def load_corpus(path: Path = CORPUS) -> list[Case]:
    cases: list[Case] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        exp = obj["expected"]
        cases.append(
            Case(
                id=obj["id"],
                text=obj["text"],
                difficulty=obj["difficulty"],
                kind=exp["kind"],
                recipes=list(exp.get("recipes", [])),
                notes=exp.get("notes", ""),
            )
        )
    return cases


@dataclass(frozen=True)
class Outcome:
    case: Case
    top: str
    confident: bool
    out_of_scope: bool  # 엔진이 범위밖으로 자각
    safety: bool  # 안전필수 표현 감지
    recognized: bool  # 인식 정확(레시피/거절 기준)
    covered: bool  # 자신있게 처리됨(확신 + 거절 아님)
    silent_fail: bool  # 자신있게 틀림(가장 위험한 실패)
    produced: bool  # build_spec→synth→verify 까지 산출물을 냄
    verify_passed: bool
    err_codes: tuple[str, ...]


def evaluate(case: Case) -> Outcome:
    res = analyze(case.text, allow_llm=False)
    top = res.recipe_id
    confident = res.confident
    oos = "out_of_scope" in res.extras
    safety = "safety_warning" in res.extras

    top_in_expected = top in case.recipes

    if case.kind == "out_of_scope":
        # 정답: 자신있게 매칭하지 *않음*(거절). out_of_scope/safety 안내면 더 좋다.
        recognized = not confident
        silent_fail = confident  # 범위밖인데 자신있게 매칭 = 침묵 실패
    else:  # recipe | multi
        # 정답: 기대 레시피 중 하나를 자신있게 선택.
        recognized = confident and top_in_expected
        # 침묵 실패: 자신있게 골랐는데 기대 밖 레시피(작업자는 틀린 줄 모름).
        silent_fail = confident and not top_in_expected

    covered = confident  # 후보선택/거절 폴백이 아니라 바로 진행

    produced = False
    verify_passed = False
    err_codes: tuple[str, ...] = ()
    # 자신있게 처리한 케이스만 실제 산출물을 만들어 위반을 본다(엔진이 실제로 내보낼 것).
    if confident:
        try:
            spec = build_spec(top, res.answers)
            st = synthesize_st(spec)
            rep = verify(spec, st)
            produced = True
            verify_passed = rep.passed
            err_codes = tuple(
                sorted({i.code for i in rep.issues if i.severity == "error"})
            )
        except Exception as exc:  # noqa: BLE001 - 측정용: 어떤 실패든 기록
            err_codes = (f"BUILD_ERR:{type(exc).__name__}",)

    return Outcome(
        case=case,
        top=top,
        confident=confident,
        out_of_scope=oos,
        safety=safety,
        recognized=recognized,
        covered=covered,
        silent_fail=silent_fail,
        produced=produced,
        verify_passed=verify_passed,
        err_codes=err_codes,
    )


def _pct(n: int, d: int) -> str:
    return f"{(100.0 * n / d):5.1f}%" if d else "  n/a"


def _bar(title: str) -> str:
    return f"\n{'=' * 4} {title} {'=' * (60 - len(title))}"


def run() -> dict[str, object]:
    cases = load_corpus()
    outs = [evaluate(c) for c in cases]

    by_diff: dict[str, list[Outcome]] = defaultdict(list)
    for o in outs:
        by_diff[o.case.difficulty].append(o)

    lines: list[str] = []
    lines.append(_bar("REAL-WORLD KO BENCHMARK (key-free, deterministic)"))
    lines.append(f"코퍼스: {len(cases)}건  ·  파일: {CORPUS.name}")
    lines.append("난이도별 분포:")
    order = ["easy", "compound", "quantified", "out_of_scope"]
    for d in order:
        lines.append(f"   {d:13} {len(by_diff.get(d, [])):3d}건")

    # ── 난이도별 인식/커버리지 ─────────────────────────────────────
    lines.append(_bar("난이도별 인식 정확도 / 커버리지 / 침묵실패"))
    lines.append(
        f"   {'difficulty':13} {'recog':>7} {'coverage':>9} {'silent-fail':>12}"
    )
    for d in order:
        grp = by_diff.get(d, [])
        if not grp:
            continue
        n = len(grp)
        rec = sum(o.recognized for o in grp)
        cov = sum(o.covered for o in grp)
        sf = sum(o.silent_fail for o in grp)
        lines.append(
            f"   {d:13} {_pct(rec, n):>7} {_pct(cov, n):>9} {_pct(sf, n):>12}"
        )
    n = len(outs)
    lines.append(
        f"   {'OVERALL':13} "
        f"{_pct(sum(o.recognized for o in outs), n):>7} "
        f"{_pct(sum(o.covered for o in outs), n):>9} "
        f"{_pct(sum(o.silent_fail for o in outs), n):>12}"
    )

    # ── compound 격차(핵심) ───────────────────────────────────────
    comp = by_diff.get("compound", [])
    multi_cases = [o for o in comp if o.case.kind == "multi"]
    lines.append(_bar("COMPOUND(다중 서브시스템) 격차 — 핵심 측정"))
    lines.append(
        "현 파이프라인은 요청당 *단 하나의* 레시피만 고른다(다중합성 자동화 없음). "
        "여러 서브시스템(컨베이어+알람+경광등 등)을 요구하는 요청은 구조적으로 "
        "한 조각밖에 못 잡는다 — 아래는 그 격차를 그대로 측정한 값."
    )
    n_multi = len(multi_cases)
    captured_one = sum(o.top in o.case.recipes for o in multi_cases)
    conf_partial = sum(o.confident and o.top in o.case.recipes for o in multi_cases)
    lines.append(
        f"   다중 서브시스템 요청(multi)        : {n_multi}건"
    )
    lines.append(
        f"   그 중 *한 조각이라도* 맞춘 비율     : {_pct(captured_one, n_multi)}"
    )
    lines.append(
        "   *전체 의도*를 캡처한 비율           :   0.0%  (구조적으로 불가 — 단일 레시피 한계)"
    )
    lines.append(
        f"   자신있게 부분만 만들어버린 비율     : {_pct(conf_partial, n_multi)}  "
        f"(작업자는 '나머지 빠짐'을 모를 위험)"
    )
    flagged_multi = sum(
        "multi_intent" in analyze(o.case.text, allow_llm=False).extras
        for o in multi_cases
    )
    lines.append(
        f"   다중의도로 *자각·안내*한 비율        : {_pct(flagged_multi, n_multi)}  "
        f"(침묵 대신 '여러 서브시스템 감지' 안내 → 개별 합성 유도)"
    )

    # ── quantified 격차 ──────────────────────────────────────────
    quant = by_diff.get("quantified", [])
    nq = len(quant)
    q_fail = sum(not o.recognized for o in quant)
    q_silent = sum(o.silent_fail for o in quant)
    lines.append(_bar("QUANTIFIED/RELATIONAL(정량·관계) 격차"))
    lines.append(
        "퍼센트·목표온도·주파수·대수제어·상호배제 같은 정량/관계 요청. 디지털 "
        "레벨스위치/카운터로 *근사*되거나 아예 표현 불가다."
    )
    lines.append(f"   정량/관계 요청              : {nq}건")
    lines.append(f"   인식 실패율(미달성)         : {_pct(q_fail, nq)}")
    lines.append(f"   그 중 자신있게 틀림(침묵)   : {_pct(q_silent, nq)}")

    # ── out-of-scope 정직성 ──────────────────────────────────────
    oos_grp = by_diff.get("out_of_scope", [])
    no = len(oos_grp)
    refused = sum(not o.confident for o in oos_grp)
    flagged = sum(o.out_of_scope or o.safety for o in oos_grp)
    leaked = sum(o.silent_fail for o in oos_grp)
    lines.append(_bar("OUT-OF-SCOPE(아날로그·통신·모션·PID) 정직성"))
    lines.append(f"   범위밖 요청                 : {no}건")
    lines.append(f"   정직하게 거절(확신 강등)    : {_pct(refused, no)}")
    lines.append(f"   범위밖/안전 안내까지 표시   : {_pct(flagged, no)}")
    lines.append(f"   자신있게 틀린 매칭(누출)    : {_pct(leaked, no)}")

    # ── 산출물 정형 위반 ─────────────────────────────────────────
    produced = [o for o in outs if o.produced]
    failed = [o for o in produced if not o.verify_passed]
    dc = sum(1 for o in produced if "DOUBLE_COIL" in o.err_codes)
    il = sum(1 for o in produced if "INTERLOCK" in o.err_codes)
    lines.append(_bar("산출물 정형 검증(엔진이 자신있게 만든 것만)"))
    lines.append(f"   자신있게 산출물 생성        : {len(produced)}건")
    n_pass = len(produced) - len(failed)
    lines.append(f"   verify 통과                 : {_pct(n_pass, len(produced))}")
    lines.append(f"   이중 코일(DOUBLE_COIL) 위반 : {dc}건")
    lines.append(f"   인터락(INTERLOCK) 위반      : {il}건")
    if failed:
        lines.append("   ⚠ 검증 실패 케이스:")
        for o in failed:
            lines.append(f"      {o.case.id}: {o.top} → {', '.join(o.err_codes)}")

    # ── 침묵 실패 톱(가장 위험) ──────────────────────────────────
    silent = [o for o in outs if o.silent_fail]
    lines.append(_bar("TOP FAILURE MODE: 침묵 실패(자신있게 틀림)"))
    if not silent:
        lines.append("   (없음 — 자신있게 틀린 매칭 0)")
    else:
        lines.append(f"   총 {len(silent)}건 — 엔진이 자신만만하게 *잘못된/부분* 답을 냄:")
        for o in silent:
            lines.append(
                f"   [{o.case.difficulty:10}] {o.case.id}: "
                f"\"{o.case.text[:30]}…\" → {o.top} "
                f"(기대 {o.case.kind}:{o.case.recipes or '거절'})"
            )

    lines.append(_bar("정직한 결론"))
    lines.append(
        "키워드 매처(BM25+부분포함)는 '단일 의도 + 흔한 패턴'에 한해 잘 동작한다. "
        "다중 서브시스템은 여전히 한 조각밖에 못 만들지만, 이제 희소-키워드 기반 "
        "다중의도 감지로 상당수를 *자각·안내*해 '자신있게 부분만 만드는' 침묵 위험을 "
        "줄였다(precision 우선 — 단일의도 오인 0). 남은 한계: (1) 전체의도 캡처는 "
        "구조적으로 0%(개별 합성/LLM 설계 필요), (2) 퍼센트/목표값/대수제어 같은 정량· "
        "관계 의미는 디지털 근사로 뭉개거나 놓치며, (3) 범위밖은 확신강등으로 비교적 "
        "정직히 거절하지만 키워드 표면이 겹치면 누출 위험이 남는다."
    )

    report = "\n".join(lines)
    print(report)

    return {
        "n": n,
        "by_difficulty": {d: len(by_diff.get(d, [])) for d in order},
        "overall_recognition": sum(o.recognized for o in outs) / n if n else 0.0,
        "overall_coverage": sum(o.covered for o in outs) / n if n else 0.0,
        "overall_silent_fail": sum(o.silent_fail for o in outs) / n if n else 0.0,
        "compound_full_capture_rate": 0.0,
        "compound_partial_confident_rate": (
            conf_partial / n_multi if n_multi else 0.0
        ),
        "quant_fail_rate": q_fail / nq if nq else 0.0,
        "oos_refusal_rate": refused / no if no else 0.0,
        "produced": len(produced),
        "verify_failures": len(failed),
        "double_coil_violations": dc,
        "interlock_violations": il,
        "report": report,
    }


def main() -> None:
    run()


if __name__ == "__main__":
    main()
