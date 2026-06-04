"""Export golden cases to JSONL for SFT (Supervised Fine-Tuning).

Pipeline:
  1. load_golden_cases()   — read JSON from golden dir (safe if dir missing/empty)
  2. verified_only()       — SAFETY GATE: drops any case where verify() raises
                             error-severity issues.  Only clean data becomes training
                             data — this is the critical invariant for the whole
                             pipeline.
  3. build_architect_examples() / build_analyst_examples()
                           — format into the chat-messages schema expected by SFT.
  4. export()              — write JSONL to disk.

Usage (CLI):
  python -m training.export_dataset \\
      --golden-dir tests/fixtures/golden \\
      --out data/architect_sft.jsonl \\
      --kind architect
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.memory_map import DeviceAllocator
from app.models import StateMachineSpec
from app.prompts import REQUIREMENTS_ANALYST_SYSTEM, ST_ARCHITECT_SYSTEM
from app.verifier import verify

# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

DEFAULT_GOLDEN_DIR = "tests/fixtures/golden"


def load_golden_cases(golden_dir: str = DEFAULT_GOLDEN_DIR) -> list[dict[str, Any]]:
    """Read every ``*.json`` file from *golden_dir* and return their contents.

    Returns an empty list (without raising) if the directory is missing or
    contains no JSON files — another agent may be building that directory
    concurrently.
    """
    p = Path(golden_dir)
    if not p.exists() or not p.is_dir():
        return []

    cases: list[dict[str, Any]] = []
    for jf in sorted(p.glob("*.json")):
        try:
            with jf.open(encoding="utf-8") as fh:
                data = json.load(fh)
            cases.append(data)
        except (json.JSONDecodeError, OSError):
            # Skip malformed / unreadable files gracefully.
            continue
    return cases


# ---------------------------------------------------------------------------
# Safety gate — MUST run before any export
# ---------------------------------------------------------------------------

def verified_only(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """CRITICAL SAFETY GATE.

    Filters *cases* to only those where ``verify(spec, golden_st)`` produces
    **no error-severity issues**.  Cases with even a single ``severity="error"``
    issue are silently dropped.

    This is the central data-quality invariant:
    **only verified-clean examples ever become training data.**

    A warning-only report (e.g. Z3 not installed → interlock downgraded to
    warning) is still treated as passing, consistent with ``VerificationReport``
    semantics.
    """
    clean: list[dict[str, Any]] = []
    for case in cases:
        try:
            raw_spec = case.get("spec")
            golden_st: str = case.get("golden_st", "")
            if raw_spec is None or not golden_st:
                continue  # Missing required fields — skip.
            spec = StateMachineSpec.model_validate(raw_spec)
            report = verify(spec, golden_st)
            if not report.has_errors:
                clean.append(case)
        except Exception:
            # Any validation/parsing error means this case is not safe.
            continue
    return clean


# ---------------------------------------------------------------------------
# Example builders
# ---------------------------------------------------------------------------

def _make_spec_user_content(spec: StateMachineSpec) -> str:
    """Combine the spec JSON with the device-map comment block."""
    allocator = DeviceAllocator().build_from_spec(spec)
    device_map = allocator.as_comment_block()
    spec_json = spec.model_dump_json(indent=2)
    return f"{device_map}\n\n{spec_json}"


def build_architect_examples(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert golden cases into SFT chat examples for the ST-architect role.

    Each example has three messages:
      system    — ST_ARCHITECT_SYSTEM (with empty instruction_context / feedback)
      user      — device-map comment + spec JSON
      assistant — golden ST code
    """
    examples: list[dict[str, Any]] = []
    for case in cases:
        raw_spec = case.get("spec")
        golden_st: str = case.get("golden_st", "")
        if raw_spec is None or not golden_st:
            continue
        try:
            spec = StateMachineSpec.model_validate(raw_spec)
        except Exception:
            continue

        system_content = ST_ARCHITECT_SYSTEM.format(
            instruction_context="(없음)",
            feedback="(없음)",
        )
        user_content = _make_spec_user_content(spec)

        examples.append(
            {
                "messages": [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": golden_st},
                ]
            }
        )
    return examples


def build_analyst_examples(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert golden cases into SFT chat examples for the requirements-analyst role.

    Each example has three messages:
      system    — REQUIREMENTS_ANALYST_SYSTEM
      user      — natural-language request
      assistant — StateMachineSpec as indented JSON
    """
    examples: list[dict[str, Any]] = []
    for case in cases:
        request: str = case.get("request", "")
        raw_spec = case.get("spec")
        if not request or raw_spec is None:
            continue
        try:
            spec = StateMachineSpec.model_validate(raw_spec)
        except Exception:
            continue

        examples.append(
            {
                "messages": [
                    {"role": "system", "content": REQUIREMENTS_ANALYST_SYSTEM},
                    {"role": "user", "content": request},
                    {"role": "assistant", "content": spec.model_dump_json(indent=2)},
                ]
            }
        )
    return examples


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export(
    golden_dir: str = DEFAULT_GOLDEN_DIR,
    out_path: str = "data/sft.jsonl",
    kind: str = "architect",
) -> int:
    """Load, gate-filter, build examples, and write JSONL.

    Args:
        golden_dir: Directory containing golden ``*.json`` cases.
        out_path:   Destination JSONL file (created / overwritten).
        kind:       ``"architect"``, ``"analyst"``, or ``"both"``.

    Returns:
        Number of examples written.
    """
    if kind not in ("architect", "analyst", "both"):
        raise ValueError(f"kind must be 'architect', 'analyst', or 'both'; got {kind!r}")

    cases = load_golden_cases(golden_dir)
    safe_cases = verified_only(cases)

    examples: list[dict[str, Any]] = []
    if kind in ("architect", "both"):
        examples.extend(build_architect_examples(safe_cases))
    if kind in ("analyst", "both"):
        examples.extend(build_analyst_examples(safe_cases))

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for ex in examples:
            fh.write(json.dumps(ex, ensure_ascii=False) + "\n")

    return len(examples)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export golden PLC cases to SFT JSONL for LoRA fine-tuning."
    )
    parser.add_argument(
        "--golden-dir",
        default=DEFAULT_GOLDEN_DIR,
        help="Directory containing golden *.json case files (default: %(default)s)",
    )
    parser.add_argument(
        "--out",
        default="data/sft.jsonl",
        help="Output JSONL path (default: %(default)s)",
    )
    parser.add_argument(
        "--kind",
        choices=["architect", "analyst", "both"],
        default="architect",
        help="Which role's examples to export (default: %(default)s)",
    )
    args = parser.parse_args()

    n = export(golden_dir=args.golden_dir, out_path=args.out, kind=args.kind)
    print(f"Wrote {n} examples → {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
