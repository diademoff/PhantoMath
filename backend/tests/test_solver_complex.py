"""Тесты комплексных чисел.

Мнимая единица — константа ``i``. Re/Im/сопряжение и арифметика считаются
sympy; проверяем значения через мост.
"""

from __future__ import annotations

from pathlib import Path

import sympy

from mymath_backend import CoreNode, load_explanations
from mymath_backend import CoreNodeType as T
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.solver import registered_types, solve
from mymath_backend.solver.complex import contains_imaginary
from mymath_backend.solver.sympy_bridge import to_sympy

EXPLANATIONS = Path(__file__).resolve().parents[2] / "truth" / "data" / "explanations.json"

I_UNIT = sympy.I


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def i() -> CoreNode:
    return CoreNode.constant("i")


def node(t: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(t, *children)


def muli(a: CoreNode, b: CoreNode) -> CoreNode:
    return node(T.MULTIPLY_IMPLICIT, a, b)


def solution_of(problem: CoreNode) -> CoreNode:
    vertical = solve(problem).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution


def step_keys(problem: CoreNode) -> list[str]:
    vertical = solve(problem).result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


Z = node(T.ADD, c("1"), muli(c("2"), i()))


class TestParts:
    def test_real_part(self) -> None:
        problem = node(T.REAL, Z)
        assert solution_of(problem).value == "1"
        assert step_keys(problem) == ["complex_rewrite"]

    def test_imaginary_part(self) -> None:
        assert solution_of(node(T.IMAGINARY, Z)).value == "2"

    def test_conjugate(self) -> None:
        problem = node(T.CONJUGATE, Z)
        assert sympy.simplify(to_sympy(solution_of(problem)) - (1 - 2 * I_UNIT)) == 0
        assert step_keys(problem) == ["complex_conjugate"]


class TestArithmetic:
    def test_product_of_complex_numbers(self) -> None:
        problem = node(T.MULTIPLY, Z, node(T.SUBTRACT, c("3"), i()))
        result = solution_of(problem)
        assert sympy.simplify(to_sympy(result) - (5 + 5 * I_UNIT)) == 0
        assert step_keys(problem) == ["complex_convert_std_form"]

    def test_pure_imaginary(self) -> None:
        problem = node(T.MULTIPLY, i(), i())
        assert sympy.simplify(to_sympy(solution_of(problem)) - (-1)) == 0

    def test_contains_imaginary(self) -> None:
        assert contains_imaginary(Z)
        assert not contains_imaginary(c("2"))


class TestExplanationKeys:
    def test_keys_exist(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        for key in ("complex_rewrite", "complex_conjugate", "complex_convert_std_form"):
            assert key in explanations
            assert explanations.arity(key) == 0
            assert "ARG" not in (explanations.raw_template(key, DEFAULT_LOCALE) or "")


class TestRegistration:
    def test_registered(self) -> None:
        assert {T.REAL, T.IMAGINARY, T.CONJUGATE} <= registered_types()
