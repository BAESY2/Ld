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
_TOKEN_RE = re.compile(r"\s*(\(|\)|[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)")


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


def check_interlocks_z3(
    spec: StateMachineSpec, skip_pairs: frozenset[tuple[str, str]] = frozenset()
) -> list[VerificationIssue]:
    """인터락 쌍이 동시에 켜질 수 있는지 Z3 로 증명한다(명세-조건 수준).

    이 검사는 *선언된 전이 조건* 의 겹침만 본다 — synth 가 코일식에 추가하는
    ``AND NOT 상대`` 가드는 보지 못해, 기동 조건이 독립인 출력 쌍(예: 서로 다른
    버튼으로 켜지는 두 모터를 교차 인터락으로 묶은 경우)에는 거짓양성을 낸다.
    그래서 합성 ST 의 k-귀납으로 *실제 상호배제가 증명된* 쌍(``skip_pairs``)은
    건너뛴다(거짓양성 억제, 보수성은 유지 — 증명 못 한 쌍은 그대로 검사).
    """
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
        if (lock.output_a, lock.output_b) in skip_pairs:
            continue  # 합성 ST 의 k-귀납이 이 쌍의 상호배제를 이미 증명함
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
            assignments = _model_str(model)
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


_ASSIGN_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*:=\s*([^;]+?)\s*;\s*$")


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
    outputs = list(eqs.keys())
    out_set = set(outputs)
    cur = _frame(outputs, 0)
    nxt = _frame(outputs, 1)
    try:
        # 순차 스캔 의미론으로 cur→nxt 전이를 만든다(시뮬레이터와 동일).
        trans = _trans_at(eqs, outputs, out_set, cur, nxt, 0)
    except ValueError:
        return []  # 비불리언 토큰 등은 ST 검사 건너뜀(명세 검사로 충분)
    issues: list[VerificationIssue] = []
    for lock in spec.interlocks:
        a, b = lock.output_a, lock.output_b
        if a not in eqs or b not in eqs:
            continue
        solver = z3.Solver()
        solver.add(*trans)
        solver.add(z3.Not(z3.And(cur[a], cur[b])))  # 귀납 가정: 현재 동시 ON 아님
        solver.add(z3.And(nxt[a], nxt[b]))  # 다음 스캔 동시 ON 가능?
        if solver.check() == z3.sat:
            model = solver.model()
            ce = _model_str(model)
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


def _build_transition_system(
    st_code: str,
) -> tuple[list[str], dict[str, str]]:
    """ST 코일식에서 (출력 심볼 목록, 출력→다음상태식) 전이계를 추출한다.

    상태 = 출력 불리언들. init = 모든 출력 false. trans: next_out = f(inputs, cur_out).
    타이머 `.Q` 등 비출력 심볼은 매 스캔 자유 입력으로 둔다(보수적 추상화).
    출력 심볼 순서는 ST 등장 순서를 따른다(결정론).
    """
    eqs = _coil_equations(st_code)
    outputs = list(eqs.keys())
    return outputs, eqs


def _instantiate(
    expr: str,
    outputs: set[str],
    frame: dict[str, z3.BoolRef],
    inputs_at_step: dict[str, z3.BoolRef],
) -> z3.BoolRef:
    """코일식을 한 스캔의 변수 프레임으로 인스턴스화한다.

    출력 심볼은 `frame`(현재 상태 변수)에, 그 외 심볼은 `inputs_at_step`(이 스텝
    전용 자유 입력)에 매핑한다. _to_z3 가 미지의 심볼을 `vars` 에 새로 만들므로,
    출력은 frame 으로 미리 채워두고 나머지는 인스턴스화 후 입력으로 흡수한다.
    """
    local: dict[str, z3.BoolRef] = dict(frame)
    node = _to_z3(expr, local)
    # local 에 새로 생긴(=출력이 아닌) 심볼은 이 스텝의 자유 입력으로 귀속시킨다.
    for sym, var in local.items():
        if sym not in outputs and sym not in frame:
            inputs_at_step.setdefault(sym, var)
    return node


def _frame(outputs: list[str], step: int) -> dict[str, z3.BoolRef]:
    """스텝 step 의 상태 변수 프레임(출력별 z3.Bool)."""
    return {o: z3.Bool(f"{o}__s{step}") for o in outputs}


def _distinct_states(
    frames: list[dict[str, z3.BoolRef]], outputs: list[str]
) -> list[z3.BoolRef]:
    """단순경로(simple-path) 제약: 어떤 두 프레임도 상태가 같지 않다."""
    constraints: list[z3.BoolRef] = []
    for i in range(len(frames)):
        for j in range(i + 1, len(frames)):
            same = z3.And(*[frames[i][o] == frames[j][o] for o in outputs])
            constraints.append(z3.Not(same))
    return constraints


def check_interlocks_kinduction(
    spec: StateMachineSpec, st_code: str, k: int = 3
) -> list[VerificationIssue]:
    """합성 ST 의 인터락 상호배제를 **k-귀납**으로 모든 도달 스캔에 대해 증명한다.

    전이계: 상태=출력 불리언, init=전부 OFF, trans: next=f(inputs, cur).
    각 인터락 쌍 (a,b) 에 대해 성질 P := ¬(a∧b) 를 k-귀납으로 증명한다:
      - base : init 에서 k 스텝 풀어 step 0..k 에서 P 가 깨지면 **실제 도달가능 위반**.
      - step : 서로 다른(simple-path) k 개 연속 상태에서 P 가 성립한다고 가정했을 때
               다음 상태에서 P 가 깨질 수 있으면 귀납 실패(증명 불가).
    base 위반은 error(반례 포함). step 만 실패하면 1-스텝 검사와 동일 강도로
    보수적 경고를 남긴다(기존 강도 약화 금지). k 는 CI 속도를 위해 작게(기본 3).
    """
    if not spec.interlocks or not _HAS_Z3:
        return []
    if k < 1:
        k = 1
    outputs, eqs = _build_transition_system(st_code)
    out_set = set(outputs)
    issues: list[VerificationIssue] = []

    for lock in spec.interlocks:
        a, b = lock.output_a, lock.output_b
        if a not in eqs or b not in eqs:
            continue
        try:
            issue = _kinduction_pair(spec, eqs, outputs, out_set, lock, a, b, k)
        except ValueError:
            continue  # 비불리언 토큰 등 → 이 쌍은 건너뜀(다른 검사로 충분)
        if issue is not None:
            issues.append(issue)
    return issues


def proven_safe_pairs(
    spec: StateMachineSpec, st_code: str, k: int = 3
) -> frozenset[tuple[str, str]]:
    """합성 ST 의 k-귀납으로 *상호배제가 증명된* 인터락 쌍을 (a,b)·(b,a) 둘 다 반환한다.

    증명(``_kinduction_pair`` 가 None)된 쌍만 넣는다 — base 위반(error)·증명불가
    (warning)·분석불가(ValueError/비코일)는 제외하므로, 이 집합으로 스펙수준
    거짓양성을 억제해도 실제 위반 탐지력은 약화되지 않는다(positive proof only).
    """
    if not spec.interlocks or not _HAS_Z3:
        return frozenset()
    if k < 1:
        k = 1
    outputs, eqs = _build_transition_system(st_code)
    out_set = set(outputs)
    proven: set[tuple[str, str]] = set()
    for lock in spec.interlocks:
        a, b = lock.output_a, lock.output_b
        if a not in eqs or b not in eqs:
            continue
        try:
            issue = _kinduction_pair(spec, eqs, outputs, out_set, lock, a, b, k)
        except ValueError:
            continue
        if issue is None:
            proven.add((a, b))
            proven.add((b, a))
    return frozenset(proven)


def _trans_at(
    eqs: dict[str, str],
    outputs: list[str],
    out_set: set[str],
    cur: dict[str, z3.BoolRef],
    nxt: dict[str, z3.BoolRef],
    step: int,
) -> list[z3.BoolRef]:
    """한 스캔의 전이 제약: 출력을 **ST 소스 순서**로 평가한다(시뮬레이터와 동일).

    시뮬레이터는 코일을 위→아래 순차 평가하므로, 어떤 코일이 다른 출력을 참조하면
    *먼저 대입된* 출력은 갱신값(nxt)을, *자기 자신·이후* 출력은 직전값(cur)을 읽는다.
    (구버그: 모든 참조를 cur 로 본 동시-갱신 추상화 → 거짓 증명·거짓 양성 발생.)
    """
    cons: list[z3.BoolRef] = []
    for i, o in enumerate(outputs):
        # 이 코일이 보는 상태 프레임: 앞서 대입된 출력은 nxt, 자기·이후는 cur.
        frame_o: dict[str, z3.BoolRef] = {
            p: (nxt[p] if j < i else cur[p]) for j, p in enumerate(outputs)
        }
        local_inputs: dict[str, z3.BoolRef] = {}
        node = _instantiate(eqs[o], out_set, frame_o, local_inputs)
        # 입력 자유변수는 스텝마다 고유해야 한다(같은 입력이 매 스캔 바뀔 수 있음).
        rename = {
            v: z3.Bool(f"{s}__i{step}") for s, v in local_inputs.items()
        }
        if rename:
            node = z3.substitute(node, *list(rename.items()))
        cons.append(nxt[o] == node)
    return cons


def _kinduction_pair(
    spec: StateMachineSpec,
    eqs: dict[str, str],
    outputs: list[str],
    out_set: set[str],
    lock: object,
    a: str,
    b: str,
    k: int,
) -> VerificationIssue | None:
    """단일 인터락 쌍에 대한 k-귀납. 위반(error)/증명불가(warning)/증명(None)."""
    reason = getattr(lock, "reason", "")
    frames = [_frame(outputs, i) for i in range(k + 1)]

    def prop_ok(fr: dict[str, z3.BoolRef]) -> z3.BoolRef:
        return z3.Not(z3.And(fr[a], fr[b]))

    # ── BASE: init(전부 OFF) → k 스텝. step 0..k 어디서든 P 위반 시 도달가능 위반.
    base = z3.Solver()
    base.add(*[z3.Not(frames[0][o]) for o in outputs])  # init
    for step in range(k):
        base.add(*_trans_at(eqs, outputs, out_set, frames[step], frames[step + 1], step))
    base.push()
    base.add(z3.Or(*[z3.And(fr[a], fr[b]) for fr in frames]))
    if base.check() == z3.sat:
        model = base.model()
        ce = _model_str(model)
        return VerificationIssue(
            code="INTERLOCK",
            severity="error",
            message=(
                f"인터락 위반(k-귀납, k={k}): '{a}' 와 '{b}' 가 초기상태에서 "
                f"{k}스캔 내 동시에 켜질 수 있습니다. ({reason})"
            ),
            counterexample=ce,
        )
    base.pop()

    # ── STEP: 서로 다른 연속 k 상태에서 P 성립 가정 → k+1 에서 P 깨짐 가능?
    step_solver = z3.Solver()
    for step in range(k):
        step_solver.add(
            *_trans_at(eqs, outputs, out_set, frames[step], frames[step + 1], step + 100)
        )
    for i in range(k):
        step_solver.add(prop_ok(frames[i]))  # 가정: 0..k-1 에서 성립
    step_solver.add(*_distinct_states(frames[:k], outputs))  # simple-path 강화
    step_solver.add(z3.And(frames[k][a], frames[k][b]))  # k 에서 위반?
    if step_solver.check() == z3.unsat:
        return None  # 귀납 성공 → 모든 도달 스캔에서 상호배제 증명
    # step 실패: base 는 안전이므로 1-스텝 검사와 동일 강도의 보수적 경고만 남긴다.
    return VerificationIssue(
        code="INTERLOCK_KIND",
        severity="warning",
        message=(
            f"인터락 k-귀납 미증명(k={k}): '{a}'/'{b}' 의 상호배제를 k={k} 로 "
            f"증명하지 못했습니다. ⚠ 안전을 보장하지 않습니다 — k 를 높이거나 "
            f"가상 PLC 시뮬레이션으로 반드시 확인하세요(초기 {k}스캔 내 위반은 없음). "
            f"({reason})"
        ),
    )


def _at_most_one(group_vars: list[z3.BoolRef]) -> z3.BoolRef:
    """그룹 내 ON 변수가 ≤1 (at-most-one / one-hot 상한) 임을 나타내는 z3 식.

    어떤 두 변수도 동시에 True 가 아님 = 모든 쌍에 대해 ¬(vi ∧ vj). 빈/단일 그룹은 항진.
    """
    if len(group_vars) < 2:
        return z3.BoolVal(True)
    pair_constraints = [
        z3.Not(z3.And(group_vars[i], group_vars[j]))
        for i in range(len(group_vars))
        for j in range(i + 1, len(group_vars))
    ]
    return z3.And(*pair_constraints)


def derive_mutex_groups(spec: StateMachineSpec) -> list[list[str]]:
    """인터락 쌍들의 합집합(연결요소)에서 ≥3개 출력의 상호배제 그룹을 유도한다.

    인터락 그래프의 *연결요소* 가 크기 3 이상이고 그 요소가 *완전그래프(clique)* —
    즉 요소 안 모든 쌍이 명시 인터락 — 일 때만 한 그룹으로 채택한다. 일부 쌍만
    인터락된 요소를 전원-배타로 격상하면 명세에 없는 성질을 강요해 거짓 양성이 되므로,
    설계자가 분명히 one-hot 의도를 선언한(모든 쌍 인터락) 경우로 한정한다. 크기 2 요소는
    기존 쌍 검사가 담당하므로 제외한다. 출력 순서는 결정론(정렬)을 따른다.
    """
    if not spec.interlocks:
        return []
    order: list[str] = []
    seen: set[str] = set()
    adj: dict[str, set[str]] = {}
    pairset: set[frozenset[str]] = set()
    for lock in spec.interlocks:
        a, b = lock.output_a, lock.output_b
        if a == b:
            continue
        for s in (a, b):
            if s not in seen:
                seen.add(s)
                order.append(s)
                adj[s] = set()
        adj[a].add(b)
        adj[b].add(a)
        pairset.add(frozenset((a, b)))

    visited: set[str] = set()
    groups: list[list[str]] = []
    for start in order:
        if start in visited:
            continue
        comp: list[str] = []
        stack = [start]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            comp.append(node)
            for nbr in adj[node]:
                if nbr not in visited:
                    stack.append(nbr)
        if len(comp) < 3:
            continue  # 크기 2 는 쌍 검사가 담당
        is_clique = all(
            frozenset((comp[i], comp[j])) in pairset
            for i in range(len(comp))
            for j in range(i + 1, len(comp))
        )
        if is_clique:
            groups.append(sorted(comp))  # 결정론적 순서
    return groups


def _kinduction_group(
    eqs: dict[str, str],
    outputs: list[str],
    out_set: set[str],
    group: list[str],
    k: int,
) -> VerificationIssue | None:
    """단일 상호배제 그룹(≥2 출력)에 대한 at-most-one k-귀납.

    위반(error, 동시 ON 출력 집합을 반례로)/증명불가(warning)/증명(None).
    전이계·스캔 의미론은 ``_kinduction_pair`` 와 동일(같은 ``_trans_at``) 이므로,
    쌍 검사가 건전하면 그룹 검사도 동일 추상화 위에서 건전하다.
    """
    present = [g for g in group if g in eqs]
    if len(present) < 2:
        return None  # 검사할 게 없음
    frames = [_frame(outputs, i) for i in range(k + 1)]

    def prop_ok(fr: dict[str, z3.BoolRef]) -> z3.BoolRef:
        return _at_most_one([fr[g] for g in present])

    def viol(fr: dict[str, z3.BoolRef]) -> z3.BoolRef:
        return z3.Not(prop_ok(fr))

    # ── BASE: init(전부 OFF) → k 스텝. 어느 스텝에서든 둘 이상 ON 이면 도달가능 위반.
    base = z3.Solver()
    base.add(*[z3.Not(frames[0][o]) for o in outputs])
    for step in range(k):
        base.add(*_trans_at(eqs, outputs, out_set, frames[step], frames[step + 1], step))
    base.push()
    base.add(z3.Or(*[viol(fr) for fr in frames]))
    if base.check() == z3.sat:
        model = base.model()
        ce = _group_counterexample(model, frames, present)
        return VerificationIssue(
            code="GROUP_MUTEX",
            severity="error",
            message=(
                f"그룹 상호배제 위반(k-귀납, k={k}): 출력 {{{', '.join(present)}}} 중 "
                f"둘 이상이 초기상태에서 {k}스캔 내 동시에 켜질 수 있습니다."
            ),
            counterexample=ce,
        )
    base.pop()

    # ── STEP: 서로 다른 연속 k 상태에서 P 성립 가정 → k 에서 P 깨짐 가능?
    step_solver = z3.Solver()
    for step in range(k):
        step_solver.add(
            *_trans_at(eqs, outputs, out_set, frames[step], frames[step + 1], step + 200)
        )
    for i in range(k):
        step_solver.add(prop_ok(frames[i]))
    step_solver.add(*_distinct_states(frames[:k], outputs))
    step_solver.add(viol(frames[k]))
    if step_solver.check() == z3.unsat:
        return None  # 귀납 성공 → 모든 도달 스캔에서 at-most-one 증명
    return VerificationIssue(
        code="GROUP_MUTEX_KIND",
        severity="warning",
        message=(
            f"그룹 상호배제 k-귀납 미증명(k={k}): 출력 {{{', '.join(present)}}} 의 "
            f"at-most-one 을 k={k} 로 증명하지 못했습니다. ⚠ 안전을 보장하지 않습니다 — "
            f"k 를 높이거나 가상 PLC 시뮬레이션으로 확인하세요(초기 {k}스캔 내 위반은 없음)."
        ),
    )


def _group_counterexample(
    model: z3.ModelRef, frames: list[dict[str, z3.BoolRef]], group: list[str]
) -> str:
    """반례를 '동시 ON 된 출력 집합' 으로 직렬화한다(결정론: 스텝·이름 정렬).

    base 반례 모델에서 그룹 내 둘 이상이 동시에 True 인 *첫* 스텝을 찾아 그 ON 집합을
    적는다. 못 찾으면(이론상) 전체 모델 직렬화로 폴백.
    """
    for step, fr in enumerate(frames):
        on = sorted(
            g for g in group if z3.is_true(model.eval(fr[g], model_completion=True))
        )
        if len(on) >= 2:
            return f"step={step}, 동시 ON={{{', '.join(on)}}}"
    return _model_str(model)


def check_group_mutex_kinduction(
    spec: StateMachineSpec,
    st_code: str,
    *,
    groups: list[list[str]] | None = None,
    k: int = 3,
) -> list[VerificationIssue]:
    """≥3개 출력 그룹의 at-most-one(one-hot 상한)을 **k-귀납**으로 증명한다.

    ``groups`` 가 None 이면 인터락 쌍들의 합집합(clique 연결요소, ``derive_mutex_groups``)
    에서 그룹을 유도한다. 명시 그룹을 주면 그대로 검사한다(쌍 인터락이 없어도 됨).
    전이계는 쌍 인터락 검사와 동일하므로 *쌍 검사가 건전하면 그룹 검사도 건전* 하다
    (동일 ``_trans_at`` 스캔 의미론 재사용). base 위반은 error(동시 ON 집합 반례),
    step-only 미증명은 보수적 warning(1-스텝 강도 약화 금지).
    """
    if not _HAS_Z3:
        return []
    if k < 1:
        k = 1
    use_groups = groups if groups is not None else derive_mutex_groups(spec)
    if not use_groups:
        return []
    outputs, eqs = _build_transition_system(st_code)
    out_set = set(outputs)
    issues: list[VerificationIssue] = []
    for group in use_groups:
        try:
            issue = _kinduction_group(eqs, outputs, out_set, group, k)
        except ValueError:
            continue  # 비불리언 토큰 등 → 이 그룹 건너뜀
        if issue is not None:
            issues.append(issue)
    return issues


def proven_safe_groups(
    spec: StateMachineSpec,
    st_code: str,
    *,
    groups: list[list[str]] | None = None,
    k: int = 3,
) -> list[list[str]]:
    """k-귀납으로 at-most-one 이 *증명된* 그룹만 (결정론 순서로) 반환한다(positive proof only)."""
    if not _HAS_Z3:
        return []
    if k < 1:
        k = 1
    use_groups = groups if groups is not None else derive_mutex_groups(spec)
    if not use_groups:
        return []
    outputs, eqs = _build_transition_system(st_code)
    out_set = set(outputs)
    proven: list[list[str]] = []
    for group in use_groups:
        try:
            issue = _kinduction_group(eqs, outputs, out_set, group, k)
        except ValueError:
            continue
        if issue is None:
            present = [g for g in group if g in eqs]
            if len(present) >= 2:
                proven.append(sorted(present))
    return proven


def _model_str(model: z3.ModelRef) -> str:
    """z3 모델을 결정론적(이름 정렬) 문자열로 직렬화 — 비결정성 누출 방지."""
    return ", ".join(
        f"{d.name()}={model[d]}" for d in sorted(model.decls(), key=lambda d: d.name())
    )


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


def check_timers_counters(spec: StateMachineSpec) -> list[VerificationIssue]:
    """타이머/카운터 명세 위생 검사(경고 수준)."""
    issues: list[VerificationIssue] = []
    for t in spec.timers:
        if t.preset_ms <= 0:
            issues.append(VerificationIssue(
                code="TIMER_PRESET", severity="warning",
                message=f"타이머 '{t.name}' 프리셋이 0 이하입니다."))
        if not t.enable_condition.strip():
            issues.append(VerificationIssue(
                code="TIMER_ENABLE", severity="warning",
                message=f"타이머 '{t.name}' 의 IN(인에이블) 조건이 비어있습니다."))
    for c in spec.counters:
        if c.preset <= 0:
            issues.append(VerificationIssue(
                code="COUNTER_PRESET", severity="warning",
                message=f"카운터 '{c.name}' PV 가 0 이하입니다."))
        if not c.reset_condition.strip():
            issues.append(VerificationIssue(
                code="COUNTER_RESET", severity="warning",
                message=f"카운터 '{c.name}' 리셋 조건이 없습니다(누적 위험)."))
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


_KIND_DEFAULT_K = 3


def verify(
    spec: StateMachineSpec, st_code: str, *, kinduction: bool = True, k: int = _KIND_DEFAULT_K
) -> VerificationReport:
    """검사를 합산해 리포트를 만든다. error 가 있으면 passed=False.

    인터락은 (1) 명세-조건 Z3, (2) 합성 ST 1-스텝 귀납(빠른 경로/폴백),
    (3) 합성 ST k-귀납(기본 on)으로 다층 검사한다. k-귀납 base 위반은 error,
    증명불가(step-only)는 보수적 warning 으로 1-스텝 강도를 약화시키지 않는다.
    """
    issues: list[VerificationIssue] = []
    # 합성 ST 의 k-귀납으로 상호배제가 증명된 쌍은 스펙수준 거짓양성에서 제외한다.
    proven = proven_safe_pairs(spec, st_code, k=k) if kinduction else frozenset()
    issues.extend(check_double_coils(st_code))
    issues.extend(check_interlocks_z3(spec, skip_pairs=proven))
    issues.extend(check_interlocks_st(spec, st_code))  # 1-스텝 빠른 경로/폴백
    if kinduction:
        issues.extend(check_interlocks_kinduction(spec, st_code, k=k))
        # 인터락 쌍의 합집합(clique)이 ≥3 출력 one-hot 그룹이면 at-most-one 도 증명한다.
        issues.extend(check_group_mutex_kinduction(spec, st_code, k=k))
    issues.extend(check_reachability(spec))
    issues.extend(check_timers_counters(spec))

    passed = not any(i.severity == "error" for i in issues)
    report = VerificationReport(issues=issues, passed=passed)

    if report.has_errors:
        fixes: list[str] = []
        codes = {i.code for i in issues if i.severity == "error"}
        if "DOUBLE_COIL" in codes:
            fixes.append("이중 코일을 M 릴레이로 분리한 뒤 OR 로 병합하세요.")
        if "INTERLOCK" in codes:
            fixes.append("상호배타 출력의 ON 조건에 상대 출력의 NOT 조건을 추가하세요.")
        if "GROUP_MUTEX" in codes:
            fixes.append(
                "one-hot 그룹의 각 출력 ON 조건에 그룹 내 다른 모든 출력의 NOT 조건을 "
                "추가하세요(동시 ≤1 보장)."
            )
        if "DEADLOCK" in codes:
            fixes.append("초기 상태를 1개 지정하세요(is_initial=True).")
        report = report.model_copy(update={"suggested_fix": " ".join(fixes)})

    return report
