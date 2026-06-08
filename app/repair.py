"""검증 게이트 자동 수리 (CEGIS류) — 중심 베팅 '검증기가 해자' 캡스톤(M4).

검증이 실패한 ST 를 *건전한* 수리로 고쳐 재검증한다. 두 수리는 의미를 망치지 않는다:
- 이중코일 → M릴레이 OR 병합(merge_double_coils): 마지막-대입 의미를 'OR 의도'로 복구(보존).
- 인터락 위반 → 코일식에 'AND NOT 상대' 가드 주입: 켜지는 조건을 *좁힌다*(안전측).
구조적 결함(데드락·미도달·프리셋·그룹/종류)은 수리 대상이 아니라 *정직 거절*한다.

종료성: 이중코일 병합은 심볼당 1회(선형 감소), 가드 주입은 멱등(이미 가드면 무변경) →
유한 반복 안에 고정점. 어떤 수리든 의미를 안전측으로만 바꾸므로 루프가 발산하지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.memory_map import DeviceAllocator, merge_double_coils
from app.models import StateMachineSpec, VerificationReport
from app.verifier import _coil_equations, verify

# 수리로 못 고치는(구조적) 검증 코드 — 정직 거절 대상.
_UNREPAIRABLE = {"DEADLOCK", "UNREACHABLE", "TIMER_PRESET", "COUNTER_PRESET",
                 "GROUP_MUTEX", "INTERLOCK_KIND", "PARSE_ERROR"}


def _has(expr: str, sym: str) -> bool:
    """식에 'NOT sym' 가드가 이미 있는가(멱등 보장용, 단어경계)."""
    return re.search(rf"NOT\s+{re.escape(sym)}\b", expr) is not None


def inject_interlock_guards(st_code: str, spec: StateMachineSpec) -> str:
    """선언된 인터락 쌍마다 두 코일식에 'AND NOT 상대'를 주입(안전측·멱등).

    ``A := expr;`` → ``A := (expr) AND NOT B;`` (그리고 B 도 대칭으로). 이미 가드돼
    있거나 코일이 ST 에 없으면 건너뛴다. 의미를 *좁히는* 수리라 위반 가능성을 늘리지 않는다.
    """
    eqs = _coil_equations(st_code)
    out = st_code
    for lock in spec.interlocks:
        for a, b in ((lock.output_a, lock.output_b), (lock.output_b, lock.output_a)):
            if a not in eqs or b not in eqs or _has(eqs[a], b):
                continue
            pat = re.compile(rf"^(\s*{re.escape(a)}\s*:=\s*)(.+?)(\s*;\s*)$", re.MULTILINE)

            def _guard(m: re.Match[str], partner: str = b) -> str:
                return f"{m.group(1)}({m.group(2)}) AND NOT {partner}{m.group(3)}"

            out = pat.sub(_guard, out, count=1)
            eqs = _coil_equations(out)  # 가드 반영
    return out


@dataclass
class RepairOutcome:
    st_code: str
    report: VerificationReport
    repaired: bool                       # 수리로 통과시켰는가
    rejected: bool                       # 구조적 불가 → 정직 거절
    strategies: tuple[str, ...] = ()     # 적용한 수리(double_coil/interlock)


def repair_iterative(
    spec: StateMachineSpec, st_code: str, *,
    allocator: DeviceAllocator | None = None, max_iterations: int = 3,
) -> RepairOutcome:
    """수리→재검증 루프. 통과시키면 repaired=True, 구조적 불가면 rejected=True."""
    alloc = allocator or DeviceAllocator().build_from_spec(spec)
    report = verify(spec, st_code)
    if report.passed:
        return RepairOutcome(st_code, report, repaired=False, rejected=False)
    applied: list[str] = []
    for _ in range(max_iterations):
        codes = {i.code for i in report.issues if i.severity == "error"}
        changed = False
        if "DOUBLE_COIL" in codes:
            res = merge_double_coils(st_code, alloc)
            if res.changed:
                st_code, changed = res.code, True
                applied.append("double_coil")
        if "INTERLOCK" in codes:
            new = inject_interlock_guards(st_code, spec)
            if new != st_code:
                st_code, changed = new, True
                applied.append("interlock")
        if not changed:  # 더 고칠 수리가 없음 → 구조적 결함
            break
        report = verify(spec, st_code)
        if report.passed:
            return RepairOutcome(st_code, report, repaired=True, rejected=False,
                                 strategies=tuple(applied))
    return RepairOutcome(st_code, report, repaired=False, rejected=True,
                         strategies=tuple(applied))


def is_structurally_unrepairable(report: VerificationReport) -> bool:
    """리포트의 error 가 구조적(수리 불가) 코드뿐인가(정직 거절 판단)."""
    errs = {i.code for i in report.issues if i.severity == "error"}
    return bool(errs) and errs <= _UNREPAIRABLE
