"""Линейные неравенства.

Модуль зарегистрирован на знаки отношения ``<``, ``≤``, ``>``, ``≥``, ``≠``.
Неравенство приводится к виду ``a·x + b ⋚ 0`` (через ``lhs - rhs``), затем
неизвестное выражается:

* при ``a > 0`` знак отношения сохраняется;
* при ``a < 0`` знак меняется на противоположный (``< ↔ >``, ``≤ ↔ ≥``).

Ответ — то же неравенство с ``x`` слева: ``x < 2``. Шаги: ``move`` для
переноса свободного члена и ``ineq_linear_div`` / ``ineq_linear_div_neg`` для
деления на коэффициент.

Поддерживаются только линейные неравенства; квадратные, дробные и системы
неравенств — следующие модули.
"""

from __future__ import annotations

from fractions import Fraction

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .arithmetic import format_number
from .base import SolveContext, Step, solver_for
from .equations import poly_of

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

    poly = poly_of(lhs, var)
    for degree, coeff in poly_of(rhs, var).items():
        poly[degree] = poly.get(degree, Fraction(0)) - coeff
        if poly[degree] == 0:
            del poly[degree]

    degree = max(poly) if poly else 0
    ctx.require(degree == 1, "поддерживаются линейные неравенства")

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


__all__ = [
    "solve_inequality",
]
