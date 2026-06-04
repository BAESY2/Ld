"""FastAPI 서버 — 라이브 미리보기 백엔드.

결정론 경로(키 불필요)만 우선 노출한다:
  POST /api/transpile : ST → 래더 JSON + 검증(이중코일)
  GET  /healthz
  GET  /                : 정적 프론트(웹 래더 에디터)

LLM 자연어 경로(/api/generate)는 Phase D/E 완료 후 추가한다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.models import LadderProgram, VerificationIssue
from app.transpiler import transpile_st
from app.verifier import check_double_coils

app = FastAPI(title="PLC Ladder Live Preview", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_STATIC_DIR = Path(__file__).resolve().parent.parent / "frontend"


class TranspileRequest(BaseModel):
    st_code: str
    title: str = ""


class TranspileResponse(BaseModel):
    ladder: LadderProgram
    issues: list[VerificationIssue]
    ok: bool


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


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


# 정적 프론트(있을 때만 마운트) — API 라우트 뒤에 둔다
if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="frontend")
