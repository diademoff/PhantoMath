"""Дроби: сокращение и преобразование смешанных чисел.

Модуль зарегистрирован на узлы ``FRACTION`` и ``FRACTION_MIXED``. Он делает
две вещи:

* сокращает дробь и возвращает её числовым значением (``CONSTANT``) --
  дальше с ним работает арифметика, поэтому ``1/3 + 1/6`` складывается;
* переводит смешанное число в неправильную дробь (``2 1/3`` -> ``7/3``).

Ключи шагов: ``frac_reduce_out`` (ARG1 -- общий делитель), ``frac_div_num``
(ARG1 -- делитель числителя и знаменателя), ``div_with_one`` (ARG1 -- знаменатель,
если он равен единице) и ``mfrac_to_frac``. Сложение дробей и деление на дробь
живут в :func:`addition_rows` / :func:`product_rows`: их экраны подробностей
повторяют последовательность строк (``mul_with_one``, ``mul``,
``frac_sum_join``, ``product``, ``frac_reduce_frac_num``). Алгебраические дроби
(с неизвестным) -- следующий модуль, здесь они отклоняются.
"""

from __future__ import annotations

from fractions import Fraction
from math import gcd, lcm

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .arithmetic import as_fraction, format_number
from .base import (
    SolveContext,
    SolveError,
    SolveResult,
    Step,
    UndefinedError,
    route,
    solver_for,
)
from .methods import method_provider


def _fold(node: CoreNode, ctx: SolveContext) -> Fraction:
    """Свернуть подвыражение и прочитать как число."""
    folded = route(node, ctx)
    if folded.type is T.BRACKET and len(folded.children) == 1:
        folded = folded.children[0]  # (8) is the number 8
    return as_fraction(folded)


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
    if denominator == 0:
        raise UndefinedError(
            "деление на ноль", "div_with_zero", explanation_args=[CoreNode.constant("0")]
        )

    value = numerator / denominator
    result = CoreNode.constant(format_number(value))
    common = _integer_common_divisor(numerator, denominator)
    if common is not None:
        # row 1 divides numerator and denominator, row 2 performs both divisions.
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
        # A computed numerator (``(1+1)/4``) gets the wrapper card: the reduction
        # screen is nested under ``frac_reduce_frac_num``. A plain ``6/8`` stays flat.
        target = ctx.result
        detail = SolveResult() if node.children[0].type is not T.CONSTANT else None
        if detail is not None:
            target = detail
            detail.set_solution(result)
        target.add_group(
            "frac_reduce_frac",
            Step(
                result if detail is not None else node,
                divided,
                "frac_div_num",
                [CoreNode.constant(str(common))],
            ),
        )
        # The app divides the numerator first, then the denominator (two stages).
        reduced_numerator = CoreNode.constant(format_number(numerator / common))
        half = CoreNode.node(T.FRACTION, reduced_numerator, divided.children[1])
        if value.denominator == 1:
            # The denominator becomes 1: The app reads `3/1` as `3` on its own row.
            whole = CoreNode.node(
                T.FRACTION,
                reduced_numerator,
                CoreNode.constant(format_number(denominator / common)),
            )
            target.add_group("divide", Step(divided, half, "div"), Step(half, whole, "div"))
            target.add_group(
                "divide", Step(whole, result, "div_with_one", [CoreNode.constant("1")])
            )
        else:
            target.add_group("divide", Step(divided, half, "div"), Step(half, result, "div"))
        if detail is not None:
            ctx.result.add_group(
                "frac_reduce_frac",
                Step(
                    result,
                    result,
                    "frac_reduce_frac_num",
                    [CoreNode.constant(str(common))],
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


def _percent_card(
    node: CoreNode, numerator: Fraction, denominator: Fraction, value: Fraction
) -> SolveResult | None:
    """The percentage card: multiply by ``k/k`` so the denominator becomes 100."""
    number = CoreNode.constant
    if numerator.denominator != 1 or denominator.denominator != 1 or denominator == 0:
        return None
    n, d = int(numerator), int(denominator)
    if 100 % d == 0:
        top, bottom = n, d
    elif 100 % value.denominator == 0:
        top, bottom = value.numerator, value.denominator
    else:
        return None
    factor = 100 // bottom
    percent = top * factor
    value_node = number(format_number(value))
    product = CoreNode.node(T.MULTIPLY, number("1"), value_node)
    joined = CoreNode.node(
        T.FRACTION,
        CoreNode.node(T.MULTIPLY, number(str(factor)), number(str(top))),
        CoreNode.node(T.MULTIPLY, number(str(bottom)), number(str(factor))),
    )
    numerator_done = CoreNode.node(T.FRACTION, number(str(percent)), joined.children[1])
    denominator_done = CoreNode.node(T.FRACTION, number(str(percent)), number(str(100)))
    detail = SolveResult()
    detail.add_group(
        "expand_msg",
        Step(
            value_node,
            product,
            "frac_mul_expand",
            [CoreNode.node(T.FRACTION, number(str(factor)), number(str(factor)))],
        ),
    )
    detail.add_group("frac_mul", Step(product, joined, "frac_mul_join"))
    denominator_step = (
        Step(
            numerator_done,
            denominator_done,
            "mul_with_one",
            [number("1")],
        )
        if bottom == 1
        else Step(numerator_done, denominator_done, "mul")
    )
    detail.add_group(
        "multiply",
        Step(joined, numerator_done, "mul"),
        denominator_step,
    )
    p = CoreNode.variable("p")
    law = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.FRACTION, p, number("100")),
        CoreNode.node(T.PERCENTAGE, p),
    )
    percentage = CoreNode.node(T.PERCENTAGE, number(str(percent)))
    detail.add_group(
        "calculate_short",
        Step(denominator_done, percentage, "by_definition", [law]),
    )
    detail.set_solution(percentage)
    card = SolveResult()
    original_gcd = gcd(abs(n), abs(d))
    if value.denominator != 1 and original_gcd > 1:
        reduction = SolveResult()
        divided = CoreNode.node(
            T.FRACTION,
            CoreNode.node(T.DIVIDE, number(str(n)), number(str(original_gcd))),
            CoreNode.node(T.DIVIDE, number(str(d)), number(str(original_gcd))),
        )
        reduction.add_group(
            "frac_reduce_frac",
            Step(
                value_node,
                divided,
                "frac_div_num",
                [number(str(original_gcd))],
            ),
        )
        half = CoreNode.node(
            T.FRACTION,
            number(str(n // original_gcd)),
            divided.children[1],
        )
        reduction.add_group(
            "divide",
            Step(divided, half, "div"),
            Step(half, value_node, "div"),
        )
        reduction.set_solution(value_node)
        card.add_group(
            "frac_reduce_frac",
            Step(
                value_node,
                value_node,
                "frac_reduce_frac_num",
                [number(str(original_gcd))],
                subresult=reduction,
            ),
        )
    card.add_group(
        "rewrite_expression",
        Step(value_node, value_node, "write_as_decimal_frac", subresult=detail),
    )
    card.set_solution(percentage)
    return card


@method_provider(T.FRACTION)
def fraction_percent_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """A numeric fraction: the reduction card and (when exact) the percentage card."""
    if len(node.children) != 2:
        return []
    scratch = SolveResult()
    try:
        numerator = _fold(
            node.children[0],
            SolveContext(result=scratch, variables=list(variables)),
        )
        denominator = _fold(
            node.children[1],
            SolveContext(result=scratch, variables=list(variables)),
        )
    except SolveError:
        return []
    if denominator == 0:
        return []
    plain = SolveResult()
    value = solve_fraction(node, SolveContext(result=plain, variables=list(variables)))
    plain.set_solution(value)
    if node.children[0].type is not T.CONSTANT:
        # A computed numerator gets the reduction wrapper; the card shows no percent card for it.
        return [plain]
    percent = _percent_card(node, numerator, denominator, as_fraction(value))
    if percent is None:
        return [plain]
    return [plain, percent]


def _fraction_parts(node: CoreNode) -> tuple[int, int] | None:
    """``(1, d)`` for a unit fraction ``1/d`` with an integer denominator."""
    if node.type is not T.FRACTION or len(node.children) != 2:
        return None
    numerator, denominator = node.children
    if (
        numerator.type is not T.CONSTANT
        or numerator.value != "1"
        or denominator.type is not T.CONSTANT
        or denominator.value is None
    ):
        return None
    try:
        value = int(denominator.value)
    except ValueError:
        return None
    return (1, value) if value > 0 else None


def _negative_power_card(
    node: CoreNode, first: tuple[int, int], second: tuple[int, int]
) -> SolveResult:
    """``1/a · 1/b`` as ``a⁻¹·b⁻¹ = (ab)⁻¹`` (the alternative card)."""
    eq, num = CoreNode.node, CoreNode.constant
    a, b = first[1], second[1]
    fr1, fr2 = node.children
    start = node
    first_step = eq(T.MULTIPLY, fr2, eq(T.POWER, num(str(a)), eq(T.NEGATIVE, num("1"))))
    second_step = eq(
        T.MULTIPLY,
        eq(T.POWER, num(str(a)), eq(T.NEGATIVE, num("1"))),
        eq(T.POWER, num(str(b)), eq(T.NEGATIVE, num("1"))),
    )
    x, n = CoreNode.variable("x"), CoreNode.variable("n")
    law = eq(
        T.EQUALS,
        eq(T.FRACTION, num("1"), eq(T.POWER, x, n)),
        eq(T.POWER, x, eq(T.NEGATIVE, n)),
    )
    card = SolveResult()
    card.add_group(
        "trans_msg_plural",
        Step(start, first_step, "using_trans", [law]),
        Step(first_step, second_step, "using_trans", [law]),
    )
    product = eq(T.POWER, eq(T.MULTIPLY, num(str(a)), num(str(b))), eq(T.NEGATIVE, num("1")))
    answer = eq(T.POWER, num(str(a * b)), eq(T.NEGATIVE, num("1")))
    detail = SolveResult()
    detail.add_group("product", Step(second_step, product, "pow_same_exp_mul"))
    detail.add_group(
        "multiply",
        Step(product, answer, "mul"),
    )
    detail.set_solution(answer)
    card.add_group("product", Step(second_step, answer, "pow_same_exp_mul", subresult=detail))
    card.set_solution(answer)
    _ = fr1
    return card


@method_provider(T.MULTIPLY, T.MULTIPLY_IMPLICIT)
def fraction_product_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """A product of two unit fractions: the plain card plus the negative powers."""
    if len(node.children) != 2:
        return []
    first = _fraction_parts(node.children[0])
    second = _fraction_parts(node.children[1])
    if first is None or second is None:
        return []
    plain = SolveResult()
    answer = route(node, SolveContext(result=plain, variables=list(variables)))
    plain.set_solution(answer)
    return [plain, _negative_power_card(node, first, second)]


@method_provider(T.DIVIDE)
def divide_by_one_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """``n / 1``: the division card and the percentage card."""
    if len(node.children) != 2:
        return []
    scratch = SolveResult()
    try:
        numerator = _fold(
            node.children[0],
            SolveContext(result=scratch, variables=list(variables)),
        )
        denominator = _fold(
            node.children[1],
            SolveContext(result=scratch, variables=list(variables)),
        )
    except SolveError:
        return []
    if denominator != 1 or numerator.denominator != 1:
        return []
    plain = SolveResult()
    answer = route(node, SolveContext(result=plain, variables=list(variables)))
    plain.set_solution(answer)
    percent = _percent_card(node, numerator, denominator, as_fraction(answer))
    if percent is None:
        return [plain]
    return [plain, percent]


def _decimal_places(value: Fraction, places: int) -> Fraction:
    """Round a positive fraction to ``places`` decimal digits (the five-digit reading)."""
    scale = 10**places
    scaled = value * scale
    rounded = (scaled.numerator * 2 + scaled.denominator) // (2 * scaled.denominator)
    return Fraction(rounded, scale)


@method_provider(T.FRACTION_MIXED)
def mixed_number_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """A mixed number: the improper fraction, its decimal reading and its percentage."""
    if len(node.children) != 3:
        return []
    scratch = SolveResult()
    try:
        whole = _fold(
            node.children[0],
            SolveContext(result=scratch, variables=list(variables)),
        )
        numerator = _fold(
            node.children[1],
            SolveContext(result=scratch, variables=list(variables)),
        )
        denominator = _fold(
            node.children[2],
            SolveContext(result=scratch, variables=list(variables)),
        )
    except SolveError:
        return []
    if denominator == 0:
        return []
    primary = SolveResult()
    answer = _solve_mixed(node, SolveContext(result=primary, variables=list(variables)))
    primary.set_solution(answer)
    value = whole + numerator / denominator
    if value <= 0:
        return [primary]
    number = CoreNode.constant
    approximate = _decimal_places(value, 5)
    rounded = _decimal_places(value, 4)
    approx_node = number(format_number(approximate))
    rounded_node = number(format_number(rounded))
    approximate_card = SolveResult()
    approximate_card.add_group("calculate_short", Step(node, approx_node, "calculate"))
    approximate_card.set_solution(approx_node)

    # The primary card becomes the nested page of the first row.
    nested = SolveResult()
    _solve_mixed(node, SolveContext(result=nested, variables=list(variables)))
    nested.set_solution(answer)
    decimal_card = SolveResult()
    decimal_card.add_group(
        "convert_expression",
        Step(node, answer, "mfrac_to_frac", subresult=nested),
    )
    decimal_card.add_group("calculate_short", Step(answer, approx_node, "calculate"))
    decimal_card.add_group("round", Step(approx_node, rounded_node, "round4"))
    scaled = CoreNode.node(T.MULTIPLY, number("1"), rounded_node)
    joined = CoreNode.node(
        T.FRACTION,
        CoreNode.node(T.MULTIPLY, number("100"), rounded_node),
        number("100"),
    )
    rewrite = SolveResult()
    rewrite.add_group(
        "expand_msg",
        Step(
            rounded_node,
            scaled,
            "limit_expand_expression",
            [CoreNode.node(T.FRACTION, number("100"), number("100"))],
        ),
    )
    rewrite.add_group("calculate_short", Step(scaled, joined, "product"))
    rewrite.add_group("multiply", Step(joined, rounded_node, "mul"))
    rewrite.set_solution(rounded_node)
    decimal_card.add_group(
        "rewrite_expression",
        Step(rounded_node, rounded_node, "write_as_decimal_frac", subresult=rewrite),
    )
    percentage_value = rounded * 100
    p = CoreNode.variable("p")
    law = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.FRACTION, p, number("100")),
        CoreNode.node(T.PERCENTAGE, p),
    )
    decimal_card.add_group(
        "calculate_short",
        Step(
            rounded_node,
            CoreNode.node(T.PERCENTAGE, number(format_number(percentage_value))),
            "by_definition",
            [law],
        ),
    )
    decimal_card.set_solution(CoreNode.node(T.PERCENTAGE, number(format_number(percentage_value))))
    return [primary, decimal_card, approximate_card]


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


def _replace_child(node: CoreNode, index: int, child: CoreNode) -> CoreNode:
    """Copy ``node`` with one operand replaced (the other operands stay as they are)."""
    children = list(node.children)
    children[index] = child
    return CoreNode.node(node.type, *children)


def _sum_detail(op: T, terms: list[int]) -> SolveResult:
    """The numerators' arithmetic as its own screen (three or more terms).

    The app adds them pairwise, so ``(3+2)+1`` is two rows and not one n-ary sum.
    """
    chain = CoreNode.constant(str(terms[0]))
    for term in terms[1:]:
        chain = CoreNode.node(op, chain, CoreNode.constant(str(term)))
    detail = SolveResult()
    detail.set_solution(route(chain, SolveContext(result=detail)))
    return detail


def integer_reduction_rows(numerator: int, denominator: int) -> SolveResult | None:
    """Rows the app shows when a fraction reduces to a whole number.

    ``100/4``: divide both parts by the denominator (``frac_div_num``), perform the
    two divisions, then read ``25/1`` as ``25`` (``div_with_one``). Used both for a
    stand-alone fraction and for one operand inside a larger expression.
    """
    if denominator <= 1 or numerator % denominator != 0:
        return None
    number = CoreNode.constant

    def fraction(n: int, d: int) -> CoreNode:
        return CoreNode.node(T.FRACTION, number(str(n)), number(str(d)))

    original = fraction(numerator, denominator)
    divided = CoreNode.node(
        T.FRACTION,
        CoreNode.node(T.DIVIDE, number(str(numerator)), number(str(denominator))),
        CoreNode.node(T.DIVIDE, number(str(denominator)), number(str(denominator))),
    )
    quotient = numerator // denominator
    detail = SolveResult()
    detail.add_group(
        "frac_reduce_frac",
        Step(original, divided, "frac_div_num", [number(str(denominator))]),
    )
    halves = CoreNode.node(T.FRACTION, number(str(quotient)), divided.children[1])
    detail.add_group(
        "divide",
        Step(divided, halves, "div"),
        Step(halves, fraction(quotient, 1), "div"),
    )
    detail.add_group(
        "divide", Step(fraction(quotient, 1), number(str(quotient)), "div_with_one", [number("1")])
    )
    detail.set_solution(number(str(quotient)))
    return detail


def addition_rows(op: T, values: list[Fraction], result: CoreNode) -> Rows | None:
    """Sum/difference of numeric fractions as main steps, as the app shows it.

    Rows (header key, step): numerators over the lowest common denominator, the
    arithmetic on numerators, and a reduction when the fraction is not in lowest
    terms. The first row's detail screen is its own sequence: expand each
    fraction, evaluate every numerator/denominator product (``mul_with_one`` when a
    factor is 1), then write the numerators over the common denominator.
    """
    if op not in (T.ADD, T.SUBTRACT) or len(values) < 2 or all(v.denominator == 1 for v in values):
        return None
    common = lcm(*(value.denominator for value in values))

    def number(value: int) -> CoreNode:
        return CoreNode.constant(str(value))

    def fraction(n: CoreNode, d: CoreNode) -> CoreNode:
        return CoreNode.node(T.FRACTION, n, d)

    def shown(value: Fraction) -> CoreNode:
        """An integer operand stays a number until the expansion step writes it as a fraction."""
        if value.denominator == 1:
            return number(value.numerator)
        return fraction(number(value.numerator), number(value.denominator))

    original = CoreNode.node(op, *[shown(v) for v in values])
    scaled = [v.numerator * (common // v.denominator) for v in values]
    combined = fraction(CoreNode.node(op, *map(number, scaled)), number(common))
    total_n = scaled[0] + sum(scaled[1:]) if op is T.ADD else scaled[0] - sum(scaled[1:])
    unreduced = fraction(number(total_n), number(common))

    expand = SolveResult()
    current = original
    if any(v.denominator == 1 for v in values):
        # The app turns a whole number into a fraction before expanding it.
        as_fractions = CoreNode.node(
            op,
            *[
                fraction(number(v.numerator), number(1)) if v.denominator == 1 else shown(v)
                for v in values
            ],
        )
        rule = CoreNode.node(
            T.EQUALS, CoreNode.variable("a"), fraction(CoreNode.variable("a"), number(1))
        )
        expand.add_group(
            "convert_expression", Step(current, as_fractions, "frac_expand_int", [rule])
        )
        current = as_fractions

    expanded_terms = [
        fraction(
            CoreNode.node(T.MULTIPLY, number(v.numerator), number(common // v.denominator))
            if common // v.denominator > 1
            else number(v.numerator),
            CoreNode.node(T.MULTIPLY, number(v.denominator), number(common // v.denominator))
            if common // v.denominator > 1
            else number(v.denominator),
        )
        for v in values
    ]
    expansions: list[Step] = []
    for index, (term, value) in enumerate(zip(expanded_terms, values, strict=True)):
        if common // value.denominator == 1:
            continue
        following = _replace_child(current, index, term)
        expansions.append(Step(current, following, "frac_sum_expand"))
        current = following
    expand.add_group("frac_expand_plural" if len(expansions) > 1 else "frac_expand", *expansions)

    # Every numerator and denominator product is its own row, in expression order.
    products: list[Step] = []
    for index, value in enumerate(values):
        factor = common // value.denominator
        if factor == 1:
            continue
        denominator_product = expanded_terms[index].children[1]
        converted_denominator = number(value.denominator * factor)

        following = _replace_child(
            current, index, fraction(number(value.numerator * factor), denominator_product)
        )
        key = "mul_with_one" if 1 in (value.numerator, factor) else "mul"
        products.append(Step(current, following, key, [number(1)] if key == "mul_with_one" else []))
        current = following

        following = _replace_child(
            current, index, fraction(number(value.numerator * factor), converted_denominator)
        )
        key = "mul_with_one" if 1 in (value.denominator, factor) else "mul"
        products.append(Step(current, following, key, [number(1)] if key == "mul_with_one" else []))
        current = following
    expand.add_group("multiply", *products)
    expand.add_group("frac_sum_join", Step(current, combined, "frac_sum_join"))
    expand.set_solution(combined)

    # Integer operand: converted to a fraction first; The app words it without the denominator.
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
        halves = fraction(number(total_n // divisor), divided.children[1])
        reduction = SolveResult()
        reduction.add_group(
            "frac_reduce_frac", Step(unreduced, divided, "frac_div_num", [number(divisor)])
        )
        reduction.add_group("divide", Step(divided, halves, "div"), Step(halves, result, "div"))
        reduction.set_solution(result)
        rows.append(
            (
                "frac_reduce_frac",
                [
                    Step(
                        unreduced,
                        result,
                        "frac_reduce_frac_num",
                        [number(divisor)],
                        subresult=reduction,
                    )
                ],
            )
        )
    return rows


def _item(n: int, d: int) -> CoreNode:
    number = CoreNode.constant
    return number(str(n)) if d == 1 else CoreNode.node(T.FRACTION, number(str(n)), number(str(d)))


def _product(items: list[list[int]]) -> CoreNode:
    """Product of the items; factors equal to 1 are dropped like in the app's pages."""
    shown = [_item(n, d) for n, d in items if (n, d) != (1, 1)] or [_item(1, 1)]
    return shown[0] if len(shown) == 1 else CoreNode.node(T.MULTIPLY, *shown)


def _division_rows(values: list[Fraction], result: CoreNode) -> Rows | None:
    """Dividing by a fraction as the step screen shows it.

    Two rows: multiply by the reciprocal (``frac_div_rec``), then the product
    (:func:`_joined_rows`). A «write the fraction as a quotient» row and a
    separate «evaluate the product» row are folded into these two (cases ``frac_div``:
    ``- | -``, ``frac_div_nocancel``: ``- | +``), so the student never sees stub rows.
    """
    if len(values) != 2 or all(v.denominator == 1 for v in values) or any(v <= 0 for v in values):
        return None
    dividend, divisor = values
    if divisor == 1:
        return None  # a plain division by one, not a fraction rewrite
    operands = [
        [dividend.numerator, dividend.denominator],
        [divisor.numerator, divisor.denominator],
    ]
    items = [operands[0], [operands[1][1], operands[1][0]]]
    divided = CoreNode.node(T.DIVIDE, _item(*operands[0]), _item(*operands[1]))
    multiplied = _product(items)
    rows: Rows = [("frac_div_rec_short", [Step(divided, multiplied, "frac_div_rec")])]
    return rows + _joined_rows(items, multiplied, result)


def _joined_rows(items: list[list[int]], current: CoreNode, result: CoreNode) -> Rows:
    """The product row: cancellations, then the joined fraction or its evaluation.

    One page per cancellation by a common divisor of a numerator and another
    factor's denominator (``frac_reduce_out``); if factors are left, either one
    "calculate the product" row (integer factor) or the join + calculate rows.
    """
    number = CoreNode.constant
    rows: Rows = []
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
    return rows


def product_rows(op: T, values: list[Fraction], result: CoreNode) -> Rows | None:
    """Product or quotient of two positive numeric operands as the app shows it.

    For a product: one page per cancellation by a common divisor of a numerator and
    another factor's denominator; if factors are left, either one "calculate the
    product" row (integer factor) or the join + calculate rows. A quotient goes
    through :func:`_division_rows`.
    """
    if op is T.DIVIDE:
        return _division_rows(values, result)
    if (
        op not in (T.MULTIPLY, T.MULTIPLY_IMPLICIT)
        or len(values) < 2
        or all(v.denominator == 1 for v in values)
        or any(v <= 0 for v in values)
    ):
        return None
    items = [[v.numerator, v.denominator] for v in values]
    return _joined_rows(items, _product(items), result) or None


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
    # the app writes the improper fraction first, then evaluates the
    # numerator: 2 1/3 -> ((2*3)+1)/3 -> (6+1)/3 -> 7/3.
    number = CoreNode.constant

    def fraction(n: CoreNode, d: CoreNode) -> CoreNode:
        return CoreNode.node(T.FRACTION, n, d)

    whole_node = number(format_number(whole))
    numerator_node = number(format_number(numerator))
    denominator_node = number(format_number(denominator))
    improper = fraction(
        CoreNode.node(
            T.ADD, CoreNode.node(T.MULTIPLY, whole_node, denominator_node), numerator_node
        ),
        denominator_node,
    )
    multiplied = fraction(
        CoreNode.node(
            T.ADD,
            number(format_number(whole * denominator)),
            numerator_node,
        ),
        denominator_node,
    )
    evaluated = fraction(number(format_number(whole * denominator + numerator)), denominator_node)
    ctx.result.add_group("convert_expression", Step(node, improper, "mfrac_to_frac"))
    ctx.result.add_group("multiply", Step(improper, multiplied, "mul"))
    ctx.result.add_group("calculate_short", Step(multiplied, evaluated, "add"))
    return result


__all__ = [
    "solve_fraction",
]
