"""Тесты точек перегиба (E): команда ``inflection``.

Вторая производная (``inflection_sec_der``), поиск точек (``inflection_find``),
точка перегиба (``inflection_the_point``). Ответ — координата ``x = …``.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import SolveError, solve


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source), command="inflection").result.vertical()
    assert vertical is not None
    return vertical


def points(source: str) -> list[str]:
    solution = _vertical(source).solution
    assert solution is not None
    items = solution.children if solution.type is T.LIST else [solution]
    return [item.children[1].value or "" for item in items]


def step_keys(source: str) -> list[str]:
    return [sub.description.type for step in _vertical(source).steps for sub in step.substeps]


class TestInflection:
    def test_cubic(self) -> None:
        source = "{x^3}"
        assert points(source) == ["0"]
        assert step_keys(source) == [
            "inflection_domain_find",
            "inflection_domain_snd_find",
            "inflection_sec_der",
            "inflection_find",
            "inflection_the_point",
        ]

    def test_shifted_cubic(self) -> None:
        assert points("{x^3-3x}") == ["0"]

    def test_no_inflection(self) -> None:
        with pytest.raises(SolveError):
            solve(parse_protocol("{x^4}"), command="inflection")
