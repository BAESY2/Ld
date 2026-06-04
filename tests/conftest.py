"""공유 픽스처."""

from __future__ import annotations

import pytest

from app.models import (
    Interlock,
    IODirection,
    IOPoint,
    SfcState,
    StateMachineSpec,
    Transition,
)


@pytest.fixture
def conveyor_spec_safe() -> StateMachineSpec:
    """정/역이 상호배타로 올바르게 잠긴 컨베이어 명세."""
    return StateMachineSpec(
        title="컨베이어(안전)",
        io_points=[
            IOPoint(symbol="FWD_PB", direction=IODirection.INPUT),
            IOPoint(symbol="REV_PB", direction=IODirection.INPUT),
            IOPoint(symbol="MOTOR_FWD", direction=IODirection.OUTPUT),
            IOPoint(symbol="MOTOR_REV", direction=IODirection.OUTPUT),
        ],
        states=[
            SfcState(name="IDLE", is_initial=True),
            SfcState(name="FORWARD", on_entry=["MOTOR_FWD := TRUE;"]),
            SfcState(name="REVERSE", on_entry=["MOTOR_REV := TRUE;"]),
        ],
        transitions=[
            Transition(from_state="IDLE", to_state="FORWARD", condition="FWD_PB AND NOT REV_PB"),
            Transition(from_state="IDLE", to_state="REVERSE", condition="REV_PB AND NOT FWD_PB"),
        ],
        interlocks=[
            Interlock(output_a="MOTOR_FWD", output_b="MOTOR_REV", reason="정/역 동시 구동 금지")
        ],
    )


@pytest.fixture
def conveyor_spec_unsafe() -> StateMachineSpec:
    """정/역이 동시에 켜질 수 있는(인터락 위반) 컨베이어 명세."""
    return StateMachineSpec(
        title="컨베이어(위험)",
        io_points=[
            IOPoint(symbol="FWD_PB", direction=IODirection.INPUT),
            IOPoint(symbol="REV_PB", direction=IODirection.INPUT),
            IOPoint(symbol="MOTOR_FWD", direction=IODirection.OUTPUT),
            IOPoint(symbol="MOTOR_REV", direction=IODirection.OUTPUT),
        ],
        states=[
            SfcState(name="IDLE", is_initial=True),
            SfcState(name="FORWARD", on_entry=["MOTOR_FWD := TRUE;"]),
            SfcState(name="REVERSE", on_entry=["MOTOR_REV := TRUE;"]),
        ],
        transitions=[
            # NOT 잠금이 빠져 FWD_PB 와 REV_PB 가 동시에 눌리면 둘 다 켜짐
            Transition(from_state="IDLE", to_state="FORWARD", condition="FWD_PB"),
            Transition(from_state="IDLE", to_state="REVERSE", condition="REV_PB"),
        ],
        interlocks=[
            Interlock(output_a="MOTOR_FWD", output_b="MOTOR_REV", reason="정/역 동시 구동 금지")
        ],
    )
