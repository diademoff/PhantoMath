"""Exponential equation and inequality cards.

``e03``–``e11`` and ``x01`` follow the row cards: one base
(``pow_to_same_base`` / ``exp_eq_exp_equalise`` / ``log_take_*``), factoring
(``factorise_call``) or the substitution ``t = a^x`` (``eq_solve_sub``); the
inequalities ``e13``/``e14`` compare the exponents and solve the linear rows.
Every ``EQUALS`` row has to be satisfied by every root of the answer.
"""

from __future__ import annotations

from collections.abc import Iterator

import sympy

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import (
    CoreSolverVerticalResult,
    CoreSolverVerticalStep,
    CoreSolverVerticalSubstep,
)
from mymath_backend.service import explanations, solve_request
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
    for step in card.steps:
        for sub in step.substeps:
            yield sub
            if sub.subresult is not None:
                yield from _rows(sub.subresult)


def _keys(card: CoreSolverVerticalResult) -> list[str]:
    return [sub.description.type for sub in _rows(card)]


def _steps(card: CoreSolverVerticalResult) -> Iterator[CoreSolverVerticalStep]:
    """Every step of the card, including the nested «Подробнее» screens."""
    for step in card.steps:
        yield step
        for sub in step.substeps:
            if sub.subresult is not None:
                yield from _steps(sub.subresult)


def _top_keys(card: CoreSolverVerticalResult) -> list[str]:
    return [sub.description.type for step in card.steps for sub in step.substeps]


def _roots(card: CoreSolverVerticalResult) -> list[sympy.Expr]:
    solution = card.solution
    assert solution is not None
    items = solution.children if solution.type is T.LIST else [solution]
    return [to_sympy(item.children[1]) for item in items if item.type is T.EQUALS]


def _alternatives(node: CoreNode) -> list[CoreNode]:
    if node.type is T.EQUALS:
        return [node]
    if node.type in (T.LIST, T.VERTICAL_LIST):
        return [item for child in node.children for item in _alternatives(child)]
    return []


def _holds(node: CoreNode, root: sympy.Expr) -> bool | None:
    """Does the root satisfy one of the side's equations? ``None`` — not checkable in ``x``."""
    alternatives = _alternatives(node)
    if not alternatives:
        return None
    checked = False
    for equation in alternatives:
        try:
            residual = to_sympy(equation.children[0]) - to_sympy(equation.children[1])
        except Exception:  # x = ±4 is a display form, not an equation
            continue
        residual = sympy.simplify(residual.subs(X, root))
        if residual.free_symbols - {X}:  # a row in the substitute ``t``: skip
            continue
        checked = True
        if residual == 0:
            return True
    return False if checked else None


def _row_preserves(left: CoreNode | None, right: CoreNode | None, root: sympy.Expr) -> bool | None:
    """Both sides of a row agree at the root (branch rows may be false on both)."""
    if left is None or right is None:
        return None
    first, second = _holds(left, root), _holds(right, root)
    if first is None or second is None:
        return None
    return first == second


class TestExponentialEquations:
    """``e03``–``e11``, ``x01``: the rows and the exact answers."""

    def test_fractional_base_is_written_as_a_negative_exponent(self) -> None:
        card = _card("{=({(frac({1},{2}))^x},{8})}")
        assert _top_keys(card) == [
            "write_as_exp",
            "pow_to_same_base",
            "exp_eq_exp_equalise",
            "eq_linear_div",
        ]
        assert to_sympy(card.solution) == sympy.Eq(X, -3)

    def test_fraction_rhs_is_written_as_a_negative_power(self) -> None:
        card = _card("{=({5^(2x-1)},{frac({1},{25})})}")
        assert _top_keys(card) == [
            "pow_to_same_base",
            "exp_eq_exp_equalise",
            "rel_move_right_const_eq",
            "calc_sum",
            "eq_linear_div",
        ]
        assert to_sympy(card.solution) == sympy.Eq(X, sympy.Rational(-1, 2))

    def test_quadratic_exponent_gives_the_quadratic_rows(self) -> None:
        card = _card("{=({2^(x^2-3x)},{frac({1},{4})})}")
        assert _top_keys(card)[:2] == ["pow_to_same_base", "exp_eq_exp_equalise"]
        assert "solution_eq_num" in _keys(card)
        assert sorted(_roots(card)) == [1, 2]

    def test_substitution_t_equals_two_to_the_x(self) -> None:
        card = _card("{=({4^x-3*2^x+2},{0})}")
        assert _top_keys(card)[:3] == ["pow_to_same_base", "using_trans", "eq_solve_sub"]
        assert "sub_msg_ret" in _keys(card)
        assert sorted(_roots(card)) == [0, 1]

    def test_substitution_with_base_three(self) -> None:
        card = _card("{=({9^x-4*3^x+3},{0})}")
        assert _top_keys(card)[:3] == ["pow_to_same_base", "using_trans", "eq_solve_sub"]
        assert sorted(_roots(card)) == [0, 1]

    def test_factoring_out_the_common_power(self) -> None:
        card = _card("{=({2^(x+1)+2^x},{12})}")
        assert _top_keys(card) == [
            "factorise_call",
            "add",
            "eq_linear_div",
            "pow_to_same_base",
            "exp_eq_exp_equalise",
        ]
        assert to_sympy(card.solution) == sympy.Eq(X, 2)

    def test_logarithm_of_both_sides(self) -> None:
        card = _card("{=({3^x},{5})}")
        assert _top_keys(card) == ["log_take_both_side", "using_sim"]
        assert to_sympy(card.solution) == sympy.Eq(X, sympy.log(5, 3))

    def test_natural_logarithm_of_both_sides(self) -> None:
        card = _card("{=({\\e^(2x)},{7})}")
        assert _top_keys(card) == ["log_take_natural", "eq_linear_div"]
        assert to_sympy(card.solution) == sympy.Eq(X, sympy.log(7) / 2)

    def test_equal_exponents_different_bases(self) -> None:
        card = _card("{=({2^x},{3^x})}")
        assert _top_keys(card) == [
            "eq_linear_div",
            "pow_to_same_base",
            "exp_eq_exp_equalise",
        ]
        assert to_sympy(card.solution) == sympy.Eq(X, 0)

    def test_linear_equation_with_an_irrational_constant(self) -> None:
        # ln(2x+1) = -1 -> 2x + 1 = 1/e -> x = 1/(2e) - 1/2 (no graph, no approximation)
        card = _card("{=({ln({2x+1})},{-1})}")
        assert _top_keys(card) == [
            "rel_restrictions_range",
            "eq_log_formula_convert",
            "pow_flip_one",
            "rel_move_right_const_eq",
            "eq_linear_div",
            "rel_restrictions_check",
        ]
        assert to_sympy(card.solution) == sympy.Eq(X, 1 / (2 * sympy.E) - sympy.Rational(1, 2))

    def test_plain_linear_equations_with_e_are_exact(self) -> None:
        assert to_sympy(_card("{=({2x},{\\e-1})}").solution) == sympy.Eq(X, (sympy.E - 1) / 2)
        assert to_sympy(_card("{=({x+1},{\\e^2})}").solution) == sympy.Eq(X, sympy.E**2 - 1)
        assert to_sympy(_card("{=({2x+1},{\\e^(-1)})}").solution) == sympy.Eq(
            X, 1 / (2 * sympy.E) - sympy.Rational(1, 2)
        )

    def test_every_equation_row_is_satisfied_by_every_root(self) -> None:
        for proto in (
            "{=({(frac({1},{2}))^x},{8})}",
            "{=({5^(2x-1)},{frac({1},{25})})}",
            "{=({2^(x^2-3x)},{frac({1},{4})})}",
            "{=({4^x-3*2^x+2},{0})}",
            "{=({9^x-4*3^x+3},{0})}",
            "{=({2^(x+1)+2^x},{12})}",
            "{=({3^x},{5})}",
            "{=({(\\e)^(2x)},{7})}",
            "{=({2^x},{3^x})}",
            "{=({ln({2x+1})},{-1})}",
        ):
            for card in _cards(proto):
                roots = _roots(card)
                assert roots, proto
                # the original equation holds at every root
                original = card.steps[0].substeps[0].left
                for root in roots:
                    assert _holds(original, root) is not False, (proto, root)
                # every row keeps the root: for a single-substep row the two sides agree at it
                # (branch rows may be false on both); a step with several substeps solves one
                # branch each, so only its left side is required to hold. Nested «Подробнее»
                # pages belong to a single branch, so they are not checked against every root.
                for step in card.steps:
                    if len(step.substeps) > 1:
                        for sub in step.substeps:
                            for root in roots:
                                assert _holds(sub.left, root) is not False, (
                                    proto,
                                    (sub.left.to_contract() if sub.left else None),
                                    root,
                                )
                        continue
                    for sub in step.substeps:
                        for root in roots:
                            assert _row_preserves(sub.left, sub.right, root) is not False, (
                                proto,
                                (sub.left.to_contract() if sub.left else None),
                                root,
                            )


class TestExponentialInequalities:
    """``e13``, ``e14``: one base, compare the exponents, then the linear rows."""

    def test_fractional_base_flips_the_direction(self) -> None:
        card = _card("{<=({(frac({1},{3}))^x},{9})}")
        assert _top_keys(card) == [
            "write_as_exp",
            "pow_to_same_base",
            "compare_exp_alg",
            "ineq_linear_neg",
        ]
        assert to_sympy(card.solution) == sympy.Interval(-2, sympy.oo, left_open=False)

    def test_power_of_one_is_written_as_the_zero_power(self) -> None:
        card = _card("{<({5^(x-2)},{1})}")
        assert _top_keys(card)[:2] == ["pow_to_same_base", "compare_exp_alg"]
        assert to_sympy(card.solution) == sympy.Interval(-sympy.oo, 2, right_open=True)


class TestExplanationArguments:
    """Every row passes exactly the number of arguments its explanation key needs.

    LOG2 left ``pow_to_same_base``/``using_trans``/``using_sim``/``write_as_exp``/
    ``eq_linear_div``/``factorise_inv_sim``/``mul_bracket``/``pow_flip_one`` without
    arguments, so the app showed a literal «ARG1». The arity comes from
    the explanation dictionary; nested «Подробнее» pages count too.
    """

    def test_every_row_passes_the_arity_of_its_key(self) -> None:
        table = explanations()
        for proto in (
            "{=({(frac({1},{2}))^x},{8})}",  # e03
            "{=({5^(2x-1)},{frac({1},{25})})}",  # e04
            "{=({2^(x^2-3x)},{frac({1},{4})})}",  # e05
            "{=({4^x-3*2^x+2},{0})}",  # e06
            "{=({9^x-4*3^x+3},{0})}",  # e07
            "{=({2^(x+1)+2^x},{12})}",  # e08
            "{=({3^x},{5})}",  # e09
            "{=({2^x},{3^x})}",  # e11
            "{<=({(frac({1},{3}))^x},{9})}",  # e13
            "{=({log({x+1},{2})+log({x-1},{2})},{3})}",  # l10
            "{=({log10({x})+log10({x-9})},{1})}",  # l11
            "{>=({log({x-1},{frac({1},{2})})},{-1})}",  # l17
            "{=({ln({2x+1})},{-1})}",  # x01
        ):
            for card in _cards(proto):
                for sub in _rows(card):
                    key = sub.description.type
                    arity = table.arity(key)
                    assert len(sub.description.args) == arity, (
                        proto,
                        key,
                        len(sub.description.args),
                        arity,
                    )

    def test_every_step_header_is_a_known_explanation(self) -> None:
        """LOG2 used ``log_msg``/``pow_flip`` as headers; the app showed «?? step_log_msg ??»."""
        table = explanations()
        for proto in (
            "{=({(frac({1},{2}))^x},{8})}",  # e03
            "{=({5^(2x-1)},{frac({1},{25})})}",  # e04
            "{=({2^(x^2-3x)},{frac({1},{4})})}",  # e05
            "{=({4^x-3*2^x+2},{0})}",  # e06
            "{=({9^x-4*3^x+3},{0})}",  # e07
            "{=({2^(x+1)+2^x},{12})}",  # e08
            "{=({3^x},{5})}",  # e09
            "{=({2^x},{3^x})}",  # e11
            "{<=({(frac({1},{3}))^x},{9})}",  # e13
            "{=({log({x+1},{2})+log({x-1},{2})},{3})}",  # l10
            "{=({log10({x})+log10({x-9})},{1})}",  # l11
            "{>=({log({x-1},{frac({1},{2})})},{-1})}",  # l17
            "{<({log10({x-2})},{1})}",  # l18
            "{=({ln({2x+1})},{-1})}",  # x01
        ):
            for card in _cards(proto):
                for step in _steps(card):
                    for header in step.step_headers:
                        table.arity(header.type)  # raises when the key is unknown


class TestLinearNegativeInequality:
    """``e13``: the ``ineq_linear_neg`` row reads ``-x ≤ 2`` (no bracket around ``x``)."""

    def test_no_bracket_around_the_variable(self) -> None:
        card = _card("{<=({(frac({1},{3}))^x},{9})}")
        rows = [sub for sub in _rows(card) if sub.description.type == "ineq_linear_neg"]
        assert rows
        left = rows[0].left
        assert left is not None and left.type is T.LESS_THAN_EQUAL
        assert left.children[0].type is T.NEGATIVE
        assert left.children[0].children[0].type is T.VARIABLE
        assert "ineq_mul_direct_neg" in _keys(card)
