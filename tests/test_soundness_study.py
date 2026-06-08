"""검증기 건전성@규모 회귀 가드 (ROADMAP H2).

scripts/soundness_study.py 의 핵심 불변식을 작은 규모로 CI 에 박는다: k-귀납이 *증명한*
인터락 쌍·그룹을 실행오라클(시뮬레이터)이 단 한 번도 반증하지 못하며(false-proof=0),
오라클이 찾은 위반은 형식검증도 빠짐없이 탐지한다(miss=0). 무작위 시드 고정 → 결정론.
전체(trials=400, random=1000)는 스크립트로 돌리고, 여기선 빠른 표본만 검사한다.
"""

from __future__ import annotations

import pytest

from app.verifier import _HAS_Z3

pytestmark = pytest.mark.skipif(not _HAS_Z3, reason="z3 미설치")


def test_verifier_sound_at_scale_small() -> None:
    from scripts.soundness_study import run

    t = run(n_random=80, seed=1234)
    # 양방향 건전성: 증명한 쌍의 거짓증명 0, 오라클 위반의 미탐지 0.
    assert t.false_proof == 0, "k-귀납이 증명한 쌍을 오라클이 반증함(불건전)"
    assert t.missed_viol == 0, "오라클 위반을 형식검증이 놓침(불건전)"
    # 표본이 의미를 가지도록 증명·위반 둘 다 실제로 발생해야 한다(공허하지 않음).
    assert t.proven_confirmed > 0
    assert t.detected_viol > 0


def test_verifier_group_mutex_sound_at_scale_small() -> None:
    """그룹(one-hot / at-most-one) 단위도 규모 표본에서 건전: false-proof=0, miss=0."""
    from scripts.soundness_study import run_full

    pt, gt = run_full(n_random=120, seed=1234)
    # 쌍·그룹 양쪽 모두 불건전 사례가 없어야 한다.
    assert pt.false_proof == 0 and pt.missed_viol == 0
    assert gt.false_proof == 0, "k-귀납이 증명한 그룹을 오라클이 반증함(불건전)"
    assert gt.missed_viol == 0, "오라클 그룹위반을 형식검증이 놓침(불건전)"
    # 그룹 표본이 공허하지 않게 증명·위반 둘 다 실제로 발생해야 한다.
    assert gt.proven_confirmed > 0, "증명된 그룹 표본이 없음(공허)"
    assert gt.detected_viol > 0, "탐지된 그룹위반 표본이 없음(공허)"
