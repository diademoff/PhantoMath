"""Тесты модуля степеней, корней и логарифмов.

Проверяются точные значения (``√16``, ``log₁₀(1000)``, ``log₂(8)``, ``ln(e)``),
сохранение узла без упрощения (``√2``) и совместная работа с арифметикой
(``√16 + 1 = 5``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mymath_backend import CoreNode, load_explanations
from mymath_backend import CoreNodeType as T
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.solver import SolveError, registered_types, solve

EXPLANATIONS = Path(__file__).resolve().parents[1] / "mymath_backend" / "data" / "explanations.json"


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def node(t: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(t, *children)


def solution_of(problem: CoreNode) -> CoreNode:
    vertical = solve(problem).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution


def step_keys(problem: CoreNode) -> list[str]:
    vertical = solve(problem).result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


def value_of(problem: CoreNode) -> str | None:
    return solution_of(problem).value


class TestRoots:
    def test_square_root_with_a_square_factor_is_pulled_out(self) -> None:
        # three rows, the answer is 2*sqrt(3).
        problem = node(T.ROOT2, c("12"))
        assert step_keys(problem) == ["root_partial_split_arg", "root_mul_each", "root_reduce"]
        answer = solution_of(problem)
        assert answer.type is T.MULTIPLY_IMPLICIT
        assert [child.value for child in answer.children[:1]] == ["2"]
        assert answer.children[1].type is T.ROOT2 and answer.children[1].children[0].value == "3"

    def test_square_free_root_gets_a_decimal_form(self) -> None:
        # √2 = √2 ≈ 1.41421, one calculate row.
        problem = node(T.ROOT2, c("2"))
        answer = solution_of(problem)
        assert answer.type is T.ALTERNATIVE_FORM
        assert answer.children[0].type is T.ROOT2
        assert answer.children[1].type is T.APPROXIMATE_SIGN
        assert step_keys(problem) == ["calculate"]

    def test_square_root_exact(self) -> None:
        assert value_of(node(T.ROOT2, c("25"))) == "5"
        assert step_keys(node(T.ROOT2, c("25"))) == ["pow_to_same_base", "root_reduce"]

    def test_cube_root_exact(self) -> None:
        assert value_of(node(T.ROOT, c("3"), c("27"))) == "3"

    def test_irrational_root_is_kept_with_a_decimal_form(self) -> None:
        problem = node(T.ROOT2, c("2"))
        answer = solution_of(problem)
        assert answer.type is T.ALTERNATIVE_FORM
        assert answer.children[0].structural_eq(problem)
        assert step_keys(problem) == ["calculate"]

    def test_negative_even_root_is_undefined_in_the_reals(self) -> None:
        # "not defined on the real numbers".
        problem = node(T.ROOT2, c("-4"))
        assert solution_of(problem).type is T.TEXT
        assert step_keys(problem) == ["root_sqr_neg"]

    def test_square_root_of_fraction(self) -> None:
        # √(4/9) = 2/3, √(9/4) = 3/2.
        assert value_of(node(T.ROOT2, node(T.FRACTION, c("4"), c("9")))) == "2/3"
        assert value_of(node(T.ROOT2, node(T.FRACTION, c("9"), c("4")))) == "3/2"

    def test_non_square_fraction_is_rationalised(self) -> None:
        # the app: sqrt(1/2) is split, rationalised by sqrt(2)/sqrt(2).
        problem = node(T.ROOT2, node(T.FRACTION, c("1"), c("2")))
        answer = solution_of(problem)
        assert answer.type is T.FRACTION
        assert answer.children[0].type is T.ROOT2 and answer.children[1].value == "2"


class TestLogarithms:
    def test_log10(self) -> None:
        assert value_of(node(T.LOG10, c("1000"))) == "3"

    def test_log_base(self) -> None:
        assert value_of(node(T.LOG, c("8"), c("2"))) == "3"

    def test_non_power_of_ten_is_kept(self) -> None:
        problem = node(T.LOG10, c("5"))
        assert solution_of(problem).structural_eq(problem)

    def test_ln_one(self) -> None:
        assert value_of(node(T.LN, c("1"))) == "0"

    def test_ln_e(self) -> None:
        assert value_of(node(T.LN, c("e"))) == "1"

    def test_exp_zero(self) -> None:
        assert value_of(node(T.EXP, c("0"))) == "1"


class TestWithArithmetic:
    def test_root_combines_with_numbers(self) -> None:
        problem = node(T.ADD, node(T.ROOT2, c("16")), c("1"))
        assert value_of(problem) == "5"
        assert step_keys(problem) == ["root_square", "add"]

    def test_log_combines_with_numbers(self) -> None:
        problem = node(T.ADD, node(T.LOG10, c("1000")), c("1"))
        assert value_of(problem) == "4"


class TestKeptNodeFoldsChild:
    """Модуль оставляет узел, но с уже свёрнутым подвыражением (Q10)."""

    def test_irrational_root_folds_radicand(self) -> None:
        problem = node(T.ROOT2, node(T.ADD, c("2"), c("3")))
        result = solution_of(problem)
        assert result.type is T.ROOT2
        assert result.children[0].value == "5"
        assert step_keys(problem) == ["add"]

    def test_answer_is_not_child_value(self) -> None:
        # √(2+3) не должно давать 5 — шаг сворачивания не подменяет ответ.
        problem = node(T.ROOT2, node(T.ADD, c("2"), c("3")))
        assert solution_of(problem).type is T.ROOT2

    def test_log_keeps_node_with_folded_argument(self) -> None:
        problem = node(T.LOG10, node(T.ADD, c("2"), c("3")))
        result = solution_of(problem)
        assert result.type is T.LOG10
        assert result.children[0].value == "5"
        assert step_keys(problem) == ["add"]

    def test_nth_root_folds_degree_and_radicand(self) -> None:
        problem = node(T.ROOT, c("3"), node(T.ADD, c("1"), c("1")))
        result = solution_of(problem)
        assert result.type is T.ROOT
        assert [child.value for child in result.children] == ["3", "2"]
        assert step_keys(problem) == ["add"]


class TestErrors:
    def test_nth_root_without_degree(self) -> None:
        with pytest.raises(SolveError, match="степень"):
            solve(node(T.ROOT, c("2")))


class TestExplanationKeys:
    def test_keys_exist(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        for key in ("root_simplify", "calculate_short"):
            assert key in explanations
            assert explanations.arity(key) == 0
            assert "ARG" not in (explanations.raw_template(key, DEFAULT_LOCALE) or "")


class TestRegistration:
    def test_registered(self) -> None:
        assert {T.ROOT2, T.ROOT, T.LOG10, T.LN, T.LOG, T.EXP} <= registered_types()


def test_product_of_square_roots_joins_them_then_evaluates_the_root() -> None:
    # sqrt(8)*sqrt(2) is sqrt(16), then 4.
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    result = solve(parse_protocol("{root2({8})*root2({2})}")).result
    vertical = result.vertical()
    assert vertical is not None and result.solution is not None
    assert result.solution.value == "4"
    assert len(vertical.steps) == 2


def test_powers_with_one_base_negative_exponent_and_exponential_equations() -> None:
    # the app on device.
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    def keys(source: str) -> list[str]:
        result = solve(parse_protocol(source)).result
        vertical = result.vertical()
        assert vertical is not None
        return [s.description.type for st in vertical.steps for s in st.substeps]

    assert keys("{2^3*2^4}") == ["pow_same_base_mul", "add"]
    assert keys("{2^-2}") == ["pow_flip_msg", "pow"]
    assert keys("{=({x^3},{8})}") == ["write_as_num_arg", "eq_root"]
    assert keys("{=({2^x},{8})}") == ["pow_to_same_base", "exp_eq_exp_equalise"]


def test_root_of_a_prime_power_takes_six_rows() -> None:
    # sqrt(27) is written as 3^3, split, expanded, reduced to 3 sqrt(3).
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    vertical = solve(parse_protocol("{root2({27})}")).result.vertical()
    assert vertical is not None
    keys = [s.description.type for st in vertical.steps for s in st.substeps]
    assert keys == [
        "pow_to_same_base",
        "root_partial_split_sum",
        "using_expand",
        "pow_with_one",
        "root_mul_each",
        "root_reduce",
    ]


def test_natural_log_of_a_power_of_e_and_log10_of_a_decimal_are_exact() -> None:
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    for source, expected in (("{ln({\\e^3})}", "3"), ("{log10({0.001})}", "-3")):
        solution = solve(parse_protocol(source)).result.vertical().solution
        assert solution is not None and solution.value == expected


def test_logarithm_of_zero_and_of_a_negative_number_is_undefined() -> None:
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    for source, key in (("{ln({0})}", "log_undef_zero"), ("{log10({-5})}", "log_neg_arg")):
        vertical = solve(parse_protocol(source)).result.vertical()
        assert vertical is not None and vertical.solution.type.name == "TEXT"
        assert [s.description.type for st in vertical.steps for s in st.substeps] == [key]


def test_odd_roots_of_negative_numbers_are_real() -> None:
    from mymath_backend.input import parse_protocol
    from mymath_backend.service import solve_request

    def value(source: str) -> str:
        return solve_request(parse_protocol(source).to_contract(), locale="ru")["result"][
            "solution"
        ]["value"]

    assert value("{(-8)^(frac({1},{3}))}") == "-2"
    assert value("{(-8)^(frac({2},{3}))}") == "4"
