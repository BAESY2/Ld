"""패턴 라이브러리(Phase L2) 테스트.

각 패턴이 (1) 파싱·트랜스파일 가능하고 (2) 이중코일 0 이며 (3) 인터록 패턴은
상대 출력의 NOT 을 포함해 구조적으로 상호배제됨을 검증한다.
"""

from __future__ import annotations

import pytest

from app.memory_map import detect_double_coils
from app.models import ElementType
from app.patterns import (
    PATTERNS,
    available_patterns,
    build_pattern,
    compose,
    first_out_alarm,
    hi_lo_level,
    interlock_pair,
    jog,
    mode_select,
    seal_in,
    star_delta,
)
from app.transpiler import transpile_st


def _no_double_coils(st: str) -> bool:
    return detect_double_coils(st) == {}


# --- 개별 패턴 -------------------------------------------------------------
def test_seal_in() -> None:
    st = seal_in("MOTOR", "START", "STOP")
    assert st == "MOTOR := (START OR MOTOR) AND NOT STOP;"
    assert _no_double_coils(st)
    assert len(transpile_st(st).rungs) == 1


def test_jog_excludes_run() -> None:
    st = jog("MOTOR_JOG", "JOG_PB", "MOTOR_RUN")
    assert "NOT MOTOR_RUN" in st
    assert _no_double_coils(st)


def test_interlock_pair_mutual_exclusion() -> None:
    st = interlock_pair("FWD", "FWD_PB", "REV", "REV_PB", "STOP")
    # 각 출력식에 상대 출력의 NOT 이 들어가 상호배제
    assert "NOT REV" in st.splitlines()[0]
    assert "NOT FWD" in st.splitlines()[1]
    assert _no_double_coils(st)
    assert len(transpile_st(st).rungs) == 2


def test_hi_lo_level() -> None:
    st = hi_lo_level("PUMP", "LO_LS", "HI_LS")
    assert _no_double_coils(st)
    assert len(transpile_st(st).rungs) == 1


def test_mode_select() -> None:
    st = mode_select("VALVE", "MODE_AUTO", "AUTO_CMD", "MAN_CMD", "STOP")
    assert _no_double_coils(st)
    assert len(transpile_st(st).rungs) == 1


def test_first_out_alarm_two_rungs_locked() -> None:
    st = first_out_alarm("LATCH_A", "FAULT_A", "LATCH_B", "FAULT_B", "RST")
    # 상호 lock-out: A 는 NOT LATCH_B, B 는 NOT LATCH_A 를 포함
    assert "NOT LATCH_B" in st
    assert "NOT LATCH_A" in st
    assert _no_double_coils(st)
    assert len(transpile_st(st).rungs) == 2


def test_star_delta_three_rungs() -> None:
    st = star_delta("MAIN", "STAR", "DELTA", "START", "STOP", "T_DONE")
    assert _no_double_coils(st)
    assert len(transpile_st(st).rungs) == 3
    # 스타/델타 상호배제
    lines = st.splitlines()
    assert "NOT DELTA" in lines[1]
    assert "NOT STAR" in lines[2]


# --- 인터록 패턴이 NC 접점을 만든다 ---------------------------------------
def test_interlock_pair_produces_nc_contacts() -> None:
    st = interlock_pair("FWD", "FWD_PB", "REV", "REV_PB", "STOP")
    ladder = transpile_st(st)
    nc_symbols = {
        el.symbol
        for rung in ladder.rungs
        for br in rung.input_branches
        for el in br.elements
        if el.element_type == ElementType.CONTACT_NC
    }
    # 상대 출력이 NC 접점으로 등장
    assert "REV" in nc_symbols
    assert "FWD" in nc_symbols


# --- 레지스트리 / 조립 -----------------------------------------------------
def test_registry_and_build_pattern() -> None:
    assert "seal_in" in available_patterns()
    st = build_pattern("seal_in", output="M0", start="A", stop="B")
    assert st == "M0 := (A OR M0) AND NOT B;"


def test_all_registered_patterns_are_clean() -> None:
    """등록된 모든 패턴이 더미 파라미터로 이중코일 0 ST 를 생성해야 한다."""
    for name, pat in PATTERNS.items():
        params = {p: f"{p.upper()}" for p in pat.params}
        st = pat.build(**params)
        assert _no_double_coils(st), f"{name} 이중코일 발생: {st}"
        assert transpile_st(st).rungs, f"{name} 트랜스파일 결과 없음"


def test_compose_joins_and_checks() -> None:
    st = compose(
        seal_in("M0", "A", "B"),
        hi_lo_level("PUMP", "LO", "HI"),
    )
    assert "M0 :=" in st and "PUMP :=" in st
    assert _no_double_coils(st)


def test_compose_rejects_double_coil() -> None:
    """두 패턴이 같은 출력을 구동하면 조립이 거부되어야 한다."""
    with pytest.raises(ValueError, match="이중코일"):
        compose(
            seal_in("MOTOR", "A", "B"),
            seal_in("MOTOR", "C", "D"),
        )
