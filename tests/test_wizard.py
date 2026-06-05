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
    # nl-design autobuild 도 design 안에 safety_note 를 담는다
    nd = c.post("/api/nl-design", json={"text": "양손으로 눌러야 프레스"}).json()
    assert nd["design"]["safety_note"]
