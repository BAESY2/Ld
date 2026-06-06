"""4 에이전트 — analyst / architect / verifier / renderer.

- LLM 을 쓰는 곳: analyst(자연어→명세), architect(명세→ST) 둘뿐.
- verifier 는 결정론 검증기(verifier.py)에 위임.
- renderer 는 결정론 트랜스파일러(transpiler.py)로 대체 → LLM 불필요, 즉시·무결점.

`_llm(model)` 이 유일한 프로바이더 결정 지점이다(vendor-agnostic).
테스트는 이 함수를 monkeypatch 하여 API 키 없이 통과한다.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

from app.config import settings
from app.memory_map import DeviceAllocator, merge_double_coils
from app.models import LadderProgram, StateMachineSpec, VerificationReport
from app.prompts import REQUIREMENTS_ANALYST_SYSTEM, ST_ARCHITECT_SYSTEM
from app.rag import get_instruction_context
from app.synth import covers_all_outputs, synthesize_st
from app.transpiler import transpile_st
from app.vendors.profiles import DEFAULT_PROFILE, VendorProfile
from app.verifier import verify

logger = logging.getLogger("plc.agents")

_T = TypeVar("_T")

# RAG corpus(data/instructions.jsonl)의 vendor 필드 값(LS/MITSUBISHI/SIEMENS/
# OMRON/ROCKWELL)으로의 매핑 키워드. 프로파일 이름(예: LS_XGK, MITSUBISHI_FX,
# SIEMENS_S7, OMRON_CJ)은 벤더 접두사를 포함하므로 이를 corpus vendor 코드로 정규화한다.
_PROFILE_VENDOR_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("MITSUBISHI", "MITSUBISHI"),
    ("SIEMENS", "SIEMENS"),
    ("OMRON", "OMRON"),
    ("ROCKWELL", "ROCKWELL"),
    ("LS", "LS"),  # LS_XGK / LS_XGI 등은 마지막에 매칭(다른 벤더 접두사 우선)
)

# 명세에서 추출해 RAG 질의를 보강할 도메인 키워드(결정론). 명세에 해당 요소가
# 있으면 질의에 더해 벤더-정확 명령어 청크(타이머/카운터/엣지/인터락 등)를 표면화한다.
_QUERY_TERMS = "타이머 카운터 정역 인터락 자기유지 접점 코일"


def _rag_vendor_for_profile(profile: VendorProfile) -> str:
    """VendorProfile.name(예: ``LS_XGK``)을 RAG corpus vendor 코드(``LS``)로 매핑."""
    upper = profile.name.upper()
    for keyword, vendor in _PROFILE_VENDOR_KEYWORDS:
        if keyword in upper:
            return vendor
    return "LS"  # 알 수 없으면 기본 LS_XGK 가정


def _build_rag_query(spec: StateMachineSpec) -> str:
    """명세에서 결정론적으로 RAG 질의 문자열을 만든다.

    제목 + 명세에 실제 존재하는 요소(타이머/카운터/인터락)의 한국어 키워드를
    더해, architect 가 필요한 벤더-정확 명령어 규격을 끌어오도록 한다.
    """
    terms: list[str] = []
    if spec.title:
        terms.append(spec.title)
    if spec.timers:
        terms.append("타이머")
    if spec.counters:
        terms.append("카운터")
    if spec.interlocks:
        terms.append("정역 인터락 상호배제")
    # 자기유지/접점/코일은 래더의 보편 요소이므로 항상 포함(결정론)
    terms.append(_QUERY_TERMS)
    return " ".join(terms) if terms else "ladder"


def _retry(fn: Callable[[], _T], attempts: int = 3, base_delay: float = 1.0) -> _T:
    """구조화 출력 파싱/일시 오류에 대한 지수 백오프 재시도."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if i < attempts - 1:
                delay = base_delay * (2**i)
                logger.warning(
                    "LLM 호출 실패(%d/%d), %.1fs 후 재시도: %s", i + 1, attempts, delay, exc
                )
                time.sleep(delay)
    assert last is not None
    raise last


def _llm(model: str) -> Any:
    """프로바이더별 채팅 모델 팩토리. 여기서만 vendor 를 결정한다.

    import 를 함수 안에서 하므로, LLM 미사용 경로(결정론 코어/트랜스파일)는
    langchain 설치 없이도 동작한다.
    """
    provider = settings.llm_provider
    temperature = settings.temperature
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, temperature=temperature, max_tokens=8000)
    if provider == "openai_compatible":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            temperature=temperature,
            base_url=settings.local_base_url,
            api_key="not-needed",
        )
    if provider == "local":
        from app.local_llm import LocalChatModel  # 사용자가 직접 구현(자체 호스팅)

        return LocalChatModel(model)
    raise ValueError(f"알 수 없는 LLM_PROVIDER: {provider}")


def run_analyst(request: str) -> StateMachineSpec:
    """자연어 요구 → 구조화된 상태머신 명세."""
    model = _llm(settings.analyst_model).with_structured_output(StateMachineSpec)
    result = _retry(
        lambda: model.invoke([("system", REQUIREMENTS_ANALYST_SYSTEM), ("human", request)])
    )
    if isinstance(result, StateMachineSpec):
        return result
    return StateMachineSpec.model_validate(result)


def run_architect(
    spec: StateMachineSpec,
    feedback: str | None = None,
    use_synth: bool = True,
    profile: VendorProfile | None = None,
) -> tuple[str, DeviceAllocator]:
    """명세 → ST 코드(+디바이스 맵).

    **결정론 합성 우선**(래더 생성 난제의 핵심): 모든 출력이 상태구동이면 LLM 없이
    명세에서 직접 자기유지 ST 를 합성한다(환각 차단, API 키 불필요). 합성 불가
    (조합 출력 등)하거나 재시도(feedback) 시에는 LLM 으로 폴백하고, 이중코일은
    후처리로 기계적으로 제거한다.

    LLM 폴백 경로에서는 활성 벤더 프로파일(기본 LS_XGK)에 맞는 명령어 규격을
    RAG 에서 검색해 프롬프트에 주입한다(벤더-정확 시맨틱 인용).
    """
    active_profile = profile or DEFAULT_PROFILE
    allocator = DeviceAllocator(profile=active_profile).build_from_spec(spec)

    # 1) 결정론 합성 경로 — 첫 시도이고 모든 출력이 상태구동일 때
    if use_synth and feedback is None and covers_all_outputs(spec):
        merged = merge_double_coils(synthesize_st(spec), allocator)
        return f"{allocator.as_comment_block()}\n\n{merged.code}", allocator

    # 2) LLM 폴백 — 조합 출력/재시도. 이중코일은 후처리로 제거.
    #    활성 벤더로 필터된 명령어 규격을 결정론 질의로 검색해 주입한다.
    vendor = _rag_vendor_for_profile(active_profile)
    instruction_context = get_instruction_context(_build_rag_query(spec), vendor=vendor)
    system = ST_ARCHITECT_SYSTEM.format(
        instruction_context=instruction_context,
        feedback=feedback or "(없음)",
    )
    human = (
        f"[명세 JSON]\n{spec.model_dump_json(indent=2)}\n\n"
        f"[디바이스 맵 — 이 심볼명을 사용]\n{allocator.as_comment_block()}"
    )
    raw = _retry(
        lambda: _llm(settings.architect_model).invoke([("system", system), ("human", human)])
    )
    st_code = raw.content if hasattr(raw, "content") else str(raw)

    # LLM 이 이중코일을 뱉어도 기계적으로 제거(회귀 방지의 핵심)
    merged = merge_double_coils(st_code, allocator)
    final = f"{allocator.as_comment_block()}\n\n{merged.code}"
    return final, allocator


def run_verifier(spec: StateMachineSpec, st_code: str) -> VerificationReport:
    """결정론 검증기에 위임."""
    return verify(spec, st_code)


def run_renderer(
    spec: StateMachineSpec, st_code: str, allocator: DeviceAllocator
) -> LadderProgram:
    """결정론 트랜스파일러로 ST → 래더(LLM 불필요)."""
    return transpile_st(st_code, allocator=allocator, title=spec.title)
