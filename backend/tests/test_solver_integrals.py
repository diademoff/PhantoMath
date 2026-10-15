"""Тесты модуля интегралов.

Значение проверяется через sympy: результат переводится обратно и сравнивается
с ожидаемой первообразной/числом.
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

EXPLANATIONS = Path(__file__).resolve().parents[2] / "truth" / "data" / "explanations.json"

x = sympy.Symbol("x")


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def var(name: str = "x") -> CoreNode:
    return CoreNode.variable(name)


def node(t: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(t, *children)


def solution_of(problem: CoreNode) -> CoreNode:
    vertical = solve(problem).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution


def step_keys(problem: CoreNode) -> list[str]:
    vertical = solve(problem).result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


class TestIndefinite:
    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            (node(T.POWER, var(), c("2")), x**3 / 3),
            (node(T.ADD, node(T.MULTIPLY, c("2"), var()), c("3")), x**2 + 3 * x),
            (node(T.SIN, var()), -sympy.cos(x)),
            (node(T.DIVIDE, c("1"), var()), sympy.log(x)),
            (node(T.EXP, var()), sympy.exp(x)),
            (var(), x**2 / 2),
        ],
    )
    def test_antiderivative(self, expression: CoreNode, expected: sympy.Expr) -> None:
        result = solution_of(node(T.INTEGRAL, expression))
        assert sympy.simplify(to_sympy(result) - expected) == 0

    def test_step_key(self) -> None:
        problem = node(T.INTEGRAL, var())
        assert step_keys(problem) == ["integrate_calc"]


class TestDefinite:
    def test_polynomial(self) -> None:
        problem = node(T.INTEGRAL_DEFINITE, c("0"), c("1"), var())
        assert solution_of(problem).value == "1/2"

    def test_integer_area(self) -> None:
        problem = node(T.INTEGRAL_DEFINITE, c("0"), c("2"), node(T.MULTIPLY, c("3"), var()))
        assert solution_of(problem).value == "6"

    def test_sine_area(self) -> None:
        problem = node(T.INTEGRAL_DEFINITE, c("0"), c("π"), node(T.SIN, var()))
        assert solution_of(problem).value == "2"


class TestUnsupported:
    def test_no_elementary_antiderivative(self) -> None:
        problem = node(T.INTEGRAL, node(T.EXP, node(T.POWER, var(), c("2"))))
        with pytest.raises(SolveError, match="элементарн"):
            solve(problem)


class TestExplanationKeys:
    def test_key_exists(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        assert "integrate_calc" in explanations
        assert explanations.arity("integrate_calc") == 0
        assert "ARG" not in (explanations.raw_template("integrate_calc", DEFAULT_LOCALE) or "")


class TestRegistration:
    def test_registered(self) -> None:
        assert {T.INTEGRAL, T.INTEGRAL_DEFINITE} <= registered_types()
