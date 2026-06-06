"""브라우저 JS 스캔 엔진 ↔ 파이썬 시뮬레이터 패리티 게이트.

frontend/sim-engine.js 가 app/simulator.py 와 *비트 단위로 동일* 한 출력 트레이스를
내는지 검증한다. 둘이 갈라지면 라이브 미리보기가 검증된 서버 동작과 어긋난다는
신호이므로, "검증된 ST = 단일 진실원천" 을 회귀로 못박는다(CLAUDE 결정론 요구).

Node 가 없으면 스킵(키 불필요, CI 의 ubuntu 러너엔 Node 존재).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.simulator import simulate
from app.synth import synthesize_st
from app.wizard import build_spec

_NODE = shutil.which("node")
_RUNNER = Path(__file__).resolve().parent.parent / "scripts" / "sim_parity_runner.mjs"

pytestmark = pytest.mark.skipif(_NODE is None, reason="node 미설치 — JS 패리티 스킵")

# (recipe, answers, [(t_ms,{sym:val})] 자극, duration_ms) — seal-in/타이머/카운터/인터락 커버
_CASES = [
    ("motor_start_stop", {}, [(0, {"START": True}), (300, {"START": False})], 1500),
    ("fwd_rev", {}, [(100, {"FWD_PB": True}), (400, {"FWD_PB": False}),
                     (600, {"REV_PB": True}), (900, {"REV_PB": False})], 1500),
    ("on_delay", {"delay_sec": "1"}, [(0, {"START": True})], 2000),
    ("count_eject", {}, [(t, {"COUNT_PULSE": b}) for t, b in
                         [(100, True), (200, False), (300, True), (400, False),
                          (500, True), (600, False)]], 1200),
]


def _js_trace(st: str, timeline: list, duration: int, step: int = 100) -> dict:
    payload = json.dumps({"stCode": st, "timeline": timeline, "duration": duration, "step": step})
    out = subprocess.run(
        [_NODE, str(_RUNNER)], input=payload, capture_output=True, text=True, timeout=30,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.parametrize("recipe,answers,timeline,duration", _CASES)
def test_js_engine_matches_python_simulator(
    recipe: str, answers: dict, timeline: list, duration: int
) -> None:
    st = synthesize_st(build_spec(recipe, answers))
    py = simulate(
        st, [(t, d) for t, d in timeline], duration_ms=duration, step_ms=100
    )
    js = _js_trace(st, timeline, duration, 100)

    assert sorted(py.outputs) == sorted(js["outputs"])
    assert len(py.samples) == len(js["samples"])
    for out in py.outputs:
        py_trace = py.output_trace(out)
        js_trace = [s["outputs"].get(out, False) for s in js["samples"]]
        assert py_trace == js_trace, f"출력 '{out}' 트레이스 불일치\nPY={py_trace}\nJS={js_trace}"
