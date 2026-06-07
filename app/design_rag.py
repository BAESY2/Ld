"""검증예제 RAG — 설계 LLM 에 '검증 통과한' 레시피 예제를 few-shot 으로 주입.

Agents4PLC 권고: 코딩 에이전트가 *검증된* 샘플을 retrieval 해 grounding 한다. 핵심
규율은 **verified-only** — 예제 저장소에는 결정론 게이트(build→synth→verify)를 통과한
레시피만 admit 한다. 검색은 키 없이 결정론(BM25-lite, app.rag 재사용)이라 CI 에서
고정 가능하며, 실제 LLM 설계 정확도 향상은 키가 있을 때 발현된다(주입 메커니즘과 검색
랭킹만 키-프리로 박는다).

설계 원칙(CLAUDE.md): 프로바이더 결정은 _llm 단일 지점, LLM 호출은 테스트에서 mock.
본 모듈은 LLM 을 호출하지 않는다(예제 생성·랭킹 전부 결정론).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.nlmatch import RECIPE_KEYWORDS
from app.rag import _bm25_lite_score, _tokenize
from app.synth import synthesize_st
from app.verifier import verify
from app.wizard import RECIPES, build_spec


@dataclass(frozen=True)
class DesignExample:
    """검증 통과한 단일 설계 예제(레시피 기반)."""

    recipe_id: str
    title: str
    intent: str  # 검색 대상 텍스트(제목 + 설명 + 키워드)
    st: str      # 검증 통과한 IEC 61131-3 ST(구체 grounding)


@lru_cache(maxsize=1)
def verified_examples() -> tuple[DesignExample, ...]:
    """모든 레시피를 기본값으로 합성·검증해 통과분만 예제 저장소로 만든다(캐시).

    검증 미통과/합성 실패 레시피는 저장소에서 제외한다(verified-only 규율).
    """
    out: list[DesignExample] = []
    for rid, recipe in RECIPES.items():
        try:
            spec = build_spec(rid)
            st = synthesize_st(spec)
            if not verify(spec, st).passed:
                continue
        except Exception:  # noqa: BLE001 - 깨진 레시피는 조용히 제외(저장소 무결성 우선)
            continue
        kws = " ".join(RECIPE_KEYWORDS.get(rid, []))
        intent = f"{recipe.title} {recipe.description} {kws}"
        out.append(DesignExample(recipe_id=rid, title=recipe.title, intent=intent, st=st))
    return tuple(out)


def retrieve_design_examples(text: str, k: int = 3) -> list[DesignExample]:
    """요청과 가장 가까운 검증예제 상위 k개(BM25-lite, 키 불필요·결정론)."""
    examples = verified_examples()
    qt = _tokenize(text)
    if not qt:
        return list(examples[:k])
    ranked = sorted(
        examples,
        key=lambda e: (_bm25_lite_score(qt, _tokenize(e.intent)), e.recipe_id),
        reverse=True,
    )
    return ranked[:k]


def format_examples_for_prompt(examples: list[DesignExample]) -> str:
    """검증예제를 설계 프롬프트용 few-shot 텍스트로 렌더(빈 입력이면 빈 문자열)."""
    if not examples:
        return ""
    blocks = [
        "# 참고: 검증을 통과한 유사 설계 예제 (형식·관용만 따르고, 요구에 맞게 새로 설계할 것)"
    ]
    for e in examples:
        blocks.append(f"## 의도: {e.title}\n```st\n{e.st.strip()}\n```")
    return "\n".join(blocks)
