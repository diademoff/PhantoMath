"""Тесты параметрических уравнений (A): команда ``solve_param``.

Аргумент — переменная, относительно которой решаем; остальные буквы —
параметры. Шаги ``eq_param_write`` и ``eq_linear_param_j_final``.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.solver import SolveError, solve


def run(source: str, target: str) -> tuple[list[str], CoreNode]:
    vertical = solve(
        parse_protocol(source),
        command="solve_param",
        args=[parse_protocol(target)],
    ).result.vertical()
    assert vertical is not None and vertical.solution is not None
    keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
    return keys, vertical.solution


class TestParam:
    def test_linear(self) -> None:
        # a·x + b = 0 -> x = −b/a.
        keys, solution = run("{=({ax+b},{0})}", "{x}")
        assert keys == ["eq_param_write", "eq_linear_param_j_final"]
        assert solution.type is T.EQUALS and solution.children[0].value == "x"
        assert solution.children[1].type is T.FRACTION

    def test_numeric(self) -> None:
        _, solution = run("{=({2x+3},{7})}", "{x}")
        assert solution.children[1].value == "2"

    def test_quadratic_parameter(self) -> None:
        # x² + a·x + 1 = 0 -> две ветви с √(a²−4).
        _, solution = run("{=({x^2+a*x+1},{0})}", "{x}")
        assert solution.type is T.LIST and len(solution.children) == 2

    def test_no_target(self) -> None:
        with pytest.raises(SolveError):
            solve(parse_protocol("{=({2x+3},{7})}"), command="solve_param")

    def test_not_equation(self) -> None:
        with pytest.raises(SolveError):
            run("{2x+3}", "{x}")
