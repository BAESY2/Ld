"""에이전트 테스트 — API 키 없이 _llm 을 monkeypatch.

핵심 회귀 테스트: architect 가 이중코일 ST 를 받아도 후처리로 단일 코일이 된다.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app import agents
from app.memory_map import detect_double_coils
from app.models import ElementType, StateMachineSpec


class _FakeStructured:
    def __init__(self, value: Any) -> None:
        self._value = value

    def invoke(self, messages: Any) -> Any:
        return self._value


class FakeLLM:
    """analyst 용(구조화 출력) / architect 용(content) 둘 다 흉내낸다."""

    def __init__(self, structured: Any = None, content: str = "") -> None:
        self._structured = structured
        self._content = content

    def with_structured_output(self, schema: Any, **kwargs: Any) -> _FakeStructured:
        return _FakeStructured(self._structured)

    def invoke(self, messages: Any) -> Any:
        return SimpleNamespace(content=self._content)


def test_run_analyst_returns_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = StateMachineSpec(title="테스트")
    monkeypatch.setattr(agents, "_llm", lambda model: FakeLLM(structured=fixture))
    result = agents.run_analyst("시작 버튼으로 모터 기동")
    assert isinstance(result, StateMachineSpec)
    assert result.title == "테스트"


def test_run_architect_strips_double_coil(
    monkeypatch: pytest.MonkeyPatch, conveyor_spec_safe: StateMachineSpec
) -> None:
    # LLM 이 일부러 이중코일 ST 를 뱉는다
    bad_st = "MOTOR_FWD := FWD_PB;\nMOTOR_FWD := AUTO_CMD;\n"
    monkeypatch.setattr(agents, "_llm", lambda model: FakeLLM(content=bad_st))

    st_code, allocator = agents.run_architect(conveyor_spec_safe)

    # 후처리로 이중코일이 제거되어야 한다
    assert detect_double_coils(st_code) == {}
    # 디바이스 맵 주석이 포함된다
    assert "디바이스 맵" in st_code


def test_run_renderer_is_deterministic(conveyor_spec_safe: StateMachineSpec) -> None:
    from app.memory_map import DeviceAllocator

    alloc = DeviceAllocator().build_from_spec(conveyor_spec_safe)
    st = "MOTOR_FWD := FWD_PB AND NOT REV_PB;"
    prog = agents.run_renderer(conveyor_spec_safe, st, alloc)
    assert prog.rungs[0].outputs[0].symbol == "MOTOR_FWD"
    assert prog.rungs[0].outputs[0].element_type == ElementType.COIL


def test_run_verifier_delegates(conveyor_spec_unsafe: StateMachineSpec) -> None:
    report = agents.run_verifier(conveyor_spec_unsafe, st_code="")
    # unsafe 명세는 인터락 위반(또는 z3 미설치 경고)을 만든다
    assert report is not None
