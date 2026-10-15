"""Тесты вычисления значения выражения (R).

Узел ``EVALUATE_EXPRESSION`` — ``[выражение, значение]``; значение подставляется
в переменную выражения, шаг ``function_evaluate_expr``.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.solver import SolveError, solve


def run(source: str) -> tuple[list[str], CoreNode]:
    vertical = solve(parse_protocol(source)).result.vertical()
    assert vertical is not None and vertical.solution is not None
    keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
    return keys, vertical.solution


class TestEvaluateExpression:
    def test_polynomial(self) -> None:
        keys, solution = run("{eval_expr({x^2+1},{2})}")
        assert keys == ["function_evaluate_expr"]
        assert solution.value == "5"

    def test_linear(self) -> None:
        assert run("{evaluate_expr({2x+3},{5})}")[1].value == "13"

    def test_two_variables(self) -> None:
        problem = CoreNode.node(
            T.EVALUATE_EXPRESSION,
            CoreNode.node(T.ADD, CoreNode.variable("x"), CoreNode.variable("y")),
            CoreNode.constant("1"),
        )
        with pytest.raises(SolveError):
            solve(problem)
