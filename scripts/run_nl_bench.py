#!/usr/bin/env python3
"""NL→명세 정확도 벤치마크 실행 — "21개 밖에서 몇 %" 정직한 측정.

결정론(키 없음) 경로를 항상 측정한다. LLM 키가 있으면 설계 폐루프
(score_design)의 '자유요청→검증통과 래더' 전환율까지 실측한다.

  python scripts/run_nl_bench.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bench import score_design, score_keyless  # noqa: E402
from app.nlmatch import analyze  # noqa: E402
from benchmarks.nl_bench_corpus import BENCH  # noqa: E402


def _has_llm_key() -> bool:
    return any(os.getenv(k) for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LLM_BASE_URL"))


def main() -> None:
    rep = score_keyless(BENCH)
    print(rep.report())
    print("\n범위 밖(표현 불가) 요청 처리:")
    for text, expected, why in BENCH:
        if expected is None:
            res = analyze(text)
            mark = "정직거절" if not res.confident else f"침묵실패→{res.recipe_id}"
            print(f"  [{mark}] {text[:34]}  · {why}")

    print()
    if _has_llm_key():
        # 키 존재 → 설계 폐루프 실측(실제 LLM 호출). model_factory=None → _llm 시드 사용.
        print(score_design(BENCH).report())
    else:
        print(
            "── 설계 경로(LLM) 정확도 ── 키 없음 — 미측정\n"
            "  하니스는 준비됨: ANTHROPIC_API_KEY(또는 OPENAI_API_KEY/LLM_BASE_URL) 설정 후\n"
            "  다시 실행하면 score_design(BENCH) 로 '자유요청→검증통과 래더' 전환율을 실측한다."
        )

    print(
        "\n해석: in-template 정확도는 '흔한 패턴'의 천장, "
        "out 침묵실패율은 '21개 밖에서 자신있게 거짓'의 위험도.\n"
        "설계 게이트 통과율은 LLM 이 천장을 넘어 검증통과 래더를 낸 비율(키 필요)."
    )


if __name__ == "__main__":
    main()
