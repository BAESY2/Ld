"""평문 설명 레이어 — 명세/래더/검증을 비전문가용 한국어로 풀어쓴다.

"완주 목표": PLC를 모르는 사람도 기획만으로 설계. 그러려면 결과(ST/IL/래더)가
아니라 **무슨 동작을 하는지**를 평이한 말로 보여줘야 한다. 전부 결정론이라
LLM/키 없이 동작한다.
"""

from __future__ import annotations

from app.models import (
    ElementType,
    IODirection,
    LadderProgram,
    LadderRung,
    StateMachineSpec,
    VerificationReport,
)

# 검증 코드 → 평문 (사유 + 고치는 법)
_ISSUE_KO: dict[str, tuple[str, str]] = {
    "DOUBLE_COIL": ("같은 출력을 두 곳에서 켜고 있어요(이중 코일).",
                    "한 출력은 한 군데에서만 제어하도록 조건을 OR로 합치세요."),
    "INTERLOCK": ("동시에 켜지면 안 되는 두 출력이 같이 켜질 수 있어요.",
                  "각 출력 조건에 '상대가 꺼져 있을 때'를 추가하세요(상호 잠금)."),
    "DEADLOCK": ("시작 상태가 없어 동작을 시작할 수 없어요.",
                 "초기 상태를 하나 지정하세요."),
    "UNREACHABLE": ("도달할 수 없는 상태가 있어요(쓰이지 않는 단계).",
                    "그 상태로 가는 조건(전이)을 추가하거나 상태를 지우세요."),
    "NO_LOGIC": ("유효한 제어 로직이 없어요.",
                 "입력이 'A := B AND C;' 같은 대입문인지 확인하세요."),
    "TIMER_PRESET": ("타이머 설정 시간이 0 이하예요.", "지연 시간을 0보다 크게 정하세요."),
    "TIMER_ENABLE": ("타이머를 켜는 조건이 비어 있어요.", "타이머를 시작시킬 신호를 지정하세요."),
    "COUNTER_PRESET": ("카운터 목표값이 0 이하예요.", "셀 개수를 1 이상으로 정하세요."),
    "COUNTER_RESET": ("카운터 리셋 조건이 없어요(계속 쌓일 위험).",
                      "0으로 되돌릴 리셋 신호를 지정하세요."),
}


def explain_spec(spec: StateMachineSpec) -> str:
    """명세를 '무엇을 하는 장치인가'로 풀어쓴다."""
    lines: list[str] = []
    if spec.title:
        lines.append(f"■ {spec.title}")
    inputs = [p for p in spec.io_points if p.direction == IODirection.INPUT]
    outputs = [p for p in spec.io_points if p.direction == IODirection.OUTPUT]
    if inputs:
        lines.append("입력(사람·센서 신호): " + ", ".join(
            f"{p.symbol}({p.description})" if p.description else p.symbol for p in inputs))
    if outputs:
        lines.append("출력(움직이는 것): " + ", ".join(
            f"{p.symbol}({p.description})" if p.description else p.symbol for p in outputs))
    for t in spec.timers:
        sec = t.preset_ms / 1000
        lines.append(f"타이머 {t.name}: 조건이 유지되면 {sec:g}초 뒤 신호를 냅니다.")
    for c in spec.counters:
        lines.append(f"카운터 {c.name}: 신호를 {c.preset}번 세면 완료됩니다.")
    if spec.interlocks:
        for il in spec.interlocks:
            why = f" ({il.reason})" if il.reason else ""
            lines.append(
                f"안전 잠금: {il.output_a} 와 {il.output_b} 는 동시에 켜지지 않습니다{why}."
            )
    return "\n".join(lines)


def _branch_phrase(rung: LadderRung) -> str:
    """렁 입력 조건을 '~이고/또는' 한국어로."""
    branch_strs: list[str] = []
    for br in rung.input_branches:
        if not br.elements:
            branch_strs.append("항상")
            continue
        parts = []
        for el in br.elements:
            state = "꺼져 있음" if el.element_type == ElementType.CONTACT_NC else "켜져 있음"
            parts.append(f"{el.symbol}가 {state}")
        branch_strs.append(", ".join(parts))
    if not branch_strs:
        return "(켜질 수 있는 조건이 없음 — 모순된 로직)"
    if len(branch_strs) > 1:
        return " 또는 ".join(f"({b})" for b in branch_strs)
    return branch_strs[0]


def _is_seal_in(rung: LadderRung) -> bool:
    """출력이 자기 입력 접점에 등장하면 자기유지."""
    outs = {o.symbol for o in rung.outputs}
    return any(
        el.symbol in outs
        for br in rung.input_branches
        for el in br.elements
    )


def explain_ladder(ladder: LadderProgram) -> list[str]:
    """각 렁을 한 줄 평문으로 설명한다."""
    out: list[str] = []
    for i, rung in enumerate(ladder.rungs, 1):
        if not rung.outputs:
            continue
        o = rung.outputs[0]
        cond = _branch_phrase(rung)
        if o.element_type == ElementType.TIMER:
            out.append(f"렁 {i}: {cond} 동안 타이머 {o.symbol}({o.description})가 동작합니다.")
        elif o.element_type == ElementType.COUNTER:
            out.append(f"렁 {i}: {cond} 마다 카운터 {o.symbol}가 1씩 셉니다.")
        else:
            tail = " (자기유지: 한 번 켜지면 정지 조건 전까지 유지)" if _is_seal_in(rung) else ""
            out.append(f"렁 {i}: {cond} 면 {o.symbol}가 켜집니다.{tail}")
    return out


def explain_issues(report: VerificationReport) -> list[str]:
    """검증 결과를 평문 경고로."""
    if report.passed and not report.issues:
        return ["✅ 검사 통과 — 이중 코일·안전 잠금·도달성에 문제가 없습니다."]
    msgs: list[str] = []
    for issue in report.issues:
        why, fix = _ISSUE_KO.get(issue.code, (issue.message, ""))
        mark = "❌" if issue.severity == "error" else "⚠️"
        line = f"{mark} {why}"
        if fix:
            line += f" → {fix}"
        msgs.append(line)
    return msgs


def explain_all(
    spec: StateMachineSpec, ladder: LadderProgram, report: VerificationReport
) -> str:
    """명세+래더+검증을 한 편의 평문 설명 문서로."""
    blocks = ["## 이 장치는 무엇을 하나요\n" + explain_spec(spec)]
    rungs = explain_ladder(ladder)
    if rungs:
        blocks.append("## 동작 설명 (한 줄씩)\n" + "\n".join(f"- {r}" for r in rungs))
    blocks.append("## 안전·검증\n" + "\n".join(f"- {m}" for m in explain_issues(report)))
    return "\n\n".join(blocks)
