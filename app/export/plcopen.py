"""PLCopen XML(IEC 61131-10) 익스포트 (Phase N).

학습(docs/research §5): PLCopen XML 은 유일한 벤더중립 표준 교환 포맷으로
OpenPLC Editor / CODESYS 계열이 직접 임포트한다. 우리 출력(ST)을 표준 ST POU
로 감싸 내보내면 무료 오픈 에디터로 라운드트립할 수 있다.

graphical LD 바디(좌표 포함)는 후속 정밀화 과제로 두고, 1차는 **ST POU**로
내보낸다(가장 단순한 유효 형태, 임포트 가능).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from app.models import DataType, IODirection, IOPoint, StateMachineSpec
from app.safety import SAFETY_NOTICE

_ASSIGN_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*:=\s*([^;]+?)\s*;\s*$")
_FB_CALL_RE = re.compile(r"^\s*[A-Za-z_]\w*\s*\(.*\)\s*;\s*$")
# 점표기 멤버(T1.Q) 포함 식별자
_IDENT_RE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")
_KEYWORDS = {"AND", "OR", "NOT", "TRUE", "FALSE"}


def infer_io_spec(st_code: str, title: str = "") -> StateMachineSpec:
    """ST 만으로 최소 명세를 추론한다(대입 좌변=출력, RHS 전용 심볼=입력).

    명세 없이 export 엔드포인트를 쓰기 위한 휴리스틱.
    """
    outputs: list[str] = []
    rhs_ids: list[str] = []
    out_set: set[str] = set()
    for line in st_code.splitlines():
        if _FB_CALL_RE.match(line):
            continue  # 타이머/카운터 FB 호출은 변수 추론에서 제외
        m = _ASSIGN_RE.match(line)
        if not m:
            continue
        lhs = m.group(1)
        if lhs not in out_set:
            out_set.add(lhs)
            outputs.append(lhs)
        for tok in _IDENT_RE.findall(m.group(2)):
            # 점표기(예: T1.Q)는 FB 출력 참조이므로 입력으로 만들지 않음
            if tok.upper() not in _KEYWORDS and "." not in tok:
                rhs_ids.append(tok)
    inputs = [s for s in dict.fromkeys(rhs_ids) if s not in out_set]
    points = [IOPoint(symbol=s, direction=IODirection.INPUT) for s in inputs]
    points += [IOPoint(symbol=s, direction=IODirection.OUTPUT) for s in outputs]
    return StateMachineSpec(title=title, io_points=points)

_TC6 = "http://www.plcopen.org/xml/tc6_0201"
_XHTML = "http://www.w3.org/1999/xhtml"

# IEC 61131-3 표준 타입 → PLCopen 타입 엘리먼트 이름
_TYPE_TAG: dict[DataType, str] = {
    DataType.BOOL: "BOOL",
    DataType.INT: "INT",
    DataType.DINT: "DINT",
    DataType.REAL: "REAL",
    DataType.TIME: "TIME",
    DataType.WORD: "WORD",
}


def _q(tag: str) -> str:
    return f"{{{_TC6}}}{tag}"


def _add_var(parent: ET.Element, name: str, data_type: DataType) -> None:
    var = ET.SubElement(parent, _q("variable"), {"name": name})
    type_el = ET.SubElement(var, _q("type"))
    ET.SubElement(type_el, _q(_TYPE_TAG.get(data_type, "BOOL")))


def to_plcopen_xml(
    spec: StateMachineSpec,
    st_code: str,
    pou_name: str = "Main",
    company: str = "Ladder AI",
) -> str:
    """명세 + ST 를 PLCopen XML(ST POU) 문자열로 직렬화한다."""
    ET.register_namespace("", _TC6)
    ET.register_namespace("xhtml", _XHTML)

    project = ET.Element(_q("project"))

    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    ET.SubElement(
        project,
        _q("fileHeader"),
        {
            "companyName": company,
            "productName": "PLC Ladder Agent",
            "productVersion": "1.0",
            "creationDateTime": now,
        },
    )
    content = ET.SubElement(
        project, _q("contentHeader"), {"name": spec.title or pou_name}
    )
    coord = ET.SubElement(content, _q("coordinateInfo"))
    for kind in ("fbd", "ld", "sfc"):
        k = ET.SubElement(coord, _q(kind))
        ET.SubElement(k, _q("scaling"), {"x": "10", "y": "10"})

    types = ET.SubElement(project, _q("types"))
    ET.SubElement(types, _q("dataTypes"))
    pous = ET.SubElement(types, _q("pous"))

    pou = ET.SubElement(pous, _q("pou"), {"name": pou_name, "pouType": "program"})
    interface = ET.SubElement(pou, _q("interface"))

    inputs = [io for io in spec.io_points if io.direction == IODirection.INPUT]
    outputs = [io for io in spec.io_points if io.direction == IODirection.OUTPUT]

    if inputs:
        in_vars = ET.SubElement(interface, _q("inputVars"))
        for io in inputs:
            _add_var(in_vars, io.symbol, io.data_type)
    if outputs:
        out_vars = ET.SubElement(interface, _q("outputVars"))
        for io in outputs:
            _add_var(out_vars, io.symbol, io.data_type)

    # 타이머/카운터 등은 지역 변수로
    local_vars = ET.SubElement(interface, _q("localVars"))
    for t in spec.timers:
        _add_var(local_vars, t.name, DataType.TIME)
    for c in spec.counters:
        _add_var(local_vars, c.name, DataType.INT)

    body = ET.SubElement(pou, _q("body"))
    st_el = ET.SubElement(body, _q("ST"))
    xhtml = ET.SubElement(st_el, f"{{{_XHTML}}}xhtml")
    xhtml.text = st_code

    ET.SubElement(project, _q("instances")).append(ET.Element(_q("configurations")))

    ET.indent(project, space="  ")
    xml_bytes: bytes = ET.tostring(project, encoding="utf-8", xml_declaration=True)
    xml_str = xml_bytes.decode("utf-8")
    # 안전 경계 고지를 XML 주석으로 파일에 *내장*한다 — JSON 봉투는 PLC 툴체인으로
    # 들어가는 순간 사라지므로, 경계가 파일과 함께 컨트롤러까지 따라가게 한다(P0).
    notice = SAFETY_NOTICE.replace("--", "—")  # XML 주석엔 '--' 금지
    comment = f"<!-- ⚠ 안전 경계 / SAFETY BOUNDARY (ISO 13849/IEC 62061): {notice} -->\n"
    decl, sep, rest = xml_str.partition("\n")
    return f"{decl}{sep}{comment}{rest}" if sep else f"{comment}{xml_str}"
