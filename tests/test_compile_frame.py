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
    assert {"PRESSURE_GE5", "TEMP_GE200"} <= flags
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


def test_same_signal_multiple_thresholds_no_double_coil() -> None:
    """회귀(Track B 발견): 같은 신호 다중 임계가 비교기 플래그 충돌→이중코일 내던 버그."""
    r = frame_to_spec("온도 75도 되면 히터 켜고 온도 85도 넘으면 히터 꺼")
    st = synthesize_st(r.spec)
    assert detect_double_coils(st) == {}  # 핵심: 이중코일 0
    flags = {c.flag for c in r.spec.comparators}
    assert flags == {"TEMP_GE75", "TEMP_GE85"}  # 임계별 고유 플래그
    assert "HEATER := (TEMP_GE75 OR HEATER) AND NOT (TEMP_GE85);" in st
    assert verify(r.spec, st).passed and r.confident


@pytest.mark.parametrize("text", [
    "온도 올려", "압력 켜", "탱크 켜", "부품 켜", "수위 돌려",
])
def test_nonsense_action_on_sensor_is_rejected(text: str) -> None:
    """의미 부적합(측정/신호/용기 구동)은 confident=False 로 정직 거절(literal 난센스 차단)."""
    assert frame_to_spec(text).confident is False


@pytest.mark.parametrize("text", [
    "펌프 켜", "밸브 열어", "모터 돌려", "히터 켜",
    "저수위면 펌프 켜고 고수위면 펌프 꺼",  # 명사+'면' 조건 파싱(되 없이도)
])
def test_legitimate_actions_still_compile(text: str) -> None:
    r = frame_to_spec(text)
    assert r.confident is True
    assert verify(r.spec, synthesize_st(r.spec)).passed


def test_sequence_compiles_to_timed_sequencer() -> None:
    """'A 켜고 다음 B 하고 다음 C' → 검증된 one-hot 타임드 시퀀서(천장: 순차/타이밍)."""
    r = frame_to_spec("모터 돌리고 다음 펌프 켜고 다음 밸브 열어")
    st = synthesize_st(r.spec)
    assert r.confident
    assert [s.name for s in r.spec.states] == ["IDLE", "S0", "S1", "S2"]  # 3단계 시퀀서
    assert len(r.spec.timers) == 3
    assert covers_all_outputs(r.spec)
    assert detect_double_coils(st) == {}
    assert verify(r.spec, st).passed


def test_sequencer_one_hot_is_formally_proven() -> None:
    """시퀀서 단계 출력의 at-most-one(one-hot)이 k-귀납으로 *증명*된다(시퀀스 안전 형식보장)."""
    from app.verifier import proven_safe_groups

    r = frame_to_spec("모터 돌리고 다음 펌프 켜고 다음 밸브 열어")
    st = synthesize_st(r.spec)
    groups = [set(g) for g in proven_safe_groups(r.spec, st)]
    assert {"MOTOR", "PUMP", "VALVE"} in groups  # 세 단계가 동시활성 불가로 증명됨
    assert verify(r.spec, st).passed


def test_sequence_delay_from_n_seconds() -> None:
    """'N초 후/뒤'의 지연이 해당 단계 타이머 프리셋이 된다."""
    r = frame_to_spec("펌프 켜고 3초 후 모터 돌리고")
    assert any(t.preset_ms == 3000 for t in r.spec.timers)
    assert verify(r.spec, synthesize_st(r.spec)).passed


def test_multi_instance_distinct_output_symbols() -> None:
    """'1번 모터/2번 모터', '펌프1/펌프2' → 인스턴스별 *고유* 출력 심볼(천장: 다중 인스턴스)."""
    def outs(text: str) -> set[str]:
        r = frame_to_spec(text)
        st = synthesize_st(r.spec)
        assert detect_double_coils(st) == {} and verify(r.spec, st).passed
        return {p.symbol for p in r.spec.io_points if p.direction.value == "OUTPUT"}

    assert {"MOTOR1", "MOTOR2"} <= outs("1번 모터 돌리고 2번 모터 멈춰")
    assert {"PUMP1", "PUMP2"} <= outs("펌프1 켜고 펌프2 끄고")
    assert {"GATEA", "GATEB"} <= outs("게이트A 열고 게이트B 닫아")


def test_multi_instance_mutex_proven() -> None:
    """'1번 도는 동안 2번 못' 류 인스턴스 상호배제가 k-귀납으로 증명된다."""
    from app.verifier import proven_safe_pairs

    r = frame_to_spec("1번 모터 돌리고 2번 모터 도는데 동시에 못 돌게")
    st = synthesize_st(r.spec)
    pairs = {tuple(sorted(p)) for p in proven_safe_pairs(r.spec, st)}
    assert ("MOTOR1", "MOTOR2") in pairs
    assert verify(r.spec, st).passed


def test_count_not_confused_with_instance() -> None:
    """'부품 10개'의 10은 개수(인스턴스 아님) — 회귀."""
    r = frame_to_spec("부품 10개 차면 배출")
    assert any(c.preset == 10 for c in r.spec.counters)
    assert "EJECT" in {p.symbol for p in r.spec.io_points if p.direction.value == "OUTPUT"}


def test_mutex_cue_auto_infers_proven_interlock() -> None:
    """'동시에 안' 단서 → 서로 다른 기기 출력 간 상호배제를 자동 합성하고 k-귀납으로 증명."""
    from app.verifier import proven_safe_pairs

    r = frame_to_spec("히터 켜고 쿨러 켜는데 동시에 안 켜지게")
    st = synthesize_st(r.spec)
    pairs = {tuple(sorted(p)) for p in proven_safe_pairs(r.spec, st)}
    assert ("COOLER", "HEATER") in pairs  # 상호배제가 *증명*됨
    assert detect_double_coils(st) == {}
    assert verify(r.spec, st).passed


def test_no_mutex_cue_no_interlock() -> None:
    """상호배제 단서가 없으면 인터락을 만들지 않는다(거짓 인터락 방지)."""
    r = frame_to_spec("저수위 되면 펌프 켜고 고수위 되면 펌프 꺼")
    assert r.spec.interlocks == []


def test_deviceless_stop_resolves_to_previous_device() -> None:
    """회귀(유령 OUT): '정지 누르면 멈춰'의 무주어 멈춤이 직전 기기(MOTOR)로 해소된다.

    이전엔 MOTOR 는 못 멈추고 유령 'OUT := OUT AND NOT (STOP)' 코일이 생겼다(의미 버그).
    """
    r = frame_to_spec("버튼 누르면 모터 돌고 정지 누르면 멈춰")
    st = synthesize_st(r.spec)
    assert r.confident is True
    assert _outs(r.spec) == {"MOTOR"}          # 유령 OUT 없음
    assert "MOTOR := (START OR MOTOR) AND NOT (STOP);" in st  # 정지가 진짜 멈춘다
    assert verify(r.spec, st).passed


def test_deviceless_off_anaphora_hysteresis() -> None:
    """'고수위 되면 꺼'(무주어) → 직전 기기 PUMP 의 OFF 조건으로 붙는다."""
    r = frame_to_spec("저수위 되면 펌프 켜고 고수위 되면 꺼")
    st = synthesize_st(r.spec)
    assert _outs(r.spec) == {"PUMP"}
    assert "PUMP := (LO_LS OR PUMP) AND NOT (HI_LS);" in st
    assert verify(r.spec, st).passed and r.confident


def test_deviceless_action_without_antecedent_rejected() -> None:
    """선행 기기 없는 무주어 동작('멈춰')은 유령 출력 대신 정직 미해결."""
    r = frame_to_spec("멈춰")
    assert r.confident is False
    assert any("대상 기기" in u for u in r.unresolved)


def test_below_threshold_hysteresis_pump() -> None:
    """'밑으로 떨어지면'(LE) + '넘으면'(GE) = 올바른 히스테리시스 펌프 제어."""
    r = frame_to_spec("압력 3바 밑으로 떨어지면 펌프 켜고 압력 5바 넘으면 펌프 꺼")
    st = synthesize_st(r.spec)
    ops = {(c.flag, c.op.value) for c in r.spec.comparators}
    assert ("PRESSURE_LE3", "<=") in ops and ("PRESSURE_GE5", ">=") in ops
    assert "PUMP := (PRESSURE_LE3 OR PUMP) AND NOT (PRESSURE_GE5);" in st
    assert detect_double_coils(st) == {} and verify(r.spec, st).passed


def test_vision_ng_condition_and_large_compound() -> None:
    """'불량 나면' 비전 NG 조건 + 6서브시스템 대규모 복합문이 즉시 컴파일·검증된다."""
    r = frame_to_spec("불량 나면 로봇 켜고 배출해")
    st = synthesize_st(r.spec)
    assert "ROBOT := (NG_SENSOR OR ROBOT);" in st
    assert verify(r.spec, st).passed and r.confident

    big = frame_to_spec(
        "저수위 되면 펌프 켜고 고수위 되면 펌프 끄고 압력 5바 넘으면 밸브 닫고 "
        "부품 10개 차면 로봇 켜고 불량 나면 배출하고 고장 나면 사이렌 울려"
    )
    assert big.confident
    outs = _outs(big.spec)
    assert {"PUMP", "VALVE", "ROBOT", "EJECT", "SIREN"} <= outs   # 6서브시스템
    st2 = synthesize_st(big.spec)
    assert detect_double_coils(st2) == {} and verify(big.spec, st2).passed


def test_star_delta_starter_compiles_and_proves() -> None:
    """'스타델타 기동' → 표준 Y-Δ 회로: Y⊥Δ k-귀납 증명 + 1스캔 개방전환 데드타임."""
    from app.simulator import simulate
    from app.verifier import proven_safe_pairs

    r = frame_to_spec("5.5킬로와트 모터 스타델타로 기동해")
    assert r.confident
    st = synthesize_st(r.spec)
    assert "MOTOR_D := (MOTOR AND T1.Q) AND NOT MOTOR_Y;" in st
    assert verify(r.spec, st).passed
    pairs = {tuple(sorted(p)) for p in proven_safe_pairs(r.spec, st)}
    assert ("MOTOR_D", "MOTOR_Y") in pairs        # 상간단락 불가가 *증명*됨
    # kW 가 명세에 실린다(산식 선정의 입력)
    assert next(p.power_kw for p in r.spec.io_points if p.symbol == "MOTOR") == 5.5
    # 실거동: 전환 시 동시 ON 0 + 데드타임 ≥1스캔
    res = simulate(st, [(100, {"START": True}), (300, {"START": False})],
                   duration_ms=9000, step_ms=100)
    y, d = res.output_trace("MOTOR_Y"), res.output_trace("MOTOR_D")
    assert not any(a and b for a, b in zip(y, d, strict=True))
    last_y = max(i for i, v in enumerate(y) if v)
    first_d = min(i for i, v in enumerate(d) if v)
    assert first_d - last_y >= 2                  # 개방전환 데드타임(1스캔 이상)


def test_pump_alternation_compiles_proves_and_simulates() -> None:
    """'펌프 두 대 교대로' → 교번 표준회로: PUMP1⊥PUMP2 k-귀납 증명 + 실거동 교번.

    실거동(스캔 시뮬레이션): 기동 1회차 PUMP1 → 정지 → 재기동 시 PUMP2 로 교번 →
    재정지 → 3회차 다시 PUMP1. 운전 중 재기동 누름은 펌프를 갈아타지 않고,
    두 펌프 동시 ON 은 단 한 스캔도 없다.
    """
    from app.simulator import simulate
    from app.verifier import proven_safe_pairs

    r = frame_to_spec("펌프 두 대 교대로 운전해")
    assert r.confident is True
    st = synthesize_st(r.spec)
    # 렁 순서가 의미를 만든다 — 엣지/직전값/토글/자기유지/상보 출력 순.
    assert st.splitlines() == [
        "EDGE := (START AND NOT START_PREV) AND NOT RUN;",
        "START_PREV := START;",
        "TGL := (EDGE AND NOT TGL) OR (TGL AND NOT EDGE);",
        "RUN := (START OR RUN) AND NOT STOP;",
        "PUMP1 := RUN AND TGL;",
        "PUMP2 := RUN AND NOT TGL;",
    ]
    assert covers_all_outputs(r.spec)
    assert detect_double_coils(st) == {}
    assert verify(r.spec, st).passed
    pairs = {tuple(sorted(p)) for p in proven_safe_pairs(r.spec, st)}
    assert ("PUMP1", "PUMP2") in pairs  # 동시 기동 불가가 *증명*됨

    res = simulate(
        st,
        [(100, {"START": True}), (300, {"START": False}),
         (500, {"START": True}), (700, {"START": False}),   # 운전 중 재누름(교체 금지)
         (1000, {"STOP": True}), (1200, {"STOP": False}),
         (2000, {"START": True}), (2200, {"START": False}),
         (3000, {"STOP": True}), (3200, {"STOP": False}),
         (4000, {"START": True}), (4200, {"START": False})],
        duration_ms=5000, step_ms=100,
    )
    p1, p2 = res.output_trace("PUMP1"), res.output_trace("PUMP2")
    assert not any(a and b for a, b in zip(p1, p2, strict=True))  # 동시 ON 0

    def at(trace: list[bool], t_ms: int) -> bool:
        return trace[t_ms // 100]

    assert at(p1, 100) and not at(p2, 100)        # 기동 1회차 → PUMP1
    assert at(p1, 900) and not at(p2, 900)        # 운전 중 재누름에도 PUMP1 유지
    assert not at(p1, 1000) and not at(p2, 1000)  # 정지
    assert at(p2, 2000) and not at(p1, 2000)      # 재기동 → PUMP2 로 교번
    assert not at(p1, 3000) and not at(p2, 3000)  # 재정지
    assert at(p1, 4000) and not at(p2, 4000)      # 3회차 → 다시 PUMP1


@pytest.mark.parametrize("text,outs", [
    ("펌프 교번 운전", {"PUMP1", "PUMP2"}),
    ("펌프 두 대 교대로 운전해", {"PUMP1", "PUMP2"}),
    ("모터 두 대 번갈아 돌려", {"MOTOR1", "MOTOR2"}),  # 기기 일반화(접두 베이스)
])
def test_alternation_cue_variants_route(text: str, outs: set[str]) -> None:
    """'교대/교번/번갈아' 단서 변형이 모두 교번 회로로 라우팅·검증된다."""
    r = frame_to_spec(text)
    assert r.confident is True
    assert outs <= _outs(r.spec)
    st = synthesize_st(r.spec)
    assert detect_double_coils(st) == {}
    assert verify(r.spec, st).passed


def test_alternator_pumps_recognized_in_plant() -> None:
    """PUMP1/PUMP2 가 설비 설계에서 pump 종류로 잡히고, 내부 릴레이는 M 주소를 받는다."""
    from app.plant import plant_from_spec

    r = frame_to_spec("펌프 교번 운전")
    layout = plant_from_spec(r.spec)
    kinds = {d.symbol: d.kind for d in layout.devices}
    assert kinds["PUMP1"] == "pump" and kinds["PUMP2"] == "pump"
    addrs = {d.symbol: d.address for d in layout.devices}
    assert addrs["TGL"].startswith("M") and addrs["RUN"].startswith("M")  # 내부 릴레이 M
    assert addrs["PUMP1"].startswith("P") and addrs["PUMP2"].startswith("P")


def test_fwd_rev_interlock_proven() -> None:
    """정역 운전 — MOTOR_FWD⊥MOTOR_REV 동시투입 금지가 k-귀납으로 증명된다."""
    from app.verifier import proven_safe_pairs

    r = frame_to_spec("정회전 돌리고 역회전 돌리고 동시에 안 되게")
    st = synthesize_st(r.spec)
    pairs = {tuple(sorted(p)) for p in proven_safe_pairs(r.spec, st)}
    assert ("MOTOR_FWD", "MOTOR_REV") in pairs
    assert verify(r.spec, st).passed and r.confident


def test_unknown_device_not_renamed_to_eject() -> None:
    """회귀(기기 뒤바뀜): 미등록 기기 동작이 EJECT 로 둔갑하던 폴백 — 카테고리명 유지."""
    r = frame_to_spec("지그 고정해")
    st = synthesize_st(r.spec)
    assert "JIG :=" in st and "EJECT" not in st
    assert verify(r.spec, st).passed
    # 무주어 '배출해'는 여전히 EJECT(의도된 동작)
    r2 = frame_to_spec("배출해")
    assert "EJECT :=" in synthesize_st(r2.spec)


def test_estop_guards_all_outputs() -> None:
    """비상정지(ESTOP) — 전 출력에 'AND NOT ESTOP' 가드. 눌리면 모든 출력 즉시 차단."""
    from app.simulator import simulate

    r = frame_to_spec("저수위 되면 펌프 켜고 고수위 되면 펌프 끄고 비상정지 누르면 전부 멈춰")
    assert r.confident
    st = synthesize_st(r.spec)
    assert "AND NOT (ESTOP)" in st
    assert verify(r.spec, st).passed and detect_double_coils(st) == {}
    outs = [p.symbol for p in r.spec.io_points if p.direction.value == "OUTPUT"]
    ins = [p.symbol for p in r.spec.io_points if p.direction.value == "INPUT"]
    # 모든 입력을 켜도(ESTOP 포함) ESTOP=1 인 스캔에서 출력은 전부 0 이어야 한다.
    res = simulate(st, [(100, {i: True for i in ins})], duration_ms=2000, step_ms=100)
    for s in res.samples:
        if s.inputs.get("ESTOP"):
            assert not any(s.outputs.get(o) for o in outs), "ESTOP 중 출력 ON — 안전 위반"


def test_estop_not_an_output_device() -> None:
    """ESTOP 은 출력 기기가 아니다(가드일 뿐) — 출력 심볼에 ESTOP 없음."""
    r = frame_to_spec("버튼 누르면 모터 돌고 비상정지 누르면 다 꺼")
    outs = {p.symbol for p in r.spec.io_points if p.direction.value == "OUTPUT"}
    assert outs == {"MOTOR"} and "ESTOP" not in outs
    assert "MOTOR := ((START OR MOTOR)) AND NOT (ESTOP);" in synthesize_st(r.spec)


def test_cascade_conveyor_containment_proven() -> None:
    """캐스케이드 연동 — 하류 먼저 기동·상류는 하류 가드, □(상류→하류) k-귀납 증명."""
    from app.simulator import simulate
    from app.verifier import prove_containment

    r = frame_to_spec("컨베이어 두 대 연동 운전해")
    assert r.confident
    st = synthesize_st(r.spec)
    assert "CONVEYOR1 := RUN AND T1.Q;" in st   # 누적 조건 인라인(점별 함의 가드)
    assert verify(r.spec, st).passed and detect_double_coils(st) == {}
    # 새 속성 클래스: 포함관계(상류가 돌면 하류는 반드시 돌고 있다) 형식 증명.
    assert prove_containment(r.spec, st, [("CONVEYOR1", "CONVEYOR2")]) == frozenset(
        {("CONVEYOR1", "CONVEYOR2")}
    )
    # 실거동: 하류 먼저, 상류는 2s(20스캔) 후 · 포함 위반 0 · STOP 동시 차단.
    res = simulate(st, [(100, {"START": True}), (300, {"START": False}),
                        (5000, {"STOP": True})], duration_ms=7000, step_ms=100)
    c1, c2 = res.output_trace("CONVEYOR1"), res.output_trace("CONVEYOR2")
    assert not any(a and not b for a, b in zip(c1, c2, strict=True))
    f1 = min(i for i, v in enumerate(c1) if v)
    f2 = min(i for i, v in enumerate(c2) if v)
    assert f2 < f1 and (f1 - f2) >= 19          # 하류 선기동 + ~2s 지연


def test_cascade_three_stage_chain() -> None:
    """3대 연동 — 지연 누적(2s/4s)과 체인 가드, 전 쌍 포함 증명."""
    from app.verifier import prove_containment

    r = frame_to_spec("컨베이어 3대 연동해")
    st = synthesize_st(r.spec)
    assert r.confident and verify(r.spec, st).passed
    proven = prove_containment(
        r.spec, st, [("CONVEYOR1", "CONVEYOR2"), ("CONVEYOR2", "CONVEYOR3")])
    assert proven == frozenset({("CONVEYOR1", "CONVEYOR2"), ("CONVEYOR2", "CONVEYOR3")})


def test_containment_proof_is_not_vacuous() -> None:
    """비공허성 — 가드 없는 회로에서는 포함 증명이 *나오지 않는다*(거짓 증명 금지)."""
    from app.verifier import prove_containment

    # 독립 트리거: 센서→히터, 버튼→쿨러 — HEATER on ∧ COOLER off 가 도달 가능.
    r = frame_to_spec("센서 감지되면 히터 켜고 버튼 누르면 쿨러 켜")
    st = synthesize_st(r.spec)
    assert prove_containment(r.spec, st, [("HEATER", "COOLER")]) == frozenset()


def test_two_hand_safety_start() -> None:
    """양수(투핸드) 안전 기동 — 동시성 창 0.5s·비동시 락·해제 후 재시도(ISO 13851 의미)."""
    from app.simulator import simulate

    r = frame_to_spec("양손 버튼 동시에 눌러야 프레스 내려가게")
    assert r.confident
    st = synthesize_st(r.spec)
    assert "PRESS_M := BTN_L AND BTN_R AND NOT LOCK;" in st  # 출력 중 양손 구속(구조)
    assert verify(r.spec, st).passed and detect_double_coils(st) == {}

    def trace(tl: list, dur: int = 3000) -> list:
        return simulate(st, tl, duration_ms=dur, step_ms=100).output_trace("PRESS_M")

    assert any(trace([(200, {"BTN_L": True, "BTN_R": True})]))            # 동시 → 기동
    assert not any(trace([(100, {"BTN_L": True}), (900, {"BTN_R": True})]))  # 0.8s 비동시 → 차단
    assert any(trace([(100, {"BTN_L": True}), (400, {"BTN_R": True})]))   # 0.3s 창내 → 기동
    rearm = trace([(100, {"BTN_L": True}), (900, {"BTN_R": True}),
                   (1500, {"BTN_L": False, "BTN_R": False}),
                   (2000, {"BTN_L": True, "BTN_R": True})])
    assert any(rearm[20:])                                               # 둘 다 뗀 뒤 재기동
    rel = trace([(200, {"BTN_L": True, "BTN_R": True}), (1000, {"BTN_R": False})])
    assert not any(rel[11:])                                             # 한손 해제 → 즉시 정지


def test_two_hand_not_misrouted_by_casual_text() -> None:
    """'양손 조심해' 같은 비제어 문장은 투핸드로 오라우팅되지 않는다(강단서 한정)."""
    assert frame_to_spec("양손 조심해").confident is False
