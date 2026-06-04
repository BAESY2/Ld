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
    return profile.mnemonic("coil")


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
            lines.append(f"{_coil_mnemonic(profile, out)} {_operand(out)}")
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
            lines.append(f"{_coil_mnemonic(profile, out)} {_operand(out)}")
        lines.append("")
    return lines


def emit(program: LadderProgram, profile: VendorProfile = DEFAULT_PROFILE) -> str:
    """LadderProgram 을 프로파일에 맞는 명령어 텍스트로 렌더한다."""
    if profile.il_style == "stl":
        header = f"// ===== {profile.name} ====="
        body = _emit_stl(program, profile)
    else:
        header = f"; ===== {profile.name} ====="
        body = _emit_orb(program, profile)
    lines = [header, *body]
    return "\n".join(lines).rstrip() + "\n"
