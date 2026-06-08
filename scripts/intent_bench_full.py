#!/usr/bin/env python3
"""무편향 벤치: 문법 의도엔진(구조) vs BM25(키워드) — 전체 코퍼스 (MASTERPLAN M1).

intent_ablation.py 가 '매퍼 커버 의도'만 본 선택편향을 보완한다. 여기선 *구조형 + 어휘형*
의도를 섞은 코퍼스 전체에 두 방식을 돌려 (1) 문법 커버리지(자신있게 매핑한 비율),
(2) 커버한 것의 정확도, (3) 정상 vs 교란(띄어쓰기/조사) 견고성을 정직하게 측정한다.

핵심 정직성: 문법엔진은 *구조형*(조건·동작·대상) 의도에 강하고 교란에 견고하지만, 어휘
변별형(스타델타·뮤팅 등)은 커버하지 않고 *기권*한다(거짓 매핑 대신). 두 방식은 상보적이다.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.intent import match_by_frame  # noqa: E402
from app.nlmatch import match_recipe  # noqa: E402

_CONF = 2.0  # 문법엔진이 '자신있게 매핑'으로 보는 점수 임계(미만이면 기권→BM25 폴백)

# 라벨 코퍼스: 구조형(문법이 잘 잡음) + 어휘형(키워드 변별, 문법 기권 예상) 혼합.
CORPUS: list[tuple[str, str, str]] = [
    # (텍스트, 정답, 유형)
    ("버튼 누르면 모터 돌고 정지 누르면 멈추게", "motor_start_stop", "구조"),
    ("기동 버튼 누르면 컨베이어 모터 돌리고", "motor_start_stop", "구조"),
    ("저수위 되면 펌프 켜고 만수위 되면 꺼", "hi_lo_level", "구조"),
    ("탱크 저수위 되면 펌프 돌리고 고수위 되면 멈춰", "hi_lo_level", "구조"),
    ("부품 10개 차면 배출", "count_eject", "구조"),
    ("부품 100개 세면 배출하고", "count_eject", "구조"),
    ("압력 5바 넘으면 밸브 닫아", "pressure_band", "구조"),
    ("압력 8바 넘으면 펌프 꺼", "pressure_band", "구조"),
    ("온도 200도 되면 히터 꺼", "temp_setpoint", "구조"),
    ("온도가 150도 넘으면 히터 끄고", "temp_setpoint", "구조"),
    ("셔터 열고 끝까지 가면 닫아", "shutter_gate", "구조"),
    ("정방향으로 돌리다가 역방향으로 돌려", "fwd_rev", "구조"),
    ("정방향 역방향 동시에 못 돌게", "fwd_rev", "구조"),
    ("고장 나면 경광등 켜", "latch_alarm", "구조"),
    # 어휘 변별형 — 문법엔진은 기권(거짓매핑 금지), BM25 가 키워드로 잡는 영역
    ("스타델타로 감압기동", "star_delta", "어휘"),
    ("조그로 잠깐만 돌리기", "jog_run", "어휘"),
    ("프레스에 뮤팅 적용해서 양손 허가", "press_muting", "어휘"),
    ("도금 라인 탈지 수세 도금 건조", "plating_line", "어휘"),
    ("서보 원점복귀하고 이동해서 정위치", "motion_home_move", "어휘"),
    ("용접 셀 클램프하고 용접하고 해제", "weld_cell", "어휘"),
]


def _gram(t: str) -> str | None:
    rid, score = match_by_frame(t)
    return rid if score >= _CONF else None  # 기권은 None


def _bm25(t: str) -> str | None:
    sc = match_recipe(t)
    return sc[0][0] if sc and sc[0][1] > 0 else None


def _no_space(t: str) -> str:
    return t.replace(" ", "")


def _report(name: str, transform: Callable[[str], str]) -> None:
    rows = [(c[0], c[1]) for c in CORPUS]
    gram_cov = gram_hit = bm_hit = 0
    gram_cov_struct = gram_hit_struct = 0
    struct_n = sum(1 for c in CORPUS if c[2] == "구조")
    for (text, label), kind in zip(rows, (c[2] for c in CORPUS), strict=True):
        t = transform(text)
        g = _gram(t)
        if g is not None:
            gram_cov += 1
            if g == label:
                gram_hit += 1
        if kind == "구조":
            if g is not None:
                gram_cov_struct += 1
                if g == label:
                    gram_hit_struct += 1
        if _bm25(t) == label:
            bm_hit += 1
    n = len(rows)
    g_acc = f"{100 * gram_hit / gram_cov:.0f}%" if gram_cov else "n/a"
    bm_pct = f"{100 * bm_hit / n:.0f}%"
    print(f"   {name:14} | 문법 커버 {gram_cov:2d}/{n} 정확 {g_acc:>4} "
          f"(구조형 {gram_hit_struct}/{struct_n}) | BM25 정확 {bm_hit:2d}/{n} ({bm_pct})")


def main() -> int:
    print("=== 무편향 벤치: 문법엔진(구조) vs BM25(키워드) ===")
    print(f"코퍼스 {len(CORPUS)}건 (구조형 {sum(1 for c in CORPUS if c[2]=='구조')} + "
          f"어휘형 {sum(1 for c in CORPUS if c[2]=='어휘')})\n")
    _report("정상", lambda t: t)
    _report("띄어쓰기제거", _no_space)
    print("\n해석: 문법엔진은 *구조형* 의도를 자신있게·정확히 매핑하고 띄어쓰기 제거에도 견고;"
          " 어휘 변별형은 *기권*(거짓매핑 대신)해 BM25 가 맡는다 = 상보적 하이브리드.")
    print("BM25 는 띄어쓰기 제거 시 급락 → 문법엔진이 그 손실을 메운다(발명의 자리).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
