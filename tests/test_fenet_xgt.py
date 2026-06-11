"""순수 stdlib LS XGT FEnet 어댑터 테스트 (로컬호스트만, 외부망/외부의존 없음)."""

from __future__ import annotations

import socket
import struct
from collections.abc import Iterator

import pytest

from app.comms.fenet_xgt import (
    CMD_READ_REQ,
    CMD_WRITE_REQ,
    COMPANY_ID,
    DT_BIT,
    HEADER_LEN,
    SRC_CLIENT,
    SRC_SERVER,
    FenetMap,
    FenetNakError,
    FenetPlcLink,
    MockFenetServer,
    bcc,
    build_header,
    build_read_request,
    build_write_request,
    frame,
    parse_header,
)
from app.comms.protocols import PlcLink, WriteRejected


# --------------------------------------------------------------------------- #
# 헤더 바이트 정확성 (LSIS-XGT, BCC, invoke id, length)                          #
# --------------------------------------------------------------------------- #
def test_header_layout_byte_exact() -> None:
    head = build_header(payload_len=0x0010, invoke_id=0x0102, source=SRC_CLIENT)
    assert len(head) == HEADER_LEN == 20
    assert head[:8] == COMPANY_ID == b"LSIS-XGT"
    assert head[8:10] == b"\x00\x00"  # PLC info
    assert head[12] == 0x00  # CPU info
    assert head[13] == SRC_CLIENT == 0x33  # source of frame
    assert head[14:16] == struct.pack("<H", 0x0102)  # invoke id (LE)
    assert head[16:18] == struct.pack("<H", 0x0010)  # length (LE)
    assert head[18] == 0x00  # FEnet position


def test_bcc_is_sum_of_first_19_bytes() -> None:
    head = build_header(payload_len=5, invoke_id=7, source=SRC_CLIENT)
    assert head[19] == bcc(head[:19])
    assert head[19] == sum(head[:19]) & 0xFF


def test_parse_header_roundtrip() -> None:
    head = build_header(payload_len=42, invoke_id=999, source=SRC_SERVER)
    source, invoke, length = parse_header(head)
    assert (source, invoke, length) == (SRC_SERVER, 999, 42)


def test_parse_header_rejects_bad_company_id() -> None:
    head = bytearray(build_header(1, 1))
    head[0] = ord("X")
    with pytest.raises(Exception, match="company"):
        parse_header(bytes(head))


def test_parse_header_rejects_bad_bcc() -> None:
    head = bytearray(build_header(1, 1))
    head[19] ^= 0xFF
    with pytest.raises(Exception, match="BCC"):
        parse_header(bytes(head))


# --------------------------------------------------------------------------- #
# 명령프레임 바이트 정확성                                                       #
# --------------------------------------------------------------------------- #
def test_build_read_request_bytes() -> None:
    body = build_read_request(DT_BIT, ["%MX0"])
    # command(2) dtype(2) reserved(2) blockcnt(2) namelen(2) name
    assert body[0:2] == struct.pack("<H", CMD_READ_REQ)
    assert body[2:4] == struct.pack("<H", DT_BIT)
    assert body[4:6] == b"\x00\x00"  # reserved
    assert body[6:8] == struct.pack("<H", 1)  # block count
    assert body[8:10] == struct.pack("<H", len("%MX0"))
    assert body[10:] == b"%MX0"


def test_build_write_request_bytes() -> None:
    body = build_write_request(DT_BIT, [("%MX5", b"\x01")])
    assert body[0:2] == struct.pack("<H", CMD_WRITE_REQ)
    assert body[2:4] == struct.pack("<H", DT_BIT)
    assert body[6:8] == struct.pack("<H", 1)  # block count
    name = "%MX5".encode("ascii")
    assert body[8:10] == struct.pack("<H", len(name))
    assert body[10 : 10 + len(name)] == name
    rest = body[10 + len(name) :]
    assert rest[0:2] == struct.pack("<H", 1)  # data count
    assert rest[2:3] == b"\x01"  # data


def test_frame_prepends_header_with_correct_length() -> None:
    body = build_read_request(DT_BIT, ["%MX0"])
    adu = frame(body, invoke_id=3, source=SRC_CLIENT)
    assert adu[:HEADER_LEN] == build_header(len(body), 3, source=SRC_CLIENT)
    assert adu[HEADER_LEN:] == body
    _src, _inv, length = parse_header(adu[:HEADER_LEN])
    assert length == len(body)


def test_determinism_same_ops_same_bytes() -> None:
    a = frame(build_write_request(DT_BIT, [("%MX0", b"\x01")]), invoke_id=1)
    b = frame(build_write_request(DT_BIT, [("%MX0", b"\x01")]), invoke_id=1)
    assert a == b


# --------------------------------------------------------------------------- #
# FenetMap                                                                      #
# --------------------------------------------------------------------------- #
def test_fenet_map_default_from_symbols_sorted() -> None:
    fmap = FenetMap.default_from_symbols(["START", "STOP"], ["MOTOR", "LAMP"])
    # 입력은 %MX0 부터, 출력은 %MX16 부터, 정렬된 순서
    assert fmap.inputs == {"START": "%MX0", "STOP": "%MX1"}
    assert fmap.outputs == {"LAMP": "%MX16", "MOTOR": "%MX17"}


def test_fenet_map_configurable_base() -> None:
    fmap = FenetMap.default_from_symbols(
        ["A"], ["B"], input_base=100, output_base=200
    )
    assert fmap.inputs == {"A": "%MX100"}
    assert fmap.outputs == {"B": "%MX200"}


# --------------------------------------------------------------------------- #
# 라운드트립: FenetPlcLink ↔ MockFenetServer                                    #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def server() -> Iterator[MockFenetServer]:
    with MockFenetServer() as srv:
        yield srv


def _make_link(server: MockFenetServer, fmap: FenetMap) -> FenetPlcLink:
    return FenetPlcLink(server.host, server.port, fenet_map=fmap, timeout=3.0)


def test_satisfies_plclink_protocol(server: MockFenetServer) -> None:
    link = _make_link(server, FenetMap())
    assert isinstance(link, PlcLink)
    link.close()


def test_write_inputs_then_read_outputs_roundtrip(server: MockFenetServer) -> None:
    fmap = FenetMap(
        inputs={"START": "%MX0", "STOP": "%MX1"},
        outputs={"MOTOR": "%MX0", "STOP_OUT": "%MX1"},
    )
    link = _make_link(server, fmap)
    try:
        link.write_inputs({"START": True, "STOP": False})
        out = link.read_outputs()
        assert out == {"MOTOR": True, "STOP_OUT": False}
        # 토글
        link.write_inputs({"START": False})
        assert link.read_outputs()["MOTOR"] is False
    finally:
        link.close()


def test_read_outputs_empty_map_returns_empty(server: MockFenetServer) -> None:
    link = _make_link(server, FenetMap())
    try:
        assert link.read_outputs() == {}
    finally:
        link.close()


def test_invoke_id_increments_across_transactions(server: MockFenetServer) -> None:
    fmap = FenetMap(inputs={"A": "%MX0"}, outputs={"A": "%MX0"})
    link = _make_link(server, fmap)
    try:
        link.write_inputs({"A": True})
        link.read_outputs()
        # 내부 invoke id 가 트랜잭션마다 증가했는지
        assert link._client._invoke == 2  # type: ignore[attr-defined]
    finally:
        link.close()


# --------------------------------------------------------------------------- #
# 미매핑 심볼 거부                                                              #
# --------------------------------------------------------------------------- #
def test_unmapped_symbol_rejected(server: MockFenetServer) -> None:
    fmap = FenetMap(inputs={"START": "%MX0"})
    link = _make_link(server, fmap)
    try:
        with pytest.raises(WriteRejected, match="GHOST"):
            link.write_inputs({"START": True, "GHOST": True})
    finally:
        link.close()


def test_empty_write_is_noop(server: MockFenetServer) -> None:
    link = _make_link(server, FenetMap())
    try:
        link.write_inputs({})  # 거부되지 않아야 함
    finally:
        link.close()


# --------------------------------------------------------------------------- #
# 워드 읽기/쓰기 라운드트립                                                      #
# --------------------------------------------------------------------------- #
def test_word_read_write_roundtrip(server: MockFenetServer) -> None:
    client = FenetPlcLink(server.host, server.port)._client  # type: ignore[attr-defined]
    try:
        client.write_word("%MW10", 0xBEEF)
        assert client.read_words(["%MW10"]) == [0xBEEF]
    finally:
        client.close()


# --------------------------------------------------------------------------- #
# NAK/에러 처리                                                                 #
# --------------------------------------------------------------------------- #
class _NakServer(MockFenetServer):
    """항상 error state != 0 응답을 반환하는 서버(테스트용)."""

    pass


def test_nak_error_raised_on_unsupported_command() -> None:
    # 클라이언트가 미지원 데이터타입을 보내면 서버가 error state 를 세팅 → NAK.
    with MockFenetServer() as srv:
        client = FenetPlcLink(srv.host, srv.port)._client  # type: ignore[attr-defined]
        try:
            with pytest.raises(FenetNakError) as ei:
                # DWORD 읽기는 mock 서버가 미지원 → error state 0x0011
                client.read_words.__self__._transaction(  # type: ignore[attr-defined]
                    build_read_request(0x0003, ["%MD0"])
                )
            assert ei.value.error_state != 0
        finally:
            client.close()


def test_nak_error_message_contains_hex() -> None:
    err = FenetNakError(0x0011, CMD_READ_REQ)
    assert "0x0011" in str(err)
    assert err.error_state == 0x0011


# --------------------------------------------------------------------------- #
# close 멱등성                                                                  #
# --------------------------------------------------------------------------- #
def test_close_is_idempotent(server: MockFenetServer) -> None:
    link = _make_link(server, FenetMap(inputs={"A": "%MX0"}))
    link.write_inputs({"A": True})
    link.close()
    link.close()  # 두 번째 close 도 예외 없이


def test_close_before_any_io_is_safe(server: MockFenetServer) -> None:
    link = _make_link(server, FenetMap())
    link.close()  # 소켓이 아직 없어도 안전


# --------------------------------------------------------------------------- #
# 서버 동작 확인(직접 소켓)                                                      #
# --------------------------------------------------------------------------- #
def test_server_echoes_invoke_id_and_source(server: MockFenetServer) -> None:
    body = build_read_request(DT_BIT, ["%MX0"])
    sock = socket.create_connection((server.host, server.port), timeout=3.0)
    try:
        sock.sendall(frame(body, invoke_id=0x1234, source=SRC_CLIENT))
        head = sock.recv(HEADER_LEN)
        source, invoke, length = parse_header(head)
        assert source == SRC_SERVER
        assert invoke == 0x1234
        assert length > 0
    finally:
        sock.close()


def test_short_read_body_raises_fenet_error(monkeypatch) -> None:
    """짧은 읽기 바디(블록카운트 미만)가 struct.error 가 아닌 FenetError 로(R7-P1)."""
    import pytest

    from app.comms.fenet_xgt import FenetError, _FenetClient

    c = _FenetClient("127.0.0.1", 2004)
    monkeypatch.setattr(c, "_transaction", lambda payload: b"\x55\x00\x00\x00\x00\x00")
    with pytest.raises(FenetError):
        c.read_bits(["%MX0", "%MX1"])
