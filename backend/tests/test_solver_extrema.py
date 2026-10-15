"""Тесты точек экстремума (E): команда ``extrema``.

Производная (``extrema_derive``), критические точки; по знаку второй
производной — ``extrema_maximum`` / ``extrema_minimum``. Ответ — координаты
``x = …``.
"""

from __future__ import annotations

from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import solve


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source), command="extrema").result.vertical()
    assert vertical is not None
    return vertical


def points(source: str) -> list[str]:
    solution = _vertical(source).solution
    assert solution is not None
    items = solution.children if solution.type is T.LIST else [solution]
    return [item.children[1].value or "" for item in items]


def step_keys(source: str) -> list[str]:
    return [sub.description.type for step in _vertical(source).steps for sub in step.substeps]


class TestExtrema:
    def test_minimum(self) -> None:
        source = "{x^2}"
        assert points(source) == ["0"]
        assert step_keys(source) == ["extrema_derive", "extrema_minimum"]

    def test_two_extrema(self) -> None:
        source = "{x^3-3x}"
        assert points(source) == ["-1", "1"]
        assert step_keys(source) == [
            "extrema_derive",
            "extrema_maximum",
            "extrema_minimum",
        ]

    def test_shifted_parabola(self) -> None:
        assert points("{x^2+1}") == ["0"]
