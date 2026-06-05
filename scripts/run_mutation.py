#!/usr/bin/env python3
"""Mutation-testing runner for the determinism core (synth/simulator/verifier/bootstrap).

Why isolated workspace: mutmut 3.x copies the *current working directory* into a
``mutants/`` dir and reads its config from the repo-root ``pyproject.toml``/``setup.cfg``.
This project's file-ownership rules forbid editing those root files, so we build a
throwaway copy of ``app/`` + ``tests/`` in a scratch directory, drop a dedicated
``pyproject.toml`` with a ``[tool.mutmut]`` section there, and run mutmut from inside it.
The real repo is never mutated and its config is never touched.

Usage::

    python scripts/run_mutation.py            # mutate all 4 core modules, full suite
    python scripts/run_mutation.py --module app/synth.py
    python scripts/run_mutation.py --keep     # keep the scratch workspace for inspection

The "test suite that must KILL mutants" is the existing pytest suite (which includes
the corpus replay / k-induction corpus tests). A mutant that survives is a
determinism/safety hole the corpus + suite do NOT catch.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The determinism-core modules under mutation (relative to repo root).
CORE_MODULES: list[str] = [
    "app/synth.py",
    "app/simulator.py",
    "app/verifier.py",
    "app/dataset/bootstrap.py",
]


def _build_pyproject(paths_to_mutate: list[str]) -> str:
    """A minimal pyproject for the scratch workspace with a [tool.mutmut] section."""
    paths = ",\n  ".join(f'"{p}"' for p in paths_to_mutate)
    return f"""\
[project]
name = "plc-ladder-agent-mutation"
version = "0.0.0"
requires-python = ">=3.11"

[tool.mutmut]
paths_to_mutate = [
  {paths}
]
tests_dir = ["tests/"]
# mutmut copies the workspace into mutants/; test_eval.py loads scripts/eval.py and
# tests/fixtures/golden relative to its parent.parent, so those must live inside mutants/.
also_copy = [
  "scripts/",
  "data/",
]
# Keep the suite key-free and fast; the live LLM tests are already skipped by default.
"""


def setup_workspace(work: Path, modules: list[str]) -> None:
    """Copy app/ + tests/ into ``work`` and write a dedicated mutmut config."""
    shutil.copytree(REPO / "app", work / "app", dirs_exist_ok=True)
    shutil.copytree(REPO / "tests", work / "tests", dirs_exist_ok=True)
    # Some tests (test_eval.py) dynamically load scripts/eval.py and read
    # tests/fixtures/golden relative to the repo root — copy scripts/ too.
    if (REPO / "scripts").exists():
        shutil.copytree(REPO / "scripts", work / "scripts", dirs_exist_ok=True)
    # The accumulated verify-gated corpus (data/bootstrap/dataset.json) is the very
    # thing under measurement — corpus-replay tests read it from disk.
    if (REPO / "data").exists():
        shutil.copytree(REPO / "data", work / "data", dirs_exist_ok=True)
    # Drop compiled caches so the copy is clean.
    for pyc in work.rglob("__pycache__"):
        shutil.rmtree(pyc, ignore_errors=True)
    (work / "pyproject.toml").write_text(_build_pyproject(modules), encoding="utf-8")
    # conftest at repo root (if any) so pytest discovery matches.
    root_conftest = REPO / "conftest.py"
    if root_conftest.exists():
        shutil.copy2(root_conftest, work / "conftest.py")


def run(work: Path) -> int:
    env = dict(os.environ)
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    proc = subprocess.run(
        [sys.executable, "-m", "mutmut", "run"],
        cwd=work,
        env=env,
    )
    return proc.returncode


def results(work: Path) -> None:
    subprocess.run([sys.executable, "-m", "mutmut", "results"], cwd=work)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--module",
        action="append",
        help="Limit mutation to this module (repeatable). Default: all 4 core modules.",
    )
    ap.add_argument("--keep", action="store_true", help="Keep the scratch workspace.")
    ap.add_argument(
        "--workdir",
        default=None,
        help="Use this scratch directory instead of a temp dir.",
    )
    args = ap.parse_args()

    modules = args.module or CORE_MODULES
    for m in modules:
        if not (REPO / m).exists():
            ap.error(f"module not found: {m}")

    work = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="mut_"))
    work.mkdir(parents=True, exist_ok=True)
    print(f"[run_mutation] workspace: {work}")
    print(f"[run_mutation] mutating: {modules}")
    try:
        setup_workspace(work, modules)
        rc = run(work)
        print("\n[run_mutation] === results ===")
        results(work)
        return rc
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
        else:
            print(f"[run_mutation] kept workspace at {work}")


if __name__ == "__main__":
    raise SystemExit(main())
