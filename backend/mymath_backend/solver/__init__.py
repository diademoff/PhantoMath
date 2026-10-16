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
from .comparison import COMPARABLE, solve_comparison, solve_order
from .complex import contains_imaginary, solve_complex, solve_imaginary_arithmetic
from .conditional import solve_conditional
from .containers import solve_add_subtract, solve_container
from .derivatives import solve_derivative
from .diff_equations import diff_eq, is_diff_equation
from .equations import solve_equation
from .evaluate import solve_evaluate_expression, solve_mean
from .fractions import solve_fraction
from .functions import (
    Definition,
    inline,
    parse_definition,
    parse_definitions,
    solve_function_node,
)
from .geometry import solve_segment, solve_segment_length
from .inequalities import solve_inequality
from .integrals import solve_integral
from .intervals import solve_interval
from .limits import solve_limit
from .matrices import solve_determinant, solve_matrix
from .methods import has_method_provider, methods_for
from .numeric import solve_numeric_equation
from .percentage import solve_percentage
from .piecewise import solve_piecewise
from .powers import solve_logarithm, solve_root
from .sequences import solve_sequence
from .series import solve_series
from .sets import solve_inclusion, solve_membership, solve_set_operation
from .sympy_bridge import from_sympy, to_sympy
from .systems import solve_system
from .trig_equations import Interval, solve_trig_equation
from .trigonometry import solve_angle_unit, solve_function
from .vertical import solve_vertical

# Ключ шага упрощения (общий с командой ``simplify``).
_KEY_SIMPLIFY = "simplify"


def solve(
    node: CoreNode,
    command: str | None = None,
    args: list[CoreNode] | None = None,
    interval: Interval | None = None,
    definitions: list[CoreNode] | None = None,
) -> CoreSolverData:
    """Решить выражение и вернуть ответ в формате контракта.

    ``command`` — имя действия (``CoreAction.command``): ``None`` или ``solve``
    решают как обычно, ``factor``/``expand``/``simplify`` и векторные команды
    применяют соответствующее преобразование (см. ``solver/commands.py``).
    ``args`` — аргументы команды (``CoreAction.args``), например второй вектор.
    ``interval`` — промежуток для отбора корней тригонометрического уравнения.

    ``definitions`` — определения функций (``f(x) = …``): вызовы ``f(…)``
    подменяются телом до решения. Определения живут только в пределах запроса,
    сервер остаётся без состояния.

    Бросает :class:`SolveError`, если задача не решается текущим набором
    модулей. Вызывающий сам решает, что показать пользователю: 404 с
    понятным текстом или 500.
    """
    definition = parse_definition(node)
    if definition is not None:
        # Само определение — это ответ, а не задача: показываем его как есть.
        result = SolveResult()
        result.add(Step(left=node, right=node, key="function"))
        result.set_solution(node)
        return build_solver_data(node, result)

    parsed_definitions: dict[str, Definition] = parse_definitions(definitions or [])
    original = node
    if parsed_definitions:
        node = inline(node, parsed_definitions)

    result = SolveResult()
    # Прямой вызов функции (``f(2)`` или ``f⁻¹(1)``) показываем отдельным
    # шагом, дальше решается уже подставленное выражение.
    if parsed_definitions and not node.structural_eq(original):
        if original.type is CoreNodeType.FUNCTION:
            argument = original.children[0] if original.children else CoreNode.empty()
            result.add(
                Step(
                    left=original,
                    right=node,
                    key="function_evaluate_value",
                    args=[argument],
                )
            )
        elif original.type is CoreNodeType.FUNCTION_INVERSE:
            result.add(Step(left=original, right=node, key="find_inverse"))
    ctx = SolveContext(result=result, variables=_free_variables(node))

    if command is not None and command != "solve":
        solution = commands.apply(command, node, ctx, args)
        result.set_solution(solution)
        return build_solver_data(node, result)

    if not ctx.variables and node.type in COMPARABLE:
        # Утверждение без переменных (``2 < 3``, ``2 = 2``) — не уравнение, а
        # сравнение: ответ «Истина»/«Ложь». С переменными работает неравенство.
        result.set_solution(solve_comparison(node, ctx))
        return build_solver_data(node, result)

    if node.type is CoreNodeType.EQUALS:
        if is_diff_equation(node):
            # y′/y″ в левой части вводит клавиатура напрямую, без команды:
            # такое равенство — дифференциальное уравнение, а не обычное.
            solution = diff_eq(node, ctx, [])
            result.set_solution(solution)
            return build_solver_data(node, result)
        abs_equation = solve_abs_equation(node, ctx.variables)
        if abs_equation is not None:
            return build_solver_data(node, abs_equation)
        trig = solve_trig_equation(node, ctx.variables, interval)
        if trig is not None:
            return build_solver_data(node, trig)
    # Способы решения — общий механизм: провайдеры по типу узла (уравнения,
    # системы, ...). Первый способ основной, остальные — альтернативы, между
    # которыми клиент переключается (`selectMethodText`).
    if has_method_provider(node.type):
        try:
            methods = methods_for(node, ctx.variables)
        except SolveError as error:
            # Аналитика не справилась (смешанные sin x = x, x^x = 2):
            # пробуем численный перебор корней.
            numeric = solve_numeric_equation(node, ctx.variables)
            if numeric is None:
                raise error
            return build_solver_data(node, numeric)
        if methods:
            return _with_methods(node, methods)

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
        folded = route(node, ctx)
    except SolveError as error:
        fallback = _simplify_fallback(node)
        if fallback is None:
            raise error
        return build_solver_data(node, fallback)
    if not result:
        # Вырожденный ввод — одно число без операций: шага нет, но ответ есть.
        result.set_solution(_constant_or_original(folded))
    else:
        # Ответ — значение, которое вернул маршрутизатор, а не последний шаг:
        # узел мог остаться несвёрнутым (``√(2+3)``), и шаг подвыражения не
        # должен подменять ответ (truth/07-open-questions.md, Q10).
        result.set_solution(folded)
    return build_solver_data(node, result)


def _with_methods(node: CoreNode, methods: list[SolveResult]) -> CoreSolverData:
    """Собрать ответ из способов решения: первый — основной, дальше — альтернативы.

    Альтернативы становятся отдельными записями вертикальной ветки, а подпись
    переключателя (`selectMethodText`) появляется, только если способ не один.
    """
    alternatives = methods[1:]
    return build_solver_data(
        node,
        methods[0],
        alternatives=alternatives,
        select_method_text="select_method" if alternatives else None,
    )


def _simplify_fallback(node: CoreNode) -> SolveResult | None:
    """Упростить символьное выражение, если обычный маршрут не справился.

    Запасной путь для тождеств и формул: арифметика не пропускает
    символьные операнды, поэтому ``sin²x + cos²x`` до неё не доходит. Для
    отношений (уравнений и неравенств) запасной путь молчит: «упрощение»
    ``sin x > x`` выдавало переписанное неравенство вместо ответа, а это
    обман пользователя. Возвращает результат с шагом «Упростить» или ``None``,
    если упрощение ничего не изменило — тогда важнее исходная ошибка.
    """
    if node.type in COMPARABLE:
        return None
    try:
        expression = to_sympy(node)
        simplified = sympy.simplify(expression)
        if simplified == expression:
            return None
        simplified_node = from_sympy(simplified)
    except (SolveError, TypeError, ValueError, AttributeError):
        # Узел не переводится в sympy (множества из чисел, мусорные слоты):
        # запасного пути нет, важнее исходная ошибка.
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


__all__ = [
    "SolveContext",
    "SolveError",
    "SolveResult",
    "Step",
    "registered_types",
    "route",
    "solve",
    "solve_abs_equation",
    "solve_add_subtract",
    "solve_angle_unit",
    "solve_arrangement",
    "solve_choose",
    "solve_comparison",
    "solve_complex",
    "solve_conditional",
    "solve_container",
    "solve_derivative",
    "solve_determinant",
    "solve_equation",
    "solve_evaluate_expression",
    "solve_factorial",
    "solve_fraction",
    "solve_function",
    "solve_function_node",
    "solve_inclusion",
    "solve_inequality",
    "solve_integral",
    "solve_interval",
    "solve_limit",
    "solve_logarithm",
    "solve_matrix",
    "solve_mean",
    "solve_membership",
    "solve_order",
    "solve_percentage",
    "solve_piecewise",
    "solve_root",
    "solve_segment",
    "solve_segment_length",
    "solve_sequence",
    "solve_series",
    "solve_set_operation",
    "solve_system",
    "solve_trig_equation",
    "solve_value_function",
    "solve_vertical",
    "solver_for",
]
