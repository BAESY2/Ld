"""PLCopen XML 익스포트(Phase N) 테스트.

생성 XML 이 잘 형성(well-formed)되고, POU/변수/ST 바디가 표준 구조로 들어가는지
검증한다.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from app.export import to_plcopen_xml
from app.models import DataType, IODirection, IOPoint, StateMachineSpec
from app.synth import synthesize_st

_TC6 = "http://www.plcopen.org/xml/tc6_0201"
_GOLDEN = Path(__file__).resolve().parent / "fixtures" / "golden"


def _q(tag: str) -> str:
    return f"{{{_TC6}}}{tag}"


_SPEC = StateMachineSpec(
    title="자기유지 테스트",
    io_points=[
        IOPoint(symbol="START", direction=IODirection.INPUT),
        IOPoint(symbol="STOP", direction=IODirection.INPUT),
        IOPoint(symbol="MOTOR", direction=IODirection.OUTPUT),
    ],
)
_ST = "MOTOR := (START OR MOTOR) AND NOT STOP;"


def test_xml_is_well_formed() -> None:
    xml = to_plcopen_xml(_SPEC, _ST)
    root = ET.fromstring(xml)  # 파싱 실패 시 예외
    assert root.tag == _q("project")


def test_pou_and_namespace() -> None:
    root = ET.fromstring(to_plcopen_xml(_SPEC, _ST))
    pou = root.find(f"./{_q('types')}/{_q('pous')}/{_q('pou')}")
    assert pou is not None
    assert pou.get("name") == "Main"
    assert pou.get("pouType") == "program"


def test_input_output_vars() -> None:
    root = ET.fromstring(to_plcopen_xml(_SPEC, _ST))
    iface = root.find(f".//{_q('interface')}")
    assert iface is not None
    in_names = {v.get("name") for v in iface.findall(f"./{_q('inputVars')}/{_q('variable')}")}
    out_names = {v.get("name") for v in iface.findall(f"./{_q('outputVars')}/{_q('variable')}")}
    assert in_names == {"START", "STOP"}
    assert out_names == {"MOTOR"}


def test_st_body_contains_code() -> None:
    root = ET.fromstring(to_plcopen_xml(_SPEC, _ST))
    xhtml = root.find(f".//{_q('body')}/{_q('ST')}/{{http://www.w3.org/1999/xhtml}}xhtml")
    assert xhtml is not None
    assert xhtml.text is not None and "MOTOR := (START OR MOTOR) AND NOT STOP;" in xhtml.text


def test_bool_type_emitted() -> None:
    root = ET.fromstring(to_plcopen_xml(_SPEC, _ST))
    var = root.find(f".//{_q('inputVars')}/{_q('variable')}")
    assert var is not None
    type_el = var.find(_q("type"))
    assert type_el is not None
    assert type_el.find(_q("BOOL")) is not None


def test_export_all_golden_well_formed() -> None:
    """모든 골든 명세의 합성 ST 가 well-formed PLCopen XML 로 나간다."""
    for path in sorted(_GOLDEN.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        spec = StateMachineSpec(**case["spec"])
        xml = to_plcopen_xml(spec, synthesize_st(spec))
        ET.fromstring(xml)  # 예외 없으면 통과


def test_timer_counter_local_vars() -> None:
    from app.models import CounterSpec, TimerSpec

    spec = StateMachineSpec(
        io_points=[IOPoint(symbol="OUT", direction=IODirection.OUTPUT)],
        timers=[TimerSpec(name="T1", preset_ms=1000)],
        counters=[CounterSpec(name="C1", preset=5)],
    )
    root = ET.fromstring(to_plcopen_xml(spec, "OUT := TRUE;"))
    local_names = {
        v.get("name")
        for v in root.findall(f".//{_q('localVars')}/{_q('variable')}")
    }
    assert {"T1", "C1"} <= local_names
    # 타이머는 TIME 타입
    for v in root.findall(f".//{_q('localVars')}/{_q('variable')}"):
        if v.get("name") == "T1":
            assert v.find(f"{_q('type')}/{_q('TIME')}") is not None


def test_data_type_mapping_int() -> None:
    spec = StateMachineSpec(
        io_points=[
            IOPoint(symbol="CNT", direction=IODirection.OUTPUT, data_type=DataType.INT)
        ]
    )
    root = ET.fromstring(to_plcopen_xml(spec, "CNT := 0;"))
    var = root.find(f".//{_q('outputVars')}/{_q('variable')}")
    assert var is not None
    assert var.find(f"{_q('type')}/{_q('INT')}") is not None
