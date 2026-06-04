"""골든셋 회귀 게이트 테스트.

scripts/eval.py 를 importlib 로 직접 로드하여 아래 속성을 보장한다:
  1. 전체 골든 케이스 통과율 == 100%
  2. 모든 케이스의 이중코일 == 0
  3. 모든 케이스의 인터락 위반 == 0
  4. 모든 케이스의 io_coverage == 1.0
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# scripts/eval.py 동적 로드 (scripts/ 는 패키지가 아니므로 importlib 사용)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_EVAL_PATH = _REPO_ROOT / "scripts" / "eval.py"
_GOLDEN_DIR = _REPO_ROOT / "tests" / "fixtures" / "golden"


def _load_eval_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("eval", _EVAL_PATH)
    assert spec is not None and spec.loader is not None, "eval.py 를 로드할 수 없습니다"
    module = importlib.util.module_from_spec(spec)
    # 프로젝트 루트가 sys.path 에 있어야 앱 임포트가 동작함
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    spec.loader.exec_module(module)
    return module


_eval = _load_eval_module()

# CaseResult 타입을 Any 로 참조 (동적 로드 모듈의 타입)
_CaseResult = Any
_Summary = dict[str, Any]
_AllResults = tuple[list[_CaseResult], _Summary]

# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def all_results() -> _AllResults:
    """모든 골든 케이스 채점 결과 + 집계 (모듈 범위 캐시)."""
    results, summary = _eval.evaluate_all(_GOLDEN_DIR)
    return results, summary


# ---------------------------------------------------------------------------
# 테스트
# ---------------------------------------------------------------------------


def test_pass_rate_100(all_results: _AllResults) -> None:
    """전체 통과율이 100% 여야 한다."""
    _, summary = all_results
    assert summary["pass_rate"] == 1.0, (
        f"통과율 {summary['pass_rate']:.0%} — 일부 케이스 실패: "
        f"{summary['total_cases'] - summary['passed_cases']}건"
    )


def test_no_double_coils(all_results: _AllResults) -> None:
    """모든 케이스에서 이중코일이 0건이어야 한다."""
    results, _ = all_results
    violations = [r for r in results if r.double_coil_count > 0]
    details = ", ".join(f"{r.name}({r.double_coil_count}건)" for r in violations)
    assert violations == [], f"이중코일 위반 케이스: {details}"


def test_no_interlock_errors(all_results: _AllResults) -> None:
    """모든 케이스에서 인터락 오류가 0건이어야 한다."""
    results, _ = all_results
    violations = [r for r in results if r.interlock_error_count > 0]
    details = ", ".join(f"{r.name}({r.interlock_error_count}건)" for r in violations)
    assert violations == [], f"인터락 위반 케이스: {details}"


def test_io_coverage_full(all_results: _AllResults) -> None:
    """모든 케이스에서 io_coverage == 1.0 이어야 한다."""
    results, _ = all_results
    incomplete = [r for r in results if r.io_coverage < 1.0]
    details = ", ".join(f"{r.name}({r.io_coverage:.2f})" for r in incomplete)
    assert incomplete == [], f"IO 커버리지 미달 케이스: {details}"


def test_golden_case_count() -> None:
    """골든 케이스가 최소 10개 이상 존재해야 한다."""
    cases = _eval.load_cases(_GOLDEN_DIR)
    assert len(cases) >= 10, f"골든 케이스 수 부족: {len(cases)}개"


def test_individual_cases_pass(all_results: _AllResults) -> None:
    """각 케이스가 개별적으로 통과해야 한다."""
    results, _ = all_results
    failed = [r for r in results if not r.passed]
    assert failed == [], "실패 케이스: " + ", ".join(r.name for r in failed)
