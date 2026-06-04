#!/usr/bin/env bash
# 개발/세션 부트스트랩: venv + dev 의존성. CI 와 동일한 도구가 돌도록 보장.
set -euo pipefail
cd "$(dirname "$0")/.."

if command -v uv >/dev/null 2>&1; then
  [ -d .venv ] || uv venv --python 3.11
  uv pip install -e ".[dev,web]" >/dev/null 2>&1 || uv pip install -e ".[dev,web]"
else
  [ -d .venv ] || python3 -m venv .venv
  .venv/bin/pip install -q -e ".[dev,web]"
fi
echo "✅ 환경 준비 완료 — 'source .venv/bin/activate' 후 pytest/ruff/mypy 사용 가능"
