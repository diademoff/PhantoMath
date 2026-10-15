"""Команды над выражением (``CoreAction``).

В Photomath над узлом может выполняться **действие**: ``{ "command": …,
"args": […] }``. Так выражаются операции, у которых нет своего типа узла:
разложить на множители, раскрыть, упростить. Наш ``POST /solve`` принимает
необязательное поле ``action`` с командой.

Имена команд — наши (в APK они не восстановлены, кроме примера ``solve``):

* ``solve`` — решить/вычислить (поведение по умолчанию, без действия);
* ``factor`` — разложить на множители (``factorise_call``);
* ``expand`` — раскрыть (``expand_msg``);
* ``simplify`` — упростить (``simplify``);
* ``domain`` — область определения выражения (``domain_find``).

Для уравнения команда применяется к обеим частям.
"""

from __future__ import annotations

from collections.abc import Callable

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import Command, SolveContext, SolveError, Step
from .domain import domain, restrictions
from .matrices import MATRIX_COMMANDS
from .sympy_bridge import from_sympy, to_sympy
from .vectors import VECTOR_COMMANDS


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


def factor(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Разложить выражение на множители."""
    del args
    return _apply_side(node, ctx, "factorise_call", sympy.factor)


def expand(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Раскрыть скобки и формулы углов.

    ``trig=True`` раскрывает и тригонометрические формулы: ``sin(2x)``
    превращается в ``2·sin(x)·cos(x)``. Без него sympy оставил бы функцию
    как есть.
    """
    del args
    return _apply_side(node, ctx, "expand_msg", lambda expr: sympy.expand(expr, trig=True))


def simplify(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Упростить выражение."""
    del args
    return _apply_side(node, ctx, "simplify", sympy.simplify)


COMMANDS: dict[str, Command] = {
    "factor": factor,
    "expand": expand,
    "simplify": simplify,
    "domain": domain,
    "restrictions": restrictions,
    **VECTOR_COMMANDS,
    **MATRIX_COMMANDS,
}


def apply(
    command: str,
    node: CoreNode,
    ctx: SolveContext,
    args: list[CoreNode] | None = None,
) -> CoreNode:
    """Выполнить команду; неизвестная команда — ошибка."""
    handler = COMMANDS.get(command)
    if handler is None:
        raise SolveError(f"неизвестная команда {command!r}")
    return handler(node, ctx, list(args or []))


__all__ = [
    "COMMANDS",
    "Command",
    "apply",
    "domain",
    "expand",
    "factor",
    "simplify",
]
