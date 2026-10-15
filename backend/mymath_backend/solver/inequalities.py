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

from fractions import Fraction

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .arithmetic import format_number
from .base import SolveContext, SolveError, Step, solver_for
from .equations import _poly_expr, poly_of
from .sympy_bridge import from_sympy, to_sympy

_HEADER = CoreRichText(type="ineq_solve_short")

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


@solver_for(*_RELATIONS)
def solve_inequality(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Решить линейное неравенство с одним неизвестным."""
    ctx.require(len(node.children) == 2, "неравенство связывает две части")
    ctx.require(len(ctx.variables) == 1, "поддерживается одно неизвестное")
    var = ctx.variables[0]
    lhs, rhs = node.children

    try:
        poly = poly_of(lhs, var)
        for degree, coeff in poly_of(rhs, var).items():
            poly[degree] = poly.get(degree, Fraction(0)) - coeff
            if poly[degree] == 0:
                del poly[degree]
    except SolveError:
        for solver in (
            _rational_inequality,
            _irrational_inequality,
            _transcendental_inequality,
        ):
            answer = solver(node, var, ctx)
            if answer is not None:
                return answer
        raise

    degree = max(poly) if poly else 0
    if degree == 0:
        return _constant_inequality(node, poly, ctx)
    if degree == 2:
        return _quadratic_inequality(node, var, poly, ctx)
    ctx.require(degree == 1, "поддерживаются линейные и квадратные неравенства")

    a = poly[1]
    b = poly.get(0, Fraction(0))
    value = -b / a
    # При делении на отрицательное число знак неравенства меняется.
    final_type = node.type if a > 0 else _FLIP[node.type]

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


_QUOTIENT_KEY: dict[T, str] = {
    T.LESS_THAN: "ineq_quotient_lt",
    T.LESS_THAN_EQUAL: "ineq_quotient_lte",
    T.GREATER_THAN: "ineq_quotient_gt",
    T.GREATER_THAN_EQUAL: "ineq_quotient_gte",
}


def _rational_inequality(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """Решить неравенство с неизвестным в знаменателе.

    Множество решений даёт ``sympy.solveset`` на числовой прямой; ответ
    переводится в промежутки/объединение. ``None`` — знаменатель не зависит
    от неизвестного (не рациональное) или отношение не поддерживается.
    """
    lhs, rhs = node.children
    try:
        expression = sympy.together(to_sympy(lhs) - to_sympy(rhs))
        _, denominator = sympy.fraction(expression)
    except SolveError:
        return None
    if not denominator.has(sympy.Symbol(var)):
        return None
    key = _QUOTIENT_KEY.get(node.type)
    if key is None:
        return None

    symbol = sympy.Symbol(var)
    try:
        values = sympy.solveset(_relational(node.type, expression), symbol, sympy.S.Reals)
    except (TypeError, ValueError, NotImplementedError):
        return None

    answer = from_sympy(values)
    ctx.result.add(Step(left=node, right=answer, key=key), [_HEADER])
    return answer


def _irrational_inequality(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """Иррациональное неравенство: корни, множество решений — ``solveset``."""
    expression = _difference(node)
    if expression is None or not _has_radical(expression):
        return None
    return _inequality_set(node, expression, "ineq_irr_solve", ctx)


def _transcendental_inequality(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """Показательное или логарифмическое неравенство через ``solveset``."""
    expression = _difference(node)
    if expression is None:
        return None
    symbol = sympy.Symbol(var)
    if expression.has(sympy.log):
        key = "ineq_solve_short"
    elif _has_variable_power(expression, symbol):
        key = "log_ineq_gt_one"
    else:
        return None
    return _inequality_set(node, expression, key, ctx)


def _difference(node: CoreNode) -> sympy.Expr | None:
    """Разность частей неравенства в sympy или ``None``."""
    lhs, rhs = node.children
    try:
        return sympy.together(to_sympy(lhs) - to_sympy(rhs))
    except SolveError:
        return None


def _inequality_set(
    node: CoreNode, expression: sympy.Expr, key: str, ctx: SolveContext
) -> CoreNode | None:
    """Множество решений неравенства через ``sympy.solveset``."""
    symbol = sympy.Symbol(ctx.variables[0])
    try:
        values = sympy.solveset(_relational(node.type, expression), symbol, sympy.S.Reals)
    except (TypeError, ValueError, NotImplementedError):
        return None
    answer = from_sympy(values)
    ctx.result.add(Step(left=node, right=answer, key=key), [_HEADER])
    return answer


def _has_radical(expression: sympy.Expr) -> bool:
    """Есть ли в выражении квадратный корень."""
    return any(
        isinstance(power, sympy.Pow) and power.exp == sympy.Rational(1, 2)
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

    if discriminant < 0:
        # Знак постоянен: его задаёт старший коэффициент. Утверждение верно
        # для всех, когда требуемый знак совпадает с фактическим.
        positive = a > 0
        true_for_all = positive != below
        key = ("ineq_quad_lead_pos_" if positive else "ineq_quad_lead_neg_") + (
            "t" if true_for_all else "f"
        )
        answer = _all_reals() if true_for_all else CoreNode.empty()
        ctx.result.add(
            Step(left=node, right=answer if true_for_all else None, key=key, args=[x, _const(a)]),
            [_HEADER],
        )
        return answer

    expression = _poly_expr(poly, var)
    symbol = sympy.Symbol(var)
    roots = sorted(sympy.solve(sympy.Eq(expression, 0), symbol), key=_sort_key)
    right = CoreNode.node(T.EQUALS, from_sympy(expression), CoreNode.constant("0"))
    ctx.result.add(Step(left=node, right=right, key="ineq_quad_to_eq_quad", args=[x]), [_HEADER])

    inside = (a > 0) == below
    return _interval_answer(roots[0], roots[-1], inside=inside, closed=closed)


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


__all__ = [
    "solve_inequality",
]
