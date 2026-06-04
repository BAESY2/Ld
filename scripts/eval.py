"""골든셋 회귀 평가 하네스 (Phase I, API 키 불필요).

결정론적 코어만 사용하여 골든 케이스를 채점한다.

하드 게이트 (모두 통과해야 pass=True):
  - 이중코일 0건 : detect_double_coils(golden_st) 결과가 없어야 함
  - 인터락 위반 0건 : verify(spec, golden_st).has_errors == False
  - 렁 수 하한 : transpile_st(golden_st) 렁 수 >= expect["min_rungs"]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 경로 설정: 이 스크립트가 scripts/ 에 있으므로 프로젝트 루트를 sys.path 에 추가
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.memory_map import detect_double_coils  # noqa: E402
from app.models import ElementType, IODirection, StateMachineSpec  # noqa: E402
from app.transpiler import transpile_st  # noqa: E402
from app.verifier import verify  # noqa: E402

# ---------------------------------------------------------------------------
# 타입 별칭
# ---------------------------------------------------------------------------
GoldenCase = dict[str, Any]


class CaseResult:
    """케이스 평가 결과."""

    def __init__(
        self,
        name: str,
        double_coil_count: int,
        interlock_error_count: int,
        deadlock_error_count: int,
        rung_count: int,
        io_coverage: float,
        passed: bool,
    ) -> None:
        self.name = name
        self.double_coil_count = double_coil_count
        self.interlock_error_count = interlock_error_count
        self.deadlock_error_count = deadlock_error_count
        self.rung_count = rung_count
        self.io_coverage = io_coverage
        self.passed = passed

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "double_coil_count": self.double_coil_count,
            "interlock_error_count": self.interlock_error_count,
            "deadlock_error_count": self.deadlock_error_count,
            "rung_count": self.rung_count,
            "io_coverage": self.io_coverage,
            "passed": self.passed,
        }


# ---------------------------------------------------------------------------
# 공개 함수
# ---------------------------------------------------------------------------


def load_cases(golden_dir: str | Path) -> list[GoldenCase]:
    """golden_dir 아래의 모든 .json 파일을 읽어 케이스 목록으로 반환한다."""
    directory = Path(golden_dir)
    cases: list[GoldenCase] = []
    for path in sorted(directory.glob("*.json")):
        with path.open(encoding="utf-8") as fh:
            cases.append(json.load(fh))
    return cases


def evaluate_case(case: GoldenCase) -> CaseResult:
    """단일 케이스를 결정론적으로 채점하고 CaseResult 를 반환한다.

    채점 항목:
      - double_coil_count   : detect_double_coils 로 검출된 심볼 수
      - interlock_error_count : verify 에서 INTERLOCK severity=error 건수
      - deadlock_error_count  : verify 에서 DEADLOCK severity=error 건수
      - rung_count            : transpile_st 결과 렁 수
      - io_coverage           : 명세 OUTPUT 심볼 중 래더 코일에 출현한 비율
      - passed                : 하드 게이트(이중코일==0, 인터락==0, 렁>=min_rungs) 충족 여부
    """
    name: str = case["name"]
    spec = StateMachineSpec(**case["spec"])
    golden_st: str = case["golden_st"]
    expect: dict[str, Any] = case["expect"]

    # 1) 이중 코일 검출
    dups = detect_double_coils(golden_st)
    double_coil_count = len(dups)

    # 2) 검증 (인터락 + 도달성)
    report = verify(spec, golden_st)
    interlock_error_count = sum(
        1 for i in report.issues if i.code == "INTERLOCK" and i.severity == "error"
    )
    deadlock_error_count = sum(
        1 for i in report.issues if i.code == "DEADLOCK" and i.severity == "error"
    )

    # 3) 트랜스파일
    ladder = transpile_st(golden_st)
    rung_count = len(ladder.rungs)

    # 4) IO 커버리지: 명세의 OUTPUT 심볼 중 래더 코일 출현 비율
    output_symbols = {
        p.symbol for p in spec.io_points if p.direction == IODirection.OUTPUT
    }
    coil_symbols = {
        elem.symbol
        for rung in ladder.rungs
        for elem in rung.outputs
        if elem.element_type == ElementType.COIL
    }
    if output_symbols:
        io_coverage = len(output_symbols & coil_symbols) / len(output_symbols)
    else:
        io_coverage = 1.0

    # 5) 하드 게이트 판정
    min_rungs: int = expect.get("min_rungs", 1)
    passed = (
        double_coil_count == 0
        and interlock_error_count == 0
        and rung_count >= min_rungs
    )

    return CaseResult(
        name=name,
        double_coil_count=double_coil_count,
        interlock_error_count=interlock_error_count,
        deadlock_error_count=deadlock_error_count,
        rung_count=rung_count,
        io_coverage=io_coverage,
        passed=passed,
    )


def evaluate_all(
    golden_dir: str | Path,
) -> tuple[list[CaseResult], dict[str, Any]]:
    """골든 디렉터리의 모든 케이스를 채점하고 (결과 목록, 집계) 를 반환한다."""
    cases = load_cases(golden_dir)
    results = [evaluate_case(c) for c in cases]

    total = len(results)
    passed_count = sum(1 for r in results if r.passed)
    pass_rate = passed_count / total if total else 0.0
    total_double_coils = sum(r.double_coil_count for r in results)
    total_interlock_violations = sum(r.interlock_error_count for r in results)

    summary: dict[str, Any] = {
        "total_cases": total,
        "passed_cases": passed_count,
        "pass_rate": pass_rate,
        "total_double_coil_violations": total_double_coils,
        "total_interlock_violations": total_interlock_violations,
    }
    return results, summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
_DEFAULT_GOLDEN_DIR = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "golden"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="골든셋 회귀 평가 — 이중코일 0건, 인터락 위반 0건을 하드 게이트로 검사한다."
    )
    parser.add_argument(
        "--golden-dir",
        default=str(_DEFAULT_GOLDEN_DIR),
        help=f"골든 케이스 디렉터리 (기본값: {_DEFAULT_GOLDEN_DIR})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="머신 가독 JSON 결과를 stdout 에 출력한다.",
    )
    args = parser.parse_args()

    results, summary = evaluate_all(args.golden_dir)

    if args.json:
        output = {
            "summary": summary,
            "cases": [r.as_dict() for r in results],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        # 테이블 헤더
        header = f"{'NAME':<30} {'RUNGS':>5} {'DBL':>4} {'ILCK':>5} {'IO_COV':>7} {'STATUS':<6}"
        sep = "-" * len(header)
        print(sep)
        print(header)
        print(sep)
        for r in results:
            status = "PASS" if r.passed else "FAIL"
            print(
                f"{r.name:<30} {r.rung_count:>5} {r.double_coil_count:>4} "
                f"{r.interlock_error_count:>5} {r.io_coverage:>7.2f} {status:<6}"
            )
        print(sep)
        # 집계
        print(
            f"\n총 케이스: {summary['total_cases']}  "
            f"통과: {summary['passed_cases']}  "
            f"통과율: {summary['pass_rate']:.0%}"
        )
        print(
            f"이중코일 총 위반: {summary['total_double_coil_violations']}건  "
            f"인터락 총 위반: {summary['total_interlock_violations']}건"
        )

    all_passed = summary["pass_rate"] == 1.0
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
