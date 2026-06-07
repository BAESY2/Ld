"""FastAPI 서버 — 라이브 미리보기 + 자연어 생성 백엔드.

  POST /api/transpile        : ST → 래더 JSON + 검증(결정론, 키 불필요)
  POST /api/emit             : ST → 벤더별 래더 명령어 텍스트(IL/STL)
  POST /api/export/plcopen   : ST → PLCopen XML(OpenPLC/CODESYS 임포트)
  POST /api/generate         : 자연어 → ST + 래더 + 검증 (LLM)
  GET  /api/recipes          : 가이드 마법사 레시피 목록(키 불필요)
  POST /api/nl-design        : 자연어 → 레시피 매칭+슬롯+설계 (결정론, 키 불필요)
  POST /api/wizard           : 레시피+답변 → 설계 (결정론, 키 불필요)
  POST /api/simulate         : ST → 가상 PLC 스캔 가동(디지털 트윈, 키 불필요)
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
from pydantic import BaseModel, Field, model_validator

from app import __version__
from app.comms.protocols import WriteRejected
from app.comms.safety_kernel import SafetyKernel
from app.config import settings
from app.design import design_and_verify
from app.emit import emit as emit_ladder
from app.error_codes import DB as ERROR_DB
from app.error_codes import ErrorCode, Vendor
from app.explain import explain_all
from app.export import infer_io_spec, to_plcopen_xml
from app.generate import GenEvent, _safe_join, generate_project
from app.graph import run_pipeline
from app.memory_map import DeviceAllocator
from app.models import (
    CrossInterlock,
    IODirection,
    LadderProgram,
    ModuleInstance,
    Project,
    StateMachineSpec,
    VerificationIssue,
    VerificationReport,
)
from app.nlmatch import analyze as nl_analyze
from app.project import ProjectError, compose, scaffold_from_recipes, scaffold_mutex
from app.safety import SAFETY_NOTICE, safety_payload
from app.simulator import MAX_SIM_SAMPLES, simulate
from app.synth import synthesize_st
from app.transpiler import transpile_st
from app.vendors import LS_XGK
from app.vendors.profiles import DEFAULT_PROFILE, available_profiles, get_profile
from app.verifier import check_double_coils, verify
from app.wizard import RECIPES, WizardError, build_spec, list_recipes
from app.xgk import simulate_xgk

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
    # 출하 게이트: 이중코일 결함은 미리보기뿐 아니라 *내보내기*에서도 막는다(CLAUDE #3).
    dbl = [i for i in check_double_coils(req.st_code) if i.severity == "error"]
    if dbl:
        return EmitResponse(
            vendor=req.vendor, text="", ok=False,
            error="이중 코일 검출 — 출하 차단: " + "; ".join(i.message for i in dbl),
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
    dbl = [i for i in check_double_coils(req.st_code) if i.severity == "error"]
    if dbl:
        return ExportResponse(
            format="plcopen-xml", content="", ok=False,
            error="이중 코일 검출 — 내보내기 차단: " + "; ".join(i.message for i in dbl),
        )
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


# 카테고리 표시 순서/그룹 라벨 — 21개 레시피를 UI 에서 의미 그룹으로 묶는다.
# (뿌리산업/안전/순차/모션 등). 미지정 카테고리는 뒤에 사전순으로 붙는다.
_CATEGORY_ORDER: tuple[str, ...] = (
    "기본", "타이머", "카운터", "공정", "모드",
    "순차", "뿌리산업", "안전", "모션", "알람",
)


@app.get("/api/recipes")
def recipes() -> list[dict[str, object]]:
    """가이드 마법사 레시피 목록(비전문가용 템플릿, 21개·평면 목록)."""
    return list_recipes()


@app.get("/api/recipes/grouped")
def recipes_grouped() -> dict[str, object]:
    """레시피를 카테고리(뿌리산업/안전/순차/모션 …)별로 묶어 반환한다.

    UI 가 그룹 헤더로 21개를 탐색할 수 있게 한다. 평면 ``recipes`` 도 함께 실어
    기존 클라이언트 호환을 유지한다(결정론·키 불필요).
    """
    flat = list_recipes()
    by_cat: dict[str, list[dict[str, object]]] = {}
    for r in flat:
        by_cat.setdefault(str(r["category"]), []).append(r)
    ordered_cats = [c for c in _CATEGORY_ORDER if c in by_cat]
    ordered_cats += sorted(c for c in by_cat if c not in _CATEGORY_ORDER)
    groups = [
        {"category": c, "recipes": by_cat[c], "count": len(by_cat[c])}
        for c in ordered_cats
    ]
    return {"total": len(flat), "groups": groups, "recipes": flat}


class NLDesignRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=settings.max_request_chars)
    autobuild: bool = True


class ScaffoldModule(BaseModel):
    name: str
    recipe: str
    recipe_title: str = ""
    safety_note: str = ""


class NLDesignResponse(BaseModel):
    ok: bool
    recipe: str
    recipe_title: str = ""
    ranked: list[dict[str, object]] = Field(default_factory=list)
    filled_answers: dict[str, str] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    confident: bool = False
    provisional: bool = False  # 확신 못 해 설계를 보류함 → 후보 중 선택 필요
    suggestion: str = ""
    design: WizardResponse | None = None
    safety_warning: str = ""
    out_of_scope: str = ""  # 21개 템플릿 밖(아날로그/모션/통신/PID 등) → 정직 거절
    multi_intent: str = ""  # 다중 서브시스템 감지 → 침묵 부분생성 대신 개별 합성 안내
    multi_intent_ids: list[str] = Field(default_factory=list)
    # 다중의도일 때 감지된 레시피로 만든 *검증 통과* 다중모듈 골격(스튜디오가 바로 채택).
    scaffold: list[ScaffoldModule] = Field(default_factory=list)
    scaffold_cross_interlocks: list[CrossInterlock] = Field(default_factory=list)
    scaffold_verified: bool = False
    safety_notice: str = SAFETY_NOTICE


@app.post("/api/nl-design", response_model=NLDesignResponse)
def nl_design(req: NLDesignRequest) -> NLDesignResponse:
    """자연어 → 레시피 매칭 + 슬롯(키 불필요). autobuild 면 곧장 설계까지."""
    res = nl_analyze(req.text, allow_llm=False)
    recipe_obj = RECIPES[res.recipe_id]
    ranked = [
        {"id": rid, "title": RECIPES[rid].title, "score": round(s, 3)}
        for rid, s in res.scores[:3]
    ]
    out_of_scope = res.extras.get("out_of_scope", "")
    multi_intent = res.extras.get("multi_intent", "")
    multi_intent_ids = (
        res.extras["multi_intent_ids"].split(",") if "multi_intent_ids" in res.extras else []
    )
    # 다중의도/상호배제면 감지 결과로 검증 통과 골격을 만들어 바로 채택 가능케 한다.
    scaffold, scaffold_cis, scaffold_verified = _build_scaffold(res.extras, req.text[:40])
    if out_of_scope:
        suggestion = "21개 결정론 템플릿 밖의 요청이에요(아날로그·모션·통신·PID 등)."
    elif multi_intent:
        suggestion = (
            f"{multi_intent} {len(scaffold)}개 모듈 골격"
            f"{'(검증 통과)' if scaffold_verified else ''}을 잡아뒀어요 — 채택해 다듬으세요."
            if scaffold else multi_intent
        )
    elif res.confident:
        suggestion = f"'{recipe_obj.title}'(으)로 이해했어요."
    else:
        cands = ", ".join(RECIPES[rid].title for rid, _ in res.scores[:3])
        suggestion = f"정확히 못 찾았어요. 후보 중 골라주세요: {cands}"
    safety_warning = res.extras.get("safety_warning", "")
    # 확신할 때(그리고 안전필수어가 없을 때)만 설계를 만든다 — 확신 없으면 후보를
    # 고르게 하고, 자신있게 *틀린* 래더(또는 비상정지를 소프트정지로)를 렌더하지 않는다(P0).
    design = None
    if req.autobuild and res.confident and not safety_warning:
        design = wizard(WizardRequest(recipe=res.recipe_id, answers=res.answers))
    return NLDesignResponse(
        ok=True, recipe=res.recipe_id, recipe_title=recipe_obj.title, ranked=ranked,
        filled_answers=res.answers, missing=res.missing, questions=res.questions,
        confident=res.confident,
        provisional=(design is None and req.autobuild),
        suggestion=suggestion, design=design,
        safety_warning=safety_warning, out_of_scope=out_of_scope,
        multi_intent=multi_intent, multi_intent_ids=multi_intent_ids,
        scaffold=scaffold, scaffold_cross_interlocks=scaffold_cis,
        scaffold_verified=scaffold_verified,
    )


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
    safety_note: str = ""  # 이 레시피 특유의 안전 주의(응답에 직접 노출)
    error: str | None = None
    safety_notice: str = SAFETY_NOTICE


@app.post("/api/wizard", response_model=WizardResponse)
def wizard(req: WizardRequest) -> WizardResponse:
    """레시피+답변 → 결정론 설계(명세→ST→래더→검증→평문설명). LLM/키 불필요."""
    try:
        spec = build_spec(req.recipe, req.answers)
    except KeyError:
        return WizardResponse(ok=False, error=f"알 수 없는 레시피: {req.recipe}")
    except WizardError as exc:
        return WizardResponse(ok=False, error=str(exc))
    try:
        st = synthesize_st(spec)
        ladder = transpile_st(st, title=spec.title)
    except ValueError as exc:
        return WizardResponse(ok=False, error=f"설계 생성 실패: {exc}")
    if not ladder.rungs:
        return WizardResponse(
            ok=False, title=spec.title,
            error="유효한 래더 로직이 만들어지지 않았어요. 신호 이름을 확인해 주세요.",
        )
    report = verify(spec, st)
    return WizardResponse(
        ok=report.passed,
        title=spec.title,
        structured_text=st,
        ladder=ladder,
        verification=report,
        explanation=explain_all(spec, ladder, report),
        safety_note=RECIPES[req.recipe].safety_note,
    )


# ---------------------------------------------------------------------------
# 프로젝트 합성 — 서브시스템 N개를 하나의 프로그램으로(대규모 설계 진입점)
# ---------------------------------------------------------------------------
class ProjectComposeRequest(BaseModel):
    """모듈 N개 + 교차 인터락 → 합성 요청. 상태는 클라이언트가 들고 매번 보낸다."""

    title: str = Field(default="", max_length=200)
    modules: list[ModuleInstance] = Field(default_factory=list, max_length=64)
    cross_interlocks: list[CrossInterlock] = Field(default_factory=list, max_length=128)


class ProjectModuleSummary(BaseModel):
    name: str
    recipe: str
    recipe_title: str = ""
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    safety_note: str = ""  # 이 모듈(레시피) 특유의 안전 주의 — 합성해도 사라지지 않게 노출


class AddrEntry(BaseModel):
    symbol: str
    address: str


class ProjectComposeResponse(BaseModel):
    ok: bool
    title: str = ""
    structured_text: str = ""
    ladder: LadderProgram | None = None
    verification: VerificationReport | None = None
    explanation: str = ""
    modules: list[ProjectModuleSummary] = Field(default_factory=list)
    address_map: list[AddrEntry] = Field(default_factory=list)
    error: str | None = None
    safety_notice: str = SAFETY_NOTICE


def _module_summaries(req: ProjectComposeRequest) -> list[ProjectModuleSummary]:
    """모듈별 입출력 심볼 요약(렌더 심볼 = 네임스페이스/공유 적용 후)."""
    out: list[ProjectModuleSummary] = []
    for m in req.modules:
        title = RECIPES[m.recipe].title if m.recipe in RECIPES else ""
        note = RECIPES[m.recipe].safety_note if m.recipe in RECIPES else ""
        try:
            sub = build_spec(m.recipe, m.answers)
        except (KeyError, WizardError):
            out.append(ProjectModuleSummary(
                name=m.name, recipe=m.recipe, recipe_title=title, safety_note=note
            ))
            continue

        def render(sym: str, mod: ModuleInstance = m) -> str:
            return mod.shared.get(sym, f"{mod.name}__{sym}")

        ins = [render(p.symbol) for p in sub.io_points if p.direction == IODirection.INPUT]
        outs = [render(p.symbol) for p in sub.io_points if p.direction == IODirection.OUTPUT]
        out.append(
            ProjectModuleSummary(
                name=m.name, recipe=m.recipe, recipe_title=title,
                inputs=ins, outputs=outs, safety_note=note,
            )
        )
    return out


def _address_map(spec: StateMachineSpec) -> list[AddrEntry]:
    """합성 명세를 전역 디바이스 할당기에 넣어 심볼→주소 맵을 만든다(충돌 0 확인용)."""
    alloc = DeviceAllocator().build_from_spec(spec)
    entries: list[AddrEntry] = []
    seen: set[str] = set()
    for iop in spec.io_points:
        if iop.symbol in seen:
            continue
        seen.add(iop.symbol)
        addr = alloc.address_of(iop.symbol)
        if addr is not None:
            entries.append(AddrEntry(symbol=iop.symbol, address=addr))
    for t in spec.timers:
        addr = alloc.address_of(t.name)
        if addr is not None:
            entries.append(AddrEntry(symbol=t.name, address=addr))
    for c in spec.counters:
        addr = alloc.address_of(c.name)
        if addr is not None:
            entries.append(AddrEntry(symbol=c.name, address=addr))
    return entries


@app.post("/api/project/compose", response_model=ProjectComposeResponse)
def project_compose(req: ProjectComposeRequest) -> ProjectComposeResponse:
    """프로젝트(모듈 N개)를 하나의 ST→래더→검증으로 합성한다(결정론·키 불필요).

    대규모 설계의 진입점: 같은 레시피를 이름만 달리해 여러 번 넣어도 네임스페이스로
    주소·심볼 충돌 0, 이중코일 0 이 구조적으로 보장된다. 교차 인터락은 Z3 로 검증.
    """
    if not req.modules:
        return ProjectComposeResponse(ok=False, error="모듈을 1개 이상 추가하세요.")
    project = Project(
        title=req.title, modules=req.modules, cross_interlocks=req.cross_interlocks
    )
    try:
        spec = compose(project)
        st = synthesize_st(spec)
        ladder = transpile_st(st, title=spec.title)
    except ProjectError as exc:
        return ProjectComposeResponse(ok=False, error=str(exc))
    except ValueError as exc:
        return ProjectComposeResponse(ok=False, error=f"합성 실패: {exc}")
    if not ladder.rungs:
        return ProjectComposeResponse(
            ok=False, title=spec.title,
            error="유효한 래더 로직이 만들어지지 않았어요(상태구동 출력이 없는 모듈일 수 있음).",
        )
    report = verify(spec, st)
    return ProjectComposeResponse(
        ok=report.passed,
        title=spec.title or req.title,
        structured_text=st,
        ladder=ladder,
        verification=report,
        explanation=explain_all(spec, ladder, report),
        modules=_module_summaries(req),
        address_map=_address_map(spec),
    )


def _suggest_name(recipe_id: str, taken: set[str]) -> str:
    """레시피 id 앞토막 + 최소 미사용 번호로 모듈 이름을 제안한다(예: motor1)."""
    base = recipe_id.split("_", 1)[0] or "mod"
    i = 1
    while f"{base}{i}" in taken:
        i += 1
    return f"{base}{i}"


def _scaffold_project(extras: dict[str, str], title: str) -> Project | None:
    """analyze extras → 채택할 Project 골격. mutex(다중 기계 상호배제) 우선, 그다음 compound."""
    if "mutex_recipe" in extras:
        return scaffold_mutex(
            extras["mutex_recipe"], int(extras.get("mutex_count", "2")),
            title=title or "상호배제 골격",
        )
    if "multi_intent_ids" in extras:
        ids = [i for i in extras["multi_intent_ids"].split(",") if i]
        if ids:
            return scaffold_from_recipes(ids, title=title or "자동 골격")
    return None


def _build_scaffold(
    extras: dict[str, str], title: str
) -> tuple[list[ScaffoldModule], list[CrossInterlock], bool]:
    """감지 결과 → 검증 시도한 골격(모듈 + 교차인터락 + 검증여부). 스튜디오가 바로 채택."""
    proj = _scaffold_project(extras, title)
    if proj is None or not proj.modules:
        return [], [], False
    verified = False
    try:
        spec = compose(proj)
        verified = verify(spec, synthesize_st(spec)).passed
    except Exception:  # noqa: BLE001 - 골격 검증 실패는 verified=False 로만 반영
        verified = False
    mods = [
        ScaffoldModule(
            name=m.name, recipe=m.recipe,
            recipe_title=RECIPES[m.recipe].title if m.recipe in RECIPES else "",
            safety_note=RECIPES[m.recipe].safety_note if m.recipe in RECIPES else "",
        )
        for m in proj.modules
    ]
    return mods, list(proj.cross_interlocks), verified


class ProjectNLAddRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=settings.max_request_chars)
    existing_names: list[str] = Field(default_factory=list, max_length=64)


class ProjectNLAddResponse(BaseModel):
    ok: bool
    recipe: str = ""
    recipe_title: str = ""
    suggested_name: str = ""
    answers: dict[str, str] = Field(default_factory=dict)
    confident: bool = False
    ranked: list[dict[str, object]] = Field(default_factory=list)
    suggestion: str = ""
    safety_warning: str = ""
    out_of_scope: str = ""
    multi_intent: str = ""
    scaffold: list[ScaffoldModule] = Field(default_factory=list)
    scaffold_cross_interlocks: list[CrossInterlock] = Field(default_factory=list)
    scaffold_verified: bool = False
    safety_notice: str = SAFETY_NOTICE


@app.post("/api/project/nl-add", response_model=ProjectNLAddResponse)
def project_nl_add(req: ProjectNLAddRequest) -> ProjectNLAddResponse:
    """자연어 한 문장 → 프로젝트에 더할 모듈 제안(레시피+이름+슬롯). 결정론·키 불필요.

    클라이언트가 이 제안을 프로젝트 목록에 넣고 ``/api/project/compose`` 를 다시
    호출하면 즉시 래더·시뮬이 갱신된다(대화형 증분 편집의 결정론 백본).
    """
    res = nl_analyze(req.text, allow_llm=False)
    recipe_obj = RECIPES[res.recipe_id]
    ranked = [
        {"id": rid, "title": RECIPES[rid].title, "score": round(s, 3)}
        for rid, s in res.scores[:3]
    ]
    out_of_scope = res.extras.get("out_of_scope", "")
    safety_warning = res.extras.get("safety_warning", "")
    multi_intent = res.extras.get("multi_intent", "")
    scaffold, scaffold_cis, scaffold_verified = _build_scaffold(res.extras, req.text[:40])
    if out_of_scope:
        suggestion = "21개 결정론 템플릿 밖의 요청이에요(아날로그·모션·통신·PID 등)."
    elif multi_intent:
        suggestion = (
            f"{multi_intent} {len(scaffold)}개 모듈 골격으로 한 번에 담을게요"
            f"{'(검증 통과)' if scaffold_verified else ''} — 채택 후 다듬으세요."
            if scaffold else multi_intent
        )
    elif res.confident:
        suggestion = f"'{recipe_obj.title}' 모듈로 추가할게요."
    else:
        cands = ", ".join(RECIPES[rid].title for rid, _ in res.scores[:3])
        suggestion = f"정확히 못 찾았어요. 후보 중 골라주세요: {cands}"
    name = _suggest_name(res.recipe_id, set(req.existing_names))
    return ProjectNLAddResponse(
        ok=True,
        recipe=res.recipe_id,
        recipe_title=recipe_obj.title,
        suggested_name=name,
        answers=res.answers,
        confident=res.confident and not safety_warning and not out_of_scope,
        ranked=ranked,
        suggestion=suggestion,
        safety_warning=safety_warning,
        out_of_scope=out_of_scope,
        multi_intent=multi_intent,
        scaffold=scaffold,
        scaffold_cross_interlocks=scaffold_cis,
        scaffold_verified=scaffold_verified,
    )


# ---------------------------------------------------------------------------
# LLM 설계 — 자유 한국어 문단 → 다중 서브시스템 분해 → 결정론 검증(근간 재설계의 심장)
# ---------------------------------------------------------------------------
class DesignRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=settings.max_request_chars)


class DesignResponse(BaseModel):
    ok: bool
    title: str = ""
    structured_text: str = ""
    ladder: LadderProgram | None = None
    verification: VerificationReport | None = None
    explanation: str = ""
    modules: list[ProjectModuleSummary] = Field(default_factory=list)
    address_map: list[AddrEntry] = Field(default_factory=list)
    project: Project | None = None  # studio 가 인라인 명세 모듈을 채택·재합성하도록 동봉
    revisions: int = 0              # verify→재생성 폐루프가 돈 횟수
    error: str | None = None
    safety_notice: str = SAFETY_NOTICE


def _summarize_project(project: Project) -> list[ProjectModuleSummary]:
    """모듈별 입출력 요약(인라인 명세/레시피 공통). 렌더 심볼=네임스페이스 적용 후."""
    out: list[ProjectModuleSummary] = []
    for m in project.modules:
        sub = m.spec
        title = ""
        if sub is None and m.recipe in RECIPES:
            title = RECIPES[m.recipe].title
            try:
                sub = build_spec(m.recipe, m.answers)
            except (KeyError, WizardError):
                sub = None
        if sub is None:
            out.append(ProjectModuleSummary(name=m.name, recipe=m.recipe, recipe_title=title))
            continue

        def render(sym: str, mod: ModuleInstance = m) -> str:
            return mod.shared.get(sym, f"{mod.name}__{sym}")

        ins = [render(p.symbol) for p in sub.io_points if p.direction == IODirection.INPUT]
        outs = [render(p.symbol) for p in sub.io_points if p.direction == IODirection.OUTPUT]
        out.append(
            ProjectModuleSummary(
                name=m.name, recipe=m.recipe, recipe_title=title or m.recipe,
                inputs=ins, outputs=outs,
            )
        )
    return out


@app.post("/api/design", response_model=DesignResponse)
def design(req: DesignRequest) -> DesignResponse:
    """자유 한국어 요구 → LLM 이 다중 서브시스템으로 분해 → 결정론 합성·검증.

    32개 템플릿/키워드 매칭의 천장을 넘는 경로: LLM 이 임의 명세를 생성하고, 코어가
    compose→verify 로 검증/차단한다. 키가 없거나 LLM 미설치면 친절히 안내(503 아님,
    ok=false). 검증 실패해도 결과를 돌려주되 ok=false 로 표시한다(불량 은닉 금지).
    """
    try:
        result = design_and_verify(req.text)
    except ValueError as exc:
        return DesignResponse(ok=False, error=str(exc))
    except Exception as exc:  # noqa: BLE001 - LLM 미설치/키 없음 등을 친절히 안내
        logger.warning("설계 LLM 실패: %s", exc)
        return DesignResponse(
            ok=False,
            error="자연어 설계에는 LLM 설정이 필요합니다(ANTHROPIC_API_KEY 등). "
            "키 없이 쓰려면 좌측 console 의 레시피 매칭 경로를 사용하세요.",
        )
    if result.spec is None:  # 합성 단계에서 실패(폐루프도 못 고침)
        return DesignResponse(
            ok=False, error=result.error or "합성 실패",
            project=result.project, modules=_summarize_project(result.project),
            revisions=result.revisions,
        )
    ladder = transpile_st(result.st_code, title=result.spec.title)
    if not ladder.rungs:
        return DesignResponse(
            ok=False, title=result.spec.title,
            error="유효한 래더 로직이 생성되지 않았습니다(요구가 이산 제어로 표현 어려울 수 있음).",
            project=result.project, modules=_summarize_project(result.project),
            revisions=result.revisions,
        )
    report = result.report
    assert report is not None
    return DesignResponse(
        ok=report.passed,
        title=result.spec.title or result.project.title,
        structured_text=result.st_code,
        ladder=ladder,
        verification=report,
        explanation=explain_all(result.spec, ladder, report),
        modules=_summarize_project(result.project),
        address_map=_address_map(result.spec),
        project=result.project,
        revisions=result.revisions,
    )


_MAX_SIM_CELLS = 200_000  # 응답 셀(샘플×신호) 상한 — 다신호 ST 폭증 차단


class SimulateRequest(BaseModel):
    st_code: str = Field(..., max_length=settings.max_st_chars)
    inputs_timeline: list[tuple[int, dict[str, bool]]] = Field(
        default_factory=list, max_length=10_000
    )
    duration_ms: int = Field(default=5000, ge=0, le=600_000)
    step_ms: int = Field(default=100, ge=1, le=10_000)

    @model_validator(mode="after")
    def _cap_sample_count(self) -> SimulateRequest:
        # 증폭형 DoS 차단: duration/step 비율이 커도 스캔 샘플 수를 상한으로 제한.
        n = self.duration_ms // self.step_ms + 1
        if n > MAX_SIM_SAMPLES:
            raise ValueError(
                f"스캔 샘플 {n}개가 상한({MAX_SIM_SAMPLES})을 초과합니다. "
                f"duration_ms 를 줄이거나 step_ms 를 키우세요."
            )
        return self


class SimulateResponse(BaseModel):
    ok: bool
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    samples: list[dict[str, object]] = Field(default_factory=list)
    error: str | None = None
    safety_notice: str = SAFETY_NOTICE


@app.post("/api/simulate", response_model=SimulateResponse)
def simulate_endpoint(req: SimulateRequest) -> SimulateResponse:
    """ST 를 가상 PLC로 스캔 가동(디지털 트윈, 결정론·키 불필요)."""
    try:
        res = simulate(
            req.st_code, req.inputs_timeline,
            duration_ms=req.duration_ms, step_ms=req.step_ms,
        )
    except ValueError as exc:
        return SimulateResponse(ok=False, error=str(exc))
    if not res.outputs and req.st_code.strip():
        # 대입문이 없는(=구동 출력 0) ST 는 가짜 통과를 막기 위해 NO_LOGIC 으로 처리.
        return SimulateResponse(
            ok=False, inputs=res.inputs, outputs=res.outputs,
            error="NO_LOGIC: 시뮬레이션할 출력(코일 대입)이 없습니다.",
        )
    # 셀 예산(샘플×신호) 상한 — 응답 폭증(메모리·대역폭) 차단(샘플수 캡만으로는
    # 다신호 ST 가 수십 MB 를 만들 수 있음).
    cells = len(res.samples) * max(1, len(res.outputs) + len(res.inputs))
    if cells > _MAX_SIM_CELLS:
        return SimulateResponse(
            ok=False, inputs=res.inputs, outputs=res.outputs,
            error=(f"결과 셀 {cells}개가 상한({_MAX_SIM_CELLS})을 초과합니다 — "
                   "duration_ms 를 줄이거나 step_ms 를 키우세요."),
        )
    return SimulateResponse(
        ok=True, inputs=res.inputs, outputs=res.outputs,
        samples=[{"t_ms": s.t_ms, "inputs": s.inputs, "outputs": s.outputs}
                 for s in res.samples],
    )


# ---------------------------------------------------------------------------
# XGK 자체검증 — 에미트된 LS_XGK 니모닉을 검증된 ST 와 차분 대조(결정론·키 불필요)
# ---------------------------------------------------------------------------
class VerifyXgkRequest(BaseModel):
    """ST 를 직접 주거나(st_code), 레시피+답변으로 합성한다(recipe)."""

    st_code: str = Field(default="", max_length=settings.max_st_chars)
    recipe: str = Field(default="", max_length=200)
    answers: dict[str, str] = Field(default_factory=dict)
    duration_ms: int = Field(default=12_000, ge=0, le=600_000)
    step_ms: int = Field(default=100, ge=1, le=10_000)

    @model_validator(mode="after")
    def _cap_sample_count(self) -> VerifyXgkRequest:
        n = self.duration_ms // self.step_ms + 1
        if n > MAX_SIM_SAMPLES:
            raise ValueError(
                f"스캔 샘플 {n}개가 상한({MAX_SIM_SAMPLES})을 초과합니다."
            )
        return self


class XgkMismatch(BaseModel):
    output: str
    sample: int
    t_ms: int
    st_value: bool
    xgk_value: bool


class VerifyXgkResponse(BaseModel):
    ok: bool
    agree: bool = False
    mismatches: list[XgkMismatch] = Field(default_factory=list)
    xgk_text: str = ""
    st: str = ""
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    error: str | None = None
    safety_notice: str = SAFETY_NOTICE


def _exercise_timeline(inputs: list[str], duration_ms: int, step_ms: int) -> list[
    tuple[int, dict[str, bool]]
]:
    """기본 운동 타임라인 — 입력을 시차로 켜고 끄며 seal-in/엣지 경로를 친다.

    차분 검사(test_xgk_differential 의 staggered)와 같은 패턴으로, 키 없이도
    유의미한 자극을 준다. duration 을 넘지 않게 안전하게 묶는다.
    """
    tl: list[tuple[int, dict[str, bool]]] = []
    span = max(step_ms, 1)
    for i, s in enumerate(inputs):
        on = span * (3 * i + 1)
        off = span * (3 * i + 1) + span * 6
        if on <= duration_ms:
            tl.append((on, {s: True}))
        if off <= duration_ms:
            tl.append((off, {s: False}))
    return tl


@app.post("/api/verify-xgk", response_model=VerifyXgkResponse)
def verify_xgk(req: VerifyXgkRequest) -> VerifyXgkResponse:
    """LS_XGK 니모닉을 에미트하고 검증된 ST 시뮬레이터와 샘플 단위로 대조한다.

    '에미트 == 검증된 ST' 증명을 사용자에게 노출한다(결정론·키 불필요).
    st_code 가 비어 있으면 recipe+answers 로 결정론 합성한다.
    """
    st = req.st_code.strip()
    if not st:
        if not req.recipe:
            return VerifyXgkResponse(ok=False, error="st_code 또는 recipe 가 필요합니다.")
        try:
            spec = build_spec(req.recipe, req.answers)
            st = synthesize_st(spec)
        except KeyError:
            return VerifyXgkResponse(ok=False, error=f"알 수 없는 레시피: {req.recipe}")
        except (WizardError, ValueError) as exc:
            return VerifyXgkResponse(ok=False, error=str(exc))
    if not st.strip():
        return VerifyXgkResponse(ok=False, error="합성된 ST 가 비어 있습니다.")
    try:
        xgk_text = emit_ladder(transpile_st(st), LS_XGK)
        sres = simulate(st, [], duration_ms=0, step_ms=req.step_ms)
        timeline = _exercise_timeline(sres.inputs, req.duration_ms, req.step_ms)
        full = simulate(st, timeline, duration_ms=req.duration_ms, step_ms=req.step_ms)
        xres = simulate_xgk(
            xgk_text, timeline, duration_ms=req.duration_ms, step_ms=req.step_ms
        )
    except ValueError as exc:
        return VerifyXgkResponse(ok=False, st=st, error=str(exc))

    mismatches: list[XgkMismatch] = []
    if sorted(full.outputs) != sorted(xres.outputs):
        # 출력 심볼 집합 자체가 다르면 전체 불일치로 간주(코일 누락 등).
        only = set(full.outputs) ^ set(xres.outputs)
        for o in sorted(only):
            mismatches.append(
                XgkMismatch(output=o, sample=-1, t_ms=-1, st_value=False, xgk_value=False)
            )
    for o in full.outputs:
        a = full.output_trace(o)
        b = xres.output_trace(o)
        for k, (x, y) in enumerate(zip(a, b, strict=False)):
            if x != y:
                mismatches.append(
                    XgkMismatch(
                        output=o, sample=k, t_ms=k * req.step_ms,
                        st_value=x, xgk_value=y,
                    )
                )
                break  # 출력당 최초 발산만 보고(간결)
    agree = not mismatches
    return VerifyXgkResponse(
        ok=True, agree=agree, mismatches=mismatches[:50], xgk_text=xgk_text, st=st,
        inputs=full.inputs, outputs=full.outputs,
    )


# ---------------------------------------------------------------------------
# 안전커널 미리보기 — 가짜 인메모리 링크 위에서 쓰기 게이팅을 시연(하드웨어 불요)
# ---------------------------------------------------------------------------
class _FakeLink:
    """인메모리 PlcLink — 실기 없이 SafetyKernel 의 deny-by-default 를 시연한다.

    write_inputs 는 마지막 통과 명령만 보관하고 read_outputs 로 되읽는다.
    """

    def __init__(self) -> None:
        self.last_write: dict[str, bool] = {}

    def write_inputs(self, values: dict[str, bool]) -> None:
        self.last_write.update(values)

    def read_outputs(self) -> dict[str, bool]:
        return dict(self.last_write)

    def close(self) -> None:  # pragma: no cover - 트리비얼
        return None


class SafetyPreviewRequest(BaseModel):
    recipe: str = Field(..., max_length=200)
    answers: dict[str, str] = Field(default_factory=dict)
    command: dict[str, bool] = Field(default_factory=dict, max_length=64)


class SafetyPreviewResponse(BaseModel):
    ok: bool
    allowed: bool = False
    reason: str = ""
    command: dict[str, bool] = Field(default_factory=dict)
    audit: list[dict[str, str]] = Field(default_factory=list)
    input_symbols: list[str] = Field(default_factory=list)
    error: str | None = None
    safety_notice: str = SAFETY_NOTICE


@app.post("/api/safety-preview", response_model=SafetyPreviewResponse)
def safety_preview(req: SafetyPreviewRequest) -> SafetyPreviewResponse:
    """레시피 명세로 SafetyKernel 을 세워 명령 쓰기를 가상 게이팅한다(하드웨어 불요).

    deny-by-default 안전 게이팅을 실기 없이 노출한다(결정론·키 불필요).
    """
    try:
        spec = build_spec(req.recipe, req.answers)
    except KeyError:
        return SafetyPreviewResponse(ok=False, error=f"알 수 없는 레시피: {req.recipe}")
    except (WizardError, ValueError) as exc:
        return SafetyPreviewResponse(ok=False, error=str(exc))
    input_symbols = sorted(
        p.symbol for p in spec.io_points if p.direction == IODirection.INPUT
    )
    kernel = SafetyKernel(_FakeLink(), spec)
    allowed = False
    reason = "안전검증 통과"
    try:
        kernel.write_inputs(req.command)
        allowed = True
    except WriteRejected as exc:
        reason = str(exc)
    audit = [{"decision": d, "reason": r} for d, r in kernel.audit_log()]
    return SafetyPreviewResponse(
        ok=True, allowed=allowed, reason=reason, command=req.command,
        audit=audit, input_symbols=input_symbols,
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
