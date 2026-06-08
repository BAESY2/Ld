"""수리 효능 회귀 가드 — 깨진 프로그램을 수리가 되살리고 잔존 실패 0."""

from __future__ import annotations


def test_repair_recovers_broken_programs() -> None:
    from scripts.repair_bench import run

    t = run()
    assert t["broken"] >= 6  # 표본이 공허하지 않음
    assert t["still_failing"] == 0  # 모든 깨진 표본이 수리되거나 정직 거절됨
    assert t["repaired"] >= t["broken"] - t["rejected"]  # 수리 가능분은 전부 통과
    assert t["repaired"] > 0
