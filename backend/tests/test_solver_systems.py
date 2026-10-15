"""Тесты модуля систем 2×2.

Уравнения системы строятся узлами (``EQUALS``), ответ — список ``x = …, y = …``.
Проверяются решение, порядок неизвестных, нелинейность и вырожденный случай
(нулевой определитель).
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


def var(name: str) -> CoreNode:
    return CoreNode.variable(name)


def node(t: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(t, *children)


def eq(left: CoreNode, right: CoreNode) -> CoreNode:
    return node(T.EQUALS, left, right)


def system(*equations: CoreNode) -> CoreNode:
    return node(T.SYSTEM, *equations)


def solution_map(problem: CoreNode) -> dict[str, str]:
    vertical = solve(problem).result.vertical()
    assert vertical is not None and vertical.solution is not None
    assert vertical.solution.type is T.LIST
    out: dict[str, str] = {}
    for equation in vertical.solution.children:
        out[equation.children[0].value or ""] = equation.children[1].value or ""
    return out


def step_keys(problem: CoreNode) -> list[str]:
    vertical = solve(problem).result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


class TestSolve:
    def test_simple_system(self) -> None:
        problem = system(
            eq(node(T.ADD, var("x"), var("y")), c("3")),
            eq(node(T.SUBTRACT, var("x"), var("y")), c("1")),
        )
        assert solution_map(problem) == {"x": "2", "y": "1"}

    def test_coefficients(self) -> None:
        problem = system(
            eq(
                node(
                    T.ADD,
                    node(T.MULTIPLY_IMPLICIT, c("2"), var("x")),
                    node(T.MULTIPLY_IMPLICIT, c("3"), var("y")),
                ),
                c("12"),
            ),
            eq(node(T.SUBTRACT, var("x"), var("y")), c("1")),
        )
        assert solution_map(problem) == {"x": "3", "y": "2"}

    def test_fraction_solution(self) -> None:
        problem = system(
            eq(node(T.ADD, var("x"), var("y")), c("1")),
            eq(node(T.SUBTRACT, var("x"), var("y")), c("0")),
        )
        assert solution_map(problem) == {"x": "1/2", "y": "1/2"}

    def test_single_step_with_header(self) -> None:
        problem = system(
            eq(node(T.ADD, var("x"), var("y")), c("3")),
            eq(node(T.SUBTRACT, var("x"), var("y")), c("1")),
        )
        assert step_keys(problem) == ["system_2x2_solve_elimination"]
        vertical = solve(problem).result.vertical()
        assert vertical is not None
        assert [h.type for h in vertical.steps[0].step_headers] == ["system_solve_short"]


class TestUnsupported:
    def test_parametric_solution(self) -> None:
        # Вырожденная система: бесконечно много решений.
        problem = system(
            eq(node(T.ADD, var("x"), var("y")), c("1")),
            eq(
                node(
                    T.ADD,
                    node(T.MULTIPLY_IMPLICIT, c("2"), var("x")),
                    node(T.MULTIPLY_IMPLICIT, c("2"), var("y")),
                ),
                c("2"),
            ),
        )
        with pytest.raises(SolveError, match="параметрическ"):
            solve(problem)


class TestExtended:
    def test_nonlinear(self) -> None:
        # xy = 1, x + y = 2 -> (1, 1).
        problem = system(
            eq(node(T.MULTIPLY, var("x"), var("y")), c("1")),
            eq(node(T.ADD, var("x"), var("y")), c("2")),
        )
        vertical = solve(problem).result.vertical()
        assert vertical is not None and vertical.solution is not None

    def test_three_unknowns(self) -> None:
        problem = system(
            eq(node(T.ADD, node(T.ADD, var("x"), var("y")), var("z")), c("6")),
            eq(node(T.SUBTRACT, var("x"), var("y")), c("0")),
            eq(node(T.SUBTRACT, var("y"), var("z")), c("0")),
        )
        assert solution_map(problem) == {"x": "2", "y": "2", "z": "2"}

    def test_one_unknown(self) -> None:
        problem = system(
            eq(node(T.ADD, var("x"), c("1")), c("3")),
            eq(node(T.SUBTRACT, var("x"), c("1")), c("1")),
        )
        vertical = solve(problem).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.children[1].value == "2"

    def test_three_equations(self) -> None:
        # Три уравнения с двумя неизвестными: решается через sympy.
        problem = system(
            eq(node(T.ADD, var("x"), var("y")), c("3")),
            eq(node(T.SUBTRACT, var("x"), var("y")), c("1")),
            eq(node(T.ADD, var("x"), c("1")), c("3")),
        )
        assert solution_map(problem) == {"x": "2", "y": "1"}


class TestExplanationKeys:
    def test_keys_exist(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        for key in ("system_2x2_solve_elimination", "system_solve_short"):
            assert key in explanations
            assert explanations.arity(key) == 0
            assert "ARG" not in (explanations.raw_template(key, DEFAULT_LOCALE) or "")


class TestRegistration:
    def test_registered(self) -> None:
        assert T.SYSTEM in registered_types()
