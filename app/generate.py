"""파일 생성(codegen) 서브시스템 — 입력 1건 → 래더 프로젝트 파일 일괄 생성.

Claude Code / Codex 식 "생성하면서 파일로 떨어뜨리기". 결정론 파이프라인
(synth/transpile/verify/emit/export)을 오케스트레이션해 디스크에 쓴다.

- **ST 입력**: LLM 절대 미사용(키 불필요·CI 안전).
- **자연어 입력**: run_pipeline 으로 NL→ST 합성(LLM, analyst 경계).
- 진행 상황은 ``on_progress`` 콜백(GenEvent)으로 흘려 CLI/웹 스트리밍 공용.
- 경로 안전: out_dir 밖으로 절대 쓰지 않는다.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from app import __version__
from app.emit import render_for_vendor
from app.explain import explain_all
from app.export import infer_io_spec, to_plcopen_xml
from app.memory_map import DeviceAllocator
from app.models import LadderProgram, StateMachineSpec, VerificationReport
from app.safety import SAFETY_INLINE_HINT, SAFETY_NOTICE
from app.transpiler import transpile_st
from app.vendors.profiles import DEFAULT_PROFILE, available_profiles, get_profile
from app.verifier import verify

_SLUG_RE = re.compile(r"[^a-z0-9_-]+")


# ---------------------------------------------------------------------------
# 모델
# ---------------------------------------------------------------------------
class GeneratedFile(BaseModel):
    path: str = Field(..., description="프로젝트 디렉터리 기준 상대 경로")
    kind: str
    bytes: int
    sha256: str
    vendor: str | None = None


class Manifest(BaseModel):
    schema_version: int = 1
    project: str
    tool_version: str = __version__
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    from_nl: bool
    used_llm: bool
    vendors: list[str]
    title: str = ""
    verification_passed: bool = False
    verification_issue_count: int = 0
    files: list[GeneratedFile] = Field(default_factory=list)
    safety_notice: str = SAFETY_NOTICE
    error: str | None = None


class GenEvent(BaseModel):
    """파이프라인 진행 이벤트 — CLI/웹 스트리밍 공용."""

    stage: str
    status: str = "ok"  # start|ok|error|skip
    message: str = ""
    file: str | None = None
    detail: dict[str, str] = Field(default_factory=dict)


ProgressFn = Callable[[GenEvent], None]


class GenerationError(Exception):
    """생성 파이프라인 실패."""


# ---------------------------------------------------------------------------
# 경로 안전
# ---------------------------------------------------------------------------
def _slugify(raw: str) -> str:
    s = _SLUG_RE.sub("-", raw.strip().lower()).strip("-")
    return s or "ladder"


def _safe_join(base: Path, rel: str) -> Path:
    """base 밖으로 새는 경로를 차단(.. / 절대경로 / 심볼릭 탈출)."""
    if Path(rel).is_absolute():
        raise ValueError(f"절대 경로 금지: {rel}")
    target = (base / rel).resolve()
    base_r = base.resolve()
    if base_r != target and base_r not in target.parents:
        raise ValueError(f"out_dir 밖 쓰기 차단: {rel}")
    return target


def _validate_vendors(vendors: list[str]) -> None:
    known = set(available_profiles())
    for v in vendors:
        if v not in known:
            raise ValueError(f"알 수 없는 벤더 '{v}' (가능: {', '.join(sorted(known))})")


# ---------------------------------------------------------------------------
# 산출물 빌드(메모리)
# ---------------------------------------------------------------------------
class _Artifacts:
    def __init__(
        self,
        spec: StateMachineSpec,
        st: str,
        ladder: LadderProgram,
        report: VerificationReport,
        il_texts: dict[str, str],
        plcopen: str,
        vendors: list[str],
        used_llm: bool,
    ) -> None:
        self.spec, self.st, self.ladder, self.report = spec, st, ladder, report
        self.il_texts, self.plcopen = il_texts, plcopen
        self.vendors, self.used_llm = vendors, used_llm


def _build(
    source: str,
    *,
    from_nl: bool,
    vendors: list[str],
    title: str,
    allow_llm: bool,
    emit: ProgressFn,
) -> _Artifacts:
    _validate_vendors(vendors)

    if from_nl:
        if not allow_llm:
            raise ValueError("자연어 입력은 LLM 이 필요합니다(allow_llm=False 와 충돌).")
        from app.graph import run_pipeline  # 지연 임포트(LLM 경로에서만)

        emit(GenEvent(stage="analyze", status="start", message="자연어 → 명세"))
        state = run_pipeline(source)
        if state.error or state.spec is None or state.verification is None:
            raise GenerationError(state.error or "파이프라인 실패")
        spec, st, report = state.spec, state.st_code, state.verification
        ladder = state.ladder or transpile_st(st, title=spec.title)
        used_llm = True
    else:
        emit(GenEvent(stage="synthesize", status="skip", message="ST 입력 — 합성 생략"))
        spec = infer_io_spec(source, title=title)
        alloc = DeviceAllocator().build_from_spec(spec)
        st = f"{alloc.as_comment_block()}\n\n{source.strip()}\n"
        emit(GenEvent(stage="verify", status="start"))
        report = verify(spec, st)
        emit(GenEvent(stage="transpile", status="start"))
        ladder = transpile_st(st, allocator=alloc, title=spec.title)
        used_llm = False

    il_texts: dict[str, str] = {}
    for v in vendors:
        emit(GenEvent(stage="emit", status="start", detail={"vendor": v}))
        il_texts[v] = render_for_vendor(st, spec, get_profile(v))

    emit(GenEvent(stage="export", status="start", message="PLCopen XML"))
    plcopen = to_plcopen_xml(spec, st)
    return _Artifacts(spec, st, ladder, report, il_texts, plcopen, vendors, used_llm)


def _render_readme(m_project: str, art: _Artifacts) -> str:
    verdict = "통과" if art.report.passed else f"실패({len(art.report.issues)}건)"
    file_lines = "\n".join(
        f"- `{f}`" for f in _expected_relpaths(art.vendors)
    )
    return (
        f"# {m_project}\n\n"
        f"PLC 래더 자동 생성 프로젝트 (tool {__version__}).\n\n"
        f"- 입력 방식: {'자연어(LLM)' if art.used_llm else 'ST(결정론)'}\n"
        f"- 검증: {verdict}\n"
        f"- 벤더: {', '.join(art.vendors)}\n\n"
        f"## 파일\n{file_lines}\n\n"
        f"## ⚠️ 안전 경계\n\n> {SAFETY_NOTICE}\n\n"
        f"`plcopen.xml` 은 OpenPLC Editor / CODESYS 로 임포트해 검토하세요.\n"
    )


def _expected_relpaths(vendors: list[str]) -> list[str]:
    rels = [
        "manifest.json", "README.md", "SAFETY.md", "spec.json", "program.st",
        "ladder.json", "EXPLAIN.md", "verification.json", "plcopen.xml",
    ]
    for v in vendors:
        ext = "stl" if get_profile(v).il_style == "stl" else "il"
        rels.append(f"il/{v}.{ext}")
    return rels


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------
def generate_project(
    source: str,
    out_dir: str | Path,
    *,
    from_nl: bool,
    vendors: list[str] | None = None,
    name: str | None = None,
    title: str = "",
    force: bool = False,
    allow_llm: bool = True,
    on_progress: ProgressFn | None = None,
) -> Manifest:
    """입력 1건(NL 또는 ST)에서 래더 프로젝트 파일을 생성하고 Manifest 를 반환한다."""
    emit: ProgressFn = on_progress or (lambda ev: None)
    vendors = vendors or [DEFAULT_PROFILE.name]

    root = Path(out_dir)
    project = _slugify(name or title or "ladder")
    project_dir = _safe_join(root, project)

    if project_dir.exists() and any(project_dir.iterdir()) and not force:
        raise ValueError(f"이미 존재하는 프로젝트: {project_dir} (덮어쓰려면 force=True)")

    try:
        art = _build(
            source, from_nl=from_nl, vendors=vendors, title=title,
            allow_llm=allow_llm, emit=emit,
        )
    except (GenerationError, ValueError) as exc:
        # 실패해도 manifest 로 기록(검사 가능하게)
        project_dir.mkdir(parents=True, exist_ok=True)
        manifest = Manifest(
            project=project, from_nl=from_nl, used_llm=from_nl,
            vendors=vendors, title=title, error=str(exc),
        )
        _safe_join(project_dir, "manifest.json").write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )
        emit(GenEvent(stage="done", status="error", message=str(exc)))
        raise

    # force 재생성 시 기존 트리를 비워 잔여(orphan) 파일이 남지 않게 한다
    if project_dir.exists() and force:
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    files: list[GeneratedFile] = []

    def put(rel: str, text: str, kind: str, vendor: str | None = None) -> None:
        target = _safe_join(project_dir, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = text.encode("utf-8")
        target.write_bytes(data)
        files.append(
            GeneratedFile(
                path=rel, kind=kind, bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(), vendor=vendor,
            )
        )
        emit(GenEvent(stage="write", status="ok", file=rel))

    put("SAFETY.md", SAFETY_NOTICE + "\n", "safety")
    put("spec.json", art.spec.model_dump_json(indent=2), "spec")
    st_body = art.st if art.st.endswith("\n") else art.st + "\n"
    put("program.st", f"{SAFETY_INLINE_HINT}\n{st_body}", "st")
    put("ladder.json", art.ladder.model_dump_json(indent=2), "ladder")
    put("EXPLAIN.md", explain_all(art.spec, art.ladder, art.report) + "\n", "explain")
    put("verification.json", art.report.model_dump_json(indent=2), "verification")
    put("plcopen.xml", art.plcopen, "plcopen")
    for v, text in art.il_texts.items():
        ext = "stl" if get_profile(v).il_style == "stl" else "il"
        put(f"il/{v}.{ext}", text, "il", vendor=v)
    put("README.md", _render_readme(project, art), "readme")

    manifest = Manifest(
        project=project,
        from_nl=from_nl,
        used_llm=art.used_llm,
        vendors=vendors,
        title=art.spec.title or title,
        verification_passed=art.report.passed,
        verification_issue_count=len(art.report.issues),
        files=files,
    )
    # manifest 는 마지막에 — 존재 자체가 완료 신호
    _safe_join(project_dir, "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    emit(GenEvent(stage="done", status="ok", message=f"{len(files) + 1} files"))
    return manifest
