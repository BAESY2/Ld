"""Stage 3 엔드투엔드 통합 — 자연어 설계가 안전커널을 거쳐 (가상)PLC를 구동한다.

전 구간 체인을 실제 Modbus-TCP 프레이밍으로 잇는다:
    build_spec(자연어 레시피) → SafetyKernel(쓰기 전 검증)
        → ModbusPlcLink(순수 stdlib Modbus 마스터) → MockModbusServer(가상 PLC).
안전 명령은 끝까지 전달되고, 위험/미지 명령은 전송 *전에* 차단됨을 확인한다.
"""

from __future__ import annotations

import pytest

from app.comms import WriteRejected
from app.comms.modbus_tcp import AddressMap, ModbusPlcLink, MockModbusServer
from app.comms.safety_kernel import SafetyKernel
from app.models import IODirection
from app.wizard import build_spec


def _io(spec: object) -> tuple[list[str], list[str]]:
    pts = spec.io_points  # type: ignore[attr-defined]
    ins = sorted(p.symbol for p in pts if p.direction == IODirection.INPUT)
    outs = sorted(p.symbol for p in pts if p.direction == IODirection.OUTPUT)
    return ins, outs


def test_safe_command_traverses_full_chain_to_virtual_plc() -> None:
    """안전한 입력 명령이 커널→Modbus→가상 PLC 코일까지 실제로 도달한다."""
    spec = build_spec("fwd_rev")
    ins, outs = _io(spec)
    amap = AddressMap.default_from_symbols(ins, outs)
    with MockModbusServer() as srv:
        link = ModbusPlcLink(srv.host, srv.port, address_map=amap)
        kernel = SafetyKernel(link, spec)
        target = ins[0]
        kernel.write_inputs({target: True})
        # 실제 Modbus 프레임이 가상 슬레이브의 해당 코일을 세팅했다
        assert srv.image.coils[amap.inputs[target]] == 1
        assert any(a.decision == "ALLOW" for a in kernel.audit)
        link.close()


def test_unknown_symbol_blocked_before_reaching_plc() -> None:
    """미지 심볼 명령은 안전커널이 전송 전에 차단 → 가상 PLC 이미지 불변."""
    spec = build_spec("fwd_rev")
    ins, outs = _io(spec)
    amap = AddressMap.default_from_symbols(ins, outs)
    with MockModbusServer() as srv:
        link = ModbusPlcLink(srv.host, srv.port, address_map=amap)
        kernel = SafetyKernel(link, spec)
        before = bytes(srv.image.coils[:32])
        with pytest.raises(WriteRejected):
            kernel.write_inputs({"HACK_RELAY": True})
        assert bytes(srv.image.coils[:32]) == before  # 전송조차 안 됨
        assert any(a.decision == "DENY" for a in kernel.audit)
        link.close()


def test_read_path_delegates_through_chain() -> None:
    """읽기 경로(커널→Modbus→가상 PLC)가 출력 심볼 맵으로 디맵되어 돌아온다."""
    spec = build_spec("motor_start_stop")
    ins, outs = _io(spec)
    amap = AddressMap.default_from_symbols(ins, outs)
    with MockModbusServer() as srv:
        link = ModbusPlcLink(srv.host, srv.port, address_map=amap)
        kernel = SafetyKernel(link, spec)
        result = kernel.read_outputs()
        assert set(result) == set(outs)  # 모든 출력 심볼이 디맵됨
        assert all(v is False for v in result.values())  # 목은 로직 미실행 → 전부 OFF
        link.close()
