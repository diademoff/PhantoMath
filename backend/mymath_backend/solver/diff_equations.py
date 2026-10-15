"""Дифференциальные уравнения (команда ``diff_eq``).

Уравнение записывается как ``y′ = f(x, y)``: производная — узел ``PRIME``
(один ребёнок — переменная, как рисует Photomath: ``c/a/a/l/h/v/k.java``),
вторая производная — ``DERIVATION2_PRIME``. Независимая переменная — вторая
свободная переменная выражения, по умолчанию ``x``.

Уравнение решает sympy (``dsolve``), вид шага выбирается по классификации
(``classify_ode``): разделяющиеся переменные — ``diff_eq_solve_by_separation``,
линейное первого порядка — ``diff_eq_solve_linear``, иначе ``diff_eq_solve``.
Ответ — ``y = …``. Аргументы команды ``[x₀, y₀]`` задают начальное условие:
тогда находится частное решение (``diff_eq_use_init_condition``).

Свободные константы интегрирования ``C1``/``C2`` переименовываются в ``C``/``D``,
чтобы ответ читался как в Photomath. Связь представления производных с
рендером APK зафиксирована здесь: ``PRIME`` — первый порядок, ``DERIVATION2_PRIME``
— второй.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step
from .sympy_bridge import from_sympy, to_sympy

_FIRST_ORDER = (T.PRIME, T.DERIVATION1_PRIME)
_CONSTANT_NAMES = ("C", "D", "E", "F")


def diff_eq(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Решить дифференциальное уравнение (общее или частное решение)."""
    if node.type is not T.EQUALS or len(node.children) != 2:
        raise SolveError("дифференциальное уравнение — это равенство")
    lhs, rhs = node.children
    order = _order_of(lhs)
    if order is None or not lhs.children:
        raise SolveError("в левой части должна быть производная y′")
    dependent = lhs.children[0]
    if dependent.type is not T.VARIABLE or not dependent.value:
        raise SolveError("производная берётся от переменной")
    dep = dependent.value
    ind = next((name for name in ctx.variables if name != dep), "x")
    xsym = sympy.Symbol(ind)
    yfun = sympy.Function(dep)

    try:
        rhs_expr = to_sympy(rhs).subs(sympy.Symbol(dep), yfun(xsym))
    except SolveError as error:
        raise SolveError("правая часть не выражается") from error
    derivative = sympy.Derivative(yfun(xsym), xsym, order)
    equation = sympy.Eq(derivative, rhs_expr)

    initial = _init_condition(args)
    if initial is None:
        try:
            solution = sympy.dsolve(equation, yfun(xsym))
        except (NotImplementedError, TypeError, ValueError) as error:
            raise SolveError("уравнение не решается") from error
        ctx.result.add(Step(left=node, right=None, key=_classification(equation, yfun(xsym))))
        answer = _solution_node(solution, dep)
        ctx.result.add(Step(left=node, right=answer, key="diff_eq_write_general_sol"))
        return answer

    x_zero, y_zero = initial
    x0 = _number(x_zero)
    y0 = _number(y_zero)
    try:
        solution = sympy.dsolve(equation, yfun(xsym), ics={yfun(x0): y0})
    except (NotImplementedError, TypeError, ValueError) as error:
        raise SolveError("уравнение с начальным условием не решается") from error
    condition = CoreNode.node(
        T.EQUALS, CoreNode.node(T.EVALUATE_EXPRESSION, CoreNode.variable(dep), x_zero), y_zero
    )
    ctx.result.add(
        Step(
            left=node,
            right=None,
            key="diff_eq_use_init_condition",
            args=[condition, y_zero, CoreNode.variable(dep), x_zero, CoreNode.variable(ind)],
        )
    )
    answer = _solution_node(solution, dep)
    ctx.result.add(Step(left=node, right=answer, key="diff_eq_find_particular"))
    return answer


def _order_of(node: CoreNode) -> int | None:
    """Порядок производной по узлу или ``None``."""
    if node.type is T.DERIVATION2_PRIME:
        return 2
    if node.type in _FIRST_ORDER:
        return 1
    return None


def _classification(equation: sympy.Eq, function: sympy.Function) -> str:
    """Ключ шага по классификации sympy."""
    try:
        hints = sympy.classify_ode(equation, function)
    except (NotImplementedError, TypeError, ValueError):
        return "diff_eq_solve"
    if "separable" in hints:
        return "diff_eq_solve_by_separation"
    if "1st_linear" in hints:
        return "diff_eq_solve_linear"
    return "diff_eq_solve"


def _solution_node(solution: sympy.Expr, dep: str) -> CoreNode:
    """Ответ ``y = …`` из результата ``dsolve`` (может быть списком ветвей)."""
    equations = solution if isinstance(solution, list) else [solution]
    nodes: list[CoreNode] = []
    for entry in equations:
        rhs = entry.rhs if isinstance(entry, sympy.Eq) else entry
        nodes.append(CoreNode.node(T.EQUALS, CoreNode.variable(dep), from_sympy(_rename(rhs))))
    if len(nodes) == 1:
        return nodes[0]
    return CoreNode.node(T.LIST, *nodes)


def _rename(expression: sympy.Expr) -> sympy.Expr:
    """Переименовать константы ``C1``/``C2``/… в ``C``/``D``/…."""
    for index, name in enumerate(_CONSTANT_NAMES, start=1):
        expression = expression.subs(sympy.Symbol(f"C{index}"), sympy.Symbol(name))
    return expression


def _init_condition(args: list[CoreNode]) -> tuple[CoreNode, CoreNode] | None:
    """Пара ``(x₀, y₀)`` начального условия или ``None``."""
    if not args:
        return None
    if len(args) != 2:
        raise SolveError("начальное условие задаётся парой (x₀, y₀)")
    return args[0], args[1]


def _number(node: CoreNode) -> sympy.Expr:
    """Точка начального условия как число sympy."""
    value = to_sympy(node)
    if value.is_number is not True:
        raise SolveError("начальное условие должно быть числом")
    return value


__all__ = [
    "diff_eq",
]
