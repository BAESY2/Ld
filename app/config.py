"""환경변수 → 타입 안전 설정 객체.

LLM 프로바이더는 여기서만 선택한다(vendor-agnostic). agents._llm() 이 이 값을 읽는다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal, cast

from dotenv import load_dotenv

load_dotenv()

LlmProvider = Literal["anthropic", "openai_compatible", "local"]


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or not raw.strip():
        return default
    return int(raw)


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None or not raw.strip():
        return default
    return float(raw)


@dataclass(frozen=True)
class Settings:
    """파이프라인 전역 설정. 환경변수에서 로드."""

    llm_provider: LlmProvider = field(
        default_factory=lambda: cast(LlmProvider, _env("LLM_PROVIDER", "anthropic"))
    )
    analyst_model: str = field(default_factory=lambda: _env("ANALYST_MODEL", "claude-sonnet-4-6"))
    architect_model: str = field(default_factory=lambda: _env("ARCHITECT_MODEL", "claude-opus-4-8"))
    renderer_model: str = field(default_factory=lambda: _env("RENDERER_MODEL", "claude-sonnet-4-6"))
    local_base_url: str = field(default_factory=lambda: _env("LOCAL_BASE_URL", "http://localhost:8000/v1"))

    temperature: float = field(default_factory=lambda: _env_float("TEMPERATURE", 0.0))
    max_revisions: int = field(default_factory=lambda: _env_int("MAX_REVISIONS", 3))
    use_rag: bool = field(default_factory=lambda: _env_bool("USE_RAG", False))
    use_z3: bool = field(default_factory=lambda: _env_bool("USE_Z3", True))

    # 서버 하드닝
    cors_origins: str = field(default_factory=lambda: _env("CORS_ORIGINS", "*"))
    max_st_chars: int = field(default_factory=lambda: _env_int("MAX_ST_CHARS", 50_000))
    max_request_chars: int = field(default_factory=lambda: _env_int("MAX_REQUEST_CHARS", 4_000))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))

    # 파일 생성(codegen) 출력 루트
    gen_out_dir: str = field(default_factory=lambda: _env("GEN_OUT_DIR", "out"))

    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
