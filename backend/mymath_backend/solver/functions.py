"""Функции как объекты: ``f(x)`` и обратная ``f⁻¹(x)``.

Узел ``FUNCTION`` хранит имя функции в ``value``, а аргумент — в ``children``
(``f(x)`` -> ``value="f"``, ``children=[x]``); ``FUNCTION_INVERSE`` — то же для
обратной функции. Это те самые узлы, что порождал редактор Photomath
(операторы ``OPERATOR_FUNCTION``/``_F``/``_G``), и которых раньше не было в
нашем реестре — тип считался неподдерживаемым.

Определения функции у нас нет, поэтому вычислить её значение нельзя: модуль
не ищет ответ, а **нормализует аргумент** — если внутри есть арифметика, она
сворачивается тем же маршрутом (``f(2+3)`` -> ``f(5)``), а сам узел остаётся
символьным. Символьная работа (упрощение, подстановка) идёт через sympy
(`to_sympy`/`from_sympy` знают эти типы).
"""

from __future__ import annotations

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, fold_semantically, solver_for


@solver_for(T.FUNCTION, T.FUNCTION_INVERSE)
def solve_function_node(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Нормализовать аргумент функции, оставив сам узел символьным."""
    folded_children = [fold_semantically(child, ctx) for child in node.children]
    if folded_children == node.children:
        return node
    return CoreNode(type=node.type, value=node.value, children=folded_children)


__all__ = [
    "solve_function_node",
]
