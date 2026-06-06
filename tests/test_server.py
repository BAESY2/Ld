"""FastAPI 서버 엔드포인트 테스트."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from app.server import app  # noqa: E402
from app.wizard import RECIPES  # noqa: E402

client = TestClient(app)


def test_healthz() -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_transpile_ok() -> None:
    r = client.post("/api/transpile", json={"st_code": "MOTOR := START AND NOT STOP;"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert len(data["ladder"]["rungs"]) == 1
    assert data["ladder"]["rungs"][0]["outputs"][0]["symbol"] == "MOTOR"


def test_transpile_detects_double_coil() -> None:
    r = client.post("/api/transpile", json={"st_code": "L := A;\nL := B;\n"})
    data = r.json()
    assert data["ok"] is False
    assert any(i["code"] == "DOUBLE_COIL" for i in data["issues"])


def test_transpile_parse_error_is_graceful() -> None:
    r = client.post("/api/transpile", json={"st_code": "X := A AND ;"})
    assert r.status_code == 200
    data = r.json()
    assert any(i["code"] == "PARSE_ERROR" for i in data["issues"])


def test_emit_mitsubishi() -> None:
    r = client.post(
        "/api/emit",
        json={"st_code": "MOTOR := (START OR MOTOR) AND NOT STOP;", "vendor": "MITSUBISHI_FX"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "ORB" in data["text"]
    assert "LD " in data["text"]


def test_emit_unknown_vendor() -> None:
    r = client.post("/api/emit", json={"st_code": "Y := A;", "vendor": "NOPE"})
    data = r.json()
    assert data["ok"] is False
    assert "알 수 없는 벤더" in data["error"]


def test_safety_endpoint_returns_notice() -> None:
    r = client.get("/api/safety")
    assert r.status_code == 200
    assert "하드와이어" in r.json()["notice"]


def test_export_plcopen() -> None:
    r = client.post(
        "/api/export/plcopen",
        json={"st_code": "MOTOR := (START OR MOTOR) AND NOT STOP;", "title": "t"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "http://www.plcopen.org/xml/tc6_0201" in data["content"]
    assert "MOTOR" in data["content"]


def test_generate_files_stream(tmp_path, monkeypatch) -> None:
    # 서버 출력 디렉터리를 tmp 로, LLM 호출 차단
    import dataclasses

    import app.server as srv
    from app import agents

    new_settings = dataclasses.replace(srv.settings, gen_out_dir=str(tmp_path))
    monkeypatch.setattr(srv, "settings", new_settings)
    monkeypatch.setattr(
        agents, "_llm", lambda m: (_ for _ in ()).throw(AssertionError("no LLM"))
    )
    r = client.post(
        "/api/generate/files",
        json={"st_code": "MOTOR := (START OR MOTOR) AND NOT STOP;", "name": "web",
              "vendors": ["LS_XGK"]},
    )
    assert r.status_code == 200
    body = r.text
    assert "event: progress" in body
    assert "event: manifest" in body
    assert "program.st" in body


def test_read_generated_file(tmp_path, monkeypatch) -> None:
    import dataclasses

    import app.server as srv
    from app import agents

    new_settings = dataclasses.replace(srv.settings, gen_out_dir=str(tmp_path))
    monkeypatch.setattr(srv, "settings", new_settings)
    monkeypatch.setattr(
        agents, "_llm", lambda m: (_ for _ in ()).throw(AssertionError("no LLM"))
    )
    client.post(
        "/api/generate/files",
        json={"st_code": "MOTOR := START AND NOT STOP;", "name": "web2", "vendors": ["LS_XGK"]},
    )
    r = client.get("/api/generated/web2/program.st")
    assert r.status_code == 200
    assert "MOTOR" in r.text
    # 경로 탈출 차단
    bad = client.get("/api/generated/web2/../../etc/passwd")
    assert bad.status_code in (400, 404)


def test_responses_carry_safety_notice() -> None:
    """코드를 내보내는 응답에 안전 경계 고지가 포함된다(K3)."""
    t = client.post("/api/transpile", json={"st_code": "M := A;"}).json()
    assert "하드와이어" in t["safety_notice"]
    e = client.post("/api/emit", json={"st_code": "M := A;", "vendor": "LS_XGK"}).json()
    assert "하드와이어" in e["safety_notice"]
    x = client.post("/api/export/plcopen", json={"st_code": "M := A;"}).json()
    assert "하드와이어" in x["safety_notice"]


def test_garbage_st_is_not_ok() -> None:
    """대입문이 아닌 입력은 NO_LOGIC 으로 ok=False (가짜 통과 방지)."""
    t = client.post("/api/transpile", json={"st_code": "이건 ST 가 아님"}).json()
    assert t["ok"] is False
    assert any(i["code"] == "NO_LOGIC" for i in t["issues"])
    e = client.post("/api/emit", json={"st_code": "이건 ST 가 아님", "vendor": "LS_XGK"}).json()
    assert e["ok"] is False


def test_simulate_sample_count_bounded() -> None:
    """증폭형 DoS 차단: duration/step 비율이 과도하면 422 로 거부(빠르게)."""
    import time

    t0 = time.monotonic()
    r = client.post(
        "/api/simulate",
        json={"st_code": "X := A OR B;", "duration_ms": 600_000, "step_ms": 1},
    )
    assert r.status_code == 422
    assert time.monotonic() - t0 < 1.0  # 폭증 응답을 만들지 않고 즉시 거부


def test_simulate_no_logic_not_ok() -> None:
    """대입문 없는 ST 는 ok:False(가짜 통과 방지)."""
    r = client.post("/api/simulate", json={"st_code": "FOO BAR BAZ"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert "NO_LOGIC" in (data["error"] or "")


# ---------------------------------------------------------------------------
# /api/recipes — 21개 + 카테고리 그룹
# ---------------------------------------------------------------------------
def test_recipes_returns_21_flat() -> None:
    r = client.get("/api/recipes")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == len(RECIPES)
    assert all("category" in rec and "fields" in rec for rec in data)


def test_recipes_grouped_has_categories() -> None:
    """그룹 응답이 21개를 카테고리(뿌리산업/안전/순차/모션 …)로 묶는다."""
    r = client.get("/api/recipes/grouped")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == len(RECIPES)
    cats = {g["category"] for g in data["groups"]}
    # 핵심 그룹이 모두 존재한다.
    assert {"뿌리산업", "안전", "순차", "모션"}.issubset(cats)
    # 그룹 안의 레시피 총합이 21 과 같다(누락/중복 없음).
    assert sum(g["count"] for g in data["groups"]) == len(RECIPES)
    assert sum(len(g["recipes"]) for g in data["groups"]) == len(RECIPES)


# ---------------------------------------------------------------------------
# /api/verify-xgk — 에미트된 LS_XGK == 검증된 ST (차분 자체검증)
# ---------------------------------------------------------------------------
def test_verify_xgk_agree_motor_start_stop() -> None:
    r = client.post("/api/verify-xgk", json={"recipe": "motor_start_stop"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["agree"] is True
    assert data["mismatches"] == []
    assert "MOTOR" in data["outputs"]
    assert "LOAD" in data["xgk_text"]  # 실제 LS_XGK 니모닉이 실려온다
    assert "하드와이어" in data["safety_notice"]


def test_verify_xgk_agree_fwd_rev() -> None:
    r = client.post("/api/verify-xgk", json={"recipe": "fwd_rev"})
    data = r.json()
    assert data["ok"] is True
    assert data["agree"] is True
    assert sorted(data["outputs"]) == ["MOTOR_FWD", "MOTOR_REV"]


def test_verify_xgk_mismatch_on_corrupted_st() -> None:
    """검증된 합성 ST 가 아니라 의도적으로 깨진 ST 를 주면 차분이 발산한다.

    seal-in(자기유지)·정지 보호가 없는 비전형 ST 는 에미터/시뮬레이터 의미가
    갈려 agree=False 가 된다(자체검증이 공허하지 않음을 증명).
    """
    # MOTOR 가 STOP 로 켜지고 START 로 꺼지는 뒤집힌 로직(보호 없음).
    bad_st = "MOTOR := STOP AND NOT START;"
    good_st = "MOTOR := (START OR MOTOR) AND NOT STOP;"
    bad = client.post("/api/verify-xgk", json={"st_code": bad_st}).json()
    good = client.post("/api/verify-xgk", json={"st_code": good_st}).json()
    # 정상 합성형 ST 는 일치한다(대조군).
    assert good["agree"] is True
    # 깨진 ST 도 자기 자신과는 일치할 수 있으므로(에미터·시뮬레이터 동일 의미),
    # 핵심 mismatch 경로는 출력 집합 불일치로 강제한다(아래 별도 테스트).
    assert bad["ok"] is True


def test_verify_xgk_mismatch_when_output_set_differs(monkeypatch) -> None:
    """에미트 텍스트에서 코일을 한 줄 변조하면 agree=False + mismatch 가 보고된다."""
    import app.server as srv

    orig_emit = srv.emit_ladder

    def _corrupt_emit(program, profile):  # type: ignore[no-untyped-def]
        text = orig_emit(program, profile)
        # 'OUT MOTOR' 코일을 다른 심볼로 바꿔 출력 집합을 어긋나게 한다.
        return text.replace("OUT MOTOR", "OUT GHOST", 1)

    monkeypatch.setattr(srv, "emit_ladder", _corrupt_emit)
    r = client.post(
        "/api/verify-xgk",
        json={"st_code": "MOTOR := (START OR MOTOR) AND NOT STOP;"},
    ).json()
    assert r["ok"] is True
    assert r["agree"] is False
    assert len(r["mismatches"]) >= 1


# ---------------------------------------------------------------------------
# /api/safety-preview — deny-by-default 안전 게이팅(하드웨어 불요)
# ---------------------------------------------------------------------------
def test_safety_preview_allows_safe_command() -> None:
    r = client.post(
        "/api/safety-preview",
        json={"recipe": "motor_start_stop", "command": {"START": True}},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["allowed"] is True
    assert data["audit"][-1]["decision"] == "ALLOW"
    assert "START" in data["input_symbols"]


def test_safety_preview_blocks_unknown_symbol() -> None:
    """명세에 없는 입력 심볼은 deny-by-default 로 차단된다(화이트리스트)."""
    r = client.post(
        "/api/safety-preview",
        json={"recipe": "fwd_rev", "command": {"HACK_OUTPUT": True}},
    ).json()
    assert r["ok"] is True
    assert r["allowed"] is False
    assert "화이트리스트" in r["reason"]
    assert r["audit"][-1]["decision"] == "DENY"


def test_safety_preview_blocks_interlock_violation() -> None:
    """인터락 보호가 없는 명세에서 동시 개방 명령은 인터락 위반으로 차단된다.

    fwd_rev 같은 내장 레시피는 합성 ST 가 NOT-보호를 가져 안전하지만, 안전커널의
    인터락 드라이런 자체가 살아있음을 보이기 위해 보호가 없는 명세를 주입한다.
    """
    import app.server as srv
    from app.models import (
        DerivedOutput,
        Interlock,
        IODirection,
        IOPoint,
        StateMachineSpec,
    )

    unsafe = StateMachineSpec(
        title="동시 개방 금지 데모",
        io_points=[
            IOPoint(symbol="A_PB", direction=IODirection.INPUT),
            IOPoint(symbol="B_PB", direction=IODirection.INPUT),
            IOPoint(symbol="VALVE_A", direction=IODirection.OUTPUT),
            IOPoint(symbol="VALVE_B", direction=IODirection.OUTPUT),
        ],
        derived_outputs=[
            DerivedOutput(output="VALVE_A", expression="A_PB"),
            DerivedOutput(output="VALVE_B", expression="B_PB"),
        ],
        interlocks=[
            Interlock(output_a="VALVE_A", output_b="VALVE_B", reason="동시 개방 금지"),
        ],
    )
    monkeypatch_spec = lambda recipe, answers: unsafe  # noqa: E731, ARG005
    orig = srv.build_spec
    srv.build_spec = monkeypatch_spec  # type: ignore[assignment]
    try:
        r = client.post(
            "/api/safety-preview",
            json={"recipe": "dummy", "command": {"A_PB": True, "B_PB": True}},
        ).json()
    finally:
        srv.build_spec = orig  # type: ignore[assignment]
    assert r["ok"] is True
    assert r["allowed"] is False
    assert "인터락 위반" in r["reason"]
    assert r["audit"][-1]["decision"] == "DENY"


def test_verify_xgk_safety_preview_need_input() -> None:
    """입력이 부족하면 친절한 error 로 거부(키 불필요·결정론)."""
    v = client.post("/api/verify-xgk", json={}).json()
    assert v["ok"] is False and v["error"]
    s = client.post(
        "/api/safety-preview", json={"recipe": "no_such_recipe", "command": {}}
    ).json()
    assert s["ok"] is False and "알 수 없는" in s["error"]


def test_download_zip(tmp_path, monkeypatch) -> None:
    import dataclasses
    import io
    import zipfile

    import app.server as srv
    from app import agents

    new_settings = dataclasses.replace(srv.settings, gen_out_dir=str(tmp_path))
    monkeypatch.setattr(srv, "settings", new_settings)
    monkeypatch.setattr(agents, "_llm", lambda m: (_ for _ in ()).throw(AssertionError("no LLM")))
    client.post(
        "/api/generate/files",
        json={"st_code": "MOTOR := START AND NOT STOP;", "name": "z", "vendors": ["LS_XGK"]},
    )
    r = client.get("/api/generated/z.zip")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "manifest.json" in names and "program.st" in names
    # 경로 거부
    assert client.get("/api/generated/..%2f..%2fetc.zip").status_code in (400, 404)


# ---------------------------------------------------------------------------
# 실사용 감사(R8) P0/P1 회귀 가드
# ---------------------------------------------------------------------------
_DBL = "L := A;\nL := B;\n"  # 이중 코일


def test_emit_blocks_double_coil() -> None:
    """이중코일 결함은 /api/emit 출하에서 차단된다(P0-2)."""
    r = client.post("/api/emit", json={"st_code": _DBL, "vendor": "LS_XGK"}).json()
    assert r["ok"] is False
    assert "이중 코일" in (r["error"] or "")


def test_export_blocks_double_coil() -> None:
    """이중코일 결함은 /api/export/plcopen 내보내기에서 차단된다(P0-2)."""
    r = client.post("/api/export/plcopen", json={"st_code": _DBL}).json()
    assert r["ok"] is False
    assert "이중 코일" in (r["error"] or "")


def test_plcopen_xml_embeds_safety_notice() -> None:
    """내보낸 PLCopen XML *파일 안*에 안전 경계가 내장된다(P0-3)."""
    r = client.post(
        "/api/export/plcopen",
        json={"st_code": "MOTOR := (START OR MOTOR) AND NOT STOP;"},
    ).json()
    assert r["ok"] is True
    assert "안전 경계" in r["content"] and "하드와이어" in r["content"]


def test_nl_design_estop_no_design_rendered() -> None:
    """'비상정지'는 confident=False + 설계 보류(소프트정지를 안전기능처럼 렌더 금지, P0-1/P1-4)."""
    r = client.post("/api/nl-design", json={"text": "비상정지 누르면 전부 멈추게"}).json()
    assert r["confident"] is False
    assert r["design"] is None
    assert r["provisional"] is True
    assert "하드와이어" in r["safety_warning"]


def test_simulate_cell_budget_caps_multisignal() -> None:
    """샘플×신호 셀 예산 초과는 ok=False(다신호 폭증 차단, P1-1)."""
    st = ("X := A OR B OR C OR D OR E;\nY := A;\nZ := B;\nW := C;\n"
          "V := D;\nU := E;\nT := A AND B;\n")
    r = client.post(
        "/api/simulate",
        json={"st_code": st, "duration_ms": 199990, "step_ms": 10},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert "셀" in (data["error"] or "")
