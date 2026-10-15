"""Тесты модуля, знака и целой части.

Проверяются точные значения, снятие модуля/знака при заведомо
неотрицательном аргументе, символьные правила целой части и сохранение
узла, когда знак неизвестен.
"""

from __future__ import annotations

from pathlib import Path

import sympy

from mymath_backend import CoreNode, load_explanations
from mymath_backend import CoreNodeType as T
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.solver import registered_types, solve
from mymath_backend.solver.sympy_bridge import to_sympy

EXPLANATIONS = Path(__file__).resolve().parents[2] / "truth" / "data" / "explanations.json"

x = sympy.Symbol("x")


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def var() -> CoreNode:
    return CoreNode.variable("x")


def node(t: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(t, *children)


def neg(child: CoreNode) -> CoreNode:
    return node(T.NEGATIVE, child)


def square() -> CoreNode:
    return node(T.POWER, var(), c("2"))


def solution_of(problem: CoreNode) -> CoreNode:
    vertical = solve(problem).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution


def value_of(problem: CoreNode) -> sympy.Expr:
    return to_sympy(solution_of(problem))


def step_keys(problem: CoreNode) -> list[str]:
    vertical = solve(problem).result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


class TestAbsolute:
    def test_negative_number(self) -> None:
        assert value_of(node(T.ABS, neg(c("5")))) == 5

    def test_positive_number(self) -> None:
        assert value_of(node(T.ABS, c("3"))) == 3

    def test_zero(self) -> None:
        assert value_of(node(T.ABS, c("0"))) == 0

    def test_fraction(self) -> None:
        assert value_of(node(T.ABS, neg(node(T.FRACTION, c("3"), c("4"))))) == sympy.Rational(3, 4)

    def test_pi_is_removed(self) -> None:
        problem = node(T.ABS, c("π"))
        assert value_of(problem) == sympy.pi
        assert step_keys(problem) == ["abs_pos"]

    def test_square_is_nonnegative(self) -> None:
        problem = node(T.ABS, square())
        result = solution_of(problem)
        assert result.type is T.POWER
        assert step_keys(problem) == ["abs_pos"]

    def test_unknown_sign_is_kept(self) -> None:
        problem = node(T.ABS, var())
        assert solution_of(problem).structural_eq(problem)
        assert step_keys(problem) == []

    def test_negative_variable_becomes_modulus(self) -> None:
        # |-x| = |x|
        problem = node(T.ABS, neg(var()))
        assert value_of(problem) == sympy.Abs(x)
        assert step_keys(problem) == ["abs"]


class TestSign:
    def test_positive(self) -> None:
        assert value_of(node(T.SIGN, c("5"))) == 1

    def test_negative(self) -> None:
        assert value_of(node(T.SIGN, neg(c("3")))) == -1

    def test_zero(self) -> None:
        assert value_of(node(T.SIGN, c("0"))) == 0

    def test_pi(self) -> None:
        assert value_of(node(T.SIGN, c("π"))) == 1

    def test_square_is_one(self) -> None:
        # Вне нуля: знак неотрицательного выражения равен 1.
        problem = node(T.SIGN, square())
        assert value_of(problem) == 1
        assert step_keys(problem) == ["find_sign"]

    def test_unknown_is_kept(self) -> None:
        problem = node(T.SIGN, var())
        assert solution_of(problem).structural_eq(problem)


class TestFloor:
    def test_positive_fraction(self) -> None:
        assert value_of(node(T.FLOOR, c("2.7"))) == 2

    def test_negative_fraction(self) -> None:
        assert value_of(node(T.FLOOR, neg(c("1.5")))) == -2

    def test_pi(self) -> None:
        assert value_of(node(T.FLOOR, c("π"))) == 3

    def test_integer_shift_moves_out(self) -> None:
        # ⌊x + 2⌋ = ⌊x⌋ + 2
        problem = node(T.FLOOR, node(T.ADD, var(), c("2")))
        assert value_of(problem) == sympy.floor(x) + 2

    def test_unknown_is_kept(self) -> None:
        problem = node(T.FLOOR, var())
        assert solution_of(problem).structural_eq(problem)


class TestWithArithmetic:
    def test_abs_plus_one(self) -> None:
        problem = node(T.ADD, node(T.ABS, neg(c("5"))), c("1"))
        assert value_of(problem) == 6
        assert step_keys(problem) == ["abs", "add"]


class TestAbsEquations:
    def roots_of(self, problem: CoreNode) -> set[sympy.Expr]:
        solution = solution_of(problem)
        equations = solution.children if solution.type is T.LIST else [solution]
        return {sympy.simplify(to_sympy(eq.children[1])) for eq in equations}

    def test_two_roots(self) -> None:
        problem = node(T.EQUALS, node(T.ABS, var()), c("3"))
        assert self.roots_of(problem) == {-3, 3}
        assert step_keys(problem) == ["eq_abs_branch", "quad_final_single"]

    def test_fraction_root(self) -> None:
        problem = node(T.EQUALS, node(T.ABS, var()), node(T.FRACTION, c("1"), c("2")))
        assert self.roots_of(problem) == {sympy.Rational(-1, 2), sympy.Rational(1, 2)}

    def test_linear_argument(self) -> None:
        argument = node(T.SUBTRACT, node(T.MULTIPLY_IMPLICIT, c("2"), var()), c("3"))
        problem = node(T.EQUALS, node(T.ABS, argument), c("5"))
        assert self.roots_of(problem) == {-1, 4}

    def test_negative_right_has_no_solution(self) -> None:
        problem = node(T.EQUALS, node(T.ABS, var()), neg(c("2")))
        assert solution_of(problem).type is T.EMPTY
        assert step_keys(problem) == ["false_statement_solve"]

    def test_zero_right_single_root(self) -> None:
        problem = node(T.EQUALS, node(T.ABS, var()), c("0"))
        assert self.roots_of(problem) == {0}

    def test_plain_equation_is_untouched(self) -> None:
        problem = node(
            T.EQUALS,
            node(T.ADD, node(T.MULTIPLY_IMPLICIT, c("2"), var()), c("3")),
            c("7"),
        )
        assert step_keys(problem) == ["move", "eq_linar_divide_both_sides"]

    def test_variable_right(self) -> None:
        # |x - 1| = x -> x = 1/2.
        argument = node(T.SUBTRACT, var(), c("1"))
        problem = node(T.EQUALS, node(T.ABS, argument), var())
        assert self.roots_of(problem) == {sympy.Rational(1, 2)}

    def test_quadratic_right(self) -> None:
        # |x| = x^2 - 2 -> x = ±2.
        right = node(T.SUBTRACT, node(T.POWER, var(), c("2")), c("2"))
        problem = node(T.EQUALS, node(T.ABS, var()), right)
        assert self.roots_of(problem) == {-2, 2}


class TestExplanationKeys:
    def test_keys_exist(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        for key in ("abs", "abs_pos", "find_sign", "calculate_floor", "eq_abs_branch"):
            assert key in explanations
            assert explanations.arity(key) == 0
            assert "ARG" not in (explanations.raw_template(key, DEFAULT_LOCALE) or "")


class TestRegistration:
    def test_registered(self) -> None:
        assert {T.ABS, T.SIGN, T.FLOOR} <= registered_types()
