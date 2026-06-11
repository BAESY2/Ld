"""가이드 마법사 테스트 — 비전문가가 레시피+답변만으로 유효 설계 생성."""

from __future__ import annotations

import pytest

from app.memory_map import detect_double_coils
from app.synth import covers_all_outputs, synthesize_st
from app.verifier import verify
from app.wizard import RECIPES, WizardError, build_spec, list_recipes


def test_list_recipes_shape() -> None:
    recipes = list_recipes()
    assert len(recipes) >= 6
    for r in recipes:
        assert {"id", "title", "description", "category", "fields"} <= set(r)
        assert all({"key", "label", "default", "kind"} <= set(f) for f in r["fields"])  # type: ignore[attr-defined]


@pytest.mark.parametrize("recipe_id", list(RECIPES))
def test_every_recipe_builds_clean_design(recipe_id: str) -> None:
    """모든 레시피가 기본값으로 이중코일 0·검증 통과·완전 커버되는 설계를 만든다."""
    spec = build_spec(recipe_id)
    assert covers_all_outputs(spec), f"{recipe_id}: 출력 미커버"
    st = synthesize_st(spec)
    assert detect_double_coils(st) == {}, f"{recipe_id}: 이중코일"
    report = verify(spec, st)
    errs = [i.code for i in report.issues if i.severity == "error"]
    assert report.passed, f"{recipe_id}: 검증 실패 {errs}"


def test_custom_symbol_names_applied() -> None:
    spec = build_spec("motor_start_stop", {"start": "PB1", "stop": "PB2", "motor": "M1"})
    st = synthesize_st(spec)
    assert "M1 :=" in st and "PB1" in st and "PB2" in st


def test_fwd_rev_has_interlock() -> None:
    spec = build_spec("fwd_rev")
    assert spec.interlocks and spec.interlocks[0].output_a == "MOTOR_FWD"
    st = synthesize_st(spec)
    assert "NOT MOTOR_REV" in st and "NOT MOTOR_FWD" in st


def test_on_delay_uses_timer() -> None:
    spec = build_spec("on_delay", {"delay_sec": "3"})
    assert spec.timers and spec.timers[0].preset_ms == 3000
    assert "T1(IN := START, PT := T#3s);" in synthesize_st(spec)


def test_count_eject_uses_counter() -> None:
    spec = build_spec("count_eject", {"count": "7"})
    assert spec.counters and spec.counters[0].preset == 7


def test_unknown_recipe_raises() -> None:
    with pytest.raises(KeyError):
        build_spec("nope")


def test_wizard_endpoint() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.server import app

    client = TestClient(app)
    assert len(client.get("/api/recipes").json()) >= 6
    r = client.post("/api/wizard", json={"recipe": "fwd_rev", "answers": {}})
    data = r.json()
    assert data["ok"] is True
    assert data["ladder"]["rungs"]
    assert "동작 설명" in data["explanation"]
    assert "하드와이어" in data["safety_notice"]
    bad = client.post("/api/wizard", json={"recipe": "nope", "answers": {}}).json()
    assert bad["ok"] is False


# --- 협의회 QA 회귀 (크래시·틀린통과 방지) ---
@pytest.mark.parametrize("bad", [
    {"start": "A B"}, {"start": "123"}, {"start": "AND"}, {"start": "TRUE"},
    {"start": "A AND B"}, {"motor": "모터"}, {"start": "X;Y"},
])
def test_invalid_symbol_rejected(bad: dict) -> None:
    with pytest.raises(WizardError):
        build_spec("motor_start_stop", bad)


def test_output_input_collision_rejected() -> None:
    with pytest.raises(WizardError, match="같은 이름"):
        build_spec("motor_start_stop", {"start": "X", "motor": "X"})


def test_fwd_rev_duplicate_output_rejected() -> None:
    with pytest.raises(WizardError):
        build_spec("fwd_rev", {"motor_fwd": "OUT", "motor_rev": "OUT"})


def test_auto_manual_is_correct_not_just_passing() -> None:
    """auto_manual: 자동모드+자동명령(수동명령 없이)에도 밸브가 열려야 한다(QA P1#3)."""
    spec = build_spec("auto_manual")
    st = synthesize_st(spec)
    expected = (
        "VALVE := ((MODE_AUTO AND AUTO_CMD) OR (NOT MODE_AUTO AND MAN_CMD)) "
        "AND NOT SYS_STOP;"
    )
    assert expected in st
    assert verify(spec, st).passed


def test_wizard_endpoint_rejects_bad_input_gracefully() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.server import app

    c = TestClient(app)
    r = c.post("/api/wizard", json={"recipe": "motor_start_stop", "answers": {"start": "모터"}})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is False and "신호 이름" in d["error"]


# --- 협의회 라운드2 QA 회귀 ---
def test_two_hand_rejects_same_button() -> None:
    with pytest.raises(WizardError):
        build_spec("two_hand_safety", {"lh": "B", "rh": "B"})


def test_two_hand_guard_in_off_condition() -> None:
    """가드가 열리면 허가가 해제되어야 한다(off 조건에 NOT guard 포함)."""
    spec = build_spec("two_hand_safety")
    leave = [t for t in spec.transitions if t.from_state == "ENABLED"][0]
    assert "GUARD_CLOSED" in leave.condition


def test_decimal_seconds_floored() -> None:
    spec = build_spec("on_delay", {"delay_sec": "3.5"})
    assert spec.timers[0].preset_ms == 3000


def test_wizard_response_carries_recipe_safety_note() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.server import app

    c = TestClient(app)
    d = c.post("/api/wizard", json={"recipe": "two_hand_safety", "answers": {}}).json()
    assert "⛔" in d["safety_note"]  # 강한 안전 경고가 응답에 직접 노출
    # nl-design autobuild 는 *확신할 때만* design 을 만들고 safety_note 를 담는다
    # (확신 못 하면 design=None — 자신있게 틀린 래더를 렌더하지 않는다, P0-1).
    nd = c.post("/api/nl-design", json={"text": "양수조작 허가"}).json()
    assert nd["confident"] is True
    assert nd["design"]["safety_note"]


# --- 뿌리산업/메카피온 신규 레시피 회귀 ---
_ROOT_RECIPES = [
    "heat_treat", "plating_line", "weld_cell",
    "conveyor_divert", "motion_home_move", "press_muting",
]


@pytest.mark.parametrize("recipe_id", _ROOT_RECIPES)
def test_root_recipe_zero_interlock_and_double_coil(recipe_id: str) -> None:
    """신규 레시피: 이중코일 0, 인터락 error 0, 검증 통과(완료 기준)."""
    spec = build_spec(recipe_id)
    st = synthesize_st(spec)
    assert detect_double_coils(st) == {}, f"{recipe_id}: 이중코일"
    report = verify(spec, st)
    il_errs = [i for i in report.issues if i.code == "INTERLOCK" and i.severity == "error"]
    assert not il_errs, f"{recipe_id}: 인터락 error {il_errs}"
    assert report.passed, f"{recipe_id}: 검증 실패"


def test_heat_treat_is_timed_sequence() -> None:
    """열처리는 승온/유지/냉각 3단계 타이머 시퀀스다."""
    spec = build_spec("heat_treat", {"t_ramp": "30", "t_hold": "60", "t_cool": "45"})
    assert len(spec.timers) == 3
    assert spec.timers[0].preset_ms == 30000
    st = synthesize_st(spec)
    assert "HEATER :=" in st and "SOAK :=" in st and "COOL_FAN :=" in st


def test_plating_line_has_four_immersion_stages() -> None:
    spec = build_spec("plating_line")
    outs = {p.symbol for p in spec.io_points if p.direction.name == "OUTPUT"}
    assert {"DEGREASE", "RINSE", "PLATE", "DRY"} <= outs
    assert verify(spec, synthesize_st(spec)).passed


def test_conveyor_divert_has_gate_interlock() -> None:
    """컨베이어 분기: 두 게이트 동시 작동 금지 인터락이 선언되고 증명된다."""
    spec = build_spec("conveyor_divert")
    assert spec.interlocks and {
        spec.interlocks[0].output_a, spec.interlocks[0].output_b
    } == {"GATE_A", "GATE_B"}
    st = synthesize_st(spec)
    assert "NOT GATE_B" in st and "NOT GATE_A" in st
    assert verify(spec, st).passed


def test_motion_one_hot_sequence_and_estop_priority() -> None:
    """모션: 원점→이동→정위치 one-hot 시퀀스, E-stop 정상 해제 시 즉시 IDLE."""
    spec = build_spec("motion_home_move")
    st = synthesize_st(spec)
    # 세 구동 출력이 한 번에 하나씩만 켜진다(이중코일 0, 합성 커버)
    assert detect_double_coils(st) == {}
    assert covers_all_outputs(spec)
    # E-stop(안전 정상 해제)이 모든 단계의 정지 가드에 들어간다(E-stop 우선)
    assert "NOT ESTOP_OK" in st
    leaves = [t for t in spec.transitions if t.to_state == "IDLE"]
    assert any("NOT ESTOP_OK" in t.condition for t in leaves)
    assert verify(spec, st).passed


def test_weld_cell_sequence_no_double_coil() -> None:
    """용접 셀: 클램프→용접→해제 시퀀스가 이중코일 없이 합성된다."""
    spec = build_spec("weld_cell")
    st = synthesize_st(spec)
    assert detect_double_coils(st) == {}
    assert "CLAMP :=" in st and "WELD :=" in st and "UNCLAMP :=" in st


def test_press_muting_rejects_same_button() -> None:
    with pytest.raises(WizardError):
        build_spec("press_muting", {"lh": "B", "rh": "B"})


def test_press_muting_has_strong_safety_note() -> None:
    """프레스 뮤팅은 강한(⛔) 안전 경고를 단다."""
    from app.wizard import RECIPES
    assert "⛔" in RECIPES["press_muting"].safety_note


# --- 라운드3 신규 12 레시피 회귀 ---
_NEW_RECIPES = [
    "three_wire", "cascade_conveyor", "overload_latch", "guard_interlock",
    "tower_lamp", "flasher", "one_shot", "conveyor_jam",
    "retry_alarm", "shutter_gate", "runtime_maint",
]


@pytest.mark.parametrize("rid", _NEW_RECIPES)
def test_new_recipe_synth_verify_clean(rid: str) -> None:
    """신규 레시피: 이중코일 0·인터락오류 0·검증 통과·완전 커버."""
    spec = build_spec(rid)
    assert covers_all_outputs(spec), f"{rid}: 출력 미커버"
    st = synthesize_st(spec)
    assert detect_double_coils(st) == {}, f"{rid}: 이중코일"
    report = verify(spec, st)
    errs = [i.code for i in report.issues if i.severity == "error"]
    assert report.passed, f"{rid}: 검증 실패 {errs}"
    assert "INTERLOCK" not in errs, f"{rid}: 인터락 오류"


def test_three_wire_stop_dominant() -> None:
    """3선식은 정지 우선 — RUN→STOPPED 전이 조건이 정지뿐이어야 한다."""
    spec = build_spec("three_wire")
    leave = [t for t in spec.transitions if t.from_state == "RUN"][0]
    assert leave.condition == "STOP_PB"
    assert "MTR := " in synthesize_st(spec)


def test_cascade_conveyor_timed_sequence() -> None:
    """다단 컨베이어: 타이머로 단계 시간차, 세 컨베이어 모두 출력."""
    spec = build_spec("cascade_conveyor", {"step_sec": "4"})
    assert spec.timers and all(t.preset_ms == 4000 for t in spec.timers)
    outs = {p.symbol for p in spec.io_points if p.description and "컨베이어" in p.description}
    assert {"CONV_UP", "CONV_MID", "CONV_DOWN"} <= outs


def test_shutter_gate_has_interlock() -> None:
    """셔터: 개·폐 동시금지 인터락이 선언되고 ST에 상호 NOT 보호가 든다."""
    spec = build_spec("shutter_gate")
    assert spec.interlocks and {spec.interlocks[0].output_a, spec.interlocks[0].output_b} == {
        "MTR_OPEN", "MTR_CLOSE"
    }
    st = synthesize_st(spec)
    assert "NOT MTR_OPEN" in st and "NOT MTR_CLOSE" in st


def test_tower_lamp_derived_one_color() -> None:
    """타워램프: 적/녹/황이 파생식으로 상호배타(동시 1색)."""
    spec = build_spec("tower_lamp")
    exprs = {d.output: d.expression for d in spec.derived_outputs}
    assert exprs["LAMP_RED"] == "FAULT"
    assert exprs["LAMP_GREEN"] == "RUNNING AND NOT FAULT"
    assert exprs["LAMP_AMBER"] == "NOT RUNNING AND NOT FAULT"
    assert verify(spec, synthesize_st(spec)).passed


def test_retry_alarm_uses_counter() -> None:
    spec = build_spec("retry_alarm", {"retries": "5"})
    assert spec.counters and spec.counters[0].preset == 5


def test_runtime_maint_uses_counter() -> None:
    spec = build_spec("runtime_maint", {"hours": "250"})
    assert spec.counters and spec.counters[0].preset == 250


def test_conveyor_jam_uses_timer() -> None:
    spec = build_spec("conveyor_jam", {"jam_sec": "6"})
    assert spec.timers and spec.timers[0].preset_ms == 6000


def test_guard_interlock_off_condition_has_guard() -> None:
    """가드가 열리면 즉시 정지 — RUN 이탈 조건에 NOT guard 포함."""
    spec = build_spec("guard_interlock")
    leave = [t for t in spec.transitions if t.from_state == "RUN"][0]
    assert "GUARD_CLOSED" in leave.condition and "ESTOP_OK" in leave.condition


def test_new_recipes_reject_bad_symbol() -> None:
    with pytest.raises(WizardError):
        build_spec("three_wire", {"motor": "모터"})

