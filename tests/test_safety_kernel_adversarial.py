"""안전커널 적대/속성(adversarial & property) 하드닝 테스트 — Track C.

``SafetyKernel`` 은 실장비 PLC 로 나가는 위험한 쓰기를 막는 fail-safe 최후 방어선이다.
이 파일은 그 *불변식(invariant)* 을 적대적으로 단정한다 — 거부된 쓰기는 절대 링크에
도달하지 않고, 내부/링크 예외는 안전측으로 떨어지며, 화이트리스트 밖 심볼은 무작위
시퀀스를 던져도 단 한 번도 통과하지 못한다.

전부 결정론적이다: LLM·네트워크·하드웨어 없음, 시드 고정 RNG, 클록 주입. 두 번 돌려도
같은 결과를 낸다. 하위 링크는 모든 호출을 기록하는 in-test Spy/Fake 로 대체한다.
"""

from __future__ import annotations

import random

import pytest

from app.comms import PlcLink, WriteRejected
from app.comms.safety_kernel import SafetyKernel
from app.models import (
    DerivedOutput,
    Interlock,
    IODirection,
    IOPoint,
    StateMachineSpec,
)
from app.wizard import build_spec


class SpyLink:
    """모든 write_inputs 호출을 *그대로* 기록하는 적대 검증용 스파이 링크.

    FakeLink 와 달리, 링크가 받은 모든 호출을 ``calls`` 에 누적해 '거부된 위험 값이
    링크에 단 한 번도 도달하지 않았다' 는 불변식을 사후에 전수 검사할 수 있게 한다.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, bool]] = []
        self._outputs: dict[str, bool] = {}
        self.closed = False

    def write_inputs(self, values: dict[str, bool]) -> None:
        self.calls.append(dict(values))

    def read_outputs(self) -> dict[str, bool]:
        return dict(self._outputs)

    def close(self) -> None:
        self.closed = True

    # ── 검증 헬퍼 ────────────────────────────────────────────────────────
    def saw_symbol(self, symbol: str) -> bool:
        """링크가 그 심볼을 *어떤 호출에서든* 받은 적이 있는가."""
        return any(symbol in c for c in self.calls)

    def saw_pair_true(self, a: str, b: str) -> bool:
        """링크가 한 호출에서 두 심볼을 동시에 True 로 받은 적이 있는가."""
        return any(c.get(a) is True and c.get(b) is True for c in self.calls)


def _unsafe_spec() -> StateMachineSpec:
    """인터락은 선언됐으나 합성 ST 가 NOT-보호를 갖지 않는 명세(동시개방 가능).

    파생출력은 인터락 NOT-항이 합성되지 않으므로, 두 입력을 동시에 주면 두 밸브가
    동시에 켜진다 — 안전커널이 드라이런으로 잡아내야 하는 시나리오.
    """
    return StateMachineSpec(
        title="동시 개방 금지 데모(보호 미합성)",
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


def _input_symbols(spec: StateMachineSpec) -> frozenset[str]:
    return frozenset(
        p.symbol for p in spec.io_points if p.direction == IODirection.INPUT
    )


# ════════════════════════════════════════════════════════════════════════
# 불변식 1 — 거부된 쓰기는 절대 링크에 도달하지 않는다 (suppress unsafe write)
# ════════════════════════════════════════════════════════════════════════
def test_rejected_write_never_reaches_link_all_paths() -> None:
    """모든 거부 경로(미등록/출력심볼/비BOOL/인터락)에서 위험 값이 링크에 안 닿는다."""
    bad_commands: list[dict[str, bool]] = [
        {"HACK_PB": True},  # 화이트리스트 밖
        {"MOTOR_FWD": True},  # 출력 심볼을 입력으로 강제
        {"FWD_PB": 1},  # type: ignore[dict-item]  # 비BOOL
        {"FWD_PB": True, "BOGUS": False},  # 일부만 미등록 → 전체 거부(원자성)
    ]
    for cmd in bad_commands:
        spy = SpyLink()
        kernel = SafetyKernel(spy, build_spec("fwd_rev"))
        with pytest.raises(WriteRejected):
            kernel.write_inputs(cmd)
        # 거부된 명령은 부분적으로도 링크에 도달하면 안 된다.
        assert spy.calls == [], f"거부된 명령이 링크에 누출됨: {cmd} -> {spy.calls}"
        assert kernel.audit_log()[-1][0] == "DENY"

    # 인터락 위반(동시개방)도 링크에 그 위험 쌍이 도달하면 안 된다.
    spy = SpyLink()
    kernel = SafetyKernel(spy, _unsafe_spec())
    with pytest.raises(WriteRejected):
        kernel.write_inputs({"A_PB": True, "B_PB": True})
    assert spy.calls == []
    assert not spy.saw_pair_true("A_PB", "B_PB")


def test_partial_dict_is_atomic_no_safe_subset_leaks() -> None:
    """미등록 심볼이 한 개라도 섞이면 *안전한 부분조차* 링크에 흘리지 않는다."""
    spy = SpyLink()
    kernel = SafetyKernel(spy, build_spec("fwd_rev"))
    with pytest.raises(WriteRejected):
        kernel.write_inputs({"FWD_PB": True, "HACK_PB": True})
    assert spy.calls == []  # FWD_PB(안전) 도 함께 차단되어야 한다(부분쓰기 금지).


# ════════════════════════════════════════════════════════════════════════
# 불변식 2 — fail-safe: 내부/링크 예외 시 안전측(쓰기 미반영/차단)으로 떨어진다
# ════════════════════════════════════════════════════════════════════════
class _RaisingLink:
    """write_inputs 가 항상 폭발하는 적대 링크(소켓 단절·하드웨어 결함 모사)."""

    def __init__(self) -> None:
        self.attempts = 0

    def write_inputs(self, values: dict[str, bool]) -> None:
        self.attempts += 1
        raise ConnectionError("link boom")

    def read_outputs(self) -> dict[str, bool]:
        return {}

    def close(self) -> None:
        pass


def test_link_exception_fails_safe_no_state_advance() -> None:
    """링크 예외 → WriteRejected + DENY 감사기록 + 레이트리밋 클록 미전진(fail-safe)."""
    clock = {"t": 0.0}
    link = _RaisingLink()
    kernel = SafetyKernel(
        link, build_spec("fwd_rev"), now=lambda: clock["t"], min_interval=1.0
    )
    with pytest.raises(WriteRejected) as ei:
        kernel.write_inputs({"FWD_PB": True})
    assert "fail-safe" in str(ei.value)
    assert link.attempts == 1
    assert kernel.audit_log()[-1][0] == "DENY"
    # 쓰기가 실제로 반영되지 않았으므로 레이트리밋 기준점도 전진하면 안 된다.
    assert kernel._last_write_at is None


def test_internal_validation_exception_fails_safe() -> None:
    """검증 내부에서 임의 예외가 나도 fail-open 이 아니라 무조건 거부한다."""
    spy = SpyLink()
    kernel = SafetyKernel(spy, build_spec("fwd_rev"))

    def _boom(values: dict[str, bool]) -> str | None:
        raise RuntimeError("synth 폭발")

    kernel._check_interlocks = _boom  # type: ignore[method-assign]
    with pytest.raises(WriteRejected) as ei:
        kernel.write_inputs({"FWD_PB": True})
    assert "fail-safe" in str(ei.value)
    assert spy.calls == []
    assert kernel.audit_log()[-1][0] == "DENY"


def test_link_exception_then_recovery_is_consistent() -> None:
    """링크가 한 번 실패한 뒤 회복돼도, 실패분은 끝까지 링크에 반영되지 않는다."""
    spy = SpyLink()
    kernel = SafetyKernel(spy, build_spec("fwd_rev"))

    # 첫 시도: 링크가 폭발하도록 일시 교체.
    boom = _RaisingLink()
    kernel._link = boom
    with pytest.raises(WriteRejected):
        kernel.write_inputs({"FWD_PB": True})

    # 회복: 정상 링크로 복귀하면 이후 안전 명령은 통과한다.
    kernel._link = spy
    kernel.write_inputs({"FWD_PB": True})
    assert spy.calls == [{"FWD_PB": True}]  # 회복 후 1건만, 실패분 누출 없음.
    decisions = [d for d, _ in kernel.audit_log()]
    assert decisions == ["DENY", "ALLOW"]


# ════════════════════════════════════════════════════════════════════════
# 불변식 3 — 레이트리밋: 한도 초과는 차단, 한도 내는 통과 (클록 주입)
# ════════════════════════════════════════════════════════════════════════
def test_rate_limit_boundary_and_link_isolation() -> None:
    """한도 미만은 차단(링크 미도달), 정확히 한도부터 통과."""
    clock = {"t": 0.0}
    spy = SpyLink()
    kernel = SafetyKernel(
        spy, build_spec("fwd_rev"), now=lambda: clock["t"], min_interval=1.0
    )
    kernel.write_inputs({"FWD_PB": True})  # t=0 첫 쓰기 통과

    clock["t"] = 0.999  # 한도 미만
    with pytest.raises(WriteRejected) as ei:
        kernel.write_inputs({"STOP": True})
    assert "레이트리밋" in str(ei.value)
    assert not spy.saw_symbol("STOP")  # 차단된 쓰기는 링크에 도달 안 함.

    clock["t"] = 1.0  # 정확히 경계 → 통과(elapsed<interval 만 차단)
    kernel.write_inputs({"STOP": True})
    assert spy.calls == [{"FWD_PB": True}, {"STOP": True}]


def test_rate_limit_denied_write_does_not_consume_budget() -> None:
    """거부된 쓰기는 레이트리밋 기준점을 전진시키지 않는다(deny 가 budget 소모 안 함)."""
    clock = {"t": 0.0}
    spy = SpyLink()
    kernel = SafetyKernel(
        spy, build_spec("fwd_rev"), now=lambda: clock["t"], min_interval=1.0
    )
    kernel.write_inputs({"FWD_PB": True})  # 기준점 t=0
    clock["t"] = 0.5
    with pytest.raises(WriteRejected):
        kernel.write_inputs({"HACK": True})  # 화이트리스트로 먼저 거부
    # 기준점이 0.5 로 밀렸다면 아래가 통과해버린다. 0 으로 남아 있어야 정상.
    clock["t"] = 0.6
    with pytest.raises(WriteRejected) as ei:
        kernel.write_inputs({"STOP": True})
    assert "레이트리밋" in str(ei.value)


def test_rate_limit_disabled_without_clock() -> None:
    """클록 미주입이면 레이트리밋 비활성 — 연속 쓰기 모두 통과."""
    spy = SpyLink()
    kernel = SafetyKernel(spy, build_spec("fwd_rev"))  # now 없음
    for _ in range(5):
        kernel.write_inputs({"FWD_PB": True})
    assert len(spy.calls) == 5


# ════════════════════════════════════════════════════════════════════════
# 불변식 4 — 감사 로그: 거부 시 사유가 audit 에 남는다
# ════════════════════════════════════════════════════════════════════════
def test_audit_records_reason_per_reject_path() -> None:
    """각 거부 경로의 사유 키워드가 감사 로그에 정확히 남는지."""
    cases: list[tuple[dict[str, bool], str]] = [
        ({"HACK_PB": True}, "화이트리스트"),
        ({"FWD_PB": 1}, "타입"),  # type: ignore[dict-item]
    ]
    for cmd, keyword in cases:
        spy = SpyLink()
        kernel = SafetyKernel(spy, build_spec("fwd_rev"))
        with pytest.raises(WriteRejected):
            kernel.write_inputs(cmd)
        decision, reason = kernel.audit_log()[-1]
        assert decision == "DENY"
        assert keyword in reason

    # 인터락 위반 사유.
    spy = SpyLink()
    kernel = SafetyKernel(spy, _unsafe_spec())
    with pytest.raises(WriteRejected):
        kernel.write_inputs({"A_PB": True, "B_PB": True})
    decision, reason = kernel.audit_log()[-1]
    assert decision == "DENY"
    assert "인터락" in reason


def test_audit_seq_monotonic_and_link_failure_audited() -> None:
    """감사 seq 가 단조 증가하고, 링크 실패도 DENY 로 감사된다."""
    link = _RaisingLink()
    kernel = SafetyKernel(link, build_spec("fwd_rev"))
    with pytest.raises(WriteRejected):
        kernel.write_inputs({"FWD_PB": True})
    with pytest.raises(WriteRejected):
        kernel.write_inputs({"STOP": True})
    seqs = [e.seq for e in kernel.audit]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)  # 단조·유일.
    assert all(e.decision == "DENY" for e in kernel.audit)
    assert all("fail-safe" in e.reason for e in kernel.audit)


# ════════════════════════════════════════════════════════════════════════
# 불변식 5 — 방어적 스냅샷: 통과 후 호출자가 dict 를 바꿔도 링크 값은 불변
# ════════════════════════════════════════════════════════════════════════
def test_caller_mutation_after_write_does_not_leak_to_link() -> None:
    """검증 통과 후 호출자가 같은 dict 를 변조해도, 링크가 받은 스냅샷은 불변.

    안전 최후 방어선의 TOCTOU 별칭(aliasing) 누출 회귀 갑옷.
    """

    captured: list[dict[str, bool]] = []

    class _RetainingLink:
        """전달받은 dict 참조를 *그대로 보관* 하는 적대 링크(비동기 큐 모사)."""

        def write_inputs(self, values: dict[str, bool]) -> None:
            captured.append(values)  # 복사 없이 참조 보관 — 별칭 누출 유도.

        def read_outputs(self) -> dict[str, bool]:
            return {}

        def close(self) -> None:
            pass

    kernel = SafetyKernel(_RetainingLink(), build_spec("fwd_rev"))
    cmd: dict[str, bool] = {"FWD_PB": True}
    kernel.write_inputs(cmd)
    # 통과 후 호출자가 위험하게 변조: 인터락 깨는 쌍을 주입.
    cmd["FWD_PB"] = False
    cmd["REV_PB"] = True
    # 링크가 보관한 스냅샷은 검증 시점 값({"FWD_PB": True}) 이어야 한다.
    assert captured == [{"FWD_PB": True}]


# ════════════════════════════════════════════════════════════════════════
# 불변식 6 — fuzz/property: 무작위 시퀀스에도 화이트리스트 밖은 단 한 번도 통과 못 함
# ════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("seed", [0, 1, 7, 42, 1234])
def test_fuzz_whitelist_outside_never_passes(seed: int) -> None:
    """시드 고정 무작위 명령 폭격 — 화이트리스트 밖 심볼은 링크에 절대 도달 못 함.

    비BOOL 값·미등록 심볼·출력 심볼·동시개방을 마구 섞어 던져도, 링크가 받은 모든
    호출은 (a) 입력 화이트리스트 안의 심볼만, (b) 전부 BOOL 값이어야 한다.
    """
    spec = _unsafe_spec()
    inputs = _input_symbols(spec)
    junk = ["HACK", "VALVE_A", "VALVE_B", "X", "", "DROP TABLE"]
    bool_vals: list[object] = [True, False]
    junk_vals: list[object] = [1, 0, "on", None, 3.14]
    pool = sorted(inputs) + junk

    rng = random.Random(seed)
    spy = SpyLink()
    kernel = SafetyKernel(spy, spec)

    for _ in range(1500):
        n = rng.randint(0, 3)
        cmd: dict[str, object] = {}
        for _ in range(n):
            sym = rng.choice(pool)
            use_junk_val = rng.random() < 0.2
            cmd[sym] = rng.choice(junk_vals if use_junk_val else bool_vals)
        try:
            kernel.write_inputs(cmd)  # type: ignore[arg-type]
        except WriteRejected:
            pass

    # 전수 검사: 링크가 받은 어떤 호출도 불변식을 위반하지 않는다.
    for call in spy.calls:
        for sym, val in call.items():
            assert sym in inputs, f"화이트리스트 밖 심볼이 링크에 누출됨: {sym}"
            assert isinstance(val, bool), f"비BOOL 값이 링크에 누출됨: {sym}={val!r}"
        # 동시개방(인터락 위반) 쌍이 한 호출로 링크에 도달하면 안 된다.
        assert not (call.get("VALVE_A") and call.get("VALVE_B"))

    # ALLOW 로 기록된 건수와 링크 호출 건수는 정확히 일치해야 한다(누출/유실 0).
    allow_count = sum(1 for d, _ in kernel.audit_log() if d == "ALLOW")
    assert allow_count == len(spy.calls)


@pytest.mark.parametrize("seed", [3, 99])
def test_fuzz_determinism_same_seed_same_audit(seed: int) -> None:
    """같은 시드면 감사 로그가 완전히 동일하다(결정론 — 두 번 돌려 비교)."""

    def run() -> list[tuple[str, str]]:
        spec = _unsafe_spec()
        inputs = sorted(_input_symbols(spec))
        pool = inputs + ["HACK", "VALVE_A", ""]
        rng = random.Random(seed)
        kernel = SafetyKernel(SpyLink(), spec)
        for _ in range(300):
            n = rng.randint(0, 2)
            cmd = {rng.choice(pool): rng.choice([True, False]) for _ in range(n)}
            try:
                kernel.write_inputs(cmd)
            except WriteRejected:
                pass
        return kernel.audit_log()

    assert run() == run()


# ── 보강: 게이트 자신이 PlcLink 계약을 만족하는지(스파이로도 확인) ──────────
def test_spy_kernel_is_plclink() -> None:
    kernel = SafetyKernel(SpyLink(), build_spec("fwd_rev"))
    assert isinstance(kernel, PlcLink)
