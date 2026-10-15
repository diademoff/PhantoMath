"""Пределы функций в конечной точке.

Модуль зарегистрирован на ``LIMIT``, ``LIMIT_LEFT`` и ``LIMIT_RIGHT``.
Дети: точка и выражение (``[to, expr]``). Предел берётся подстановкой:
неизвестное заменяется значением точки, и выражение сворачивается обычным
решателем (арифметика, корни, логарифмы). Если подстановка даёт
неопределённость (``0/0``, деление на ноль) или точного значения нет —
предел не вычисляется: раскрытие неопределённостей и пределы на
бесконечности — следующие модули.

Шаг один — ``limit_solve``.
"""

from __future__ import annotations

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .arithmetic import as_fraction
from .base import SolveContext, SolveError, SolveResult, Step, route, solver_for

_LIMITS = (T.LIMIT, T.LIMIT_LEFT, T.LIMIT_RIGHT)


def _substitute(node: CoreNode, var: str, replacement: CoreNode) -> CoreNode:
    """Заменить переменную ``var`` узлом ``replacement`` по всему дереву."""
    if node.type is T.VARIABLE and node.value == var:
        return replacement
    if not node.children:
        return node
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[_substitute(child, var, replacement) for child in node.children],
    )


@solver_for(*_LIMITS)
def solve_limit(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить предел подстановкой значения."""
    ctx.require(len(node.children) == 2, "предел задаётся точкой и выражением")
    ctx.require(len(ctx.variables) <= 1, "поддерживается одно неизвестное")
    var = ctx.variables[0] if ctx.variables else "x"
    point, expression = node.children
    try:
        as_fraction(point)
    except SolveError as err:
        raise SolveError(
            "пределы на бесконечности и в параметрических точках пока не поддерживаются"
        ) from err

    substituted = _substitute(expression, var, point)
    # Считаем в отдельном накопителе: шаги подстановки не должны попадать в
    # список шагов предела — показываем один шаг «Вычислите предел».
    scratch = SolveContext(result=SolveResult(), variables=[])
    value = route(substituted, scratch)
    text = value.value
    if value.type is not T.CONSTANT or text is None:
        raise SolveError("предел не вычисляется точно")

    result = CoreNode.constant(text)
    ctx.result.add(Step(left=node, right=result, key="limit_solve"))
    return result


__all__ = [
    "solve_limit",
]
