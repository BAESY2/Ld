"""속성 기반 퍼징 — 결정론 스캔 시뮬레이터의 안전·결정론 불변식 자동 탐색.

Hypothesis 로 합성된 실제 레시피(build_spec → synthesize_st)를 무작위 입력
타임라인으로 가동(simulate)하면서, 모든 생성 트레이스에 대해 다음 불변식이
깨지는 최소 반례를 자동으로 찾는다(shrinking):

  1. 인터락 상호배타: spec 의 선언된 인터락 쌍은 어떤 샘플에서도 동시 ON 불가
     (fwd_rev / jog_run / star_delta — spec.interlocks 로 데이터 구동).
  2. 시퀀서 one-hot: car_wash / timed_traffic / batch_fill_mix_drain 은
     매 샘플 단계 출력이 최대 1개만 ON.
  3. 결정론: 동일 타임라인으로 두 번 가동하면 출력 트레이스가 바이트 동일.
  4. 무크래시·유계: in-bounds 타임라인에서 절대 예외 없이, MAX_SIM_SAMPLES 이하.

CLAUDE.md 결정론 요구에 따라 derandomize 프로파일을 등록해 실행 간 재현 가능하게
고정한다. LLM 호출이 없으므로 키 불필요·CI 안전.
"""

from __future__ import annotations

import pytest

pytest.importorskip("hypothesis", reason="hypothesis (dev extra) 미설치 — 속성 퍼징 스킵")

from hypothesis import HealthCheck, given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from app.simulator import MAX_SIM_SAMPLES, SimResult, simulate
from app.synth import synthesize_st
from app.wizard import build_spec, list_recipes

# ── 재현 가능 프로파일(실행 간 동일 예제 → CLAUDE.md 결정론 규칙) ──────────────
settings.register_profile(
    "stateful_sim",
    max_examples=50,
    deadline=None,  # 합성+가동은 빠르지만 CI 머신 편차로 인한 flaky 방지
    derandomize=True,  # 고정 시드: 두 번 돌려도 같은 예제·같은 반례
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
settings.load_profile("stateful_sim")

ALL_RECIPE_IDS: list[str] = [str(r["id"]) for r in list_recipes()]

# spec 이 인터락을 선언하는(쌍이 1개 이상) 레시피만 인터락 불변식이 의미가 있다.
# 데이터 구동: fwd_rev / jog_run / star_delta 가 여기에 해당.
# (two_hand_safety 는 출력이 1개라 인터락 쌍이 없음 → 자연히 제외됨)
INTERLOCK_RECIPE_IDS: list[str] = [
    rid for rid in ALL_RECIPE_IDS if build_spec(rid).interlocks
]

# 타임드 시퀀서 — one-hot(매 샘플 단계 출력 ≤ 1) 이 구조적으로 보장돼야 한다.
SEQUENCER_RECIPE_IDS: list[str] = ["car_wash", "timed_traffic", "batch_fill_mix_drain"]


def _inputs_of(rid: str) -> list[str]:
    spec = build_spec(rid)
    return [p.symbol for p in spec.io_points if p.direction.value == "INPUT"]


def _st_of(rid: str) -> str:
    return synthesize_st(build_spec(rid))


@st.composite
def timeline_and_clock(
    draw: st.DrawFn, input_syms: list[str]
) -> tuple[list[tuple[int, dict[str, bool]]], int, int]:
    """무작위 입력 타임라인 + step/duration 생성(MAX_SIM_SAMPLES 이내 보장).

    - step_ms: 10..500 (sane bounds)
    - duration_ms: step_ms*0 .. step_ms*(샘플상한 미만) — 샘플 수가 상한을 넘지 않게 clamp
    - 각 이벤트: 임의 시각 + 입력 심볼 부분집합의 on/off 엣지
    """
    step_ms = draw(st.integers(min_value=10, max_value=500))
    # 샘플 수 = duration//step + 1 ≤ MAX_SIM_SAMPLES. 퍼징 속도를 위해 80 샘플로 제한.
    max_samples = min(MAX_SIM_SAMPLES, 80)
    max_events = max_samples - 1
    n_samples = draw(st.integers(min_value=1, max_value=max_samples))
    duration_ms = (n_samples - 1) * step_ms

    n_events = draw(st.integers(min_value=0, max_value=min(12, max(0, max_events))))
    timeline: list[tuple[int, dict[str, bool]]] = []
    if input_syms:
        for _ in range(n_events):
            # 가동 구간 내 임의 시각(경계 포함)
            t = draw(st.integers(min_value=0, max_value=max(0, duration_ms)))
            # 입력 심볼의 비어있지 않은 부분집합에 on/off 값을 무작위 배정
            syms = draw(
                st.lists(
                    st.sampled_from(input_syms),
                    min_size=1,
                    max_size=len(input_syms),
                    unique=True,
                )
            )
            edge = {s: draw(st.booleans()) for s in syms}
            timeline.append((t, edge))
    return timeline, duration_ms, step_ms


def _serialize(res: SimResult) -> list[tuple[int, tuple[bool, ...], tuple[bool, ...]]]:
    """트레이스를 비교용 불변 표현으로 직렬화(바이트 동일성 비교용)."""
    out_syms = res.outputs
    in_syms = res.inputs
    return [
        (
            s.t_ms,
            tuple(s.inputs.get(k, False) for k in in_syms),
            tuple(s.outputs.get(k, False) for k in out_syms),
        )
        for s in res.samples
    ]


# ── 1) 모든 15개 레시피: 무크래시·유계·결정론 ───────────────────────────────
@given(data=st.data())
def test_no_crash_bounded_and_deterministic(data: st.DataObject) -> None:
    """모든 레시피에서 in-bounds 타임라인은 예외 없이 가동되고 유계·결정론적이다."""
    for rid in ALL_RECIPE_IDS:
        st_code = _st_of(rid)
        inputs = _inputs_of(rid)
        timeline, duration_ms, step_ms = data.draw(
            timeline_and_clock(inputs), label=f"timeline[{rid}]"
        )
        r1 = simulate(st_code, timeline, duration_ms=duration_ms, step_ms=step_ms)
        # 유계
        assert len(r1.samples) <= MAX_SIM_SAMPLES, f"{rid}: {len(r1.samples)} 샘플"
        assert len(r1.samples) == duration_ms // step_ms + 1, f"{rid}: 샘플 수 불일치"
        # 결정론: 동일 타임라인 재가동 → 바이트 동일
        r2 = simulate(st_code, timeline, duration_ms=duration_ms, step_ms=step_ms)
        assert _serialize(r1) == _serialize(r2), (
            f"{rid}: 비결정론적 트레이스 — timeline={timeline}, "
            f"duration={duration_ms}, step={step_ms}"
        )


# ── 2) 인터락 상호배타(fwd_rev / jog_run / star_delta) ──────────────────────
@given(data=st.data())
def test_interlock_mutual_exclusion(data: st.DataObject) -> None:
    """선언된 인터락 쌍은 어떤 입력 타임라인·어떤 샘플에서도 동시에 ON 될 수 없다."""
    for rid in INTERLOCK_RECIPE_IDS:
        spec = build_spec(rid)
        st_code = synthesize_st(spec)
        inputs = [p.symbol for p in spec.io_points if p.direction.value == "INPUT"]
        timeline, duration_ms, step_ms = data.draw(
            timeline_and_clock(inputs), label=f"timeline[{rid}]"
        )
        res = simulate(st_code, timeline, duration_ms=duration_ms, step_ms=step_ms)
        for pair in spec.interlocks:
            for s in res.samples:
                a = s.outputs.get(pair.output_a, False)
                b = s.outputs.get(pair.output_b, False)
                assert not (a and b), (
                    f"{rid} @ {s.t_ms}ms: 인터락 위반 "
                    f"{pair.output_a}+{pair.output_b} 동시 ON — "
                    f"timeline={timeline}, duration={duration_ms}, step={step_ms}"
                )


# ── 3) 시퀀서 one-hot(car_wash / timed_traffic / batch) ─────────────────────
@given(data=st.data())
def test_sequencer_one_hot(data: st.DataObject) -> None:
    """타임드 시퀀서는 매 샘플 단계 출력이 최대 1개만 ON(one-hot)."""
    for rid in SEQUENCER_RECIPE_IDS:
        spec = build_spec(rid)
        st_code = synthesize_st(spec)
        inputs = [p.symbol for p in spec.io_points if p.direction.value == "INPUT"]
        timeline, duration_ms, step_ms = data.draw(
            timeline_and_clock(inputs), label=f"timeline[{rid}]"
        )
        res = simulate(st_code, timeline, duration_ms=duration_ms, step_ms=step_ms)
        for s in res.samples:
            on = [k for k, v in s.outputs.items() if v]
            assert len(on) <= 1, (
                f"{rid} @ {s.t_ms}ms: one-hot 위반 {on} — "
                f"timeline={timeline}, duration={duration_ms}, step={step_ms}"
            )
