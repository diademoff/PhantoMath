"""Тесты модуля линейных неравенств.

Проверяются знак отношения (в том числе смена знака при делении на
отрицательное число), изоляция неизвестного и шаги.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sympy

from mymath_backend import CoreNode, load_explanations
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.solver import SolveError, registered_types, solve
from mymath_backend.solver.sympy_bridge import to_sympy

EXPLANATIONS = Path(__file__).resolve().parents[1] / "mymath_backend" / "data" / "explanations.json"


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def var(name: str) -> CoreNode:
    return CoreNode.variable(name)


def node(t: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(t, *children)


def muli(a: CoreNode, b: CoreNode) -> CoreNode:
    return node(T.MULTIPLY_IMPLICIT, a, b)


def ineq(t: T, left: CoreNode, right: CoreNode) -> CoreNode:
    return node(t, left, right)


def solution_of(problem: CoreNode) -> CoreNode:
    vertical = solve(problem).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution


def step_keys(problem: CoreNode) -> list[str]:
    vertical = solve(problem).result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


class TestSolve:
    def test_less_than(self) -> None:
        problem = ineq(T.LESS_THAN, node(T.ADD, muli(c("2"), var("x")), c("1")), c("5"))
        solution = solution_of(problem)
        assert solution.type is T.LESS_THAN
        assert solution.children[0].value == "x"
        assert solution.children[1].value == "2"
        assert step_keys(problem) == ["rel_move_right_const_ineq", "sub", "ineq_linear_div"]

    def test_negative_coefficient_flips(self) -> None:
        problem = ineq(T.LESS_THAN, muli(c("-2"), var("x")), c("4"))
        solution = solution_of(problem)
        assert solution.type is T.GREATER_THAN
        assert solution.children[1].value == "-2"
        assert step_keys(problem) == [
            "ineq_linear_div_neg",
            "div_with_self",
            "div_pos_neg",
            "quotient",
        ]

    def test_already_isolated(self) -> None:
        problem = ineq(T.GREATER_THAN_EQUAL, var("x"), c("3"))
        solution = solution_of(problem)
        assert solution.type is T.GREATER_THAN_EQUAL
        assert solution.children[1].value == "3"
        assert step_keys(problem) == []

    def test_less_or_equal(self) -> None:
        problem = ineq(T.LESS_THAN_EQUAL, muli(c("3"), var("x")), c("6"))
        solution = solution_of(problem)
        assert solution.type is T.LESS_THAN_EQUAL
        assert solution.children[1].value == "2"

    def test_not_equals(self) -> None:
        problem = ineq(T.NOT_EQUALS, var("x"), c("2"))
        solution = solution_of(problem)
        assert solution.type is T.NOT_EQUALS
        assert solution.children[1].value == "2"

    def test_header(self) -> None:
        problem = ineq(T.LESS_THAN, node(T.ADD, muli(c("2"), var("x")), c("1")), c("5"))
        vertical = solve(problem).result.vertical()
        assert vertical is not None
        assert [h.type for h in vertical.steps[0].step_headers] == ["rel_move_right_const_ineq"]


class TestQuadratic:
    def quad(self) -> CoreNode:
        # x^2 - 5x + 6
        return node(
            T.ADD,
            node(T.POWER, var("x"), c("2")),
            node(T.NEGATIVE, muli(c("5"), var("x"))),
            c("6"),
        )

    def test_less_than_inside(self) -> None:
        # x^2 - 5x + 6 < 0 -> (2, 3)
        answer = solution_of(ineq(T.LESS_THAN, self.quad(), c("0")))
        assert answer.type is T.OPEN_OPEN_INTERVAL
        assert [child.value for child in answer.children] == ["2", "3"]

    def test_greater_than_outside(self) -> None:
        # x^2 - 5x + 6 > 0 -> (-inf, 2) ∪ (3, inf)
        answer = solution_of(ineq(T.GREATER_THAN, self.quad(), c("0")))
        assert answer.type is T.UNION

    def test_less_equal_closed(self) -> None:
        answer = solution_of(ineq(T.LESS_THAN_EQUAL, self.quad(), c("0")))
        assert answer.type is T.CLOSED_CLOSED_INTERVAL

    def test_always_true(self) -> None:
        # x^2 + 1 > 0 для всех x.
        problem = ineq(T.GREATER_THAN, node(T.ADD, node(T.POWER, var("x"), c("2")), c("1")), c("0"))
        answer = solution_of(problem)
        assert answer.type is T.OPEN_OPEN_INTERVAL

    def test_unary_minus_precedence(self) -> None:
        # -x^2 - 1 < 0 -> истинно для всех x (проверка приоритета унарного минуса).
        problem = ineq(
            T.LESS_THAN,
            node(T.SUBTRACT, node(T.NEGATIVE, node(T.POWER, var("x"), c("2"))), c("1")),
            c("0"),
        )
        answer = solution_of(problem)
        assert answer.type is T.OPEN_OPEN_INTERVAL
        assert answer.children[0].type is T.NEGATIVE


class TestRationalInequality:
    def test_fraction_less(self) -> None:
        # 1/(x-1) < 2 -> (-inf, 1) ∪ (3/2, inf)
        problem = ineq(
            T.LESS_THAN, node(T.FRACTION, c("1"), node(T.SUBTRACT, var("x"), c("1"))), c("2")
        )
        answer = solution_of(problem)
        assert answer.type is T.UNION

    def test_pole_excluded_root_included(self) -> None:
        # (x-1)/(x+1) >= 0 -> (-inf,-1) ∪ [1, inf)
        problem = ineq(
            T.GREATER_THAN_EQUAL,
            node(
                T.FRACTION,
                node(T.SUBTRACT, var("x"), c("1")),
                node(T.ADD, var("x"), c("1")),
            ),
            c("0"),
        )
        answer = solution_of(problem)
        assert answer.type is T.UNION
        assert answer.children[1].type is T.CLOSED_OPEN_INTERVAL


class TestAbsInequality:
    def test_less_than(self) -> None:
        # |x| < 2 -> (-2, 2).
        problem = ineq(T.LESS_THAN, node(T.ABS, var("x")), c("2"))
        answer = solution_of(problem)
        assert answer.type is T.OPEN_OPEN_INTERVAL
        assert [child.value for child in answer.children] == ["-2", "2"]

    def test_greater_union(self) -> None:
        # |x| > 3 -> (-∞, -3) ∪ (3, ∞).
        problem = ineq(T.GREATER_THAN, node(T.ABS, var("x")), c("3"))
        assert solution_of(problem).type is T.UNION

    def test_always_true(self) -> None:
        # |x| ≥ -1 -> вся прямая.
        problem = ineq(T.GREATER_THAN_EQUAL, node(T.ABS, var("x")), c("-1"))
        answer = solution_of(problem)
        assert answer.type is T.OPEN_OPEN_INTERVAL
        assert answer.children[0].type is T.NEGATIVE

    def test_step_key(self) -> None:
        problem = ineq(T.LESS_THAN, node(T.ABS, var("x")), c("2"))
        vertical = solve(problem).result.vertical()
        assert vertical is not None
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        assert keys == ["ineq_separate_abs", "intersection", "ineq_linear", "intersection", "union"]


class TestInequalitySystem:
    def test_open_intersection(self) -> None:
        problem = node(
            T.SYSTEM,
            ineq(T.LESS_THAN, var("x"), c("3")),
            ineq(T.GREATER_THAN, var("x"), c("1")),
        )
        answer = solution_of(problem)
        assert answer.type is T.OPEN_OPEN_INTERVAL
        assert [child.value for child in answer.children] == ["1", "3"]

    def test_empty(self) -> None:
        problem = node(
            T.SYSTEM,
            ineq(T.GREATER_THAN, var("x"), c("2")),
            ineq(T.LESS_THAN, var("x"), c("0")),
        )
        assert solution_of(problem).type is T.EMPTY


class TestCompoundInequality:
    def test_double_open(self) -> None:
        # 1 < x < 3 -> (1, 3)
        problem = node(T.LESS_THAN, c("1"), var("x"), c("3"))
        answer = solution_of(problem)
        assert answer.type is T.OPEN_OPEN_INTERVAL
        assert [child.value for child in answer.children] == ["1", "3"]

    def test_double_linear_expression(self) -> None:
        # 1 <= 2x+1 <= 7 -> [0, 3]
        middle = node(T.ADD, muli(c("2"), var("x")), c("1"))
        problem = node(T.LESS_THAN_EQUAL, c("1"), middle, c("7"))
        answer = solution_of(problem)
        assert answer.type is T.CLOSED_CLOSED_INTERVAL
        assert [child.value for child in answer.children] == ["0", "3"]


class TestTranscendentalInequality:
    def test_irrational(self) -> None:
        # sqrt(x+1) < x-1 -> (3, inf)
        problem = ineq(
            T.LESS_THAN,
            node(T.ROOT2, node(T.ADD, var("x"), c("1"))),
            node(T.SUBTRACT, var("x"), c("1")),
        )
        answer = solution_of(problem)
        assert answer.type is T.OPEN_OPEN_INTERVAL
        assert answer.children[0].value == "3"

    def test_exponential(self) -> None:
        # 2^x < 8 -> (-inf, 3)
        problem = ineq(T.LESS_THAN, node(T.POWER, c("2"), var("x")), c("8"))
        answer = solution_of(problem)
        assert answer.type is T.OPEN_OPEN_INTERVAL
        assert answer.children[1].value == "3"

    def test_logarithmic(self) -> None:
        # log_2 x >= 3 -> [8, inf)
        problem = ineq(T.GREATER_THAN_EQUAL, node(T.LOG, var("x"), c("2")), c("3"))
        answer = solution_of(problem)
        assert answer.type is T.CLOSED_OPEN_INTERVAL
        assert answer.children[0].value == "8"


class TestUnsupported:
    def test_two_variables(self) -> None:
        problem = ineq(T.LESS_THAN, node(T.ADD, var("x"), var("y")), c("1"))
        with pytest.raises(SolveError, match="одно неизвестное"):
            solve(problem)


class TestExplanationKeys:
    def test_keys_exist_with_matching_arity(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        for key, arity in (
            ("move", 0),
            ("ineq_linear_div", 1),
            ("ineq_linear_div_neg", 1),
            ("ineq_solve_short", 0),
        ):
            assert key in explanations
            assert explanations.arity(key) == arity


class TestRegistration:
    def test_registered(self) -> None:
        assert {
            T.LESS_THAN,
            T.LESS_THAN_EQUAL,
            T.GREATER_THAN,
            T.GREATER_THAN_EQUAL,
            T.NOT_EQUALS,
        } <= registered_types()


class TestPeriodicInequality:
    """Тригонометрическое неравенство без отрезка: общий ответ с ``+kT``."""

    def test_sine_greater_than_half(self) -> None:
        problem = ineq(T.GREATER_THAN, node(T.SIN, var("x")), node(T.FRACTION, c("1"), c("2")))
        solution = solution_of(problem)
        assert solution.type is T.OPEN_OPEN_INTERVAL
        assert step_keys(problem) == ["trig_find_intervals_smpl", "trig_general_sol"]
        names = {child.value for child in solution.walk() if child.type is T.VARIABLE}
        assert "k" in names

    def test_non_strict_keeps_closed_ends(self) -> None:
        problem = ineq(
            T.GREATER_THAN_EQUAL, node(T.SIN, var("x")), node(T.FRACTION, c("1"), c("2"))
        )
        assert solution_of(problem).type is T.CLOSED_CLOSED_INTERVAL

    def test_abs_sine_uses_shorter_period(self) -> None:
        # ``solveset`` не берёт |sin| на периоде -- вступает метод интервалов.
        problem = ineq(
            T.GREATER_THAN,
            node(T.ABS, node(T.SIN, var("x"))),
            node(T.FRACTION, c("1"), c("2")),
        )
        solution = solution_of(problem)
        assert solution.type is T.OPEN_OPEN_INTERVAL
        assert step_keys(problem) == ["trig_find_intervals_smpl", "trig_general_sol"]

    def test_tangent_period_pi(self) -> None:
        problem = ineq(T.GREATER_THAN, node(T.TAN, var("x")), c("0"))
        solution = solution_of(problem)
        assert solution.type is T.OPEN_OPEN_INTERVAL

    def test_true_for_all_reals(self) -> None:
        problem = ineq(T.LESS_THAN, node(T.SIN, var("x")), c("2"))
        solution = solution_of(problem)
        assert solution.type is T.OPEN_OPEN_INTERVAL
        assert solution.children[0].type is T.NEGATIVE

    def test_no_solution(self) -> None:
        problem = ineq(T.GREATER_THAN, node(T.SIN, var("x")), c("2"))
        assert solution_of(problem).type is T.EMPTY
        assert step_keys(problem) == ["rel_el_of_zero"]

    def test_a_surd_bound_is_a_number_not_an_irrational_inequality(self) -> None:
        # cos x ≤ √2/2 lost its period: √2 sent it to the root inequality
        solution = solution_of(parse_protocol("{<=({cos({x})},{frac({root2({2})},{2})})}"))
        k = sympy.Symbol("k")
        assert solution.type is T.CLOSED_CLOSED_INTERVAL
        ends = [sympy.expand(to_sympy(end)) for end in solution.children]
        assert ends == [sympy.pi / 4 + 2 * sympy.pi * k, 7 * sympy.pi / 4 + 2 * sympy.pi * k]

    def test_an_arc_through_zero_is_one_interval(self) -> None:
        solution = solution_of(parse_protocol("{<({sin({x})},{frac({1},{2})})}"))
        k = sympy.Symbol("k")
        assert solution.type is T.OPEN_OPEN_INTERVAL
        ends = [sympy.expand(to_sympy(end)) for end in solution.children]
        assert ends == [-7 * sympy.pi / 6 + 2 * sympy.pi * k, sympy.pi / 6 + 2 * sympy.pi * k]

    def test_a_lone_point_is_a_series_and_a_point_at_zero_joins_its_arc(self) -> None:
        k = sympy.Symbol("k")
        top = solution_of(parse_protocol("{>=({sin({x})},{1})}"))
        assert top.type is T.EQUALS
        assert sympy.expand(to_sympy(top.children[1])) == sympy.pi / 2 + 2 * sympy.pi * k
        below = solution_of(parse_protocol("{<=({sin({x})},{0})}"))
        assert below.type is T.CLOSED_CLOSED_INTERVAL
        ends = [sympy.expand(to_sympy(end)) for end in below.children]
        assert ends == [-sympy.pi + 2 * sympy.pi * k, 2 * sympy.pi * k]


def test_quadratic_inequality_follows_cases_and_intersections() -> None:
    # x^2 - 5x + 6 < 0 is factored, split into two sign cases,
    # each inequality solved, the systems intersected and the results united.
    problem = parse_protocol("{<({x^2-5x+6},{0})}")
    assert step_keys(problem)[4:] == ["ineq_product_p_two"] + ["ineq_linear"] * 4 + [
        "intersection",
        "intersection",
        "union",
    ]


def test_square_above_a_number_moves_takes_the_root_then_splits_into_cases() -> None:
    # x^2 - 4 > 0 is |x| > 2 after two nested rows.
    problem = parse_protocol("{>({x^2-4},{0})}")
    assert step_keys(problem) == [
        "rel_move_right_const_ineq",
        "ineq_pow_sqrt_root",
        "ineq_separate_abs",
        "intersection",
        "ineq_linear",
        "intersection",
        "union",
    ]
    assert solution_of(problem).type is T.UNION


def test_unknown_on_both_sides_flips_only_for_a_negative_net_coefficient() -> None:
    for source, relation, bound in [
        ("{>({2x+1},{5x-2})}", T.LESS_THAN, "1"),
        ("{<({3x-2},{x+4})}", T.LESS_THAN, "3"),
        ("{<({x+5},{3x+1})}", T.GREATER_THAN, "2"),
    ]:
        solution = solution_of(parse_protocol(source))
        assert solution.type is relation and solution.children[1].value == bound


def test_cubic_inequality_is_solved_with_roots_and_a_sign_chart() -> None:
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    vertical = solve(parse_protocol("{>=({x^3-x},{0})}")).result.vertical()
    assert vertical is not None and vertical.solution is not None
    assert vertical.solution.type.name == "UNION"
    keys = [s.description.type for st in vertical.steps for s in st.substeps]
    assert keys == ["factorise_call", "ineq_poly_roots", "ineq_poly_sign_chart"]


def test_unknown_over_a_number_is_multiplied_out_in_two_rows() -> None:
    vertical = solve(parse_protocol("{>({frac({x},{2})},{3})}")).result.vertical()
    assert vertical is not None and vertical.solution is not None
    assert [len(g.substeps) for g in vertical.steps] == [1, 2]
    assert vertical.solution.type is T.GREATER_THAN and vertical.solution.children[1].value == "6"


def test_square_below_a_number_takes_the_root_and_splits_into_cases() -> None:
    # x^2-9<0 -> |x|<3 -> two cases -> (-3, 3).
    problem = parse_protocol("{<({x^2-9},{0})}")
    assert step_keys(problem)[:2] == ["rel_move_right_const_ineq", "ineq_pow_sqrt_root"]
    solution = solution_of(problem)
    assert solution.type is T.OPEN_OPEN_INTERVAL
    assert solution.children[1].value == "3"


def test_cubic_inequality_with_irrational_roots_uses_a_sign_chart() -> None:
    # x^3 + 5x^2 + 3x - 2 >= 0: sympy gives up (ConditionSet), the roots are only numeric
    solution = solution_of(parse_protocol("{>=({x^3+5x^2+3x},{2})}"))
    assert solution.type is T.UNION
    assert solution.children[0].type is T.CLOSED_CLOSED_INTERVAL


def test_cancelling_fractions_and_single_points_in_inequalities() -> None:
    assert solution_of(parse_protocol("{<({frac({x},{3x})},{2})}")).type is T.UNION
    assert vertical_of_empty("{>({frac({x},{3x})},{2})}")
    point = solution_of(parse_protocol("{<=({x^2},{0})}"))
    assert point.type is T.SET and point.children[0].value == "0"


def vertical_of_empty(source: str) -> bool:
    vertical = solve(parse_protocol(source)).result.vertical()
    return vertical is not None and (vertical.solution is None or vertical.solution.type is T.EMPTY)
