"""Степени, корни и логарифмы: точное числовое упрощение.

Модуль зарегистрирован на узлы ``ROOT2``, ``ROOT``, ``LOG10``, ``LN``,
``LOG`` и ``EXP``. Он упрощает их, когда результат точен:

* ``√16 = 4``, ``∛27 = 3`` -- корень из полного квадрата/куба;
* ``log₁₀(1000) = 3``, ``log₂(8) = 3``, ``ln(e) = 1``, ``ln(1) = 0``;
* ``e⁰ = 1``.

Если точного значения нет (``√2``, ``log₁₀(5)``), узел возвращается без
изменений: символическое упрощение вида ``√8 = 2√2`` и действия с
иррациональностями — отдельная задача. Числа при этом остаются точными:
``√16 + 1 = 5``.

Ключи шагов: ``root_simplify`` для корней и ``calculate_short`` для
логарифмов и экспоненты.
"""

from __future__ import annotations

from math import isqrt

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step, route, solver_for

_KEY_ROOT = "root_simplify"
_KEY_CALCULATE = "calculate_short"


def _integer(node: CoreNode) -> int | None:
    """Целое значение константы или ``None``."""
    if node.type is not T.CONSTANT or node.value is None:
        return None
    text = node.value.strip()
    try:
        value = int(text)
    except ValueError:
        return None
    return value if str(value) == text else None


def _perfect_root(value: int, degree: int) -> int | None:
    """Целый корень ``degree``-й степени или ``None``."""
    if value < 0 and degree % 2 == 0:
        return None
    magnitude = abs(value)
    estimate = isqrt(magnitude) if degree == 2 else round(magnitude ** (1 / degree))
    for candidate in range(max(estimate - 2, 0), estimate + 3):
        if candidate**degree == magnitude:
            return -candidate if value < 0 else candidate
    return None


def _exact_log(value: int, base: int) -> int | None:
    """Показатель ``k``, если ``value == base^k``."""
    if value <= 0 or base <= 1:
        return None
    power, exponent = 1, 0
    while power < value:
        power *= base
        exponent += 1
        if exponent > 64:
            return None
    return exponent if power == value else None


@solver_for(T.ROOT2, T.ROOT)
def solve_root(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Упростить корень, если он извлекается нацело."""
    if node.type is T.ROOT2:
        degree = 2
        radicand = node.children[0]
    else:
        if len(node.children) != 2:
            raise SolveError("корень n-й степени должен иметь степень и подкоренное")
        degree_value = _integer(route(node.children[0], ctx))
        if degree_value is None or degree_value <= 1:
            return node
        degree = degree_value
        radicand = node.children[1]

    value = _integer(route(radicand, ctx))
    if value is None or value < 0:
        return node
    root = _perfect_root(value, degree)
    if root is None:
        return node

    result = CoreNode.constant(str(root))
    ctx.result.add(Step(left=node, right=result, key=_KEY_ROOT))
    return result


@solver_for(T.LOG10, T.LN, T.LOG, T.EXP)
def solve_logarithm(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить логарифм или экспоненту, если значение точное."""
    result: CoreNode | None = None

    if node.type is T.LN:
        argument = route(node.children[0], ctx)
        if argument.type is T.CONSTANT and argument.value == "e":
            result = CoreNode.constant("1")
        elif _integer(argument) == 1:
            result = CoreNode.constant("0")
    elif node.type is T.EXP:
        if _integer(route(node.children[0], ctx)) == 0:
            result = CoreNode.constant("1")
    elif node.type is T.LOG10:
        value = _integer(route(node.children[0], ctx))
        if value is not None:
            exponent = _exact_log(value, 10)
            if exponent is not None:
                result = CoreNode.constant(str(exponent))
    elif node.type is T.LOG:
        if len(node.children) == 2:
            value = _integer(route(node.children[0], ctx))
            base = _integer(route(node.children[1], ctx))
            if value is not None and base is not None:
                exponent = _exact_log(value, base)
                if exponent is not None:
                    result = CoreNode.constant(str(exponent))

    if result is None:
        return node
    ctx.result.add(Step(left=node, right=result, key=_KEY_CALCULATE))
    return result


__all__ = [
    "solve_logarithm",
    "solve_root",
]
