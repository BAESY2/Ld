#!/usr/bin/env python3
"""적대·대규모 NL→컴파일→검증 정직 벤치 (compile_bench 의 무편향·규모 보완).

기존 compile_corpus(52건)의 자가채점 약점 — *규모*와 *적대성* — 을 보완한다.
benchmarks/compile_adversarial.jsonl(110건)로 frame_to_spec 컴파일러를 난이도별로
정직하게 측정한다. 자랑이 아니라 한계와 *침묵실패(자신있게 틀림)* 를 드러내는 게 목적.

파이프라인(키 불필요·100% 결정론):
    text → frame_to_spec → (confident 면) synthesize_st → verify → detect_double_coils

함정 설계(코퍼스):
  - oos_invocab : in-vocab 단어가 섞인 *범위밖*(PID/모션/통신/HMI…) → 반드시 거절(False).
  - oos_chatter : 잡담·문서요청·IT — 제어 의도 아님 → 거절.
  - adversarial_typo : 띄어쓰기 파괴·오타·별칭·인스턴스 혼합 → 견고하게 컴파일.
  - easy/quantified/compound : 단일~복합 다절(수위+카운터+알람+다중출력).

난이도별 지표:
  - 커버리지(coverage)   : 기대군 중 confident=True 로 컴파일된 비율.
  - 검증통과율(verify)   : confident 컴파일 중 verify().passed 비율.
  - 이중코일0(no_dbl)    : confident 컴파일 중 이중코일이 0 인 비율.
  - 침묵실패(silent)     : *범위밖*인데 confident=True — 자신있게 틀린 위험(0 이어야 안전).
  - 정직거절(honest_hold): *범위밖*을 confident=False 로 정직하게 거절한 비율.

핵심 안전속성: (1) 침묵실패 = 0, (2) confident 컴파일은 전부 verify 통과·이중코일 0.
이 둘은 tests/test_compile_adversarial.py 가 단정한다.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.compile_frame import frame_to_spec  # noqa: E402
from app.memory_map import detect_double_coils  # noqa: E402
from app.synth import synthesize_st  # noqa: E402
from app.verifier import verify  # noqa: E402

_CORPUS = (
    Path(__file__).resolve().parent.parent / "benchmarks" / "compile_adversarial.jsonl"
)
# 난이도 출력 순서(컴파일 기대군 → 범위밖 함정군).
_DIFFICULTY_ORDER = (
    "easy",
    "quantified",
    "compound",
    "adversarial_typo",
    "oos_invocab",
    "oos_chatter",
)


@dataclass
class Case:
    """코퍼스 한 줄 + 컴파일·검증 결과(결정론)."""

    text: str
    difficulty: str
    expect_compile: bool  # 라벨: 컴파일 기대 여부
    note: str = ""
    confident: bool = False
    verified: bool = False
    double_coil: bool = False

    @property
    def silent_failure(self) -> bool:
        """범위밖(컴파일 비기대)인데 confident 로 컴파일 — 자신있게 틀림(위험)."""
        return (not self.expect_compile) and self.confident

    @property
    def honest_hold(self) -> bool:
        """범위밖을 confident=False 로 정직하게 거절."""
        return (not self.expect_compile) and (not self.confident)

    @property
    def missed_compile(self) -> bool:
        """컴파일 기대인데 confident=False — 침묵실패는 아니나 커버리지 손실(정직 기권)."""
        return self.expect_compile and (not self.confident)


@dataclass
class Bucket:
    """난이도 한 그룹의 집계."""

    total: int = 0
    confident: int = 0
    verified: int = 0
    no_double_coil: int = 0
    expect_compile: int = 0
    silent_failures: int = 0
    honest_holds: int = 0
    cases: list[Case] = field(default_factory=list)

    def add(self, c: Case) -> None:
        self.total += 1
        self.cases.append(c)
        if c.expect_compile:
            self.expect_compile += 1
        if c.confident:
            self.confident += 1
            if c.verified:
                self.verified += 1
            if not c.double_coil:
                self.no_double_coil += 1
        if c.silent_failure:
            self.silent_failures += 1
        if c.honest_hold:
            self.honest_holds += 1

    @property
    def out_of_scope(self) -> int:
        """이 버킷의 범위밖(컴파일 비기대) 건수."""
        return self.total - self.expect_compile

    @property
    def coverage(self) -> float:
        """기대군 대비 confident 비율(범위밖만 있는 버킷은 1.0=공집합 진)."""
        return self.confident / self.expect_compile if self.expect_compile else 1.0

    @property
    def verify_rate(self) -> float:
        """confident 컴파일 중 verify 통과 비율(컴파일 없으면 1.0=공집합 진)."""
        return self.verified / self.confident if self.confident else 1.0

    @property
    def no_dbl_rate(self) -> float:
        """confident 컴파일 중 이중코일0 비율."""
        return self.no_double_coil / self.confident if self.confident else 1.0

    @property
    def honest_hold_rate(self) -> float:
        """범위밖 중 정직거절 비율(범위밖 없으면 1.0)."""
        return self.honest_holds / self.out_of_scope if self.out_of_scope else 1.0


def _run_case(rec: dict[str, object]) -> Case:
    """한 코퍼스 레코드를 컴파일→합성→검증해 Case 로 만든다(결정론)."""
    c = Case(
        text=str(rec["text"]),
        difficulty=str(rec["difficulty"]),
        expect_compile=bool(rec["expect_compile"]),
        note=str(rec.get("note", "")),
    )
    result = frame_to_spec(c.text)
    c.confident = result.confident
    if c.confident:
        st = synthesize_st(result.spec)
        c.double_coil = bool(detect_double_coils(st))
        c.verified = verify(result.spec, st).passed
    return c


def load_corpus(path: Path = _CORPUS) -> list[dict[str, object]]:
    """JSONL 코퍼스를 로드한다(빈 줄 무시)."""
    records: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))
    return records


def run(path: Path = _CORPUS) -> dict[str, Bucket]:
    """코퍼스 전체를 돌려 난이도별 Bucket 을 만든다(난이도 순 정렬, 결정론)."""
    buckets: dict[str, Bucket] = defaultdict(Bucket)
    for rec in load_corpus(path):
        case = _run_case(rec)
        buckets[case.difficulty].add(case)
    ordered: dict[str, Bucket] = {}
    for diff in _DIFFICULTY_ORDER:
        if diff in buckets:
            ordered[diff] = buckets[diff]
    for diff in sorted(buckets):  # 알 수 없는 난이도도 결정론적으로 뒤에 붙임
        if diff not in ordered:
            ordered[diff] = buckets[diff]
    return ordered


def total_silent_failures(buckets: dict[str, Bucket]) -> int:
    return sum(b.silent_failures for b in buckets.values())


def all_confident_safe(buckets: dict[str, Bucket]) -> bool:
    """모든 confident 컴파일이 verify 통과 + 이중코일0 인가(핵심 안전속성)."""
    return all(
        c.verified and not c.double_coil
        for b in buckets.values()
        for c in b.cases
        if c.confident
    )


def format_report(buckets: dict[str, Bucket]) -> str:
    """정직한 결론 텍스트를 포함한 표를 만든다(무엇을 못 하는지 명시)."""
    lines: list[str] = []
    lines.append("=== 적대·대규모 NL→컴파일→검증 정직 벤치 (frame_to_spec) ===")
    header = (
        f"{'난이도':<16} {'건수':>4} {'기대':>4} {'커버리지':>8} {'검증통과':>8} "
        f"{'이중코일0':>9} {'정직거절':>8} {'침묵실패':>8}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for diff, b in buckets.items():
        lines.append(
            f"{diff:<16} {b.total:>4} {b.expect_compile:>4} {b.coverage:>7.0%} "
            f"{b.verify_rate:>7.0%} {b.no_dbl_rate:>8.0%} {b.honest_hold_rate:>7.0%} "
            f"{b.silent_failures:>8}"
        )

    total = sum(b.total for b in buckets.values())
    confident = sum(b.confident for b in buckets.values())
    verified = sum(b.verified for b in buckets.values())
    no_dbl = sum(b.no_double_coil for b in buckets.values())
    silent = total_silent_failures(buckets)
    oos = sum(b.out_of_scope for b in buckets.values())
    holds = sum(b.honest_holds for b in buckets.values())
    expect = sum(b.expect_compile for b in buckets.values())
    missed = sum(1 for b in buckets.values() for c in b.cases if c.missed_compile)
    lines.append("-" * len(header))
    lines.append(
        f"전체 {total}건 · 기대 {expect}건 · confident {confident}건 · "
        f"verify통과 {verified}/{confident} · 이중코일0 {no_dbl}/{confident}"
    )
    lines.append(
        f"범위밖 {oos}건 · 정직거절 {holds}/{oos} · 침묵실패(자신있게 틀림) {silent} · "
        f"미컴파일(정직기권) {missed}/{expect}"
    )

    lines.append("")
    lines.append("정직한 결론:")
    if silent == 0:
        lines.append(
            "  - 침묵실패 0: 범위밖(in-vocab 섞인 PID·모션·통신·HMI·잡담)을 단 한 건도"
        )
        lines.append(
            "    confident 로 컴파일하지 않았다. 모르는 것은 거절한다(거짓 합성 0)."
        )
    else:
        lines.append(
            f"  - ⚠ 침묵실패 {silent}건: 범위밖을 자신있게 컴파일했다 — 즉시 점검 필요."
        )
    if all_confident_safe(buckets):
        lines.append(
            "  - confident 컴파일은 전부 verify 통과 + 이중코일0(합성→검증 게이트가 보증)."
        )
    else:
        lines.append("  - ⚠ confident 컴파일 중 verify 실패 또는 이중코일 발생 — 회귀.")
    lines.append("")
    lines.append("한계(못 하는 것 — 측정으로 드러난 범위):")
    lines.append(
        "  - in-vocab 명사(모터·히터·밸브)가 섞여도 PID/서보위치/토크/통신 등 *제어 클래스*"
    )
    lines.append("    밖이면 미등록 어휘가 coverage 를 낮춰 거절한다 — 침묵실패가 아니다.")
    lines.append(
        "  - 미등록 종결('잡아·움직여')·신호어('닿으면')는 기대 컴파일이라도 정직 기권."
    )
    lines.append("    어휘를 늘리면 커버리지가 오른다(레시피가 아니라 원시어휘 확장).")
    return "\n".join(lines)


def main() -> int:
    buckets = run()
    print(format_report(buckets))
    # 안전속성 위반 시 비정상 종료(CI 가드).
    if total_silent_failures(buckets) != 0 or not all_confident_safe(buckets):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
