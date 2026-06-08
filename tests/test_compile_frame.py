"""의도 프레임 → 명세 컴파일러 테스트 (천장 돌파 — 레시피 없는 조합적 합성).

핵심 주장: 어떤 단일 레시피도 커버하지 않는 *임의 조합* 의도가 검증 가능한 ST 로
컴파일된다(이중코일 0, verify 통과). 미해결 절은 confident=False 로 정직히 강등.
"""

from __future__ import annotations

import pytest

from app.compile_frame import frame_to_spec
from app.memory_map import detect_double_coils
from app.synth import covers_all_outputs, synthesize_st
from app.verifier import verify


def _outs(spec) -> set[str]:  # type: ignore[no-untyped-def]
    return {p.symbol for p in spec.io_points if p.direction.value == "OUTPUT"}


def test_novel_three_subsystem_compiles_and_verifies() -> None:
    """수위펌프 + 카운터배출 + 알람 — 어떤 레시피에도 없는 3-서브시스템 조합."""
    r = frame_to_spec(
        "저수위 되면 펌프 켜고 고수위 되면 펌프 끄고 부품 10개 차면 배출하고 고장 나면 경광등 켜"
    )
    assert r.confident is True
    assert _outs(r.spec) == {"PUMP", "EJECT", "BEACON"}
    st = synthesize_st(r.spec)
    # 수위 히스테리시스(LO on / HI off) + 카운터 + 알람이 한 프로그램에.
    assert "PUMP := (LO_LS OR PUMP) AND NOT (HI_LS);" in st
    assert any(c.preset == 10 for c in r.spec.counters)
    assert "BEACON := (FAULT OR BEACON);" in st
    assert covers_all_outputs(r.spec)
    assert detect_double_coils(st) == {}
    assert verify(r.spec, st).passed


def test_dual_analog_compound_compiles() -> None:
    """압력 + 온도 두 아날로그 설정값을 한 프로그램으로 — 비교기 2개."""
    r = frame_to_spec("압력 5바 넘으면 밸브 닫고 온도 200도 되면 히터 꺼")
    assert r.confident is True
    flags = {c.flag for c in r.spec.comparators}
    assert {"PRESSURE_HI", "TEMP_HI"} <= flags
    st = synthesize_st(r.spec)
    assert detect_double_coils(st) == {}
    assert verify(r.spec, st).passed


def test_simple_motor_compiles() -> None:
    r = frame_to_spec("버튼 누르면 모터 돌리고")
    assert "MOTOR" in _outs(r.spec)
    st = synthesize_st(r.spec)
    assert verify(r.spec, st).passed


def test_out_of_domain_not_confident() -> None:
    r = frame_to_spec("오늘 점심 뭐 먹지")
    assert r.confident is False


def test_compile_is_deterministic() -> None:
    t = "저수위 되면 펌프 켜고 고수위 되면 펌프 끄고 고장 나면 경광등 켜"
    a, b = frame_to_spec(t), frame_to_spec(t)
    assert synthesize_st(a.spec) == synthesize_st(b.spec)
    assert a.confident == b.confident


@pytest.mark.parametrize("text", [
    "저수위 되면 펌프 켜고 고수위 되면 꺼",
    "부품 5개 차면 배출",
    "고장 나면 경광등 켜",
    "압력 3바 넘으면 펌프 꺼",
])
def test_various_intents_compile_and_verify(text: str) -> None:
    r = frame_to_spec(text)
    st = synthesize_st(r.spec)
    assert detect_double_coils(st) == {}
    assert verify(r.spec, st).passed
