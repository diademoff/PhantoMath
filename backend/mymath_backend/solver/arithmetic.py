"""Вычисление арифметики по порядку действий.

Первый модуль решателя: считает выражения из чисел, знаков, скобок,
неявного умножения и степеней. Каждая операция добавляет шаг с ключом
объяснения (``add``, ``sub``, ``mul``,
``div``, ``calculate_short``), поэтому тексты подставляются автоматически.

Покрыто: числовые константы, ``+ - * /``, неявное умножение, ``^``,
скобки ``BRACKET``, возведение отрицательного основания в нечётную степень.

Не покрыто (следующие модули): буквы, ``FRACTION`` как отдельный узел,
функции, уравнения, неравенства.

Известное упрощение: ``left`` шага -- сам свёртываемый узел, а не полное
выражение с уже посчитанной частью. Для арифметики это читаемо, но при
переходе к уравнениям придётся вести накопительную строку.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType
from ..node_types import CoreNodeType as T
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

KEY_CALCULATE = "calculate_short"

# Ключ пояснения на операцию. Берём из словаря, чтобы не выдумывать формулировки.
# Для операций, у которых в словаре нет точной формулировки, берём
# calculate_short («Посчитать»): он честнее, чем чужой по смыслу ключ.
_EXPLANATION_KEY: dict[CoreNodeType, str] = {
    T.ADD: "add",
    T.SUBTRACT: "sub",
    T.MULTIPLY: "mul",
    T.MULTIPLY_IMPLICIT: "mul",
    T.DIVIDE: "div",
    T.POWER: KEY_CALCULATE,
    T.NEGATIVE: KEY_CALCULATE,
    T.POSITIVE: KEY_CALCULATE,
}

# Пояснения для вырожденных случаев: они отвечают на «а почему так?».
_KEY_DIV_ZERO = "div_with_zero"
_KEY_DIV_ONE = "div_with_one"
_KEY_ADD_ZERO = "add_with_zero"
_KEY_SUB_SELF = "sub_with_self_num"
_KEY_MUL_ZERO = "mul_with_zero"
_KEY_MUL_NEG_ONE = "mul_with_neg_one"
_KEY_MUL_ONE = "mul_with_one"
_KEY_CALC_SUM = "calc_sum"
_KEY_CALC_DIFF = "calc_diff"
_KEY_FRAC_REDUCE = "frac_reduce_frac_num"

_MAX_POWER = 4096
"""Потолок показателя степени.

Без него ``9^9^9`` уводит вычисление в бесконечный рост целых и
``MemoryError``.
"""

_BINARY_OPS = (T.ADD, T.SUBTRACT, T.MULTIPLY, T.MULTIPLY_IMPLICIT, T.DIVIDE, T.POWER)


def as_fraction(node: CoreNode) -> Fraction:
    """Числовое значение узла. Буквы не принимаются."""
    if node.type is not T.CONSTANT:
        raise SolveError(f"ожидалось число, получено {node.type}")
    text = (node.value or "").strip()
    if not text:
        raise SolveError("пустая константа")
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError) as err:
        raise SolveError(f"не удалось прочитать число {text!r}") from err


def number_of(node: CoreNode) -> Fraction:
    """Число, записанное листом до свёртки: минус, дробь, скобка, плюс.

    Матрицы читают ячейки как есть — ``mat(…;…,-2)`` приходит узлом
    ``NEGATIVE(CONSTANT)``, а ``1/2`` — узлом ``FRACTION``. Одного
    :func:`as_fraction` для этого мало: он понимает только готовую константу.
    """
    if node.type in (T.NEGATIVE, T.POSITIVE) and len(node.children) == 1:
        value = number_of(node.children[0])
        return -value if node.type is T.NEGATIVE else value
    if node.type is T.BRACKET and len(node.children) == 1:
        return number_of(node.children[0])
    if node.type in (T.FRACTION, T.DIVIDE) and len(node.children) == 2:
        denominator = number_of(node.children[1])
        if denominator == 0:
            raise UndefinedError(
                "деление на ноль",
                _KEY_DIV_ZERO,
                explanation_args=[CoreNode.constant("0")],
            )
        return number_of(node.children[0]) / denominator
    return as_fraction(node)


def format_number(value: Fraction) -> str:
    """Записать дробную величину для показа.

    Целые -- без дробной части, остальные -- числитель/знаменатель.
    """
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


def is_zero(node: CoreNode) -> bool:
    """Свёрнулось ли поддерево в ноль."""
    return node.type is T.CONSTANT and (node.value or "") == "0"


def _log_power_identity(node: CoreNode, ctx: SolveContext) -> CoreNode | None:
    """``a^(log_a x) = x``: a power of the base of its own logarithm is the argument.

    the app shows one row, ``using_sim``, with the definition as the argument.
    Applies to ``ln`` too: ``e^(ln x)``.
    """
    base, exponent = node.children
    while base.type is T.BRACKET and len(base.children) == 1:
        base = base.children[0]
    while exponent.type is T.BRACKET and len(exponent.children) == 1:
        exponent = exponent.children[0]
    if base.type is not T.CONSTANT:
        return None
    a, x = CoreNode.variable("a"), CoreNode.variable("b")
    if exponent.type is T.LOG and len(exponent.children) == 2:
        argument, log_base = exponent.children
        pairs = log_base.type is T.CONSTANT and log_base.value == base.value
        law = CoreNode.node(
            T.EQUALS,
            CoreNode.node(T.POWER, a, CoreNode.node(T.LOG, x, a)),
            x,
        )
    elif exponent.type is T.LOG10 and len(exponent.children) == 1:
        argument, pairs = exponent.children[0], base.value == "10"
        law = CoreNode.node(
            T.EQUALS,
            CoreNode.node(T.POWER, base, CoreNode.node(T.LOG10, x)),
            x,
        )
    elif exponent.type is T.LN and len(exponent.children) == 1:
        argument, pairs = exponent.children[0], base.value == "e"
        law = CoreNode.node(
            T.EQUALS,
            CoreNode.node(T.POWER, base, CoreNode.node(T.LN, x)),
            x,
        )
    else:
        return None
    if not pairs:
        return None
    ctx.result.add_group("simplify", Step(node, argument, "using_sim", [law]))
    return argument


@solver_for(
    T.CONSTANT,
    T.VARIABLE,
    T.ADD,
    T.SUBTRACT,
    T.MULTIPLY,
    T.MULTIPLY_IMPLICIT,
    T.DIVIDE,
    T.POWER,
    T.NEGATIVE,
    T.POSITIVE,
    T.BRACKET,
)
def solve_arithmetic(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Свернуть поддерево в число, добавив шаг на каждую операцию.

    Обход идёт в глубину, поэтому сначала считаются вложенные операции и
    только потом внешняя. Это и есть порядок действий: степени, затем
    умножение и деление, затем сложение и вычитание.

    Возвращает константу со значением поддерева; скобки возвращаются как
    ``BRACKET`` с уже свёрнутым содержимым, чтобы сохранить видимость
    группировки в последующих шагах.
    """
    if node.type in (T.CONSTANT, T.VARIABLE):
        _check_leaf(node)
        return node

    if node.type is T.POWER and (defined := _log_power_identity(node, ctx)) is not None:
        return defined
    node = _flatten_fraction_sum(node)
    if ctx.depth == 0 and (shown := _whole_fraction_rows(node, ctx)) is not None:
        return shown
    if ctx.depth == 0 and (shown := _unary_minus_rows(node, ctx)) is not None:
        return shown
    if ctx.depth == 0 and (shown := _minus_negative_rows(node, ctx)) is not None:
        return shown
    if ctx.depth == 0 and (shown := _sum_chain_rows(node, ctx)) is not None:
        return shown
    if ctx.depth == 0 and (shown := _root_product_rows(node, ctx)) is not None:
        return shown
    if ctx.depth == 0 and (shown := _negative_power_rows(node, ctx)) is not None:
        return shown
    # Дети сворачиваются через общий реестр: так арифметика складывается с
    # другими модулями (например, дробь сворачивается своим модулем).
    ctx.depth += 1
    try:
        folded = [route(child, ctx) for child in node.children]
    finally:
        ctx.depth -= 1

    if node.type is T.BRACKET:
        ctx.require(len(folded) == 1, "в скобках должно быть одно выражение")
        return CoreNode(type=T.BRACKET, children=folded)
    if not folded:
        raise SolveError(f"узел {node.type} без операндов")
    if any(child.type is T.EMPTY for child in folded):
        # Неопределённая часть (√−2) делает неопределённым всё выражение:
        # Решатель отвечает «Не определено» вместо свёртки соседних слагаемых.
        raise UndefinedError(
            "выражение содержит неопределённую часть",
            "root_sqr_neg",
            header="expr_not_def_in_r",
        )
    if not all(_is_settled(c) for c in folded):
        raise SolveError(f"после свёртки в {node.type} остались не-константы")

    if node.type is T.POWER:
        shown = _decimal_power_card(node, folded, ctx)
        if shown is not None:
            return shown

    values = [_value_of(c) for c in folded]
    result, key = _apply(node.type, values)
    constant = CoreNode.constant(format_number(result))
    from .fractions import addition_rows, product_detail, product_rows

    # A degenerate change (zero, self, one, minus one) is one row by itself: the
    # fraction screens would only repeat it.
    plain = key in (_KEY_ADD_ZERO, _KEY_SUB_SELF, _KEY_MUL_ZERO, _KEY_MUL_NEG_ONE, _KEY_MUL_ONE)
    # Common-denominator rows only for fraction operands; decimals add as plain numbers.
    is_fraction = all(
        "/" in (c.value or "") or v.denominator == 1 for c, v in zip(folded, values, strict=True)
    )
    if (
        not plain
        and is_fraction
        and (
            rows := addition_rows(node.type, values, constant)
            or product_rows(node.type, values, constant)
        )
    ):
        for header, steps in rows:
            ctx.result.add_group(header, *steps)
        return constant
    if (
        node.type is T.POWER
        and values[1] == 2
        and values[0].denominator == 1
        and values[0] >= 2
        and folded[0].type is T.CONSTANT
    ):
        # n^2 is written as n x n, then multiplied.
        base = folded[0]
        product = CoreNode.node(T.MULTIPLY, base, base)
        power = CoreNode(node.type, children=folded)
        if ctx.depth > 0:  # part of a larger expression: one stage, the rows on its detail screen
            inner = SolveResult()
            inner.add_group("write_as_mul_short", Step(power, product, "pow_to_mul"))
            inner.add_group("calculate_short", Step(product, constant, "mul"))
            inner.set_solution(constant)
            ctx.result.add(
                Step(power, constant, "pow", subresult=inner),
                [CoreRichText(type="calculate_short")],
            )
            return constant
        ctx.result.add_group("write_as_mul_short", Step(power, product, "pow_to_mul"))
        ctx.result.add_group("calculate_short", Step(product, constant, "mul"))
        return constant
    if node.type is T.NEGATIVE and ctx.depth > 0 and folded[0].type is T.CONSTANT:
        # a typed −1 inside 2·(−1 + 4) is a number, not a «−1 → −1» row (2·3, 6)
        return constant
    # decimals multiply in one plain row (1,5*4)
    decimal = any("." in (c.value or "") for c in folded)
    detail = None if decimal else product_detail(node.type, values, constant)
    step = Step(
        left=CoreNode(node.type, children=folded),
        right=constant,
        key=key,
        args=_step_args(key, node, constant),
        subresult=detail,
    )
    # every operation is its own row (main step).
    ctx.result.add_group(detail.header if detail and detail.header else key, step)
    return constant


def _compensation_methods(node: CoreNode, variables: list[str]) -> list[SolveResult] | None:
    """``m.5 * k`` for a positive integer ``k``: the plain row and multiplication by compensation.

    (1,5*4): write 1,5 as 2 - 0,5, distribute, multiply, subtract.
    """
    first, factor = node.children
    if not (
        first.type is T.CONSTANT
        and factor.type is T.CONSTANT
        and (first.value or "").endswith(".5")
        and (factor.value or "").isdigit()
        and int(factor.value or 0) >= 2
    ):
        return None
    try:
        base = Fraction(first.value or "")
    except ValueError:
        return None
    if base <= 0 or base.denominator != 2:
        return None
    k = int(factor.value or 0)
    up, half = int(base) + 1, Fraction(1, 2)

    def number(value: Fraction | int) -> CoreNode:
        return CoreNode.constant(format_number(Fraction(value)))

    plain = SolveResult()
    plain.set_solution(route(node, SolveContext(plain, list(variables))))
    wrapped = CoreNode.node(T.BRACKET, CoreNode.node(T.SUBTRACT, number(up), number(half)))
    written = CoreNode.node(T.MULTIPLY, wrapped, factor)
    spread = CoreNode.node(
        T.SUBTRACT,
        CoreNode.node(T.MULTIPLY, number(up), factor),
        CoreNode.node(T.MULTIPLY, number(half), factor),
    )
    first_done = CoreNode.node(
        T.SUBTRACT, number(up * k), CoreNode.node(T.MULTIPLY, number(half), factor)
    )
    second_done = CoreNode.node(T.SUBTRACT, number(up * k), number(half * k))
    total = number(base * k)
    a, b = CoreNode.variable("a"), CoreNode.variable("b")
    law = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.MULTIPLY, CoreNode.node(T.NEGATIVE, a), b),
        CoreNode.node(
            T.NEGATIVE,
            CoreNode.node(T.BRACKET, CoreNode.node(T.MULTIPLY, a, b)),
        ),
    )
    detail = SolveResult()
    detail.add_group(
        "neg_mul_msg",
        Step(
            CoreNode.node(T.MULTIPLY, CoreNode.node(T.NEGATIVE, number(half)), factor),
            CoreNode.node(
                T.NEGATIVE,
                CoreNode.node(T.BRACKET, CoreNode.node(T.MULTIPLY, number(half), factor)),
            ),
            "mul_neg_pos",
            [law],
        ),
    )
    detail.add_group(
        "multiply",
        Step(
            CoreNode.node(
                T.NEGATIVE,
                CoreNode.node(T.BRACKET, CoreNode.node(T.MULTIPLY, number(half), factor)),
            ),
            CoreNode.node(T.NEGATIVE, number(half * k)),
            "mul",
        ),
    )
    detail.set_solution(CoreNode.node(T.NEGATIVE, number(half * k)))
    rows = SolveResult()
    rows.add_group("write_as_diff_short", Step(node, written, "write_as_diff", [first]))
    rows.add_group("remove_bracket_short", Step(written, spread, "mul_bracket", [factor]))
    rows.add_group(
        "calculate_short",
        Step(spread, first_done, "mul"),
        Step(first_done, second_done, "mul", subresult=detail),
    )
    rows.add_group("calculate_short", Step(second_done, total, "sub"))
    rows.set_solution(total)
    return [plain, rows]


@method_provider(T.MULTIPLY)
def distributive_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """``(a + b) * k`` or ``k * (a + b)``: the plain order and the distributive property.

    both are offered; any other product is left to the plain path.
    """
    if len(node.children) != 2:
        return []
    if (compensation := _compensation_methods(node, variables)) is not None:
        return compensation
    first, second = node.children
    bracket_first = first.type is T.BRACKET
    bracket = first if bracket_first else second
    factor = second if bracket_first else first
    inner = bracket.children[0] if bracket.type is T.BRACKET else None
    if inner is None or inner.type is not T.ADD or len(inner.children) != 2:
        return []
    values = [_plain_number(c) for c in (*inner.children, factor)]
    if any(v is None for v in values):
        return []
    a, b, k = (v for v in values if v is not None)
    plain = SolveResult()
    plain.set_solution(route(node, SolveContext(plain, list(variables))))

    def number(value: Decimal) -> CoreNode:
        text = format(abs(value).normalize(), "f")
        constant = CoreNode.constant(text)
        return CoreNode.node(T.NEGATIVE, constant) if value < 0 else constant

    def product(value: Decimal) -> CoreNode:
        if bracket_first:
            # a negative factor on the right keeps its brackets: 2·(−2)
            right = CoreNode.node(T.BRACKET, factor) if k < 0 else factor
            return CoreNode.node(T.MULTIPLY, number(value), right)
        right = number(value)
        return CoreNode.node(
            T.MULTIPLY, factor, CoreNode.node(T.BRACKET, right) if value < 0 else right
        )

    def multiply_key(value: Decimal) -> str:
        if value == 0 or k == 0:
            return "mul_with_zero"
        return "mul_with_one" if 1 in (abs(value), abs(k)) else "mul"

    def pair(left: CoreNode, right_value: Decimal) -> CoreNode:
        # The app writes a negative second term as a difference: −9 − 12
        if right_value < 0:
            return CoreNode.node(T.SUBTRACT, left, number(-right_value))
        return CoreNode.node(T.ADD, left, number(right_value))

    first_value, second_value = a * k, b * k
    expanded = CoreNode.node(T.ADD, product(a), product(b))
    half = CoreNode.node(T.ADD, number(first_value), product(b))
    summed = pair(number(first_value), second_value)
    total = plain.solution if plain.solution is not None else number(first_value + second_value)
    if first_value == 0:
        sum_key = "add_with_zero"
    elif first_value + second_value == 0:
        sum_key = "sub_with_self_num"
    elif second_value < 0:
        sum_key = "calc_diff"
    elif first_value < 0:
        sum_key = "calc_sum"
    else:
        sum_key = "add"
    spread = SolveResult()
    spread.add_group("remove_bracket_short", Step(node, expanded, "mul_bracket", [factor]))
    spread.add_group(
        "calculate_short",
        Step(expanded, half, multiply_key(a)),
        Step(half, summed, multiply_key(b)),
    )
    spread.add_group("calculate_short", Step(summed, total, sum_key))
    spread.set_solution(total)
    return [plain, spread]


def _plain_number(node: CoreNode) -> Decimal | None:
    """``3``, ``0.5`` or ``−2`` as typed; ``None`` for anything else."""
    sign = 1
    if node.type is T.NEGATIVE and len(node.children) == 1:
        sign, node = -1, node.children[0]
    text = node.value or ""
    if node.type is not T.CONSTANT or not text.replace(".", "", 1).isdigit():
        return None
    return sign * Decimal(text)


def _sum_chain_rows(node: CoreNode, ctx: SolveContext) -> CoreNode | None:
    """``a + b*c - d`` for integers: the products first, then one row for the whole sum.

    Three or more terms stay on a single row whose detail screen
    adds them one by one; a chain of bare numbers was not verified and stays as it is.
    """
    terms: list[tuple[CoreNodeType, CoreNode]] = []
    current = node
    while current.type in (T.ADD, T.SUBTRACT) and len(current.children) == 2:
        terms.append((current.type, current.children[1]))
        current = current.children[0]
    terms.append((T.ADD, current))
    terms.reverse()
    operands = [term for _, term in terms]
    if len(terms) < 3 or all(term.type is T.CONSTANT for term in operands):
        return None
    try:
        if any(
            _value_of(route(term, SolveContext(SolveResult()))).denominator != 1
            for term in operands
        ):
            return None
    except SolveError:
        return None
    ctx.depth += 1
    try:
        folded = [route(term, ctx) for term in operands]
    finally:
        ctx.depth -= 1
    # a bracketed number is just that number inside the chain (it would be re-routed forever)
    folded = [c.children[0] if c.type is T.BRACKET and len(c.children) == 1 else c for c in folded]
    chain = folded[0]
    for (op, _), value in zip(terms[1:], folded[1:], strict=True):
        chain = CoreNode.node(op, chain, value)
    values = [_value_of(c) for c in folded]
    detail = SolveResult()
    if (
        len(folded) >= 2
        and terms[-1][0] is T.SUBTRACT
        and all(op is T.ADD for op, _ in terms[1:-1])
        and all(value > 0 for value in values)
    ):
        # The app sums the positive terms first (`2+12`), then subtracts the last one.
        prefix = sum(values[:-1], Fraction(0))
        drained = CoreNode.node(T.SUBTRACT, CoreNode.constant(format_number(prefix)), folded[-1])
        total = CoreNode.constant(format_number(prefix - values[-1]))
        detail.add_group("calc_sum", Step(chain, drained, "sum_real_positive"))
        detail.add_group("calculate_short", Step(drained, total, "sub"))
        detail.set_solution(total)
    else:
        total = route(chain, SolveContext(detail))
        detail.set_solution(total)
    ctx.result.add_group("calculate_short", Step(chain, total, "sum", subresult=detail))
    return total


def _root_product_rows(node: CoreNode, ctx: SolveContext) -> CoreNode | None:
    """``sqrt(a) * sqrt(b)`` for positive integers: join under one root, then evaluate the root.

    The two rows the card shows for ``sqrt(8) * sqrt(2)``.
    """
    if node.type not in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) or len(node.children) != 2:
        return None
    first, second = node.children
    if not all(
        child.type is T.ROOT2
        and len(child.children) == 1
        and child.children[0].type is T.CONSTANT
        and (child.children[0].value or "").isdigit()
        and child.children[0].value != "0"
        for child in (first, second)
    ):
        return None
    joined = CoreNode.node(
        T.ROOT2,
        CoreNode.constant(
            str(int(first.children[0].value or 0) * int(second.children[0].value or 0))
        ),
    )
    detail = SolveResult()
    detail.add_group("root_radical_msg", Step(node, joined, "root_mul"))
    detail.add_group(
        "multiply",
        Step(
            CoreNode.node(T.MULTIPLY, first.children[0], second.children[0]),
            CoreNode.constant(
                str(int(first.children[0].value or 0) * int(second.children[0].value or 0))
            ),
            "mul",
        ),
    )
    detail.set_solution(joined)
    ctx.result.add_group("calculate_short", Step(node, joined, "product", subresult=detail))
    scratch = SolveResult()
    value = route(joined, SolveContext(result=scratch, variables=list(ctx.variables), depth=1))
    for step in scratch:  # separate rows: ``add`` would merge them into the one above
        ctx.result.add_group("calculate_short", step)
    return value


def _negative_power_rows(node: CoreNode, ctx: SolveContext) -> CoreNode | None:
    """``a^-n`` for integers: write it with a positive exponent, then evaluate the power.

    The two rows the card shows for ``2^-2``.
    """
    if node.type is not T.POWER or len(node.children) != 2:
        return None
    base, exponent = node.children
    if not (
        base.type is T.CONSTANT
        and (base.value or "").isdigit()
        and int(base.value or 0) >= 2
        and exponent.type is T.NEGATIVE
        and exponent.children[0].type is T.CONSTANT
        and (exponent.children[0].value or "").isdigit()
        and int(exponent.children[0].value or 0) >= 1
    ):
        return None
    n = exponent.children[0]
    letters = CoreNode.variable("a"), CoreNode.variable("n")
    rule = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.POWER, letters[0], CoreNode.node(T.NEGATIVE, letters[1])),
        CoreNode.node(T.FRACTION, CoreNode.constant("1"), CoreNode.node(T.POWER, *letters)),
    )
    flipped = CoreNode.node(T.FRACTION, CoreNode.constant("1"), CoreNode.node(T.POWER, base, n))
    ctx.result.add_group("pow_express_pos_exp", Step(node, flipped, "pow_flip_msg", [rule]))
    value = Fraction(1, int(base.value or 1) ** int(n.value or 1))
    answer = CoreNode.node(
        T.FRACTION, CoreNode.constant("1"), CoreNode.constant(str(value.denominator))
    )
    from .quadratic_cards import _detail

    ctx.result.add_group(
        "evaluate",
        Step(
            flipped,
            answer,
            "pow",
            subresult=_detail(
                CoreNode.node(T.POWER, base, n), CoreNode.constant(str(value.denominator))
            ),
        ),
    )
    return answer


@method_provider(T.MULTIPLY)
def power_product_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """``a^m * a^n``: add the exponents, then sum them; The app offers the same rows twice."""
    _ = variables
    if len(node.children) != 2:
        return []
    first, second = node.children
    if not all(
        child.type is T.POWER
        and child.children[0].type is T.CONSTANT
        and child.children[1].type is T.CONSTANT
        and (child.children[1].value or "").isdigit()
        for child in (first, second)
    ) or not first.children[0].structural_eq(second.children[0]):
        return []
    base = first.children[0]
    m, n = int(first.children[1].value or 0), int(second.children[1].value or 0)
    joined = CoreNode.node(
        T.POWER,
        base,
        CoreNode.node(T.ADD, first.children[1], second.children[1]),
    )
    final = CoreNode.node(T.POWER, base, CoreNode.constant(str(m + n)))

    def card() -> SolveResult:
        result = SolveResult()
        result.add_group(
            ["product", "series_calc_short"][0], Step(node, joined, "pow_same_base_mul")
        )
        result.add_group("calculate_short", Step(joined, final, "add"))
        result.set_solution(final)
        return result

    return [card(), card()]


def _with_child(node: CoreNode, index: int, child: CoreNode) -> CoreNode:
    """Copy ``node`` with one operand replaced."""
    children = list(node.children)
    children[index] = child
    return CoreNode.node(node.type, *children)


def _integer_fraction(node: CoreNode) -> tuple[int, int] | None:
    """``(numerator, denominator)`` of a fraction that reduces to a whole number.

    Accepts both spellings: a fraction node from the editor and a ``/`` division.
    """
    if node.type not in (T.FRACTION, T.DIVIDE) or len(node.children) != 2:
        return None
    numbers: list[int] = []
    for child in node.children:
        text = (child.value or "") if child.type is T.CONSTANT else ""
        if not text.isdigit():
            return None
        numbers.append(int(text))
    numerator, denominator = numbers
    if denominator <= 1 or numerator % denominator != 0:
        return None
    return numerator, denominator


def _whole_fraction_rows(node: CoreNode, ctx: SolveContext) -> CoreNode | None:
    """``100/4 + 6``: reduce the fraction in place, as the app shows it.

    The reduction is one row over the whole expression (``frac_reduce_frac_num``)
    whose detail screen divides both parts and then reads ``25/1`` as ``25``.
    """
    if node.type not in (T.ADD, T.SUBTRACT) or len(node.children) != 2:
        return None
    for index, child in enumerate(node.children):
        pair = _integer_fraction(child)
        if pair is None or node.children[1 - index].type is not T.CONSTANT:
            continue
        numerator, denominator = pair
        from .fractions import integer_reduction_rows

        detail = integer_reduction_rows(numerator, denominator)
        if detail is None:
            return None
        fraction = CoreNode.node(
            T.FRACTION, CoreNode.constant(str(numerator)), CoreNode.constant(str(denominator))
        )
        whole = CoreNode.constant(str(numerator // denominator))
        ctx.result.add_group(
            "frac_reduce_frac",
            Step(
                _with_child(node, index, fraction),
                _with_child(node, index, whole),
                _KEY_FRAC_REDUCE,
                [CoreNode.constant(str(denominator))],
                subresult=detail,
            ),
        )
        return route(_with_child(node, index, whole), ctx)
    return None


def _decimal_power_card(
    node: CoreNode, folded: list[CoreNode], ctx: SolveContext
) -> CoreNode | None:
    """``5^0.5``: write the decimal exponent as a fraction, then apply the power rule.

    row ``dec_to_frac`` (``5^0.5`` -> ``5^(1/2)``),
    then the rule ``a^(m/n) = ⁿ√(aᵐ)`` with the answer ``√5 ≈ 2.23607``. Only
    a decimal exponent outside the exact rational powers is rewritten: ``4^0.5``
    stays the plain ``2``, and integer powers are untouched.
    """
    if ctx.depth != 0 or node.type is not T.POWER or len(folded) != 2:
        return None
    base, exponent = folded
    text = (exponent.value or "") if exponent.type is T.CONSTANT else ""
    if "." not in text:
        return None
    try:
        power = Fraction(text)
    except ValueError:
        return None
    if power.denominator == 1 or abs(power.numerator) > _MAX_POWER:
        return None
    if base.type is not T.CONSTANT:
        return None
    value = _value_of(base)
    if value <= 0 or _rational_power(value, power) is not None:
        return None
    try:
        approximate = f"{float(value) ** float(power):.5f}".rstrip("0").rstrip(".")
    except (OverflowError, ValueError):
        return None

    def number(integer: int) -> CoreNode:
        return CoreNode.constant(str(integer))

    fraction = CoreNode.node(T.FRACTION, number(power.numerator), number(power.denominator))
    rewritten = CoreNode.node(T.POWER, base, fraction)
    ctx.result.add_group("convert_expression", Step(node, rewritten, "dec_to_frac"))
    inside = base if power.numerator == 1 else CoreNode.node(T.POWER, base, number(power.numerator))
    root = (
        CoreNode.node(T.ROOT2, inside)
        if power.denominator == 2
        else CoreNode.node(T.ROOT, number(power.denominator), inside)
    )
    answer = CoreNode.node(
        T.ALTERNATIVE_FORM,
        root,
        CoreNode.node(T.APPROXIMATE_SIGN, CoreNode.constant(approximate)),
    )
    a, m, n = CoreNode.variable("a"), CoreNode.variable("m"), CoreNode.variable("n")
    law = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.POWER, a, CoreNode.node(T.FRACTION, m, n)),
        CoreNode.node(T.ROOT, n, CoreNode.node(T.POWER, a, m)),
    )
    ctx.result.add_group("trans_msg", Step(rewritten, answer, "using_trans", [law]))
    return answer


def _unary_minus_rows(node: CoreNode, ctx: SolveContext) -> CoreNode | None:
    """``-2 + 5``: extract the minus, then subtract, as the app shows it."""
    if node.type is not T.ADD or len(node.children) != 2:
        return None
    first, second = node.children
    if first.type is not T.NEGATIVE or len(first.children) != 1:
        return None
    magnitude, positive = first.children[0], second
    if magnitude.type is not T.CONSTANT or positive.type is not T.CONSTANT:
        return None
    try:
        small, big = _value_of(magnitude), _value_of(positive)
    except SolveError:
        return None
    if small.denominator != 1 or big.denominator != 1 or big <= small:
        return None  # only the verified order: a negative term smaller than the positive one
    opened = CoreNode.node(
        T.POSITIVE, CoreNode.node(T.BRACKET, CoreNode.node(T.SUBTRACT, positive, magnitude))
    )
    total = CoreNode.constant(format_number(big - small))
    ctx.result.add_group("extract_neg", Step(node, opened, "add_sign_sub"))
    ctx.result.add_group("calculate_short", Step(opened, total, "sub"))
    return total


def _minus_negative_rows(node: CoreNode, ctx: SolveContext) -> CoreNode | None:
    """``a - (-b)`` for integers: open the bracket, then one summing row with a detail screen.

    The two rows the card shows for ``-3-(-5)``.
    """
    if node.type is not T.SUBTRACT or len(node.children) != 2:
        return None
    left, right = node.children
    inner = right.children[0] if right.type is T.BRACKET else None
    if inner is None or inner.type is not T.NEGATIVE or inner.children[0].type is not T.CONSTANT:
        return None
    try:
        a, b = _value_of(route(left, SolveContext(SolveResult()))), _value_of(inner.children[0])
    except SolveError:
        return None
    if a.denominator != 1 or b.denominator != 1:
        return None
    opened = CoreNode.node(T.ADD, left, inner.children[0])
    ctx.result.add_group(
        "remove_bracket_short",
        Step(node, opened, "neg_neg_arg", [CoreNode.variable("-")]),
    )
    total = CoreNode.constant(format_number(a + b))
    if not (a < 0 < b):
        # `7-(-3)`: the bracket is opened into `7+3` and one sum row follows.
        key = _apply(T.ADD, [a, b])[1]
        ctx.result.add_group(
            "calculate_short", Step(opened, total, key, _step_args(key, opened, total))
        )
        return total
    reordered = CoreNode.node(
        T.SUBTRACT, CoreNode.constant(format_number(b)), CoreNode.constant(format_number(-a))
    )
    inner_rows = SolveResult()
    inner_rows.add_group("add_sign_sub", Step(opened, reordered, "add_sign_sub"))
    inner_rows.add_group("calculate_short", Step(reordered, total, "sub"))
    inner_rows.set_solution(total)
    ctx.result.add_group("calculate_short", Step(opened, total, "calc_sum", subresult=inner_rows))
    return total


def _flatten_fraction_sum(node: CoreNode) -> CoreNode:
    """``a/b + c/d + e/f`` is one addition, not two nested ones."""
    if node.type is not T.ADD:
        return node
    leaves: list[CoreNode] = []

    def collect(part: CoreNode) -> None:
        if part.type is T.ADD:
            for child in part.children:
                collect(child)
        else:
            leaves.append(part)

    collect(node)
    if (
        len(leaves) > 2
        and sum(leaf.type is T.FRACTION for leaf in leaves) >= 2
        and all(leaf.type in (T.FRACTION, T.CONSTANT) for leaf in leaves)
    ):
        return CoreNode(type=T.ADD, children=leaves)
    return node


def _step_args(key: str, node: CoreNode, result: CoreNode) -> list[CoreNode]:
    """Аргументы ``ARG1…`` для вырожденных случаев.

    Шаблоны этих ключей требуют аргумент. Без него пользователь читал
    служебную метку: «Любое выражение, разделенное на ARG1, равно самому
    себе».
    """
    if key == _KEY_DIV_ONE:
        # «…разделенное на ARG1…» — делитель (последний операнд деления).
        return [node.children[-1]]
    if key == _KEY_SUB_SELF:
        # «Сумма двух противоположных чисел равна ARG1» — результат (ноль).
        return [result]
    if key in (_KEY_ADD_ZERO, _KEY_MUL_ZERO):
        # «При добавлении или вычитании ARG1…», «…умноженное на ARG1…» — ноль.
        return [CoreNode.constant("0")]
    if key == _KEY_MUL_NEG_ONE:
        return [CoreNode.constant("-1")]
    if key == _KEY_MUL_ONE:
        return [CoreNode.constant("1")]
    return []


def _is_settled(node: CoreNode) -> bool:
    """Свёрнулось ли поддерево до значения.

    Скобки не мешают значению, но остаются узлом: ``2*(3+4)`` -- это
    умножение на результат скобок, а не на узел ``BRACKET``.
    """
    if node.type is T.CONSTANT:
        return True
    return (
        node.type is T.BRACKET and len(node.children) == 1 and node.children[0].type is T.CONSTANT
    )


def _value_of(node: CoreNode) -> Fraction:
    """Значение свёрнутого узла, со снятием скобок."""
    if node.type is T.BRACKET and len(node.children) == 1:
        return as_fraction(node.children[0])
    return as_fraction(node)


def _check_leaf(node: CoreNode) -> None:
    """Проверить, что лист действительно число, а не переменная."""
    if node.type is T.VARIABLE:
        raise SolveError("переменные в арифметике не вычисляются: нужен модуль уравнений")
    if not node.value:
        raise SolveError("константа без значения")


def _rational_power(base: Fraction, exponent: Fraction) -> Fraction | None:
    """``base ** exponent`` when it is a rational number, else ``None``."""
    import sympy

    value = sympy.Rational(base.numerator, base.denominator) ** sympy.Rational(
        exponent.numerator, exponent.denominator
    )
    return Fraction(int(value.p), int(value.q)) if value.is_Rational else None


def _apply(op: CoreNodeType, values: list[Fraction]) -> tuple[Fraction, str]:
    """Вычислить операцию и выбрать ключ пояснения."""
    if op in (T.ADD, T.SUBTRACT, T.POSITIVE):
        total = values[0]
        for v in values[1:]:
            total = total + v if op is T.ADD else total - v
        if op is T.POSITIVE:
            return values[0], _KEY_ADD_ZERO
        if op is T.SUBTRACT:
            if total == 0 and len(values) == 2 and values[0] == values[1]:
                return total, _KEY_SUB_SELF
            if 0 in values:
                return total, _KEY_ADD_ZERO
            if total < 0 and all(v > 0 for v in values):
                # 4-6 and 1-3 are "calculate the difference", not "subtract".
                return total, _KEY_CALC_DIFF
            return total, _EXPLANATION_KEY[op]
        if total == 0 and len(values) == 2 and values[0] == -values[1]:
            # -1+1 is "two opposites add up to zero", not "add the numbers".
            return total, _KEY_SUB_SELF
        if 0 in values:
            return total, _KEY_ADD_ZERO
        if any(v < 0 for v in values) and any(v > 0 for v in values):
            # -5+3 is "calculate the sum" of numbers with different signs.
            return total, _KEY_CALC_SUM
        return total, _EXPLANATION_KEY[op]

    if op in (T.MULTIPLY, T.MULTIPLY_IMPLICIT):
        product = Fraction(1)
        for v in values:
            product *= v
        if 0 in values:
            return product, _KEY_MUL_ZERO
        if -1 in values:
            return product, _KEY_MUL_NEG_ONE
        others = [v for v in values if v != 1]
        if not others or len(others) == 1:
            # The only real factor is the product itself: "multiplied by 1 does not change".
            return product, _KEY_MUL_ONE
        if product == 1:
            return product, KEY_CALCULATE
        return product, _EXPLANATION_KEY[op]

    if op is T.NEGATIVE:
        return -values[0], _EXPLANATION_KEY[op]

    if op is T.DIVIDE:
        result = values[0]
        for v in values[1:]:
            if v == 0:
                raise UndefinedError(
                    "деление на ноль", _KEY_DIV_ZERO, explanation_args=[CoreNode.constant("0")]
                )
            result /= v
            if result == values[0] and v == 1:
                return result, _KEY_DIV_ONE
        return result, _EXPLANATION_KEY[op]

    if op is T.POWER:
        base, exponent = values[0], values[1]
        if exponent.denominator != 1 and base > 0 and abs(exponent.numerator) <= _MAX_POWER:
            exact = _rational_power(base, exponent)
            if exact is not None:  # 9^(1/2) = 3, 8^(2/3) = 4
                return exact, _EXPLANATION_KEY[op]
        if (
            exponent.denominator != 1
            and base < 0
            and exponent.denominator % 2 == 1
            and abs(exponent.numerator) <= _MAX_POWER
        ):
            # an odd root of a negative number is real: (-8)^(1/3) = -2, (-8)^(2/3) = 4
            exact = _rational_power(-base, exponent)
            if exact is not None:
                return (-exact if exponent.numerator % 2 else exact), _EXPLANATION_KEY[op]
        if exponent.denominator != 1 and base < 0 and exponent.denominator % 2 == 0:
            raise SolveError(
                "чётный корень из отрицательного числа не имеет вещественного значения"
            )
        if exponent.denominator != 1 or abs(exponent.numerator) > _MAX_POWER:
            raise SolveError("показатель степени вне поддерживаемого диапазона")
        if base == 0 and exponent.numerator < 0:
            raise UndefinedError(
                "деление на ноль",
                _KEY_DIV_ZERO,
                explanation_args=[CoreNode.constant("0")],
            )
        if base < 0 and exponent.numerator % 2 != 0:
            return Fraction(-((-base) ** exponent.numerator)), _EXPLANATION_KEY[op]
        return Fraction(base) ** exponent.numerator, _EXPLANATION_KEY[op]

    raise SolveError(f"операция {op} не реализована в арифметике")
