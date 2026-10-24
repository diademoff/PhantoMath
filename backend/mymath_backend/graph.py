"""Семплирование функции для графика.

Клиент рисует график сам, поэтому отдаём только точки.

Функция берётся из узла (``y = f(x)``) через мост sympy и вычисляется
``lambdify``; вещественные конечные значения собираются в точки. Точки с
разрывом (NaN, деление на ноль, комплексный результат) пропускаются.
"""

from __future__ import annotations

import math
import operator
from collections.abc import Callable
from typing import Any, cast

import sympy

from .ast import CoreNode
from .node_types import CoreNodeType as T
from .solver.base import SolveError
from .solver.sympy_bridge import to_sympy

_CONDITIONS: dict[T, Callable[[float, float], bool]] = {
    T.LESS_THAN: operator.lt,
    T.LESS_THAN_EQUAL: operator.le,
    T.GREATER_THAN: operator.gt,
    T.GREATER_THAN_EQUAL: operator.ge,
    T.EQUALS: operator.eq,
    T.NOT_EQUALS: operator.ne,
}

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

    node = _plotted(node)
    variable = free_variable(node)
    function = _function(node, variable)

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
        "annotations": _annotations_or_empty(node, x_min, x_max),
    }


_RELATIONS = (
    T.EQUALS,
    T.LESS_THAN,
    T.LESS_THAN_EQUAL,
    T.GREATER_THAN,
    T.GREATER_THAN_EQUAL,
)


def _annotations_or_empty(node: CoreNode, x_min: float, x_max: float) -> dict[str, Any]:
    """The marked points are a bonus: when sympy cannot find them the curve is still drawn."""
    try:
        return graph_annotations(node, x_min, x_max)
    except Exception:
        return {}


def _plotted(node: CoreNode) -> CoreNode:
    """An equation or inequality is drawn as ``y = left - right`` (its roots are the zeros)."""
    if node.type not in _RELATIONS or len(node.children) != 2:
        return node
    left, right = node.children
    if right.type is T.CONSTANT and right.value == "0":
        return left
    return CoreNode.node(T.SUBTRACT, left, CoreNode.node(T.BRACKET, right))


def _function(node: CoreNode, variable: str) -> Callable[[float], float]:
    """Функция ``x -> f(x)``; для кусочной — по ветвям с условиями."""
    symbol = sympy.Symbol(variable)
    if node.type is not T.PIECEWISE_DEFINITION:
        return _scalar(node, symbol)
    branches = [
        (_scalar(node.children[index], symbol), _condition(node.children[index + 1], symbol))
        for index in range(0, len(node.children) - 1, 2)
    ]

    def evaluate(x: float) -> float:
        for expression, condition in branches:
            try:
                if condition(x):
                    return expression(x)
            except (ValueError, TypeError, ZeroDivisionError):
                continue
        return math.nan

    return evaluate


def _scalar(node: CoreNode, symbol: sympy.Symbol) -> Callable[[float], float]:
    """Числовая функция от одного выражения."""
    return cast(Callable[[float], float], sympy.lambdify(symbol, to_sympy(node), modules=["math"]))


def _condition(node: CoreNode, symbol: sympy.Symbol) -> Callable[[float], bool]:
    """Предикат условия-отношения."""
    comparison = _CONDITIONS.get(node.type)
    if comparison is None or len(node.children) != 2:
        raise SolveError("условие кусочной функции — отношение двух выражений")
    left = _scalar(node.children[0], symbol)
    right = _scalar(node.children[1], symbol)
    return lambda x: comparison(left(x), right(x))


def graph_annotations(node: CoreNode, x_min: float, x_max: float) -> dict[str, Any]:
    """Опорные точки графика: корни, пересечение с осью y, экстремумы, асимптоты.

    Соответствует меткам ``graph_rt_info_*``. Значения вещественные и
    конечные; при неудаче соответствующая группа остаётся пустой. Для кусочной
    функции возвращается только признак ``piecewise``.
    """
    if node.type is T.PIECEWISE_DEFINITION:
        return {"piecewise": True}

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
