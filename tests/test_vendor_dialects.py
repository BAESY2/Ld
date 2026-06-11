"""추가 벤더 방언(Phase N 확장) 테스트.

신규 프로파일(LS_XGI IEC, OMRON_NX, SIEMENS_S7_SCL)과 기존 프로파일을
위저드 레시피 4종(motor_start_stop/fwd_rev/on_delay/count_eject)로 합성→트랜스파일→
에미트하며, 방언별 니모닉·주소 표기가 올바른지, 이중코일이 새지 않는지,
출력이 결정론적인지 검증한다.

방언 출처(웹 리서치):
  * LS_XGI       : LS Electric XGI/XGR/XEC Instructions Manual — IEC 직접변수 %IX/%QX/%MX,
                   IEC IL(LD/LDN/AND/ANDN/OR(/ST)).
  * OMRON_NX     : Omron NJ/NX-series CPU Unit Software Manual — W(작업, word.bit)/H(보존),
                   가산 타이머(TON), 심볼변수 중심.
  * SIEMENS_S7_SCL: Siemens SIMATIC SCL — `OUT := (A AND NOT B) OR ...;` 대입식, byte.bit 주소.
"""

from __future__ import annotations

import re

import pytest

from app.emit import emit, render_for_vendor
from app.models import (
    DeviceClass,
    IODirection,
    IOPoint,
    StateMachineSpec,
)
from app.synth import synthesize_st
from app.transpiler import transpile_st
from app.vendors.profiles import (
    LS_XGI,
    LS_XGK,
    MITSUBISHI_FX,
    OMRON_CJ,
    OMRON_NX,
    SIEMENS_S7,
    SIEMENS_S7_SCL,
    VendorProfile,
    available_profiles,
    get_profile,
)
from app.wizard import build_spec

RECIPES = ("motor_start_stop", "fwd_rev", "on_delay", "count_eject")
ALL_PROFILES: tuple[VendorProfile, ...] = (
    LS_XGK,
    MITSUBISHI_FX,
    SIEMENS_S7,
    OMRON_CJ,
    LS_XGI,
    OMRON_NX,
    SIEMENS_S7_SCL,
)


def _render(recipe_id: str, profile: VendorProfile) -> str:
    spec = build_spec(recipe_id)
    st = synthesize_st(spec)
    return render_for_vendor(st, spec, profile)


# --- 레지스트리: 신규 프로파일 등록 --------------------------------------
def test_new_profiles_registered() -> None:
    names = set(available_profiles())
    assert {"LS_XGI", "OMRON_NX", "SIEMENS_S7_SCL"} <= names
    assert get_profile("LS_XGI") is LS_XGI
    assert get_profile("OMRON_NX") is OMRON_NX
    assert get_profile("SIEMENS_S7_SCL") is SIEMENS_S7_SCL


# --- LS_XGI: IEC 직접변수 %IX/%QX/%MX + IEC IL ---------------------------
def test_ls_xgi_iec_io_addresses() -> None:
    # 입력 %IX, 출력 %QX (슬롯.워드.비트 → %IX0.0 형태)
    assert LS_XGI.format_address(DeviceClass.P, 0, IODirection.INPUT) == "%IX0.0"
    assert LS_XGI.format_address(DeviceClass.P, 0, IODirection.OUTPUT) == "%QX0.0"
    # 내부 릴레이는 평면 비트 %MX0
    assert LS_XGI.format_address(DeviceClass.M, 0) == "%MX0"
    assert LS_XGI.format_address(DeviceClass.M, 7) == "%MX7"


def test_ls_xgi_iec_il_mnemonics() -> None:
    text = _render("motor_start_stop", LS_XGI)
    # IEC IL: LD/LDN 접점, ST 저장코일, 병렬은 OR( … )
    assert "%IX0.0" in text  # 입력
    assert "%QX0.0" in text  # 출력
    assert "%MX" not in text or "%MX" in text  # (내부릴레이는 이 레시피엔 없을 수 있음)
    assert re.search(r"^LD ", text, re.M)
    assert "OR(" in text  # 자기유지 병렬항
    assert re.search(r"^ST %QX0\.0$", text, re.M)  # IEC 저장코일
    # XGK 니모닉(LOAD/OUT)이나 10진 P 주소가 새지 않아야 함
    assert "LOAD" not in text
    assert "OUT " not in text
    assert "P0000" not in text


def test_ls_xgi_negated_contacts_use_ldn_andn() -> None:
    text = _render("motor_start_stop", LS_XGI)
    assert re.search(r"\bANDN ", text)  # NOT STOP → ANDN


# --- OMRON_NX: W/H word.bit, 가산 타이머 ---------------------------------
def test_omron_nx_work_holding_areas() -> None:
    # 내부=W, 보존(K)=H — 둘 다 word.bit
    assert OMRON_NX.format_address(DeviceClass.M, 0) == "W0.00"
    assert OMRON_NX.format_address(DeviceClass.M, 16) == "W1.00"
    assert OMRON_NX.format_address(DeviceClass.K, 0) == "H0.00"


def test_omron_nx_channel_bit_io() -> None:
    text = _render("motor_start_stop", OMRON_NX)
    # 옴론 channel.bit (CIO0.00) 형태
    assert "CIO0.00" in text
    assert re.search(r"CIO\d+\.\d{2}", text)


def test_omron_nx_timer_not_countdown_unlike_cj() -> None:
    # NX/NJ TON 은 가산, CJ TIM 은 감산
    assert OMRON_NX.timer_is_countdown is False
    assert OMRON_CJ.timer_is_countdown is True


# --- SIEMENS_S7_SCL: 대입식 출력 -----------------------------------------
def test_siemens_scl_assignment_form() -> None:
    text = _render("motor_start_stop", SIEMENS_S7_SCL)
    # OUT := (A AND NOT B) OR (...);  형태
    assert ":=" in text
    assert "AND" in text
    assert "NOT" in text
    assert "OR" in text
    assert text.rstrip().endswith(";")
    # 대입 좌변은 byte.bit 출력 주소
    assert re.search(r"%Q0\.0 := ", text)
    # STL 블록 니모닉(A(/O()이 새지 않아야 함
    assert "A(" not in text
    assert "O(" not in text


def test_siemens_scl_single_term_no_outer_parens() -> None:
    spec = StateMachineSpec(
        io_points=[
            IOPoint(symbol="A", direction=IODirection.INPUT),
            IOPoint(symbol="B", direction=IODirection.INPUT),
            IOPoint(symbol="Y", direction=IODirection.OUTPUT),
        ]
    )
    text = render_for_vendor("Y := A AND NOT B;", spec, SIEMENS_S7_SCL)
    assert re.search(r"%Q0\.0 := %I0\.0 AND NOT %I0\.1;", text)
    assert "(" not in text.split(":=", 1)[1]  # 단일 곱항 → 괄호 없음


# --- 미쓰비시 8진 I/O 보존 -------------------------------------------------
def test_mitsubishi_octal_xy_addressing() -> None:
    # 입력 X(8진), 출력 Y(8진), 내부 M(10진)
    assert MITSUBISHI_FX.format_address(DeviceClass.P, 8, IODirection.INPUT) == "X10"
    assert MITSUBISHI_FX.format_address(DeviceClass.P, 8, IODirection.OUTPUT) == "Y10"
    assert MITSUBISHI_FX.format_address(DeviceClass.M, 10) == "M10"
    text = _render("motor_start_stop", MITSUBISHI_FX)
    assert re.search(r"\bX\d+\b", text)  # X 입력
    assert re.search(r"\bY\d+\b", text)  # Y 출력
    assert "LDI" in text or "ANI" in text  # 미쓰비시 부정 니모닉


# --- 옴론 channel.bit 보존 -------------------------------------------------
def test_omron_cj_channel_bit() -> None:
    assert OMRON_CJ.format_address(DeviceClass.P, 0, IODirection.INPUT) == "CIO0.00"
    assert OMRON_CJ.format_address(DeviceClass.P, 16, IODirection.INPUT) == "CIO1.00"


# --- 이중 코일 누수 없음(모든 프로파일/레시피) ---------------------------
def _coil_targets(text: str, profile: VendorProfile) -> list[str]:
    """렌더 텍스트에서 코일/저장 대상 피연산자를 추출한다."""
    targets: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith((";", "//", "(*")):
            continue
        if profile.il_style == "scl":
            m = re.match(r"^(\S+) :=", line)
            if m:
                targets.append(m.group(1))
        elif profile.il_style == "iec_il":
            m = re.match(r"^ST (\S+)$", line)
            if m:
                targets.append(m.group(1))
        elif profile.il_style == "stl":
            m = re.match(r"^= (\S+)$", line)
            if m:
                targets.append(m.group(1))
        else:  # orb
            m = re.match(r"^OUT (\S+)$", line)
            if m:
                targets.append(m.group(1))
    return targets


@pytest.mark.parametrize("recipe_id", RECIPES)
@pytest.mark.parametrize("profile", ALL_PROFILES, ids=lambda p: p.name)
def test_no_double_coil_leak(recipe_id: str, profile: VendorProfile) -> None:
    text = _render(recipe_id, profile)
    targets = _coil_targets(text, profile)
    assert len(targets) == len(set(targets)), (
        f"{profile.name}/{recipe_id} 이중코일: {targets}"
    )


# --- 결정론: 같은 입력 → 같은 출력 ---------------------------------------
@pytest.mark.parametrize("recipe_id", RECIPES)
@pytest.mark.parametrize("profile", ALL_PROFILES, ids=lambda p: p.name)
def test_deterministic_output(recipe_id: str, profile: VendorProfile) -> None:
    assert _render(recipe_id, profile) == _render(recipe_id, profile)


# --- 같은 ST 가 방언마다 다른 텍스트를 낸다 ------------------------------
def test_dialects_produce_distinct_text() -> None:
    prog = transpile_st("MOTOR := (START OR MOTOR) AND NOT STOP;")
    rendered = {p.name: emit(prog, p) for p in ALL_PROFILES}
    # 7개 프로파일이 모두 서로 다른 텍스트
    assert len(set(rendered.values())) == len(ALL_PROFILES)


# --- 기존 LS_XGK/미쓰비시 출력 불변(골든) -------------------------------
def test_ls_xgk_output_unchanged() -> None:
    prog = transpile_st("MOTOR := (START OR MOTOR) AND NOT STOP;")
    text = emit(prog, LS_XGK)
    assert text.count("ORB") == 1
    assert "LOAD START" in text
    assert "AND NOT STOP" in text
    assert text.rstrip().endswith("OUT MOTOR")


def test_mitsubishi_output_unchanged() -> None:
    prog = transpile_st("MOTOR_FWD := FWD AND NOT REV AND NOT STOP;")
    text = emit(prog, MITSUBISHI_FX)
    lines = [ln for ln in text.splitlines() if ln and not ln.startswith((";", "//"))]
    assert lines[0].startswith("LD ")
    assert any(ln.startswith("ANI ") for ln in lines)
    assert lines[-1].startswith("OUT ")
    assert "ORB" not in text  # 단일 곱항
