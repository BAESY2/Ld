"""벤더 프로파일(Phase L1) 테스트.

같은 명세가 벤더별로 호환 불가한 주소 모델로 렌더되는지 검증한다.
LS 기본값은 기존 동작(10진, 입출력 공용 P)을 보존해야 한다.
"""

from __future__ import annotations

from app.memory_map import DeviceAllocator
from app.models import DeviceClass, IODirection, IOPoint, StateMachineSpec
from app.vendors import (
    LS_XGK,
    MITSUBISHI_FX,
    OMRON_CJ,
    SIEMENS_S7,
    DeviceRole,
    available_profiles,
    get_profile,
    role_of,
)

_IO_SPEC = StateMachineSpec(
    io_points=[
        IOPoint(symbol="A", direction=IODirection.INPUT),
        IOPoint(symbol="B", direction=IODirection.INPUT),
        IOPoint(symbol="C", direction=IODirection.OUTPUT),
        IOPoint(symbol="D", direction=IODirection.OUTPUT),
    ]
)


# --- role_of 매핑 ----------------------------------------------------------
def test_role_of_p_splits_by_direction() -> None:
    assert role_of(DeviceClass.P, IODirection.INPUT) == DeviceRole.INPUT
    assert role_of(DeviceClass.P, IODirection.OUTPUT) == DeviceRole.OUTPUT
    # 방향 미지정 → 입력으로 본다(기존 호출 호환)
    assert role_of(DeviceClass.P, None) == DeviceRole.INPUT


def test_role_of_non_io() -> None:
    assert role_of(DeviceClass.M) == DeviceRole.INTERNAL
    assert role_of(DeviceClass.T) == DeviceRole.TIMER
    assert role_of(DeviceClass.C) == DeviceRole.COUNTER
    assert role_of(DeviceClass.K) == DeviceRole.KEEP


# --- LS 기본값: 기존 동작 보존 --------------------------------------------
def test_ls_default_preserves_legacy_addresses() -> None:
    a = DeviceAllocator().build_from_spec(_IO_SPEC)
    # 입출력이 P 인덱스를 공유하며 10진 4자리로 순차 발급
    assert a.address_of("A") == "P0000"
    assert a.address_of("B") == "P0001"
    assert a.address_of("C") == "P0002"
    assert a.address_of("D") == "P0003"


def test_ls_data_register_width_5() -> None:
    assert LS_XGK.format_address(DeviceClass.D, 0) == "D00000"


# --- 미쓰비시: X/Y 분리 + 8진 --------------------------------------------
def test_mitsubishi_splits_x_y() -> None:
    a = DeviceAllocator(MITSUBISHI_FX).build_from_spec(_IO_SPEC)
    # 입력은 X, 출력은 Y 로 갈리고 각자 0부터
    assert a.address_of("A") == "X0"
    assert a.address_of("B") == "X1"
    assert a.address_of("C") == "Y0"
    assert a.address_of("D") == "Y1"


def test_mitsubishi_octal_io_numbering() -> None:
    # 8번째 입력 = 8진수로 X10 (8,9 건너뜀)
    assert MITSUBISHI_FX.format_address(DeviceClass.P, 8, IODirection.INPUT) == "X10"
    assert MITSUBISHI_FX.format_address(DeviceClass.P, 7, IODirection.INPUT) == "X7"
    # 내부릴레이는 10진
    assert MITSUBISHI_FX.format_address(DeviceClass.M, 12) == "M12"


# --- 지멘스: byte.bit -----------------------------------------------------
def test_siemens_byte_bit_addressing() -> None:
    assert SIEMENS_S7.format_address(DeviceClass.P, 0, IODirection.INPUT) == "%I0.0"
    assert SIEMENS_S7.format_address(DeviceClass.P, 0, IODirection.OUTPUT) == "%Q0.0"
    # 8번째 비트 → 다음 바이트
    assert SIEMENS_S7.format_address(DeviceClass.P, 8, IODirection.INPUT) == "%I1.0"
    assert SIEMENS_S7.format_address(DeviceClass.P, 9, IODirection.INPUT) == "%I1.1"


# --- 옴론: channel.bit(16비트) + 감산 타이머 -----------------------------
def test_omron_channel_bit_16() -> None:
    assert OMRON_CJ.format_address(DeviceClass.P, 0, IODirection.INPUT) == "CIO0.00"
    # 16비트/워드 → 16번째 비트가 다음 채널
    assert OMRON_CJ.format_address(DeviceClass.P, 16, IODirection.INPUT) == "CIO1.00"


def test_omron_timer_is_countdown() -> None:
    assert OMRON_CJ.timer_is_countdown is True
    assert LS_XGK.timer_is_countdown is False


# --- 니모닉 ----------------------------------------------------------------
def test_oneshot_mnemonics_differ_across_vendors() -> None:
    assert LS_XGK.mnemonic("oneshot_rising") == "OUTP"
    assert MITSUBISHI_FX.mnemonic("oneshot_rising") == "PLS"
    assert SIEMENS_S7.mnemonic("oneshot_rising") == "P"
    assert OMRON_CJ.mnemonic("oneshot_rising") == "DIFU"


def test_unknown_mnemonic_returns_op() -> None:
    assert LS_XGK.mnemonic("nonexistent_op") == "nonexistent_op"


# --- 레지스트리 ------------------------------------------------------------
def test_profile_registry() -> None:
    names = available_profiles()
    assert {"LS_XGK", "MITSUBISHI_FX", "SIEMENS_S7", "OMRON_CJ"} <= set(names)
    assert get_profile("MITSUBISHI_FX") is MITSUBISHI_FX
