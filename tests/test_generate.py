"""파일 생성(codegen) 서브시스템 테스트.

ST 경로는 LLM 없이(키 불필요) 전체 파일셋을 만들고, 경로 안전을 보장해야 한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import agents
from app.generate import (
    GenEvent,
    Manifest,
    _safe_join,
    _slugify,
    generate_project,
)
from app.safety import SAFETY_NOTICE


def _no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """_llm 호출 시 실패시켜 ST 경로가 LLM 을 안 쓰는지 보장."""
    def boom(model: str) -> object:
        raise AssertionError("ST 경로에서 LLM 을 호출하면 안 된다")

    monkeypatch.setattr(agents, "_llm", boom)


_ST = "MOTOR := (START OR MOTOR) AND NOT STOP;"


def test_st_path_generates_full_fileset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_llm(monkeypatch)
    m = generate_project(
        _ST, tmp_path, from_nl=False, vendors=["LS_XGK", "MITSUBISHI_FX"], name="demo"
    )
    assert isinstance(m, Manifest)
    assert m.used_llm is False
    proj = tmp_path / "demo"
    for rel in ("manifest.json", "SAFETY.md", "spec.json", "program.st",
                "ladder.json", "verification.json", "plcopen.xml",
                "il/LS_XGK.il", "il/MITSUBISHI_FX.il", "README.md"):
        assert (proj / rel).exists(), f"누락: {rel}"


def test_manifest_roundtrip_and_hashes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_llm(monkeypatch)
    generate_project(_ST, tmp_path, from_nl=False, name="demo")
    raw = json.loads((tmp_path / "demo" / "manifest.json").read_text(encoding="utf-8"))
    m2 = Manifest.model_validate(raw)
    assert m2.project == "demo"
    assert m2.verification_passed is True
    # 모든 파일에 sha256/bytes 기록
    assert all(f.sha256 and f.bytes > 0 for f in m2.files)


def test_safety_file_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_llm(monkeypatch)
    generate_project(_ST, tmp_path, from_nl=False, name="demo")
    assert SAFETY_NOTICE in (tmp_path / "demo" / "SAFETY.md").read_text(encoding="utf-8")


def test_siemens_uses_stl_extension(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_llm(monkeypatch)
    generate_project(_ST, tmp_path, from_nl=False, vendors=["SIEMENS_S7"], name="s")
    assert (tmp_path / "s" / "il" / "SIEMENS_S7.stl").exists()


def test_progress_events_emitted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_llm(monkeypatch)
    events: list[GenEvent] = []
    generate_project(_ST, tmp_path, from_nl=False, name="demo", on_progress=events.append)
    stages = {e.stage for e in events}
    assert {"verify", "transpile", "emit", "export", "write", "done"} <= stages
    assert any(e.stage == "done" and e.status == "ok" for e in events)


def test_unknown_vendor_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_llm(monkeypatch)
    with pytest.raises(ValueError, match="알 수 없는 벤더"):
        generate_project(_ST, tmp_path, from_nl=False, vendors=["NOPE"], name="x")


def test_no_overwrite_without_force(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_llm(monkeypatch)
    generate_project(_ST, tmp_path, from_nl=False, name="demo")
    with pytest.raises(ValueError, match="이미 존재"):
        generate_project(_ST, tmp_path, from_nl=False, name="demo")
    # force 면 덮어쓰기 성공
    generate_project(_ST, tmp_path, from_nl=False, name="demo", force=True)


def test_nl_path_requires_llm_allowed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="LLM"):
        generate_project("자연어", tmp_path, from_nl=True, allow_llm=False, name="x")


# --- 경로 안전 ---
def test_safe_join_blocks_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _safe_join(tmp_path, "../etc/passwd")
    with pytest.raises(ValueError):
        _safe_join(tmp_path, "/etc/passwd")
    # 정상 상대경로는 통과
    assert _safe_join(tmp_path, "il/LS_XGK.il").name == "LS_XGK.il"


def test_slugify() -> None:
    assert _slugify("컨베이어 Conveyor #1!") == "conveyor-1"
    assert _slugify("   ") == "ladder"


def test_cli_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_llm(monkeypatch)
    from app.gen import main

    rc = main(["--st", _ST, "--out", str(tmp_path), "--no-llm", "--name", "cli", "-q"])
    assert rc == 0
    assert (tmp_path / "cli" / "manifest.json").exists()
