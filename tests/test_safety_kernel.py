"""안전커널(쓰기 전 검증 게이트) 단위 테스트.

Modbus 없이 in-test 가짜 PlcLink 만으로 deny-by-default·fail-safe 게이트를 검증한다.
모든 검사는 결정론적이며(LLM/네트워크 없음, 클록 주입), 두 번 돌려도 같은 결과다.
"""

from __future__ import annotations

from app.comms import PlcLink, WriteRejected
from app.comms.safety_kernel import AuditEntry, SafetyKernel
from app.models import (
    DerivedOutput,
    Interlock,
    IODirection,
    IOPoint,
    StateMachineSpec,
)
from app.wizard import build_spec


class FakeLink:
    """검증 통과분만 받는 in-test 가짜 PlcLink(쓰기 기록·재생)."""

    def __init__(self) -> None:
        self.writes: list[dict[str, bool]] = []
        self._outputs: dict[str, bool] = {}
        self.closed = False

    def write_inputs(self, values: dict[str, bool]) -> None:
        self.writes.append(dict(values))

    def read_outputs(self) -> dict[str, bool]:
        return dict(self._outputs)

    def close(self) -> None:
        self.closed = True


def _unsafe_spec() -> StateMachineSpec:
    """인터락은 선언되었으나 합성 ST 가 NOT-보호를 갖지 않는 명세.

    파생출력(derived_outputs)은 인터락 NOT-항이 합성되지 않으므로, 두 입력을
    동시에 주면 두 밸브가 동시에 켜진다 — 안전커널이 잡아야 하는 시나리오.
    """
    return StateMachineSpec(
        title="동시 개방 금지 데모",
        io_points=[
            IOPoint(symbol="A_PB", direction=IODirection.INPUT),
            IOPoint(symbol="B_PB", direction=IODirection.INPUT),
            IOPoint(symbol="VALVE_A", direction=IODirection.OUTPUT),
            IOPoint(symbol="VALVE_B", direction=IODirection.OUTPUT),
        ],
        derived_outputs=[
            DerivedOutput(output="VALVE_A", expression="A_PB"),
            DerivedOutput(output="VALVE_B", expression="B_PB"),
        ],
        interlocks=[
            Interlock(output_a="VALVE_A", output_b="VALVE_B", reason="동시 개방 금지"),
        ],
    )


# ── PlcLink 계약 ──────────────────────────────────────────────────────────
def test_safety_kernel_is_plclink() -> None:
    kernel = SafetyKernel(FakeLink(), build_spec("fwd_rev"))
    assert isinstance(kernel, PlcLink)  # runtime_checkable Protocol


# ── 정상 명령은 통과 ──────────────────────────────────────────────────────
def test_safe_command_passes_through() -> None:
    link = FakeLink()
    kernel = SafetyKernel(link, build_spec("fwd_rev"))
    kernel.write_inputs({"FWD_PB": True})
    assert link.writes == [{"FWD_PB": True}]
    assert kernel.audit_log()[-1] == ("ALLOW", "안전검증 통과")


def test_read_outputs_delegates_to_wrapped_link() -> None:
    link = FakeLink()
    link._outputs = {"MOTOR_FWD": True}
    kernel = SafetyKernel(link, build_spec("fwd_rev"))
    assert kernel.read_outputs() == {"MOTOR_FWD": True}


def test_close_delegates_to_wrapped_link() -> None:
    link = FakeLink()
    SafetyKernel(link, build_spec("fwd_rev")).close()
    assert link.closed is True


# ── 인터락 동시구동 차단 ──────────────────────────────────────────────────
def test_interlock_coenergize_rejected_link_never_sees_it() -> None:
    link = FakeLink()
    kernel = SafetyKernel(link, _unsafe_spec())
    try:
        kernel.write_inputs({"A_PB": True, "B_PB": True})
        raise AssertionError("동시 개방 명령이 거부되지 않았다")
    except WriteRejected as exc:
        assert "인터락 위반" in str(exc)
        assert "VALVE_A" in str(exc) and "VALVE_B" in str(exc)
    # 위험 명령은 실링크에 절대 도달하지 않는다(suppress unsafe write).
    assert link.writes == []
    assert kernel.audit_log()[-1][0] == "DENY"


def test_safe_single_valve_passes_on_unsafe_spec() -> None:
    link = FakeLink()
    kernel = SafetyKernel(link, _unsafe_spec())
    kernel.write_inputs({"A_PB": True})  # 한쪽만 — 인터락 무위반
    assert link.writes == [{"A_PB": True}]


# ── 화이트리스트 ──────────────────────────────────────────────────────────
def test_unknown_symbol_rejected() -> None:
    link = FakeLink()
    kernel = SafetyKernel(link, build_spec("fwd_rev"))
    try:
        kernel.write_inputs({"HACK_PB": True})
        raise AssertionError("모르는 심볼이 거부되지 않았다")
    except WriteRejected as exc:
        assert "화이트리스트 위반" in str(exc)
    assert link.writes == []


def test_output_symbol_not_writable_as_input() -> None:
    """출력 심볼(MOTOR_FWD)은 입력 쓰기 화이트리스트에 없다 → 거부."""
    link = FakeLink()
    kernel = SafetyKernel(link, build_spec("fwd_rev"))
    try:
        kernel.write_inputs({"MOTOR_FWD": True})
        raise AssertionError("출력 심볼 강제쓰기가 거부되지 않았다")
    except WriteRejected:
        pass
    assert link.writes == []


# ── 타입/범위 ─────────────────────────────────────────────────────────────
def test_non_bool_value_rejected() -> None:
    link = FakeLink()
    kernel = SafetyKernel(link, build_spec("fwd_rev"))
    try:
        kernel.write_inputs({"FWD_PB": 1})  # type: ignore[dict-item]
        raise AssertionError("비불리언 값이 거부되지 않았다")
    except WriteRejected as exc:
        assert "타입 위반" in str(exc)
    assert link.writes == []


# ── fail-safe(검증 예외 → 거부) ───────────────────────────────────────────
class _BoomLink:
    """검증과 무관하나, 화이트리스트 검사 중 폭발하도록 spec 을 망가뜨린 케이스."""

    def __init__(self) -> None:
        self.writes: list[dict[str, bool]] = []

    def write_inputs(self, values: dict[str, bool]) -> None:
        self.writes.append(dict(values))

    def read_outputs(self) -> dict[str, bool]:
        return {}

    def close(self) -> None:
        pass


def test_validation_exception_fails_safe_deny() -> None:
    """검증 내부에서 예외가 나면 fail-open 이 아니라 무조건 거부한다."""
    link = _BoomLink()
    kernel = SafetyKernel(link, build_spec("fwd_rev"))

    # 인터락 검사가 폭발하도록 합성 단계를 강제로 깨뜨린다.
    def _boom(values: dict[str, bool]) -> str | None:
        raise RuntimeError("synth 폭발")

    kernel._check_interlocks = _boom  # type: ignore[method-assign]
    try:
        kernel.write_inputs({"FWD_PB": True})
        raise AssertionError("검증 예외 시 fail-open 되었다(거부했어야 함)")
    except WriteRejected as exc:
        assert "fail-safe" in str(exc)
    assert link.writes == []
    assert kernel.audit_log()[-1][0] == "DENY"


# ── 레이트리밋(결정론 클록 주입) ──────────────────────────────────────────
def test_rate_limit_blocks_too_fast_with_injected_clock() -> None:
    clock = {"t": 0.0}
    link = FakeLink()
    kernel = SafetyKernel(
        link, build_spec("fwd_rev"), now=lambda: clock["t"], min_interval=1.0
    )
    kernel.write_inputs({"FWD_PB": True})  # t=0, 첫 쓰기 통과
    clock["t"] = 0.5  # 간격 부족
    try:
        kernel.write_inputs({"FWD_PB": False})
        raise AssertionError("레이트리밋이 너무 빠른 쓰기를 막지 못했다")
    except WriteRejected as exc:
        assert "레이트리밋 위반" in str(exc)
    clock["t"] = 1.5  # 충분한 간격 → 통과
    kernel.write_inputs({"FWD_PB": False})
    assert link.writes == [{"FWD_PB": True}, {"FWD_PB": False}]


# ── 감사 로그 결정론 ──────────────────────────────────────────────────────
def test_audit_log_records_decisions_deterministically() -> None:
    def run() -> list[tuple[str, str]]:
        link = FakeLink()
        kernel = SafetyKernel(link, _unsafe_spec())
        try:
            kernel.write_inputs({"A_PB": True, "B_PB": True})  # DENY
        except WriteRejected:
            pass
        kernel.write_inputs({"A_PB": True})  # ALLOW
        try:
            kernel.write_inputs({"HACK": True})  # DENY (whitelist)
        except WriteRejected:
            pass
        return kernel.audit_log()

    first = run()
    second = run()
    assert first == second  # 두 번 돌려도 동일(결정론)
    decisions = [d for d, _ in first]
    assert decisions == ["DENY", "ALLOW", "DENY"]


def test_audit_entry_as_tuple() -> None:
    entry = AuditEntry(decision="ALLOW", reason="ok", seq=3)
    assert entry.as_tuple() == ("ALLOW", "ok")


def test_link_write_failure_fails_safe_and_audits() -> None:
    """링크 쓰기 자체가 실패해도 fail-safe: WriteRejected + DENY 감사기록(R7-P2)."""
    import pytest

    from app.comms import WriteRejected
    from app.comms.safety_kernel import SafetyKernel
    from app.wizard import build_spec

    class _RaisingLink:
        def write_inputs(self, values: dict[str, bool]) -> None:
            raise RuntimeError("link boom")

        def read_outputs(self) -> dict[str, bool]:
            return {}

        def close(self) -> None:
            pass

    k = SafetyKernel(_RaisingLink(), build_spec("fwd_rev"))
    with pytest.raises(WriteRejected):
        k.write_inputs({"FWD_PB": True})  # 검증 통과 후 링크 쓰기에서 폭발
    assert k.audit[-1].decision == "DENY"
    assert k._last_write_at is None
