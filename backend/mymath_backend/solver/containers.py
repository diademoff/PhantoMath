"""Служебные и оформительские типы узлов.

Типы без собственной математики: контейнеры (``LIST``/``VERTICAL_LIST``),
нотация (``DIFFERENTIAL``, ``DERIVATION_DIFF``, ``ADD_SUBTRACT*``,
``APPROXIMATE*``, ``EQUALS_SIGN``, ``ALTERNATIVE_FORM``), функции-объекты
(``FUNCTION``, ``FUNCTION_INVERSE``), кусочные/условные определения,
разбиение матриц (``MATRIX_SPLIT_*``) и текстовые/сервисные узлы.

Список: содержимое сворачивается, если это возможно (``LIST``/``VERTICAL_LIST``),
остальное возвращается как есть — так маршрутизация не считает их
«нереализованным типом». Геометрия (``LINE_SEGMENT*``) намеренно не
регистрируется (исключена решением пользователя).
"""

from __future__ import annotations

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, fold_semantically, route, solver_for

_LIST_TYPES = (T.LIST, T.VERTICAL_LIST)

_NOTATION_TYPES = (
    T.DIFFERENTIAL,
    T.DERIVATION_DIFF,
    T.ADD_SUBTRACT_SIGN,
    T.APPROXIMATE,
    T.APPROXIMATE_SIGN,
    T.ALTERNATIVE_FORM,
    T.EQUALS_SIGN,
    T.FUNCTION,
    T.FUNCTION_INVERSE,
    T.PIECEWISE_DEFINITION,
    T.CONDITIONAL_EXPRESSION,
    T.MATRIX_SPLIT_LAST,
    T.MATRIX_SPLIT_CENTER,
    T.PERIODIC,
    T.TEXT,
    T.TEXT_KEY,
    T.EMPTY,
    T.STRING,
    T.UNKNOWN,
    T.CHOOSE_LOCALIZE,
)


@solver_for(*_LIST_TYPES)
def solve_container(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Свернуть элементы списка (сам список сохраняется)."""
    children = [fold_semantically(child, ctx) for child in node.children]
    return CoreNode.node(node.type, *children)


@solver_for(*_NOTATION_TYPES)
def solve_notation(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Нотация/контейнер без собственной математики — остаётся как есть."""
    _ = ctx
    return node


@solver_for(T.ADD_SUBTRACT)
def solve_add_subtract(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Плюс-минус: две ветви ``a+b`` и ``a−b`` с шагами.

    Числовые операнды раскрываются в список из двух значений (шаги ``add`` и
    ``sub``); символьные остаются как есть — точных значений у них нет.
    """
    if len(node.children) != 2:
        raise SolveError("плюс-минус соединяет два выражения")
    folded = [fold_semantically(child, ctx) for child in node.children]
    if not all(child.type is T.CONSTANT and child.value for child in folded):
        return node
    branches = [route(CoreNode.node(op, *folded), ctx) for op in (T.ADD, T.SUBTRACT)]
    return CoreNode.node(T.LIST, *branches)


__all__ = [
    "solve_add_subtract",
    "solve_container",
    "solve_notation",
]
