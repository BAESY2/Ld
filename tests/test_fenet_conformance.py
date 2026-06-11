"""LS XGT FEnet 와이어포맷 바이트정밀 적합성(conformance) 핀.

목적: 어댑터(app.comms.fenet_xgt)가 내보내는 프레임 바이트를 **권위 1차 출처**의
문서화된 바이트열에 못박아(pin) 회귀를 막는다.

엔디언 정형 결론(전 필드 little-endian, 헤더·명령블록 모두 LE):
  * LS ELECTRIC 공식 *XGB FEnet I/F Module User's Manual*(XBL-EMTA), Ch.5.2
    "Frame examples — Request frame for individual reading of variables" 의
    워크드 예제가 와이어 바이트를 직접 보여준다:
        Command 0x54 0x00 / Block No. 0x01 0x00 / Variable Length 0x04 0x00
    → Command(0x0054)/Block(1)/VarLen(4) 모두 저위바이트 선행 = LE.
    명령코드 표도 Read-Req 를 와이어형 "0x5400"(= `54 00`)로 표기.
  * Wireshark 디섹터 ciaoly/PLC-XGT-protocol-for-Wireshark/xgb.lua:
    Invoke ID/Length 포함 모든 멀티바이트 필드를 ``add_le`` 로 읽음(헤더도 LE).
  * golanglsplc song9063/golanglsplc/lsplc.go makeHeader:
    ``bytes[15], bytes[14] = get2BytesFromInt(invokeId)`` 에서
    ``get2BytesFromInt -> (hi, lo)`` → bytes[14]=lo(저위)가 낮은 오프셋 = LE.

아래 ``_EXPECTED_*`` 상수는 위 출처에서 직접 베껴 하드코딩한 기대 바이트열이다.
어댑터 산출물이 이 상수와 정확히 일치해야 하며, MockFenetServer 와 라운드트립도
검증한다. (외부망/외부의존 없음: localhost 목서버만 사용.)
"""

from __future__ import annotations

import socket
import struct
from collections.abc import Iterator

import pytest

from app.comms.fenet_xgt import (
    DT_BIT,
    DT_WORD,
    HEADER_LEN,
    FenetMap,
    FenetPlcLink,
    MockFenetServer,
    bcc,
    build_header,
    build_read_request,
    build_write_request,
    frame,
    parse_header,
)

# --------------------------------------------------------------------------- #
# 권위 출처에서 직접 베낀 기대 바이트열 (명령블록, 헤더 제외)                     #
# --------------------------------------------------------------------------- #
# (1) 비트 읽기 %MX0 — LS 매뉴얼 Ch.5.2 워크드 예제의 명령블록.
#     54 00 | 00 00 | 00 00 | 01 00 | 04 00 | 25 4D 58 30
#     Command=0x0054 | DataType=0x0000(BIT) | Reserved | Block=1 | VarLen=4 | "%MX0"
_EXPECTED_READ_BIT_MX0 = bytes.fromhex("54 00 00 00 00 00 01 00 04 00 25 4D 58 30".replace(" ", ""))

# (2) 워드 쓰기 %MW100=1 — docs 브리프가 인용한 LS 예제와 동일 레이아웃.
#     58 00 | 02 00 | 00 00 | 01 00 | 06 00 | 25 4D 57 31 30 30 | 02 00 | 01 00
#     Command=0x0058(write) | DataType=0x0002(WORD) | Reserved | Block=1 |
#     VarLen=6 | "%MW100" | DataCnt=2 | Data=0x0001(LE)
_EXPECTED_WRITE_WORD_MW100_1 = bytes.fromhex(
    "58 00 02 00 00 00 01 00 06 00 25 4D 57 31 30 30 02 00 01 00".replace(" ", "")
)

# (3) 워드 읽기 %MW100 — 동일 레이아웃(데이터 없음).
#     54 00 | 02 00 | 00 00 | 01 00 | 06 00 | 25 4D 57 31 30 30
_EXPECTED_READ_WORD_MW100 = bytes.fromhex(
    "54 00 02 00 00 00 01 00 06 00 25 4D 57 31 30 30".replace(" ", "")
)

# 검산: ASCII 디바이스 이름 바이트가 실제로 "%MX0"/"%MW100" 인지.
assert _EXPECTED_READ_BIT_MX0[10:] == b"%MX0"
assert _EXPECTED_WRITE_WORD_MW100_1[10:16] == b"%MW100"
assert _EXPECTED_READ_WORD_MW100[10:] == b"%MW100"


# --------------------------------------------------------------------------- #
# 명령블록 바이트정밀 핀                                                         #
# --------------------------------------------------------------------------- #
def test_read_bit_mx0_matches_ls_manual_example() -> None:
    """비트 읽기 %MX0 명령블록이 LS 매뉴얼 Ch.5.2 예제와 바이트 일치."""
    body = build_read_request(DT_BIT, ["%MX0"])
    assert body == _EXPECTED_READ_BIT_MX0
    # 길이 0x0E(=14) 도 매뉴얼 예제와 일치.
    assert len(body) == 0x0E


def test_write_word_mw100_matches_documented_example() -> None:
    """워드 쓰기 %MW100=1 명령블록이 문서화된 예제와 바이트 일치."""
    body = build_write_request(DT_WORD, [("%MW100", struct.pack("<H", 1))])
    assert body == _EXPECTED_WRITE_WORD_MW100_1
    assert len(body) == 0x14  # =20


def test_read_word_mw100_byte_exact() -> None:
    """워드 읽기 %MW100 명령블록이 LE 레이아웃과 바이트 일치."""
    body = build_read_request(DT_WORD, ["%MW100"])
    assert body == _EXPECTED_READ_WORD_MW100


# --------------------------------------------------------------------------- #
# 엔디언 핀: 헤더도 little-endian 임을 못박는다(브리프의 BE 주장 반증)            #
# --------------------------------------------------------------------------- #
def test_header_invoke_and_length_are_little_endian() -> None:
    """Invoke ID/Length 가 LE(저위바이트 선행)로 직렬화되는지 바이트로 확정.

    구별 가능한 값(0x1234, 0x00AB)을 써서 BE 였다면 다른 바이트가 나오게 한다.
    """
    head = build_header(payload_len=0x00AB, invoke_id=0x1234)
    # Invoke ID off14..16: LE 면 34 12, BE 면 12 34.
    assert head[14:16] == b"\x34\x12"
    assert head[14:16] != b"\x12\x34"
    # Length off16..18: LE 면 AB 00, BE 면 00 AB.
    assert head[16:18] == b"\xAB\x00"
    assert head[16:18] != b"\x00\xAB"


def test_full_adu_read_bit_byte_exact() -> None:
    """완성 ADU(헤더+블록) 바이트정밀: 헤더 LE + BCC + 매뉴얼 명령블록."""
    body = build_read_request(DT_BIT, ["%MX0"])
    adu = frame(body, invoke_id=1)
    expected_header = bytes.fromhex(
        # LSIS-XGT\0\0 | PLCinfo 00 00 | CPU 00 | src 33 | inv 01 00(LE) |
        # len 0E 00(LE) | pos 00 | BCC
        "4C 53 49 53 2D 58 47 54 00 00 00 00 00 33 01 00 0E 00 00".replace(" ", "")
    )
    assert adu[: HEADER_LEN - 1] == expected_header
    # BCC = 앞 19바이트 합의 하위 1바이트.
    assert adu[HEADER_LEN - 1] == bcc(adu[: HEADER_LEN - 1])
    # 명령블록은 매뉴얼 예제와 일치.
    assert adu[HEADER_LEN:] == _EXPECTED_READ_BIT_MX0
    # 헤더 길이 필드가 블록 길이를 정확히 가리킴.
    _src, _inv, length = parse_header(adu[:HEADER_LEN])
    assert length == len(_EXPECTED_READ_BIT_MX0)


# --------------------------------------------------------------------------- #
# 라운드트립: 핀된 와이어포맷이 MockFenetServer 와 호환되는지                     #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def server() -> Iterator[MockFenetServer]:
    with MockFenetServer() as srv:
        yield srv


def test_pinned_read_bit_roundtrips_through_mock(server: MockFenetServer) -> None:
    """핀된 비트 읽기 프레임을 그대로 목서버에 보내 응답이 파싱되는지."""
    server.image.write_bit("%MX0", True)
    sock = socket.create_connection((server.host, server.port), timeout=3.0)
    try:
        sock.sendall(frame(_EXPECTED_READ_BIT_MX0, invoke_id=0x1234))
        head = sock.recv(HEADER_LEN)
        src, invoke, length = parse_header(head)
        assert invoke == 0x1234
        body = b""
        while len(body) < length:
            body += sock.recv(length - len(body))
        # 응답: command(2) dtype(2) reserved(2) errstate(2) blockcnt(2) [dcnt(2) data]
        command, _dt, _rsv, errstate = struct.unpack("<HHHH", body[:8])
        assert errstate == 0
        (blockcnt,) = struct.unpack("<H", body[8:10])
        assert blockcnt == 1
        (dcnt,) = struct.unpack("<H", body[10:12])
        assert body[12 : 12 + dcnt] == b"\x01"  # %MX0=True
    finally:
        sock.close()


def test_pinned_write_word_roundtrips_through_mock(server: MockFenetServer) -> None:
    """핀된 워드 쓰기 프레임 → 목서버 디바이스 이미지에 1 이 기록되는지."""
    sock = socket.create_connection((server.host, server.port), timeout=3.0)
    try:
        sock.sendall(frame(_EXPECTED_WRITE_WORD_MW100_1, invoke_id=7))
        head = sock.recv(HEADER_LEN)
        _src, invoke, length = parse_header(head)
        assert invoke == 7
        body = b""
        while len(body) < length:
            body += sock.recv(length - len(body))
        _cmd, _dt, _rsv, errstate = struct.unpack("<HHHH", body[:8])
        assert errstate == 0
    finally:
        sock.close()
    assert server.image.read_word("%MW100") == 1


def test_high_level_link_roundtrip_preserves_wire_semantics(
    server: MockFenetServer,
) -> None:
    """FenetPlcLink 경유 write→read 라운드트립(고수준 계약)."""
    fmap = FenetMap(inputs={"START": "%MX0"}, outputs={"LAMP": "%MX0"})
    link = FenetPlcLink(server.host, server.port, fenet_map=fmap)
    try:
        link.write_inputs({"START": True})
        assert link.read_outputs() == {"LAMP": True}
    finally:
        link.close()
