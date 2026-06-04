#!/usr/bin/env bash
# 맥/리눅스에서 라이브 래더 에디터를 띄운다.
#   ./run.sh           → http://localhost:8000 에서 웹앱 실행
# 의존성: python3.11+. uv 가 있으면 더 빠르게 설치한다.
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"

if command -v uv >/dev/null 2>&1; then
  [ -d .venv ] || uv venv --python 3.11
  uv pip install -e ".[web]" >/dev/null
  source .venv/bin/activate
else
  [ -d .venv ] || python3 -m venv .venv
  source .venv/bin/activate
  pip install -q -e ".[web]"
fi

echo "▶ PLC 래더 라이브 에디터 → http://localhost:${PORT}"
# 맥이면 브라우저 자동 오픈
if command -v open >/dev/null 2>&1; then (sleep 1.5; open "http://localhost:${PORT}") & fi
exec uvicorn app.server:app --host 0.0.0.0 --port "${PORT}"
