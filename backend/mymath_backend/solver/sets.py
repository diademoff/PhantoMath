"""Множества и отношения на них.

Модуль покрывает конечные множества (``SET``), операции над ними
(``UNION``, ``INTERSECTION``, ``DIFFERENCE``) и отношения
(``ELEMENT_OF``/``ELEMENT_NOT_OF``, ``SUBSET_*``/``SUPERSET_*``).

Структура узлов взята из рендера APK (``c.a.a.l.h.v.k``, ``EditorView``):
``SET`` — элементы через запятую, ``UNION``/``INTERSECTION`` — операнды через
``∪``/``∩``, ``DIFFERENCE`` и все отношения — по два ребёнка.

Шаги: у ``union`` и ``intersection`` есть ключи словаря; у разности и отношений
ключей нет, поэтому ответ отдаётся **без шага**. Булев ответ — узел
``TEXT[TEXT_KEY("true"/"false")]``, как в APK: первый ребёнок ``TEXT`` задаёт
ключ текста, который клиент подставляет («Истина»/«Ложь»).
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step, boolean_node, fold_semantically, solver_for
from .sympy_bridge import from_sympy, to_sympy

_SET_OPS = (T.SET, T.UNION, T.INTERSECTION, T.DIFFERENCE)
_MEMBERSHIP = (T.ELEMENT_OF, T.ELEMENT_NOT_OF)
_INCLUSION = (
    T.SUBSET_OR_EQUALS,
    T.PROPER_SUBSET,
    T.NOT_PROPER_SUBSET,
    T.SUPERSET_OR_EQUALS,
    T.PROPER_SUPERSET,
    T.NOT_PROPER_SUPERSET,
)

# Ключ шага у операции, если он есть в словаре объяснений.
_STEP_KEY: dict[T, str] = {
    T.UNION: "union",
    T.INTERSECTION: "intersection",
}


@solver_for(*_SET_OPS)
def solve_set_operation(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Свести конечное множество и операции над множествами через sympy."""
    ctx.require(len(node.children) >= 1, "операция над множествами требует операндов")
    normalized = CoreNode.node(node.type, *(fold_semantically(c, ctx) for c in node.children))
    result = from_sympy(to_sympy(normalized))
    key = _STEP_KEY.get(node.type)
    if key is not None and not result.structural_eq(node):
        ctx.result.add(Step(left=node, right=result, key=key))
    return result


@solver_for(*_MEMBERSHIP)
def solve_membership(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Проверить вхождение элемента в множество и вернуть «Истина»/«Ложь»."""
    ctx.require(len(node.children) == 2, "отношение требует двух операндов")
    element = to_sympy(fold_semantically(node.children[0], ctx))
    target = to_sympy(fold_semantically(node.children[1], ctx))
    contains = target.contains(element)
    if contains not in (True, False):
        raise SolveError("вхождение не определено")
    value = not contains if node.type is T.ELEMENT_NOT_OF else contains
    return boolean_node(value)


@solver_for(*_INCLUSION)
def solve_inclusion(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Проверить включение множеств и вернуть «Истина»/«Ложь»."""
    ctx.require(len(node.children) == 2, "отношение требует двух операндов")
    left = to_sympy(fold_semantically(node.children[0], ctx))
    right = to_sympy(fold_semantically(node.children[1], ctx))
    value = _inclusion_value(node.type, left, right)
    if value not in (True, False):
        raise SolveError("включение не определено")
    return boolean_node(value)


def _inclusion_value(node_type: T, left: sympy.Set, right: sympy.Set) -> bool | None:
    """Значение отношения включения; ``None`` — не удалось определить.

    ``NOT_PROPER_SUBSET``/``NOT_PROPER_SUPERSET`` — отрицание собственного
    включения (символы ``⊄``/``⊅`` в рендере APK).
    """
    if node_type is T.SUBSET_OR_EQUALS:
        return _as_bool(left.is_subset(right))
    if node_type is T.PROPER_SUBSET:
        return _as_bool(left.is_proper_subset(right))
    if node_type is T.NOT_PROPER_SUBSET:
        return _negate(_as_bool(left.is_proper_subset(right)))
    if node_type is T.SUPERSET_OR_EQUALS:
        return _as_bool(left.is_superset(right))
    if node_type is T.PROPER_SUPERSET:
        return _as_bool(left.is_proper_superset(right))
    return _negate(_as_bool(left.is_proper_superset(right)))


def _as_bool(value: object) -> bool | None:
    """Привести ответ sympy к ``bool``; иначе «неизвестно»."""
    return value if isinstance(value, bool) else None


def _negate(value: bool | None) -> bool | None:
    """Логическое отрицание с сохранением «неизвестно»."""
    if value is None:
        return None
    return not value


__all__ = [
    "solve_inclusion",
    "solve_membership",
    "solve_set_operation",
]
