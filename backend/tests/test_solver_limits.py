"""Тесты модуля пределов (подстановкой в конечной точке)."""

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


def var(name: str = "x") -> CoreNode:
    return CoreNode.variable(name)


def node(t: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(t, *children)


def limit(point: CoreNode, expression: CoreNode, t: T = T.LIMIT) -> CoreNode:
    return node(t, point, expression)


def value_of(problem: CoreNode) -> str | None:
    vertical = solve(problem).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution.value


def step_keys(problem: CoreNode) -> list[str]:
    vertical = solve(problem).result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


class TestLimits:
    def test_polynomial(self) -> None:
        problem = limit(c("2"), node(T.POWER, var(), c("2")))
        assert value_of(problem) == "4"
        assert step_keys(problem) == ["limit_solve"]

    def test_linear_expression(self) -> None:
        problem = limit(c("3"), node(T.ADD, node(T.MULTIPLY_IMPLICIT, c("2"), var()), c("1")))
        assert value_of(problem) == "7"

    def test_fraction_result(self) -> None:
        problem = limit(c("2"), node(T.DIVIDE, c("1"), var()))
        assert value_of(problem) == "1/2"

    def test_square_root(self) -> None:
        problem = limit(c("0"), node(T.ROOT2, node(T.ADD, var(), c("4"))))
        assert value_of(problem) == "2"

    def test_one_sided_uses_same_value(self) -> None:
        problem = limit(c("2"), node(T.POWER, var(), c("2")), T.LIMIT_LEFT)
        assert value_of(problem) == "4"

    def test_constant_expression(self) -> None:
        problem = limit(c("5"), c("7"))
        assert value_of(problem) == "7"


class TestUnsupported:
    def test_indeterminate_is_reported(self) -> None:
        numerator = node(T.SUBTRACT, node(T.POWER, var(), c("2")), c("1"))
        denominator = node(T.SUBTRACT, var(), c("1"))
        with pytest.raises(SolveError):
            solve(limit(c("1"), node(T.DIVIDE, numerator, denominator)))

    def test_point_at_infinity(self) -> None:
        with pytest.raises(SolveError, match="бесконечности"):
            solve(limit(c("∞"), node(T.POWER, var(), c("2"))))

    def test_unknown_function_is_rejected(self) -> None:
        with pytest.raises(SolveError, match="реализован"):
            solve(limit(c("0"), node(T.SIN, var())))


class TestExplanationKeys:
    def test_key_exists(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        assert "limit_solve" in explanations
        assert explanations.arity("limit_solve") == 0
        assert "ARG" not in (explanations.raw_template("limit_solve", DEFAULT_LOCALE) or "")


class TestRegistration:
    def test_registered(self) -> None:
        assert {T.LIMIT, T.LIMIT_LEFT, T.LIMIT_RIGHT} <= registered_types()
