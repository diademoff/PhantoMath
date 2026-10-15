"""Тесты модуля тригонометрии: единицы угла и точные значения.

Проверяются градусная и радианная мера, табличные значения прямых
функций, сохранение узла без упрощения (``sin(1)``) и совместная работа с
арифметикой. Значение сверяется через sympy, чтобы тест не зависел от
формы узла (``√3/2`` может быть записано по-разному).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sympy

from mymath_backend import CoreNode, load_explanations
from mymath_backend import CoreNodeType as T
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.solver import SolveError, registered_types, solve
from mymath_backend.solver.sympy_bridge import to_sympy

EXPLANATIONS = Path(__file__).resolve().parents[2] / "truth" / "data" / "explanations.json"


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def node(t: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(t, *children)


def degrees(value: str) -> CoreNode:
    return node(T.DEGREE, c(value))


def solution_of(problem: CoreNode) -> CoreNode:
    vertical = solve(problem).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution


def value_of(problem: CoreNode) -> sympy.Expr:
    return to_sympy(solution_of(problem))


def step_keys(problem: CoreNode) -> list[str]:
    vertical = solve(problem).result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


class TestDegrees:
    def test_sin_30(self) -> None:
        assert value_of(node(T.SIN, degrees("30"))) == sympy.Rational(1, 2)

    def test_cos_60(self) -> None:
        assert value_of(node(T.COS, degrees("60"))) == sympy.Rational(1, 2)

    def test_tan_45(self) -> None:
        assert value_of(node(T.TAN, degrees("45"))) == 1

    def test_cos_30_is_sqrt_three_over_two(self) -> None:
        result = solution_of(node(T.COS, degrees("30")))
        # Форма ответа -- одна дробь √3/2, а не 1/2·√3.
        assert result.type is T.FRACTION
        assert to_sympy(result) == sympy.sqrt(3) / 2

    def test_cot_45(self) -> None:
        assert value_of(node(T.COT, degrees("45"))) == 1

    def test_sec_60(self) -> None:
        assert value_of(node(T.SEC, degrees("60"))) == 2

    def test_csc_30(self) -> None:
        assert value_of(node(T.CSC, degrees("30"))) == 2

    def test_sin_180(self) -> None:
        assert value_of(node(T.SIN, degrees("180"))) == 0


class TestRadians:
    def test_sin_sixth_pi(self) -> None:
        problem = node(T.SIN, node(T.DIVIDE, c("π"), c("6")))
        assert value_of(problem) == sympy.Rational(1, 2)

    def test_cos_third_pi(self) -> None:
        problem = node(T.COS, node(T.DIVIDE, c("π"), c("3")))
        assert value_of(problem) == sympy.Rational(1, 2)

    def test_tan_quarter_pi(self) -> None:
        problem = node(T.TAN, node(T.DIVIDE, c("π"), c("4")))
        assert value_of(problem) == 1

    def test_sin_pi(self) -> None:
        assert value_of(node(T.SIN, c("π"))) == 0

    def test_cos_zero(self) -> None:
        assert value_of(node(T.COS, c("0"))) == 1

    def test_explicit_radian_wrapper(self) -> None:
        problem = node(T.SIN, node(T.RADIAN, node(T.DIVIDE, c("π"), c("6"))))
        assert value_of(problem) == sympy.Rational(1, 2)


class TestSymbolic:
    def test_non_exact_radians_kept(self) -> None:
        problem = node(T.SIN, c("1"))
        assert solution_of(problem).structural_eq(problem)
        assert step_keys(problem) == []

    def test_bare_number_is_radians(self) -> None:
        # sin(30) -- это 30 радиан, точного табличного значения нет.
        problem = node(T.SIN, c("30"))
        assert solution_of(problem).structural_eq(problem)

    def test_variable_kept(self) -> None:
        problem = node(T.COS, CoreNode.variable("x"))
        assert solution_of(problem).structural_eq(problem)

    def test_angle_unit_node_is_preserved(self) -> None:
        problem = degrees("30")
        assert solution_of(problem).structural_eq(problem)


class TestWithArithmetic:
    def test_sin_plus_one(self) -> None:
        problem = node(T.ADD, node(T.SIN, degrees("30")), c("1"))
        assert value_of(problem) == sympy.Rational(3, 2)
        assert step_keys(problem) == ["trig_table_calc", "add"]


class TestErrors:
    def test_tan_90_is_undefined(self) -> None:
        with pytest.raises(SolveError) as info:
            solve(node(T.TAN, degrees("90")))
        assert info.value.explanation_key == "trig_err_undef"

    def test_cot_zero_is_undefined(self) -> None:
        with pytest.raises(SolveError):
            solve(node(T.COT, c("0")))


class TestExplanationKeys:
    def test_keys_exist(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        for key in ("trig_table_calc", "trig_err_undef"):
            assert key in explanations
        assert explanations.arity("trig_table_calc") == 0
        assert "ARG" not in (explanations.raw_template("trig_table_calc", DEFAULT_LOCALE) or "")


class TestRegistration:
    def test_registered(self) -> None:
        assert {T.SIN, T.COS, T.TAN, T.COT, T.SEC, T.CSC, T.DEGREE, T.RADIAN} <= registered_types()
