"""브라우저 단독판(docs/web.html) 정합 테스트 — 엔진 모듈 목록 드리프트 가드.

web.html 은 저장소의 app/*.py 를 그대로 fetch 해 WASM(Pyodide)에서 실행한다.
컴파일 경로의 import 체인이 바뀌었는데 web.html 모듈 목록이 안 따라가면 링크가
조용히 깨진다 — 여기서 ast 로 실제 체인을 재계산해 목록과 대조한다.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "docs" / "web.html"

# web.html 이 브라우저에서 import 하는 진입 모듈(엔진 공개 표면).
_ENTRY = [
    "intent", "compile_frame", "synth", "verifier", "transpiler", "plant",
    "explain", "export", "emit",
]


def _import_chain(entries: list[str]) -> set[str]:
    """app 패키지 내부 import 체인(전이적)을 ast 로 계산한다.

    모듈이 *패키지*(디렉터리)면 __init__.py 만이 아니라 패키지 안 모든 .py 를
    파싱한다 — 서브모듈(예: export/plcopen.py)이 끌어오는 의존(app.safety)을
    놓치면 web.html 이 런타임에 ModuleNotFoundError 로 깨진다(실제 회귀).
    """
    seen: set[str] = set()
    queue = list(entries)
    while queue:
        m = queue.pop()
        if m in seen:
            continue
        seen.add(m)
        flat = ROOT / "app" / f"{m}.py"
        pkg = ROOT / "app" / m
        files = [flat] if flat.exists() else sorted(pkg.glob("*.py")) if pkg.is_dir() else []
        for p in files:
            tree = ast.parse(p.read_text(encoding="utf-8"))
            for n in ast.walk(tree):
                mods: list[str] = []
                if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("app"):
                    mods = [n.module]
                elif isinstance(n, ast.Import):
                    mods = [a.name for a in n.names if a.name.startswith("app.")]
                for mm in mods:
                    parts = mm.split(".")
                    if len(parts) >= 2 and parts[1] not in seen:
                        queue.append(parts[1])
    return seen


def _listed(name: str) -> list[str]:
    text = WEB.read_text(encoding="utf-8")
    m = re.search(name + r"\s*=\s*\[(.*?)\]", text, re.S)
    assert m, f"web.html 에 {name} 목록이 없다"
    return re.findall(r'"([^"]+)"', m.group(1))


def test_web_html_exists_and_loads_engine_from_repo() -> None:
    text = WEB.read_text(encoding="utf-8")
    assert "loadPyodide" in text                    # WASM 런타임
    assert "raw.githubusercontent.com/baesy2/ld" in text  # 저장소 소스 그대로
    assert "frame_to_spec" in text                  # 진짜 컴파일러 호출


def _listed_pkgs() -> dict[str, list[str]]:
    text = WEB.read_text(encoding="utf-8")
    m = re.search(r"PKG_MODULES\s*=\s*\{(.*?)\}", text, re.S)
    assert m, "web.html 에 PKG_MODULES 가 없다"
    pkgs: dict[str, list[str]] = {}
    for pm in re.finditer(r'"(\w+)"\s*:\s*\[([^\]]*)\]', m.group(1)):
        pkgs[pm.group(1)] = re.findall(r'"([^"]+)"', pm.group(2))
    return pkgs


def test_web_module_list_covers_import_chain() -> None:
    """web.html 의 모듈 목록(평면+패키지)이 실제 import 체인을 빠짐없이 싣는다."""
    listed = set(_listed("APP_MODULES")) | {"vendors"} | set(_listed_pkgs())
    chain = _import_chain(_ENTRY)
    missing = chain - listed
    assert not missing, f"web.html 모듈 목록 누락: {sorted(missing)}"


def test_web_listed_modules_all_exist() -> None:
    """목록의 모든 모듈 파일이 실제로 존재한다(fetch 404 방지)."""
    for m in _listed("APP_MODULES"):
        assert (ROOT / "app" / f"{m}.py").exists(), m
    for m in _listed("VENDOR_MODULES"):
        assert (ROOT / "app" / "vendors" / f"{m}.py").exists(), m
    for pkg, mods in _listed_pkgs().items():
        for m in mods:
            assert (ROOT / "app" / pkg / f"{m}.py").exists(), f"{pkg}/{m}"
    for j in _listed("JS_MODULES"):
        assert (ROOT / "frontend" / j).exists(), j
