"""compile_bench 안전속성 테스트 (MASTERPLAN G4).

핵심 단정(과장 금지, 측정 기반):
  (a) 범위밖 침묵실패 = 0     — 자신있게 틀린 컴파일이 단 한 건도 없다.
  (b) confident 컴파일은 전부 verify 통과 + 이중코일 0 — 합성→검증 게이트의 안전속성.
벤치 자체가 깨지지 않고 결정론적으로 도는 것도 확인한다(LLM 미사용·키 불필요).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BENCH_PATH = _ROOT / "scripts" / "compile_bench.py"

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_spec = importlib.util.spec_from_file_location("compile_bench", _BENCH_PATH)
assert _spec is not None and _spec.loader is not None
compile_bench = importlib.util.module_from_spec(_spec)
sys.modules["compile_bench"] = compile_bench  # dataclass 가 모듈을 찾을 수 있도록 등록
_spec.loader.exec_module(compile_bench)


def test_corpus_loads_and_is_substantial() -> None:
    """코퍼스가 40~60건이고 4개 난이도 라벨을 모두 포함한다."""
    records = compile_bench.load_corpus()
    assert 40 <= len(records) <= 60, f"코퍼스 크기 범위 벗어남: {len(records)}"
    difficulties = {str(r["difficulty"]) for r in records}
    assert difficulties == {"easy", "quantified", "compound", "out_of_scope"}
    for r in records:
        assert isinstance(r["text"], str) and r["text"]
        assert isinstance(r["compile"], bool)


def test_bench_runs_without_crashing() -> None:
    """벤치 전체가 예외 없이 돌고, 난이도별 버킷이 비지 않는다."""
    buckets = compile_bench.run()
    assert buckets, "버킷이 비어있음"
    assert sum(b.total for b in buckets.values()) >= 40
    for diff in ("easy", "quantified", "compound", "out_of_scope"):
        assert diff in buckets and buckets[diff].total > 0


def test_no_silent_failures() -> None:
    """(a) 범위밖(compile=False)을 confident 로 컴파일한 경우가 0 이어야 한다."""
    buckets = compile_bench.run()
    silent = compile_bench.total_silent_failures(buckets)
    offenders = [
        c.text
        for b in buckets.values()
        for c in b.cases
        if c.silent_failure
    ]
    assert silent == 0, f"침묵실패(자신있게 틀림) 발생: {offenders}"


def test_confident_compiles_verify_and_no_double_coil() -> None:
    """(b) confident 컴파일은 전부 verify 통과 + 이중코일 0 (핵심 안전속성)."""
    buckets = compile_bench.run()
    assert compile_bench.all_confident_safe(buckets)
    confident_cases = [
        c for b in buckets.values() for c in b.cases if c.confident
    ]
    assert confident_cases, "confident 컴파일이 하나도 없음(커버리지 0 — 벤치 무의미)"
    for c in confident_cases:
        assert c.verified, f"confident 인데 verify 실패: {c.text}"
        assert not c.double_coil, f"confident 인데 이중코일: {c.text}"


def test_out_of_scope_all_honestly_held() -> None:
    """범위밖은 전부 confident=False 로 정직하게 거절한다(보류율 100%)."""
    buckets = compile_bench.run()
    oos = buckets["out_of_scope"]
    assert oos.honest_holds == oos.total
    assert oos.silent_failures == 0


def test_in_scope_coverage_is_meaningful() -> None:
    """in-scope 라벨(compile=True)은 실제로 대부분 confident 로 컴파일된다.

    코퍼스 라벨과 컴파일러 동작이 일치(라벨이 곧 컴파일 결과)함을 단정한다 —
    벤치 수치가 라벨과 어긋나면(과장/축소) 여기서 깨진다.
    """
    buckets = compile_bench.run()
    for b in buckets.values():
        for c in b.cases:
            assert c.confident == c.expect_compile, (
                f"라벨 불일치: 기대 compile={c.expect_compile} "
                f"실제 confident={c.confident} | {c.text}"
            )


def test_run_is_deterministic() -> None:
    """동일 입력에 동일 수치(결정론) — 비결정성 누출 방지."""
    def key(bk: dict[str, object]) -> dict[str, tuple[float, float, float, int]]:
        return {
            d: (bk[d].coverage, bk[d].verify_rate, bk[d].no_dbl_rate, bk[d].silent_failures)
            for d in bk
        }

    assert key(compile_bench.run()) == key(compile_bench.run())


def test_main_exits_zero() -> None:
    """안전속성 충족 시 main() 은 0 을 반환한다(CI 가드)."""
    assert compile_bench.main() == 0
