"""LS XGK 니모닉 스캔 인터프리터 — 에미터 IL 텍스트를 가상 PLC로 가동.

에미터(``app.emit.ladder_il._emit_orb``)가 LS_XGK 프로파일로 뽑아낸 니모닉 텍스트를
파싱해 IL 스택머신으로 실행한다. 그 결과 출력 트레이스를 검증된 ST 시뮬레이터
(``app.simulator.simulate``)와 샘플 단위로 차분 대조함으로써, **에미트된 XGK 가
검증된 ST 와 동치**임을 증명한다.

구현 범위(scope discipline): LS_XGK 프로파일이 실제로 에미트하는 명령어 부분집합만
지원한다 — 즉 ``LOAD`` / ``LOAD NOT`` / ``AND`` / ``AND NOT`` / ``ORB`` (접점부) 와
``OUT`` / ``SET`` / ``RST`` / ``TON`` / ``CTU`` (출력부). IL 의 일반 ``OR`` / ``ORI`` /
``ANB`` 도 스택머신상 자명하게 처리하지만(에미터가 미래에 낼 수 있으므로), XGT 전체
명령어 집합을 구현하지는 않는다.

타이밍 의미론은 ``app.simulator`` 의 ``_Timer`` / ``_Counter`` / ``_eval`` /
``_parse_time_ms`` 를 **재사용**한다(재구현 금지). 그래야 타이머/카운터 동작이 ST
시뮬레이터와 바이트 동일해지고 차분 대조가 의미를 갖는다.

결정론: 벽시계 미사용, 정렬된 순회, 순수 함수.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.boolexpr import Const, Var
from app.simulator import (
    MAX_SIM_SAMPLES,
    _Counter,
    _parse_time_ms,
    _Timer,
)

# 프로파일이 에미트하는 헤더/주석/빈줄 — 파싱 시 무시.
_HEADER_RE = re.compile(r"^;\s*=+\s*\S+\s*=+\s*$")


@dataclass(frozen=True)
class _Contact:
    """접점 니모닉 한 줄: op(LOAD/AND/OR + 부정여부) + 피연산자."""

    op: str  # "LD" | "AND" | "OR" | "ORB" | "ANB"
    operand: str  # ORB/ANB 는 ""
    negate: bool = False


@dataclass(frozen=True)
class _Output:
    """출력 니모닉 한 줄."""

    kind: str  # "OUT" | "SET" | "RST" | "TON" | "CTU"
    operand: str
    preset: str = ""  # 타이머/카운터 프리셋 토큰("T#5s" / "10")


@dataclass(frozen=True)
class _Rung:
    """렁 하나 = 접점 스트림 + 출력들."""

    contacts: tuple[_Contact, ...]
    outputs: tuple[_Output, ...]


# 출력 니모닉 → (kind, 프리셋 토큰 수)
_OUTPUT_OPS = {
    "OUT": 0,
    "SET": 0,
    "RST": 0,
    "TON": 1,
    "TOF": 1,
    "TP": 1,
    "CTU": 1,
    "CTD": 1,
}


def _parse_contact(tokens: list[str]) -> _Contact:
    """접점 줄 토큰을 ``_Contact`` 로. 'LOAD'/'AND' + 선택적 'NOT' + 피연산자."""
    head = tokens[0].upper()
    if head == "ORB":
        return _Contact(op="ORB", operand="")
    if head == "ANB":
        return _Contact(op="ANB", operand="")
    if head in ("LOAD", "LD", "LDN", "LDI"):
        op = "LD"
        rest = tokens[1:]
        negate = head in ("LDN", "LDI")
    elif head in ("AND", "ANI", "ANDN"):
        op = "AND"
        rest = tokens[1:]
        negate = head in ("ANI", "ANDN")
    elif head in ("OR", "ORI", "ORN"):
        op = "OR"
        rest = tokens[1:]
        negate = head in ("ORI", "ORN")
    else:
        raise ValueError(f"알 수 없는 접점 니모닉: {tokens!r}")
    # 'LOAD NOT X' / 'AND NOT X' 처럼 NOT 이 별도 토큰일 수 있다.
    if rest and rest[0].upper() == "NOT":
        negate = True
        rest = rest[1:]
    if len(rest) != 1:
        raise ValueError(f"접점 피연산자 파싱 실패: {tokens!r}")
    return _Contact(op=op, operand=rest[0], negate=negate)


class XgkProgram:
    """에미트된 LS_XGK 니모닉 텍스트를 파싱해 렁 목록으로 보관."""

    def __init__(self, xgk_text: str) -> None:
        self.rungs: list[_Rung] = []
        contacts: list[_Contact] = []
        outputs: list[_Output] = []

        def flush() -> None:
            if contacts or outputs:
                self.rungs.append(_Rung(tuple(contacts), tuple(outputs)))
            contacts.clear()
            outputs.clear()

        for raw in xgk_text.splitlines():
            line = raw.strip()
            if not line:
                flush()  # 빈 줄 = 렁 경계
                continue
            if line.startswith(";") or line.startswith("//"):
                continue  # 주석/헤더
            tokens = line.split()
            head = tokens[0].upper()
            if head in _OUTPUT_OPS:
                n_preset = _OUTPUT_OPS[head]
                operand = tokens[1]
                preset = tokens[2] if n_preset and len(tokens) > 2 else ""
                outputs.append(_Output(kind=head, operand=operand, preset=preset))
            else:
                contacts.append(_parse_contact(tokens))
        flush()

    # -- 디바이스/심볼 수집 -------------------------------------------------
    def fb_outputs(self) -> list[_Output]:
        """타이머/카운터 출력(=FB) 목록(렁 순서)."""
        return [
            o
            for r in self.rungs
            for o in r.outputs
            if o.kind in ("TON", "TOF", "TP", "CTU", "CTD")
        ]

    def coil_operands(self) -> list[str]:
        """OUT/SET/RST 가 구동하는 코일 피연산자(중복 제거·정의 순서 유지)."""
        seen: list[str] = []
        for r in self.rungs:
            for o in r.outputs:
                if o.kind in ("OUT", "SET", "RST") and o.operand not in seen:
                    seen.append(o.operand)
        return seen

    def operands(self) -> set[str]:
        """접점/출력에 등장하는 모든 피연산자."""
        out: set[str] = set()
        for r in self.rungs:
            for c in r.contacts:
                if c.operand:
                    out.add(c.operand)
            for o in r.outputs:
                out.add(o.operand)
        return out


@dataclass
class XgkSample:
    t_ms: int
    inputs: dict[str, bool]
    outputs: dict[str, bool]


@dataclass
class XgkResult:
    samples: list[XgkSample]
    outputs: list[str]
    inputs: list[str]
    timers: list[str] = field(default_factory=list)

    def output_trace(self, name: str) -> list[bool]:
        return [s.outputs.get(name, False) for s in self.samples]


def _eval_contacts(contacts: tuple[_Contact, ...], table: dict[str, bool]) -> bool:
    """IL 스택머신으로 접점 스트림을 평가해 렁 파워를 돌려준다.

    LD x→push v(x); LDN x→push ¬v(x); AND/ANI→top ∧ (¬)v(x);
    OR/ORI→top ∨ (¬)v(x); ANB→a∧b; ORB→a∨b.
    """
    stack: list[bool] = []
    for c in contacts:
        if c.op == "ORB":
            b = stack.pop()
            a = stack.pop()
            stack.append(a or b)
        elif c.op == "ANB":
            b = stack.pop()
            a = stack.pop()
            stack.append(a and b)
        else:
            val = table.get(c.operand, False)
            if c.negate:
                val = not val
            if c.op == "LD":
                stack.append(val)
            elif c.op == "AND":
                stack[-1] = stack[-1] and val
            else:  # OR
                stack[-1] = stack[-1] or val
    return stack[-1] if stack else False


def _power_var(operand: str) -> str:
    """FB 인에이블/카운트 신호를 담을 합성 변수명(피연산자별로 유일)."""
    return f"__pwr__{operand}"


def _build_fb(
    prog: XgkProgram,
) -> tuple[dict[str, _Timer], dict[str, _Counter], list[tuple[_Output, str]]]:
    """타이머/카운터 FB 를 ``_Timer``/``_Counter`` 로 구성한다.

    인에이블/카운트 식은 합성 파워 변수(``Var``)로 두고, 스캔마다 해당 렁의 파워를
    그 변수에 써 넣어 ST 시뮬레이터와 동일한 ``_eval`` 경로로 구동한다.
    카운터의 RESET 은 에미터가 별도 렁으로 내지 않으므로(검증 게이트가 reset 을 IN
    식에 합성) FALSE 로 둔다.
    """
    timers: dict[str, _Timer] = {}
    counters: dict[str, _Counter] = {}
    drives: list[tuple[_Output, str]] = []
    for rung in prog.rungs:
        for out in rung.outputs:
            if out.kind not in ("TON", "TOF", "TP", "CTU", "CTD"):
                continue
            pv = _power_var(out.operand)
            drives.append((out, pv))
            if out.kind in ("CTU", "CTD"):
                preset = int(re.sub(r"\D", "", out.preset) or 0)
                counters[out.operand] = _Counter(
                    kind=out.kind,
                    preset=preset,
                    count_expr=Var(pv),
                    reset_expr=Const(False),
                )
            else:
                timers[out.operand] = _Timer(
                    kind=out.kind,
                    preset_ms=_parse_time_ms(out.preset),
                    enable_expr=Var(pv),
                )
    return timers, counters, drives


def simulate_xgk(
    xgk_text: str,
    inputs_timeline: list[tuple[int, dict[str, bool]]],
    *,
    duration_ms: int,
    step_ms: int = 100,
) -> XgkResult:
    """에미트된 XGK 니모닉을 가상 PLC로 가동한다(``simulate`` 와 동일 시그니처/스캔순서).

    스캔순서: 입력 읽기 → FB(.Q) 갱신 → 렁 top-to-bottom 평가 → 출력 쓰기 → 샘플.
    디바이스 상태는 피연산자 문자열(주소 또는 심볼)로 키잉한다.
    """
    if step_ms <= 0:
        raise ValueError("step_ms 는 1 이상이어야 합니다.")
    n_samples = duration_ms // step_ms + 1
    if n_samples > MAX_SIM_SAMPLES:
        raise ValueError(
            f"스캔 샘플 {n_samples}개가 상한({MAX_SIM_SAMPLES})을 초과합니다."
        )

    prog = XgkProgram(xgk_text)
    timers, counters, fb_drives = _build_fb(prog)

    coils = prog.coil_operands()
    fb_q = {f"{name}.Q" for name in timers} | {f"{name}.Q" for name in counters}
    # 입력 = 어떤 출력/FB.Q 도 아니고 멤버접근(.)도 아닌 피연산자.
    inputs = sorted(
        op
        for op in prog.operands()
        if op not in coils and op not in fb_q and "." not in op
    )

    table: dict[str, bool] = {}
    for c in coils:
        table[c] = False

    timeline = sorted(inputs_timeline, key=lambda x: x[0])
    cur_inputs: dict[str, bool] = {s: False for s in inputs}
    samples: list[XgkSample] = []
    ti = 0
    t = 0
    while t <= duration_ms:
        # 1) 입력 읽기
        while ti < len(timeline) and timeline[ti][0] <= t:
            cur_inputs.update(timeline[ti][1])
            ti += 1
        for s in inputs:
            table[s] = cur_inputs.get(s, False)
        # 2) FB 인에이블/카운트 렁 파워를 합성 변수에 기록 → FB 갱신 → .Q 반영.
        #    (직전 스캔 코일값 참조 = ST 시뮬레이터와 동일 시점)
        for out, pv in fb_drives:
            for rung in prog.rungs:
                if out in rung.outputs:
                    table[pv] = _eval_contacts(rung.contacts, table)
                    break
        for name, tmr in timers.items():
            tmr.scan(table, step_ms)
            table[f"{name}.Q"] = tmr.q
        for name, cnt in counters.items():
            cnt.scan(table)
            table[f"{name}.Q"] = cnt.q
        # 3) 렁 top-to-bottom 평가 → 코일 출력 쓰기(seal-in 은 직전 값 참조)
        for rung in prog.rungs:
            coil_outs = [
                o for o in rung.outputs if o.kind in ("OUT", "SET", "RST")
            ]
            if not coil_outs:
                continue
            power = _eval_contacts(rung.contacts, table)
            for o in coil_outs:
                if o.kind == "OUT":
                    table[o.operand] = power
                elif o.kind == "SET":
                    if power:
                        table[o.operand] = True
                else:  # RST
                    if power:
                        table[o.operand] = False
        samples.append(
            XgkSample(
                t_ms=t,
                inputs={s: table.get(s, False) for s in inputs},
                outputs={c: table.get(c, False) for c in coils},
            )
        )
        t += step_ms

    return XgkResult(
        samples=samples,
        outputs=coils,
        inputs=inputs,
        timers=sorted(timers) + sorted(counters),
    )
