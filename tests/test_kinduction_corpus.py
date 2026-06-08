"""축적 코퍼스 전체에 대한 k-귀납 인터락 증명 회귀 테스트.

data/bootstrap/dataset.json 의 모든 샘플을 (recipe_id, answers) 로 재구성·합성해
k-귀납이 어떤 안전 샘플에서도 인터락 위반(error)을 보고하지 않음을 증명한다.
또한 의도적으로 망가뜨린 ST(상대 NOT 누락)에서는 위반을 반례와 함께 잡는지 확인한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models import Interlock, IODirection, IOPoint, StateMachineSpec
from app.synth import synthesize_st
from app.verifier import (
    _HAS_Z3,
    check_group_mutex_kinduction,
    check_interlocks_kinduction,
    derive_mutex_groups,
)
from app.wizard import RECIPES, build_spec

z3_only = pytest.mark.skipif(not _HAS_Z3, reason="z3 미설치")

_DATASET = Path(__file__).resolve().parent.parent / "data" / "bootstrap" / "dataset.json"


def _load_samples() -> list[dict[str, object]]:
    if not _DATASET.exists():
        return []
    data = json.loads(_DATASET.read_text(encoding="utf-8"))
    return list(data.get("samples", []))


@z3_only
def test_kinduction_no_violation_over_full_corpus() -> None:
    """코퍼스 모든 안전 샘플에서 k-귀납 인터락 error 가 0 이다."""
    samples = _load_samples()
    assert samples, "dataset.json 비어있음(부트스트랩 먼저 생성 필요)"
    checked_interlock = 0
    for s in samples:
        rid = str(s["recipe_id"])
        answers = {str(k): str(v) for k, v in dict(s["answers"]).items()}  # type: ignore[arg-type]
        if rid not in RECIPES:
            continue
        spec = build_spec(rid, answers)
        st = synthesize_st(spec)
        issues = check_interlocks_kinduction(spec, st, k=3)
        errs = [i for i in issues if i.code == "INTERLOCK" and i.severity == "error"]
        assert errs == [], f"{rid} 샘플에서 k-귀납 인터락 위반: {[e.message for e in errs]}"
        if spec.interlocks:
            checked_interlock += 1
    assert checked_interlock > 0, "인터락 있는 샘플이 하나도 검사되지 않음"


@z3_only
def test_kinduction_regression_broken_st_detected() -> None:
    """상대 NOT 보호가 빠진 ST 는 k-귀납이 도달가능 위반(error+반례)으로 잡는다."""
    spec = StateMachineSpec(
        io_points=[
            IOPoint(symbol="FWD_PB", direction=IODirection.INPUT),
            IOPoint(symbol="REV_PB", direction=IODirection.INPUT),
            IOPoint(symbol="MOTOR_FWD", direction=IODirection.OUTPUT),
            IOPoint(symbol="MOTOR_REV", direction=IODirection.OUTPUT),
        ],
        interlocks=[Interlock(output_a="MOTOR_FWD", output_b="MOTOR_REV")],
    )
    broken = (
        "MOTOR_FWD := (FWD_PB OR MOTOR_FWD) AND NOT (STOP);\n"
        "MOTOR_REV := (REV_PB OR MOTOR_REV) AND NOT (STOP);"
    )
    issues = check_interlocks_kinduction(spec, broken, k=3)
    errs = [i for i in issues if i.code == "INTERLOCK" and i.severity == "error"]
    assert len(errs) == 1
    assert errs[0].counterexample != ""
    # 결정론: 반례는 정렬되어 누출 위험 없음
    assert errs[0].counterexample == ", ".join(sorted(errs[0].counterexample.split(", ")))


@z3_only
def test_group_mutex_no_violation_over_recipe_corpus() -> None:
    """≥3 출력 one-hot 그룹을 가진 모든 레시피 합성 ST 에서 GROUP_MUTEX error 가 0 이다.

    인터락 clique 가 ≥3 인 레시피(multiway_sort 의 GATE_A/B/C 등)를 합성해, 그룹
    at-most-one 증명이 안전 샘플에서 거짓 양성을 내지 않음을 확인한다(최소 1개 그룹 검사).
    """
    checked_groups = 0
    for rid in RECIPES:
        spec = build_spec(rid)
        groups = derive_mutex_groups(spec)
        if not groups:
            continue
        st = synthesize_st(spec)
        issues = check_group_mutex_kinduction(spec, st, k=3)
        errs = [i for i in issues if i.code == "GROUP_MUTEX" and i.severity == "error"]
        assert errs == [], f"{rid} 그룹 상호배제 거짓 위반: {[e.message for e in errs]}"
        checked_groups += len(groups)
    assert checked_groups > 0, "≥3 출력 one-hot 그룹을 가진 레시피가 하나도 검사되지 않음"


@z3_only
def test_group_mutex_regression_broken_group_detected() -> None:
    """one-hot 가드가 모두 빠진 3출력 ST 는 그룹 검사가 동시 ON 집합 반례로 잡는다."""
    spec = StateMachineSpec(
        interlocks=[
            Interlock(output_a="A", output_b="B"),
            Interlock(output_a="A", output_b="C"),
            Interlock(output_a="B", output_b="C"),
        ]
    )
    broken = "A := X1 OR A;\nB := X2 OR B;\nC := X3 OR C;"
    issues = check_group_mutex_kinduction(spec, broken, k=3)
    errs = [i for i in issues if i.code == "GROUP_MUTEX" and i.severity == "error"]
    assert len(errs) == 1
    assert "동시 ON" in errs[0].counterexample
