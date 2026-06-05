"""실기/가상 PLC 통신 계약 (Stage 3 공유 인터페이스, 벤더 무관).

모든 어댑터(Modbus/OpenPLC/LS XGT)와 안전커널은 이 최소 양방향 인터페이스
``PlcLink`` 위에서 동작한다 — 구현을 서로 모른 채 병렬 개발 가능.
심볼 수준(BOOL)으로만 주고받고, 주소 매핑은 각 어댑터 내부 책임이다.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class WriteRejected(Exception):
    """안전커널이 위험하다고 판단해 PLC 쓰기를 차단했을 때 발생.

    message 에는 차단 사유(위반 규칙·심볼)를 담아 운전자에게 노출한다.
    """


@runtime_checkable
class PlcLink(Protocol):
    """가상/실기 PLC 와의 최소 양방향 링크(BOOL 심볼 단위, 벤더 무관).

    write_inputs: 입력 심볼→값을 PLC 입력 이미지에 쓴다(예: 버튼/센서 강제).
    read_outputs: PLC 출력 이미지(코일)를 심볼→값으로 읽는다.
    close:        링크 자원을 해제한다(소켓 등).
    """

    def write_inputs(self, values: dict[str, bool]) -> None: ...

    def read_outputs(self) -> dict[str, bool]: ...

    def close(self) -> None: ...
