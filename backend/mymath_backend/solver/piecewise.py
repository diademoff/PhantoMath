"""Кусочно-заданные функции (команда ``piecewise_value``).

Узел ``PIECEWISE_DEFINITION`` хранит пары «выражение, условие»:
``[expr1, cond1, expr2, cond2, …]``. Условие — отношение (``<``, ``≤``, ``>``,
``≥``, ``=``, ``≠``). Значение функции в точке — выражение первой пары, чьё
условие истинно; если ни одно не истинно, значения нет. Шаги:
``function_evaluate`` и ``function_evaluate_value`` (со значением).
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step
from .sympy_bridge import from_sympy, to_sympy

_RELATIONS = (
    T.EQUALS,
    T.NOT_EQUALS,
    T.LESS_THAN,
    T.LESS_THAN_EQUAL,
    T.GREATER_THAN,
    T.GREATER_THAN_EQUAL,
)


def piecewise_value(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Вычислить кусочно-заданную функцию в точке (аргумент — значение)."""
    if node.type is not T.PIECEWISE_DEFINITION:
        raise SolveError("значение берётся у кусочно-заданной функции")
    if len(args) != 1:
        raise SolveError("нужно значение аргумента")
    if len(node.children) < 2 or len(node.children) % 2 != 0:
        raise SolveError("кусочная функция: пары «выражение, условие»")

    symbol = _first_variable(node)
    value = to_sympy(args[0])
    ctx.result.add(Step(left=node, right=None, key="function_evaluate"))
    for index in range(0, len(node.children), 2):
        expression, condition = node.children[index], node.children[index + 1]
        if _condition_holds(condition, symbol, value):
            result = from_sympy(sympy.simplify(to_sympy(expression).subs(symbol, value)))
            ctx.result.add(
                Step(left=node, right=result, key="function_evaluate_value", args=[args[0]])
            )
            return result
    raise SolveError("ни одно условие кусочной функции не выполнено")


def _first_variable(node: CoreNode) -> sympy.Symbol:
    """Первая переменная выражения (или ``x``)."""
    for item in node.walk():
        if item.type is T.VARIABLE and item.value:
            return sympy.Symbol(item.value)
    return sympy.Symbol("x")


def _condition_holds(condition: CoreNode, symbol: sympy.Symbol, value: sympy.Expr) -> bool:
    """Истинно ли условие-отношение при данном значении переменной."""
    if condition.type not in _RELATIONS or len(condition.children) != 2:
        raise SolveError("условие кусочной функции — отношение двух выражений")
    left_node, right_node = condition.children
    left = to_sympy(left_node).subs(symbol, value)
    right = to_sympy(right_node).subs(symbol, value)
    comparison = _compare(condition.type, left, right)
    if comparison is sympy.true:
        return True
    if comparison is sympy.false:
        return False
    simplified = sympy.simplify(comparison)
    if simplified is sympy.true:
        return True
    if simplified is sympy.false:
        return False
    raise SolveError("условие кусочной функции не удалось проверить")


def _compare(node_type: T, left: sympy.Expr, right: sympy.Expr) -> sympy.Basic:
    """Отношение как объект sympy."""
    if node_type is T.EQUALS:
        return sympy.Eq(left, right)
    if node_type is T.NOT_EQUALS:
        return sympy.Ne(left, right)
    if node_type is T.LESS_THAN:
        return sympy.Lt(left, right)
    if node_type is T.LESS_THAN_EQUAL:
        return sympy.Le(left, right)
    if node_type is T.GREATER_THAN:
        return sympy.Gt(left, right)
    return sympy.Ge(left, right)


__all__ = [
    "piecewise_value",
]
