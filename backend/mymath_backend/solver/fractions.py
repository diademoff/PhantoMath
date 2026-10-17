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

from ..ast import CoreNode
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
        # Photomath: row 1 divides numerator and denominator, row 2 performs both divisions.
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
        ctx.result.add_group(
            "frac_reduce_frac",
            Step(node, divided, "frac_div_num", [CoreNode.constant(str(common))]),
        )
        # Photomath divides the numerator first, then the denominator (two stages).
        half = CoreNode.node(
            T.FRACTION,
            CoreNode.constant(format_number(numerator / common)),
            divided.children[1],
        )
        ctx.result.add_group("divide", Step(divided, half, "div"), Step(half, result, "div"))
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


Rows = list[tuple[str, list[Step]]]


def _sum_detail(op: T, terms: list[int]) -> SolveResult:
    """The numerators' arithmetic as its own screen (three or more terms)."""
    detail = SolveResult()
    total = CoreNode.node(op, *[CoreNode.constant(str(n)) for n in terms])
    detail.set_solution(route(total, SolveContext(result=detail)))
    return detail


def addition_rows(op: T, values: list[Fraction], result: CoreNode) -> Rows | None:
    """Sum/difference of numeric fractions as main steps, as Photomath 7.10.0 shows it.

    Rows (header key, step): numerators over the lowest common denominator (with a
    three-row detail: convert, calculate, convert), the arithmetic on numerators,
    and a reduction when the fraction is not in lowest terms.
    """
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
    scaled = [v.numerator * (common // v.denominator) for v in values]
    converted = CoreNode.node(op, *[fraction(number(n), number(common)) for n in scaled])
    combined = fraction(CoreNode.node(op, *map(number, scaled)), number(common))
    total_n = scaled[0] + sum(scaled[1:]) if op is T.ADD else scaled[0] - sum(scaled[1:])
    unreduced = fraction(number(total_n), number(common))

    expand = SolveResult()
    expand.add_group("frac_sum_expand", Step(original, expanded, "frac_sum_expand"))
    expand.add_group("calculate_short", Step(expanded, converted, "calculate_short"))
    expand.add_group("convert_expression", Step(converted, combined, "convert_expression"))
    expand.set_solution(combined)

    # Integer operand: converted to a fraction first; Photomath words it without the denominator.
    join = any(v.denominator == 1 for v in values)
    rows: Rows = [
        (
            "convert_expression",
            [
                Step(
                    original,
                    combined,
                    "frac_sum_join" if join else "frac_sum_common",
                    [] if join else [number(common)],
                    subresult=expand,
                )
            ],
        ),
        (
            "calculate_short" if len(values) == 2 else "calc_sum",
            [
                Step(
                    combined,
                    unreduced,
                    ("add" if op is T.ADD else "sub") if len(values) == 2 else "sum_real_positive",
                    subresult=None if len(values) == 2 else _sum_detail(op, scaled),
                )
            ],
        ),
    ]
    divisor = gcd(abs(total_n), common)
    if total_n == common:
        rows.append(("divide", [Step(unreduced, result, "div_with_self", [number(1)])]))
    elif divisor > 1:
        divided = fraction(
            CoreNode.node(T.DIVIDE, number(total_n), number(divisor)),
            CoreNode.node(T.DIVIDE, number(common), number(divisor)),
        )
        reduction = SolveResult()
        reduction.add_group(
            "frac_reduce_frac", Step(unreduced, divided, "frac_div_num", [number(divisor)])
        )
        reduction.add_group("divide", Step(divided, result, "div"))
        reduction.set_solution(result)
        rows.append(
            (
                "frac_reduce_frac",
                [Step(unreduced, result, "frac_reduce", [number(divisor)], subresult=reduction)],
            )
        )
    return rows


def _item(n: int, d: int) -> CoreNode:
    number = CoreNode.constant
    return number(str(n)) if d == 1 else CoreNode.node(T.FRACTION, number(str(n)), number(str(d)))


def _product(items: list[list[int]]) -> CoreNode:
    """Product of the items; factors equal to 1 are dropped like in Photomath's pages."""
    shown = [_item(n, d) for n, d in items if (n, d) != (1, 1)] or [_item(1, 1)]
    return shown[0] if len(shown) == 1 else CoreNode.node(T.MULTIPLY, *shown)


def product_rows(op: T, values: list[Fraction], result: CoreNode) -> Rows | None:
    """Product or quotient of two positive numeric operands as Photomath 7.10.0 shows it.

    Reciprocal (for division), then one page per cancellation by a common divisor of
    a numerator and another factor's denominator; if factors are left, either one
    "calculate the product" row (integer factor) or the join + calculate rows.
    """
    if op is T.DIVIDE and len(values) != 2:
        return None
    if (
        op not in (T.MULTIPLY, T.MULTIPLY_IMPLICIT, T.DIVIDE)
        or len(values) < 2
        or all(v.denominator == 1 for v in values)
        or any(v <= 0 for v in values)
    ):
        return None
    number = CoreNode.constant
    rows: Rows = []
    operands = [[v.numerator, v.denominator] for v in values]
    if op is T.DIVIDE:
        items = [operands[0], [operands[1][1], operands[1][0]]]
        rows.append(
            (
                "frac_div_rec_short",
                [
                    Step(
                        CoreNode.node(T.DIVIDE, *[_item(*o) for o in operands]),
                        _product(items),
                        "frac_div_rec",
                    )
                ],
            )
        )
    else:
        items = operands
    current = _product(items)
    pages: list[Step] = []
    while pair := next(
        (
            (i, j, gcd(items[i][0], items[j][1]))
            for i in range(len(items))
            for j in range(len(items))
            if i != j and gcd(items[i][0], items[j][1]) > 1
        ),
        None,
    ):
        i, j, g = pair
        items[i][0] //= g
        items[j][1] //= g
        following = _product(items)
        pages.append(Step(current, following, "frac_reduce_out", [number(str(g))]))
        current = following
    if pages:
        rows.append(("frac_reduce_num", pages))
    left = [it for it in items if tuple(it) != (1, 1)]
    if len(left) > 1:
        numerators = CoreNode.node(T.MULTIPLY, *[number(str(n)) for n, _ in left])
        denominators = CoreNode.node(T.MULTIPLY, *[number(str(d)) for _, d in left])
        joined = CoreNode.node(T.FRACTION, numerators, denominators)
        top = 1
        for n, _ in left:
            top *= n
        bottom = 1
        for _, d in left:
            bottom *= d
        half = CoreNode.node(T.FRACTION, number(str(top)), denominators)
        done = _item(top, bottom)
        calc = [
            Step(
                joined,
                half,
                "mul_with_one"
                if sorted(n for n, _ in left)[:-1] == [1] * (len(left) - 1)
                else "mul",
                [number("1")] if sorted(n for n, _ in left)[:-1] == [1] * (len(left) - 1) else [],
            )
        ]
        if bottom != 1:
            calc.append(Step(half, done, "mul"))
        if any(d == 1 for _, d in left):
            detail = SolveResult()
            detail.add_group("frac_mul", Step(current, joined, "frac_mul_join"))
            detail.add_group("calculate_short", *calc)
            detail.set_solution(result)
            rows.append(("product", [Step(current, result, "product", subresult=detail)]))
        else:
            rows.append(("frac_mul", [Step(current, joined, "frac_mul_join")]))
            rows.append(("calculate_short", calc))
    return rows or None


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
