"""Тесты слоя команд (CoreAction)."""

from __future__ import annotations

from pathlib import Path

import pytest
import sympy

from mymath_backend import CoreNode, load_explanations
from mymath_backend import CoreNodeType as T
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.solver import SolveError, solve
from mymath_backend.solver.sympy_bridge import to_sympy

EXPLANATIONS = Path(__file__).resolve().parents[2] / "truth" / "data" / "explanations.json"

x = sympy.Symbol("x")


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def var() -> CoreNode:
    return CoreNode.variable("x")


def node(t: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(t, *children)


def muli(a: CoreNode, b: CoreNode) -> CoreNode:
    return node(T.MULTIPLY_IMPLICIT, a, b)


def solution_of(problem: CoreNode, command: str) -> CoreNode:
    vertical = solve(problem, command=command).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution


def step_keys(problem: CoreNode, command: str) -> list[str]:
    vertical = solve(problem, command=command).result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


class TestCommands:
    def test_factor(self) -> None:
        problem = node(
            T.ADD, node(T.ADD, node(T.POWER, var(), c("2")), muli(c("2"), var())), c("1")
        )
        result = solution_of(problem, "factor")
        assert sympy.simplify(to_sympy(result) - (x + 1) ** 2) == 0
        assert step_keys(problem, "factor") == ["factorise_call"]

    def test_expand(self) -> None:
        problem = node(T.POWER, node(T.ADD, var(), c("1")), c("2"))
        result = solution_of(problem, "expand")
        assert sympy.simplify(to_sympy(result) - (x**2 + 2 * x + 1)) == 0
        assert step_keys(problem, "expand") == ["expand_msg"]

    def test_simplify(self) -> None:
        problem = node(T.DIVIDE, node(T.POWER, var(), c("2")), var())
        result = solution_of(problem, "simplify")
        assert sympy.simplify(to_sympy(result) - x) == 0
        assert step_keys(problem, "simplify") == ["simplify"]

    def test_command_applies_to_both_sides(self) -> None:
        equation = node(
            T.EQUALS,
            node(T.ADD, node(T.ADD, node(T.POWER, var(), c("2")), muli(c("2"), var())), c("1")),
            c("0"),
        )
        result = solution_of(equation, "factor")
        assert result.type is T.EQUALS
        assert sympy.simplify(to_sympy(result.children[0]) - (x + 1) ** 2) == 0

    def test_solve_command_is_normal_solving(self) -> None:
        problem = node(T.ADD, c("2"), c("3"))
        vertical = solve(problem, command="solve").result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.value == "5"


class TestUnsupported:
    def test_unknown_command(self) -> None:
        with pytest.raises(SolveError, match="команда"):
            solve(node(T.ADD, c("1"), c("1")), command="телепорт")


class TestExplanationKeys:
    def test_keys_exist(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        for key in ("factorise_call", "expand_msg", "simplify"):
            assert key in explanations
            assert explanations.arity(key) == 0
            assert "ARG" not in (explanations.raw_template(key, DEFAULT_LOCALE) or "")
