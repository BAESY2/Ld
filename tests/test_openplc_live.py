"""실 OpenPLC 런타임 대 우리 시뮬레이터 차분 검증 — 통합 테스트(env 가드).

CI 는 하드웨어/도커가 없으므로 ``OPENPLC_HOST`` 가 설정되지 않으면 **깨끗이 스킵**
한다(키 없이 통과 규칙). ``OPENPLC_HOST`` 가 있으면 실 OpenPLC v3 런타임에 우리
합성 프로그램을 적재→구동하고, ``run_differential`` 로 비트 단위 일치를 단언한다.

재현(로컬 도커):
  docker run -d --name openplc -p 8080:8080 -p 5502:502 dainok/openplc:latest
  OPENPLC_HOST=127.0.0.1 OPENPLC_PORT=5502 pytest -q tests/test_openplc_live.py

순수 단위(스킵 없이 항상 도는) 테스트로 ST 래핑·코일맵·주소변환의 결정론도 함께
검증한다(도커 불필요).
"""

from __future__ import annotations

import os

import pytest

from app.synth import synthesize_st
from app.wizard import build_spec
from scripts.openplc_live_diff import (
    build_coil_map,
    default_timeline,
    run,
    wrap_st_for_openplc,
)

_LIVE = os.environ.get("OPENPLC_HOST")
_requires_openplc = pytest.mark.skipif(
    not _LIVE, reason="OPENPLC_HOST 미설정 — 실 OpenPLC 없는 CI 에서는 스킵"
)


# ── 도커 불필요 단위 테스트(항상 실행) ───────────────────────────────────────


def test_coil_map_outputs_then_inputs_no_overlap() -> None:
    """출력은 코일 0.., 입력은 출력 다음 바이트부터 — 충돌 없음(이중 의미 방지)."""
    spec = build_spec("fwd_rev")
    coils = build_coil_map(spec)
    assert set(coils.outputs.values()) == {0, 1}
    # 입력은 다음 바이트(코일 8..)부터.
    assert min(coils.inputs.values()) >= 8
    assert set(coils.outputs.values()).isdisjoint(set(coils.inputs.values()))


def test_wrap_st_declares_located_coils_and_fb() -> None:
    """래핑 ST 가 %QX 로케이티드 선언 + (타이머 시) FB 인스턴스를 별도 VAR 로 낸다."""
    spec = build_spec("on_delay", {"output": "LAMP"})
    body = synthesize_st(spec)
    coils = build_coil_map(spec)
    st = wrap_st_for_openplc(spec, body, coils)
    assert "LAMP AT %QX0.0 : BOOL;" in st
    assert "AT %QX1.0 : BOOL;" in st  # 입력 코일
    assert "T1 : TON;" in st
    # 로케이티드와 FB 는 *별도* VAR 블록(MatIEC 파싱 요건).
    assert st.count("VAR\n") >= 2
    # 비표준 RESET 은 OpenPLC 사본에서 표준 R 로 번역(카운터 레시피).
    cspec = build_spec("count_eject", {"count": "3"})
    cst = wrap_st_for_openplc(cspec, synthesize_st(cspec), build_coil_map(cspec))
    assert "RESET :=" not in cst
    assert "R :=" in cst


def test_timing_recipe_uses_scan_period_step() -> None:
    """타이머/카운터 레시피는 OpenPLC 스캔주기(50ms)에 맞춰 표본화해야 한다.

    (양자화 스큐를 없애 비트 단위 일치를 얻는 핵심 — docs/OPENPLC_LIVE.md 참조.)
    """
    spec = build_spec("on_delay", {"output": "LAMP"})
    _, _, step = default_timeline(spec)
    assert step == 50
    combo = build_spec("motor_start_stop")
    _, _, cstep = default_timeline(combo)
    assert cstep == 100  # 조합/래치는 빠른 표본화로 충분


# ── 실 OpenPLC 차분(OPENPLC_HOST 있을 때만) ──────────────────────────────────


@_requires_openplc
@pytest.mark.parametrize("recipe", ["motor_start_stop", "fwd_rev"])
def test_live_combinational_agrees(recipe: str) -> None:
    """실 OpenPLC 와 우리 시뮬레이터가 조합/래치 레시피에서 비트 단위로 일치."""
    assert run(recipe) == 0, f"{recipe}: OpenPLC 와 시뮬레이터가 갈라짐"


@_requires_openplc
def test_live_timer_agrees(monkeypatch: pytest.MonkeyPatch) -> None:
    """실 OpenPLC 와 우리 시뮬레이터가 타이머(TON) 레시피에서 비트 단위로 일치.

    on_delay 의 기본 출력명 OUTPUT 은 IEC 예약어라 LAMP 로 덮어쓴다.
    """
    monkeypatch.setenv("OPENPLC_ANSWERS", "output=LAMP")
    assert run("on_delay") == 0


@_requires_openplc
def test_live_counter_agrees(monkeypatch: pytest.MonkeyPatch) -> None:
    """실 OpenPLC 와 우리 시뮬레이터가 카운터(CTU) 레시피에서 비트 단위로 일치."""
    monkeypatch.setenv("OPENPLC_ANSWERS", "count=3")
    assert run("count_eject") == 0
