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
        "annotations": graph_annotations(node, x_min, x_max),
    }


def graph_annotations(node: CoreNode, x_min: float, x_max: float) -> dict[str, Any]:
    """Опорные точки графика: корни, пересечение с осью y, экстремумы, асимптоты.

    Соответствует меткам ``graph_rt_info_*`` Photomath. Значения вещественные и
    конечные; при неудаче соответствующая группа остаётся пустой.
    """
    variable = free_variable(node)
    symbol = sympy.Symbol(variable)
    expression = to_sympy(node)
    result: dict[str, Any] = {
        "roots": [],
        "yIntercept": None,
        "maxima": [],
        "minima": [],
        "verticalAsymptotes": [],
        "horizontalAsymptotes": [],
    }

    for root in _real_values(sympy.solve(sympy.Eq(expression, 0), symbol)):
        if x_min <= root <= x_max:
            result["roots"].append([root, 0.0])

    at_zero = _real_value(expression.subs(symbol, 0))
    if at_zero is not None:
        result["yIntercept"] = [0.0, at_zero]

    derivative = sympy.diff(expression, symbol)
    for point in _real_values(sympy.solve(sympy.Eq(derivative, 0), symbol)):
        if not x_min <= point <= x_max:
            continue
        second = _real_value(sympy.diff(derivative, symbol).subs(symbol, point))
        value = _real_value(expression.subs(symbol, point))
        if second is None or value is None:
            continue
        if second < 0:
            result["maxima"].append([point, value])
        elif second > 0:
            result["minima"].append([point, value])

    _, denominator = sympy.fraction(sympy.together(expression))
    for point in _real_values(sympy.solve(sympy.Eq(denominator, 0), symbol)):
        limit = sympy.limit(expression, symbol, point)
        if limit in (sympy.oo, -sympy.oo):
            result["verticalAsymptotes"].append(point)

    for bound in (sympy.oo, -sympy.oo):
        value = _real_value(sympy.limit(expression, symbol, bound))
        if value is not None and value not in result["horizontalAsymptotes"]:
            result["horizontalAsymptotes"].append(value)
    return result


def _real_values(values: list[sympy.Expr]) -> list[float]:
    """Действительные конечные числа из списка выражений."""
    result: list[float] = []
    for value in values:
        number = _real_value(value)
        if number is not None:
            result.append(number)
    return result


def _real_value(expression: sympy.Expr) -> float | None:
    """Числовое значение выражения или ``None``, если оно не вещественное."""
    try:
        number = float(sympy.N(expression))
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    return number


__all__ = [
    "DEFAULT_SAMPLES",
    "free_variable",
    "graph_annotations",
    "sample",
]
