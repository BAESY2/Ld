#!/usr/bin/env python3
"""Targeted (hand-crafted) mutation harness for the determinism/safety core.

Motivation
----------
``mutmut`` 3.x generates thousands of syntactic mutants but, in this codebase, its
trampoline-based test→function coverage mapping fails to associate the heavyweight
corpus/k-induction tests with the mutated functions ("could not find any test case
for any mutant"). See ``scripts/run_mutation.py`` for that path and its limitation.

This harness instead injects the *specific, safety-relevant* faults the review cares
about — the ones a PLC ladder synthesizer must never regress on:

  * seal-in latch  AND ↔ OR        (``... ) AND NOT (...`` becomes ``... ) OR NOT (...``)
  * drop the interlock ``AND NOT <partner>`` term (mutual-exclusion hole)
  * timer preset off-by-one / comparison flip (``>=`` → ``>``)
  * counter fire comparison flip
  * k-induction base/step swap & guard weakening
  * bootstrap gate disabled (verify gate / mutex gate made vacuous)

For each mutant it copies the *current* source tree into a scratch dir, applies one
exact-string patch, runs the existing pytest suite (which includes the corpus replay
and k-induction corpus tests), and records whether the suite goes RED (mutant KILLED)
or stays GREEN (mutant SURVIVED = a determinism/safety hole).

Run::

    python scripts/targeted_mutation.py                 # all mutants, full suite
    python scripts/targeted_mutation.py --list          # just list the mutants
    python scripts/targeted_mutation.py --only seal_in_and_to_or
    python scripts/targeted_mutation.py --tests tests/test_synth.py tests/test_simulator.py
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Mutant:
    name: str          # stable id
    rel_path: str      # file under repo to patch
    old: str           # exact substring to replace (must be unique in file)
    new: str           # replacement
    fault: str         # human description of the injected fault


# Body of the bootstrap 'verified' gate (the two lines guarded by ``if report.has_errors:``),
# kept as a constant so the anchor strings below stay within the line-length limit.
_VERIFY_GATE_BODY = (
    '        errs = [f"{i.code}" for i in report.issues if i.severity == "error"]\n'
    '        return gates, st, "", f"verify: {sorted(set(errs))}"'
)

# The catalogue of safety-relevant faults. ``old`` strings are taken verbatim from the
# current sources; the harness asserts each appears exactly once before patching.
MUTANTS: list[Mutant] = [
    Mutant(
        name="seal_in_and_to_or",
        rel_path="app/synth.py",
        old='expr += f" AND NOT ({off_expr})"',
        new='expr += f" OR NOT ({off_expr})"',
        fault="seal-in turn-off joined with OR instead of AND (latch never resets / wrong gate)",
    ),
    Mutant(
        name="drop_interlock_not_partner",
        rel_path="app/synth.py",
        old='expr += f" AND NOT {partner}"',
        new='expr += ""  # MUTANT: dropped AND NOT partner',
        fault="interlock 'AND NOT <partner>' term dropped — mutual-exclusion lost",
    ),
    Mutant(
        name="turn_on_or_to_and",
        rel_path="app/synth.py",
        old='on_expr = " OR ".join(f"({c})" for c in turn_on)',
        new='on_expr = " AND ".join(f"({c})" for c in turn_on)',
        fault="turn-on conditions joined with AND not OR (fires only if all entry conds true)",
    ),
    Mutant(
        name="ton_fire_off_by_one",
        rel_path="app/simulator.py",
        old="            self.q = self.acc >= self.preset_ms",
        new="            self.q = self.acc > self.preset_ms",
        fault="TON fires on acc > preset instead of >= (1-step late / off-by-one timer)",
    ),
    Mutant(
        name="ctu_fire_off_by_one",
        rel_path="app/simulator.py",
        old="        self.q = self.cnt >= self.preset if self.kind != \"CTD\" else self.cnt <= 0",
        new="        self.q = self.cnt > self.preset if self.kind != \"CTD\" else self.cnt <= 0",
        fault="CTU fires on cnt > preset instead of >= (counter off-by-one)",
    ),
    Mutant(
        name="counter_edge_to_level",
        rel_path="app/simulator.py",
        old="            if cu and not self._prev:  # 상승 엣지",
        new="            if cu:  # MUTANT: level instead of rising edge",
        fault="counter counts on level instead of rising edge (over-counts every scan)",
    ),
    Mutant(
        name="kind_base_guard_weaken",
        rel_path="app/verifier.py",
        old="    base.add(z3.Or(*[z3.And(fr[a], fr[b]) for fr in frames]))",
        new="    base.add(z3.And(*[z3.And(fr[a], fr[b]) for fr in frames]))",
        fault="k-induction BASE Or→And over frames (misses single-frame reachable violation)",
    ),
    Mutant(
        name="kind_step_assume_negate",
        rel_path="app/verifier.py",
        old="        step_solver.add(prop_ok(frames[i]))  # 가정: 0..k-1 에서 성립",
        new="        step_solver.add(z3.Not(prop_ok(frames[i])))  # MUTANT: assume violation",
        fault="k-induction STEP inductive hypothesis negated (assumes the property is false)",
    ),
    Mutant(
        name="interlock_st_drop_guard",
        rel_path="app/verifier.py",
        old="        solver.add(z3.Not(z3.And(cur[a], cur[b])))  # 귀납 가정: 현재 동시 ON 아님",
        new="        solver.add(z3.Or(cur[a], cur[b]))  # MUTANT: wrong inductive assumption",
        fault="1-step interlock ST check uses wrong current-state assumption",
    ),
    Mutant(
        name="bootstrap_verify_gate_vacuous",
        rel_path="app/dataset/bootstrap.py",
        old="    if report.has_errors:\n" + _VERIFY_GATE_BODY,
        new="    if False:  # MUTANT: verify gate disabled\n" + _VERIFY_GATE_BODY,
        fault="bootstrap 'verified' gate disabled — unverified specs would enter the corpus",
    ),
]


def _snapshot(work: Path) -> None:
    for sub in ("app", "tests", "scripts", "data"):
        src = REPO / sub
        if src.exists():
            shutil.copytree(src, work / sub, dirs_exist_ok=True)
    for cache in work.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    root_conftest = REPO / "conftest.py"
    if root_conftest.exists():
        shutil.copy2(root_conftest, work / "conftest.py")


class AnchorError(RuntimeError):
    """The mutant's anchor string is not present exactly once (source moved)."""


def _apply(work: Path, m: Mutant) -> None:
    target = work / m.rel_path
    text = target.read_text(encoding="utf-8")
    count = text.count(m.old)
    if count != 1:
        raise AnchorError(
            f"mutant '{m.name}': expected exactly 1 occurrence of its anchor in "
            f"{m.rel_path}, found {count}. The source moved; update MUTANTS."
        )
    target.write_text(text.replace(m.old, m.new), encoding="utf-8")


def _run_suite(work: Path, tests: list[str]) -> tuple[bool, str]:
    """Return (suite_green, tail). suite_green=True means all selected tests passed."""
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests]
    proc = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    out = (proc.stdout + proc.stderr).strip().splitlines()
    tail = "\n".join(out[-3:]) if out else ""
    return proc.returncode == 0, tail


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", help="Run only these mutant names (repeatable).")
    ap.add_argument("--list", action="store_true", help="List mutants and exit.")
    ap.add_argument(
        "--tests",
        nargs="*",
        default=["tests/"],
        help="pytest targets to run as the killing suite (default: tests/).",
    )
    args = ap.parse_args()

    chosen = MUTANTS
    if args.only:
        chosen = [m for m in MUTANTS if m.name in set(args.only)]
        missing = set(args.only) - {m.name for m in chosen}
        if missing:
            ap.error(f"unknown mutant(s): {sorted(missing)}")

    if args.list:
        for m in MUTANTS:
            print(f"{m.name:32s} {m.rel_path:28s} {m.fault}")
        return 0

    # Baseline: confirm the suite is GREEN on the unmutated snapshot first.
    base = Path(tempfile.mkdtemp(prefix="mut_base_"))
    try:
        _snapshot(base)
        green, tail = _run_suite(base, args.tests)
        print(f"[baseline] {'GREEN' if green else 'RED'} :: {tail}")
        if not green:
            print("[baseline] suite is not green on the snapshot; aborting (fix env/tests first).")
            return 2
    finally:
        shutil.rmtree(base, ignore_errors=True)

    killed: list[str] = []
    survived: list[tuple[str, str]] = []
    skipped: list[str] = []
    for m in chosen:
        work = Path(tempfile.mkdtemp(prefix=f"mut_{m.name}_"))
        try:
            _snapshot(work)
            try:
                _apply(work, m)
            except AnchorError as exc:
                skipped.append(m.name)
                print(f"[{'SKIP(anchor)':12s}] {m.name:32s} :: {exc}")
                continue
            green, tail = _run_suite(work, args.tests)
            if green:
                survived.append((m.name, m.fault))
                status = "SURVIVED ⚠"
            else:
                killed.append(m.name)
                status = "killed"
            print(f"[{status:12s}] {m.name:32s} :: {tail.splitlines()[-1] if tail else ''}")
        finally:
            shutil.rmtree(work, ignore_errors=True)

    total = len(chosen) - len(skipped)
    print("\n=== targeted mutation summary ===")
    if skipped:
        print(f"skipped  {len(skipped)} (anchor moved): {skipped}")
    print(f"killed   {len(killed)}/{total}")
    print(f"survived {len(survived)}/{total}")
    for name, fault in survived:
        m = next(x for x in MUTANTS if x.name == name)
        print(f"  SURVIVED {name} ({m.rel_path}): {fault}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
