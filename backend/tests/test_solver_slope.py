"""Тесты углового коэффициента и пересечения с осью (O): ``slope_intercept``.

Линейное уравнение приводится к виду ``y = kx + b`` (шаг
``rewrite_in_slope_intercept_form``); ``k`` и ``b`` называются шагом
``slope_and_y_intercept``.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.solver import SolveError, solve


def run(source: str) -> tuple[list[str], CoreNode]:
    vertical = solve(parse_protocol(source), command="slope_intercept").result.vertical()
    assert vertical is not None and vertical.solution is not None
    keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
    return keys, vertical.solution


class TestSlopeIntercept:
    def test_general_form(self) -> None:
        # 2x + 3y = 6 -> y = 2 − 2x/3.
        keys, solution = run("{=({2x+3y},{6})}")
        assert keys == [
            "rewrite_in_slope_intercept_form",
            "identify_y_intercept_as_const_term",
            "slope_and_y_intercept",
        ]
        assert solution.type is T.EQUALS and solution.children[0].value == "y"

    def test_slope_form(self) -> None:
        # y = 2x + 3.
        _, solution = run("{=({y},{2x+3})}")
        assert solution.children[1].type is T.ADD

    def test_not_linear(self) -> None:
        with pytest.raises(SolveError):
            run("{=({x^2+y},{0})}")

    def test_needs_two_variables(self) -> None:
        with pytest.raises(SolveError):
            run("{=({2x+3},{7})}")
