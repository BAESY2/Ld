"""matiec 컴파일 게이트(선택적 의존성) 테스트.

matiec(iec2c) 가 없는 환경에서도 통과해야 한다(skip 처리). 설치된 환경에서는
실제 컴파일 성공/실패를 검증한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.compile_gate import (
    CompileResult,
    compile_check,
    matiec_available,
    wrap_program,
)
from app.models import StateMachineSpec
from app.synth import synthesize_st

_GOLDEN = Path(__file__).resolve().parent / "fixtures" / "golden"


def test_matiec_available_is_bool() -> None:
    assert isinstance(matiec_available(), bool)


def test_wrap_program_structure() -> None:
    prog = wrap_program("MOTOR := (START OR MOTOR) AND NOT STOP;")
    assert "PROGRAM Main" in prog
    assert "CONFIGURATION" in prog
    # 식별자가 VAR 로 선언되고 키워드는 제외
    assert "MOTOR : BOOL;" in prog
    assert "START : BOOL;" in prog
    assert "STOP : BOOL;" in prog
    assert "AND : BOOL;" not in prog
    assert "NOT : BOOL;" not in prog


def test_compile_check_skips_gracefully_when_absent() -> None:
    result = compile_check("MOTOR := START AND NOT STOP;")
    assert isinstance(result, CompileResult)
    if not matiec_available():
        assert result.skipped is True
        assert result.ok is True  # skip 은 파이프라인을 막지 않는다


@pytest.mark.skipif(not matiec_available(), reason="matiec(iec2c) 미설치")
def test_valid_st_compiles() -> None:
    result = compile_check("MOTOR := (START OR MOTOR) AND NOT STOP;")
    assert result.ok is True
    assert result.skipped is False


@pytest.mark.skipif(not matiec_available(), reason="matiec(iec2c) 미설치")
def test_broken_st_fails_compile() -> None:
    result = compile_check("MOTOR := (START OR ;")
    assert result.ok is False


@pytest.mark.skipif(not matiec_available(), reason="matiec(iec2c) 미설치")
def test_all_golden_synth_compiles() -> None:
    for path in sorted(_GOLDEN.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        spec = StateMachineSpec(**case["spec"])
        result = compile_check(synthesize_st(spec))
        assert result.ok, f"{case['name']}: {result.message}"
