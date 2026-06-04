"""데이터 계약 round-trip 직렬화 테스트."""

from __future__ import annotations

from app.models import (
    CounterSpec,
    CounterType,
    DataType,
    DeviceClass,
    ElementType,
    Interlock,
    IODirection,
    IOPoint,
    LadderBranch,
    LadderElement,
    LadderProgram,
    LadderRung,
    SfcState,
    StateMachineSpec,
    TimerSpec,
    TimerType,
    Transition,
    VerificationIssue,
    VerificationReport,
)


def _roundtrip(model):  # type: ignore[no-untyped-def]
    cls = type(model)
    restored = cls.model_validate_json(model.model_dump_json())
    assert restored == model
    return restored


def test_spec_models_roundtrip() -> None:
    spec = StateMachineSpec(
        title="t",
        io_points=[
            IOPoint(
                symbol="START_PB",
                direction=IODirection.INPUT,
                data_type=DataType.BOOL,
                device_class=DeviceClass.P,
                fixed_address="P0001",
            )
        ],
        timers=[TimerSpec(name="T_RUN", timer_type=TimerType.TON, preset_ms=1000)],
        counters=[CounterSpec(name="C_PART", counter_type=CounterType.CTU, preset=10)],
        states=[SfcState(name="RUN", is_initial=True, on_entry=["MOTOR := TRUE;"])],
        transitions=[Transition(from_state="IDLE", to_state="RUN", condition="START_PB")],
        interlocks=[Interlock(output_a="A", output_b="B", reason="r")],
    )
    _roundtrip(spec)


def test_verification_models_roundtrip_and_has_errors() -> None:
    report = VerificationReport(
        passed=False,
        issues=[
            VerificationIssue(
                code="INTERLOCK", severity="error", message="m", counterexample="x=True"
            ),
            VerificationIssue(code="UNREACHABLE", severity="warning", message="w"),
        ],
    )
    restored = _roundtrip(report)
    assert restored.has_errors is True

    ok = VerificationReport(issues=[VerificationIssue(code="X", severity="warning", message="m")])
    assert ok.has_errors is False


def test_ladder_models_roundtrip() -> None:
    program = LadderProgram(
        title="prog",
        rungs=[
            LadderRung(
                comment="rung1",
                input_branches=[
                    LadderBranch(
                        elements=[
                            LadderElement(
                                element_type=ElementType.CONTACT_NO,
                                symbol="START_PB",
                                address="P0001",
                            )
                        ]
                    )
                ],
                outputs=[
                    LadderElement(element_type=ElementType.COIL, symbol="MOTOR", address="P0010")
                ],
            )
        ],
    )
    _roundtrip(program)


def test_enum_serialization_is_string() -> None:
    io = IOPoint(symbol="X", direction=IODirection.OUTPUT)
    data = io.model_dump(mode="json")
    assert data["direction"] == "OUTPUT"
    assert data["device_class"] == "P"
