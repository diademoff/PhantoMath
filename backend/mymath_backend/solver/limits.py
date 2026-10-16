"""Пределы функций.

Модуль зарегистрирован на ``LIMIT``, ``LIMIT_LEFT`` и ``LIMIT_RIGHT``.
Дети: точка и выражение (``[to, expr]``). Предел считает sympy, поэтому
работают пределы в конечной точке, на бесконечности и односторонние,
включая раскрытие неопределённостей.

Результат переводится обратно в ``CoreNode`` мостом; ``∞`` даёт константу
«∞». Если предел не существует или не вычисляется — :class:`SolveError`.

Шаг один — ``limit_solve``.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step, solver_for
from .sympy_bridge import from_sympy, to_sympy

_LIMITS = (T.LIMIT, T.LIMIT_LEFT, T.LIMIT_RIGHT)

# Направление подхода: слева «-», справа и двусторонний «+».
_DIRECTION: dict[T, str] = {
    T.LIMIT: "+",
    T.LIMIT_LEFT: "-",
    T.LIMIT_RIGHT: "+",
}


def _two_sided(expression: sympy.Expr, symbol: sympy.Symbol, point: sympy.Expr) -> sympy.Expr:
    """Двусторонний предел в конечной точке: стороны обязаны совпасть.

    Раньше двусторонний предел считался как правосторонний (``dir="+"``),
    поэтому ``1/x`` при ``x → 0`` давал ``∞`` вместо «не существует».
    """
    # Вызывается только для T.LIMIT в конечной точке (см. solve_limit).
    try:
        left = sympy.limit(expression, symbol, point, "-")
        right = sympy.limit(expression, symbol, point, "+")
    except (TypeError, ValueError, NotImplementedError):
        raise SolveError("предел не существует или не вычисляется") from None
    if left != right:
        raise SolveError("предел не существует или не вычисляется")
    return right


@solver_for(*_LIMITS)
def solve_limit(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить предел через sympy."""
    ctx.require(len(node.children) == 2, "предел задаётся точкой и выражением")
    ctx.require(len(ctx.variables) <= 1, "поддерживается одно неизвестное")
    var = ctx.variables[0] if ctx.variables else "x"
    point, expression = node.children
    symbol = sympy.Symbol(var)
    point_value = to_sympy(point)
    expression_value = to_sympy(expression)

    if node.type is T.LIMIT and point_value not in (sympy.oo, -sympy.oo):
        value = _two_sided(expression_value, symbol, point_value)
    else:
        value = sympy.limit(expression_value, symbol, point_value, _DIRECTION[node.type])
    if not isinstance(value, sympy.Expr) or value is sympy.nan or value.has(sympy.Limit):
        raise SolveError("предел не существует или не вычисляется")

    classification = _classification(expression_value, symbol, point_value, value, node.type, var)
    if classification is not None:
        key, classification_args = classification
        ctx.result.add(Step(left=node, right=None, key=key, args=classification_args))

    try:
        result = from_sympy(sympy.simplify(value))
    except SolveError as err:
        # Неопределённая форма вроде AccumBounds: предела нет.
        raise SolveError("предел не существует или не вычисляется") from err
    ctx.result.add(Step(left=node, right=result, key="limit_solve"))
    return result


def _classification(
    expression: sympy.Expr,
    symbol: sympy.Symbol,
    point: sympy.Expr,
    value: sympy.Expr,
    node_type: T,
    variable: str,
) -> tuple[str, list[CoreNode]] | None:
    """Шаг с видом предела (константа, подстановка, многочлен, односторонний, Лопиталь)."""
    if not expression.has(symbol):
        return "limit_solve_const", []
    if _indeterminate(expression, symbol, point):
        return "limit_lhopital_long", []
    if node_type in (T.LIMIT_LEFT, T.LIMIT_RIGHT) and value.is_finite is True:
        key = "limit_common_left" if node_type is T.LIMIT_LEFT else "limit_common_right"
        return key, [
            from_sympy(expression),
            from_sympy(value),
            CoreNode.variable(variable),
            from_sympy(point),
        ]
    if point not in (sympy.oo, -sympy.oo):
        substituted = expression.subs(symbol, point)
        if substituted.is_finite is True:
            return "limit_solve_insert_value", [from_sympy(point)]
        return None
    if _is_polynomial(expression, symbol):
        return _poly_key(expression, symbol, point, value)
    return None


def _poly_key(
    expression: sympy.Expr, symbol: sympy.Symbol, point: sympy.Expr, value: sympy.Expr
) -> tuple[str, list[CoreNode]]:
    """Ключ предела многочлена на бесконечности (степень и старший коэффициент)."""
    polynomial = sympy.Poly(expression, symbol)
    leading = polynomial.LC()
    degree = polynomial.degree()
    if point is sympy.oo:
        key = "limit_poly_pos_inf_pos_lead" if leading > 0 else "limit_poly_pos_inf_neg_lead"
    else:
        even = degree % 2 == 0
        if leading > 0:
            key = "limit_poly_neg_inf_pos_lead_even" if even else "limit_poly_neg_inf_pos_lead_odd"
        else:
            key = "limit_poly_neg_inf_neg_lead_even" if even else "limit_poly_neg_inf_neg_lead_odd"
    return key, [from_sympy(point), from_sympy(value)]


def _is_polynomial(expression: sympy.Expr, symbol: sympy.Symbol) -> bool:
    """Многочлен ли выражение по переменной."""
    try:
        sympy.Poly(expression, symbol)
    except sympy.PolynomialError:
        return False
    return True


def _indeterminate(expression: sympy.Expr, symbol: sympy.Symbol, point: sympy.Expr) -> bool:
    """Есть ли неопределённость ``0/0`` или ``∞/∞`` (применимо правило Лопиталя)."""
    numerator, denominator = sympy.fraction(sympy.together(expression))
    if denominator == 1 or not denominator.has(symbol):
        return False
    try:
        top = sympy.limit(numerator, symbol, point)
        bottom = sympy.limit(denominator, symbol, point)
    except (TypeError, ValueError, NotImplementedError):
        return False
    zero_over_zero = top == 0 and bottom == 0
    infinity_over_infinity = top in (sympy.oo, -sympy.oo) and bottom in (sympy.oo, -sympy.oo)
    return bool(zero_over_zero or infinity_over_infinity)


__all__ = [
    "solve_limit",
]
