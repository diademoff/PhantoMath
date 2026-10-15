"""Тесты оси симметрии и формы по корням параболы (E).

Команды ``axis_of_symmetry`` и ``intercept_form``.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.solver import SolveError, solve


def run(source: str, command: str) -> tuple[list[str], CoreNode]:
    vertical = solve(parse_protocol(source), command=command).result.vertical()
    assert vertical is not None and vertical.solution is not None
    keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
    return keys, vertical.solution


class TestAxisOfSymmetry:
    def test_shifted(self) -> None:
        keys, solution = run("{x^2-4x+3}", "axis_of_symmetry")
        assert keys == ["find_axis"]
        assert solution.type is T.EQUALS
        assert solution.children[1].value == "2"

    def test_not_quadratic(self) -> None:
        with pytest.raises(SolveError):
            run("{x^3}", "axis_of_symmetry")


class TestInterceptForm:
    def test_two_roots(self) -> None:
        keys, solution = run("{x^2-4x+3}", "intercept_form")
        assert keys == ["intercept_form"]
        assert solution.type is T.MULTIPLY

    def test_no_real_roots(self) -> None:
        _, solution = run("{x^2+1}", "intercept_form")
        assert solution.type is T.ADD
