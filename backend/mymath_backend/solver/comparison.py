"""Сравнение чисел и выражений и упорядочивание.

Отношение без свободных переменных (``2 < 3``, ``2 = 2``) — это утверждение,
истинное или ложное, а не уравнение: булев ответ — ``TEXT[TEXT_KEY]``.
Сравнение запускается из :func:`mymath_backend.solver.solve`
(спец-обработка отношений без переменных), поэтому своего ``solver_for`` у
проверки нет; при переменных работает модуль неравенств.

Ключи шага: ``compare_eq_eq``/``compare_eq_neq`` для равенства,
``compare_ineq`` для неравенства. Дроби с разными знаменателями решатель
сначала приводит к наименьшему общему знаменателю (``frac_expand_lcd_msg``,
``mul_with_one``/``mul``) и только потом сравнивает числители
(``compare_frac_nom``); карточка перекрёстного умножения
(``compare_frac_cross``) — второй способ, его точка входа пока
показывает один способ.

Узел ``ORDER`` — упорядочивание элементов по возрастанию; ответ — тот же узел
с отсортированными детьми. Ключа шага у ``ORDER`` в словаре нет, поэтому ответ
отдаётся **без шага**.
"""

from __future__ import annotations

from fractions import Fraction

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .arithmetic import format_number
from .base import SolveContext, SolveError, Step, boolean_node, fold_semantically, solver_for
from .sympy_bridge import to_sympy

# Отношения, которые без переменных становятся утверждением «Истина»/«Ложь».
COMPARABLE = (
    T.EQUALS,
    T.NOT_EQUALS,
    T.LESS_THAN,
    T.LESS_THAN_EQUAL,
    T.GREATER_THAN,
    T.GREATER_THAN_EQUAL,
)


def solve_comparison(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Проверить утверждение без переменных и вернуть «Истина»/«Ложь»."""
    ctx.require(len(node.children) == 2, "утверждение связывает две части")
    left, right = to_sympy(node.children[0]), to_sympy(node.children[1])
    value = _evaluate(node.type, left, right)
    if value not in (True, False):
        raise SolveError("утверждение не удалось проверить")
    answer = boolean_node(value)
    if node.type is not T.EQUALS and _fraction_rows(node, left, right, answer, ctx):
        return answer
    detail = _detail_key(left, right)
    if detail is not None:
        ctx.result.add(Step(left=node, right=None, key=detail))
    ctx.result.add(Step(left=node, right=answer, key=_step_key(node.type, value)))
    return answer


def _step_key(node_type: T, value: bool) -> str:
    """Ключ итоговой карточки проверки."""
    if node_type is T.EQUALS:
        return "compare_eq_eq" if value else "compare_eq_neq"
    return "compare_ineq"


def _const(value: int | Fraction) -> CoreNode:
    return CoreNode.constant(format_number(Fraction(value)))


def _product(first: int, second: int) -> CoreNode:
    """``a · b`` как узел умножения (``a`` и ``b`` — целые)."""
    return CoreNode.node(T.MULTIPLY, _const(first), _const(second))


def _product_key(first: int, second: int) -> tuple[str, list[CoreNode]]:
    """Key of one multiplication row: a factor of 1 is the ``mul_with_one`` card."""
    if 1 in (first, second):
        return "mul_with_one", [_const(Fraction(1))]
    return "mul", []


def _replace_side(relation: T, node: CoreNode, position: int, side: CoreNode) -> CoreNode:
    """``node`` with one side replaced, keeping the relation and the other side."""
    children = [node.children[0], node.children[1]]
    children[position] = side
    return CoreNode.node(relation, *children)


def _fraction_rows(
    node: CoreNode, left: sympy.Expr, right: sympy.Expr, answer: CoreNode, ctx: SolveContext
) -> bool:
    """The app's default card for ``a/b ⋚ c/d``: least common denominator, then numerators.

    Returns ``False`` (without touching the result) outside the verified shape:
    non-rational sides, integers, equal numerators or equal denominators.
    """
    if not (left.is_Rational and right.is_Rational):
        return False
    n1, d1 = int(left.p), int(left.q)
    n2, d2 = int(right.p), int(right.q)
    if d1 == 1 or d2 == 1 or n1 == n2 or d1 == d2:
        return False
    lcd = int(sympy.ilcm(d1, d2))
    m1, m2 = lcd // d1, lcd // d2
    if m1 == 1 and m2 == 1:
        return False
    relation = node.type
    right_node = node.children[1]
    current = node
    expansion: list[Step] = []
    if m1 != 1:
        expanded = CoreNode.node(
            relation,
            CoreNode.node(T.FRACTION, _product(n1, m1), _product(d1, m1)),
            right_node,
        )
        expansion.append(Step(current, expanded, "frac_expand_lcd_msg", [_const(lcd)]))
        current = expanded
    if m2 != 1:
        expanded = CoreNode.node(
            relation,
            current.children[0],
            CoreNode.node(T.FRACTION, _product(n2, m2), _product(d2, m2)),
        )
        expansion.append(Step(current, expanded, "frac_expand_lcd_msg", [_const(lcd)]))
        current = expanded

    multiplications: list[Step] = []
    for numerator, denominator, multiplier, position in (
        (n1, d1, m1, 0),
        (n2, d2, m2, 1),
    ):
        if multiplier == 1:
            continue
        fraction = current.children[position]
        key, args = _product_key(numerator, multiplier)
        following = _replace_side(
            relation,
            current,
            position,
            CoreNode.node(T.FRACTION, _const(numerator * multiplier), fraction.children[1]),
        )
        multiplications.append(Step(current, following, key, args))
        current = following
        fraction = current.children[position]
        key, args = _product_key(denominator, multiplier)
        following = _replace_side(
            relation,
            current,
            position,
            CoreNode.node(T.FRACTION, fraction.children[0], _const(denominator * multiplier)),
        )
        multiplications.append(Step(current, following, key, args))
        current = following

    count_left, count_right = n1 * m1, n2 * m2
    numerators = CoreNode.node(relation, _const(count_left), _const(count_right))
    ctx.result.add_group("frac_expand_plural", *expansion)
    if multiplications:
        ctx.result.add_group("multiply", *multiplications)
    ctx.result.add_group("compare_nums", Step(current, numerators, "compare_frac_nom"))
    ctx.result.add_group("compare_check_ineq", Step(numerators, answer, "compare_ineq"))
    return True


def _detail_key(left: sympy.Expr, right: sympy.Expr) -> str | None:
    """Шаг с приёмом сравнения дробей или ``None``."""
    numerator_left, denominator_left = sympy.fraction(sympy.nsimplify(left))
    numerator_right, denominator_right = sympy.fraction(sympy.nsimplify(right))
    if denominator_left == 1 and denominator_right == 1:
        return None
    if denominator_left == denominator_right:
        return "compare_frac_nom"
    if numerator_left == numerator_right:
        return "compare_frac_den"
    return "compare_frac_cross"


def _evaluate(node_type: T, left: sympy.Expr, right: sympy.Expr) -> bool | None:
    """Значение отношения между двумя выражениями без переменных.

    ``None`` — sympy не смог свести отношение к булеву значению.
    """
    if node_type is T.EQUALS:
        result: sympy.Basic = sympy.Eq(left, right)
    elif node_type is T.NOT_EQUALS:
        result = sympy.Ne(left, right)
    elif node_type is T.LESS_THAN:
        result = left < right
    elif node_type is T.LESS_THAN_EQUAL:
        result = left <= right
    elif node_type is T.GREATER_THAN:
        result = left > right
    else:
        result = left >= right
    return _as_bool(result)


def _as_bool(value: object) -> bool | None:
    """Свести ответ sympy к ``bool``; ``None`` — значение не определено.

    sympy отдаёт ``BooleanTrue``/``BooleanFalse`` (не питоновский ``bool``)
    либо нерешённое отношение; последнее пробуем упростить.
    """
    if isinstance(value, bool):
        return value
    if value is sympy.true or value is sympy.false:
        return value is sympy.true
    simplified = sympy.simplify(value)
    if isinstance(simplified, bool):
        return simplified
    if simplified is sympy.true or simplified is sympy.false:
        return simplified is sympy.true
    return None


@solver_for(T.ORDER)
def solve_order(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Упорядочить элементы ``ORDER`` по возрастанию."""
    ctx.require(len(node.children) >= 1, "ORDER требует элементов")
    items = [fold_semantically(child, ctx) for child in node.children]
    try:
        ordered = sorted(items, key=lambda item: to_sympy(item).sort_key())
    except (TypeError, ValueError) as error:
        raise SolveError("элементы нельзя упорядочить") from error
    return CoreNode.node(T.ORDER, *ordered)


__all__ = [
    "COMPARABLE",
    "solve_comparison",
    "solve_order",
]
