"""설정 로더 테스트."""

from __future__ import annotations

import pytest

from app.config import Settings


def test_env_overrides_are_reflected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("MAX_REVISIONS", "5")
    monkeypatch.setenv("USE_RAG", "true")
    monkeypatch.setenv("ARCHITECT_MODEL", "qwen2.5-coder-32b")

    s = Settings()

    assert s.llm_provider == "local"
    assert s.max_revisions == 5
    assert s.use_rag is True
    assert s.architect_model == "qwen2.5-coder-32b"


def test_defaults() -> None:
    s = Settings()
    assert s.max_revisions == 3
    assert s.use_z3 is True
