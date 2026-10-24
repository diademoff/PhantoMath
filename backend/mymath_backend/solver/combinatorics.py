"""Комбинаторика: факториал, биномиальный коэффициент, перестановки, размещения.

Модуль зарегистрирован на ``FACTORIAL``, ``CHOOSE``,
``CHOOSE_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT``,
``PARTIAL_PERMUTATION_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT`` и ``VARIATION``.
Аргументы должны быть целыми: ``n`` -- неотрицательное, ``k`` -- ``0 ≤ k ≤ n``.

Шаги повторяют карточки: разложение по формуле, сокращение
факториала, произведение и сокращение дроби.
"""

from __future__ import annotations

from math import comb, factorial, perm

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .arithmetic import as_fraction
from .base import (
    SolveContext,
    SolveError,
    SolveResult,
    Step,
    UndefinedError,
    route,
    solver_for,
)

_CHOOSES = (T.CHOOSE, T.CHOOSE_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT)
_ARRANGEMENTS = (T.PARTIAL_PERMUTATION_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT, T.VARIATION)

_MAX_FACTORIAL = 1000
_EXPANDED_FACTORIAL = 20  # longer products are not written out


def _integer(
    node: CoreNode, ctx: SolveContext, message: str, *, undefined_key: str | None = None
) -> int:
    """Целое неотрицательное из аргумента.

    ``undefined_key`` задаёт ключ пояснения для «Не определено»: факториал и
    перестановка вне области определения — это ответ «Не определено», а не ошибка.
    """
    value = as_fraction(route(node, ctx))
    if value.denominator != 1 or value.numerator < 0:
        if undefined_key is not None:
            raise UndefinedError(message, undefined_key, explanation_args=[CoreNode.constant("0")])
        raise SolveError(message)
    return value.numerator


def _num(value: int) -> CoreNode:
    return CoreNode.constant(str(value))


def _product_of(factors: list[int]) -> CoreNode:
    if len(factors) == 1:
        return _num(factors[0])
    return CoreNode.node(T.MULTIPLY, *[_num(factor) for factor in factors])


def _factorial(value: int | CoreNode) -> CoreNode:
    child = _num(value) if isinstance(value, int) else value
    return CoreNode.node(T.FACTORIAL, child)


def _factorial_law() -> CoreNode:
    n, dots = CoreNode.variable("n"), CoreNode.variable("…")
    return CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.FACTORIAL, n),
        CoreNode.node(
            T.MULTIPLY,
            n,
            CoreNode.node(T.BRACKET, CoreNode.node(T.SUBTRACT, n, _num(1))),
            dots,
            _num(2),
            _num(1),
        ),
    )


def _clever_product_detail(factors: list[int], value: int) -> SolveResult:
    """The product page the card shows for a longer factorial: drop 1, fold round pairs."""
    detail = SolveResult()
    current = list(factors)
    if 1 in current:
        before = _product_of(current)
        current.remove(1)
        detail.add_group("multiply", Step(before, _product_of(current), "mul_with_one", [_num(1)]))
    while len(current) > 1:
        pair: tuple[int, int] | None = None
        for first in range(len(current)):
            for second in range(first + 1, len(current)):
                if (current[first] * current[second]) % 10 == 0:
                    pair = (first, second)
                    break
            if pair is not None:
                break
        if pair is not None:
            first, second = pair
            product = current[first] * current[second]
            rest = [item for index, item in enumerate(current) if index not in pair]
            before = _product_of(current)
            current = [product, *rest]
            detail.add_group(
                "multiply",
                Step(
                    before,
                    _product_of(current),
                    "mul_real_clever" if len(current) > 1 else "mul",
                    [_num(product)] if len(current) > 1 else [],
                ),
            )
        else:
            product = current[0] * current[1]
            before = _product_of(current)
            current = [product, *current[2:]]
            key = "mul"
            detail.add_group(
                "multiply",
                Step(
                    before,
                    _product_of(current),
                    key,
                    [_num(product)] if key == "mul_real_clever" else [],
                ),
            )
    detail.set_solution(_num(value))
    return detail


def _plain_product_detail(factors: list[int], value: int) -> SolveResult:
    """Left-to-right ``mul`` rows (the numerator product of a binomial coefficient)."""
    detail = SolveResult()
    current = list(factors)
    while len(current) > 1:
        product = current[0] * current[1]
        before = _product_of(current)
        current = [product, *current[2:]]
        detail.add_group("multiply", Step(before, _product_of(current), "mul"))
    detail.set_solution(_num(value))
    return detail


def _factorial_detail(value: int, result: int) -> SolveResult:
    """One factorial evaluated on its own page: the formula, then the product."""
    detail = SolveResult()
    factors = list(range(1, value + 1))
    detail.add_group(
        "factorial_calculate",
        Step(_factorial(value), _product_of(factors), "factorial_formula", [_factorial_law()]),
    )
    inner: SolveResult | None
    if value <= 2:
        inner = SolveResult()
        inner.add_group(
            "multiply", Step(_product_of(factors), _num(result), "mul_with_one", [_num(1)])
        )
        inner.set_solution(_num(result))
    elif value >= 4:
        inner = _clever_product_detail(factors, result)
    else:
        inner = None
    detail.add_group(
        "calculate_short",
        Step(_product_of(factors), _num(result), "product", subresult=inner),
    )
    detail.set_solution(_num(result))
    return detail


def _factorial_rows(arguments: int, result: int, ctx: SolveContext) -> CoreNode:
    """``n!``: the formula row and the product row (the two cards)."""
    factors = list(range(1, arguments + 1))
    product = _product_of(factors)
    ctx.result.add_group(
        "factorial_calculate",
        Step(
            CoreNode.node(T.FACTORIAL, _num(arguments)),
            product,
            "factorial_formula",
            [_factorial_law()],
        ),
    )
    inner: SolveResult | None
    if arguments <= 2:
        inner = SolveResult()
        inner.add_group("multiply", Step(product, _num(result), "mul_with_one", [_num(1)]))
        inner.set_solution(_num(result))
    elif arguments >= 4:
        inner = _clever_product_detail(factors, result)
    else:
        inner = None
    ctx.result.add_group("calculate_short", Step(product, _num(result), "product", subresult=inner))
    return _num(result)


@solver_for(T.FACTORIAL)
def solve_factorial(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить факториал целого неотрицательного числа."""
    argument = _integer(
        node.children[0],
        ctx,
        "факториал определён только для целых неотрицательных чисел",
        undefined_key="factorial_non_integer",
    )
    ctx.require(argument <= _MAX_FACTORIAL, "факториал слишком большой")
    result = CoreNode.constant(str(factorial(argument)))
    if argument == 0:
        law = CoreNode.node(
            T.EQUALS,
            CoreNode.node(T.FACTORIAL, _num(0)),
            _num(1),
        )
        ctx.result.add_group("calculate_short", Step(node, result, "by_definition", [law]))
        return result
    if 2 <= argument <= _EXPANDED_FACTORIAL:
        return _factorial_rows(argument, factorial(argument), ctx)
    ctx.result.add(Step(left=node, right=result, key="factorial_calculate"))
    return result


def _choose_law(kind: T) -> CoreNode:
    n, k = CoreNode.variable("n"), CoreNode.variable("k")
    if kind is T.CHOOSE:
        c = CoreNode.node(T.CHOOSE, n, k)
    else:
        c = CoreNode.node(T.CHOOSE_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT, n, k)
    formula = CoreNode.node(
        T.EQUALS,
        c,
        CoreNode.node(
            T.FRACTION,
            CoreNode.node(T.FACTORIAL, n),
            CoreNode.node(
                T.MULTIPLY,
                CoreNode.node(T.FACTORIAL, k),
                CoreNode.node(
                    T.FACTORIAL,
                    CoreNode.node(T.BRACKET, CoreNode.node(T.SUBTRACT, n, k)),
                ),
            ),
        ),
    )
    return formula


def _choose_def_same() -> CoreNode:
    n = CoreNode.variable("n")
    return CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.CHOOSE, n, n),
        _num(1),
    )


@solver_for(*_CHOOSES)
def solve_choose(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить биномиальный коэффициент ``C(n, k)``."""
    ctx.require(len(node.children) == 2, "биномиальный коэффициент задаётся двумя числами")
    n = _integer(node.children[0], ctx, "C(n, k) определён только для целых неотрицательных")
    k = _integer(node.children[1], ctx, "C(n, k) определён только для целых неотрицательных")
    ctx.require(k <= n, "для C(n, k) нужно k ≤ n")
    result_value = comb(n, k)
    result = _num(result_value)
    if k in (0, n):
        law = CoreNode.node(
            T.EQUALS,
            CoreNode.node(node.type, CoreNode.variable("n"), CoreNode.variable("k")),
            _num(1),
        )
        ctx.result.add_group("calculate_short", Step(node, result, "choose_def_same", [law]))
        return result
    if k == 1:
        ctx.result.add(Step(left=node, right=result, key="choose_calculate"))
        return result
    _choose_rows(node, n, k, result_value, ctx)
    return result


def _choose_rows(node: CoreNode, n: int, k: int, result: int, ctx: SolveContext) -> None:
    eq = CoreNode.node
    rest = n - k
    formula = _choose_law(node.type if node.type is T.CHOOSE else T.CHOOSE)
    if node.type is T.CHOOSE_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT:
        formula = _choose_law(T.CHOOSE_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT)
    start = eq(
        T.FRACTION,
        _factorial(n),
        eq(
            T.MULTIPLY,
            _factorial(k),
            eq(T.FACTORIAL, eq(T.BRACKET, eq(T.SUBTRACT, _num(n), _num(k)))),
        ),
    )
    ctx.result.add_group("expand_msg", Step(node, start, "choose_expand", [formula]))
    factors = list(range(rest + 1, n + 1))
    numerator = eq(T.MULTIPLY, _factorial(rest), *[_num(factor) for factor in factors])
    expanded = eq(
        T.FRACTION,
        numerator,
        eq(
            T.MULTIPLY,
            _factorial(k),
            eq(T.FACTORIAL, eq(T.BRACKET, eq(T.SUBTRACT, _num(n), _num(k)))),
        ),
    )
    law = eq(
        T.EQUALS,
        _factorial(CoreNode.variable("n")),
        eq(
            T.MULTIPLY,
            CoreNode.variable("n"),
            _factorial(eq(T.BRACKET, eq(T.SUBTRACT, CoreNode.variable("n"), _num(1)))),
        ),
    )
    denominator_fact = eq(T.FACTORIAL, _num(rest))
    simplified = eq(T.FRACTION, numerator, eq(T.MULTIPLY, _factorial(k), denominator_fact))
    ctx.result.add_group(
        ["expand_key", "calculate_short"],
        Step(start, expanded, "using_expand", [law]),
        Step(expanded, simplified, "sub"),
    )
    cancelled = eq(T.FRACTION, _product_of(factors), _factorial(k))
    ctx.result.add_group(
        "frac_reduce_frac",
        Step(simplified, cancelled, "frac_reduce_frac_alg", [denominator_fact]),
    )
    product_value = 1
    for factor in factors:
        product_value *= factor
    current = cancelled
    if len(factors) > 1:
        if len(factors) == 2:
            current = eq(T.FRACTION, _num(product_value), _factorial(k))
            ctx.result.add_group("multiply", Step(cancelled, current, "mul"))
        else:
            detail = _plain_product_detail(factors, product_value)
            current = eq(T.FRACTION, _num(product_value), _factorial(k))
            ctx.result.add_group(
                "calculate_short",
                Step(cancelled, current, "product", subresult=detail),
            )
    factorial_value = factorial(k)
    inner = _factorial_detail(k, factorial_value)
    ctx.result.add_group(
        "calculate_short",
        Step(current, _num(result), "factorial_calculate", subresult=inner),
    )
    denominator = eq(
        T.FRACTION,
        eq(T.DIVIDE, _num(product_value), _num(factorial_value)),
        eq(T.DIVIDE, _num(factorial_value), _num(factorial_value)),
    )
    detail = SolveResult()
    detail.add_group(
        "frac_reduce_frac",
        Step(_num(result), denominator, "frac_div_num", [_num(factorial_value)]),
    )
    after_top = eq(
        T.FRACTION,
        _num(product_value // factorial_value),
        eq(T.DIVIDE, _num(factorial_value), _num(factorial_value)),
    )
    after_bottom = _num(result)
    detail.add_group(
        "divide",
        Step(denominator, after_top, "div"),
        Step(after_top, after_bottom, "div"),
    )
    detail.add_group("divide", Step(after_bottom, _num(result), "div_with_one", [_num(1)]))
    detail.set_solution(_num(result))
    ctx.result.add_group(
        "frac_reduce_frac",
        Step(
            _num(result),
            _num(result),
            "frac_reduce_frac_num",
            [_num(factorial_value)],
            subresult=detail,
        ),
    )


def _permutation_rows(node: CoreNode, n: int, k: int, result: CoreNode, ctx: SolveContext) -> None:
    """``nPk = n!/(n-k)!``, written out and reduced: the rows the app shows for 5P2."""
    eq = CoreNode.node

    def num(value: int) -> CoreNode:
        return _num(value)

    if k == n:
        law = eq(
            T.EQUALS,
            eq(
                T.PARTIAL_PERMUTATION_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT,
                CoreNode.variable("n"),
                CoreNode.variable("n"),
            ),
            _factorial(CoreNode.variable("n")),
        )
        ctx.result.add_group(
            "calculate_short", Step(node, _factorial(n), "permutation_def_same", [law])
        )
        inner = _factorial_detail(n, factorial(n))
        ctx.result.add_group(
            "calculate_short",
            Step(_factorial(n), result, "factorial_calculate", subresult=inner),
        )
        return

    letters = CoreNode.variable("n"), CoreNode.variable("r")
    formula = eq(
        T.EQUALS,
        eq(T.PARTIAL_PERMUTATION_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT, *letters),
        eq(
            T.FRACTION,
            eq(T.FACTORIAL, letters[0]),
            eq(T.FACTORIAL, eq(T.BRACKET, eq(T.SUBTRACT, *letters))),
        ),
    )
    rest = eq(T.FACTORIAL, num(n - k))
    denominator = eq(T.FACTORIAL, eq(T.BRACKET, eq(T.SUBTRACT, num(n), num(k))))
    start = eq(T.FRACTION, eq(T.FACTORIAL, num(n)), denominator)
    ctx.result.add_group("expand_msg", Step(node, start, "permutation_expand", [formula]))
    product = eq(T.MULTIPLY, *[num(n - i) for i in range(k)], rest)
    law = eq(
        T.EQUALS,
        eq(T.FACTORIAL, letters[0]),
        eq(
            T.MULTIPLY,
            letters[0],
            eq(T.FACTORIAL, eq(T.BRACKET, eq(T.SUBTRACT, letters[0], num(1)))),
        ),
    )
    written = eq(T.FRACTION, product, denominator)
    simplified = eq(T.FRACTION, product, rest)
    ctx.result.add_group(
        ["expand_key", "calculate_short"],
        Step(start, written, "using_expand", [law]),
        Step(written, simplified, "sub"),
    )
    reduced = eq(T.MULTIPLY, *[num(n - i) for i in range(k)])
    ctx.result.add_group(
        "frac_reduce_frac", Step(simplified, reduced, "frac_reduce_frac_alg", [rest])
    )
    ctx.result.add_group("calculate_short", Step(reduced, result, "mul"))


@solver_for(*_ARRANGEMENTS)
def solve_arrangement(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить число перестановок/размещений ``P(n, k)``."""
    ctx.require(len(node.children) == 2, "перестановка задаётся двумя числами")
    n = _integer(
        node.children[0],
        ctx,
        "перестановка определена только для целых неотрицательных",
        undefined_key="permutation_coef_non_integer",
    )
    k = _integer(
        node.children[1],
        ctx,
        "перестановка определена только для целых неотрицательных",
        undefined_key="permutation_coef_non_integer",
    )
    ctx.require(k <= n, "для перестановки нужно k ≤ n")
    key = "variation_not_allowed_calculate" if node.type is T.VARIATION else "permutation_calculate"
    result = CoreNode.constant(str(perm(n, k)))
    if node.type is not T.VARIATION and k >= 1 and (k == n or (k >= 2 and n - k >= 2)):
        _permutation_rows(node, n, k, result, ctx)
        return result
    ctx.result.add(Step(left=node, right=result, key=key))
    return result


__all__ = [
    "solve_arrangement",
    "solve_choose",
    "solve_factorial",
]
