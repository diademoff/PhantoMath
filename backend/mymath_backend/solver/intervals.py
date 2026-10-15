"""Числовые промежутки (интервалы).

Модуль зарегистрирован на четыре типа промежутков — открытый/закрытый край
слева и справа (``OPEN_OPEN_INTERVAL``, ``OPEN_CLOSED_INTERVAL``,
``CLOSED_OPEN_INTERVAL``, ``CLOSED_CLOSED_INTERVAL``). Дети узла — две
границы: начало и конец.

Промежуток сам по себе не вычисляется: это представление множества решений,
которым пользуются неравенства и область определения. Здесь он
**нормализуется**: границы сворачиваются как подвыражения, а пустой
промежуток (начало больше конца, либо края равны с открытым концом)
заменяется на ``EMPTY``. Если после свёртки промежуток изменился, к шагам
добавляется ``rewrite_interval`` («перепишите интервал»).
"""

from __future__ import annotations

from ..ast import CoreNode
from .base import SolveContext, Step, fold_semantically, solver_for
from .sympy_bridge import INTERVALS, to_sympy

_KEY_REWRITE = "rewrite_interval"


@solver_for(*INTERVALS)
def solve_interval(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Свернуть границы промежутка и распознать пустой.

    Шаги свёртки границ переносятся в результат (``1+1`` даёт шаг ``add``),
    после чего при изменении добавляется ``rewrite_interval``.
    """
    ctx.require(len(node.children) == 2, "промежуток задаётся началом и концом")
    start = fold_semantically(node.children[0], ctx)
    end = fold_semantically(node.children[1], ctx)
    normalized = CoreNode.node(node.type, start, end)

    if _is_empty(normalized):
        ctx.result.add(Step(left=node, right=CoreNode.empty(), key=_KEY_REWRITE))
        return CoreNode.empty()

    if not normalized.structural_eq(node):
        ctx.result.add(Step(left=node, right=normalized, key=_KEY_REWRITE))
    return normalized


def _is_empty(node: CoreNode) -> bool:
    """Пуст ли промежуток.

    Пустоту решает sympy: ``(2, 1)`` и ``(1, 1)`` дают ``EmptySet``,
    а ``[1, 1]`` — точку, а не пустое множество.
    """
    return to_sympy(node).is_empty is True


__all__ = [
    "solve_interval",
]
