"""프로젝트 합성 코어 — 다중 서브시스템 조립의 결정론·무충돌·교차인터락 검증.

CLAUDE.md: LLM 미사용(키 불필요)·결정론. 합성 결과가 기존 synth/verify
파이프라인을 그대로 통과하고(이중코일 0), 모듈 간 주소·심볼 충돌이 0 임을 증명한다.
"""

from __future__ import annotations

import pytest

from app.memory_map import DeviceAllocator
from app.models import CrossInterlock, ModuleInstance, Project
from app.project import ProjectError, compose
from app.synth import covers_all_outputs, synthesize_st
from app.verifier import verify


def _two_motors() -> Project:
    return Project(
        title="2모터 라인",
        modules=[
            ModuleInstance(name="conv1", recipe="motor_start_stop"),
            ModuleInstance(name="conv2", recipe="motor_start_stop"),
        ],
    )


# ── 네임스페이스 분리: 같은 레시피 2회여도 충돌 0 ──────────────────────────────
def test_same_recipe_twice_namespaced_no_collision() -> None:
    spec = compose(_two_motors())
    symbols = [io.symbol for io in spec.io_points]
    # 같은 레시피지만 프리픽스로 전부 구분된다(6개 모두 유일).
    assert len(symbols) == len(set(symbols)) == 6
    assert "conv1__MOTOR" in symbols
    assert "conv2__MOTOR" in symbols
    state_names = {s.name for s in spec.states}
    assert {"conv1__IDLE", "conv1__RUN", "conv2__IDLE", "conv2__RUN"} <= state_names


def test_composed_spec_synthesizes_and_verifies_clean() -> None:
    spec = compose(_two_motors())
    assert covers_all_outputs(spec)
    st = synthesize_st(spec)
    report = verify(spec, st)
    assert report.passed, report.issues
    # 전역 이중코일 0 (네임스페이스로 구조적 보장).
    assert not any(i.code == "DOUBLE_COIL" for i in report.issues)


def test_composed_addresses_unique_across_modules() -> None:
    spec = compose(_two_motors())
    alloc = DeviceAllocator().build_from_spec(spec)
    addrs = [alloc.address_of(io.symbol) for io in spec.io_points]
    assert all(a is not None for a in addrs)
    assert len(addrs) == len(set(addrs))  # 모듈 간 주소 충돌 0


# ── 모듈 내부 인터락이 리네임 후에도 보존된다 ────────────────────────────────
def test_internal_interlock_preserved_after_rename() -> None:
    proj = Project(
        modules=[ModuleInstance(name="m1", recipe="fwd_rev")],
    )
    spec = compose(proj)
    assert spec.interlocks, "정역 모듈은 인터락을 가져야 한다"
    for il in spec.interlocks:
        assert il.output_a.startswith("m1__")
        assert il.output_b.startswith("m1__")
    st = synthesize_st(spec)
    report = verify(spec, st)
    # 상호배제가 합성식에 보존돼 인터락 error 가 없어야 한다.
    assert report.passed, report.issues


# ── 공유 입력: shared 매핑은 프리픽스를 면제하고 전역 심볼로 묶는다 ───────────
def test_shared_input_merges_to_global_symbol() -> None:
    proj = Project(
        modules=[
            ModuleInstance(
                name="a", recipe="motor_start_stop", shared={"STOP": "MASTER_STOP"}
            ),
            ModuleInstance(
                name="b", recipe="motor_start_stop", shared={"STOP": "MASTER_STOP"}
            ),
        ],
    )
    spec = compose(proj)
    symbols = {io.symbol for io in spec.io_points}
    assert "MASTER_STOP" in symbols
    assert "a__STOP" not in symbols and "b__STOP" not in symbols
    # 공유 입력이 양쪽 전이 조건에 그대로 들어간다.
    conds = " ".join(tr.condition for tr in spec.transitions)
    assert "MASTER_STOP" in conds
    assert verify(spec, synthesize_st(spec)).passed


# ── 교차 인터락: '모듈.심볼' 해석 + 위반 검출 ────────────────────────────────
def test_cross_interlock_resolves_and_merges() -> None:
    proj = Project(
        modules=[
            ModuleInstance(name="pump1", recipe="motor_start_stop"),
            ModuleInstance(name="pump2", recipe="motor_start_stop"),
        ],
        cross_interlocks=[
            CrossInterlock(
                output_a="pump1.MOTOR", output_b="pump2.MOTOR", reason="동시 가동 금지"
            )
        ],
    )
    spec = compose(proj)
    locks = [(il.output_a, il.output_b) for il in spec.interlocks]
    assert ("pump1__MOTOR", "pump2__MOTOR") in locks


def test_cross_interlock_violation_detected_by_verifier() -> None:
    # 두 모터가 독립 기동 → 동시 ON 가능. 교차 인터락만 선언하고 합성식엔 상호배제가
    # 안 들어가므로(레시피 내부 인터락 아님) 검증기가 위반을 잡아야 한다.
    proj = Project(
        modules=[
            ModuleInstance(name="p1", recipe="motor_start_stop"),
            ModuleInstance(name="p2", recipe="motor_start_stop"),
        ],
        cross_interlocks=[
            CrossInterlock(output_a="p1.MOTOR", output_b="p2.MOTOR", reason="동시 금지")
        ],
    )
    spec = compose(proj)
    report = verify(spec, synthesize_st(spec))
    assert not report.passed
    assert any(i.code == "INTERLOCK" and i.severity == "error" for i in report.issues)


# ── 결정론: 같은 프로젝트를 두 번 합성하면 바이트 동일 ───────────────────────
def test_compose_is_deterministic() -> None:
    proj = _two_motors()
    assert compose(proj).model_dump_json() == compose(proj).model_dump_json()


# ── 오류 처리 ────────────────────────────────────────────────────────────────
def test_empty_project_raises() -> None:
    with pytest.raises(ProjectError):
        compose(Project(modules=[]))


def test_duplicate_module_name_raises() -> None:
    proj = Project(
        modules=[
            ModuleInstance(name="x", recipe="motor_start_stop"),
            ModuleInstance(name="x", recipe="motor_start_stop"),
        ],
    )
    with pytest.raises(ProjectError):
        compose(proj)


def test_bad_module_name_raises() -> None:
    proj = Project(modules=[ModuleInstance(name="1 conv", recipe="motor_start_stop")])
    with pytest.raises(ProjectError):
        compose(proj)


def test_unknown_recipe_raises() -> None:
    proj = Project(modules=[ModuleInstance(name="m", recipe="does_not_exist")])
    with pytest.raises(ProjectError):
        compose(proj)


def test_cross_interlock_unknown_module_raises() -> None:
    proj = Project(
        modules=[ModuleInstance(name="m1", recipe="motor_start_stop")],
        cross_interlocks=[CrossInterlock(output_a="ghost.MOTOR", output_b="m1.MOTOR")],
    )
    with pytest.raises(ProjectError):
        compose(proj)


def test_cross_interlock_unknown_symbol_raises() -> None:
    proj = Project(
        modules=[ModuleInstance(name="m1", recipe="motor_start_stop")],
        cross_interlocks=[CrossInterlock(output_a="m1.NOPE", output_b="m1.MOTOR")],
    )
    with pytest.raises(ProjectError):
        compose(proj)
