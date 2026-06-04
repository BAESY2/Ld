"""디바이스 할당기 + 이중 코일 병합 (결정론 코어, API 키 불필요).

핵심: 심볼↔주소 1:1 캐싱으로 이중 코일을 *구조적으로* 차단하고,
ST 텍스트에 남은 이중 대입은 M 릴레이로 우회 후 OR 병합한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models import DeviceClass, StateMachineSpec

# 디바이스 클래스별 주소 자릿수
_DIGIT_WIDTH: dict[DeviceClass, int] = {
    DeviceClass.P: 4,
    DeviceClass.M: 4,
    DeviceClass.T: 4,
    DeviceClass.C: 4,
    DeviceClass.L: 4,
    DeviceClass.K: 4,
    DeviceClass.D: 5,
}


class DeviceAllocator:
    """심볼 ↔ 주소 1:1 매핑. 같은 심볼은 항상 같은 주소를 돌려준다."""

    def __init__(self) -> None:
        self._symbol_to_addr: dict[str, str] = {}
        self._addr_to_symbol: dict[str, str] = {}
        self._next_index: dict[DeviceClass, int] = {dc: 0 for dc in DeviceClass}

    def _format(self, device_class: DeviceClass, index: int) -> str:
        width = _DIGIT_WIDTH[device_class]
        return f"{device_class.value}{index:0{width}d}"

    def _claim(self, symbol: str, address: str) -> None:
        owner = self._addr_to_symbol.get(address)
        if owner is not None and owner != symbol:
            raise ValueError(
                f"주소 충돌: {address} 는 이미 '{owner}' 에 할당됨 (요청 심볼='{symbol}')"
            )
        self._symbol_to_addr[symbol] = address
        self._addr_to_symbol[address] = symbol

    def allocate(
        self,
        symbol: str,
        device_class: DeviceClass,
        fixed_address: str | None = None,
    ) -> str:
        """심볼에 주소를 발급한다. 재호출 시 캐시된 주소 반환. 충돌 시 ValueError."""
        existing = self._symbol_to_addr.get(symbol)
        if existing is not None:
            if fixed_address is not None and fixed_address != existing:
                raise ValueError(
                    f"심볼 '{symbol}' 은 이미 {existing} 에 할당됨 (요청 고정주소={fixed_address})"
                )
            return existing

        if fixed_address is not None:
            self._claim(symbol, fixed_address)
            return fixed_address

        # 자동 발급: 빈 인덱스를 찾을 때까지 전진
        while True:
            addr = self._format(device_class, self._next_index[device_class])
            self._next_index[device_class] += 1
            if addr not in self._addr_to_symbol:
                self._claim(symbol, addr)
                return addr

    def allocate_internal_relay(self, hint: str) -> str:
        """우회용 M 릴레이를 새로 발급한다. hint 는 고유 심볼 생성에만 사용."""
        symbol = f"_AUX_{hint}"
        # hint 가 중복될 수 있으므로 고유해질 때까지 접미사 부여
        base = symbol
        n = 0
        while symbol in self._symbol_to_addr:
            n += 1
            symbol = f"{base}_{n}"
        return self.allocate(symbol, DeviceClass.M)

    def build_from_spec(self, spec: StateMachineSpec) -> DeviceAllocator:
        """명세의 모든 변수를 선발급한다. fixed_address 우선, 나머지는 순차."""
        # 고정 주소 먼저 점유(충돌 회피)
        for io in spec.io_points:
            if io.fixed_address is not None:
                self.allocate(io.symbol, io.device_class, io.fixed_address)
        for io in spec.io_points:
            if io.fixed_address is None:
                self.allocate(io.symbol, io.device_class)
        for t in spec.timers:
            self.allocate(t.name, DeviceClass.T)
        for c in spec.counters:
            self.allocate(c.name, DeviceClass.C)
        return self

    def address_of(self, symbol: str) -> str | None:
        return self._symbol_to_addr.get(symbol)

    def as_comment_block(self) -> str:
        """ST 상단에 붙일 맵핑 주석."""
        if not self._symbol_to_addr:
            return "// (디바이스 맵 비어있음)"
        lines = ["// === 디바이스 맵 ==="]
        for sym, addr in self._symbol_to_addr.items():
            lines.append(f"// {sym:<24} {addr}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 이중 코일 검출 / 병합
# ---------------------------------------------------------------------------
# `SYMBOL := expr;` 형태의 단순 대입문. 좌변은 식별자 1개.
_ASSIGN_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*:=\s*(.+?)\s*;\s*$")


def detect_double_coils(st_code: str) -> dict[str, list[str]]:
    """동일 좌변 심볼에 2회 이상 대입하는 경우만 {심볼: [우변식, ...]} 로 반환."""
    assigns: dict[str, list[str]] = {}
    for line in st_code.splitlines():
        m = _ASSIGN_RE.match(line)
        if not m:
            continue
        symbol, expr = m.group(1), m.group(2)
        assigns.setdefault(symbol, []).append(expr)
    return {sym: exprs for sym, exprs in assigns.items() if len(exprs) >= 2}


@dataclass
class DoubleCoilResult:
    """병합 결과."""

    code: str
    merged_symbols: list[str] = field(default_factory=list)
    aux_addresses: dict[str, list[str]] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return bool(self.merged_symbols)


def merge_double_coils(st_code: str, allocator: DeviceAllocator) -> DoubleCoilResult:
    """이중 대입을 M 릴레이로 우회한 뒤 말미에 OR 병합문을 추가한다.

    `MOTOR_FWD := A;  MOTOR_FWD := B;`
      → `M000x := A;  M000y := B;  MOTOR_FWD := M000x OR M000y;  // 이중코일 병합(OR)`
    중복이 없으면 원본을 그대로 돌려준다.
    """
    dups = detect_double_coils(st_code)
    if not dups:
        return DoubleCoilResult(code=st_code)

    # 각 중복 심볼의 출현마다 aux M 주소를 미리 발급
    occurrence_counter: dict[str, int] = {sym: 0 for sym in dups}
    aux_addresses: dict[str, list[str]] = {sym: [] for sym in dups}
    for sym in dups:
        for i in range(len(dups[sym])):
            aux = allocator.allocate_internal_relay(f"{sym}_{i}")
            aux_addresses[sym].append(aux)

    # 라인을 다시 훑으며 중복 심볼의 좌변을 aux 로 치환
    out_lines: list[str] = []
    for line in st_code.splitlines():
        m = _ASSIGN_RE.match(line)
        if m and m.group(1) in dups:
            sym = m.group(1)
            expr = m.group(2)
            idx = occurrence_counter[sym]
            occurrence_counter[sym] += 1
            aux = aux_addresses[sym][idx]
            indent = line[: len(line) - len(line.lstrip())]
            out_lines.append(f"{indent}{aux} := {expr};")
        else:
            out_lines.append(line)

    # 말미에 OR 병합문 추가
    out_lines.append("")
    out_lines.append("// 이중코일 병합(OR)")
    merged_symbols: list[str] = []
    for sym, auxes in aux_addresses.items():
        merged_symbols.append(sym)
        out_lines.append(f"{sym} := {' OR '.join(auxes)};")

    return DoubleCoilResult(
        code="\n".join(out_lines),
        merged_symbols=merged_symbols,
        aux_addresses=aux_addresses,
    )
