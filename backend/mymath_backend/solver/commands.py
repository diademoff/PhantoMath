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
* ``domain`` — область определения выражения (``domain_find``);
* ``restrictions`` — недопустимые значения выражения (``rel_restrictions_find``);
* ``to_fraction`` — десятичную дробь в обыкновенную (``dec_to_frac``);
* ``to_percent`` — число в проценты (``rewrite_as_percent``);
* ``to_sci`` — число в экспоненциальную запись (``sci_form_msg``);
* ``to_mixed`` — неправильную дробь в смешанное число (``convert_improper_fraction``).

Для уравнения команда применяется к обеим частям.
"""

from __future__ import annotations

from collections.abc import Callable

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import Command, SolveContext, SolveError, Step, boolean_node
from .domain import domain, restrictions
from .integrals import area
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


def to_fraction(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Десятичную дробь — в обыкновенную."""
    del args
    return _apply_side(node, ctx, "dec_to_frac", sympy.nsimplify)


def to_percent(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Число — в проценты."""
    del args
    result = CoreNode.node(T.PERCENTAGE, from_sympy(sympy.sympify(to_sympy(node)) * 100))
    ctx.result.add(Step(left=node, right=result, key="rewrite_as_percent"))
    return result


def to_sci(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Число — в экспоненциальную запись ``a · 10ⁿ``."""
    del args
    value = to_sympy(node)
    if value.is_real is not True or value.is_number is not True:
        raise SolveError("экспоненциальная запись берётся у числа")
    if value == 0:
        result = CoreNode.constant("0")
    else:
        exponent = int(sympy.floor(sympy.log(abs(value), 10)))
        mantissa = float(value) / (10.0**exponent)
        power = CoreNode.node(T.POWER, CoreNode.constant("10"), CoreNode.constant(str(exponent)))
        result = CoreNode.node(T.MULTIPLY, CoreNode.constant(_trim(mantissa)), power)
    ctx.result.add(Step(left=node, right=result, key="sci_form_msg"))
    return result


def _trim(value: float) -> str:
    """Число без хвостового ``.0``."""
    text = repr(value)
    return text[:-2] if text.endswith(".0") else text


def to_mixed(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Неправильную дробь — в смешанное число."""
    del args
    value = sympy.nsimplify(to_sympy(node))
    if not isinstance(value, sympy.Rational) or value.q == 1:
        raise SolveError("смешанное число — из неправильной дроби")
    whole = sympy.Integer(sympy.floor(abs(value)))
    numerator = sympy.Integer(abs(value.p)) - whole * value.q
    if value < 0:
        whole = -whole
    result = CoreNode.node(
        T.FRACTION_MIXED,
        from_sympy(whole),
        from_sympy(numerator),
        from_sympy(sympy.Integer(value.q)),
    )
    ctx.result.add(Step(left=node, right=result, key="convert_improper_fraction"))
    return result


def prove(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Проверить, является ли равенство тождеством."""
    del args
    if node.type is not T.EQUALS or len(node.children) != 2:
        raise SolveError("доказывать нужно равенство")
    difference = sympy.simplify(to_sympy(node.children[0]) - to_sympy(node.children[1]))
    identity = difference == 0
    answer = boolean_node(identity)
    key = "prove_identity_true" if identity else "prove_identity_both_false"
    ctx.result.add(Step(left=node, right=answer, key=key))
    return answer


def substitute(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Подставить значение переменной в выражение."""
    if len(args) != 1:
        raise SolveError("нужно одно значение для подстановки")
    if len(ctx.variables) != 1:
        raise SolveError("подстановка: поддерживается одна переменная")
    symbol = sympy.Symbol(ctx.variables[0])
    result = from_sympy(sympy.simplify(to_sympy(node).subs(symbol, to_sympy(args[0]))))
    ctx.result.add(Step(left=node, right=result, key="substitute_value"))
    return result


def even_odd(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Определить чётность/нечётность функции."""
    del args
    expression_node = (
        node.children[1] if node.type is T.EQUALS and len(node.children) == 2 else node
    )
    if len(ctx.variables) != 1:
        raise SolveError("чётность: поддерживается одна переменная")
    symbol = sympy.Symbol(ctx.variables[0])
    expression = to_sympy(expression_node)
    negated = expression.subs(symbol, -symbol)
    if sympy.simplify(expression - negated) == 0:
        key = "function_even"
    elif sympy.simplify(expression + negated) == 0:
        key = "function_odd"
    else:
        key = "function_not_even_nor_odd"
    ctx.result.add(Step(left=node, right=None, key=key))
    return expression_node


COMMANDS: dict[str, Command] = {
    "factor": factor,
    "expand": expand,
    "simplify": simplify,
    "domain": domain,
    "restrictions": restrictions,
    "area": area,
    "even_odd": even_odd,
    "prove": prove,
    "substitute": substitute,
    "to_fraction": to_fraction,
    "to_mixed": to_mixed,
    "to_percent": to_percent,
    "to_sci": to_sci,
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
    "area",
    "domain",
    "even_odd",
    "expand",
    "factor",
    "prove",
    "restrictions",
    "simplify",
    "substitute",
    "to_fraction",
    "to_mixed",
    "to_percent",
    "to_sci",
]
