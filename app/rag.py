"""IEC 61131-3 명령어 규격 RAG (Phase G).

architect 가 허용된 명령어 규격 안에서만 ST 를 짜도록 컨텍스트를 주입한다.

동작 모드
---------
* USE_RAG=false (기본): ``_FALLBACK_INSTRUCTIONS`` 문자열을 반환한다.
  corpus 파일이나 외부 의존성이 전혀 없어도 동작한다.
* USE_RAG=true: ``data/instructions.jsonl`` corpus를 lazy-load하고 경량
  BM25-lite 랭커로 상위 k개 항목을 반환한다.  faiss/sentence-transformers
  가 없어도 동작한다.
* USE_RAG=true + FAISS 가용 (Phase-G FAISS 업그레이드 경로):
  ``USE_FAISS=true`` 환경 변수와 함께 faiss 및 임베딩 백엔드가 설치된
  경우에만 벡터 검색을 활성화한다.  이 경로는 선택적(optional)이므로
  faiss/sentence-transformers 가 없는 환경에서는 절대 실행되지 않는다.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.config import settings

# ---------------------------------------------------------------------------
# 폴백 명령어 (USE_RAG=false 또는 corpus 파일 없을 때 사용)
# ---------------------------------------------------------------------------
_FALLBACK_INSTRUCTIONS = """\
- 불리언 연산자: AND, OR, NOT, 괄호.
- 대입: SYMBOL := 불리언식;
- 타이머(TON): 입력 조건이 preset(ms) 동안 유지되면 Q 출력 ON.
- 카운터(CTU): 입력 상승엣지마다 카운트, preset 도달 시 Q ON.
- 자기유지: OUT := (START OR OUT) AND NOT STOP;
"""

# corpus 파일 기본 경로 (패키지 루트 기준)
_DEFAULT_CORPUS_PATH = Path(__file__).parent.parent / "data" / "instructions.jsonl"

# ---------------------------------------------------------------------------
# Corpus 타입 별칭
# ---------------------------------------------------------------------------
_CorpusEntry = dict[str, Any]


# ---------------------------------------------------------------------------
# Lazy corpus loader
# ---------------------------------------------------------------------------

_corpus_cache: list[_CorpusEntry] | None = None


def _load_corpus(path: Path | None = None) -> list[_CorpusEntry]:
    """JSONL corpus 를 읽어 캐시한다.  파일이 없거나 파싱 오류면 빈 리스트 반환."""
    global _corpus_cache
    if path is None:
        if _corpus_cache is not None:
            return _corpus_cache
        path = _DEFAULT_CORPUS_PATH

    entries: list[_CorpusEntry] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for _lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    # 손상된 줄은 조용히 건너뜀
                    pass
    except FileNotFoundError:
        pass  # corpus 없으면 폴백으로 degradation

    # 기본 경로인 경우만 캐시
    if path == _DEFAULT_CORPUS_PATH:
        _corpus_cache = entries
    return entries


# ---------------------------------------------------------------------------
# BM25-lite 랭커 (외부 라이브러리 불필요)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[^\w가-힣]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    """소문자 + 한국어 포함 단순 토크나이저."""
    return [t for t in _TOKEN_RE.split(text.lower()) if t]


def _entry_tokens(entry: _CorpusEntry) -> list[str]:
    """검색 대상 텍스트를 토큰 리스트로 변환한다."""
    parts: list[str] = []
    for field in ("name", "category", "description", "example"):
        val = entry.get(field, "")
        if isinstance(val, str):
            parts.extend(_tokenize(val))
    for kw in entry.get("keywords", []):
        if isinstance(kw, str):
            # 키워드는 2배 가중치를 위해 두 번 추가
            toks = _tokenize(kw)
            parts.extend(toks)
            parts.extend(toks)
    # name 도 추가 부스트 (정확 매칭 중요)
    name = entry.get("name", "")
    if isinstance(name, str):
        parts.extend(_tokenize(name))
    return parts


def _bm25_lite_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    k1: float = 1.5,
    b: float = 0.75,
    avg_dl: float = 60.0,
) -> float:
    """단순 BM25-lite 점수 계산 (IDF 는 균일하게 1로 근사)."""
    if not query_tokens or not doc_tokens:
        return 0.0
    dl = len(doc_tokens)
    # 토큰 빈도 테이블
    tf_map: dict[str, int] = {}
    for tok in doc_tokens:
        tf_map[tok] = tf_map.get(tok, 0) + 1

    score = 0.0
    for qt in set(query_tokens):
        tf = tf_map.get(qt, 0)
        if tf == 0:
            continue
        numerator = tf * (k1 + 1)
        denominator = tf + k1 * (1 - b + b * dl / avg_dl)
        score += numerator / denominator  # IDF ≈ 1
    return score


def _rank_corpus(
    query: str,
    corpus: list[_CorpusEntry],
    k: int = 4,
) -> list[_CorpusEntry]:
    """BM25-lite 로 corpus를 랭킹하고 상위 k개를 반환한다."""
    query_tokens = _tokenize(query)
    if not query_tokens:
        return corpus[:k]

    scored: list[tuple[float, int]] = []
    for idx, entry in enumerate(corpus):
        doc_tokens = _entry_tokens(entry)
        score = _bm25_lite_score(query_tokens, doc_tokens)
        scored.append((score, idx))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [corpus[i] for _, i in scored[:k]]


# ---------------------------------------------------------------------------
# 결과 포매터
# ---------------------------------------------------------------------------

def _format_entry(entry: _CorpusEntry) -> str:
    """단일 항목을 읽기 쉬운 텍스트로 변환한다."""
    lines: list[str] = []
    name = entry.get("name", "?")
    category = entry.get("category", "")
    syntax = entry.get("syntax", "")
    devices = entry.get("devices", "")
    description = entry.get("description", "")
    example = entry.get("example", "")

    lines.append(f"[{name}] ({category})")
    if syntax:
        lines.append(f"  구문: {syntax}")
    if devices:
        lines.append(f"  디바이스: {devices}")
    if description:
        lines.append(f"  설명: {description}")
    if example:
        lines.append(f"  예시:\n    {example.strip()}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 선택적(optional) FAISS 경로 — Phase-G FAISS 업그레이드
#
# faiss 와 임베딩 백엔드(sentence-transformers 등)가 설치된 환경에서
# USE_FAISS=true 환경 변수를 설정하면 이 경로가 활성화된다.
# 그렇지 않으면 조용히 비활성화된다.
# ---------------------------------------------------------------------------

def _try_faiss_retrieve(query: str, k: int) -> str | None:
    """FAISS 벡터 검색을 시도한다.  faiss 또는 임베딩 백엔드가 없으면 None 반환."""
    use_faiss = os.environ.get("USE_FAISS", "false").strip().lower() in {"1", "true", "yes"}
    if not use_faiss:
        return None

    try:
        import faiss  # optional dep; ignore_missing_imports covers this
        from sentence_transformers import SentenceTransformer  # optional dep
    except ImportError:
        return None

    # 여기에 FAISS 인덱스 빌드/검색 로직을 구현한다 (faiss 설치 시 활성화).
    # 현재는 스텁으로, faiss 가 임포트 되더라도 아래 로직을 구현해야 한다.
    # 구현 순서:
    #   1. corpus를 _load_corpus()로 로드
    #   2. SentenceTransformer 모델로 각 항목의 description+keywords 임베딩
    #   3. faiss.IndexFlatIP 로 인덱스 구축 (캐시)
    #   4. query 임베딩 후 index.search(query_vec, k)
    #   5. 결과 항목을 _format_entry로 포매팅 후 반환
    _ = faiss  # suppress unused import warning
    _ = SentenceTransformer
    return None  # 미구현 상태 — BM25 폴백으로


# ---------------------------------------------------------------------------
# 퍼블릭 인터페이스
# ---------------------------------------------------------------------------


class InstructionRetriever:
    """IEC 61131-3 명령어 규격 검색기.

    Parameters
    ----------
    corpus_path:
        JSONL corpus 경로. None 이면 기본 경로(``data/instructions.jsonl``)를 사용.
    """

    def __init__(self, corpus_path: Path | None = None) -> None:
        self._corpus_path = corpus_path

    def retrieve(self, query: str, k: int = 4) -> str:
        """query 에 가장 관련 있는 명령어 규격 텍스트를 반환한다.

        USE_RAG=false 이면 항상 ``_FALLBACK_INSTRUCTIONS`` 를 반환한다.
        """
        if not settings.use_rag:
            return _FALLBACK_INSTRUCTIONS

        # 선택적 FAISS 경로 시도
        faiss_result = _try_faiss_retrieve(query, k)
        if faiss_result is not None:
            return faiss_result

        # BM25-lite 경량 검색
        corpus = _load_corpus(self._corpus_path)
        if not corpus:
            # corpus 로드 실패 → 폴백
            return _FALLBACK_INSTRUCTIONS

        top_entries = _rank_corpus(query, corpus, k=k)
        chunks = [_format_entry(e) for e in top_entries]
        return "\n\n".join(chunks)


_retriever = InstructionRetriever()


def get_instruction_context(query: str) -> str:
    """싱글톤 진입점.  agents.py 에서 임포트한다."""
    return _retriever.retrieve(query)
