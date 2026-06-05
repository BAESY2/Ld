"""검증 게이트 자기증식 데이터셋 — '축적된 데이터로 결정론 강화'의 실체.

연구(AutoPLC·AlphaVerus) 결론: 합성기를 단단하게 만드는 가장 확실한 방법은,
스스로 명세를 변형·합성하고 **검증을 통과한 샘플만 누적**해 회귀망을 키우는 것이다.
LLM·API 키 불필요·완전 결정론(같은 입력 → 같은 코퍼스)으로 CI 에서 그대로 돈다.

파이프라인(레시피 × 결정론적 파라미터 변형 → 후보):
  build_spec → synthesize_st → 5개 결정론 게이트
    G1 synth      : 합성이 예외 없이 성공
    G2 no_dbl_coil: 이중코일 0(출력당 1대입)
    G3 verified   : 정형검증 통과(인터락/이중코일/도달성 에러 0)
    G4 determinism: synth 2회·sim 2회 결과가 바이트 동일(결정론 증명)
    G5 mutex      : 시뮬레이션 어떤 샘플에서도 인터락 쌍 동시 ON 없음
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
from app.simulator import simulate
from app.synth import synthesize_st
from app.verifier import verify
from app.wizard import RECIPES, Field, Recipe, build_spec

# 게이트 순서(통과 판정 순). non_vacuous 는 '항상 OFF/무조건 TRUE' 같은
# 공허하게 검증을 통과하는 퇴화 샘플로 코퍼스가 오염되는 것을 막는다(AlphaVerus 통찰).
_GATE_NAMES = ("synth", "no_double_coil", "verified", "non_vacuous",
               "determinism", "mutex")
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


def _canonical_st(st: str) -> str:
    """주석·잉여공백 제거 후 줄 단위로 정규화(코드 의미는 보존, 순서 유지)."""
    lines = []
    for raw in st.splitlines():
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


def _vacuous_output(st: str, spec: StateMachineSpec) -> str | None:
    """공허한 출력 코일을 찾는다(있으면 심볼명, 없으면 None).

    퇴화 신호: 출력이 상수(`OUT := FALSE/TRUE;`)이거나 자기참조뿐이라
    실제 입력이 출력을 구동하지 못하면(=검증이 공허하게 통과) 코퍼스에서 제외.
    """
    output_syms = {
        p.symbol for p in spec.io_points if p.direction == IODirection.OUTPUT
    }
    for line in st.splitlines():
        code = line.split("//", 1)[0].strip()
        m = _ASSIGN_RE.match(code)
        if not m or m.group(1) not in output_syms:
            continue
        drivers = _expr_vars(parse(m.group(2))) - {m.group(1)}
        if not drivers:  # 상수거나 자기참조뿐 → 구동원 없음
            return m.group(1)
    return None


def _trace_repr(st: str, spec: StateMachineSpec) -> str:
    """모든 입력을 t=0 에 ON 으로 두고 가동한 출력 트레이스의 결정론적 직렬화."""
    stim = [(0, {sym: True for sym in _input_symbols(spec)})]
    res = simulate(st, stim, duration_ms=_SIM_DURATION_MS, step_ms=_SIM_STEP_MS)
    return "|".join(
        f"{s.t_ms}:{','.join(sorted(k for k, v in s.outputs.items() if v))}"
        for s in res.samples
    )


# ── 게이트 ────────────────────────────────────────────────────────────────

def _run_gates(spec: StateMachineSpec) -> tuple[dict[str, bool], str, str, str]:
    """5개 결정론 게이트 실행. (gates, st, fingerprint, reason) 반환.

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

    # G4 determinism: synth 2회 + sim 2회 가 바이트 동일
    try:
        st2 = synthesize_st(spec)
        t1 = _trace_repr(st, spec)
        t2 = _trace_repr(st2, spec)
    except Exception as exc:  # noqa: BLE001
        return gates, st, "", f"determinism-sim: {exc}"
    if _canonical_st(st) != _canonical_st(st2) or t1 != t2:
        return gates, st, "", "determinism: 재실행 결과 불일치"
    gates["determinism"] = True

    # G5 mutex: 인터락 쌍이 어떤 샘플에서도 동시 ON 이 아님
    stim = [(0, {sym: True for sym in _input_symbols(spec)})]
    res = simulate(st, stim, duration_ms=_SIM_DURATION_MS, step_ms=_SIM_STEP_MS)
    for pair in spec.interlocks:
        for s in res.samples:
            if s.outputs.get(pair.output_a) and s.outputs.get(pair.output_b):
                return gates, st, "", (
                    f"mutex: {pair.output_a}+{pair.output_b} @ {s.t_ms}ms"
                )
    gates["mutex"] = True

    return gates, st, _hash(_canonical_st(st)), ""


# ── 생성 ──────────────────────────────────────────────────────────────────

def generate(recipe_ids: list[str] | None = None) -> BootstrapReport:
    """검증 게이트를 통과한 샘플만 누적한 결정론 코퍼스를 만든다.

    recipe_ids 미지정 시 전체 레시피. 같은 입력이면 항상 같은 코퍼스(결정론).
    """
    ids = recipe_ids if recipe_ids is not None else list(RECIPES.keys())
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
            report.samples.append(Sample(
                sample_id=f"{rid}#{fp}",
                recipe_id=rid,
                answers=answers,
                st=st,
                fingerprint=fp,
                trace_fingerprint=_hash(_trace_repr(st, spec)),
                gates=gates,
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
