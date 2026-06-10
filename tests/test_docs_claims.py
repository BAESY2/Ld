"""백서·매뉴얼의 회로 카탈로그가 *실제로* 컴파일·검증되는지 단정(문서 거짓말 방지).

매뉴얼 §3 표준회로 카탈로그의 각 한국어 예문이 confident 컴파일 + verify 통과해야
한다. 문서가 자랑하는 모든 줄은 테스트로 뒷받침된다 — '데모 주장 금지' 원칙.
"""

from __future__ import annotations

import pytest

from app.compile_frame import frame_to_spec
from app.memory_map import detect_double_coils
from app.synth import synthesize_st
from app.verifier import verify

# (매뉴얼 §3 / 백서 §5 의 예문, 기대 출력 일부)
CATALOG = [
    ("버튼 누르면 모터 돌고 정지 누르면 멈춰", {"MOTOR"}),
    ("버튼 누르면 모터 돌고 비상정지 누르면 다 꺼", {"MOTOR"}),
    ("저수위 되면 펌프 켜고 고수위 되면 펌프 꺼", {"PUMP"}),
    ("5.5킬로와트 모터 스타델타로 기동해", {"MOTOR", "MOTOR_Y", "MOTOR_D"}),
    ("정회전 돌리고 역회전 돌리고 동시에 안 되게", {"MOTOR_FWD", "MOTOR_REV"}),
    ("펌프 두 대 교대로 운전해", {"PUMP1", "PUMP2"}),
    ("모터 돌리고 다음 펌프 켜고 다음 밸브 열어", {"MOTOR", "PUMP", "VALVE"}),
    ("부품 10개 차면 배출", {"EJECT"}),
    ("히터 켜고 쿨러 켜는데 동시에 안 켜지게", {"HEATER", "COOLER"}),
    ("컨베이어 돌리고 다음 충전기 켜고 다음 캡핑기 켜고 다음 배출해",
     {"CONVEYOR", "FILLER", "CAPPER", "EJECT"}),
]


@pytest.mark.parametrize("text,expected", CATALOG)
def test_manual_catalog_compiles_and_verifies(text: str, expected: set[str]) -> None:
    r = frame_to_spec(text)
    assert r.confident, f"매뉴얼 카탈로그 항목이 보류됨: {text}"
    st = synthesize_st(r.spec)
    outs = {p.symbol for p in r.spec.io_points if p.direction.value == "OUTPUT"}
    assert expected <= outs, f"{text}: 기대 출력 {expected} ⊄ {outs}"
    assert detect_double_coils(st) == {}
    assert verify(r.spec, st).passed


def test_whitepaper_proven_safety_claims() -> None:
    """백서 §5 가 주장하는 동시투입 금지 증명이 실제로 성립한다."""
    from app.verifier import proven_safe_pairs

    claims = [
        ("5.5킬로와트 모터 스타델타로 기동해", ("MOTOR_D", "MOTOR_Y")),
        ("정회전 돌리고 역회전 돌리고 동시에 안 되게", ("MOTOR_FWD", "MOTOR_REV")),
        ("펌프 두 대 교대로 운전해", ("PUMP1", "PUMP2")),
    ]
    for text, pair in claims:
        r = frame_to_spec(text)
        st = synthesize_st(r.spec)
        proven = {tuple(sorted(p)) for p in proven_safe_pairs(r.spec, st)}
        assert tuple(sorted(pair)) in proven, f"{text}: {pair} 증명 실패"


def test_docs_exist() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    for doc in ("WHITEPAPER.md", "MANUAL.md", "ERRORCODES.md"):
        p = root / "docs" / doc
        assert p.exists() and len(p.read_text(encoding="utf-8")) > 1000, doc
