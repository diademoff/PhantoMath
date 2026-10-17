"""Дроби: сокращение и преобразование смешанных чисел.

Модуль зарегистрирован на узлы ``FRACTION`` и ``FRACTION_MIXED``. Он делает
две вещи:

* сокращает дробь и возвращает её числовым значением (``CONSTANT``) --
  дальше с ним работает арифметика, поэтому ``1/3 + 1/6`` складывается;
* переводит смешанное число в неправильную дробь (``2 1/3`` -> ``7/3``).

Ключи шагов: ``frac_reduce_out`` (ARG1 -- общий делитель),
``div_with_one`` (ARG1 -- знаменатель, если он равен единице) и
``convert_mixed_number``. Алгебраические дроби (с неизвестным) -- следующий
модуль, здесь они отклоняются.
"""

from __future__ import annotations

from fractions import Fraction
from math import gcd, lcm

from ..ast import CoreNode, colored
from ..node_types import CoreNodeType as T
from .arithmetic import as_fraction, format_number
from .base import SolveContext, SolveResult, Step, route, solver_for


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
        divided = CoreNode.node(
            T.FRACTION,
            CoreNode.node(
                T.DIVIDE,
                CoreNode.constant(format_number(numerator)),
                CoreNode.constant(str(common)),
            ),
            CoreNode.node(
                T.DIVIDE,
                CoreNode.constant(format_number(denominator)),
                CoreNode.constant(str(common)),
            ),
        )
        reduced = CoreNode.node(
            T.FRACTION,
            CoreNode.constant(format_number(numerator / common)),
            CoreNode.constant(format_number(denominator / common)),
        )
        detail = SolveResult(header="lesson_fraction")
        detail.add_group(
            "lesson_fraction",
            Step(node, divided, "lesson_gcd", [CoreNode.constant(str(common))]),
            Step(divided, reduced, "lesson_fraction_divide"),
            Step(reduced, result, "lesson_fraction_finish"),
        )
        detail.set_solution(result)
        ctx.result.add_group(
            "lesson_fraction",
            Step(left=crossed, right=None, key="frac_reduce_reduce"),
            Step(
                left=crossed,
                right=result,
                key="frac_reduce_out",
                args=[CoreNode.constant(str(common))],
                subresult=detail,
            ),
        )
    elif denominator == 1:
        # Дробь со знаменателем 1 — то же деление на единицу, что и `6 ÷ 1`
        # (`div_with_one` в арифметике). Без шага экран «Шаги по решению»
        # оставался пустым, хотя запись менялась: `frac(6,1)` → `6`.
        ctx.result.add(
            Step(
                left=node,
                right=result,
                key="div_with_one",
                args=[node.children[1]],
            )
        )
    elif numerator.denominator != 1 or denominator.denominator != 1:
        ctx.result.add_group(
            "lesson_fraction_product",
            Step(
                node,
                result,
                "div",
                subresult=product_detail(T.DIVIDE, [numerator, denominator], result),
            ),
        )
    return result


def product_detail(op: T, values: list[Fraction], result: CoreNode) -> SolveResult | None:
    """Exact multiplication/reciprocal steps, including nested numeric fractions."""
    if (
        op not in (T.MULTIPLY, T.MULTIPLY_IMPLICIT, T.DIVIDE)
        or len(values) < 2
        or all(v.denominator == 1 for v in values)
    ):
        return None

    def number(n: int) -> CoreNode:
        return CoreNode.constant(str(n))

    def fraction(value: Fraction) -> CoreNode:
        return CoreNode.node(T.FRACTION, number(value.numerator), number(value.denominator))

    original = CoreNode.node(op, *map(fraction, values))
    detail = SolveResult(header="lesson_fraction_product")
    factors = [values[0], *[1 / v if op is T.DIVIDE else v for v in values[1:]]]
    multiplied = CoreNode.node(T.MULTIPLY, *map(fraction, factors))
    current = original
    if op is T.DIVIDE:
        detail.add_group(
            "lesson_fraction_product", Step(current, multiplied, "lesson_fraction_reciprocal")
        )
        current = multiplied
    products = CoreNode.node(
        T.FRACTION,
        CoreNode.node(T.MULTIPLY, *[number(v.numerator) for v in factors]),
        CoreNode.node(T.MULTIPLY, *[number(v.denominator) for v in factors]),
    )
    detail.add_group(
        "lesson_fraction_product",
        Step(current, products, "lesson_fraction_multiply"),
        Step(products, result, "lesson_fraction_finish"),
    )
    detail.set_solution(result)
    return detail


def addition_detail(op: T, values: list[Fraction], result: CoreNode) -> SolveResult | None:
    """A common-denominator derivation for a numeric sum/difference of fractions."""
    if op not in (T.ADD, T.SUBTRACT) or len(values) < 2 or all(v.denominator == 1 for v in values):
        return None
    common = lcm(*(value.denominator for value in values))

    def number(value: int) -> CoreNode:
        return CoreNode.constant(str(value))

    def fraction(n: CoreNode, d: CoreNode) -> CoreNode:
        return CoreNode.node(T.FRACTION, n, d)

    original = CoreNode.node(
        op, *[fraction(number(v.numerator), number(v.denominator)) for v in values]
    )
    expanded = CoreNode.node(
        op,
        *[
            fraction(
                CoreNode.node(T.MULTIPLY, number(v.numerator), number(common // v.denominator)),
                CoreNode.node(T.MULTIPLY, number(v.denominator), number(common // v.denominator)),
            )
            for v in values
        ],
    )
    numerators = [number(v.numerator * (common // v.denominator)) for v in values]
    converted = CoreNode.node(op, *[fraction(n, number(common)) for n in numerators])
    combined = fraction(CoreNode.node(op, *numerators), number(common))
    total = values[0] + sum(values[1:]) if op is T.ADD else values[0] - sum(values[1:])
    unreduced_n = (
        sum(v.numerator * (common // v.denominator) for v in values)
        if op is T.ADD
        else values[0].numerator * (common // values[0].denominator)
        - sum(v.numerator * (common // v.denominator) for v in values[1:])
    )
    unreduced = fraction(number(unreduced_n), number(common))
    reduction = SolveResult()
    divisor = gcd(abs(unreduced_n), common)
    if divisor > 1:
        divided = fraction(
            CoreNode.node(T.DIVIDE, number(unreduced_n), number(divisor)),
            CoreNode.node(T.DIVIDE, number(common), number(divisor)),
        )
        reduction.add_group(
            "lesson_fraction",
            Step(unreduced, divided, "lesson_gcd", [number(divisor)]),
            Step(divided, result, "lesson_fraction_divide"),
        )
        reduction.set_solution(result)
    detail = SolveResult(header="lesson_fraction_sum")
    detail.add_group(
        "lesson_fraction_sum",
        Step(original, expanded, "lesson_common_denominator", [number(common)]),
        Step(expanded, converted, "lesson_simplify"),
        Step(converted, combined, "lesson_combine_numerators"),
        Step(combined, unreduced, "lesson_fraction_finish"),
        Step(
            unreduced, result, "lesson_fraction_finish", subresult=reduction if reduction else None
        ),
    )
    detail.set_solution(CoreNode.constant(format_number(total)))
    return detail


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
