"""Решатель: точка входа и маршрутизация по типам узлов.

Модули регистрируются декоратором :func:`~mymath_backend.solver.base.solver_for`
при импорте; :func:`solve` находит модуль по ``CoreNode.type`` и отдаёт
результат в формате контракта Photomath.

Состав модулей расширяется по мере готовности: сейчас это арифметика.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType
from ..results import CoreSolverData
from . import commands
from .absolute import solve_abs_equation, solve_value_function
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
from .combinatorics import solve_arrangement, solve_choose, solve_factorial
from .complex import contains_imaginary, solve_complex, solve_imaginary_arithmetic
from .derivatives import solve_derivative
from .equations import solve_equation, solve_methods
from .fractions import solve_fraction
from .inequalities import solve_inequality
from .integrals import solve_integral
from .limits import solve_limit
from .matrices import solve_determinant, solve_matrix
from .powers import solve_logarithm, solve_root
from .series import solve_series
from .sympy_bridge import from_sympy, to_sympy
from .systems import solve_system
from .trig_equations import Interval, solve_trig_equation
from .trigonometry import solve_angle_unit, solve_function

# Ключ шага упрощения (общий с командой ``simplify``).
_KEY_SIMPLIFY = "simplify"


def solve(
    node: CoreNode,
    command: str | None = None,
    args: list[CoreNode] | None = None,
    interval: Interval | None = None,
) -> CoreSolverData:
    """Решить выражение и вернуть ответ в формате контракта.

    ``command`` — имя действия (``CoreAction.command``): ``None`` или ``solve``
    решают как обычно, ``factor``/``expand``/``simplify`` и векторные команды
    применяют соответствующее преобразование (см. ``solver/commands.py``).
    ``args`` — аргументы команды (``CoreAction.args``), например второй вектор.
    ``interval`` — промежуток для отбора корней тригонометрического уравнения.

    Бросает :class:`SolveError`, если задача не решается текущим набором
    модулей. Вызывающий сам решает, что показать пользователю: 404 с
    понятным текстом или 500.
    """
    result = SolveResult()
    ctx = SolveContext(result=result, variables=_free_variables(node))

    if command is not None and command != "solve":
        solution = commands.apply(command, node, ctx, args)
        result.set_solution(solution)
        return build_solver_data(node, result)

    if node.type is CoreNodeType.EQUALS:
        abs_equation = solve_abs_equation(node, ctx.variables)
        if abs_equation is not None:
            return build_solver_data(node, abs_equation)
        trig = solve_trig_equation(node, ctx.variables, interval)
        if trig is not None:
            return build_solver_data(node, trig)
        # Уравнение решается несколькими способами; первый — основной.
        methods = solve_methods(node, ctx.variables)
        alternatives = methods[1:]
        return build_solver_data(
            node,
            methods[0],
            alternatives=alternatives,
            select_method_text="select_method" if alternatives else None,
        )

    if contains_imaginary(node) and node.type not in (
        CoreNodeType.REAL,
        CoreNodeType.IMAGINARY,
        CoreNodeType.CONJUGATE,
    ):
        # Арифметику с мнимой единицей считает sympy: наше сворачивание к
        # числу её не знает. Re/Im/сопряжение отрабатывают свои модули.
        result.set_solution(solve_imaginary_arithmetic(node, ctx))
        return build_solver_data(node, result)

    try:
        route(node, ctx)
    except SolveError as error:
        fallback = _simplify_fallback(node)
        if fallback is None:
            raise error
        return build_solver_data(node, fallback)
    if not result:
        # Вырожденный ввод — одно число без операций: шага нет, но ответ есть.
        result.set_solution(_constant_or_original(node))
    else:
        result.set_solution(_final_value(result))
    return build_solver_data(node, result)


def _simplify_fallback(node: CoreNode) -> SolveResult | None:
    """Упростить символьное выражение, если обычный маршрут не справился.

    Запасной путь для тождеств и формул: арифметика не пропускает
    символьные операнды, поэтому ``sin²x + cos²x`` до неё не доходит.
    Возвращает результат с шагом «Упростить» или ``None``, если упрощение
    ничего не изменило — тогда важнее исходная ошибка.
    """
    try:
        expression = to_sympy(node)
        simplified = sympy.simplify(expression)
        if simplified == expression:
            return None
        simplified_node = from_sympy(simplified)
    except SolveError:
        return None

    result = SolveResult()
    result.add(Step(left=node, right=simplified_node, key=_KEY_SIMPLIFY))
    result.set_solution(simplified_node)
    return result


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
    "solve_abs_equation",
    "solve_angle_unit",
    "solve_arrangement",
    "solve_choose",
    "solve_complex",
    "solve_derivative",
    "solve_determinant",
    "solve_equation",
    "solve_factorial",
    "solve_fraction",
    "solve_function",
    "solve_inequality",
    "solve_integral",
    "solve_limit",
    "solve_logarithm",
    "solve_matrix",
    "solve_root",
    "solve_series",
    "solve_system",
    "solve_trig_equation",
    "solve_value_function",
    "solver_for",
]
