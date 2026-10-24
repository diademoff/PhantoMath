"""Тесты вершины параболы (E): команда ``vertex``.

Для квадратичной функции находится ``x₀ = −b/(2a)`` и ``y₀ = f(x₀)``
(шаг ``find_vertex``); ответ — ``x = …``, ``y = …``.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import SolveError, solve


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source), command="vertex").result.vertical()
    assert vertical is not None
    return vertical


def vertex(source: str) -> tuple[str, str]:
    answer = _vertical(source).solution
    assert answer is not None and answer.type is T.LIST
    return answer.children[0].children[1].value or "", answer.children[1].children[1].value or ""


class TestVertex:
    def test_shifted(self) -> None:
        assert vertex("{x^2-4x+3}") == ("2", "-1")

    def test_origin(self) -> None:
        assert vertex("{x^2}") == ("0", "0")

    def test_not_quadratic(self) -> None:
        with pytest.raises(SolveError):
            solve(parse_protocol("{x^3}"), command="vertex")
