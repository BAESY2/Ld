"""타임드 시퀀서 one-hot 안전성 독립 검증 단정(키 불필요·결정론).

컴파일러(frame_to_spec)가 '다음/N초 후' 시퀀스 마커로 합성하는 타임드 시퀀서가
(a) 어떤 START/STOP 입력 타임라인에서도 두 단계 출력이 동시에 ON 되지 않고(one-hot),
(b) 시퀀스가 단계를 순서대로(첫→끝) 거친다는 것을 디지털 트윈 시뮬레이터로 단정한다.

검증기(Z3 k-귀납)와 *독립적* 인 교차확인 — Z3 가 "안전"이라 한 것을 실제 PLC 스캔
의미론으로 가동해 반례가 없음을 보인다(자가채점이 아니다).
"""

from __future__ import annotations

import pytest

from app.compile_frame import frame_to_spec
from app.memory_map import detect_double_coils
from app.simulator import simulate
from app.synth import synthesize_st
from scripts.sequencer_safety_bench import (
    _input_timelines,
    _step_duration_ms,
    evaluate_case,
    run,
)

# 대표 시퀀서 — 순차('다음')·타이밍('N초 후')·혼합·2~5단계를 모두 덮는다.
_REPRESENTATIVE: list[tuple[str, list[str]]] = [
    ("모터 돌리고 다음 펌프 켜고 다음 밸브 열어", ["MOTOR", "PUMP", "VALVE"]),
    ("펌프 켜고 3초 후 모터 돌리고", ["PUMP", "MOTOR"]),
    ("램프 켜고 2초 후 부저 켜고 3초 후 사이렌 켜고", ["LAMP", "BUZZER", "SIREN"]),
    ("히터 켜고 다음 송풍기 켜고 다음 펌프 켜고 다음 밸브 열어",
     ["HEATER", "FAN", "PUMP", "VALVE"]),
    ("컨베이어 켜고 다음 로봇 켜고 다음 게이트 열고 다음 호퍼 켜고 다음 도어 열어",
     ["CONVEYOR", "ROBOT", "GATE", "HOPPER", "DOOR"]),
]


def _step_outputs(text: str) -> tuple[str, list[str]]:
    """대표 텍스트를 컴파일해 (ST, 단계 출력 심볼순서)를 돌려준다(전제 단정 포함)."""
    r = frame_to_spec(text)
    assert r.confident, f"시퀀스가 confident 컴파일되지 않음: {text}"
    outputs = [p.symbol for p in r.spec.io_points if p.direction.value == "OUTPUT"]
    assert len(outputs) >= 2, f"단계 출력이 2개 미만: {text}"
    assert len(r.spec.timers) >= 2, f"타이머가 2개 미만(시퀀서 아님): {text}"
    st = synthesize_st(r.spec)
    assert detect_double_coils(st) == {}, f"이중코일 발생: {text}"
    return st, outputs


@pytest.mark.parametrize("text,expect_outs", _REPRESENTATIVE)
def test_expected_step_outputs(text: str, expect_outs: list[str]) -> None:
    """대표 시퀀서가 기대한 단계 출력 심볼을 *순서대로* 합성한다(회귀 고정)."""
    _, outputs = _step_outputs(text)
    assert outputs == expect_outs


@pytest.mark.parametrize("text,_expect", _REPRESENTATIVE)
def test_one_hot_preserved_under_any_timeline(text: str, _expect: list[str]) -> None:
    """(a) 어떤 START/STOP 입력 타임라인에서도 두 단계 동시 ON 이 0(one-hot 보존)."""
    import random

    st, outputs = _step_outputs(text)
    r = frame_to_spec(text)
    max_t = _step_duration_ms([t.preset_ms for t in r.spec.timers])
    rng = random.Random(7)
    timelines = _input_timelines(rng, n_random=12, max_t=max_t)
    for tl in timelines:
        res = simulate(st, tl, duration_ms=max_t, step_ms=100)
        for s in res.samples:
            on = [o for o in outputs if s.outputs.get(o, False)]
            assert len(on) <= 1, (
                f"동시 ON 위반 @ {s.t_ms}ms: {on} (텍스트={text!r}, 타임라인={tl})"
            )


@pytest.mark.parametrize("text,expect_outs", _REPRESENTATIVE)
def test_sequence_walks_all_steps_in_order(text: str, expect_outs: list[str]) -> None:
    """(b) 시퀀스가 단계를 순서대로 거침(첫→끝 도달, 켜지는 순서가 선언 순서와 일치)."""
    st, outputs = _step_outputs(text)
    # START 짧은 펄스 후 손 떼고(자기유지·타이머 핸드오프로) 끝까지 진행.
    r = frame_to_spec(text)
    max_t = _step_duration_ms([t.preset_ms for t in r.spec.timers])
    res = simulate(
        st,
        [(0, {"START": True, "STOP": False}), (300, {"START": False})],
        duration_ms=max_t,
        step_ms=100,
    )
    # 각 단계가 한 번은 ON 된다(비공허성).
    first_on: dict[str, int] = {}
    for o in outputs:
        trace = res.output_trace(o)
        assert any(trace), f"단계 '{o}' 가 한 번도 ON 되지 않음(공허): {text}"
        first_on[o] = trace.index(True)
    # 켜지는 순서가 선언 순서와 일치한다(첫→끝 순차 진행).
    onsets = [first_on[o] for o in outputs]
    assert onsets == sorted(onsets), (
        f"단계 점화 순서가 선언 순서와 다름: {dict(zip(outputs, onsets, strict=True))}"
    )


@pytest.mark.parametrize("text,_expect", _REPRESENTATIVE)
def test_only_one_step_on_with_start_held(text: str, _expect: list[str]) -> None:
    """START 를 끝까지 누른 채로도(재기동 압박) 단계 출력은 항상 ≤ 1 이다."""
    st, outputs = _step_outputs(text)
    r = frame_to_spec(text)
    max_t = _step_duration_ms([t.preset_ms for t in r.spec.timers])
    res = simulate(st, [(0, {"START": True, "STOP": False})],
                   duration_ms=max_t, step_ms=100)
    worst = max(
        (sum(1 for o in outputs if s.outputs.get(o, False)) for s in res.samples),
        default=0,
    )
    assert worst <= 1, f"START 유지 중 동시 ON {worst}개: {text}"


def test_evaluate_case_reports_clean_for_representative() -> None:
    """evaluate_case 가 대표 시퀀서를 위반 0·전 단계 도달로 보고한다(벤치 함수 직접 단정)."""
    import random

    for text, _ in _REPRESENTATIVE:
        rep = evaluate_case(text, random.Random(3), n_random=8)
        assert rep is not None, f"시퀀서로 인식되지 않음: {text}"
        assert rep.one_hot_ok, f"one-hot 위반: {rep.violations}"
        assert rep.all_steps_reached, f"단계 미도달: {rep.reached}"
        assert rep.scans_checked > 0


def test_bench_run_is_deterministic_and_clean() -> None:
    """벤치 전체가 결정론적이고(같은 시드=같은 결과) one-hot 위반 0·전 단계 도달이다."""
    a = run(seed=20260608, n_cases=24)
    b = run(seed=20260608, n_cases=24)
    assert [r.text for r in a.reports] == [r.text for r in b.reports]  # 결정론
    assert a.total_violations == b.total_violations == 0
    assert a.all_one_hot and a.all_steps_reached
    assert len(a.reports) >= 15  # 실질적 규모(대부분이 시퀀서로 인식됨)
    assert a.total_scans > 1000  # 대규모 스캔 검사
