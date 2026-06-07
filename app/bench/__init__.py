"""NL→명세 정확도 벤치마크 — "21개 밖에서 몇 %" 시금석 측정."""

from app.bench.design_accuracy import DesignBenchResult, score_design
from app.bench.nl_accuracy import BenchResult, score_keyless

__all__ = ["BenchResult", "DesignBenchResult", "score_design", "score_keyless"]
