#!/usr/bin/env python3
"""수리 효능 벤치 — 고장난 ST 를 자동 수리해 살리는 통과율(M4 측정, 정직).

인터락 보유 레시피의 *검증 통과* ST 를 일부러 고장낸다(① 가드 제거→인터락 위반,
② 코일 복제→이중코일). 그 깨진 프로그램을 repair_iterative 로 수리해 *다시 검증 통과*
시키는 비율을 잰다. 구조적 결함은 수리 대상이 아님(정직 거절). 결정론·키 불필요.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.project import compose, scaffold_mutex  # noqa: E402
from app.repair import repair_iterative  # noqa: E402
from app.synth import synthesize_st  # noqa: E402
from app.verifier import verify  # noqa: E402
from app.wizard import RECIPES, build_spec  # noqa: E402


def _specs() -> list[tuple[str, object]]:
    out: list[tuple[str, object]] = []
    for rid in RECIPES:
        s = build_spec(rid)
        if s.interlocks:
            out.append((rid, s))
    for n in (2, 3):
        out.append((f"mutex_x{n}", compose(scaffold_mutex("motor_start_stop", n))))
    return out


def _break_guards(st: str, spec: object) -> str:
    """인터락 가드(AND NOT 상대)를 제거 → 인터락 위반 프로그램."""
    syms = {s for lock in spec.interlocks for s in (lock.output_a, lock.output_b)}  # type: ignore[attr-defined]
    for sym in syms:
        st = re.sub(rf"\s+AND\s+NOT\s+{re.escape(sym)}\b", "", st)
    return st


def _break_double(st: str, spec: object) -> str:
    """첫 출력 코일을 한 줄 복제 → 이중코일 프로그램."""
    for lock in spec.interlocks:  # type: ignore[attr-defined]
        a = lock.output_a
        if re.search(rf"^\s*{re.escape(a)}\s*:=", st, re.MULTILINE):
            return st + f"\n{a} := FALSE;"
    return st


def run() -> dict[str, int]:
    tally = {"broken": 0, "repaired": 0, "rejected": 0, "still_failing": 0}
    for _name, spec in _specs():
        good = synthesize_st(spec)
        if not verify(spec, good).passed:
            continue
        for breaker in (_break_guards, _break_double):
            broken = breaker(good, spec)
            if verify(spec, broken).passed:
                continue  # 고장 안 남(구조적 one-hot 등) → 표본 제외
            tally["broken"] += 1
            o = repair_iterative(spec, broken)
            if o.repaired and o.report.passed:
                tally["repaired"] += 1
            elif o.rejected:
                tally["rejected"] += 1
            else:
                tally["still_failing"] += 1
    return tally


def main() -> int:
    t = run()
    n = t["broken"]
    print("=== 수리 효능 벤치 (고장→수리→재검증) ===")
    print(f"고장낸 프로그램        : {n}")
    print(f"수리해 검증 통과       : {t['repaired']}  ({100 * t['repaired'] / max(1, n):.0f}%)")
    print(f"정직 거절(구조적 불가) : {t['rejected']}")
    print(f"수리 실패(잔존)        : {t['still_failing']}")
    print("\n의미: 인터락 위반·이중코일로 깨진 프로그램을 자동 수리(가드 주입·OR 병합)로 "
          "되살린다. 모든 수리 결과는 verify 게이트를 다시 통과해야 '수리됨'으로 센다.")
    return 0 if t["still_failing"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
