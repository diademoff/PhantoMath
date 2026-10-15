"""Тесты обратной функции (R): команда ``inverse_function``.

Выражение ``y = f(x)`` решается относительно ``x``; ответ — ``y = f⁻¹(x)``
(шаг ``find_inverse``). Ветвящиеся случаи (``x²``) отклоняются.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.solver import SolveError, solve


def answer(source: str) -> CoreNode:
    vertical = solve(parse_protocol(source), command="inverse_function").result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution


def rhs(source: str) -> CoreNode:
    solution = answer(source)
    assert solution.type is T.EQUALS and solution.children[0].value == "y"
    return solution.children[1]


class TestInverseFunction:
    def test_linear(self) -> None:
        # f(x) = 2x + 3 -> f⁻¹(x) = x/2 − 3/2.
        result = rhs("{2x+3}")
        assert result.type is T.SUBTRACT

    def test_cube(self) -> None:
        # f(x) = x³ -> ∛x.
        result = rhs("{x^3}")
        assert result.type is T.ROOT
        assert result.children[0].value == "3"

    def test_log(self) -> None:
        # ln x -> eˣ.
        assert rhs("{ln({x})}").type is T.EXP

    def test_exponential(self) -> None:
        # eˣ -> ln x.
        assert rhs("{exp({x})}").type is T.LN

    def test_not_one_to_one(self) -> None:
        with pytest.raises(SolveError, match="однознач"):
            answer("{x^2}")

    def test_step_key(self) -> None:
        vertical = solve(parse_protocol("{2x+3}"), command="inverse_function").result.vertical()
        assert vertical is not None
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        assert keys == ["find_inverse"]
