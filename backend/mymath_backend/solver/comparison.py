"""Сравнение чисел и выражений и упорядочивание.

Отношение без свободных переменных (``2 < 3``, ``2 = 2``) — это утверждение,
истинное или ложное, а не уравнение: булев ответ — ``TEXT[TEXT_KEY]`` (как в
APK). Сравнение запускается из :func:`mymath_backend.solver.solve`
(спец-обработка отношений без переменных), поэтому своего ``solver_for`` у
проверки нет; при переменных работает модуль неравенств.

Ключи шага: ``compare_eq`` для равенства, ``compare_ineq`` для неравенства.

Узел ``ORDER`` — упорядочивание элементов по возрастанию; ответ — тот же узел
с отсортированными детьми. Ключа шага у ``ORDER`` в словаре нет, поэтому ответ
отдаётся **без шага**.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step, boolean_node, fold_semantically, solver_for
from .sympy_bridge import to_sympy

# Отношения, которые без переменных становятся утверждением «Истина»/«Ложь».
COMPARABLE = (
    T.EQUALS,
    T.NOT_EQUALS,
    T.LESS_THAN,
    T.LESS_THAN_EQUAL,
    T.GREATER_THAN,
    T.GREATER_THAN_EQUAL,
)

# Равенство и неравенство проверяются разными ключами словаря.
_STEP_KEY: dict[T, str] = {
    T.EQUALS: "compare_eq",
    T.NOT_EQUALS: "compare_ineq",
}


def solve_comparison(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Проверить утверждение без переменных и вернуть «Истина»/«Ложь»."""
    ctx.require(len(node.children) == 2, "утверждение связывает две части")
    value = _evaluate(node.type, to_sympy(node.children[0]), to_sympy(node.children[1]))
    if value not in (True, False):
        raise SolveError("утверждение не удалось проверить")
    answer = boolean_node(value)
    ctx.result.add(Step(left=node, right=answer, key=_STEP_KEY.get(node.type, "compare_ineq")))
    return answer


def _evaluate(node_type: T, left: sympy.Expr, right: sympy.Expr) -> bool | None:
    """Значение отношения между двумя выражениями без переменных.

    ``None`` — sympy не смог свести отношение к булеву значению.
    """
    if node_type is T.EQUALS:
        result: sympy.Basic = sympy.Eq(left, right)
    elif node_type is T.NOT_EQUALS:
        result = sympy.Ne(left, right)
    elif node_type is T.LESS_THAN:
        result = left < right
    elif node_type is T.LESS_THAN_EQUAL:
        result = left <= right
    elif node_type is T.GREATER_THAN:
        result = left > right
    else:
        result = left >= right
    return _as_bool(result)


def _as_bool(value: object) -> bool | None:
    """Свести ответ sympy к ``bool``; ``None`` — значение не определено.

    sympy отдаёт ``BooleanTrue``/``BooleanFalse`` (не питоновский ``bool``)
    либо нерешённое отношение; последнее пробуем упростить.
    """
    if isinstance(value, bool):
        return value
    if value is sympy.true or value is sympy.false:
        return value is sympy.true
    simplified = sympy.simplify(value)
    if isinstance(simplified, bool):
        return simplified
    if simplified is sympy.true or simplified is sympy.false:
        return simplified is sympy.true
    return None


@solver_for(T.ORDER)
def solve_order(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Упорядочить элементы ``ORDER`` по возрастанию."""
    ctx.require(len(node.children) >= 1, "ORDER требует элементов")
    items = [fold_semantically(child, ctx) for child in node.children]
    try:
        ordered = sorted(items, key=lambda item: to_sympy(item).sort_key())
    except (TypeError, ValueError) as error:
        raise SolveError("элементы нельзя упорядочить") from error
    return CoreNode.node(T.ORDER, *ordered)


__all__ = [
    "COMPARABLE",
    "solve_comparison",
    "solve_order",
]
