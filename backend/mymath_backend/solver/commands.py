"""Команды над выражением (``CoreAction``).

В Photomath над узлом может выполняться **действие**: ``{ "command": …,
"args": […] }``. Так выражаются операции, у которых нет своего типа узла:
разложить на множители, раскрыть, упростить. Наш ``POST /solve`` принимает
необязательное поле ``action`` с командой.

Имена команд — наши (в APK они не восстановлены, кроме примера ``solve``):

* ``solve`` — решить/вычислить (поведение по умолчанию, без действия);
* ``factor`` — разложить на множители (``factorise_call``);
* ``expand`` — раскрыть (``expand_msg``);
* ``simplify`` — упростить (``simplify``).

Для уравнения команда применяется к обеим частям.
"""

from __future__ import annotations

from collections.abc import Callable

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step
from .sympy_bridge import from_sympy, to_sympy

Command = Callable[[CoreNode, SolveContext], CoreNode]


def _apply_side(
    node: CoreNode, ctx: SolveContext, key: str, transform: Callable[[sympy.Expr], sympy.Expr]
) -> CoreNode:
    """Применить символьное преобразование к узлу (для уравнения — к частям)."""
    if node.type is T.EQUALS and len(node.children) == 2:
        left = from_sympy(transform(to_sympy(node.children[0])))
        right = from_sympy(transform(to_sympy(node.children[1])))
        result = CoreNode.node(T.EQUALS, left, right)
    else:
        result = from_sympy(transform(to_sympy(node)))
    ctx.result.add(Step(left=node, right=result, key=key))
    return result


def factor(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Разложить выражение на множители."""
    return _apply_side(node, ctx, "factorise_call", sympy.factor)


def expand(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Раскрыть скобки."""
    return _apply_side(node, ctx, "expand_msg", sympy.expand)


def simplify(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Упростить выражение."""
    return _apply_side(node, ctx, "simplify", sympy.simplify)


COMMANDS: dict[str, Command] = {
    "factor": factor,
    "expand": expand,
    "simplify": simplify,
}


def apply(command: str, node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Выполнить команду; неизвестная команда — ошибка."""
    handler = COMMANDS.get(command)
    if handler is None:
        raise SolveError(f"неизвестная команда {command!r}")
    return handler(node, ctx)


__all__ = [
    "COMMANDS",
    "Command",
    "apply",
    "expand",
    "factor",
    "simplify",
]
