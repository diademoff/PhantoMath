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


def negative(child: CoreNode) -> CoreNode:
    return node(T.NEGATIVE, child)


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


class TestInverse:
    def test_asin_half(self) -> None:
        assert value_of(node(T.ASIN, c("1/2"))) == sympy.pi / 6

    def test_acos_half(self) -> None:
        assert value_of(node(T.ACOS, c("1/2"))) == sympy.pi / 3

    def test_atan_one(self) -> None:
        assert value_of(node(T.ATAN, c("1"))) == sympy.pi / 4

    def test_acot_one(self) -> None:
        assert value_of(node(T.ACOT, c("1"))) == sympy.pi / 4

    def test_asec_two(self) -> None:
        assert value_of(node(T.ASEC, c("2"))) == sympy.pi / 3

    def test_acsc_two(self) -> None:
        assert value_of(node(T.ACSC, c("2"))) == sympy.pi / 6

    def test_asin_one(self) -> None:
        assert value_of(node(T.ASIN, c("1"))) == sympy.pi / 2

    def test_angle_written_as_fraction(self) -> None:
        result = solution_of(node(T.ASIN, c("1/2")))
        assert result.type is T.FRACTION
        assert to_sympy(result) == sympy.pi / 6


class TestHyperbolic:
    def test_sinh_zero(self) -> None:
        assert value_of(node(T.SINH, c("0"))) == 0

    def test_cosh_zero(self) -> None:
        assert value_of(node(T.COSH, c("0"))) == 1

    def test_tanh_zero(self) -> None:
        assert value_of(node(T.TANH, c("0"))) == 0

    def test_sech_zero(self) -> None:
        assert value_of(node(T.SECH, c("0"))) == 1

    def test_coth_zero_is_undefined(self) -> None:
        with pytest.raises(SolveError):
            solve(node(T.COTH, c("0")))

    def test_csch_zero_is_undefined(self) -> None:
        with pytest.raises(SolveError):
            solve(node(T.CSCH, c("0")))


class TestInverseHyperbolic:
    def test_asinh_zero(self) -> None:
        assert value_of(node(T.ASINH, c("0"))) == 0

    def test_acosh_one(self) -> None:
        assert value_of(node(T.ACOSH, c("1"))) == 0

    def test_atanh_zero(self) -> None:
        assert value_of(node(T.ATANH, c("0"))) == 0

    def test_asech_one(self) -> None:
        assert value_of(node(T.ASECH, c("1"))) == 0

    def test_asinh_one_is_logarithm(self) -> None:
        assert value_of(node(T.ASINH, c("1"))) == sympy.log(1 + sympy.sqrt(2))

    def test_acsch_one_is_logarithm(self) -> None:
        assert value_of(node(T.ACSCH, c("1"))) == sympy.log(1 + sympy.sqrt(2))


class TestMoreSymbolic:
    def test_asin_of_third_kept(self) -> None:
        problem = node(T.ASIN, c("1/3"))
        assert solution_of(problem).structural_eq(problem)

    def test_asin_out_of_domain_kept(self) -> None:
        problem = node(T.ASIN, c("2"))
        assert solution_of(problem).structural_eq(problem)

    def test_sinh_of_one_kept(self) -> None:
        problem = node(T.SINH, c("1"))
        assert solution_of(problem).structural_eq(problem)

    def test_acosh_two_kept(self) -> None:
        problem = node(T.ACOSH, c("2"))
        assert solution_of(problem).structural_eq(problem)


class TestParity:
    def test_sin_is_odd(self) -> None:
        problem = node(T.SIN, negative(CoreNode.variable("x")))
        result = solution_of(problem)
        assert result.type is T.NEGATIVE
        assert result.children[0].type is T.SIN
        assert step_keys(problem) == ["trig_neg_sin"]

    def test_cos_is_even(self) -> None:
        problem = node(T.COS, negative(CoreNode.variable("x")))
        result = solution_of(problem)
        assert result.type is T.COS
        assert step_keys(problem) == ["trig_neg_cos"]

    def test_tan_is_odd(self) -> None:
        problem = node(T.TAN, negative(CoreNode.variable("x")))
        assert solution_of(problem).type is T.NEGATIVE

    def test_sinh_is_odd(self) -> None:
        problem = node(T.SINH, negative(CoreNode.variable("x")))
        assert solution_of(problem).type is T.NEGATIVE
        assert step_keys(problem) == ["trig_hyp_neg_sinh"]

    def test_cosh_is_even(self) -> None:
        problem = node(T.COSH, negative(CoreNode.variable("x")))
        assert solution_of(problem).type is T.COSH

    def test_negative_numeric_angle(self) -> None:
        problem = node(T.SIN, negative(degrees("30")))
        assert to_sympy(solution_of(problem)) == sympy.Rational(-1, 2)

    def test_asin_is_odd(self) -> None:
        problem = node(T.ASIN, negative(c("1/2")))
        assert to_sympy(solution_of(problem)) == -sympy.pi / 6


class TestPeriodicity:
    def test_degrees_above_full_turn(self) -> None:
        problem = node(T.SIN, degrees("390"))
        assert value_of(problem) == sympy.Rational(1, 2)
        assert step_keys(problem) == ["trig_rewrite_coterminal_pos", "trig_table_calc"]

    def test_degrees_negative_full_turn(self) -> None:
        assert value_of(node(T.SIN, degrees("750"))) == sympy.Rational(1, 2)

    def test_radians_multiple_of_pi(self) -> None:
        problem = node(T.SIN, node(T.FRACTION, node(T.MULTIPLY_IMPLICIT, c("13"), c("π")), c("6")))
        assert value_of(problem) == sympy.Rational(1, 2)

    def test_tangent_has_half_period(self) -> None:
        problem = node(T.TAN, node(T.FRACTION, node(T.MULTIPLY_IMPLICIT, c("5"), c("π")), c("4")))
        assert value_of(problem) == 1

    def test_already_reduced_not_rewritten(self) -> None:
        problem = node(T.SIN, degrees("30"))
        assert step_keys(problem) == ["trig_table_calc"]

    def test_plain_radians_not_reduced(self) -> None:
        # sin(7) -- 7 радиан, не рациональное кратное π: не сворачиваем.
        problem = node(T.SIN, c("7"))
        assert solution_of(problem).structural_eq(problem)


class TestErrors:
    def test_tan_90_is_undefined(self) -> None:
        with pytest.raises(SolveError) as info:
            solve(node(T.TAN, degrees("90")))
        assert info.value.explanation_key == "trig_err_undef"

    def test_cot_zero_is_undefined(self) -> None:
        with pytest.raises(SolveError):
            solve(node(T.COT, c("0")))

    def test_acosh_zero_is_undefined(self) -> None:
        # acosh(0) = i·π/2 -- вне действительной области определения.
        with pytest.raises(SolveError) as info:
            solve(node(T.ACOSH, c("0")))
        assert info.value.explanation_key == "trig_err_undef"

    def test_atanh_one_is_undefined(self) -> None:
        with pytest.raises(SolveError):
            solve(node(T.ATANH, c("1")))

    def test_asec_zero_is_undefined(self) -> None:
        with pytest.raises(SolveError):
            solve(node(T.ASEC, c("0")))


class TestExplanationKeys:
    def test_keys_exist(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        zero_arity = (
            "trig_table_calc",
            "trig_func_calc",
            "trig_rewrite_coterminal_pos",
            "trig_neg_sin",
            "trig_neg_cos",
            "trig_neg",
            "trig_hyp_neg_sinh",
            "trig_hyp_neg",
        )
        for key in (*zero_arity, "trig_err_undef"):
            assert key in explanations
        for key in zero_arity:
            assert explanations.arity(key) == 0
            assert "ARG" not in (explanations.raw_template(key, DEFAULT_LOCALE) or "")


class TestRegistration:
    def test_registered(self) -> None:
        functions = {
            T.SIN,
            T.COS,
            T.TAN,
            T.COT,
            T.SEC,
            T.CSC,
            T.ASIN,
            T.ACOS,
            T.ATAN,
            T.ACOT,
            T.ASEC,
            T.ACSC,
            T.SINH,
            T.COSH,
            T.TANH,
            T.COTH,
            T.SECH,
            T.CSCH,
            T.ASINH,
            T.ACOSH,
            T.ATANH,
            T.ACOTH,
            T.ASECH,
            T.ACSCH,
        }
        assert functions | {T.DEGREE, T.RADIAN} <= registered_types()
