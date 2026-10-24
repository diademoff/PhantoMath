"""Суммы (знак суммирования).

Модуль зарегистрирован на ``SIGMA_DEFINITE``. Дети: ``[индекс, нижний предел, верхний предел,
выражение]``. Принимается и форма редактора ``[нижний, верхний, выражение]``
с индексом ``n``.

Сумма вычисляется sympy; для числовых пределов выходит точное число, для
символьной верхней границы — формула. Результат переводится обратно в
``CoreNode`` мостом.

Карточки сумм — как в карточках: формула первых ``n`` чисел/квадратов,
арифметическая прогрессия, геометрическая сумма, вынос константы и подстановка
значений по одному. Признаки сходимости (p-признак, интегральный, Даламбер,
Коши, Лейбниц, сравнение, радиус) расписаны по строкам, включая
вложенную цепочку несобственного интеграла в интегральном признаке.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, SolveResult, Step, boolean_node, solver_for
from .definite_cards import row_improper_card
from .methods import method_provider
from .sympy_bridge import from_sympy, to_sympy


def _parts(node: CoreNode) -> tuple[str, CoreNode, CoreNode, CoreNode]:
    """Разобрать узел в ``(имя индекса, нижний, верхний, выражение)``."""
    if len(node.children) == 4:
        index, lower, upper, expression = node.children
        if index.type is not T.VARIABLE or not index.value:
            raise SolveError("индекс суммы должен быть переменной")
        return index.value, lower, upper, expression
    if len(node.children) == 3:
        lower, upper, expression = node.children
        return "n", lower, upper, expression
    raise SolveError("сумма задаётся индексом, пределами и выражением")


def _is_reversed(low: sympy.Expr, high: sympy.Expr) -> bool:
    """Перевёрнуты ли числовые пределы (нижний больше верхнего).

    Иначе sympy молча считает «назад» (``Σ₅¹ n = −9``) и выдаёт уверенный,
    но бессмысленный ответ. Символьные пределы не трогаем.
    """
    try:
        return bool(low.is_number and high.is_number and low > high)
    except TypeError:
        return False


@solver_for(T.SIGMA_DEFINITE)
def solve_series(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить сумму ряда."""
    index, lower, upper, expression = _parts(node)
    symbol = sympy.Symbol(index)
    low, high = to_sympy(lower), to_sympy(upper)
    if _is_reversed(low, high):
        raise SolveError("нижний предел суммы больше верхнего")
    value = sympy.summation(
        to_sympy(expression),
        (symbol, low, high),
    )
    if value.has(sympy.Sum):
        raise SolveError("сумму не удалось вычислить")
    special = _special_sum(to_sympy(expression), symbol, to_sympy(lower), to_sympy(upper))
    if special is not None:
        ctx.result.add(Step(left=node, right=None, key=special, args=[from_sympy(to_sympy(upper))]))
    result = from_sympy(sympy.simplify(value))
    ctx.result.add(Step(left=node, right=result, key="series_sigma_find_sub"))
    return result


@method_provider(T.SIGMA_DEFINITE)
def sum_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """``Σ`` of a few small values in the cards.

    A sum of the first ``n`` numbers (or squares) gets the formula card, the
    arithmetic-progression card and the plain substitution card; a geometric
    sum gets the geometric rule and the substitution; a constant term gets the
    extraction card. Anything else uses the general path.
    """
    try:
        index, lower, upper, expression = _parts(node)
    except SolveError:
        return []
    if not (
        lower.type is T.CONSTANT
        and (lower.value or "").isdigit()
        and upper.type is T.CONSTANT
        and (upper.value or "").isdigit()
    ):
        return _generated_cards(index, lower, upper, expression)
    low, n = int(lower.value or 0), int(upper.value or 0)
    if not (0 <= low < n <= 12):
        return _generated_cards(index, lower, upper, expression)
    term = to_sympy(expression)
    symbol = sympy.Symbol(index)
    if sympy.simplify(term - symbol) == 0:
        return _arithmetic_cards(index, n, squares=False, lower=low)
    if low == 1 and sympy.simplify(term - symbol**2) == 0:
        return _arithmetic_cards(index, n, squares=True)
    if low == 1 and term.is_number and term != 0:
        return [_constant_card(index, n, expression)]
    linear = sympy.expand(term - symbol * (term.coeff(symbol)))
    if low == 1 and term.coeff(symbol).is_Integer and linear.is_Integer:
        return _ap_cards(index, n, int(term.coeff(symbol)), int(linear), expression)
    return _generated_cards(index, lower, upper, expression)


def _generated_cards(
    index: str, lower: CoreNode, upper: CoreNode, expression: CoreNode
) -> list[SolveResult]:
    """Cards for a geometric sum ``a^n`` (any lower bound) and the plain card."""
    symbol = sympy.Symbol(index)
    term = to_sympy(expression)
    base, exponent = term.as_base_exp()
    if exponent != symbol or base.free_symbols or base == 1 or not base.is_number:
        return []
    try:
        low, high = to_sympy(lower), to_sympy(upper)
        count = int(high - low + 1)
    except (TypeError, ValueError):
        return []
    if count < 1 or count > 20:
        return []
    total = sympy.simplify(sympy.summation(term, (symbol, low, high)))
    total_node = from_sympy(total)
    geometric = _geometric_card(index, lower, upper, expression, count, high, total_node)
    plain = _substitution_card(index, lower, upper, expression, total_node)
    return [geometric, plain]


# ── rows of one card ──────────────────────────────────────────────────


def _fold_add(parts: list[CoreNode]) -> CoreNode:
    """A left-associative sum: ``((1 + 2) + 3) + 4`` as the app writes it."""
    result = parts[0]
    for part in parts[1:]:
        result = CoreNode.node(T.ADD, result, part)
    return result


def _plain_detail(terms: list[CoreNode], total: CoreNode) -> SolveResult:
    """«Подробнее» of a sum of numbers: one pairwise addition per row."""
    if len(terms) >= 10:
        return _clever_detail(terms, total)
    detail = SolveResult()
    current = list(terms)
    # A zero first term is dropped before the additions.
    if len(current) > 1 and current[0].type is T.CONSTANT and current[0].value == "0":
        before = _fold_add(current)
        current = current[1:]
        detail.add_group(
            "calculate_short",
            Step(before, _fold_add(current), "add_with_zero", [CoreNode.constant("0")]),
        )
    while len(current) > 1:
        before = _fold_add(current)
        first_value = int(to_sympy(current[0]))
        last_value = int(to_sympy(current[-1]))
        if len(current) > 2 and first_value and last_value and (first_value + last_value) % 10 == 0:
            # The app pairs the ends when they make a ten (2+3, 5+5 → 10).
            merged = from_sympy(to_sympy(current[0]) + to_sympy(current[-1]))
            current = [merged, *current[1:-1]]
            after = _fold_add(current) if len(current) > 1 else merged
            detail.add_group("calculate_short", Step(before, after, "add_real_clever", [merged]))
            continue
        value = from_sympy(to_sympy(current[0]) + to_sympy(current[1]))
        current = [value, *current[2:]]
        after = _fold_add(current) if len(current) > 1 else value
        detail.add_group("calculate_short", Step(before, after, "add"))
    detail.set_solution(total)
    return detail


def _clever_detail(terms: list[CoreNode], total: CoreNode) -> SolveResult:
    """Ten or more numbers: pair the ends to make tens, then add up (verified ``Σ1..10``)."""
    detail = SolveResult()
    current = list(terms)
    first_accumulation = True
    left, right = 0, len(current) - 2
    while left < right:
        before = _fold_add(current)
        merged = from_sympy(to_sympy(current[left]) + to_sympy(current[right]))
        current = [merged, *current[1:right], current[-1]]
        after = _fold_add(current)
        detail.add_group("calculate_short", Step(before, after, "add_real_clever", [merged]))
        before = after
        total_node = from_sympy(to_sympy(current[0]) + to_sympy(current[-1]))
        current = [total_node, *current[1:-1]]
        after = current[0] if len(current) == 1 else _fold_add(current)
        if first_accumulation:
            first_accumulation = False
            detail.add_group(
                "calculate_short",
                Step(before, after, "add_real_clever", [total_node]),
            )
        else:
            detail.add_group("calculate_short", Step(before, after, "add"))
        left, right = 0, len(current) - 2
    if not current[0].structural_eq(total):
        detail.add_group("calculate_short", Step(current[0], total, "add"))
    detail.set_solution(total)
    return detail


def _powers_detail(terms: list[CoreNode], total: CoreNode) -> SolveResult:
    """«Подробнее» of a sum of powers: evaluate the powers, then add them up."""
    detail = SolveResult()
    current = list(terms)
    steps: list[Step] = []
    for index, term in enumerate(terms):
        if term.type is not T.POWER:
            continue
        base, exponent = term.children
        value = from_sympy(to_sympy(term))
        before = _fold_add(current)
        current[index] = value
        after = _fold_add(current)
        if exponent.type is T.CONSTANT and exponent.value == "0":
            key, args = "pow_with_zero", [exponent, CoreNode.constant("1")]
        elif exponent.type is T.CONSTANT and exponent.value == "1":
            key, args = "pow_with_one", [CoreNode.constant("1")]
        elif base.type is T.CONSTANT and base.value == "1":
            key, args = "pow_one", [base]
        else:
            key, args = "pow", []
        steps.append(Step(before, after, key, args))
    if steps:
        detail.add_group("calculate_short", *steps)
    summed = _fold_add(current)
    if not summed.structural_eq(total):
        detail.add_group("calculate_short", Step(summed, total, "sum_real_positive"))
    detail.set_solution(total)
    return detail


def _formula_pos_int_nodes(n: int) -> tuple[CoreNode, CoreNode, CoreNode, CoreNode]:
    """``n(n+1)/2`` as the app writes it: the filled formula and the product."""
    eq, num = CoreNode.node, CoreNode.constant
    two, one, count = num("2"), num("1"), num(str(n))
    filled = eq(
        T.FRACTION,
        eq(T.MULTIPLY, count, eq(T.BRACKET, eq(T.ADD, count, one))),
        two,
    )
    added = eq(T.FRACTION, eq(T.MULTIPLY, count, num(str(n + 1))), two)
    if n % 2 == 0:
        reduced = eq(T.MULTIPLY, num(str(n // 2)), num(str(n + 1)))
    else:
        reduced = eq(T.MULTIPLY, count, num(str((n + 1) // 2)))
    return filled, added, reduced, num(str(n * (n + 1) // 2))


def _formula_pos_int_detail(n: int, total: CoreNode) -> SolveResult:
    """``5·(5+1)/2 → 5·6/2 → 5·3 → 15`` (verified ``Σi``)."""
    filled, added, reduced, _product = _formula_pos_int_nodes(n)
    detail = SolveResult()
    if n % 2 == 0:
        detail.add_group(
            "calculate_short",
            Step(filled, added, "add"),
            Step(added, reduced, "frac_reduce_frac_num", [CoreNode.constant("2")]),
        )
    else:
        detail.add_group("calculate_short", Step(filled, added, "add"))
        detail.add_group(
            "calculate_short",
            Step(added, reduced, "frac_reduce_frac_num", [CoreNode.constant("2")]),
        )
    detail.add_group("calculate_short", Step(reduced, total, "mul"))
    detail.set_solution(total)
    return detail


def _formula_offset_detail(n: int, offset: CoreNode, total: CoreNode) -> SolveResult:
    """``(5·6/2 − 1) → (5·3 − 1) → (15 − 1) → 14`` (verified ``Σi`` from 2)."""
    eq = CoreNode.node
    filled, added, reduced, product = _formula_pos_int_nodes(n)
    detail = SolveResult()
    detail.add_group(
        "calculate_short",
        Step(eq(T.SUBTRACT, filled, offset), eq(T.SUBTRACT, added, offset), "add"),
    )
    detail.add_group(
        "calculate_short",
        Step(
            eq(T.SUBTRACT, added, offset),
            eq(T.SUBTRACT, reduced, offset),
            "frac_reduce_frac_num",
            [CoreNode.constant("2")],
        ),
    )
    detail.add_group(
        "calculate_short",
        Step(eq(T.SUBTRACT, reduced, offset), eq(T.SUBTRACT, product, offset), "mul"),
    )
    detail.add_group("calculate_short", Step(eq(T.SUBTRACT, product, offset), total, "sub"))
    detail.set_solution(total)
    return detail


def _pos_int_sum_detail(index: str, n: int) -> SolveResult:
    """The nested «use Σi = n(n+1)/2» screen inside the interval separation."""
    eq, var, num = CoreNode.node, CoreNode.variable, CoreNode.constant
    letter, count = var("n"), num(str(n))
    general = eq(
        T.FRACTION,
        eq(T.MULTIPLY, letter, eq(T.BRACKET, eq(T.ADD, letter, num("1")))),
        num("2"),
    )
    filled, _added, _reduced, product = _formula_pos_int_nodes(n)
    detail = SolveResult()
    detail.add_group(
        CoreRichText(type="series_formula_short", args=[general]),
        Step(
            _sigma_node(index, num("1"), count, var(index)),
            filled,
            "series_formula_pos_int",
            [count, letter, letter, general],
        ),
    )
    detail.add_group(
        "calculate_short",
        Step(filled, product, "calculate_direct", subresult=_formula_pos_int_detail(n, product)),
    )
    detail.set_solution(product)
    return detail


def _formula_square_detail(n: int, total: CoreNode) -> SolveResult | None:
    """``4·5·9/6 → … → 30`` (verified ``Σi²`` for ``n = 4``)."""
    eq = CoreNode.node
    count = CoreNode.constant(str(n))
    two = CoreNode.constant("2")
    six = CoreNode.constant("6")

    def fraction(left: CoreNode, denominator: CoreNode) -> CoreNode:
        return eq(T.FRACTION, left, denominator)

    def product(*parts: CoreNode) -> CoreNode:
        return eq(T.MULTIPLY, *parts)

    filled = fraction(
        product(
            count,
            eq(T.BRACKET, eq(T.ADD, count, CoreNode.constant("1"))),
            eq(T.BRACKET, eq(T.ADD, product(two, count), CoreNode.constant("1"))),
        ),
        six,
    )
    first_add = fraction(
        product(
            count,
            eq(T.BRACKET, CoreNode.constant(str(n + 1))),
            eq(T.BRACKET, eq(T.ADD, product(two, count), CoreNode.constant("1"))),
        ),
        six,
    )
    doubled = fraction(
        product(
            count,
            eq(T.BRACKET, CoreNode.constant(str(n + 1))),
            eq(T.BRACKET, eq(T.ADD, CoreNode.constant(str(2 * n)), CoreNode.constant("1"))),
        ),
        six,
    )
    divisor = sympy.gcd(n, 6)
    if divisor < 2 or (2 * n + 1) % 3:
        return None
    reduced = fraction(
        product(
            CoreNode.constant(str(n // divisor)),
            eq(T.BRACKET, CoreNode.constant(str(n + 1))),
            eq(T.BRACKET, eq(T.ADD, CoreNode.constant(str(2 * n)), CoreNode.constant("1"))),
        ),
        CoreNode.constant(str(6 // divisor)),
    )
    summed = fraction(
        product(
            CoreNode.constant(str(n // divisor)),
            eq(T.BRACKET, CoreNode.constant(str(n + 1))),
            eq(T.BRACKET, CoreNode.constant(str(2 * n + 1))),
        ),
        CoreNode.constant(str(6 // divisor)),
    )
    cancelled = product(
        CoreNode.constant(str(n // divisor)),
        CoreNode.constant(str(n + 1)),
        CoreNode.constant("3"),
    )
    detail = SolveResult()
    detail.add_group(
        "calculate_short",
        Step(filled, first_add, "add"),
        Step(
            first_add,
            doubled,
            "mul",
        ),
        Step(doubled, reduced, "frac_reduce_frac_alg", [CoreNode.constant(str(divisor))]),
    )
    detail.add_group("calculate_short", Step(reduced, summed, "add"))
    detail.add_group(
        "calculate_short",
        Step(summed, cancelled, "frac_reduce_frac_num", [CoreNode.constant("3")]),
    )
    detail.add_group("calculate_short", Step(cancelled, total, "product"))
    detail.set_solution(total)
    return detail


def _arithmetic_detail(high: int, first: CoreNode, last: CoreNode, total: CoreNode) -> SolveResult:
    """``3·(3+7)/2 → 3·10/2 → 3·5 → 15`` (verified ``Σ(2n+1)``)."""
    eq = CoreNode.node
    count = CoreNode.constant(str(high))
    filled = eq(
        T.FRACTION,
        eq(T.MULTIPLY, count, eq(T.BRACKET, eq(T.ADD, first, last))),
        CoreNode.constant("2"),
    )
    first_value, last_value = int(to_sympy(first)), int(to_sympy(last))
    summed = first_value + last_value
    if first_value == 0:
        added = eq(
            T.FRACTION,
            eq(T.MULTIPLY, count, CoreNode.constant(str(last_value))),
            CoreNode.constant("2"),
        )
        first_step = Step(filled, added, "add_with_zero", [CoreNode.constant("0")])
    else:
        added = eq(
            T.FRACTION,
            eq(T.MULTIPLY, count, CoreNode.constant(str(summed))),
            CoreNode.constant("2"),
        )
        first_step = Step(filled, added, "add")
    quotient = sympy.Rational(summed, 2)
    reduced = eq(T.MULTIPLY, count, from_sympy(quotient))
    detail = SolveResult()
    if high % 2 == 0:
        detail.add_group(
            "calculate_short",
            first_step,
            Step(added, reduced, "frac_reduce_out", [CoreNode.constant("2")]),
        )
    else:
        detail.add_group("calculate_short", first_step)
        detail.add_group(
            "calculate_short",
            Step(added, reduced, "frac_reduce_frac_num", [CoreNode.constant("2")]),
        )
    detail.add_group("calculate_short", Step(reduced, total, "mul"))
    detail.set_solution(total)
    return detail


def _geometric_card(
    index: str,
    lower: CoreNode,
    upper: CoreNode,
    expression: CoreNode,
    count: int,
    high: sympy.Expr,
    total_node: CoreNode,
) -> SolveResult:
    """The geometric-sum card: number of terms, first term and ratio, then the rule."""
    eq, var, num = CoreNode.node, CoreNode.variable, CoreNode.constant
    term = to_sympy(expression)
    base = term.as_base_exp()[0]
    count_node = num(str(count))
    card = SolveResult(header="series_find_sum_geom")
    filled = eq(T.EQUALS, var(index), eq(T.ADD, eq(T.SUBTRACT, upper, lower), num("1")))
    after_zero = eq(T.EQUALS, var(index), eq(T.ADD, upper, num("1")))
    card.add_group(
        "series_sigma_calc_n_simple",
        Step(
            _sigma_node(index, lower, upper, expression),
            filled,
            "series_sigma_calc_n",
            [num("1")],
        ),
    )
    detail = SolveResult()
    detail.add_group("calculate_short", Step(filled, after_zero, "add_with_zero", [num("0")]))
    detail.add_group(
        "calculate_short", Step(after_zero, eq(T.EQUALS, var(index), count_node), "add")
    )
    detail.set_solution(eq(T.EQUALS, var(index), count_node))
    card.add_group(
        "calculate_short",
        Step(filled, eq(T.EQUALS, var(index), count_node), "sum", subresult=detail),
    )
    ratio = eq(
        T.LIST,
        eq(T.EQUALS, var("a_1"), eq(T.POWER, from_sympy(base), lower)),
        eq(T.EQUALS, var("r"), from_sympy(base)),
    )
    card.add_group(
        "series_sigma_find_fst_ratio_simple",
        Step(
            eq(T.EQUALS, var(index), count_node),
            ratio,
            "series_sigma_find_fst_ratio",
            [var("a_1"), lower, var(index), from_sympy(term), var("r")],
        ),
    )
    first_one = eq(
        T.LIST,
        eq(T.EQUALS, var("a_1"), num("1")),
        eq(T.EQUALS, var("r"), from_sympy(base)),
    )
    card.add_group(
        "calculate_short",
        Step(ratio, first_one, "pow_with_zero", [num("0"), num("1")]),
    )
    rule = eq(
        T.EQUALS,
        var(f"S_{count}"),
        eq(
            T.MULTIPLY,
            var("a_1"),
            eq(
                T.FRACTION,
                eq(T.SUBTRACT, num("1"), eq(T.POWER, var("r"), count_node)),
                eq(T.SUBTRACT, num("1"), var("r")),
            ),
        ),
    )
    card.add_group(
        "series_sigma_geom_use_formula",
        Step(
            first_one,
            rule,
            "series_sigma_geom_write_rule",
            [
                eq(
                    T.EQUALS,
                    var("S_n"),
                    eq(
                        T.MULTIPLY,
                        var("a_1"),
                        eq(
                            T.FRACTION,
                            eq(T.SUBTRACT, num("1"), eq(T.POWER, var("r"), var("n"))),
                            eq(T.SUBTRACT, num("1"), var("r")),
                        ),
                    ),
                ),
                eq(T.EQUALS, var("n"), count_node),
            ],
        ),
    )
    substituted = eq(
        T.EQUALS,
        var(f"S_{count}"),
        eq(
            T.MULTIPLY,
            num("1"),
            eq(
                T.FRACTION,
                eq(
                    T.SUBTRACT,
                    num("1"),
                    eq(T.POWER, from_sympy(base), count_node),
                ),
                eq(T.SUBTRACT, num("1"), from_sympy(base)),
            ),
        ),
    )
    card.add_group(
        "trig_use_substitution",
        Step(
            rule,
            substituted,
            "series_sigma_sub",
            [num("1"), var("a_1"), from_sympy(base), var("r")],
        ),
    )
    card.add_group(
        "calculate_short",
        Step(
            substituted,
            total_node,
            "calculate_direct",
            subresult=_geometric_detail(substituted.children[1], total_node),
        ),
    )
    card.set_solution(total_node)
    return card


def _geometric_detail(filled: CoreNode, total: CoreNode) -> SolveResult:
    """``1·(1−2⁴)/(1−2) → (1−16)/(−1) → −15/−1 → 15``."""
    eq, num = CoreNode.node, CoreNode.constant
    inner = filled.children[1] if filled.type is T.MULTIPLY else filled
    detail = SolveResult()
    first: list[Step] = []
    current = filled
    if filled.type is T.MULTIPLY:
        first.append(Step(filled, inner, "mul_with_one", [filled.children[0]]))
        current = inner
    numerator, denominator = inner.children
    power = numerator.children[1]
    powered_up = eq(T.SUBTRACT, num("1"), from_sympy(sympy.simplify(to_sympy(power))))
    after_power = eq(T.FRACTION, powered_up, denominator)
    denominator_value = from_sympy(sympy.simplify(to_sympy(denominator)))
    after_denominator = eq(T.FRACTION, powered_up, denominator_value)
    first.append(Step(current, after_power, "pow"))
    first.append(Step(after_power, after_denominator, "calc_diff"))
    detail.add_group("calculate_short", *first)
    numerator_value = from_sympy(sympy.simplify(to_sympy(powered_up)))
    gathered = eq(T.FRACTION, numerator_value, denominator_value)
    detail.add_group("calculate_short", Step(after_denominator, gathered, "calc_diff"))
    detail.add_group(
        "calculate_short",
        Step(gathered, total, "div_with_neg_one", [denominator_value]),
    )
    detail.set_solution(total)
    return detail


def _substitute_variable(node: CoreNode, name: str, value: CoreNode) -> CoreNode:
    """``2n + 1`` with ``n = 3``; the power of a number is not evaluated yet."""
    if node.type is T.VARIABLE and node.value == name:
        return value
    if not node.children:
        return node
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[_substitute_variable(child, name, value) for child in node.children],
    )


def _substitution_card(
    index: str,
    lower: CoreNode,
    upper: CoreNode,
    expression: CoreNode,
    total: CoreNode,
) -> SolveResult:
    """The plain card: write the sum as numbers, then add them up."""
    low, high = to_sympy(lower), to_sympy(upper)
    count = int(high - low + 1)
    terms: list[CoreNode] = []
    for step in range(count):
        terms.append(_substitute_variable(expression, index, CoreNode.constant(str(low + step))))
    written = _fold_add(terms)
    card = SolveResult(header="series_sigma_find_sub")
    card.add_group(
        "convert_expression",
        Step(
            _sigma_node(index, lower, upper, expression),
            written,
            "sigma_sum_convert",
            [lower, upper],
        ),
    )
    if any(term.type is T.POWER for term in terms):
        detail = _powers_detail(terms, total)
        key = "calculate_direct"
    else:
        detail = _plain_detail(terms, total)
        key = "sum_real_positive"
    card.add_group(
        "calculate_short",
        Step(written, total, key, subresult=detail),
    )
    card.set_solution(total)
    return card


def _sigma_node(index: str, lower: CoreNode, upper: CoreNode, expression: CoreNode) -> CoreNode:
    return CoreNode.node(T.SIGMA_DEFINITE, CoreNode.variable(index), lower, upper, expression)


def _constant_card(index: str, n: int, expression: CoreNode) -> SolveResult:
    """``Σ3 = 3·Σ1 = 3·4 = 12`` (verified ``Σ3``)."""
    eq, var, num = CoreNode.node, CoreNode.variable, CoreNode.constant
    value = to_sympy(expression)
    sigma = _sigma_node(index, num("1"), num(str(n)), expression)
    one = num("1")
    as_product = eq(T.MULTIPLY, from_sympy(value), one)
    written = _sigma_node(index, num("1"), num(str(n)), as_product)
    extraction_rule = eq(
        T.EQUALS,
        _sigma_node("k", num("1"), num(str(n)), eq(T.MULTIPLY, var("c"), var("a_k"))),
        eq(
            T.MULTIPLY,
            var("c"),
            _sigma_node("k", num("1"), num(str(n)), var("a_k")),
        ),
    )
    separated = eq(
        T.MULTIPLY,
        from_sympy(value),
        _sigma_node(index, num("1"), num(str(n)), one),
    )
    ones_rule = eq(
        T.EQUALS,
        _sigma_node("k", num("1"), var("n"), one),
        var("n"),
    )
    counted = eq(T.MULTIPLY, from_sympy(value), num(str(n)))
    card = SolveResult(header="series_find_sum_special")
    card.add_group(
        "find_sum",
        Step(sigma, written, "write_as_mul", [one]),
    )
    card.add_group(
        "find_sum",
        Step(written, separated, "series_sigma_rewrite_extract", [extraction_rule]),
    )
    card.add_group(
        "find_sum",
        Step(
            separated,
            counted,
            "series_sigma_const_one",
            [
                var("n"),
                num("1"),
                ones_rule,
            ],
        ),
    )
    total = from_sympy(sympy.simplify(value * n))
    card.add_group("calculate_short", Step(counted, total, "mul"))
    card.set_solution(total)
    return card


def _square_node(node: CoreNode) -> CoreNode:
    return CoreNode.node(T.POWER, node, CoreNode.constant("2"))


def _arithmetic_cards(index: str, n: int, *, squares: bool, lower: int = 1) -> list[SolveResult]:
    """The app's formula, arithmetic-progression and substitution cards.

    ``lower`` is the first index; a sum that does not start at 1 gets the
    «rewrite the sum» row first (``series_sigma_rewrite_*``).
    """
    eq, var, num = CoreNode.node, CoreNode.variable, CoreNode.constant
    symbol = sympy.Symbol(index)
    term_node = _square_node(var(index)) if squares else var(index)
    term = symbol**2 if squares else symbol
    total = from_sympy(sympy.summation(term, (symbol, lower, n)))
    count_node, letter = num(str(n)), var("n")
    if squares:
        general = eq(
            T.FRACTION,
            eq(
                T.MULTIPLY,
                letter,
                eq(T.BRACKET, eq(T.ADD, letter, num("1"))),
                eq(T.BRACKET, eq(T.ADD, eq(T.MULTIPLY, num("2"), letter), num("1"))),
            ),
            num("6"),
        )
        filled = eq(
            T.FRACTION,
            eq(
                T.MULTIPLY,
                count_node,
                eq(T.BRACKET, eq(T.ADD, count_node, num("1"))),
                eq(T.BRACKET, eq(T.ADD, eq(T.MULTIPLY, num("2"), count_node), num("1"))),
            ),
            num("6"),
        )
        key = "series_formula_square"
    else:
        general = eq(
            T.FRACTION,
            eq(T.MULTIPLY, letter, eq(T.BRACKET, eq(T.ADD, letter, num("1")))),
            num("2"),
        )
        _filled, _added, _reduced, filled = _formula_pos_int_nodes(n)
        key = "series_formula_pos_int"
    formula = SolveResult(header="series_find_sum_special")
    if squares:
        detail = _formula_square_detail(n, total)
        formula.add_group(
            CoreRichText(type="series_formula_short", args=[general]),
            Step(
                _sigma_node(index, num("1"), count_node, term_node),
                filled,
                key,
                [count_node, letter, letter, general],
            ),
        )
        formula.add_group(
            "calculate_short",
            Step(filled, total, "calculate_direct", subresult=detail),
        )
        formula.set_solution(total)
        plain = _substitution_card(index, num("1"), count_node, term_node, total)
        return [formula, plain]
    if lower == 1:
        formula.add_group(
            CoreRichText(type="series_formula_short", args=[general]),
            Step(
                _sigma_node(index, num("1"), count_node, term_node),
                filled,
                key,
                [count_node, letter, letter, general],
            ),
        )
        formula.add_group(
            "calculate_short",
            Step(
                filled,
                total,
                "calculate_direct",
                subresult=_formula_pos_int_detail(n, total),
            ),
        )
    elif lower == 0:
        one_sum = _sigma_node(index, num("1"), count_node, term_node)
        formula.add_group(
            "series_rewrite_sum",
            Step(
                _sigma_node(index, num("0"), count_node, term_node),
                one_sum,
                "series_sigma_rewrite_start0",
                [eq(T.EQUALS, var(index), num("0")), num("0"), num("1")],
            ),
        )
        formula.add_group(
            CoreRichText(type="series_formula_short", args=[general]),
            Step(one_sum, filled, key, [count_node, letter, letter, general]),
        )
        formula.add_group(
            "calculate_short",
            Step(
                filled,
                total,
                "calculate_direct",
                subresult=_formula_pos_int_detail(n, total),
            ),
        )
    elif lower == 2:
        offset = num("1")
        one_sum = _sigma_node(index, num("1"), count_node, term_node)
        formula.add_group(
            "series_rewrite_sum",
            Step(
                _sigma_node(index, num("2"), count_node, term_node),
                eq(T.SUBTRACT, one_sum, offset),
                "series_sigma_rewrite_start2",
                [num("1"), var(index), eq(T.EQUALS, var(index), num("1"))],
            ),
        )
        with_offset = eq(T.SUBTRACT, filled, offset)
        formula.add_group(
            CoreRichText(type="series_formula_short", args=[general]),
            Step(
                eq(T.SUBTRACT, one_sum, offset),
                with_offset,
                key,
                [count_node, letter, letter, general],
            ),
        )
        formula.add_group(
            "calculate_short",
            Step(
                with_offset,
                total,
                "calculate_direct",
                subresult=_formula_offset_detail(n, offset, total),
            ),
        )
    else:
        high_sum = _sigma_node(index, num("1"), count_node, term_node)
        low_count = num(str(lower - 1))
        low_sum = _sigma_node(index, num("1"), low_count, term_node)
        rule = eq(
            T.EQUALS,
            _sigma_node(index, num(str(lower)), count_node, term_node),
            eq(T.SUBTRACT, high_sum, low_sum),
        )
        formula.add_group(
            "use_property_sum",
            Step(
                _sigma_node(index, num(str(lower)), count_node, term_node),
                eq(T.SUBTRACT, high_sum, low_sum),
                "series_sigma_rewrite_separate",
                [rule],
            ),
        )
        high_total = num(str(n * (n + 1) // 2))
        after_high = eq(T.SUBTRACT, high_total, low_sum)
        low_total = num(str((lower - 1) * lower // 2))
        formula.add_group(
            "find_sum_pl",
            Step(
                eq(T.SUBTRACT, high_sum, low_sum),
                after_high,
                "series_find_sum_pos_int",
                [var("n")],
                subresult=_pos_int_sum_detail(index, n),
            ),
            Step(
                after_high,
                eq(T.SUBTRACT, high_total, low_total),
                "series_find_sum_pos_int",
                [var("n")],
                subresult=_pos_int_sum_detail(index, lower - 1),
            ),
        )
        formula.add_group(
            "calculate_short",
            Step(eq(T.SUBTRACT, high_total, low_total), total, "sub"),
        )
    formula.set_solution(total)
    arithmetic = _arithmetic_card(index, n, total, lower=lower)
    plain = _substitution_card(index, num(str(lower)), count_node, term_node, total)
    return [formula, arithmetic, plain]


def _ap_term_node(a: int, b: int, k: int) -> CoreNode:
    eq, num = CoreNode.node, CoreNode.constant
    return eq(T.ADD, eq(T.MULTIPLY, num(str(a)), num(str(k))), num(str(b)))


def _ap_term_detail(a: int, b: int, k: int) -> SolveResult:
    """``2·3 + 1 → 6 + 1 → 7`` (one term of an arithmetic progression)."""
    eq, num = CoreNode.node, CoreNode.constant
    detail = SolveResult()
    if k == 1:
        detail.add_group(
            "calculate_short",
            Step(
                _ap_term_node(a, b, k),
                eq(T.ADD, num(str(a * k)), num(str(b))),
                "mul_with_one",
                [num("1")],
            ),
        )
    else:
        detail.add_group(
            "calculate_short",
            Step(_ap_term_node(a, b, k), eq(T.ADD, num(str(a * k)), num(str(b))), "mul"),
        )
    detail.add_group(
        "calculate_short",
        Step(
            eq(T.ADD, num(str(a * k)), num(str(b))),
            num(str(a * k + b)),
            "add",
        ),
    )
    detail.set_solution(num(str(a * k + b)))
    return detail


def _ap_cards(index: str, n: int, a: int, b: int, expression: CoreNode) -> list[SolveResult]:
    """The app's arithmetic-progression card and the plain card for ``Σ(a·k + b)``."""
    eq, var, num = CoreNode.node, CoreNode.variable, CoreNode.constant
    total = from_sympy(sympy.summation(a * sympy.Symbol(index) + b, (sympy.Symbol(index), 1, n)))
    first, last = var("a_1"), var(f"a_{n}")
    pair = eq(
        T.LIST,
        eq(T.EQUALS, first, num(str(a + b))),
        eq(T.EQUALS, last, num(str(a * n + b))),
    )
    sigma = _sigma_node(index, num("1"), num(str(n)), expression)
    detail = SolveResult()
    first_pair = eq(
        T.LIST,
        eq(T.EQUALS, first, _ap_term_node(a, b, 1)),
        eq(T.EQUALS, last, _ap_term_node(a, b, n)),
    )
    middle = eq(
        T.LIST,
        eq(T.EQUALS, first, num(str(a + b))),
        eq(T.EQUALS, last, _ap_term_node(a, b, n)),
    )
    detail.add_group(
        "calculate_short",
        Step(first_pair, middle, "calculate_direct", subresult=_ap_term_detail(a, b, 1)),
    )
    detail.add_group(
        "calculate_short",
        Step(middle, pair, "calculate_direct", subresult=_ap_term_detail(a, b, n)),
    )
    detail.set_solution(pair)
    card = SolveResult(header="series_find_sum_arith")
    card.add_group(
        "series_sigma_find_fst_last_term",
        Step(
            sigma,
            pair,
            "series_sigma_find_fst_last",
            [first, num("1"), var(index), expression, last, num(str(n)), var(index)],
            subresult=detail,
        ),
    )
    rule = eq(
        T.EQUALS,
        var(f"S_{n}"),
        eq(T.MULTIPLY, num(str(n)), eq(T.FRACTION, eq(T.ADD, first, last), num("2"))),
    )
    card.add_group(
        "series_sigma_arith_use_formula",
        Step(
            pair,
            rule,
            "series_sigma_arith_write_rule",
            [
                eq(
                    T.EQUALS,
                    var("S_n"),
                    eq(
                        T.MULTIPLY,
                        var("n"),
                        eq(T.FRACTION, eq(T.ADD, var("a_1"), var("a_n")), num("2")),
                    ),
                ),
                eq(T.EQUALS, var("n"), num(str(n))),
            ],
        ),
    )
    substituted = eq(
        T.EQUALS,
        var(f"S_{n}"),
        eq(
            T.MULTIPLY,
            num(str(n)),
            eq(
                T.FRACTION,
                eq(T.ADD, num(str(a + b)), num(str(a * n + b))),
                num("2"),
            ),
        ),
    )
    card.add_group(
        "trig_use_substitution",
        Step(
            rule,
            substituted,
            "series_sigma_sub",
            [num(str(a + b)), first, num(str(a * n + b)), last],
        ),
    )
    card.add_group(
        "calculate_short",
        Step(
            substituted,
            total,
            "calculate_direct",
            subresult=_arithmetic_detail(n, num(str(a + b)), num(str(a * n + b)), total),
        ),
    )
    card.set_solution(total)
    plain = _ap_plain_card(index, a, b, n, expression, total)
    return [card, plain]


def _ap_plain_card(
    index: str, a: int, b: int, n: int, expression: CoreNode, total: CoreNode
) -> SolveResult:
    """The plain card of ``Σ(2n+1)``: substitute the values and add them up."""
    eq, num = CoreNode.node, CoreNode.constant
    terms = [_ap_term_node(a, b, k) for k in range(1, n + 1)]
    written = _fold_add([eq(T.BRACKET, term) for term in terms])
    card = SolveResult(header="series_sigma_find_sub")
    card.add_group(
        "convert_expression",
        Step(
            _sigma_node(index, num("1"), num(str(n)), expression),
            written,
            "sigma_sum_convert",
            [num("1"), num(str(n))],
        ),
    )
    detail = SolveResult()
    after_one = eq(T.ADD, num(str(a)), num(str(b)))
    detail.add_group("calculate_short", Step(terms[0], after_one, "mul_with_one", [num("1")]))
    evaluated = [eq(T.ADD, num(str(a * k)), num(str(b))) for k in range(2, n + 1)]
    values = [num(str(a + b)), *[num(str(a * k + b)) for k in range(2, n + 1)]]
    products: list[Step] = [Step(after_one, values[0], "add")]
    for index_of_step, _term in enumerate(evaluated, start=2):
        products.append(
            Step(
                eq(T.MULTIPLY, num(str(a)), num(str(index_of_step))),
                num(str(a * index_of_step)),
                "mul",
            )
        )
    detail.add_group("calculate_short", *products)
    adds: list[Step] = []
    running = values[0]
    rest = list(evaluated)
    while rest:
        before = _fold_add([running, *rest])
        running = eq(T.ADD, running, values[len(values) - len(rest)])
        rest = rest[1:]
        adds.append(Step(before, _fold_add([running, *rest]) if rest else running, "add"))
    detail.add_group("calculate_short", *adds)
    detail.add_group("calculate_short", Step(running, total, "sum_real_positive"))
    detail.set_solution(total)
    card.add_group("calculate_short", Step(written, total, "calculate_direct", subresult=detail))
    card.set_solution(total)
    return card


def _arithmetic_card(index: str, high: int, total: CoreNode, lower: int = 1) -> SolveResult:
    """The arithmetic-progression card of ``Σi`` over ``[lower, high]``."""
    eq, var, num = CoreNode.node, CoreNode.variable, CoreNode.constant
    count = high - lower + 1
    first, last = var("a_1"), var(f"a_{count}")
    pair = eq(
        T.LIST,
        eq(T.EQUALS, first, num(str(lower))),
        eq(T.EQUALS, last, num(str(high))),
    )
    card = SolveResult(header="series_find_sum_arith")
    sigma = _sigma_node(index, num(str(lower)), num(str(high)), var(index))
    start: CoreNode = sigma
    if lower != 1:
        counted = eq(T.EQUALS, var("n"), num(str(count)))
        start = counted
        calc = eq(
            T.EQUALS,
            var("n"),
            eq(T.ADD, eq(T.SUBTRACT, num(str(high)), num(str(lower))), num("1")),
        )
        card.add_group(
            "series_sigma_calc_n_simple",
            Step(sigma, calc, "series_sigma_calc_n", [num("1")]),
        )
        detail = SolveResult()
        if lower == 0:
            simplified = eq(T.ADD, num(str(high)), num("1"))
            detail.add_group(
                "calculate_short",
                Step(calc, simplified, "add_with_zero", [num("0")]),
            )
            detail.add_group(
                "calculate_short",
                Step(simplified, num(str(count)), "add"),
            )
        else:
            difference = eq(T.SUBTRACT, num(str(high + 1)), num(str(lower)))
            detail.add_group(
                "calculate_short",
                Step(calc, difference, "sum_real_positive"),
            )
            detail.add_group(
                "calculate_short",
                Step(difference, num(str(count)), "sub"),
            )
        detail.set_solution(counted)
        card.add_group(
            "calculate_short",
            Step(calc, counted, "sum", subresult=detail),
        )
    card.add_group(
        "series_sigma_find_fst_last_term",
        Step(
            start,
            pair,
            "series_sigma_find_fst_last",
            [
                first,
                num(str(lower)),
                var(index),
                var(index),
                last,
                num(str(high)),
                var(index),
            ],
        ),
    )
    rule = eq(
        T.EQUALS,
        var(f"S_{count}"),
        eq(
            T.MULTIPLY,
            num(str(count)),
            eq(T.FRACTION, eq(T.ADD, first, last), num("2")),
        ),
    )
    card.add_group(
        "series_sigma_arith_use_formula",
        Step(
            pair,
            rule,
            "series_sigma_arith_write_rule",
            [
                eq(
                    T.EQUALS,
                    var("S_n"),
                    eq(
                        T.MULTIPLY,
                        var("n"),
                        eq(T.FRACTION, eq(T.ADD, var("a_1"), var("a_n")), num("2")),
                    ),
                ),
                eq(T.EQUALS, var("n"), num(str(count))),
            ],
        ),
    )
    substituted = eq(
        T.EQUALS,
        var(f"S_{count}"),
        eq(
            T.MULTIPLY,
            num(str(count)),
            eq(
                T.FRACTION,
                eq(T.ADD, num(str(lower)), num(str(high))),
                num("2"),
            ),
        ),
    )
    card.add_group(
        "trig_use_substitution",
        Step(
            rule,
            substituted,
            "series_sigma_sub",
            [num(str(lower)), first, num(str(high)), last],
        ),
    )
    card.add_group(
        "calculate_short",
        Step(
            substituted,
            total,
            "calculate_direct",
            subresult=_arithmetic_detail(count, num(str(lower)), num(str(high)), total),
        ),
    )
    card.set_solution(total)
    return card


def _special_sum(
    term: sympy.Expr, symbol: sympy.Symbol, lower: sympy.Expr, upper: sympy.Expr
) -> str | None:
    """Ключ формулы специальной суммы (первые ``n`` чисел) или ``None``."""
    if lower != 1 or upper in (sympy.oo, -sympy.oo):
        return None
    candidates = [
        ("series_find_sum_cube", symbol**3),
        ("series_find_sum_square", symbol**2),
        ("series_find_sum_pos_int", symbol),
        ("series_find_sum_even", 2 * symbol),
        ("series_find_sum_odd", 2 * symbol - 1),
    ]
    for key, reference in candidates:
        if sympy.simplify(term - reference) == 0:
            return key
    return None


def _text(key: str) -> CoreNode:
    """``TEXT[TEXT_KEY("converges")]``: the service resolves the word."""
    return CoreNode.node(T.TEXT, CoreNode(type=T.TEXT_KEY, value=key))


def _pseries_exponent(term: sympy.Expr, symbol: sympy.Symbol) -> sympy.Expr | None:
    """``p`` for ``1/nᵖ`` (``None`` when the term is not a p-series term)."""
    _, body = sympy.simplify(term).as_coeff_Mul()
    if not isinstance(body, sympy.Pow) or body.base != symbol:
        return None
    exponent = -body.exp
    return exponent if exponent.is_number else None


def convergence(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Определить, сходится ли ряд (сумма с бесконечным пределом).

    Сначала признак обобщённого гармонического ряда (``p``),
    затем точная сумма (sympy), затем интегральный признак.
    """
    del args
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("сходимость определяется у ряда (суммы)")
    index, lower, upper, expression = _parts(node)
    symbol = sympy.Symbol(index)
    ctx.result.add(Step(left=node, right=None, key="series_test_group"))
    term = to_sympy(expression)
    exponent = _pseries_exponent(term, symbol)
    if exponent is not None:
        return _pseries_convergence(node, ctx, exponent)
    value = sympy.summation(term, (symbol, to_sympy(lower), to_sympy(upper)))
    if value.has(sympy.Sum):
        # No closed form: the necessary condition first, then the integral test.
        limit_value = sympy.limit(term, symbol, sympy.oo)
        limit_node = CoreNode.node(T.LIMIT, CoreNode.constant("∞"), from_sympy(term))
        ctx.result.add_group(
            "limit_solve",
            Step(
                node,
                limit_node,
                "series_nth_term_test_use",
                [from_sympy(term)],
            ),
        )
        if limit_value.is_number and limit_value != 0:
            answer = boolean_node(False)
            ctx.result.add_group(
                "series_test_diverges",
                Step(
                    limit_node,
                    answer,
                    "series_nth_term_test_lim_nozero",
                    [CoreNode.constant("0")],
                ),
            )
            return answer
        if limit_value == 0:
            ctx.result.add_group(
                "series_test_inconclusive",
                Step(
                    from_sympy(limit_value),
                    _text("inconclusive"),
                    "series_nth_term_test_lim_zero",
                    [from_sympy(limit_value)],
                ),
            )
        return _integral_test(node, ctx, expression, lower, symbol)
    converges = value.is_finite is True
    answer = boolean_node(converges)
    ctx.result.add_group(
        "series_test_converges" if converges else "series_test_diverges",
        Step(left=node, right=answer, key="convergent" if converges else "divergent"),
    )
    return answer


def _pseries_convergence(node: CoreNode, ctx: SolveContext, exponent: sympy.Expr) -> CoreNode:
    """The ``p``-series rows of ``convergence``: ``p = 1`` → the harmonic series."""
    eq, num, var = CoreNode.node, CoreNode.constant, CoreNode.variable
    p_node = from_sympy(exponent)
    stated = eq(T.EQUALS, var("p"), p_node)
    ctx.result.add_group(
        CoreRichText(type="series_pseries_test_use_smpl", args=[p_node]),
        Step(node, stated, "series_pseries_test_use", [stated]),
    )
    converges = (exponent > 1) is sympy.true
    condition = eq(T.GREATER_THAN if converges else T.LESS_THAN_EQUAL, p_node, num("1"))
    answer = boolean_node(converges)
    ctx.result.add_group(
        "series_test_converges" if converges else "series_test_diverges",
        Step(
            stated,
            answer,
            "series_pseries_test_converges" if converges else "series_pseries_test_diverges",
            [condition],
        ),
    )
    return answer


def integral_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Интегральный признак сходимости (команда ``integral_test``)."""
    del args
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("интегральный признак применяется к ряду (сумме)")
    index, lower, _, expression = _parts(node)
    return _integral_test(node, ctx, expression, lower, sympy.Symbol(index))


def _integral_test(
    node: CoreNode,
    ctx: SolveContext,
    expression: CoreNode,
    lower: CoreNode,
    symbol: sympy.Symbol,
) -> CoreNode:
    """Интегральный признак: ``∫_N^∞ f(x) dx`` для ``f(x) = a(x)``.

    The rows: write the term as a function, take the improper
    integral (the whole verified chain), read the limit and only then conclude.
    """
    variable = sympy.Symbol("t") if str(symbol) != "t" else sympy.Symbol("u")
    function = to_sympy(expression).subs(symbol, variable)
    boundary = to_sympy(lower)
    ctx.result.add(Step(left=node, right=None, key="series_integral_test"))
    function_node = from_sympy(function)
    function_rule = CoreNode.node(
        T.EQUALS,
        CoreNode(type=T.FUNCTION, value="f", children=[CoreNode.variable(str(variable))]),
        function_node,
    )
    ctx.result.add_group(
        "series_integral_test_write_as_fun_smpl",
        Step(
            node,
            function_rule,
            "series_integral_test_write_as_fun",
            [expression, CoreNode.variable(str(symbol))],
        ),
    )
    definite = CoreNode.node(T.INTEGRAL_DEFINITE, lower, CoreNode.constant("∞"), function_node)
    approach = CoreNode.node(
        T.GREATER_THAN_EQUAL,
        CoreNode.variable(str(variable)),
        lower,
    )
    ctx.result.add_group(
        "series_integral_test_use_smpl",
        Step(
            function_rule,
            definite,
            "series_integral_test_use",
            [function_rule, approach],
        ),
    )
    try:
        value = sympy.integrate(function, (variable, boundary, sympy.oo))
    except (TypeError, ValueError, NotImplementedError) as error:
        raise SolveError("интегральный признак не применим") from error
    if value.has(sympy.Integral):
        raise SolveError("интегральный признак не применим")
    if value.is_finite is True:
        converges = True
    elif value in (sympy.oo, -sympy.oo, sympy.zoo) or value.is_finite is False:
        converges = False
    else:
        raise SolveError("интегральный признак не применим")
    improper = row_improper_card(definite, [str(variable)])
    if improper is not None:
        ctx.result.extend(improper)
    value_node = from_sympy(value)
    if converges:
        convergent = _text("convergent")
        ctx.result.add_group(
            "integrate_imp_converges_smpl",
            Step(value_node, convergent, "integrate_imp_converges"),
        )
        answer = boolean_node(True)
        ctx.result.add_group(
            "series_test_converges",
            Step(convergent, answer, "series_integral_test_converges"),
        )
        return answer
    divergent = _text("divergent")
    ctx.result.add_group(
        "integrate_imp_diverges_simple",
        Step(value_node, divergent, "integrate_imp_diverges", [value_node]),
    )
    answer = boolean_node(False)
    ctx.result.add_group(
        "series_test_diverges",
        Step(divergent, answer, "series_integral_test_diverges"),
    )
    return answer


def alt_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Признак Лейбница для знакочередующегося ряда (команда ``alt_test``)."""
    del args
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("признак Лейбница применяется к ряду (сумме)")
    index, _, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    term = to_sympy(expression)
    if not term.has((-sympy.Integer(1)) ** symbol):
        raise SolveError("ряд не знакочередующийся")

    magnitude = sympy.Abs(term)
    ctx.result.add(Step(left=node, right=None, key="series_alt_test"))
    limit = sympy.limit(magnitude, symbol, sympy.oo)
    ctx.result.add_group(
        "limit_solve",
        Step(
            node,
            CoreNode.node(T.LIMIT, CoreNode.constant("∞"), from_sympy(magnitude)),
            "series_alt_test_check",
            [CoreNode.variable(index)],
        ),
    )
    ratio = sympy.simplify(magnitude.subs(symbol, symbol + 1) / magnitude)
    decreasing = sympy.limit(ratio, symbol, sympy.oo)
    inequality = CoreNode.node(
        T.GREATER_THAN_EQUAL,
        CoreNode(type=T.FUNCTION, value="a_n", children=[CoreNode.variable(index)]),
        CoreNode(type=T.FUNCTION, value="a_n+1", children=[CoreNode.variable(index)]),
    )
    ctx.result.add_group(
        "compare_check_ineq",
        Step(
            CoreNode.constant("0"),
            inequality,
            "series_alt_test_snd_cond",
            [inequality],
        ),
    )
    if limit == 0 and decreasing.is_number and (decreasing <= 1) is sympy.true:
        true_node = _text("true")
        detail = SolveResult()
        domain = _alt_domain(magnitude, symbol)
        if domain is not None:
            detail.add_group(
                "calculate_short",
                Step(
                    CoreNode.node(T.ELEMENT_OF, CoreNode.variable(index), domain),
                    true_node,
                    "series_alt_test_true",
                    [
                        CoreNode.node(
                            T.EQUALS,
                            CoreNode.variable(index),
                            CoreNode.constant("1"),
                        ),
                        inequality,
                        CoreNode.variable(index),
                    ],
                ),
            )
            detail.set_solution(true_node)
        ctx.result.add_group(
            "series_alt_test_snd_cond_true_smpl",
            Step(
                inequality,
                true_node,
                "series_alt_test_snd_cond_true",
                [CoreNode.variable(index)],
                subresult=detail if domain is not None else None,
            ),
        )
        answer = boolean_node(True)
        ctx.result.add_group(
            "series_test_converges",
            Step(true_node, answer, "series_alt_test_converges"),
        )
        return answer
    answer = boolean_node(False)
    ctx.result.add_group(
        "series_test_diverges",
        Step(
            CoreNode.constant("0"),
            answer,
            "series_nth_term_test_lim_nozero",
            [CoreNode.constant("0")],
        ),
    )
    return answer


def _alt_domain(magnitude: sympy.Expr, symbol: sympy.Symbol) -> CoreNode | None:
    """The ``n`` where ``aₙ ≥ aₙ₊₁`` holds (the app's second-condition domain)."""
    try:
        condition = sympy.Ge(magnitude, magnitude.subs(symbol, symbol + 1))
        domain = sympy.solve_univariate_inequality(condition, symbol, relational=False)
    except (TypeError, ValueError, NotImplementedError):
        return None
    if domain is sympy.S.Reals or domain is sympy.S.EmptySet:
        return None
    try:
        return from_sympy(domain)
    except Exception:  # не все множества выражаются в контракте
        return None


def _remove_abs_step(
    ctx: SolveContext, limit_node: CoreNode, plain: sympy.Expr, symbol: sympy.Symbol
) -> None:
    """The app drops ``|·|`` when the terms are known to be non-negative."""
    ctx.result.add_group(
        "abs_remove_short",
        Step(
            limit_node,
            CoreNode.node(T.LIMIT, CoreNode.constant("∞"), from_sympy(plain)),
            "series_ratio_test_remove_abs",
            [
                CoreNode.constant("0"),
                CoreNode.node(
                    T.EQUALS,
                    CoreNode.variable(str(symbol)),
                    CoreNode.constant("0"),
                ),
            ],
        ),
    )


def ratio_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Признак Даламбера: сходимость ряда по пределу ``|aₙ₊₁/aₙ|``.

    the app's rows: the limit of the ratio, ``|·|`` dropped for positive
    terms, then the conclusion (``1`` leaves the question open).
    """
    del args
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("признак Даламбера применяется к ряду (сумме)")
    index, _, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    term = to_sympy(expression)
    if term == 0:
        raise SolveError("нулевой член ряда")
    plain = sympy.simplify(term.subs(symbol, symbol + 1) / term)
    ratio = sympy.simplify(sympy.Abs(plain))

    ctx.result.add(Step(left=node, right=None, key="series_ratio_test"))
    limit_node = CoreNode.node(T.LIMIT, CoreNode.constant("∞"), from_sympy(ratio))
    ctx.result.add_group(
        "limit_solve",
        Step(left=node, right=limit_node, key="series_ratio_test_use", args=[from_sympy(ratio)]),
    )
    if not plain.has(sympy.Abs) and plain.is_negative is not True:
        _remove_abs_step(ctx, limit_node, plain, symbol)
    limit = sympy.limit(ratio, symbol, sympy.oo)
    if limit in (sympy.oo, -sympy.oo, sympy.zoo):
        key, answer = "series_ratio_test_lim_inf", boolean_node(False)
        args_nodes = [from_sympy(sympy.oo)]
        header = "series_test_diverges"
    elif limit.is_number and (limit < 1) is sympy.true:
        key = "series_ratio_test_lim_ltone"
        answer, args_nodes = boolean_node(True), [CoreNode.constant("1")]
        header = "series_test_converges"
    elif limit.is_number and (limit > 1) is sympy.true:
        key, answer, args_nodes = (
            "series_ratio_test_lim_gtone",
            boolean_node(False),
            [CoreNode.constant("1")],
        )
        header = "series_test_diverges"
    else:
        inconclusive = _text("inconclusive")
        ctx.result.add_group(
            "series_test_inconclusive",
            Step(
                from_sympy(limit) if limit.is_number else limit_node,
                inconclusive,
                "series_ratio_test_lim_one",
                [CoreNode.constant("1")],
            ),
        )
        return inconclusive

    ctx.result.add_group(header, Step(left=node, right=answer, key=key, args=args_nodes))
    return answer


def root_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Радикальный признак (Коши): предел ``|aₙ|^(1/n)``."""
    del args
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("радикальный признак применяется к ряду (сумме)")
    index, _, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    term = to_sympy(expression)
    plain = sympy.Abs(term) ** (sympy.Integer(1) / symbol)
    root = sympy.Abs(term) ** (sympy.Integer(1) / symbol)

    ctx.result.add(Step(left=node, right=None, key="series_root_test"))
    limit_node = CoreNode.node(T.LIMIT, CoreNode.constant("∞"), from_sympy(root))
    ctx.result.add_group(
        "limit_solve",
        Step(left=node, right=limit_node, key="series_root_test_use", args=[from_sympy(root)]),
    )
    ctx.result.add_group(
        "abs_remove_short",
        Step(
            limit_node,
            CoreNode.node(
                T.LIMIT,
                CoreNode.constant("∞"),
                from_sympy(plain.subs(sympy.Abs(term), term)),
            ),
            "series_root_test_remove_abs",
            [
                CoreNode.constant("0"),
                CoreNode.node(
                    T.EQUALS,
                    CoreNode.variable(str(symbol)),
                    CoreNode.constant("0"),
                ),
            ],
        ),
    )
    limit = sympy.limit(root, symbol, sympy.oo)
    if limit in (sympy.oo, -sympy.oo, sympy.zoo):
        key, answer, args_nodes = (
            "series_root_test_lim_inf",
            boolean_node(False),
            [from_sympy(sympy.oo)],
        )
        header = "series_test_diverges"
    elif limit.is_number and (limit < 1) is sympy.true:
        key, answer, args_nodes = (
            "series_root_test_lim_ltone",
            boolean_node(True),
            [CoreNode.constant("1")],
        )
        header = "series_test_converges"
    elif limit.is_number and (limit > 1) is sympy.true:
        key, answer, args_nodes = (
            "series_root_test_lim_gtone",
            boolean_node(False),
            [CoreNode.constant("1")],
        )
        header = "series_test_diverges"
    else:
        inconclusive = _text("inconclusive")
        ctx.result.add_group(
            "series_test_inconclusive",
            Step(
                from_sympy(limit) if limit.is_number else limit_node,
                inconclusive,
                "series_root_test_lim_one",
                [CoreNode.constant("1")],
            ),
        )
        return inconclusive
    ctx.result.add_group(header, Step(left=node, right=answer, key=key, args=args_nodes))
    return answer


def nth_term_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Необходимый признак сходимости: предел общего члена.

    A non-zero limit diverges; a zero limit is «не даёт ответа» (the app's
    ``inconclusive`` card), not an error.
    """
    del args
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("необходимый признак применяется к ряду (сумме)")
    index, _, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    term = to_sympy(expression)

    ctx.result.add(Step(left=node, right=None, key="series_nth_term_test"))
    ctx.result.add_group(
        "limit_solve",
        Step(left=node, right=None, key="series_nth_term_test_use", args=[from_sympy(term)]),
    )
    limit = sympy.limit(term, symbol, sympy.oo)
    if limit.is_number and limit != 0:
        answer = boolean_node(False)
        ctx.result.add_group(
            "series_test_diverges",
            Step(
                left=node,
                right=answer,
                key="series_nth_term_test_lim_nozero",
                args=[CoreNode.constant("0")],
            ),
        )
        return answer
    if limit.is_number and limit == 0:
        inconclusive = _text("inconclusive")
        ctx.result.add_group(
            "series_test_inconclusive",
            Step(
                from_sympy(limit),
                inconclusive,
                "series_nth_term_test_lim_zero",
                [from_sympy(limit)],
            ),
        )
        return inconclusive
    raise SolveError("необходимый признак сходимости не даёт ответа")


def radius_of_convergence(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Радиус сходимости степенного ряда ``Σ aₙ·xⁿ``.

    the app's rows: the limit of ``|aₙ₊₁/aₙ|``, the limit without ``n``
    (a finite radius) or the separated factor of ``x`` (an infinite one), the
    absolute-value comparison (finite) or ``|x|·0`` (infinite), then the radius.
    """
    del args
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("радиус сходимости — у степенного ряда (суммы)")
    index, _, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    variable = next((name for name in ctx.variables if name != index), None)
    if variable is None:
        raise SolveError("в степенном ряде нет переменной")
    xsym = sympy.Symbol(variable)

    term = to_sympy(expression)
    coefficient = sympy.simplify(term / xsym**symbol)
    if coefficient.has(xsym):
        raise SolveError("ряд не степенной: нужен вид aₙ·xⁿ")
    ratio = sympy.simplify(sympy.Abs(term.subs(symbol, symbol + 1) / term))
    abs_x = sympy.Abs(xsym)
    factor = sympy.simplify(ratio / abs_x)
    if factor.has(xsym) or factor == 0:
        raise SolveError("ряд не степенной: нужен вид aₙ·xⁿ")
    limit_value = sympy.limit(ratio, symbol, sympy.oo)
    coefficient_limit = sympy.limit(factor, symbol, sympy.oo)
    radius = sympy.oo if coefficient_limit == 0 else 1 / coefficient_limit

    ctx.result.add(Step(left=node, right=None, key="convergence_radius_find"))
    limit_node = CoreNode.node(T.LIMIT, CoreNode.constant("∞"), from_sympy(ratio))
    ctx.result.add_group(
        "limit_solve",
        Step(
            left=node,
            right=limit_node,
            key="convergence_radius_limit",
            args=[from_sympy(ratio)],
        ),
    )
    if not ratio.has(symbol) and limit_value.has(xsym):
        # The limit already has no n: |x|/R (a finite radius).
        ctx.result.add_group(
            "limit_solve",
            Step(
                limit_node,
                from_sympy(ratio),
                "convergence_radius_no_var",
                [
                    CoreNode.variable(index),
                    CoreNode.node(T.EQUALS, limit_node, from_sympy(ratio)),
                ],
            ),
        )
        abs_node = from_sympy(ratio)
        inequality = CoreNode.node(T.LESS_THAN, abs_node, CoreNode.constant("1"))
        ctx.result.add_group(
            "convergence_radius_abs_smpl",
            Step(
                left=abs_node,
                right=inequality,
                key="convergence_radius_abs",
                args=[CoreNode.constant("1")],
            ),
        )
        final_left = inequality
    else:
        # |x| · g(n): take |x| out of the limit, then g(n) → 0, so R = ∞.
        factor_node = from_sympy(factor)
        separated = CoreNode.node(
            T.MULTIPLY, CoreNode.node(T.ABS, CoreNode.variable(variable)), factor_node
        )
        separated_limit = CoreNode.node(T.LIMIT, CoreNode.constant("∞"), separated)
        ctx.result.add_group(
            "write_as_product",
            Step(
                limit_node,
                separated_limit,
                "convergence_radius_frac_sep",
                [factor_node],
            ),
        )
        inside_limit = CoreNode.node(T.LIMIT, CoreNode.constant("∞"), factor_node)
        front = CoreNode.node(
            T.MULTIPLY, CoreNode.node(T.ABS, CoreNode.variable(variable)), inside_limit
        )
        ctx.result.add_group(
            "trans_msg",
            Step(
                separated_limit,
                front,
                "convergence_radius_const_front",
                [
                    CoreNode.node(T.ABS, CoreNode.variable(variable)),
                    CoreNode.variable(index),
                    CoreNode.node(T.EQUALS, inside_limit, from_sympy(coefficient_limit)),
                ],
            ),
        )
        stripped = CoreNode.node(
            T.MULTIPLY,
            CoreNode.node(T.ABS, CoreNode.variable(variable)),
            CoreNode.node(T.LIMIT, CoreNode.constant("∞"), factor_node),
        )
        ctx.result.add_group(
            "abs_remove_short",
            Step(
                front,
                stripped,
                "series_root_test_remove_abs",
                [
                    CoreNode.constant("0"),
                    CoreNode.node(
                        T.EQUALS,
                        CoreNode.variable(index),
                        CoreNode.constant("0"),
                    ),
                ],
            ),
        )
        zero = CoreNode.constant(str(coefficient_limit))
        reduced = CoreNode.node(T.MULTIPLY, CoreNode.node(T.ABS, CoreNode.variable(variable)), zero)
        ctx.result.add_group(
            "evaluate",
            Step(stripped, reduced, "limit_solve"),
        )
        ctx.result.add_group(
            "product",
            Step(
                reduced,
                CoreNode.constant("0"),
                "mul_with_zero",
                [CoreNode.constant("0")],
            ),
        )
        final_left = CoreNode.constant("0")
    if radius in (sympy.oo, -sympy.oo, sympy.zoo):
        answer = from_sympy(sympy.oo)
        key = "convergence_radius_conv_inf"
    else:
        answer = from_sympy(radius)
        key = "convergence_radius_conv"
    named = CoreNode.node(T.EQUALS, CoreNode.variable("R"), answer)
    ctx.result.add_group(
        CoreRichText(type="convergence_radius_conv_smpl", args=[named]),
        Step(
            left=final_left,
            right=named,
            key=key,
            args=[CoreNode.variable(variable), named],
        ),
    )
    return answer


def pseries_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Признак обобщённого гармонического ряда: ``Σ 1/nᵖ`` сходится при ``p > 1``."""
    del args
    index, _, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    term = sympy.simplify(to_sympy(expression))
    _, rest = term.as_coeff_Mul()
    if not isinstance(rest, sympy.Pow) or rest.base != symbol:
        raise SolveError("ряд не обобщённый гармонический")
    exponent = -rest.exp

    ctx.result.add(Step(left=node, right=None, key="series_pseries_test"))
    ctx.result.add_group(
        CoreRichText(type="series_pseries_test_use_smpl", args=[from_sympy(exponent)]),
        Step(
            left=node,
            right=None,
            key="series_pseries_test_use",
            args=[from_sympy(exponent)],
        ),
    )
    converges = (exponent > 1) is sympy.true
    condition = CoreNode.node(
        T.GREATER_THAN if converges else T.LESS_THAN_EQUAL,
        from_sympy(exponent),
        CoreNode.constant("1"),
    )
    answer = boolean_node(converges)
    key = "series_pseries_test_converges" if converges else "series_pseries_test_diverges"
    ctx.result.add_group(
        "series_test_converges" if converges else "series_test_diverges",
        Step(left=node, right=answer, key=key, args=[condition]),
    )
    return answer


def geom_series_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Признак геометрического ряда: отношение соседних членов постоянно."""
    del args
    index, _, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    term = to_sympy(expression)
    if term == 0:
        raise SolveError("нулевой член ряда")
    ratio = sympy.simplify(term.subs(symbol, symbol + 1) / term)
    if ratio.has(symbol):
        raise SolveError("ряд не геометрический")

    ctx.result.add(Step(left=node, right=None, key="series_geom_series_test"))
    converges = (sympy.Abs(ratio) < 1) is sympy.true
    condition = CoreNode.node(
        T.LESS_THAN if converges else T.GREATER_THAN_EQUAL,
        from_sympy(sympy.Abs(ratio)),
        CoreNode.constant("1"),
    )
    answer = boolean_node(converges)
    key = "series_geom_series_test_converges" if converges else "series_geom_series_test_diverges"
    ctx.result.add_group(
        "series_test_converges" if converges else "series_test_diverges",
        Step(left=node, right=answer, key=key, args=[condition]),
    )
    return answer


def _series_converges(expression: CoreNode, symbol: sympy.Symbol, lower: CoreNode) -> bool | None:
    """Сходится ли ряд с данным общим членом (``None`` — не определить)."""
    term = to_sympy(expression)
    value = sympy.summation(term, (symbol, to_sympy(lower), sympy.oo))
    if not value.has(sympy.Sum):
        if value.is_finite is True:
            return True
        if value in (sympy.oo, -sympy.oo, sympy.zoo) or value.is_finite is False:
            return False
        return None
    variable = sympy.Symbol("t") if str(symbol) != "t" else sympy.Symbol("u")
    integral = sympy.integrate(term.subs(symbol, variable), (variable, to_sympy(lower), sympy.oo))
    if integral.is_finite is True:
        return True
    if integral in (sympy.oo, -sympy.oo, sympy.zoo) or integral.is_finite is False:
        return False
    return None


def _reference(node: CoreNode) -> tuple[CoreNode, sympy.Symbol]:
    """Ряд-эталон из аргумента команды."""
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("ряд-эталон — это сумма")
    index, _, _, expression = _parts(node)
    return expression, sympy.Symbol(index)


def direct_comparison_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Признак сравнения: почленное сравнение с рядом-эталоном (аргумент)."""
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("признак сравнения применяется к ряду (сумме)")
    ctx.require(len(args) == 1, "нужен ряд-эталон")
    index, lower, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    reference_expression, _ = _reference(args[0])
    reference_converges = _series_converges(reference_expression, sympy.Symbol(index), lower)
    ctx.require(reference_converges is not None, "ряд-эталон не исследован")

    ratio = sympy.limit(to_sympy(expression) / to_sympy(reference_expression), symbol, sympy.oo)
    ctx.require(ratio.is_number is True, "сравнение членов не установлено")
    if reference_converges:
        ctx.require(
            (ratio <= 1) is sympy.true,
            "сравнение членов не выполнено: aₙ не меньше bₙ",
        )
    else:
        ctx.require(
            (ratio >= 1) is sympy.true,
            "сравнение членов не выполнено: aₙ не больше bₙ",
        )
    ctx.result.add(Step(left=node, right=None, key="series_direct_comp_test"))
    ctx.result.add_group(
        "series_direct_comp_test_use_smpl",
        Step(left=node, right=None, key="series_direct_comp_test_use", args=[args[0]]),
    )
    if reference_converges:
        key, converges = "series_direct_comp_test_converges", True
    else:
        key, converges = "series_direct_comp_test_diverges", False
    answer = boolean_node(converges)
    ctx.result.add_group(
        "series_test_converges" if converges else "series_test_diverges",
        Step(left=node, right=answer, key=key, args=[args[0]]),
    )
    return answer


def limit_comparison_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Предельный признак сравнения с рядом-эталоном (аргумент)."""
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("предельный признак сравнения применяется к ряду (сумме)")
    ctx.require(len(args) == 1, "нужен ряд-эталон")
    index, lower, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    reference_expression, _ = _reference(args[0])
    reference_converges = _series_converges(reference_expression, symbol, lower)
    ctx.require(reference_converges is not None, "ряд-эталон не исследован")

    ratio = sympy.limit(to_sympy(expression) / to_sympy(reference_expression), symbol, sympy.oo)
    ctx.require(
        ratio.is_finite is True and ratio.is_positive is True,
        "предельное отношение не конечно и не положительно",
    )
    ctx.result.add(Step(left=node, right=None, key="series_limit_test"))
    if reference_converges:
        key, converges = "series_limit_test_converges", True
        ctx.result.add_group(
            "series_limit_test_use_smpl",
            Step(left=node, right=None, key="series_limit_test_use_conv", args=[args[0]]),
        )
    else:
        key, converges = "series_limit_test_diverges", False
        ctx.result.add_group(
            "series_limit_test_use_smpl",
            Step(left=node, right=None, key="series_limit_test_use_div", args=[args[0]]),
        )
    answer = boolean_node(converges)
    ctx.result.add_group(
        "series_test_converges" if converges else "series_test_diverges",
        Step(left=node, right=answer, key=key, args=[args[0]]),
    )
    return answer


__all__ = [
    "alt_test",
    "convergence",
    "direct_comparison_test",
    "geom_series_test",
    "integral_test",
    "limit_comparison_test",
    "nth_term_test",
    "pseries_test",
    "radius_of_convergence",
    "ratio_test",
    "root_test",
    "solve_series",
]
