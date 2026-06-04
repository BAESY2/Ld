"""app/rag.py 단위 테스트.

USE_RAG=false (기본) 와 USE_RAG=true 두 경로를 커버한다.
monkeypatch 는 각 테스트 후 자동 복원되므로 타 테스트에 영향이 없다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import app.rag as rag_module
from app.rag import InstructionRetriever, get_instruction_context

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _set_use_rag(monkeypatch: pytest.MonkeyPatch, value: bool) -> None:
    """app.rag.settings.use_rag 를 패치한다 (frozen dataclass 우회)."""
    # settings 는 frozen dataclass 이므로 모듈 참조를 직접 교체한다.
    import app.config as config_module

    original = config_module.settings
    # object.__setattr__ 로 frozen 우회 없이, 새 Settings 인스턴스 생성
    from app.config import Settings
    new_settings = Settings.__new__(Settings)
    # dataclass 필드를 dict 로 복사 후 use_rag 만 교체
    import dataclasses
    for f in dataclasses.fields(original):
        object.__setattr__(new_settings, f.name, getattr(original, f.name))
    object.__setattr__(new_settings, "use_rag", value)

    monkeypatch.setattr(config_module, "settings", new_settings)
    monkeypatch.setattr(rag_module, "settings", new_settings)


# ---------------------------------------------------------------------------
# USE_RAG=false 경로
# ---------------------------------------------------------------------------


class TestFallbackPath:
    """USE_RAG=false 일 때 폴백 명령어를 반환해야 한다."""

    def test_get_instruction_context_returns_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_use_rag(monkeypatch, False)
        result = get_instruction_context("타이머")
        # 폴백 문자열에 포함된 키워드 확인
        assert "TON" in result or "자기유지" in result, (
            f"폴백 응답에 'TON' 또는 '자기유지' 가 없음: {result!r}"
        )

    def test_fallback_does_not_require_corpus(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """corpus 파일이 없어도 폴백이 동작해야 한다."""
        _set_use_rag(monkeypatch, False)
        # 존재하지 않는 경로를 가진 retriever
        retriever = InstructionRetriever(corpus_path=tmp_path / "nonexistent.jsonl")
        result = retriever.retrieve("타이머")
        assert "TON" in result or "자기유지" in result

    def test_fallback_contains_boolean_ops(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_use_rag(monkeypatch, False)
        result = get_instruction_context("AND OR NOT")
        assert "AND" in result

    def test_retriever_use_rag_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_use_rag(monkeypatch, False)
        retriever = InstructionRetriever()
        assert retriever.retrieve("카운터") == rag_module._FALLBACK_INSTRUCTIONS


# ---------------------------------------------------------------------------
# USE_RAG=true 경로 (corpus 검색)
# ---------------------------------------------------------------------------


class TestCorpusPath:
    """USE_RAG=true 일 때 corpus 에서 관련 항목을 찾아야 한다."""

    def test_timer_query_returns_ton(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_use_rag(monkeypatch, True)
        # corpus 캐시를 무효화해 재로드 보장
        monkeypatch.setattr(rag_module, "_corpus_cache", None)
        result = get_instruction_context("타이머")
        assert "TON" in result, f"타이머 쿼리 결과에 TON 없음: {result[:200]}"

    def test_timer_english_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_use_rag(monkeypatch, True)
        monkeypatch.setattr(rag_module, "_corpus_cache", None)
        result = get_instruction_context("timer on delay")
        assert "TON" in result

    def test_counter_query_returns_ctu(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_use_rag(monkeypatch, True)
        monkeypatch.setattr(rag_module, "_corpus_cache", None)
        result = get_instruction_context("카운터")
        assert "CTU" in result, f"카운터 쿼리 결과에 CTU 없음: {result[:200]}"

    def test_counter_english_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_use_rag(monkeypatch, True)
        monkeypatch.setattr(rag_module, "_corpus_cache", None)
        result = get_instruction_context("counter up")
        assert "CTU" in result

    def test_self_hold_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_use_rag(monkeypatch, True)
        monkeypatch.setattr(rag_module, "_corpus_cache", None)
        result = get_instruction_context("자기유지 실링")
        assert "SELF_HOLD" in result or "자기유지" in result

    def test_result_is_non_empty_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_use_rag(monkeypatch, True)
        monkeypatch.setattr(rag_module, "_corpus_cache", None)
        result = get_instruction_context("비교 GT 크다")
        assert isinstance(result, str) and len(result) > 0


# ---------------------------------------------------------------------------
# 비정상 경로: corpus 파일 없음
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """corpus 파일이 없을 때 예외 없이 폴백을 반환해야 한다."""

    def test_missing_corpus_falls_back(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _set_use_rag(monkeypatch, True)
        retriever = InstructionRetriever(corpus_path=tmp_path / "no_such_file.jsonl")
        result = retriever.retrieve("타이머")
        # 예외 없이 폴백 반환
        assert isinstance(result, str)
        assert "TON" in result or "자기유지" in result

    def test_empty_corpus_falls_back(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """빈 JSONL 파일도 예외 없이 처리해야 한다."""
        _set_use_rag(monkeypatch, True)
        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("", encoding="utf-8")
        retriever = InstructionRetriever(corpus_path=empty_file)
        result = retriever.retrieve("타이머")
        assert isinstance(result, str)
        assert "TON" in result or "자기유지" in result

    def test_malformed_jsonl_partial_load(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """일부 줄이 손상된 JSONL 이라도 유효한 줄은 로드되어야 한다."""
        _set_use_rag(monkeypatch, True)
        corpus_file = tmp_path / "partial.jsonl"
        ton_entry = (
            '{"name": "TON", "category": "TIMER", "syntax": "TON_inst(...)", '
            '"devices": "T", "description": "타이머 온딜레이", '
            '"example": "TON1(IN:=X0,PT:=T#5s);", '
            '"keywords": ["타이머", "TON"]}'
        )
        corpus_file.write_text(
            ton_entry + "\nNOT_VALID_JSON\n",
            encoding="utf-8",
        )
        retriever = InstructionRetriever(corpus_path=corpus_file)
        result = retriever.retrieve("타이머")
        assert "TON" in result


# ---------------------------------------------------------------------------
# 모듈 임포트 — faiss 없이도 임포트 가능 확인
# ---------------------------------------------------------------------------


def test_module_importable_without_faiss() -> None:
    """faiss 없이도 app.rag 를 임포트할 수 있어야 한다."""
    import sys

    # faiss 를 sys.modules 에서 가짜로 제거한 상태에서 재임포트
    faiss_backup = sys.modules.pop("faiss", None)
    try:
        # rag 모듈을 강제 재로드
        if "app.rag" in sys.modules:
            del sys.modules["app.rag"]
        import app.rag as reloaded  # noqa: F401
        assert hasattr(reloaded, "get_instruction_context")
        assert hasattr(reloaded, "InstructionRetriever")
    finally:
        if faiss_backup is not None:
            sys.modules["faiss"] = faiss_backup
        # 원래 모듈로 복원
        if "app.rag" in sys.modules:
            del sys.modules["app.rag"]
        import app.rag  # noqa: F401
