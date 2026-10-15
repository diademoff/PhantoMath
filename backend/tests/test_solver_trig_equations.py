"""Тесты тригонометрических уравнений.

Проверяются общее решение сериями (``x = π/6 + 2πk``), тождество и
отсутствие решений, линейный аргумент, функции с двух сторон и отбор
корней на промежутке. Значение серии сверяется по смещению при ``k = 0``.
"""

from __future__ import annotations

from pathlib import Path

import sympy

from mymath_backend import CoreNode, load_explanations
from mymath_backend import CoreNodeType as T
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.solver import solve
from mymath_backend.solver.sympy_bridge import to_sympy

EXPLANATIONS = Path(__file__).resolve().parents[2] / "truth" / "data" / "explanations.json"

_K = sympy.Symbol("k")


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def x() -> CoreNode:
    return CoreNode.variable("x")


def node(t: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(t, *children)


def muli(a: CoreNode, b: CoreNode) -> CoreNode:
    return node(T.MULTIPLY_IMPLICIT, a, b)


def eq(a: CoreNode, b: CoreNode) -> CoreNode:
    return node(T.EQUALS, a, b)


def half() -> CoreNode:
    return node(T.FRACTION, c("1"), c("2"))


def solution_of(problem: CoreNode) -> CoreNode:
    vertical = solve(problem).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution


def step_keys(problem: CoreNode, interval: tuple[CoreNode, CoreNode] | None = None) -> list[str]:
    vertical = solve(problem, interval=interval).result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


def series_offsets(problem: CoreNode) -> set[sympy.Expr]:
    """Смещения серий (значение при ``k = 0``) -- для сверки ответа."""
    solution = solution_of(problem)
    equations = solution.children if solution.type is T.LIST else [solution]
    return {sympy.simplify(to_sympy(equation.children[1]).subs(_K, 0)) for equation in equations}


class TestGeneralSolution:
    def test_sine_two_series(self) -> None:
        problem = eq(node(T.SIN, x()), half())
        assert series_offsets(problem) == {sympy.pi / 6, 5 * sympy.pi / 6}
        assert step_keys(problem) == ["trig_general_sol"]

    def test_cosine_two_series(self) -> None:
        problem = eq(node(T.COS, x()), half())
        assert series_offsets(problem) == {sympy.pi / 3, 5 * sympy.pi / 3}

    def test_tangent_single_series(self) -> None:
        problem = eq(node(T.TAN, x()), c("1"))
        assert series_offsets(problem) == {sympy.pi / 4}

    def test_solution_is_equation_in_variable(self) -> None:
        solution = solution_of(eq(node(T.SIN, x()), half()))
        assert solution.type is T.LIST
        assert all(child.type is T.EQUALS for child in solution.children)
        assert all(child.children[0].value == "x" for child in solution.children)

    def test_linear_argument(self) -> None:
        problem = eq(node(T.SIN, muli(c("2"), x())), half())
        assert series_offsets(problem) == {sympy.pi / 12, 5 * sympy.pi / 12}

    def test_two_sided(self) -> None:
        problem = eq(node(T.SIN, x()), node(T.COS, x()))
        assert sympy.pi / 4 in series_offsets(problem)


class TestSpecialCases:
    def test_no_solution(self) -> None:
        problem = eq(node(T.SIN, x()), c("2"))
        assert solution_of(problem).type is T.EMPTY
        assert step_keys(problem) == ["false_statement_solve"]

    def test_identity(self) -> None:
        problem = eq(node(T.SIN, x()), node(T.SIN, x()))
        assert solution_of(problem).type is T.EMPTY
        assert step_keys(problem) == ["solutions_inf_many"]

    def test_polynomial_equation_is_untouched(self) -> None:
        problem = eq(node(T.ADD, muli(c("2"), x()), c("3")), c("7"))
        assert step_keys(problem) == ["move", "eq_linar_divide_both_sides"]


class TestInterval:
    def test_selects_roots(self) -> None:
        problem = eq(node(T.SIN, x()), half())
        interval = (c("0"), muli(c("2"), c("π")))
        solution = solve(problem, interval=interval).result.vertical()
        assert solution is not None and solution.solution is not None
        assert solution.solution.type is T.LIST
        assert len(solution.solution.children) == 2
        assert step_keys(problem, interval) == ["trig_general_sol", "trig_find_intervals_smpl"]

    def test_selected_values(self) -> None:
        problem = eq(node(T.SIN, x()), half())
        interval = (c("0"), muli(c("2"), c("π")))
        vertical = solve(problem, interval=interval).result.vertical()
        assert vertical is not None and vertical.solution is not None
        values = sorted(to_sympy(child.children[1]) for child in vertical.solution.children)
        assert values == [sympy.pi / 6, 5 * sympy.pi / 6]

    def test_empty_interval(self) -> None:
        problem = eq(node(T.SIN, x()), half())
        interval = (c("π"), muli(c("2"), c("π")))
        vertical = solve(problem, interval=interval).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.type is T.EMPTY


class TestExplanationKeys:
    def test_keys_exist(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        for key, arity in (
            ("trig_general_sol", 1),
            ("trig_find_intervals_smpl", 1),
        ):
            assert key in explanations
            assert explanations.arity(key) == arity
            assert "ARG" in (explanations.raw_template(key, DEFAULT_LOCALE) or "")
