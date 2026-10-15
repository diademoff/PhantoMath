"""Тесты моста CoreNode ↔ sympy.

Проверяется прямой и обратный перевод. Основная проверка — круг:
``to_sympy(from_sympy(expr))`` должно совпадать с ``simplify(expr)``; так
тестируется и структура, которую увидит фронт, и корректность значений.
"""

from __future__ import annotations

import pytest
import sympy

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.solver import SolveError
from mymath_backend.solver.sympy_bridge import from_sympy, simplify_node, to_sympy

x = sympy.Symbol("x")


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def var(name: str = "x") -> CoreNode:
    return CoreNode.variable(name)


def node(t: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(t, *children)


def roundtrip(expr: sympy.Expr) -> sympy.Expr:
    return sympy.simplify(to_sympy(from_sympy(expr)) - expr)


class TestToSympy:
    def test_numbers(self) -> None:
        assert to_sympy(c("3")) == 3
        assert to_sympy(c("1/2")) == sympy.Rational(1, 2)

    def test_constants(self) -> None:
        assert to_sympy(c("π")) == sympy.pi
        assert to_sympy(c("e")) == sympy.E

    def test_implicit_product(self) -> None:
        assert to_sympy(node(T.MULTIPLY_IMPLICIT, c("2"), var())) == 2 * x

    def test_fraction_and_power(self) -> None:
        assert to_sympy(node(T.FRACTION, c("1"), var())) == 1 / x
        assert to_sympy(node(T.POWER, var(), c("2"))) == x**2

    def test_functions(self) -> None:
        assert to_sympy(node(T.SIN, var())) == sympy.sin(x)
        assert to_sympy(node(T.LN, var())) == sympy.log(x)

    def test_unknown_node(self) -> None:
        with pytest.raises(SolveError):
            to_sympy(node(T.MATRIX, c("1")))


class TestFromSympy:
    def test_integer_and_rational(self) -> None:
        assert from_sympy(sympy.Integer(5)).value == "5"
        assert from_sympy(sympy.Rational(1, 2)).value == "1/2"

    def test_polynomial_roundtrip(self) -> None:
        assert roundtrip(2 * x**2 - 3 * x + 1) == 0

    def test_fraction_roundtrip(self) -> None:
        assert roundtrip(1 / x) == 0
        assert roundtrip(2 / (x + 1)) == 0

    def test_sqrt_becomes_root2(self) -> None:
        assert from_sympy(sympy.sqrt(x)).type is T.ROOT2

    def test_negative_is_negative_node(self) -> None:
        result = from_sympy(-sympy.cos(x))
        assert result.type is T.NEGATIVE
        assert result.children[0].type is T.COS

    def test_subtraction_reads_as_minus(self) -> None:
        result = from_sympy(2 * x - 3)
        assert result.type is T.SUBTRACT
        assert result.children[1].value == "3"

    def test_functions_roundtrip(self) -> None:
        assert roundtrip(sympy.sin(x) + sympy.exp(x)) == 0

    def test_logarithm_roundtrip(self) -> None:
        assert roundtrip(sympy.log(x) + 1) == 0

    def test_simplify_node(self) -> None:
        messy = node(
            T.ADD,
            node(T.MULTIPLY, c("2"), var()),
            node(T.MULTIPLY, c("3"), var()),
        )
        assert to_sympy(simplify_node(messy)) == 5 * x
