"""Тесты экстремумов на отрезке (E): команда ``extrema_on_interval``.

Сравниваются значения функции в критических точках внутри отрезка и на концах;
ответ — ``x = …`` для максимума и минимума.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend.input import parse_protocol
from mymath_backend.solver import SolveError, solve


def run(source: str, lower: str, upper: str) -> tuple[list[str], CoreNode]:
    vertical = solve(
        parse_protocol(source),
        command="extrema_on_interval",
        args=[parse_protocol(lower), parse_protocol(upper)],
    ).result.vertical()
    assert vertical is not None and vertical.solution is not None
    keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
    return keys, vertical.solution


def points(solution: CoreNode) -> list[str]:
    return [child.children[1].value or "" for child in solution.children]


class TestExtremaOnInterval:
    def test_cubic(self) -> None:
        # x³ − 3x на [−2, 3]: максимум при x = 3, минимум при x = −2.
        keys, solution = run("{x^3-3x}", "{-2}", "{3}")
        assert keys[0] == "extrema_find_critical"
        assert keys[-1] == "extrema_final"
        assert points(solution) == ["3", "-2"]

    def test_quadratic(self) -> None:
        # x² на [1, 2]: максимум при x = 2, минимум при x = 1.
        _, solution = run("{x^2}", "{1}", "{2}")
        assert points(solution) == ["2", "1"]

    def test_requires_bounds(self) -> None:
        with pytest.raises(SolveError):
            solve(parse_protocol("{x^2}"), command="extrema_on_interval")
