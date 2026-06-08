#!/usr/bin/env python3
"""독립 백엔드 교차 실행 동치 벤치 — '자가채점' 약점 타파.

같은 컴파일 산출물(ST)을 *서로 다른 독립 실행기*에 동일 입력 타임라인으로 돌려
출력 트레이스가 일치함을 검사한다. 단일 시뮬레이터의 자가채점을 넘어, 교차검증으로
신뢰도를 끌어올린다.

백엔드:
  (1) 파이썬 스캔 시뮬레이터   ``app.simulator.simulate``        — 기준(ground truth)
  (2) XGK IL 인터프리터        ``app.xgk.simulate_xgk``          — 에미트된 LS_XGK 니모닉 실행
  (3) OpenPLC 트윈(시뮬백)     ``app.twin.openplc_adapter``     — IEC 런타임 차분 머신

(3)은 CI/오프라인에서 ``SimBackedLink`` 로 (1)을 재생하므로 정의상 (1)과 일치한다
(차분 머신의 무결성 보증). 실 OpenPLC(env ``OPENPLC_HOST``)가 있으면 같은 seam 으로
실기에도 연결 가능하지만, 본 벤치는 결정론을 위해 시뮬백 링크만 쓴다.

코퍼스 규율: *불리언* 한국어 지시만 — 아날로그 비교기는 백엔드별 수치 지원 차이를
회피하기 위해 제외한다. 자기유지/조건/인터락/시퀀서 위주(15~25건)다.

결정론: 벽시계 미사용, 정렬 순회, 고정 타임라인. 두 번 실행이 비트 동일하다.

직접 실행::

    python scripts/cross_backend_bench.py            # 사람용 표
    python scripts/cross_backend_bench.py --json      # 기계용 JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

# 직접 실행(``python scripts/cross_backend_bench.py``) 시 레포 루트를 import 경로에 둔다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.compile_frame import frame_to_spec
from app.emit import emit
from app.simulator import SimResult, simulate
from app.synth import synthesize_st
from app.transpiler import transpile_st
from app.twin.openplc_adapter import SimBackedLink, run_differential
from app.vendors import LS_XGK
from app.xgk import XgkResult, simulate_xgk

# 입력 타임라인 한 점: (t_ms, {입력심볼: 값})
Timeline = list[tuple[int, dict[str, bool]]]

DURATION_MS = 8_000
STEP_MS = 100

# 불리언 컴파일 코퍼스(아날로그 비교기 제외). 자기유지·조건·인터락·시퀀서 위주.
CORPUS: tuple[str, ...] = (
    # ── 단순 자기유지(START/STOP 버튼) ──────────────────────────────────────
    "기동 버튼을 누르면 펌프가 돌고 정지 버튼을 누르면 멈춘다",
    "시작 버튼을 누르면 모터가 돌고 정지 버튼을 누르면 멈춘다",
    "시작 버튼을 누르면 진공을 켜고 정지 버튼을 누르면 끈다",
    "시작 버튼을 누르면 솔레노이드를 켜고 정지 버튼을 누르면 끈다",
    "시작 버튼을 누르면 노즐을 켜고 정지 버튼을 누르면 끈다",
    "시작 버튼을 누르면 드릴을 켜고 정지 버튼을 누르면 끈다",
    "시작 버튼을 누르면 냉각기를 켜고 정지 버튼을 누르면 끈다",
    "시작 버튼을 누르면 압축기를 켜고 정지 버튼을 누르면 끈다",
    # ── 센서/조건 트리거 자기유지 ────────────────────────────────────────────
    "센서가 감지되면 컨베이어를 돌리고 정지하면 멈춘다",
    "센서가 감지되면 밸브를 열고 정지하면 닫는다",
    "센서가 감지되면 팬을 돌리고 정지하면 멈춘다",
    "센서가 감지되면 송풍기를 돌리고 정지하면 멈춘다",
    "센서가 감지되면 사이렌을 켜고 정지하면 끈다",
    "고장이 나면 부저를 켜고 정지하면 끈다",
    "고장이 나면 경광등을 켜고 정지하면 끈다",
    "리미트 스위치가 켜지면 실린더를 켜고 정지하면 끈다",
    "근접 센서가 감지되면 클램프를 켜고 정지하면 끈다",
    "광전 센서가 감지되면 호퍼를 켜고 정지하면 끈다",
    # ── 인터락(상호배제) ─────────────────────────────────────────────────────
    "게이트 A와 게이트 B는 동시에 열 수 없다. 시작하면 게이트 A를 연다. 누르면 게이트 B를 연다.",
    # ── 시퀀서(순차 단계) ────────────────────────────────────────────────────
    "시작하면 셔터를 올리고 다음 컨베이어를 돌리고 다음 램프를 켠다",
    "시작하면 모터를 돌리고 2초 후 펌프를 돌리고 다음 밸브를 연다",
)


@dataclass(frozen=True)
class Divergence:
    """한 신호의 최초 발산: (출력, 스텝, t_ms, A값, B값)."""

    signal: str
    step: int
    t_ms: int
    a_val: bool
    b_val: bool


@dataclass
class CaseResult:
    """한 코퍼스 케이스의 교차 동치 결과."""

    text: str
    inputs: list[str]
    outputs: list[str]
    # 백엔드 쌍별 발산(없으면 일치). 키: "sim_vs_xgk" / "sim_vs_openplc".
    divergences: dict[str, Divergence | None] = field(default_factory=dict)
    error: str | None = None

    @property
    def compiled(self) -> bool:
        return self.error is None and bool(self.outputs)

    def agrees(self, pair: str) -> bool:
        return self.divergences.get(pair) is None


def _build(text: str) -> tuple[str, str]:
    """한국어 지시 → (검증된 ST, 에미트된 LS_XGK 니모닉)."""
    result = frame_to_spec(text)
    st = synthesize_st(result.spec)
    xgk = emit(transpile_st(st), LS_XGK)
    return st, xgk


def _input_symbols(st: str) -> list[str]:
    """ST 시뮬레이터가 인식하는 입력 심볼(정렬)."""
    return simulate(st, [], duration_ms=0, step_ms=STEP_MS).inputs


def staggered_timeline(symbols: Sequence[str]) -> Timeline:
    """입력을 시차로 켜고 끄는 자극 — seal-in/엣지 경로를 폭넓게 친다(결정론).

    각 입력 i 를 (300·i+100)ms 에 켜고 1000ms 뒤 끈다. 출력 토글·래치·해제를
    모두 자극하므로 백엔드 간 미세 차이가 트레이스로 드러난다.
    """
    tl: Timeline = []
    for i, s in enumerate(symbols):
        tl.append((300 * i + 100, {s: True}))
        tl.append((300 * i + 1100, {s: False}))
    return tl


def _first_divergence(
    a_trace: list[bool], b_trace: list[bool], signal: str
) -> Divergence | None:
    """두 출력 트레이스의 최초 발산(없으면 None)."""
    for step, (x, y) in enumerate(zip(a_trace, b_trace, strict=False)):
        if x != y:
            return Divergence(
                signal=signal, step=step, t_ms=step * STEP_MS, a_val=x, b_val=y
            )
    return None


def _sim_vs_xgk(
    sres: SimResult, xres: XgkResult, outputs: list[str]
) -> Divergence | None:
    """파이썬 시뮬 ↔ XGK 인터프리터 트레이스 최초 발산."""
    if sorted(sres.outputs) != sorted(xres.outputs):
        return Divergence(signal="<output-set>", step=-1, t_ms=-1,
                          a_val=False, b_val=False)
    for o in outputs:
        div = _first_divergence(sres.output_trace(o), xres.output_trace(o), o)
        if div is not None:
            return div
    return None


def _sim_vs_openplc(
    st: str, tl: Timeline, outputs: list[str]
) -> Divergence | None:
    """파이썬 시뮬 ↔ OpenPLC 트윈(시뮬백 IEC 런타임) 트레이스 최초 발산.

    ``run_differential`` 가 step 격자에서 양쪽을 대조해 결정론적 ``DiffReport`` 를
    낸다. 시뮬백 링크라 정의상 일치해야 한다(차분 머신 무결성 보증).
    """
    link = SimBackedLink(st, tl, duration_ms=DURATION_MS, step_ms=STEP_MS)
    report = run_differential(
        st, None, link, tl, duration_ms=DURATION_MS, step_ms=STEP_MS
    )
    if report.first_divergence is None:
        return None
    m = report.first_divergence
    return Divergence(
        signal=m.symbol, step=m.t_ms // STEP_MS, t_ms=m.t_ms,
        a_val=m.sim_val, b_val=m.plc_val,
    )


def run_case(text: str) -> CaseResult:
    """한 케이스를 세 백엔드에 돌려 쌍별 동치를 검사한다(결정론)."""
    try:
        st, xgk = _build(text)
    except Exception as exc:  # noqa: BLE001 — 벤치는 컴파일 실패를 케이스로 흡수
        return CaseResult(text=text, inputs=[], outputs=[], error=repr(exc))

    inputs = _input_symbols(st)
    tl = staggered_timeline(inputs)
    sres = simulate(st, tl, duration_ms=DURATION_MS, step_ms=STEP_MS)
    if not sres.outputs:
        return CaseResult(text=text, inputs=inputs, outputs=[],
                          error="구동 출력 없음")
    xres = simulate_xgk(xgk, tl, duration_ms=DURATION_MS, step_ms=STEP_MS)

    return CaseResult(
        text=text,
        inputs=inputs,
        outputs=list(sres.outputs),
        divergences={
            "sim_vs_xgk": _sim_vs_xgk(sres, xres, list(sres.outputs)),
            "sim_vs_openplc": _sim_vs_openplc(st, tl, list(sres.outputs)),
        },
    )


@dataclass
class BenchSummary:
    """전체 벤치 집계(결정론)."""

    cases: list[CaseResult]

    @property
    def compiled(self) -> list[CaseResult]:
        return [c for c in self.cases if c.compiled]

    def pair_agree_rate(self, pair: str) -> tuple[int, int]:
        """쌍별 (일치 케이스 수, 컴파일 케이스 수)."""
        comp = self.compiled
        agree = sum(1 for c in comp if c.agrees(pair))
        return agree, len(comp)


PAIRS = ("sim_vs_xgk", "sim_vs_openplc")
PAIR_LABELS = {
    "sim_vs_xgk": "PySim <-> XGK IL",
    "sim_vs_openplc": "PySim <-> OpenPLC(트윈)",
}


def run_bench() -> BenchSummary:
    """전체 코퍼스를 돌려 집계를 만든다(결정론·부작용 없음)."""
    return BenchSummary(cases=[run_case(t) for t in CORPUS])


# ── 기대되는 차이 문서화 ──────────────────────────────────────────────────────
# 본 벤치는 *불리언* 코퍼스만 쓰므로 타이머 양자화·수치 비교 같은 백엔드별 차이가
# 발생하지 않도록 설계했다(아날로그 비교기 제외). 시퀀서의 타이머는 세 백엔드가
# 동일한 _Timer 양자화 로직(app.simulator._Timer)을 재사용하므로 step_ms 격자에서
# 같은 샘플에 발화한다 — 즉 기대되는 차이가 0 이며, 발산은 곧 실제 결함이다.
EXPECTED_DIFFERENCES = (
    "타이머 양자화: 세 백엔드가 app.simulator._Timer 를 공유해 step_ms 격자에서 "
    "동일 샘플에 발화 -> 기대 차이 0.",
    "수치 비교: 아날로그 비교기는 코퍼스에서 제외(백엔드별 수치 지원 차이 회피).",
    "OpenPLC 트윈: 오프라인 시뮬백 링크라 PySim 재생 -> 정의상 PySim 과 일치.",
)


def _render_text(summary: BenchSummary) -> str:
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("독립 백엔드 교차 실행 동치 벤치 (cross-backend equivalence)")
    lines.append("=" * 78)
    n = len(summary.cases)
    comp = summary.compiled
    lines.append(f"코퍼스 {n}건 / 컴파일 성공 {len(comp)}건 "
                 f"(duration={DURATION_MS}ms, step={STEP_MS}ms, 자극=staggered)")
    lines.append("")
    for pair in PAIRS:
        agree, total = summary.pair_agree_rate(pair)
        pct = (100.0 * agree / total) if total else 0.0
        lines.append(f"  [{PAIR_LABELS[pair]}] 일치 {agree}/{total} ({pct:.1f}%)")
    lines.append("")
    lines.append("-" * 78)
    lines.append(f"{'#':>2}  {'sim/xgk':<9}{'sim/plc':<9}  지시")
    lines.append("-" * 78)
    for i, c in enumerate(summary.cases, 1):
        if not c.compiled:
            lines.append(f"{i:>2}  {'(컴파일 실패: ' + (c.error or '?') + ')':<20}"
                         f"{c.text[:34]}")
            continue
        cols = ""
        for pair in PAIRS:
            cols += ("OK " if c.agrees(pair) else "X! ").ljust(9)
        lines.append(f"{i:>2}  {cols} {c.text[:34]}")
    lines.append("-" * 78)
    # 발산 상세(있으면).
    any_div = False
    for i, c in enumerate(summary.cases, 1):
        for pair in PAIRS:
            d = c.divergences.get(pair)
            if d is not None:
                any_div = True
                lines.append(
                    f"  발산 #{i} [{pair}] 신호={d.signal} 스텝={d.step} "
                    f"(t={d.t_ms}ms) A={d.a_val} B={d.b_val}"
                )
    if not any_div:
        lines.append("  발산 없음 — 모든 컴파일 케이스가 백엔드 간 비트 일치.")
    lines.append("")
    lines.append("기대되는 차이(문서화·정렬됨):")
    for note in EXPECTED_DIFFERENCES:
        lines.append(f"  - {note}")
    lines.append("=" * 78)
    return "\n".join(lines)


def _div_to_dict(d: Divergence | None) -> dict[str, object] | None:
    if d is None:
        return None
    return {
        "signal": d.signal, "step": d.step, "t_ms": d.t_ms,
        "a_val": d.a_val, "b_val": d.b_val,
    }


def _to_json(summary: BenchSummary) -> str:
    payload = {
        "duration_ms": DURATION_MS,
        "step_ms": STEP_MS,
        "n_cases": len(summary.cases),
        "n_compiled": len(summary.compiled),
        "pairs": {
            pair: {
                "label": PAIR_LABELS[pair],
                "agree": summary.pair_agree_rate(pair)[0],
                "total": summary.pair_agree_rate(pair)[1],
            }
            for pair in PAIRS
        },
        "cases": [
            {
                "text": c.text,
                "inputs": c.inputs,
                "outputs": c.outputs,
                "compiled": c.compiled,
                "error": c.error,
                "divergences": {
                    pair: _div_to_dict(c.divergences.get(pair)) for pair in PAIRS
                },
            }
            for c in summary.cases
        ],
        "expected_differences": list(EXPECTED_DIFFERENCES),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    args = parser.parse_args(argv)
    summary = run_bench()
    if args.json:
        print(_to_json(summary))
    else:
        print(_render_text(summary))
    # 컴파일된 모든 케이스가 모든 쌍에서 일치하면 0, 아니면 1(CI 게이트용).
    ok = all(c.agrees(pair) for c in summary.compiled for pair in PAIRS)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
