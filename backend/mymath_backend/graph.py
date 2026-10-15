"""Семплирование функции для графика.

Полноценный ``CoreGraphResult`` Photomath не воспроизводим (его вёрстка осей
не разобрана) и не нужен: клиент рисует график сам. Отдаём только точки.

Функция берётся из узла (``y = f(x)``) через мост sympy и вычисляется
``lambdify``; вещественные конечные значения собираются в точки. Точки с
разрывом (NaN, деление на ноль, комплексный результат) пропускаются.
"""

from __future__ import annotations

import math
from typing import Any

import sympy

from .ast import CoreNode
from .solver.base import SolveError
from .solver.sympy_bridge import to_sympy

DEFAULT_SAMPLES = 400
_MAX_SAMPLES = 5000


def free_variable(node: CoreNode) -> str:
    """Первая переменная выражения или ``x``."""
    for item in node.walk():
        if item.type.value == "VARIABLE" and item.value:
            return item.value
    return "x"


def sample(
    node: CoreNode, x_min: float, x_max: float, samples: int = DEFAULT_SAMPLES
) -> dict[str, Any]:
    """Точки графика ``f(x)`` на отрезке ``[x_min, x_max]``."""
    if not math.isfinite(x_min) or not math.isfinite(x_max) or x_max <= x_min:
        raise SolveError("неверный диапазон графика")
    if samples < 2 or samples > _MAX_SAMPLES:
        raise SolveError("неверное число точек")

    variable = free_variable(node)
    function = sympy.lambdify(sympy.Symbol(variable), to_sympy(node), modules=["math"])

    points: list[list[float]] = []
    step = (x_max - x_min) / (samples - 1)
    for index in range(samples):
        x = x_min + index * step
        try:
            y = function(x)
        except (ValueError, TypeError, ZeroDivisionError, OverflowError):
            continue
        if isinstance(y, complex) or not isinstance(y, (int, float)):
            continue
        if not math.isfinite(y):
            continue
        points.append([x, float(y)])

    if not points:
        raise SolveError("не удалось построить график: нет вещественных значений")

    ys = [point[1] for point in points]
    return {
        "variable": variable,
        "xMin": x_min,
        "xMax": x_max,
        "yMin": min(ys),
        "yMax": max(ys),
        "points": points,
    }


__all__ = [
    "DEFAULT_SAMPLES",
    "free_variable",
    "sample",
]
