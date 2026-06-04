"""Tests for the training data export pipeline.

These tests are fully self-contained — they do NOT depend on the golden
fixture directory existing on disk.  All test data is built synthetically
inside each test function.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Minimal synthetic test fixtures
# ---------------------------------------------------------------------------

# A valid, verified single-coil spec + golden ST
_VALID_SPEC: dict[str, Any] = {
    "title": "테스트 단순 코일",
    "io_points": [
        {
            "symbol": "START_PB",
            "direction": "INPUT",
            "data_type": "BOOL",
            "device_class": "P",
            "description": "기동 버튼",
            "fixed_address": None,
        },
        {
            "symbol": "LAMP",
            "direction": "OUTPUT",
            "data_type": "BOOL",
            "device_class": "P",
            "description": "표시등",
            "fixed_address": None,
        },
    ],
    "timers": [],
    "counters": [],
    "states": [
        {"name": "IDLE", "is_initial": True, "on_entry": [], "description": "대기"},
        {
            "name": "ON",
            "is_initial": False,
            "on_entry": ["LAMP := TRUE;"],
            "description": "표시등 점등",
        },
    ],
    "transitions": [
        {
            "from_state": "IDLE",
            "to_state": "ON",
            "condition": "START_PB",
            "description": "기동",
        },
        {
            "from_state": "ON",
            "to_state": "IDLE",
            "condition": "NOT START_PB",
            "description": "정지",
        },
    ],
    "interlocks": [],
}

_VALID_GOLDEN_ST = "LAMP := START_PB;"

# A golden ST with a double-coil (same symbol assigned twice) — must be dropped
_DOUBLE_COIL_GOLDEN_ST = "LAMP := START_PB;\nLAMP := NOT START_PB;"

_VALID_CASE: dict[str, Any] = {
    "name": "test_single_coil",
    "request": "START_PB 를 누르면 LAMP 가 켜집니다.",
    "spec": _VALID_SPEC,
    "golden_st": _VALID_GOLDEN_ST,
}

_DOUBLE_COIL_CASE: dict[str, Any] = {
    "name": "test_double_coil",
    "request": "이중 코일 오류 케이스.",
    "spec": _VALID_SPEC,
    "golden_st": _DOUBLE_COIL_GOLDEN_ST,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_export() -> Any:
    """Import training.export_dataset (always available — no heavy deps)."""
    return importlib.import_module("training.export_dataset")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildArchitectExamples:
    """build_architect_examples produces well-formed SFT chat examples."""

    def test_produces_three_messages(self) -> None:
        mod = _import_export()
        examples = mod.build_architect_examples([_VALID_CASE])
        assert len(examples) == 1
        msgs = examples[0]["messages"]
        assert len(msgs) == 3

    def test_roles_in_order(self) -> None:
        mod = _import_export()
        msgs = mod.build_architect_examples([_VALID_CASE])[0]["messages"]
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[2]["role"] == "assistant"

    def test_assistant_equals_golden_st(self) -> None:
        mod = _import_export()
        msgs = mod.build_architect_examples([_VALID_CASE])[0]["messages"]
        assert msgs[2]["content"] == _VALID_GOLDEN_ST

    def test_system_contains_architect_marker(self) -> None:
        mod = _import_export()
        msgs = mod.build_architect_examples([_VALID_CASE])[0]["messages"]
        # ST_ARCHITECT_SYSTEM contains this Korean phrase
        assert "ST 코드 아키텍트" in msgs[0]["content"]

    def test_user_contains_device_map_and_spec(self) -> None:
        mod = _import_export()
        msgs = mod.build_architect_examples([_VALID_CASE])[0]["messages"]
        user_content = msgs[1]["content"]
        # Device map comment block
        assert "디바이스 맵" in user_content
        # Spec JSON contains the symbol
        assert "START_PB" in user_content

    def test_empty_cases_returns_empty(self) -> None:
        mod = _import_export()
        assert mod.build_architect_examples([]) == []

    def test_case_missing_golden_st_skipped(self) -> None:
        mod = _import_export()
        bad = {**_VALID_CASE, "golden_st": ""}
        assert mod.build_architect_examples([bad]) == []


class TestBuildAnalystExamples:
    """build_analyst_examples produces well-formed SFT chat examples."""

    def test_produces_three_messages(self) -> None:
        mod = _import_export()
        examples = mod.build_analyst_examples([_VALID_CASE])
        assert len(examples) == 1
        msgs = examples[0]["messages"]
        assert len(msgs) == 3

    def test_roles_in_order(self) -> None:
        mod = _import_export()
        msgs = mod.build_analyst_examples([_VALID_CASE])[0]["messages"]
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[2]["role"] == "assistant"

    def test_user_equals_request(self) -> None:
        mod = _import_export()
        msgs = mod.build_analyst_examples([_VALID_CASE])[0]["messages"]
        assert msgs[1]["content"] == _VALID_CASE["request"]

    def test_assistant_is_valid_spec_json(self) -> None:
        mod = _import_export()
        msgs = mod.build_analyst_examples([_VALID_CASE])[0]["messages"]
        parsed = json.loads(msgs[2]["content"])
        # Should contain io_points key from StateMachineSpec
        assert "io_points" in parsed

    def test_system_contains_analyst_marker(self) -> None:
        mod = _import_export()
        msgs = mod.build_analyst_examples([_VALID_CASE])[0]["messages"]
        # REQUIREMENTS_ANALYST_SYSTEM contains this Korean phrase
        assert "요구사항 분석가" in msgs[0]["content"]

    def test_empty_cases_returns_empty(self) -> None:
        mod = _import_export()
        assert mod.build_analyst_examples([]) == []


class TestVerifiedOnly:
    """verified_only keeps correct cases and drops double-coil cases."""

    def test_keeps_valid_case(self) -> None:
        mod = _import_export()
        result = mod.verified_only([_VALID_CASE])
        assert len(result) == 1
        assert result[0] is _VALID_CASE

    def test_drops_double_coil_case(self) -> None:
        """A case with a double-coil ST must be excluded (DOUBLE_COIL is error-severity)."""
        mod = _import_export()
        result = mod.verified_only([_DOUBLE_COIL_CASE])
        assert result == []

    def test_filters_mixed_list(self) -> None:
        mod = _import_export()
        cases = [_VALID_CASE, _DOUBLE_COIL_CASE, _VALID_CASE]
        result = mod.verified_only(cases)
        # Only the two valid cases pass
        assert len(result) == 2

    def test_missing_spec_skipped(self) -> None:
        mod = _import_export()
        bad = {"name": "no-spec", "request": "x", "golden_st": "X := TRUE;"}
        assert mod.verified_only([bad]) == []

    def test_missing_golden_st_skipped(self) -> None:
        mod = _import_export()
        bad = {**_VALID_CASE, "golden_st": ""}
        assert mod.verified_only([bad]) == []


class TestLoadGoldenCases:
    """load_golden_cases is safe when the golden dir is missing or empty."""

    def test_missing_dir_returns_empty(self) -> None:
        mod = _import_export()
        result = mod.load_golden_cases("/nonexistent/path/that/does/not/exist")
        assert result == []

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        mod = _import_export()
        result = mod.load_golden_cases(str(tmp_path))
        assert result == []

    def test_reads_json_files(self, tmp_path: Path) -> None:
        mod = _import_export()
        (tmp_path / "case01.json").write_text(
            json.dumps(_VALID_CASE), encoding="utf-8"
        )
        result = mod.load_golden_cases(str(tmp_path))
        assert len(result) == 1
        assert result[0]["name"] == "test_single_coil"

    def test_skips_malformed_json(self, tmp_path: Path) -> None:
        mod = _import_export()
        (tmp_path / "bad.json").write_text("{invalid json{{", encoding="utf-8")
        (tmp_path / "good.json").write_text(
            json.dumps(_VALID_CASE), encoding="utf-8"
        )
        result = mod.load_golden_cases(str(tmp_path))
        assert len(result) == 1


class TestExportFunction:
    """export() writes JSONL to disk."""

    def test_writes_jsonl(self, tmp_path: Path) -> None:
        mod = _import_export()
        # Write a golden case to a temp golden dir
        golden_dir = tmp_path / "golden"
        golden_dir.mkdir()
        (golden_dir / "case01.json").write_text(
            json.dumps(_VALID_CASE), encoding="utf-8"
        )
        out_path = tmp_path / "out.jsonl"
        n = mod.export(
            golden_dir=str(golden_dir),
            out_path=str(out_path),
            kind="architect",
        )
        assert n == 1
        assert out_path.exists()
        lines = out_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert "messages" in obj

    def test_both_kind_doubles_output(self, tmp_path: Path) -> None:
        mod = _import_export()
        golden_dir = tmp_path / "golden"
        golden_dir.mkdir()
        (golden_dir / "case01.json").write_text(
            json.dumps(_VALID_CASE), encoding="utf-8"
        )
        out_path = tmp_path / "both.jsonl"
        n = mod.export(
            golden_dir=str(golden_dir),
            out_path=str(out_path),
            kind="both",
        )
        assert n == 2  # one architect + one analyst example

    def test_double_coil_case_excluded_from_export(self, tmp_path: Path) -> None:
        mod = _import_export()
        golden_dir = tmp_path / "golden"
        golden_dir.mkdir()
        (golden_dir / "bad.json").write_text(
            json.dumps(_DOUBLE_COIL_CASE), encoding="utf-8"
        )
        out_path = tmp_path / "out.jsonl"
        n = mod.export(
            golden_dir=str(golden_dir),
            out_path=str(out_path),
            kind="architect",
        )
        assert n == 0

    def test_invalid_kind_raises(self, tmp_path: Path) -> None:
        mod = _import_export()
        with pytest.raises(ValueError, match="kind must be"):
            mod.export(
                golden_dir=str(tmp_path),
                out_path=str(tmp_path / "out.jsonl"),
                kind="invalid",
            )

    def test_missing_golden_dir_writes_empty(self, tmp_path: Path) -> None:
        mod = _import_export()
        out_path = tmp_path / "out.jsonl"
        n = mod.export(
            golden_dir="/nonexistent/golden",
            out_path=str(out_path),
            kind="architect",
        )
        assert n == 0
        assert out_path.exists()


class TestTrainLoraImport:
    """train_lora module must import without torch/peft installed."""

    def test_module_imports_cleanly(self) -> None:
        """The heavy imports are deferred; importing the module must not fail."""
        mod = importlib.import_module("training.train_lora")
        assert mod is not None

    def test_config_dataclass_accessible(self) -> None:
        mod = importlib.import_module("training.train_lora")
        cfg = mod.LoRATrainConfig()
        assert cfg.base_model == "Qwen/Qwen2.5-Coder-7B-Instruct"
        assert cfg.lora_r == 16
        assert cfg.lora_alpha == 32
        assert cfg.bf16 is True
        assert cfg.gradient_checkpointing is True
        assert "q_proj" in cfg.target_modules

    def test_train_function_exists(self) -> None:
        mod = importlib.import_module("training.train_lora")
        assert callable(mod.train)
