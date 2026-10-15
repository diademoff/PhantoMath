"""Тесты площади под кривой (K): команда ``area``.

Принимает определённый интеграл и считает интеграл модуля функции, разбивая
отрезок по корням; шаги ``total_area`` и ``integrate_calc``.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import SolveError, solve


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source), command="area").result.vertical()
    assert vertical is not None
    return vertical


def value_of(source: str) -> str:
    solution = _vertical(source).solution
    assert solution is not None
    return solution.value or ""


def step_keys(source: str) -> list[str]:
    return [sub.description.type for step in _vertical(source).steps for sub in step.substeps]


class TestArea:
    def test_sign_change(self) -> None:
        source = "{integral_def({-1},{1},{x^3})}"
        assert value_of(source) == "1/2"
        assert step_keys(source) == [
            "total_area_fun",
            "total_area_x_intercept",
            "total_area",
            "integrate_calc",
        ]

    def test_no_sign_change(self) -> None:
        assert value_of("{integral_def({0},{2},{x^2})}") == "8/3"

    def test_periodic(self) -> None:
        assert value_of("{integral_def({0},{2*pi},{sin({x})})}") == "4"

    def test_requires_definite_integral(self) -> None:
        with pytest.raises(SolveError):
            solve(CoreNode.node(T.INTEGRAL, CoreNode.variable("x")), command="area")
