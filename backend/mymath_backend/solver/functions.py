"""Функции как объекты и их определения.

Две связанные вещи:

* **Узел ``FUNCTION``/``FUNCTION_INVERSE``** — функция как объект: имя в
  ``value``, аргумент в детях (``f(x)`` -> ``value="f"``, ``children=[x]``).
  Без определения значение не вычисляется: модуль нормализует аргумент
  (``f(2+3)`` -> ``f(5)``), а работа идёт через sympy.

* **Определения функций** ``f(x, …) = тело``. Определения приходят с запросом
  (`definitions`) и живут только в его пределах — сервер остаётся без
  состояния. Перед решением вызовы ``f(…)`` заменяются телом с подстановкой
  аргументов, а ``f⁻¹(a)`` — решением ``тело = a`` относительно параметра.

Так ``f(x) = 2x+1`` больше не «неизвестный тип»: его можно определить, а затем
вычислить ``f(2)``, взять ``f′(x)`` и обратную ``f⁻¹(a)``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, fold_semantically, solver_for
from .sympy_bridge import from_sympy, to_sympy

# Предел раскрытия определений: защита от ссылающихся друг на друга функций.
_MAX_DEPTH = 8


@dataclass(frozen=True)
class Definition:
    """Определение функции ``f(параметры…) = тело``."""

    name: str
    params: list[str]
    body: CoreNode


def parse_definition(node: CoreNode) -> Definition | None:
    """Распознать определение функции ``f(x, …) = тело`` или ``None``."""
    if node.type is not T.EQUALS or len(node.children) != 2:
        return None
    head, body = node.children
    if head.type is not T.FUNCTION or not head.value:
        return None
    if not head.children or any(child.type is not T.VARIABLE for child in head.children):
        return None
    params = [child.value for child in head.children if child.value]
    if len(params) != len(head.children):
        return None
    return Definition(name=head.value, params=params, body=body)


def parse_definitions(nodes: Iterable[CoreNode]) -> dict[str, Definition]:
    """Определения из запроса: имя -> определение."""
    out: dict[str, Definition] = {}
    for node in nodes:
        definition = parse_definition(node)
        if definition is not None:
            out[definition.name] = definition
    return out


def inline(node: CoreNode, definitions: dict[str, Definition], depth: int = 0) -> CoreNode:
    """Заменить вызовы определённых функций их выражениями.

    ``f(a)`` -> тело с ``параметр = a``; ``f⁻¹(a)`` -> решение ``тело = a``.
    Определения раскрываются рекурсивно (одна функция может звать другую),
    но не глубже ``_MAX_DEPTH``.
    """
    if depth > _MAX_DEPTH:
        return node

    if node.type is T.FUNCTION and node.value in definitions:
        definition = definitions[node.value]
        if len(definition.params) == len(node.children):
            mapping = dict(zip(definition.params, node.children, strict=True))
            expanded = _substitute(body=definition.body, mapping=mapping)
            return inline(expanded, definitions, depth + 1)
        return node

    if node.type is T.FUNCTION_INVERSE and node.value in definitions:
        argument = node.children[0] if node.children else CoreNode.empty()
        inverted = inverse_of(definitions[node.value], argument)
        return inline(inverted, definitions, depth + 1)

    if not node.children:
        return node
    children = [inline(child, definitions, depth) for child in node.children]
    if children == node.children:
        return node
    return CoreNode(
        type=node.type,
        value=node.value,
        children=children,
        color=node.color,
        crossed=node.crossed,
    )


def inverse_of(definition: Definition, argument: CoreNode) -> CoreNode:
    """``f⁻¹(argument)``: решить ``тело(параметр) = argument`` относительно параметра."""
    if len(definition.params) != 1:
        raise SolveError("обратная функция есть только у функции одной переменной")
    symbol = sympy.Symbol(definition.params[0])
    try:
        equation = sympy.Eq(to_sympy(definition.body), to_sympy(argument))
        solutions = sympy.solve(equation, symbol)
    except (ValueError, TypeError, NotImplementedError, sympy.SympifyError) as err:
        raise SolveError("не удалось найти обратную функцию") from err
    if not solutions:
        raise SolveError("обратная функция не найдена")
    if len(solutions) > 1:
        raise SolveError("обратная функция не однозначна")
    return from_sympy(sympy.simplify(solutions[0]))


def _substitute(*, body: CoreNode, mapping: dict[str, CoreNode]) -> CoreNode:
    """Подставить значения параметров в тело определения."""
    if body.type is T.VARIABLE and body.value in mapping:
        return mapping[body.value]
    if not body.children:
        return body
    return CoreNode(
        type=body.type,
        value=body.value,
        children=[_substitute(body=child, mapping=mapping) for child in body.children],
        color=body.color,
        crossed=body.crossed,
    )


@solver_for(T.FUNCTION, T.FUNCTION_INVERSE)
def solve_function_node(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Нормализовать аргумент функции, оставив сам узел символьным."""
    folded_children = [fold_semantically(child, ctx) for child in node.children]
    if folded_children == node.children:
        return node
    return CoreNode(type=node.type, value=node.value, children=folded_children)


__all__ = [
    "Definition",
    "inline",
    "inverse_of",
    "parse_definition",
    "parse_definitions",
    "solve_function_node",
]
