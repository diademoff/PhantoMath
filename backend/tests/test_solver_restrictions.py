"""Тесты недопустимых значений выражения (команда ``restrictions``, D2).

Проверяется дополнение области определения: знаменатель, аргумент логарифма,
подкоренное выражение; если недопустимых значений нет — ``EMPTY`` со шагом
``rel_restrictions_none``.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import SolveError, solve


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source), command="restrictions").result.vertical()
    assert vertical is not None
    return vertical


def solution_of(source: str) -> CoreNode:
    vertical = _vertical(source)
    assert vertical.solution is not None
    return vertical.solution


def step_keys(source: str) -> list[str]:
    return [sub.description.type for step in _vertical(source).steps for sub in step.substeps]


class TestRestrictions:
    def test_no_restrictions(self) -> None:
        assert solution_of("{x^2+1}").type is T.EMPTY
        assert step_keys("{x^2+1}") == ["rel_restrictions_none"]

    def test_single_pole(self) -> None:
        answer = solution_of("{frac({1},{x-1})}")
        assert answer.type is T.SET
        assert [child.value for child in answer.children] == ["1"]
        assert step_keys("{frac({1},{x-1})}") == ["rel_restrictions_find"]

    def test_two_poles(self) -> None:
        answer = solution_of("{frac({1},{x^2-1})}")
        assert answer.type is T.SET
        assert [child.value for child in answer.children] == ["-1", "1"]

    def test_square_root(self) -> None:
        answer = solution_of("{root2({x-2})}")
        assert answer.type is T.OPEN_OPEN_INTERVAL
        assert answer.children[1].value == "2"

    def test_logarithm(self) -> None:
        answer = solution_of("{ln({x})}")
        assert answer.type is T.OPEN_CLOSED_INTERVAL
        assert answer.children[1].value == "0"


class TestErrors:
    def test_equation(self) -> None:
        with pytest.raises(SolveError):
            solve(parse_protocol("{=({x^2},{1})}"), command="restrictions")

    def test_two_variables(self) -> None:
        with pytest.raises(SolveError):
            solve(parse_protocol("{frac({1},{x+y})}"), command="restrictions")
