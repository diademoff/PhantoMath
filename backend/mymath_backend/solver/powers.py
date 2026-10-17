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
from math import isqrt

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .arithmetic import format_number
from .base import SolveContext, SolveError, SolveResult, Step, fold_semantically, solver_for

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


@solver_for(T.ROOT2, T.ROOT)
def solve_root(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Упростить корень, если он извлекается нацело.

    Если точного корня нет, узел возвращается, но **с уже свёрнутыми**
    степенью и подкоренным: ``√(2+3)`` даёт шаг ``2+3 = 5`` и ответ ``√5``
    (см. ``truth/07-open-questions.md``, Q10).
    """
    if node.type is T.ROOT2:
        degree = 2
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
    if (
        degree == 2
        and integer is not None
        and integer > 1
        and (root is None or root.denominator == 1)
    ):
        return _square_root_rows(node, integer, ctx) or kept
    if root is None:
        return kept

    result = CoreNode.constant(format_number(root))
    ctx.result.add(Step(left=node, right=result, key=_KEY_ROOT))
    return result


def _square_root_rows(node: CoreNode, n: int, ctx: SolveContext) -> CoreNode | None:
    """Photomath 7.10.0 rows for a square root of an integer: via a power, or pulling a factor out.

    ``None`` when ``n`` is square-free (nothing to simplify).
    """
    k = max(c for c in range(1, isqrt(n) + 1) if n % (c * c) == 0)
    if k == 1:
        return None

    def number(value: int) -> CoreNode:
        return CoreNode.constant(str(value))

    def square(value: int) -> CoreNode:
        return CoreNode.node(T.POWER, number(value), number(2))

    root_of = lambda inner: CoreNode.node(T.ROOT2, inner)  # noqa: E731
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
    factored = root_of(CoreNode.node(T.MULTIPLY, square(k), number(rest)))
    split = CoreNode.node(T.MULTIPLY, root_of(square(k)), root_of(number(rest)))
    detail = SolveResult()
    detail.add_group("root_reduce", Step(split, result, "root_reduce", [two]))
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
    if node.type is T.LN:
        argument = fold_semantically(node.children[0], ctx)
        node = CoreNode(type=T.LN, children=[argument])
        if argument.type is T.CONSTANT and argument.value == "e":
            result = CoreNode.constant("1")
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
        value = _integer(argument)
        if value is not None:
            exponent = _exact_log(value, 10)
            if exponent is not None:
                result = CoreNode.constant(str(exponent))
    elif node.type is T.LOG:
        if len(node.children) == 2:
            value_node = fold_semantically(node.children[0], ctx)
            base_node = fold_semantically(node.children[1], ctx)
            node = CoreNode(type=T.LOG, children=[value_node, base_node])
            value = _integer(value_node)
            base = _integer(base_node)
            if value is not None and base is not None:
                exponent = _exact_log(value, base)
                if exponent is not None:
                    result = CoreNode.constant(str(exponent))

    if result is None:
        return node
    ctx.result.add(Step(left=node, right=result, key=_KEY_CALCULATE))
    return result


__all__ = [
    "solve_logarithm",
    "solve_root",
]
