"""Столбиковые (школьные) вычисления (P).

Узлы ``VERTICAL_ADD``/``VERTICAL_SUBTRACT``/``VERTICAL_MULTIPLY`` — список
операндов (дети выравниваются по столбцам, см. ``g0.o`` в рендере APK),
``HORIZONTAL_MULTIPLY`` — обычное произведение двух множителей,
``US_LONGDIV``/``RU_LONGDIV``/``VERTICAL_DIVIDE`` — деление.

Математика считается sympy; шаг называет столбиковый метод
(``animation_long_add``/``animation_long_sub``/``animation_long_mul``/
``animation_long_div``). Пошаговый рендер столбиков и анимация — уровень
приложения, не решателя.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step, solver_for
from .sympy_bridge import from_sympy, to_sympy

_KEYS: dict[T, str] = {
    T.VERTICAL_ADD: "animation_long_add",
    T.VERTICAL_SUBTRACT: "animation_long_sub",
    T.VERTICAL_MULTIPLY: "animation_long_mul",
    T.HORIZONTAL_MULTIPLY: "calculate_short",
    T.VERTICAL_DIVIDE: "animation_long_div",
    T.US_LONGDIV: "animation_long_div",
    T.RU_LONGDIV: "animation_long_div",
}


@solver_for(*_KEYS)
def solve_vertical(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить столбиковое выражение (сложение, вычитание, умножение, деление)."""
    ctx.require(len(node.children) >= 2, "столбиковое вычисление: минимум два операнда")
    values = [to_sympy(child) for child in node.children]

    if node.type is T.VERTICAL_ADD:
        value = sympy.Add(*values)
    elif node.type is T.VERTICAL_SUBTRACT:
        value = values[0] - sympy.Add(*values[1:])
    elif node.type in (T.VERTICAL_MULTIPLY, T.HORIZONTAL_MULTIPLY):
        value = sympy.Mul(*values)
    else:
        divisor = sympy.Mul(*values[1:])
        if divisor == 0:
            raise SolveError("деление на ноль в столбиковом вычислении")
        value = values[0] / divisor

    result = from_sympy(sympy.simplify(value))
    ctx.result.add(Step(left=node, right=result, key=_KEYS[node.type]))
    return result


__all__ = [
    "solve_vertical",
]
