"""결정론 명세→ST 합성기 (래더 생성 난제의 핵심 해법).

연구·실무 공통 결론: **LD 자유생성은 미해결 난제**다. 그래서 LLM 에게 래더를
자유작성시키지 않는다. LLM 은 자연어→명세(구조화 추출)만 하고, **명세→ST 는
결정론적으로 합성**한다 → 래더 로직에서 환각을 원천 차단.

합성 규칙(상태머신 → 자기유지):
  각 출력 OUT 에 대해
    - on_states  : on_entry 에 ``OUT := TRUE;`` 가 있는 상태들
    - turn_on    : on_states 로 진입하는 전이들의 조건(OR)
    - turn_off   : on_states 에서 비활성 상태로 나가는 전이들의 조건(OR)
    - 인터락     : 상대 출력의 NOT 추가(상호배제 강제)
  ⇒ ``OUT := (turn_on OR OUT) AND NOT (turn_off) AND NOT <상대들>;``

이는 결정론·테스트가능하며 이중코일 0(출력당 1회 대입)을 보장한다.
on_entry 로 구동되지 않는 조합 출력(예: 알람 경음기)은 합성 불가 → LLM/패턴 폴백.
"""

from __future__ import annotations

import re

from app.boolexpr import parse
from app.models import IODirection, StateMachineSpec

_SET_TRUE_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*:=\s*TRUE\s*;\s*$", re.IGNORECASE)


def _derived_map(spec: StateMachineSpec) -> dict[str, str]:
    """파생(조합) 출력 심볼 → 불리언식. on_entry 와 충돌하면 ValueError."""
    result: dict[str, str] = {}
    for d in spec.derived_outputs:
        if _on_states(spec, d.output):
            raise ValueError(
                f"파생 출력 '{d.output}' 이 상태 on_entry 로도 구동됩니다(이중 정의)."
            )
        parse(d.expression)  # 파싱 불가하면 즉시 ValueError
        result[d.output] = d.expression
    return result


def _output_symbols(spec: StateMachineSpec) -> list[str]:
    """OUTPUT 방향 IO 심볼(명세 순서 유지, 중복 제거)."""
    seen: set[str] = set()
    out: list[str] = []
    for io in spec.io_points:
        if io.direction == IODirection.OUTPUT and io.symbol not in seen:
            seen.add(io.symbol)
            out.append(io.symbol)
    return out


def _on_states(spec: StateMachineSpec, output: str) -> set[str]:
    """on_entry 에 ``output := TRUE;`` 가 있는 상태 이름 집합."""
    names: set[str] = set()
    for state in spec.states:
        for stmt in state.on_entry:
            m = _SET_TRUE_RE.match(stmt)
            if m and m.group(1) == output:
                names.add(state.name)
                break
    return names


def _interlock_partners(spec: StateMachineSpec, output: str) -> list[str]:
    """output 과 상호배제(인터락) 관계인 상대 출력들(명세 순서)."""
    partners: list[str] = []
    for lock in spec.interlocks:
        if lock.output_a == output and lock.output_b not in partners:
            partners.append(lock.output_b)
        elif lock.output_b == output and lock.output_a not in partners:
            partners.append(lock.output_a)
    return partners


def _synth_one(spec: StateMachineSpec, output: str) -> str | None:
    """단일 출력의 ST 한 줄을 합성한다(불가 시 None).

    파생 출력은 그 불리언식을 그대로, 그 외는 상태머신에서 자기유지로 합성한다.
    """
    derived = _derived_map(spec)
    if output in derived:
        return f"{output} := {derived[output]};"

    on_states = _on_states(spec, output)
    if not on_states:
        return None
    turn_on = [tr.condition for tr in spec.transitions if tr.to_state in on_states]
    if not turn_on:
        return None
    # 전이 조건이 파싱 가능한 불리언식인지 검증(다운스트림 크래시 방지)
    for cond in turn_on:
        parse(cond)
    turn_off = [
        tr.condition
        for tr in spec.transitions
        if tr.from_state in on_states and tr.to_state not in on_states
    ]
    on_expr = " OR ".join(f"({c})" for c in turn_on)
    expr = f"({on_expr} OR {output})"
    if turn_off:
        off_expr = " OR ".join(f"({c})" for c in turn_off)
        expr += f" AND NOT ({off_expr})"
    for partner in _interlock_partners(spec, output):
        expr += f" AND NOT {partner}"
    return f"{output} := {expr};"


def synthesizable_outputs(spec: StateMachineSpec) -> set[str]:
    """결정론 합성이 가능한(상태구동) 출력 집합."""
    return {o for o in _output_symbols(spec) if _synth_one(spec, o) is not None}


def covers_all_outputs(spec: StateMachineSpec) -> bool:
    """명세의 모든 OUTPUT 을 결정론 합성으로 덮을 수 있는가."""
    outs = _output_symbols(spec)
    return bool(outs) and synthesizable_outputs(spec) == set(outs)


def synthesize_st(spec: StateMachineSpec) -> str:
    """명세를 결정론적으로 ST(자기유지 형식)로 합성한다.

    합성 가능한 출력만 한 줄씩 대입문으로 만든다(이중코일 0 보장).
    """
    lines: list[str] = []
    for output in _output_symbols(spec):
        line = _synth_one(spec, output)
        if line is not None:
            lines.append(line)
    return "\n".join(lines)
