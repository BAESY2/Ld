"""명령어 규격 RAG (스텁 → Phase G 에서 FAISS 로 교체).

architect 가 허용된 명령어 규격 안에서만 ST 를 짜도록 컨텍스트를 주입한다.
USE_RAG=false 면 더미 규격을 반환한다.
"""

from __future__ import annotations

from app.config import settings

_FALLBACK_INSTRUCTIONS = """\
- 불리언 연산자: AND, OR, NOT, 괄호.
- 대입: SYMBOL := 불리언식;
- 타이머(TON): 입력 조건이 preset(ms) 동안 유지되면 Q 출력 ON.
- 카운터(CTU): 입력 상승엣지마다 카운트, preset 도달 시 Q ON.
- 자기유지: OUT := (START OR OUT) AND NOT STOP;
"""


class InstructionRetriever:
    """명령어 규격 검색기. 1차는 더미, Phase G 에서 FAISS."""

    def retrieve(self, query: str, k: int = 4) -> str:
        if not settings.use_rag:
            return _FALLBACK_INSTRUCTIONS
        # Phase G: FAISS 검색으로 교체
        return _FALLBACK_INSTRUCTIONS


_retriever = InstructionRetriever()


def get_instruction_context(query: str) -> str:
    """싱글톤 진입점."""
    return _retriever.retrieve(query)
