"""가이드 마법사 테스트 — 비전문가가 레시피+답변만으로 유효 설계 생성."""

from __future__ import annotations

import pytest

from app.memory_map import detect_double_coils
from app.synth import covers_all_outputs, synthesize_st
from app.verifier import verify
from app.wizard import RECIPES, build_spec, list_recipes


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
