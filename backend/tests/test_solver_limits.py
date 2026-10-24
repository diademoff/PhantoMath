"""Тесты модуля пределов.

Предел считает sympy: проверяем конечные точки, бесконечность, односторонние
и раскрытие неопределённости. Значение сверяется через мост.
"""

from __future__ import annotations

from pathlib import Path

import sympy

from mymath_backend import CoreNode, load_explanations
from mymath_backend import CoreNodeType as T
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import registered_types, solve
from mymath_backend.solver.sympy_bridge import to_sympy

EXPLANATIONS = Path(__file__).resolve().parents[1] / "mymath_backend" / "data" / "explanations.json"


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def var(name: str = "x") -> CoreNode:
    return CoreNode.variable(name)


def node(t: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(t, *children)


def limit(point: CoreNode, expression: CoreNode, t: T = T.LIMIT) -> CoreNode:
    return node(t, point, expression)


def solution_of(problem: CoreNode) -> CoreNode:
    vertical = solve(problem).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution


def value_of(problem: CoreNode) -> str | None:
    return solution_of(problem).value


def vertical_of(problem: CoreNode) -> CoreSolverVerticalResult:
    vertical = solve(problem).result.vertical()
    assert vertical is not None
    return vertical


def step_keys(problem: CoreNode) -> list[str]:
    vertical = vertical_of(problem)
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


class TestLimits:
    def test_polynomial(self) -> None:
        problem = limit(c("2"), node(T.POWER, var(), c("2")))
        assert value_of(problem) == "4"
        assert step_keys(problem) == ["limit_solve", "pow"]  # the app rows

    def test_linear_expression(self) -> None:
        problem = limit(c("3"), node(T.ADD, node(T.MULTIPLY_IMPLICIT, c("2"), var()), c("1")))
        assert value_of(problem) == "7"

    def test_fraction_result(self) -> None:
        assert value_of(limit(c("2"), node(T.DIVIDE, c("1"), var()))) == "1/2"

    def test_square_root(self) -> None:
        assert value_of(limit(c("0"), node(T.ROOT2, node(T.ADD, var(), c("4"))))) == "2"

    def test_constant_expression(self) -> None:
        assert value_of(limit(c("5"), c("7"))) == "7"


class TestAdvanced:
    def test_indeterminate_is_resolved(self) -> None:
        # (x^2 - 1)/(x - 1) при x -> 1: раскрывается в 2.
        numerator = node(T.SUBTRACT, node(T.POWER, var(), c("2")), c("1"))
        denominator = node(T.SUBTRACT, var(), c("1"))
        problem = limit(c("1"), node(T.DIVIDE, numerator, denominator))
        assert value_of(problem) == "2"
        assert step_keys(problem) == [
            "lesson_calc_uncertainty_00",
            "lesson_calc_domain",
            "lesson_calc_factor",
            "lesson_calc_cancel_factor",
            "lesson_calc_substitute",
            "lesson_calc_simplify",
        ]

    def test_infinity_over_infinity(self) -> None:
        # (2x + 1)/(x − 3) при x -> ∞: неопределённость ∞/∞.
        numerator = node(T.ADD, node(T.MULTIPLY_IMPLICIT, c("2"), var()), c("1"))
        denominator = node(T.SUBTRACT, var(), c("3"))
        problem = limit(c("∞"), node(T.DIVIDE, numerator, denominator))
        assert value_of(problem) == "2"
        assert step_keys(problem) == [
            "lesson_calc_uncertainty_inf",
            "lesson_calc_divide_highest",
            "lesson_calc_inf_terms_zero",
            "lesson_calc_inf_deg_eq",
        ]

    def test_limit_at_infinity(self) -> None:
        problem = limit(c("∞"), node(T.POWER, var(), c("2")))
        assert value_of(problem) == "∞"

    def test_right_limit_of_reciprocal(self) -> None:
        problem = limit(c("0"), node(T.DIVIDE, c("1"), var()), T.LIMIT_RIGHT)
        assert value_of(problem) == "∞"

    def test_left_limit_of_reciprocal_is_negative_infinity(self) -> None:
        problem = limit(c("0"), node(T.DIVIDE, c("1"), var()), T.LIMIT_LEFT)
        assert to_sympy(solution_of(problem)) == -sympy.oo


def assert_does_not_exist(problem: CoreNode) -> None:
    """A non-existent limit is an answer with a verdict, not a 422."""
    vertical = vertical_of(problem)
    assert vertical.solution is None
    assert "limit_does_not_exist_msg" in step_keys(problem)


class TestDne:
    def test_nonexistent_limit(self) -> None:
        problem = limit(c("0"), node(T.SIN, node(T.DIVIDE, c("1"), var())))
        assert_does_not_exist(problem)

    def test_two_sided_reciprocal_diverges_by_sides(self) -> None:
        """Двусторонний предел 1/x в нуле: слева −∞, справа +∞ — не существует."""
        problem = limit(c("0"), node(T.DIVIDE, c("1"), var()), T.LIMIT)
        assert_does_not_exist(problem)

    def test_two_sided_agreeing_infinities(self) -> None:
        """1/x² в нуле: обе стороны +∞ — предел есть."""
        problem = limit(c("0"), node(T.DIVIDE, c("1"), node(T.POWER, var(), c("2"))), T.LIMIT)
        assert value_of(problem) == "∞"

    def test_two_sided_sign_jump(self) -> None:
        """|x|/x в нуле: слева −1, справа 1 — не существует."""
        problem = limit(c("0"), node(T.DIVIDE, node(T.ABS, var()), var()), T.LIMIT)
        assert_does_not_exist(problem)


class TestExplanationKeys:
    def test_key_exists(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        assert "limit_solve" in explanations
        assert explanations.arity("limit_solve") == 0
        assert "ARG" not in (explanations.raw_template("limit_solve", DEFAULT_LOCALE) or "")


class TestRegistration:
    def test_registered(self) -> None:
        assert {T.LIMIT, T.LIMIT_LEFT, T.LIMIT_RIGHT} <= registered_types()


def test_linear_limit_substitutes_then_evaluates_on_its_own_row() -> None:
    # lim x->3 (2x+1) is a substitution row and an evaluation row.
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    group = solve(parse_protocol("{lim({3},{2x+1})}")).result.groups[0]
    keys = [
        s["description"]["type"] for st in group.entries[0].result["steps"] for s in st["substeps"]
    ]
    assert keys == ["limit_solve", "calculate_direct"]


def test_inverse_power_at_infinity_quotes_one_law_on_one_row() -> None:
    # lim x->oo 1/x is a single "common limit" row.
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    group = solve(parse_protocol("{lim({inf},{frac({1},{x})})}")).result.groups[0]
    steps = group.entries[0].result["steps"]
    assert [s["description"]["type"] for st in steps for s in st["substeps"]] == ["limit_common"]


def test_sin_over_x_has_the_law_card_and_the_lhopital_card() -> None:
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    entries = solve(parse_protocol("{lim({0},{frac({sin({x})},{x})})}")).result.groups[0].entries
    shapes = [[len(st["substeps"]) for st in e.result["steps"]] for e in entries]
    assert shapes == [[1], [1, 2, 1, 1, 1]]
