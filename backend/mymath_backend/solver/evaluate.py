"""Вычисление значения выражения (узел ``EVALUATE_EXPRESSION``).

Узел ``EVALUATE_EXPRESSION`` хранит выражение и значение переменной
(``[выражение, значение]``); значение подставляется в единственную переменную
выражения. Шаг — ``function_evaluate_expr``.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, SolveResult, Step, route, solver_for
from .sympy_bridge import from_sympy, to_sympy


@solver_for(T.EVALUATE_EXPRESSION)
def solve_evaluate_expression(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Подставить значение в выражение и вычислить."""
    if len(node.children) != 2:
        raise SolveError("вычисление выражения: выражение и значение")
    expression_node, value_node = node.children
    expression = to_sympy(expression_node)
    symbols = sorted(expression.free_symbols, key=lambda item: item.name)
    if len(symbols) != 1:
        raise SolveError("выражение должно содержать одну переменную")
    result = from_sympy(sympy.simplify(expression.subs(symbols[0], to_sympy(value_node))))
    ctx.result.add(
        Step(
            left=node,
            right=result,
            key="function_evaluate_expr",
            subresult=_evaluation_detail(expression_node, symbols[0].name, value_node),
        )
    )
    return result


def _evaluation_detail(
    expression: CoreNode, name: str, value: CoreNode
) -> SolveResult | None:
    """Подробные шаги вычисления — раскрываемое пояснение шага.

    Подставляем значение вместо переменной и решаем получившееся числовое
    выражение тем же маршрутом, что и обычный ввод: так под шагом виден
    порядок действий. Детали не прикладываем, если выражение после подстановки
    не сворачивается или не изменилось.
    """
    substituted = _substitute(expression, name, value)
    scratch = SolveResult()
    scratch_ctx = SolveContext(result=scratch, variables=[])
    try:
        folded = route(substituted, scratch_ctx)
    except SolveError:
        return None
    if not scratch or folded.structural_eq(substituted):
        return None
    scratch.set_solution(folded)
    return scratch


def _substitute(node: CoreNode, name: str, value: CoreNode) -> CoreNode:
    """Заменить переменную ``name`` на узел ``value`` (копия дерева)."""
    if node.type is T.VARIABLE and node.value == name:
        return value
    if not node.children:
        return node
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[_substitute(child, name, value) for child in node.children],
        color=node.color,
        crossed=node.crossed,
    )


@solver_for(T.MEAN)
def solve_mean(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Среднее арифметическое значений (узел ``MEAN``).

    Ответ — сумма, делённая на число слагаемых; шаг ``calculate_short``.
    """
    ctx.require(len(node.children) >= 1, "среднее: хотя бы одно значение")
    values = [to_sympy(child) for child in node.children]
    result = from_sympy(sympy.simplify(sympy.Add(*values) / len(values)))
    ctx.result.add(Step(left=node, right=result, key="calculate_short"))
    return result


__all__ = [
    "solve_evaluate_expression",
    "solve_mean",
]
