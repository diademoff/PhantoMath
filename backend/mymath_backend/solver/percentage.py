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
    inner = node.children[0]
    value = sympy.nsimplify(to_sympy(inner) / 100)
    answer = from_sympy(value)
    shown = to_sympy(inner)
    if not (shown.is_Integer and shown > 0 and value.is_Rational):
        ctx.result.add(Step(left=node, right=answer, key=_KEY))
        return answer
    # by definition p% = p/100, then the fraction is reduced
    letter = CoreNode.variable("p")
    rule = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.PERCENTAGE, letter),
        CoreNode.node(T.FRACTION, letter, CoreNode.constant("100")),
    )
    fraction = CoreNode.node(T.FRACTION, inner, CoreNode.constant("100"))
    ctx.result.add_group("calculate_short", Step(node, fraction, "by_definition", [rule]))
    divisor = sympy.gcd(int(shown), 100)
    if divisor > 1:
        ctx.result.add_group(
            "frac_reduce_frac",
            Step(fraction, answer, "frac_reduce", [CoreNode.constant(str(divisor))]),
        )
    return answer


__all__ = [
    "solve_percentage",
]
