"""Суммы (знак суммирования).

Модуль зарегистрирован на ``SIGMA_DEFINITE``. Дети, как в нативном решателе
(``c/a/a/l/h/v/k.java``): ``[индекс, нижний предел, верхний предел,
выражение]``. Принимается и форма редактора ``[нижний, верхний, выражение]``
с индексом ``n``.

Сумма вычисляется sympy; для числовых пределов выходит точное число, для
символьной верхней границы — формула. Результат переводится обратно в
``CoreNode`` мостом.

Шаг один — ``series_sigma_find_sub``.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step, boolean_node, solver_for
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


@solver_for(T.SIGMA_DEFINITE)
def solve_series(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить сумму ряда."""
    index, lower, upper, expression = _parts(node)
    symbol = sympy.Symbol(index)
    value = sympy.summation(
        to_sympy(expression),
        (symbol, to_sympy(lower), to_sympy(upper)),
    )
    if value.has(sympy.Sum):
        raise SolveError("сумму не удалось вычислить")
    result = from_sympy(sympy.simplify(value))
    ctx.result.add(Step(left=node, right=result, key="series_sigma_find_sub"))
    return result


def convergence(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Определить, сходится ли ряд (сумма с бесконечным пределом)."""
    del args
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("сходимость определяется у ряда (суммы)")
    index, lower, upper, expression = _parts(node)
    symbol = sympy.Symbol(index)
    value = sympy.summation(to_sympy(expression), (symbol, to_sympy(lower), to_sympy(upper)))
    if value.has(sympy.Sum):
        raise SolveError("сходимость не определена")
    converges = value.is_finite is True
    answer = boolean_node(converges)
    ctx.result.add(Step(left=node, right=answer, key="convergent" if converges else "divergent"))
    return answer


def ratio_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Признак Даламбера: сходимость ряда по пределу ``|aₙ₊₁/aₙ|``.

    Шаги ``series_ratio_test_use`` и ``series_ratio_test_lim_ltone``/
    ``_gtone``/``_inf``. Предел, равный ``1``, ответа не даёт — :class:`SolveError`.
    """
    del args
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("признак Даламбера применяется к ряду (сумме)")
    index, _, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    term = to_sympy(expression)
    if term == 0:
        raise SolveError("нулевой член ряда")
    ratio = sympy.simplify(sympy.Abs(term.subs(symbol, symbol + 1) / term))

    ctx.result.add(Step(left=node, right=None, key="series_ratio_test"))
    ctx.result.add(
        Step(left=node, right=None, key="series_ratio_test_use", args=[from_sympy(ratio)])
    )
    limit = sympy.limit(ratio, symbol, sympy.oo)
    if limit in (sympy.oo, -sympy.oo, sympy.zoo):
        key, answer = "series_ratio_test_lim_inf", boolean_node(False)
        args = [from_sympy(sympy.oo)]
    elif limit.is_number and (limit < 1) is sympy.true:
        key = "series_ratio_test_lim_ltone"
        answer, args = boolean_node(True), [CoreNode.constant("1")]
    elif limit.is_number and (limit > 1) is sympy.true:
        key, answer, args = (
            "series_ratio_test_lim_gtone",
            boolean_node(False),
            [CoreNode.constant("1")],
        )
    else:
        raise SolveError("признак Даламбера не даёт ответа")

    ctx.result.add(Step(left=node, right=answer, key=key, args=args))
    return answer


def root_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Радикальный признак (Коши): предел ``|aₙ|^(1/n)``.

    Шаги ``series_root_test``, ``series_root_test_use`` и
    ``series_root_test_lim_ltone``/``_gtone``/``_inf``. Предел ``1`` ответа не даёт.
    """
    del args
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("радикальный признак применяется к ряду (сумме)")
    index, _, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    term = to_sympy(expression)
    root = sympy.Abs(term) ** (sympy.Integer(1) / symbol)

    ctx.result.add(Step(left=node, right=None, key="series_root_test"))
    ctx.result.add(Step(left=node, right=None, key="series_root_test_use", args=[from_sympy(root)]))
    limit = sympy.limit(root, symbol, sympy.oo)
    if limit in (sympy.oo, -sympy.oo, sympy.zoo):
        key, answer, args_nodes = (
            "series_root_test_lim_inf",
            boolean_node(False),
            [from_sympy(sympy.oo)],
        )
    elif limit.is_number and (limit < 1) is sympy.true:
        key, answer, args_nodes = (
            "series_root_test_lim_ltone",
            boolean_node(True),
            [CoreNode.constant("1")],
        )
    elif limit.is_number and (limit > 1) is sympy.true:
        key, answer, args_nodes = (
            "series_root_test_lim_gtone",
            boolean_node(False),
            [CoreNode.constant("1")],
        )
    else:
        raise SolveError("радикальный признак не даёт ответа")
    ctx.result.add(Step(left=node, right=answer, key=key, args=args_nodes))
    return answer


def nth_term_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Необходимый признак сходимости: предел общего члена.

    Если предел отличен от нуля — ряд расходится (``series_nth_term_test_lim_nozero``);
    нулевой предел ответа не даёт (:class:`SolveError`).
    """
    del args
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("необходимый признак применяется к ряду (сумме)")
    index, _, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    term = to_sympy(expression)

    ctx.result.add(Step(left=node, right=None, key="series_nth_term_test"))
    ctx.result.add(
        Step(left=node, right=None, key="series_nth_term_test_use", args=[from_sympy(term)])
    )
    limit = sympy.limit(term, symbol, sympy.oo)
    if limit.is_number and limit != 0:
        answer = boolean_node(False)
        ctx.result.add(
            Step(
                left=node,
                right=answer,
                key="series_nth_term_test_lim_nozero",
                args=[CoreNode.constant("0")],
            )
        )
        return answer
    raise SolveError("необходимый признак сходимости не даёт ответа")


__all__ = [
    "convergence",
    "nth_term_test",
    "ratio_test",
    "root_test",
    "solve_series",
]
