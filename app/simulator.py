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
# 합성기가 FB 호출 앞에 남기는 타입 주석: "// 타이머 T1 (TOF, 2000ms)"
_TIMER_KIND_RE = re.compile(r"타이머\s+([A-Za-z_]\w*)\s*\(\s*(TON|TOF|TP)", re.IGNORECASE)


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
    _prev_in: bool = False
    _running: bool = False  # TP: 펄스 진행 중 여부

    def scan(self, table: dict[str, bool], dt: int) -> None:
        inp = _eval(self.enable_expr, table)
        if self.kind == "TOF":
            self._scan_tof(inp, dt)
        elif self.kind == "TP":
            self._scan_tp(inp, dt)
        else:  # TON
            self._scan_ton(inp, dt)
        self._prev_in = inp

    def _scan_ton(self, inp: bool, dt: int) -> None:
        # 상승 스캔에서는 시간을 적립하지 않고(acc=0) 직전 구간만 누적한다.
        # → IN 이 막 True 가 된 스캔이 곧바로 dt 를 더해 1스캔 조기 발화하던 버그 차단.
        if inp:
            self.acc = min(self.acc + dt, self.preset_ms) if self._prev_in else 0
            self.q = self.acc >= self.preset_ms
        else:
            self.acc = 0
            self.q = False

    def _scan_tof(self, inp: bool, dt: int) -> None:
        if inp:
            self.acc = 0
            self.q = True
        elif self.q:
            # 하강 직후 스캔은 적립하지 않고(타이밍 시작), 이후 구간부터 누적.
            if self._prev_in:
                self.acc = 0
            else:
                self.acc = min(self.acc + dt, self.preset_ms)
                if self.acc >= self.preset_ms:
                    self.q = False

    def _scan_tp(self, inp: bool, dt: int) -> None:
        if self._running:
            self.acc = min(self.acc + dt, self.preset_ms)
            if self.acc >= self.preset_ms:
                self.q = False
                self._running = False
        elif inp and not self._prev_in:  # 상승 엣지에서 펄스 시작
            self._running = True
            self.acc = 0
            self.q = self.preset_ms > 0


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
        self._kinds: dict[str, str] = {}  # 주석에서 추출한 타이머 타입(TON/TOF/TP)
        for line in st_code.splitlines():
            km = _TIMER_KIND_RE.search(line)
            if km:
                self._kinds[km.group(1)] = km.group(2).upper()
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
                kind=self._kinds.get(name, "TON"),
                preset_ms=_parse_time_ms(args.get("PT", "")),
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


# 스캔 샘플 수 상한(증폭형 DoS 방지). duration/step 비율이 커도 메모리·시간 폭증 차단.
MAX_SIM_SAMPLES = 20_000


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
    if step_ms <= 0:
        raise ValueError("step_ms 는 1 이상이어야 합니다.")
    n_samples = duration_ms // step_ms + 1
    if n_samples > MAX_SIM_SAMPLES:
        raise ValueError(
            f"스캔 샘플 {n_samples}개가 상한({MAX_SIM_SAMPLES})을 초과합니다 "
            f"(duration_ms/step_ms 비율을 줄이세요)."
        )
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
