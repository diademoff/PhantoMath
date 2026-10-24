"""Тесты модуля интегралов.

Значение проверяется через sympy: результат переводится обратно и сравнивается
с ожидаемой первообразной/числом.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import sympy

from mymath_backend import CoreNode, load_explanations
from mymath_backend import CoreNodeType as T
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult, ResultGroupType
from mymath_backend.solver import SolveError, registered_types, solve
from mymath_backend.solver.sympy_bridge import to_sympy

EXPLANATIONS = Path(__file__).resolve().parents[1] / "mymath_backend" / "data" / "explanations.json"

x = sympy.Symbol("x")


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def var(name: str = "x") -> CoreNode:
    return CoreNode.variable(name)


def node(t: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(t, *children)


def solution_of(problem: CoreNode) -> CoreNode:
    vertical = solve(problem).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution


def entries_of(problem: CoreNode) -> list[dict[str, Any]]:
    """Method cards in order: the textbook card first, the verified one next."""
    group = solve(problem).result.groups[0]
    return [entry.result for entry in group.entries if entry.result]


def step_keys(problem: CoreNode, method: int = 0) -> list[str]:
    result = entries_of(problem)[method]
    return [
        sub["description"]["type"]
        for step in result.get("steps") or []
        for sub in step.get("substeps") or []
    ]


def legacy_step_keys(problem: CoreNode) -> list[str]:
    """Keys of the verified card as built (the switcher offers it only where it adds steps)."""
    from mymath_backend.solver.integrals import _legacy_card

    return [step.key for step in _legacy_card(problem, ["x"])]


class TestIndefinite:
    @pytest.mark.parametrize(
        ("expression", "expected"),
        [
            (node(T.ADD, node(T.MULTIPLY, c("2"), var()), c("3")), x**2 + 3 * x),
            (node(T.DIVIDE, c("1"), var()), sympy.log(sympy.Abs(x))),
            (node(T.EXP, var()), sympy.exp(x)),
            (var(), x**2 / 2),
        ],
    )
    def test_antiderivative(self, expression: CoreNode, expected: sympy.Expr) -> None:
        result = solution_of(node(T.INTEGRAL, expression))
        if result.type is T.LIST:  # "... + C, C in R" (the app's form for polynomials)
            result = result.children[0]
            expected = expected + sympy.Symbol("C")
        assert sympy.simplify(to_sympy(result) - expected) == 0

    def test_power_rule_adds_the_constant_of_integration(self) -> None:
        # the answer is x^3/3 + C, C in R, in two rows.
        problem = node(T.INTEGRAL, node(T.POWER, var(), c("2")))
        result = solution_of(problem)
        assert result.type is T.LIST and result.children[1].type is T.ELEMENT_OF
        assert sympy.simplify(to_sympy(result.children[0]) - (x**3 / 3 + sympy.Symbol("C"))) == 0
        assert step_keys(problem) == ["lesson_calc_int_table_rule", "integrate_msg_addc"]
        assert legacy_step_keys(problem) == ["integrate_msg", "integrate_msg_addc"]

    def test_sum_of_monomials_uses_the_sum_property_then_constant(self) -> None:
        # the integral of 3x^2 + 2x is x^3 + x^2 + C, C in R.
        problem = node(
            T.INTEGRAL,
            node(
                T.ADD,
                node(T.MULTIPLY_IMPLICIT, c("3"), node(T.POWER, var(), c("2"))),
                node(T.MULTIPLY_IMPLICIT, c("2"), var()),
            ),
        )
        assert step_keys(problem) == [
            "lesson_calc_int_sum_rule",
            "lesson_calc_int_term_table",
            "lesson_calc_int_term_table",
            "integrate_msg_addc",
        ]
        assert step_keys(problem, 1) == [
            "integrate_msg_sum",
            "integrate",
            "integrate",
            "integrate_msg_addc",
        ]
        result = solution_of(problem)
        assert result.type is T.LIST
        assert sympy.simplify(to_sympy(result.children[0]) - (x**3 + x**2 + sympy.Symbol("C"))) == 0

    def test_sine_is_one_table_step_then_the_constant(self) -> None:
        problem = node(T.INTEGRAL, node(T.SIN, var()))
        assert step_keys(problem) == ["lesson_calc_int_table_rule", "integrate_msg_addc"]
        assert legacy_step_keys(problem) == ["integrate_msg", "integrate_msg_addc"]
        result = solution_of(problem)
        assert (
            sympy.simplify(to_sympy(result.children[0]) - (-sympy.cos(x) + sympy.Symbol("C"))) == 0
        )

    def test_step_key(self) -> None:
        problem = node(T.INTEGRAL, var())
        assert step_keys(problem) == ["lesson_calc_int_table_rule", "integrate_msg_addc"]
        assert legacy_step_keys(problem) == ["integrate", "integrate_calc", "integrate_msg_addc"]


class TestDefinite:
    def test_polynomial(self) -> None:
        problem = node(T.INTEGRAL_DEFINITE, c("0"), c("1"), var())
        assert solution_of(problem).value == "1/2"

    def test_integer_area(self) -> None:
        problem = node(T.INTEGRAL_DEFINITE, c("0"), c("2"), node(T.MULTIPLY, c("3"), var()))
        assert solution_of(problem).value == "6"

    def test_sine_area(self) -> None:
        problem = node(T.INTEGRAL_DEFINITE, c("0"), c("π"), node(T.SIN, var()))
        assert solution_of(problem).value == "2"


class TestImproper:
    def test_convergent_discontinuity(self) -> None:
        # ∫_0^1 1/√x dx = 2: разрыв в нижнем пределе.
        problem = node(
            T.INTEGRAL_DEFINITE,
            c("0"),
            c("1"),
            node(T.FRACTION, c("1"), node(T.ROOT2, var())),
        )
        assert solution_of(problem).value == "2"
        # The lesson card is the first method; the verified card stays the second.
        assert "lesson_calc_int_imp_value" in step_keys(problem)
        assert step_keys(problem, 1) == [
            "integrate_imp_rewrite_using_lim_sided_msg",
            "integrate_def",
            "limit_solve",
        ]

    def test_divergent(self) -> None:
        # ∫_{-1}^1 1/x² dx расходится.
        denominator = node(T.POWER, var(), c("2"))
        problem = node(
            T.INTEGRAL_DEFINITE,
            c("-1"),
            c("1"),
            node(T.FRACTION, c("1"), denominator),
        )
        # A divergent integral is an answer card, not an error (report #12).
        solution = solution_of(problem)
        assert solution.type is T.TEXT and "расходится" in (solution.value or "")


class TestIterated:
    def test_double(self) -> None:
        # ∫_0^1 ∫_0^2 x·y² dy dx = 4/3 (внутренняя переменная — y).
        integrand = node(T.MULTIPLY_IMPLICIT, var("x"), node(T.POWER, var("y"), c("2")))
        inner = node(T.INTEGRAL_DEFINITE, c("0"), c("2"), integrand)
        problem = node(T.INTEGRAL_DEFINITE, c("0"), c("1"), inner)
        assert solution_of(problem).value == "4/3"
        # the app's two rows: the inner integral (with its own chain) and the outer one.
        assert step_keys(problem) == ["integrate_iterated_inner", "integrate_def"]

    def test_single_variable(self) -> None:
        inner = node(T.INTEGRAL_DEFINITE, c("0"), c("1"), var("x"))
        problem = node(T.INTEGRAL_DEFINITE, c("0"), c("1"), inner)
        with pytest.raises(SolveError, match="две переменные"):
            solve(problem)


class TestRightDash:
    def test_substitute_limits(self) -> None:
        # x²|₀¹ = 1.
        problem = node(T.INTEGRAL_RIGHT_DASH, node(T.POWER, var(), c("2")), c("0"), c("1"))
        assert solution_of(problem).value == "1"
        assert step_keys(problem) == ["integrate_def_bounds"]

    def test_protocol(self) -> None:
        problem = parse_protocol("{integralrightdash({x^3},{1},{2})}")
        assert solution_of(problem).value == "7"


class TestUnsupported:
    def test_no_elementary_antiderivative(self) -> None:
        problem = node(T.INTEGRAL, node(T.EXP, node(T.POWER, var(), c("2"))))
        # An answer card that names the reason, not a SolveError (report #12).
        solution = solution_of(problem)
        assert solution.type is T.TEXT and "элементарн" in (solution.value or "")

    @pytest.mark.parametrize(
        "source",
        [
            "{integral({exp({-x^2})})}",
            "{integral({sin({x^2})})}",
            "{integral({pow({x},{x})})}",
        ],
    )
    def test_no_elementary_antiderivative_protocol(self, source: str) -> None:
        """Неэлементарные первообразные из ввода с клавиатуры — карточка-ответ."""
        solution = solution_of(parse_protocol(source))
        assert solution.type is T.TEXT and "элементарн" in (solution.value or "")


class TestMethod:
    def keys_of(self, problem: CoreNode, method: int = 0) -> list[str]:
        return step_keys(problem, method)

    def test_table_has_no_method_step(self) -> None:
        problem = node(T.INTEGRAL, node(T.EXP, var()))
        assert self.keys_of(problem) == ["lesson_calc_int_table_rule", "integrate_msg_addc"]
        # The verified card still has no method step either.
        assert legacy_step_keys(problem) == [
            "integrate",
            "integrate_calc",
            "integrate_msg_addc",
        ]

    def test_by_parts(self) -> None:
        # x·e^x — интегрирование по частям.
        problem = node(T.INTEGRAL, node(T.MULTIPLY, var(), node(T.EXP, var())))
        assert self.keys_of(problem) == [
            "lesson_calc_int_parts_formula",
            "lesson_calc_int_parts_choose",
            "lesson_calc_int_parts_differential",
            "lesson_calc_int_parts_apply",
            "lesson_calc_int_parts_remainder",
            "lesson_calc_int_parts_answer",
            "integrate_msg_addc",
        ]
        # The verified card is built, but the switcher does not offer a copy.
        assert legacy_step_keys(problem) == [
            "integrate_by_parts_prepare",
            "integrate_parts_differential",
            "integrate_parts_integral",
            "integrate_parts_sub",
            "simplify",
            "integrate_msg",
            "integrate_msg_addc",
        ]

    def test_substitution(self) -> None:
        # sin(2x) — замена.
        argument = node(T.MULTIPLY_IMPLICIT, c("2"), var())
        problem = node(T.INTEGRAL, node(T.SIN, argument))
        assert self.keys_of(problem) == [
            "lesson_calc_int_linear_rule",
            "lesson_calc_int_substitute",
            "lesson_calc_int_differential",
            "lesson_calc_int_rewrite",
            "lesson_calc_int_inner_table",
            "lesson_calc_int_back_sub",
            "integrate_msg_addc",
        ]
        assert legacy_step_keys(problem) == [
            "integrate",
            "integrate_differential_sub",
            "integrate_using_substitution",
            "integrate_calc",
            "integrate_msg_addc",
        ]

    def test_partial_fractions(self) -> None:
        # 1/(x^2 - 1) — простейшие дроби.
        denominator = node(T.SUBTRACT, node(T.POWER, var(), c("2")), c("1"))
        problem = node(T.INTEGRAL, node(T.FRACTION, c("1"), denominator))
        assert self.keys_of(problem) == [
            "lesson_calc_int_frac_factor",
            "lesson_calc_int_frac_form",
            "lesson_calc_int_frac_equations",
            "lesson_calc_int_frac_coeffs",
            "lesson_calc_int_frac_numbers",
            "lesson_calc_int_sum_rule",
            "lesson_calc_int_term_table",
            "lesson_calc_int_term_table",
            "integrate_msg_addc",
        ]
        assert legacy_step_keys(problem) == [
            "integrate",
            "integrate_sep_frac_short",
            "integrate_calc",
            "integrate_msg_addc",
        ]

    def test_improper(self) -> None:
        # ∫_1^∞ 1/x^2 dx — несобственный.
        denominator = node(T.POWER, var(), c("2"))
        problem = node(T.INTEGRAL_DEFINITE, c("1"), c("∞"), node(T.FRACTION, c("1"), denominator))
        assert "lesson_calc_int_imp_value" in self.keys_of(problem)
        assert self.keys_of(problem, 1) == [
            "integrate_imp_rewrite_using_lim",
            "integrate_def",
            "limit_solve",
        ]


class TestExplanationKeys:
    def test_key_exists(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        assert "integrate_calc" in explanations
        assert explanations.arity("integrate_calc") == 0
        assert "ARG" not in (explanations.raw_template("integrate_calc", DEFAULT_LOCALE) or "")


class TestRegistration:
    def test_registered(self) -> None:
        assert {T.INTEGRAL, T.INTEGRAL_DEFINITE} <= registered_types()


def test_constant_multiples_follow_rows() -> None:
    # ∫6x dx pulls 6 out, integrates x, simplifies, adds C.
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    def keys(source: str, method: int = 0) -> list[str]:
        group = solve(parse_protocol(source)).result.groups[0]
        return [
            s["description"]["type"]
            for st in group.entries[method].result["steps"]
            for s in st["substeps"]
        ]

    assert keys("{integral({6x})}") == ["lesson_calc_int_table_rule", "integrate_msg_addc"]
    assert keys("{integral({5})}") == ["lesson_calc_int_table_rule", "integrate_msg_addc"]


def test_linear_integrand_uses_the_sum_property_with_a_table_page_for_the_constant() -> None:
    # the integral of 2x+3 is x^2+3x+C in four rows' worth of keys.
    problem = node(T.INTEGRAL, node(T.ADD, node(T.MULTIPLY_IMPLICIT, c("2"), var()), c("3")))
    assert step_keys(problem) == [
        "lesson_calc_int_sum_rule",
        "lesson_calc_int_term_table",
        "lesson_calc_int_term_table",
        "integrate_msg_addc",
    ]
    assert step_keys(problem, 1) == [
        "integrate_msg_sum",
        "integrate",
        "integrate_msg",
        "integrate_msg_addc",
    ]


def test_x_times_sin_is_one_step_of_by_parts_stages() -> None:
    vertical = solve(parse_protocol("{integral({x*sin({x})})}")).result.vertical()
    assert vertical is not None and vertical.solution is not None
    # One «Вычислите интеграл» step with its stages, then «Прибавить C».
    assert [len(step.substeps) for step in vertical.steps] == [5, 1]


def test_x_times_sin_keeps_the_app_card_alongside_the_lesson() -> None:
    # Case ``int_xsin``: the app shows the by-parts card (six rows with
    # two detail screens). It must stay in the switcher next to the textbook card,
    # otherwise the app has fewer rows than the app for this integral.
    group = solve(parse_protocol("{integral({x*sin({x})})}")).result.group(ResultGroupType.VERTICAL)
    assert group is not None and len(group.entries) == 2
    app_card = CoreSolverVerticalResult.from_contract(group.entries[1].result)
    assert [len(step.substeps) for step in app_card.steps] == [1, 2, 1, 2, 1, 1]
    assert app_card.steps[0].substeps[0].description.type == "integrate_by_parts_prepare"


def test_integral_of_the_absolute_value_of_a_linear_function() -> None:
    from mymath_backend.service import solve_request

    solution = solve_request(parse_protocol("{integral({abs({x})})}").to_contract(), locale="ru")[
        "result"
    ]["solution"]
    assert "ABS" in str(solution) and "FRACTION" in str(solution)
