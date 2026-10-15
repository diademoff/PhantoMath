"""Суммы (знак суммирования).

Модуль зарегистрирован на ``SIGMA_DEFINITE``. Дети, как в нативном решателе
(``c/a/a/l/h/v/k.java``): ``[индекс, нижний предел, верхний предел,
выражение]``. Принимается и форма редактора ``[нижний, верхний, выражение]``
с индексом ``n``.

Сумма вычисляется sympy; для числовых пределов выходит точное число, для
символьной верхней границы — формула. Результат переводится обратно в
``CoreNode`` мостом.

Шаг один — ``series_sigma_find_sub``.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step, boolean_node, solver_for
from .sympy_bridge import from_sympy, to_sympy


def _parts(node: CoreNode) -> tuple[str, CoreNode, CoreNode, CoreNode]:
    """Разобрать узел в ``(имя индекса, нижний, верхний, выражение)``."""
    if len(node.children) == 4:
        index, lower, upper, expression = node.children
        if index.type is not T.VARIABLE or not index.value:
            raise SolveError("индекс суммы должен быть переменной")
        return index.value, lower, upper, expression
    if len(node.children) == 3:
        lower, upper, expression = node.children
        return "n", lower, upper, expression
    raise SolveError("сумма задаётся индексом, пределами и выражением")


@solver_for(T.SIGMA_DEFINITE)
def solve_series(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить сумму ряда."""
    index, lower, upper, expression = _parts(node)
    symbol = sympy.Symbol(index)
    value = sympy.summation(
        to_sympy(expression),
        (symbol, to_sympy(lower), to_sympy(upper)),
    )
    if value.has(sympy.Sum):
        raise SolveError("сумму не удалось вычислить")
    result = from_sympy(sympy.simplify(value))
    ctx.result.add(Step(left=node, right=result, key="series_sigma_find_sub"))
    return result


def convergence(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Определить, сходится ли ряд (сумма с бесконечным пределом)."""
    del args
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("сходимость определяется у ряда (суммы)")
    index, lower, upper, expression = _parts(node)
    symbol = sympy.Symbol(index)
    value = sympy.summation(to_sympy(expression), (symbol, to_sympy(lower), to_sympy(upper)))
    if value.has(sympy.Sum):
        raise SolveError("сходимость не определена")
    converges = value.is_finite is True
    answer = boolean_node(converges)
    ctx.result.add(Step(left=node, right=answer, key="convergent" if converges else "divergent"))
    return answer


__all__ = [
    "convergence",
    "solve_series",
]
