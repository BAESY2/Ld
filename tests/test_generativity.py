"""생성성 회귀 가드 — 컴파일러가 '37개'가 아니라 조합적으로 열려 있음을 고정.

유한 어휘에서 무작위 조합을 컴파일해, 검증 통과한 *서로 다른* 프로그램이 수백 개 이상
나오고 전부 게이트(이중코일0·verify)를 통과함을 단정. 시드 고정 → 결정론.
"""

from __future__ import annotations


def test_compiler_generates_many_distinct_verified_programs() -> None:
    from scripts.generativity_bench import run

    distinct, total = run(trials_per_k=200, seed=7)
    # 고정 레시피(37) 를 압도하는 *서로 다른 검증 통과* 프로그램이 나와야 한다.
    assert distinct >= 300, f"서로 다른 검증 프로그램이 너무 적음: {distinct}"
    assert distinct > 37  # '37개'가 아니라 조합적으로 열려 있음
    assert total == 600
