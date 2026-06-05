"""순수 표준 라이브러리 LS XGT FEnet 전용(dedicated) 프로토콜 어댑터 (Stage 3 통신 계층).

외부 의존성(PyXGT 등) 없이 ``socket``/``struct``/``socketserver`` 만으로 LS일렉트릭
XGT/XGB FEnet 전용 프로토콜(TCP 2004)의 응용 프레임(application frame)을 직접
조립/해석한다. ``PlcLink`` 계약(app.comms.protocols)을 만족하는 :class:`FenetPlcLink`
를 제공해 우리 엔진이 실제 LS PLC 를 네이티브로 구동할 수 있게 한다.

프레이밍 요약 (XGT Dedicated Protocol — LS FEnet I/F Module User's Manual,
오픈소스 구현 ``nakeeun/lsxgt_tcp_communication`` 및 Wireshark 디섹터
``ciaoly/PLC-XGT-protocol-for-Wireshark/xgb.lua`` 로 바이트 단위 교차 검증):

    ADU = 응용헤더(20바이트) + 명령프레임(command block)

    응용헤더(Application Header, little-endian, 20바이트):
        off  0  Company ID   10  ASCII "LSIS-XGT\\x00\\x00" (8글자 + NUL 패딩)
        off 10  PLC Info      2  예약(0x0000)
        off 12  CPU Info      1  CPU 종류(요청 시 0)
        off 13  Source(방향)  1  0x33=클라이언트 요청, 0x11=서버 응답
        off 14  Invoke ID     2  요청/응답 짝맞춤용 일련번호(LE), 요청마다 증가
        off 16  Length        2  뒤따르는 명령프레임 바이트 수(LE)
        off 18  FEnet Pos     1  모듈 슬롯/베이스 위치(기본 0)
        off 19  BCC           1  헤더 0..18 바이트 합의 하위 1바이트(checksum)

    명령프레임(Command Block, little-endian):
        Command    2  읽기요청 0x0054 / 쓰기요청 0x0058
                      읽기응답 0x0055 / 쓰기응답 0x0059
        Data Type  2  bit 0x0000 / byte 0x0001 / word 0x0002 / dword 0x0003 /
                      lword 0x0004 / 연속(continuous) 0x0014
        Reserved   2  0x0000
        Block Cnt  2  변수 블록 개수(개별읽기/쓰기는 1)
        per block(요청):
            Name Len  2  변수이름 ASCII 길이
            Name      N  "%MX0" / "%MW100" / "%DW10" 등
            (쓰기에 한해) Data Cnt 2 + Data  데이터 바이트 수 + 데이터
        응답:
            Error State 2  0x0000=정상, 그 외=NAK/에러
            (정상 읽기응답) Block Cnt 2, per block: Data Cnt 2 + Data

바이트 순서는 헤더·명령블록 **전부 LE(little-endian)** 다 — XGT 전용 프로토콜은
모든 멀티바이트 수치(Invoke ID/Length/Command/Data Type/Block Count/Var-name Len)를
리틀엔디언으로 보낸다. 비트 데이터(bit) 는 1바이트(0x00/0x01)로 표현된다.

엔디언 검증(2026-06, 3개 독립 1차 출처 교차검증 — 정형 결론):
  * **권위 출처(LS 매뉴얼 본문)**: LS ELECTRIC 공식 *XGB FEnet I/F Module User's
    Manual* (XBL-EMTA), Chapter 5.2 "Frame examples — Request frame for individual
    reading of variables" 의 워크드 예제가 와이어 바이트를 직접 명시한다:
        Command 0x54 0x00 / Block No. 0x01 0x00 / Variable Length 0x04 0x00
    → Command(0x0054), Block(1), VarLen(4) 모두 **저위바이트 선행(LE)**.
    또한 명령코드 표는 Read-Req 를 "0x5400" (와이어형 `54 00`) 로 표기 → LE 확정.
    (https://www.dalroad.com/wp-content/uploads/2015/04/XGB-FEnet_Manual-ENG_V1.5.pdf)
  * **Wireshark 디섹터**(ciaoly/PLC-XGT-protocol-for-Wireshark/xgb.lua): Invoke ID,
    Length 포함 모든 멀티바이트 필드를 ``add_le`` 로 읽는다 → 헤더도 LE.
  * **golanglsplc**(song9063/golanglsplc/lsplc.go) makeHeader: ``get2BytesFromInt``
    가 ``(hi, lo)`` 를 반환하고 ``bytes[15], bytes[14] = get2BytesFromInt(invokeId)``
    로 대입 → **bytes[14]=lo, bytes[15]=hi** = 낮은 오프셋에 저위바이트 = LE.
    (Length 도 동일 패턴.)

  ⇒ docs/LS_MITSUBISHI_PROTOCOL_BRIEF.md 의 "헤더=BE, 블록=LE" 주장은 **오류**다
    (golanglsplc 의 헷갈리는 다중대입을 BE 로 오독한 데서 비롯). 실제로는 헤더·블록
    모두 LE 이며, 본 어댑터(모든 struct 포맷 ``<``)가 **맞다**. 따라서 로직은
    변경하지 않는다. 바이트 정밀 핀은 tests/test_fenet_conformance.py 가, 실 CPU
    대조 절차는 scripts/fenet_pcap_verify.py 가 못박는다.
"""

from __future__ import annotations

import socket
import socketserver
import struct
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.comms.protocols import WriteRejected

__all__ = [
    "FenetError",
    "FenetMap",
    "FenetNakError",
    "FenetPlcLink",
    "MockFenetServer",
    "WriteRejected",
]

# --------------------------------------------------------------------------- #
# 프로토콜 상수                                                                 #
# --------------------------------------------------------------------------- #
COMPANY_ID = b"LSIS-XGT"  # 8글자
_COMPANY_FIELD = COMPANY_ID + b"\x00\x00"  # 10바이트(NUL 패딩)
HEADER_LEN = 20

SRC_CLIENT = 0x33  # source of frame: 클라이언트→PLC 요청
SRC_SERVER = 0x11  # source of frame: PLC→클라이언트 응답

# 명령(Command)
CMD_READ_REQ = 0x0054
CMD_WRITE_REQ = 0x0058
CMD_READ_RESP = 0x0055
CMD_WRITE_RESP = 0x0059

# 데이터 타입(Data Type)
DT_BIT = 0x0000
DT_BYTE = 0x0001
DT_WORD = 0x0002
DT_DWORD = 0x0003
DT_LWORD = 0x0004
DT_CONTINUOUS = 0x0014

_DEFAULT_PORT = 2004
_MAX_BLOCKS = 16  # XGT 개별 서비스 최대 블록 수


class FenetError(Exception):
    """FEnet 통신/프레이밍 오류(연결 끊김, 잘못된 헤더/체크섬 등)."""


class FenetNakError(FenetError):
    """PLC 가 에러(error state != 0)/NAK 응답을 반환했을 때 발생."""

    def __init__(self, error_state: int, command: int) -> None:
        self.error_state = error_state
        self.command = command
        super().__init__(
            f"XGT FEnet NAK: error state 0x{error_state:04X} "
            f"for command 0x{command:04X}"
        )


# --------------------------------------------------------------------------- #
# 프레임 빌드/파싱 헬퍼                                                          #
# --------------------------------------------------------------------------- #
def bcc(header_first19: bytes) -> int:
    """헤더 앞 19바이트(0..18)의 합 하위 1바이트(BCC checksum)를 계산한다."""
    return sum(header_first19) & 0xFF


def build_header(payload_len: int, invoke_id: int, *, source: int = SRC_CLIENT) -> bytes:
    """응용헤더(20바이트)를 조립한다. BCC 는 앞 19바이트 합으로 채운다."""
    head19 = struct.pack(
        "<10sHBBHHB",
        _COMPANY_FIELD,
        0x0000,  # PLC info(예약)
        0x00,  # CPU info
        source & 0xFF,
        invoke_id & 0xFFFF,
        payload_len & 0xFFFF,
        0x00,  # FEnet position
    )
    return head19 + bytes([bcc(head19)])


def parse_header(data: bytes) -> tuple[int, int, int]:
    """응용헤더를 검증/해석해 (source, invoke_id, payload_len) 을 돌려준다."""
    if len(data) < HEADER_LEN:
        raise FenetError("short application header")
    if data[:8] != COMPANY_ID:
        raise FenetError(f"bad company id: {data[:8]!r}")
    company, _plc, _cpu, source, invoke_id, length, _pos = struct.unpack(
        "<10sHBBHHB", data[:19]
    )
    expected = bcc(data[:19])
    if data[19] != expected:
        raise FenetError(
            f"bad BCC: got 0x{data[19]:02X}, expected 0x{expected:02X}"
        )
    return source, invoke_id, length


def build_read_request(data_type: int, names: Sequence[str]) -> bytes:
    """읽기 요청 명령프레임(헤더 제외)을 조립한다."""
    if not 1 <= len(names) <= _MAX_BLOCKS:
        raise ValueError(f"block count out of range: {len(names)}")
    body = struct.pack("<HHHH", CMD_READ_REQ, data_type, 0x0000, len(names))
    for name in names:
        raw = name.encode("ascii")
        body += struct.pack("<H", len(raw)) + raw
    return body


def build_write_request(data_type: int, items: Sequence[tuple[str, bytes]]) -> bytes:
    """쓰기 요청 명령프레임(헤더 제외)을 조립한다. items=[(이름, 데이터바이트)]."""
    if not 1 <= len(items) <= _MAX_BLOCKS:
        raise ValueError(f"block count out of range: {len(items)}")
    body = struct.pack("<HHHH", CMD_WRITE_REQ, data_type, 0x0000, len(items))
    # 변수명 블록들 먼저, 그 다음 데이터 블록들 (XGT 개별 쓰기 레이아웃).
    for name, _ in items:
        raw = name.encode("ascii")
        body += struct.pack("<H", len(raw)) + raw
    for _, payload in items:
        body += struct.pack("<H", len(payload)) + payload
    return body


def frame(payload: bytes, invoke_id: int, *, source: int = SRC_CLIENT) -> bytes:
    """명령프레임에 헤더를 붙여 완성된 ADU 를 만든다."""
    return build_header(len(payload), invoke_id, source=source) + payload


# --------------------------------------------------------------------------- #
# 매핑                                                                          #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FenetMap:
    """심볼 ↔ LS 디바이스 이름 매핑.

    LS 의 FEnet/Modbus 주소 체계는 PLC 마다 설정이 다르므로 하드코딩하지 않고
    PLC 별 디바이스 이름 매핑을 그대로 보관한다.

    inputs:  쓰기 대상 심볼 → 비트 디바이스 이름(예 "%MX0").
    outputs: 읽기 대상 심볼 → 비트 디바이스 이름(예 "%MX16").
    """

    inputs: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)

    @classmethod
    def default_from_symbols(
        cls,
        input_symbols: Sequence[str],
        output_symbols: Sequence[str],
        *,
        input_base: int = 0,
        output_base: int = 16,
    ) -> FenetMap:
        """정렬된 심볼 목록을 %MX 비트 디바이스에 순차 매핑한 기본 맵을 만든다.

        입력은 ``%MX{input_base}`` 부터, 출력은 ``%MX{output_base}`` 부터
        하나씩 증가하며 배정한다. 베이스가 설정 가능하므로 PLC 별로 조정 가능.
        """
        inputs = {
            sym: f"%MX{input_base + i}" for i, sym in enumerate(sorted(input_symbols))
        }
        outputs = {
            sym: f"%MX{output_base + i}"
            for i, sym in enumerate(sorted(output_symbols))
        }
        return cls(inputs=inputs, outputs=outputs)


# --------------------------------------------------------------------------- #
# 순수 stdlib FEnet 클라이언트                                                  #
# --------------------------------------------------------------------------- #
class _FenetClient:
    """최소 XGT FEnet 전용 프로토콜 클라이언트. 비트/워드 개별 읽기·쓰기 지원."""

    def __init__(self, host: str, port: int = _DEFAULT_PORT, timeout: float = 3.0) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._invoke = 0
        self._sock: socket.socket | None = None

    # -- 연결 관리 --------------------------------------------------------- #
    def _connect(self) -> socket.socket:
        if self._sock is None:
            sock = socket.create_connection((self._host, self._port), timeout=self._timeout)
            sock.settimeout(self._timeout)
            self._sock = sock
        return self._sock

    def close(self) -> None:
        """소켓을 닫는다(멱등)."""
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    # -- 프레이밍 ---------------------------------------------------------- #
    def _next_invoke(self) -> int:
        self._invoke = (self._invoke + 1) & 0xFFFF
        return self._invoke

    @staticmethod
    def _recv_exact(sock: socket.socket, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise FenetError("connection closed by peer")
            buf.extend(chunk)
        return bytes(buf)

    def _transaction(self, payload: bytes) -> bytes:
        """명령프레임을 보내고 응답 명령프레임(헤더 제외)을 돌려준다."""
        sock = self._connect()
        invoke = self._next_invoke()
        sock.sendall(frame(payload, invoke, source=SRC_CLIENT))

        head = self._recv_exact(sock, HEADER_LEN)
        source, r_invoke, length = parse_header(head)
        if source != SRC_SERVER:
            raise FenetError(f"unexpected source of frame: 0x{source:02X}")
        if r_invoke != invoke:
            raise FenetError(f"invoke id mismatch: sent {invoke}, got {r_invoke}")
        body = self._recv_exact(sock, length)
        self._check_resp(body)
        return body

    @staticmethod
    def _check_resp(body: bytes) -> None:
        """응답 명령프레임을 검사한다. error state != 0 이면 NAK 예외."""
        if len(body) < 8:
            raise FenetError("short command response")
        command, _dtype, _reserved, error_state = struct.unpack("<HHHH", body[:8])
        if error_state != 0:
            raise FenetNakError(error_state, command)

    # -- 비트 ------------------------------------------------------------- #
    def read_bits(self, names: Sequence[str]) -> list[bool]:
        """비트 디바이스(%MX 등) 들을 개별 읽기한다."""
        body = self._transaction(build_read_request(DT_BIT, names))
        return self._parse_read_bits(body, len(names))

    def write_bit(self, name: str, value: bool) -> None:
        """비트 디바이스(%MX 등) 하나를 쓴다(0x00/0x01)."""
        data = b"\x01" if value else b"\x00"
        self._transaction(build_write_request(DT_BIT, [(name, data)]))

    # -- 워드 ------------------------------------------------------------- #
    def read_words(self, names: Sequence[str]) -> list[int]:
        """워드 디바이스(%MW 등) 들을 개별 읽기한다(16비트 LE)."""
        body = self._transaction(build_read_request(DT_WORD, names))
        return self._parse_read_words(body, len(names))

    def write_word(self, name: str, value: int) -> None:
        """워드 디바이스(%MW 등) 하나를 쓴다(16비트 LE)."""
        data = struct.pack("<H", value & 0xFFFF)
        self._transaction(build_write_request(DT_WORD, [(name, data)]))

    # -- 응답 파싱 -------------------------------------------------------- #
    @staticmethod
    def _iter_read_blocks(body: bytes, count: int) -> list[bytes]:
        # body: command(2) dtype(2) reserved(2) errstate(2) blockcnt(2) [blocks]
        # 악성/불량 PLC 응답: 짧은 바디로 struct.error 가 새지 않게 길이 가드.
        if len(body) < 10:
            raise FenetError("short read response (no block count)")
        block_count = struct.unpack("<H", body[8:10])[0]
        if block_count != count:
            raise FenetError(f"block count mismatch: want {count}, got {block_count}")
        out: list[bytes] = []
        off = 10
        for _ in range(count):
            if off + 2 > len(body):
                raise FenetError("short read block header")
            (dcount,) = struct.unpack("<H", body[off : off + 2])
            off += 2
            chunk = body[off : off + dcount]
            if len(chunk) != dcount:
                raise FenetError("short read data block")
            out.append(chunk)
            off += dcount
        return out

    def _parse_read_bits(self, body: bytes, count: int) -> list[bool]:
        return [block[0] != 0 if block else False for block in self._iter_read_blocks(body, count)]

    def _parse_read_words(self, body: bytes, count: int) -> list[int]:
        out: list[int] = []
        for block in self._iter_read_blocks(body, count):
            if len(block) < 2:
                raise FenetError("short word read block")
            out.append(struct.unpack("<H", block[:2])[0])
        return out


# --------------------------------------------------------------------------- #
# PlcLink 구현                                                                  #
# --------------------------------------------------------------------------- #
class FenetPlcLink:
    """``PlcLink`` 를 만족하는 LS XGT FEnet 어댑터(비트 디바이스 단위).

    write_inputs: 입력 심볼 값을 매핑된 비트 디바이스(%MX)에 쓴다.
    read_outputs: 출력 심볼을 매핑된 비트 디바이스(%MX)에서 읽는다.
    매핑에 없는 심볼은 :class:`WriteRejected` 로 거부한다(오타/이중쓰기 방지).
    """

    def __init__(
        self,
        host: str,
        port: int = _DEFAULT_PORT,
        fenet_map: FenetMap | None = None,
        timeout: float = 3.0,
    ) -> None:
        self._map = fenet_map if fenet_map is not None else FenetMap()
        self._client = _FenetClient(host, port, timeout=timeout)

    def write_inputs(self, values: dict[str, bool]) -> None:
        """입력 심볼 값을 PLC 비트 디바이스에 쓴다(개별 쓰기)."""
        if not values:
            return
        unknown = sorted(set(values) - set(self._map.inputs))
        if unknown:
            raise WriteRejected(f"미매핑 입력 심볼: {', '.join(unknown)}")
        for sym in sorted(values):
            self._client.write_bit(self._map.inputs[sym], bool(values[sym]))

    def read_outputs(self) -> dict[str, bool]:
        """PLC 출력 비트 디바이스를 읽어 심볼→BOOL 사전으로 반환한다."""
        outputs = self._map.outputs
        if not outputs:
            return {}
        syms = sorted(outputs)
        names = [outputs[s] for s in syms]
        bits = self._client.read_bits(names)
        return dict(zip(syms, bits, strict=True))

    def close(self) -> None:
        """링크를 닫는다(멱등)."""
        self._client.close()


# --------------------------------------------------------------------------- #
# 테스트용 인프로세스 FEnet 슬레이브                                            #
# --------------------------------------------------------------------------- #
class _DeviceImage:
    """%MX 비트 / %MW 워드 디바이스 이미지(스레드 안전).

    디바이스 이름(예 "%MX16", "%MW10")을 키로 비트/워드 값을 보관한다.
    """

    def __init__(self) -> None:
        self.bits: dict[str, bool] = {}
        self.words: dict[str, int] = {}
        self.lock = threading.Lock()

    def read_bit(self, name: str) -> bool:
        with self.lock:
            return self.bits.get(name, False)

    def write_bit(self, name: str, value: bool) -> None:
        with self.lock:
            self.bits[name] = value

    def read_word(self, name: str) -> int:
        with self.lock:
            return self.words.get(name, 0)

    def write_word(self, name: str, value: int) -> None:
        with self.lock:
            self.words[name] = value & 0xFFFF


class _FenetRequestHandler(socketserver.BaseRequestHandler):
    """단일 연결에서 여러 FEnet 트랜잭션을 처리한다."""

    server: MockFenetServer

    def handle(self) -> None:
        sock = self.request
        while True:
            head = self._recv_exact(sock, HEADER_LEN)
            if head is None:
                return
            try:
                _src, invoke, length = parse_header(head)
            except FenetError:
                return
            body = self._recv_exact(sock, length)
            if body is None:
                return
            resp_body = self._dispatch(body)
            out = frame(resp_body, invoke, source=SRC_SERVER)
            try:
                sock.sendall(out)
            except OSError:
                return

    @staticmethod
    def _recv_exact(sock: socket.socket, n: int) -> bytes | None:
        buf = bytearray()
        while len(buf) < n:
            try:
                chunk = sock.recv(n - len(buf))
            except OSError:
                return None
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)

    @staticmethod
    def _resp(command: int, data_type: int, error: int, tail: bytes = b"") -> bytes:
        return struct.pack("<HHHH", command, data_type, 0x0000, error) + tail

    def _dispatch(self, body: bytes) -> bytes:
        if len(body) < 8:
            return self._resp(0, 0, 0x0001)
        command, data_type, _reserved, block_count = struct.unpack("<HHHH", body[:8])
        try:
            if command == CMD_READ_REQ:
                return self._handle_read(data_type, block_count, body)
            if command == CMD_WRITE_REQ:
                return self._handle_write(data_type, block_count, body)
            return self._resp(command, data_type, 0x0010)  # 미지원 명령
        except (struct.error, IndexError):
            return self._resp(command, data_type, 0x00FF)  # 프레이밍 오류

    def _handle_read(self, data_type: int, block_count: int, body: bytes) -> bytes:
        image = self.server.image
        off = 8
        names: list[str] = []
        for _ in range(block_count):
            (nlen,) = struct.unpack("<H", body[off : off + 2])
            off += 2
            names.append(body[off : off + nlen].decode("ascii"))
            off += nlen
        tail = struct.pack("<H", block_count)
        for name in names:
            if data_type == DT_BIT:
                data = b"\x01" if image.read_bit(name) else b"\x00"
            elif data_type == DT_WORD:
                data = struct.pack("<H", image.read_word(name))
            else:
                return self._resp(CMD_READ_RESP, data_type, 0x0011)
            tail += struct.pack("<H", len(data)) + data
        return self._resp(CMD_READ_RESP, data_type, 0x0000, tail)

    def _handle_write(self, data_type: int, block_count: int, body: bytes) -> bytes:
        image = self.server.image
        off = 8
        names: list[str] = []
        for _ in range(block_count):
            (nlen,) = struct.unpack("<H", body[off : off + 2])
            off += 2
            names.append(body[off : off + nlen].decode("ascii"))
            off += nlen
        for name in names:
            (dcount,) = struct.unpack("<H", body[off : off + 2])
            off += 2
            data = body[off : off + dcount]
            off += dcount
            if data_type == DT_BIT:
                image.write_bit(name, data[:1] != b"\x00")
            elif data_type == DT_WORD:
                image.write_word(name, struct.unpack("<H", data[:2])[0])
            else:
                return self._resp(CMD_WRITE_RESP, data_type, 0x0011)
        return self._resp(CMD_WRITE_RESP, data_type, 0x0000)


class MockFenetServer(socketserver.ThreadingTCPServer):
    """인프로세스 XGT FEnet 슬레이브(테스트용). 컨텍스트 매니저 지원.

    에페메럴 포트(port=0)로 시작하고 ``host``/``port`` 속성으로 접속 주소를 노출.
    내부 ``image`` 가 %MX 비트/%MW 워드 디바이스 이미지를 보관한다.
    """

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.image = _DeviceImage()
        super().__init__((host, port), _FenetRequestHandler)
        self._thread: threading.Thread | None = None

    def handle_error(self, request: object, client_address: object) -> None:
        # 클라이언트가 연결을 끊는 등으로 처리 중 예외가 나도 조용히 무시한다(테스트 노이즈 방지).
        return

    @property
    def host(self) -> str:
        return str(self.server_address[0])

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    def start(self) -> None:
        """백그라운드 스레드에서 서버를 구동한다."""
        if self._thread is None:
            self._thread = threading.Thread(target=self.serve_forever, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """서버를 정지하고 소켓을 해제한다(멱등)."""
        if self._thread is not None:
            self.shutdown()
            self._thread.join(timeout=5.0)
            self._thread = None
        self.server_close()

    def __enter__(self) -> MockFenetServer:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()
