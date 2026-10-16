"""Тесты дифференциальных уравнений (I): команда ``diff_eq``.

``y′ = f(x, y)`` (узел ``PRIME``); вид шага — по классификации: разделяющиеся
переменные (``diff_eq_solve_by_separation``), линейное (``diff_eq_solve_linear``),
иначе ``diff_eq_solve``. Ответ — ``y = …``; с аргументами ``[x₀, y₀]`` — частное
решение (``diff_eq_use_init_condition``, ``diff_eq_find_particular``).
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import SolveError, solve


def _vertical(source: str, args: list[str] | None = None) -> CoreSolverVerticalResult:
    vertical = solve(
        parse_protocol(source),
        command="diff_eq",
        args=[parse_protocol(arg) for arg in args or []],
    ).result.vertical()
    assert vertical is not None
    return vertical


def step_keys(source: str, args: list[str] | None = None) -> list[str]:
    return [sub.description.type for step in _vertical(source, args).steps for sub in step.substeps]


def answer(source: str, args: list[str] | None = None) -> CoreNode:
    solution = _vertical(source, args).solution
    assert solution is not None
    return solution


class TestDiffEq:
    def test_separation(self) -> None:
        source = "{=({prime({y})},{y})}"
        assert step_keys(source) == ["diff_eq_solve_by_separation", "diff_eq_write_general_sol"]
        solution = answer(source)
        assert solution.type is T.EQUALS and solution.children[0].value == "y"

    def test_separation_polynomial(self) -> None:
        assert answer("{=({prime({y})},{x^2})}").children[1].type is T.ADD

    def test_linear(self) -> None:
        source = "{=({prime({y})},{x+y})}"
        assert step_keys(source) == ["diff_eq_solve_linear", "diff_eq_write_general_sol"]

    def test_initial_condition(self) -> None:
        source = "{=({prime({y})},{y})}"
        assert step_keys(source, ["{0}", "{1}"]) == [
            "diff_eq_use_init_condition",
            "diff_eq_find_particular",
        ]
        # y′ = y, y(0) = 1 -> y = eˣ (константа определена).
        assert answer(source, ["{0}", "{1}"]).children[1].type is T.EXP

    def test_second_order(self) -> None:
        node = CoreNode.node(
            T.EQUALS,
            CoreNode.node(T.DERIVATION2_PRIME, CoreNode.variable("y")),
            CoreNode.constant("0"),
        )
        vertical = solve(node, command="diff_eq").result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.children[1].type is T.ADD

    def test_not_equation(self) -> None:
        with pytest.raises(SolveError):
            solve(parse_protocol("{y}"), command="diff_eq")

    def test_no_derivative(self) -> None:
        with pytest.raises(SolveError):
            solve(parse_protocol("{=({y},{x})}"), command="diff_eq")


class TestDiffEqWithoutCommand:
    """Уравнения с y′/y″ вводит клавиатура напрямую — команда не нужна."""

    @pytest.mark.parametrize(
        ("source", "first_step"),
        [
            ("{=({prime({y})},{y})}", "diff_eq_solve_by_separation"),
            ("{=({prime({y})},{x+y})}", "diff_eq_solve_linear"),
            ("{=({derivation2_prime({y})},{y})}", "diff_eq_solve"),
        ],
    )
    def test_auto_routing(self, source: str, first_step: str) -> None:
        vertical = solve(parse_protocol(source)).result.vertical()
        assert vertical is not None and vertical.solution is not None
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        assert keys[0] == first_step
        assert vertical.solution.type is T.EQUALS
        assert vertical.solution.children[0].value == "y"
