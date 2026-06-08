#!/usr/bin/env python3
"""타임드 시퀀서 one-hot 안전성 *독립* 대규모 검증 벤치 (디지털 트윈 시뮬레이터).

컴파일러(frame_to_spec)가 '다음/그다음/순서대로/N초 후' 시퀀스 마커로 합성하는
*타임드 시퀀서* — N단계 출력을 시간차로 하나씩 켜는 상태머신 — 가 실행 중 *동시에
두 단계 이상 ON 되지 않음*(one-hot / at-most-one)을 검증기(Z3 k-귀납)와 **독립적으로**
디지털 트윈 시뮬레이터로 대규모 검증한다. 검증기가 "안전하다"고 말한 것을, 실제 PLC
스캔 의미론으로 가동해 *반례를 못 찾는지* 교차확인하는 것이다(자가채점 아님).

파이프라인(키 불필요·결정론·시드 고정):
    한국어 시퀀스 지시 → frame_to_spec → synthesize_st →
    무작위/스윕 START·STOP 입력 타임라인으로 simulate →
    매 스캔에서 단계 출력 중 ON 개수 ≤ 1 검사(one-hot).

핵심 안전속성:
  (1) one-hot 보존  : 모든 케이스·모든 입력 타임라인·모든 스캔에서 동시 ON ≤ 1 (위반 0).
  (2) 비공허성      : 시퀀스가 실제로 단계를 거친다(각 단계가 적어도 한 입력에서 ON 도달).

위반이 있으면 케이스 텍스트·시각(t_ms)·동시 ON 출력 목록을 보고한다.
이 속성들은 tests/test_sequencer_safety.py 가 대표 시퀀서에 대해 단정한다.
"""

from __future__ import annotations

import hashlib
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.compile_frame import frame_to_spec  # noqa: E402
from app.memory_map import detect_double_coils  # noqa: E402
from app.simulator import SimResult, simulate  # noqa: E402
from app.synth import synthesize_st  # noqa: E402

# 출력 액추에이터 기기(서로 다른 출력 심볼로 컴파일되는 것들 — 중복 출력은 시퀀스 부적합).
_DEVICES: tuple[str, ...] = (
    "모터", "펌프", "밸브", "히터", "컨베이어", "송풍기", "팬", "램프", "부저",
    "사이렌", "로봇", "드릴", "클램프", "노즐", "쿨러", "압축기", "도어", "셔터",
    "호퍼", "피더",
)
# 각 기기에 어울리는 동작 술어(켜기/돌리기/열기 류 — 단계 출력 ON).
_VERBS: dict[str, tuple[str, ...]] = {
    "모터": ("돌리고", "돌려"),
    "펌프": ("켜고", "켜"),
    "밸브": ("열고", "열어"),
    "도어": ("열고", "열어"),
    "셔터": ("열고", "열어"),
}
_DEFAULT_VERBS: tuple[str, ...] = ("켜고", "켜")
# 단계 사이 진행 마커(순차/타이밍 혼합). N초 후는 그 단계로의 지연 프리셋이 된다.
_SEQ_JOINS: tuple[str, ...] = ("다음", "그다음", "순서대로")
_DELAY_JOINS: tuple[str, ...] = ("1초 후", "2초 후", "3초 후", "2초 뒤")


def _verb(rng: random.Random, dev: str, *, last: bool) -> str:
    """기기에 맞는 동작 술어. 마지막 단계는 종결형('켜')도 섞어 문장이 끝나게 한다."""
    cands = _VERBS.get(dev, _DEFAULT_VERBS)
    # 종결형은 보통 두 번째(리스트의 [1]), 비종결('-고')은 [0].
    return cands[1] if (last and len(cands) > 1 and rng.random() < 0.5) else cands[0]


def _generate_texts(rng: random.Random, n: int) -> list[str]:
    """2~5단계 시퀀스 한국어 지시를 n건 생성한다(기기 중복 없음·결정론).

    각 단계는 '기기 동작' + (마지막 아니면) 진행 마커(다음/그다음/순서대로/N초 후).
    'N초 후' 마커는 타임드 지연을 섞어 순차+타이밍 조합을 시험한다.
    """
    texts: list[str] = []
    for _ in range(n):
        n_steps = rng.randint(2, 5)
        devs = rng.sample(_DEVICES, n_steps)  # 중복 없는 출력 → 시퀀스 적합
        parts: list[str] = []
        for i, dev in enumerate(devs):
            last = i == n_steps - 1
            parts.append(f"{dev} {_verb(rng, dev, last=last)}")
            if not last:
                # 순차 마커 또는 'N초 후' 지연 마커를 섞는다.
                if rng.random() < 0.5:
                    parts.append(rng.choice(_SEQ_JOINS))
                else:
                    parts.append(rng.choice(_DELAY_JOINS))
        texts.append(" ".join(parts))
    return texts


def _input_timelines(
    rng: random.Random, n_random: int, max_t: int
) -> list[list[tuple[int, dict[str, bool]]]]:
    """START/STOP 입력 타임라인 모음 — 스윕(결정론) + 무작위(시드 고정).

    one-hot 은 입력과 무관하게 보존되어야 하므로, 다양한 START/STOP 패턴을 던진다:
      - START 짧은 펄스(정상 기동), START 계속 유지(재기동 압박),
      - 중간 STOP, 중간 재START, 마구잡이 토글.
    """
    sweeps: list[list[tuple[int, dict[str, bool]]]] = [
        [(0, {"START": True, "STOP": False}), (300, {"START": False})],  # 짧은 펄스
        [(0, {"START": True, "STOP": False})],                            # 계속 유지
        [(0, {"START": True, "STOP": False}), (300, {"START": False}),
         (max_t // 2, {"STOP": True}), (max_t // 2 + 300, {"STOP": False})],  # 중간 정지
        [(0, {"START": True, "STOP": False}), (300, {"START": False}),
         (max_t // 3, {"START": True}), (max_t // 3 + 300, {"START": False})],  # 재기동
    ]
    randoms: list[list[tuple[int, dict[str, bool]]]] = []
    for _ in range(n_random):
        tl: list[tuple[int, dict[str, bool]]] = []
        t = 0
        while t <= max_t:
            tl.append((t, {"START": rng.random() < 0.5, "STOP": rng.random() < 0.2}))
            t += rng.choice((100, 200, 300, 500))
        randoms.append(tl)
    return sweeps + randoms


@dataclass
class Violation:
    """one-hot 위반 한 건(케이스·시각·동시 ON 출력)."""

    text: str
    t_ms: int
    outputs_on: list[str]


@dataclass
class CaseReport:
    """한 시퀀서 케이스의 one-hot/비공허성 결과."""

    text: str
    n_steps: int
    outputs: list[str]
    timers: int
    scans_checked: int = 0
    timelines: int = 0
    max_simul: int = 0  # 전 타임라인에서 본 최대 동시 ON
    reached: dict[str, bool] = field(default_factory=dict)
    violations: list[Violation] = field(default_factory=list)

    @property
    def one_hot_ok(self) -> bool:
        return self.max_simul <= 1 and not self.violations

    @property
    def all_steps_reached(self) -> bool:
        return bool(self.outputs) and all(self.reached.get(o, False) for o in self.outputs)


def _step_duration_ms(timers_preset: list[int]) -> int:
    """전체 시퀀스를 끝까지 거치기에 충분한 가동 시간(여유 포함)."""
    # 각 단계 타이머 합 + 마지막 기본 드웰 + 스캔 여유.
    return sum(timers_preset) + 4000


def evaluate_case(
    text: str, rng: random.Random, *, n_random: int = 6
) -> CaseReport | None:
    """한 시퀀스 지시를 컴파일→합성→여러 입력 타임라인 시뮬→one-hot/도달성 검사.

    confident 컴파일이 아니거나 시퀀서(타이머≥2·출력≥2)가 아니면 None(검사 대상 아님).
    """
    r = frame_to_spec(text)
    outputs = [p.symbol for p in r.spec.io_points if p.direction.value == "OUTPUT"]
    if not r.confident or len(outputs) < 2 or len(r.spec.timers) < 2:
        return None
    st = synthesize_st(r.spec)
    presets = [t.preset_ms for t in r.spec.timers]
    max_t = _step_duration_ms(presets)
    rep = CaseReport(
        text=text, n_steps=len(outputs), outputs=outputs, timers=len(r.spec.timers),
        reached={o: False for o in outputs},
    )
    for tl in _input_timelines(rng, n_random, max_t):
        res: SimResult = simulate(st, tl, duration_ms=max_t, step_ms=100)
        rep.timelines += 1
        rep.scans_checked += len(res.samples)
        for s in res.samples:
            on = [o for o in outputs if s.outputs.get(o, False)]
            rep.max_simul = max(rep.max_simul, len(on))
            if len(on) > 1:
                rep.violations.append(Violation(text=text, t_ms=s.t_ms, outputs_on=on))
        for o in outputs:
            if any(res.output_trace(o)):
                rep.reached[o] = True
    # 이중코일도 곁다리 확인(스캔 결정론 전제).
    assert detect_double_coils(st) == {}, f"이중코일 발생: {text}"
    return rep


@dataclass
class BenchResult:
    """벤치 전체 집계."""

    reports: list[CaseReport]
    generated: int
    skipped: int

    @property
    def total_violations(self) -> int:
        return sum(len(r.violations) for r in self.reports)

    @property
    def total_scans(self) -> int:
        return sum(r.scans_checked for r in self.reports)

    @property
    def all_one_hot(self) -> bool:
        return all(r.one_hot_ok for r in self.reports)

    @property
    def all_steps_reached(self) -> bool:
        return all(r.all_steps_reached for r in self.reports)


def run(*, seed: int = 20260608, n_cases: int = 30) -> BenchResult:
    """시드 고정 결정론 벤치 — n_cases건의 시퀀스를 생성·검증한다."""
    rng = random.Random(seed)
    texts = _generate_texts(rng, n_cases)
    reports: list[CaseReport] = []
    skipped = 0
    for text in texts:
        # 케이스별 입력 RNG는 본문 시드 + 안정 해시(blake2b)로 파생 — 프로세스 간
        # 재현되도록 내장 hash() 대신 해시함수를 쓴다(PYTHONHASHSEED 무관, 결정론).
        digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
        case_rng = random.Random(seed ^ int.from_bytes(digest, "big"))
        rep = evaluate_case(text, case_rng)
        if rep is None:
            skipped += 1
            continue
        reports.append(rep)
    return BenchResult(reports=reports, generated=len(texts), skipped=skipped)


def format_report(res: BenchResult) -> str:
    """정직한 결론 텍스트를 포함한 표를 만든다."""
    lines: list[str] = []
    lines.append("=== 타임드 시퀀서 one-hot 안전성 독립 검증 (디지털 트윈) ===")
    header = (
        f"{'단계':>3} {'출력심볼':<30} {'타임라인':>6} {'스캔':>7} "
        f"{'최대동시ON':>9} {'단계도달':>8}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for r in sorted(res.reports, key=lambda x: (x.n_steps, x.text)):
        outs = ",".join(r.outputs)
        if len(outs) > 29:
            outs = outs[:26] + "..."
        reach = "전부" if r.all_steps_reached else "미달"
        lines.append(
            f"{r.n_steps:>3} {outs:<30} {r.timelines:>6} {r.scans_checked:>7} "
            f"{r.max_simul:>9} {reach:>8}"
        )
    lines.append("-" * len(header))
    lines.append(
        f"검사 시퀀서 {len(res.reports)}건 (생성 {res.generated} · 비대상 {res.skipped}) · "
        f"총 스캔 {res.total_scans} · one-hot 위반 {res.total_violations}"
    )
    lines.append("")
    lines.append("정직한 결론:")
    if res.all_one_hot:
        lines.append(
            "  - one-hot 보존: 모든 케이스·모든 입력 타임라인·모든 스캔에서 동시 ON <= 1."
        )
        lines.append(
            "    (검증기 Z3 결과와 독립적으로 디지털 트윈이 반례를 못 찾음 = 교차확인.)"
        )
    else:
        lines.append(f"  - [경고] one-hot 위반 {res.total_violations}건 — 즉시 점검:")
        for r in res.reports:
            for v in r.violations[:3]:
                lines.append(f"      {v.text!r} @ {v.t_ms}ms: {', '.join(v.outputs_on)}")
    if res.all_steps_reached:
        lines.append("  - 비공허성: 모든 시퀀서가 단계를 실제로 거친다(각 단계 ON 도달).")
    else:
        lines.append("  - [경고] 일부 시퀀서가 단계에 도달하지 못함(공허한 통과 위험):")
        for r in res.reports:
            if not r.all_steps_reached:
                miss = [o for o in r.outputs if not r.reached.get(o)]
                lines.append(f"      {r.text!r}: 미도달 {', '.join(miss)}")
    lines.append("")
    lines.append("한계(정직):")
    lines.append("  - 검사 대상은 출력>=2·타이머>=2 인 *타임드 시퀀서*뿐(자기유지 단일출력 제외).")
    lines.append("  - 입력 타임라인은 스윕+무작위 표본 — 전수증명이 아니다(증명은 Z3 k-귀납이")
    lines.append("    담당; 이 벤치는 그 증명에 대한 *독립적 반례탐색* 역할).")
    return "\n".join(lines)


def main() -> int:
    res = run()
    print(format_report(res))
    # 안전속성 위반 시 비정상 종료(CI 가드).
    if not res.all_one_hot or not res.all_steps_reached or not res.reports:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
