"""불리언식 파서 + DNF(Sum-of-Products) 변환 (결정론, 의존성 없음).

ST 의 불리언식을 AST 로 파싱하고, 래더의 Sum-of-Products 표현을 위해
DNF(OR of ANDs of literals)로 정규화한다. 리터럴은 항상 변수 또는 NOT 변수다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# AST
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Const:
    value: bool


@dataclass(frozen=True)
class Not:
    operand: Node


@dataclass(frozen=True)
class And:
    operands: tuple[Node, ...]


@dataclass(frozen=True)
class Or:
    operands: tuple[Node, ...]


Node = Var | Const | Not | And | Or


# ---------------------------------------------------------------------------
# 파서 (우선순위 NOT > AND > OR)
# ---------------------------------------------------------------------------
# 식별자는 점표기 멤버 접근(예: T1.Q, C1.CV)을 단일 토큰으로 허용한다.
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


def parse(expr: str) -> Node:
    """불리언식 문자열을 AST 로 파싱한다."""
    tokens = _tokenize(expr)
    idx = 0

    def peek() -> str | None:
        return tokens[idx] if idx < len(tokens) else None

    def advance() -> str:
        nonlocal idx
        tok = tokens[idx]
        idx += 1
        return tok

    def parse_or() -> Node:
        nodes = [parse_and()]
        while (tok := peek()) is not None and tok.upper() == "OR":
            advance()
            nodes.append(parse_and())
        return nodes[0] if len(nodes) == 1 else Or(tuple(nodes))

    def parse_and() -> Node:
        nodes = [parse_not()]
        while (tok := peek()) is not None and tok.upper() == "AND":
            advance()
            nodes.append(parse_not())
        return nodes[0] if len(nodes) == 1 else And(tuple(nodes))

    def parse_not() -> Node:
        tok = peek()
        if tok is None:
            raise ValueError(f"식이 갑자기 끝남: {expr!r}")
        if tok.upper() == "NOT":
            advance()
            return Not(parse_not())
        if tok == "(":
            advance()
            node = parse_or()
            if peek() != ")":
                raise ValueError(f"닫는 괄호 누락: {expr!r}")
            advance()
            return node
        sym = advance()
        upper = sym.upper()
        if upper == "TRUE":
            return Const(True)
        if upper == "FALSE":
            return Const(False)
        return Var(sym)

    node = parse_or()
    if idx != len(tokens):
        raise ValueError(f"식 파싱 후 잔여 토큰: {tokens[idx:]!r}")
    return node


# ---------------------------------------------------------------------------
# DNF (Sum-of-Products)
# ---------------------------------------------------------------------------
# DNF 항 폭발 가드(지수 폭발로 인한 행 방지). 초과 시 ValueError.
_MAX_DNF_TERMS = 4096

# 리터럴: (이름, 부정여부)  예: ("A", False) = A,  ("B", True) = NOT B
Literal = tuple[str, bool]
# 곱항(AND term): 리터럴 집합.  None = 항상 거짓(FALSE)
Term = frozenset[Literal]


def _to_nnf(node: Node, negate: bool = False) -> Node:
    """NOT 을 변수 앞까지 밀어 넣는다(De Morgan)."""
    match node:
        case Var(name):
            return Not(Var(name)) if negate else Var(name)
        case Const(value):
            return Const(not value) if negate else Const(value)
        case Not(operand):
            return _to_nnf(operand, not negate)
        case And(operands):
            children = [_to_nnf(o, negate) for o in operands]
            return Or(tuple(children)) if negate else And(tuple(children))
        case Or(operands):
            children = [_to_nnf(o, negate) for o in operands]
            return And(tuple(children)) if negate else Or(tuple(children))
    raise TypeError(f"알 수 없는 노드: {node!r}")


def to_dnf(node: Node) -> list[Term]:
    """AST 를 DNF 항 목록으로 변환한다.

    반환: 곱항(Term) 리스트. 전체는 이들의 OR.
    빈 리스트 = 항상 거짓. [frozenset()] = 항상 참(빈 곱항).
    """
    nnf = _to_nnf(node)

    def dist(n: Node) -> list[Term]:
        match n:
            case Var(name):
                return [frozenset({(name, False)})]
            case Not(Var(name)):
                return [frozenset({(name, True)})]
            case Const(value):
                return [frozenset()] if value else []
            case Or(operands):
                terms: list[Term] = []
                for o in operands:
                    terms.extend(dist(o))
                return terms
            case And(operands):
                # 곱의 분배: 각 피연산자의 항들을 데카르트 곱
                acc: list[Term] = [frozenset()]
                for o in operands:
                    o_terms = dist(o)
                    new_acc: list[Term] = []
                    for a in acc:
                        for b in o_terms:
                            new_acc.append(a | b)
                    acc = new_acc
                    if not acc:  # 한쪽이 FALSE 면 전체 FALSE
                        return []
                    if len(acc) > _MAX_DNF_TERMS:
                        raise ValueError(
                            f"DNF 항이 {_MAX_DNF_TERMS}개를 초과했습니다(식이 너무 복잡). "
                            "패턴/LLM 경로로 분해하세요."
                        )
                return acc
        raise TypeError(f"NNF 위반 노드: {n!r}")

    raw = dist(nnf)

    # 모순 항(A AND NOT A) 제거 + 중복 제거(순서 보존)
    seen: set[Term] = set()
    result: list[Term] = []
    for term in raw:
        names = {lit[0] for lit in term}
        if any((name, False) in term and (name, True) in term for name in names):
            continue  # 모순
        if term in seen:
            continue
        seen.add(term)
        result.append(term)
    return result
