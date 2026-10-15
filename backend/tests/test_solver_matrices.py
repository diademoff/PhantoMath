"""Тесты модуля определителей.

Элементы задаются в порядке «по строкам»; отдельно проверяется форма со
строками ``MATRIX_ROW``.
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


def det(t: T, *elements: CoreNode) -> CoreNode:
    return CoreNode.node(t, *elements)


def row(*elements: CoreNode) -> CoreNode:
    return CoreNode.node(T.MATRIX_ROW, *elements)


def value_of(problem: CoreNode) -> str | None:
    vertical = solve(problem).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution.value


def step_keys(problem: CoreNode) -> list[str]:
    vertical = solve(problem).result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


class TestDeterminants:
    def test_2x2(self) -> None:
        problem = det(T.DETERMINANT2, c("1"), c("2"), c("3"), c("4"))
        assert value_of(problem) == "-2"
        assert step_keys(problem) == ["det2_calc"]

    def test_3x3_identity(self) -> None:
        problem = det(
            T.DETERMINANT3, c("1"), c("0"), c("0"), c("0"), c("1"), c("0"), c("0"), c("0"), c("1")
        )
        assert value_of(problem) == "1"

    def test_3x3_general(self) -> None:
        problem = det(
            T.DETERMINANT3, c("1"), c("2"), c("3"), c("4"), c("5"), c("6"), c("7"), c("8"), c("10")
        )
        assert value_of(problem) == "-3"

    def test_4x4_identity(self) -> None:
        values = [c("1" if i % 5 == 0 else "0") for i in range(16)]
        assert value_of(det(T.DETERMINANT4, *values)) == "1"

    def test_rows_form(self) -> None:
        problem = CoreNode.node(
            T.DETERMINANT,
            row(c("2"), c("0")),
            row(c("0"), c("3")),
        )
        assert value_of(problem) == "6"

    def test_elements_may_be_expressions(self) -> None:
        first = CoreNode.node(T.ADD, c("1"), c("1"))
        problem = det(T.DETERMINANT2, first, c("0"), c("0"), c("5"))
        assert value_of(problem) == "10"


class TestUnsupported:
    def test_not_square(self) -> None:
        problem = det(T.DETERMINANT2, c("1"), c("2"), c("3"))
        with pytest.raises(SolveError, match="квадратной"):
            solve(problem)

    def test_non_numeric_element(self) -> None:
        problem = det(T.DETERMINANT2, c("1"), CoreNode.variable("x"), c("3"), c("4"))
        with pytest.raises(SolveError):
            solve(problem)


class TestExplanationKeys:
    def test_keys_exist(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        for key in ("det2_calc", "det3_sarrus_eval", "det_laplace_rule_row_simple"):
            assert key in explanations
            assert explanations.arity(key) == 0
            assert "ARG" not in (explanations.raw_template(key, DEFAULT_LOCALE) or "")


class TestRegistration:
    def test_registered(self) -> None:
        assert {
            T.DETERMINANT,
            T.DETERMINANT2,
            T.DETERMINANT3,
            T.DETERMINANT3_SARRUS,
            T.DETERMINANT4,
            T.DETERMINANT5,
        } <= registered_types()
