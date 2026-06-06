"""RAG → architect 파이프라인 통합 회귀 테스트 (Phase G 배선).

목적
----
``run_architect`` 의 LLM 폴백 경로가 활성 벤더 프로파일에 맞는 명령어 규격을
RAG(``data/instructions.jsonl``)에서 검색해 시스템 프롬프트에 실제로 주입하는지
검증한다. (연구: Agents4PLC/LLM4PLC — RAG 주입이 ST 컴파일 정확도를 크게 높임.)

원칙(과제 제약 준수)
  * LLM 호출 없음 — ``agents._llm`` 을 monkeypatch 한 가짜 모델이 프롬프트를
    기록만 한다. API 키 불필요·결정론적.
  * USE_RAG=true 로 실제 corpus 를 사용하되, 검색은 BM25-lite(키 불필요).
  * 벤더 필터가 주입 컨텍스트를 바꾼다는 것을 LS vs 미쓰비시로 직접 대조한다.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace
from typing import Any

import pytest

import app.rag as rag_module
from app import agents
from app.memory_map import detect_double_coils
from app.models import StateMachineSpec
from app.vendors.profiles import LS_XGK, MITSUBISHI_FX

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _set_use_rag(monkeypatch: pytest.MonkeyPatch, value: bool) -> None:
    """frozen Settings 를 복제·교체해 use_rag 를 켜고 corpus 캐시를 무효화한다.

    (test_rag_vendor.py 와 동일 패턴.)
    """
    import app.config as config_module
    from app.config import Settings

    original = config_module.settings
    new_settings = Settings.__new__(Settings)
    for f in dataclasses.fields(original):
        object.__setattr__(new_settings, f.name, getattr(original, f.name))
    object.__setattr__(new_settings, "use_rag", value)

    monkeypatch.setattr(config_module, "settings", new_settings)
    monkeypatch.setattr(rag_module, "settings", new_settings)
    monkeypatch.setattr(rag_module, "_corpus_cache", None)


class _RecordingLLM:
    """architect 폴백용 가짜 모델 — 받은 메시지를 기록하고 고정 ST 를 돌려준다.

    동일 인스턴스를 ``_llm`` 팩토리가 매번 반환하도록 클로저로 공유한다.
    """

    def __init__(self, content: str) -> None:
        self._content = content
        self.captured: list[Any] = []

    def invoke(self, messages: Any) -> Any:
        self.captured.append(messages)
        return SimpleNamespace(content=self._content)

    @property
    def system_prompt(self) -> str:
        """마지막 호출의 system 메시지 본문."""
        assert self.captured, "_llm 이 호출되지 않았다"
        messages = self.captured[-1]
        # messages = [("system", <body>), ("human", <body>)]
        role, body = messages[0]
        assert role == "system"
        return str(body)


# ---------------------------------------------------------------------------
# 1. RAG 컨텍스트가 프롬프트에 실제로 주입된다
# ---------------------------------------------------------------------------


def test_architect_injects_rag_context_into_prompt(
    monkeypatch: pytest.MonkeyPatch, conveyor_spec_safe: StateMachineSpec
) -> None:
    """LLM 폴백 시 시스템 프롬프트에 RAG 에서 검색한 벤더 명령어 텍스트가 들어간다."""
    _set_use_rag(monkeypatch, True)
    fake = _RecordingLLM(content="MOTOR_FWD := FWD_PB;\n")
    monkeypatch.setattr(agents, "_llm", lambda model: fake)

    # use_synth=False 로 LLM 폴백 경로 강제 (기본 프로파일 = LS_XGK)
    st_code, _ = agents.run_architect(conveyor_spec_safe, use_synth=False)

    prompt = fake.system_prompt
    # 폴백 문자열이 아니라 실제 corpus(LS) 청크가 주입돼야 한다.
    assert "LS" in prompt, f"LS 벤더 청크가 프롬프트에 없음: {prompt}"
    # 명세에 인터락이 있으므로 정역/인터락/자기유지 idiom 이 표면화돼야 한다.
    assert any(tok in prompt for tok in ("인터락", "정역", "자기유지")), (
        f"인터락/정역 청크가 표면화되지 않음: {prompt}"
    )
    # 후처리(merge_double_coils)는 그대로 유지된다(이중코일 0).
    assert detect_double_coils(st_code) == {}


def test_architect_query_surfaces_vendor_timer_chunk(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """타이머가 있는 명세 → LS 타이머 청크(TON/타이머)가 프롬프트에 표면화."""
    from app.models import TimerSpec

    _set_use_rag(monkeypatch, True)
    spec = StateMachineSpec(
        title="지연 기동",
        timers=[TimerSpec(name="T1", preset_ms=3000, enable_condition="START")],
    )
    fake = _RecordingLLM(content="LAMP := T1.Q;\n")
    monkeypatch.setattr(agents, "_llm", lambda model: fake)

    agents.run_architect(spec, use_synth=False, profile=LS_XGK)

    prompt = fake.system_prompt
    assert "TON" in prompt or "타이머" in prompt, (
        f"타이머 청크가 표면화되지 않음: {prompt}"
    )
    assert "LS" in prompt


# ---------------------------------------------------------------------------
# 2. 벤더 필터가 주입 컨텍스트를 바꾼다 (LS vs 미쓰비시)
# ---------------------------------------------------------------------------


def test_vendor_filter_changes_injected_context(
    monkeypatch: pytest.MonkeyPatch, conveyor_spec_safe: StateMachineSpec
) -> None:
    """같은 명세라도 활성 프로파일이 LS↔미쓰비시면 주입 컨텍스트가 달라진다."""
    _set_use_rag(monkeypatch, True)

    ls_fake = _RecordingLLM(content="X := Y;\n")
    monkeypatch.setattr(agents, "_llm", lambda model: ls_fake)
    agents.run_architect(conveyor_spec_safe, use_synth=False, profile=LS_XGK)
    ls_prompt = ls_fake.system_prompt

    mit_fake = _RecordingLLM(content="X := Y;\n")
    monkeypatch.setattr(agents, "_llm", lambda model: mit_fake)
    agents.run_architect(conveyor_spec_safe, use_synth=False, profile=MITSUBISHI_FX)
    mit_prompt = mit_fake.system_prompt

    # 두 컨텍스트는 서로 달라야 한다(벤더 필터가 실제로 작동).
    assert ls_prompt != mit_prompt, "벤더가 달라도 컨텍스트가 동일 — 필터 미작동"
    # 미쓰비시 프롬프트엔 미쓰비시 마커가, LS 프롬프트엔 없어야 한다.
    assert "미쓰비시" in mit_prompt, f"미쓰비시 청크 누락: {mit_prompt}"
    assert "미쓰비시" not in ls_prompt, f"LS 프롬프트에 미쓰비시 누출: {ls_prompt}"


# ---------------------------------------------------------------------------
# 3. 프로파일 이름 → RAG vendor 코드 매핑(결정론)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("profile_name", "expected_vendor"),
    [
        ("LS_XGK", "LS"),
        ("LS_XGI", "LS"),
        ("MITSUBISHI_FX", "MITSUBISHI"),
        ("SIEMENS_S7", "SIEMENS"),
        ("OMRON_CJ", "OMRON"),
    ],
)
def test_profile_to_rag_vendor_mapping(
    profile_name: str, expected_vendor: str
) -> None:
    from app.vendors.profiles import get_profile

    profile = get_profile(profile_name)
    assert agents._rag_vendor_for_profile(profile) == expected_vendor


# ---------------------------------------------------------------------------
# 4. RAG 질의는 명세 요소를 결정론적으로 반영한다
# ---------------------------------------------------------------------------


def test_build_rag_query_includes_spec_terms(
    conveyor_spec_safe: StateMachineSpec,
) -> None:
    query = agents._build_rag_query(conveyor_spec_safe)
    assert conveyor_spec_safe.title in query
    # 인터락이 있으므로 정역/인터락 키워드가 들어간다.
    assert "인터락" in query
    # 보편 래더 요소 키워드는 항상 포함(결정론).
    assert "자기유지" in query and "접점" in query
