"""Решатель: точка входа и маршрутизация по типам узлов.

Модули регистрируются декоратором :func:`~mymath_backend.solver.base.solver_for`
при импорте; :func:`solve` находит модуль по ``CoreNode.type`` и отдаёт
результат в формате контракта Photomath.

Состав модулей расширяется по мере готовности: сейчас это арифметика.
"""

from __future__ import annotations

from ..ast import CoreNode
from ..results import CoreSolverData
from .arithmetic import format_number
from .base import (
    SolveContext,
    SolveError,
    SolveResult,
    Step,
    build_solver_data,
    registered_types,
    route,
    solver_for,
)
from .derivatives import solve_derivative
from .equations import solve_equation
from .fractions import solve_fraction
from .inequalities import solve_inequality
from .powers import solve_logarithm, solve_root
from .systems import solve_system


def solve(node: CoreNode) -> CoreSolverData:
    """Решить выражение и вернуть ответ в формате контракта.

    Бросает :class:`SolveError`, если задача не решается текущим набором
    модулей. Вызывающий сам решает, что показать пользователю: 404 с
    понятным текстом или 500.
    """
    result = SolveResult()
    ctx = SolveContext(result=result, variables=_free_variables(node))
    route(node, ctx)
    if not result:
        # Вырожденный ввод — одно число без операций: шага нет, но ответ есть.
        result.set_solution(_constant_or_original(node))
    else:
        result.set_solution(_final_value(result))
    return build_solver_data(node, result)


def _free_variables(node: CoreNode) -> list[str]:
    """Переменные, встречающиеся в выражении, в порядке появления."""
    seen: list[str] = []
    for n in node.walk():
        if n.type.value == "VARIABLE" and n.value and n.value not in seen:
            seen.append(n.value)
    return seen


def _constant_or_original(node: CoreNode) -> CoreNode:
    """Ответ для выражения без операций."""
    from .arithmetic import as_fraction, is_zero

    del is_zero
    if node.type.value == "CONSTANT" and node.value:
        return CoreNode.constant(node.value)
    if node.type.value == "VARIABLE":
        return node
    try:
        return CoreNode.constant(format_number(as_fraction(node)))
    except SolveError:
        return node


def _final_value(result: SolveResult) -> CoreNode:
    """Взять значение последнего шага как ответ."""
    last: Step | None = None
    for step in result:
        last = step
    if last is None or last.right is None:
        return CoreNode.empty()
    return last.right


__all__ = [
    "SolveContext",
    "SolveError",
    "SolveResult",
    "Step",
    "registered_types",
    "route",
    "solve",
    "solve_derivative",
    "solve_equation",
    "solve_fraction",
    "solve_inequality",
    "solve_logarithm",
    "solve_root",
    "solve_system",
    "solver_for",
]
