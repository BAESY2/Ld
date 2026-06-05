"""실기/가상 PLC 통신 계층 (Stage 3 — 다이렉트 제어 'Hands').

안전커널 통과분만 실기로 나간다: 자연어→검증→가상테스트→**안전커널**→PLC.
"""

from app.comms.protocols import PlcLink, WriteRejected

__all__ = ["PlcLink", "WriteRejected"]
