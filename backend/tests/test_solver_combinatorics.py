"""Тесты модуля комбинаторики."""

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


def value_of(problem: CoreNode) -> str | None:
    vertical = solve(problem).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution.value


def step_keys(problem: CoreNode) -> list[str]:
    vertical = solve(problem).result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


class TestFactorial:
    def test_five(self) -> None:
        problem = node(T.FACTORIAL, c("5"))
        assert value_of(problem) == "120"
        assert step_keys(problem) == ["factorial_formula", "product"]

    def test_zero(self) -> None:
        assert value_of(node(T.FACTORIAL, c("0"))) == "1"

    def test_non_integer(self) -> None:
        with pytest.raises(SolveError, match="целых"):
            solve(node(T.FACTORIAL, c("2.5")))


class TestChoose:
    def test_binomial(self) -> None:
        problem = node(T.CHOOSE, c("5"), c("2"))
        assert value_of(problem) == "10"
        assert step_keys(problem) == ["choose_calculate"]

    def test_full(self) -> None:
        assert value_of(node(T.CHOOSE, c("5"), c("5"))) == "1"

    def test_k_greater_than_n(self) -> None:
        with pytest.raises(SolveError, match="k ≤ n"):
            solve(node(T.CHOOSE, c("2"), c("5")))


class TestArrangements:
    def test_permutation(self) -> None:
        problem = node(T.PARTIAL_PERMUTATION_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT, c("5"), c("2"))
        assert value_of(problem) == "20"
        assert step_keys(problem) == ["permutation_calculate"]

    def test_variation(self) -> None:
        problem = node(T.VARIATION, c("5"), c("2"))
        assert value_of(problem) == "20"
        assert step_keys(problem) == ["variation_not_allowed_calculate"]


class TestExplanationKeys:
    def test_keys_exist(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        for key in (
            "factorial_calculate",
            "choose_calculate",
            "permutation_calculate",
            "variation_not_allowed_calculate",
        ):
            assert key in explanations
            assert explanations.arity(key) == 0
            assert "ARG" not in (explanations.raw_template(key, DEFAULT_LOCALE) or "")


class TestRegistration:
    def test_registered(self) -> None:
        assert {
            T.FACTORIAL,
            T.CHOOSE,
            T.CHOOSE_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT,
            T.PARTIAL_PERMUTATION_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT,
            T.VARIATION,
        } <= registered_types()
