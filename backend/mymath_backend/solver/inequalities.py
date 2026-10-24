"""Линейные и квадратные неравенства.

Модуль зарегистрирован на знаки отношения ``<``, ``≤``, ``>``, ``≥``, ``≠``.
Неравенство приводится к виду ``p(x) ⋚ 0`` (через ``lhs - rhs``), затем:

* степень 1 — неизвестное выражается: при ``a > 0`` знак сохраняется, при
  ``a < 0`` меняется на противоположный; ответ — ``x < 2``;
* степень 2 — метод интервалов: находятся корни, знак старшего коэффициента
  задаёт промежутки; ответ — промежуток или их объединение;
* степень 0 — утверждение верно для всех или ни для одного значения;
* неизвестное в знаменателе — множество решений даёт ``sympy.solveset``,
  ответ — промежутки/объединение (ключи ``ineq_quotient_*``);
* корень, логарифм или степень с переменным показателем — тоже ``solveset``
  (ключи ``ineq_irr_solve``, ``ineq_solve_short``, ``log_ineq_gt_one``).

Ключи: ``ineq_linear_div``/``ineq_linear_div_neg``, ``move``,
``ineq_quad_to_eq_quad``, ``ineq_quad_lead_*``. Ответ-промежуток — узлы
``OPEN_*_INTERVAL``/``CLOSED_*_INTERVAL`` и ``UNION``.
"""

from __future__ import annotations

import itertools
from fractions import Fraction
from math import isqrt

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from . import quadratic_cards
from .arithmetic import as_fraction, format_number, number_of
from .base import SolveContext, SolveError, SolveResult, Step, UndefinedError, solver_for
from .domain import add_restriction_steps
from .equations import _poly_expr, _simple_side, poly_of
from .sympy_bridge import from_sympy, to_sympy
from .trig_equations import _series as _trig_series
from .trig_equations import looks_trigonometric

_HEADER = CoreRichText(type="ineq_solve_short")

_PARAMETER = "k"
"""Имя параметра периода в общем решении неравенства: ``π/6 + 2πk < x``."""

_RELATIONS = (
    T.LESS_THAN,
    T.LESS_THAN_EQUAL,
    T.GREATER_THAN,
    T.GREATER_THAN_EQUAL,
    T.NOT_EQUALS,
)

# Смена знака отношения при делении на отрицательное число.
_FLIP: dict[T, T] = {
    T.LESS_THAN: T.GREATER_THAN,
    T.LESS_THAN_EQUAL: T.GREATER_THAN_EQUAL,
    T.GREATER_THAN: T.LESS_THAN,
    T.GREATER_THAN_EQUAL: T.LESS_THAN_EQUAL,
    T.NOT_EQUALS: T.NOT_EQUALS,
}


def _const(value: Fraction) -> CoreNode:
    return CoreNode.constant(format_number(value))


def _x_term(coefficient: Fraction, var: str) -> CoreNode:
    x = CoreNode.variable(var)
    if coefficient == 1:
        return x
    if coefficient == -1:
        return CoreNode(type=T.NEGATIVE, children=[x])
    return CoreNode(type=T.MULTIPLY_IMPLICIT, children=[_const(coefficient), x])


def _negated(node: CoreNode) -> CoreNode:
    """``−node`` as a node; a leading minus is dropped (``−(−2) = 2``)."""
    if node.type is T.NEGATIVE and len(node.children) == 1:
        return node.children[0]
    return CoreNode(type=T.NEGATIVE, children=[node])


def _zero_rhs_move(
    node: CoreNode, collapsed: CoreNode, constant: Fraction
) -> tuple[SolveResult, CoreNode]:
    """Rows for ``collapsed + constant ⋚ 0`` with the constant carried to the right.

    This is the flat shape the app shows when the right side is zero:
    balance the constant, drop the opposite, then drop the leading zero. Both
    ``x - 3 < 0`` and ``x² - 9 < 0`` (and the even-power cards) use it.
    Returns the detail screen and the resulting relation ``collapsed ⋚ −constant``.
    """
    left, zero = node.children[0], _const(Fraction(0))
    amount = _const(abs(constant))
    sign = T.SUBTRACT if constant > 0 else T.ADD
    balanced = CoreNode.node(
        node.type, CoreNode.node(sign, left, amount), CoreNode.node(sign, zero, amount)
    )
    after = CoreNode.node(node.type, collapsed, CoreNode.node(sign, zero, amount))
    final_rhs = _const(-constant) if constant < 0 else _negated(_const(constant))
    final = CoreNode.node(node.type, collapsed, final_rhs)
    detail = SolveResult()
    detail.add_group("rel_move_right_const_msg", Step(node, balanced, "rel_swap_right_const"))
    detail.add_group(
        ["remove_opposites", CoreRichText(type="remove_zero", args=[zero])],
        Step(balanced, after, "sub_with_self_remove_num"),
        Step(after, final, "add_with_zero", [zero]),
    )
    detail.set_solution(final)
    return detail, final


def _coefficient(node: CoreNode) -> Fraction | None:
    """Numeric value of ``c`` or ``−c``, else ``None``."""
    try:
        if node.type is T.NEGATIVE and len(node.children) == 1:
            return -as_fraction(node.children[0])
        return as_fraction(node)
    except SolveError:
        return None


def _constant_times_linear(node: CoreNode, var: str) -> tuple[Fraction, CoreNode] | None:
    """``c · X`` for a nonzero constant ``c`` and linear ``X`` (a bracket is unwrapped)."""
    if node.type not in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) or len(node.children) != 2:
        return None
    first, second = node.children
    coefficient = _coefficient(first)
    inner = second
    if coefficient is None:
        coefficient = _coefficient(second)
        inner = first
    if coefficient is None or coefficient == 0:
        return None
    if inner.type is T.BRACKET and len(inner.children) == 1:
        inner = inner.children[0]
    if _simple_side(inner, var) is None:
        return None
    return coefficient, inner


def _compact_linear_rows(condition: CoreNode, var: str) -> SolveResult | None:
    """Compact rows the app uses inside rational/irrational cards.

    One ``rel_move_right_const_ineq`` row for the constant, then one
    ``ineq_linear_div``/``ineq_linear_div_neg`` row when the coefficient is not 1.
    """
    left_side, right_side = (
        _simple_side(condition.children[0], var),
        _simple_side(condition.children[1], var),
    )
    if left_side is None or right_side is None:
        return None
    (a1, b1), (a2, b2) = left_side, right_side
    if a1 == 0 or a2 != 0:
        return None
    result = SolveResult()
    current = condition
    if b1 != 0:
        moved = CoreNode.node(condition.type, _x_term(a1, var), _const(b2 - b1))
        result.add_group(
            "rel_move_right_const_msg", Step(current, moved, "rel_move_right_const_ineq")
        )
        current = moved
    if a1 != 1:
        final = _condition_solution(current, var)
        key = "ineq_linear_div_neg" if a1 < 0 else "ineq_linear_div"
        result.add_group("divide_both_sides", Step(current, final, key, [_const(a1)]))
        current = final
    result.set_solution(current)
    return result


def _condition_rows(condition: CoreNode, var: str, *, compact: bool = False) -> SolveResult | None:
    """Rows the app shows for one linear condition ``a x + b ⋚ c``.

    ``None`` means the condition is outside the verified shape; the caller then
    falls back to a single ``ineq_linear`` row.
    """
    node = condition
    result = SolveResult()
    left = node.children[0]
    product = (
        _constant_times_linear(left, var)
        if node.children[1].type is T.CONSTANT and node.children[1].value in ("0", "-0")
        else None
    )
    if product is not None:
        coefficient, inner = product
        flipped = _FLIP[node.type] if coefficient < 0 else node.type
        divided = CoreNode.node(flipped, inner, _const(Fraction(0)))
        key = "ineq_linear_div_neg" if coefficient < 0 else "ineq_linear_div"
        result.add_group("divide_both_sides", Step(node, divided, key, [_const(coefficient)]))
        compact_rows = _compact_linear_rows(divided, var)
        if compact_rows is not None:
            result.extend(compact_rows)
            result.set_solution(compact_rows.solution or divided)
        return result
    if left.type is T.NEGATIVE and len(left.children) == 1 and len(node.children) == 2:
        inner, flipped = left.children[0], _FLIP[node.type]
        if inner.type is T.BRACKET and len(inner.children) == 1:
            target = inner.children[0]
            sides = _simple_side(target, var)
            if sides is None or sides[0] != 1:
                return None
            paired = CoreNode.node(flipped, target, _negated(node.children[1]))
            result.add_group("rel_linear_neg_msg", Step(node, paired, "ineq_linear_neg"))
            node = paired
        elif inner.type is T.VARIABLE and inner.value == var:
            minus_one = _negated(_const(Fraction(1)))
            scaled = CoreNode.node(
                flipped,
                CoreNode.node(T.MULTIPLY, minus_one, CoreNode.node(T.BRACKET, left)),
                CoreNode.node(T.MULTIPLY, minus_one, node.children[1]),
            )
            result.add_group(
                "multiply_both_sides",
                Step(node, scaled, "ineq_mul_direct_neg", [minus_one]),
            )
            unwrapped = CoreNode.node(flipped, inner, scaled.children[1])
            solved = CoreNode.node(flipped, inner, _negated(node.children[1]))
            result.add_group(
                "product_plural",
                Step(scaled, unwrapped, "mul_with_neg_one", [minus_one]),
                Step(unwrapped, solved, "mul_with_one", [_const(Fraction(1))]),
            )
            result.set_solution(solved)
            return result
        else:
            return None
    left_side, right_side = _simple_side(node.children[0], var), _simple_side(node.children[1], var)
    if left_side is None or right_side is None:
        return None
    (a1, b1), (a2, b2) = left_side, right_side
    if a1 == 0 or a2 != 0:
        return None
    if compact and a1 not in (1, -1):
        compact_rows = _compact_linear_rows(node, var)
        if compact_rows is not None:
            result.extend(compact_rows)
            result.set_solution(compact_rows.solution or node)
            return result
    collapsed = _x_term(a1, var)
    if b1 == 0:
        result.set_solution(node)
        return result
    if b2 == b1:
        # The constant cancels on both sides: The app deletes the equal terms at once.
        final = CoreNode.node(node.type, collapsed, _const(Fraction(0)))
        result.add_group("rel_del_term", Step(node, final, "ineq_del_opp"))
        result.set_solution(final)
        return result
    if b2 == 0:
        detail, final = _zero_rhs_move(node, collapsed, b1)
        result.extend(detail)
        result.set_solution(final)
        return result
    amount = _const(abs(b1))
    sign = T.SUBTRACT if b1 > 0 else T.ADD
    lhs, rhs = node.children
    balanced = CoreNode.node(
        node.type, CoreNode.node(sign, lhs, amount), CoreNode.node(sign, rhs, amount)
    )
    after = CoreNode.node(node.type, collapsed, CoreNode.node(sign, rhs, amount))
    move = SolveResult()
    move.add_group("rel_move_right_const_msg", Step(node, balanced, "rel_swap_right_const"))
    move.add_group("remove_opposites", Step(balanced, after, "sub_with_self_remove_num"))
    move.set_solution(after)
    result.add_group(
        "rel_move_right_const_ineq",
        Step(node, after, "rel_move_right_const_ineq", subresult=move),
    )
    final = CoreNode.node(node.type, collapsed, _const(b2 - b1))
    key = "calc_sum" if b1 < 0 and b2 < 0 else ("add" if b1 < 0 else "sub")
    result.add_group("calculate_short", Step(after, final, key))
    result.set_solution(final)
    return result


def _sum_detail(
    a1: Fraction, a2: Fraction, coefficient: Fraction, before: CoreNode, var: str
) -> SolveResult:
    """Detail screen of ``a1 x ± a2 x`` as the app writes it, expression by expression."""
    x = CoreNode.variable(var)
    one_x = CoreNode.node(T.MULTIPLY_IMPLICIT, _const(Fraction(1)), x)
    sign = T.SUBTRACT if a2 > 0 else T.ADD
    with_one = CoreNode.node(sign, _x_term(a1, var), one_x)
    bracket = CoreNode.node(T.SUBTRACT if coefficient >= 0 else T.ADD, _const(a1), _const(abs(a2)))
    grouped = CoreNode.node(T.MULTIPLY_IMPLICIT, CoreNode.node(T.BRACKET, bracket), x)
    explicit = _x_term(coefficient, var)
    detail = SolveResult()
    detail.add_group(
        CoreRichText(type="sum_one_coeff", args=[_const(Fraction(1))]),
        Step(
            before,
            with_one,
            "sum_suffix_add_neg_one" if a2 > 0 else "sum_suffix_add_one",
            [_negated(_const(Fraction(1))) if a2 > 0 else _const(Fraction(1))],
        ),
    )
    detail.add_group("sum_suffix", Step(with_one, grouped, "sum_suffix_sub_detail"))
    detail.add_group("calculate_short", Step(grouped, explicit, "sub" if a2 > 0 else "add"))
    solved = explicit
    if coefficient == 1:
        detail.add_group(
            CoreRichText(type="sum_suffix_del_one_short", args=[_const(Fraction(1))]),
            Step(explicit, x, "sum_suffix_del_one", [_const(Fraction(1))]),
        )
        solved = x
    detail.set_solution(solved)
    return detail


def _divide_rows(
    relation: T,
    current: CoreNode,
    var: str,
    coefficient: Fraction,
    total: Fraction,
    ctx: SolveContext,
) -> CoreNode:
    """Divide both sides by ``coefficient``; The app nests the screen when rows came before."""
    final_type = relation if coefficient > 0 else _FLIP[relation]
    divisor = (
        CoreNode(type=T.BRACKET, children=[_const(coefficient)])
        if coefficient < 0
        else _const(coefficient)
    )
    divided = CoreNode.node(
        final_type,
        CoreNode.node(T.FRACTION, current.children[0], divisor),
        CoreNode.node(T.FRACTION, current.children[1], divisor),
    )
    x = CoreNode.variable(var)
    by_self = CoreNode.node(final_type, x, CoreNode.node(T.FRACTION, current.children[1], divisor))
    solution = CoreNode.node(final_type, x, _const(total / coefficient))
    numerator = current.children[1]
    zero_divided = numerator.type is T.CONSTANT and (numerator.value or "") in ("0", "-0")
    last = (
        Step(by_self, solution, "div_zero", [_const(Fraction(0))])
        if zero_divided
        else Step(by_self, solution, "quotient")
    )
    key = "ineq_linear_div_neg" if coefficient < 0 else "ineq_linear_div"
    if coefficient < 0 and total > 0:  # the flip is its own row
        by_sign = CoreNode.node(
            final_type, x, _negated(CoreNode.node(T.FRACTION, _const(total), _const(-coefficient)))
        )
        ctx.result.add_group(
            "divide_both_sides", Step(current, divided, key, [_const(coefficient)])
        )
        ctx.result.add_group(
            "divide",
            Step(divided, by_self, "div_with_self", [_const(Fraction(1))]),
            Step(by_self, by_sign, "div_pos_neg", [CoreNode.variable("−")]),
            Step(by_sign, solution, "quotient"),
        )
        return solution
    pages = [
        Step(divided, by_self, "div_with_self", [_const(Fraction(1))]),
        last,
    ]
    if not ctx.result:  # symbol already divided out: both rows are top-level
        ctx.result.add_group(
            "divide_both_sides", Step(current, divided, key, [_const(coefficient)])
        )
        ctx.result.add_group("divide", *pages)
        return solution
    detail = SolveResult()
    detail.add_group("divide_both_sides", Step(current, divided, key, [_const(coefficient)]))
    detail.add_group("divide", *pages)
    detail.set_solution(solution)
    ctx.result.add_group(
        "divide_both_sides",
        Step(current, solution, key, [_const(coefficient)], subresult=detail),
    )
    return solution


def _ineq_rows(
    node: CoreNode, lhs: CoreNode, rhs: CoreNode, var: str, ctx: SolveContext
) -> CoreNode | None:
    """The app rows for ``a1 x + b1 ⋚ a2 x + b2``.

    Same order as the verified cards, with the inequality keys of the move and
    divide screens (``rel_move_right_const_ineq``, ``sub_with_self_remove_*``,
    ``ineq_linear_div``). ``None`` means a side is not a plain ``a x + b``.
    """
    left_side, right_side = _simple_side(lhs, var), _simple_side(rhs, var)
    if left_side is None or right_side is None:
        return None
    (a1, b1), (a2, b2) = left_side, right_side
    if a1 == 0 or a1 == a2:
        return None
    if a2 == 0:
        detail = _condition_rows(node, var)
        if detail is None or detail.solution is None:
            return None
        ctx.result.extend(detail)
        if a1 == 1:
            return detail.solution
        return _divide_rows(node.type, detail.solution, var, a1, b2 - b1, ctx)

    eq = CoreNode.node
    term = _x_term(abs(a2), var)
    sign = T.SUBTRACT if a2 > 0 else T.ADD
    moved_lhs = eq(sign, lhs, term)
    balanced = eq(node.type, eq(sign, lhs, term), eq(sign, rhs, term))
    after = eq(node.type, moved_lhs, _const(b2))
    move_left = SolveResult()
    move_left.add_group("rel_swap_left_var_msg", Step(node, balanced, "rel_swap_left_var"))
    move_left.add_group("remove_opposites", Step(balanced, after, "sub_with_self_remove_alg"))
    move_left.set_solution(after)
    stages = [Step(node, after, "rel_move_left_var", subresult=move_left)]
    current, cur_lhs, cur_rhs = after, moved_lhs, _const(b2)
    amount = _const(abs(b1))
    if b1 != 0:
        sign_const = T.SUBTRACT if b1 > 0 else T.ADD
        balanced_const = eq(
            node.type, eq(sign_const, cur_lhs, amount), eq(sign_const, cur_rhs, amount)
        )
        x_part = eq(T.SUBTRACT if a2 > 0 else T.ADD, _x_term(a1, var), _x_term(abs(a2), var))
        rhs_after = eq(sign_const, _const(b2), amount)
        after_const = eq(node.type, x_part, rhs_after)
        move_right = SolveResult()
        move_right.add_group(
            "rel_move_right_const_msg",
            Step(after, balanced_const, "rel_swap_right_const"),
        )
        move_right.add_group(
            "remove_opposites",
            Step(balanced_const, after_const, "sub_with_self_remove_num"),
        )
        move_right.set_solution(after_const)
        stages.append(Step(after, after_const, "rel_move_right_const_ineq", subresult=move_right))
        current, cur_lhs, cur_rhs = after_const, x_part, rhs_after
    ctx.result.add_group("rel_move_short", *stages)

    coefficient = a1 - a2
    detail = _sum_detail(a1, a2, coefficient, cur_lhs, var)
    collected = eq(node.type, _x_term(coefficient, var), cur_rhs)
    if b1 != 0 and b2 != 0:
        done = eq(node.type, _x_term(coefficient, var), _const(b2 - b1))
        ctx.result.add_group(
            ["sum_suffix", "calculate_short"],
            Step(current, collected, "sum_suffix", subresult=detail),
            Step(collected, done, "add" if b1 < 0 else "sub"),
        )
        current = done
    else:
        ctx.result.add_group("sum_suffix", Step(current, collected, "sum_suffix", subresult=detail))
        current = collected
    if coefficient == 1:
        return current
    return _divide_rows(node.type, current, var, coefficient, b2 - b1, ctx)


def _single_points(node: CoreNode) -> CoreNode:
    """``[0, 0]`` is the single point ``{0}``."""
    if (
        node.type is T.CLOSED_CLOSED_INTERVAL
        and len(node.children) == 2
        and node.children[0].structural_eq(node.children[1])
    ):
        return CoreNode.node(T.SET, node.children[0])
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[_single_points(child) for child in node.children],
    )


@solver_for(*_RELATIONS)
def solve_inequality(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Решить неравенство; одиночная точка записывается как множество ``{a}``."""
    return _single_points(_solve_inequality(node, ctx))


def _solve_inequality(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Решить линейное неравенство с одним неизвестным."""
    ctx.require(len(node.children) >= 2, "неравенство связывает две части")
    ctx.require(len(ctx.variables) == 1, "поддерживается одно неизвестное")
    var = ctx.variables[0]
    if len(node.children) > 2:
        compound = _compound_inequality(node, var, ctx)
        if compound is None:
            raise SolveError("двойное неравенство не решается")
        return compound
    lhs, rhs = node.children

    restriction = _power_restriction_rows(node, var)
    if restriction is not None:
        card, state = restriction
        ctx.result.extend(card)
        if _negative_power_always_positive(node, var):
            answer = _always_true_answer(node, var)
            if answer is not None:
                ctx.result.add_group(
                    CoreRichText(type="rel_el_of_r", args=[CoreNode.variable(var)]),
                    Step(
                        state,
                        answer,
                        "rel_terminators_left_pos_true",
                        [CoreNode.variable(var)],
                    ),
                )
                return answer
        if (shown := _negative_odd_power_card(node, var, state, ctx)) is not None:
            return shown

    try:
        poly = poly_of(lhs, var)
        for degree, coeff in poly_of(rhs, var).items():
            poly[degree] = poly.get(degree, Fraction(0)) - coeff
            if poly[degree] == 0:
                del poly[degree]
    except SolveError as error:
        for solver in (
            _rational_inequality,
            _cancelling_fraction_inequality,
            _irrational_inequality,
            _abs_inequality,
            _transcendental_inequality,
            _trig_inequality,
        ):
            answer = solver(node, var, ctx)
            if answer is not None:
                return answer
        # Прежний «уравнение с узлом SIN не решается» здесь вводил в заблуждение:
        # это неравенство, и ни один специальный путь его не взял.
        raise SolveError(
            "неравенство не решается: выражение не сводится к многочлену, дроби, "
            "корню, модулю, показателю или периоду"
        ) from error

    degree = max(poly) if poly else 0
    if degree == 0:
        return _constant_inequality(node, poly, ctx)
    if degree == 2:
        return _quadratic_inequality(node, var, poly, ctx)
    if degree >= 3 and (shown := _odd_power_inequality(node, var, poly, ctx)) is not None:
        return shown
    if degree >= 3 and (shown := _polynomial_inequality(node, var, poly, ctx)) is not None:
        return shown
    ctx.require(degree == 1, "поддерживаются линейные, квадратные и многочленные неравенства")

    if (shown := _multiply_first(node, var, ctx)) is not None:
        return shown

    a = poly[1]
    b = poly.get(0, Fraction(0))
    value = -b / a
    # При делении на отрицательное число знак неравенства меняется.
    final_type = node.type if a > 0 else _FLIP[node.type]

    rows = _ineq_rows(node, lhs, rhs, var, ctx)
    if rows is not None:
        return rows

    left = node
    already = poly_of(lhs, var) == {1: a} and poly_of(rhs, var) == {0: -b}
    if b != 0 and not already:
        after_move = CoreNode(type=node.type, children=[_x_term(a, var), _const(-b)])
        ctx.result.add(Step(left=node, right=after_move, key="move"), [_HEADER])
        left = after_move

    solution = CoreNode(type=final_type, children=[CoreNode.variable(var), _const(value)])
    if a != 1:
        key = "ineq_linear_div_neg" if a < 0 else "ineq_linear_div"
        ctx.result.add(Step(left=left, right=solution, key=key, args=[_const(a)]), [_HEADER])
    return solution


def _multiply_first(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """``x / d`` against a number, ``d`` a positive integer: multiply both sides at once."""
    fraction, number = node.children
    if not (
        fraction.type is T.FRACTION
        and fraction.children[0].type is T.VARIABLE
        and fraction.children[0].value == var
        and fraction.children[1].type is T.CONSTANT
        and (fraction.children[1].value or "").isdigit()
        and int(fraction.children[1].value or 0) > 0
        and number.type is T.CONSTANT
        and (number.value or "").isdigit()
    ):
        return None
    d = fraction.children[1]
    rel = CoreNode.node
    scaled = rel(node.type, rel(T.MULTIPLY, d, fraction), rel(T.MULTIPLY, d, number))
    cleared = rel(node.type, CoreNode.variable(var), rel(T.MULTIPLY, d, number))
    solution = rel(
        node.type,
        CoreNode.variable(var),
        _const(Fraction(int(d.value or 1) * int(number.value or 0))),
    )
    ctx.result.add_group("multiply_both_sides", Step(node, scaled, "ineq_mul_direct", [d]))
    ctx.result.add_group(
        ["reduce", "multiply"],
        Step(scaled, cleared, "frac_reduce_out", [d]),
        Step(cleared, solution, "mul"),
    )
    return solution


_QUOTIENT_KEY: dict[T, str] = {
    T.LESS_THAN: "ineq_quotient_lt",
    T.LESS_THAN_EQUAL: "ineq_quotient_lte",
    T.GREATER_THAN: "ineq_quotient_gt",
    T.GREATER_THAN_EQUAL: "ineq_quotient_gte",
}


def _quotient_cases(relation: T) -> tuple[tuple[T, T], tuple[T, T]]:
    """Sign cases of ``A / B ⋚ 0``; the denominator comparison is always strict."""
    return {
        T.LESS_THAN: ((T.LESS_THAN, T.GREATER_THAN), (T.GREATER_THAN, T.LESS_THAN)),
        T.GREATER_THAN: ((T.GREATER_THAN, T.GREATER_THAN), (T.LESS_THAN, T.LESS_THAN)),
        T.LESS_THAN_EQUAL: (
            (T.LESS_THAN_EQUAL, T.GREATER_THAN),
            (T.GREATER_THAN_EQUAL, T.LESS_THAN),
        ),
        T.GREATER_THAN_EQUAL: (
            (T.GREATER_THAN_EQUAL, T.GREATER_THAN),
            (T.LESS_THAN_EQUAL, T.LESS_THAN),
        ),
    }[relation]


def _mk(kind: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(kind, *children)


def _rel(kind: T, left: CoreNode, right: CoreNode) -> CoreNode:
    return CoreNode.node(kind, left, right)


def _two_case_rows(
    node: CoreNode,
    var: str,
    numerator: CoreNode,
    denominator: CoreNode,
    answer: CoreNode,
    *,
    kept: CoreNode | None,
) -> SolveResult | None:
    """``A/B ⋚ 0``: split into sign cases, solve four linear conditions, intersect, unite."""
    x = CoreNode.variable(var)
    zero = _const(Fraction(0))
    pair = _quotient_cases(node.type)
    cases = _mk(
        T.LIST,
        _mk(T.SYSTEM, _rel(pair[0][0], numerator, zero), _rel(pair[0][1], denominator, zero)),
        _mk(T.SYSTEM, _rel(pair[1][0], numerator, zero), _rel(pair[1][1], denominator, zero)),
    )
    sets = [_system_set(case, var) for case in cases.children]
    if any(item is None for item in sets):
        return None
    try:
        intervals = [from_sympy(item) for item in sets if item is not None]
    except SolveError:
        return None
    start = _rel(node.type, _mk(T.FRACTION, numerator, denominator), zero)
    state = [list(case.children) for case in cases.children]
    pages: list[Step] = []
    for index, case in enumerate(cases.children):
        for position, condition in enumerate(case.children):
            before = _mk(T.LIST, *[_mk(T.SYSTEM, *terms) for terms in state])
            detail, solved = _abs_detail(condition, var, compact=True)
            state[index][position] = solved
            following = _mk(T.LIST, *[_mk(T.SYSTEM, *terms) for terms in state])
            pages.append(Step(before, following, "ineq_linear", [x], subresult=detail))
    first = _mk(T.LIST, _rel(T.ELEMENT_OF, x, intervals[0]), _mk(T.SYSTEM, *state[1]))
    second = _mk(
        T.LIST,
        _rel(T.ELEMENT_OF, x, intervals[0]),
        _rel(T.ELEMENT_OF, x, intervals[1]),
    )
    local = SolveResult()
    local.add_group("eq_separate_short", Step(start, cases, _QUOTIENT_KEY[node.type]))
    local.add_group("ineq_solve_short_plural", *pages)
    local.add_group(
        "intersection_plural",
        Step(pages[-1].right, first, "intersection"),
        Step(first, second, "intersection"),
    )
    union_right = answer if kept is None else _mk(T.LIST, answer, kept)
    local.add_group("union", Step(second, union_right, "union"))
    if kept is not None:
        local.add_group("intersection", Step(union_right, answer, "rel_restrictions_intersect"))
    local.set_solution(answer)
    return local


def _restrictions_detail(
    node: CoreNode,
    var: str,
    *,
    find_key: str,
    find_args: list[CoreNode],
    forbidden: CoreNode,
    solve_title: str | None,
    solve_step: Step | None,
    kept: CoreNode,
) -> tuple[SolveResult, CoreNode]:
    """The app's ``rel_restrictions_range`` card: find the excluded values, keep the rest."""
    state = _mk(T.LIST, node, kept)
    detail = SolveResult()
    detail.add_group("rel_restrictions_find", Step(node, forbidden, find_key, find_args))
    source = forbidden
    if solve_step is not None:
        detail.add_group(solve_title or "calculate_short", solve_step)
        if solve_step.right is not None:
            source = solve_step.right
    detail.add_group("exclude_values", Step(source, state, "rel_restrictions_range_complement"))
    detail.set_solution(state)
    card = SolveResult()
    card.add_group(
        "rel_restrictions_range",
        Step(node, state, "rel_restrictions_range", subresult=detail),
    )
    return card, state


def _has_range_restriction(ctx: SolveContext) -> bool:
    """Has a ``rel_restrictions_range`` card already been added to this result?"""
    return any(step.key == "rel_restrictions_range" for step in ctx.result)


def _sum_terms(node: CoreNode) -> list[CoreNode] | None:
    """Flat list of the terms of a sum, or ``None`` when a difference hides a variable term."""
    if node.type is T.ADD:
        out: list[CoreNode] = []
        for child in node.children:
            terms = _sum_terms(child)
            if terms is None:
                return None
            out.extend(terms)
        return out
    if node.type is T.SUBTRACT and len(node.children) == 2:
        second = node.children[1]
        if second.type is T.CONSTANT or second.type is T.POWER:
            terms = _sum_terms(node.children[0])
            if terms is None:
                return None
            return [*terms, CoreNode(type=T.NEGATIVE, children=[second])]
        return None
    return [node]


def _nonnegative_term(term: CoreNode, var: str) -> bool:
    """Is the term never negative on the domain (a constant, an even power, ``|·|``)?"""
    if term.type is T.NEGATIVE and len(term.children) == 1:
        return False
    if term.type is T.CONSTANT:
        try:
            return as_fraction(term) >= 0
        except SolveError:
            return False
    if term.type is T.ABS:
        return True
    if term.type is T.POWER and len(term.children) == 2:
        base, exponent = term.children
        if base.type is T.VARIABLE and base.value == var:
            value = _coefficient(exponent)
            if value is not None:
                return value.denominator == 1 and int(value) % 2 == 0
        return False
    if term.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) and len(term.children) == 2:
        coefficient = _coefficient(term.children[0])
        if coefficient is not None and coefficient > 0:
            return _nonnegative_term(term.children[1], var)
        coefficient = _coefficient(term.children[1])
        if coefficient is not None and coefficient > 0:
            return _nonnegative_term(term.children[0], var)
    return False


def _negative_power_always_positive(node: CoreNode, var: str) -> bool:
    """``x⁻² + 1 > 0``: every term is non-negative and a negative power is present."""
    lhs, rhs = node.children
    if (
        node.type not in (T.GREATER_THAN, T.GREATER_THAN_EQUAL)
        or rhs.type is not T.CONSTANT
        or (rhs.value or "") not in ("0", "-0")
    ):
        return False
    terms = _sum_terms(lhs)
    if not terms:
        return False
    has_negative_power = any(
        term.type is T.POWER
        and len(term.children) == 2
        and term.children[0].type is T.VARIABLE
        and term.children[0].value == var
        and _coefficient(term.children[1]) is not None
        and (_coefficient(term.children[1]) or Fraction(0)) < 0
        for term in terms
    )
    return has_negative_power and all(_nonnegative_term(term, var) for term in terms)


def _always_true_answer(node: CoreNode, var: str) -> CoreNode | None:
    """Solution set of a statement that holds everywhere it is defined."""
    expression = _difference(node)
    if expression is None:
        return None
    try:
        values = sympy.solveset(
            _relational(node.type, expression), sympy.Symbol(var), sympy.S.Reals
        )
        return from_sympy(values)
    except (SolveError, TypeError, ValueError, NotImplementedError):
        return None


def _negative_odd_power_card(
    node: CoreNode, var: str, state: CoreNode, ctx: SolveContext
) -> CoreNode | None:
    """``x⁻ⁿ + 1 ⋚ 0`` with odd ``n``: flip to ``1/xⁿ``, join, then solve the sign cases."""
    lhs, rhs = node.children
    if (
        node.type not in (T.LESS_THAN, T.LESS_THAN_EQUAL, T.GREATER_THAN, T.GREATER_THAN_EQUAL)
        or rhs.type is not T.CONSTANT
        or (rhs.value or "") not in ("0", "-0")
    ):
        return None
    terms = _sum_terms(lhs)
    if not terms or len(terms) != 2:
        return None
    constants = [term for term in terms if term.type is T.CONSTANT]
    negatives = [
        term
        for term in terms
        if term.type is T.POWER
        and len(term.children) == 2
        and term.children[0].type is T.VARIABLE
        and term.children[0].value == var
        and (_coefficient(term.children[1]) or Fraction(0)) < 0
    ]
    if len(constants) != 1 or len(negatives) != 1:
        return None
    if as_fraction(constants[0]) != 1:
        return None
    exponent = _coefficient(negatives[0].children[1])
    assert exponent is not None
    n = int(-exponent)
    if n < 1 or n % 2 == 0:
        return None
    answer = _always_true_answer(node, var)
    if answer is None:
        return None
    x, zero = CoreNode.variable(var), _const(Fraction(0))
    power = CoreNode.node(T.POWER, x, _const(Fraction(n)))
    one = _const(Fraction(1))
    a, parameter = CoreNode.variable("a"), CoreNode.variable("n")
    template = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.POWER, a, CoreNode(type=T.NEGATIVE, children=[parameter])),
        CoreNode.node(T.FRACTION, one, CoreNode.node(T.POWER, a, parameter)),
    )
    flipped_expression = CoreNode.node(T.ADD, CoreNode.node(T.FRACTION, one, power), one)
    flipped = CoreNode.node(node.type, flipped_expression, zero)
    bracketed = CoreNode.node(T.BRACKET, power)
    as_fraction_expression = CoreNode.node(
        T.ADD, CoreNode.node(T.FRACTION, one, power), CoreNode.node(T.FRACTION, one, one)
    )
    expanded = CoreNode.node(
        T.ADD,
        CoreNode.node(T.FRACTION, one, power),
        CoreNode.node(
            T.FRACTION,
            CoreNode.node(T.MULTIPLY, bracketed, one),
            CoreNode.node(T.MULTIPLY, bracketed, one),
        ),
    )
    denominator_product = CoreNode.node(T.MULTIPLY, bracketed, one)
    with_numerator = CoreNode.node(
        T.ADD,
        CoreNode.node(T.FRACTION, one, power),
        CoreNode.node(T.FRACTION, power, denominator_product),
    )
    with_denominator = CoreNode.node(
        T.ADD,
        CoreNode.node(T.FRACTION, one, power),
        CoreNode.node(T.FRACTION, power, power),
    )
    joined_expression = CoreNode.node(T.FRACTION, CoreNode.node(T.ADD, one, power), power)
    join = SolveResult()
    join.add_group(
        "convert_expression",
        Step(
            flipped_expression,
            as_fraction_expression,
            "frac_expand_int",
            [
                CoreNode.node(
                    T.EQUALS,
                    CoreNode.variable("q"),
                    CoreNode.node(T.FRACTION, CoreNode.variable("q"), one),
                )
            ],
        ),
    )
    join.add_group(
        "frac_expand",
        Step(as_fraction_expression, expanded, "frac_sum_expand"),
    )
    join.add_group(
        "product_plural",
        Step(expanded, with_numerator, "mul_with_one", [one]),
        Step(with_numerator, with_denominator, "mul_with_one", [one]),
    )
    join.add_group(
        "trans_msg",
        Step(with_denominator, joined_expression, "frac_sum_join"),
    )
    join.set_solution(joined_expression)
    joined = CoreNode.node(node.type, joined_expression, zero)
    local = SolveResult()
    local.add_group("pow_express_pos_exp", Step(state, flipped, "pow_flip_msg", [template]))
    local.add_group("trans_msg", Step(flipped, joined, "frac_sum_join", subresult=join))
    rows = _two_case_rows(
        node,
        var,
        CoreNode.node(T.ADD, one, power),
        power,
        answer,
        kept=CoreNode.node(T.NOT_EQUALS, x, zero),
    )
    if rows is None:
        return None
    local.extend(rows)
    ctx.result.extend(local)
    return answer


def _power_restriction_rows(node: CoreNode, var: str) -> tuple[SolveResult, CoreNode] | None:
    """Domain card for ``x⁰``, ``x⁻ⁿ`` and ``x^{p/q}`` (``rel_restrictions_range``).

    Only the restriction row of the verified cards is produced: the rewriting rows
    that follow (``pow_with_zero``, ``pow_flip_one``, ``using_trans``) live in the
    powers/quadratic modules.
    """
    x, zero = CoreNode.variable(var), _const(Fraction(0))
    for part in node.walk():
        if part.type is not T.POWER or len(part.children) != 2:
            continue
        base, exponent = part.children
        if base.type is not T.VARIABLE or base.value != var:
            continue
        if exponent.type is T.NEGATIVE and len(exponent.children) == 1:
            try:
                value = -as_fraction(exponent.children[0])
            except SolveError:
                continue
        elif exponent.type is T.CONSTANT and exponent.value is not None:
            try:
                value = as_fraction(exponent)
            except SolveError:
                continue
        else:
            continue
        if value == 0:
            key, args = "rel_restrictions_base_zero_zero", [x, zero, part]
            forbidden, kept = _rel(T.EQUALS, base, zero), _rel(T.NOT_EQUALS, x, zero)
        elif value < 0:
            key, args = "rel_restrictions_base_zero_neg", [x, zero, part]
            forbidden, kept = _rel(T.EQUALS, base, zero), _rel(T.NOT_EQUALS, x, zero)
        elif value.denominator != 1:
            key, args = "rel_restrictions_exp_neg_base", [x, part]
            forbidden, kept = _rel(T.LESS_THAN, x, zero), _rel(T.GREATER_THAN_EQUAL, x, zero)
        else:
            continue
        card, state = _restrictions_detail(
            node,
            var,
            find_key=key,
            find_args=args,
            forbidden=forbidden,
            solve_title=None,
            solve_step=None,
            kept=kept,
        )
        return card, state
    return None


def _rational_normalization_card(
    node: CoreNode, var: str, answer: CoreNode, ctx: SolveContext
) -> bool:
    """``c/(x+b) ⋚ d`` or ``x/(x+b) ⋚ d``: restrictions, common denominator, sign cases.

    The verified the app family: integer ``c``/``d``, denominator ``x + b``.
    Returns ``False`` without touching the result for everything else.
    """
    lhs, rhs = node.children
    if lhs.type is not T.FRACTION or len(lhs.children) != 2 or rhs.type is not T.CONSTANT:
        return False
    numerator_node, denominator_node = lhs.children
    try:
        shift = as_fraction(rhs)
    except SolveError:
        return False
    if shift.denominator != 1 or shift == 0:
        return False
    denominator = _simple_side(denominator_node, var)
    numerator = _simple_side(numerator_node, var)
    if denominator is None or numerator is None or denominator[0] != 1:
        return False
    b = denominator[1]
    na, nb = numerator
    constant_numerator = na == 0
    variable_numerator = na == 1 and nb == 0
    if not (constant_numerator or variable_numerator):
        return False
    x = CoreNode.variable(var)
    zero = _const(Fraction(0))
    kept = _rel(T.NOT_EQUALS, x, _const(-b))
    forbidden = _rel(T.EQUALS, denominator_node, zero)
    restriction, state = _restrictions_detail(
        node,
        var,
        find_key="rel_restrictions_den_zero",
        find_args=[x, zero, denominator_node],
        forbidden=forbidden,
        solve_title="eq_solve_short",
        solve_step=Step(forbidden, _rel(T.EQUALS, x, _const(-b)), "eq_linear", [x]),
        kept=kept,
    )
    local = SolveResult()
    local.extend(restriction)

    # Move the right-hand constant left.
    moved_expression = _mk(T.SUBTRACT, lhs, _const(shift))
    balanced = _rel(node.type, moved_expression, _mk(T.SUBTRACT, _const(shift), _const(shift)))
    moved = _rel(node.type, moved_expression, zero)
    move = SolveResult()
    move.add_group(
        "rel_move_left_const_msg",
        Step(node, balanced, "rel_swap_left_const"),
    )
    move.add_group("sub_with_self_del", Step(balanced, moved, "sub_with_self_num", [zero]))
    move.set_solution(moved)
    local.add_group(
        "rel_move_left_const_msg", Step(state, moved, "rel_move_left_const", subresult=move)
    )

    # Bring both terms over the denominator.
    bracketed = _mk(T.BRACKET, denominator_node)
    rhs_fraction = _mk(T.FRACTION, _const(shift), _const(Fraction(1)))
    expanded_fraction = _mk(
        T.FRACTION,
        _mk(T.MULTIPLY, bracketed, _const(shift)),
        _mk(T.MULTIPLY, bracketed, _const(Fraction(1))),
    )
    reduced_fraction = _mk(
        T.FRACTION,
        _mk(T.MULTIPLY, bracketed, _const(shift)),
        denominator_node,
    )
    join = SolveResult()
    join.add_group(
        "convert_expression",
        Step(
            moved_expression,
            _mk(T.SUBTRACT, lhs, rhs_fraction),
            "frac_expand_int",
            [
                _rel(
                    T.EQUALS,
                    CoreNode.variable("a"),
                    _mk(T.FRACTION, CoreNode.variable("a"), _const(Fraction(1))),
                )
            ],
        ),
    )
    join.add_group(
        "frac_expand",
        Step(
            _mk(T.SUBTRACT, lhs, rhs_fraction),
            _mk(T.SUBTRACT, lhs, expanded_fraction),
            "frac_sum_expand",
        ),
    )
    join.add_group(
        "product",
        Step(
            _mk(T.SUBTRACT, lhs, expanded_fraction),
            _mk(T.SUBTRACT, lhs, reduced_fraction),
            "mul_with_one",
            [_const(Fraction(1))],
        ),
    )
    joined_expression = _mk(
        T.FRACTION,
        _mk(T.SUBTRACT, numerator_node, _mk(T.MULTIPLY_IMPLICIT, _const(shift), bracketed)),
        denominator_node,
    )
    join.add_group(
        "trans_msg",
        Step(
            _mk(T.SUBTRACT, lhs, reduced_fraction),
            joined_expression,
            "frac_sum_join",
        ),
    )
    join.set_solution(joined_expression)
    joined = _rel(node.type, joined_expression, zero)
    local.add_group("trans_msg", Step(moved, joined, "frac_sum_join", subresult=join))

    # Open the bracket in the numerator.
    negated_product = _mk(T.MULTIPLY_IMPLICIT, _negated(_const(shift)), bracketed)
    each = _mk(
        T.SUBTRACT,
        _mk(T.MULTIPLY_IMPLICIT, _negated(_const(shift)), x),
        _mk(T.MULTIPLY, _const(shift), _mk(T.BRACKET, _const(b))),
    )
    inner_solved = _mk(
        T.ADD,
        _mk(T.MULTIPLY_IMPLICIT, _negated(_const(shift)), x),
        _const(-shift * b),
    )
    product_key = "mul_with_neg_one" if b == -1 else "mul"
    product_args = [_negated(_const(Fraction(1)))] if b == -1 else []
    bracket_detail = SolveResult()
    bracket_detail.add_group(
        CoreRichText(type="mul_bracket_each_short", args=[_negated(_const(shift))]),
        Step(negated_product, each, "mul_bracket_each", [_negated(_const(shift))]),
    )
    bracket_detail.add_group(
        "product" if b == -1 else "multiply",
        Step(each, inner_solved, product_key, product_args),
    )
    bracket_detail.set_solution(inner_solved)
    expanded_numerator = _mk(
        T.ADD,
        _mk(T.SUBTRACT, numerator_node, _mk(T.MULTIPLY_IMPLICIT, _const(shift), x)),
        _const(-shift * b),
    )
    expanded_expression = _mk(T.FRACTION, expanded_numerator, denominator_node)
    expanded = _rel(node.type, expanded_expression, zero)
    local.add_group(
        "remove_bracket_short",
        Step(
            joined,
            expanded,
            "mul_bracket",
            [_negated(_const(shift))],
            subresult=bracket_detail,
        ),
    )

    if constant_numerator:
        linear_numerator = _mk(
            T.SUBTRACT,
            _const(nb - shift * b),
            _mk(T.MULTIPLY_IMPLICIT, _const(shift), x),
        )
        final_expression = _mk(T.FRACTION, linear_numerator, denominator_node)
        local.add_group(
            "calculate_short", Step(expanded, _rel(node.type, final_expression, zero), "add")
        )
    else:
        before = _mk(T.SUBTRACT, x, _mk(T.MULTIPLY_IMPLICIT, _const(shift), x))
        with_one = _mk(
            T.SUBTRACT,
            _mk(T.MULTIPLY_IMPLICIT, _const(Fraction(1)), x),
            _mk(T.MULTIPLY_IMPLICIT, _const(shift), x),
        )
        grouped = _mk(
            T.MULTIPLY_IMPLICIT,
            _mk(T.BRACKET, _mk(T.SUBTRACT, _const(Fraction(1)), _const(shift))),
            x,
        )
        coefficient = Fraction(1) - shift
        collected = _mk(T.MULTIPLY_IMPLICIT, _const(coefficient), x)
        sum_detail = SolveResult()
        sum_detail.add_group(
            CoreRichText(type="sum_one_coeff", args=[_const(Fraction(1))]),
            Step(before, with_one, "sum_suffix_add_one", [_const(Fraction(1))]),
        )
        sum_detail.add_group("sum_suffix", Step(with_one, grouped, "sum_suffix_sub_detail"))
        sum_detail.add_group("calculate_short", Step(grouped, collected, "calc_diff"))
        sum_detail.set_solution(collected)
        summed_numerator = _mk(T.ADD, collected, _const(-shift * b))
        final_expression = _mk(T.FRACTION, summed_numerator, denominator_node)
        local.add_group(
            "sum_suffix",
            Step(
                expanded,
                _rel(node.type, final_expression, zero),
                "sum_suffix",
                subresult=sum_detail,
            ),
        )
        if coefficient not in (0, 1) and (-shift * b) % coefficient == 0:
            inside = (-shift * b) // coefficient
            factored_numerator = _mk(
                T.MULTIPLY_IMPLICIT,
                _const(coefficient),
                _mk(T.BRACKET, _mk(T.SUBTRACT, x, _const(Fraction(-inside)))),
            )
            factored_expression = _mk(T.FRACTION, factored_numerator, denominator_node)
            local.add_group(
                "factorise_call",
                Step(
                    _rel(node.type, final_expression, zero),
                    _rel(node.type, factored_expression, zero),
                    "extract_arg",
                    [_const(coefficient)],
                ),
            )
            final_expression = factored_expression
    numerator_final = final_expression.children[0]
    rows = _two_case_rows(node, var, numerator_final, denominator_node, answer, kept=kept)
    if rows is None:
        return False
    local.extend(rows)
    local.set_solution(answer)
    ctx.result.extend(local)
    return True


def _cancelling_fraction_inequality(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """``x/(3x) > 2``: the unknown cancels, so the truth of the relation is the same everywhere.

    A true relation holds for every real number except the zeros of the denominators; a false
    one has no solutions.
    """
    from .equations import _all_real_except

    symbol = sympy.Symbol(var)
    poles: list[sympy.Expr] = []
    for part in node.walk():
        if part.type in (T.FRACTION, T.DIVIDE) and len(part.children) == 2:
            denominator = to_sympy(part.children[1])
            if denominator.has(symbol):
                poles.extend(sympy.solve(denominator, symbol))
    if not poles:
        return None
    left, right = (to_sympy(child) for child in node.children)
    verdict = _relational(node.type, sympy.simplify(left - right))
    if sympy.simplify(left - right).free_symbols:
        return None
    ctx.result.add(Step(left=node, right=None, key="rel_restrictions_find"), [_HEADER])
    if verdict is sympy.true:
        return _all_real_except(poles)
    ctx.result.add(Step(left=node, right=None, key="false_statement_solve"), [_HEADER])
    return CoreNode.empty()


def _direct_quotient_card(node: CoreNode, var: str, answer: CoreNode, ctx: SolveContext) -> bool:
    """``(linear)/(linear) ⋚ 0``: the app's sign-case card without a separate restriction row."""
    lhs, rhs = node.children
    if lhs.type is not T.FRACTION or len(lhs.children) != 2 or rhs.type is not T.CONSTANT:
        return False
    try:
        if as_fraction(rhs) != 0:
            return False
    except SolveError:
        return False
    numerator, denominator = lhs.children
    if _simple_side(numerator, var) is None or _simple_side(denominator, var) is None:
        return False
    rows = _two_case_rows(node, var, numerator, denominator, answer, kept=None)
    if rows is None:
        return False
    ctx.result.extend(rows)
    return True


def _rational_inequality(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """Решить неравенство с неизвестным в знаменателе.

    Множество решений даёт ``sympy.solveset`` на числовой прямой; ответ
    переводится в промежутки/объединение. Для разобранных вручную семейств строки
    строятся по карточкам: ``(linear)/(linear) ⋚ 0`` — сразу случаи знаков,
    ``c/(x+b) ⋚ d`` и ``x/(x+b) ⋚ d`` — ОДЗ, общий знаменатель, случаи знаков.
    ``None`` — знаменатель не зависит от неизвестной (не рациональное) или
    отношение не поддерживается.
    """
    lhs, rhs = node.children
    try:
        expression = sympy.together(to_sympy(lhs) - to_sympy(rhs))
        numerator, denominator = sympy.fraction(expression)
    except SolveError:
        return None
    if not denominator.has(sympy.Symbol(var)):
        return None
    symbol = sympy.Symbol(var)
    if _has_variable_power(denominator, symbol) or _has_variable_power(numerator, symbol):
        # ``(1/3)^x`` в знаменателе — это показательное, а не рациональное неравенство
        return None
    key = _QUOTIENT_KEY.get(node.type)
    if key is None:
        return None
    try:
        values = sympy.solveset(_relational(node.type, expression), symbol, sympy.S.Reals)
    except (TypeError, ValueError, NotImplementedError):
        return None
    answer = from_sympy(values)
    if _direct_quotient_card(node, var, answer, ctx):
        return answer
    if _rational_normalization_card(node, var, answer, ctx):
        return answer

    if not _has_range_restriction(ctx):
        add_restriction_steps(node, [var], ctx, expression)
    ctx.result.add(Step(left=node, right=answer, key=key), [_HEADER])
    return answer


def _compound_inequality(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """Двойное (тройное) неравенство ``a ⋚ x ⋚ b`` — пересечение условий.

    Цепочка из трёх и более детей разбирается в ``And`` отношений; множество
    решений даёт ``solveset``, ответ — промежуток.
    """
    try:
        values = [to_sympy(child) for child in node.children]
    except SolveError:
        return None
    symbol = sympy.Symbol(var)
    conditions = [
        _chain_relation(node.type, left, right) for left, right in itertools.pairwise(values)
    ]
    try:
        pieces = [sympy.solveset(condition, symbol, sympy.S.Reals) for condition in conditions]
    except (TypeError, ValueError, NotImplementedError):
        return None
    result_set = pieces[0] if len(pieces) == 1 else sympy.Intersection(*pieces)
    try:
        answer = from_sympy(sympy.simplify(result_set))
    except SolveError:
        return None
    ctx.result.add(Step(left=node, right=answer, key="ineq_solve_separate"), [_HEADER])
    return answer


def _chain_relation(node_type: T, left: sympy.Expr, right: sympy.Expr) -> sympy.Rel:
    """Одно звено цепочки неравенств."""
    if node_type is T.LESS_THAN:
        return sympy.Lt(left, right)
    if node_type is T.LESS_THAN_EQUAL:
        return sympy.Le(left, right)
    if node_type is T.GREATER_THAN:
        return sympy.Gt(left, right)
    if node_type is T.GREATER_THAN_EQUAL:
        return sympy.Ge(left, right)
    return sympy.Ne(left, right)


def _irrational_rows(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """``√(a x + b) ⋚ c x + d``: restriction, two sign cases, squaring, intersections."""
    lhs, rhs = node.children
    if (
        lhs.type is not T.ROOT2
        or len(lhs.children) != 1
        or node.type not in (T.LESS_THAN, T.LESS_THAN_EQUAL, T.GREATER_THAN, T.GREATER_THAN_EQUAL)
    ):
        return None
    radicand_node = lhs.children[0]
    if _simple_side(radicand_node, var) is None or _simple_side(rhs, var) is None:
        return None
    expression = _difference(node)
    if expression is None:
        return None
    x, zero = CoreNode.variable(var), _const(Fraction(0))
    symbol = sympy.Symbol(var)
    try:
        answer = from_sympy(
            sympy.solveset(_relational(node.type, expression), symbol, sympy.S.Reals)
        )
        squared = CoreNode.node(
            node.type, radicand_node, from_sympy(sympy.expand(to_sympy(rhs) ** 2))
        )
        squared_values = sympy.solveset(
            _relational(node.type, to_sympy(radicand_node) - to_sympy(rhs) ** 2),
            symbol,
            sympy.S.Reals,
        )
        squared_answer = from_sympy(squared_values)
    except (SolveError, TypeError, ValueError, NotImplementedError):
        return None
    positive = CoreNode.node(T.GREATER_THAN_EQUAL, rhs, zero)
    negative = CoreNode.node(T.LESS_THAN, rhs, zero)
    positive_set = _relation_set(positive, var)
    if positive_set is None or squared_values is None:
        return None
    case_set = sympy.simplify(sympy.Intersection(squared_values, positive_set))
    try:
        case_interval = from_sympy(case_set)
        union_node = from_sympy(sympy.simplify(sympy.Union(case_set, sympy.S.EmptySet)))
    except SolveError:
        return None
    forbidden = CoreNode.node(T.LESS_THAN, radicand_node, zero)
    kept_relation = CoreNode.node(T.GREATER_THAN_EQUAL, radicand_node, zero)
    kept = _condition_solution(kept_relation, var)
    solved_forbidden = _condition_solution(forbidden, var)
    restriction, state = _restrictions_detail(
        node,
        var,
        find_key="rel_restrictions_root_base_neg",
        find_args=[x, radicand_node],
        forbidden=forbidden,
        solve_title="ineq_solve_short",
        solve_step=Step(forbidden, solved_forbidden, "ineq_linear", [x]),
        kept=kept,
    )
    cases = CoreNode.node(
        T.LIST,
        CoreNode.node(T.LIST, node, positive),
        CoreNode.node(T.LIST, node, negative),
    )
    square_detail = SolveResult()
    square_detail.add_group("compare_solve_ineq", Step(node, squared, "ineq_irrational_square"))
    solved_square = CoreNode.node(T.ELEMENT_OF, x, squared_answer)
    square_detail.add_group("ineq_solve_short", Step(squared, solved_square, "ineq_linear", [x]))
    square_detail.set_solution(solved_square)
    rows = [list(case.children) for case in cases.children]
    pages: list[Step] = []
    before = CoreNode.node(T.LIST, *[CoreNode.node(T.LIST, *terms) for terms in rows])
    rows[0][0] = solved_square
    after = CoreNode.node(T.LIST, *[CoreNode.node(T.LIST, *terms) for terms in rows])
    pages.append(Step(before, after, "ineq_linear", [x], subresult=square_detail))
    for index, position in ((0, 1), (1, 1)):
        before = CoreNode.node(T.LIST, *[CoreNode.node(T.LIST, *terms) for terms in rows])
        detail, solved = _abs_detail(rows[index][position], var)
        rows[index][position] = solved
        after = CoreNode.node(T.LIST, *[CoreNode.node(T.LIST, *terms) for terms in rows])
        pages.append(Step(before, after, "ineq_linear", [x], subresult=detail))
        if index == 0:
            empty = CoreNode.node(T.ELEMENT_OF, x, CoreNode.empty())
            before = CoreNode.node(T.LIST, *[CoreNode.node(T.LIST, *terms) for terms in rows])
            rows[1][0] = empty
            after = CoreNode.node(T.LIST, *[CoreNode.node(T.LIST, *terms) for terms in rows])
            pages.append(
                Step(
                    before,
                    after,
                    "rel_terminators_pos_zero_neg_false",
                    [zero, x],
                )
            )
    first = CoreNode.node(
        T.LIST,
        CoreNode.node(T.ELEMENT_OF, x, case_interval),
        CoreNode.node(T.LIST, *rows[1]),
    )
    second = CoreNode.node(
        T.LIST,
        CoreNode.node(T.ELEMENT_OF, x, case_interval),
        CoreNode.node(T.ELEMENT_OF, x, CoreNode.empty()),
    )
    with_restriction = CoreNode.node(T.LIST, union_node, kept)
    local = SolveResult()
    local.extend(restriction)
    local.add_group(
        "eq_separate_short",
        Step(state, cases, "ineq_separate_root", [_const(Fraction(2))]),
    )
    local.add_group(["rel_solve", "rel_state_false"], *pages)
    local.add_group(
        "intersection_plural",
        Step(pages[-1].right, first, "intersection"),
        Step(first, second, "intersection"),
    )
    local.add_group("union", Step(second, with_restriction, "union"))
    local.add_group("intersection", Step(with_restriction, answer, "rel_restrictions_intersect"))
    local.set_solution(answer)
    ctx.result.extend(local)
    return answer


def _irrational_inequality(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """Иррациональное неравенство: корни, множество решений — ``solveset``."""
    expression = _difference(node)
    if expression is None or not _has_radical(expression):
        return None
    if (shown := _irrational_rows(node, var, ctx)) is not None:
        return shown
    return _inequality_set(
        node,
        expression,
        "ineq_irr_solve",
        ctx,
        with_restrictions=not _has_range_restriction(ctx),
    )


def _abs_case(node: CoreNode, inner: CoreNode, k: Fraction) -> tuple[CoreNode, CoreNode]:
    """The two sign cases of ``|inner| ⋚ k`` in the app's order."""
    eq = CoreNode.node
    zero, bound = _const(Fraction(0)), _const(k)
    negative = (
        CoreNode(type=T.NEGATIVE, children=[inner])
        if inner.type is T.VARIABLE
        else CoreNode(type=T.NEGATIVE, children=[eq(T.BRACKET, inner)])
    )
    first = eq(T.SYSTEM, eq(node.type, inner, bound), eq(T.GREATER_THAN_EQUAL, inner, zero))
    second = eq(T.SYSTEM, eq(node.type, negative, bound), eq(T.LESS_THAN, inner, zero))
    return eq(T.LIST, first, second), negative


def _condition_solution(condition: CoreNode, var: str) -> CoreNode:
    """Solved form of a linear condition: ``−x < 2`` -> ``x > −2``."""
    left_side, right_side = (
        _simple_side(condition.children[0], var),
        _simple_side(condition.children[1], var),
    )
    if left_side is None or right_side is None or left_side[0] == 0:
        # ``x - √5 < 0``: the bound is an expression, not a constant.
        lhs, rhs = condition.children
        if (
            rhs.type is T.CONSTANT
            and (rhs.value or "") in ("0", "-0")
            and lhs.type is T.SUBTRACT
            and len(lhs.children) == 2
            and lhs.children[0].type is T.VARIABLE
            and lhs.children[0].value == var
        ):
            return CoreNode.node(condition.type, CoreNode.variable(var), lhs.children[1])
        return condition
    a, b = left_side
    final = condition.type if a > 0 else _FLIP[condition.type]
    return CoreNode.node(final, CoreNode.variable(var), _const((right_side[1] - b) / a))


def _relation_set(condition: CoreNode, var: str) -> sympy.Set | None:
    """Solution set of one relation, or ``None`` when sympy cannot express it."""
    expression = _difference(condition)
    if expression is None:
        return None
    try:
        return sympy.solveset(
            _relational(condition.type, expression), sympy.Symbol(var), sympy.S.Reals
        )
    except (TypeError, ValueError, NotImplementedError):
        return None


def _system_set(case: CoreNode, var: str) -> sympy.Set | None:
    """Intersection of the conditions of one system/list."""
    sets = [_relation_set(condition, var) for condition in case.children]
    if not sets or any(item is None for item in sets):
        return None
    result = sets[0]
    for item in sets[1:]:
        result = sympy.Intersection(result, item)
    try:
        return sympy.simplify(result)
    except (TypeError, ValueError):
        return None


def _odd_power_condition(condition: CoreNode, var: str) -> tuple[SolveResult, CoreNode] | None:
    """``xⁿ ⋚ c`` with odd ``n`` as one condition inside a sign-case card."""
    lhs, rhs = condition.children
    if rhs.type is not T.CONSTANT or (rhs.value or "") not in ("0", "-0"):
        return None
    terms = _sum_terms(lhs)
    if not terms:
        return None
    powers = [
        term
        for term in terms
        if term.type is T.POWER
        and len(term.children) == 2
        and term.children[0].type is T.VARIABLE
        and term.children[0].value == var
    ]
    if len(powers) != 1:
        return None
    exponent = _coefficient(powers[0].children[1])
    if exponent is None or exponent.denominator != 1:
        return None
    n = int(exponent)
    if n < 3 or n % 2 == 0:
        return None
    constants = [term for term in terms if term.type is T.CONSTANT]
    if len(constants) + 1 != len(terms):
        return None
    power, x, zero = powers[0], CoreNode.variable(var), _const(Fraction(0))
    detail = SolveResult()
    if not constants:
        marker = CoreNode.variable(
            {T.GREATER_THAN: ">0", T.LESS_THAN: "<0"}.get(condition.type, "0")
        )
        solved = CoreNode.node(condition.type, x, zero)
        detail.add_group(
            CoreRichText(type="set_base_arg", args=[marker]),
            Step(condition, solved, "ineq_pow_odd_zero", [marker]),
        )
        detail.set_solution(solved)
        return detail, solved
    constant = as_fraction(constants[0])
    moved = CoreNode.node(condition.type, power, _const(-constant))
    detail.add_group(
        "rel_move_right_const_msg",
        Step(condition, moved, "rel_move_right_const_ineq"),
    )
    radical = CoreNode.node(T.ROOT, _const(Fraction(n)), _const(-constant))
    rooted = CoreNode.node(
        condition.type, CoreNode.node(T.ROOT, _const(Fraction(n)), power), radical
    )
    reduced = CoreNode.node(condition.type, x, radical)
    value = sympy.real_root(sympy.Rational(-constant), n)
    root_detail = SolveResult()
    root_detail.add_group("compare_solve_ineq", Step(moved, rooted, "ineq_pow_root_var"))
    if value.is_Rational:
        solved = CoreNode.node(condition.type, x, _const(Fraction(int(value.p), int(value.q))))
        root_detail.add_group(
            ["reduce", "calculate_short"],
            Step(rooted, reduced, "root_reduce", [_const(Fraction(n))]),
            Step(reduced, solved, "root_cube"),
        )
    else:
        solved = reduced
        root_detail.add_group("reduce", Step(rooted, reduced, "root_reduce", [_const(Fraction(n))]))
    root_detail.set_solution(solved)
    detail.add_group(
        "compare_solve_ineq",
        Step(moved, solved, "ineq_pow_root_var", subresult=root_detail),
    )
    detail.set_solution(solved)
    return detail, solved


def _abs_detail(
    condition: CoreNode, var: str, *, compact: bool = False
) -> tuple[SolveResult, CoreNode]:
    """Detail screen for one condition; falls back to a single ``ineq_linear`` row."""
    odd = _odd_power_condition(condition, var)
    if odd is not None:
        return odd
    solved = _condition_solution(condition, var)
    detail = _condition_rows(condition, var, compact=compact)
    if detail is not None and detail.solution is not None:
        return detail, detail.solution
    fallback = SolveResult()
    fallback.add_group(
        CoreRichText(type="ineq_linear", args=[CoreNode.variable(var)]),
        Step(condition, solved, "ineq_linear", [CoreNode.variable(var)]),
    )
    fallback.set_solution(solved)
    return fallback, solved


def _abs_against_number(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """``|inner| ⋚ k`` for a linear ``inner`` and a positive ``k``: the rows the app shows.

    A bare ``|x|`` takes the verified compact card (the positive case is resolved inside
    the first intersection row); a shifted ``|x − 1|`` solves all four linear conditions
    first and then intersects the two systems. ``|x| < 0`` has no solutions at all.
    """
    left, right = node.children
    if not (
        node.type in (T.LESS_THAN, T.GREATER_THAN, T.LESS_THAN_EQUAL, T.GREATER_THAN_EQUAL)
        and left.type is T.ABS
        and right.type is T.CONSTANT
        and right.value is not None
        and right.value.isdigit()
    ):
        return None
    if int(right.value) == 0:
        if node.type not in (T.LESS_THAN, T.LESS_THAN_EQUAL):
            return None
        x, zero = CoreNode.variable(var), _const(Fraction(0))
        ctx.result.add_group(
            CoreRichText(type="rel_el_of_zero", args=[x]),
            Step(
                node,
                CoreNode.node(T.ELEMENT_OF, x, CoreNode.empty()),
                "rel_terminators_left_pos_zero_false",
                [zero, x],
            ),
        )
        return CoreNode.empty()
    if int(right.value) < 0:
        return None
    inner = left.children[0]
    sides = _simple_side(inner, var)
    if sides is None or sides[0] != 1:
        return None
    k = Fraction(int(right.value))
    if inner.type is not T.VARIABLE:
        return _abs_shifted_rows(node, inner, k, var, ctx)

    eq, x = CoreNode.node, CoreNode.variable(var)
    cases, _negative = _abs_case(node, inner, k)
    first_set = _system_set(cases.children[0], var)
    second_set = _system_set(cases.children[1], var)
    if first_set is None or second_set is None:
        return None
    try:
        positive_set = from_sympy(first_set)
        negative_set = from_sympy(second_set)
        answer = from_sympy(sympy.Union(first_set, second_set))
    except SolveError:
        return None
    positive = eq(T.ELEMENT_OF, x, positive_set)
    detail, solved = _abs_detail(cases.children[1].children[0], var)
    negative_solved = eq(T.SYSTEM, solved, cases.children[1].children[1])
    first = eq(T.LIST, positive, cases.children[1])
    second = eq(T.LIST, positive, negative_solved)
    third = eq(T.LIST, positive, eq(T.ELEMENT_OF, x, negative_set))
    local = SolveResult()
    local.add_group(
        "eq_separate_short",
        Step(node, cases, "ineq_separate_abs", [CoreNode.constant("2")]),
    )
    local.add_group(
        ["intersection", "rel_solve"],
        Step(cases, first, "intersection"),
        Step(first, second, "ineq_linear", [x], subresult=detail),
    )
    local.add_group("intersection", Step(second, third, "intersection"))
    local.add_group("union", Step(third, answer, "union"))
    local.set_solution(answer)
    ctx.result.extend(local)
    return answer


def _abs_shifted_rows(
    node: CoreNode, inner: CoreNode, k: Fraction, var: str, ctx: SolveContext
) -> CoreNode | None:
    """``|x − 1| ≤ 2``: all four conditions solved, then the systems intersected and united."""
    eq, x = CoreNode.node, CoreNode.variable(var)
    cases, _negative = _abs_case(node, inner, k)
    first_set = _system_set(cases.children[0], var)
    second_set = _system_set(cases.children[1], var)
    if first_set is None or second_set is None:
        return None
    try:
        first_interval = from_sympy(first_set)
        second_interval = from_sympy(second_set)
        answer = from_sympy(sympy.Union(first_set, second_set))
    except SolveError:
        return None
    state = [list(case.children) for case in cases.children]
    pages: list[Step] = []
    for index, case in enumerate(cases.children):
        for position, condition in enumerate(case.children):
            before = eq(T.LIST, *[eq(T.SYSTEM, *terms) for terms in state])
            detail, solved = _abs_detail(condition, var)
            state[index][position] = solved
            following = eq(T.LIST, *[eq(T.SYSTEM, *terms) for terms in state])
            pages.append(Step(before, following, "ineq_linear", [x], subresult=detail))
    first = eq(T.LIST, eq(T.ELEMENT_OF, x, first_interval), eq(T.SYSTEM, *state[1]))
    second = eq(
        T.LIST,
        eq(T.ELEMENT_OF, x, first_interval),
        eq(T.ELEMENT_OF, x, second_interval),
    )
    local = SolveResult()
    local.add_group(
        "eq_separate_short",
        Step(node, cases, "ineq_separate_abs", [CoreNode.constant("2")]),
    )
    local.add_group("ineq_solve_short_plural", *pages)
    local.add_group(
        "intersection_plural",
        Step(pages[-1].right, first, "intersection"),
        Step(first, second, "intersection"),
    )
    local.add_group("union", Step(second, answer, "union"))
    local.set_solution(answer)
    ctx.result.extend(local)
    return answer


def _even_power_over_constant(
    node: CoreNode, var: str, poly: dict[int, Fraction], ctx: SolveContext
) -> CoreNode | None:
    """``x² + k ⋚ 0`` with ``k > 0``: move ``k``, then an even power is never negative."""
    c = poly.get(0, Fraction(0))
    if set(poly) != {2, 0} or poly[2] != 1 or c <= 0:
        return None
    x, eq = CoreNode.variable(var), CoreNode.node
    zero = _const(Fraction(0))
    squared = eq(T.POWER, x, CoreNode.constant("2"))
    detail, moved = _zero_rhs_move(node, squared, c)
    ctx.result.add_group(
        "rel_move_right_const_msg",
        Step(node, moved, "rel_move_right_const_ineq", subresult=detail),
    )
    holds = node.type in (T.GREATER_THAN, T.GREATER_THAN_EQUAL)
    if holds:
        answer = _all_reals()
        ctx.result.add_group(
            CoreRichText(type="rel_el_of_r", args=[x]),
            Step(moved, answer, "rel_terminators_pow_all_sol", [x, zero]),
        )
        return answer
    ctx.result.add_group(
        CoreRichText(type="rel_el_of_zero", args=[x]),
        Step(
            moved,
            eq(T.ELEMENT_OF, x, CoreNode.empty()),
            "rel_terminators_pow_no_sol",
            [x, zero],
        ),
    )
    return CoreNode.empty()


def _sqrt_rows(moved: CoreNode, var: str, k: Fraction, ctx: SolveContext) -> CoreNode:
    """Take the square root of both sides: ``x² ⋚ k²`` -> ``|x| ⋚ k`` with its screen."""
    eq, x = CoreNode.node, CoreNode.variable(var)
    squared, number = moved.children
    rooted = eq(moved.type, eq(T.ROOT2, squared), eq(T.ROOT2, number))
    absolute_root = eq(moved.type, eq(T.ABS, x), eq(T.ROOT2, number))
    absolute = eq(moved.type, eq(T.ABS, x), _const(k))
    root = SolveResult()
    root.add_group("compare_solve_ineq", Step(moved, rooted, "ineq_pow_sqrt_root"))
    root.add_group(
        ["reduce", "calculate_short"],
        Step(rooted, absolute_root, "root_reduce", [_const(Fraction(2))]),
        Step(absolute_root, absolute, "root_square"),
    )
    root.set_solution(absolute)
    ctx.result.add_group(
        "compare_solve_ineq",
        Step(moved, absolute, "ineq_pow_sqrt_root", subresult=root),
    )
    return absolute


def _square_above_number(
    node: CoreNode, var: str, poly: dict[int, Fraction], ctx: SolveContext
) -> CoreNode | None:
    """``x^2 - k^2 ⋚ 0``: move the constant, take the root, then the cases."""
    c = poly.get(0, Fraction(0))
    if (
        node.type not in (T.GREATER_THAN, T.LESS_THAN, T.GREATER_THAN_EQUAL, T.LESS_THAN_EQUAL)
        or set(poly) != {2, 0}
        or poly[2] != 1
        or c >= 0
    ):
        return None
    k = sympy.sqrt(-sympy.Rational(c.numerator, c.denominator))
    if not (k.is_Integer and k > 0):
        return None
    eq, x = CoreNode.node, CoreNode.variable(var)
    squared = eq(T.POWER, x, CoreNode.constant("2"))
    detail, moved = _zero_rhs_move(node, squared, c)
    ctx.result.add_group(
        "rel_move_right_const_msg",
        Step(node, moved, "rel_move_right_const_ineq", subresult=detail),
    )
    absolute = _sqrt_rows(moved, var, Fraction(int(k)), ctx)
    return _abs_against_number(absolute, var, ctx)


def _abs_inequality(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """Неравенство с модулем: два случая, множество решений — ``solveset``."""
    if (shown := _abs_against_number(node, var, ctx)) is not None:
        return shown
    expression = _difference(node)
    if expression is None or not expression.has(sympy.Abs):
        return None
    symbol = sympy.Symbol(var)
    try:
        values = sympy.solveset(_relational(node.type, expression), symbol, sympy.S.Reals)
    except (TypeError, ValueError, NotImplementedError):
        return None
    try:
        answer = from_sympy(values)
    except SolveError:
        return None
    ctx.result.add(
        Step(left=node, right=answer, key="ineq_separate_abs", args=[CoreNode.constant("2")]),
        [_HEADER],
    )
    return answer


def _unwrap_node(node: CoreNode) -> CoreNode:
    """Убрать скобки/унарный плюс у показателя степени."""
    while node.type in (T.BRACKET, T.POSITIVE) and len(node.children) == 1:
        node = node.children[0]
    return node


def _integer_power(value: Fraction, base: Fraction) -> int | None:
    """Целый ``k`` с ``value == base^k`` или ``None`` (``base > 1``)."""
    if base <= 1:
        return None
    if value == 1:
        return 0
    power, exponent = Fraction(1), 0
    if value > 1:
        while power < value and exponent < 256:
            power *= base
            exponent += 1
        return exponent if power == value else None
    inverse, exponent = Fraction(1), 0
    while inverse > value and exponent < 256:
        inverse /= base
        exponent -= 1
    return exponent if inverse == value else None


def _exponential_rows(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """``a^f(x) ⋚ a^k``: одно основание, приравнять показатели, обычные строки неравенства."""
    lhs, rhs = node.children
    if lhs.type is not T.POWER or len(lhs.children) != 2:
        return None
    base_node, exponent_node = lhs.children
    try:
        base = number_of(base_node)
        value = number_of(rhs)
    except (SolveError, UndefinedError):
        return None
    if base <= 0 or base == 1 or value <= 0:
        return None
    factor = Fraction(1)
    canonical = base
    if base.denominator != 1:
        # ``(1/3)^x``: Решатель переписывает как ``3^{-x}`` (строка ``write_as_exp``)
        canonical, factor = 1 / base, Fraction(-1)
    if canonical.denominator != 1:
        return None
    exponent = _simple_side(_unwrap_node(exponent_node), var)
    if exponent is None or exponent[0] == 0:
        return None
    k = _integer_power(value, canonical)
    if k is None:
        return None
    canonical_node = _const(canonical)
    steps: list[Step] = []
    current = node
    shown_exponent = _unwrap_node(exponent_node)
    if factor == -1:
        shown_exponent = CoreNode.node(T.NEGATIVE, shown_exponent)
        rewritten = CoreNode.node(
            node.type, CoreNode.node(T.POWER, canonical_node, shown_exponent), rhs
        )
        steps.append(Step(current, rewritten, "write_as_exp", [canonical_node]))
        current = rewritten
    same_base = CoreNode.node(
        node.type,
        CoreNode.node(T.POWER, canonical_node, shown_exponent),
        CoreNode.node(T.POWER, canonical_node, _const(Fraction(k))),
    )
    steps.append(Step(current, same_base, "pow_to_same_base", [canonical_node]))
    ctx.result.add_group("write_as_exp_short", *steps)
    condition = CoreNode.node(node.type, shown_exponent, _const(Fraction(k)))
    ctx.result.add_group(
        "compare_exponents",
        Step(same_base, condition, "compare_exp_alg", [_const(Fraction(1))]),
    )
    left = condition.children[0]
    if left.type is T.NEGATIVE:
        # ``-x ⋚ 2``: The app shows one ``ineq_linear_neg`` row whose detail multiplies
        # both sides by -1 (no bracket around ``x``)
        detail = _condition_rows(condition, var)
        if detail is not None and detail.solution is not None:
            ctx.result.add_group(
                "rel_linear_neg_msg",
                Step(condition, detail.solution, "ineq_linear_neg", subresult=detail),
            )
        else:
            _ineq_rows(condition, condition.children[0], condition.children[1], var, ctx)
    else:
        _ineq_rows(condition, condition.children[0], condition.children[1], var, ctx)
    expression = _difference(node)
    if expression is None:
        return None
    try:
        final = from_sympy(
            sympy.solveset(_relational(node.type, expression), sympy.Symbol(var), sympy.S.Reals)
        )
    except (SolveError, TypeError, ValueError, NotImplementedError):
        return None
    return final


def _log_formula_args(node: CoreNode, base_node: CoreNode, bound: CoreNode) -> list[CoreNode]:
    """Template arguments of ``ineq_log_formula_*_xab_pow``: the general law.

    ``[0 < a < 1 | a > 1, log_a x ⋚ b, x ⋚ a^b]``.
    """
    a, x, b = (CoreNode.variable(name) for name in ("a", "x", "b"))
    try:
        base = number_of(base_node)
    except (SolveError, UndefinedError):
        base = Fraction(2)
    if base > 1:
        base_condition = CoreNode.node(T.GREATER_THAN, a, _const(Fraction(1)))
        power_type = node.type
    else:
        base_condition = CoreNode.node(
            T.LESS_THAN,
            CoreNode.node(T.LESS_THAN, _const(Fraction(0)), a),
            _const(Fraction(1)),
        )
        power_type = _FLIP[node.type]
    return [
        base_condition,
        CoreNode.node(node.type, CoreNode.node(T.LOG, x, a), b),
        CoreNode.node(power_type, x, CoreNode.node(T.POWER, a, b)),
    ]


def _power_detail(base_node: CoreNode, exponent: int, value: Fraction) -> SolveResult:
    """``2³ = (2·2)·2 = 8``: the two rows the app shows under ``pow``."""
    product = base_node
    for _ in range(exponent - 1):
        product = CoreNode.node(T.MULTIPLY, product, base_node)
    detail = SolveResult()
    detail.add_group(
        "write_as_mul_short",
        Step(
            CoreNode.node(T.POWER, base_node, _const(Fraction(exponent))),
            product,
            "pow_to_mul",
        ),
    )
    detail.add_group("multiply", Step(product, _const(value), "mul"))
    detail.set_solution(_const(value))
    return detail


def _range_condition(set_expr: sympy.Set, x: CoreNode) -> CoreNode:
    """Множество значений как условие: полубесконечный промежуток — неравенством."""
    if isinstance(set_expr, sympy.Interval):
        if set_expr.start is -sympy.oo:
            kind = T.LESS_THAN if set_expr.right_open else T.LESS_THAN_EQUAL
            return CoreNode.node(kind, x, from_sympy(set_expr.end))
        if set_expr.end is sympy.oo:
            kind = T.GREATER_THAN if set_expr.left_open else T.GREATER_THAN_EQUAL
            return CoreNode.node(kind, x, from_sympy(set_expr.start))
    return CoreNode.node(T.ELEMENT_OF, x, from_sympy(set_expr))


def _logarithm_rows(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """``log_a f(x) ⋚ c``: ОДЗ аргумента, формула, степень, обычные строки, пересечение.

    Основание ``a > 1`` сохраняет знак, ``0 < a < 1`` меняет его (``ineq_log_formula_lt_*``).
    """
    lhs, rhs = node.children
    if lhs.type not in (T.LOG, T.LOG10, T.LN):
        return None
    if lhs.type is T.LOG and len(lhs.children) == 2:
        argument_node, base_node = lhs.children
    elif lhs.type is T.LOG10:
        argument_node, base_node = lhs.children[0], _const(Fraction(10))
    else:
        argument_node, base_node = lhs.children[0], CoreNode.constant("e")
    try:
        base = number_of(base_node)
        bound = number_of(rhs)
    except (SolveError, UndefinedError):
        return None
    if base <= 0 or base == 1:
        return None
    symbol = sympy.Symbol(var)
    x, zero = CoreNode.variable(var), _const(Fraction(0))
    try:
        forbidden_set = sympy.solve_univariate_inequality(
            sympy.Le(to_sympy(argument_node), 0), symbol, relational=False
        )
    except (NotImplementedError, TypeError, ValueError):
        return None
    forbidden = CoreNode.node(T.LESS_THAN_EQUAL, argument_node, zero)
    kept = _range_condition(sympy.simplify(sympy.Complement(sympy.S.Reals, forbidden_set)), x)
    solve_step = None
    if argument_node.type is not T.VARIABLE or argument_node.value != var:
        # a compound argument needs the ordinary inequality row: ``x - 1 ≤ 0`` -> ``x ≤ 1``
        solve_step = Step(forbidden, _range_condition(forbidden_set, x), "ineq_linear", [x])
    restriction, state = _restrictions_detail(
        node,
        var,
        find_key="rel_restrictions_log_arg",
        find_args=[x, lhs, zero],
        forbidden=forbidden,
        solve_title="ineq_solve_short",
        solve_step=solve_step,
        kept=kept,
    )
    local = SolveResult()
    local.extend(restriction)
    flipped = node.type if base > 1 else _FLIP[node.type]
    key = "ineq_log_formula_gt_xab_pow" if base > 1 else "ineq_log_formula_lt_xab_pow"
    formula = CoreNode.node(flipped, argument_node, CoreNode.node(T.POWER, base_node, rhs))
    local.add_group(
        "compare_rewrite_ineq",
        Step(state, formula, key, _log_formula_args(node, base_node, rhs)),
    )
    value = Fraction(base) ** bound
    evaluated = CoreNode.node(flipped, argument_node, _const(Fraction(value)))
    if bound == 1:
        pow_key, pow_args, pow_page = "pow_with_one", [_const(Fraction(1))], None
        pow_title = "pow"
    elif bound < 0:
        pow_key, pow_args, pow_page = "pow_flip_one", [_const(Fraction(-1))], None
        pow_title = "pow_exp_msg"
    else:
        pow_key, pow_args = "pow", []
        pow_title = "evaluate"
        pow_page = (
            _power_detail(base_node, int(bound), Fraction(value))
            if bound.denominator == 1
            else None
        )
    local.add_group(pow_title, Step(formula, evaluated, pow_key, pow_args, subresult=pow_page))
    inner = SolveContext(result=local, variables=[var])
    solved = _ineq_rows(evaluated, evaluated.children[0], evaluated.children[1], var, inner)
    if solved is None:
        return None
    with_restriction = CoreNode.node(T.LIST, solved, kept)
    expression = _difference(node)
    if expression is None:
        return None
    try:
        answer = from_sympy(
            sympy.solveset(_relational(node.type, expression), symbol, sympy.S.Reals)
        )
    except (SolveError, TypeError, ValueError, NotImplementedError):
        return None
    local.add_group("intersection", Step(with_restriction, answer, "rel_restrictions_intersect"))
    local.set_solution(answer)
    ctx.result.extend(local)
    return answer


def _transcendental_inequality(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """Показательное или логарифмическое неравенство через ``solveset``."""
    expression = _difference(node)
    if expression is None:
        return None
    symbol = sympy.Symbol(var)
    if expression.has(sympy.log):
        if (shown := _logarithm_rows(node, var, ctx)) is not None:
            return shown
        key = "ineq_solve_short"
    elif _has_variable_power(expression, symbol):
        if (shown := _exponential_rows(node, var, ctx)) is not None:
            return shown
        key = "log_ineq_gt_one"
    else:
        return None
    return _inequality_set(node, expression, key, ctx)


def _trig_period(expression: sympy.Expr, symbol: sympy.Symbol) -> sympy.Expr | None:
    """Наименьший период выражения: ``periodicity`` или проверка по определению.

    ``sympy.periodicity`` не знает модуль от периода (``|sin x|`` с периодом
    ``π``), поэтому при отказе кандидаты ``π`` и ``2π`` проверяются прямым
    тождеством ``f(x+T) = f(x)``. Подходящий кандидат может быть и больше
    минимального периода -- решение от этого не неверно, лишь не сокращено.
    """
    try:
        period = sympy.periodicity(expression, symbol)
    except (TypeError, ValueError):
        period = None
    if period is not None and period.is_number and period > 0:
        return period
    for candidate in (sympy.pi, 2 * sympy.pi):
        try:
            if sympy.simplify(expression.subs(symbol, symbol + candidate) - expression) == 0:
                return candidate
        except (TypeError, ValueError):
            continue
    return None


def _trig_inequality(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """Периодическое тригонометрическое неравенство: ответ на одном периоде + ``kT``.

    ``sympy.solveset`` на ``Reals`` теряет периодичность (``sin x > 1/2``
    сужает до главного промежутка), поэтому множество решений берут на одном
    периоде ``[0; T]`` и продолжают сдвигом на ``T·k``: границы промежутков
    записываются как ``π/6 + 2πk``. Если ``solveset`` не берёт отношение на
    периоде (``|sin x| > 1/2``), применяют метод интервалов: нули уравнения
    режут период, знак проверяют в серединах дуг. Ключи -- ``trig_find_period``
    и ``trig_general_sol``, ответ -- промежуток или объединение.
    """
    if not looks_trigonometric(node):
        return None
    expression = _difference(node)
    if expression is None:
        return None
    plain = sympy.Symbol(var)
    symbol = sympy.Symbol(var, real=True)
    expression = expression.subs(plain, symbol)
    if expression.free_symbols != {symbol}:
        return None
    period = _trig_period(expression, symbol)
    if period is None:
        return None

    pieces = _period_pieces(node, expression, symbol, period)
    x = CoreNode.variable(var)
    if pieces is None:
        return None
    if not pieces:
        ctx.result.add(Step(left=node, right=None, key="rel_el_of_zero", args=[x]), [_HEADER])
        return CoreNode.empty()

    if any(start is sympy.S.NegativeInfinity for start, _, _, _ in pieces):
        answer = _all_reals()
        ctx.result.add(Step(left=node, right=answer, key="rel_el_of_r", args=[x]), [_HEADER])
        return answer
    if len(pieces) > 1 and pieces[0][0] == 0 and pieces[-1][1] == period:
        # Дуга через x = 0 -- один промежуток, как в учебнике: (−7π/6 + 2πk, π/6 + 2πk).
        first, last = pieces[0], pieces[-1]
        pieces = [(last[0] - period, first[1], last[2], first[3]), *pieces[1:-1]]

    def pieces_node(with_period: bool) -> CoreNode:
        intervals: list[CoreNode] = []
        for start_value, end_value, left_closed, right_closed in pieces:
            if with_period:
                start = _trig_series(start_value, period)
                end = _trig_series(end_value, period)
            else:
                start = from_sympy(start_value)
                end = from_sympy(end_value)
            if start_value == end_value:
                intervals.append(CoreNode.node(T.EQUALS, x, start))
                continue
            intervals.append(_interval(start, end, left_closed, right_closed))
        return intervals[0] if len(intervals) == 1 else _union(intervals)

    # One period first (its ends are the roots of the equation on the unit circle), then + Tk.
    one_period = pieces_node(False)
    answer = pieces_node(True)
    ctx.result.add(
        Step(
            left=node,
            right=one_period,
            key="trig_find_intervals_smpl",
            args=[x],
            subresult=_circle_roots(node, expression, symbol, period),
        ),
        [_HEADER],
    )
    ctx.result.add(
        Step(
            left=one_period,
            right=answer,
            key="trig_general_sol",
            args=[_trig_series(0, period)],
        ),
        [_HEADER],
    )
    return answer


def _circle_roots(
    node: CoreNode, expression: sympy.Expr, symbol: sympy.Symbol, period: sympy.Expr
) -> SolveResult | None:
    """«Подробнее»: the roots of the equation on [0; T) -- the ends of the arcs."""
    try:
        zeros = sympy.solveset(sympy.Eq(expression, 0), symbol, sympy.Interval.Ropen(0, period))
    except (TypeError, ValueError, NotImplementedError):
        return None
    if not isinstance(zeros, sympy.FiniteSet) or not zeros:
        return None
    x = CoreNode.variable(str(symbol))
    roots = [
        CoreNode.node(T.EQUALS, x, from_sympy(zero))
        for zero in sorted(zeros, key=lambda zero: float(sympy.N(zero)))
    ]
    window = _interval(CoreNode.constant("0"), from_sympy(period), True, False)
    found = roots[0] if len(roots) == 1 else CoreNode.node(T.LIST, *roots)
    page = SolveResult()
    page.add(
        Step(
            left=CoreNode.node(T.EQUALS, *node.children),
            right=found,
            key="trig_find_circle_intervals",
            args=[x, window],
        ),
        [CoreRichText(type="eq_solve_short")],
    )
    page.set_solution(found)
    return page


def _period_pieces(
    node: CoreNode, expression: sympy.Expr, symbol: sympy.Symbol, period: sympy.Expr
) -> list[tuple[sympy.Expr, sympy.Expr, bool, bool]] | None:
    """Куски решений на одном периоде ``(начало, конец, левый закрыт, правый закрыт)``.

    Сначала ``solveset`` на промежутке ``[0; T]``; его ответ переводят в
    куски. Если ``solveset`` сдаётся (``ConditionSet`` -- так бывает с
    ``|sin x|``), нули уравнения режут период на дуги, и каждая дуга
    проверяется подстановкой середины (метод интервалов). ``None`` -- случай
    не для модуля; пустой список -- решений нет.
    """
    try:
        base = sympy.solveset(
            _relational(node.type, expression), symbol, domain=sympy.Interval(0, period)
        )
    except (TypeError, ValueError, NotImplementedError):
        return None
    if base is sympy.S.EmptySet:
        return []
    if isinstance(base, sympy.Interval) and base.start == 0 and base.end == period:
        return [(sympy.S.NegativeInfinity, sympy.S.Infinity, False, False)]
    if not isinstance(base, sympy.ConditionSet):
        pieces: list[tuple[sympy.Expr, sympy.Expr, bool, bool]] = []
        for piece in base.args if isinstance(base, sympy.Union) else (base,):
            if isinstance(piece, sympy.FiniteSet):
                # sin x ≤ 0 holds at the lone point x = 0; sin x ≥ 1 only at π/2
                pieces += [(point, point, True, True) for point in piece.args]
                continue
            if not isinstance(piece, sympy.Interval):
                return None
            pieces.append((piece.start, piece.end, not piece.left_open, not piece.right_open))
        return sorted(pieces, key=lambda piece: float(sympy.N(piece[0])))

    return _chart_pieces(node, expression, symbol, period)


def _chart_pieces(
    node: CoreNode, expression: sympy.Expr, symbol: sympy.Symbol, period: sympy.Expr
) -> list[tuple[sympy.Expr, sympy.Expr, bool, bool]] | None:
    """Метод интервалов на периоде: нули режут окружность, знак в серединах дуг."""
    try:
        zeros_set = sympy.solveset(
            sympy.Eq(expression, 0), symbol, domain=sympy.Interval(0, period)
        )
    except (TypeError, ValueError, NotImplementedError):
        return None
    if not isinstance(zeros_set, sympy.FiniteSet):
        return None
    zeros = sorted({sympy.simplify(z) for z in zeros_set.args}, key=lambda z: float(sympy.N(z)))
    if any(z == period for z in zeros):
        # x = T совпадает с x = 0 на периодической окружности.
        zeros = [z for z in zeros if z != period]
    if not zeros:
        holds = _relation_holds_value(node, expression, symbol, period / 2)
        if holds is None:
            return None
        return [(sympy.S.NegativeInfinity, sympy.S.Infinity, False, False)] if holds else []

    closed = node.type in (T.LESS_THAN_EQUAL, T.GREATER_THAN_EQUAL)
    count = len(zeros)
    pieces: list[tuple[sympy.Expr, sympy.Expr, bool, bool]] = []
    for index in range(count):
        start = zeros[index]
        end = zeros[(index + 1) % count]
        end_wrapped = end if index + 1 < count else end + period
        middle = (start + end_wrapped) / 2
        holds = _relation_holds_value(node, expression, symbol, middle)
        if holds is None:
            return None
        if holds:
            pieces.append((start, end_wrapped, closed, closed))
    return pieces


def _relation_holds_value(
    node: CoreNode, expression: sympy.Expr, symbol: sympy.Symbol, value: sympy.Expr
) -> bool | None:
    """Верно ли отношение ``f ⋚ 0`` в точке; ``None``, если истина не вычисляется."""
    try:
        difference = sympy.simplify(expression.subs(symbol, value))
        resolved = sympy.simplify(_relational(node.type, difference))
    except (TypeError, ValueError):
        return None
    if resolved is sympy.true:
        return True
    if resolved is sympy.false:
        return False
    return None


def _difference(node: CoreNode) -> sympy.Expr | None:
    """Разность частей неравенства в sympy или ``None``."""
    lhs, rhs = node.children
    try:
        return sympy.together(to_sympy(lhs) - to_sympy(rhs))
    except SolveError:
        return None


def _inequality_set(
    node: CoreNode,
    expression: sympy.Expr,
    key: str,
    ctx: SolveContext,
    *,
    with_restrictions: bool = True,
) -> CoreNode | None:
    """Множество решений неравенства через ``sympy.solveset``.

    ``None`` -- sympy вернул множество, которое не переводится в узлы
    (например, ``ConditionSet`` для ``|sin x| > 1/2``): тогда путь не наш и
    вызывающий пробует следующий решатель.
    """
    symbol = sympy.Symbol(ctx.variables[0])
    try:
        values = sympy.solveset(_relational(node.type, expression), symbol, sympy.S.Reals)
    except (TypeError, ValueError, NotImplementedError):
        return None
    try:
        answer = from_sympy(values)
    except SolveError:
        return None
    if with_restrictions:
        add_restriction_steps(node, ctx.variables, ctx, expression)
    ctx.result.add(Step(left=node, right=answer, key=key), [_HEADER])
    return answer


def _has_radical(expression: sympy.Expr) -> bool:
    """Есть ли в выражении квадратный корень из выражения с буквой (√2 -- просто число)."""
    return any(
        isinstance(power, sympy.Pow)
        and power.exp == sympy.Rational(1, 2)
        and power.base.free_symbols
        for power in expression.atoms(sympy.Pow)
    )


def _has_variable_power(expression: sympy.Expr, symbol: sympy.Symbol) -> bool:
    """Есть ли степень с переменной в показателе (показательное выражение)."""
    return any(
        isinstance(power, sympy.Pow) and power.exp.has(symbol)
        for power in expression.atoms(sympy.Pow)
    )


def _relational(node_type: T, expression: sympy.Expr) -> sympy.Rel:
    """Отношение ``выражение ⋚ 0`` для решателя множеств sympy."""
    zero = sympy.Integer(0)
    if node_type is T.LESS_THAN:
        return sympy.Lt(expression, zero)
    if node_type is T.LESS_THAN_EQUAL:
        return sympy.Le(expression, zero)
    if node_type is T.GREATER_THAN:
        return sympy.Gt(expression, zero)
    if node_type is T.GREATER_THAN_EQUAL:
        return sympy.Ge(expression, zero)
    return sympy.Ne(expression, zero)


def _constant_inequality(node: CoreNode, poly: dict[int, Fraction], ctx: SolveContext) -> CoreNode:
    """Неравенство, где неизвестное сократилось: верно для всех или ни для кого."""
    value = poly.get(0, Fraction(0))
    x = CoreNode.variable(ctx.variables[0])
    if _holds(node.type, negative=value < 0, zero=value == 0):
        answer = _all_reals()
        ctx.result.add(Step(left=node, right=answer, key="rel_el_of_r", args=[x]), [_HEADER])
    else:
        answer = CoreNode.empty()
        ctx.result.add(Step(left=node, right=None, key="rel_el_of_zero", args=[x]), [_HEADER])
    return answer


def _polynomial_inequality(
    node: CoreNode, var: str, poly: dict[int, Fraction], ctx: SolveContext
) -> CoreNode | None:
    """Многочлен степени 3 и выше: разложить, найти корни, знаки на промежутках."""
    expression = _poly_expr(poly, var)
    symbol = sympy.Symbol(var)
    try:
        roots = sorted(sympy.real_roots(sympy.Poly(expression, symbol)), key=_sort_key)
        values = sympy.solveset(_relational(node.type, expression), symbol, sympy.S.Reals)
        try:
            answer = from_sympy(values)
        except SolveError:  # sympy gave up (ConditionSet): the sign chart on the roots is enough
            answer = _sign_chart_answer(node.type, expression, symbol, roots)
    except (TypeError, ValueError, NotImplementedError, SolveError, sympy.PolynomialError):
        return None
    zero = CoreNode.constant("0")
    factored = from_sympy(sympy.factor(expression))
    equation = CoreNode.node(T.EQUALS, factored, zero)
    points = sorted(set(roots), key=_sort_key)
    found = CoreNode.node(
        T.LIST, *[CoreNode.node(T.EQUALS, CoreNode.variable(var), from_sympy(r)) for r in points]
    )
    ctx.result.add(
        Step(left=from_sympy(expression), right=factored, key="factorise_call"), [_HEADER]
    )
    ctx.result.add(Step(left=equation, right=found, key="ineq_poly_roots"), [_HEADER])
    ctx.result.add(Step(left=found, right=answer, key="ineq_poly_sign_chart"), [_HEADER])
    return answer


def _sign_chart_answer(
    node_type: T, expression: sympy.Expr, symbol: sympy.Symbol, roots: list[sympy.Expr]
) -> CoreNode:
    """The solution set from the real roots and the sign of the polynomial between them."""
    points = sorted(set(roots), key=_sort_key)
    closed = node_type in (T.LESS_THAN_EQUAL, T.GREATER_THAN_EQUAL)
    below = node_type in (T.LESS_THAN, T.LESS_THAN_EQUAL)
    keys = [_sort_key(point) for point in points]
    probes = [keys[0] - 1.0] if keys else [0.0]
    probes += [(a + b) / 2 for a, b in itertools.pairwise(keys)]
    probes += [keys[-1] + 1.0] if keys else []
    holds = []
    for probe in probes:
        value = float(sympy.N(expression.subs(symbol, probe)))
        holds.append(value < 0 if below else value > 0)
    infinity: list[CoreNode | None] = [None, *[from_sympy(p) for p in points], None]
    pieces: list[list[object]] = []  # [start, end, left_closed, right_closed]
    for index, good in enumerate(holds):
        if not good:
            continue
        start, end = infinity[index], infinity[index + 1]
        left_closed = closed and start is not None
        right_closed = closed and end is not None
        adjacent = index > 0 and holds[index - 1]
        if pieces and adjacent and closed:
            pieces[-1][1], pieces[-1][3] = end, right_closed  # (a, p] + [p, b) -> (a, b)
            continue
        pieces.append([start, end, left_closed, right_closed])
    items: list[tuple[float, CoreNode]] = []
    for a, b, lc, rc in pieces:
        start = a if isinstance(a, CoreNode) else _neg_inf()
        end = b if isinstance(b, CoreNode) else _pos_inf()
        items.append(
            (
                _sort_key_node(a) if isinstance(a, CoreNode) else float("-inf"),
                _interval(start, end, bool(lc), bool(rc)),
            )
        )
    if closed:  # an isolated root satisfies "<= 0" / ">= 0" on its own: x = 1 for (x-1)^2 <= 0
        for index, point in enumerate(points):
            if not holds[index] and not holds[index + 1]:
                items.append((keys[index], CoreNode.node(T.SET, from_sympy(point))))
    if not items:
        return CoreNode.empty()
    nodes = [node for _, node in sorted(items, key=lambda item: item[0])]
    return _union(nodes)


def _sort_key_node(node: CoreNode) -> float:
    try:
        return float(sympy.N(to_sympy(node)))
    except (SolveError, TypeError, ValueError):
        return 0.0


_PRODUCT_CASES: dict[T, tuple[tuple[T, T], tuple[T, T]]] = {
    T.LESS_THAN: ((T.LESS_THAN, T.GREATER_THAN), (T.GREATER_THAN, T.LESS_THAN)),
    T.GREATER_THAN: ((T.GREATER_THAN, T.GREATER_THAN), (T.LESS_THAN, T.LESS_THAN)),
    T.LESS_THAN_EQUAL: (
        (T.LESS_THAN_EQUAL, T.GREATER_THAN_EQUAL),
        (T.GREATER_THAN_EQUAL, T.LESS_THAN_EQUAL),
    ),
    T.GREATER_THAN_EQUAL: (
        (T.GREATER_THAN_EQUAL, T.GREATER_THAN_EQUAL),
        (T.LESS_THAN_EQUAL, T.LESS_THAN_EQUAL),
    ),
}

_PRODUCT_SYMBOLS: dict[T, str] = {
    T.LESS_THAN: "<0",
    T.GREATER_THAN: ">0",
    T.LESS_THAN_EQUAL: "≤0",
    T.GREATER_THAN_EQUAL: "≥0",
}


def _factor_inequality(
    node: CoreNode,
    var: str,
    a: int,
    b: int,
    c: int,
    answer: CoreNode,
    ctx: SolveContext,
) -> CoreNode | None:
    """``x² − 5x + 6 ⋚ 0``: split the middle term, factor, split the signs, intersect, unite.

    The verified family is a monic quadratic with ``b < 0 < c`` and a perfect square
    discriminant; the rows are the order. ``None`` (without touching
    the result) for everything else.
    """
    if a != 1 or b >= 0 or c <= 0:
        return None
    d = b * b - 4 * c
    if d <= 0 or isqrt(d) ** 2 != d:
        return None
    root = isqrt(d)
    if (b + root) % 2 or (b - root) % 2:
        return None
    low, high = Fraction(-b - root, 2), Fraction(-b + root, 2)
    if low.denominator != 1 or high.denominator != 1:
        return None
    p, q = (b + root) // 2, (b - root) // 2  # p + q = b, p q = c, p > q
    if q == 0:
        return None
    num = quadratic_cards._num
    mono = quadratic_cards._mono
    poly = quadratic_cards._poly
    x, zero = CoreNode.variable(var), num(0)

    def rel(kind: T, left: CoreNode, right: CoreNode) -> CoreNode:
        return CoreNode.node(kind, left, right)

    bracket = poly([(1, 1), (-low, 0)], var)
    other = poly([(1, 1), (-high, 0)], var)
    wrapped = CoreNode.node(T.BRACKET, bracket)
    head = CoreNode.node(T.MULTIPLY, x, wrapped)
    split = rel(node.type, poly([(1, 2), (p, 1), (q, 1), (c, 0)], var), zero)
    headed = rel(
        node.type,
        CoreNode.node(T.ADD, CoreNode.node(T.SUBTRACT, head, mono(abs(q), 1, var)), num(c)),
        zero,
    )
    grouped = rel(
        node.type,
        CoreNode.node(T.SUBTRACT, head, CoreNode.node(T.MULTIPLY_IMPLICIT, num(abs(q)), wrapped)),
        zero,
    )
    product = rel(
        node.type, CoreNode.node(T.MULTIPLY, wrapped, CoreNode.node(T.BRACKET, other)), zero
    )
    split_cases = _product_cases(node, bracket, other, var)
    if split_cases is None:
        return None
    cases, intervals = split_cases

    local = SolveResult()
    local.add_group(
        "rewrite_expression",
        Step(
            node,
            split,
            "write_as_diff_fact",
            [CoreNode.node(T.MULTIPLY_IMPLICIT, num(b), x)],
        ),
    )
    local.add_group(
        "factorise_call_plural",
        Step(split, headed, "extract_arg", [x]),
        Step(headed, grouped, "extract_arg", [num(q)]),
    )
    local.add_group("factorise_call", Step(grouped, product, "extract_arg", [bracket]))
    _product_tail(node, var, cases, intervals, product, answer, local)
    ctx.result.extend(local)
    return answer


def _product_cases(
    node: CoreNode, bracket: CoreNode, other: CoreNode, var: str
) -> tuple[CoreNode, list[CoreNode]] | None:
    """Sign-case systems of a two-factor product inequality and their intervals."""
    pair = _PRODUCT_CASES.get(node.type)
    if pair is None:
        return None
    zero = _const(Fraction(0))

    def rel(kind: T, left: CoreNode, right: CoreNode) -> CoreNode:
        return CoreNode.node(kind, left, right)

    (first_one, first_two), (second_one, second_two) = pair
    cases = CoreNode.node(
        T.LIST,
        CoreNode.node(T.SYSTEM, rel(first_one, bracket, zero), rel(first_two, other, zero)),
        CoreNode.node(T.SYSTEM, rel(second_one, bracket, zero), rel(second_two, other, zero)),
    )
    sets = [_system_set(case, var) for case in cases.children]
    if any(item is None for item in sets):
        return None
    try:
        intervals = [from_sympy(item) for item in sets if item is not None]
    except SolveError:
        return None
    return cases, intervals


def _product_tail(
    node: CoreNode,
    var: str,
    cases: CoreNode,
    intervals: list[CoreNode],
    product: CoreNode,
    answer: CoreNode,
    local: SolveResult,
) -> None:
    """``ineq_product_p_two`` -> four conditions -> two intersections -> union."""
    x = CoreNode.variable(var)
    local.add_group(
        "eq_separate_short",
        Step(
            product,
            cases,
            "ineq_product_p_two",
            [
                CoreNode.variable(_PRODUCT_SYMBOLS[node.type]),
                cases.children[0],
                cases.children[1],
                product.children[0],
            ],
        ),
    )
    state = [list(case.children) for case in cases.children]
    pages: list[Step] = []
    for index, case in enumerate(cases.children):
        for position, condition in enumerate(case.children):
            before = CoreNode.node(T.LIST, *[CoreNode.node(T.SYSTEM, *terms) for terms in state])
            detail, solved = _abs_detail(condition, var)
            state[index][position] = solved
            following = CoreNode.node(T.LIST, *[CoreNode.node(T.SYSTEM, *terms) for terms in state])
            pages.append(Step(before, following, "ineq_linear", [x], subresult=detail))
    local.add_group("ineq_solve_short_plural", *pages)
    first = CoreNode.node(
        T.LIST,
        CoreNode.node(T.ELEMENT_OF, x, intervals[0]),
        CoreNode.node(T.SYSTEM, *state[1]),
    )
    second = CoreNode.node(
        T.LIST,
        CoreNode.node(T.ELEMENT_OF, x, intervals[0]),
        CoreNode.node(T.ELEMENT_OF, x, intervals[1]),
    )
    local.add_group(
        "intersection",
        Step(pages[-1].right, first, "intersection"),
        Step(first, second, "intersection"),
    )
    local.add_group("union", Step(second, answer, "union"))
    local.set_solution(answer)


def _substitute_inequality(
    node: CoreNode,
    var: str,
    a: Fraction,
    b: Fraction,
    c: Fraction,
    answer: CoreNode,
    ctx: SolveContext,
) -> CoreNode | None:
    """Irrational roots: substitute them into ``(x − x₁)(x − x₂)`` and solve the sign cases."""
    if a <= 0:
        return None
    expression = _poly_expr({2: a, 1: b, 0: c}, var)
    symbol = sympy.Symbol(var)
    try:
        roots = sorted(sympy.solve(sympy.Eq(expression, 0), symbol), key=_sort_key)
        high, low = from_sympy(roots[-1]), from_sympy(roots[0])
    except (SolveError, TypeError, ValueError, NotImplementedError, sympy.PolynomialError):
        return None
    if len(roots) != 2:
        return None
    x, zero = CoreNode.variable(var), _const(Fraction(0))
    bracket = CoreNode.node(T.SUBTRACT, x, high)
    other = CoreNode.node(T.SUBTRACT, x, low)
    wrapped_b = CoreNode.node(T.BRACKET, bracket)
    wrapped_o = CoreNode.node(T.BRACKET, other)
    if a == 1:
        product_node = CoreNode.node(T.MULTIPLY, wrapped_b, wrapped_o)
        card = "ineq_quad_substitute_expr_no_coeff"
    else:
        product_node = CoreNode.node(
            T.MULTIPLY,
            CoreNode.node(T.MULTIPLY_IMPLICIT, _const(a), wrapped_b),
            wrapped_o,
        )
        card = "ineq_quad_substitute_expr"
    product = CoreNode.node(node.type, product_node, zero)
    split_cases = _product_cases(node, bracket, other, var)
    if split_cases is None:
        return None
    cases, intervals = split_cases
    equation = CoreNode.node(T.EQUALS, from_sympy(expression), zero)
    roots_list = CoreNode.node(
        T.LIST,
        CoreNode.node(T.EQUALS, x, high),
        CoreNode.node(T.EQUALS, x, low),
    )
    x1, x2 = CoreNode.variable("x_1"), CoreNode.variable("x_2")
    symbolic_roots = CoreNode.node(T.LIST, x1, x2)
    template = CoreNode.node(
        T.MULTIPLY,
        CoreNode.node(T.BRACKET, CoreNode.node(T.SUBTRACT, x, x1)),
        CoreNode.node(T.BRACKET, CoreNode.node(T.SUBTRACT, x, x2)),
    )
    if a != 1:
        template = CoreNode.node(
            T.MULTIPLY,
            CoreNode.node(
                T.MULTIPLY_IMPLICIT,
                CoreNode.variable("a"),
                CoreNode.node(T.BRACKET, CoreNode.node(T.SUBTRACT, x, x1)),
            ),
            CoreNode.node(T.BRACKET, CoreNode.node(T.SUBTRACT, x, x2)),
        )
    local = SolveResult()
    local.add_group(
        "eq_quad_rel_solve",
        Step(node, equation, "ineq_quad_to_eq_quad", [symbolic_roots]),
    )
    local.add_group("eq_solve_short", Step(equation, roots_list, "eq_linear", [x]))
    local.add_group(
        CoreRichText(type="factorise_exp_short", args=[template]),
        Step(roots_list, product, card, [symbolic_roots, template]),
    )
    factorised = product
    if a != 1:
        factorised = CoreNode.node(node.type, CoreNode.node(T.MULTIPLY, wrapped_b, wrapped_o), zero)
        local.add_group(
            "divide_both_sides",
            Step(product, factorised, "ineq_linear_div", [_const(a)]),
        )
    _product_tail(node, var, cases, intervals, factorised, answer, local)
    local.set_solution(answer)
    ctx.result.extend(local)
    return answer


def _odd_power_inequality(
    node: CoreNode, var: str, poly: dict[int, Fraction], ctx: SolveContext
) -> CoreNode | None:
    """``xⁿ ⋚ c`` with odd ``n``: take the odd root of both sides."""
    powers = [degree for degree in poly if degree >= 3]
    if len(powers) != 1 or set(poly) - {powers[0], 0}:
        return None
    n = powers[0]
    if n % 2 == 0 or poly[n] != 1 or n != 3:
        return None
    constant = poly.get(0, Fraction(0))
    x, zero = CoreNode.variable(var), _const(Fraction(0))
    power = CoreNode.node(T.POWER, x, _const(Fraction(n)))
    if constant == 0:
        marker = CoreNode.variable({T.GREATER_THAN: ">0", T.LESS_THAN: "<0"}.get(node.type, "0"))
        local = SolveResult()
        local.add_group(
            CoreRichText(type="set_base_arg", args=[marker]),
            Step(
                node,
                CoreNode.node(node.type, x, zero),
                "ineq_pow_odd_zero",
                [marker],
            ),
        )
        answer = CoreNode.node(node.type, x, zero)
        local.set_solution(answer)
        ctx.result.extend(local)
        return answer
    move, moved = _zero_rhs_move(node, power, constant)
    ctx.result.add_group(
        "rel_move_right_const_msg",
        Step(node, moved, "rel_move_right_const_ineq", subresult=move),
    )
    radical = CoreNode.node(T.ROOT, _const(Fraction(n)), _const(-constant))
    rooted = CoreNode.node(node.type, CoreNode.node(T.ROOT, _const(Fraction(n)), power), radical)
    reduced = CoreNode.node(node.type, x, radical)
    root_detail = SolveResult()
    root_detail.add_group("compare_solve_ineq", Step(moved, rooted, "ineq_pow_root_var"))
    value = sympy.real_root(sympy.Rational(-constant), n)
    if value.is_Rational:
        final = CoreNode.node(node.type, x, _const(Fraction(int(value.p), int(value.q))))
        root_detail.add_group(
            ["reduce", "calculate_short"],
            Step(rooted, reduced, "root_reduce", [_const(Fraction(n))]),
            Step(reduced, final, "root_cube"),
        )
    else:
        final = reduced
        root_detail.add_group("reduce", Step(rooted, reduced, "root_reduce", [_const(Fraction(n))]))
    root_detail.set_solution(final)
    ctx.result.add_group(
        "compare_solve_ineq",
        Step(moved, final, "ineq_pow_root_var", subresult=root_detail),
    )
    return final


def _square_above_zero(
    node: CoreNode, var: str, poly: dict[int, Fraction], ctx: SolveContext
) -> CoreNode | None:
    """``x² ⋛ 0``: remove an explicit ``− 0``, then an even power is true except at 0."""
    if set(poly) != {2} or poly[2] != 1 or node.type not in (T.GREATER_THAN, T.GREATER_THAN_EQUAL):
        return None
    x, zero = CoreNode.variable(var), _const(Fraction(0))
    squared = CoreNode.node(T.POWER, x, CoreNode.constant("2"))
    current = node
    local = SolveResult()
    left = node.children[0]
    if (
        left.type is T.SUBTRACT
        and len(left.children) == 2
        and left.children[1].type is T.CONSTANT
        and (left.children[1].value or "") in ("0", "-0")
    ):
        cleaned = CoreNode.node(node.type, squared, zero)
        local.add_group(
            CoreRichText(type="remove_zero", args=[zero]),
            Step(node, cleaned, "add_with_zero", [zero]),
        )
        current = cleaned
    equality = CoreNode.node(T.EQUALS, squared, zero)
    local.add_group(
        CoreRichText(type="ineq_pow_even_true_except", args=[equality]),
        Step(
            current,
            equality,
            "rel_terminators_left_pos_zero_true_except",
            [zero, x, equality],
        ),
    )
    solved = CoreNode.node(T.EQUALS, x, zero)
    detail = SolveResult()
    detail.add_group(
        CoreRichText(type="log_set_base_zero", args=[zero]),
        Step(equality, solved, "eq_quad_exp_zero", [zero]),
    )
    detail.set_solution(solved)
    local.add_group("eq_solve_short", Step(equality, solved, "eq_linear", [x], subresult=detail))
    try:
        answer = from_sympy(sympy.Complement(sympy.S.Reals, sympy.FiniteSet(0)))
    except SolveError:
        return None
    local.add_group(
        CoreRichText(type="ineq_pow_even_true_except", args=[equality]),
        Step(solved, answer, "ineq_pow_diff", [x, equality]),
    )
    local.set_solution(answer)
    ctx.result.extend(local)
    return answer


def _quadratic_inequality(
    node: CoreNode, var: str, poly: dict[int, Fraction], ctx: SolveContext
) -> CoreNode:
    """Квадратное неравенство методом интервалов."""
    a = poly.get(2, Fraction(0))
    b = poly.get(1, Fraction(0))
    c = poly.get(0, Fraction(0))
    x = CoreNode.variable(var)
    discriminant = b * b - 4 * a * c
    below = node.type in (T.LESS_THAN, T.LESS_THAN_EQUAL)
    closed = node.type in (T.LESS_THAN_EQUAL, T.GREATER_THAN_EQUAL)

    if (shown := _square_above_zero(node, var, poly, ctx)) is not None:
        return shown
    if (shown := _even_power_over_constant(node, var, poly, ctx)) is not None:
        return shown
    expression = _poly_expr(poly, var)
    if discriminant < 0:
        # Знак постоянен: его задаёт старший коэффициент. Утверждение верно
        # для всех, когда требуемый знак совпадает с фактическим.
        positive = a > 0
        true_for_all = positive != below
        key = ("ineq_quad_lead_pos_" if positive else "ineq_quad_lead_neg_") + (
            "t" if true_for_all else "f"
        )
        answer = _all_reals() if true_for_all else CoreNode.empty()
        local = SolveResult()
        equation = CoreNode.node(T.EQUALS, from_sympy(expression), CoreNode.constant("0"))
        no_roots = CoreNode.node(T.ELEMENT_NOT_OF, x, CoreNode.variable("ℝ"))
        pair = CoreNode.node(T.LIST, CoreNode.variable("x_1"), CoreNode.variable("x_2"))
        local.add_group(
            "eq_quad_rel_solve",
            Step(node, equation, "ineq_quad_to_eq_quad", [pair]),
        )
        local.add_group("eq_solve_short", Step(equation, no_roots, "eq_linear", [x]))
        a_var, b_var, c_var = (CoreNode.variable(name) for name in ("a", "b", "c"))
        standard = CoreNode.node(
            T.ADD,
            CoreNode.node(
                T.ADD,
                CoreNode.node(
                    T.MULTIPLY_IMPLICIT, a_var, CoreNode.node(T.POWER, x, _const(Fraction(2)))
                ),
                CoreNode.node(T.MULTIPLY_IMPLICIT, b_var, x),
            ),
            c_var,
        )
        template = CoreNode.node(T.EQUALS, standard, _const(Fraction(0)))
        state = CoreNode.node(T.LIST, node, CoreNode.node(T.EQUALS, a_var, _const(a)))
        local.add_group(
            "determine_leading_coefficient",
            Step(no_roots, state, "ineq_quad_find_a", [a_var, template]),
        )
        final = answer if true_for_all else CoreNode.node(T.ELEMENT_OF, x, CoreNode.empty())
        local.add_group(
            CoreRichText(type="rel_el_of_r" if true_for_all else "rel_el_of_zero", args=[x]),
            Step(state, final, key, [x, a_var]),
        )
        local.set_solution(answer)
        ctx.result.extend(local)
        return answer

    symbol = sympy.Symbol(var)
    roots = sorted(sympy.solve(sympy.Eq(expression, 0), symbol), key=_sort_key)
    if (shown := _square_above_number(node, var, poly, ctx)) is not None:
        return shown
    inside = (a > 0) == below
    answer = _interval_answer(roots[0], roots[-1], inside=inside, closed=closed)
    if {a.denominator, b.denominator, c.denominator} == {1} and (
        shown := _factor_inequality(node, var, int(a), int(b), int(c), answer, ctx)
    ) is not None:
        return shown
    square_discriminant = (
        discriminant.denominator == 1
        and isqrt(discriminant.numerator) ** 2 == discriminant.numerator
    )
    if (
        not square_discriminant
        and (shown := _substitute_inequality(node, var, a, b, c, answer, ctx)) is not None
    ):
        return shown
    right = CoreNode.node(T.EQUALS, from_sympy(expression), CoreNode.constant("0"))
    ctx.result.add(Step(left=node, right=right, key="ineq_quad_to_eq_quad", args=[x]), [_HEADER])
    return answer


def _interval_answer(lo: sympy.Expr, hi: sympy.Expr, *, inside: bool, closed: bool) -> CoreNode:
    """Ответ-промежуток по корням ``lo ≤ hi``."""
    low, high = from_sympy(lo), from_sympy(hi)
    if _is_zero(lo - hi):
        if inside and closed:
            return _interval(low, high, True, True)  # точка [r, r]
        if inside:
            return CoreNode.empty()
        if closed:
            return _all_reals()
        return _union(
            [
                _interval(_neg_inf(), low, False, False),
                _interval(high, _pos_inf(), False, False),
            ]
        )
    if inside:
        return _interval(low, high, closed, closed)
    return _union(
        [
            _interval(_neg_inf(), low, False, closed),
            _interval(high, _pos_inf(), closed, False),
        ]
    )


def _holds(node_type: T, *, negative: bool, zero: bool) -> bool:
    """Верно ли отношение для выражения с известным знаком."""
    if node_type is T.LESS_THAN:
        return negative
    if node_type is T.LESS_THAN_EQUAL:
        return negative or zero
    if node_type is T.GREATER_THAN:
        return not negative and not zero
    if node_type is T.GREATER_THAN_EQUAL:
        return not negative
    return not zero


def _interval(start: CoreNode, end: CoreNode, left_closed: bool, right_closed: bool) -> CoreNode:
    """Узел промежутка по открытости краёв."""
    node_type = {
        (True, True): T.CLOSED_CLOSED_INTERVAL,
        (True, False): T.CLOSED_OPEN_INTERVAL,
        (False, True): T.OPEN_CLOSED_INTERVAL,
        (False, False): T.OPEN_OPEN_INTERVAL,
    }[(left_closed, right_closed)]
    return CoreNode.node(node_type, start, end)


def _all_reals() -> CoreNode:
    """Вся числовая прямая как промежуток ``(-∞, +∞)``."""
    return _interval(_neg_inf(), _pos_inf(), False, False)


def _neg_inf() -> CoreNode:
    return CoreNode.node(T.NEGATIVE, CoreNode.constant("∞"))


def _pos_inf() -> CoreNode:
    return CoreNode.constant("∞")


def _union(nodes: list[CoreNode]) -> CoreNode:
    if len(nodes) == 1:
        return nodes[0]
    return CoreNode.node(T.UNION, *nodes)


def _is_zero(expression: sympy.Expr) -> bool:
    result = sympy.simplify(expression) == 0
    return result is True or result is sympy.true


def _sort_key(root: sympy.Expr) -> float:
    try:
        return float(sympy.N(root))
    except (TypeError, ValueError):
        return 0.0


def _positive_quotient(node: CoreNode, var: str) -> tuple[CoreNode, str] | None:
    """``positive / denominator ⋚ 0``: the sign is the denominator's."""
    lhs, rhs = node.children
    if (
        lhs.type is not T.FRACTION
        or len(lhs.children) != 2
        or rhs.type is not T.CONSTANT
        or (rhs.value or "") not in ("0", "-0")
    ):
        return None
    numerator, denominator = lhs.children
    value = _coefficient(numerator)
    if value is None or value <= 0 or _simple_side(denominator, var) is None:
        return None
    if node.type not in (T.GREATER_THAN, T.GREATER_THAN_EQUAL):
        return None
    key = "ineq_quotient_pos_num_gt" if node.type is T.GREATER_THAN else "ineq_quotient_pos_num_gte"
    return CoreNode.node(node.type, denominator, _const(Fraction(0))), key


def inequality_on_interval(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Решить неравенство на отрезке методом интервалов (в т.ч. тригонометрическое).

    Аргументы — границы отрезка. Выражение ``f = lhs − rhs`` разбивается
    точками нулей и разрывов; на каждом промежутке проверяется знак ``f``;
    подходящие промежутки объединяются, концы включаются по нестрогому
    отношению. Ответ — промежуток или объединение.
    """
    ctx.require(node.type in _RELATIONS, "неравенство: знак отношения")
    ctx.require(len(args) == 2, "нужны границы отрезка")
    ctx.require(len(ctx.variables) == 1, "неравенство на отрезке: одна неизвестная")
    symbol = sympy.Symbol(ctx.variables[0])
    shortcut = _positive_quotient(node, ctx.variables[0])
    if shortcut is not None:
        transformed, key = shortcut
        marker = CoreNode.variable(">0" if node.type is T.GREATER_THAN else "≥0")
        ctx.result.add(
            Step(node, transformed, key, [marker]),
            [CoreRichText(type="ineq_quotionet_cpp_short", args=[marker])],
        )
        node = transformed
    lower, upper = to_sympy(args[0]), to_sympy(args[1])
    if lower > upper:
        lower, upper = upper, lower
    if lower.is_real is not True or upper.is_real is not True:
        raise SolveError("границы отрезка должны быть числами")

    expression = sympy.together(to_sympy(node.children[0]) - to_sympy(node.children[1]))
    singular = _real_points(sympy.singularities(expression, symbol), lower, upper)
    roots = [
        root
        for root in _real_points(sympy.solve(sympy.Eq(expression, 0), symbol), lower, upper)
        if not any(sympy.simplify(root - point) == 0 for point in singular)
    ]
    critical = sorted({*singular, *roots}, key=_sort_key)
    boundaries = [lower, *critical, upper]

    atoms: list[sympy.Set] = []
    for start, end in itertools.pairwise(boundaries):
        if _relation_holds(node.type, expression.subs(symbol, (start + end) / 2)):
            left_closed = _relation_holds(node.type, expression.subs(symbol, start))
            right_closed = _relation_holds(node.type, expression.subs(symbol, end))
            atoms.append(
                sympy.Interval(start, end, left_open=not left_closed, right_open=not right_closed)
            )
    for point in critical:
        if _relation_holds(node.type, expression.subs(symbol, point)):
            atoms.append(sympy.Interval(point, point))

    combined = sympy.simplify(sympy.Union(*atoms)) if atoms else sympy.EmptySet
    answer = from_sympy(combined)
    ctx.result.add(Step(left=node, right=answer, key="ineq_solve_short"), [_HEADER])
    return answer


def _real_points(values: object, lower: sympy.Expr, upper: sympy.Expr) -> list[sympy.Expr]:
    """Действительные точки из набора/списка внутри ``(lower, upper)``."""
    if isinstance(values, (sympy.FiniteSet, list, tuple, set)):
        candidates = list(values)
    else:
        return []
    result: list[sympy.Expr] = []
    for point in candidates:
        try:
            if point.is_real is False:
                continue
            value = float(sympy.N(point))
        except (TypeError, ValueError):
            continue
        if float(sympy.N(lower)) < value < float(sympy.N(upper)):
            result.append(point)
    return result


def _relation_holds(node_type: T, value: sympy.Expr) -> bool:
    """Верно ли строгое/нестрогое отношение для значения выражения."""
    try:
        number = float(sympy.N(value))
    except (TypeError, ValueError):
        return False
    if node_type is T.LESS_THAN:
        return number < 0
    if node_type is T.LESS_THAN_EQUAL:
        return number <= 0
    if node_type is T.GREATER_THAN:
        return number > 0
    if node_type is T.GREATER_THAN_EQUAL:
        return number >= 0
    if node_type is T.EQUALS:
        return number == 0
    return number != 0


__all__ = [
    "inequality_on_interval",
    "solve_inequality",
]
