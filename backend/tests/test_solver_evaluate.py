"""Тесты подстановки значения (R): команда ``substitute``.

Аргумент команды — значение переменной; ответ — результат подстановки
(шаг ``substitute_value``).
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import SolveError, solve


def _substitute(source: str, value: str) -> CoreSolverVerticalResult:
    vertical = solve(
        parse_protocol(source),
        command="substitute",
        args=[parse_protocol(value)],
    ).result.vertical()
    assert vertical is not None
    return vertical


def value_of(source: str, value: str) -> str:
    solution = _substitute(source, value).solution
    assert solution is not None
    return solution.value or ""


class TestSubstitute:
    def test_polynomial(self) -> None:
        answer = _substitute("{x^2+1}", "{2}")
        assert answer.solution is not None and answer.solution.value == "5"

    def test_sine(self) -> None:
        assert value_of("{sin({x})}", "{0}") == "0"

    def test_fraction(self) -> None:
        assert value_of("{frac({1},{x+1})}", "{1}") == "1/2"

    def test_requires_value(self) -> None:
        with pytest.raises(SolveError):
            solve(CoreNode.variable("x"), command="substitute")
