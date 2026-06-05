"""결정론 스캔 시뮬레이터 — 가상환경에서 합성 로직을 실제 PLC처럼 1:1 가동·테스트.

디지털 트윈 코어(사업 2단계 '무결점 검증'). LLM 없이 결정론적으로, 합성된 ST를
PLC 스캔 의미론(입력 읽기 → 로직 연산 → 출력 쓰기)으로 시간축에서 실행한다.
타이머(TON/TOF/TP)·카운터(CTU/CTD)의 상태를 유지하며, 입력 타임라인을 주면
출력 트레이스를 돌려준다. 이중코일 0(출력당 1대입)이라 스캔이 결정론적이다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.boolexpr import And, Const, Node, Not, Or, Var, parse

_ASSIGN_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*:=\s*([^;]+?)\s*;\s*$")
_FB_CALL_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*\((.*)\)\s*;\s*$")
_FB_ARG_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*:=\s*(.+?)\s*$")
_TIME_RE = re.compile(r"T#\s*(?:(\d+)s)?(?:(\d+)ms)?", re.IGNORECASE)


def _parse_time_ms(text: str) -> int:
    """'T#5s' -> 5000, 'T#500ms' -> 500. 인식 불가 시 0."""
    m = _TIME_RE.search(text)
    if not m:
        return 0
    s = int(m.group(1)) if m.group(1) else 0
    ms = int(m.group(2)) if m.group(2) else 0
    return s * 1000 + ms


def _eval(node: Node, table: dict[str, bool]) -> bool:
    match node:
        case Var(name):
            return table.get(name, False)
        case Const(value):
            return value
        case Not(operand):
            return not _eval(operand, table)
        case And(operands):
            return all(_eval(o, table) for o in operands)
        case Or(operands):
            return any(_eval(o, table) for o in operands)
    raise TypeError(f"알 수 없는 노드: {node!r}")


@dataclass
class _Timer:
    kind: str
    preset_ms: int
    enable_expr: Node
    acc: int = 0
    q: bool = False

    def scan(self, table: dict[str, bool], dt: int) -> None:
        inp = _eval(self.enable_expr, table)
        if self.kind == "TOF":
            if inp:
                self.acc = 0
                self.q = True
            elif self.q:
                self.acc += dt
                if self.acc >= self.preset_ms:
                    self.q = False
        else:  # TON / TP(근사: TON)
            if inp:
                self.acc = min(self.acc + dt, self.preset_ms)
                self.q = self.acc >= self.preset_ms
            else:
                self.acc = 0
                self.q = False


@dataclass
class _Counter:
    kind: str
    preset: int
    count_expr: Node
    reset_expr: Node
    cnt: int = 0
    q: bool = False
    _prev: bool = False

    def scan(self, table: dict[str, bool]) -> None:
        if _eval(self.reset_expr, table):
            self.cnt = 0
        else:
            cu = _eval(self.count_expr, table)
            if cu and not self._prev:  # 상승 엣지
                self.cnt += -1 if self.kind == "CTD" else 1
            self._prev = cu
        self.q = self.cnt >= self.preset if self.kind != "CTD" else self.cnt <= 0


@dataclass
class SimSample:
    t_ms: int
    inputs: dict[str, bool]
    outputs: dict[str, bool]


@dataclass
class SimResult:
    samples: list[SimSample]
    outputs: list[str]
    inputs: list[str]
    timers: list[str] = field(default_factory=list)

    def output_trace(self, sym: str) -> list[bool]:
        return [s.outputs.get(sym, False) for s in self.samples]


class _Program:
    """ST 를 파싱해 시뮬레이션 가능한 형태로 보관."""

    def __init__(self, st_code: str) -> None:
        self.assigns: list[tuple[str, Node]] = []
        self.timers: dict[str, _Timer] = {}
        self.counters: dict[str, _Counter] = {}
        self.driven: list[str] = []
        for line in st_code.splitlines():
            code = line.split("//", 1)[0].strip()
            if not code:
                continue
            fb = _FB_CALL_RE.match(code)
            if fb and ":=" in fb.group(2):
                self._add_fb(fb.group(1), fb.group(2))
                continue
            m = _ASSIGN_RE.match(code)
            if m:
                lhs = m.group(1)
                self.assigns.append((lhs, parse(m.group(2))))
                if lhs not in self.driven:
                    self.driven.append(lhs)

    def _add_fb(self, name: str, args_text: str) -> None:
        args: dict[str, str] = {}
        for piece in args_text.split(","):
            am = _FB_ARG_RE.match(piece)
            if am:
                args[am.group(1).upper()] = am.group(2)
        if "CU" in args or "CD" in args:
            kind = "CTD" if "CD" in args else "CTU"
            self.counters[name] = _Counter(
                kind=kind,
                preset=int(re.sub(r"\D", "", args.get("PV", "0")) or 0),
                count_expr=parse(args.get("CU") or args.get("CD") or "FALSE"),
                reset_expr=parse(args.get("RESET", "FALSE")),
            )
        elif "IN" in args:
            self.timers[name] = _Timer(
                kind="TON", preset_ms=_parse_time_ms(args.get("PT", "")),
                enable_expr=parse(args["IN"]),
            )

    def symbols(self) -> set[str]:
        syms: set[str] = set()
        for _, node in self.assigns:
            syms |= _node_vars(node)
        for t in self.timers.values():
            syms |= _node_vars(t.enable_expr)
        for c in self.counters.values():
            syms |= _node_vars(c.count_expr) | _node_vars(c.reset_expr)
        return syms


def _node_vars(node: Node) -> set[str]:
    match node:
        case Var(name):
            return {name}
        case Not(operand):
            return _node_vars(operand)
        case And(operands) | Or(operands):
            out: set[str] = set()
            for o in operands:
                out |= _node_vars(o)
            return out
        case _:
            return set()


def simulate(
    st_code: str,
    inputs_timeline: list[tuple[int, dict[str, bool]]],
    *,
    duration_ms: int,
    step_ms: int = 100,
) -> SimResult:
    """ST 를 가상 PLC로 가동한다.

    inputs_timeline: [(t_ms, {입력심볼: 값}), ...] — 해당 시각부터 그 입력값을 유지.
    duration_ms/step_ms: 0..duration 까지 step 간격으로 스캔, 매 스캔 샘플 기록.
    """
    prog = _Program(st_code)
    table: dict[str, bool] = {}
    driven = prog.driven
    fb_q = {f"{n}.Q" for n in prog.timers} | {f"{n}.Q" for n in prog.counters}
    all_syms = prog.symbols()
    inputs = sorted(s for s in all_syms if s not in driven and s not in fb_q and "." not in s)
    for s in driven:
        table[s] = False

    timeline = sorted(inputs_timeline, key=lambda x: x[0])
    cur_inputs: dict[str, bool] = {s: False for s in inputs}
    samples: list[SimSample] = []
    ti = 0
    t = 0
    while t <= duration_ms:
        # 1) 입력 읽기 (해당 시각까지의 입력 변화 반영)
        while ti < len(timeline) and timeline[ti][0] <= t:
            cur_inputs.update(timeline[ti][1])
            ti += 1
        for s in inputs:
            table[s] = cur_inputs.get(s, False)
        # 2) FB(타이머/카운터) 갱신 → .Q 반영
        for name, tmr in prog.timers.items():
            tmr.scan(table, step_ms)
            table[f"{name}.Q"] = tmr.q
        for name, cnt in prog.counters.items():
            cnt.scan(table)
            table[f"{name}.Q"] = cnt.q
        # 3) 로직 연산 → 출력 쓰기 (top-to-bottom, seal-in 은 직전 값 참조)
        for lhs, node in prog.assigns:
            table[lhs] = _eval(node, table)
        samples.append(SimSample(
            t_ms=t,
            inputs={s: table.get(s, False) for s in inputs},
            outputs={s: table.get(s, False) for s in driven},
        ))
        t += step_ms

    return SimResult(samples=samples, outputs=driven, inputs=inputs,
                     timers=sorted(prog.timers) + sorted(prog.counters))
