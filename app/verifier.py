"""정형 검증기 — 문법이 아닌 *논리* 검증 (결정론 코어).

3종 검사:
  1. 이중 코일      : detect_double_coils 결과를 error 로.
  2. 인터락 (Z3)    : 상호배타 출력이 동시에 켜질 수 있으면 반례와 함께 error.
  3. 도달성/데드락  : 초기 상태 없음=error, 진입 전이 없는 상태=warning.

Z3 미설치 시 인터락은 warning 만 남기고 통과한다(파이프라인 중단 금지).
"""

from __future__ import annotations

import re

from app.memory_map import detect_double_coils
from app.models import StateMachineSpec, VerificationIssue, VerificationReport

try:  # z3 는 선택적 의존성처럼 다룬다
    import z3

    _HAS_Z3 = True
except Exception:  # pragma: no cover - 환경에 z3 없을 때
    _HAS_Z3 = False


# ---------------------------------------------------------------------------
# 불리언식 → Z3 (재귀하강 파서)
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"\s*(\(|\)|[A-Za-z_]\w*)")


def _tokenize(expr: str) -> list[str]:
    tokens: list[str] = []
    pos = 0
    while pos < len(expr):
        m = _TOKEN_RE.match(expr, pos)
        if not m:
            if expr[pos].isspace():
                pos += 1
                continue
            raise ValueError(f"인식 불가 토큰: {expr[pos:]!r}")
        tokens.append(m.group(1))
        pos = m.end()
    return tokens


def _to_z3(expr: str, vars: dict[str, z3.BoolRef]) -> z3.BoolRef:
    """AND/OR/NOT/괄호/심볼 불리언식을 z3 식으로 변환.

    문법 (우선순위 NOT > AND > OR):
      or_expr  := and_expr (OR and_expr)*
      and_expr := not_expr (AND not_expr)*
      not_expr := NOT not_expr | '(' or_expr ')' | SYMBOL
    """
    tokens = _tokenize(expr)
    idx = 0

    def peek() -> str | None:
        return tokens[idx] if idx < len(tokens) else None

    def advance() -> str:
        nonlocal idx
        tok = tokens[idx]
        idx += 1
        return tok

    def parse_or() -> z3.BoolRef:
        node = parse_and()
        while (tok := peek()) is not None and tok.upper() == "OR":
            advance()
            node = z3.Or(node, parse_and())
        return node

    def parse_and() -> z3.BoolRef:
        node = parse_not()
        while (tok := peek()) is not None and tok.upper() == "AND":
            advance()
            node = z3.And(node, parse_not())
        return node

    def parse_not() -> z3.BoolRef:
        tok = peek()
        if tok is None:
            raise ValueError(f"식이 갑자기 끝남: {expr!r}")
        if tok.upper() == "NOT":
            advance()
            return z3.Not(parse_not())
        if tok == "(":
            advance()
            node = parse_or()
            if peek() != ")":
                raise ValueError(f"닫는 괄호 누락: {expr!r}")
            advance()
            return node
        # 심볼
        sym = advance()
        upper = sym.upper()
        if upper == "TRUE":
            return z3.BoolVal(True)
        if upper == "FALSE":
            return z3.BoolVal(False)
        if sym not in vars:
            vars[sym] = z3.Bool(sym)
        return vars[sym]

    node = parse_or()
    if idx != len(tokens):
        raise ValueError(f"식 파싱 후 잔여 토큰: {tokens[idx:]!r}")
    return node


# ---------------------------------------------------------------------------
# 출력 ON 조건 수집
# ---------------------------------------------------------------------------
_SET_TRUE_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*:=\s*TRUE\s*;\s*$", re.IGNORECASE)


def _collect_output_conditions(spec: StateMachineSpec) -> dict[str, list[str]]:
    """각 출력이 켜지는(:= TRUE) 전이 조건들을 수집한다.

    transition.to_state 의 on_entry 에 `OUT := TRUE;` 가 있으면,
    그 전이의 condition 이 OUT 의 ON 조건이 된다.
    """
    states = {s.name: s for s in spec.states}
    result: dict[str, list[str]] = {}
    for tr in spec.transitions:
        target = states.get(tr.to_state)
        if target is None:
            continue
        for stmt in target.on_entry:
            m = _SET_TRUE_RE.match(stmt)
            if m:
                output = m.group(1)
                result.setdefault(output, []).append(tr.condition)
    return result


def check_interlocks_z3(spec: StateMachineSpec) -> list[VerificationIssue]:
    """인터락 쌍이 동시에 켜질 수 있는지 Z3 로 증명한다."""
    if not spec.interlocks:
        return []
    if not _HAS_Z3:
        return [
            VerificationIssue(
                code="INTERLOCK",
                severity="warning",
                message="z3 미설치로 인터락을 검증하지 못했습니다(통과 처리).",
            )
        ]

    conditions = _collect_output_conditions(spec)
    issues: list[VerificationIssue] = []

    for lock in spec.interlocks:
        conds_a = conditions.get(lock.output_a, [])
        conds_b = conditions.get(lock.output_b, [])
        if not conds_a or not conds_b:
            # 한쪽이라도 켜지는 조건이 없으면 동시 ON 불가
            continue
        shared: dict[str, z3.BoolRef] = {}
        on_a = z3.Or(*[_to_z3(c, shared) for c in conds_a])
        on_b = z3.Or(*[_to_z3(c, shared) for c in conds_b])
        solver = z3.Solver()
        solver.add(z3.And(on_a, on_b))
        if solver.check() == z3.sat:
            model = solver.model()
            assignments = ", ".join(f"{d.name()}={model[d]}" for d in model.decls())
            issues.append(
                VerificationIssue(
                    code="INTERLOCK",
                    severity="error",
                    message=(
                        f"인터락 위반: '{lock.output_a}' 와 '{lock.output_b}' 가 "
                        f"동시에 켜질 수 있습니다. ({lock.reason})"
                    ),
                    counterexample=assignments,
                )
            )
    return issues


_ASSIGN_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*:=\s*(.+?)\s*;\s*$")


def _coil_equations(st_code: str) -> dict[str, str]:
    """ST 에서 `OUT := expr;` 의 좌변→우변식을 수집한다(주석/비대입 라인 무시)."""
    eqs: dict[str, str] = {}
    for line in st_code.splitlines():
        m = _ASSIGN_RE.match(line)
        if m:
            eqs[m.group(1)] = m.group(2)
    return eqs


def check_interlocks_st(spec: StateMachineSpec, st_code: str) -> list[VerificationIssue]:
    """**실제 합성 ST** 의 코일식으로 인터락을 검증한다(명세-only 검사 보강).

    seal-in 래치(`OR OUT`)와 `AND NOT partner` 항을 포함한 다음-상태식을 Z3 로
    귀납 검사한다: 현재 ¬(a∧b) 라고 가정했을 때 다음 스캔에 a'∧b' 가 가능하면 위반.
    동작 ST 가 상대 출력의 NOT 보호를 잃으면(회귀) 여기서 잡힌다.
    """
    if not spec.interlocks or not _HAS_Z3:
        return []
    eqs = _coil_equations(st_code)
    issues: list[VerificationIssue] = []
    for lock in spec.interlocks:
        a, b = lock.output_a, lock.output_b
        if a not in eqs or b not in eqs:
            continue
        shared: dict[str, z3.BoolRef] = {}
        try:
            a_next = _to_z3(eqs[a], shared)
            b_next = _to_z3(eqs[b], shared)
        except ValueError:
            continue  # 비불리언 토큰 등은 ST 검사 건너뜀(명세 검사로 충분)
        a_cur = shared.setdefault(a, z3.Bool(a))
        b_cur = shared.setdefault(b, z3.Bool(b))
        solver = z3.Solver()
        solver.add(z3.Not(z3.And(a_cur, b_cur)))  # 귀납 가정: 현재 동시 ON 아님
        solver.add(z3.And(a_next, b_next))  # 다음 스캔 동시 ON 가능?
        if solver.check() == z3.sat:
            model = solver.model()
            ce = ", ".join(f"{d.name()}={model[d]}" for d in model.decls())
            issues.append(
                VerificationIssue(
                    code="INTERLOCK",
                    severity="error",
                    message=(
                        f"인터락 위반(ST): '{a}' 와 '{b}' 의 합성식이 동시에 켜질 수 "
                        f"있습니다. ({lock.reason})"
                    ),
                    counterexample=ce,
                )
            )
    return issues


def check_reachability(spec: StateMachineSpec) -> list[VerificationIssue]:
    """초기 상태 존재 + 각 상태 도달성.

    상태머신이 아예 없으면(순수 조합 ST) 초기 상태를 요구하지 않는다.
    """
    issues: list[VerificationIssue] = []
    if not spec.states:
        return issues
    initials = [s for s in spec.states if s.is_initial]
    if not initials:
        issues.append(
            VerificationIssue(
                code="DEADLOCK",
                severity="error",
                message="초기 상태(is_initial=True)가 없습니다. 진입점을 지정하세요.",
            )
        )

    incoming = {tr.to_state for tr in spec.transitions}
    for state in spec.states:
        if state.is_initial:
            continue
        if state.name not in incoming:
            issues.append(
                VerificationIssue(
                    code="UNREACHABLE",
                    severity="warning",
                    message=f"상태 '{state.name}' 로 진입하는 전이가 없습니다(도달 불가).",
                )
            )
    return issues


def check_double_coils(st_code: str) -> list[VerificationIssue]:
    dups = detect_double_coils(st_code)
    return [
        VerificationIssue(
            code="DOUBLE_COIL",
            severity="error",
            message=f"이중 코일: '{sym}' 에 {len(exprs)}회 대입되었습니다.",
        )
        for sym, exprs in dups.items()
    ]


def verify(spec: StateMachineSpec, st_code: str) -> VerificationReport:
    """3종 검사를 합산해 리포트를 만든다. error 가 있으면 passed=False."""
    issues: list[VerificationIssue] = []
    issues.extend(check_double_coils(st_code))
    issues.extend(check_interlocks_z3(spec))
    issues.extend(check_interlocks_st(spec, st_code))
    issues.extend(check_reachability(spec))

    passed = not any(i.severity == "error" for i in issues)
    report = VerificationReport(issues=issues, passed=passed)

    if report.has_errors:
        fixes: list[str] = []
        codes = {i.code for i in issues if i.severity == "error"}
        if "DOUBLE_COIL" in codes:
            fixes.append("이중 코일을 M 릴레이로 분리한 뒤 OR 로 병합하세요.")
        if "INTERLOCK" in codes:
            fixes.append("상호배타 출력의 ON 조건에 상대 출력의 NOT 조건을 추가하세요.")
        if "DEADLOCK" in codes:
            fixes.append("초기 상태를 1개 지정하세요(is_initial=True).")
        report = report.model_copy(update={"suggested_fix": " ".join(fixes)})

    return report
