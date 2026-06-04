"""벤더 래더 에미터(Phase N) 테스트.

같은 ST 가 벤더별로 다른 명령어·주소로 렌더되는지, Sum-of-Products 의
ORB/STL 블록 인코딩이 올바른지 검증한다.
"""

from __future__ import annotations

from app.emit import emit, render_for_vendor
from app.models import (
    DeviceClass,
    IODirection,
    IOPoint,
    StateMachineSpec,
)
from app.transpiler import transpile_st
from app.vendors import LS_XGK, MITSUBISHI_FX, OMRON_CJ, SIEMENS_S7


# --- 단일 곱항: ORB 없음 ---------------------------------------------------
def test_mitsubishi_single_term() -> None:
    prog = transpile_st("MOTOR_FWD := FWD AND NOT REV AND NOT STOP;")
    text = emit(prog, MITSUBISHI_FX)
    lines = [ln for ln in text.splitlines() if ln and not ln.startswith(("//", ";"))]
    # LD <first>, ANI <nc>, ANI <nc>, OUT
    assert lines[0].startswith("LD ")
    assert lines.count("ORB") == 0
    assert any(ln.startswith("ANI ") for ln in lines)
    assert lines[-1].startswith("OUT ")


# --- 두 곱항(자기유지): ORB 1회 --------------------------------------------
def test_ls_seal_in_uses_orb() -> None:
    # (START OR MOTOR) AND NOT STOP → 두 곱항
    prog = transpile_st("MOTOR := (START OR MOTOR) AND NOT STOP;")
    text = emit(prog, LS_XGK)
    assert text.count("ORB") == 1
    assert "LOAD " in text
    assert "AND NOT " in text
    assert text.rstrip().endswith("OUT MOTOR")


def test_omron_seal_in_uses_orb() -> None:
    prog = transpile_st("MOTOR := (START OR MOTOR) AND NOT STOP;")
    text = emit(prog, OMRON_CJ)
    assert text.count("ORB") == 1
    assert "LD " in text


# --- 지멘스 STL 블록 -------------------------------------------------------
def test_siemens_stl_blocks() -> None:
    prog = transpile_st("MOTOR := (START OR MOTOR) AND NOT STOP;")
    text = emit(prog, SIEMENS_S7)
    assert "A(" in text
    assert "O(" in text
    assert text.rstrip().endswith("= MOTOR")


def test_siemens_single_term_no_parens() -> None:
    prog = transpile_st("Y := A AND B;")
    text = emit(prog, SIEMENS_S7)
    assert "A(" not in text  # 단일 곱항은 괄호 없음
    assert "= Y" in text


# --- 벤더 주소가 실제로 입혀진다 ------------------------------------------
_SPEC = StateMachineSpec(
    io_points=[
        IOPoint(symbol="FWD", direction=IODirection.INPUT, device_class=DeviceClass.P),
        IOPoint(symbol="REV", direction=IODirection.INPUT, device_class=DeviceClass.P),
        IOPoint(symbol="MOTOR", direction=IODirection.OUTPUT, device_class=DeviceClass.P),
    ]
)


def test_render_for_vendor_ls_addresses() -> None:
    text = render_for_vendor("MOTOR := FWD AND NOT REV;", _SPEC, LS_XGK)
    # LS: 입출력 공용 P, 10진 4자리
    assert "P0000" in text  # FWD
    assert "P0002" in text  # MOTOR (FWD=0, REV=1, MOTOR=2)


def test_render_for_vendor_mitsubishi_addresses() -> None:
    text = render_for_vendor("MOTOR := FWD AND NOT REV;", _SPEC, MITSUBISHI_FX)
    # 미쓰비시: 입력 X, 출력 Y
    assert "X0" in text  # FWD
    assert "X1" in text  # REV
    assert "Y0" in text  # MOTOR
    assert "P0000" not in text


def test_render_for_vendor_siemens_addresses() -> None:
    text = render_for_vendor("MOTOR := FWD AND NOT REV;", _SPEC, SIEMENS_S7)
    assert "%I0.0" in text  # FWD
    assert "%Q0.0" in text  # MOTOR


def test_default_profile_is_ls() -> None:
    prog = transpile_st("Y := A;")
    assert emit(prog).startswith(";")  # LS = ORB 스타일 헤더(';')
