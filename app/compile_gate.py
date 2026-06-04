"""matiec 컴파일 게이트 (선택적 의존성, LLM4PLC 검증 스택).

생성된 ST 가 **실제로 IEC 61131-3 문법으로 컴파일되는지** 오픈소스 matiec
(``iec2c``)로 확인한다. matiec 가 설치돼 있으면 게이트가 동작하고, 없으면
조용히 건너뛴다(z3 와 동일한 선택적-의존성 패턴 — API 키/외부툴 없이 CI 통과).

LLM4PLC 연구가 쓰는 것과 동일한 게이트: matiec(문법) → (선택) nuXmv(의미).
여기서는 문법 게이트만 다룬다.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

_IDENT_RE = re.compile(r"[A-Za-z_]\w*")
_KEYWORDS = {
    "AND", "OR", "NOT", "TRUE", "FALSE", "XOR", "MOD",
    "IF", "THEN", "ELSE", "ELSIF", "END_IF",
}


def matiec_available() -> bool:
    """matiec 컴파일러(iec2c)가 PATH 에 있는지."""
    return shutil.which("iec2c") is not None


@dataclass(frozen=True)
class CompileResult:
    """컴파일 게이트 결과."""

    ok: bool
    skipped: bool
    message: str


def _collect_idents(st_code: str) -> list[str]:
    """ST 에서 변수 식별자를 수집한다(키워드 제외, 순서 보존)."""
    names: list[str] = []
    seen: set[str] = set()
    for tok in _IDENT_RE.findall(st_code):
        if tok.upper() in _KEYWORDS or tok in seen:
            continue
        seen.add(tok)
        names.append(tok)
    return names


def wrap_program(st_code: str) -> str:
    """ST 본문을 컴파일 가능한 완전한 IEC 프로그램+컨피그로 감싼다.

    모든 식별자를 BOOL VAR 로 선언한다(현재 합성 ST 는 전부 불리언).
    """
    idents = _collect_idents(st_code)
    var_block = "\n".join(f"  {name} : BOOL;" for name in idents)
    return (
        "PROGRAM Main\n"
        "VAR\n"
        f"{var_block}\n"
        "END_VAR\n"
        f"{st_code}\n"
        "END_PROGRAM\n\n"
        "CONFIGURATION Config0\n"
        "  RESOURCE Res0 ON PLC\n"
        "    TASK MainTask(INTERVAL := T#20ms, PRIORITY := 0);\n"
        "    PROGRAM Inst0 WITH MainTask : Main;\n"
        "  END_RESOURCE\n"
        "END_CONFIGURATION\n"
    )


def compile_check(st_code: str, timeout: float = 20.0) -> CompileResult:
    """ST 가 matiec 로 컴파일되는지 확인한다(미설치 시 skip).

    반환 ok 는 'skip 이면 True(게이트 미적용)'로 둬서 파이프라인을 막지 않는다.
    """
    if not matiec_available():
        return CompileResult(
            ok=True, skipped=True, message="matiec(iec2c) 미설치 — 컴파일 게이트 건너뜀"
        )

    program = wrap_program(st_code)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "prog.st"
        src.write_text(program, encoding="utf-8")
        try:
            proc = subprocess.run(
                ["iec2c", str(src)],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:  # pragma: no cover - 환경 의존
            return CompileResult(ok=False, skipped=False, message=f"iec2c 실행 실패: {exc}")

    if proc.returncode == 0:
        return CompileResult(ok=True, skipped=False, message="컴파일 성공")
    detail = (proc.stderr or proc.stdout or "").strip()
    return CompileResult(ok=False, skipped=False, message=f"컴파일 실패: {detail}")
