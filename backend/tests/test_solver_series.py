"""Тесты модуля сумм (знак суммирования)."""

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


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def var(name: str = "n") -> CoreNode:
    return CoreNode.variable(name)


def node(t: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(t, *children)


def value_of(problem: CoreNode) -> str | None:
    vertical = solve(problem).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution.value


def step_keys(problem: CoreNode) -> list[str]:
    vertical = solve(problem).result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


class TestSeries:
    def test_natural_numbers(self) -> None:
        problem = node(T.SIGMA_DEFINITE, var(), c("1"), c("5"), var())
        assert value_of(problem) == "15"
        assert step_keys(problem) == ["series_find_sum_pos_int", "series_sigma_find_sub"]

    def test_squares(self) -> None:
        problem = node(T.SIGMA_DEFINITE, var(), c("1"), c("4"), node(T.POWER, var(), c("2")))
        assert value_of(problem) == "30"

    def test_geometric(self) -> None:
        problem = node(T.SIGMA_DEFINITE, var(), c("0"), c("3"), node(T.POWER, c("2"), var()))
        assert value_of(problem) == "15"

    def test_editor_form_without_index(self) -> None:
        problem = node(T.SIGMA_DEFINITE, c("1"), c("3"), var())
        assert value_of(problem) == "6"

    def test_symbolic_upper_bound(self) -> None:
        problem = node(T.SIGMA_DEFINITE, var(), c("1"), var("N"), var())
        solution = solve(problem).result.vertical().solution
        assert solution is not None
        big_n = sympy.Symbol("N")
        expected = big_n * (big_n + 1) / 2
        assert sympy.simplify(to_sympy(solution) - expected) == 0


class TestUnsupported:
    def test_bad_arity(self) -> None:
        with pytest.raises(SolveError, match="сумма"):
            solve(node(T.SIGMA_DEFINITE, var(), c("1")))


class TestExplanationKeys:
    def test_key_exists(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        assert "series_sigma_find_sub" in explanations
        assert explanations.arity("series_sigma_find_sub") == 0
        assert "ARG" not in (
            explanations.raw_template("series_sigma_find_sub", DEFAULT_LOCALE) or ""
        )


class TestRegistration:
    def test_registered(self) -> None:
        assert T.SIGMA_DEFINITE in registered_types()
