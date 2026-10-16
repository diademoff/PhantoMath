"""Тесты разложения на простейшие дроби (K): команда ``partial_fractions``.

Рациональное выражение раскладывается sympy (``apart``); шаг ``partial_frac``.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.solver import SolveError, solve


def run(source: str) -> tuple[list[str], CoreNode]:
    vertical = solve(parse_protocol(source), command="partial_fractions").result.vertical()
    assert vertical is not None and vertical.solution is not None
    keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
    return keys, vertical.solution


class TestPartialFractions:
    def test_two_factors(self) -> None:
        keys, solution = run("{frac({1},{x^2-1})}")
        assert keys == ["partial_frac"]
        assert solution.type is T.SUBTRACT
        assert all(child.type is T.FRACTION for child in solution.children)

    def test_cancels(self) -> None:
        # (x+1)/(x²−1) = 1/(x−1).
        _, solution = run("{frac({x+1},{x^2-1})}")
        assert solution.type is T.FRACTION

    def test_polynomial_part(self) -> None:
        # (x²+x+1)/(x+1) = x + 1/(x+1).
        _, solution = run("{frac({x^2+x+1},{x+1})}")
        assert solution.type is T.ADD

    def test_not_rational(self) -> None:
        with pytest.raises(SolveError):
            run("{x^2+1}")

    def test_equation(self) -> None:
        # Уравнение — не выражение: `sympy.together` падал `TypeError`,
        # ответ не уходил вовсе, клиент видел обрыв соединения.
        with pytest.raises(SolveError, match="рационального"):
            run("{=({x^2-5x+6},{0})}")
