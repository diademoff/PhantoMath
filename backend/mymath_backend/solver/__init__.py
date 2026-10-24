"""Решатель: точка входа и маршрутизация по типам узлов.

Модули регистрируются декоратором :func:`~mymath_backend.solver.base.solver_for`
при импорте; :func:`solve` находит модуль по ``CoreNode.type`` и отдаёт
результат в формате контракта решателя.

Состав модулей расширяется по мере готовности: сейчас это арифметика.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType
from ..results import CoreSolverData
from . import commands
from . import complex_cards as _complex_cards  # noqa: F401  (registers the (a+i)(c-i) cards)
from .absolute import solve_abs_equation, solve_value_function
from .arithmetic import format_number
from .base import (
    SolveContext,
    SolveError,
    SolveResult,
    Step,
    UndefinedError,
    build_solver_data,
    division_by_zero,
    registered_types,
    route,
    solver_for,
    undefined_data,
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
from .matrices import (
    determinant_expansion,
    is_matrix_expression,
    lone_matrix_rows,
    matrix_expression,
    solve_determinant,
    solve_matrix,
)
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
from .trigonometry import angle_methods, pythagorean_identity, solve_angle_unit, solve_function
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

    «Не определено» (деление на ноль, факториал вне области, корень из
    отрицательного числа) ошибкой не считается: здесь, в единственной точке
    входа, сигнал превращается в ответ.
    """
    try:
        return _solve_inner(
            node, command=command, args=args, interval=interval, definitions=definitions
        )
    except UndefinedError as undefined:
        return undefined_data(node, undefined)
    except RecursionError as error:
        raise SolveError("слишком глубокое выражение") from error


def _solve_inner(
    node: CoreNode,
    command: str | None = None,
    args: list[CoreNode] | None = None,
    interval: Interval | None = None,
    definitions: list[CoreNode] | None = None,
) -> CoreSolverData:
    """Тело :func:`solve` (выделено ради перехвата глубины рекурсии)."""
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
        if command in {"to_degrees", "to_radians"}:
            methods = angle_methods(node, command)
            if methods is not None:
                return _with_methods(node, methods)
        solution = commands.apply(command, node, ctx, args)
        result.set_solution(solution)
        return build_solver_data(node, result)

    identity = pythagorean_identity(node, ctx)
    if identity is not None:
        result.set_solution(identity)
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
        if division_by_zero(node) is not None:
            # Неопределённая часть делает уравнение неопределённым целиком:
            # Решатель отвечает «Не определено» с пояснением div_with_zero.
            raise UndefinedError(
                "деление на ноль",
                "div_with_zero",
                explanation_args=[CoreNode.constant("0")],
            )
        abs_equation = solve_abs_equation(node, ctx.variables)
        if abs_equation is not None:
            return build_solver_data(node, abs_equation)
        trig = solve_trig_equation(node, ctx.variables, interval)
        if trig is not None:
            return build_solver_data(node, trig)
        expanded = _determinant_equation(node)
        if expanded is not None:
            return _solve_expanded_equation(node, expanded, ctx)
    if node.type is CoreNodeType.SYSTEM and is_diff_equation(node):
        # Задача Коши, набранная системой: {ODE, y(x₀) = y₀, y′(x₀) = y₁}.
        solution = diff_eq(node, ctx, [])
        result.set_solution(solution)
        return build_solver_data(node, result)
    # Способы решения — общий механизм: провайдеры по типу узла (уравнения,
    # системы, ...). Первый способ основной, остальные — альтернативы, между
    # которыми клиент переключается (`selectMethodText`).
    if has_method_provider(node.type):
        try:
            methods = methods_for(node, ctx.variables)
        except UndefinedError:
            raise  # «Не определено» — ответ, а не повод искать корни численно
        except SolveError as error:
            # Аналитика не справилась (смешанные sin x = x, x^x = 2):
            # пробуем численный перебор корней.
            numeric = solve_numeric_equation(node, ctx.variables)
            if numeric is None:
                raise error
            return build_solver_data(node, numeric)
        if methods:
            return _with_methods(node, methods)

    if is_matrix_expression(node):
        result.set_solution(matrix_expression(node, ctx))
        return build_solver_data(node, result)

    if contains_imaginary(node) and node.type not in (
        CoreNodeType.REAL,
        CoreNodeType.IMAGINARY,
        CoreNodeType.CONJUGATE,
    ):
        # Арифметику с мнимой единицей считает sympy: наше сворачивание к
        # числу её не знает. Re/Im/сопряжение отрабатывают свои модули.
        result.set_solution(solve_imaginary_arithmetic(node, ctx))
        return build_solver_data(node, result)

    if node.type is CoreNodeType.MATRIX and (lone := lone_matrix_rows(node, ctx)) is not None:
        result.set_solution(lone)
        return build_solver_data(node, result)

    try:
        folded = route(node, ctx)
    except UndefinedError:
        raise  # ответ «Не определено» известен; упрощать нечего
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
        # должен подменять ответ.
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


def _determinant_equation(node: CoreNode) -> CoreNode | None:
    """``det(…x…) = c`` or a bare square matrix with ``x``: the equation after expanding.

    Only a side that really is a square determinant/matrix with unknowns is
    opened; anything else keeps its own solver.
    """
    expanded = [determinant_expansion(child) for child in node.children]
    if all(item is None for item in expanded):
        return None
    sides = [
        item if item is not None else child
        for item, child in zip(expanded, node.children, strict=True)
    ]
    return CoreNode.node(CoreNodeType.EQUALS, *sides)


def _solve_expanded_equation(
    original: CoreNode, expanded: CoreNode, ctx: SolveContext
) -> CoreSolverData:
    """Show the opened determinant first, then solve the polynomial equation as usual."""
    ctx.result.add(Step(left=original, right=expanded, key="det_expand_equation"))
    if has_method_provider(expanded.type):
        try:
            methods = methods_for(expanded, ctx.variables)
        except SolveError:
            methods = []
        if methods and methods[0].solution is not None:
            ctx.result.extend(methods[0])
            ctx.result.set_solution(methods[0].solution)
            alternatives = methods[1:]
            return build_solver_data(
                original,
                ctx.result,
                alternatives=alternatives,
                select_method_text="select_method" if alternatives else None,
            )
    ctx.result.set_solution(solve_equation(expanded, ctx))
    return build_solver_data(original, ctx.result)


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
        derivative = any(
            n.type
            in (
                CoreNodeType.DERIVATION,
                CoreNodeType.DERIVATION1,
                CoreNodeType.DERIVATION1_DIFF,
                CoreNodeType.PRIME,
                CoreNodeType.DERIVATION1_PRIME,
                CoreNodeType.DERIVATION2_PRIME,
            )
            for n in node.walk()
        )
        constant_expression = (
            node.type
            in (
                CoreNodeType.ADD,
                CoreNodeType.SUBTRACT,
                CoreNodeType.MULTIPLY,
                CoreNodeType.MULTIPLY_IMPLICIT,
                CoreNodeType.DIVIDE,
                CoreNodeType.FRACTION,
                CoreNodeType.POWER,
                CoreNodeType.NEGATIVE,
                CoreNodeType.POSITIVE,
                CoreNodeType.BRACKET,
            )
            and expression.is_number is True
            and expression.is_real is True
            and expression.is_finite is True
            and any(
                (n.type is CoreNodeType.CONSTANT and n.value in ("π", "pi", "e"))
                or n.type in (CoreNodeType.ROOT2, CoreNodeType.ROOT)
                for n in node.walk()
            )
        )
        if simplified == expression and not derivative and not constant_expression:
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


# Letters that are constants, not unknowns. The phone's «e» key sends
# ``VARIABLE e``; differentiating by e or solving for it is never right.
_CONSTANT_NAMES = frozenset({"e", "π", "pi", "i", "∞"})


def _free_variables(node: CoreNode) -> list[str]:
    """Переменные, встречающиеся в выражении, в порядке появления."""
    seen: list[str] = []
    for n in node.walk():
        if (
            n.type.value == "VARIABLE"
            and n.value
            and n.value not in _CONSTANT_NAMES
            and n.value not in seen
        ):
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
