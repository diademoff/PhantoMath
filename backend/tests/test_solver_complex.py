"""Тесты комплексных чисел.

Мнимая единица — константа ``i``. Re/Im/сопряжение и арифметика считаются
sympy; проверяем значения через мост.
"""

from __future__ import annotations

from pathlib import Path

import sympy

from mymath_backend import CoreNode, load_explanations
from mymath_backend import CoreNodeType as T
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.input import parse_protocol
from mymath_backend.solver import registered_types, solve
from mymath_backend.solver.complex import contains_imaginary
from mymath_backend.solver.sympy_bridge import to_sympy

EXPLANATIONS = Path(__file__).resolve().parents[1] / "mymath_backend" / "data" / "explanations.json"

I_UNIT = sympy.I


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def i() -> CoreNode:
    return CoreNode.constant("i")


def node(t: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(t, *children)


def muli(a: CoreNode, b: CoreNode) -> CoreNode:
    return node(T.MULTIPLY_IMPLICIT, a, b)


def solution_of(problem: CoreNode) -> CoreNode:
    vertical = solve(problem).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution


def step_keys(problem: CoreNode) -> list[str]:
    vertical = solve(problem).result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


Z = node(T.ADD, c("1"), muli(c("2"), i()))


class TestParts:
    def test_real_part(self) -> None:
        problem = node(T.REAL, Z)
        assert solution_of(problem).value == "1"
        assert step_keys(problem) == ["complex_find_parts", "complex_rewrite"]

    def test_imaginary_part(self) -> None:
        assert solution_of(node(T.IMAGINARY, Z)).value == "2"

    def test_conjugate(self) -> None:
        problem = node(T.CONJUGATE, Z)
        assert sympy.simplify(to_sympy(solution_of(problem)) - (1 - 2 * I_UNIT)) == 0
        assert step_keys(problem) == ["complex_conjugate"]


class TestArithmetic:
    def test_product_of_complex_numbers(self) -> None:
        problem = node(T.MULTIPLY, Z, node(T.SUBTRACT, c("3"), i()))
        result = solution_of(problem)
        assert sympy.simplify(to_sympy(result) - (5 + 5 * I_UNIT)) == 0
        assert step_keys(problem) == [
            "mul_bracket_cross_each",
            "product",
            "product",
            "by_definition",
            "mul_with_neg_one",
            "add",
            "sum_suffix",
        ]

    def test_pure_imaginary(self) -> None:
        problem = node(T.MULTIPLY, i(), i())
        assert sympy.simplify(to_sympy(solution_of(problem)) - (-1)) == 0

    def test_contains_imaginary(self) -> None:
        assert contains_imaginary(Z)
        assert not contains_imaginary(c("2"))


class TestComplexPowerRoots:
    def _run(self, source: str, command: str, arg: str) -> tuple[list[str], CoreNode]:
        vertical = solve(
            parse_protocol(source),
            command=command,
            args=[parse_protocol(arg)],
        ).result.vertical()
        assert vertical is not None and vertical.solution is not None
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        return keys, vertical.solution

    def test_power(self) -> None:
        # (1 + i)² = 2i.
        keys, solution = self._run(r"{1+\i}", "complex_power", "{2}")
        assert keys == [
            "complex_conjugate_find",
            "complex_add_bars",
            "complex_mod_formula",
            "complex_find_parts_pair",
            "complex_pow_polar_moivre_simple",
        ]
        assert sympy.simplify(to_sympy(solution) - (1 + I_UNIT) ** 2) == 0

    def test_roots(self) -> None:
        # Корни второй степени из 1 — множество {−1, 1}.
        keys, solution = self._run("{1}", "complex_roots", "{2}")
        assert keys == ["complex_find_root_polar"]
        assert solution.type is T.SET and len(solution.children) == 2

    def test_roots_of_complex(self) -> None:
        _, solution = self._run(r"{1+\i}", "complex_roots", "{2}")
        assert solution.type is T.SET and len(solution.children) == 2

    def test_polar_multiply(self) -> None:
        # (1 + i)(3 − i) = 4 + 2i.
        keys, solution = self._run(r"{1+\i}", "complex_polar_multiply", r"{3-\i}")
        assert keys == ["complex_mul_polar"]
        assert sympy.simplify(to_sympy(solution) - (1 + I_UNIT) * (3 - I_UNIT)) == 0

    def test_polar_divide(self) -> None:
        # (1 + i)/(1 − i) = i.
        keys, solution = self._run(r"{1+\i}", "complex_polar_divide", r"{1-\i}")
        assert keys == ["complex_divide_polar"]
        assert sympy.simplify(to_sympy(solution) - I_UNIT) == 0


class TestExplanationKeys:
    def test_keys_exist(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        for key in ("complex_rewrite", "complex_conjugate", "complex_convert_std_form"):
            assert key in explanations
            assert explanations.arity(key) == 0
            assert "ARG" not in (explanations.raw_template(key, DEFAULT_LOCALE) or "")


class TestRegistration:
    def test_registered(self) -> None:
        assert {T.REAL, T.IMAGINARY, T.CONJUGATE} <= registered_types()


def test_product_of_a_plus_i_and_c_minus_i_has_foil_and_distributive_cards() -> None:
    # (2+i)(1-i) = 3 - i, shown by FOIL and by distribution.
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    source = "{(3+imag({}))*(1-imag({}))}"
    result = solve(parse_protocol(source)).result
    assert len(result.groups[0].entries) == 2
    solution = result.solution
    assert solution is not None and solution.children[0].value == "4"


def test_the_unit_i_is_never_sent_as_a_bare_imaginary_node() -> None:
    """The app has no IMAGINARY node type: it would draw nothing where the i belongs."""
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    for source in ("{=({x^2+2x+5},{0})}", "{(2+\\i)*(1-\\i)}", "{(1+\\i)^2}"):
        data = solve(parse_protocol(source))
        assert "IMAGINARY" not in repr(data.to_contract()), source


def test_one_plus_i_over_one_minus_i_has_the_conjugate_card() -> None:
    from mymath_backend.service import solve_request

    result = solve_request(
        parse_protocol("{frac({1+imag({})},{1-imag({})})}").to_contract(), locale="ru"
    )["result"]
    keys = [
        [s["description"]["type"] for st in entry["result"]["steps"] for s in st["substeps"]]
        for group in result["groups"]
        for entry in group["entries"]
    ]
    assert keys[0][0] == "complex_rationalize_mul" and keys[0][-1] == "frac_reduce_frac_alg"


def test_polar_cards_for_a_quotient_and_a_square() -> None:
    from mymath_backend.service import solve_request

    def cards(source: str) -> list[list[str]]:
        result = solve_request(parse_protocol(source).to_contract(), locale="ru")["result"]
        return [
            [s["description"]["type"] for st in e["result"]["steps"] for s in st["substeps"]]
            for g in result["groups"]
            for e in g["entries"]
        ]

    assert cards("{frac({1+imag({})},{1-imag({})})}")[1][0] == "complex_trig_form"
    assert cards("{(1+imag({}))^2}")[2][:2] == ["complex_trig_form", "complex_pow_polar_moivre"]
