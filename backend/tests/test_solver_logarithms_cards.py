"""Logarithm cards.

Two groups of behaviour:

* ``log_b(a ± c)`` and ``log_b f(x) = c`` follow the row cards:
  the sum/difference rule, ``pow_to_same_base``, ``using_sim``; and for an equation the
  domain, the conversion to ``f(x) = b^c``, the ordinary linear/quadratic rows and the check.
* every ``EQUALS`` row is a consequence the student reads, so each root of the answer has
  to satisfy it — checked by substituting the root with sympy.
"""

from __future__ import annotations

from collections.abc import Iterator

import sympy

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult, CoreSolverVerticalSubstep
from mymath_backend.service import solve_request
from mymath_backend.solver.sympy_bridge import to_sympy

X = sympy.Symbol("x")


def _cards(proto: str) -> list[CoreSolverVerticalResult]:
    data = solve_request(parse_protocol(proto).to_contract(), render=False, locale="ru")
    return [
        CoreSolverVerticalResult.from_contract(entry["result"])
        for group in data["result"]["groups"]
        for entry in group["entries"]
        if entry.get("result")
    ]


def _card(proto: str) -> CoreSolverVerticalResult:
    cards = _cards(proto)
    assert cards and cards[0].solution is not None
    return cards[0]


def _rows(card: CoreSolverVerticalResult) -> Iterator[CoreSolverVerticalSubstep]:
    """Every row of the card, including the nested «Подробнее» screens."""
    for step in card.steps:
        for sub in step.substeps:
            yield sub
            if sub.subresult is not None:
                yield from _rows(sub.subresult)


def _keys(card: CoreSolverVerticalResult) -> list[str]:
    return [sub.description.type for sub in _rows(card)]


def _top_keys(card: CoreSolverVerticalResult) -> list[str]:
    return [sub.description.type for step in card.steps for sub in step.substeps]


def _condition(card: CoreSolverVerticalResult) -> CoreNode:
    """The domain condition the first row puts next to the equation."""
    first = card.steps[0].substeps[0].right
    assert first is not None and first.type is T.LIST
    return first.children[1]


def _roots(card: CoreSolverVerticalResult) -> list[sympy.Expr]:
    solution = card.solution
    assert solution is not None
    items = solution.children if solution.type is T.LIST else [solution]
    return [to_sympy(item.children[1]) for item in items if item.type is T.EQUALS]


def _alternatives(node: CoreNode) -> list[CoreNode]:
    """The equations a row's side offers; a list of branches means «or»."""
    if node.type is T.EQUALS:
        return [node]
    if node.type in (T.LIST, T.VERTICAL_LIST):
        return [item for child in node.children for item in _alternatives(child)]
    return []


def _holds(node: CoreNode, root: sympy.Expr) -> bool | None:
    """Does the root satisfy one of the side's equations? ``None`` — not translatable."""
    alternatives = _alternatives(node)
    if not alternatives:
        return None
    checked = False
    for equation in alternatives:
        try:
            residual = to_sympy(equation.children[0]) - to_sympy(equation.children[1])
        except Exception:  # x = ±4 is a display form, not an equation
            continue
        checked = True
        if sympy.simplify(residual.subs(X, root)) == 0:
            return True
    return False if checked else None


class TestLogArithmetic:
    """``l02``–``l07``: exact logarithms, sums of logarithms, ``a^log_a b`` and ``ln e^t``."""

    def test_a_fraction_that_is_a_power_of_the_base_is_evaluated(self) -> None:
        # log₃(1/9) = log₃(3⁻²) = -2, the argument written as a power on its own screen
        card = _card("{log({frac({1},{9})},{3})}")
        assert _top_keys(card) == ["pow_to_same_base", "using_sim"]
        assert to_sympy(card.solution) == -2

    def test_a_fractional_exponent_is_evaluated(self) -> None:
        # log₉ 3 = log₉ 9^(1/2) = 1/2
        assert to_sympy(_card("{log({3},{9})}").solution) == sympy.Rational(1, 2)

    def test_difference_of_logs_is_joined_then_evaluated(self) -> None:
        card = _card("{log({12},{2})-log({3},{2})}")
        assert _top_keys(card) == ["log_sum_resolve_minus", "pow_to_same_base", "using_sim"]
        assert to_sympy(card.solution) == 2

    def test_sum_of_logs_is_joined_then_evaluated(self) -> None:
        card = _card("{log({4},{6})+log({9},{6})}")
        assert _top_keys(card) == ["log_sum_resolve_plus", "pow_to_same_base", "using_sim"]
        assert to_sympy(card.solution) == 2

    def test_three_logs_with_one_base_are_joined(self) -> None:
        card = _card("{log({4},{2})+log({8},{2})+log({16},{2})}")
        assert _top_keys(card)[0] == "log_sum_resolve_plus"
        assert to_sympy(card.solution) == 9

    def test_a_sum_that_is_not_an_exact_power_keeps_the_logarithm(self) -> None:
        card = _card("{log({3},{2})+log({5},{2})}")
        assert _top_keys(card) == ["log_sum_resolve_plus"]
        assert to_sympy(card.solution) == sympy.log(15, 2)

    def test_a_power_of_the_base_of_its_own_logarithm_is_the_argument(self) -> None:
        card = _card("{2^(log({7},{2}))}")
        assert _top_keys(card) == ["using_sim"]
        assert to_sympy(card.solution) == 7

    def test_natural_log_of_a_power_of_e_uses_the_power_rule(self) -> None:
        card = _card("{ln({\\e^5})}")
        assert _top_keys(card) == ["using_trans", "log_same_base_arg_ln", "mul_with_one"]
        assert to_sympy(card.solution) == 5

    def test_decimal_logarithms_are_joined(self) -> None:
        # the joined argument is the base itself: log₁₀10 = 1, no «write as a power» row
        card = _card("{log10({2})+log10({5})}")
        assert _top_keys(card) == ["log_sum_resolve_plus", "log_same_base_arg"]
        assert to_sympy(card.solution) == 1

    def test_natural_logarithms_are_joined(self) -> None:
        card = _card("{ln({\\e^2})+ln({\\e^3})}")
        assert _top_keys(card)[0] == "log_sum_resolve_plus"
        assert to_sympy(card.solution) == 5


class TestLogEquation:
    """``l09``, ``l12``, ``l15``: the domain comes from ``f(x)`` and the base, then ``f = b^c``."""

    def test_linear_argument_domain_and_conversion(self) -> None:
        card = _card("{=({log({2x-1},{3})},{2})}")
        assert _top_keys(card) == [
            "rel_restrictions_range",
            "eq_log_formula_convert",
            "pow",
            "rel_move_right_const_eq",
            "add",
            "eq_linear_div",
            "rel_restrictions_check",
        ]
        assert to_sympy(_condition(card)) == sympy.Gt(X, sympy.Rational(1, 2))
        assert "rel_restrictions_log_arg" in _keys(card)
        # the app shows headers as plain text, so they carry no formula (was «log(2·x - 1, 3)»)
        detail = card.steps[0].substeps[0].subresult
        assert detail is not None
        assert [h.type for step in detail.steps for h in step.step_headers] == [
            "rel_restrictions_find",
            "ineq_solve_short",
            "exclude_values",
        ]
        assert to_sympy(card.solution) == sympy.Eq(X, 5)

    def test_quadratic_argument_domain_and_conversion(self) -> None:
        card = _card("{=({log({x^2-4x},{5})},{1})}")
        assert _top_keys(card)[:3] == [
            "rel_restrictions_range",
            "eq_log_formula_convert",
            "pow_with_one",
        ]
        assert _top_keys(card)[-1] == "rel_restrictions_check"
        condition = _condition(card)
        assert condition.type is T.ELEMENT_OF
        assert to_sympy(condition.children[1]) == sympy.Union(
            sympy.Interval.open(-sympy.oo, 0), sympy.Interval.open(4, sympy.oo)
        )
        assert sorted(_roots(card)) == [-1, 5]

    def test_variable_base_domain_keeps_only_the_positive_base(self) -> None:
        # log_x 16 = 2 -> 16 = x², and x = -4 is not a base of a logarithm
        card = _card("{=({log({16},{x})},{2})}")
        assert _top_keys(card)[:2] == ["rel_restrictions_range", "eq_log_formula_convert"]
        assert _top_keys(card)[-1] == "rel_restrictions_check"
        assert "rel_restrictions_log_base" in _keys(card)
        condition = _condition(card)
        assert condition.type is T.ELEMENT_OF
        assert to_sympy(condition.children[1]) == sympy.Union(
            sympy.Interval.open(0, 1), sympy.Interval.open(1, sympy.oo)
        )
        assert _roots(card) == [4]

    def test_every_equation_row_is_satisfied_by_every_root(self) -> None:
        """Each row is a consequence: no root may fall out of the chain.

        A row whose side is a list offers alternatives (``x + 1 = 0, x - 5 = 0``): a root
        needs one of them. The rows before a branch (several substeps) are checked on their
        left side only, because each substep then solves one branch.
        """
        for proto in (
            "{=({log({2x-1},{3})},{2})}",
            "{=({log({x^2-4x},{5})},{1})}",
            "{=({log({16},{x})},{2})}",
            "{=({log({x},{2})},{3})}",
            "{=({ln({x})},{2})}",
            "{=({log({x+1},{2})+log({x-1},{2})},{3})}",
            "{=({log10({x})+log10({x-9})},{1})}",
        ):
            for card in _cards(proto):
                roots = _roots(card)
                assert roots, proto
                for step in card.steps:
                    substeps = step.substeps
                    sides = [sub.left for sub in substeps]
                    if len(substeps) == 1:
                        sides += [substeps[0].right]
                    for side in sides:
                        if side is None:
                            continue
                        for root in roots:
                            assert _holds(side, root) is not False, (
                                proto,
                                side.to_contract(),
                                root,
                            )


class TestLogSumAndSubstitution:
    """``l10``–``l13``: a sum of logarithms and the substitution ``t = log_a x``."""

    def test_sum_of_logs_is_joined_then_converted(self) -> None:
        card = _card("{=({log({x+1},{2})+log({x-1},{2})},{3})}")
        assert _top_keys(card) == [
            "rel_restrictions_range",
            "using_sim",
            "factorise_inv_sim",
            "eq_log_formula_convert",
            "pow",
            "rel_move_right_const_eq",
            "add",
            "quad_sqrt_sides",
            "quad_separate_signs",
            "rel_restrictions_check",
        ]
        assert to_sympy(_condition(card)) == sympy.Gt(X, 1)
        assert to_sympy(card.solution) == sympy.Eq(X, 3)

    def test_decimal_sum_of_logs_is_joined_then_converted(self) -> None:
        card = _card("{=({log10({x})+log10({x-9})},{1})}")
        assert _top_keys(card)[:4] == [
            "rel_restrictions_range",
            "using_sim",
            "mul_bracket",
            "eq_log_formula_convert",
        ]
        assert _top_keys(card)[-1] == "rel_restrictions_check"
        assert to_sympy(_condition(card)) == sympy.Gt(X, 9)
        assert to_sympy(card.solution) == sympy.Eq(X, 10)

    def test_quadratic_in_a_logarithm_uses_the_substitution(self) -> None:
        card = _card("{=({log({x},{2})^2-3*log({x},{2})+2},{0})}")
        assert _top_keys(card)[:2] == ["rel_restrictions_range", "eq_solve_sub"]
        assert "sub_msg_ret" in _keys(card)
        assert _top_keys(card)[-1] == "rel_restrictions_check"
        assert to_sympy(_condition(card)) == sympy.Gt(X, 0)
        assert sorted(_roots(card)) == [2, 4]

    def test_variable_base_swaps_the_sides(self) -> None:
        # log_x 16 = 2 -> 16 = x² -> x² = 16 (the ``rel_swap_eq`` row)
        card = _card("{=({log({16},{x})},{2})}")
        assert _top_keys(card)[:3] == [
            "rel_restrictions_range",
            "eq_log_formula_convert",
            "rel_swap_eq",
        ]
        assert _roots(card) == [4]


class TestLogInequalities:
    """``l17``, ``l18``: the domain, the log formula, the linear rows, the intersection."""

    def test_base_below_one_flips_the_direction(self) -> None:
        card = _card("{>=({log({x-1},{frac({1},{2})})},{-1})}")
        assert _top_keys(card) == [
            "rel_restrictions_range",
            "ineq_log_formula_lt_xab_pow",
            "pow_flip_one",
            "rel_move_right_const_ineq",
            "add",
            "rel_restrictions_intersect",
        ]
        assert to_sympy(card.solution) == sympy.Interval(1, 3, left_open=True)

    def test_decimal_log_inequality(self) -> None:
        card = _card("{<({log10({x-2})},{1})}")
        assert _top_keys(card) == [
            "rel_restrictions_range",
            "ineq_log_formula_gt_xab_pow",
            "pow_with_one",
            "rel_move_right_const_ineq",
            "add",
            "rel_restrictions_intersect",
        ]
        assert to_sympy(card.solution) == sympy.Interval.open(2, 12)

    def test_the_move_row_uses_the_inequality_key_and_header(self) -> None:
        # the equation text («…в правую часть равенства») must not appear for an inequality
        for proto in (
            "{>=({log({x-1},{frac({1},{2})})},{-1})}",
            "{<({log10({x-2})},{1})}",
        ):
            card = _card(proto)
            found = False
            for step in card.steps:
                for sub in step.substeps:
                    if sub.description.type == "rel_move_right_const_ineq":
                        found = True
                        assert [h.type for h in step.step_headers] == ["rel_move_right_const_ineq"]
            assert found, proto
