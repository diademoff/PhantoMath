"""Комбинаторика: факториал, биномиальный коэффициент, перестановки, размещения.

Модуль зарегистрирован на ``FACTORIAL``, ``CHOOSE``,
``CHOOSE_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT``,
``PARTIAL_PERMUTATION_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT`` и ``VARIATION``.
Аргументы должны быть целыми: ``n`` -- неотрицательное, ``k`` -- ``0 ≤ k ≤ n``.

Шаги: ``factorial_calculate``, ``choose_calculate``,
``permutation_calculate``, ``variation_not_allowed_calculate``.
"""

from __future__ import annotations

from math import comb, factorial, perm

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .arithmetic import as_fraction
from .base import SolveContext, SolveError, Step, route, solver_for

_CHOOSES = (T.CHOOSE, T.CHOOSE_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT)
_ARRANGEMENTS = (T.PARTIAL_PERMUTATION_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT, T.VARIATION)

_MAX_FACTORIAL = 1000


def _integer(node: CoreNode, ctx: SolveContext, message: str) -> int:
    value = as_fraction(route(node, ctx))
    if value.denominator != 1 or value.numerator < 0:
        raise SolveError(message)
    return value.numerator


@solver_for(T.FACTORIAL)
def solve_factorial(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить факториал целого неотрицательного числа."""
    argument = _integer(
        node.children[0], ctx, "факториал определён только для целых неотрицательных чисел"
    )
    ctx.require(argument <= _MAX_FACTORIAL, "факториал слишком большой")
    result = CoreNode.constant(str(factorial(argument)))
    ctx.result.add(Step(left=node, right=result, key="factorial_calculate"))
    return result


@solver_for(*_CHOOSES)
def solve_choose(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить биномиальный коэффициент ``C(n, k)``."""
    ctx.require(len(node.children) == 2, "биномиальный коэффициент задаётся двумя числами")
    n = _integer(node.children[0], ctx, "C(n, k) определён только для целых неотрицательных")
    k = _integer(node.children[1], ctx, "C(n, k) определён только для целых неотрицательных")
    ctx.require(k <= n, "для C(n, k) нужно k ≤ n")
    result = CoreNode.constant(str(comb(n, k)))
    ctx.result.add(Step(left=node, right=result, key="choose_calculate"))
    return result


@solver_for(*_ARRANGEMENTS)
def solve_arrangement(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить число перестановок/размещений ``P(n, k)``."""
    ctx.require(len(node.children) == 2, "перестановка задаётся двумя числами")
    n = _integer(node.children[0], ctx, "перестановка определена только для целых неотрицательных")
    k = _integer(node.children[1], ctx, "перестановка определена только для целых неотрицательных")
    ctx.require(k <= n, "для перестановки нужно k ≤ n")
    key = "variation_not_allowed_calculate" if node.type is T.VARIATION else "permutation_calculate"
    result = CoreNode.constant(str(perm(n, k)))
    ctx.result.add(Step(left=node, right=result, key=key))
    return result


__all__ = [
    "solve_arrangement",
    "solve_choose",
    "solve_factorial",
]
