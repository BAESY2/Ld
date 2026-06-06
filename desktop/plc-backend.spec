# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 스펙 — 자가포함 백엔드(plc-backend) 단일 실행파일.
# 저장소 루트에서:  pyinstaller --clean -y desktop/plc-backend.spec
# 산출: dist/plc-backend (onefile). 정적 프론트(frontend/)와 RAG 코퍼스(data/)를
# 함께 번들하므로, 별도 파일 배포 없이 더블클릭으로 도는 오프라인 앱이 된다.
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [("frontend", "frontend"), ("data", "data")]
binaries = []
hiddenimports = ["app.server", *collect_submodules("uvicorn")]

# z3(네이티브 라이브러리)·uvicorn·fastapi·pydantic 의 동반 파일/바이너리를 모두 수집.
for pkg in ("z3", "uvicorn", "fastapi", "pydantic", "starlette"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["desktop/backend_entry.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)
# EXE 에 a.binaries/a.datas 를 직접 넘기면 onefile(단일 실행파일)로 묶인다.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="plc-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
)
