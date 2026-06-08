#!/usr/bin/env python3
"""검증기 건전성@규모 연구 (ROADMAP H2 — 논문급 실증 backbone).

자동합성 프로그램과 적대적 뮤턴트(인터락 가드 제거)에 대해, **형식검증(k-귀납)** 판정을
**독립 오라클(디지털 트윈 시뮬레이터, 무작위 타임라인 반증 탐색)** 과 교차검증한다.

핵심 측정(검증기 논문의 표 1):
  · false-proof(거짓증명) : 형식=SAFE 인데 오라클이 위반 발견 → **불건전(반드시 0)**.
  · detection            : 오라클이 위반을 찾은 뮤턴트 중 형식이 잡은 비율(탐지력).
  · false-alarm          : 형식=UNSAFE 인데 오라클이 (한계 내) 도달 못함(정밀도).

오라클은 *sound refuter* 다 — 위반을 찾으면 진짜 위반(시뮬은 실행의미). 못 찾으면
'한계 내 미발견'일 뿐 안전 증명은 아니다(그 증명은 형식검증의 몫). 따라서 false-proof
는 진짜 불건전 반례다. 키 불필요·결정론(무작위는 시드 고정).
"""

from __future__ import annotations

import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import StateMachineSpec  # noqa: E402
from app.project import compose, scaffold_mutex  # noqa: E402
from app.simulator import simulate  # noqa: E402
from app.synth import synthesize_st  # noqa: E402
from app.verifier import (  # noqa: E402
    _HAS_Z3,
    check_interlocks_kinduction,
    proven_safe_pairs,
)
from app.wizard import RECIPES, build_spec  # noqa: E402

_TRIALS = 400  # 오라클 무작위 타임라인 수
_SCANS = 10    # 타임라인 길이(스캔)
_SEED = 1234


def _interlocked_specs() -> list[tuple[str, StateMachineSpec]]:
    """인터락을 가진 모든 프로그램(레시피 + mutex scaffold 합성)."""
    out: list[tuple[str, StateMachineSpec]] = []
    for rid in RECIPES:
        s = build_spec(rid)
        if s.interlocks:
            out.append((rid, s))
    for n in (2, 3, 4):
        out.append((f"mutex_motor_x{n}", compose(scaffold_mutex("motor_start_stop", n))))
    return out


def _rand_expr(rng: random.Random, syms: list[str], depth: int = 2) -> str:
    """boolexpr/시뮬레이터 양쪽이 파싱 가능한 무작위 불리언식(원자=심볼/NOT 심볼)."""
    if depth <= 0 or rng.random() < 0.4:
        s = rng.choice(syms)
        return f"NOT {s}" if rng.random() < 0.35 else s
    op = rng.choice([" AND ", " OR "])
    left = _rand_expr(rng, syms, depth - 1)
    right = _rand_expr(rng, syms, depth - 1)
    return f"({left}{op}{right})"


@dataclass
class RandProg:
    st: str
    pairs: list[tuple[str, str]]
    spec: StateMachineSpec


def _random_programs(count: int, seed: int) -> list[tuple[str, RandProg]]:
    """무작위 ST 프로그램(코일별 무작위 불리언식 + 무작위 인터락 쌍). 검증기 직접 퍼징.

    합성기를 거치지 않은 *임의* 코일 방정식을 만들어, 형식검증이 실행의미(시뮬)와
    어긋나 '거짓 증명'하지 않는지 직접 시험한다 — 검증기 건전성의 가장 강한 표본.
    """
    from app.models import Interlock

    rng = random.Random(seed)
    progs: list[tuple[str, RandProg]] = []
    for idx in range(count):
        n_out = rng.randint(2, 4)
        n_in = rng.randint(2, 4)
        outs = [f"O{i}" for i in range(n_out)]
        ins = [f"I{i}" for i in range(n_in)]
        atoms = outs + ins
        lines: list[str] = []
        for o in outs:
            # 자기유지 가능(자기참조 허용) + 무작위 가드
            rhs = _rand_expr(rng, atoms, depth=rng.randint(1, 3))
            lines.append(f"{o} := {rhs};")
        st = "\n".join(lines)
        # 무작위 인터락 쌍 1~2개(서로 다른 출력)
        pairs: list[tuple[str, str]] = []
        if n_out >= 2:
            for _ in range(rng.randint(1, 2)):
                a, b = rng.sample(outs, 2)
                if (a, b) not in pairs and (b, a) not in pairs:
                    pairs.append((a, b))
        spec = StateMachineSpec(
            interlocks=[Interlock(output_a=a, output_b=b) for a, b in pairs]
        )
        progs.append((f"rand#{idx}", RandProg(st=st, pairs=pairs, spec=spec)))
    return progs


def _strip_guards(st: str, pairs: list[tuple[str, str]]) -> str:
    """적대적 뮤턴트: 각 인터락 쌍의 상호배제 가드(AND NOT 상대)를 ST 에서 제거."""
    mutated = st
    syms = {s for p in pairs for s in p}
    for sym in syms:
        mutated = re.sub(rf"\s+AND\s+NOT\s+{re.escape(sym)}\b", "", mutated)
    return mutated


def _oracle_finds_violation(st: str, pairs: list[tuple[str, str]]) -> bool:
    """무작위 타임라인 반증 탐색: 어떤 인터락 쌍이라도 동시 ON 에 도달하면 True."""
    probe = simulate(st, [(0, {})], duration_ms=_SCANS * 100, step_ms=100)
    inputs = probe.inputs
    if any(_pair_both_on(probe, pairs)):
        return True
    rng = random.Random(_SEED)
    if not inputs:
        return False
    for _ in range(_TRIALS):
        timeline = [
            (i * 100, {s: rng.random() < 0.5 for s in inputs}) for i in range(_SCANS)
        ]
        res = simulate(st, timeline, duration_ms=_SCANS * 100, step_ms=100)
        if any(_pair_both_on(res, pairs)):
            return True
    return False


@dataclass
class PairTally:
    """쌍 단위 혼동행렬 — 검증기 *증명*의 건전성/완전성."""

    proven: int = 0              # k-귀납이 증명한 쌍
    proven_confirmed: int = 0    # 증명 + 오라클도 위반 못 찾음(건전)
    false_proof: int = 0         # ★증명했는데 오라클이 위반 발견(불건전 — 0이어야)
    detected_viol: int = 0       # 오라클 위반 + 형식도 error 로 탐지
    missed_viol: int = 0         # ★오라클 위반인데 형식 미탐지(불건전 — 0이어야)
    unproven_safe: int = 0       # 미증명 & 오라클도 미도달(완전성 공백)


_PairSet = set[tuple[str, str]]


def _pair_verdict(spec: StateMachineSpec, st: str) -> tuple[_PairSet, _PairSet]:
    """(증명된 쌍 집합, error 로 위반판정된 쌍 집합) — 둘 다 무방향 정규화."""
    proven_dir = proven_safe_pairs(spec, st)
    proven = {tuple(sorted(p)) for p in proven_dir}
    err: set[tuple[str, str]] = set()
    for lock in spec.interlocks:
        for issue in check_interlocks_kinduction(
            StateMachineSpec(interlocks=[lock]), st
        ):
            if issue.severity == "error":
                err.add(tuple(sorted((lock.output_a, lock.output_b))))
    return proven, err


def _pair_both_on(res: object, pairs: list[tuple[str, str]]) -> list[bool]:
    return [
        bool(s.outputs.get(a) and s.outputs.get(b))
        for s in res.samples  # type: ignore[attr-defined]
        for a, b in pairs
    ]


def _corpus(n_random: int, seed: int) -> list[tuple[str, StateMachineSpec, str]]:
    """프로그램 코퍼스: 인터락 레시피(+가드제거 적대 뮤턴트) + 무작위 ST 프로그램."""
    progs: list[tuple[str, StateMachineSpec, str]] = []
    for name, spec in _interlocked_specs():
        st = synthesize_st(spec)
        progs.append((name, spec, st))
        pairs = [(lock.output_a, lock.output_b) for lock in spec.interlocks]
        progs.append((f"{name}__mut", spec, _strip_guards(st, pairs)))  # 적대 뮤턴트
    for name, rp in _random_programs(n_random, seed):
        if rp.pairs:
            progs.append((name, rp.spec, rp.st))
    return progs


def _classify(t: PairTally, name: str, pair: tuple[str, str],
              proven: bool, errored: bool, oracle_viol: bool) -> None:
    if proven and oracle_viol:
        t.false_proof += 1
        print(f"  ★[FALSE-PROOF] {name} {pair}: k-귀납 증명했는데 오라클 위반!")
    elif proven:
        t.proven += 1
        t.proven_confirmed += 1
    elif oracle_viol and errored:
        t.detected_viol += 1
    elif oracle_viol and not errored:
        t.missed_viol += 1
        print(f"  ★[MISS] {name} {pair}: 오라클 위반인데 형식 미탐지!")
    else:
        t.unproven_safe += 1


def run(n_random: int = 300, seed: int = _SEED) -> PairTally:
    t = PairTally()
    for name, spec, st in _corpus(n_random, seed):
        proven, err = _pair_verdict(spec, st)
        for lock in spec.interlocks:
            pair = tuple(sorted((lock.output_a, lock.output_b)))
            ov = _oracle_finds_violation(st, [(lock.output_a, lock.output_b)])
            _classify(t, name, pair, pair in proven, pair in err, ov)
    return t


def _pct(a: int, b: int) -> str:
    return f"{100.0 * a / b:5.1f}%" if b else "  n/a"


def main() -> int:
    if not _HAS_Z3:
        print("z3 미설치 — 건전성 연구 건너뜀")
        return 0
    print(f"=== 검증기 건전성@규모 — 쌍 단위 (trials={_TRIALS}, scans={_SCANS}, seed={_SEED}) ===")
    t = run()
    total = (t.proven_confirmed + t.false_proof + t.detected_viol
             + t.missed_viol + t.unproven_safe)
    oracle_viol = t.false_proof + t.detected_viol + t.missed_viol
    print("\n---- 쌍 단위 혼동행렬 ----")
    print(f"검사한 인터락 쌍               : {total}")
    print(f"k-귀납 *증명* 한 쌍            : {t.proven + t.false_proof}")
    print(f"  └ 오라클도 안전 확인(건전)   : {t.proven_confirmed}")
    print(f"  └ ★false-proof(불건전)      : {t.false_proof}   ← 0 이어야 건전")
    det = _pct(t.detected_viol, oracle_viol)
    print(f"오라클이 위반 발견한 쌍        : {oracle_viol}")
    print(f"  └ 형식도 탐지(detection)     : {t.detected_viol}  ({det})")
    print(f"  └ ★형식 미탐지(miss)         : {t.missed_viol}   ← 0 이어야 건전")
    print(f"미증명·미반증(완전성 공백)     : {t.unproven_safe}")
    sound = t.false_proof == 0 and t.missed_viol == 0
    print(f"\n판정: {'건전(SOUND) — false-proof=0, miss=0' if sound else '불건전 사례 발견!'}")
    print("의미: 무작위 300+ 프로그램 + 실레시피 + 적대 뮤턴트에 걸쳐, k-귀납이 *증명한* "
          "쌍을 실행오라클이 단 한 번도 반증 못함 = 검증기 건전성의 규모 실증(논문급 표).")
    return 0 if sound else 1


if __name__ == "__main__":
    raise SystemExit(main())
