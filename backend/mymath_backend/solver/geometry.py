"""Отрезок и его длина (``LINE_SEGMENT``, ``LINE_SEGMENT_LENGTH``).

Единственная геометрия, которая есть в APK: в нативном движке найдены строки
``line_segment`` и ``line_segment_length``, в контракте — типы ``LINE_SEGMENT``
и ``LINE_SEGMENT_LENGTH``. Отдельного решателя геометрии (площадь, периметр,
треугольники, окружности) в артефактах **нет** — только эти обозначения, и
длины в реальных задачах движок считал своим общим механизмом.

Что делаем:

* ``LINE_SEGMENT`` — обозначение отрезка (``AB`` с чертой сверху): узел
  символьный, значение у него не вычисляется;
* ``LINE_SEGMENT_LENGTH`` — длина отрезка: если заданы две числовые точки
  (координаты), считаем расстояние ``√((x₁−x₂)² + (y₁−y₂)²)``; если заданы два
  числа — ``|a − b|`` на числовой прямой; иначе узел остаётся символьным.

Тексты шагов берутся из существующих ключей (``calculate_short`` для расстояния
и ``abs`` для модуля): геометрических ключей объяснений в APK нет.
"""

from __future__ import annotations

from fractions import Fraction

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, Step, solver_for
from .sympy_bridge import from_sympy, to_sympy


@solver_for(T.LINE_SEGMENT)
def solve_segment(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Отрезок как объект: значение не вычисляется, узел символьный."""
    _ = ctx
    return node


@solver_for(T.LINE_SEGMENT_LENGTH)
def solve_segment_length(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Длина отрезка: расстояние между точками или ``|a − b|``."""
    endpoints = _endpoints(node)
    if endpoints is None:
        return node
    first, second = endpoints
    if (
        _is_point(first)
        and _is_point(second)
        and len(first.children) == len(second.children)
    ):
        coordinates = [
            to_sympy(left) - to_sympy(right)
            for left, right in zip(first.children, second.children, strict=True)
        ]
        distance = sympy.sqrt(sum(coordinate**2 for coordinate in coordinates))
        result = from_sympy(sympy.simplify(distance))
        ctx.result.add(Step(left=node, right=result, key="calculate_short"))
        return result
    a, b = _number(first), _number(second)
    if a is not None and b is not None:
        result = from_sympy(sympy.Abs(a - b))
        ctx.result.add(Step(left=node, right=result, key="abs"))
        return result
    # Метки (``A``, ``B``) без координат — длина остаётся символьной.
    return node


def _endpoints(node: CoreNode) -> tuple[CoreNode, CoreNode] | None:
    """Концы отрезка: два ребёнка или единственный ``LINE_SEGMENT``."""
    children = node.children
    if len(children) == 2:
        return children[0], children[1]
    if len(children) == 1:
        segment = children[0]
        if segment.type is T.LINE_SEGMENT and len(segment.children) == 2:
            return segment.children[0], segment.children[1]
    return None


def _is_point(node: CoreNode) -> bool:
    """Точка ли это: список числовых координат (``LIST`` из констант)."""
    if node.type is not T.LIST or not node.children:
        return False
    return all(_number(child) is not None for child in node.children)


def _number(node: CoreNode) -> Fraction | None:
    """Число узла, если это числовая константа."""
    if node.type is not T.CONSTANT or node.value is None:
        return None
    try:
        return Fraction(node.value.strip())
    except ValueError:
        return None


__all__ = [
    "solve_segment",
    "solve_segment_length",
]
