"""Условное выражение (узел ``CONDITIONAL_EXPRESSION``).

Дети в порядке ``[условие, ветвь «да», ветвь «нет»]``. Если условие решается
без переменных (``2 < 3``) — берётся соответствующая ветвь и добавляется шаг
``true``/``false``; иначе узел остаётся символьным и переводится в ``Piecewise``
(см. ``sympy_bridge``), так что работает и внутри выражений.

Собственного типа узла у условия нет: это обычное отношение (``<``, ``≤``, …),
поэтому проверка — через ``sympy.simplify`` от его перевода.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step, solver_for
from .sympy_bridge import to_sympy


@solver_for(T.CONDITIONAL_EXPRESSION)
def solve_conditional(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Выбрать ветвь условного выражения, если условие решается."""
    ctx.require(
        len(node.children) == 3,
        "условное выражение: условие, ветвь «да», ветвь «нет»",
    )
    condition, then, otherwise = node.children
    decision = _decide(condition)
    if decision is None:
        # Условие зависит от переменной — узел остаётся символьным.
        return node
    chosen = then if decision else otherwise
    ctx.result.add(Step(left=node, right=chosen, key="true" if decision else "false"))
    return chosen


def _decide(condition: CoreNode) -> bool | None:
    """Истинно ли условие; ``None``, если решить не удалось."""
    try:
        value = sympy.simplify(to_sympy(condition))
    except SolveError:
        return None
    if value is sympy.true:
        return True
    if value is sympy.false:
        return False
    return None


__all__ = [
    "solve_conditional",
]
