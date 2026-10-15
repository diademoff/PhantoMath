"""Тесты пересечений с осями (E): команда ``intercepts``.

С осью x — корни ``f(x) = 0`` (``find_x_intercept`` + ``x_intercept_substitute``,
при их отсутствии ``no_x_intercept``); с осью y — ``f(0)`` (``find_y_intercept``
+ ``y_intercept_substitute``, при отсутствии ``no_y_intercept``). Ответ — список
``x = …`` / ``y = …``.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import SolveError, solve


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source), command="intercepts").result.vertical()
    assert vertical is not None
    return vertical


def step_keys(source: str) -> list[str]:
    return [sub.description.type for step in _vertical(source).steps for sub in step.substeps]


def answer(source: str) -> list[tuple[str, str]]:
    """Каждое пересечение как ``(ось, значение)``."""
    solution = _vertical(source).solution
    assert solution is not None
    items = solution.children if solution.type is T.LIST else [solution]
    return [(item.children[0].value or "", item.children[1].value or "") for item in items]


class TestIntercepts:
    def test_two_roots_and_y(self) -> None:
        source = "{x^2-1}"
        assert answer(source) == [("x", "-1"), ("x", "1"), ("y", "-1")]
        assert step_keys(source) == [
            "find_x_intercept",
            "x_intercept_substitute",
            "two_x_intercepts",
            "find_y_intercept",
            "y_intercept_substitute",
        ]

    def test_no_x_intercept(self) -> None:
        source = "{x^2+1}"
        assert answer(source) == [("y", "1")]
        assert step_keys(source) == [
            "find_x_intercept",
            "x_intercept_substitute",
            "no_x_intercept",
            "find_y_intercept",
            "y_intercept_substitute",
        ]

    def test_linear(self) -> None:
        assert answer("{x-2}") == [("x", "2"), ("y", "-2")]

    def test_cubic_origin(self) -> None:
        assert answer("{x^3}") == [("x", "0"), ("y", "0")]

    def test_trigonometric(self) -> None:
        assert answer("{sin({x})}") == [("x", "0"), ("x", "π"), ("y", "0")]

    def test_no_intercepts(self) -> None:
        with pytest.raises(SolveError):
            solve(parse_protocol("{1/x}"), command="intercepts")
