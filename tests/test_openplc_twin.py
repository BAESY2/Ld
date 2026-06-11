"""디지털-트윈 차분 검증(app.twin.openplc_adapter) 테스트.

CI-safe: 실 OpenPLC 테스트는 env OPENPLC_HOST 가 없으면 skip. 나머지는 우리
시뮬레이터로 뒷받침되는 SimBackedLink 로 네트워크 없이 차분 머신을 검증한다.
"""

from __future__ import annotations

import os

import pytest

from app.synth import synthesize_st
from app.twin.openplc_adapter import (
    DiffReport,
    SimBackedLink,
    connect_openplc,
    flip_once,
    linear_bit_map,
    run_differential,
)
from app.wizard import build_spec

# 입력 타임라인 타입
Timeline = list[tuple[int, dict[str, bool]]]


def _st_and_spec(recipe_id: str, answers: dict[str, str] | None = None):
    spec = build_spec(recipe_id, answers or {})
    return synthesize_st(spec), spec


# 레시피별 (타임라인, duration, step) — 출력이 실제로 바뀌도록 자극을 준다.
_CASES: dict[str, Timeline] = {
    "motor_start_stop": [(0, {"START": False}), (200, {"START": True}),
                         (500, {"START": False}), (700, {"STOP": True})],
    "fwd_rev": [(0, {}), (200, {"FWD_PB": True}), (500, {"FWD_PB": False, "STOP": True}),
                (700, {"STOP": False, "REV_PB": True})],
    "car_wash": [(0, {}), (100, {"START": True}), (300, {"START": False})],
}


@pytest.mark.parametrize("recipe_id", sorted(_CASES))
def test_agreement_simbacked_matches_simulate(recipe_id: str) -> None:
    """결함 없는 SimBackedLink 는 simulate() 와 100% 일치해야 한다(거짓 불일치 0)."""
    timeline = _CASES[recipe_id]
    st, spec = _st_and_spec(recipe_id)
    duration, step = 1000, 100
    link = SimBackedLink(st, timeline, duration_ms=duration, step_ms=step)
    report = run_differential(
        st, spec, link, timeline, duration_ms=duration, step_ms=step
    )
    assert report.agreement is True, report.summary
    assert report.mismatches == ()
    assert report.first_divergence is None
    assert report.n_samples == duration // step + 1
    assert report.outputs  # 비교 대상 출력이 비어있지 않음
    assert "AGREE" in report.summary


def test_discrepancy_detected_with_injected_fault() -> None:
    """한 출력을 한 시점에 뒤집으면 차분 머신이 *정확히 그 점*을 보고한다."""
    recipe_id = "motor_start_stop"
    timeline = _CASES[recipe_id]
    st, spec = _st_and_spec(recipe_id)
    duration, step = 1000, 100

    # 모터가 켜져 있을 표본(START=True 직후, t=300ms)에서 MOTOR 를 뒤집는다.
    fault = flip_once("MOTOR", 300)
    faulty = SimBackedLink(
        st, timeline, duration_ms=duration, step_ms=step, fault=fault
    )
    report = run_differential(
        st, spec, faulty, timeline, duration_ms=duration, step_ms=step
    )

    assert report.agreement is False
    assert len(report.mismatches) == 1
    m = report.mismatches[0]
    assert (m.t_ms, m.symbol) == (300, "MOTOR")
    assert m.sim_val != m.plc_val
    assert "DIVERGE" in report.summary
    assert report.first_divergence == m


def test_fault_at_off_sample_still_detected() -> None:
    """모터가 꺼져있을 시점(t=0)을 뒤집어도(False→True) 잡아낸다."""
    recipe_id = "motor_start_stop"
    timeline = _CASES[recipe_id]
    st, spec = _st_and_spec(recipe_id)
    fault = flip_once("MOTOR", 0)
    link = SimBackedLink(st, timeline, duration_ms=500, step_ms=100, fault=fault)
    report = run_differential(st, spec, link, timeline, duration_ms=500, step_ms=100)
    assert report.agreement is False
    assert report.first_divergence is not None
    assert report.first_divergence.t_ms == 0
    assert report.first_divergence.sim_val is False
    assert report.first_divergence.plc_val is True


def test_determinism_two_runs_identical() -> None:
    """같은 입력으로 두 번 돌리면 DiffReport 가 완전히 동일하다."""
    recipe_id = "fwd_rev"
    timeline = _CASES[recipe_id]
    st, spec = _st_and_spec(recipe_id)
    duration, step = 1000, 100

    def make() -> DiffReport:
        link = SimBackedLink(st, timeline, duration_ms=duration, step_ms=step)
        return run_differential(
            st, spec, link, timeline, duration_ms=duration, step_ms=step
        )

    r1, r2 = make(), make()
    assert r1 == r2
    assert r1.summary == r2.summary
    assert r1.mismatches == r2.mismatches


def test_determinism_with_fault_identical() -> None:
    """결함이 있어도 두 번 실행이 동일한(정렬된) 불일치를 낸다."""
    st, spec = _st_and_spec("motor_start_stop")
    timeline = _CASES["motor_start_stop"]

    def run() -> DiffReport:
        link = SimBackedLink(
            st, timeline, duration_ms=1000, step_ms=100, fault=flip_once("MOTOR", 300)
        )
        return run_differential(st, spec, link, timeline, duration_ms=1000, step_ms=100)

    assert run() == run()


def test_spec_none_compares_all_sim_outputs() -> None:
    """spec=None 이면 시뮬레이터가 구동하는 출력 전체를 비교한다."""
    st, _ = _st_and_spec("fwd_rev")
    timeline = _CASES["fwd_rev"]
    link = SimBackedLink(st, timeline, duration_ms=600, step_ms=100)
    report = run_differential(st, None, link, timeline, duration_ms=600, step_ms=100)
    assert report.agreement is True
    assert set(report.outputs) == {"MOTOR_FWD", "MOTOR_REV"}


def test_settle_hook_is_called_each_sample() -> None:
    """settle_hook 은 매 표본마다 한 번씩 호출된다(쓰기→정착→읽기 가정)."""
    st, spec = _st_and_spec("motor_start_stop")
    timeline = _CASES["motor_start_stop"]
    calls = {"n": 0}

    def settle() -> None:
        calls["n"] += 1

    report = run_differential(
        st, spec, SimBackedLink(st, timeline, duration_ms=500, step_ms=100),
        timeline, duration_ms=500, step_ms=100, settle_hook=settle,
    )
    assert calls["n"] == report.n_samples == 6


def test_simbacked_link_close_blocks_io() -> None:
    """닫힌 링크는 read/write 를 거부한다(자원 수명 계약)."""
    st, _ = _st_and_spec("motor_start_stop")
    timeline = _CASES["motor_start_stop"]
    link = SimBackedLink(st, timeline, duration_ms=200, step_ms=100)
    link.close()
    with pytest.raises(RuntimeError):
        link.read_outputs()
    with pytest.raises(RuntimeError):
        link.write_inputs({})


def test_report_notes_document_sampling_assumption() -> None:
    """DiffReport 는 표본화 가정을 notes 로 문서화한다(실 PLC 비동기 스캔 대비)."""
    st, spec = _st_and_spec("motor_start_stop")
    timeline = _CASES["motor_start_stop"]
    report = run_differential(
        st, spec, SimBackedLink(st, timeline, duration_ms=200, step_ms=100),
        timeline, duration_ms=200, step_ms=100,
    )
    assert report.notes
    assert any("settle" in n for n in report.notes)


def test_connect_openplc_requires_host() -> None:
    """host 도 env OPENPLC_HOST 도 없으면 ValueError(네트워크 시도 전에 차단)."""
    saved = os.environ.pop("OPENPLC_HOST", None)
    try:
        with pytest.raises(ValueError, match="host"):
            connect_openplc()
    finally:
        if saved is not None:
            os.environ["OPENPLC_HOST"] = saved


def test_connect_openplc_uses_link_factory_seam() -> None:
    """link_factory 주입 시 modbus_tcp 없이도 PlcLink 를 만든다(디커플링 seam)."""
    st, _ = _st_and_spec("motor_start_stop")
    timeline = _CASES["motor_start_stop"]
    made: dict[str, object] = {}

    def factory(host: str, port: int) -> SimBackedLink:
        made["host"] = host
        made["port"] = port
        return SimBackedLink(st, timeline, duration_ms=200, step_ms=100)

    link = connect_openplc("10.0.0.5", 1502, link_factory=factory)
    assert made == {"host": "10.0.0.5", "port": 1502}
    assert isinstance(link, SimBackedLink)


def test_connect_openplc_inline_requires_addr_maps() -> None:
    """인라인 경로에 주소 맵이 없으면 ValueError(네트워크 시도 전에 차단)."""
    with pytest.raises(ValueError, match="in_addr"):
        connect_openplc("10.0.0.5")


def test_linear_bit_map_helper() -> None:
    """linear_bit_map 은 심볼을 start 부터 0,1,2,... 비트주소로 배치한다."""
    assert linear_bit_map(["A", "B", "C"]) == {"A": 0, "B": 1, "C": 2}
    assert linear_bit_map(["X", "Y"], start=8) == {"X": 8, "Y": 9}


@pytest.mark.skipif(
    not os.environ.get("OPENPLC_HOST"),
    reason="실 OpenPLC 가 없으면 skip (CI-safe). OPENPLC_HOST 설정 시 활성화.",
)
def test_real_openplc_agrees_with_simulator() -> None:
    """실 OpenPLC vs 우리 시뮬레이터 차분 검증(하드웨어 있을 때만).

    OpenPLC 에 motor_start_stop 의 PLCopen XML(app/export/plcopen.py)을 임포트·실행
    중이라고 가정한다. 입력/출력 비트주소는 런타임 변수 선언 순서를 따라 선형 배치.
    """
    st, spec = _st_and_spec("motor_start_stop")
    timeline = _CASES["motor_start_stop"]
    in_addr = linear_bit_map(["START", "STOP"])
    out_addr = linear_bit_map(["MOTOR"])
    link = connect_openplc(in_addr=in_addr, out_addr=out_addr)
    try:
        report = run_differential(
            st, spec, link, timeline, duration_ms=2000, step_ms=200,
            settle_hook=lambda: __import__("time").sleep(0.1),
        )
    finally:
        link.close()
    assert report.agreement is True, report.summary
