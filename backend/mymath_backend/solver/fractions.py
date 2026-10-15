"""Дроби: сокращение и преобразование смешанных чисел.

Модуль зарегистрирован на узлы ``FRACTION`` и ``FRACTION_MIXED``. Он делает
две вещи:

* сокращает дробь и возвращает её числовым значением (``CONSTANT``) --
  дальше с ним работает арифметика, поэтому ``1/3 + 1/6`` складывается;
* переводит смешанное число в неправильную дробь (``2 1/3`` -> ``7/3``).

Ключи шагов: ``frac_reduce_out`` (ARG1 -- общий делитель) и
``convert_mixed_number``. Алгебраические дроби (с неизвестным) -- следующий
модуль, здесь они отклоняются.
"""

from __future__ import annotations

from fractions import Fraction
from math import gcd

from ..ast import CoreNode, colored
from ..node_types import CoreNodeType as T
from .arithmetic import as_fraction, format_number
from .base import SolveContext, Step, route, solver_for


def _fold(node: CoreNode, ctx: SolveContext) -> Fraction:
    """Свернуть подвыражение и прочитать как число."""
    return as_fraction(route(node, ctx))


def _integer_common_divisor(numerator: Fraction, denominator: Fraction) -> int | None:
    """Общий делитель целых числителя и знаменателя, если оба целые."""
    if numerator.denominator != 1 or denominator.denominator != 1:
        return None
    divisor = gcd(abs(numerator.numerator), abs(denominator.numerator))
    return divisor if divisor > 1 else None


@solver_for(T.FRACTION, T.FRACTION_MIXED)
def solve_fraction(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Сократить дробь или преобразовать смешанное число.

    Возвращает числовую константу со значением дроби; для неправильной
    дроби со общим делителем добавляется шаг сокращения.
    """
    if node.type is T.FRACTION_MIXED:
        return _solve_mixed(node, ctx)
    return _solve_fraction(node, ctx)


def _solve_fraction(node: CoreNode, ctx: SolveContext) -> CoreNode:
    ctx.require(len(node.children) == 2, "у дроби должны быть числитель и знаменатель")
    numerator = _fold(node.children[0], ctx)
    denominator = _fold(node.children[1], ctx)
    ctx.require(denominator != 0, "деление на ноль", "div_with_zero")

    value = numerator / denominator
    result = CoreNode.constant(format_number(value))
    common = _integer_common_divisor(numerator, denominator)
    if common is not None:
        # Микро-анимация: показываем, что числитель и знаменатель сокращаются.
        crossed = CoreNode.node(
            T.FRACTION,
            colored(CoreNode.constant(format_number(numerator)), crossed=True),
            colored(CoreNode.constant(format_number(denominator)), crossed=True),
        )
        ctx.result.add(
            Step(
                left=crossed,
                right=result,
                key="frac_reduce_out",
                args=[CoreNode.constant(str(common))],
            )
        )
    return result


def _solve_mixed(node: CoreNode, ctx: SolveContext) -> CoreNode:
    ctx.require(
        len(node.children) == 3,
        "у смешанного числа должны быть целая часть, числитель и знаменатель",
    )
    whole = _fold(node.children[0], ctx)
    numerator = _fold(node.children[1], ctx)
    denominator = _fold(node.children[2], ctx)
    ctx.require(denominator != 0, "деление на ноль", "div_with_zero")

    value = whole + numerator / denominator
    result = CoreNode.constant(format_number(value))
    ctx.result.add(Step(left=node, right=result, key="convert_mixed_number"))
    return result


__all__ = [
    "solve_fraction",
]
