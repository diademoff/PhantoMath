"""Тесты столбиковых вычислений (P).

``VERTICAL_ADD``/``VERTICAL_SUBTRACT``/``VERTICAL_MULTIPLY`` — список операндов,
``HORIZONTAL_MULTIPLY`` — два множителя, ``US_LONGDIV``/``RU_LONGDIV``/
``VERTICAL_DIVIDE`` — деление. Шаг называет столбиковый метод.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.solver import SolveError, registered_types, solve


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def run(node_type: T, *values: str) -> tuple[list[str], str]:
    node = CoreNode.node(node_type, *(c(value) for value in values))
    vertical = solve(node).result.vertical()
    assert vertical is not None and vertical.solution is not None
    keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
    return keys, vertical.solution.value or ""


class TestVertical:
    def test_add(self) -> None:
        assert run(T.VERTICAL_ADD, "123", "456") == (["animation_long_add"], "579")

    def test_subtract(self) -> None:
        assert run(T.VERTICAL_SUBTRACT, "456", "123") == (["animation_long_sub"], "333")

    def test_multiply(self) -> None:
        assert run(T.VERTICAL_MULTIPLY, "12", "34") == (["animation_long_mul"], "408")

    def test_horizontal_multiply(self) -> None:
        assert run(T.HORIZONTAL_MULTIPLY, "7", "8") == (["calculate_short"], "56")

    def test_long_division(self) -> None:
        assert run(T.US_LONGDIV, "10", "2") == (["animation_long_div"], "5")

    def test_division_fraction(self) -> None:
        assert run(T.RU_LONGDIV, "10", "4") == (["animation_long_div"], "5/2")

    def test_division_by_zero(self) -> None:
        node = CoreNode.node(T.US_LONGDIV, c("1"), c("0"))
        with pytest.raises(SolveError):
            solve(node)

    def test_single_operand(self) -> None:
        with pytest.raises(SolveError):
            solve(CoreNode.node(T.VERTICAL_ADD, c("1")))

    def test_protocol(self) -> None:
        result = solve(parse_protocol("{vert_add({12},{30})}")).result.vertical()
        assert result is not None and result.solution is not None
        assert result.solution.value == "42"

    def test_registered(self) -> None:
        assert {
            T.VERTICAL_ADD,
            T.VERTICAL_SUBTRACT,
            T.VERTICAL_MULTIPLY,
            T.HORIZONTAL_MULTIPLY,
            T.US_LONGDIV,
            T.RU_LONGDIV,
            T.VERTICAL_DIVIDE,
        } <= registered_types()
