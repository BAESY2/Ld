#!/usr/bin/env python3
"""NL→컴파일→검증 정직 벤치 (MASTERPLAN G4) — 과장 금지, 측정만.

frame_to_spec 컴파일러가 *현장형 한국어* 제어 지시를 얼마나 *검증 가능하게* 컴파일
하는지를 난이도별로 정직하게 잰다. 자랑이 아니라 한계를 드러내는 게 목적이다.

파이프라인(키 불필요·결정론):
    text → frame_to_spec → (confident 면) synthesize_st → verify → detect_double_coils

난이도별 지표:
  - 커버리지(coverage)   : confident=True 로 컴파일된 비율(컴파일을 시도해 성공한 비율).
  - 검증통과율(verify)   : confident 컴파일 중 verify().passed 비율.
  - 이중코일0(no_dbl)    : confident 컴파일 중 이중코일이 0 인 비율.
  - 침묵실패(silent)     : *범위밖*(compile=False 라벨)인데 confident=True 로 컴파일 —
                           자신있게 틀린 위험한 경우(0 이어야 안전).
  - 정직보류(honest_hold): *범위밖*을 confident=False 로 정직하게 거절한 비율.

핵심 안전속성: (1) 침묵실패 = 0, (2) confident 컴파일은 전부 verify 통과·이중코일 0.
이 둘은 tests/test_compile_bench.py 가 단정한다.
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

_CORPUS = Path(__file__).resolve().parent.parent / "benchmarks" / "compile_corpus.jsonl"
_DIFFICULTY_ORDER = ("easy", "quantified", "compound", "out_of_scope")


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
    def coverage(self) -> float:
        """컴파일 커버리지 = confident 비율(전체 대비)."""
        return self.confident / self.total if self.total else 0.0

    @property
    def verify_rate(self) -> float:
        """confident 컴파일 중 verify 통과 비율(컴파일 없으면 1.0=공집합 진)."""
        return self.verified / self.confident if self.confident else 1.0

    @property
    def no_dbl_rate(self) -> float:
        """confident 컴파일 중 이중코일0 비율."""
        return self.no_double_coil / self.confident if self.confident else 1.0


def _run_case(rec: dict[str, object]) -> Case:
    """한 코퍼스 레코드를 컴파일→합성→검증해 Case 로 만든다(결정론)."""
    c = Case(
        text=str(rec["text"]),
        difficulty=str(rec["difficulty"]),
        expect_compile=bool(rec["compile"]),
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
            line = line.strip()
            if line:
                records.append(json.loads(line))
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
    lines.append("=== NL→컴파일→검증 정직 벤치 (frame_to_spec) ===")
    header = (
        f"{'난이도':<12} {'건수':>4} {'커버리지':>8} {'검증통과':>8} "
        f"{'이중코일0':>9} {'침묵실패':>8} {'정직보류':>8}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for diff, b in buckets.items():
        lines.append(
            f"{diff:<12} {b.total:>4} {b.coverage:>7.0%} {b.verify_rate:>7.0%} "
            f"{b.no_dbl_rate:>8.0%} {b.silent_failures:>8} {b.honest_holds:>8}"
        )

    total = sum(b.total for b in buckets.values())
    confident = sum(b.confident for b in buckets.values())
    verified = sum(b.verified for b in buckets.values())
    no_dbl = sum(b.no_double_coil for b in buckets.values())
    silent = total_silent_failures(buckets)
    oos = sum(b.total - b.expect_compile for b in buckets.values())
    holds = sum(b.honest_holds for b in buckets.values())
    lines.append("-" * len(header))
    lines.append(
        f"전체 {total}건 · confident {confident}건 · verify통과 {verified}/{confident} · "
        f"이중코일0 {no_dbl}/{confident}"
    )
    lines.append(
        f"범위밖 {oos}건 · 정직보류 {holds}/{oos} · 침묵실패(자신있게 틀림) {silent}"
    )

    lines.append("")
    lines.append("정직한 결론:")
    if silent == 0:
        lines.append(
            "  - 침묵실패 0: 범위밖(아날로그PID·모션·통신·잡담)을 단 한 건도 confident 로"
        )
        lines.append(
            "    컴파일하지 않았다. 모르는 것은 거절한다(거짓 합성 없음)."
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
    lines.append("  - 아날로그 PID/PI 루프, 모션·서보·토크·위치 제어는 컴파일 대상 아님(거절).")
    lines.append("  - 통신(Modbus 등)·HMI 트렌드·프로그램 전송·잡담은 제어 의도 아님(거절).")
    lines.append(
        "  - 미등록 어휘(예 '비상정지')·끊긴 종결('켜주세요')·공백분리 수량('80 도')은"
    )
    lines.append(
        "    coverage 가 떨어져 confident=False 가 된다 → 컴파일은 못 하지만 *조용히 틀리지는*"
    )
    lines.append("    않는다(어휘를 늘리면 커버리지가 올라간다 — 레시피가 아니라 원시어휘 확장).")
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
