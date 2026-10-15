"""Область определения выражения (команда ``domain``).

Область определения — множество значений переменной, при которых выражение
определено (знаменатель не ноль, подкоренное выражение неотрицательно,
аргумент логарифма положителен и т.д.). Считает sympy
(``continuous_domain``), ответ выражается промежутками, их объединением или
разностью; всё множество действительных чисел — промежуток ``(-∞, +∞)``.

Шаг — ``domain_find``. Если область определения не выражается промежутками
(например, у ``tan`` она задаётся вычитанием периодического множества) —
:class:`SolveError`.
"""

from __future__ import annotations

import sympy
from sympy.calculus.util import continuous_domain

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step
from .sympy_bridge import from_sympy, to_sympy

_KEY = "domain_find"
_KEY_RESTRICTIONS = "rel_restrictions_find"


def all_reals() -> CoreNode:
    """Область определения как промежуток ``(-∞, +∞)``."""
    return from_sympy(sympy.S.Reals)


def domain(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Найти область определения выражения."""
    del args
    if node.type is T.EQUALS:
        raise SolveError("область определения берётся у выражения, а не у уравнения")

    expression = to_sympy(node)
    symbols = sorted(expression.free_symbols, key=lambda symbol: symbol.name)
    if len(symbols) > 1:
        raise SolveError("область определения: поддерживается одна переменная")

    answer = all_reals() if not symbols else _domain_of(expression, symbols[0])
    ctx.result.add(Step(left=node, right=answer, key=_KEY))
    return answer


def restrictions(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Найти недопустимые значения выражения (дополнение области определения).

    Знаменатель, аргумент логарифма, подкоренное выражение и т.п. дают
    значения, при которых выражение не определено. Ответ — множество
    (промежуток, объединение или конечное множество точек); если таких нет —
    ``EMPTY``.
    """
    del args
    if node.type is T.EQUALS:
        raise SolveError("недопустимые значения берутся у выражения, а не у уравнения")

    expression = to_sympy(node)
    symbols = sorted(expression.free_symbols, key=lambda symbol: symbol.name)
    if len(symbols) > 1:
        raise SolveError("недопустимые значения: поддерживается одна переменная")

    forbidden = sympy.EmptySet if not symbols else _forbidden(expression, symbols[0])
    answer = from_sympy(forbidden)
    key = "rel_restrictions_none" if answer.type is T.EMPTY else _KEY_RESTRICTIONS
    ctx.result.add(Step(left=node, right=answer, key=key))
    return answer


def _forbidden(expression: sympy.Expr, symbol: sympy.Symbol) -> sympy.Set:
    """Множество недопустимых значений: дополнение области определения."""
    try:
        allowed = continuous_domain(expression, symbol, sympy.S.Reals)
        return sympy.simplify(sympy.Complement(sympy.S.Reals, allowed))
    except (NotImplementedError, ValueError) as error:
        raise SolveError("недопустимые значения не выражаются") from error


def _domain_of(expression: sympy.Expr, symbol: sympy.Symbol) -> CoreNode:
    """Область определения выражения относительно переменной."""
    try:
        values = continuous_domain(expression, symbol, sympy.S.Reals)
        return from_sympy(values)
    except (NotImplementedError, ValueError) as error:
        raise SolveError("область определения не выражается промежутками") from error
    except SolveError as error:
        raise SolveError("область определения не выражается промежутками") from error


__all__ = [
    "all_reals",
    "domain",
    "restrictions",
]
