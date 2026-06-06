"""벤더 래더 에미터 (Phase N) — LadderProgram → 벤더별 명령어 텍스트(IL/STL).

L1 ``VendorProfile`` 의 니모닉·주소 표기를 사용해, Sum-of-Products 래더를
벤더별 명령어 리스트로 렌더한다.

  * IL 계열(LS/미쓰비시/옴론): ``LD/LOAD → AND/ANI → ORB → OUT`` 블록 인코딩.
    각 곱항(병렬 브랜치)을 LOAD+AND 로 쌓고, 두 번째 브랜치부터 ORB 로 OR 결합.
  * STL(지멘스): ``A( … ) O( … ) =`` 중첩 블록.

주의: 생성 텍스트는 벤더 IDE 임포트 포맷이 아니라 **사람이 검토하는 명령어 표현**이다.
실제 다운로드 전 해당 IDE에서 반드시 검증해야 한다(docs/SAFETY.md).
"""

from __future__ import annotations

from app.models import ElementType, LadderBranch, LadderElement, LadderProgram
from app.vendors.profiles import DEFAULT_PROFILE, VendorProfile


def _operand(el: LadderElement) -> str:
    """주소가 할당돼 있으면 주소, 없으면 심볼명."""
    return el.address or el.symbol


def _coil_mnemonic(profile: VendorProfile, el: LadderElement) -> str:
    if el.element_type == ElementType.COIL_SET:
        return profile.mnemonic("set")
    if el.element_type == ElementType.COIL_RESET:
        return profile.mnemonic("reset")
    if el.element_type == ElementType.TIMER:
        return profile.mnemonic("timer_on")
    if el.element_type == ElementType.COUNTER:
        return profile.mnemonic("counter_up")
    return profile.mnemonic("coil")


def _output_line(profile: VendorProfile, el: LadderElement) -> str:
    """출력 명령 한 줄. 타이머/카운터는 프리셋(description)을 피연산자로 덧붙인다."""
    mnem = _coil_mnemonic(profile, el)
    if el.element_type in (ElementType.TIMER, ElementType.COUNTER) and el.description:
        return f"{mnem} {_operand(el)} {el.description}"
    return f"{mnem} {_operand(el)}"


def _nonempty_branches(branches: list[LadderBranch]) -> list[LadderBranch]:
    return [b for b in branches if b.elements]


def _emit_orb(program: LadderProgram, profile: VendorProfile) -> list[str]:
    """LD/AND/ORB 계열(LS·미쓰비시·옴론) 명령어 리스트 생성."""
    ld_no = profile.mnemonic("contact_no")
    ld_nc = profile.mnemonic("contact_nc")
    and_no = profile.mnemonic("and_no")
    and_nc = profile.mnemonic("and_nc")
    orb = profile.mnemonic("or_block")

    lines: list[str] = []
    for rung in program.rungs:
        if rung.comment:
            lines.append(f"; {rung.comment}")
        branches = _nonempty_branches(rung.input_branches)
        if not branches:
            lines.append("; (무조건 ON — 상시 접점 필요)")
        for i, br in enumerate(branches):
            for j, el in enumerate(br.elements):
                is_nc = el.element_type == ElementType.CONTACT_NC
                if j == 0:
                    mnem = ld_nc if is_nc else ld_no
                else:
                    mnem = and_nc if is_nc else and_no
                lines.append(f"{mnem} {_operand(el)}")
            if i > 0:
                lines.append(orb)  # 이전 블록과 OR 결합
        for out in rung.outputs:
            lines.append(_output_line(profile, out))
        lines.append("")
    return lines


def _emit_stl(program: LadderProgram, profile: VendorProfile) -> list[str]:
    """지멘스 STL: A( … ) O( … ) = 중첩 블록."""
    a = profile.mnemonic("contact_no")
    an = profile.mnemonic("contact_nc")

    def lit(el: LadderElement) -> str:
        mnem = an if el.element_type == ElementType.CONTACT_NC else a
        return f"  {mnem} {_operand(el)}"

    lines: list[str] = []
    for rung in program.rungs:
        if rung.comment:
            lines.append(f"// {rung.comment}")
        branches = _nonempty_branches(rung.input_branches)
        single = len(branches) == 1
        for i, br in enumerate(branches):
            if single:
                for el in br.elements:
                    lines.append(lit(el).strip())
            else:
                lines.append("A(" if i == 0 else "O(")
                for el in br.elements:
                    lines.append(lit(el))
                lines.append(")")
        for out in rung.outputs:
            lines.append(_output_line(profile, out))
        lines.append("")
    return lines


def _emit_iec_il(program: LadderProgram, profile: VendorProfile) -> list[str]:
    """IEC 61131-3 IL(LS XGI/XEC): LD/LDN → AND/ANDN, 병렬은 OR( … ) 괄호, ST 저장.

    각 곱항(직렬 AND)을 LD/AND 로 쌓고, 두 번째 브랜치부터 ``OR(`` … ``)`` 로
    이전 결과와 OR 결합한다(IEC IL 의 괄호식 누적).
    """
    ld = profile.mnemonic("contact_no")
    ldn = profile.mnemonic("contact_nc")
    and_no = profile.mnemonic("and_no")
    and_nc = profile.mnemonic("and_nc")
    or_op = profile.mnemonic("or_no")

    def term(br: LadderBranch, first_mnem: str, rest_mnem: str, first_nc: str,
             rest_nc: str, indent: str) -> list[str]:
        out: list[str] = []
        for j, el in enumerate(br.elements):
            is_nc = el.element_type == ElementType.CONTACT_NC
            if j == 0:
                mnem = first_nc if is_nc else first_mnem
            else:
                mnem = rest_nc if is_nc else rest_mnem
            out.append(f"{indent}{mnem} {_operand(el)}")
        return out

    lines: list[str] = []
    for rung in program.rungs:
        if rung.comment:
            lines.append(f"(* {rung.comment} *)")
        branches = _nonempty_branches(rung.input_branches)
        if not branches:
            lines.append("(* 무조건 ON — 상시 접점 필요 *)")
        for i, br in enumerate(branches):
            if i == 0:
                lines.extend(term(br, ld, and_no, ldn, and_nc, ""))
            else:
                # OR( <첫 리터럴> ) 로 새 곱항 시작, 내부 AND 누적, ) 로 닫음
                lines.append(f"{or_op}(")
                lines.extend(term(br, ld, and_no, ldn, and_nc, "  "))
                lines.append(")")
        for out in rung.outputs:
            lines.append(_output_line(profile, out))
        lines.append("")
    return lines


def _scl_term(profile: VendorProfile, br: LadderBranch) -> str:
    """직렬 브랜치(AND) → SCL 부분식: A AND NOT B AND C."""
    parts: list[str] = []
    for el in br.elements:
        operand = _operand(el)
        if el.element_type == ElementType.CONTACT_NC:
            parts.append(f"{profile.op_not} {operand}")
        else:
            parts.append(operand)
    return f" {profile.op_and} ".join(parts)


def _emit_scl(program: LadderProgram, profile: VendorProfile) -> list[str]:
    """지멘스 SCL 대입식: OUT := (A AND NOT B) OR (C);.

    각 곱항을 괄호로 감싸 OR 결합. 단일 곱항이면 괄호 생략.
    SET/RESET/타이머/카운터는 SCL 식으로 깔끔히 표현되지 않으므로 명령형 주석으로 남긴다.
    """
    lines: list[str] = []
    for rung in program.rungs:
        if rung.comment:
            lines.append(f"// {rung.comment}")
        branches = _nonempty_branches(rung.input_branches)
        if branches:
            terms = [_scl_term(profile, br) for br in branches]
            if len(terms) == 1:
                rhs = terms[0]
            else:
                rhs = f" {profile.op_or} ".join(f"({t})" for t in terms)
        else:
            rhs = "TRUE"
        for out in rung.outputs:
            if out.element_type == ElementType.COIL:
                lines.append(f"{_operand(out)} {profile.assign} {rhs};")
            else:
                # SET/RESET/TIMER/COUNTER 는 SCL 단순 대입으로 표현 불가 → 검토 주석
                lines.append(f"// {_output_line(profile, out)}  (조건: {rhs})")
        lines.append("")
    return lines


def emit(program: LadderProgram, profile: VendorProfile = DEFAULT_PROFILE) -> str:
    """LadderProgram 을 프로파일에 맞는 명령어 텍스트로 렌더한다."""
    if profile.il_style == "stl":
        header = f"// ===== {profile.name} ====="
        body = _emit_stl(program, profile)
    elif profile.il_style == "scl":
        header = f"// ===== {profile.name} ====="
        body = _emit_scl(program, profile)
    elif profile.il_style == "iec_il":
        header = f"(* ===== {profile.name} ===== *)"
        body = _emit_iec_il(program, profile)
    else:
        header = f"; ===== {profile.name} ====="
        body = _emit_orb(program, profile)
    lines = [header, *body]
    return "\n".join(lines).rstrip() + "\n"
