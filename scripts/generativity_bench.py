#!/usr/bin/env python3
"""생성성(generativity) 벤치 — '37개'가 아니라 조합적으로 열려 있음을 *수치*로 (MASTERPLAN).

frame_to_spec 컴파일러는 고정 레시피가 아니라, 유한 어휘(조건 유형 × 동작 × 기기)의 임의
조합을 검증 가능한 프로그램으로 컴파일한다. 무작위 조합을 대량 생성해, 검증 통과한 *서로
다른* 프로그램 수를 센다. 모든 산출물은 synth→verify 게이트 통과(이중코일 0). 키 불필요·결정론.

핵심: 조합 공간은 규칙 수 R 에 지수적(≈(조건×동작×기기)^R) — 사실상 무한. 어휘만 늘리면
표현 범위가 더 넓어진다(레시피 추가가 아니라 *원시어휘* 확장).
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.compile_frame import frame_to_spec  # noqa: E402
from app.memory_map import detect_double_coils  # noqa: E402
from app.synth import synthesize_st  # noqa: E402
from app.verifier import verify  # noqa: E402

_CONDS = [
    "저수위 되면", "고수위 되면", "고장 나면", "부품 {n}개 차면",
    "압력 {n}바 넘으면", "온도 {n}도 되면", "도착하면", "막히면",
    "광센서 감지되면", "리밋 도착하면",
]
_ACTS = [
    "펌프 켜", "펌프 꺼", "모터 돌려", "모터 멈춰", "밸브 닫아", "히터 꺼",
    "경광등 켜", "배출해", "사이렌 켜", "팬 돌려", "클램프 고정하고", "실린더 올려",
    "부저 울려", "적색등 켜",
]


def _make(rules: list[tuple[str, str]], rng: random.Random) -> str:
    parts = []
    for c, a in rules:
        parts.append(f"{c.format(n=rng.choice([3, 5, 10, 50, 100, 200]))} {a}")
    return " ".join(parts)


def run(trials_per_k: int = 800, seed: int = 7) -> tuple[int, int]:
    """(검증 통과한 서로 다른 프로그램 수, 총 시도 수). 결정론(시드 고정)."""
    rng = random.Random(seed)
    distinct: set[str] = set()
    total = 0
    for k in (1, 2, 3):
        for _ in range(trials_per_k):
            rules = [(rng.choice(_CONDS), rng.choice(_ACTS)) for _ in range(k)]
            text = _make(rules, rng)
            total += 1
            r = frame_to_spec(text)
            if not r.confident:
                continue
            st = synthesize_st(r.spec)
            if detect_double_coils(st):
                continue
            if verify(r.spec, st).passed:
                distinct.add(st)
    return len(distinct), total


def main() -> int:
    n_vocab = len(_CONDS) * len(_ACTS)
    distinct, total = run()
    print("=== 생성성 벤치: 컴파일러는 '37개'가 아니다 ===")
    print(f"유한 어휘: 조건 {len(_CONDS)}유형 × 동작·기기 {len(_ACTS)} = 규칙 원자 {n_vocab}개")
    print(f"무작위 조합 시도 {total}건 → *검증 통과 서로 다른 프로그램* {distinct}개 (이중코일0)")
    print("\n해석: 같은 유한 어휘에서 조합적으로 쏟아진다. 조합 공간은 규칙 수에 지수적(사실상")
    print("무한) — 레시피를 늘리는 게 아니라 원시어휘를 늘리면 표현 범위가 넓어진다.")
    print("모든 산출물은 형식검증 게이트를 통과한다(환각 0).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
