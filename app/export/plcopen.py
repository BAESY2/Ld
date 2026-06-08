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

from app.models import DataType, IODirection, IOPoint, StateMachineSpec
from app.safety import SAFETY_NOTICE

# 결정론적 고정 타임스탬프 (now() 금지 — 동일 입력 → 동일 바이트 출력 보장).
# ISO 8601 dateTime, PLCopen TC6 xsd:dateTime 형식.
_FIXED_DATETIME = "2024-01-01T00:00:00"

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
_XSI = "http://www.w3.org/2001/XMLSchema-instance"

# IEC 61131-3 표준 타입 → PLCopen 타입 엘리먼트 이름
_TYPE_TAG: dict[DataType, str] = {
    DataType.BOOL: "BOOL",
    DataType.INT: "INT",
    DataType.DINT: "DINT",
    DataType.REAL: "REAL",
    DataType.TIME: "TIME",
    DataType.WORD: "WORD",
}


# CDATA 직렬화 우회용 마커. ElementTree 는 CDATA 를 지원하지 않으므로 ST 본문을
# 마커로 감싸 트리에 넣고, tostring 후 escape 된 블록 전체를 CDATA 로 치환한다.
# 마커는 XML-special 문자가 없어 escape 되지 않으며, 일반 ST 코드에 나타나지 않는다.
_CDATA_OPEN = "@@CDATA_OPEN@@"
_CDATA_CLOSE = "@@CDATA_CLOSE@@"
_CDATA_BLOCK_RE = re.compile(
    re.escape(_CDATA_OPEN) + r"(.*?)" + re.escape(_CDATA_CLOSE), re.DOTALL
)


def _unescape(text: str) -> str:
    """ElementTree 텍스트 escape 를 역으로 푼다(&amp;/&lt;/&gt; → 원문)."""
    return (
        text.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
    )


def _wrap_cdata(text: str) -> str:
    """텍스트를 CDATA 섹션으로 감싼다. 본문에 ``]]>`` 가 있어도 안전.

    CDATA 안에는 종료 토큰 ``]]>`` 를 그대로 둘 수 없다(파서가 거기서 섹션을
    닫아 well-formed 가 깨진다 → IDE 임포트 실패). 표준 회피법: ``]]>`` 를
    ``]]]]><![CDATA[>`` 로 쪼개 두 개의 인접 CDATA 섹션으로 분할한다.
    """
    safe = text.replace("]]>", "]]]]><![CDATA[>")
    return f"<![CDATA[{safe}]]>"


def validate_plcopen_xml(xml: str) -> None:
    """내보낸 XML 이 PLCopen TC6 v2.01 임포트 적합한지 결정론적으로 검증한다.

    외부 IDE(OpenPLC Editor/CODESYS) 임포트가 깨지는 주된 원인을 단정으로
    잡아낸다. 위반 시 ``ValueError`` 를 던진다(조용한 손상 금지).

    검사 항목:
      1. ``xml.etree`` 로 파싱되는 well-formed 문서.
      2. 루트가 ``{tc6_0201}project`` 이고 tc6/xhtml/xsi namespace 선언 존재.
      3. 필수 구조: types/pous/pou + interface + body/ST + instances 체인.
      4. ``pouInstance@typeName`` 이 실제 정의된 POU 를 가리킴(dangling 금지).
    """
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:  # well-formed 아님 → IDE 가 못 읽음
        raise ValueError(f"PLCopen XML 이 well-formed 가 아님: {exc}") from exc

    if root.tag != _q("project"):
        raise ValueError(f"루트가 project 가 아님: {root.tag}")
    for ns in (_TC6, _XHTML, _XSI):
        if ns not in xml:
            raise ValueError(f"namespace 선언 누락: {ns}")

    pous = root.findall(f"./{_q('types')}/{_q('pous')}/{_q('pou')}")
    if not pous:
        raise ValueError("types/pous/pou 구조 누락")
    pou_names = {p.get("name") for p in pous}
    for pou in pous:
        if pou.find(_q("interface")) is None:
            raise ValueError(f"pou '{pou.get('name')}' interface 누락")
        if pou.find(f"./{_q('body')}/{_q('ST')}") is None:
            raise ValueError(f"pou '{pou.get('name')}' body/ST 누락")

    if root.find(f"./{_q('instances')}/{_q('configurations')}/{_q('configuration')}") is None:
        raise ValueError("instances/configurations/configuration 누락")

    for inst in root.iter(_q("pouInstance")):
        if inst.get("typeName") not in pou_names:
            raise ValueError(
                f"pouInstance.typeName 이 미정의 POU 를 참조(dangling): "
                f"{inst.get('typeName')}"
            )


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
    """명세 + ST 를 완전한(runnable) PLCopen TC6 XML v2.01 문자열로 직렬화한다.

    OpenPLC Editor(Beremiz) 임포트가 요구하는 완전 프로젝트 구조:
      project(tc6_0201 + xhtml/xsi ns)
        ├ fileHeader(companyName/productName/productVersion/creationDateTime)
        ├ contentHeader(name) → coordinateInfo → fbd/ld/sfc/scaling
        ├ types → dataTypes / pous → pou(program) → interface + body(ST/CDATA)
        └ instances → configurations → configuration → resource
              → task(interval/priority) → pouInstance(name/typeName)

    creationDateTime 은 고정값(_FIXED_DATETIME)이라 동일 입력 → 바이트 동일.
    """
    ET.register_namespace("", _TC6)
    ET.register_namespace("xhtml", _XHTML)
    ET.register_namespace("xsi", _XSI)

    # 루트에 3개 네임스페이스 선언을 명시(Beremiz 가 xhtml/xsi 선언을 기대).
    project = ET.Element(
        _q("project"),
        {
            f"{{{_XSI}}}schemaLocation": (
                f"{_TC6} http://www.plcopen.org/xml/tc6_0201/tc6_0201.xsd"
            ),
        },
    )

    ET.SubElement(
        project,
        _q("fileHeader"),
        {
            "companyName": company,
            "productName": "PLC Ladder Agent",
            "productVersion": "1.0",
            "creationDateTime": _FIXED_DATETIME,
        },
    )
    content = ET.SubElement(
        project,
        _q("contentHeader"),
        {
            "name": spec.title or pou_name,
            "modificationDateTime": _FIXED_DATETIME,
        },
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

    # TC6 v2.01 interface 시퀀스 순서: localVars → inputVars → outputVars → ...
    # (타이머/카운터·비교기 플래그 등 지역 변수 먼저)
    # 비교기 플래그(PRESSURE_GE5 등)는 ST 본문에서 대입·참조되지만 입출력이 아닌
    # 내부 BOOL 신호다 — 선언하지 않으면 IDE 임포트가 "정의되지 않은 변수"로 깨진다.
    if spec.timers or spec.counters or spec.comparators:
        local_vars = ET.SubElement(interface, _q("localVars"))
        for t in spec.timers:
            _add_var(local_vars, t.name, DataType.TIME)
        for c in spec.counters:
            _add_var(local_vars, c.name, DataType.INT)
        for cmp in spec.comparators:
            _add_var(local_vars, cmp.flag, DataType.BOOL)
    if inputs:
        in_vars = ET.SubElement(interface, _q("inputVars"))
        for io in inputs:
            _add_var(in_vars, io.symbol, io.data_type)
    if outputs:
        out_vars = ET.SubElement(interface, _q("outputVars"))
        for io in outputs:
            _add_var(out_vars, io.symbol, io.data_type)

    body = ET.SubElement(pou, _q("body"))
    st_el = ET.SubElement(body, _q("ST"))
    # Beremiz 는 ST 바디를 xhtml:p + CDATA 로 기대한다.
    p_el = ET.SubElement(st_el, f"{{{_XHTML}}}p")
    p_el.text = _CDATA_OPEN + st_code + _CDATA_CLOSE

    # 완전한 instances → configurations → configuration → resource → task →
    # pouInstance. 이 블록이 있어야 컨트롤러에 올라가는 "runnable" 프로젝트가 된다.
    instances = ET.SubElement(project, _q("instances"))
    configurations = ET.SubElement(instances, _q("configurations"))
    configuration = ET.SubElement(
        configurations, _q("configuration"), {"name": "Config0"}
    )
    resource = ET.SubElement(configuration, _q("resource"), {"name": "Res0"})
    task = ET.SubElement(
        resource,
        _q("task"),
        {"name": "task0", "interval": "T#20ms", "priority": "0"},
    )
    ET.SubElement(
        task, _q("pouInstance"), {"name": "instance0", "typeName": pou_name}
    )

    ET.indent(project, space="  ")
    xml_bytes: bytes = ET.tostring(project, encoding="utf-8", xml_declaration=True)
    xml_str = xml_bytes.decode("utf-8")
    # 마커로 감싼 ST 블록을 실제 CDATA 로 복원한다. 내부 텍스트는 ElementTree 가
    # escape 했으므로 unescape 해 원문 ST 를 그대로 CDATA 안에 넣는다.
    def _to_cdata(m: re.Match[str]) -> str:
        return _wrap_cdata(_unescape(m.group(1)))

    xml_str = _CDATA_BLOCK_RE.sub(_to_cdata, xml_str)
    # 안전 경계 고지를 XML 주석으로 파일에 *내장*한다 — JSON 봉투는 PLC 툴체인으로
    # 들어가는 순간 사라지므로, 경계가 파일과 함께 컨트롤러까지 따라가게 한다(P0).
    notice = SAFETY_NOTICE.replace("--", "—")  # XML 주석엔 '--' 금지
    comment = f"<!-- ⚠ 안전 경계 / SAFETY BOUNDARY (ISO 13849/IEC 62061): {notice} -->\n"
    decl, sep, rest = xml_str.partition("\n")
    return f"{decl}{sep}{comment}{rest}" if sep else f"{comment}{xml_str}"
