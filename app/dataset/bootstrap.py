"""검증 게이트 자기증식 데이터셋 — '축적된 데이터로 결정론 강화'의 실체.

연구(AutoPLC·AlphaVerus) 결론: 합성기를 단단하게 만드는 가장 확실한 방법은,
스스로 명세를 변형·합성하고 **검증을 통과한 샘플만 누적**해 회귀망을 키우는 것이다.
LLM·API 키 불필요·완전 결정론(같은 입력 → 같은 코퍼스)으로 CI 에서 그대로 돈다.

파이프라인(레시피 × 결정론적 파라미터 변형 → 후보):
  build_spec → synthesize_st → 6개 결정론·안전 게이트
    G1 synth       : 합성이 예외 없이 성공
    G2 no_dbl_coil : 이중코일 0(출력당 1대입)
    G3 verified    : 정형검증 통과(인터락/이중코일/도달성 에러 0)
    G4 non_vacuous : 입력에 무감한 자명/죽은 코일 배제(공허 통과 차단, AlphaVerus)
    G5 determinism : synth 2회·sim 2회 결과가 **바이트 동일**(결정론 증명)
    G6 mutex       : 다단계 자극으로 실제 구동 시 인터락 쌍 동시 ON 없음
모든 게이트를 통과한 후보만 Sample 로 누적하고, ST 지문으로 중복을 제거한다.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.boolexpr import And, Node, Not, Or, Var, parse
from app.memory_map import detect_double_coils
from app.models import IODirection, StateMachineSpec
from app.simulator import (
    MAX_SIM_SAMPLES,
    SimResult,
    _Program,
    coil_block_is_idempotent,
    permutation_invariant_outputs,
    simulate,
)
from app.synth import synthesize_st
from app.verifier import verify
from app.wizard import RECIPES, Field, Recipe, build_spec

# 게이트 순서(통과 판정 순). non_vacuous 는 '항상 OFF/무조건 TRUE' 같은
# 공허하게 검증을 통과하는 퇴화 샘플로 코퍼스가 오염되는 것을 막는다(AlphaVerus 통찰).
_GATE_NAMES = ("synth", "no_double_coil", "verified", "non_vacuous",
               "determinism", "mutex", "metamorphic")
_SIM_DURATION_MS = 2000
_SIM_STEP_MS = 100
_ASSIGN_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*:=\s*([^;]+?)\s*;\s*$")


@dataclass(frozen=True)
class Sample:
    """게이트를 모두 통과한 결정론 코퍼스 1건."""

    sample_id: str
    recipe_id: str
    answers: dict[str, str]
    st: str
    fingerprint: str        # 정규화 ST 의 해시(중복제거·결정론 앵커)
    trace_fingerprint: str  # 시뮬레이션 트레이스 해시
    gates: dict[str, bool]
    energized: list[str]     # 자극으로 실제 켜진 출력(커버리지 — 누적 데이터 강화)


@dataclass
class Rejection:
    recipe_id: str
    answers: dict[str, str]
    failed_gate: str
    reason: str


@dataclass
class BootstrapReport:
    total_candidates: int = 0
    passed: int = 0
    rejected: int = 0
    samples: list[Sample] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)

    @property
    def unique(self) -> int:
        return len({s.fingerprint for s in self.samples})

    @property
    def recipe_ids(self) -> set[str]:
        return {s.recipe_id for s in self.samples}


# ── 결정론적 파라미터 변형 ────────────────────────────────────────────────

def _numeric_variants(default: str) -> list[str]:
    """숫자 슬롯의 변형값(결정론적·작게). default 와 1·2 를 합쳐 정렬·중복제거."""
    try:
        d = int(float(default))
    except (TypeError, ValueError):
        d = 1
    return [str(v) for v in sorted({1, 2, max(d, 1)})]


def _perturbations(recipe: Recipe) -> Iterator[dict[str, str]]:
    """레시피 1개의 후보 답변들(결정론). baseline + 숫자필드 1개씩 변형(폭증 방지)."""
    defaults = {f.key: f.default for f in recipe.fields}
    yield dict(defaults)  # baseline (모두 기본값)
    numeric: list[Field] = [f for f in recipe.fields if f.kind in ("int", "time_sec")]
    for f in numeric:
        for val in _numeric_variants(f.default):
            if val == f.default:
                continue
            ans = dict(defaults)
            ans[f.key] = val
            yield ans


# ── 지문(결정론 증명·중복제거) ────────────────────────────────────────────

_COMMENT_RE = re.compile(r"//.*$")


# 합성기가 출력 동작에 영향을 주는 의미를 주석으로만 인코딩하는 경우(예: 타이머
# 타입 `// 타이머 T1 (TOF, ...)` → 시뮬레이터가 TON/TOF/TP 를 이 주석으로 결정)
# 가 있다. 이런 '의미 있는 주석'은 정규화에서 보존해야 지문 충돌을 막는다.
_SEMANTIC_COMMENT_RE = re.compile(
    r"//\s*타이머\s+[A-Za-z_]\w*\s*\(\s*(?:TON|TOF|TP)\b", re.IGNORECASE
)


def _canonical_st(st: str) -> str:
    """주석·잉여공백 제거 후 줄 단위로 정규화(코드 의미는 보존, 순서 유지).

    단, 시뮬레이션 의미를 담은 주석(타이머 타입 등)은 보존한다 — 그렇지 않으면
    TON/TOF 처럼 트레이스가 전혀 다른 두 ST 가 같은 지문으로 충돌(중복 오제거)한다.
    """
    lines = []
    for raw in st.splitlines():
        if _SEMANTIC_COMMENT_RE.search(raw):
            lines.append(re.sub(r"\s+", " ", raw.strip()))
            continue
        code = _COMMENT_RE.sub("", raw).strip()
        if code:
            lines.append(re.sub(r"\s+", " ", code))
    return "\n".join(lines)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _input_symbols(spec: StateMachineSpec) -> list[str]:
    return sorted(p.symbol for p in spec.io_points if p.direction == IODirection.INPUT)


def _expr_vars(node: Node) -> set[str]:
    match node:
        case Var(name):
            return {name}
        case Not(operand):
            return _expr_vars(operand)
        case And(operands) | Or(operands):
            out: set[str] = set()
            for o in operands:
                out |= _expr_vars(o)
            return out
        case _:  # Const
            return set()


_MAX_VACUITY_VARS = 12  # 진리표 완전탐색 상한(2^12=4096). 초과 시 비공허로 간주.


def _is_constant_expr(node: Node, variables: list[str]) -> bool:
    """식이 모든 변수 대입에서 동일한 값(항상 TRUE 또는 항상 FALSE)이면 True.

    퇴화(공허) 판정의 의미론적 핵심: 어떤 입력을 뒤집어도 출력이 바뀌지 않으면
    (tautology `A OR NOT A`, contradiction `A AND NOT A`) 그 출력은 실제로
    구동되지 않는 죽은/자명한 코일이다. 변수 수가 많으면(>상한) 보수적으로
    '비상수'(=비공허)로 처리해 게이트가 과하게 막지 않게 한다.
    """
    if len(variables) > _MAX_VACUITY_VARS:
        return False
    first: bool | None = None
    for mask in range(1 << len(variables)):
        table = {v: bool(mask & (1 << i)) for i, v in enumerate(variables)}
        val = _eval_const(node, table)
        if first is None:
            first = val
        elif val != first:
            return False
    return True


def _eval_const(node: Node, table: dict[str, bool]) -> bool:
    match node:
        case Var(name):
            return table.get(name, False)
        case Not(operand):
            return not _eval_const(operand, table)
        case And(operands):
            return all(_eval_const(o, table) for o in operands)
        case Or(operands):
            return any(_eval_const(o, table) for o in operands)
        case _:  # Const
            return bool(getattr(node, "value", False))


def _vacuous_output(st: str, spec: StateMachineSpec) -> str | None:
    """공허한 출력 코일을 찾는다(있으면 심볼명, 없으면 None).

    퇴화 신호:
      (1) 출력이 상수/자기참조뿐이라 구동원이 없거나,
      (2) 식이 모든 입력 대입에서 상수(tautology/contradiction)라 입력에
          무감(無感)한 죽은/자명한 코일 → 검증이 공허하게 통과.
    seal-in 식 `(... ) OR OUT ...` 는 자기참조 변수(OUT)를 자유변수로 포함해
    상수 여부를 판정하므로 정상 seal-in 은 비상수로 통과한다.
    """
    output_syms = {
        p.symbol for p in spec.io_points if p.direction == IODirection.OUTPUT
    }
    for line in st.splitlines():
        code = line.split("//", 1)[0].strip()
        m = _ASSIGN_RE.match(code)
        if not m or m.group(1) not in output_syms:
            continue
        node = parse(m.group(2))
        all_vars = _expr_vars(node)
        drivers = all_vars - {m.group(1)}
        if not drivers:  # 상수거나 자기참조뿐 → 구동원 없음
            return m.group(1)
        if _is_constant_expr(node, sorted(all_vars)):  # 입력 무감(자명/죽은 코일)
            return m.group(1)
    return None


def _max_preset_ms(spec: StateMachineSpec) -> int:
    """명세 내 최대 타이머 프리셋(ms). 시뮬 구간을 타이머가 발화하도록 보장하는 데 쓴다."""
    return max((t.preset_ms for t in spec.timers), default=0)


def _sum_preset_ms(spec: StateMachineSpec) -> int:
    """명세 내 모든 타이머 프리셋의 합(ms).

    N단계 타임드 시퀀서(세차·신호등·배치)는 각 단계 타이머가 **직렬로 핸드오프**되므로
    한 입력(START)을 *모든 단계 프리셋의 합* 만큼 유지해야 마지막 단계까지 도달한다.
    최댓값(_max_preset_ms)만으로는 1~2단계만 켜지고 마지막 단계 출력이 코퍼스에서
    영원히 죽은 채로 남아 커버리지(energized)가 거짓으로 불완전해진다.
    """
    return sum(t.preset_ms for t in spec.timers)


def _max_counter_preset(spec: StateMachineSpec) -> int:
    """명세 내 최대 카운터 프리셋(PV). 엣지 펄스를 PV 만큼 줘야 카운터가 발화한다."""
    return max((c.preset for c in spec.counters), default=0)


def _exercise_stimulus(spec: StateMachineSpec) -> tuple[list[tuple[int, dict[str, bool]]], int]:
    """기계를 실제로 '구동'하는 결정론적 다단계 입력 자극과 그에 맞는 sim 길이를 만든다.

    문제: 모든 입력을 동시에 ON 으로 두면 STOP/REV/HI 같은 차단 입력까지 켜져
    대부분의 기계가 IDLE 에 갇혀 어떤 출력도 안 켜진다 → mutex/트레이스가 공허.
    해법: 각 입력을 한 번에 하나씩(+ 인접 쌍) 단계적으로 ON 하며, 각 단계가 타이머
    프리셋을 넘기도록 충분히 길게 잡고, 마지막에 입력별 **엣지 펄스 열**을 추가해
    카운터(CTU/CTD)와 엣지 구동 로직까지 실제로 발화시킨다(전부 결정론 유지).
    """
    inputs = _input_symbols(spec)
    # 각 단계는 타이머가 발화할 만큼 길어야 한다(+여유 1스캔). 단, N단계 시퀀서는
    # 타이머가 직렬 핸드오프되므로 한 입력을 '모든 프리셋의 합' 만큼 유지해야 마지막
    # 단계까지 구동된다 → 합(sum)을 써야 마지막 단계 출력의 죽음(거짓 커버리지)을 막는다.
    phase_ms = max(_SIM_DURATION_MS, _sum_preset_ms(spec) + 3 * _SIM_STEP_MS)
    phases: list[dict[str, bool]] = [{}]  # P0: 전부 OFF(초기화)
    for sym in inputs:  # 각 입력 단독 ON
        phases.append({s: (s == sym) for s in inputs})
    for i in range(len(inputs) - 1):  # 인접 입력 쌍 ON(전이 트리거 다양화)
        pair = {inputs[i], inputs[i + 1]}
        phases.append({s: (s in pair) for s in inputs})
    for sym in inputs:  # 단독 OFF(나머지 전부 ON) — 다중 허가 출력(예: 가드+E-stop+기동)
        phases.append({s: (s != sym) for s in inputs})  # 을 깨우고 정지 입력만 끄는 조합
    phases.append({s: True for s in inputs})  # 마지막: 전부 ON(차단/정지 경계)
    stim: list[tuple[int, dict[str, bool]]] = []
    for k, ph in enumerate(phases):
        stim.append((k * phase_ms, {s: ph.get(s, False) for s in inputs}))
    total = len(phases) * phase_ms
    # 엣지 펄스 열: 입력을 하나씩 ON→OFF 로 PV+여유 회 토글해 상승엣지를 만든다.
    # (카운터는 상승엣지마다 +1 이므로 '유지 ON' 만으로는 1회만 세고 발화 못 함)
    pulses = max(4, _max_counter_preset(spec) + 2)
    t = total
    for sym in inputs:
        for _ in range(pulses):
            stim.append((t, {s: (s == sym) for s in inputs}))
            t += _SIM_STEP_MS
            stim.append((t, {s: False for s in inputs}))
            t += _SIM_STEP_MS
    return stim, t


class StimulusTooLarge(ValueError):
    """자극 길이가 시뮬 샘플 상한을 넘어 기계를 안전하게 구동할 수 없음.

    (예: 카운터 PV 가 매우 커 엣지 펄스 열이 MAX_SIM_SAMPLES 를 초과.)
    determinism 실패로 오인되지 않도록 별도 예외로 분리해 게이트가 정직한 사유를 남긴다.
    """


def _exercise(st: str, spec: StateMachineSpec) -> SimResult:
    stim, total = _exercise_stimulus(spec)
    # 자극이 시뮬 상한을 넘기면 'determinism-sim' 으로 오기록되지 않도록 먼저 막는다.
    if total // _SIM_STEP_MS + 1 > MAX_SIM_SAMPLES:
        raise StimulusTooLarge(
            f"자극 샘플 {total // _SIM_STEP_MS + 1}개가 상한({MAX_SIM_SAMPLES})을 초과 "
            f"(타이머 프리셋/카운터 PV 가 너무 큼)."
        )
    return simulate(st, stim, duration_ms=total, step_ms=_SIM_STEP_MS)


def _trace_repr(st: str, spec: StateMachineSpec) -> str:
    """기계를 단계적으로 구동(_exercise_stimulus)해 얻은 출력 트레이스의 결정론적 직렬화.

    (이전: 모든 입력 동시 ON → 대부분 IDLE 갇힘으로 트레이스가 공허했음)
    """
    res = _exercise(st, spec)
    return "|".join(
        f"{s.t_ms}:{','.join(sorted(k for k, v in s.outputs.items() if v))}"
        for s in res.samples
    )


# ── 변형관계(metamorphic) 게이트 ────────────────────────────────────────────

# 변형관계 검사용 진리표 완전탐색 상한(2^MAX). 입력+FB(.Q) 변수가 많으면 보수적으로
# 대각선(전부 OFF/전부 ON + 단독 ON) 표본만 써서 게이트가 과하게 무거워지지 않게 한다.
_MAX_METAMORPHIC_VARS = 10


def _metamorphic_probe_vars(st: str, spec: StateMachineSpec) -> tuple[list[str], list[str]]:
    """(입력 심볼, FB .Q 심볼) — 코일 블록이 의존하는 비코일 자유변수 목록.

    입력 + 타이머/카운터 .Q 를 *독립 상태* 로 고정한 채 코일 블록만 재평가하기 위함.
    """
    prog = _Program(st)
    inputs = _input_symbols(spec)
    fb_q = [f"{n}.Q" for n in prog.timers] + [f"{n}.Q" for n in prog.counters]
    return inputs, sorted(fb_q)


def _metamorphic_tables(probe: list[str]) -> Iterator[dict[str, bool]]:
    """probe 변수에 대한 결정론적 입력/FB-상태 표본을 만든다.

    변수 수가 작으면 진리표를 완전탐색(2^n), 크면 대각선 표본(전부 OFF/전부 ON +
    각 변수 단독 ON)으로 축약해 폭증을 막되 결정론을 유지한다.
    """
    n = len(probe)
    if n <= _MAX_METAMORPHIC_VARS:
        for mask in range(1 << n):
            yield {v: bool(mask & (1 << i)) for i, v in enumerate(probe)}
        return
    yield dict.fromkeys(probe, False)
    yield dict.fromkeys(probe, True)
    for i in range(n):
        yield {v: (j == i) for j, v in enumerate(probe)}


def _check_metamorphic(st: str, spec: StateMachineSpec) -> str:
    """변형관계#1(멈춤불변 고정점) + #2(입력순열 불변)를 검사. 위반 시 사유, 통과 시 ""."""
    inputs, fb_q = _metamorphic_probe_vars(st, spec)
    probe = inputs + fb_q
    # 입력 순열: 입력 수가 적으면 전순열, 많으면 정방향/역방향만(결정론·보수적).
    if len(inputs) <= 4:
        orders = [list(p) for p in _permutations(inputs)]
    else:
        orders = [list(inputs), list(reversed(inputs))]
    for table in _metamorphic_tables(probe):
        if not coil_block_is_idempotent(st, table):
            return f"metamorphic: 코일 블록이 1패스에 고정점에 닿지 못함 @ {table}"
        snapshot = {s: table[s] for s in inputs}
        base = {s: table[s] for s in fb_q}
        if not permutation_invariant_outputs(st, base, snapshot, orders):
            return f"metamorphic: 입력순열에 따라 출력이 달라짐 @ {table}"
    return ""


def _permutations(seq: list[str]) -> Iterator[tuple[str, ...]]:
    """결정론적 전순열(itertools.permutations 래퍼 — 입력 순서 그대로 lexicographic)."""
    from itertools import permutations

    return permutations(seq)


# ── 게이트 ────────────────────────────────────────────────────────────────

def _run_gates(spec: StateMachineSpec) -> tuple[dict[str, bool], str, str, str]:
    """6개 결정론·안전 게이트 실행. (gates, st, fingerprint, reason) 반환.

    어느 게이트라도 실패하면 그 지점에서 중단(이후 게이트는 False)하고 reason 을 남긴다.
    """
    gates = dict.fromkeys(_GATE_NAMES, False)
    # G1 synth
    try:
        st = synthesize_st(spec)
    except Exception as exc:  # noqa: BLE001 — 후보 거절 사유로 기록
        return gates, "", "", f"synth: {exc}"
    gates["synth"] = True

    # G2 no double coil
    dbl = detect_double_coils(st)
    if dbl:
        return gates, st, "", f"double_coil: {sorted(dbl)}"
    gates["no_double_coil"] = True

    # G3 formal verify (인터락/이중코일/도달성 에러 0)
    report = verify(spec, st)
    if report.has_errors:
        errs = [f"{i.code}" for i in report.issues if i.severity == "error"]
        return gates, st, "", f"verify: {sorted(set(errs))}"
    gates["verified"] = True

    # G3.5 non-vacuity: 공허하게 검증을 통과하는 퇴화 출력 차단
    vac = _vacuous_output(st, spec)
    if vac is not None:
        return gates, st, "", f"non_vacuous: {vac} 가 상수/자기참조뿐(구동원 없음)"
    gates["non_vacuous"] = True

    # G4 determinism: synth 2회 + sim 2회 가 **바이트 동일**(주석 포함).
    # 주석까지 동일해야 한다 — _canonical_st 비교만 하면 주석에 심어진 비결정성
    # (난수 nonce·타임스탬프 등)이 그대로 지속 산출물(Sample.st)에 새어 들어가
    # 게이트가 'determinism=True' 라고 거짓 보증한다.
    try:
        st2 = synthesize_st(spec)
        t1 = _trace_repr(st, spec)
        t2 = _trace_repr(st2, spec)
    except StimulusTooLarge as exc:
        # 결정론 실패가 아니라 자극이 시뮬 상한을 넘긴 것 — 정직한 별도 사유로 기록.
        return gates, st, "", f"stimulus_too_large: {exc}"
    except Exception as exc:  # noqa: BLE001
        return gates, st, "", f"determinism-sim: {exc}"
    if st != st2 or t1 != t2:
        return gates, st, "", "determinism: 재실행 결과 불일치"
    gates["determinism"] = True

    # G5 mutex: 인터락 쌍이 어떤 샘플에서도 동시 ON 이 아님.
    # 기계를 실제로 구동하는 다단계 자극(_exercise_stimulus)으로 검사한다 —
    # 모든 입력 동시 ON 한 스냅샷으로는 대부분 기계가 IDLE 에 갇혀 인터락 상태에
    # 도달조차 못 해 mutex 가 '공허하게' 통과하던 결함을 차단한다.
    res = _exercise(st, spec)
    for pair in spec.interlocks:
        for s in res.samples:
            if s.outputs.get(pair.output_a) and s.outputs.get(pair.output_b):
                return gates, st, "", (
                    f"mutex: {pair.output_a}+{pair.output_b} @ {s.t_ms}ms"
                )
    gates["mutex"] = True

    # G7 metamorphic(오라클 없는 변형관계): 입력·FB(.Q) 상태를 고정한 채
    #   #1 멈춤불변 고정점 — 코일 블록 재평가가 1패스에 수렴(스캔 1회 결정성),
    #   #2 입력순열 불변 — 한 스캔 안 입력 읽기 순서가 출력을 바꾸지 않음.
    # 둘 다 합성된 top-to-bottom seal-in 의 결정성을 *명세 정답 없이* 강화한다.
    mm = _check_metamorphic(st, spec)
    if mm:
        return gates, st, "", mm
    gates["metamorphic"] = True

    return gates, st, _hash(_canonical_st(st)), ""


# ── 생성 ──────────────────────────────────────────────────────────────────

def generate(recipe_ids: list[str] | None = None) -> BootstrapReport:
    """검증 게이트를 통과한 샘플만 누적한 결정론 코퍼스를 만든다.

    recipe_ids 미지정 시 전체 레시피. 같은 입력이면 항상 같은 코퍼스(결정론).
    """
    ids = recipe_ids if recipe_ids is not None else list(RECIPES.keys())
    unknown = [r for r in ids if r not in RECIPES]
    if unknown:
        raise KeyError(f"알 수 없는 레시피 id: {sorted(unknown)}")
    report = BootstrapReport()
    seen: set[str] = set()
    for rid in ids:
        recipe = RECIPES[rid]
        for answers in _perturbations(recipe):
            report.total_candidates += 1
            # build_spec 자체가 거절할 수도 있음(검증 실패 = 게이트 역할)
            try:
                spec = build_spec(rid, answers)
            except Exception as exc:  # noqa: BLE001
                report.rejected += 1
                report.rejections.append(Rejection(rid, answers, "build_spec", str(exc)))
                continue
            gates, st, fp, reason = _run_gates(spec)
            if not all(gates.values()):
                report.rejected += 1
                failed = next(g for g in _GATE_NAMES if not gates[g])
                report.rejections.append(Rejection(rid, answers, failed, reason))
                continue
            if fp in seen:  # 중복(near-dup) 제거 — 코퍼스를 군더더기로 채우지 않음
                continue
            seen.add(fp)
            report.passed += 1
            outs = [
                p.symbol for p in spec.io_points
                if p.direction == IODirection.OUTPUT
            ]
            res = _exercise(st, spec)
            energized = sorted({
                o for s in res.samples for o in outs if s.outputs.get(o)
            })
            report.samples.append(Sample(
                sample_id=f"{rid}#{fp}",
                recipe_id=rid,
                answers=answers,
                st=st,
                fingerprint=fp,
                trace_fingerprint=_hash(_trace_repr(st, spec)),
                gates=gates,
                energized=energized,
            ))
    return report


def write_dataset(report: BootstrapReport, path: str | Path) -> Path:
    """코퍼스를 JSON 으로 직렬화(샘플 + 요약 통계). 누적 데이터 산출물."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": {
            "total_candidates": report.total_candidates,
            "passed": report.passed,
            "rejected": report.rejected,
            "unique": report.unique,
            "recipes": sorted(report.recipe_ids),
        },
        "samples": [asdict(s) for s in report.samples],
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def main() -> None:  # pragma: no cover - CLI 편의
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "data/bootstrap/dataset.json"
    rep = generate()
    write_dataset(rep, out)
    print(
        f"후보 {rep.total_candidates} → 통과 {rep.passed} (중복제거 후 {rep.unique}) "
        f"· 거절 {rep.rejected} · 레시피 {len(rep.recipe_ids)}개 → {out}"
    )


if __name__ == "__main__":  # pragma: no cover
    main()
