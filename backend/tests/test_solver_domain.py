"""Тесты области определения выражения (команда ``domain``).

Проверяются многочлен (вся прямая), рациональная функция (объединение
промежутков), корень, логарифм, а также ошибки для уравнения, нескольких
переменных и невыразимой промежутками области (``tan``).
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import SolveError, solve


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source), command="domain").result.vertical()
    assert vertical is not None
    return vertical


def solution_of(source: str) -> CoreNode:
    vertical = _vertical(source)
    assert vertical.solution is not None
    return vertical.solution


def step_keys(source: str) -> list[str]:
    return [sub.description.type for step in _vertical(source).steps for sub in step.substeps]


def const(value: str) -> CoreNode:
    return CoreNode.constant(value)


def negative_infinity() -> CoreNode:
    return CoreNode.node(T.NEGATIVE, const("∞"))


def all_reals() -> CoreNode:
    return CoreNode.node(T.OPEN_OPEN_INTERVAL, negative_infinity(), const("∞"))


class TestDomain:
    def test_polynomial_is_all_reals(self) -> None:
        source = "{x^2+1}"
        assert solution_of(source).structural_eq(all_reals())
        assert step_keys(source) == ["domain_find"]

    def test_constant_is_all_reals(self) -> None:
        assert solution_of("{5}").structural_eq(all_reals())

    def test_rational_excludes_pole(self) -> None:
        answer = solution_of("{frac({1},{x-1})}")
        assert answer.type is T.UNION
        assert len(answer.children) == 2
        assert answer.children[0].type is T.OPEN_OPEN_INTERVAL

    def test_square_root(self) -> None:
        answer = solution_of("{root2({x-2})}")
        assert answer.type is T.CLOSED_OPEN_INTERVAL
        assert [child.value for child in answer.children] == ["2", "∞"]

    def test_logarithm(self) -> None:
        answer = solution_of("{ln({x})}")
        assert answer.type is T.OPEN_OPEN_INTERVAL
        assert [child.value for child in answer.children] == ["0", "∞"]

    def test_two_poles(self) -> None:
        answer = solution_of("{frac({1},{x^2-1})}")
        assert answer.type is T.UNION
        assert len(answer.children) == 3


class TestErrors:
    def test_equation_is_not_expression(self) -> None:
        with pytest.raises(SolveError):
            solve(parse_protocol("{=({x^2},{1})}"), command="domain")

    def test_two_variables(self) -> None:
        with pytest.raises(SolveError):
            solve(parse_protocol("{x+y}"), command="domain")

    def test_tangent_not_expressible(self) -> None:
        with pytest.raises(SolveError):
            solve(parse_protocol("{tan({x})}"), command="domain")
