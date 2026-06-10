"""명세 → 3D 설비 배치도 컴파일러 테스트 (결정론·종류추론·탱크/계기 합성)."""

from __future__ import annotations

from app.compile_frame import frame_to_spec
from app.plant import input_kind, output_kind, plant_from_spec
from app.wizard import build_spec


def _by_symbol(layout, symbol):  # type: ignore[no-untyped-def]
    return next(d for d in layout.devices if d.symbol == symbol)


def test_output_kind_inference() -> None:
    assert output_kind("MOTOR") == "motor"
    assert output_kind("MOTOR2") == "motor"      # 다중 인스턴스도 같은 종류
    assert output_kind("PUMP1") == "pump"
    assert output_kind("VALVE") == "valve"
    assert output_kind("BEACON") == "beacon"
    assert output_kind("CONVEYOR") == "conveyor"
    assert output_kind("EJECT") == "ejector"
    assert output_kind("XYZZY") == "actuator"    # 미지정은 일반 구동기


def test_input_kind_inference() -> None:
    assert input_kind("START") == "button"
    assert input_kind("ESTOP") == "estop"        # 비상정지가 버튼보다 우선
    assert input_kind("LO_LS") == "level"
    assert input_kind("FAULT") == "fault"
    assert input_kind("PROX1") == "sensor"


def test_motor_recipe_layout() -> None:
    """모터 기동/정지 — 모터 1대(중앙열) + 버튼 2개(조작반열)."""
    layout = plant_from_spec(build_spec("motor_start_stop"))
    motor = _by_symbol(layout, "MOTOR")
    assert motor.kind == "motor" and motor.role == "output" and motor.z == 0.0
    start = _by_symbol(layout, "START")
    assert start.kind == "button" and start.role == "input" and start.z > 0
    assert "모터" in motor.label


def test_hysteresis_pump_gets_tank() -> None:
    """수위 신호(저/고수위) → 탱크가 서고, 펌프가 탱크를 채우는 연결이 생긴다."""
    r = frame_to_spec("저수위 되면 펌프 켜고 고수위 되면 펌프 꺼")
    layout = plant_from_spec(r.spec)
    tank = _by_symbol(layout, "TANK")
    assert tank.kind == "tank" and tank.z < 0
    assert "PUMP" in tank.fed_by
    lo = _by_symbol(layout, "LO_LS")
    assert lo.kind == "level"


def test_analog_comparators_become_gauges() -> None:
    """압력/온도 비교기 → 신호별 계기(임계값 정렬 포함)."""
    r = frame_to_spec("압력 5바 넘으면 밸브 닫고 온도 200도 되면 히터 꺼")
    layout = plant_from_spec(r.spec)
    gauges = {d.symbol: d for d in layout.devices if d.kind == "gauge"}
    assert set(gauges) == {"PRESSURE", "TEMP"}
    assert gauges["PRESSURE"].thresholds == [5.0]
    assert gauges["TEMP"].thresholds == [200.0]


def test_sequence_devices_spread_on_floor() -> None:
    """시퀀서 3기기 — 서로 다른 x 에 결정론 배치(겹침 0)."""
    r = frame_to_spec("모터 돌리고 다음 펌프 켜고 다음 밸브 열어")
    layout = plant_from_spec(r.spec)
    outs = [d for d in layout.devices if d.role == "output"]
    xs = [d.x for d in outs]
    assert len(outs) == 3 and len(set(xs)) == 3
    assert layout.floor_w >= max(abs(x) for x in xs) * 2


def test_layout_is_deterministic() -> None:
    text = "저수위 되면 펌프 켜고 고수위 되면 펌프 끄고 고장 나면 경광등 켜"
    a = plant_from_spec(frame_to_spec(text).spec)
    b = plant_from_spec(frame_to_spec(text).spec)
    assert a.model_dump() == b.model_dump()


def test_cad_tags_are_unique_and_kind_prefixed() -> None:
    """CAD 태그번호 — 종류별 접두(P-/M-/TK-/PT-)·전 기기 고유(도면 식별자)."""
    r = frame_to_spec("저수위 되면 펌프 켜고 고수위 되면 펌프 끄고 고장 나면 경광등 켜")
    layout = plant_from_spec(r.spec)
    tags = [d.tag for d in layout.devices]
    assert all(tags), "모든 기기에 태그가 있어야 한다"
    assert len(set(tags)) == len(tags), "태그는 고유해야 한다"
    assert _by_symbol(layout, "PUMP").tag.startswith("P-")
    assert _by_symbol(layout, "TANK").tag.startswith("TK-")
    assert _by_symbol(layout, "BEACON").tag.startswith("XL-")


def test_gauge_tag_follows_isa_letter() -> None:
    """계기 태그 — 압력 PT-, 온도 TT-(ISA 계열 문자)."""
    r = frame_to_spec("압력 5바 넘으면 밸브 닫고 온도 200도 되면 히터 꺼")
    layout = plant_from_spec(r.spec)
    assert _by_symbol(layout, "PRESSURE").tag.startswith("PT-")
    assert _by_symbol(layout, "TEMP").tag.startswith("TT-")


def test_bom_parts_per_device() -> None:
    """설계 세분화 — 기기마다 부품 명세(BOM)가 붙는다(모터→접촉기/EOCR…)."""
    layout = plant_from_spec(build_spec("motor_start_stop"))
    motor = _by_symbol(layout, "MOTOR")
    assert any("전자접촉기" in p for p in motor.parts)
    assert any("열동계전기" in p for p in motor.parts)
    start = _by_symbol(layout, "START")
    assert any("푸시버튼" in p for p in start.parts)


def test_motor_family_power_chain_complete() -> None:
    """전동기 계열 BOM 에 동력 체인 전부(MCCB·인버터·MC·EOCR) — 제어반 단선도의 원천."""
    layout = plant_from_spec(frame_to_spec("펌프 켜고 컨베이어 돌려").spec)
    for sym in ("PUMP", "CONVEYOR"):
        parts = " ".join(_by_symbol(layout, sym).parts)
        for comp in ("MCCB", "인버터", "전자접촉기", "열동계전기"):
            assert comp in parts, f"{sym} BOM 에 {comp} 누락"


def test_plc_addresses_assigned_to_io() -> None:
    """IO 기기에 LS 디바이스 주소(P…)가 결정론 부여된다(탱크는 IO 아님→빈 값)."""
    r = frame_to_spec("저수위 되면 펌프 켜고 고수위 되면 펌프 꺼")
    layout = plant_from_spec(r.spec)
    assert _by_symbol(layout, "PUMP").address.startswith("P")
    assert _by_symbol(layout, "LO_LS").address.startswith("P")
    assert _by_symbol(layout, "TANK").address == ""


def test_connections_pipe_and_signal() -> None:
    """연결 컴파일 — 펌프→탱크 배관, 입력→PLC·PLC→구동기 신호선."""
    r = frame_to_spec("저수위 되면 펌프 켜고 고수위 되면 펌프 꺼")
    layout = plant_from_spec(r.spec)
    kinds = {(c.src, c.dst, c.kind) for c in layout.connections}
    assert ("PUMP", "TANK", "pipe") in kinds
    assert ("PLC", "PUMP", "signal") in kinds
    assert ("LO_LS", "PLC", "signal") in kinds


def test_robot_and_vision_devices() -> None:
    """다관절 로봇(출력)·비전 카메라(검출 입력)가 종류·태그로 선다."""
    r = frame_to_spec("불량 나면 로봇 켜고 배출해")
    layout = plant_from_spec(r.spec)
    robot = _by_symbol(layout, "ROBOT")
    assert robot.kind == "robot" and robot.tag.startswith("RB-")
    assert any("다관절" in p for p in robot.parts)
    ng = _by_symbol(layout, "NG_SENSOR")
    assert ng.kind == "vision" and ng.tag.startswith("VS-")
