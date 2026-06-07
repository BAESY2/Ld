"""프로젝트 합성/자연어-모듈추가 API 테스트 (TestClient, 키 불필요·결정론).

스튜디오(대규모 설계) 워크스페이스의 백엔드 계약을 고정한다.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.server import app

client = TestClient(app)


def test_nl_add_korean_motor_phrase() -> None:
    r = client.post(
        "/api/project/nl-add",
        json={"text": "버튼 누르면 모터 돌고 정지 누르면 선다", "existing_names": []},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] and j["recipe"] == "motor_start_stop"
    assert j["confident"] is True
    assert j["suggested_name"] == "motor1"  # 앞토막+번호


def test_nl_add_suggests_unique_name() -> None:
    r = client.post(
        "/api/project/nl-add",
        json={"text": "모터 기동 정지", "existing_names": ["motor1", "motor2"]},
    )
    assert r.json()["suggested_name"] == "motor3"


def test_nl_add_safety_term_is_flagged_and_not_confident() -> None:
    r = client.post(
        "/api/project/nl-add",
        json={"text": "비상정지 누르면 모두 정지", "existing_names": []},
    )
    j = r.json()
    assert j["safety_warning"]  # 비상정지 → 경고
    assert j["confident"] is False  # 안전필수어는 자동 확신 금지


def test_compose_two_modules_distinct_addresses() -> None:
    body = {
        "title": "라인",
        "modules": [
            {"name": "conv1", "recipe": "motor_start_stop"},
            {"name": "conv2", "recipe": "motor_start_stop"},
        ],
    }
    j = client.post("/api/project/compose", json=body).json()
    assert j["ok"] is True
    assert len(j["ladder"]["rungs"]) == 2
    addrs = [e["address"] for e in j["address_map"]]
    assert len(addrs) == len(set(addrs))  # 전역 주소 충돌 0
    names = {m["name"] for m in j["modules"]}
    assert names == {"conv1", "conv2"}


def test_compose_surfaces_per_module_safety_note() -> None:
    # 다중 서브시스템을 개별 합성해도 각 모듈(레시피)의 안전 주의가 사라지면 안 된다.
    body = {
        "modules": [
            {"name": "m1", "recipe": "motor_start_stop"},
            {"name": "guard", "recipe": "guard_interlock"},
        ],
    }
    j = client.post("/api/project/compose", json=body).json()
    assert j["ok"] is True
    notes = {m["name"]: m["safety_note"] for m in j["modules"]}
    assert "비상정지" in notes["m1"]
    assert "⛔" in notes["guard"]  # 안전 강경고가 모듈 단위로 노출


def test_compose_cross_interlock_enforced_and_passes() -> None:
    # 교차 인터락을 선언하면 합성식이 상대를 가드하고 검증을 통과해야 한다(거짓양성 없음).
    body = {
        "modules": [
            {"name": "p1", "recipe": "motor_start_stop"},
            {"name": "p2", "recipe": "motor_start_stop"},
        ],
        "cross_interlocks": [
            {"output_a": "p1__MOTOR", "output_b": "p2__MOTOR", "reason": "동시 금지"}
        ],
    }
    j = client.post("/api/project/compose", json=body).json()
    assert j["ok"] is True, j.get("verification")
    assert "AND NOT p2__MOTOR" in j["structured_text"]
    assert not any(
        i["code"] == "INTERLOCK" and i["severity"] == "error"
        for i in j["verification"]["issues"]
    )


def test_compose_accepts_inline_spec_module() -> None:
    # studio 가 /api/design 결과(인라인 명세 모듈)를 채택해 재합성하는 경로.
    spec = {
        "title": "모터",
        "io_points": [
            {"symbol": "START", "direction": "INPUT"},
            {"symbol": "STOP", "direction": "INPUT"},
            {"symbol": "MOTOR", "direction": "OUTPUT"},
        ],
        "states": [
            {"name": "IDLE", "is_initial": True},
            {"name": "RUN", "on_entry": ["MOTOR := TRUE;"]},
        ],
        "transitions": [
            {"from_state": "IDLE", "to_state": "RUN", "condition": "START AND NOT STOP"},
            {"from_state": "RUN", "to_state": "IDLE", "condition": "STOP"},
        ],
    }
    body = {"modules": [{"name": "m1", "spec": spec}]}
    j = client.post("/api/project/compose", json=body).json()
    assert j["ok"] is True
    assert any("m1__MOTOR" in e["symbol"] for e in j["address_map"])
    assert len(j["ladder"]["rungs"]) >= 1


def test_compose_empty_is_error() -> None:
    j = client.post("/api/project/compose", json={"modules": []}).json()
    assert j["ok"] is False and j["error"]


def test_compose_then_simulate_roundtrip() -> None:
    # 스튜디오 라이브 시뮬 경로: compose 의 ST 를 그대로 /api/simulate 에 넣어 가동.
    body = {"modules": [{"name": "m1", "recipe": "motor_start_stop"}]}
    comp = client.post("/api/project/compose", json=body).json()
    st = comp["structured_text"]
    sim = client.post(
        "/api/simulate",
        json={
            "st_code": st,
            "inputs_timeline": [[0, {"m1__START": True}], [300, {"m1__START": False}]],
            "duration_ms": 1000,
            "step_ms": 100,
        },
    ).json()
    assert sim["ok"] is True
    # seal-in: START 를 떼도 MOTOR 는 유지(자기유지)된다.
    assert "m1__MOTOR" in sim["outputs"]
    last = sim["samples"][-1]["outputs"]
    assert last["m1__MOTOR"] is True
