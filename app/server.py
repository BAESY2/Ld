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

from app.error_codes import DB as ERROR_DB
from app.error_codes import ErrorCode, Vendor
from app.graph import run_pipeline
from app.models import LadderProgram, StateMachineSpec, VerificationIssue, VerificationReport
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


class GenerateRequest(BaseModel):
    request: str


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
