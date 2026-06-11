"""전 레시피 데모 데이터 제너레이터 — 유저 라인 빌더의 데이터 소스.

엔진의 모든 레시피를 합성·검증·트랜스파일·시뮬해 ``frontend/demo-data.js``
(``window.DEMO_ALL``)로 출력한다. 플랫폼의 '라인 추가'가 이 데이터로 임의
레시피를 라인 인스턴스로 만든다. 검증 실패 레시피가 있으면 생성이 실패한다
(전 레시피 그린 보증).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.emit import render_for_vendor
from app.explain import explain_all
from app.memory_map import DeviceAllocator
from app.models import DataType, DeviceClass, IODirection
from app.simulator import simulate
from app.synth import synthesize_st
from app.transpiler import transpile_st
from app.verifier import verify
from app.wizard import RECIPES, build_spec

ROOT = Path(__file__).resolve().parent.parent
OUT_JS = ROOT / "frontend" / "demo-data.js"


def _timeline(
    bool_ins: list[str], analog_ins: list[str]
) -> list[tuple[int, dict[str, bool | int]]]:
    """범용 자극: 불리언 입력 순차 펄스, 아날로그는 0 고정(표시용)."""
    tl: list[tuple[int, dict[str, bool | int]]] = []
    if analog_ins:
        tl.append((0, dict.fromkeys(analog_ins, 0)))
    t = 300
    for sym in bool_ins:
        tl.append((t, {sym: True}))
        tl.append((t + 600, {sym: False}))
        t += 1200
    return tl


def build_payload() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for rid in RECIPES:
        spec = build_spec(rid, {})
        st = synthesize_st(spec)
        ladder = transpile_st(st, title=spec.title)
        report = verify(spec, st)
        if not report.passed:
            raise RuntimeError(f"레시피 검증 실패: {rid}")
        analog_ins = [
            p.symbol for p in spec.io_points
            if p.data_type != DataType.BOOL
        ]
        alloc = DeviceAllocator()
        addr: dict[str, str] = {}
        for p in spec.io_points:
            is_p = p.device_class == DeviceClass.P
            addr[p.symbol] = alloc.allocate(
                p.symbol, p.device_class, direction=p.direction if is_p else None)
        for rung in ladder.rungs:
            for o in rung.outputs:
                et = o.element_type.value if hasattr(o.element_type, "value") else o.element_type
                if et == "TIMER":
                    addr[o.symbol] = alloc.allocate(o.symbol, DeviceClass.T)
                if et == "COUNTER":
                    addr[o.symbol] = alloc.allocate(o.symbol, DeviceClass.C)
        bool_ins = [
            p.symbol for p in spec.io_points
            if p.data_type == DataType.BOOL and p.direction == IODirection.INPUT
        ][:4]
        res = simulate(st, _timeline(bool_ins, analog_ins), duration_ms=8000, step_ms=400)
        sample0 = res.samples[0]
        tkey = next(f for f in vars(sample0) if f not in ("inputs", "outputs"))
        out[rid] = {
            "title": spec.title,
            "category": RECIPES[rid].category,
            "st": st,
            "ladder": ladder.model_dump(),
            "explain": explain_all(spec, ladder, report),
            "passed": True,
            "addr": addr,
            "il_xgk": render_for_vendor(st, spec),
            "analog_inputs": analog_ins,
            "desc": {p.symbol: p.description for p in spec.io_points},
            "sim": {
                "inputs": res.inputs,
                "outputs": res.outputs,
                "samples": [
                    {"t": getattr(x, tkey), "i": x.inputs, "o": x.outputs}
                    for x in res.samples
                ],
            },
        }
    return out


def render_js(payload: dict[str, dict[str, Any]]) -> str:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return (
        "/* 자동 생성 — scripts/gen_demo_data.py (전 레시피 합성·검증 산출물).\n"
        "   직접 수정 금지. */\n"
        f"window.DEMO_ALL={body};\n"
    )


def main() -> None:
    js = render_js(build_payload())
    OUT_JS.write_text(js, encoding="utf-8")
    print(f"built {OUT_JS} ({len(js):,} bytes, recipes={len(RECIPES)})")


if __name__ == "__main__":
    main()
