"""MELSEC MC 프로토콜(SLMP 3E 바이너리) 어댑터 테스트.

전부 localhost(인프로세스 목 슬레이브)에서 동작하며 외부 네트워크/의존성 없음.
3E 프레임 바이트 정확성, 비트 니블 패킹, 종료코드 에러, 미매핑 거부,
라운드트립, 멱등 close, 결정론을 검증한다.
"""

from __future__ import annotations

import struct

import pytest

from app.comms.melsec import (
    DEVICE_CODES,
    MelsecEndCodeError,
    MelsecMap,
    MelsecPlcLink,
    MockMelsecServer,
    WriteRejected,
    _Mc3eBinary,
    pack_bits_nibble,
    parse_device,
    unpack_bits_nibble,
)
from app.comms.protocols import PlcLink


# --------------------------------------------------------------------------- #
# 디바이스 파서                                                                 #
# --------------------------------------------------------------------------- #
def test_parse_device_decimal_and_hex() -> None:
    assert parse_device("M0") == (0x90, 0)
    assert parse_device("D100") == (0xA8, 100)
    # X/Y 는 16진수 번호.
    assert parse_device("X10") == (0x9C, 0x10)
    assert parse_device("Y1F") == (0x9D, 0x1F)
    assert parse_device("B20") == (0xA0, 0x20)


def test_parse_device_longest_prefix_wins() -> None:
    # "SM"/"CS"/"TS" 가 "S"/"C"/"T" 보다 우선해야 한다.
    assert parse_device("SM400")[0] == DEVICE_CODES["SM"]
    assert parse_device("CS5")[0] == DEVICE_CODES["CS"]
    assert parse_device("TS3")[0] == DEVICE_CODES["TS"]


def test_parse_device_errors() -> None:
    with pytest.raises(ValueError):
        parse_device("")
    with pytest.raises(ValueError):
        parse_device("Q5")  # 알 수 없는 접두어
    with pytest.raises(ValueError):
        parse_device("M")  # 번호 없음
    with pytest.raises(ValueError):
        parse_device("DZZ")  # 잘못된 10진수


# --------------------------------------------------------------------------- #
# 비트 니블 패킹                                                                #
# --------------------------------------------------------------------------- #
def test_nibble_pack_roundtrip_crossing_byte() -> None:
    # 16비트: 바이트 경계를 넘는 패턴(점0 ON, 점1 OFF, 점8 ON ...).
    bits = [True, False, True, True, False, False, True, False,
            True, True, False, False, False, False, False, True]
    packed = pack_bits_nibble(bits)
    assert len(packed) == 8  # 2점/바이트
    # 점0 → byte0 상위 니블, 점1 → byte0 하위 니블.
    assert packed[0] == 0x10  # 점0 ON, 점1 OFF
    assert packed[1] == 0x11  # 점2 ON, 점3 ON
    assert unpack_bits_nibble(packed, len(bits)) == bits


def test_nibble_pack_odd_count_pads() -> None:
    bits = [True, False, True]  # 3점 → 2바이트, 마지막 하위 니블 패딩
    packed = pack_bits_nibble(bits)
    assert len(packed) == 2
    assert packed[0] == 0x10  # 점0 ON, 점1 OFF
    assert packed[1] == 0x10  # 점2 ON, 패딩 0
    assert unpack_bits_nibble(packed, 3) == bits


# --------------------------------------------------------------------------- #
# 3E 프레임 바이트 정확성                                                       #
# --------------------------------------------------------------------------- #
def test_build_request_frame_read_bits_M0() -> None:
    # "16비트 M0 읽기" 의 정확한 요청 바이트.
    req = _Mc3eBinary._request_prefix(0x0401, 0x0001, 0x90, 0, 16)
    frame = _Mc3eBinary._build_request(req)
    expected = bytes([
        0x50, 0x00,              # 서브헤더 0x5000 (BE)
        0x00,                    # 네트워크 번호
        0xFF,                    # PC 번호
        0xFF, 0x03,              # 요청 대상 모듈 IO 0x03FF (LE)
        0x00,                    # 요청 대상 국번
        0x0C, 0x00,              # 요청 데이터 길이 = 12 (LE)
        0x10, 0x00,              # 모니터링 타이머 0x0010 (LE)
        0x01, 0x04,              # 커맨드 0x0401 (LE)
        0x01, 0x00,              # 서브커맨드 0x0001 (LE)
        0x90,                    # 디바이스 코드 M
        0x00, 0x00, 0x00,        # 선두 디바이스 번호 0 (3바이트 LE)
        0x10, 0x00,              # 점수 16 (LE)
    ])
    assert frame == expected
    # 요청 데이터 길이 필드 = 모니터링타이머(2)+요청데이터(10) = 12.
    assert struct.unpack("<H", frame[7:9])[0] == 12


def test_build_request_frame_write_word_D100_1234() -> None:
    # "D100 = 1234 워드 쓰기" 의 정확한 요청 바이트.
    req = _Mc3eBinary._request_prefix(0x1401, 0x0000, 0xA8, 100, 1)
    req += struct.pack("<H", 1234)
    frame = _Mc3eBinary._build_request(req)
    expected = bytes([
        0x50, 0x00,              # 서브헤더 (BE)
        0x00, 0xFF,              # 네트워크 / PC
        0xFF, 0x03,              # 모듈 IO 0x03FF (LE)
        0x00,                    # 국번
        0x0E, 0x00,              # 요청 데이터 길이 = 14 (LE)
        0x10, 0x00,              # 모니터링 타이머 (LE)
        0x01, 0x14,              # 커맨드 0x1401 (LE)
        0x00, 0x00,              # 서브커맨드 0x0000 (LE, 워드)
        0xA8,                    # 디바이스 코드 D
        0x64, 0x00, 0x00,        # 선두 번호 100 = 0x64 (3바이트 LE)
        0x01, 0x00,              # 점수 1 (LE)
        0xD2, 0x04,              # 데이터 1234 = 0x04D2 (LE)
    ])
    assert frame == expected


def test_build_request_frame_write_bit_M0_1() -> None:
    # "M0 = 1 비트 쓰기" 의 정확한 요청 바이트(니블 패킹).
    req = _Mc3eBinary._request_prefix(0x1401, 0x0001, 0x90, 0, 1)
    req += pack_bits_nibble([True])
    frame = _Mc3eBinary._build_request(req)
    # 데이터부 마지막 바이트: 점0 ON → 상위 니블 → 0x10.
    assert frame[-1] == 0x10
    assert frame[11:13] == bytes([0x01, 0x14])  # 커맨드 0x1401
    assert frame[13:15] == bytes([0x01, 0x00])  # 서브 0x0001


# --------------------------------------------------------------------------- #
# 클라이언트 ↔ 목 슬레이브 라운드트립                                           #
# --------------------------------------------------------------------------- #
def test_client_write_read_bits_roundtrip() -> None:
    with MockMelsecServer() as server:
        client = _Mc3eBinary(server.host, server.port, timeout=2.0)
        try:
            pattern = [True, False, True, True, False, False, False, True,
                       False, True, False, False, False, False, True, True]
            client.write_bits("M0", pattern)
            assert client.read_bits("M0", 16) == pattern
            # 개별 비트도 정확히 읽힌다.
            assert client.read_bits("M2", 1) == [True]
            assert client.read_bits("M4", 1) == [False]
        finally:
            client.close()


def test_mock_server_holds_distinct_device_codes() -> None:
    # 같은 번호라도 디바이스 코드가 다르면 독립적으로 보관.
    with MockMelsecServer() as server:
        client = _Mc3eBinary(server.host, server.port, timeout=2.0)
        try:
            client.write_bits("M0", [True])
            client.write_bits("X0", [False])
            assert client.read_bits("M0", 1) == [True]
            assert client.read_bits("X0", 1) == [False]
        finally:
            client.close()


# --------------------------------------------------------------------------- #
# 종료코드 에러                                                                 #
# --------------------------------------------------------------------------- #
def test_nonzero_end_code_raises() -> None:
    # 워드 서브커맨드는 목 슬레이브가 거부(0xC05C) → MelsecEndCodeError.
    with MockMelsecServer() as server:
        client = _Mc3eBinary(server.host, server.port, timeout=2.0)
        try:
            with pytest.raises(MelsecEndCodeError) as exc:
                client.read_words("D0", 1)
            assert exc.value.end_code == 0xC05C
            assert "0xC05C" in str(exc.value)
        finally:
            client.close()


# --------------------------------------------------------------------------- #
# PlcLink 어댑터                                                                #
# --------------------------------------------------------------------------- #
def test_plclink_satisfies_protocol() -> None:
    link = MelsecPlcLink("127.0.0.1", melsec_map=MelsecMap())
    assert isinstance(link, PlcLink)
    link.close()


def test_plclink_write_read_via_map() -> None:
    mmap = MelsecMap.default_on_m_bits(
        input_symbols=["start", "stop"],
        output_symbols=["motor", "lamp"],
    )
    with MockMelsecServer() as server:
        link = MelsecPlcLink(
            server.host, port=server.port, melsec_map=mmap, timeout=2.0
        )
        try:
            link.write_inputs({"start": True, "stop": False})
            # 입력은 출력 영역과 다른 디바이스이므로 출력은 아직 전부 OFF.
            assert link.read_outputs() == {"motor": False, "lamp": False}
            # 출력 디바이스에 직접 써서 read_outputs 가 반영하는지 확인.
            server.image.write_bits(*_dev("M1000"), [True])  # motor
            server.image.write_bits(*_dev("M1001"), [True])  # lamp
            assert link.read_outputs() == {"motor": True, "lamp": True}
        finally:
            link.close()


def _dev(s: str) -> tuple[int, int]:
    return parse_device(s)


def test_plclink_rejects_unmapped_symbol() -> None:
    mmap = MelsecMap(inputs={"start": "M0"})
    link = MelsecPlcLink("127.0.0.1", melsec_map=mmap)
    try:
        with pytest.raises(WriteRejected) as exc:
            link.write_inputs({"start": True, "ghost": False})
        assert "ghost" in str(exc.value)
    finally:
        link.close()


def test_plclink_empty_ops_noop() -> None:
    link = MelsecPlcLink("127.0.0.1", melsec_map=MelsecMap())
    try:
        link.write_inputs({})  # 빈 입력 → 통신 없이 무동작
        assert link.read_outputs() == {}  # 빈 출력맵 → 통신 없이 빈 사전
    finally:
        link.close()


def test_default_map_layout() -> None:
    mmap = MelsecMap.default_on_m_bits(["b", "a"], ["y", "x"])
    # 정렬되어 매핑된다.
    assert mmap.inputs == {"a": "M0", "b": "M1"}
    assert mmap.outputs == {"x": "M1000", "y": "M1001"}


# --------------------------------------------------------------------------- #
# 멱등 close / 결정론                                                           #
# --------------------------------------------------------------------------- #
def test_close_idempotent() -> None:
    with MockMelsecServer() as server:
        link = MelsecPlcLink(server.host, port=server.port, timeout=2.0)
        link.write_inputs({})  # 연결 생성 안 됨(빈)
        link.close()
        link.close()  # 두 번째 close 도 안전
        client = _Mc3eBinary(server.host, server.port, timeout=2.0)
        client.read_bits("M0", 1)  # 실제 소켓 생성 후
        client.close()
        client.close()  # 멱등


def test_determinism_repeated_frames_identical() -> None:
    # 동일 입력 → 동일 바이트 프레임(트랜잭션 ID 같은 상태 없음).
    f1 = _Mc3eBinary._build_request(
        _Mc3eBinary._request_prefix(0x0401, 0x0001, 0x90, 0, 16)
    )
    f2 = _Mc3eBinary._build_request(
        _Mc3eBinary._request_prefix(0x0401, 0x0001, 0x90, 0, 16)
    )
    assert f1 == f2
