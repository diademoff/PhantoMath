"""Вычисление значения выражения (узел ``EVALUATE_EXPRESSION``).

Узел ``EVALUATE_EXPRESSION`` хранит выражение и значение переменной
(``[выражение, значение]``); значение подставляется в единственную переменную
выражения. Шаг — ``function_evaluate_expr``.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step, solver_for
from .sympy_bridge import from_sympy, to_sympy


@solver_for(T.EVALUATE_EXPRESSION)
def solve_evaluate_expression(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Подставить значение в выражение и вычислить."""
    _ = ctx
    if len(node.children) != 2:
        raise SolveError("вычисление выражения: выражение и значение")
    expression_node, value_node = node.children
    expression = to_sympy(expression_node)
    symbols = sorted(expression.free_symbols, key=lambda item: item.name)
    if len(symbols) != 1:
        raise SolveError("выражение должно содержать одну переменную")
    result = from_sympy(sympy.simplify(expression.subs(symbols[0], to_sympy(value_node))))
    ctx.result.add(Step(left=node, right=result, key="function_evaluate_expr"))
    return result


__all__ = [
    "solve_evaluate_expression",
]
