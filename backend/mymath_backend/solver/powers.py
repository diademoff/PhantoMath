"""Степени, корни и логарифмы: точное числовое упрощение.

Модуль зарегистрирован на узлы ``ROOT2``, ``ROOT``, ``LOG10``, ``LN``,
``LOG`` и ``EXP``. Он упрощает их, когда результат точен:

* ``√16 = 4``, ``∛27 = 3``, ``√(4/9) = 2/3`` -- корень из полного
  квадрата/куба (в том числе из рациональной дроби);
* ``log₁₀(1000) = 3``, ``log₂(8) = 3``, ``ln(e) = 1``, ``ln(1) = 0``;
* ``e⁰ = 1``.

Если точного значения нет (``√2``, ``log₁₀(5)``), узел возвращается без
изменений: символическое упрощение вида ``√8 = 2√2`` и действия с
иррациональностями — отдельная задача. Числа при этом остаются точными:
``√16 + 1 = 5``.

Ключи шагов: ``root_simplify`` для корней и ``calculate_short`` для
логарифмов и экспоненты.
"""

from __future__ import annotations

from fractions import Fraction
from math import isqrt, log

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .arithmetic import format_number
from .base import (
    SolveContext,
    SolveError,
    SolveResult,
    Step,
    UndefinedError,
    fold_semantically,
    solver_for,
)
from .methods import method_provider

_KEY_ROOT = "root_simplify"
_KEY_CALCULATE = "calculate_short"


def _integer(node: CoreNode) -> int | None:
    """Целое значение константы или ``None``."""
    if node.type is not T.CONSTANT or node.value is None:
        return None
    text = node.value.strip()
    try:
        value = int(text)
    except ValueError:
        return None
    return value if str(value) == text else None


def _is_negative_integer(node: CoreNode) -> bool:
    """``-4`` as a constant or as a minus in front of one."""
    if node.type is T.NEGATIVE and len(node.children) == 1:
        inner = _integer(node.children[0])
        return inner is not None and inner > 0
    value = _integer(node)
    return value is not None and value < 0


def _perfect_root(value: int, degree: int) -> int | None:
    """Целый корень ``degree``-й степени или ``None``."""
    if value < 0 and degree % 2 == 0:
        return None
    magnitude = abs(value)
    estimate = isqrt(magnitude) if degree == 2 else round(magnitude ** (1 / degree))
    for candidate in range(max(estimate - 2, 0), estimate + 3):
        if candidate**degree == magnitude:
            return -candidate if value < 0 else candidate
    return None


def _exact_log(value: int, base: int) -> int | None:
    """Показатель ``k``, если ``value == base^k``."""
    if value <= 0 or base <= 1:
        return None
    power, exponent = 1, 0
    while power < value:
        power *= base
        exponent += 1
        if exponent > 64:
            return None
    return exponent if power == value else None


def _rational(node: CoreNode) -> Fraction | None:
    """Рациональное значение константы или ``None``."""
    if node.type is not T.CONSTANT or node.value is None:
        return None
    try:
        return Fraction(node.value.strip())
    except (ValueError, ZeroDivisionError):
        return None


def _numeric_value(node: CoreNode) -> Fraction | None:
    """Точное рациональное значение числового узла (``1/9``, ``0,01``, ``-2``)."""
    if node.type is T.CONSTANT:
        return _rational(node)
    if node.type in (T.BRACKET, T.POSITIVE) and len(node.children) == 1:
        return _numeric_value(node.children[0])
    if node.type is T.NEGATIVE and len(node.children) == 1:
        inner = _numeric_value(node.children[0])
        return -inner if inner is not None else None
    if node.type is T.FRACTION and len(node.children) == 2:
        top, bottom = _numeric_value(node.children[0]), _numeric_value(node.children[1])
        if top is not None and bottom not in (None, 0):
            return top / bottom
    return None


def _log_exponent(argument: CoreNode, base: int) -> Fraction | None:
    """Показатель ``k``, при котором ``argument == base^k`` (для рациональных чисел).

    ``log₃(1/9) = log₃(3⁻²)``, ``log₉ 3 = log₉ 9^(1/2)``: и целые, и дробные показатели.
    """
    if base <= 1:
        return None
    value = _numeric_value(argument)
    if value is None or value <= 0:
        return None
    for denominator in range(1, 13):
        # base^k = value  ⇔  base^(p/q) = value  ⇔  base^p = value^q
        top = _exact_log(value.numerator**denominator, base)
        bottom = _exact_log(value.denominator**denominator, base)
        if top is not None and bottom is not None:
            return Fraction(top - bottom, denominator)
    return None


def _number_node(value: Fraction) -> CoreNode:
    """Рациональное число как узел: целое — константа, дробь — ``FRACTION``."""
    if value.denominator == 1:
        return CoreNode.constant(str(value.numerator))
    return CoreNode.node(
        T.FRACTION,
        CoreNode.constant(str(value.numerator)),
        CoreNode.constant(str(value.denominator)),
    )


def _exact_root(node: CoreNode, degree: int) -> Fraction | None:
    """Точный корень ``degree``-й степени из рационального числа или ``None``.

    Работает и с дробями: ``√(4/9) = 2/3``, ``√(9/4) = 3/2``. Если корень
    не извлекается точно (``√(1/2)``) или подкоренное не число, возвращает
    ``None`` -- вызывающий оставляет узел.
    """
    value = _rational(node)
    if value is None:
        return None
    numerator = _perfect_root(value.numerator, degree)
    denominator = _perfect_root(value.denominator, degree)
    if numerator is None or denominator in (None, 0):
        return None
    return Fraction(numerator, denominator)


def _root_fraction_rows(
    node: CoreNode, numerator: int, denominator: int, root: Fraction | None, ctx: SolveContext
) -> CoreNode | None:
    """``sqrt(n/d)`` in the order.

    A perfect fraction is split into two roots, both radicands are written as
    powers and reduced; ``1/sqrt(d)`` is rationalised through ``sqrt(d)/sqrt(d)``.
    """
    if numerator <= 0 or denominator <= 0:
        return None
    eq, num = CoreNode.node, CoreNode.constant
    top, bottom = num(str(numerator)), num(str(denominator))
    top_root, bottom_root = _perfect_root(numerator, 2), _perfect_root(denominator, 2)
    if root is not None and top_root is not None and bottom_root is not None:
        upper, lower = eq(T.ROOT2, top), eq(T.ROOT2, bottom)
        current = eq(T.FRACTION, upper, lower)
        ctx.result.add_group("root_radical_msg", Step(node, current, "root_frac_each"))
        for kind, value in (("top", top_root), ("bottom", bottom_root)):
            powered = eq(T.ROOT2, eq(T.POWER, num(str(value)), num("2")))
            if kind == "top":
                upper = powered
            else:
                lower = powered
            nxt = eq(T.FRACTION, upper, lower)
            ctx.result.add_group(
                "write_as_exp_short",
                Step(current, nxt, "pow_to_same_base", [num(str(value))]),
            )
            current = nxt
        reduced_top = eq(T.FRACTION, num(str(top_root)), lower)
        ctx.result.add_group(
            "root_simplify_plural",
            Step(current, reduced_top, "root_reduce", [num("2")]),
        )
        result = num(format_number(root))
        ctx.result.add_group(
            "root_simplify_plural",
            Step(reduced_top, result, "root_reduce", [num("2")]),
        )
        return result
    if numerator != 1:
        # Only the verified family: sqrt(1/d) rationalised by sqrt(d)/sqrt(d).
        return None
    unit, lower = num("1"), eq(T.ROOT2, bottom)
    split = eq(T.FRACTION, eq(T.ROOT2, num("1")), lower)
    simplified = eq(T.FRACTION, unit, lower)
    inner = SolveResult()
    inner.add_group("root_radical_msg", Step(node, split, "root_frac_each"))
    inner.add_group("root", Step(split, simplified, "root_one", [num("1")]))
    inner.set_solution(simplified)
    ctx.result.add_group(
        "root_radical_msg", Step(node, simplified, "root_frac_each", subresult=inner)
    )
    factor = eq(T.FRACTION, lower, eq(T.ROOT2, bottom))
    product = eq(T.MULTIPLY, simplified, factor)
    ctx.result.add_group("expand_msg", Step(simplified, product, "frac_mul_expand_root", [factor]))
    squared = eq(T.MULTIPLY, eq(T.ROOT2, bottom), eq(T.ROOT2, bottom))
    joined = eq(T.FRACTION, eq(T.MULTIPLY, unit, eq(T.ROOT2, bottom)), squared)
    ctx.result.add_group("frac_mul", Step(product, joined, "frac_mul_join"))
    upper = eq(T.ROOT2, bottom)
    cleared = eq(T.FRACTION, upper, squared)
    ctx.result.add_group("product_plural", Step(joined, cleared, "mul_with_one", [num("1")]))
    answer = eq(T.FRACTION, upper, num(str(denominator)))
    ctx.result.add(Step(cleared, answer, "root2_sqr"))
    return answer


@solver_for(T.ROOT2, T.ROOT)
def solve_root(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Упростить корень, если он извлекается нацело.

    Если точного корня нет, узел возвращается, но **с уже свёрнутыми**
    степенью и подкоренным: ``√(2+3)`` даёт шаг ``2+3 = 5`` и ответ ``√5``.
    """
    if node.type is T.ROOT2:
        degree = 2
        if _is_negative_integer(node.children[0]):
            # (sqrt of -4): "not defined on the real
            # numbers" — the whole answer is «Не определено», not the empty set.
            raise UndefinedError(
                "квадратный корень из отрицательного числа",
                "root_sqr_neg",
                header="expr_not_def_in_r",
            )
        radicand = fold_semantically(node.children[0], ctx)
        kept = CoreNode(type=T.ROOT2, children=[radicand])
    else:
        if len(node.children) != 2:
            raise SolveError("корень n-й степени должен иметь степень и подкоренное")
        degree_node = fold_semantically(node.children[0], ctx)
        radicand = fold_semantically(node.children[1], ctx)
        kept = CoreNode(type=T.ROOT, children=[degree_node, radicand])
        degree_value = _integer(degree_node)
        if degree_value is None or degree_value <= 1:
            return kept
        degree = degree_value

    root = _exact_root(radicand, degree)
    integer = _integer(radicand)
    if integer == 0:
        # sqrt(0) = 0, one row ("any root of zero is zero").
        zero = CoreNode.constant("0")
        ctx.result.add_group("root", Step(node, zero, "root_zero", [zero]))
        return zero
    fraction = _rational(radicand)
    if degree == 2 and fraction is not None and fraction.denominator != 1 and fraction > 0:
        rows = _root_fraction_rows(node, fraction.numerator, fraction.denominator, root, ctx)
        if rows is not None:
            return rows
    if (
        degree == 2
        and integer is not None
        and integer > 1
        and (root is None or root.denominator == 1)
    ):
        rows = _square_root_rows(node, integer, ctx)
        if rows is not None:
            return rows
        literal = node.children[0].type is T.CONSTANT if node.children else False
        if root is None and ctx.depth == 0 and literal:
            # (sqrt 3): a bare irrational root keeps
            # its exact form and carries the decimal approximation, like 5^0.5.
            # A folded radicand (sqrt(2+3) -> sqrt 5) keeps today's card.
            return _approximate_root(node, kept, integer, ctx)
        return kept
    if root is None:
        return kept

    result = CoreNode.constant(format_number(root))
    if node.type is T.ROOT and root.denominator == 1 and integer is not None and degree >= 3:
        if ctx.depth == 0 and root >= 2:
            # (cube/fourth root of a power): write the
            # radicand as a power with the root as base, then reduce.
            base = CoreNode.constant(str(int(root)))
            powered = CoreNode.node(
                T.ROOT,
                node.children[0],
                CoreNode.node(T.POWER, base, node.children[0]),
            )
            ctx.result.add_group(
                "write_as_exp_short", Step(node, powered, "pow_to_same_base", [base])
            )
            ctx.result.add_group(
                "root_partial", Step(powered, result, "root_reduce", [node.children[0]])
            )
            return result
        return result
    ctx.result.add(Step(left=node, right=result, key=_KEY_ROOT))
    return result


def _approximate_root(node: CoreNode, kept: CoreNode, integer: int, ctx: SolveContext) -> CoreNode:
    """``√3`` -> ``√3 ≈ 1.73205``, the answer node the app shows for 5^0.5."""
    text = f"{float(sympy.N(sympy.sqrt(integer), 10)):.6g}"
    answer = CoreNode.node(
        T.ALTERNATIVE_FORM,
        kept,
        CoreNode.node(T.APPROXIMATE_SIGN, CoreNode.constant(text)),
    )
    ctx.result.add_group("calculate_short", Step(node, answer, "calculate"))
    ctx.result.header = "calculate_short"
    return answer


def _prime_power_root_rows(node: CoreNode, p: int, e: int, ctx: SolveContext) -> CoreNode:
    """``sqrt(p^e)`` for a prime ``p`` and an odd ``e >= 3``: six rows (sqrt 27).

    Write as a power, split the exponent, expand, drop ``^1``, split the root, reduce.
    """
    eq = CoreNode.node

    def number(value: int) -> CoreNode:
        return CoreNode.constant(str(value))

    base = number(p)
    even = eq(T.POWER, base, number(e - 1))
    powered = eq(T.ROOT2, eq(T.POWER, base, number(e)))
    ctx.result.add_group("write_as_exp_short", Step(node, powered, "pow_to_same_base", [base]))
    split = eq(T.ROOT2, eq(T.POWER, base, eq(T.ADD, number(e - 1), number(1))))
    ctx.result.add_group(
        "root_partial_split_rewrite", Step(powered, split, "root_partial_split_sum")
    )
    letters = CoreNode.variable("a"), CoreNode.variable("m"), CoreNode.variable("n")
    law = eq(
        T.EQUALS,
        eq(T.POWER, letters[0], eq(T.ADD, letters[1], letters[2])),
        eq(T.MULTIPLY, eq(T.POWER, letters[0], letters[1]), eq(T.POWER, letters[0], letters[2])),
    )
    expanded = eq(T.ROOT2, eq(T.MULTIPLY, even, eq(T.POWER, base, number(1))))
    ctx.result.add_group("expand_msg", Step(split, expanded, "using_expand", [law]))
    dropped = eq(T.ROOT2, eq(T.MULTIPLY, even, base))
    ctx.result.add_group(
        ["pow", "series_calc_short"][0], Step(expanded, dropped, "pow_with_one", [number(1)])
    )
    joined = eq(T.MULTIPLY, eq(T.ROOT2, even), eq(T.ROOT2, base))
    ctx.result.add_group("root_radical_msg", Step(dropped, joined, "root_mul_each"))
    result = eq(T.MULTIPLY_IMPLICIT, number(p ** ((e - 1) // 2)), eq(T.ROOT2, base))
    detail = SolveResult()
    square = eq(T.ROOT2, even)
    magnitude = number(p ** ((e - 1) // 2))
    detail.add_group(
        "root_simplify", Step(square, eq(T.ABS, magnitude), "root_reduce", [number(2)])
    )
    detail.add_group("abs", Step(eq(T.ABS, magnitude), magnitude, "abs_real"))
    detail.set_solution(result)
    ctx.result.add_group(
        "root_partial", Step(joined, result, "root_reduce", [number(2)], subresult=detail)
    )
    return result


def _square_root_rows(node: CoreNode, n: int, ctx: SolveContext) -> CoreNode | None:
    """The app rows for a square root of an integer: via a power, or pulling a factor out.

    ``None`` when ``n`` is square-free (nothing to simplify).
    """
    k = max(c for c in range(1, isqrt(n) + 1) if n % (c * c) == 0)
    if k == 1:
        return None
    if ctx.depth > 0:
        # Inside a larger expression the app evaluates the root as one stage whose detail
        # screen holds the rows; sibling roots become pages of the same row.
        inner = SolveResult()
        answer = _square_root_rows(node, n, SolveContext(result=inner))
        if answer is None:
            return None
        inner.set_solution(answer)
        ctx.result.add(
            Step(node, answer, "root_square", subresult=inner),
            [CoreRichText(type="calculate_short")],
        )
        return answer

    def number(value: int) -> CoreNode:
        return CoreNode.constant(str(value))

    def square(value: int) -> CoreNode:
        return CoreNode.node(T.POWER, number(value), number(2))

    def root_of(inner: CoreNode) -> CoreNode:
        return CoreNode.node(T.ROOT2, inner)

    two = number(2)
    rest = n // (k * k)
    if rest == 1:
        result = number(k)
        powered = root_of(square(k))
        ctx.result.add_group(
            "write_as_exp_short", Step(node, powered, "pow_to_same_base", [number(k)])
        )
        ctx.result.add_group("root_partial", Step(powered, result, "root_reduce", [two]))
        return result
    result = CoreNode.node(T.MULTIPLY_IMPLICIT, number(k), root_of(number(rest)))
    exponent = 2 * round(log(k, rest)) + 1 if rest > 1 and k > 1 else 0
    if exponent >= 3 and rest**exponent == n and all(rest % d for d in range(2, isqrt(rest) + 1)):
        return _prime_power_root_rows(node, rest, exponent, ctx)
    factored = root_of(CoreNode.node(T.MULTIPLY, square(k), number(rest)))
    split = CoreNode.node(T.MULTIPLY, root_of(square(k)), root_of(number(rest)))
    detail = SolveResult()
    square_root = root_of(square(k))
    magnitude = number(k)
    detail.add_group(
        "root_simplify", Step(square_root, CoreNode.node(T.ABS, magnitude), "root_reduce", [two])
    )
    detail.add_group("abs", Step(CoreNode.node(T.ABS, magnitude), magnitude, "abs_real"))
    detail.set_solution(result)
    ctx.result.add_group("factorise_call", Step(node, factored, "root_partial_split_arg", [two]))
    ctx.result.add_group("root_radical_msg", Step(factored, split, "root_mul_each"))
    ctx.result.add_group(
        "root_partial", Step(split, result, "root_reduce", [two], subresult=detail)
    )
    return result


@solver_for(T.LOG10, T.LN, T.LOG, T.EXP)
def solve_logarithm(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить логарифм или экспоненту, если значение точное.

    Аргументы сворачиваются заранее; если точного значения нет, узел
    возвращается со свёрнутыми аргументами (``log₁₀(2+3)`` -> ``log₁₀(5)``).
    """
    result: CoreNode | None = None
    if node.type in (T.LN, T.LOG10) and _is_negative_integer(node.children[0]):
        raise UndefinedError(
            "логарифм отрицательного числа",
            "log_neg_arg",
            header="expr_not_def_in_r",
        )
    if node.type is T.LN:
        argument = fold_semantically(node.children[0], ctx)
        node = CoreNode(type=T.LN, children=[argument])
        if argument.type is T.CONSTANT and argument.value == "e":
            result = CoreNode.constant("1")
        elif (
            argument.type is T.POWER
            and argument.children[0].type is T.CONSTANT
            and argument.children[0].value == "e"
        ):
            result = argument.children[1]
        elif _integer(argument) == 1:
            result = CoreNode.constant("0")
    elif node.type is T.EXP:
        argument = fold_semantically(node.children[0], ctx)
        node = CoreNode(type=T.EXP, children=[argument])
        if _integer(argument) == 0:
            result = CoreNode.constant("1")
    elif node.type is T.LOG10:
        argument = fold_semantically(node.children[0], ctx)
        node = CoreNode(type=T.LOG10, children=[argument])
        exponent = _log_exponent(argument, 10)
        if exponent is not None:
            result = _number_node(exponent)
    elif node.type is T.LOG:
        if len(node.children) == 2:
            value_node = fold_semantically(node.children[0], ctx)
            base_node = fold_semantically(node.children[1], ctx)
            node = CoreNode(type=T.LOG, children=[value_node, base_node])
            base = _integer(base_node)
            if base is not None:
                # log₃(1/9): the argument is an exact power of the base, integer or fraction
                exponent = _log_exponent(value_node, base)
                if exponent is not None:
                    result = _number_node(exponent)

    if result is None and node.type in (T.LN, T.LOG10):
        bound = _rational(node.children[0])
        if bound is not None and bound <= 0:
            # no logarithm of zero or of a negative number on the real numbers
            key = "log_undef_zero" if bound == 0 else "log_neg_arg"
            args = [CoreNode.constant("0")] if bound == 0 else []
            raise UndefinedError(
                "логарифм не определён",
                key,
                explanation_args=args,
                header="expr_not_def_in_r",
            )
    if result is None:
        return node
    if node.type is T.EXP:
        zero, one = CoreNode.constant("0"), CoreNode.constant("1")
        ctx.result.add_group("pow", Step(node, result, "pow_with_zero", [zero, one]))
        return result
    if node.type is T.LN and result.value == "0":
        one, zero = CoreNode.constant("1"), CoreNode.constant("0")
        ctx.result.add_group("log_calculate", Step(node, result, "log_arg_one", [one, zero]))
        return result
    if node.type is T.LN and node.children[0].type is T.POWER:
        # ln e⁵: the power rule, then ln e = 1, then the product with one
        return _ln_power_rows(node, result, ctx)
    if node.type is T.LN and node.children[0].type is T.CONSTANT and node.children[0].value == "e":
        one = CoreNode.constant("1")
        ctx.result.add_group(
            "log_calculate",
            Step(node, result, "log_same_base_arg_ln", [CoreNode.variable("e"), one]),
        )
        return result
    if node.type is T.LOG10:
        if result.value == "0" and (node.children[0].value or "") == "1":
            one, zero = CoreNode.constant("1"), CoreNode.constant("0")
            ctx.result.add_group("log_calculate", Step(node, result, "log_arg_one", [one, zero]))
            return result
        if ctx.depth == 0 and _integer(result) not in (None, 0):
            return _log_rows(node, result, CoreNode.constant("10"), ctx)
    if node.type is T.LOG and ctx.depth == 0 and _integer(result) is not None:
        log_base = node.children[1]
        return _log_rows(node, result, log_base, ctx)
    ctx.result.add(Step(left=node, right=result, key=_KEY_CALCULATE))
    return result


def _log_rows(node: CoreNode, result: CoreNode, base: CoreNode, ctx: SolveContext) -> CoreNode:
    """``log_a(a^k)`` in the rows: power of the base, change of base, reduce."""
    eq, num = CoreNode.node, CoreNode.constant
    if node.children[0].structural_eq(base):
        # log_b b = 1: the argument is the base itself, no «write as a power» row
        one = num("1")
        ctx.result.add_group("log_calculate", Step(node, one, "log_same_base_arg", [one]))
        return one
    base_value = _integer(base) or 1
    exponent = _log_exponent(node.children[0], base_value)
    if exponent is None:
        exponent = Fraction(_integer(result) or 0)
    exponent_node = _number_node(exponent)

    def powered_log(argument: CoreNode) -> CoreNode:
        if base.value == "10":
            return eq(T.LOG10, argument)
        return eq(T.LOG, argument, base)

    powered = powered_log(eq(T.POWER, base, exponent_node))
    ctx.result.add_group(
        "write_as_exp_short",
        Step(
            node,
            powered,
            "pow_to_same_base",
            [base],
            subresult=_same_base_page(node.children[0], exponent, base, powered),
        ),
    )
    x = CoreNode.variable("x")
    a = CoreNode.variable("a")
    generic = eq(T.EQUALS, eq(T.LOG, eq(T.POWER, a, x), a), x)
    if base.value == "10":
        generic = eq(T.EQUALS, eq(T.LOG10, eq(T.POWER, num("10"), x)), x)
    rule = generic
    translation = eq(
        T.EQUALS,
        eq(T.LOG, eq(T.POWER, a, x), a),
        eq(T.MULTIPLY, x, eq(T.LOG, a, a)),
    )
    one = num("1")
    base_log = powered_log(base)
    detail = SolveResult()
    detail.add_group(
        "trans_msg",
        Step(
            powered,
            eq(T.MULTIPLY, base_log, exponent_node),
            "using_trans",
            [translation],
        ),
    )
    detail.add_group(
        "log_calculate",
        Step(
            eq(T.MULTIPLY, base_log, exponent_node),
            eq(T.MULTIPLY, one, exponent_node),
            "log_same_base_arg",
            [one],
        ),
    )
    detail.add_group(
        "product",
        Step(
            eq(T.MULTIPLY, one, exponent_node),
            result,
            "mul_with_one",
            [one],
        ),
    )
    detail.set_solution(result)
    ctx.result.add_group("simplify", Step(powered, result, "using_sim", [rule], subresult=detail))
    return result


def _ln_power_rows(node: CoreNode, result: CoreNode, ctx: SolveContext) -> CoreNode:
    """``ln eᵗ = t·ln e = t·1 = t``: the three rows the app shows."""
    eq, num = CoreNode.node, CoreNode.constant
    exponent = node.children[0].children[1]
    e, one = num("e"), num("1")
    a, n = CoreNode.variable("a"), CoreNode.variable("n")
    law = eq(
        T.EQUALS,
        eq(T.LN, eq(T.POWER, a, n)),
        eq(T.MULTIPLY, n, eq(T.LN, a)),
    )
    product = eq(T.MULTIPLY_IMPLICIT, exponent, eq(T.LN, e))
    scaled = eq(T.MULTIPLY, exponent, one)
    ctx.result.add_group("trans_msg", Step(node, product, "using_trans", [law]))
    ctx.result.add_group("log_calculate", Step(product, scaled, "log_same_base_arg_ln", [e, one]))
    ctx.result.add_group("product", Step(scaled, result, "mul_with_one", [one]))
    return result


def _same_base_page(
    argument: CoreNode, exponent: Fraction, base: CoreNode, powered: CoreNode
) -> SolveResult | None:
    """``1/9 = 1/3² = 3⁻²``: the page the app opens on the «write as a power» row.

    Only a fraction whose numerator and denominator are both powers of the base needs
    it: for plain numbers the row is the whole story (``log₂ 4 = log₂ 2²``).
    """
    value, base_value = _numeric_value(argument), _integer(base)
    if value is None or base_value is None or value.denominator == 1:
        return None
    if exponent.denominator != 1:
        return None
    top, bottom = _exact_log(value.numerator, base_value), _exact_log(value.denominator, base_value)
    if top is None or bottom is None:
        return None
    numerator = (
        CoreNode.constant("1")
        if top == 0
        else CoreNode.node(T.POWER, base, CoreNode.constant(str(top)))
    )
    rewritten = CoreNode.node(
        T.FRACTION, numerator, CoreNode.node(T.POWER, base, CoreNode.constant(str(bottom)))
    )
    a, n = CoreNode.variable("a"), CoreNode.variable("n")
    law = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.FRACTION, CoreNode.constant("1"), CoreNode.node(T.POWER, a, n)),
        CoreNode.node(T.POWER, a, CoreNode.node(T.NEGATIVE, n)),
    )
    page = SolveResult()
    page.header = "write_as_exp_short"
    page.add_group("write_as_exp_short", Step(argument, rewritten, "pow_to_same_base", [base]))
    page.add_group("trans_msg", Step(rewritten, powered.children[0], "using_trans", [law]))
    page.set_solution(powered.children[0])
    return page


def _perfect_power_base(value: int) -> tuple[int, int] | None:
    """``(base, exponent)`` with ``base ** exponent == value`` and ``exponent >= 4``."""
    for base in range(2, isqrt(value) + 1):
        exponent, power = 2, base * base
        while power < value:
            power *= base
            exponent += 1
        if power == value and exponent >= 4:
            return base, exponent
    return None


@method_provider(T.ROOT2)
def root_perfect_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """A perfect square that is also a higher power: the card also writes ``2⁴``."""
    _ = variables
    if len(node.children) != 1:
        return []
    radicand = node.children[0]
    value = _integer(radicand)
    if value is None or value <= 1:
        return []
    root = _perfect_root(value, 2)
    if root is None:
        return []
    powered = _perfect_power_base(value)
    if powered is None:
        return []
    base, exponent = powered
    plain = SolveResult()
    answer = solve_root(node, SolveContext(result=plain))
    plain.set_solution(answer)
    eq = CoreNode.node
    extended = eq(
        T.ROOT2, eq(T.POWER, CoreNode.constant(str(base)), CoreNode.constant(str(exponent)))
    )
    detail = SolveResult()
    detail.add_group(
        "write_as_exp_short",
        Step(node, extended, "pow_to_same_base", [CoreNode.constant(str(base))]),
    )
    reduced = eq(
        T.POWER, eq(T.ABS, CoreNode.constant(str(base))), CoreNode.constant(str(exponent // 2))
    )
    detail.add_group(
        "root_simplify", Step(extended, reduced, "root_reduce", [CoreNode.constant("2")])
    )
    detail.set_solution(answer)
    card = SolveResult()
    card.add_group(
        "write_as_exp_short",
        Step(node, extended, "pow_to_same_base", [CoreNode.constant(str(base))]),
    )
    card.add_group(
        "root_simplify", Step(extended, reduced, "root_reduce", [CoreNode.constant("2")])
    )
    card.set_solution(answer)
    _ = detail
    return [plain, card]


@method_provider(T.LN)
def logarithm_alternative_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """``ln 1``: besides the definition, the card shows the change-of-base card."""
    _ = variables
    if len(node.children) != 1 or _integer(node.children[0]) != 1:
        return []
    plain = SolveResult()
    answer = solve_logarithm(node, SolveContext(result=plain))
    plain.set_solution(answer)
    eq = CoreNode.node
    a, x = CoreNode.variable("a"), CoreNode.variable("x")
    law = eq(
        T.EQUALS,
        eq(T.LOG, x, a),
        eq(T.FRACTION, eq(T.LOG10, x), eq(T.LOG10, a)),
    )
    rewritten = eq(
        T.ALTERNATIVE_FORM,
        eq(
            T.FRACTION,
            eq(T.LOG10, CoreNode.constant("1")),
            eq(T.LOG10, CoreNode.constant("e")),
        ),
        CoreNode.constant("0"),
    )
    card = SolveResult()
    card.add_group("rewrite_expression", Step(node, rewritten, "log_rewrite", [law]))
    card.set_solution(answer)
    return [plain, card]


__all__ = [
    "solve_logarithm",
    "solve_root",
]
