"""Тесты модуля производной.

Результат сравнивается структурно с ожидаемым деревом: так проверяется и
упрощение (нет лишних ``·1`` и ``+0``, коэффициент сведён), и сами правила.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sympy

from mymath_backend import CoreNode, load_explanations
from mymath_backend import CoreNodeType as T
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import SolveError, registered_types, solve
from mymath_backend.solver.sympy_bridge import to_sympy

EXPLANATIONS = Path(__file__).resolve().parents[1] / "mymath_backend" / "data" / "explanations.json"

# Символ sympy для сверки (``x`` занят конструктором узла).
sx = sympy.Symbol("x")


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def x() -> CoreNode:
    return CoreNode.variable("x")


def node(t: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(t, *children)


def muli(a: CoreNode, b: CoreNode) -> CoreNode:
    return node(T.MULTIPLY_IMPLICIT, a, b)


def derivative(expression: CoreNode) -> CoreNode:
    return node(T.DERIVATION1, expression)


def solution_of(expression: CoreNode) -> CoreNode:
    vertical = solve(derivative(expression)).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution


def legacy_vertical(problem: CoreNode) -> CoreSolverVerticalResult:
    """The verified the app card: the alternative now that the textbook one is first."""
    group = solve(problem).result.groups[0]
    return CoreSolverVerticalResult.from_contract(group.entries[-1].result)


def step_keys(expression: CoreNode) -> list[str]:
    vertical = solve(derivative(expression)).result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


class TestRules:
    def test_constant(self) -> None:
        assert solution_of(c("5")).structural_eq(c("0"))

    def test_variable(self) -> None:
        assert solution_of(x()).structural_eq(c("1"))

    def test_other_variable_is_constant(self) -> None:
        # Две переменные: дифференцируем по первой (x), поэтому y — константа.
        assert solution_of(muli(x(), CoreNode.variable("y"))).structural_eq(CoreNode.variable("y"))

    def test_linear(self) -> None:
        assert solution_of(muli(c("2"), x())).structural_eq(c("2"))

    def test_power(self) -> None:
        assert solution_of(node(T.POWER, x(), c("2"))).structural_eq(muli(c("2"), x()))

    def test_polynomial_is_simplified(self) -> None:
        expression = node(T.ADD, muli(c("3"), node(T.POWER, x(), c("2"))), muli(c("2"), x()))
        expected = node(T.ADD, muli(c("6"), x()), c("2"))
        assert solution_of(expression).structural_eq(expected)

    def test_difference(self) -> None:
        expression = node(T.SUBTRACT, node(T.POWER, x(), c("3")), x())
        expected = node(T.SUBTRACT, muli(c("3"), node(T.POWER, x(), c("2"))), c("1"))
        assert solution_of(expression).structural_eq(expected)

    def test_quotient(self) -> None:
        expression = node(T.DIVIDE, c("1"), x())
        expected = node(T.FRACTION, c("-1"), node(T.POWER, x(), c("2")))
        assert solution_of(expression).structural_eq(expected)

    def test_sine(self) -> None:
        assert solution_of(node(T.SIN, x())).structural_eq(node(T.COS, x()))

    def test_cosine(self) -> None:
        assert solution_of(node(T.COS, x())).structural_eq(node(T.NEGATIVE, node(T.SIN, x())))

    def test_sine_with_chain_rule(self) -> None:
        expression = node(T.SIN, muli(c("2"), x()))
        expected = muli(c("2"), node(T.COS, muli(c("2"), x())))
        assert solution_of(expression).structural_eq(expected)

    def test_natural_log(self) -> None:
        assert solution_of(node(T.LN, x())).structural_eq(node(T.FRACTION, c("1"), x()))

    def test_exponential(self) -> None:
        assert solution_of(node(T.EXP, x())).structural_eq(node(T.EXP, x()))

    def test_square_root(self) -> None:
        expression = node(T.ROOT2, x())
        expected = node(
            T.FRACTION,
            c("1"),
            muli(c("2"), node(T.ROOT2, x())),
        )
        assert solution_of(expression).structural_eq(expected)


class TestSteps:
    def test_variable_rule(self) -> None:
        assert step_keys(x()) == ["derive_var"]

    def test_product_rule_step(self) -> None:
        assert step_keys(muli(x(), node(T.SIN, x()))) == [
            "lesson_calc_rule_product",
            "lesson_calc_part_first",
            "lesson_calc_part_second",
            "lesson_calc_compose_derivatives",
            "lesson_calc_simplify_result",
        ]

    def test_chain_rule_step(self) -> None:
        assert step_keys(node(T.SIN, muli(c("2"), x()))) == [
            "lesson_calc_rule_chain",
            "lesson_calc_part_argument",
            "lesson_calc_compose_derivatives",
            "lesson_calc_simplify_result",
        ]

    def test_header(self) -> None:
        vertical = solve(derivative(x())).result.vertical()
        assert vertical is not None and vertical.header is not None
        assert vertical.header.type == "lesson_calc_header_deriv_table"


class TestUnsupported:
    def test_sympy_fallback_handles_more_functions(self) -> None:
        # sec нет в таблице правил, но sympy берёт производную.
        result = solution_of(node(T.SEC, x()))
        assert sympy.simplify(to_sympy(result) - (sympy.sec(sx) * sympy.tan(sx))) == 0

    def test_variable_exponent_goes_through_sympy(self) -> None:
        result = solution_of(node(T.POWER, x(), x()))
        expected = sx**sx * (sympy.log(sx) + 1)
        assert sympy.simplify(to_sympy(result) - expected) == 0


class TestExplanationKeys:
    def test_keys_exist_with_matching_arity(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        for key in ("find_derivative", "derive_short"):
            assert key in explanations
            template = explanations.raw_template(key, DEFAULT_LOCALE) or ""
            assert explanations.arity(key) == 0
            assert "ARG" not in template


class TestHigherOrder:
    def _solution(self, source: str, order: str) -> CoreNode:
        vertical = solve(
            parse_protocol(source),
            command="nth_derivative",
            args=[parse_protocol(order)],
        ).result.vertical()
        assert vertical is not None and vertical.solution is not None
        return vertical.solution

    def _keys(self, source: str, order: str) -> list[str]:
        vertical = solve(
            parse_protocol(source),
            command="nth_derivative",
            args=[parse_protocol(order)],
        ).result.vertical()
        assert vertical is not None
        return [sub.description.type for step in vertical.steps for sub in step.substeps]

    def test_second(self) -> None:
        assert self._solution("{x^3}", "{2}").structural_eq(muli(c("6"), x()))
        assert self._keys("{x^3}", "{2}") == ["derive_higher_order", "second_derivative"]

    def test_third(self) -> None:
        assert self._solution("{x^4}", "{3}").structural_eq(muli(c("24"), x()))
        assert self._keys("{x^4}", "{3}") == [
            "derive_higher_order",
            "derive_multi",
            "find_high_order_derivative",
        ]

    def test_first_is_plain(self) -> None:
        assert self._keys("{x^2}", "{1}") == ["find_derivative"]

    def test_nested_ddx_is_supported(self) -> None:
        """d/dx(d/dx x²) — второй порядок без ошибки «узел DERIVATION1…»."""
        vertical = solve(
            parse_protocol("{derivation_prime({derivation_prime({x^2})})}")
        ).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.structural_eq(c("2"))


class TestLeibnizRows:
    def test_sum_of_monomials_uses_the_sum_rule_then_products(self) -> None:
        # d/dx (3x^2 + 2x) = 6x + 2: rule, one page per term, then the products.
        problem = node(
            T.DERIVATION1_DIFF,
            x(),
            node(T.ADD, muli(c("3"), node(T.POWER, x(), c("2"))), muli(c("2"), x())),
        )
        vertical = legacy_vertical(problem)
        assert vertical is not None and vertical.solution is not None
        assert [[s.description.type for s in step.substeps] for step in vertical.steps] == [
            ["derive_use_rule"],
            ["derive", "derive"],
            ["product"],
        ]
        assert vertical.solution.structural_eq(node(T.ADD, muli(c("6"), x()), c("2")))

    def test_sine_is_one_table_step(self) -> None:
        problem = node(T.DERIVATION1_DIFF, x(), node(T.SIN, x()))
        vertical = legacy_vertical(problem)
        assert vertical is not None
        assert [s.description.type for st in vertical.steps for s in st.substeps] == [
            "derive_table_desc"
        ]


class TestLeibniz:
    def test_with_respect(self) -> None:
        # d/dx (x²) = 2x.
        problem = node(T.DERIVATION1_DIFF, x(), node(T.POWER, x(), c("2")))
        vertical = legacy_vertical(problem)
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.structural_eq(muli(c("2"), x()))
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        assert keys == ["derive_table_desc", "sub", "pow_with_one"]  # the app rows

    def test_other_variable(self) -> None:
        # d/dx (x·y) = y.
        expression = muli(x(), CoreNode.variable("y"))
        problem = node(T.DERIVATION1_DIFF, x(), expression)
        vertical = legacy_vertical(problem)
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.structural_eq(CoreNode.variable("y"))


class TestNotation:
    def test_prime(self) -> None:
        vertical = solve(parse_protocol("{prime({x^2})}")).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.structural_eq(muli(c("2"), x()))
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        assert keys == ["lesson_calc_rule_power", "lesson_calc_simplify_result"]

    def test_second_prime(self) -> None:
        vertical = solve(parse_protocol("{derivation2_prime({x^3})}")).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.structural_eq(muli(c("6"), x()))

    @pytest.mark.parametrize(
        "source",
        ["{derivation_prime({x},{y})}", "{nderivation({x},{2})}", "{prime({x},{y})}"],
    )
    def test_extra_child_rejected(self, source: str) -> None:
        """Лишний ребёнок молча не отбрасывается."""
        with pytest.raises(SolveError, match="одно выражение"):
            solve(parse_protocol(source))


class TestRegistration:
    def test_registered(self) -> None:
        assert {
            T.DERIVATION,
            T.DERIVATION1,
            T.DERIVATION1_DIFF,
            T.PRIME,
            T.DERIVATION2_PRIME,
        } <= registered_types()


class TestRealFallback:
    """Sympy-откат дифференцирует по вещественной переменной."""

    def test_abs_derivative_is_sign(self) -> None:
        vertical = solve(parse_protocol("{derivation_prime({abs({x})})}")).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.type is T.SIGN
        assert vertical.solution.children[0].value == "x"


def test_chain_rule_for_sin_of_kx_follows_rows() -> None:
    # d/dx sin(2x) uses g = 2x, two derivative pages, back-substitution.
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    group = solve(parse_protocol("{derivation_diff({x},{sin({2x})})}")).result.groups[0]
    vertical = CoreSolverVerticalResult.from_contract(group.entries[-1].result)
    assert vertical is not None
    keys = [s.description.type for st in vertical.steps for s in st.substeps]
    assert keys == ["derive_chain_where", "derive", "derive", "sub_msg_ret", "var_order"]


def test_derivative_of_k_x_squared_pulls_the_constant_out() -> None:
    # d/dx 3x^2 = 3 * d/dx x^2 = 3 * 2x = 6x.
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    group = solve(parse_protocol("{derivation_diff({x},{3x^2})}")).result.groups[0]
    # Entry 0 is the textbook card; the verified card is the alternative.
    vertical = CoreSolverVerticalResult.from_contract(group.entries[-1].result)
    keys = [s.description.type for st in vertical.steps for s in st.substeps]
    assert keys == ["derive_use_rule", "derive_table_desc", "product"]


def test_product_of_simple_factors_gets_rule_two_pages_and_simplify() -> None:
    # d/dx (x sin x) is a rule row, two derivative pages, simplify.
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    group = solve(parse_protocol("{derivation_diff({x},{x*sin({x})})}")).result.groups[0]
    steps = group.entries[-1].result["steps"]
    assert [len(st["substeps"]) for st in steps] == [1, 2, 1]


def test_derivative_of_e_to_x_is_one_table_row() -> None:
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    group = solve(parse_protocol("{derivation_diff({x},{\\e^x})}")).result.groups[0]
    steps = group.entries[-1].result["steps"]
    assert [s["description"]["type"] for st in steps for s in st["substeps"]] == [
        "derive_table_desc"
    ]


def test_derivative_of_a_root_is_collected_into_one_fraction() -> None:
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    solution = (
        solve(parse_protocol("{derivation_diff({x},{root2({1+x^2})})}")).result.vertical().solution
    )
    assert solution is not None and solution.type.name == "FRACTION"


def test_quotient_of_simple_terms_has_rule_pages_and_a_shortest_answer() -> None:
    group = solve(parse_protocol("{derivation_diff({x},{frac({x},{x+1})})}")).result.groups[0]
    vertical = CoreSolverVerticalResult.from_contract(group.entries[-1].result)
    assert vertical.solution is not None
    assert [len(step.substeps) for step in vertical.steps] == [1, 2, 1]
    assert vertical.solution.type is T.FRACTION and vertical.solution.children[0].value == "1"


def test_polynomial_derivative_and_integral_are_not_factored() -> None:
    from mymath_backend.service import solve_request

    def solution(source: str) -> dict:
        return solve_request(parse_protocol(source).to_contract(), locale="ru")["result"][
            "solution"
        ]

    derivative = solution("{derivation_diff({x},{x^3-4x^2+7})}")
    assert derivative["type"] == "SUBTRACT"  # 3x^2 - 8x, not x(3x - 8)
    integral = solution("{integral({3x^2-2x+1})}")
    assert "MULTIPLY" not in str(integral).replace("MULTIPLY_IMPLICIT", "")


def test_second_derivative_in_a_sum_is_evaluated_not_factored() -> None:
    """The phone sends d²/dx²(3x²) − 2x: the answer is 6 − 2x, not −2(x − 3)."""
    problem = parse_protocol("{derivation2_prime({x^2 3})-2x}")
    vertical = solve(problem).result.vertical()
    assert vertical is not None and vertical.solution is not None
    assert vertical.solution.type is T.SUBTRACT  # 6 - 2x, not a factored product
    assert sympy.simplify(to_sympy(vertical.solution) - (sympy.Integer(6) - 2 * sx)) == 0
    keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
    assert "factorise_call" not in keys


def test_e_is_eulers_number_not_the_variable_of_differentiation() -> None:
    vertical = solve(parse_protocol("{derivation_prime({e^2 x})}")).result.vertical()
    assert vertical is not None and vertical.solution is not None
    assert sympy.simplify(to_sympy(vertical.solution) - sympy.E**2) == 0
    assert to_sympy(vertical.solution).free_symbols == set()


def test_e_does_not_leave_log_e_in_a_product_derivative() -> None:
    vertical = solve(parse_protocol("{derivation_prime({x^2 e^x sin({x})})}")).result.vertical()
    assert vertical is not None and vertical.solution is not None
    expression = to_sympy(vertical.solution)
    expected = sympy.diff(sx**2 * sympy.exp(sx) * sympy.sin(sx), sx)
    assert sympy.simplify(expression - expected) == 0
    # ``e`` is Euler's number: it must not survive as a free symbol.
    assert expression.free_symbols == {sx}


def test_second_remarkable_limit_still_answers_eulers_number() -> None:
    vertical = solve(parse_protocol("{lim({inf},{(1+frac({1},{x}))^x})}")).result.vertical()
    assert vertical is not None and vertical.solution is not None
    assert vertical.solution.structural_eq(CoreNode.constant("e"))
    assert to_sympy(vertical.solution) is sympy.E
