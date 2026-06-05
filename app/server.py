"""FastAPI 서버 — 라이브 미리보기 + 자연어 생성 백엔드.

  POST /api/transpile        : ST → 래더 JSON + 검증(결정론, 키 불필요)
  POST /api/emit             : ST → 벤더별 래더 명령어 텍스트(IL/STL)
  POST /api/export/plcopen   : ST → PLCopen XML(OpenPLC/CODESYS 임포트)
  POST /api/generate         : 자연어 → ST + 래더 + 검증 (LLM)
  GET  /api/recipes          : 가이드 마법사 레시피 목록(키 불필요)
  POST /api/wizard           : 레시피+답변 → 설계 (결정론, 키 불필요)
  POST /api/generate/files   : 파일 생성 진행 SSE 스트림(Codex 식)
  GET  /api/generated/{p}/.. : 생성된 파일 조회
  GET  /api/errorcodes       : 에러코드 조회
  GET  /api/safety           : 안전 경계 고지
  GET  /healthz · /version
  GET  /                     : 정적 프론트(웹 래더 에디터)
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import uuid
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import __version__
from app.config import settings
from app.emit import emit as emit_ladder
from app.error_codes import DB as ERROR_DB
from app.error_codes import ErrorCode, Vendor
from app.explain import explain_all
from app.export import infer_io_spec, to_plcopen_xml
from app.generate import GenEvent, _safe_join, generate_project
from app.graph import run_pipeline
from app.models import LadderProgram, StateMachineSpec, VerificationIssue, VerificationReport
from app.safety import SAFETY_NOTICE, safety_payload
from app.synth import synthesize_st
from app.transpiler import transpile_st
from app.vendors.profiles import DEFAULT_PROFILE, available_profiles, get_profile
from app.verifier import check_double_coils, verify
from app.wizard import build_spec, list_recipes

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
    safety_notice: str = SAFETY_NOTICE


def _no_logic_issue(st_code: str, rung_count: int) -> VerificationIssue | None:
    """입력이 비어있지 않은데 렁이 0개면 'NO_LOGIC' 경고를 만든다(가짜 통과 방지)."""
    if st_code.strip() and rung_count == 0:
        return VerificationIssue(
            code="NO_LOGIC",
            severity="warning",
            message="유효한 래더 로직이 생성되지 않았습니다(ST 가 대입문이 아닐 수 있음).",
        )
    return None


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


@app.get("/api/safety")
def safety() -> dict[str, str]:
    """안전 경계 고지 — 검증은 논리 보조이며 안전 인증이 아님(K3)."""
    return safety_payload()


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
    nl = _no_logic_issue(req.st_code, len(ladder.rungs))
    if nl is not None:
        issues.append(nl)
    ok = not any(i.severity == "error" for i in issues) and not any(
        i.code == "NO_LOGIC" for i in issues
    )
    return TranspileResponse(ladder=ladder, issues=issues, ok=ok)


class EmitRequest(BaseModel):
    st_code: str = Field(..., max_length=settings.max_st_chars)
    vendor: str = Field(default="LS_XGK")


class EmitResponse(BaseModel):
    vendor: str
    text: str
    ok: bool
    error: str | None = None
    safety_notice: str = SAFETY_NOTICE


@app.post("/api/emit", response_model=EmitResponse)
def emit(req: EmitRequest) -> EmitResponse:
    """ST → 벤더별 래더 명령어 텍스트(IL/STL) 렌더(결정론, Phase N)."""
    try:
        profile = get_profile(req.vendor)
    except KeyError:
        return EmitResponse(
            vendor=req.vendor,
            text="",
            ok=False,
            error=f"알 수 없는 벤더: {req.vendor} (가능: {', '.join(available_profiles())})",
        )
    try:
        program = transpile_st(req.st_code)
        text = emit_ladder(program, profile)
    except ValueError as exc:
        return EmitResponse(vendor=req.vendor, text="", ok=False, error=str(exc))
    if _no_logic_issue(req.st_code, len(program.rungs)) is not None:
        return EmitResponse(
            vendor=req.vendor, text=text, ok=False, error="유효한 래더 로직이 없습니다."
        )
    return EmitResponse(vendor=req.vendor, text=text, ok=True)


class ExportRequest(BaseModel):
    st_code: str = Field(..., max_length=settings.max_st_chars)
    title: str = Field(default="", max_length=200)


class ExportResponse(BaseModel):
    format: str
    content: str
    ok: bool
    error: str | None = None
    safety_notice: str = SAFETY_NOTICE


@app.post("/api/export/plcopen", response_model=ExportResponse)
def export_plcopen(req: ExportRequest) -> ExportResponse:
    """ST → PLCopen XML(OpenPLC/CODESYS 임포트 가능, Phase N)."""
    try:
        spec = infer_io_spec(req.st_code, title=req.title)
        xml = to_plcopen_xml(spec, req.st_code)
    except ValueError as exc:
        return ExportResponse(format="plcopen-xml", content="", ok=False, error=str(exc))
    return ExportResponse(format="plcopen-xml", content=xml, ok=True)


class GenerateFilesRequest(BaseModel):
    st_code: str = Field(default="", max_length=settings.max_st_chars)
    request: str = Field(default="", max_length=settings.max_request_chars)
    vendors: list[str] = Field(default_factory=lambda: [DEFAULT_PROFILE.name], max_length=8)
    name: str | None = None
    title: str = ""


@app.post("/api/generate/files")
async def generate_files(req: GenerateFilesRequest) -> StreamingResponse:
    """파일 생성 진행을 SSE 로 스트리밍한다(Codex 식 실시간 생성).

    ST 입력이면 LLM 미사용. 진행 이벤트(event: progress) → 최종 event: manifest.
    파일은 서버 gen_out_dir 아래에 쓰이며 /api/generated/... 로 조회한다.
    """
    from_nl = not req.st_code.strip()
    source = req.st_code if not from_nl else req.request
    # 이름 미지정 시 고유 run-id 로 → 동시 요청이 같은 디렉터리에 충돌하지 않음
    run_name = req.name or f"run-{uuid.uuid4().hex[:8]}"

    async def event_stream() -> AsyncIterator[str]:
        queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue()

        def on_progress(ev: GenEvent) -> None:
            queue.put_nowait(("progress", ev.model_dump_json()))

        async def worker() -> None:
            try:
                if not source.strip():
                    raise ValueError("입력이 비어 있습니다(st_code 또는 request 필요).")
                manifest = await asyncio.to_thread(
                    generate_project,
                    source,
                    settings.gen_out_dir,
                    from_nl=from_nl,
                    vendors=req.vendors,
                    name=run_name,
                    title=req.title,
                    force=True,
                    allow_llm=from_nl,
                    on_progress=on_progress,
                )
                queue.put_nowait(("manifest", manifest.model_dump_json()))
            except Exception as exc:  # noqa: BLE001
                queue.put_nowait(("error", json.dumps({"error": str(exc)}, ensure_ascii=False)))
            queue.put_nowait(None)

        task = asyncio.create_task(worker())
        while True:
            item = await queue.get()
            if item is None:
                break
            name, data = item
            yield f"event: {name}\ndata: {data}\n\n"
        await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/generated/{project}.zip")
def download_zip(project: str) -> Response:
    """생성된 프로젝트를 ZIP 으로 내려받는다(gen_out_dir 아래로 제한)."""
    base = Path(settings.gen_out_dir)
    try:
        proj_dir = _safe_join(base, project)
    except ValueError:
        return PlainTextResponse("경로 거부", status_code=400)
    if not proj_dir.is_dir():
        return PlainTextResponse("프로젝트 없음", status_code=404)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(proj_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(proj_dir).as_posix())
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{project}.zip"'},
    )


@app.get("/api/generated/{project}/{path:path}", response_class=PlainTextResponse)
def read_generated(project: str, path: str) -> PlainTextResponse:
    """생성된 파일 내용을 반환한다(gen_out_dir 아래로 경로 제한)."""
    base = Path(settings.gen_out_dir)
    try:
        target = _safe_join(base, f"{project}/{path}")
    except ValueError:
        return PlainTextResponse("경로 거부", status_code=400)
    if not target.is_file():
        return PlainTextResponse("파일 없음", status_code=404)
    return PlainTextResponse(target.read_text(encoding="utf-8"))


@app.get("/api/recipes")
def recipes() -> list[dict[str, object]]:
    """가이드 마법사 레시피 목록(비전문가용 템플릿)."""
    return list_recipes()


class WizardRequest(BaseModel):
    recipe: str
    answers: dict[str, str] = Field(default_factory=dict)


class WizardResponse(BaseModel):
    ok: bool
    title: str = ""
    structured_text: str = ""
    ladder: LadderProgram | None = None
    verification: VerificationReport | None = None
    explanation: str = ""
    error: str | None = None
    safety_notice: str = SAFETY_NOTICE


@app.post("/api/wizard", response_model=WizardResponse)
def wizard(req: WizardRequest) -> WizardResponse:
    """레시피+답변 → 결정론 설계(명세→ST→래더→검증→평문설명). LLM/키 불필요."""
    try:
        spec = build_spec(req.recipe, req.answers)
    except KeyError:
        return WizardResponse(ok=False, error=f"알 수 없는 레시피: {req.recipe}")
    st = synthesize_st(spec)
    ladder = transpile_st(st, title=spec.title)
    report = verify(spec, st)
    return WizardResponse(
        ok=report.passed,
        title=spec.title,
        structured_text=st,
        ladder=ladder,
        verification=report,
        explanation=explain_all(spec, ladder, report),
    )


class GenerateRequest(BaseModel):
    request: str = Field(..., min_length=1, max_length=settings.max_request_chars)


class GenerateResponse(BaseModel):
    logic_analysis: str
    structured_text: str
    ladder: LadderProgram | None
    verification: VerificationReport | None
    explanation: str = ""
    error: str | None = None
    safety_notice: str = SAFETY_NOTICE


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
    explanation = ""
    if state.spec is not None and state.ladder is not None and state.verification is not None:
        explanation = explain_all(state.spec, state.ladder, state.verification)
    return GenerateResponse(
        logic_analysis=analysis,
        structured_text=state.st_code,
        ladder=state.ladder,
        verification=state.verification,
        explanation=explanation,
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
