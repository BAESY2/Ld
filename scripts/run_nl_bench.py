#!/usr/bin/env python3
"""NL→명세 정확도 벤치마크 실행 — "21개 밖에서 몇 %" 정직한 측정.

결정론(키 없음) 경로를 항상 측정한다. ANTHROPIC_API_KEY 가 있으면 LLM 합성 경로의
임의-로직 정확도까지 측정하도록 확장할 자리(현재는 결정론 바닥값만 출력).

  python scripts/run_nl_bench.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bench import score_keyless  # noqa: E402
from app.nlmatch import analyze  # noqa: E402
from benchmarks.nl_bench_corpus import BENCH  # noqa: E402


def main() -> None:
    rep = score_keyless(BENCH)
    print(rep.report())
    print("\n범위 밖(표현 불가) 요청 처리:")
    for text, expected, why in BENCH:
        if expected is None:
            res = analyze(text)
            mark = "정직거절" if not res.confident else f"침묵실패→{res.recipe_id}"
            print(f"  [{mark}] {text[:34]}  · {why}")
    print(
        "\n해석: in-template 정확도는 '흔한 패턴'의 천장, "
        "out 침묵실패율은 '21개 밖에서 자신있게 거짓'의 위험도.\n"
        "LLM 임의-로직 합성 정확도는 키가 있어야 측정 가능(미측정 = 미해결 난제)."
    )


if __name__ == "__main__":
    main()
