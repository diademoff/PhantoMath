"""Тесты модуля степеней, корней и логарифмов.

Проверяются точные значения (``√16``, ``log₁₀(1000)``, ``log₂(8)``, ``ln(e)``),
сохранение узла без упрощения (``√2``) и совместная работа с арифметикой
(``√16 + 1 = 5``).
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


def value_of(problem: CoreNode) -> str | None:
    return solution_of(problem).value


class TestRoots:
    def test_square_root_exact(self) -> None:
        assert value_of(node(T.ROOT2, c("25"))) == "5"
        assert step_keys(node(T.ROOT2, c("25"))) == ["root_simplify"]

    def test_cube_root_exact(self) -> None:
        assert value_of(node(T.ROOT, c("3"), c("27"))) == "3"

    def test_irrational_root_is_kept(self) -> None:
        problem = node(T.ROOT2, c("2"))
        assert solution_of(problem).structural_eq(problem)
        assert step_keys(problem) == []

    def test_negative_even_root_is_left(self) -> None:
        problem = node(T.ROOT2, c("-4"))
        assert solution_of(problem).structural_eq(problem)


class TestLogarithms:
    def test_log10(self) -> None:
        assert value_of(node(T.LOG10, c("1000"))) == "3"

    def test_log_base(self) -> None:
        assert value_of(node(T.LOG, c("8"), c("2"))) == "3"

    def test_non_power_of_ten_is_kept(self) -> None:
        problem = node(T.LOG10, c("5"))
        assert solution_of(problem).structural_eq(problem)

    def test_ln_one(self) -> None:
        assert value_of(node(T.LN, c("1"))) == "0"

    def test_ln_e(self) -> None:
        assert value_of(node(T.LN, c("e"))) == "1"

    def test_exp_zero(self) -> None:
        assert value_of(node(T.EXP, c("0"))) == "1"


class TestWithArithmetic:
    def test_root_combines_with_numbers(self) -> None:
        problem = node(T.ADD, node(T.ROOT2, c("16")), c("1"))
        assert value_of(problem) == "5"
        assert step_keys(problem) == ["root_simplify", "add"]

    def test_log_combines_with_numbers(self) -> None:
        problem = node(T.ADD, node(T.LOG10, c("1000")), c("1"))
        assert value_of(problem) == "4"


class TestErrors:
    def test_nth_root_without_degree(self) -> None:
        with pytest.raises(SolveError, match="степень"):
            solve(node(T.ROOT, c("2")))


class TestExplanationKeys:
    def test_keys_exist(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        for key in ("root_simplify", "calculate_short"):
            assert key in explanations
            assert explanations.arity(key) == 0
            assert "ARG" not in (explanations.raw_template(key, DEFAULT_LOCALE) or "")


class TestRegistration:
    def test_registered(self) -> None:
        assert {T.ROOT2, T.ROOT, T.LOG10, T.LN, T.LOG, T.EXP} <= registered_types()
