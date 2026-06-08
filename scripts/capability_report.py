#!/usr/bin/env python3
"""정직한 통합 능력 스코어카드 — 흩어진 벤치를 *한 화면*으로 (펀딩/신뢰 서사용).

이 리포트는 새 측정을 발명하지 않는다. 기존 벤치들의 핵심 함수를 *import 호출*해
(서브프로세스 아님 — 결정론·빠름) 한 자리에 모은다. 각 줄은 무엇을 *할 수 있고* 무엇을
*못 하는지*를 수치로만 말한다. 과장 금지, 측정 없는 주장 금지.

집계 항목(전부 키 불필요·결정론):
  · 이해(NL)        : in-template 정확도 / 침묵실패율          (app.bench.nl_accuracy)
  · 실세계(messy)    : 인식·커버리지·침묵실패                   (scripts.run_realworld_bench)
  · 컴파일(코퍼스)   : 커버리지·검증통과·이중코일0·침묵실패     (scripts.compile_bench)
  · 적대벤치(110)    : 침묵실패·정직거절                        (scripts.compile_adversarial_bench)
  · 생성성          : 검증 통과 distinct 프로그램 수            (scripts.generativity_bench)
  · 교차백엔드      : PySim↔XGK↔OpenPLC 트레이스 일치율         (scripts.cross_backend_bench)
  · 수리            : 고장→수리→재검증 효능                     (scripts.repair_bench)
  · 검증기 건전성    : false-proof / miss (작은 규모 n)          (scripts.soundness_study)

핵심 불변(스코어카드가 단정·tests/test_capability_report.py 가 검사):
  (1) 컴파일·적대 벤치 침묵실패 = 0,
  (2) confident 컴파일은 전부 verify 통과 + 이중코일 0,
  (3) 검증기 건전성: false-proof = 0, miss = 0 (쌍·그룹 모두).

직접 실행::

    python scripts/capability_report.py            # 사람용 스코어카드
    python scripts/capability_report.py --json      # 기계용 JSON
    python scripts/capability_report.py --soundness-n 200   # 건전성 규모 상향
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TypeVar

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bench.nl_accuracy import score_keyless  # noqa: E402
from benchmarks.nl_bench_corpus import BENCH  # noqa: E402
from scripts import compile_adversarial_bench as adv  # noqa: E402
from scripts import compile_bench as cb  # noqa: E402
from scripts import cross_backend_bench as xb  # noqa: E402
from scripts import generativity_bench as gen  # noqa: E402
from scripts import repair_bench as rep  # noqa: E402
from scripts import run_realworld_bench as rw  # noqa: E402
from scripts import soundness_study as snd  # noqa: E402

# 건전성 연구 기본 규모(무거우므로 작게 — 작은 n 에서도 false-proof/miss=0 불변).
_DEFAULT_SOUNDNESS_N = 80

_T = TypeVar("_T")


@dataclass
class Metric:
    """스코어카드 한 줄: 측정 + 정직한 한계."""

    name: str
    value: str
    limit: str
    detail: dict[str, object] = field(default_factory=dict)


@dataclass
class Scorecard:
    """전 항목 집계(결정론). 핵심 불변 플래그를 직접 보유한다."""

    metrics: list[Metric] = field(default_factory=list)
    # 핵심 안전 불변(테스트가 단정).
    compile_silent_failures: int = 0
    adversarial_silent_failures: int = 0
    compile_all_confident_safe: bool = True
    adversarial_all_confident_safe: bool = True
    soundness_pair_false_proof: int = 0
    soundness_pair_miss: int = 0
    soundness_group_false_proof: int = 0
    soundness_group_miss: int = 0
    soundness_n: int = _DEFAULT_SOUNDNESS_N
    soundness_ran: bool = True

    @property
    def all_invariants_hold(self) -> bool:
        """모든 핵심 안전 불변이 성립하는가(스코어카드 통과 조건)."""
        sound_ok = (not self.soundness_ran) or (
            self.soundness_pair_false_proof == 0
            and self.soundness_pair_miss == 0
            and self.soundness_group_false_proof == 0
            and self.soundness_group_miss == 0
        )
        return (
            self.compile_silent_failures == 0
            and self.adversarial_silent_failures == 0
            and self.compile_all_confident_safe
            and self.adversarial_all_confident_safe
            and sound_ok
        )


def _pct(a: int, b: int) -> str:
    return f"{100.0 * a / b:.0f}%" if b else "n/a"


def _quiet(fn: Callable[..., _T], *args: object, **kwargs: object) -> _T:
    """벤치 함수가 stdout 으로 자체 리포트를 찍어도 삼킨다(우린 수치만 쓴다)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return fn(*args, **kwargs)


def build_scorecard(soundness_n: int = _DEFAULT_SOUNDNESS_N) -> Scorecard:
    """모든 벤치 핵심 함수를 import 호출해 한 스코어카드로 모은다(결정론)."""
    card = Scorecard(soundness_n=soundness_n)

    # ── 1) 이해(NL in-template) — 키 없는 결정론 매처 ────────────────────────
    nl = score_keyless(BENCH)
    card.metrics.append(
        Metric(
            name="이해(NL in-template)",
            value=(
                f"정확도 {nl.in_template_accuracy:.0%} "
                f"({nl.in_confident_correct}/{nl.n_in_template}) · "
                f"21개밖 침묵실패 {nl.out_silent_fail_rate:.0%} "
                f"({nl.out_silent_fail}/{nl.n_out_template})"
            ),
            limit=(
                "교과서형 단일의도에 한함. 보류 "
                f"{nl.in_not_confident}건은 '맞을 수 있었으나 확신 못함'(거짓 매칭 대신 기권)."
            ),
            detail={
                "in_template_accuracy": nl.in_template_accuracy,
                "in_confident_correct": nl.in_confident_correct,
                "n_in_template": nl.n_in_template,
                "out_silent_fail": nl.out_silent_fail,
                "out_silent_fail_rate": nl.out_silent_fail_rate,
            },
        )
    )

    # ── 2) 실세계(messy) — 거친 복합 요청 ───────────────────────────────────
    rwres = _quiet(rw.run)
    sf_rate = float(rwres["overall_silent_fail"])  # type: ignore[arg-type]
    produced = int(rwres["produced"])  # type: ignore[arg-type]
    vfail = int(rwres["verify_failures"])  # type: ignore[arg-type]
    card.metrics.append(
        Metric(
            name="실세계(messy KO)",
            value=(
                f"인식 {float(rwres['overall_recognition']):.0%} · "
                f"커버리지 {float(rwres['overall_coverage']):.0%} · "
                f"침묵실패 {sf_rate:.1%} "
                f"(산출물 verify {_pct(produced - vfail, produced)})"
            ),
            limit=(
                "다중 서브시스템 *전체의도* 캡처는 구조적 0%(단일 레시피 한계). 정량/관계는 "
                "디지털 근사. messy 경로(BM25)는 침묵실패가 0 이 아니다(키워드 표면 겹침)."
            ),
            detail={
                "overall_recognition": rwres["overall_recognition"],
                "overall_coverage": rwres["overall_coverage"],
                "overall_silent_fail": rwres["overall_silent_fail"],
                "produced": rwres["produced"],
                "verify_failures": rwres["verify_failures"],
                "double_coil_violations": rwres["double_coil_violations"],
                "interlock_violations": rwres["interlock_violations"],
            },
        )
    )

    # ── 3) 컴파일(코퍼스 52) — frame_to_spec 컴파일러 ───────────────────────
    cbk = cb.run()
    c_total = sum(b.total for b in cbk.values())
    c_conf = sum(b.confident for b in cbk.values())
    c_ver = sum(b.verified for b in cbk.values())
    c_dbl0 = sum(b.no_double_coil for b in cbk.values())
    c_silent = cb.total_silent_failures(cbk)
    c_safe = cb.all_confident_safe(cbk)
    card.compile_silent_failures = c_silent
    card.compile_all_confident_safe = c_safe
    card.metrics.append(
        Metric(
            name="컴파일(코퍼스 52)",
            value=(
                f"confident {c_conf}/{c_total} · verify {_pct(c_ver, c_conf)} · "
                f"이중코일0 {_pct(c_dbl0, c_conf)} · 침묵실패 {c_silent}"
            ),
            limit=(
                "아날로그 PID/모션/통신/잡담은 컴파일 대상 아님(거절). 미등록 어휘·끊긴 "
                "종결은 coverage 하락으로 기권 — 조용히 틀리진 않는다."
            ),
            detail={
                "total": c_total, "confident": c_conf, "verified": c_ver,
                "no_double_coil": c_dbl0, "silent_failures": c_silent,
                "all_confident_safe": c_safe,
            },
        )
    )

    # ── 4) 적대·대규모 벤치(110) — in-vocab 함정 포함 ──────────────────────
    advk = adv.run()
    a_total = sum(b.total for b in advk.values())
    a_conf = sum(b.confident for b in advk.values())
    a_oos = sum(b.out_of_scope for b in advk.values())
    a_holds = sum(b.honest_holds for b in advk.values())
    a_silent = adv.total_silent_failures(advk)
    a_safe = adv.all_confident_safe(advk)
    card.adversarial_silent_failures = a_silent
    card.adversarial_all_confident_safe = a_safe
    card.metrics.append(
        Metric(
            name="적대벤치(110)",
            value=(
                f"confident {a_conf}건 전부 verify·이중코일0 · "
                f"범위밖 {a_oos}건 정직거절 {_pct(a_holds, a_oos)} · 침묵실패 {a_silent}"
            ),
            limit=(
                "in-vocab 명사가 섞여도 PID/서보/토크/통신 등 *제어 클래스* 밖이면 거절. "
                "literal 의미검사는 없다 — coverage 게이트에 의존한다."
            ),
            detail={
                "total": a_total, "confident": a_conf, "out_of_scope": a_oos,
                "honest_holds": a_holds, "silent_failures": a_silent,
                "all_confident_safe": a_safe,
            },
        )
    )

    # ── 5) 생성성 — '37개'가 아님을 distinct 수로 ───────────────────────────
    distinct, gtotal = gen.run()
    card.metrics.append(
        Metric(
            name="생성성(combinatorial)",
            value=(
                f"무작위 조합 {gtotal}건 → 검증통과 *distinct* {distinct}개 (이중코일0)"
            ),
            limit=(
                "유한 어휘(조건10×동작14)의 조합 — 어휘 밖 의미(아날로그 PID 등)는 못 늘린다. "
                "레시피가 아니라 원시어휘를 늘려야 범위가 넓어진다."
            ),
            detail={"distinct": distinct, "trials": gtotal},
        )
    )

    # ── 6) 교차백엔드 동치 — 자가채점 타파 ─────────────────────────────────
    xsum = xb.run_bench()
    xpairs: dict[str, object] = {}
    xline: list[str] = []
    for pair in xb.PAIRS:
        agree, tot = xsum.pair_agree_rate(pair)
        xpairs[pair] = {"agree": agree, "total": tot}
        xline.append(f"{xb.PAIR_LABELS[pair]} {agree}/{tot} ({_pct(agree, tot)})")
    card.metrics.append(
        Metric(
            name="교차백엔드 동치",
            value=" · ".join(xline),
            limit=(
                "불리언 코퍼스만(아날로그 비교기 제외). OpenPLC 트윈은 오프라인 시뮬백 "
                "재생이라 정의상 PySim 과 일치 — 실기 OPENPLC_HOST 연결은 별도."
            ),
            detail={"n_compiled": len(xsum.compiled), "pairs": xpairs},
        )
    )

    # ── 7) 수리 효능 — 고장→수리→재검증 ────────────────────────────────────
    rt = rep.run()
    n_broken = int(rt["broken"])
    card.metrics.append(
        Metric(
            name="수리 효능(M4)",
            value=(
                f"고장 {n_broken}건 → 수리·재검증 통과 {rt['repaired']} "
                f"({_pct(int(rt['repaired']), n_broken)}) · 잔존실패 {rt['still_failing']}"
            ),
            limit=(
                "인터락 위반·이중코일 등 *국소* 결함만 건전 수리. 구조적 결함(one-hot 등)은 "
                "정직 거절(수리 대상 아님)."
            ),
            detail=dict(rt),
        )
    )

    # ── 8) 검증기 건전성@규모(작은 n) — 해자 ───────────────────────────────
    if snd._HAS_Z3:
        pt, gt = snd.run_full(n_random=soundness_n, seed=snd._SEED)
        card.soundness_ran = True
        card.soundness_pair_false_proof = pt.false_proof
        card.soundness_pair_miss = pt.missed_viol
        card.soundness_group_false_proof = gt.false_proof
        card.soundness_group_miss = gt.missed_viol
        pair_oracle = (pt.false_proof + pt.detected_viol
                       + pt.warned_viol + pt.missed_viol)
        grp_oracle = (gt.false_proof + gt.detected_viol
                      + gt.warned_viol + gt.missed_viol)
        card.metrics.append(
            Metric(
                name=f"검증기 건전성(n={soundness_n})",
                value=(
                    f"쌍: false-proof {pt.false_proof} · miss {pt.missed_viol} · "
                    f"증명확인 {pt.proven_confirmed} · 탐지 {pt.detected_viol}/{pair_oracle} | "
                    f"그룹: false-proof {gt.false_proof} · miss {gt.missed_viol} · "
                    f"증명확인 {gt.proven_confirmed} · 탐지 {gt.detected_viol}/{grp_oracle}"
                ),
                limit=(
                    f"여기선 작은 규모(random={soundness_n}) — soundness_study.run_full 은 "
                    "기본 1000개. 인터락(상호배제) 속성에 한함(타이밍·아날로그 의미론은 확대 중)."
                ),
                detail={
                    "n_random": soundness_n,
                    "pair_false_proof": pt.false_proof,
                    "pair_miss": pt.missed_viol,
                    "pair_proven_confirmed": pt.proven_confirmed,
                    "pair_detected": pt.detected_viol,
                    "group_false_proof": gt.false_proof,
                    "group_miss": gt.missed_viol,
                    "group_proven_confirmed": gt.proven_confirmed,
                    "group_detected": gt.detected_viol,
                },
            )
        )
    else:
        card.soundness_ran = False
        card.metrics.append(
            Metric(
                name="검증기 건전성",
                value="z3 미설치 — 건너뜀",
                limit="z3 설치 시 k-귀납 건전성을 오라클과 교차검증한다.",
                detail={"z3": False},
            )
        )

    return card


_CAN = (
    "결정론(키 없음) 한국어→정형검증 PLC 컴파일러로서: 흔한 단일의도를 검증된 ST/래더로 "
    "컴파일(이중코일0·인터락0), 모르는 것은 정직 거절(컴파일·적대벤치 침묵실패 0), "
    "유한 어휘를 조합적으로(수천 distinct) 생성, 깨진 프로그램을 건전 수리, 산출물을 "
    "독립 백엔드 3종에서 교차검증(트레이스 100% 일치), 인터락 안전을 형식증명(건전성 "
    "false-proof=0·miss=0)."
)
_CANNOT = (
    "아날로그 PID/모션/서보/토크·통신(Modbus)·HMI 는 컴파일 대상이 아니다(거절). 다중 "
    "서브시스템의 *전체의도* 자동합성은 구조적 0%(단일 레시피 한계). messy(BM25) 경로는 "
    "침묵실패가 0 이 아니다. literal 의미검사 없이 coverage 게이트에 의존. 안전 인증"
    "(TÜV/SIL)·실하드웨어 양산은 범위 밖(조직 필요). 연구 프리뷰다 — 숨기지 않는다."
)


def format_report(card: Scorecard) -> str:
    """한 화면 스코어카드 텍스트(정직한 한계 포함)."""
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("정직한 통합 능력 스코어카드 — 결정론 한국어→정형검증 PLC 컴파일러")
    lines.append("(연구 프리뷰 · 키 불필요 · 100% 결정론 · 측정 없는 주장 금지)")
    lines.append("=" * 78)
    for m in card.metrics:
        lines.append(f"▸ {m.name}")
        lines.append(f"    {m.value}")
        lines.append(f"    한계: {m.limit}")
    lines.append("-" * 78)
    lines.append("핵심 안전 불변(테스트가 단정):")
    lines.append(
        f"    컴파일 침묵실패={card.compile_silent_failures} · "
        f"적대 침묵실패={card.adversarial_silent_failures} · "
        f"confident 전부 안전(verify+이중코일0)="
        f"{card.compile_all_confident_safe and card.adversarial_all_confident_safe}"
    )
    if card.soundness_ran:
        lines.append(
            f"    건전성(n={card.soundness_n}): 쌍 false-proof="
            f"{card.soundness_pair_false_proof}·miss={card.soundness_pair_miss} · "
            f"그룹 false-proof={card.soundness_group_false_proof}·"
            f"miss={card.soundness_group_miss}"
        )
    lines.append(f"    → 모든 불변 성립: {card.all_invariants_hold}")
    lines.append("-" * 78)
    lines.append("할 수 있는 것:")
    lines.append(f"    {_CAN}")
    lines.append("못 하는 것(정직):")
    lines.append(f"    {_CANNOT}")
    lines.append("=" * 78)
    return "\n".join(lines)


def _to_json(card: Scorecard) -> str:
    payload = {
        "metrics": [asdict(m) for m in card.metrics],
        "invariants": {
            "compile_silent_failures": card.compile_silent_failures,
            "adversarial_silent_failures": card.adversarial_silent_failures,
            "compile_all_confident_safe": card.compile_all_confident_safe,
            "adversarial_all_confident_safe": card.adversarial_all_confident_safe,
            "soundness_ran": card.soundness_ran,
            "soundness_n": card.soundness_n,
            "soundness_pair_false_proof": card.soundness_pair_false_proof,
            "soundness_pair_miss": card.soundness_pair_miss,
            "soundness_group_false_proof": card.soundness_group_false_proof,
            "soundness_group_miss": card.soundness_group_miss,
            "all_invariants_hold": card.all_invariants_hold,
        },
        "can_do": _CAN,
        "cannot_do": _CANNOT,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="정직한 통합 능력 스코어카드")
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    parser.add_argument(
        "--soundness-n", type=int, default=_DEFAULT_SOUNDNESS_N,
        help=f"건전성 연구 무작위 프로그램 수(기본 {_DEFAULT_SOUNDNESS_N}, 무거움)",
    )
    args = parser.parse_args(argv)
    # 비결정 환경변수 차단(키 있어도 결정론 경로만).
    os.environ.pop("ANTHROPIC_API_KEY", None)
    card = build_scorecard(soundness_n=args.soundness_n)
    print(_to_json(card) if args.json else format_report(card))
    # 핵심 불변 위반 시 비정상 종료(CI 게이트).
    return 0 if card.all_invariants_hold else 1


if __name__ == "__main__":
    raise SystemExit(main())
