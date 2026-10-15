"""Тесты асимптот (E): команда ``asymptotes``.

Вертикальные (``find_vert_asymptote`` / ``no_vert_asymptote``) и горизонтальные
(``find_hor_asymptote`` с пределами / ``no_hor_asymptote``). Ответ — ``x = …``
и ``y = …``.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import SolveError, solve


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source), command="asymptotes").result.vertical()
    assert vertical is not None
    return vertical


def lines(source: str) -> list[tuple[str, str]]:
    solution = _vertical(source).solution
    assert solution is not None
    items = solution.children if solution.type is T.LIST else [solution]
    return [(item.children[0].value or "", item.children[1].value or "") for item in items]


def step_keys(source: str) -> list[str]:
    return [sub.description.type for step in _vertical(source).steps for sub in step.substeps]


class TestAsymptotes:
    def test_hyperbola(self) -> None:
        source = "{1/x}"
        assert lines(source) == [("x", "0"), ("y", "0")]
        assert step_keys(source) == ["find_vert_asymptote", "find_hor_asymptote"]

    def test_two_vertical(self) -> None:
        assert lines("{frac({1},{x^2-1})}") == [("x", "-1"), ("x", "1"), ("y", "0")]

    def test_exponential(self) -> None:
        source = "{exp({x})}"
        assert lines(source) == [("y", "0")]
        assert step_keys(source) == ["no_vert_asymptote", "find_hor_asymptote"]

    def test_no_asymptotes(self) -> None:
        with pytest.raises(SolveError):
            solve(parse_protocol("{x^2}"), command="asymptotes")
