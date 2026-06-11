"""순수 stdlib Modbus-TCP 어댑터 테스트 (로컬호스트만, 외부망/외부의존 없음)."""

from __future__ import annotations

import struct
from collections.abc import Iterator

import pytest

from app.comms import PlcLink, WriteRejected
from app.comms.modbus_tcp import (
    AddressMap,
    MockModbusServer,
    ModbusExceptionError,
    ModbusPlcLink,
    _ModbusTcp,
    pack_bits,
    unpack_bits,
)


# --------------------------------------------------------------------------- #
# 비트 패킹 단위 테스트 (LSB-first, 사양 §6.1/6.2)                              #
# --------------------------------------------------------------------------- #
def test_pack_bits_lsb_first_single_byte() -> None:
    # 첫 코일=bit0, 8번째 코일=bit7
    assert pack_bits([True]) == b"\x01"
    assert pack_bits([False, True]) == b"\x02"
    assert pack_bits([True] * 8) == b"\xff"
    # bit 7 (8번째)
    bits = [False] * 7 + [True]
    assert pack_bits(bits) == b"\x80"


def test_pack_bits_crosses_byte_boundary() -> None:
    # bit 8 (9번째)는 byte1 의 bit0
    bits = [False] * 8 + [True]
    assert pack_bits(bits) == b"\x00\x01"
    # bit 15 (16번째)는 byte1 의 bit7
    bits = [False] * 15 + [True]
    assert pack_bits(bits) == b"\x00\x80"


def test_pack_unpack_roundtrip_10_bits() -> None:
    pattern = [True, False, True, True, False, False, False, True, True, False]
    packed = pack_bits(pattern)
    assert len(packed) == 2  # 10비트 → 2바이트
    assert unpack_bits(packed, 10) == pattern


def test_pack_bits_deterministic() -> None:
    pattern = [True, False, True] * 5
    assert pack_bits(pattern) == pack_bits(pattern)


# --------------------------------------------------------------------------- #
# AddressMap                                                                   #
# --------------------------------------------------------------------------- #
def test_address_map_default_from_symbols_sorted() -> None:
    amap = AddressMap.default_from_symbols(["START", "STOP"], ["MOTOR", "LAMP"])
    # 정렬된 순서로 0부터 부여
    assert amap.inputs == {"START": 0, "STOP": 1}
    assert amap.outputs == {"LAMP": 0, "MOTOR": 1}
    assert amap.output_kind == "coil"


def test_address_map_discrete_output_kind() -> None:
    amap = AddressMap.default_from_symbols([], ["X"], output_kind="discrete")
    assert amap.output_kind == "discrete"


# --------------------------------------------------------------------------- #
# 라운드트립: ModbusPlcLink ↔ MockModbusServer                                 #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def server() -> Iterator[MockModbusServer]:
    srv = MockModbusServer()
    srv.start()
    yield srv
    srv.stop()


def test_roundtrip_write_then_read(server: MockModbusServer) -> None:
    amap = AddressMap.default_from_symbols(
        ["START", "STOP"], ["MOTOR", "LAMP"]
    )
    link = ModbusPlcLink(server.host, server.port, address_map=amap)
    try:
        assert isinstance(link, PlcLink)
        link.write_inputs({"START": True, "STOP": False})
        # 출력은 코일이므로 입력 쓰기가 출력 영역과 같은 코일 0/1 을 건드린다.
        out = link.read_outputs()
        # LAMP→coil0=START값, MOTOR→coil1=STOP값
        assert out == {"LAMP": True, "MOTOR": False}
    finally:
        link.close()


def test_roundtrip_multibit_byte_boundary(server: MockModbusServer) -> None:
    # 10개 코일을 입력/출력으로 동일 주소공간에 두고 바이트경계 교차 검증
    syms = [f"B{i}" for i in range(10)]
    amap = AddressMap(
        inputs={s: i for i, s in enumerate(syms)},
        outputs={s: i for i, s in enumerate(syms)},
        output_kind="coil",
    )
    link = ModbusPlcLink(server.host, server.port, address_map=amap)
    try:
        values = {f"B{i}": (i % 3 == 0) for i in range(10)}
        link.write_inputs(values)
        out = link.read_outputs()
        assert out == values
        # 직접 슬레이브 이미지 확인 (LSB-first 패킹이 올바른지)
        coils = server.image.read_coils(0, 10)
        assert coils == [values[f"B{i}"] for i in range(10)]
    finally:
        link.close()


def test_discrete_input_read(server: MockModbusServer) -> None:
    # 출력을 디스크리트 입력(FC02)로 읽도록 구성
    amap = AddressMap(outputs={"SENS": 5}, output_kind="discrete")
    # 슬레이브 디스크리트 입력 이미지 직접 세팅
    server.image.discrete[5] = 1
    link = ModbusPlcLink(server.host, server.port, address_map=amap)
    try:
        assert link.read_outputs() == {"SENS": True}
    finally:
        link.close()


def test_single_coil_write_fc05(server: MockModbusServer) -> None:
    # 단일 입력 → FC05 경로
    amap = AddressMap(inputs={"ONLY": 3}, outputs={"ONLY": 3})
    link = ModbusPlcLink(server.host, server.port, address_map=amap)
    try:
        link.write_inputs({"ONLY": True})
        assert server.image.read_coils(3, 1) == [True]
        assert link.read_outputs() == {"ONLY": True}
    finally:
        link.close()


def test_noncontiguous_inputs_use_fc05(server: MockModbusServer) -> None:
    amap = AddressMap(inputs={"A": 0, "B": 5}, outputs={"A": 0, "B": 5})
    link = ModbusPlcLink(server.host, server.port, address_map=amap)
    try:
        link.write_inputs({"A": True, "B": True})
        assert server.image.read_coils(0, 1) == [True]
        assert server.image.read_coils(5, 1) == [True]
        assert server.image.read_coils(1, 1) == [False]  # 사이는 안 건드림
    finally:
        link.close()


# --------------------------------------------------------------------------- #
# 예외/오류 처리                                                                #
# --------------------------------------------------------------------------- #
def test_illegal_address_raises_modbus_exception(server: MockModbusServer) -> None:
    client = _ModbusTcp(server.host, server.port)
    try:
        with pytest.raises(ModbusExceptionError) as ei:
            # 주소공간을 넘어서는 읽기 → ILLEGAL DATA ADDRESS (0x02)
            client.read_coils(65535, 10)
        assert ei.value.exception_code == 0x02
        assert "ILLEGAL DATA ADDRESS" in str(ei.value)
    finally:
        client.close()


def test_illegal_function_raises(server: MockModbusServer) -> None:
    client = _ModbusTcp(server.host, server.port)
    try:
        # FC03(holding registers) 미지원 → ILLEGAL FUNCTION (0x01)
        pdu = struct.pack(">BHH", 0x03, 0, 1)
        with pytest.raises(ModbusExceptionError) as ei:
            client._transaction(pdu)
        assert ei.value.exception_code == 0x01
    finally:
        client.close()


def test_write_unmapped_symbol_rejected(server: MockModbusServer) -> None:
    amap = AddressMap(inputs={"A": 0}, outputs={"A": 0})
    link = ModbusPlcLink(server.host, server.port, address_map=amap)
    try:
        with pytest.raises(WriteRejected) as ei:
            link.write_inputs({"GHOST": True})
        assert "GHOST" in str(ei.value)
    finally:
        link.close()


# --------------------------------------------------------------------------- #
# 트랜잭션 ID 증가 / close 멱등 / 결정론                                        #
# --------------------------------------------------------------------------- #
def test_transaction_id_increments(server: MockModbusServer) -> None:
    client = _ModbusTcp(server.host, server.port)
    try:
        client.write_coil(0, True)
        first = client._txn
        client.write_coil(0, False)
        second = client._txn
        client.read_coils(0, 1)
        third = client._txn
        assert second == first + 1
        assert third == second + 1
    finally:
        client.close()


def test_transaction_id_wraps() -> None:
    client = _ModbusTcp("127.0.0.1", 1)  # 연결 안 함
    client._txn = 0xFFFF
    assert client._next_txn() == 0x0000


def test_close_is_idempotent(server: MockModbusServer) -> None:
    link = ModbusPlcLink(
        server.host, server.port, address_map=AddressMap(outputs={"X": 0})
    )
    link.read_outputs()
    link.close()
    link.close()  # 두 번째도 안전
    link.close()


def test_determinism_same_ops_same_result(server: MockModbusServer) -> None:
    amap = AddressMap.default_from_symbols(
        [f"I{i}" for i in range(12)], [f"I{i}" for i in range(12)]
    )
    vals = {f"I{i}": (i % 2 == 0) for i in range(12)}
    results = []
    for _ in range(3):
        link = ModbusPlcLink(server.host, server.port, address_map=amap)
        link.write_inputs(vals)
        results.append(link.read_outputs())
        link.close()
    assert results[0] == results[1] == results[2] == vals


def test_pack_bits_determinism_byte_exact() -> None:
    # 동일 입력 → 바이트 동일 (framing 결정론)
    bits = [True, True, False, True, False, False, False, True, True]
    assert pack_bits(bits) == pack_bits(bits) == b"\x8b\x01"


def test_server_context_manager() -> None:
    with MockModbusServer() as srv:
        link = ModbusPlcLink(
            srv.host, srv.port, address_map=AddressMap(inputs={"A": 0}, outputs={"A": 0})
        )
        link.write_inputs({"A": True})
        assert link.read_outputs() == {"A": True}
        link.close()


def test_malformed_response_raises_modbus_error(monkeypatch) -> None:
    """악성/불량 PLC 응답(짧거나 byte_count 부족)이 raw 예외가 아닌 ModbusError 로(R7-P1)."""
    import pytest

    from app.comms.modbus_tcp import ModbusError, _ModbusTcp

    c = _ModbusTcp("127.0.0.1", 502)
    monkeypatch.setattr(c, "_transaction", lambda pdu: b"\x01")  # byte_count 없음
    with pytest.raises(ModbusError):
        c.read_coils(0, 16)
    monkeypatch.setattr(c, "_transaction", lambda pdu: b"\x01\x01\x00")  # 16비트인데 1바이트
    with pytest.raises(ModbusError):
        c.read_coils(0, 16)
    monkeypatch.setattr(c, "_transaction", lambda pdu: b"\x05\x00")  # write 에코 짧음
    with pytest.raises(ModbusError):
        c.write_coil(0, True)
    monkeypatch.setattr(c, "_transaction", lambda pdu: b"\x0f\x00\x00")  # write_coils 에코 짧음
    with pytest.raises(ModbusError):
        c.write_coils(0, [True, False])
