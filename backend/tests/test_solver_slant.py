"""Тесты наклонной асимптоты (E): команда ``slant_asymptote``.

``k = lim f(x)/x``, ``b = lim (f(x) − kx)``; ответ ``y = kx + b`` (шаги
``slope_slant_asymptote``, ``intercept_slant_asymptote``, ``def_slant_asymptote``).
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.solver import SolveError, solve


def run(source: str) -> tuple[list[str], CoreNode]:
    vertical = solve(parse_protocol(source), command="slant_asymptote").result.vertical()
    assert vertical is not None and vertical.solution is not None
    keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
    return keys, vertical.solution


class TestSlantAsymptote:
    def test_simple(self) -> None:
        # (x² + 1)/x = x + 1/x → y = x.
        keys, solution = run("{frac({x^2+1},{x})}")
        assert keys == [
            "slope_slant_asymptote",
            "intercept_slant_asymptote",
            "def_slant_asymptote",
        ]
        assert solution.type is T.EQUALS and solution.children[1].value == "x"

    def test_with_intercept(self) -> None:
        # (x² + 2x)/(x) = x + 2 → y = x + 2.
        _, solution = run("{frac({x^2+2x},{x})}")
        assert solution.children[1].type is T.ADD

    def test_no_slant(self) -> None:
        with pytest.raises(SolveError, match="наклонной"):
            run("{frac({x^2+1},{x^2-1})}")

    def test_not_rational(self) -> None:
        # Степень берётся у многочлена: у `exp(x)` она бросала
        # `PolynomialError`, и ответ не уходил клиенту вовсе.
        with pytest.raises(SolveError, match="рациональной"):
            run("{exp({x})}")
