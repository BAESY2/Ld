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
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import StateMachineSpec  # noqa: E402
from app.project import compose, scaffold_mutex  # noqa: E402
from app.simulator import simulate  # noqa: E402
from app.synth import synthesize_st  # noqa: E402
from app.verifier import (  # noqa: E402
    _HAS_Z3,
    check_group_mutex_kinduction,
    check_interlocks_kinduction,
    derive_mutex_groups,
    proven_safe_groups,
    proven_safe_pairs,
)
from app.wizard import RECIPES, build_spec  # noqa: E402

_TRIALS = 400      # 오라클 무작위 타임라인 수
_SCANS = 10        # 타임라인 길이(스캔)
_SEED = 1234
_N_RANDOM = 1000   # 무작위 프로그램 기본 수(규모 — 건전성을 규모로 재실증)


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
    groups: list[list[str]]  # ≥3 출력 one-hot 그룹(있으면 clique 인터락으로 선언)


def _random_programs(count: int, seed: int) -> list[tuple[str, RandProg]]:
    """무작위 ST 프로그램(코일별 무작위 불리언식 + 무작위 인터락 쌍). 검증기 직접 퍼징.

    합성기를 거치지 않은 *임의* 코일 방정식을 만들어, 형식검증이 실행의미(시뮬)와
    어긋나 '거짓 증명'하지 않는지 직접 시험한다 — 검증기 건전성의 가장 강한 표본.
    """
    from app.models import Interlock

    rng = random.Random(seed)
    progs: list[tuple[str, RandProg]] = []
    for idx in range(count):
        # 그룹(≥3 출력 one-hot) 교란을 위해 출력 3~5개도 자주 만든다.
        n_out = rng.randint(2, 5)
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
        # 출력이 3개 이상이면 절반 확률로 3개를 골라 one-hot clique 그룹으로 선언한다
        # (모든 쌍을 인터락으로 박아 derive_mutex_groups 가 그룹으로 잡도록). 코일식은
        # 여전히 무작위라 대개 미증명/위반 — 그룹 검사의 건전성을 임의 로직으로 시험.
        groups: list[list[str]] = []
        if n_out >= 3 and rng.random() < 0.5:
            g = sorted(rng.sample(outs, 3))
            groups.append(g)
            for i in range(3):
                for j in range(i + 1, 3):
                    a, b = g[i], g[j]
                    if (a, b) not in pairs and (b, a) not in pairs:
                        pairs.append((a, b))
        spec = StateMachineSpec(
            interlocks=[Interlock(output_a=a, output_b=b) for a, b in pairs]
        )
        progs.append(
            (f"rand#{idx}", RandProg(st=st, pairs=pairs, spec=spec, groups=groups))
        )
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
    return _oracle_search(st, lambda res: any(_pair_both_on(res, pairs)))


def _oracle_finds_group_violation(st: str, group: list[str]) -> bool:
    """무작위 타임라인 반증 탐색: 그룹 내 둘 이상이 동시에 ON 인 스캔에 도달하면 True."""
    return _oracle_search(st, lambda res: _group_two_on(res, group))


def _oracle_search(st: str, hit: Callable[[object], bool]) -> bool:
    """공통 반증 탐색: 무입력 프로브 + 무작위 타임라인 _TRIALS 회. hit(res)->bool."""
    probe = simulate(st, [(0, {})], duration_ms=_SCANS * 100, step_ms=100)
    inputs = probe.inputs
    if hit(probe):
        return True
    rng = random.Random(_SEED)
    if not inputs:
        return False
    for _ in range(_TRIALS):
        timeline = [
            (i * 100, {s: rng.random() < 0.5 for s in inputs}) for i in range(_SCANS)
        ]
        res = simulate(st, timeline, duration_ms=_SCANS * 100, step_ms=100)
        if hit(res):
            return True
    return False


def _group_two_on(res: object, group: list[str]) -> bool:
    """어떤 스캔 샘플에서든 그룹 내 ON 출력이 2개 이상이면 True(at-most-one 위반)."""
    for s in res.samples:  # type: ignore[attr-defined]
        if sum(1 for g in group if s.outputs.get(g)) >= 2:
            return True
    return False


@dataclass
class PairTally:
    """쌍 단위 혼동행렬 — 검증기 *증명*의 건전성/완전성."""

    proven: int = 0              # k-귀납이 증명한 쌍
    proven_confirmed: int = 0    # 증명 + 오라클도 위반 못 찾음(건전)
    false_proof: int = 0         # ★증명했는데 오라클이 위반 발견(불건전 — 0이어야)
    detected_viol: int = 0       # 오라클 위반 + 형식도 error/warning 으로 깃발(탐지)
    warned_viol: int = 0         # 오라클 위반 + 형식은 보수적 warning(미증명, 침묵 아님)
    missed_viol: int = 0         # ★오라클 위반인데 형식이 완전 침묵(불건전 — 0이어야)
    unproven_safe: int = 0       # 미증명 & 오라클도 미도달(완전성 공백)


@dataclass
class GroupTally:
    """그룹(one-hot / at-most-one) 단위 혼동행렬 — 검증기 *그룹 증명*의 건전성/완전성."""

    proven_confirmed: int = 0    # at-most-one 증명 + 오라클도 위반 못 찾음(건전)
    false_proof: int = 0         # ★증명했는데 오라클이 둘 이상 동시 ON 발견(불건전 — 0이어야)
    detected_viol: int = 0       # 오라클 위반 + 형식도 error/warning 으로 깃발(탐지)
    warned_viol: int = 0         # 오라클 위반 + 형식은 보수적 warning(미증명, 침묵 아님)
    missed_viol: int = 0         # ★오라클 위반인데 형식이 완전 침묵(불건전 — 0이어야)
    unproven_safe: int = 0       # 미증명 & 오라클도 미도달(완전성 공백)


_PairSet = set[tuple[str, str]]


def _pair_verdict(
    spec: StateMachineSpec, st: str
) -> tuple[_PairSet, _PairSet, _PairSet]:
    """(증명된 쌍, error 위반쌍, warning(보수적 미증명) 쌍) — 모두 무방향 정규화.

    warning 은 *침묵 통과가 아니다* — k-귀납이 작은 k 로 증명하지 못했으나 base 는
    안전이라 "안전 미보장, k 상향/시뮬 확인 필요" 라고 명시 깃발을 든 경우다. 따라서
    오라클이 (긴 지평에서) 찾은 위반을 verifier 가 warning 한 건 침묵실패(miss)가 아니라
    완전성 공백이다. 진짜 불건전(miss)은 verifier 가 *아무 신호도 없이* 통과한 경우뿐.
    """
    proven_dir = proven_safe_pairs(spec, st)
    proven: set[tuple[str, str]] = {(a, b) for a, b in (sorted(p) for p in proven_dir)}
    err: set[tuple[str, str]] = set()
    warned: set[tuple[str, str]] = set()
    for lock in spec.interlocks:
        key: tuple[str, str] = tuple(sorted((lock.output_a, lock.output_b)))  # type: ignore[assignment]
        for issue in check_interlocks_kinduction(
            StateMachineSpec(interlocks=[lock]), st
        ):
            if issue.severity == "error":
                err.add(key)
            elif issue.severity == "warning":
                warned.add(key)
    return proven, err, warned


def _group_verdict(
    spec: StateMachineSpec, st: str, groups: list[list[str]]
) -> tuple[list[list[str]], list[list[str]], list[list[str]]]:
    """(증명 그룹, GROUP_MUTEX error 그룹, GROUP_MUTEX_KIND warning 그룹) — 정렬 정규화.

    groups 가 비면 spec.interlocks 의 clique 합집합에서 유도한다(derive_mutex_groups).
    warning 은 쌍 검사와 같은 의미(보수적 미증명, 침묵 아님)이며 miss 로 세지 않는다.
    """
    use = groups or derive_mutex_groups(spec)
    proven = [sorted(g) for g in proven_safe_groups(spec, st, groups=use or None)]
    err: list[list[str]] = []
    warned: list[list[str]] = []
    for g in use:
        issues = check_group_mutex_kinduction(spec, st, groups=[g])
        if any(i.code == "GROUP_MUTEX" and i.severity == "error" for i in issues):
            err.append(sorted(g))
        elif any(i.severity == "warning" for i in issues):
            warned.append(sorted(g))
    return proven, err, warned


def _pair_both_on(res: object, pairs: list[tuple[str, str]]) -> list[bool]:
    return [
        bool(s.outputs.get(a) and s.outputs.get(b))
        for s in res.samples  # type: ignore[attr-defined]
        for a, b in pairs
    ]


@dataclass
class _Prog:
    name: str
    spec: StateMachineSpec
    st: str
    groups: list[list[str]]  # 검사 대상 명시 그룹(비면 인터락 clique 에서 유도)


def _corpus(n_random: int, seed: int) -> list[_Prog]:
    """프로그램 코퍼스: 인터락 레시피(+가드제거 적대 뮤턴트) + 무작위 ST 프로그램.

    레시피의 그룹은 derive_mutex_groups 로 유도(multiway_sort 의 GATE_A/B/C 등). 적대
    뮤턴트는 가드를 제거해 쌍·그룹 양쪽 상호배제를 모두 깨뜨린다. 무작위 프로그램은
    명시 one-hot clique 그룹을 절반 포함해 임의 코일식으로 그룹 검사를 교란한다.
    """
    progs: list[_Prog] = []
    for name, spec in _interlocked_specs():
        st = synthesize_st(spec)
        progs.append(_Prog(name, spec, st, derive_mutex_groups(spec)))
        pairs = [(lock.output_a, lock.output_b) for lock in spec.interlocks]
        mut = _strip_guards(st, pairs)
        progs.append(_Prog(f"{name}__mut", spec, mut, derive_mutex_groups(spec)))
    for name, rp in _random_programs(n_random, seed):
        if rp.pairs or rp.groups:
            progs.append(_Prog(name, rp.spec, rp.st, rp.groups))
    return progs


def _classify(t: PairTally, name: str, pair: tuple[str, str],
              proven: bool, errored: bool, warned: bool, oracle_viol: bool) -> None:
    if proven and oracle_viol:
        t.false_proof += 1
        print(f"  ★[FALSE-PROOF] {name} {pair}: k-귀납 증명했는데 오라클 위반!")
    elif proven:
        t.proven += 1
        t.proven_confirmed += 1
    elif oracle_viol and errored:
        t.detected_viol += 1
    elif oracle_viol and warned:
        t.warned_viol += 1  # 보수적 warning(침묵 아님) — 완전성 공백, 건전성 유지
    elif oracle_viol:
        t.missed_viol += 1  # 형식이 완전 침묵 — 진짜 불건전
        print(f"  ★[MISS] {name} {pair}: 오라클 위반인데 형식 *완전 침묵*!")
    else:
        t.unproven_safe += 1


def _classify_group(g: GroupTally, name: str, group: list[str],
                    proven: bool, errored: bool, warned: bool, oracle_viol: bool) -> None:
    label = "{" + ", ".join(group) + "}"
    if proven and oracle_viol:
        g.false_proof += 1
        print(f"  ★[GROUP FALSE-PROOF] {name} {label}: at-most-one 증명했는데 오라클 위반!")
    elif proven:
        g.proven_confirmed += 1
    elif oracle_viol and errored:
        g.detected_viol += 1
    elif oracle_viol and warned:
        g.warned_viol += 1
    elif oracle_viol:
        g.missed_viol += 1
        print(f"  ★[GROUP MISS] {name} {label}: 오라클 그룹위반인데 형식 *완전 침묵*!")
    else:
        g.unproven_safe += 1


def run_full(
    n_random: int = _N_RANDOM, seed: int = _SEED
) -> tuple[PairTally, GroupTally]:
    """쌍·그룹 두 혼동행렬을 한 번에 채운다(코퍼스 1회 순회 — 합성 비용 공유)."""
    pt = PairTally()
    gt = GroupTally()
    for prog in _corpus(n_random, seed):
        proven_p, err_p, warn_p = _pair_verdict(prog.spec, prog.st)
        for lock in prog.spec.interlocks:
            pair: tuple[str, str] = tuple(sorted((lock.output_a, lock.output_b)))  # type: ignore[assignment]
            ov = _oracle_finds_violation(prog.st, [(lock.output_a, lock.output_b)])
            _classify(pt, prog.name, pair, pair in proven_p, pair in err_p,
                      pair in warn_p, ov)
        if prog.groups:
            proven_g, err_g, warn_g = _group_verdict(prog.spec, prog.st, prog.groups)
            proven_set = {tuple(g) for g in proven_g}
            err_set = {tuple(g) for g in err_g}
            warn_set = {tuple(g) for g in warn_g}
            for group in prog.groups:
                key = tuple(sorted(group))
                gv = _oracle_finds_group_violation(prog.st, group)
                _classify_group(gt, prog.name, sorted(group), key in proven_set,
                                key in err_set, key in warn_set, gv)
    return pt, gt


def run(n_random: int = 300, seed: int = _SEED) -> PairTally:
    """쌍 단위 결과만 — 기존 호출자/테스트 호환(작은 규모 빠른 경로)."""
    return run_full(n_random=n_random, seed=seed)[0]


def _pct(a: int, b: int) -> str:
    return f"{100.0 * a / b:5.1f}%" if b else "  n/a"


def main() -> int:
    if not _HAS_Z3:
        print("z3 미설치 — 건전성 연구 건너뜀")
        return 0
    print(f"=== 검증기 건전성@규모 (random={_N_RANDOM}, trials={_TRIALS}, "
          f"scans={_SCANS}, seed={_SEED}) ===")
    t, g = run_full()

    total = (t.proven_confirmed + t.false_proof + t.detected_viol
             + t.warned_viol + t.missed_viol + t.unproven_safe)
    oracle_viol = t.false_proof + t.detected_viol + t.warned_viol + t.missed_viol
    print("\n---- 쌍 단위 혼동행렬 (인터락 쌍 at-most-one) ----")
    print(f"검사한 인터락 쌍               : {total}")
    print(f"k-귀납 *증명* 한 쌍            : {t.proven + t.false_proof}")
    print(f"  └ 오라클도 안전 확인(건전)   : {t.proven_confirmed}")
    print(f"  └ ★false-proof(불건전)      : {t.false_proof}   ← 0 이어야 건전")
    print(f"오라클이 위반 발견한 쌍        : {oracle_viol}")
    pdet = _pct(t.detected_viol, oracle_viol)
    print(f"  └ 형식 error 탐지(detection) : {t.detected_viol}  ({pdet})")
    print(f"  └ 보수적 warning(침묵 아님)  : {t.warned_viol}")
    print(f"  └ ★형식 완전침묵(miss)      : {t.missed_viol}   ← 0 이어야 건전")
    print(f"미증명·미반증(완전성 공백)     : {t.unproven_safe}")

    g_total = (g.proven_confirmed + g.false_proof + g.detected_viol
               + g.warned_viol + g.missed_viol + g.unproven_safe)
    g_oracle = g.false_proof + g.detected_viol + g.warned_viol + g.missed_viol
    print("\n---- 그룹 단위 혼동행렬 (≥3 출력 one-hot / at-most-one) ----")
    print(f"검사한 상호배제 그룹           : {g_total}")
    print(f"k-귀납 *증명* 한 그룹          : {g.proven_confirmed + g.false_proof}")
    print(f"  └ 오라클도 안전 확인(건전)   : {g.proven_confirmed}")
    print(f"  └ ★false-proof(불건전)      : {g.false_proof}   ← 0 이어야 건전")
    print(f"오라클이 위반 발견한 그룹      : {g_oracle}")
    gdet = _pct(g.detected_viol, g_oracle)
    print(f"  └ 형식 error 탐지(detection) : {g.detected_viol}  ({gdet})")
    print(f"  └ 보수적 warning(침묵 아님)  : {g.warned_viol}")
    print(f"  └ ★형식 완전침묵(miss)      : {g.missed_viol}   ← 0 이어야 건전")
    print(f"미증명·미반증(완전성 공백)     : {g.unproven_safe}")

    sound = (t.false_proof == 0 and t.missed_viol == 0
             and g.false_proof == 0 and g.missed_viol == 0)
    verdict = "건전(SOUND) — 쌍·그룹 모두 false-proof=0, miss=0" if sound else "불건전 사례 발견!"
    print(f"\n판정: {verdict}")
    print(f"의미: 무작위 {_N_RANDOM} 프로그램 + 실레시피 + 적대 뮤턴트에 걸쳐, k-귀납이 "
          "*증명한* 쌍·그룹을 실행오라클이 단 한 번도 반증 못함 = 검증기 건전성의 규모 "
          "실증(쌍 단위 + 그룹 one-hot 혼동행렬, 논문급 표).")
    return 0 if sound else 1


if __name__ == "__main__":
    raise SystemExit(main())
