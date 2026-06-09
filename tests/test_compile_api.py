"""/api/compile 엔드포인트 테스트 — 컴파일러를 제품의 기본 합성 경로로 노출.

핵심 주장: 한국어 복합문을 레시피 매칭이 아니라 *컴파일러*가 검증된 래더로 합성하고,
도메인 밖 문장은 confident=False 로 정직히 강등해 래더 생성을 보류한다(거짓 생성 금지).
모두 결정론(LLM/키 불필요).
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from app.server import app  # noqa: E402

client = TestClient(app)


def test_compile_compound_korean_is_confident_and_verified() -> None:
    """저수위 펌프 + 고수위 정지 + 고장 경광등 — 레시피 없는 복합문이 컴파일·검증된다."""
    r = client.post(
        "/api/compile",
        json={"text": "저수위 되면 펌프 켜고 고수위 되면 펌프 끄고 고장 나면 경광등 켜"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["confident"] is True
    # 이해 내용(understood)에 펌프·경광등 등 핵심 의도가 설명가능하게 담긴다.
    assert "펌프" in data["understood"]
    assert "경광등" in data["understood"]
    assert data["verification"] is not None
    assert data["verification"]["passed"] is True
    assert data["double_coil_free"] is True
    assert data["unresolved"] == []
    # 컴파일된 ST/래더가 실제로 만들어졌다(보류 아님).
    assert "PUMP" in data["structured_text"]
    assert data["ladder"] is not None
    assert len(data["ladder"]["rungs"]) >= 1
    assert "하드와이어" in data["safety_notice"]


def test_compile_out_of_domain_holds_ladder() -> None:
    """도메인 밖 문장 → confident=False, 래더 보류(거짓 생성 금지)."""
    r = client.post("/api/compile", json={"text": "오늘 점심 뭐 먹지"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True            # 요청 처리 자체는 성공
    assert data["confident"] is False    # 정직 강등
    assert data["ladder"] is None        # 래더 생성 보류
    assert data["structured_text"] == ""


def test_compile_single_intent_compiles() -> None:
    r = client.post(
        "/api/compile", json={"text": "압력 5바 넘으면 밸브 닫고 온도 200도 되면 히터 꺼"}
    )
    data = r.json()
    assert data["confident"] is True
    assert data["verification"]["passed"] is True
    assert data["double_coil_free"] is True


def test_compile_is_deterministic() -> None:
    body = {"text": "저수위 되면 펌프 켜고 고수위 되면 펌프 끄고 고장 나면 경광등 켜"}
    a = client.post("/api/compile", json=body).json()
    b = client.post("/api/compile", json=body).json()
    assert a["structured_text"] == b["structured_text"]
    assert a["confident"] == b["confident"]
    assert a["understood"] == b["understood"]


def test_compile_rejects_empty() -> None:
    r = client.post("/api/compile", json={"text": ""})
    assert r.status_code == 422  # min_length=1 검증


def test_compile_exposes_proven_interlocks() -> None:
    """상호배제 단서가 있는 문장은 *증명된 동시금지* 묶음을 응답에 노출한다(해자 가시화)."""
    r = client.post(
        "/api/compile", json={"text": "히터 켜고 쿨러 켜는데 동시에 안 켜지게"}
    )
    data = r.json()
    assert data["confident"] is True
    proven = {tuple(p) for p in data["proven_interlocks"]}
    assert ("COOLER", "HEATER") in proven  # k-귀납으로 증명된 쌍이 그대로 실린다


def test_compile_no_mutex_no_proven_interlocks() -> None:
    """상호배제 단서가 없으면 증명 묶음은 비어 있다(거짓 증거 금지)."""
    r = client.post(
        "/api/compile", json={"text": "저수위 되면 펌프 켜고 고수위 되면 펌프 꺼"}
    )
    data = r.json()
    assert data["confident"] is True
    assert data["proven_interlocks"] == []
