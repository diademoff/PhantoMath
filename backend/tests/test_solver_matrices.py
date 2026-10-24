"""Тесты модуля определителей.

Элементы задаются в порядке «по строкам»; отдельно проверяется форма со
строками ``MATRIX_ROW``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sympy

from mymath_backend import CoreNode, load_explanations
from mymath_backend import CoreNodeType as T
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.solver import SolveError, registered_types, solve
from mymath_backend.solver.sympy_bridge import to_sympy

EXPLANATIONS = Path(__file__).resolve().parents[1] / "mymath_backend" / "data" / "explanations.json"


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def det(t: T, *elements: CoreNode) -> CoreNode:
    return CoreNode.node(t, *elements)


def row(*elements: CoreNode) -> CoreNode:
    return CoreNode.node(T.MATRIX_ROW, *elements)


def value_of(problem: CoreNode) -> str | None:
    vertical = solve(problem).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution.value


def step_keys(problem: CoreNode) -> list[str]:
    vertical = solve(problem).result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


class TestDeterminants:
    def test_2x2(self) -> None:
        problem = det(T.DETERMINANT2, c("1"), c("2"), c("3"), c("4"))
        assert value_of(problem) == "-2"
        assert step_keys(problem) == [
            "det2_determinant_rule",
            "mul_with_one",
            "mul",
            "calc_diff",
        ]

    def test_3x3_identity(self) -> None:
        problem = det(
            T.DETERMINANT3, c("1"), c("0"), c("0"), c("0"), c("1"), c("0"), c("0"), c("0"), c("1")
        )
        assert value_of(problem) == "1"

    def test_3x3_general(self) -> None:
        problem = det(
            T.DETERMINANT3, c("1"), c("2"), c("3"), c("4"), c("5"), c("6"), c("7"), c("8"), c("10")
        )
        assert value_of(problem) == "-3"

    def test_4x4_identity(self) -> None:
        values = [c("1" if i % 5 == 0 else "0") for i in range(16)]
        assert value_of(det(T.DETERMINANT4, *values)) == "1"

    def test_rows_form(self) -> None:
        problem = CoreNode.node(
            T.DETERMINANT,
            row(c("2"), c("0")),
            row(c("0"), c("3")),
        )
        assert value_of(problem) == "6"

    def test_elements_may_be_expressions(self) -> None:
        first = CoreNode.node(T.ADD, c("1"), c("1"))
        problem = det(T.DETERMINANT2, first, c("0"), c("0"), c("5"))
        assert value_of(problem) == "10"


class TestUnsupported:
    def test_not_square(self) -> None:
        problem = det(T.DETERMINANT2, c("1"), c("2"), c("3"))
        with pytest.raises(SolveError, match="квадратной"):
            solve(problem)

    def test_non_numeric_element_is_symbolic(self) -> None:
        # |1 x; 3 4| = 4 - 3x: letters in a determinant are solved symbolically.
        problem = det(T.DETERMINANT2, c("1"), CoreNode.variable("x"), c("3"), c("4"))
        solution = solve(problem).result.vertical().solution
        assert solution is not None
        x = sympy.Symbol("x")
        assert sympy.simplify(to_sympy(solution) - (4 - 3 * x)) == 0


class TestExplanationKeys:
    def test_keys_exist(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        for key in ("det2_calc", "det3_sarrus_eval", "det_laplace_rule_row_simple"):
            assert key in explanations
            assert explanations.arity(key) == 0
            assert "ARG" not in (explanations.raw_template(key, DEFAULT_LOCALE) or "")


class TestRegistration:
    def test_registered(self) -> None:
        assert {
            T.DETERMINANT,
            T.DETERMINANT2,
            T.DETERMINANT3,
            T.DETERMINANT3_SARRUS,
            T.DETERMINANT4,
            T.DETERMINANT5,
        } <= registered_types()


def test_lone_matrix_is_solved_as_its_determinant_in_four_rows() -> None:
    # a bare [[1,2],[3,4]] is notation, formula, products, difference.
    problem = CoreNode.node(T.MATRIX, row(c("1"), c("2")), row(c("3"), c("4")))
    vertical = solve(problem).result.vertical()
    assert vertical is not None and vertical.solution is not None
    assert vertical.solution.value == "-2"
    keys = [s.description.type for st in vertical.steps for s in st.substeps]
    assert keys == [
        "matrix_det_rewrite",
        "det2_determinant_rule",
        "mul_with_one",
        "mul",
        "calc_diff",
    ]


def test_lone_matrix_keeps_both_products_on_one_row() -> None:
    # Case ``mat_det`` row 3: «Любое выражение, умноженное на 1» | «Умножьте числа»
    # are two pages of one row, not two rows. Splitting them breaks parity.
    problem = CoreNode.node(T.MATRIX, row(c("1"), c("2")), row(c("3"), c("4")))
    vertical = solve(problem).result.vertical()
    assert vertical is not None
    assert [len(step.substeps) for step in vertical.steps] == [1, 1, 2, 1]


def test_matrix_arithmetic_in_an_expression_is_evaluated() -> None:
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    def rows(source: str) -> list[list[str]]:
        solution = solve(parse_protocol(source)).result.vertical().solution
        assert solution is not None
        return [[cell.value for cell in row.children] for row in solution.children]

    a = "mat({mat_row({1},{2})},{mat_row({3},{4})})"
    i = "mat({mat_row({1},{0})},{mat_row({0},{1})})"
    assert rows(f"{{{a}+{i}}}") == [["2", "2"], ["3", "5"]]
    assert rows(f"{{{a}^2}}") == [["7", "10"], ["15", "22"]]
    assert rows("{mat({mat_row({2},{1})},{mat_row({1},{1})})^-1}") == [["1", "-1"], ["-1", "2"]]


def test_matrix_sum_writes_every_cell_as_a_sum_then_evaluates_the_cells() -> None:
    # one row for the sums, one row with a stage per cell.
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    a = "mat({mat_row({1},{2})},{mat_row({3},{4})})"
    i = "mat({mat_row({1},{0})},{mat_row({0},{1})})"
    vertical = solve(parse_protocol(f"{{{a}+{i}}}")).result.vertical()
    assert vertical is not None
    assert [len(st.substeps) for st in vertical.steps] == [1, 4]
    keys = [s.description.type for st in vertical.steps for s in st.substeps]
    assert keys == ["matrix_add_elements", "add", "add_with_zero", "add_with_zero", "add"]
