"""래더 렌더러 파워플로우 색 회귀 가드 (Node 로 frontend/ladder-render.js 구동).

무상태 호출(다른 화면 호환)과 상태 주입(스튜디오 라이브 하이라이트) 두 경로를
모두 고정한다: 도통 접점/경로=라이브 초록, 비도통=흐림/꺼짐, 점등 코일=초록.

Node 없으면 스킵(CI ubuntu 러너엔 존재).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_NODE = shutil.which("node")
_RUNNER = Path(__file__).resolve().parent.parent / "scripts" / "ladder_render_runner.mjs"

pytestmark = pytest.mark.skipif(_NODE is None, reason="node 미설치 — 렌더러 색 검사 스킵")

C_LIVE = "#5ff08a"   # 도통/점등 초록
C_OFF = "#454c57"    # 비도통 접점
W_STATIC = "#3a7"    # 무상태 기본 전선(다른 화면 호환)
W_DIM = "#33414f"    # 비도통 직렬 구간

_LADDER = {
    "rungs": [
        {
            "comment": "test",
            "input_branches": [
                {"elements": [{"element_type": "CONTACT_NO", "symbol": "A", "address": "P0000"}]}
            ],
            "outputs": [{"element_type": "COIL", "symbol": "Y", "address": "P0001"}],
        }
    ]
}


def _svg(state: dict | None) -> str:
    payload = json.dumps({"ladder": _LADDER, "state": state})
    out = subprocess.run(
        [_NODE, str(_RUNNER)], input=payload, capture_output=True, text=True, timeout=30
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_stateless_keeps_legacy_colors() -> None:
    svg = _svg(None)
    assert "A" in svg and "Y" in svg
    assert W_STATIC in svg          # 기존 초록 전선 유지
    assert C_LIVE not in svg        # 상태 없으면 라이브 하이라이트 없음


def test_energized_path_and_coil_are_live() -> None:
    svg = _svg({"A": True, "Y": True})
    assert C_LIVE in svg            # 도통 접점/직렬경로/점등 코일 = 초록


def test_dead_contact_and_segment_are_dim() -> None:
    svg = _svg({"A": False})
    assert C_OFF in svg             # NO 접점 비도통 = 꺼짐색
    assert W_DIM in svg             # 접점 하류 직렬 구간 = 흐림
