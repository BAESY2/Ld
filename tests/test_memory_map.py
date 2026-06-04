"""디바이스 할당기 + 이중코일 병합 테스트."""

from __future__ import annotations

import re

import pytest

from app.memory_map import (
    DeviceAllocator,
    detect_double_coils,
    merge_double_coils,
)
from app.models import DeviceClass, IODirection, IOPoint, StateMachineSpec


# --- C1: allocator ---------------------------------------------------------
def test_same_symbol_returns_same_address() -> None:
    a = DeviceAllocator()
    first = a.allocate("MOTOR", DeviceClass.P)
    second = a.allocate("MOTOR", DeviceClass.P)
    assert first == second


def test_fixed_address_collision_raises() -> None:
    a = DeviceAllocator()
    a.allocate("X", DeviceClass.P, fixed_address="P0005")
    with pytest.raises(ValueError):
        a.allocate("Y", DeviceClass.P, fixed_address="P0005")


def test_build_from_spec_sequential_io() -> None:
    spec = StateMachineSpec(
        io_points=[
            IOPoint(symbol="A", direction=IODirection.INPUT),
            IOPoint(symbol="B", direction=IODirection.INPUT),
            IOPoint(symbol="C", direction=IODirection.OUTPUT),
            IOPoint(symbol="D", direction=IODirection.OUTPUT),
        ]
    )
    a = DeviceAllocator().build_from_spec(spec)
    assert a.address_of("A") == "P0000"
    assert a.address_of("B") == "P0001"
    assert a.address_of("C") == "P0002"
    assert a.address_of("D") == "P0003"


def test_fixed_address_does_not_collide_with_auto() -> None:
    spec = StateMachineSpec(
        io_points=[
            IOPoint(symbol="A", direction=IODirection.INPUT),
            IOPoint(symbol="FIXED", direction=IODirection.INPUT, fixed_address="P0000"),
            IOPoint(symbol="B", direction=IODirection.INPUT),
        ]
    )
    a = DeviceAllocator().build_from_spec(spec)
    # FIXED 가 P0000 을 점유하므로 자동 할당은 이를 건너뛴다
    assert a.address_of("FIXED") == "P0000"
    assert a.address_of("A") != "P0000"
    assert a.address_of("B") != "P0000"
    assert a.address_of("A") != a.address_of("B")


def test_internal_relay_allocates_m_device() -> None:
    a = DeviceAllocator()
    addr = a.allocate_internal_relay("hint")
    assert addr.startswith("M")


# --- C2: double-coil -------------------------------------------------------
def test_detect_double_coils() -> None:
    st = "MOTOR_FWD := A;\nMOTOR_FWD := B;\nLAMP := C;\n"
    dups = detect_double_coils(st)
    assert set(dups.keys()) == {"MOTOR_FWD"}
    assert dups["MOTOR_FWD"] == ["A", "B"]


def test_no_double_coil_returns_original() -> None:
    a = DeviceAllocator()
    st = "MOTOR := A AND B;\nLAMP := C;\n"
    result = merge_double_coils(st, a)
    assert result.changed is False
    assert result.code == st


def test_merge_double_coils_produces_or_merge() -> None:
    a = DeviceAllocator()
    st = "MOTOR_FWD := A;\nMOTOR_FWD := B;\n"
    result = merge_double_coils(st, a)

    assert result.changed is True
    assert result.merged_symbols == ["MOTOR_FWD"]

    # aux M 주소 2개가 발급되고 좌변이 치환됨
    auxes = result.aux_addresses["MOTOR_FWD"]
    assert len(auxes) == 2
    assert all(x.startswith("M") for x in auxes)

    # 치환된 대입문 존재
    assert f"{auxes[0]} := A;" in result.code
    assert f"{auxes[1]} := B;" in result.code

    # OR 병합문 존재, 형태: MOTOR_FWD := M.. OR M..;
    merge_line = re.search(r"^MOTOR_FWD := (.+);$", result.code, re.MULTILINE)
    assert merge_line is not None
    assert " OR " in merge_line.group(1)

    # 병합 후에는 더 이상 이중코일이 아님
    assert detect_double_coils(result.code) == {}
