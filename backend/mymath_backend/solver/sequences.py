"""Последовательности: арифметическая и геометрическая.

Модуль зарегистрирован на узел ``SEQUENCE`` (токен ``sequence``). По первым
членам прогрессия распознаётся:

* если разность между соседними членами постоянна — арифметическая
  (шаг ``seq_state_common_diff``);
* если постоянно отношение — геометрическая (``seq_state_common_ratio``);
* иначе — :class:`SolveError`.

Ответ — следующие четыре члена (шаг ``seq_state_next_four`` и список-узел
``LIST``). Явная и рекуррентная формулы — следующие модули.
"""

from __future__ import annotations

import itertools

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step, boolean_node, solver_for
from .sympy_bridge import from_sympy, to_sympy

_NEXT_COUNT = 4
_KEY_DIFF = "seq_state_common_diff"
_KEY_RATIO = "seq_state_common_ratio"
_KEY_NEXT = "seq_state_next_four"


@solver_for(T.SEQUENCE)
def solve_sequence(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Распознать прогрессию и продолжить её на четыре члена."""
    ctx.require(len(node.children) >= 2, "нужно не меньше двух членов")
    try:
        terms = [to_sympy(child) for child in node.children]
    except SolveError as error:
        raise SolveError("члены последовательности не читаются") from error

    difference = _constant_difference(terms)
    if difference is not None:
        following = _extend(terms[-1], difference, multiply=False)
        key, step_value = _KEY_DIFF, difference
    else:
        ratio = _constant_ratio(terms)
        if ratio is None:
            raise SolveError("последовательность не арифметическая и не геометрическая")
        following = _extend(terms[-1], ratio, multiply=True)
        key, step_value = _KEY_RATIO, ratio

    next_list = CoreNode.node(T.LIST, *(from_sympy(value) for value in following))
    ctx.result.add(Step(left=node, right=None, key=key, args=[from_sympy(step_value)]))
    ctx.result.add(Step(left=node, right=next_list, key=_KEY_NEXT, args=[next_list]))
    return next_list


def explicit_formula(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Записать явную формулу общего члена ``aₙ``.

    Аргумент команды не нужен: разность/знаменатель определяются по первым
    членам. Шаги ``seq_write_explicit_formula`` и
    ``seq_arithmetic_sub_explicit_formula``/``seq_geometric_sub_explicit_formula``.
    """
    del args
    ctx.require(node.type is T.SEQUENCE and len(node.children) >= 2, "нужна последовательность")
    terms = [to_sympy(child) for child in node.children]
    first, step, formula, arithmetic = _explicit(terms)
    key = (
        "seq_arithmetic_sub_explicit_formula"
        if arithmetic
        else "seq_geometric_sub_explicit_formula"
    )

    answer = from_sympy(formula)
    ctx.result.add(Step(left=node, right=None, key="seq_write_explicit_formula"))
    ctx.result.add(
        Step(
            left=node,
            right=answer,
            key=key,
            args=[from_sympy(first), from_sympy(step), CoreNode.variable("n"), answer],
        )
    )
    return answer


def sequence_convergence(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Определить сходимость последовательности (предел общего члена).

    Предел берётся у явной формулы ``aₙ``; шаги ``seq_find_limit`` и
    ``seq_lim_conv``/``seq_lim_div``/``seq_no_lim_div``. Ответ — «Истина»/«Ложь».
    """
    del args
    ctx.require(node.type is T.SEQUENCE and len(node.children) >= 2, "нужна последовательность")
    terms = [to_sympy(child) for child in node.children]
    _, _, formula, _ = _explicit(terms)
    index = sympy.Symbol("n")
    value = sympy.limit(formula, index, sympy.oo)
    if value is sympy.nan or value.has(sympy.Limit):
        key = "seq_no_lim_div"
        converges = False
    elif value in (sympy.oo, -sympy.oo, sympy.zoo):
        key = "seq_lim_div"
        converges = False
    else:
        key = "seq_lim_conv"
        converges = True
    answer = boolean_node(converges)
    ctx.result.add(Step(left=node, right=None, key="seq_find_limit"))
    ctx.result.add(Step(left=node, right=answer, key=key))
    return answer


def _explicit(terms: list[sympy.Expr]) -> tuple[sympy.Expr, sympy.Expr, sympy.Expr, bool]:
    """``(первый член, шаг, формула aₙ, арифметическая?)``."""
    index = sympy.Symbol("n")
    first = terms[0]
    difference = _constant_difference(terms)
    if difference is not None:
        return first, difference, sympy.simplify(first + (index - 1) * difference), True
    ratio = _constant_ratio(terms)
    if ratio is None:
        raise SolveError("последовательность не арифметическая и не геометрическая")
    return first, ratio, sympy.simplify(first * ratio ** (index - 1)), False


def _constant_difference(terms: list[sympy.Expr]) -> sympy.Expr | None:
    """Постоянная разность соседних членов или ``None``."""
    differences = [b - a for a, b in itertools.pairwise(terms)]
    return differences[0] if _all_equal(differences) else None


def _constant_ratio(terms: list[sympy.Expr]) -> sympy.Expr | None:
    """Постоянное отношение соседних членов или ``None``."""
    if any(_is_zero(term) for term in terms[:-1]):
        return None
    ratios = [b / a for a, b in itertools.pairwise(terms)]
    return ratios[0] if _all_equal(ratios) else None


def _all_equal(values: list[sympy.Expr]) -> bool:
    """Все значения равны между собой."""
    if not values:
        return False
    first = values[0]
    return all(_is_zero(value - first) for value in values[1:])


def _is_zero(expression: sympy.Expr) -> bool:
    result = expression == 0
    return result is True or result is sympy.true


def _extend(last: sympy.Expr, step: sympy.Expr, *, multiply: bool) -> list[sympy.Expr]:
    """Следующие ``_NEXT_COUNT`` членов."""
    following: list[sympy.Expr] = []
    current = last
    for _ in range(_NEXT_COUNT):
        current = current * step if multiply else current + step
        following.append(current)
    return following


__all__ = [
    "explicit_formula",
    "sequence_convergence",
    "solve_sequence",
]
