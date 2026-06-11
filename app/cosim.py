"""실시간 코시뮬레이션 세션 — 가상 PLC를 고정 스캔 주기로 스텝 구동.

브라우저 데모(rAF ≈ 16.7ms 근사)와 달리, 서버 코어 시뮬레이터(`app.simulator`
— OpenPLC 런타임과 bit-for-bit 차분검증 완료)를 1ms 단위 고정 주기로 구동한다.
WebSocket(`/api/cosim`)을 통해 입력을 즉시 반영하고 스캔 단위로 상태를 돌려준다.

프로토콜(JSON 메시지):
  클라 → 서버
    {"type": "init", "st_code": "...", "step_ms": 10}
    {"type": "set",  "inputs": {"START": true}}
    {"type": "step", "scans": 10}
    {"type": "state"}
    {"type": "trace"}                      # 누적 스캔 트레이스(기록/리플레이용)
  서버 → 클라
    {"type": "ready", "inputs": [...], "outputs": [...], "step_ms": 10}
    {"type": "state", "t_ms": 120, "inputs": {...}, "outputs": {...},
     "timers": {"T0": {"acc_ms": 40, "preset_ms": 1000, "q": false}},
     "counters": {"C1": {"cnt": 3, "preset": 10, "q": false}}}
    {"type": "error", "error": "..."}

LLM 호출 없음(결정론) — CI에서 키 없이 동작한다.
"""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.simulator import _eval, _Program

MIN_STEP_MS = 1
MAX_STEP_MS = 1000
MAX_SCANS_PER_STEP = 1000
MAX_TRACE_SCANS = 60_000  # 10ms 스텝 기준 10분 — 초과 시 앞부분을 버린다


class CosimError(ValueError):
    """프로토콜/입력 오류 — 메시지는 클라이언트에 그대로 전달된다."""


class CosimSession:
    """ST 1편을 스캔 단위로 구동하는 상태 보존 세션."""

    def __init__(self, st_code: str, step_ms: int = 10) -> None:
        if not st_code.strip():
            raise CosimError("st_code 가 비어 있습니다.")
        if len(st_code) > settings.max_st_chars:
            raise CosimError(f"st_code 가 상한({settings.max_st_chars}자)을 초과합니다.")
        if not (MIN_STEP_MS <= step_ms <= MAX_STEP_MS):
            raise CosimError(f"step_ms 는 {MIN_STEP_MS}~{MAX_STEP_MS} 범위여야 합니다.")
        self._prog = _Program(st_code)
        if not self._prog.driven:
            raise CosimError("구동(대입) 변수가 없는 ST 입니다.")
        self.step_ms = step_ms
        self.t_ms = 0
        fb_q = {f"{n}.Q" for n in self._prog.timers} | {f"{n}.Q" for n in self._prog.counters}
        self.inputs: list[str] = sorted(
            s
            for s in self._prog.symbols()
            if s not in self._prog.driven and s not in fb_q and "." not in s
        )
        self.outputs: list[str] = list(self._prog.driven)
        self._table: dict[str, bool] = {s: False for s in self._prog.driven}
        self._cur_inputs: dict[str, bool] = {s: False for s in self.inputs}
        self.trace: list[dict[str, Any]] = []
        self.trace_truncated = False

    def set_inputs(self, values: dict[str, Any]) -> None:
        """입력 심볼 값을 갱신한다. 미지 심볼/비불리언은 거부."""
        for sym, val in values.items():
            if sym not in self._cur_inputs:
                raise CosimError(f"알 수 없는 입력 심볼: {sym}")
            if not isinstance(val, bool):
                raise CosimError(f"입력 값은 bool 이어야 합니다: {sym}={val!r}")
        for sym, val in values.items():
            self._cur_inputs[sym] = bool(val)

    def step(self, scans: int = 1) -> None:
        """PLC 스캔 의미론(입력 → FB → 로직)으로 scans회 전진한다."""
        if not (1 <= scans <= MAX_SCANS_PER_STEP):
            raise CosimError(f"scans 는 1~{MAX_SCANS_PER_STEP} 범위여야 합니다.")
        for _ in range(scans):
            for s in self.inputs:
                self._table[s] = self._cur_inputs[s]
            for name, tmr in self._prog.timers.items():
                tmr.scan(self._table, self.step_ms)
                self._table[f"{name}.Q"] = tmr.q
            for name, cnt in self._prog.counters.items():
                cnt.scan(self._table)
                self._table[f"{name}.Q"] = cnt.q
            for lhs, node in self._prog.assigns:
                self._table[lhs] = _eval(node, self._table)
            self.t_ms += self.step_ms
            self.trace.append({
                "t_ms": self.t_ms,
                "i": {sym: self._table.get(sym, False) for sym in self.inputs},
                "o": {sym: self._table.get(sym, False) for sym in self.outputs},
            })
            if len(self.trace) > MAX_TRACE_SCANS:
                del self.trace[: len(self.trace) - MAX_TRACE_SCANS]
                self.trace_truncated = True

    def state(self) -> dict[str, Any]:
        """현재 스냅샷(JSON 직렬화 가능)."""
        return {
            "type": "state",
            "t_ms": self.t_ms,
            "inputs": {s: self._table.get(s, self._cur_inputs[s]) for s in self.inputs},
            "outputs": {s: self._table.get(s, False) for s in self.outputs},
            "timers": {
                n: {"acc_ms": t.acc, "preset_ms": t.preset_ms, "q": t.q}
                for n, t in self._prog.timers.items()
            },
            "counters": {
                n: {"cnt": c.cnt, "preset": c.preset, "q": c.q}
                for n, c in self._prog.counters.items()
            },
        }


def handle_message(
    session: CosimSession | None, msg: dict[str, Any]
) -> tuple[CosimSession | None, dict[str, Any]]:
    """메시지 1건 처리 → (세션, 응답). 순수 함수라 WebSocket 없이 테스트 가능."""
    mtype = msg.get("type")
    try:
        if mtype == "init":
            session = CosimSession(
                st_code=str(msg.get("st_code", "")),
                step_ms=int(msg.get("step_ms", 10)),
            )
            return session, {
                "type": "ready",
                "inputs": session.inputs,
                "outputs": session.outputs,
                "step_ms": session.step_ms,
            }
        if session is None:
            raise CosimError("먼저 init 으로 세션을 만들어야 합니다.")
        if mtype == "set":
            inputs = msg.get("inputs")
            if not isinstance(inputs, dict):
                raise CosimError("set 메시지에는 inputs(dict) 가 필요합니다.")
            session.set_inputs(inputs)
            return session, session.state()
        if mtype == "step":
            session.step(int(msg.get("scans", 1)))
            return session, session.state()
        if mtype == "state":
            return session, session.state()
        if mtype == "trace":
            return session, {
                "type": "trace",
                "samples": session.trace,
                "truncated": session.trace_truncated,
            }
        raise CosimError(f"알 수 없는 메시지 type: {mtype!r}")
    except CosimError as exc:
        return session, {"type": "error", "error": str(exc)}
    except (TypeError, ValueError) as exc:
        return session, {"type": "error", "error": f"잘못된 메시지: {exc}"}
