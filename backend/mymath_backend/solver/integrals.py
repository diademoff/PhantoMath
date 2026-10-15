"""Интегралы: неопределённый и определённый.

Модуль зарегистрирован на ``INTEGRAL`` (первообразная) и
``INTEGRAL_DEFINITE`` (``[нижний, верхний, выражение]``). Считает sympy:
первообразная ищется ``integrate``, результат переводится обратно в
``CoreNode`` мостом :mod:`~mymath_backend.solver.sympy_bridge`.

Если элементарной первообразной нет (``∫e^{x²}dx``), поднимается
:class:`SolveError` — это ожидаемый исход, а не сбой.

Шаг один — ``integrate_calc``.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step, solver_for
from .sympy_bridge import from_sympy, to_sympy


def _variable(ctx: SolveContext) -> sympy.Symbol:
    """Переменная интегрирования: единственная свободная или ``x``."""
    return sympy.Symbol(ctx.variables[0] if ctx.variables else "x")


@solver_for(T.INTEGRAL, T.INTEGRAL_DEFINITE)
def solve_integral(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Взять интеграл через sympy."""
    ctx.require(len(ctx.variables) <= 1, "поддерживается одно неизвестное")
    symbol = _variable(ctx)

    if node.type is T.INTEGRAL:
        ctx.require(len(node.children) >= 1, "интеграл без подынтегрального выражения")
        antiderivative = sympy.integrate(to_sympy(node.children[-1]), symbol)
        if antiderivative.has(sympy.Integral):
            raise SolveError("первообразная не выражается через элементарные функции")
        try:
            result = from_sympy(sympy.simplify(antiderivative))
        except SolveError as err:
            # sympy вернул специальную функцию (erfi, Ei, …): элементарной
            # первообразной нет, и в наш AST это не переводится.
            raise SolveError("первообразная не выражается через элементарные функции") from err
    else:
        ctx.require(len(node.children) == 3, "определённый интеграл: пределы и выражение")
        lower, upper, expression = node.children
        value = sympy.integrate(
            to_sympy(expression),
            (symbol, to_sympy(lower), to_sympy(upper)),
        )
        if value.has(sympy.Integral) or value is sympy.oo:
            raise SolveError("определённый интеграл не вычисляется")
        result = from_sympy(sympy.simplify(value))

    ctx.result.add(Step(left=node, right=result, key="integrate_calc"))
    return result


__all__ = [
    "solve_integral",
]
