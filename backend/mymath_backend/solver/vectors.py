"""Векторы: наше представление и операции.

В контракте CoreNode нет типа вектора, поэтому вводим **своё**
представление: вектор — это узел ``LIST`` с компонентами. Операции — команды
(``CoreAction``); второй операнд приходит в ``action.args``.

Команды:

* ``vector_length`` — длина (модуль);
* ``vector_add`` / ``vector_subtract`` — сложение и вычитание (второй вектор);
* ``vector_scale`` — умножение на скаляр (скаляр в ``args``);
* ``vector_dot`` — скалярное произведение;
* ``vector_cross`` — векторное произведение (только 3D).

Считает sympy; шаг — ``calculate_short`` (специальных ключей под векторы в
словаре нет).
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import Command, SolveContext, SolveError, Step
from .sympy_bridge import from_sympy, to_sympy

_VECTOR_TYPES = (T.LIST, T.VERTICAL_LIST)
_KEY = "calculate_short"


def _components(node: CoreNode) -> sympy.Matrix:
    """Компоненты вектора как матрица-столбец sympy."""
    if node.type not in _VECTOR_TYPES or not node.children:
        raise SolveError("ожидался вектор: узел LIST с компонентами")
    return sympy.Matrix([to_sympy(child) for child in node.children])


def _vector_node(values: sympy.Matrix) -> CoreNode:
    return CoreNode.node(
        T.LIST,
        *[from_sympy(sympy.simplify(component)) for component in values],
    )


def _record(node: CoreNode, result: CoreNode, ctx: SolveContext) -> CoreNode:
    ctx.result.add(Step(left=node, right=result, key=_KEY))
    return result


def vector_length(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Длина вектора: корень из суммы квадратов компонент."""
    vector = _components(node)
    return _record(node, from_sympy(sympy.sqrt(vector.dot(vector))), ctx)


def _require_same_shape(first: sympy.Matrix, second: sympy.Matrix) -> None:
    """Размерности операндов совпадают, иначе операция не определена."""
    if first.shape != second.shape:
        raise SolveError("векторы должны быть одной размерности")


def vector_add(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Сложение векторов."""
    if not args:
        raise SolveError("для сложения нужен второй вектор")
    first, second = _components(node), _components(args[0])
    _require_same_shape(first, second)
    return _record(node, _vector_node(first + second), ctx)


def vector_subtract(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Вычитание векторов."""
    if not args:
        raise SolveError("для вычитания нужен второй вектор")
    first, second = _components(node), _components(args[0])
    _require_same_shape(first, second)
    return _record(node, _vector_node(first - second), ctx)


def vector_scale(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Умножение вектора на скаляр."""
    if not args:
        raise SolveError("для умножения нужен скаляр")
    scalar = to_sympy(args[0])
    return _record(node, _vector_node(_components(node) * scalar), ctx)


def vector_dot(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Скалярное произведение."""
    if not args:
        raise SolveError("для скалярного произведения нужен второй вектор")
    first, second = _components(node), _components(args[0])
    _require_same_shape(first, second)
    product = first.dot(second)
    return _record(node, from_sympy(sympy.simplify(product)), ctx)


def vector_cross(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Векторное произведение (только для 3D)."""
    if not args:
        raise SolveError("для векторного произведения нужен второй вектор")
    first = _components(node)
    second = _components(args[0])
    if first.shape != (3, 1) or second.shape != (3, 1):
        raise SolveError("векторное произведение определено только для 3D")
    return _record(node, _vector_node(first.cross(second)), ctx)


VECTOR_COMMANDS: dict[str, Command] = {
    "vector_length": vector_length,
    "vector_add": vector_add,
    "vector_subtract": vector_subtract,
    "vector_scale": vector_scale,
    "vector_dot": vector_dot,
    "vector_cross": vector_cross,
}

__all__ = [
    "VECTOR_COMMANDS",
    "vector_add",
    "vector_cross",
    "vector_dot",
    "vector_length",
    "vector_scale",
    "vector_subtract",
]
