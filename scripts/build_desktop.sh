#!/usr/bin/env bash
# 자가포함 데스크톱 앱 빌드. 저장소 루트에서 실행한다.
#
#   bash scripts/build_desktop.sh           # 백엔드 단일 실행파일만 → dist/plc-backend
#   bash scripts/build_desktop.sh --tauri   # + Tauri 네이티브 창(.app/.dmg/.exe)까지
#
# 산출물(백엔드 단일 실행파일)은 그 자체로 더블클릭 시 로컬 서버를 띄우고 브라우저로
# 스튜디오를 연다(오프라인·인터넷 불필요). --tauri 는 추가로 네이티브 창으로 감싼다.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "▶ [1/2] 백엔드 자가포함 번들 (PyInstaller)…"
python -m pip install -q pyinstaller
# web 의존성(fastapi/uvicorn)이 현재 환경에 있어야 한다(pip install -e ".[web]").
python -m PyInstaller --clean -y desktop/plc-backend.spec
echo "✓ dist/plc-backend 생성 완료"

if [[ "${1:-}" != "--tauri" ]]; then
  echo "완료. dist/plc-backend 를 실행하면 http://127.0.0.1:8000/studio.html 가 열립니다."
  exit 0
fi

echo "▶ [2/2] Tauri 네이티브 창 빌드…"
command -v cargo >/dev/null || { echo "✗ Rust/cargo 가 필요합니다(https://rustup.rs)"; exit 1; }
command -v rustc >/dev/null || { echo "✗ rustc 가 필요합니다"; exit 1; }

TRIPLE="$(rustc -Vv | awk '/host:/{print $2}')"
EXT=""
case "${OSTYPE:-}" in msys*|cygwin*|win*) EXT=".exe";; esac
mkdir -p desktop/src-tauri/binaries
cp "dist/plc-backend${EXT}" "desktop/src-tauri/binaries/plc-backend-${TRIPLE}${EXT}"
echo "✓ 사이드카 배치: desktop/src-tauri/binaries/plc-backend-${TRIPLE}${EXT}"

( cd desktop/src-tauri \
    && cargo tauri icon icons/icon.png \
    && cargo tauri build )
echo "✓ 네이티브 앱 빌드 완료 (desktop/src-tauri/target/release/bundle/ 확인)"
