"""Карточки простейших тригонометрических уравнений.

Проверяются ключи строк (по порядку), ответ-серия и две общие договорённости:
период пишется ``2kπ``/``kπ`` (параметр перед ``π``), а серии, отличающиеся на
долю периода, сливаются в одну.
"""

from __future__ import annotations

import sympy

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.solver import solve
from mymath_backend.solver.sympy_bridge import to_sympy

_K = sympy.Symbol("k")


def solve_proto(proto: str) -> CoreNode:
    vertical = solve(parse_protocol(proto)).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution


def row_keys(proto: str) -> list[str]:
    vertical = solve(parse_protocol(proto)).result.vertical()
    assert vertical is not None
    return [
        substep.description.type
        for step in vertical.steps
        for substep in step.substeps
        if substep.description is not None
    ]


def series(proto: str) -> set[tuple[sympy.Expr, sympy.Expr]]:
    """``(период, смещение)`` каждой серии ответа."""
    answer = solve_proto(proto)
    equations = answer.children if answer.type is T.LIST else [answer]
    out = set()
    for equation in equations:
        assert equation.type is T.EQUALS
        expression = to_sympy(equation.children[1])
        out.add((sympy.simplify(expression.coeff(_K)), sympy.simplify(expression.subs(_K, 0))))
    return out


SINE_HALF = "{=({sin({x})},{frac({1},{2})})}"
COSINE_NEGATIVE = "{=({cos({x})},{-frac({root2({2})},{2})})}"
COTANGENT_MINUS_ONE = "{=({cot({x})},{-1})}"
COSINE_THIRD = "{=({cos({x})},{frac({1},{3})})}"
SINE_DOUBLE = "{=({sin({2x})},{frac({root2({3})},{2})})}"
COSINE_SHIFTED = "{=({2cos({x-frac({pi},{4})})},{root2({2})})}"
SINE_SCALED = "{=({2sin({x})+1},{0})}"
HOMOGENEOUS = "{=({sin({x})-root2({3})cos({x})},{0})}"


class TestCardRows:
    def test_cosine_negative_value_uses_arcus_second(self) -> None:
        assert row_keys(COSINE_NEGATIVE) == [
            "trig_eq_two_sollutions",
            "trig_eq_isolate",
            "trig_eq_isolate",
            "trig_arcus_second",
            "trig_arcus_second",
            "trig_eq_fun_period",
            "trig_eq_fun_period",
            "eq_linear",
            "trig_eq_positive_period",
            "solution_eq_num",
        ]
        assert series(COSINE_NEGATIVE) == {
            (2 * sympy.pi, 3 * sympy.pi / 4),
            (2 * sympy.pi, 5 * sympy.pi / 4),
        }

    def test_cotangent_has_domain_and_single_series(self) -> None:
        assert row_keys(COTANGENT_MINUS_ONE) == [
            "rel_restrictions_range",
            "trig_eq_isolate",
            "trig_arcus_second",
            "trig_eq_fun_period",
            "rel_restrictions_intersect",
        ]
        assert series(COTANGENT_MINUS_ONE) == {(sympy.pi, 3 * sympy.pi / 4)}

    def test_nontabular_cosine_has_no_arcus_value(self) -> None:
        assert row_keys(COSINE_THIRD) == [
            "trig_eq_two_sollutions",
            "trig_eq_isolate",
            "trig_eq_isolate",
            "trig_eq_fun_period",
            "trig_eq_fun_period",
            "eq_linear",
            "trig_eq_same_angle_period",
            "trig_eq_positive_period",
            "solution_eq_num",
            "calculate",
        ]
        base = sympy.acos(sympy.Rational(1, 3))
        assert series(COSINE_THIRD) == {(2 * sympy.pi, base), (2 * sympy.pi, -base)}

    def test_linear_argument_divides_both_cases(self) -> None:
        assert row_keys(SINE_DOUBLE) == [
            "trig_eq_two_sollutions",
            "trig_eq_isolate",
            "trig_eq_isolate",
            "trig_arcus_first",
            "trig_arcus_first",
            "trig_eq_fun_period",
            "trig_eq_fun_period",
            "eq_linear",
            "eq_linear",
            "trig_eq_positive_period",
            "solution_eq_num",
        ]
        assert series(SINE_DOUBLE) == {
            (sympy.pi, sympy.pi / 6),
            (sympy.pi, sympy.pi / 3),
        }

    def test_shifted_coefficient_argument(self) -> None:
        assert row_keys(COSINE_SHIFTED) == [
            "eq_linear_div",
            "trig_eq_two_sollutions",
            "trig_eq_isolate",
            "simplify",
            "trig_arcus_first",
            "trig_eq_isolate",
            "trig_arcus_first",
            "trig_eq_fun_period",
            "trig_eq_fun_period",
            "eq_linear",
            "eq_linear",
            "trig_eq_canonical_form_arg",
            "trig_eq_positive_period",
            "add_with_zero",
            "solution_eq_num",
        ]
        assert series(COSINE_SHIFTED) == {
            (2 * sympy.pi, sympy.Integer(0)),
            (2 * sympy.pi, sympy.pi / 2),
        }

    def test_scaled_sine_moves_constant_then_divides(self) -> None:
        assert row_keys(SINE_SCALED) == [
            "rel_move_right_const_eq",
            "eq_linear_div",
            "trig_eq_two_sollutions",
            "trig_eq_isolate",
            "trig_eq_isolate",
            "trig_arcus_fourth",
            "trig_arcus_fourth",
            "trig_eq_fun_period",
            "trig_eq_fun_period",
            "trig_eq_canonical_form_arg",
            "eq_linear",
            "trig_eq_positive_period",
            "solution_eq_num",
        ]
        assert series(SINE_SCALED) == {
            (2 * sympy.pi, 7 * sympy.pi / 6),
            (2 * sympy.pi, 11 * sympy.pi / 6),
        }


class TestPeriodNotation:
    def test_parameter_stands_before_pi(self) -> None:
        """``x = π/6 + 2kπ``: узел ``add(π/6, muli(muli(2,k),π))``."""
        answer = solve_proto(SINE_HALF)
        equations = answer.children if answer.type is T.LIST else [answer]
        assert equations
        for equation in equations:
            right = equation.children[1]
            assert right.type is T.ADD
            offset, period = right.children
            assert offset.type is T.FRACTION
            assert period.type is T.MULTIPLY_IMPLICIT
            inner, pi = period.children
            assert pi.type is T.CONSTANT and pi.value == "π"
            assert inner.type is T.MULTIPLY_IMPLICIT
            factor, parameter = inner.children
            assert parameter.type is T.VARIABLE and parameter.value == "k"
            assert factor.type is T.CONSTANT and factor.value == "2"

    def test_single_period_is_k_pi(self) -> None:
        answer = solve_proto(COTANGENT_MINUS_ONE)
        assert answer.type is T.EQUALS
        right = answer.children[1]
        assert right.type is T.ADD
        period = right.children[1]
        assert period.type is T.MULTIPLY_IMPLICIT
        assert period.children[0].type is T.VARIABLE
        assert period.children[0].value == "k"
        assert period.children[1].value == "π"


class TestSeriesMerge:
    def test_two_series_one_period_apart_become_one(self) -> None:
        """``sin x - √3cos x = 0``: ответ ``x = π/3 + kπ``."""
        answer = solve_proto(HOMOGENEOUS)
        assert answer.type is T.EQUALS
        assert to_sympy(answer.children[0]).name == "x"
        assert series(HOMOGENEOUS) == {(sympy.pi, sympy.pi / 3)}


SIN_SQUARED = "{=({2sin({x})^2-sin({x})-1},{0})}"
COS_SQUARED_IDENTITY = "{=({2cos({x})^2+3sin({x})},{0})}"
HOMOGENEOUS_LINEAR = "{=({sin({x})-root2({3})cos({x})},{0})}"
HOMOGENEOUS_QUADRATIC = "{=({sin({x})^2+sin({x})cos({x})-2cos({x})^2},{0})}"
FACTORED_SINE_DOUBLE = "{=({sin({2x})-sin({x})},{0})}"
FACTORED_COSINE = "{=({cos({x})^2-cos({x})},{0})}"


class TestReducibleCards:
    """Уравнения, сводящиеся к простейшим: подстановка, тождество, однородные, разложение."""

    def test_squared_sine_substitution(self) -> None:
        assert row_keys(SIN_SQUARED) == [
            "eq_solve_sub",
            "eq_linear",
            "sub_msg_ret",
            "eq_linear",
            "eq_linear",
            "union",
        ]
        assert series(SIN_SQUARED) == {(2 * sympy.pi / 3, sympy.pi / 2)}

    def test_cosine_squared_identity_first(self) -> None:
        assert row_keys(COS_SQUARED_IDENTITY) == [
            "using_expand",
            "mul_bracket",
            "eq_solve_sub",
            "eq_linear",
            "sub_msg_ret",
            "eq_linear",
            "eq_linear",
            "union",
            "solution_eq_num",
        ]
        assert series(COS_SQUARED_IDENTITY) == {
            (2 * sympy.pi, 7 * sympy.pi / 6),
            (2 * sympy.pi, 11 * sympy.pi / 6),
        }

    def test_homogeneous_linear_to_tangent(self) -> None:
        assert row_keys(HOMOGENEOUS_LINEAR) == [
            "rel_move_right",
            "eq_linear_div",
            "trig_eq_isolate",
            "trig_arcus_first",
            "trig_eq_fun_period",
            "rel_restrictions_intersect",
        ]
        assert series(HOMOGENEOUS_LINEAR) == {(sympy.pi, sympy.pi / 3)}

    def test_homogeneous_quadratic_to_tangent_polynomial(self) -> None:
        assert row_keys(HOMOGENEOUS_QUADRATIC) == [
            "eq_linear_div",
            "eq_solve_sub",
            "eq_linear",
            "sub_msg_ret",
            "eq_linear",
            "eq_linear",
            "rel_restrictions_intersect",
            "solution_eq_num",
            "calculate",
        ]
        assert series(HOMOGENEOUS_QUADRATIC) == {
            (sympy.pi, -sympy.atan(2)),
            (sympy.pi, sympy.pi / 4),
        }

    def test_sine_double_angle_factors(self) -> None:
        assert row_keys(FACTORED_SINE_DOUBLE) == [
            "using_expand",
            "extract_arg",
            "quad_separate_zero_product",
            "eq_linear",
            "eq_linear",
            "union",
            "solution_eq_num",
        ]
        assert series(FACTORED_SINE_DOUBLE) == {
            (sympy.pi, sympy.Integer(0)),
            (2 * sympy.pi / 3, sympy.pi / 3),
        }

    def test_cosine_common_factor(self) -> None:
        assert row_keys(FACTORED_COSINE) == [
            "extract_arg",
            "quad_separate_zero_product",
            "eq_linear",
            "eq_linear",
            "solution_eq_num",
        ]
        assert series(FACTORED_COSINE) == {
            (2 * sympy.pi, sympy.Integer(0)),
            (sympy.pi, sympy.pi / 2),
        }
