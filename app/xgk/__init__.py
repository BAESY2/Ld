"""LS XGK 니모닉 스캔 인터프리터 패키지.

에미터(``app.emit.ladder_il``)가 LS_XGK 프로파일로 뽑아낸 IL 니모닉 텍스트를
가상 PLC로 가동해, 검증된 ST 시뮬레이터(``app.simulator``)와 차분(differential)
대조하는 검증 코어다. 타이밍 의미론은 ST 시뮬레이터의 ``_Timer``/``_Counter`` 를
그대로 재사용해 바이트 동일성을 보장한다.
"""

from __future__ import annotations

from app.xgk.interpreter import XgkProgram, XgkResult, XgkSample, simulate_xgk

__all__ = ["XgkProgram", "XgkResult", "XgkSample", "simulate_xgk"]
