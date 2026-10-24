"""Тесты кусочно-заданных функций (R): команда ``piecewise_value``.

Узел ``PIECEWISE_DEFINITION`` — пары «выражение, условие»; значение в точке
берётся из первой пары с истинным условием.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.solver import SolveError, solve


def piecewise(expression1: CoreNode, condition1: CoreNode, *rest: CoreNode) -> CoreNode:
    return CoreNode.node(T.PIECEWISE_DEFINITION, expression1, condition1, *rest)


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def var(name: str = "x") -> CoreNode:
    return CoreNode.variable(name)


def run(problem: CoreNode, value: str) -> tuple[list[str], CoreNode]:
    vertical = solve(
        problem, command="piecewise_value", args=[parse_protocol(value)]
    ).result.vertical()
    assert vertical is not None and vertical.solution is not None
    keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
    return keys, vertical.solution


class TestPiecewiseValue:
    def test_first_branch(self) -> None:
        # f(x) = x², x < 0; x + 1, x ≥ 0. f(−2) = 4.
        problem = piecewise(
            CoreNode.node(T.POWER, var(), c("2")),
            CoreNode.node(T.LESS_THAN, var(), c("0")),
            CoreNode.node(T.ADD, var(), c("1")),
            CoreNode.node(T.GREATER_THAN_EQUAL, var(), c("0")),
        )
        keys, solution = run(problem, "{-2}")
        assert keys == ["function_evaluate", "function_evaluate_value"]
        assert solution.value == "4"

    def test_second_branch(self) -> None:
        problem = piecewise(
            CoreNode.node(T.POWER, var(), c("2")),
            CoreNode.node(T.LESS_THAN, var(), c("0")),
            CoreNode.node(T.ADD, var(), c("1")),
            CoreNode.node(T.GREATER_THAN_EQUAL, var(), c("0")),
        )
        assert run(problem, "{2}")[1].value == "3"

    def test_no_branch(self) -> None:
        problem = piecewise(
            var(),
            CoreNode.node(T.LESS_THAN, var(), c("0")),
            c("0"),
            CoreNode.node(T.GREATER_THAN, var(), c("10")),
        )
        with pytest.raises(SolveError, match="ни одно условие"):
            run(problem, "{5}")

    def test_requires_value(self) -> None:
        problem = piecewise(var(), CoreNode.node(T.LESS_THAN, var(), c("0")))
        with pytest.raises(SolveError):
            solve(problem, command="piecewise_value")
