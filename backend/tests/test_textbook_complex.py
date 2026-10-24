"""Карточки комплексных чисел: полярная форма, арифметика, степени, корни, уравнения.

Ответы сверяются через sympy, а не строками: карточки пишут число в той же
алгебраической форме, что и клавиатура, а равенство проверяет мост.
"""

from __future__ import annotations

import sympy

from mymath_backend.ast import CoreNode
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import solve
from mymath_backend.solver.sympy_bridge import to_sympy

I_UNIT = sympy.I
Z = sympy.Symbol("z")


def _vertical(
    source: str, command: str | None = None, arg: str | None = None
) -> CoreSolverVerticalResult:
    arguments = [parse_protocol(arg)] if arg is not None else None
    vertical = solve(parse_protocol(source), command=command, args=arguments).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical


def _keys(vertical: CoreSolverVerticalResult) -> list[str]:
    return [
        substep.description.type
        for step in vertical.steps
        for substep in step.substeps
        if substep.description is not None
    ]


def _nested_keys(vertical: CoreSolverVerticalResult) -> list[str]:
    found: list[str] = []
    for step in vertical.steps:
        for substep in step.substeps:
            if substep.subresult is not None:
                found.extend(
                    inner.description.type
                    for inner in substep.subresult.steps
                    for inner in inner.substeps
                    if inner.description is not None
                )
    return found


def _same(node: CoreNode, expected: sympy.Expr) -> None:
    difference = sympy.simplify(sympy.expand_complex(to_sympy(node) - expected))
    assert difference == 0 or abs(complex(difference.evalf())) < 1e-9, (node, expected)


def _root_values(node: CoreNode) -> list[sympy.Expr]:
    """Корни из ответа: ``z = …``, их список или множество значений."""
    members = list(node.children) if node.type.name in ("SET", "LIST") else [node]
    values: list[sympy.Expr] = []
    for member in members:
        if member.type.name == "EQUALS":
            values.append(to_sympy(member.children[1]))
        else:
            values.append(to_sympy(member))
    return values


class TestPolarForm:
    def test_real_number_has_zero_angle(self) -> None:
        vertical = _vertical("{1}", "polar")
        _same(vertical.solution, sympy.Integer(1))
        assert _keys(vertical) == ["complex_calculate_polar", "write_polar_form"]

    def test_negative_real_number_has_angle_pi(self) -> None:
        answer = _vertical("{-3}", "polar").solution
        _same(answer, sympy.Integer(-3))
        assert sympy.simplify(sympy.arg(to_sympy(answer))) == sympy.pi

    def test_polar_form_steps_render_with_the_numbers(self) -> None:
        vertical = _vertical("{2*\\i}", "polar")
        texts = [substep.description.type for step in vertical.steps for substep in step.substeps]
        assert texts == ["complex_calculate_polar", "write_polar_form"]


class TestSumAndDifference:
    def test_sum_of_complex_numbers(self) -> None:
        vertical = _vertical("{(1+3*\\i)+(4-5*\\i)}")
        _same(vertical.solution, 5 - 2 * I_UNIT)
        assert _keys(vertical) == ["complex_separate", "sum_suffix"]

    def test_difference_with_a_radical_real_part(self) -> None:
        vertical = _vertical("{(-2+\\i)-(root2({3})+5*\\i)}")
        _same(vertical.solution, -2 - sympy.sqrt(3) - 4 * I_UNIT)
        assert _keys(vertical) == ["complex_separate", "sum_suffix"]

    def test_difference_the_other_way_round(self) -> None:
        vertical = _vertical("{(root2({3})+5*\\i)-(-2+\\i)}")
        _same(vertical.solution, 2 + sympy.sqrt(3) + 4 * I_UNIT)

    def test_sum_with_real_parts_of_opposite_signs(self) -> None:
        _same(_vertical("{(5+2*\\i)+(2-5*\\i)}").solution, 7 - 3 * I_UNIT)


class TestProduct:
    def test_square_of_a_complex_number(self) -> None:
        vertical = _vertical("{(2+3*\\i)^2}")
        _same(vertical.solution, -5 + 12 * I_UNIT)
        assert _keys(vertical) == ["using_expand", "by_definition", "pow", "sum_suffix"]

    def test_product_keeps_the_foil_cards(self) -> None:
        vertical = _vertical("{(5+2*\\i)*(2-5*\\i)}")
        _same(vertical.solution, 20 - 21 * I_UNIT)
        assert "mul_bracket_cross_each" in _keys(vertical)


class TestQuotient:
    def test_quotient_is_cleared_with_the_conjugate(self) -> None:
        vertical = _vertical("{frac({13+\\i},{7-6*\\i})}")
        _same(vertical.solution, 1 + I_UNIT)
        assert _keys(vertical) == [
            "complex_rationalize_mul",
            "mul_bracket_cross_each",
            "factorise_inv_sim",
            "complex_convert_std_form",
        ]

    def test_quotient_turns_into_the_imaginary_unit(self) -> None:
        _same(_vertical("{frac({5+2*\\i},{2-5*\\i})}").solution, I_UNIT)

    def test_rationalize_uses_the_same_card(self) -> None:
        vertical = _vertical("{frac({1},{root2({3})+\\i})}", "rationalize")
        _same(vertical.solution, (sympy.sqrt(3) - I_UNIT) / 4)
        assert _keys(vertical)[0] == "complex_rationalize_mul"

    def test_product_of_complex_fractions(self) -> None:
        source = "{frac({(-1+3*\\i)*(-2+\\i)+root2({3})*(7-\\i)},{-2*(-2+\\i)^2+(-1-7*\\i)})}"
        _same(_vertical(source).solution, I_UNIT - sympy.sqrt(3))

    def test_negative_power_of_a_quotient(self) -> None:
        source = "{((-1+frac({1},{4})*\\i)/(frac({1},{2})+2*\\i))^(-3)}"
        vertical = _vertical(source)
        _same(vertical.solution, 8 * I_UNIT)
        assert _keys(vertical)[0] == "complex_pow_inverse"


class TestPowers:
    def test_unit_powers_use_the_period(self) -> None:
        for source, expected in (
            ("{\\i^10}", -1),
            ("{\\i^33}", I_UNIT),
            ("{(-\\i)^21}", -I_UNIT),
        ):
            vertical = _vertical(source)
            _same(vertical.solution, expected)
            keys = _keys(vertical)
            assert keys[-2:] == ["complex_i_period", "by_definition"], source

    def test_power_of_an_imaginary_multiple(self) -> None:
        vertical = _vertical("{(-2*\\i)^7}")
        _same(vertical.solution, 128 * I_UNIT)
        assert _keys(vertical) == ["complex_pow_split", "complex_i_period", "by_definition"]

    def test_power_of_a_fraction_times_the_unit(self) -> None:
        _same(_vertical("{(frac({\\i},{2}))^8}").solution, sympy.Rational(1, 256))

    def test_power_by_de_moivre(self) -> None:
        vertical = _vertical("{(1-root2({3})*\\i)^30}")
        _same(vertical.solution, 2**30)
        assert _keys(vertical) == [
            "complex_trig_form",
            "complex_pow_polar_moivre",
            "complex_convert_std_form",
        ]
        assert "complex_mod_arg" in _nested_keys(vertical)

    def test_power_with_the_expand_command(self) -> None:
        vertical = _vertical("{(3+root2({3})*\\i)^20}", "expand")
        _same(vertical.solution, (3 + sympy.sqrt(3) * I_UNIT) ** 20)
        assert "complex_pow_polar_moivre" in _keys(vertical)

    def test_product_powered_through_the_trigonometric_form(self) -> None:
        source = "{((-1+root2({3})*\\i)*frac({1},{4})*(cos({deg({30})})+\\i*sin({deg({30})})))^10}"
        _same(_vertical(source).solution, sympy.Rational(1, 2048) + sympy.sqrt(3) * I_UNIT / 2048)


class TestRoots:
    def test_two_square_roots_of_a_complex_number(self) -> None:
        vertical = _vertical("{1+root2({3})*\\i}", "complex_roots")
        values = _root_values(vertical.solution)
        assert len(values) == 2
        for value in values:
            assert sympy.simplify(value**2 - (1 + sympy.sqrt(3) * I_UNIT)) == 0
        assert _keys(vertical) == ["complex_find_root_polar"]
        assert "complex_root_formula" in _nested_keys(vertical)

    def test_square_roots_of_four_i(self) -> None:
        values = _root_values(_vertical("{4*\\i}", "complex_roots").solution)
        assert len(values) == 2
        assert all(sympy.simplify(value**2 - 4 * I_UNIT) == 0 for value in values)

    def test_roots_of_a_real_number(self) -> None:
        values = _root_values(_vertical("{1}", "complex_roots", "{2}").solution)
        assert sorted((complex(value) for value in values), key=lambda item: item.real) == [-1, 1]


class TestComplexEquations:
    def test_linear_equation_with_a_denominator(self) -> None:
        source = "{=({frac({3+4*\\i},{z})+frac({4-\\i},{3+2*\\i})},{frac({62-50*\\i},{13})})}"
        vertical = _vertical(source)
        assert _root_values(vertical.solution) == [I_UNIT]
        assert _keys(vertical) == [
            "complex_clear_denominator",
            "rel_move_right_const_eq",
            "eq_linear_div",
            "complex_convert_std_form",
        ]
        assert "complex_rationalize_mul" in _nested_keys(vertical)

    def test_linear_equation_with_products_and_powers_of_the_unit(self) -> None:
        source = "{=({(-2+\\i)^2+frac({2-3*\\i},{-5+\\i})+z*\\i^3},{\\i^10})}"
        vertical = _vertical(source)
        values = _root_values(vertical.solution)
        assert len(values) == 1
        expected = -sympy.Rational(7, 2) - sympy.Rational(7, 2) * I_UNIT
        assert sympy.simplify(values[0] - expected) == 0
        assert _keys(vertical)[0] == "simplify"

    def test_quadratic_with_complex_coefficients(self) -> None:
        vertical = _vertical("{=({z^2+(3+2*\\i)*z-5+3*\\i},{0})}")
        values = _root_values(vertical.solution)
        assert len(values) == 2
        for value in values:
            assert sympy.simplify(value**2 + (3 + 2 * I_UNIT) * value - 5 + 3 * I_UNIT) == 0
        assert _keys(vertical) == [
            "complex_quad_coeffs",
            "eq_quad_eval_disc_sub",
            "root_square",
            "quad_formula_abc",
            "coeff_sub",
            "quad_separate_signs",
        ]
        assert vertical.header is not None and vertical.header.type == "eq_quad_solve_complex"

    def test_quadratic_with_a_complex_leading_coefficient(self) -> None:
        vertical = _vertical("{=({(\\i)*z^2+(3-2*\\i)*z-6},{0})}")
        values = _root_values(vertical.solution)
        assert len(values) == 2
        for value in values:
            assert sympy.simplify(I_UNIT * value**2 + (3 - 2 * I_UNIT) * value - 6) == 0
        assert "root_square" in _keys(vertical)
