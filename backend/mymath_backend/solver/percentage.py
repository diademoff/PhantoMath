"""Проценты.

Модуль зарегистрирован на узел ``PERCENTAGE``: ``p% = p / 100``. Ответ —
обыкновенная дробь (узел ``FRACTION``) после сокращения; целое значение
даёт константу. Шаг — ``percent_to_frac``.

Так процент участвует и в арифметике: ``50% · 200`` сворачивается в
``1/2 · 200 = 100``.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, Step, solver_for
from .sympy_bridge import from_sympy, to_sympy

_KEY = "percent_to_frac"


@solver_for(T.PERCENTAGE)
def solve_percentage(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Преобразовать процент в дробь."""
    ctx.require(len(node.children) == 1, "процент берётся от одного выражения")
    value = sympy.nsimplify(to_sympy(node.children[0]) / 100)
    answer = from_sympy(value)
    ctx.result.add(Step(left=node, right=answer, key=_KEY))
    return answer


__all__ = [
    "solve_percentage",
]
