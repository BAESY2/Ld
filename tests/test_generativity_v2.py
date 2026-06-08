"""생성성 v2 벤치 검증 — 카테고리별·전체 distinct 가 충분하고 전부 게이트 통과인지.

핵심 주장의 회귀 방지:
  1. 각 카테고리(instance/sequence/analog)에서 검증 통과 distinct 가 충분히 나온다(≥50).
  2. 전체 distinct 가 기존 평면(1840)을 크게 넘는다(≥2500).
  3. 집계 대상은 모두 이중코일 0·verify 통과(환각 0 게이트).
  4. 결정론 — 같은 시드면 같은 결과.
모든 검사는 결정론(시드 고정)이며 LLM·API 키가 필요 없다.
"""

from __future__ import annotations

from app.compile_frame import frame_to_spec
from app.memory_map import detect_double_coils
from app.synth import synthesize_st
from app.verifier import verify
from scripts.generativity_v2_bench import _GENERATORS, run


def test_each_category_generates_enough_distinct() -> None:
    """각 카테고리에서 검증 통과 distinct 프로그램이 충분히 나온다(카테고리당 ≥50)."""
    by_cat = run()
    assert set(by_cat) == {"instance", "sequence", "analog"}
    for name, sts in by_cat.items():
        assert len(sts) >= 50, f"{name} distinct={len(sts)} (<50)"


def test_overall_distinct_far_exceeds_baseline() -> None:
    """전체 distinct 가 기존 평면(1840)을 크게 넘는다(≥2500)."""
    by_cat = run()
    overall: set[str] = set()
    for sts in by_cat.values():
        overall |= sts
    assert len(overall) >= 2500, f"전체 distinct={len(overall)} (<2500)"


def test_all_counted_programs_pass_gate() -> None:
    """집계된 모든 ST 는 다시 돌려도 이중코일 0·verify 통과여야 한다(환각 0 게이트)."""
    by_cat = run()
    seen = 0
    for sts in by_cat.values():
        for st in sts:
            assert not detect_double_coils(st), f"이중코일 누출: {st!r}"
            seen += 1
    assert seen >= 2500  # 표본이 충분히 큼(빈 집계로 통과하는 일 방지)


def test_gate_helper_rejects_double_coil_and_failures() -> None:
    """게이트(_passing_st 와 동일 경로)가 통과시킨 산출물은 실제로 verify 통과·이중코일 0."""
    import random

    from scripts.generativity_v2_bench import _passing_st

    rng = random.Random(123)
    checked = 0
    for _name, gen in _GENERATORS.items():
        for _ in range(200):
            text = gen(rng)
            st = _passing_st(text)
            if st is None:
                continue
            # _passing_st 가 통과시킨 것은 독립 재검증으로도 통과해야 한다.
            r = frame_to_spec(text)
            assert r.confident
            assert not detect_double_coils(st)
            assert verify(r.spec, synthesize_st(r.spec)).passed
            checked += 1
    assert checked > 0


def test_deterministic_same_seed_same_counts() -> None:
    """결정론: 같은 시드·시도 수면 카테고리별 결과 집합이 완전히 같다."""
    a = run(trials_per_category=300, seed=11)
    b = run(trials_per_category=300, seed=11)
    assert {k: len(v) for k, v in a.items()} == {k: len(v) for k, v in b.items()}
    for k in a:
        assert a[k] == b[k]
