"""디지털-트윈 차분 검증(differential testing) — 우리 스캔 시뮬레이터 vs 외부 IEC 런타임.

'무결점 검증'을 자기검증에서 *외부검증*으로 승격한다. 동일한 입력 타임라인을
(a) 우리 결정론 시뮬레이터 ``simulate()`` 와 (b) 외부 PLC(OpenPLC)에 *동시에* 가해
출력 트레이스를 샘플 단위로 대조한다. 두 독립 구현이 일치하면 신뢰도가 급상승하고,
어긋나면 정확히 어디서 갈라졌는지(t_ms·심볼·양쪽 값)를 보고한다.

설계 원칙(파일 소유권/병렬 개발):
  * 통신은 ``app.comms.protocols.PlcLink`` Protocol 한 가지에만 의존한다.
    modbus_tcp 모듈(병렬 작성 중)은 **import 하지 않는다**.
  * CI 는 하드웨어/네트워크 없이 통과해야 하므로, 우리 시뮬레이터로 뒷받침되는
    ``SimBackedLink`` 를 제공해 차분 머신을 키 없이 검증한다(반드시 simulate() 와 일치).
  * 실 OpenPLC 경로는 ``link_factory`` 주입 seam 또는 stdlib 소켓 기반 *인라인*
    최소 Modbus 클라이언트로 분리하고, 환경변수 ``OPENPLC_HOST`` 가 있을 때만 쓴다.

실 PLC 는 비동기 스캔(자체 주기)으로 돈다. 우리는 매 step 마다 입력을 쓰고
``settle_hook`` 으로 안정화를 기다린 뒤 출력을 읽는 '쓰기→정착→읽기' 표본화를
가정한다(이 가정은 ``DiffReport.notes`` 와 본 docstring 에 명시한다).
"""

from __future__ import annotations

import os
import socket
import struct
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.comms.protocols import PlcLink
from app.models import IODirection, StateMachineSpec
from app.simulator import simulate

# 입력 타임라인 한 점: (t_ms, {입력심볼: 값})
InputsTimeline = list[tuple[int, dict[str, bool]]]
# 안정화 훅: 외부 PLC 가 입력을 반영해 한 스캔 이상 돌도록 대기(테스트는 no-op).
SettleHook = Callable[[], None]


@dataclass(frozen=True)
class Mismatch:
    """한 표본에서 한 심볼의 시뮬레이터-PLC 불일치."""

    t_ms: int
    symbol: str
    sim_val: bool
    plc_val: bool


@dataclass(frozen=True)
class DiffReport:
    """차분 검증 결과(결정론적·직렬화 친화).

    agreement:  모든 표본·모든 출력에서 두 구현이 일치하는가.
    mismatches: 불일치 목록(t_ms→symbol 정렬, 결정론적).
    outputs:    대조한 출력 심볼(정렬).
    n_samples:  비교한 표본 수.
    summary:    사람이 읽는 한 줄 요약(결정론적).
    notes:      표본화 가정 등 메타.
    """

    agreement: bool
    mismatches: tuple[Mismatch, ...]
    outputs: tuple[str, ...]
    n_samples: int
    summary: str
    notes: tuple[str, ...] = ()

    @property
    def first_divergence(self) -> Mismatch | None:
        """가장 이른(t_ms, symbol) 불일치(있으면). 디버깅 진입점."""
        return self.mismatches[0] if self.mismatches else None


_SAMPLING_NOTE = (
    "표본화 가정: 매 step 마다 write_inputs → settle_hook() → read_outputs "
    "(쓰기→정착→읽기). 실 PLC 는 비동기 스캔이므로 settle 로 1스캔 이상 안정화를 가정."
)


def run_differential(
    st_code: str,
    spec: StateMachineSpec | None,
    link: PlcLink,
    inputs_timeline: InputsTimeline,
    *,
    duration_ms: int,
    step_ms: int = 100,
    settle_hook: SettleHook | None = None,
) -> DiffReport:
    """우리 simulate() 와 외부 PLC(``link``)를 동일 타임라인으로 구동·대조한다.

    1) 우리 시뮬레이터로 ground-truth 트레이스를 얻는다(결정론).
    2) 동일한 step 격자에서 외부 PLC 에 그 시각의 입력을 쓰고(write_inputs),
       settle_hook 으로 안정화한 뒤 출력을 읽어(read_outputs) 표본을 만든다.
    3) 두 트레이스를 (t_ms, 출력심볼) 단위로 비교한다.

    ``spec`` 은 비교 대상 출력 심볼을 한정하는 데 쓴다(없으면 시뮬레이터가 구동하는
    출력 전체를 비교). 반환 ``DiffReport`` 는 결정론적이다(정렬된 불일치·요약).
    """
    sim = simulate(st_code, inputs_timeline, duration_ms=duration_ms, step_ms=step_ms)

    if spec is not None:
        spec_outs = {
            io.symbol for io in spec.io_points if io.direction == IODirection.OUTPUT
        }
        compare_outputs = sorted(o for o in sim.outputs if o in spec_outs)
    else:
        compare_outputs = sorted(sim.outputs)

    # 입력 타임라인을 step 격자에 맞춰 현재값으로 펼친다(시뮬레이터와 동일 의미론).
    timeline = sorted(inputs_timeline, key=lambda x: x[0])
    settle = settle_hook or (lambda: None)

    mismatches: list[Mismatch] = []
    cur_inputs: dict[str, bool] = {s: False for s in sim.inputs}
    ti = 0
    for sample in sim.samples:
        t = sample.t_ms
        while ti < len(timeline) and timeline[ti][0] <= t:
            cur_inputs.update(timeline[ti][1])
            ti += 1
        # 외부 PLC: 쓰기 → 정착 → 읽기
        link.write_inputs({s: cur_inputs.get(s, False) for s in sim.inputs})
        settle()
        plc_outputs = link.read_outputs()
        for sym in compare_outputs:
            sim_val = bool(sample.outputs.get(sym, False))
            plc_val = bool(plc_outputs.get(sym, False))
            if sim_val != plc_val:
                mismatches.append(Mismatch(t, sym, sim_val, plc_val))

    mismatches.sort(key=lambda m: (m.t_ms, m.symbol))
    agreement = not mismatches
    n_samples = len(sim.samples)
    if agreement:
        summary = (
            f"AGREE: {n_samples}개 표본 × {len(compare_outputs)}개 출력 전부 일치."
        )
    else:
        first = mismatches[0]
        summary = (
            f"DIVERGE: 불일치 {len(mismatches)}건 / {n_samples}표본. "
            f"최초 t={first.t_ms}ms {first.symbol} "
            f"(sim={first.sim_val}, plc={first.plc_val})."
        )
    return DiffReport(
        agreement=agreement,
        mismatches=tuple(mismatches),
        outputs=tuple(compare_outputs),
        n_samples=n_samples,
        summary=summary,
        notes=(_SAMPLING_NOTE,),
    )


# 강제 불일치 주입기: (t_ms, 출력심볼, 시뮬출력값) → 반환할 PLC 값.
FaultFn = Callable[[int, str, bool], bool]


class SimBackedLink:
    """우리 시뮬레이터로 뒷받침되는 ``PlcLink`` — CI 에서 차분 머신을 키 없이 검증.

    OpenPLC 가 없어도 ``run_differential`` 을 돌릴 수 있도록, 같은 ST 를 같은 step 으로
    *우리* 시뮬레이터로 미리 가동해 step 별 출력 표를 만들어 둔다. write_inputs/
    read_outputs 가 그 표를 step 순서대로 재생한다. 결함을 주입하지 않으면 정의상
    simulate() 와 **완전히 일치**하므로 차분 머신의 무결성(거짓 불일치 0)을 보증한다.

    fault 를 주입하면(예: 한 출력을 한 시점에 뒤집기) read_outputs 가 그 시점에서
    어긋난 값을 돌려준다 → 차분 머신이 *실제로* 발산을 잡아내는지 증명한다.
    """

    def __init__(
        self,
        st_code: str,
        inputs_timeline: InputsTimeline,
        *,
        duration_ms: int,
        step_ms: int = 100,
        fault: FaultFn | None = None,
    ) -> None:
        self._result = simulate(
            st_code, inputs_timeline, duration_ms=duration_ms, step_ms=step_ms
        )
        self._fault = fault
        self._step = 0  # write_inputs 가 0,1,2,... 로 전진(read 가 같은 step 을 본다)
        self._closed = False

    def write_inputs(self, values: dict[str, bool]) -> None:  # noqa: ARG002
        # 입력은 미리 가동된 표가 이미 반영하고 있으므로, 여기서는 step 만 전진한다.
        # (실 PLC 의 입력 강제 의미론을 흉내내되, 결정론을 위해 표를 신뢰한다.)
        if self._closed:
            raise RuntimeError("닫힌 SimBackedLink 에 write 할 수 없습니다.")

    def read_outputs(self) -> dict[str, bool]:
        if self._closed:
            raise RuntimeError("닫힌 SimBackedLink 에서 read 할 수 없습니다.")
        idx = min(self._step, len(self._result.samples) - 1)
        sample = self._result.samples[idx]
        self._step += 1
        outputs = {s: bool(sample.outputs.get(s, False)) for s in self._result.outputs}
        if self._fault is not None:
            t_ms = sample.t_ms
            outputs = {
                sym: self._fault(t_ms, sym, val) for sym, val in outputs.items()
            }
        return outputs

    def close(self) -> None:
        self._closed = True


def flip_once(symbol: str, t_ms: int) -> FaultFn:
    """특정 (symbol, t_ms) 표본에서 해당 출력을 한 번만 뒤집는 결함 주입기.

    차분 머신이 *정확히 그 한 점*의 발산을 보고하는지 테스트하는 데 쓴다.
    """

    def fault(sample_t: int, sym: str, val: bool) -> bool:
        if sym == symbol and sample_t == t_ms:
            return not val
        return val

    return fault


# ---------------------------------------------------------------------------
# 실 OpenPLC 경로 (네트워크/하드웨어) — env OPENPLC_HOST 가 있을 때만 사용.
# ---------------------------------------------------------------------------
#
# OpenPLC Modbus 슬레이브 매핑(연구 출처는 모듈 하단 주석):
#   %IX (디지털 입력)  → Discrete Inputs, function 0x02 (읽기 전용 비트)
#   %QX (디지털 출력)  → Coils,          function 0x01 읽기 / 0x05 쓰기 (비트)
#   %IW (아날로그 입력) → Input Registers, function 0x04
#   %QW/%MW (워드)     → Holding Registers, function 0x03
#   포트: TCP 502
#   비트 주소: %QX{msp}.{lsp} ↔ Modbus 데이터주소 = msp*8 + lsp (예: %QX2.6 = 22)
#
# 주의: 우리 입력 심볼은 PLC 의 %IX(디지털 입력)에, 출력 심볼은 %QX(코일)에 대응한다.
# 우리는 입력을 '강제'하기 위해, OpenPLC 가 입력 미러로 노출하는 코일/홀딩에 쓰는
# 매핑을 호출자가 ``in_addr``/``out_addr`` 로 제공하도록 한다(런타임 설정마다 다름).

_MBAP_PROTO_ID = 0  # Modbus/TCP 프로토콜 식별자(항상 0)


def _modbus_request(unit_id: int, pdu: bytes, *, tid: int = 1) -> bytes:
    """MBAP 헤더 + PDU 로 Modbus/TCP ADU 를 만든다."""
    length = len(pdu) + 1  # unit id + PDU
    header = struct.pack(">HHHB", tid, _MBAP_PROTO_ID, length, unit_id)
    return header + pdu


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Modbus 응답 도중 연결이 끊겼습니다.")
        buf.extend(chunk)
    return bytes(buf)


def _txn(sock: socket.socket, unit_id: int, pdu: bytes) -> bytes:
    """ADU 를 보내고 응답 PDU(함수코드 이후 바이트)를 돌려준다."""
    sock.sendall(_modbus_request(unit_id, pdu))
    header = _recv_exact(sock, 7)  # tid, proto, len, unit
    _, _, length, _ = struct.unpack(">HHHB", header)
    body = _recv_exact(sock, length - 1)  # PDU
    if not body:
        raise ConnectionError("빈 Modbus PDU 응답.")
    fc = body[0]
    if fc & 0x80:  # 예외 응답
        code = body[1] if len(body) > 1 else 0
        raise OSError(f"Modbus 예외 응답 fc=0x{fc:02x} code=0x{code:02x}")
    return body


class _InlineModbusLink:
    """stdlib 소켓 기반 최소 Modbus/TCP ``PlcLink`` (실 OpenPLC 전용).

    심볼→비트주소 매핑(``in_addr``: 입력 강제용 코일, ``out_addr``: 출력 코일)은
    런타임 구성에 의존하므로 호출자가 제공한다. CI 에서는 절대 인스턴스화하지 않는다
    (OPENPLC_HOST 가 있을 때만 connect_openplc 가 만든다).
    """

    def __init__(
        self,
        host: str,
        port: int,
        in_addr: dict[str, int],
        out_addr: dict[str, int],
        *,
        unit_id: int = 0,
        timeout_s: float = 3.0,
    ) -> None:
        self._in_addr = dict(in_addr)
        self._out_addr = dict(out_addr)
        self._unit = unit_id
        self._sock = socket.create_connection((host, port), timeout=timeout_s)

    def write_inputs(self, values: dict[str, bool]) -> None:
        # 입력 강제 = 입력 미러 코일에 단일 코일 쓰기(function 0x05).
        for sym, val in values.items():
            addr = self._in_addr.get(sym)
            if addr is None:
                continue
            payload = 0xFF00 if val else 0x0000
            pdu = struct.pack(">BHH", 0x05, addr, payload)
            _txn(self._sock, self._unit, pdu)

    def read_outputs(self) -> dict[str, bool]:
        # 출력 코일 읽기(function 0x01). 주소 범위를 한 번에 읽어 비트를 분배한다.
        if not self._out_addr:
            return {}
        lo = min(self._out_addr.values())
        hi = max(self._out_addr.values())
        count = hi - lo + 1
        pdu = struct.pack(">BHH", 0x01, lo, count)
        body = _txn(self._sock, self._unit, pdu)
        byte_count = body[1]
        data = body[2 : 2 + byte_count]
        result: dict[str, bool] = {}
        for sym, addr in self._out_addr.items():
            bit = addr - lo
            byte_i, bit_i = divmod(bit, 8)
            result[sym] = bool(data[byte_i] >> bit_i & 1) if byte_i < len(data) else False
        return result

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


def connect_openplc(
    host: str | None = None,
    port: int = 502,
    *,
    in_addr: dict[str, int] | None = None,
    out_addr: dict[str, int] | None = None,
    link_factory: Callable[[str, int], PlcLink] | None = None,
    unit_id: int = 0,
    timeout_s: float = 3.0,
) -> PlcLink:
    """실 OpenPLC 용 ``PlcLink`` 팩토리(thin seam).

    우선순위:
      1) ``link_factory`` 가 주어지면 그것으로 링크를 만든다(modbus_tcp 등 외부 구현
         주입 — 본 모듈은 그 구현을 import 하지 않는다).
      2) 아니면 stdlib 소켓 기반 인라인 Modbus 링크를 만든다(``in_addr``/``out_addr`` 필수).

    ``host`` 가 없으면 env ``OPENPLC_HOST`` 를 본다. 둘 다 없으면 ValueError.
    네트워크/하드웨어를 건드리는 유일한 진입점이며 CI 는 호출하지 않는다.
    """
    resolved_host = host or os.environ.get("OPENPLC_HOST")
    if not resolved_host:
        raise ValueError(
            "OpenPLC host 가 없습니다. host 인자 또는 env OPENPLC_HOST 를 설정하세요."
        )
    if link_factory is not None:
        return link_factory(resolved_host, port)
    if in_addr is None or out_addr is None:
        raise ValueError(
            "인라인 Modbus 링크에는 in_addr/out_addr (심볼→비트주소) 매핑이 필요합니다. "
            "또는 link_factory 를 주입하세요."
        )
    return _InlineModbusLink(
        resolved_host, port, in_addr, out_addr, unit_id=unit_id, timeout_s=timeout_s
    )


def linear_bit_map(symbols: Iterable[str], start: int = 0) -> dict[str, int]:
    """심볼들을 start 부터 0,1,2,... 비트주소로 선형 배치한다(기본 매핑 헬퍼).

    %QX0.0=0, %QX0.1=1, ... 순서. 실 OpenPLC 의 변수 선언 순서와 맞춰 쓰면 된다.
    """
    return {sym: start + i for i, sym in enumerate(symbols)}


# ── 연구 출처(OpenPLC Modbus 매핑) ────────────────────────────────────────────
# - thiagoralves/OpenPLC_v3 — Modbus Configuration (DeepWiki):
#     %IX→discrete inputs(FC02), %QX→coils(FC01/05), %IW→input regs(FC04),
#     %MW/%QW→holding regs(FC03). TCP 포트 502.
#     https://deepwiki.com/thiagoralves/OpenPLC_v3/3.3-modbus-configuration
# - OpenPLC Modbus 슬레이브 레퍼런스(주소 변환식 msp*8+lsp, 예 %QX2.6=coil 22):
#     https://openplcproject.github.io/reference/modbus-slave/
# - 차분 테스트(두 독립 구현 대조) 일반 패턴: McKeeman, "Differential Testing
#     for Software", Digital Technical Journal, 1998.
