"""순수 표준 라이브러리 Mitsubishi MELSEC MC 프로토콜(SLMP 3E 바이너리) 어댑터.

외부 의존성(pymcprotocol 등) 없이 ``socket``/``struct``/``socketserver`` 만으로
MC 프로토콜 3E 바이너리 프레임 클라이언트와 테스트용 인프로세스 슬레이브를
구현한다. ``PlcLink`` 계약(app.comms.protocols)을 만족하는 :class:`MelsecPlcLink`
를 제공한다.

3E 바이너리 요청 프레임 레이아웃 (SLMP / MELSEC Communication Protocol):

    ┌ 서브헤더            2바이트  0x5000  → 바이트열 ``50 00``
    │ 네트워크 번호       1바이트  0x00
    │ PC 번호             1바이트  0xFF
    │ 요청 대상 모듈 IO   2바이트  0x03FF  → LE 바이트열 ``FF 03``
    │ 요청 대상 국번      1바이트  0x00
    │ 요청 데이터 길이    2바이트  LE      (모니터링 타이머 이후 전체 길이)
    │ 모니터링 타이머     2바이트  LE      0x0010 (250ms 단위, 0=무한대기)
    ├ ── 이하 "요청 데이터" (길이에 포함) ──
    │ 커맨드              2바이트  LE      0x0401 일괄읽기 / 0x1401 일괄쓰기
    │ 서브커맨드          2바이트  LE      0x0001 비트 / 0x0000 워드
    │ 디바이스 코드       1바이트          D=0xA8, M=0x90 ...
    │ 선두 디바이스 번호  3바이트  LE
    │ 디바이스 점수       2바이트  LE
    └ (쓰기일 때) 데이터  가변

응답 프레임 레이아웃:

    ┌ 서브헤더            2바이트  0xD000  → 바이트열 ``D0 00``
    │ 네트워크/PC/IO/국번 4바이트  (요청 에코)
    │ 응답 데이터 길이    2바이트  LE      (종료코드 이후 전체 길이)
    │ 종료 코드           2바이트  LE      0x0000=정상, 그 외=에러
    └ (읽기일 때) 데이터  가변

비트 패킹(비트 일괄읽기/쓰기, 서브커맨드 0x0001):
    1점 = 1니블(4비트), 한 바이트에 2점. 짝수번째 점 → 상위 니블,
    홀수번째 점 → 하위 니블. 값 0x1 = ON, 0x0 = OFF.
    (점수가 홀수면 마지막 바이트 하위 니블은 0으로 패딩.)

워드 패킹(워드 일괄읽기/쓰기, 서브커맨드 0x0000):
    1점 = 1워드 = 2바이트 리틀엔디언.

기본 TCP 포트는 5007(설정 가능).
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
    "DEVICE_CODES",
    "MelsecError",
    "MelsecEndCodeError",
    "MelsecMap",
    "MelsecPlcLink",
    "MockMelsecServer",
    "WriteRejected",
    "pack_bits_nibble",
    "parse_device",
    "unpack_bits_nibble",
]

# --------------------------------------------------------------------------- #
# 프로토콜 상수                                                                 #
# --------------------------------------------------------------------------- #
_SUBHEADER_REQUEST = 0x5000
_SUBHEADER_RESPONSE = 0xD000
_NETWORK_NO = 0x00
_PC_NO = 0xFF
_DEST_MODULE_IO = 0x03FF
_DEST_STATION = 0x00
_MONITORING_TIMER = 0x0010  # 250ms 단위 → 약 4초

_CMD_BATCH_READ = 0x0401
_CMD_BATCH_WRITE = 0x1401
_SUBCMD_BIT = 0x0001
_SUBCMD_WORD = 0x0000

# 요청 헤더(모니터링 타이머까지)는 11바이트로 고정.
#   subheader(2)+net(1)+pc(1)+io(2)+station(1)+len(2)+timer(2) = 11
_REQ_HEADER_LEN = 11
# 응답 헤더(데이터 길이까지)는 9바이트.
#   subheader(2)+net(1)+pc(1)+io(2)+station(1)+len(2) = 9
_RESP_HEADER_LEN = 9

# 디바이스 점수 한계(비트/워드 일괄, 사양상 보수적 상한).
_MAX_POINTS = 7168

# MC 프로토콜 3E 바이너리 디바이스 코드 (1바이트).
DEVICE_CODES: dict[str, int] = {
    "SM": 0x91,  # 특수 릴레이
    "SD": 0xA9,  # 특수 레지스터
    "X": 0x9C,  # 입력
    "Y": 0x9D,  # 출력
    "M": 0x90,  # 내부 릴레이
    "L": 0x92,  # 래치 릴레이
    "F": 0x93,  # 어넌시에이터
    "V": 0x94,  # 에지 릴레이
    "B": 0xA0,  # 링크 릴레이
    "D": 0xA8,  # 데이터 레지스터
    "W": 0xB4,  # 링크 레지스터
    "TS": 0xC1,  # 타이머 접점
    "TC": 0xC0,  # 타이머 코일
    "TN": 0xC2,  # 타이머 현재값
    "CS": 0xC4,  # 카운터 접점
    "CC": 0xC3,  # 카운터 코일
    "CN": 0xC5,  # 카운터 현재값
    "R": 0xAF,  # 파일 레지스터
    "Z": 0xCC,  # 인덱스 레지스터
}

# 16진수로 디바이스 번호를 표기하는 디바이스(X/Y/B/W/SM/SD 등).
_HEX_DEVICES: frozenset[str] = frozenset(
    {"X", "Y", "B", "W", "SM", "SD", "DX", "DY"}
)


class MelsecError(Exception):
    """MC 프로토콜 통신/프레이밍 오류(연결 끊김, 잘못된 응답 등)."""


class MelsecEndCodeError(MelsecError):
    """슬레이브가 0이 아닌 종료코드(에러)를 반환했을 때 발생."""

    def __init__(self, end_code: int) -> None:
        self.end_code = end_code
        super().__init__(f"MELSEC end code 0x{end_code:04X} (nonzero → error)")


# --------------------------------------------------------------------------- #
# 비트 니블 패킹 헬퍼                                                           #
# --------------------------------------------------------------------------- #
def pack_bits_nibble(values: Sequence[bool]) -> bytes:
    """BOOL 시퀀스를 비트 일괄용 니블 패킹 바이트열로 인코딩한다.

    점 i 는 바이트 ``i // 2`` 에 들어가며, 짝수 i 는 상위 니블(0x10),
    홀수 i 는 하위 니블(0x01)을 차지한다. 값 ON 이면 1, OFF 이면 0.
    """
    n_bytes = (len(values) + 1) // 2
    out = bytearray(n_bytes)
    for i, val in enumerate(values):
        if val:
            shift = 4 if (i % 2 == 0) else 0
            out[i // 2] |= 1 << shift
    return bytes(out)


def unpack_bits_nibble(data: bytes, count: int) -> list[bool]:
    """니블 패킹 바이트열에서 ``count`` 개의 BOOL 을 추출한다."""
    result: list[bool] = []
    for i in range(count):
        byte = data[i // 2]
        nib = (byte >> 4) if (i % 2 == 0) else (byte & 0x0F)
        result.append(bool(nib & 0x01))
    return result


# --------------------------------------------------------------------------- #
# 디바이스 문자열 파서                                                          #
# --------------------------------------------------------------------------- #
def parse_device(device: str) -> tuple[int, int]:
    """"M0","D100","X10" 같은 디바이스 문자열을 (디바이스 코드, 선두번호)로 파싱.

    X/Y/B/W 등은 번호를 16진수로 해석하고(예: "X10" → 16), D/M/L 등은
    10진수로 해석한다(예: "D100" → 100). 알 수 없는 접두어/번호는 ValueError.
    """
    s = device.strip().upper()
    if not s:
        raise ValueError("빈 디바이스 문자열")

    # 가장 긴 접두어부터 매칭(예: "SM","CS" 가 "S","C" 보다 우선).
    prefix = ""
    for cand in sorted(DEVICE_CODES, key=len, reverse=True):
        if s.startswith(cand):
            prefix = cand
            break
    if not prefix:
        raise ValueError(f"알 수 없는 디바이스 접두어: {device!r}")

    num_part = s[len(prefix):]
    if not num_part:
        raise ValueError(f"디바이스 번호 없음: {device!r}")
    base = 16 if prefix in _HEX_DEVICES else 10
    try:
        head = int(num_part, base)
    except ValueError as exc:
        raise ValueError(f"잘못된 디바이스 번호: {device!r}") from exc
    if head < 0 or head > 0xFFFFFF:
        raise ValueError(f"디바이스 번호 범위 초과: {device!r}")
    return DEVICE_CODES[prefix], head


# --------------------------------------------------------------------------- #
# 순수 stdlib MC 프로토콜 3E 바이너리 클라이언트                                #
# --------------------------------------------------------------------------- #
class _Mc3eBinary:
    """최소 MC 프로토콜 3E 바이너리 클라이언트.

    비트/워드 일괄 읽기·쓰기(0x0401/0x1401, 서브 0x0001/0x0000)를 지원.
    """

    def __init__(
        self,
        host: str,
        port: int = 5007,
        timeout: float = 3.0,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._sock: socket.socket | None = None

    # -- 연결 관리 --------------------------------------------------------- #
    def _connect(self) -> socket.socket:
        if self._sock is None:
            sock = socket.create_connection(
                (self._host, self._port), timeout=self._timeout
            )
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
    @staticmethod
    def _build_request(request_data: bytes) -> bytes:
        """요청 데이터(커맨드 이후)에 3E 헤더를 붙여 완성된 프레임을 만든다.

        요청 데이터 길이 = 모니터링 타이머(2) + request_data 길이.
        """
        length = 2 + len(request_data)
        # subheader(BE) + net + pc + io(LE) + station + len(LE) + timer(LE)
        header = struct.pack(
            ">H", _SUBHEADER_REQUEST
        ) + struct.pack(
            "<BBHBHH",
            _NETWORK_NO,
            _PC_NO,
            _DEST_MODULE_IO,
            _DEST_STATION,
            length,
            _MONITORING_TIMER,
        )
        return header + request_data

    def _recv_exact(self, sock: socket.socket, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise MelsecError("connection closed by peer")
            buf.extend(chunk)
        return bytes(buf)

    def _transaction(self, request_data: bytes) -> bytes:
        """요청 데이터를 보내고, 응답의 (종료코드 이후) 데이터부를 돌려준다.

        종료코드가 0 이 아니면 :class:`MelsecEndCodeError` 를 발생시킨다.
        """
        sock = self._connect()
        sock.sendall(self._build_request(request_data))

        header = self._recv_exact(sock, _RESP_HEADER_LEN)
        subheader = struct.unpack(">H", header[0:2])[0]
        if subheader != _SUBHEADER_RESPONSE:
            raise MelsecError(
                f"bad response subheader: 0x{subheader:04X}"
            )
        resp_len = struct.unpack("<H", header[7:9])[0]
        if resp_len < 2:
            raise MelsecError(f"invalid response data length: {resp_len}")
        body = self._recv_exact(sock, resp_len)
        end_code = struct.unpack("<H", body[0:2])[0]
        if end_code != 0x0000:
            raise MelsecEndCodeError(end_code)
        return body[2:]

    # -- 요청 데이터 빌더 -------------------------------------------------- #
    @staticmethod
    def _request_prefix(
        command: int,
        subcommand: int,
        device_code: int,
        head: int,
        count: int,
    ) -> bytes:
        """커맨드/서브커맨드/디바이스 지정부를 만든다.

        head 는 3바이트 LE, count 는 2바이트 LE.
        """
        head_le = struct.pack("<I", head)[:3]  # 하위 3바이트만
        return (
            struct.pack("<HH", command, subcommand)
            + struct.pack("<B", device_code)
            + head_le
            + struct.pack("<H", count)
        )

    # -- 공개 메서드 ------------------------------------------------------- #
    def read_bits(self, device: str, count: int) -> list[bool]:
        """비트 일괄 읽기(0x0401, 서브 0x0001)."""
        if not (1 <= count <= _MAX_POINTS):
            raise ValueError(f"count out of range: {count}")
        code, head = parse_device(device)
        req = self._request_prefix(
            _CMD_BATCH_READ, _SUBCMD_BIT, code, head, count
        )
        data = self._transaction(req)
        return unpack_bits_nibble(data, count)

    def write_bits(self, device: str, vals: Sequence[bool]) -> None:
        """비트 일괄 쓰기(0x1401, 서브 0x0001)."""
        count = len(vals)
        if not (1 <= count <= _MAX_POINTS):
            raise ValueError(f"count out of range: {count}")
        code, head = parse_device(device)
        req = self._request_prefix(
            _CMD_BATCH_WRITE, _SUBCMD_BIT, code, head, count
        ) + pack_bits_nibble(vals)
        self._transaction(req)

    def read_words(self, device: str, count: int) -> list[int]:
        """워드 일괄 읽기(0x0401, 서브 0x0000)."""
        if not (1 <= count <= _MAX_POINTS):
            raise ValueError(f"count out of range: {count}")
        code, head = parse_device(device)
        req = self._request_prefix(
            _CMD_BATCH_READ, _SUBCMD_WORD, code, head, count
        )
        data = self._transaction(req)
        if len(data) < count * 2:
            raise MelsecError("short word-read response")
        return [
            struct.unpack_from("<H", data, i * 2)[0] for i in range(count)
        ]

    def write_words(self, device: str, vals: Sequence[int]) -> None:
        """워드 일괄 쓰기(0x1401, 서브 0x0000)."""
        count = len(vals)
        if not (1 <= count <= _MAX_POINTS):
            raise ValueError(f"count out of range: {count}")
        code, head = parse_device(device)
        payload = b"".join(struct.pack("<H", v & 0xFFFF) for v in vals)
        req = self._request_prefix(
            _CMD_BATCH_WRITE, _SUBCMD_WORD, code, head, count
        ) + payload
        self._transaction(req)


# --------------------------------------------------------------------------- #
# 심볼 ↔ MELSEC 디바이스 매핑                                                   #
# --------------------------------------------------------------------------- #
@dataclass
class MelsecMap:
    """심볼 ↔ MELSEC 디바이스 매핑(비트 디바이스).

    inputs:  쓰기 대상 심볼 → 비트 디바이스 문자열(예: "M0").
    outputs: 읽기 대상 심볼 → 비트 디바이스 문자열(예: "M16").
    """

    inputs: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)

    @classmethod
    def default_on_m_bits(
        cls,
        input_symbols: Sequence[str],
        output_symbols: Sequence[str],
        input_base: int = 0,
        output_base: int = 1000,
    ) -> MelsecMap:
        """정렬된 심볼 목록으로부터 기본 맵을 M 비트 위에 만든다.

        입력 심볼 → M{input_base}, M{input_base+1}, ...
        출력 심볼 → M{output_base}, M{output_base+1}, ...
        (입출력 영역이 겹치지 않도록 기본 베이스를 분리.)
        """
        inputs = {
            sym: f"M{input_base + i}"
            for i, sym in enumerate(sorted(input_symbols))
        }
        outputs = {
            sym: f"M{output_base + i}"
            for i, sym in enumerate(sorted(output_symbols))
        }
        return cls(inputs=inputs, outputs=outputs)


# --------------------------------------------------------------------------- #
# PlcLink 구현                                                                  #
# --------------------------------------------------------------------------- #
class MelsecPlcLink:
    """``PlcLink`` 를 만족하는 MC 프로토콜 3E 바이너리 어댑터.

    write_inputs: 입력 심볼 값을 비트 디바이스에 일괄 쓰기(0x1401)로 강제.
    read_outputs: 출력 심볼을 비트 디바이스에서 일괄 읽기(0x0401)로 읽음.
    """

    def __init__(
        self,
        host: str,
        port: int = 5007,
        melsec_map: MelsecMap | None = None,
        timeout: float = 3.0,
    ) -> None:
        self._map = melsec_map if melsec_map is not None else MelsecMap()
        self._client = _Mc3eBinary(host, port, timeout=timeout)

    def write_inputs(self, values: dict[str, bool]) -> None:
        """입력 심볼 값을 PLC 비트 디바이스에 쓴다.

        매핑에 없는 심볼은 :class:`WriteRejected` 로 거부한다(오타/이중코일 방지).
        디바이스마다 1점씩 개별 비트 일괄쓰기로 쓴다(주소 불연속 안전).
        """
        if not values:
            return
        unknown = sorted(set(values) - set(self._map.inputs))
        if unknown:
            raise WriteRejected(f"미매핑 입력 심볼: {', '.join(unknown)}")

        for sym in sorted(values):
            device = self._map.inputs[sym]
            self._client.write_bits(device, [bool(values[sym])])

    def read_outputs(self) -> dict[str, bool]:
        """PLC 출력 심볼 값을 읽어 심볼→BOOL 사전으로 반환한다."""
        outputs = self._map.outputs
        if not outputs:
            return {}
        result: dict[str, bool] = {}
        for sym, device in outputs.items():
            bits = self._client.read_bits(device, 1)
            result[sym] = bits[0]
        return result

    def close(self) -> None:
        """링크를 닫는다(멱등)."""
        self._client.close()


# --------------------------------------------------------------------------- #
# 테스트용 인프로세스 MC 프로토콜 3E 슬레이브                                    #
# --------------------------------------------------------------------------- #
class _DeviceImage:
    """디바이스별 비트 이미지(스레드 안전).

    (디바이스 코드, 번호) → BOOL. 미설정 비트는 OFF 로 본다.
    """

    def __init__(self) -> None:
        self._bits: dict[tuple[int, int], bool] = {}
        self.lock = threading.Lock()

    def read_bits(self, code: int, head: int, count: int) -> list[bool]:
        with self.lock:
            return [
                self._bits.get((code, head + i), False) for i in range(count)
            ]

    def write_bits(
        self, code: int, head: int, values: Sequence[bool]
    ) -> None:
        with self.lock:
            for i, v in enumerate(values):
                self._bits[(code, head + i)] = bool(v)


class _Mc3eRequestHandler(socketserver.BaseRequestHandler):
    """단일 연결에서 여러 3E 바이너리 트랜잭션을 처리한다(비트 일괄 읽기/쓰기)."""

    server: MockMelsecServer

    def handle(self) -> None:
        sock = self.request
        while True:
            head = self._recv_exact(sock, _REQ_HEADER_LEN)
            if head is None:
                return
            subheader = struct.unpack(">H", head[0:2])[0]
            req_len = struct.unpack("<H", head[7:9])[0]
            # 요청 데이터 길이는 모니터링 타이머(2)를 포함 → 나머지 = req_len-2.
            body = self._recv_exact(sock, req_len - 2)
            if body is None:
                return
            if subheader != _SUBHEADER_REQUEST:
                return
            resp = self._dispatch(body)
            try:
                sock.sendall(resp)
            except OSError:
                return

    @staticmethod
    def _recv_exact(sock: socket.socket, n: int) -> bytes | None:
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)

    @staticmethod
    def _response(end_code: int, data: bytes = b"") -> bytes:
        body = struct.pack("<H", end_code) + data
        length = len(body)
        header = struct.pack(">H", _SUBHEADER_RESPONSE) + struct.pack(
            "<BBHBH",
            _NETWORK_NO,
            _PC_NO,
            _DEST_MODULE_IO,
            _DEST_STATION,
            length,
        )
        return header + body

    def _dispatch(self, body: bytes) -> bytes:
        image = self.server.image
        try:
            command, subcommand = struct.unpack_from("<HH", body, 0)
            device_code = body[4]
            head = int.from_bytes(body[5:8], "little")
            count = struct.unpack_from("<H", body, 8)[0]
        except (struct.error, IndexError):
            return self._response(0xC059)  # 커맨드/디바이스 지정 오류

        if subcommand != _SUBCMD_BIT:
            # 이 목 슬레이브는 비트 일괄만 지원.
            return self._response(0xC05C)

        if command == _CMD_BATCH_READ:
            if not (1 <= count <= _MAX_POINTS):
                return self._response(0xC056)  # 점수 범위 초과
            bits = image.read_bits(device_code, head, count)
            return self._response(0x0000, pack_bits_nibble(bits))

        if command == _CMD_BATCH_WRITE:
            if not (1 <= count <= _MAX_POINTS):
                return self._response(0xC056)
            data = body[10:]
            bits = unpack_bits_nibble(data, count)
            image.write_bits(device_code, head, bits)
            return self._response(0x0000)

        return self._response(0xC059)  # 미지원 커맨드


class MockMelsecServer(socketserver.ThreadingTCPServer):
    """인프로세스 MC 프로토콜 3E 바이너리 슬레이브(테스트용). 컨텍스트 매니저.

    비트 일괄 읽기/쓰기(0x0401/0x1401, 서브 0x0001)를 지원하며 디바이스 비트
    이미지를 보유한다. 에페메럴 포트(port=0)로 시작하고 ``host``/``port`` 로
    접속 주소를 노출한다.
    """

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.image = _DeviceImage()
        super().__init__((host, port), _Mc3eRequestHandler)
        self._thread: threading.Thread | None = None

    @property
    def host(self) -> str:
        return str(self.server_address[0])

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    def start(self) -> None:
        """백그라운드 스레드에서 서버를 구동한다."""
        if self._thread is None:
            self._thread = threading.Thread(
                target=self.serve_forever, daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        """서버를 정지하고 소켓을 해제한다(멱등)."""
        if self._thread is not None:
            self.shutdown()
            self._thread.join(timeout=5.0)
            self._thread = None
        self.server_close()

    def __enter__(self) -> MockMelsecServer:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()
