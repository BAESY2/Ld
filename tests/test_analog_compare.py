"""아날로그 1단계 — 수치 비교(Cmp) 파싱·시뮬레이션 테스트 (LLM/키 불필요).

범위: 비교식은 시뮬레이션 전용. 래더(DNF) 변환·합성기 출력에는 아직 등장하지
않으며, to_dnf 는 명시적으로 거부한다(2단계에서 비교 접점으로 확장 예정).
"""

from __future__ import annotations

import pytest

from app.boolexpr import Cmp, Not, parse, to_dnf
from app.simulator import simulate

HYST_ST = "PUMP := ((LEVEL < 300) OR PUMP) AND NOT ((LEVEL >= 700));"


class TestCmpParse:
    def test_basic_comparison(self) -> None:
        assert parse("LEVEL < 300") == Cmp("LEVEL", "<", 300)
        assert parse("TEMP >= 80") == Cmp("TEMP", ">=", 80)
        assert parse("N = 5") == Cmp("N", "=", 5)
        assert parse("N <> 5") == Cmp("N", "<>", 5)

    def test_mirrored_literal_normalizes_to_var_lhs(self) -> None:
        assert parse("300 > LEVEL") == Cmp("LEVEL", "<", 300)
        assert parse("80 <= TEMP") == Cmp("TEMP", ">=", 80)

    def test_comparison_inside_boolean_expr(self) -> None:
        node = parse("RUN AND NOT (LEVEL >= 700)")
        assert isinstance(node.operands[1], Not)  # type: ignore[union-attr]

    def test_rejects_bad_operands(self) -> None:
        for bad in ["LEVEL <", "300 < 400", "LEVEL < ABC", "42"]:
            with pytest.raises(ValueError):
                parse(bad)



class TestAnalogSimulate:
    def test_hysteresis_fill_pump(self) -> None:
        res = simulate(
            HYST_ST,
            [(0, {"LEVEL": 500}), (200, {"LEVEL": 250}), (600, {"LEVEL": 750})],
            duration_ms=800,
            step_ms=100,
        )
        assert "LEVEL" in res.inputs
        trace = res.output_trace("PUMP")
        # 500: 양 임계 사이 + 비유지 → OFF / 250: <300 → ON(래치) / 750: >=700 → OFF
        assert trace[0] is False
        assert trace[2] is True and trace[5] is True
        assert trace[6] is False and trace[8] is False

    def test_self_hold_keeps_pump_between_thresholds(self) -> None:
        res = simulate(
            HYST_ST,
            [(0, {"LEVEL": 250}), (200, {"LEVEL": 500})],
            duration_ms=400,
            step_ms=100,
        )
        # 250 에서 켜진 뒤 500(임계 사이)에서도 자기유지로 유지
        assert res.output_trace("PUMP") == [True, True, True, True, True]

    def test_equality_comparison(self) -> None:
        res = simulate(
            "MATCH := COUNT = 5;",
            [(0, {"COUNT": 4}), (100, {"COUNT": 5}), (200, {"COUNT": 6})],
            duration_ms=200,
            step_ms=100,
        )
        assert res.output_trace("MATCH") == [False, True, False]

    def test_bool_inputs_still_work_alongside_analog(self) -> None:
        res = simulate(
            "OUT := EN AND (LEVEL > 100);",
            [(0, {"EN": True, "LEVEL": 50}), (100, {"LEVEL": 150})],
            duration_ms=200,
            step_ms=100,
        )
        assert res.output_trace("OUT") == [False, True, True]


class TestZ3Arithmetic:
    def test_disjoint_ranges_unsat(self) -> None:
        import z3

        from app.verifier import _to_z3

        bools: dict[str, z3.BoolRef] = {}
        ints: dict[str, z3.ArithRef] = {}
        a = _to_z3("LEVEL < 300", bools, ints)
        b = _to_z3("LEVEL >= 700", bools, ints)
        solver = z3.Solver()
        solver.add(z3.And(a, b))
        assert solver.check() == z3.unsat  # 범위 배타 — 동시 참 불가능 증명

    def test_overlapping_ranges_sat(self) -> None:
        import z3

        from app.verifier import _to_z3

        bools: dict[str, z3.BoolRef] = {}
        ints: dict[str, z3.ArithRef] = {}
        a = _to_z3("LEVEL < 500", bools, ints)
        b = _to_z3("LEVEL >= 300", bools, ints)
        solver = z3.Solver()
        solver.add(z3.And(a, b))
        assert solver.check() == z3.sat  # 300~499 에서 동시 참 가능

    def test_mixed_bool_and_cmp(self) -> None:
        import z3

        from app.verifier import _to_z3

        bools: dict[str, z3.BoolRef] = {}
        ints: dict[str, z3.ArithRef] = {}
        f = _to_z3("RUN AND NOT (LEVEL >= 700) AND LEVEL < 300", bools, ints)
        solver = z3.Solver()
        solver.add(f)
        assert solver.check() == z3.sat
        assert "RUN" in bools and "LEVEL" in ints


class TestCmpLadder:
    def test_dnf_emits_comparison_literal(self) -> None:
        terms = to_dnf(parse("RUN AND LEVEL < 300"))
        assert terms == [frozenset({("RUN", False), ("LEVEL < 300", False)})]

    def test_negated_comparison_becomes_inverted_literal(self) -> None:
        terms = to_dnf(parse("NOT (LEVEL < 300)"))
        assert terms == [frozenset({("LEVEL >= 300", False)})]

    def test_transpile_st_creates_comparison_contact(self) -> None:
        from app.transpiler import transpile_st

        lad = transpile_st(
            "PUMP := ((LEVEL < 300) OR PUMP) AND NOT ((LEVEL >= 700));",
            title="수위 채움 펌프",
        )
        syms = {
            e.symbol
            for r in lad.rungs
            for b in r.input_branches
            for e in b.elements
        }
        assert "LEVEL < 300" in syms
        assert "LEVEL < 700" in syms  # NOT(>=700)이 NNF 에서 <700 NO 접점으로 정규화
