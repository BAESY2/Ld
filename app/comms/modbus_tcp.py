"""순수 표준 라이브러리 Modbus-TCP 어댑터 (Stage 3 통신 계층).

외부 의존성(pymodbus 등) 없이 ``socket``/``struct``/``socketserver`` 만으로
Modbus-TCP 마스터(클라이언트)와 테스트용 인프로세스 슬레이브를 구현한다.
``PlcLink`` 계약(app.comms.protocols)을 만족하는 :class:`ModbusPlcLink` 를 제공한다.

프레이밍 요약 (Modbus Application Protocol V1.1b3, MBAP):
    ADU = MBAP(7바이트) + PDU
    MBAP = transaction_id(2, BE) + protocol_id(2, =0) + length(2, BE) + unit_id(1)
        length = unit_id(1) + PDU 바이트 수
    PDU  = function_code(1) + data...
    예외응답: function_code | 0x80, 그다음 1바이트 exception code.

비트 패킹: 코일/디스크리트 입력은 LSB-first 로 바이트에 채운다.
    첫 코일 = byte0 의 bit0(0x01), 8번째 코일 = byte0 의 bit7(0x80),
    9번째 코일 = byte1 의 bit0. (Modbus 사양 §6.1/6.2)

주소 매핑(OpenPLC 관례): PLC 디지털 입력 %IX → Modbus 주소 0..,
출력 %QX → Modbus 주소 0... 디스크리트 입력은 읽기 전용이므로 입력을
"강제(force)" 하려면 코일(FC05/0F)에 써야 한다 — 기본 맵은 양쪽 모두 코일.
"""

from __future__ import annotations

import socket
import socketserver
import struct
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.comms.protocols import WriteRejected

__all__ = [
    "AddressMap",
    "ModbusError",
    "ModbusExceptionError",
    "ModbusPlcLink",
    "MockModbusServer",
    "OutputKind",
    "WriteRejected",
]

OutputKind = Literal["coil", "discrete"]

# Modbus function codes
_FC_READ_COILS = 0x01
_FC_READ_DISCRETE_INPUTS = 0x02
_FC_WRITE_SINGLE_COIL = 0x05
_FC_WRITE_MULTIPLE_COILS = 0x0F

# Modbus exception codes → 사람이 읽을 메시지
_EXCEPTION_TEXT: dict[int, str] = {
    0x01: "ILLEGAL FUNCTION",
    0x02: "ILLEGAL DATA ADDRESS",
    0x03: "ILLEGAL DATA VALUE",
    0x04: "SLAVE DEVICE FAILURE",
}

_PROTOCOL_ID = 0x0000
_MBAP_LEN = 7
_COIL_ON = 0xFF00
_COIL_OFF = 0x0000
_MAX_BITS = 2000  # 사양상 FC01/02 최대 코일 수


class ModbusError(Exception):
    """Modbus 통신/프레이밍 오류(연결 끊김, 잘못된 응답 등)."""


class ModbusExceptionError(ModbusError):
    """슬레이브가 Modbus 예외응답(function|0x80)을 반환했을 때 발생."""

    def __init__(self, function_code: int, exception_code: int) -> None:
        self.function_code = function_code
        self.exception_code = exception_code
        text = _EXCEPTION_TEXT.get(exception_code, "UNKNOWN")
        super().__init__(
            f"Modbus exception 0x{exception_code:02X} ({text}) "
            f"for function 0x{function_code:02X}"
        )


# --------------------------------------------------------------------------- #
# 비트 패킹 헬퍼 (LSB-first)                                                    #
# --------------------------------------------------------------------------- #
def pack_bits(values: Sequence[bool]) -> bytes:
    """BOOL 시퀀스를 LSB-first 바이트열로 패킹한다.

    bit i 는 byte ``i // 8`` 의 ``1 << (i % 8)`` 위치에 들어간다.
    """
    n_bytes = (len(values) + 7) // 8
    out = bytearray(n_bytes)
    for i, val in enumerate(values):
        if val:
            out[i // 8] |= 1 << (i % 8)
    return bytes(out)


def unpack_bits(data: bytes, count: int) -> list[bool]:
    """LSB-first 바이트열에서 ``count`` 개의 BOOL 을 추출한다."""
    result: list[bool] = []
    for i in range(count):
        byte = data[i // 8]
        result.append(bool((byte >> (i % 8)) & 0x01))
    return result


# --------------------------------------------------------------------------- #
# 주소 매핑                                                                     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AddressMap:
    """심볼 ↔ Modbus 주소 매핑.

    inputs:      쓰기 대상 심볼 → 코일 주소(FC05/0F 로 강제).
    outputs:     읽기 대상 심볼 → 주소(코일 FC01 또는 디스크리트 입력 FC02).
    output_kind: 출력을 읽을 때 사용할 영역("coil" 또는 "discrete").
    """

    inputs: dict[str, int] = field(default_factory=dict)
    outputs: dict[str, int] = field(default_factory=dict)
    output_kind: OutputKind = "coil"

    @classmethod
    def default_from_symbols(
        cls,
        input_symbols: Sequence[str],
        output_symbols: Sequence[str],
        output_kind: OutputKind = "coil",
    ) -> AddressMap:
        """정렬된 심볼 목록으로부터 기본 OpenPLC 맵을 만든다.

        입력 심볼은 코일 주소 0,1,2... 에, 출력 심볼은 주소 0,1,2... 에 매핑한다.
        (OpenPLC: %IX→0.., %QX→0..). 디스크리트 입력은 쓸 수 없으므로 입력은
        항상 코일에 매핑된다.
        """
        inputs = {sym: i for i, sym in enumerate(sorted(input_symbols))}
        outputs = {sym: i for i, sym in enumerate(sorted(output_symbols))}
        return cls(inputs=inputs, outputs=outputs, output_kind=output_kind)


# --------------------------------------------------------------------------- #
# 순수 stdlib Modbus-TCP 클라이언트                                            #
# --------------------------------------------------------------------------- #
class _ModbusTcp:
    """최소 Modbus-TCP 마스터(클라이언트). FC 01/02/05/0F 지원."""

    def __init__(
        self,
        host: str,
        port: int = 502,
        unit_id: int = 1,
        timeout: float = 3.0,
    ) -> None:
        self._host = host
        self._port = port
        self._unit_id = unit_id & 0xFF
        self._timeout = timeout
        self._txn = 0
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
    def _next_txn(self) -> int:
        self._txn = (self._txn + 1) & 0xFFFF
        return self._txn

    def _recv_exact(self, sock: socket.socket, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ModbusError("connection closed by peer")
            buf.extend(chunk)
        return bytes(buf)

    def _transaction(self, pdu: bytes) -> bytes:
        """PDU 를 보내고 응답 PDU 를 돌려준다. 예외응답은 파싱해 예외 발생."""
        sock = self._connect()
        txn = self._next_txn()
        length = len(pdu) + 1  # unit_id + PDU
        header = struct.pack(">HHHB", txn, _PROTOCOL_ID, length, self._unit_id)
        sock.sendall(header + pdu)

        resp_header = self._recv_exact(sock, _MBAP_LEN)
        r_txn, r_proto, r_len, r_unit = struct.unpack(">HHHB", resp_header)
        if r_txn != txn:
            raise ModbusError(f"transaction id mismatch: sent {txn}, got {r_txn}")
        if r_proto != _PROTOCOL_ID:
            raise ModbusError(f"bad protocol id: {r_proto}")
        if r_len < 1:
            raise ModbusError(f"invalid MBAP length: {r_len}")
        resp_pdu = self._recv_exact(sock, r_len - 1)
        if not resp_pdu:
            raise ModbusError("empty response PDU")

        function = resp_pdu[0]
        if function & 0x80:
            exc_code = resp_pdu[1] if len(resp_pdu) > 1 else 0
            raise ModbusExceptionError(function & 0x7F, exc_code)
        return resp_pdu

    # -- 공개 함수 코드 ---------------------------------------------------- #
    def _read_bits(self, function: int, addr: int, count: int) -> list[bool]:
        if not (1 <= count <= _MAX_BITS):
            raise ValueError(f"count out of range: {count}")
        pdu = struct.pack(">BHH", function, addr, count)
        resp = self._transaction(pdu)
        # resp = function(1) + byte_count(1) + data... — 악성/불량 PLC 응답을
        # 그대로 믿지 않는다(짧거나 byte_count 가 count 에 못 미치면 ModbusError).
        if len(resp) < 2:
            raise ModbusError("short read response (no byte count)")
        byte_count = resp[1]
        if byte_count < (count + 7) // 8:
            raise ModbusError(
                f"read byte_count={byte_count} too small for {count} bits"
            )
        data = resp[2 : 2 + byte_count]
        if len(data) != byte_count:
            raise ModbusError("short read response")
        return unpack_bits(data, count)

    def read_coils(self, addr: int, count: int) -> list[bool]:
        """FC01 — 코일 읽기."""
        return self._read_bits(_FC_READ_COILS, addr, count)

    def read_discrete_inputs(self, addr: int, count: int) -> list[bool]:
        """FC02 — 디스크리트 입력 읽기."""
        return self._read_bits(_FC_READ_DISCRETE_INPUTS, addr, count)

    def write_coil(self, addr: int, value: bool) -> None:
        """FC05 — 단일 코일 쓰기."""
        payload = _COIL_ON if value else _COIL_OFF
        pdu = struct.pack(">BHH", _FC_WRITE_SINGLE_COIL, addr, payload)
        resp = self._transaction(pdu)
        # 정상 응답은 요청 에코.
        if len(resp) < 3:
            raise ModbusError("short write_coil echo")
        r_addr = struct.unpack(">H", resp[1:3])[0]
        if r_addr != addr:
            raise ModbusError("write_coil echo address mismatch")

    def write_coils(self, addr: int, values: Sequence[bool]) -> None:
        """FC0F — 다중 코일 쓰기."""
        count = len(values)
        if not (1 <= count <= 0x07B0):
            raise ValueError(f"coil count out of range: {count}")
        data = pack_bits(values)
        pdu = struct.pack(
            ">BHHB", _FC_WRITE_MULTIPLE_COILS, addr, count, len(data)
        ) + data
        resp = self._transaction(pdu)
        if len(resp) < 5:
            raise ModbusError("short write_coils echo")
        r_addr, r_count = struct.unpack(">HH", resp[1:5])
        if r_addr != addr or r_count != count:
            raise ModbusError("write_coils echo mismatch")


# --------------------------------------------------------------------------- #
# PlcLink 구현                                                                  #
# --------------------------------------------------------------------------- #
class ModbusPlcLink:
    """``PlcLink`` 를 만족하는 Modbus-TCP 어댑터.

    write_inputs: 입력 심볼 값을 코일(FC0F, 단일이면 FC05)로 강제.
    read_outputs: 출력 심볼을 코일(FC01) 또는 디스크리트 입력(FC02)으로 읽음.
    """

    def __init__(
        self,
        host: str,
        port: int = 502,
        address_map: AddressMap | None = None,
        unit_id: int = 1,
        timeout: float = 3.0,
    ) -> None:
        self._map = address_map if address_map is not None else AddressMap()
        self._client = _ModbusTcp(host, port, unit_id=unit_id, timeout=timeout)

    def write_inputs(self, values: dict[str, bool]) -> None:
        """입력 심볼 값을 PLC 코일에 쓴다.

        매핑에 없는 심볼은 :class:`WriteRejected` 로 거부한다(이중코일/오타 방지).
        연속 주소면 한 번의 FC0F 로, 아니면 개별 FC05 로 쓴다.
        """
        if not values:
            return
        unknown = sorted(set(values) - set(self._map.inputs))
        if unknown:
            raise WriteRejected(f"미매핑 입력 심볼: {', '.join(unknown)}")

        pairs = sorted(
            ((self._map.inputs[sym], bool(val)) for sym, val in values.items()),
            key=lambda p: p[0],
        )
        addrs = [a for a, _ in pairs]
        if len(addrs) > 1 and addrs == list(range(addrs[0], addrs[0] + len(addrs))):
            self._client.write_coils(addrs[0], [v for _, v in pairs])
        else:
            for addr, val in pairs:
                self._client.write_coil(addr, val)

    def read_outputs(self) -> dict[str, bool]:
        """PLC 출력 심볼 값을 읽어 심볼→BOOL 사전으로 반환한다."""
        outputs = self._map.outputs
        if not outputs:
            return {}
        addrs = sorted(set(outputs.values()))
        lo, hi = addrs[0], addrs[-1]
        span = hi - lo + 1
        if self._map.output_kind == "discrete":
            bits = self._client.read_discrete_inputs(lo, span)
        else:
            bits = self._client.read_coils(lo, span)
        return {sym: bits[addr - lo] for sym, addr in outputs.items()}

    def close(self) -> None:
        """링크를 닫는다(멱등)."""
        self._client.close()


# --------------------------------------------------------------------------- #
# 테스트용 인프로세스 Modbus-TCP 슬레이브                                       #
# --------------------------------------------------------------------------- #
class _SlaveImage:
    """코일/디스크리트 입력 비트 이미지(스레드 안전)."""

    def __init__(self, size: int = 65536) -> None:
        self._size = size
        self.coils = bytearray(size)
        self.discrete = bytearray(size)
        self.lock = threading.Lock()

    def _read(self, mem: bytearray, addr: int, count: int) -> list[bool]:
        if addr < 0 or addr + count > self._size:
            raise IndexError
        return [bool(mem[addr + i]) for i in range(count)]

    def read_coils(self, addr: int, count: int) -> list[bool]:
        with self.lock:
            return self._read(self.coils, addr, count)

    def read_discrete(self, addr: int, count: int) -> list[bool]:
        with self.lock:
            return self._read(self.discrete, addr, count)

    def write_coil(self, addr: int, value: bool) -> None:
        with self.lock:
            if addr < 0 or addr >= self._size:
                raise IndexError
            self.coils[addr] = 1 if value else 0

    def write_coils(self, addr: int, values: Sequence[bool]) -> None:
        with self.lock:
            if addr < 0 or addr + len(values) > self._size:
                raise IndexError
            for i, v in enumerate(values):
                self.coils[addr + i] = 1 if v else 0


class _ModbusRequestHandler(socketserver.BaseRequestHandler):
    """단일 연결에서 여러 Modbus 트랜잭션을 처리한다."""

    server: MockModbusServer

    def handle(self) -> None:
        sock = self.request
        while True:
            try:
                header = self._recv_exact(sock, _MBAP_LEN)
            except (ModbusError, OSError):
                return
            if header is None:
                return
            txn, proto, length, unit = struct.unpack(">HHHB", header)
            try:
                pdu = self._recv_exact(sock, length - 1)
            except (ModbusError, OSError):
                return
            if pdu is None:
                return
            resp_pdu = self._dispatch(pdu)
            resp_len = len(resp_pdu) + 1
            out = struct.pack(">HHHB", txn, proto, resp_len, unit) + resp_pdu
            try:
                sock.sendall(out)
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

    def _exception(self, function: int, code: int) -> bytes:
        return struct.pack(">BB", function | 0x80, code)

    def _dispatch(self, pdu: bytes) -> bytes:
        function = pdu[0]
        image = self.server.image
        try:
            if function in (_FC_READ_COILS, _FC_READ_DISCRETE_INPUTS):
                addr, count = struct.unpack(">HH", pdu[1:5])
                if not (1 <= count <= _MAX_BITS):
                    return self._exception(function, 0x03)
                reader = (
                    image.read_coils
                    if function == _FC_READ_COILS
                    else image.read_discrete
                )
                bits = reader(addr, count)
                data = pack_bits(bits)
                return struct.pack(">BB", function, len(data)) + data
            if function == _FC_WRITE_SINGLE_COIL:
                addr, value = struct.unpack(">HH", pdu[1:5])
                if value not in (_COIL_ON, _COIL_OFF):
                    return self._exception(function, 0x03)
                image.write_coil(addr, value == _COIL_ON)
                return pdu  # 요청 에코
            if function == _FC_WRITE_MULTIPLE_COILS:
                addr, count, byte_count = struct.unpack(">HHB", pdu[1:6])
                data = pdu[6 : 6 + byte_count]
                bits = unpack_bits(data, count)
                image.write_coils(addr, bits)
                return struct.pack(">BHH", function, addr, count)
            return self._exception(function, 0x01)  # ILLEGAL FUNCTION
        except IndexError:
            return self._exception(function, 0x02)  # ILLEGAL DATA ADDRESS
        except struct.error:
            return self._exception(function, 0x03)  # ILLEGAL DATA VALUE


class MockModbusServer(socketserver.ThreadingTCPServer):
    """인프로세스 Modbus-TCP 슬레이브(테스트용). 컨텍스트 매니저 지원.

    에페메럴 포트(port=0)로 시작하고 ``host``/``port`` 속성으로 접속 주소를 노출.
    """

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.image = _SlaveImage()
        super().__init__((host, port), _ModbusRequestHandler)
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
            self._thread = threading.Thread(target=self.serve_forever, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """서버를 정지하고 소켓을 해제한다(멱등)."""
        if self._thread is not None:
            self.shutdown()
            self._thread.join(timeout=5.0)
            self._thread = None
        self.server_close()

    def __enter__(self) -> MockModbusServer:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()
