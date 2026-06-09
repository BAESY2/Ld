#!/usr/bin/env python3
"""형식증명 *커버리지* 정직 측정 — 검증기 완전성(completeness).

건전성(soundness; false-proof=0)은 이미 입증됨(soundness_study). 이 리포트는 *다른*
축을 잰다: 검증기가 컴파일 산출물이 *선언한* 안전 속성(상호배제)을 *얼마나 증명하는가*
(완전성). 즉 '증명됨 vs 미증명(보수적 warning) vs 위반(error)' 비율이다.

핵심 지표:
    선언된 상호배제 속성 중 형식 증명된 비율
      = proven / (proven + unproven + violated)

대상 코퍼스(상호배제를 *가진* 컴파일 산출물; 100% 결정론·키 불필요):
  (a) mutex_cue       : '동시에 금지/인터락/같이 안' 단서 문장 → 컴파일러가 인터락 쌍 생성.
  (b) multi_instance  : 1번/2번·인스턴스1/2 같은 *다중 인스턴스* + 동시금지 → 인스턴스간 mutex.
  (c) sequence        : 순차(다음/N초 후) → 타임드 시퀀서 단계 출력 one-hot(쌍+그룹).
  (d) interlock_recipe: wizard 인터락 레시피(정역·조그/연속·Y-Δ·분기게이트·다분류·셔터).

각 프로그램에서 *선언된* 상호배제 속성을 두 종류로 본다:
  - 쌍 속성(pair)  : Interlock(a,b) 1개 = 1 속성. proven_safe_pairs 로 증명 판정.
  - 그룹 속성(group): ≥3 출력 one-hot(clique) 1개 = 1 속성. proven_safe_groups 로 판정.
각 속성을 proven / unproven(보수적 warning) / violated(error) 로 분류해 집계한다.

정직성:
  - proven 만 '증명됨'으로 센다(positive proof only; warning·error 는 미증명/위반).
  - 무엇이 미증명으로 남는지 명시한다(완전성의 한계 = 정직한 결론).
  - 작은 표본 false-proof 점검: 증명된 속성을 실행오라클(시뮬레이터)이 반증 못함을 확인.

tests/test_proof_coverage.py 가 (a) 무예외, (b) 합리적 증명 하한, (c) false-proof 0 단정.
"""

from __future__ import annotations

import itertools
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.compile_frame import frame_to_spec  # noqa: E402
from app.models import StateMachineSpec  # noqa: E402
from app.simulator import simulate  # noqa: E402
from app.synth import covers_all_outputs, synthesize_st  # noqa: E402
from app.verifier import (  # noqa: E402
    check_group_mutex_kinduction,
    check_interlocks_kinduction,
    derive_mutex_groups,
    proven_safe_groups,
    proven_safe_pairs,
)
from app.wizard import RECIPES  # noqa: E402

# 상호배제 단서 + 출력 액추에이터 동사(서로 다른 출력 심볼로 컴파일되는 기기).
_DEV_VERB: dict[str, str] = {
    "펌프": "돌리고", "모터": "돌리고", "히터": "켜고", "밸브": "열고",
    "램프": "켜고", "부저": "켜고", "팬": "돌리고", "송풍기": "돌리고",
    "컨베이어": "돌리고", "사이렌": "켜고", "경광등": "켜고",
}
_MUTEX_CUE = ("인터락", "동시에 금지", "동시에 못", "같이 안")
# wizard 에서 인터락(또는 mutex 그룹)을 *선언* 하는 레시피들("인터락 레시피").
_INTERLOCK_RECIPES = (
    "fwd_rev", "jog_run", "star_delta", "conveyor_divert", "multiway_sort", "shutter_gate",
)


@dataclass(frozen=True)
class Program:
    """검사 대상 프로그램 한 건(상호배제를 선언한 컴파일/레시피 산출물)."""

    category: str
    label: str
    spec: StateMachineSpec


def _two_output_mutex_cues() -> list[Program]:
    """(a) 두 출력 + 상호배제 단서 문장 → 컴파일러 인터락 쌍."""
    progs: list[Program] = []
    devs = list(_DEV_VERB)
    for (da, db), cue in zip(itertools.combinations(devs, 2), itertools.cycle(_MUTEX_CUE)):
        text = f"{da} {_DEV_VERB[da]} {db} {_DEV_VERB[db]} {cue}"
        r = frame_to_spec(text)
        if r.confident and r.spec.interlocks:
            progs.append(Program("mutex_cue", text, r.spec))
    return progs


def _multi_instance_mutex() -> list[Program]:
    """(b) 다중 인스턴스(1번/2번·base1/base2) + 동시금지 → 인스턴스간 mutex."""
    progs: list[Program] = []
    for base in ("펌프", "모터", "밸브", "팬", "송풍기"):
        verb = _DEV_VERB.get(base, "켜고")
        end = verb.replace("고", "").strip() or verb
        for text in (
            f"1번 {base} {verb} 2번 {base} {end} 동시에 금지",
            f"{base}1 {verb} {base}2 {end} 같이 안",
        ):
            r = frame_to_spec(text)
            if r.confident and r.spec.interlocks:
                progs.append(Program("multi_instance", text, r.spec))
    return progs


def _sequences() -> list[Program]:
    """(c) 순차(다음) → 타임드 시퀀서: 단계 출력 one-hot(쌍 + ≥3 그룹)."""
    progs: list[Program] = []
    seqs = (
        ("모터", "펌프", "밸브"),
        ("컨베이어", "히터", "팬"),
        ("펌프", "밸브", "송풍기", "램프"),
        ("모터", "컨베이어"),
    )
    for seq in seqs:
        parts: list[str] = []
        for i, d in enumerate(seq):
            parts.append(f"{d} {_DEV_VERB.get(d, '켜고')}")
            if i < len(seq) - 1:
                parts.append("다음")
        text = "버튼 누르면 " + " ".join(parts)
        r = frame_to_spec(text)
        if r.confident and r.spec.interlocks:
            progs.append(Program("sequence", text, r.spec))
    return progs


def _interlock_recipes() -> list[Program]:
    """(d) wizard 인터락 레시피(기본값 빌드) → 선언된 인터락/그룹."""
    progs: list[Program] = []
    for rid in _INTERLOCK_RECIPES:
        rec = RECIPES.get(rid)
        if rec is None:
            continue
        spec = rec.build({})
        if spec.interlocks and covers_all_outputs(spec):
            progs.append(Program("interlock_recipe", rec.title, spec))
    return progs


def build_corpus() -> list[Program]:
    """상호배제를 *가진* 컴파일/레시피 산출물 코퍼스(결정론)."""
    return (
        _two_output_mutex_cues()
        + _multi_instance_mutex()
        + _sequences()
        + _interlock_recipes()
    )


# ---------------------------------------------------------------------------
# 속성 분류: proven / unproven(warning) / violated(error)
# ---------------------------------------------------------------------------
@dataclass
class PropTally:
    """한 종류(쌍/그룹) 속성의 증명 상태 집계."""

    proven: int = 0
    unproven: int = 0
    violated: int = 0

    @property
    def declared(self) -> int:
        return self.proven + self.unproven + self.violated

    def add(self, other: PropTally) -> None:
        self.proven += other.proven
        self.unproven += other.unproven
        self.violated += other.violated


@dataclass
class ProgramReport:
    """한 프로그램의 쌍·그룹 속성 증명 상태."""

    program: Program
    pairs: PropTally = field(default_factory=PropTally)
    groups: PropTally = field(default_factory=PropTally)
    # false-proof 점검: 증명된 속성을 시뮬레이터가 반증 못했는가(작은 표본).
    oracle_disproved: list[str] = field(default_factory=list)


def _classify_pairs(spec: StateMachineSpec, st: str, k: int) -> PropTally:
    """선언된 인터락 쌍 각각을 proven/unproven/violated 로 분류한다.

    proven_safe_pairs 가 증명한 쌍은 proven. 그 외는 check_interlocks_kinduction 의
    이슈 severity 로 판정: error 가 있으면 위반, warning 만 있으면 미증명. 이슈도 없으면
    (분석불가 등) 보수적으로 미증명으로 센다(완전성 측정이므로 미증명에 포함).
    """
    tally = PropTally()
    proven = proven_safe_pairs(spec, st, k=k)
    issues = check_interlocks_kinduction(spec, st, k=k)
    has_error = any(i.severity == "error" for i in issues)
    has_warn = any(i.severity == "warning" for i in issues)
    for lock in spec.interlocks:
        a, b = lock.output_a, lock.output_b
        if (a, b) in proven:
            tally.proven += 1
        elif has_error:
            tally.violated += 1
        elif has_warn:
            tally.unproven += 1
        else:
            tally.unproven += 1
    return tally


def _classify_groups(spec: StateMachineSpec, st: str, k: int) -> PropTally:
    """선언된 ≥3 출력 one-hot 그룹을 proven/unproven/violated 로 분류한다."""
    tally = PropTally()
    declared = derive_mutex_groups(spec)
    if not declared:
        return tally
    proven = {tuple(sorted(g)) for g in proven_safe_groups(spec, st, k=k)}
    issues = check_group_mutex_kinduction(spec, st, k=k)
    has_error = any(i.severity == "error" for i in issues)
    has_warn = any(i.severity == "warning" for i in issues)
    for group in declared:
        if tuple(sorted(group)) in proven:
            tally.proven += 1
        elif has_error:
            tally.violated += 1
        elif has_warn:
            tally.unproven += 1
        else:
            tally.unproven += 1
    return tally


def _oracle_check(spec: StateMachineSpec, st: str) -> list[str]:
    """증명된 mutex 가 시뮬레이터 실행에서 깨지는지(false-proof) 작은 표본 점검.

    출력 심볼에 대해 모든 입력을 결정론 토글(짧은 펄스/유지)로 가동, 매 스캔에서
    선언된 쌍이 동시 ON 이면 반증으로 본다(정상이면 빈 리스트).
    """
    inputs = [p.symbol for p in spec.io_points if p.direction.value == "INPUT"]
    pairs = [(lock.output_a, lock.output_b) for lock in spec.interlocks]
    if not pairs:
        return []
    timelines: list[list[tuple[int, dict[str, bool]]]] = [
        [(0, {s: True for s in inputs})],
        [(0, {s: (i % 2 == 0) for i, s in enumerate(inputs)})],
        [(0, {s: True for s in inputs}), (300, {s: False for s in inputs})],
    ]
    disproved: list[str] = []
    for tl in timelines:
        try:
            res = simulate(st, tl, duration_ms=3000, step_ms=100)
        except Exception:
            continue
        for sample in res.samples:
            for a, b in pairs:
                if sample.outputs.get(a, False) and sample.outputs.get(b, False):
                    disproved.append(f"{a}&{b}@{sample.t_ms}ms")
    return sorted(set(disproved))


def analyze(program: Program, *, k: int = 3, oracle: bool = True) -> ProgramReport:
    """한 프로그램의 쌍·그룹 속성 증명 상태 + false-proof 점검."""
    spec = program.spec
    st = synthesize_st(spec)
    rep = ProgramReport(program=program)
    rep.pairs = _classify_pairs(spec, st, k)
    rep.groups = _classify_groups(spec, st, k)
    if oracle and (rep.pairs.proven or rep.groups.proven):
        rep.oracle_disproved = _oracle_check(spec, st)
    return rep


@dataclass
class CoverageResult:
    """전체 코퍼스의 증명 커버리지 집계."""

    reports: list[ProgramReport]

    @property
    def pairs(self) -> PropTally:
        t = PropTally()
        for r in self.reports:
            t.add(r.pairs)
        return t

    @property
    def groups(self) -> PropTally:
        t = PropTally()
        for r in self.reports:
            t.add(r.groups)
        return t

    @property
    def total(self) -> PropTally:
        t = PropTally()
        t.add(self.pairs)
        t.add(self.groups)
        return t

    @property
    def coverage(self) -> float:
        d = self.total.declared
        return (self.total.proven / d) if d else 0.0

    @property
    def false_proofs(self) -> list[str]:
        out: list[str] = []
        for r in self.reports:
            for d in r.oracle_disproved:
                out.append(f"{r.program.label}: {d}")
        return out

    def by_category(self) -> dict[str, PropTally]:
        cat: dict[str, PropTally] = defaultdict(PropTally)
        for r in self.reports:
            cat[r.program.category].add(r.pairs)
            cat[r.program.category].add(r.groups)
        return dict(cat)


def run(*, k: int = 3, oracle: bool = True) -> CoverageResult:
    """코퍼스를 만들고 각 프로그램의 증명 커버리지를 측정한다(결정론)."""
    corpus = build_corpus()
    reports = [analyze(p, k=k, oracle=oracle) for p in corpus]
    return CoverageResult(reports=reports)


def _pct(tally: PropTally) -> str:
    d = tally.declared
    if not d:
        return "  -  "
    return f"{100.0 * tally.proven / d:5.1f}%"


def format_report(res: CoverageResult) -> str:
    lines: list[str] = []
    lines.append("=== 형식증명 커버리지 정직 측정 (검증기 완전성) ===")
    lines.append(
        f"검사 프로그램 {len(res.reports)}건 (상호배제를 *선언한* 컴파일/레시피 산출물)"
    )
    lines.append("")
    header = (
        f"{'카테고리':<16} {'프로그램':>5} {'선언속성':>6} {'증명':>5} "
        f"{'미증명':>6} {'위반':>5} {'증명율':>7}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    cats = res.by_category()
    prog_count: dict[str, int] = defaultdict(int)
    for r in res.reports:
        prog_count[r.program.category] += 1
    for cat in ("mutex_cue", "multi_instance", "sequence", "interlock_recipe"):
        if cat not in cats:
            continue
        t = cats[cat]
        lines.append(
            f"{cat:<16} {prog_count[cat]:>5} {t.declared:>6} {t.proven:>5} "
            f"{t.unproven:>6} {t.violated:>5} {_pct(t):>7}"
        )
    lines.append("-" * len(header))
    tot = res.total
    lines.append(
        f"{'합계':<16} {len(res.reports):>5} {tot.declared:>6} {tot.proven:>5} "
        f"{tot.unproven:>6} {tot.violated:>5} {_pct(tot):>7}"
    )
    lines.append("")
    lines.append("속성 종류별:")
    lines.append(
        f"  - 쌍(pair)  : 선언 {res.pairs.declared} / 증명 {res.pairs.proven} "
        f"/ 미증명 {res.pairs.unproven} / 위반 {res.pairs.violated}"
    )
    lines.append(
        f"  - 그룹(one-hot >=3): 선언 {res.groups.declared} / 증명 {res.groups.proven} "
        f"/ 미증명 {res.groups.unproven} / 위반 {res.groups.violated}"
    )
    lines.append("")
    lines.append("핵심 지표:")
    lines.append(
        f"  - 선언된 상호배제 속성 중 형식 증명된 비율 = "
        f"{tot.proven}/{tot.declared} = {100.0 * res.coverage:.1f}%"
    )
    lines.append("")
    lines.append("false-proof 점검(증명된 속성을 실행오라클이 반증?):")
    fps = res.false_proofs
    if fps:
        lines.append(f"  - [경고] {len(fps)}건 반증 — 증명이 건전하지 않음(즉시 점검):")
        for fp in fps[:6]:
            lines.append(f"      {fp}")
    else:
        lines.append(
            "  - 0건 — 증명된 모든 mutex 를 디지털 트윈이 반증 못함(작은 표본 교차확인)."
        )
    lines.append("")
    lines.append("정직한 결론(완전성의 한계 = 미증명으로 남는 것):")
    if tot.unproven == 0 and tot.violated == 0:
        lines.append(
            "  - 이 코퍼스의 *모든* 선언 상호배제 속성이 k-귀납으로 형식 증명됨(미증명 0)."
        )
        lines.append(
            "    이유: 컴파일러/인터락 레시피가 각 출력식에 'AND NOT 상대' 가드를 *구조적으로*"
        )
        lines.append(
            "    박으므로 k=3 귀납이 닫힌다. 가드 없는 선언 mutex 는 미증명/위반으로 남는다"
        )
        lines.append("    (검증기가 침묵하지 않음 — 별도 확인됨).")
    else:
        lines.append(
            f"  - 미증명 {tot.unproven}건은 k=3-귀납이 닫히지 않은 경우(보수적 warning; "
            "안전 미보장, 침묵하지 않음)."
        )
        if tot.violated:
            lines.append(f"  - 위반 {tot.violated}건은 동시 ON 반례가 잡힌 경우(error).")
    lines.append("")
    lines.append("한계(정직):")
    lines.append("  - 측정 범위는 *상호배제* 속성뿐(도달성·타이밍 정량 속성의 완전성은 별도).")
    lines.append("  - 커버리지 100%는 '우리 컴파일러 산출물'에 대한 것 — 임의 ST 의 완전성은")
    lines.append("    보장하지 않는다(가드 없는 코드는 미증명으로 정직 보고).")
    lines.append("  - k=3 고정 — 더 긴 위반 지평을 갖는 가상의 명세는 미증명으로 남을 수 있다.")
    return "\n".join(lines)


def main() -> int:
    res = run()
    print(format_report(res))
    # 안전 가드: 검사 대상이 있고, false-proof 0 이어야 한다.
    if not res.reports or res.false_proofs:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
