"""PLCopen TC6-XML v2.01 익스포트 — Beremiz/OpenPLC 임포트 적합성 테스트.

검증 목표(연구 결과 기반):
  OpenPLC Editor(Beremiz)는 **완전한** PLCopen TC6-XML v2.01 프로젝트
  (namespace ``http://www.plcopen.org/xml/tc6_0201``)를 요구한다. 가장 흔한
  임포트 실패 원인은 (1) namespace/version 불일치, (2) configuration/resource/
  task 누락 등 불완전 프로젝트, (3) fileHeader 필수 속성 누락이다.

이 테스트는 우리가 내보내는 XML 이:
  (a) well-formed (xml.etree 파싱 성공)
  (b) tc6_0201 + xhtml + xsi namespace 선언
  (c) fileHeader 필수 속성 4종 + ISO 8601 형식
  (d) contentHeader/coordinateInfo(fbd/ld/sfc/scaling)
  (e) program POU + ST 바디 CDATA
  (f) configuration/resource/task/pouInstance (runnable)
  (g) 결정론적(동일 입력 → 바이트 동일, now() 미사용)
임을 보장한다.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

from app.export import infer_io_spec, to_plcopen_xml, validate_plcopen_xml
from app.models import (
    CounterSpec,
    IODirection,
    IOPoint,
    StateMachineSpec,
    TimerSpec,
)

_TC6 = "http://www.plcopen.org/xml/tc6_0201"
_XHTML = "http://www.w3.org/1999/xhtml"
_XSI = "http://www.w3.org/2001/XMLSchema-instance"

# ISO 8601 dateTime (xsd:dateTime) — YYYY-MM-DDThh:mm:ss[.fff][±zz:zz]
_ISO_DT = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:\d{2}|Z)?$"
)


def _q(tag: str) -> str:
    return f"{{{_TC6}}}{tag}"


_SPEC = StateMachineSpec(
    title="자기유지 테스트",
    io_points=[
        IOPoint(symbol="START", direction=IODirection.INPUT),
        IOPoint(symbol="STOP", direction=IODirection.INPUT),
        IOPoint(symbol="MOTOR", direction=IODirection.OUTPUT),
    ],
    timers=[TimerSpec(name="T1", preset_ms=1000)],
    counters=[CounterSpec(name="C1", preset=5)],
)
_ST = "MOTOR := (START OR MOTOR) AND NOT STOP;"


# ---------------------------------------------------------------------------
# (a) well-formed
# ---------------------------------------------------------------------------
def test_well_formed_and_root() -> None:
    root = ET.fromstring(to_plcopen_xml(_SPEC, _ST))
    assert root.tag == _q("project")


# ---------------------------------------------------------------------------
# (b) namespaces (tc6_0201 + xhtml + xsi)
# ---------------------------------------------------------------------------
def test_namespaces_declared() -> None:
    xml = to_plcopen_xml(_SPEC, _ST)
    assert f'xmlns="{_TC6}"' in xml
    assert f'xmlns:xhtml="{_XHTML}"' in xml
    assert f'xmlns:xsi="{_XSI}"' in xml


def test_version_is_0201_not_0101() -> None:
    # 가장 흔한 실패 원인: 0101 등 다른 버전 namespace.
    xml = to_plcopen_xml(_SPEC, _ST)
    assert "tc6_0201" in xml
    assert "tc6_0101" not in xml


# ---------------------------------------------------------------------------
# (c) fileHeader 필수 속성 + ISO 8601
# ---------------------------------------------------------------------------
def test_file_header_required_attrs() -> None:
    root = ET.fromstring(to_plcopen_xml(_SPEC, _ST))
    fh = root.find(_q("fileHeader"))
    assert fh is not None
    for attr in ("companyName", "productName", "productVersion", "creationDateTime"):
        val = fh.get(attr)
        assert val, f"fileHeader.{attr} 누락"
    assert _ISO_DT.match(fh.get("creationDateTime") or ""), "creationDateTime 형식 오류"


# ---------------------------------------------------------------------------
# (d) contentHeader / coordinateInfo
# ---------------------------------------------------------------------------
def test_content_header_and_coordinate_info() -> None:
    root = ET.fromstring(to_plcopen_xml(_SPEC, _ST))
    ch = root.find(_q("contentHeader"))
    assert ch is not None
    assert ch.get("name") == "자기유지 테스트"
    coord = ch.find(_q("coordinateInfo"))
    assert coord is not None
    for kind in ("fbd", "ld", "sfc"):
        k = coord.find(_q(kind))
        assert k is not None, f"coordinateInfo/{kind} 누락"
        scaling = k.find(_q("scaling"))
        assert scaling is not None
        assert scaling.get("x") and scaling.get("y")


# ---------------------------------------------------------------------------
# (e) program POU + ST 바디 CDATA
# ---------------------------------------------------------------------------
def test_program_pou_with_st_cdata() -> None:
    xml = to_plcopen_xml(_SPEC, _ST)
    root = ET.fromstring(xml)
    pou = root.find(f"./{_q('types')}/{_q('pous')}/{_q('pou')}")
    assert pou is not None
    assert pou.get("name") == "Main"
    assert pou.get("pouType") == "program"
    p = pou.find(f"./{_q('body')}/{_q('ST')}/{{{_XHTML}}}p")
    assert p is not None
    assert p.text is not None and _ST in p.text
    # 실제 CDATA 구문이 직렬화돼 있어야 한다(escape 된 텍스트 아님).
    assert "<![CDATA[" in xml and "]]>" in xml


def test_st_cdata_preserves_special_chars() -> None:
    # ST 에 < > & 가 있어도 CDATA 안에서 원문 그대로 보존돼야 한다.
    st = "Y := A < B AND C > D;  (* x & y *)"
    xml = to_plcopen_xml(_SPEC, st)
    ET.fromstring(xml)  # 여전히 well-formed
    assert "A < B AND C > D" in xml
    assert "x & y" in xml


def test_only_base_iec_types() -> None:
    root = ET.fromstring(to_plcopen_xml(_SPEC, _ST))
    allowed = {"BOOL", "INT", "DINT", "REAL", "TIME", "WORD"}
    for type_el in root.iter(_q("type")):
        for child in type_el:
            tag = child.tag.rsplit("}", 1)[-1]
            assert tag in allowed, f"비표준 타입: {tag}"


def test_var_list_order_localvars_first() -> None:
    # TC6 v2.01 interface 시퀀스: localVars → inputVars → outputVars.
    root = ET.fromstring(to_plcopen_xml(_SPEC, _ST))
    iface = root.find(f".//{_q('interface')}")
    assert iface is not None
    order = [c.tag.rsplit("}", 1)[-1] for c in iface]
    assert order == ["localVars", "inputVars", "outputVars"]
    in_names = {
        v.get("name") for v in iface.findall(f"./{_q('inputVars')}/{_q('variable')}")
    }
    out_names = {
        v.get("name") for v in iface.findall(f"./{_q('outputVars')}/{_q('variable')}")
    }
    assert in_names == {"START", "STOP"}
    assert out_names == {"MOTOR"}


# ---------------------------------------------------------------------------
# (f) configuration / resource / task / pouInstance (runnable project)
# ---------------------------------------------------------------------------
def test_complete_instances_configuration() -> None:
    root = ET.fromstring(to_plcopen_xml(_SPEC, _ST))
    config = root.find(
        f"./{_q('instances')}/{_q('configurations')}/{_q('configuration')}"
    )
    assert config is not None
    assert config.get("name")
    resource = config.find(_q("resource"))
    assert resource is not None
    assert resource.get("name")
    task = resource.find(_q("task"))
    assert task is not None
    assert task.get("name")
    assert task.get("interval")
    assert task.get("priority") is not None
    pou_inst = task.find(_q("pouInstance"))
    assert pou_inst is not None
    assert pou_inst.get("name")
    # pouInstance.typeName 은 실제 정의된 POU 를 가리켜야 한다(dangling reference 금지).
    assert pou_inst.get("typeName") == "Main"


def test_no_dangling_pou_reference() -> None:
    root = ET.fromstring(to_plcopen_xml(_SPEC, _ST))
    pou_names = {
        p.get("name")
        for p in root.findall(f"./{_q('types')}/{_q('pous')}/{_q('pou')}")
    }
    for inst in root.iter(_q("pouInstance")):
        assert inst.get("typeName") in pou_names


# ---------------------------------------------------------------------------
# (g) 결정론(동일 입력 → 바이트 동일)
# ---------------------------------------------------------------------------
def test_deterministic_byte_identical() -> None:
    a = to_plcopen_xml(_SPEC, _ST)
    b = to_plcopen_xml(_SPEC, _ST)
    assert a == b
    assert a.encode("utf-8") == b.encode("utf-8")


def test_no_runtime_now_in_source() -> None:
    # now() 를 쓰지 않음을 소스 수준에서도 못 박는다(회귀 방지).
    import inspect

    from app.export import plcopen

    src = inspect.getsource(plcopen)
    assert "datetime.now" not in src
    assert ".now()" not in src
    assert "import datetime" not in src and "from datetime" not in src


def test_fixed_timestamp() -> None:
    root = ET.fromstring(to_plcopen_xml(_SPEC, _ST))
    fh = root.find(_q("fileHeader"))
    assert fh is not None
    # 고정 타임스탬프여야 한다(현재 연도 의존 금지).
    assert fh.get("creationDateTime") == "2024-01-01T00:00:00"


def test_unique_pou_names() -> None:
    root = ET.fromstring(to_plcopen_xml(_SPEC, _ST))
    names = [
        p.get("name")
        for p in root.findall(f"./{_q('types')}/{_q('pous')}/{_q('pou')}")
    ]
    assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# 선택적 lxml 구조 검증(있으면 더 엄격하게, 없으면 skip 없이 통과)
# ---------------------------------------------------------------------------
def test_lxml_structural_if_available() -> None:
    try:
        from lxml import etree  # type: ignore[import-untyped]
    except ImportError:
        return  # heavy dep 추가 금지 — lxml 없으면 etree 기반 검증으로 충분.
    xml = to_plcopen_xml(_SPEC, _ST).encode("utf-8")
    root = etree.fromstring(xml)  # noqa: S320 (신뢰된 자체 생성 XML)
    nsmap = root.nsmap
    assert nsmap.get(None) == _TC6
    assert nsmap.get("xhtml") == _XHTML
    # 핵심 경로가 모두 존재.
    ns = {"p": _TC6, "x": _XHTML}
    assert root.findall(".//p:configuration", ns)
    assert root.findall(".//p:task", ns)
    assert root.findall(".//p:body/p:ST/x:p", ns)


# ---------------------------------------------------------------------------
# (h) minidom 으로도 파싱 가능(well-formed) — etree 외 두번째 파서로 교차검증
# ---------------------------------------------------------------------------
def test_minidom_parses_well_formed() -> None:
    from xml.dom import minidom

    xml = to_plcopen_xml(_SPEC, _ST)
    doc = minidom.parseString(xml)  # 깨지면 ExpatError → 테스트 실패
    assert doc.documentElement.tagName.endswith("project")


# ---------------------------------------------------------------------------
# (i) validate_plcopen_xml 헬퍼 — 정상 출력은 통과, 손상 입력은 ValueError
# ---------------------------------------------------------------------------
def test_validate_helper_accepts_export() -> None:
    validate_plcopen_xml(to_plcopen_xml(_SPEC, _ST))  # 예외 없으면 통과


def test_validate_helper_rejects_malformed() -> None:
    with pytest.raises(ValueError, match="well-formed"):
        validate_plcopen_xml("<project><unclosed>")


def test_validate_helper_rejects_wrong_root() -> None:
    with pytest.raises(ValueError, match="project 가 아님"):
        validate_plcopen_xml('<foo xmlns="bar"/>')


def test_validate_helper_rejects_dangling_pou_reference() -> None:
    # 정상 XML 에서 pouInstance.typeName 을 미정의 POU 로 바꾸면 거부돼야 한다.
    xml = to_plcopen_xml(_SPEC, _ST)
    broken = xml.replace('typeName="Main"', 'typeName="Ghost"')
    with pytest.raises(ValueError, match="dangling"):
        validate_plcopen_xml(broken)


# ---------------------------------------------------------------------------
# (j) ST 본문에 CDATA 종료 토큰 ``]]>`` 가 있어도 well-formed 유지(회귀 방지)
# ---------------------------------------------------------------------------
def test_st_with_cdata_terminator_stays_well_formed() -> None:
    # ``]]>`` 는 CDATA 섹션을 조기 종료시켜 과거 XML 을 깨뜨렸다(버그).
    st = "X := Y;  (* 주석에 ]]> 종료토큰 포함 *)"
    xml = to_plcopen_xml(_SPEC, st)
    # 두 파서 모두 well-formed 로 받아들여야 한다.
    ET.fromstring(xml)
    from xml.dom import minidom

    minidom.parseString(xml)
    validate_plcopen_xml(xml)
    # 본문 텍스트는 보존(쪼개진 CDATA 너머로 합쳐 읽으면 원문).
    root = ET.fromstring(xml)
    p = root.find(f".//{{{_XHTML}}}p")
    assert p is not None and p.text is not None
    assert "종료토큰" in p.text


# ---------------------------------------------------------------------------
# (k) infer_io_spec 추론 변수가 interface 에 빠짐없이 선언되는지(라운드트립)
#     누락되면 IDE 임포트가 "정의되지 않은 변수" 로 깨진다.
# ---------------------------------------------------------------------------
def _declared_var_names(root: ET.Element) -> dict[str, set[str]]:
    iface = root.find(f".//{_q('interface')}")
    assert iface is not None
    out: dict[str, set[str]] = {}
    for vl in iface:
        kind = vl.tag.rsplit("}", 1)[-1]
        out[kind] = {
            v.get("name") or "" for v in vl.findall(_q("variable"))
        }
    return out


def test_infer_io_roundtrip_declares_all_vars() -> None:
    st = (
        "MOTOR := (START OR MOTOR) AND NOT STOP;\n"
        "LAMP := MOTOR AND ENABLE;\n"
    )
    spec = infer_io_spec(st, title="추론")
    xml = to_plcopen_xml(spec, st)
    validate_plcopen_xml(xml)
    root = ET.fromstring(xml)
    declared = _declared_var_names(root)
    all_declared = set().union(*declared.values()) if declared else set()

    inputs = {p.symbol for p in spec.io_points if p.direction == IODirection.INPUT}
    outputs = {p.symbol for p in spec.io_points if p.direction == IODirection.OUTPUT}

    # 추론된 입력/출력이 정확히 inputVars/outputVars 에 분류돼 선언돼야 한다.
    assert declared.get("inputVars", set()) == inputs
    assert declared.get("outputVars", set()) == outputs
    # 어떤 추론 변수도 XML 에서 누락되면 안 된다.
    inferred = {p.symbol for p in spec.io_points}
    assert inferred <= all_declared, f"interface 에 누락된 변수: {inferred - all_declared}"


def test_infer_io_selfheld_output_not_duplicated_as_input() -> None:
    # 자기유지: MOTOR 가 RHS 에도 있지만 출력일 뿐 입력으로 중복 선언되면 안 됨.
    st = "MOTOR := (START OR MOTOR) AND NOT STOP;"
    spec = infer_io_spec(st)
    xml = to_plcopen_xml(spec, st)
    root = ET.fromstring(xml)
    declared = _declared_var_names(root)
    assert "MOTOR" in declared.get("outputVars", set())
    assert "MOTOR" not in declared.get("inputVars", set())


def test_special_chars_escaped_and_well_formed() -> None:
    # ST 에 < > & 가 있어도 (CDATA 로) 깨지지 않고 원문 보존 + 두 파서 모두 통과.
    st = "Y := A < B AND C > D;  (* x & y && z *)"
    spec = StateMachineSpec(
        title="특수문자",
        io_points=[
            IOPoint(symbol="A", direction=IODirection.INPUT),
            IOPoint(symbol="Y", direction=IODirection.OUTPUT),
        ],
    )
    xml = to_plcopen_xml(spec, st)
    ET.fromstring(xml)
    from xml.dom import minidom

    minidom.parseString(xml)
    assert "A < B AND C > D" in xml
    assert "x & y && z" in xml
