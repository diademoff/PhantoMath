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


@solver_for(*_LIMITS)
def solve_limit(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить предел через sympy."""
    ctx.require(len(node.children) == 2, "предел задаётся точкой и выражением")
    ctx.require(len(ctx.variables) <= 1, "поддерживается одно неизвестное")
    var = ctx.variables[0] if ctx.variables else "x"
    point, expression = node.children

    value = sympy.limit(
        to_sympy(expression),
        sympy.Symbol(var),
        to_sympy(point),
        _DIRECTION[node.type],
    )
    if not isinstance(value, sympy.Expr) or value is sympy.nan or value.has(sympy.Limit):
        raise SolveError("предел не существует или не вычисляется")

    try:
        result = from_sympy(sympy.simplify(value))
    except SolveError as err:
        # Неопределённая форма вроде AccumBounds: предела нет.
        raise SolveError("предел не существует или не вычисляется") from err
    ctx.result.add(Step(left=node, right=result, key="limit_solve"))
    return result


__all__ = [
    "solve_limit",
]
