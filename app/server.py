"""FastAPI 서버 — 라이브 미리보기 + 자연어 생성 백엔드.

  POST /api/transpile  : ST → 래더 JSON + 검증(결정론, 키 불필요)
  POST /api/generate   : 자연어 → ST + 래더 + 검증 (LLM)
  GET  /api/errorcodes : 에러코드 조회
  GET  /healthz · /version
  GET  /               : 정적 프론트(웹 래더 에디터)
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import __version__
from app.config import settings
from app.error_codes import DB as ERROR_DB
from app.error_codes import ErrorCode, Vendor
from app.graph import run_pipeline
from app.models import LadderProgram, StateMachineSpec, VerificationIssue, VerificationReport
from app.transpiler import transpile_st
from app.verifier import check_double_coils

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("plc.server")

app = FastAPI(title="PLC Ladder Agent", version=__version__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_STATIC_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    """예기치 못한 예외를 깔끔한 JSON 에러로 (스택 노출 금지)."""
    logger.exception("처리되지 않은 예외: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": "내부 서버 오류"})


class TranspileRequest(BaseModel):
    st_code: str = Field(..., max_length=settings.max_st_chars)
    title: str = Field(default="", max_length=200)


class TranspileResponse(BaseModel):
    ladder: LadderProgram
    issues: list[VerificationIssue]
    ok: bool


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict[str, str]:
    return {
        "version": __version__,
        "llm_provider": settings.llm_provider,
        "use_z3": str(settings.use_z3),
        "use_rag": str(settings.use_rag),
    }


@app.post("/api/transpile", response_model=TranspileResponse)
def transpile(req: TranspileRequest) -> TranspileResponse:
    """ST 를 래더로 변환하고 이중코일을 검사한다(결정론, 즉시)."""
    issues: list[VerificationIssue] = []
    try:
        issues.extend(check_double_coils(req.st_code))
        ladder = transpile_st(req.st_code, title=req.title)
    except ValueError as exc:
        issues.append(
            VerificationIssue(code="PARSE_ERROR", severity="error", message=str(exc))
        )
        ladder = LadderProgram(title=req.title)
    ok = not any(i.severity == "error" for i in issues)
    return TranspileResponse(ladder=ladder, issues=issues, ok=ok)


class GenerateRequest(BaseModel):
    request: str = Field(..., min_length=1, max_length=settings.max_request_chars)


class GenerateResponse(BaseModel):
    logic_analysis: str
    structured_text: str
    ladder: LadderProgram | None
    verification: VerificationReport | None
    error: str | None = None


def _logic_analysis(spec: StateMachineSpec) -> str:
    """전이 조건 → 동작을 3줄 이내로 요약한다."""
    lines: list[str] = []
    for tr in spec.transitions[:3]:
        target = next((s for s in spec.states if s.name == tr.to_state), None)
        actions = "; ".join(target.on_entry) if target else ""
        lines.append(f"{tr.condition} → {tr.to_state} ({actions})")
    if spec.interlocks:
        pairs = ", ".join(f"{i.output_a}⊥{i.output_b}" for i in spec.interlocks)
        lines.append(f"인터락: {pairs}")
    return "\n".join(lines) if lines else "(요약 없음)"


@app.post("/api/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest) -> GenerateResponse:
    """자연어 → ST + 래더 + 검증. LLM 사용(키 없으면 error 로 안내)."""
    state = run_pipeline(req.request)
    analysis = _logic_analysis(state.spec) if state.spec is not None else ""
    return GenerateResponse(
        logic_analysis=analysis,
        structured_text=state.st_code,
        ladder=state.ladder,
        verification=state.verification,
        error=state.error,
    )


@app.get("/api/errorcodes", response_model=list[ErrorCode])
def error_codes(vendor: str = "", q: str = "") -> list[ErrorCode]:
    """에러코드 조회. vendor/q 로 필터(부분일치, 대소문자 무시)."""
    v: Vendor | None = None
    if vendor:
        try:
            v = Vendor(vendor)
        except ValueError:
            return []
    return ERROR_DB.search(q, v)


# 정적 프론트(있을 때만 마운트) — API 라우트 뒤에 둔다
if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="frontend")
