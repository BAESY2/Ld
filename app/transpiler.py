"""결정론적 ST → 래더(Sum-of-Products) 트랜스파일러 (Phase H1, API 키 불필요).

ST 의 `OUT := <불리언식>;` 대입문 각각을 래더 렁 하나로 변환한다.
불리언식을 DNF 로 정규화 → 각 곱항이 직렬(AND) 브랜치, 항들의 OR 이 병렬 브랜치.
LLM 의존 없이 즉시 변환되므로 라이브 미리보기의 엔진이 된다.
"""

from __future__ import annotations

import re

from app.boolexpr import parse, to_dnf
from app.memory_map import DeviceAllocator
from app.models import (
    ElementType,
    LadderBranch,
    LadderElement,
    LadderProgram,
    LadderRung,
)

_ASSIGN_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*:=\s*(.+?)\s*;\s*$")
_COMMENT_RE = re.compile(r"^\s*//\s?(.*)$")


def _rung_from_assignment(
    output_symbol: str,
    expr: str,
    comment: str,
    allocator: DeviceAllocator | None,
) -> LadderRung:
    terms = to_dnf(parse(expr))

    def addr(sym: str) -> str:
        return allocator.address_of(sym) or "" if allocator else ""

    branches: list[LadderBranch] = []
    for term in terms:
        # 결정론적 순서: (이름, 부정여부) 정렬
        literals = sorted(term, key=lambda lit: (lit[0], lit[1]))
        elements = [
            LadderElement(
                element_type=ElementType.CONTACT_NC if negated else ElementType.CONTACT_NO,
                symbol=name,
                address=addr(name),
            )
            for name, negated in literals
        ]
        branches.append(LadderBranch(elements=elements))

    output = LadderElement(
        element_type=ElementType.COIL,
        symbol=output_symbol,
        address=addr(output_symbol),
    )
    return LadderRung(comment=comment, input_branches=branches, outputs=[output])


def transpile_st(
    st_code: str, allocator: DeviceAllocator | None = None, title: str = ""
) -> LadderProgram:
    """ST 코드를 LadderProgram 으로 변환한다.

    - `OUT := expr;` 한 줄 = 렁 하나.
    - 바로 위의 `// 주석` 은 해당 렁의 comment 가 된다.
    - 디바이스 맵 주석 블록/빈 줄은 무시.
    """
    rungs: list[LadderRung] = []
    pending_comment = ""

    for line in st_code.splitlines():
        assign = _ASSIGN_RE.match(line)
        if assign:
            rungs.append(
                _rung_from_assignment(
                    assign.group(1), assign.group(2), pending_comment, allocator
                )
            )
            pending_comment = ""
            continue

        comment = _COMMENT_RE.match(line)
        if comment:
            text = comment.group(1).strip()
            # 디바이스 맵 헤더/항목은 렁 주석으로 쓰지 않음
            if text.startswith("===") or text.startswith("(디바이스"):
                pending_comment = ""
            elif re.match(r"^\S+\s+[PMTCLKD]\d+$", text):
                pending_comment = ""
            else:
                pending_comment = text
            continue

        # 그 외(빈 줄 등)는 보류 주석 초기화
        if not line.strip():
            pending_comment = ""

    return LadderProgram(title=title, rungs=rungs)
