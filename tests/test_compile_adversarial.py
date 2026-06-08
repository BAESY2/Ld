"""적대·대규모 컴파일 벤치 안전속성 테스트 (compile_adversarial_bench).

기존 compile_bench(52건)의 자가채점 약점 — *규모·무편향·적대성* — 을 보완한 110건
코퍼스에 대해 다음 핵심 안전속성을 단정한다(과장 금지, 측정 기반):

  (a) 범위밖 함정의 침묵실패 = 0 — *자신있게 잘못 컴파일* 이 단 한 건도 없다(핵심).
      특히 in-vocab 단어(모터·히터·밸브 등)가 섞인 PID/모션/통신/HMI 범위밖을
      confident 로 컴파일하지 않는다.
  (b) confident 컴파일은 전부 verify 통과 + 이중코일 0 — 합성→검증 게이트의 안전속성.

벤치 자체가 결정론적으로(LLM 미사용·키 불필요) 도는 것도 확인한다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BENCH_PATH = _ROOT / "scripts" / "compile_adversarial_bench.py"

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_spec = importlib.util.spec_from_file_location("compile_adversarial_bench", _BENCH_PATH)
assert _spec is not None and _spec.loader is not None
compile_adversarial_bench = importlib.util.module_from_spec(_spec)
# dataclass 가 모듈을 찾을 수 있도록 등록.
sys.modules["compile_adversarial_bench"] = compile_adversarial_bench
_spec.loader.exec_module(compile_adversarial_bench)

_bench = compile_adversarial_bench
_OOS_DIFFICULTIES = ("oos_invocab", "oos_chatter")


def test_corpus_loads_and_is_large_and_adversarial() -> None:
    """코퍼스가 100건 이상이고, 6개 난이도 + 적대(범위밖) 함정군을 포함한다."""
    records = _bench.load_corpus()
    assert len(records) >= 100, f"코퍼스가 100건 미만: {len(records)}"
    difficulties = {str(r["difficulty"]) for r in records}
    assert {"easy", "quantified", "compound", "adversarial_typo"} <= difficulties
    assert {"oos_invocab", "oos_chatter"} <= difficulties
    # 범위밖(함정) 비중이 충분히 커야 침묵실패 측정이 의미 있다.
    oos = sum(1 for r in records if not bool(r["expect_compile"]))
    assert oos >= 30, f"범위밖 함정이 너무 적음: {oos}"
    for r in records:
        assert isinstance(r["text"], str) and r["text"]
        assert isinstance(r["expect_compile"], bool)
        assert isinstance(r["difficulty"], str) and r["difficulty"]


def test_bench_runs_without_crashing() -> None:
    """벤치 전체가 예외 없이 돌고, 난이도별 버킷이 비지 않는다."""
    buckets = _bench.run()
    assert buckets, "버킷이 비어있음"
    assert sum(b.total for b in buckets.values()) >= 100
    for diff in ("easy", "quantified", "compound", "adversarial_typo"):
        assert diff in buckets and buckets[diff].total > 0
    for diff in _OOS_DIFFICULTIES:
        assert diff in buckets and buckets[diff].out_of_scope > 0


def test_no_silent_failures_core_safety() -> None:
    """(a) 핵심 안전속성: 범위밖 함정의 침묵실패 = 0.

    in-vocab 단어가 섞인 범위밖을 *자신있게 잘못 컴파일* 하지 않음을 단정한다.
    """
    buckets = _bench.run()
    silent = _bench.total_silent_failures(buckets)
    offenders = [
        c.text for b in buckets.values() for c in b.cases if c.silent_failure
    ]
    assert silent == 0, f"침묵실패(자신있게 틀림) 발생: {offenders}"


def test_in_vocab_out_of_scope_traps_all_rejected() -> None:
    """in-vocab 단어가 섞인 범위밖 함정을 단 하나도 confident 로 컴파일하지 않는다."""
    buckets = _bench.run()
    for diff in _OOS_DIFFICULTIES:
        bucket = buckets[diff]
        assert bucket.silent_failures == 0
        assert bucket.honest_holds == bucket.out_of_scope
        for c in bucket.cases:
            assert not c.confident, f"범위밖을 confident 로 컴파일: {c.text}"


def test_confident_compiles_verify_and_no_double_coil() -> None:
    """(b) confident 컴파일은 전부 verify 통과 + 이중코일 0 (핵심 안전속성)."""
    buckets = _bench.run()
    assert _bench.all_confident_safe(buckets)
    confident_cases = [c for b in buckets.values() for c in b.cases if c.confident]
    assert confident_cases, "confident 컴파일이 하나도 없음(벤치 무의미)"
    for c in confident_cases:
        assert c.verified, f"confident 인데 verify 실패: {c.text}"
        assert not c.double_coil, f"confident 인데 이중코일: {c.text}"


def test_labels_match_compiler_behavior() -> None:
    """코퍼스 라벨(expect_compile)과 컴파일러 동작(confident)이 일치한다.

    수치가 라벨과 어긋나면(과장/축소) 여기서 깨진다 — 벤치 정직성의 닻.
    """
    buckets = _bench.run()
    mismatches = [
        (c.text, c.expect_compile, c.confident)
        for b in buckets.values()
        for c in b.cases
        if c.confident != c.expect_compile
    ]
    assert not mismatches, f"라벨 불일치: {mismatches}"


def test_run_is_deterministic() -> None:
    """동일 입력에 동일 수치(결정론) — 비결정성 누출 방지."""

    def key(bk: dict[str, object]) -> dict[str, tuple[float, float, float, int]]:
        return {
            d: (
                bk[d].coverage,
                bk[d].verify_rate,
                bk[d].no_dbl_rate,
                bk[d].silent_failures,
            )
            for d in bk
        }

    assert key(_bench.run()) == key(_bench.run())


def test_main_exits_zero() -> None:
    """안전속성 충족 시 main() 은 0 을 반환한다(CI 가드)."""
    assert _bench.main() == 0
