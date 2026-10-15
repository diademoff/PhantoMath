"""Тесты модуля производной.

Результат сравнивается структурно с ожидаемым деревом: так проверяется и
упрощение (нет лишних ``·1`` и ``+0``, коэффициент сведён), и сами правила.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mymath_backend import CoreNode, load_explanations
from mymath_backend import CoreNodeType as T
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.solver import SolveError, registered_types, solve

EXPLANATIONS = Path(__file__).resolve().parents[2] / "truth" / "data" / "explanations.json"


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def x() -> CoreNode:
    return CoreNode.variable("x")


def node(t: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(t, *children)


def muli(a: CoreNode, b: CoreNode) -> CoreNode:
    return node(T.MULTIPLY_IMPLICIT, a, b)


def derivative(expression: CoreNode) -> CoreNode:
    return node(T.DERIVATION1, expression)


def solution_of(expression: CoreNode) -> CoreNode:
    vertical = solve(derivative(expression)).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution


def step_keys(expression: CoreNode) -> list[str]:
    vertical = solve(derivative(expression)).result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


class TestRules:
    def test_constant(self) -> None:
        assert solution_of(c("5")).structural_eq(c("0"))

    def test_variable(self) -> None:
        assert solution_of(x()).structural_eq(c("1"))

    def test_other_variable_is_constant(self) -> None:
        # Две переменные: дифференцируем по первой (x), поэтому y — константа.
        assert solution_of(muli(x(), CoreNode.variable("y"))).structural_eq(CoreNode.variable("y"))

    def test_linear(self) -> None:
        assert solution_of(muli(c("2"), x())).structural_eq(c("2"))

    def test_power(self) -> None:
        assert solution_of(node(T.POWER, x(), c("2"))).structural_eq(muli(c("2"), x()))

    def test_polynomial_is_simplified(self) -> None:
        expression = node(T.ADD, muli(c("3"), node(T.POWER, x(), c("2"))), muli(c("2"), x()))
        expected = node(T.ADD, muli(c("6"), x()), c("2"))
        assert solution_of(expression).structural_eq(expected)

    def test_difference(self) -> None:
        expression = node(T.SUBTRACT, node(T.POWER, x(), c("3")), x())
        expected = node(T.SUBTRACT, muli(c("3"), node(T.POWER, x(), c("2"))), c("1"))
        assert solution_of(expression).structural_eq(expected)

    def test_quotient(self) -> None:
        expression = node(T.DIVIDE, c("1"), x())
        expected = node(T.FRACTION, c("-1"), node(T.POWER, x(), c("2")))
        assert solution_of(expression).structural_eq(expected)

    def test_sine(self) -> None:
        assert solution_of(node(T.SIN, x())).structural_eq(node(T.COS, x()))

    def test_cosine(self) -> None:
        assert solution_of(node(T.COS, x())).structural_eq(node(T.NEGATIVE, node(T.SIN, x())))

    def test_sine_with_chain_rule(self) -> None:
        expression = node(T.SIN, muli(c("2"), x()))
        expected = muli(c("2"), node(T.COS, muli(c("2"), x())))
        assert solution_of(expression).structural_eq(expected)

    def test_natural_log(self) -> None:
        assert solution_of(node(T.LN, x())).structural_eq(node(T.FRACTION, c("1"), x()))

    def test_exponential(self) -> None:
        assert solution_of(node(T.EXP, x())).structural_eq(node(T.EXP, x()))

    def test_square_root(self) -> None:
        expression = node(T.ROOT2, x())
        expected = node(
            T.FRACTION,
            c("1"),
            muli(c("2"), node(T.ROOT2, x())),
        )
        assert solution_of(expression).structural_eq(expected)


class TestSteps:
    def test_step_key(self) -> None:
        assert step_keys(x()) == ["find_derivative"]

    def test_header(self) -> None:
        vertical = solve(derivative(x())).result.vertical()
        assert vertical is not None
        assert [h.type for h in vertical.steps[0].step_headers] == ["derive_short"]


class TestUnsupported:
    def test_type_without_rule_is_rejected(self) -> None:
        with pytest.raises(SolveError, match="не поддерживается"):
            solve(derivative(node(T.SEC, x())))


class TestExplanationKeys:
    def test_keys_exist_with_matching_arity(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        for key in ("find_derivative", "derive_short"):
            assert key in explanations
            template = explanations.raw_template(key, DEFAULT_LOCALE) or ""
            assert explanations.arity(key) == 0
            assert "ARG" not in template


class TestRegistration:
    def test_registered(self) -> None:
        assert {T.DERIVATION, T.DERIVATION1} <= registered_types()
