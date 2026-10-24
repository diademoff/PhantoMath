"""Тесты приближённого значения (O): команда ``approximate``.

Ответ — узел ``APPROXIMATE[выражение, округлённое значение]``; шаг ``roundN`` по
числу знаков после запятой (аргумент команды, по умолчанию 0).
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.solver import SolveError, solve


def run(source: str, digits: str | None = None) -> tuple[list[str], CoreNode]:
    args = [parse_protocol(digits)] if digits is not None else []
    vertical = solve(parse_protocol(source), command="approximate", args=args).result.vertical()
    assert vertical is not None and vertical.solution is not None
    keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
    return keys, vertical.solution


class TestApproximate:
    def test_round_to_integer(self) -> None:
        keys, solution = run("{root2({2})}")
        assert keys == ["round0"]
        assert solution.type is T.APPROXIMATE
        assert solution.children[1].value == "1"

    def test_round_four(self) -> None:
        keys, solution = run("{root2({2})}", "{4}")
        assert keys == ["round4"]
        assert solution.children[1].value == "1.4142"

    def test_fraction(self) -> None:
        _, solution = run("{frac({1},{3})}", "{3}")
        assert solution.children[1].value == "0.333"

    def test_pi(self) -> None:
        _, solution = run("{pi}", "{2}")
        assert solution.children[1].value == "3.14"

    def test_non_number(self) -> None:
        with pytest.raises(SolveError):
            run("{x}")

    def test_bad_digits(self) -> None:
        with pytest.raises(SolveError):
            run("{root2({2})}", "{-1}")
