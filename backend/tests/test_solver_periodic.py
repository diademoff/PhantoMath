"""Тесты периодических дробей (O): команда ``periodic_to_frac``.

Узел ``PERIODIC[цифры, период]``: ``0.s(rep)`` = ``(s − s[:p]) / (10ⁿ − 10ᵖ)``,
где ``p`` — число неповторяющихся цифр. Шаг — ``periodic_to_frac``.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.solver import SolveError, solve


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def periodic(digits: str, period: str) -> CoreNode:
    return CoreNode.node(T.PERIODIC, c(digits), c(period))


def value(node: CoreNode) -> str:
    vertical = solve(node, command="periodic_to_frac").result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution.value or ""


def step_keys(node: CoreNode) -> list[str]:
    vertical = solve(node, command="periodic_to_frac").result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


class TestPeriodic:
    def test_pure_single_digit(self) -> None:
        assert value(periodic("3", "1")) == "1/3"
        assert step_keys(periodic("3", "1")) == ["periodic_to_frac"]

    def test_existing_digit(self) -> None:
        # 0.1(6) = 1/6.
        assert value(periodic("16", "1")) == "1/6"

    def test_multi_digit_period(self) -> None:
        # 0.(12) = 4/33.
        assert value(periodic("12", "2")) == "4/33"

    def test_from_protocol(self) -> None:
        assert value(parse_protocol("{periodic({6},{1})}")) == "2/3"

    def test_bad_period(self) -> None:
        with pytest.raises(SolveError):
            value(periodic("3", "5"))

    def test_not_periodic(self) -> None:
        with pytest.raises(SolveError):
            value(c("3"))
