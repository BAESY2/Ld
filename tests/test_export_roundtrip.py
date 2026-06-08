"""컴파일 산출물 export 라운드트립 — 상호운용 신뢰 (Phase N+).

컴파일러(``app.compile_frame.frame_to_spec``)가 만드는 새 구조가 PLCopen XML 과
벤더 IL 로 *깨지지 않고* 내보내지는지 단정한다. 세 가지 새 구조를 검증한다:

  1. 타임드 시퀀서: 타이머 FB 호출(``T0(IN:=.., PT:=..)``)·``.Q`` 참조가 보존되고
     XML/IL 이 well-formed·필수구조를 만족한다.
  2. 다중 인스턴스 출력: ``MOTOR1``/``MOTOR2`` 가 변수 선언·접점 양쪽에 보존된다.
  3. 아날로그 비교기: 비교 접점(``PRESSURE >= 5``)이 IL 에 표현되고, 비교기 플래그
     ``PRESSURE_GE5`` 가 PLCopen 인터페이스에 (내부 BOOL 로) 빠짐없이 선언된다.

회귀로 잡은 깨짐(이 라운드에서 수정):
  * 비교기 플래그가 PLCopen 인터페이스에 미선언 → IDE 임포트 "정의되지 않은 변수".
  * 비교 접점이 IL 에서 ``LOAD PRESSURE>=5`` 처럼 연산자가 피연산자에 붙어 깨짐.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

from app.compile_frame import frame_to_spec
from app.emit import emit
from app.export import to_plcopen_xml, validate_plcopen_xml
from app.models import IODirection, StateMachineSpec
from app.synth import synthesize_st
from app.transpiler import transpile_st
from app.vendors import LS_XGK, MITSUBISHI_FX, OMRON_CJ, SIEMENS_S7
from app.vendors.profiles import VendorProfile

_TC6 = "http://www.plcopen.org/xml/tc6_0201"
_XHTML = "http://www.w3.org/1999/xhtml"

_SEQ = "모터 돌리고 다음 펌프 켜고 다음 밸브 열어"
_MULTI = "1번 모터 돌리고 2번 모터 멈춰"
_CMP = "압력 5바 넘으면 펌프 꺼"

_PROFILES: list[VendorProfile] = [LS_XGK, MITSUBISHI_FX, OMRON_CJ, SIEMENS_S7]


def _q(tag: str) -> str:
    return f"{{{_TC6}}}{tag}"


def _compile_st(text: str) -> tuple[StateMachineSpec, str]:
    """컴파일 → 합성. 컴파일이 confident 해야(=신뢰 산출) 라운드트립 대상이다."""
    result = frame_to_spec(text)
    assert result.confident, f"{text!r} 컴파일 비확신: {result.unresolved}"
    st = synthesize_st(result.spec)
    assert st.strip(), "합성 ST 가 비어 있음"
    return result.spec, st


def _declared_vars(xml: str) -> set[str]:
    root = ET.fromstring(xml)
    return {v.get("name") or "" for v in root.iter(_q("variable"))}


def _body_st(xml: str) -> str:
    root = ET.fromstring(xml)
    p = root.find(f".//{{{_XHTML}}}p")
    assert p is not None and p.text is not None
    return p.text


# ---------------------------------------------------------------------------
# 공통: 세 산출물 모두 well-formed·검증 통과·결정론
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text", [_SEQ, _MULTI, _CMP])
def test_plcopen_wellformed_and_validated(text: str) -> None:
    spec, st = _compile_st(text)
    xml = to_plcopen_xml(spec, st)
    ET.fromstring(xml)  # well-formed
    validate_plcopen_xml(xml)  # 필수구조·dangling 없음


@pytest.mark.parametrize("text", [_SEQ, _MULTI, _CMP])
def test_plcopen_deterministic(text: str) -> None:
    spec, st = _compile_st(text)
    assert to_plcopen_xml(spec, st) == to_plcopen_xml(spec, st)


@pytest.mark.parametrize("text", [_SEQ, _MULTI, _CMP])
@pytest.mark.parametrize("profile", _PROFILES)
def test_emit_does_not_crash_and_nonempty(text: str, profile: VendorProfile) -> None:
    _spec, st = _compile_st(text)
    il = emit(transpile_st(st), profile)
    assert il.strip(), f"{profile.name} IL 이 비어 있음"


@pytest.mark.parametrize("text", [_SEQ, _MULTI, _CMP])
def test_no_undeclared_vars_in_plcopen(text: str) -> None:
    """ST 본문에서 쓰인 모든 심볼이 인터페이스에 선언돼야 한다(미선언=IDE 임포트 깨짐).

    제외: ``.Q``/``.ET`` 등 FB 멤버, FB 타입명(TON/CTU), TIME 리터럴 토큰(s/ms/T).
    """
    spec, st = _compile_st(text)
    xml = to_plcopen_xml(spec, st)
    declared = _declared_vars(xml)
    fb_types = {"TON", "TOF", "TP", "CTU", "CTD"}
    arg_kw = {"IN", "PT", "CU", "CD", "R", "PV", "Q", "ET"}
    time_tok = {"T", "s", "ms", "m", "h", "d"}
    bool_lit = {"AND", "OR", "NOT", "TRUE", "FALSE"}
    skip = fb_types | arg_kw | time_tok | bool_lit
    used: set[str] = set()
    for tok in re.findall(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", st):
        base = tok.split(".")[0]  # T0.Q → T0
        if base in skip:
            continue
        used.add(base)
    missing = used - declared
    assert not missing, f"{text!r}: 인터페이스 미선언 심볼 {missing} (선언: {sorted(declared)})"


# ---------------------------------------------------------------------------
# (1) 타임드 시퀀서: 타이머 FB 호출·.Q 참조 보존
# ---------------------------------------------------------------------------
def test_sequencer_timer_fb_preserved_in_plcopen() -> None:
    spec, st = _compile_st(_SEQ)
    assert spec.timers, "시퀀서인데 타이머가 없음"
    xml = to_plcopen_xml(spec, st)
    body = _body_st(xml)
    declared = _declared_vars(xml)
    for t in spec.timers:
        # FB 인스턴스가 변수로 선언되고, IN:=/PT:= 호출·.Q 참조가 본문에 보존.
        assert t.name in declared, f"타이머 {t.name} 미선언"
        assert re.search(rf"{t.name}\s*\(\s*IN\s*:=", body), f"{t.name} IN 호출 누락"
        assert "PT :=" in body or "PT:=" in body, "PT 프리셋 누락"
        assert f"{t.name}.Q" in body, f"{t.name}.Q 참조 누락"


def test_sequencer_timer_fb_preserved_in_il() -> None:
    _spec, st = _compile_st(_SEQ)
    il = emit(transpile_st(st), LS_XGK)
    # 타이머 FB·.Q 접점이 IL 에 표현된다.
    assert "TON T0" in il and "TON T1" in il and "TON T2" in il
    assert "T0.Q" in il, ".Q 접점이 IL 에서 누락"


# ---------------------------------------------------------------------------
# (2) 다중 인스턴스 출력: MOTOR1/MOTOR2 보존
# ---------------------------------------------------------------------------
def test_multi_instance_outputs_preserved() -> None:
    spec, st = _compile_st(_MULTI)
    outs = {p.symbol for p in spec.io_points if p.direction == IODirection.OUTPUT}
    assert {"MOTOR1", "MOTOR2"} <= outs, f"다중 인스턴스 출력 누락: {outs}"
    xml = to_plcopen_xml(spec, st)
    root = ET.fromstring(xml)
    out_names = {
        v.get("name")
        for v in root.findall(f".//{_q('outputVars')}/{_q('variable')}")
    }
    assert {"MOTOR1", "MOTOR2"} <= out_names, f"outputVars 누락: {out_names}"
    body = _body_st(xml)
    assert "MOTOR1" in body and "MOTOR2" in body


def test_multi_instance_distinct_contacts_in_il() -> None:
    _spec, st = _compile_st(_MULTI)
    il = emit(transpile_st(st), LS_XGK)
    # 두 인스턴스가 서로 다른 출력 코일로 보존(이중코일·충돌 없음).
    assert "OUT MOTOR1" in il
    assert "OUT MOTOR2" in il


# ---------------------------------------------------------------------------
# (3) 아날로그 비교기: 플래그 선언 + 비교 접점 표현
# ---------------------------------------------------------------------------
def test_comparator_flag_declared_in_plcopen() -> None:
    spec, st = _compile_st(_CMP)
    assert spec.comparators, "비교기가 없음"
    flag = spec.comparators[0].flag  # 예: PRESSURE_GE5
    xml = to_plcopen_xml(spec, st)
    validate_plcopen_xml(xml)
    declared = _declared_vars(xml)
    # 플래그가 (내부 BOOL 로) 선언돼야 한다 — 미선언이면 IDE 임포트가 깨졌었다.
    assert flag in declared, f"비교기 플래그 {flag} 가 인터페이스에 미선언"
    # 비교 임계와 신호가 본문에 표현된다(PRESSURE >= 5).
    body = _body_st(xml)
    assert "PRESSURE" in body and ">=" in body


def test_comparator_flag_is_bool_localvar() -> None:
    spec, st = _compile_st(_CMP)
    flag = spec.comparators[0].flag
    root = ET.fromstring(to_plcopen_xml(spec, st))
    local = root.find(f".//{_q('localVars')}")
    assert local is not None
    found = None
    for v in local.findall(_q("variable")):
        if v.get("name") == flag:
            tel = v.find(_q("type"))
            assert tel is not None
            found = list(tel)[0].tag.rsplit("}", 1)[-1]
    assert found == "BOOL", f"비교기 플래그 타입이 BOOL 이 아님: {found}"


@pytest.mark.parametrize("profile", _PROFILES)
def test_comparator_contact_not_glued_in_il(profile: VendorProfile) -> None:
    """비교 접점이 IL 에서 연산자-피연산자 붙음('PRESSURE>=5') 없이 표현돼야 한다."""
    _spec, st = _compile_st(_CMP)
    il = emit(transpile_st(st), profile)
    # 깨진 형태(연산자가 피연산자에 붙음)가 없어야 한다.
    assert "PRESSURE>=5" not in il, f"{profile.name}: 비교 접점이 깨진 채 붙어 있음"
    # 비교가 사람이 읽는 접점으로 표현(신호·연산자가 분리).
    assert re.search(r"PRESSURE\s*>=\s*5", il), f"{profile.name}: 비교 접점 표현 누락"
