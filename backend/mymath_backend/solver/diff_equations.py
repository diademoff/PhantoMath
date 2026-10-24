"""Дифференциальные уравнения (команда ``diff_eq``).

Уравнение — любое равенство с производной зависимой переменной (``y′``,
``y″``) в любой части и на любой глубине: ``y′ = f(x, y)``, ``x·y′ = y``,
``y″ − 3y′ + 2y = 0``. Производные записываются узлами ``PRIME``,
``DERIVATION1`` (клавиша ``d/dx``), ``DERIVATION1_PRIME``,
``DERIVATION2_PRIME`` и вложенным ``PRIME(PRIME(y))``. Порядок — старшая
производная в уравнении; зависимая переменная — та, от которой берётся
производная, независимая — вторая свободная переменная (по умолчанию ``x``).

Перед переводом в sympy переменная ``y`` заменяется функцией ``y(x)`` **на
обеих частях** и на любой глубине, поэтому ``y′`` справа больше не становится
единицей (``diff(y, y) = 1``): уравнение решается как ``Eq(lhs − rhs, 0)``.

Задача Коши приходит либо аргументами команды ``[x₀, y₀]`` (условие
``y(x₀) = y₀``), либо системой ``{system(ODE, y(x₀) = y₀, y′(x₀) = y₁)}``:
внутри системы ``y·(x₀)`` читается как ``y(x₀)``, а ``y′·(x₀)`` — как
``y′(x₀)``. Условий может быть от нуля до порядка уравнения.

Вид шага выбирается по классификации ``classify_ode`` в порядке учебника:
разделяющиеся переменные, точное уравнение (в полных дифференциалах),
однородное, линейное, Бернулли; для старших порядков — понижение порядка,
однородное уравнение с постоянными коэффициентами, частное решение по виду
правой части, иначе вариация постоянных.

Уравнение первого порядка показывает учебную карточку метода
(:mod:`ode_cards`): заголовок с названием метода, шаг «Решите уравнение» и
этапы-факты (``y = ux``, ``dy/y = x dx``) вместе с преобразованиями
``left → right``; каждое интегрирование несёт вложенную карточку интеграла.
Уравнение второго порядка показывает карточку :mod:`ode_second_cards`:
понижение порядка, характеристическое уравнение с тремя случаями корней,
специальную правую часть с резонансом или задачу Коши с системой для
постоянных.
Если карточку построить нельзя или её ответ не проходит ``checkodesol``,
остаётся прежний короткий ответ в два шага.

Ответ — ``y = …``, а если явного решения нет — неявное ``F(x, y) = C``.
Свободные постоянные называются как в задачнике: у уравнения первого
порядка ``C``, у уравнения порядка выше первого — ``C1``, ``C2``
(в приложении они рисуются как C₁, C₂). Логарифм независимой переменной
(или линейного выражения в ней) записывается с модулем: ``ln|x|``.
"""

from __future__ import annotations

import contextlib
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, SolveResult, Step
from .book_style import book_card, book_products
from .sympy_bridge import from_sympy, to_sympy

_FIRST_ORDER = (T.PRIME, T.DERIVATION1, T.DERIVATION1_PRIME)
_DERIVATIVE_TYPES = (*_FIRST_ORDER, T.DERIVATION2_PRIME)

_CONSTANT_NAMES = ("C", "C1", "C2", "C3")
"""Имена постоянных интегрирования: ``C`` у первого порядка, ``C1``/``C2``
у старших. Так их подписывает задачник (приложение рисует индексы)."""

_KIND_SEPARATION = "diff_eq_solve_by_separation"
_KIND_HOMOGENEOUS = "lesson_ode_homogeneous"
_KIND_LINEAR = "diff_eq_solve_linear"
_KIND_BERNOULLI = "diff_eq_solve_bernoulli_subs"
_KIND_EXACT = "lesson_ode_exact"
_KIND_REDUCTION = "diff_eq_solve_by_integration"
_KIND_REDUCIBLE = "lesson_ode_reduction_of_order"
_KIND_CONSTANT_HOMOGENEOUS = "lesson_ode_constant_coeff_homogeneous"
_KIND_CONSTANT_SPECIAL = "lesson_ode_constant_coeff_special"
_KIND_VARIATION = "lesson_ode_variation_of_constants"
_KIND_GENERAL = "diff_eq_solve"
_KIND_WITH_CONDITION = "lesson_ode_solution_with_condition"
_KIND_SINGULAR = "lesson_ode_singular_solution"

_DsolveHint = str | None
_HINTS: dict[str, _DsolveHint] = {
    _KIND_SEPARATION: "separable",
    _KIND_HOMOGENEOUS: None,
    _KIND_LINEAR: "1st_linear",
    _KIND_BERNOULLI: "Bernoulli",
    _KIND_REDUCTION: None,
    _KIND_REDUCIBLE: None,
    _KIND_CONSTANT_HOMOGENEOUS: "nth_linear_constant_coeff_homogeneous",
    _KIND_CONSTANT_SPECIAL: "nth_linear_constant_coeff_undetermined_coefficients",
    _KIND_VARIATION: "nth_linear_constant_coeff_variation_of_parameters",
    _KIND_GENERAL: None,
}

_DSOLVE_TIMEOUT = 20.0
"""Предел времени на один вызов ``sympy.dsolve``, секунд.

У ``dsolve`` нет собственного тайм-аута: «трудные» уравнения (маятник
``y'' = sin(y)``) вешают запрос навсегда. Превышение превращается в
``SolveError``; зависший поток sympy при этом остаётся жить до своего конца
(см. ``_dsolve_limited``).
"""


def diff_eq(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Решить дифференциальное уравнение (общее или частное решение)."""
    if node.type is T.SYSTEM:
        problem = _system_problem(node, ctx.variables)
        if problem is None:
            raise SolveError("система не является задачей Коши для уравнения")
        equation_node, dep, order, ind, conditions = problem
        xsym = sympy.Symbol(ind)
        equation = _sympy_equation(equation_node, dep, xsym)
        return _solve(equation, equation_node, dep, order, xsym, conditions, ctx)

    if node.type is not T.EQUALS or len(node.children) != 2:
        raise SolveError("дифференциальное уравнение — это равенство")
    lhs, rhs = node.children
    info = _equation_info(lhs, rhs, ctx.variables)
    if info is None:
        raise SolveError("в уравнении должна быть производная y′")
    dep, order, ind = info
    xsym = sympy.Symbol(ind)
    equation = _sympy_equation(node, dep, xsym)
    conditions = _command_conditions(args)
    return _solve(equation, node, dep, order, xsym, conditions, ctx)


def _solve(
    equation: sympy.Eq,
    problem: CoreNode,
    dep: str,
    order: int,
    xsym: sympy.Symbol,
    conditions: list[tuple[int, sympy.Expr, sympy.Expr, CoreNode, CoreNode]],
    ctx: SolveContext,
) -> CoreNode:
    """Общий ход: классификация, решение, шаги метода и ответа."""
    yfun = sympy.Function(dep)
    applied = yfun(xsym)
    kind, potential = _classification(equation, applied, xsym, order)

    if order >= 2:
        from .ode_second_cards import second_order_card

        card = second_order_card(problem, equation, dep, xsym, kind, conditions)
        if card is not None:
            return _show_card(ctx, *card)

    if order == 1:
        card = _first_order_card(problem, equation, dep, xsym.name, kind, conditions)
        if card is not None:
            return _show_card(ctx, *card)

    ctx.result.add(Step(left=problem, right=None, key=kind))

    if kind == _KIND_EXACT and potential is not None:
        answer = _exact_answer(potential, conditions, dep, xsym, applied)
        _add_condition_steps(ctx, conditions, dep, xsym.name)
        ctx.result.add(
            Step(
                left=problem,
                right=answer,
                key=(
                    "diff_eq_find_particular"
                    if conditions and _complete(conditions, order)
                    else _KIND_WITH_CONDITION
                    if conditions
                    else "diff_eq_write_general_sol"
                ),
            )
        )
        return answer

    ics = {_derivative_at(k, x0, applied, xsym): value for k, x0, value, _, _ in conditions}
    try:
        solution = _dsolve_with_fallback(equation, applied, ics or None, kind)
    except SolveError:
        raise
    except (NotImplementedError, TypeError, ValueError) as error:
        raise SolveError("уравнение не решается") from error

    answer = _solution_node(solution, dep, xsym, order)
    _add_condition_steps(ctx, conditions, dep, xsym.name)
    ctx.result.add(
        Step(
            left=problem,
            right=answer,
            key=(
                "diff_eq_find_particular"
                if _complete(conditions, order)
                else _KIND_WITH_CONDITION
                if conditions
                else "diff_eq_write_general_sol"
            ),
        )
    )
    if not conditions:
        singular = _singular_solution(equation, applied, dep, xsym, kind, answer)
        if singular:
            ctx.result.add(Step(left=singular, right=None, key=_KIND_SINGULAR))
    return answer


def _show_card(ctx: SolveContext, header: str, result: SolveResult, answer: CoreNode) -> CoreNode:
    """The card of a method, its formulas written as in the book."""
    book_card(result)
    answer = book_products(answer) or answer
    ctx.result.header = header
    ctx.result.extend(result)
    ctx.result.set_solution(answer)
    return answer


def _complete(
    conditions: list[tuple[int, sympy.Expr, sympy.Expr, CoreNode, CoreNode]], order: int
) -> bool:
    """Все условия задачи Коши заданы (порядок уравнения покрыт)."""
    return len(conditions) >= order


def _first_order_card(
    problem: CoreNode,
    equation: sympy.Eq,
    dep: str,
    ind: str,
    kind: str,
    conditions: list[tuple[int, sympy.Expr, sympy.Expr, CoreNode, CoreNode]],
) -> tuple[str, SolveResult, CoreNode] | None:
    """Учебная карточка метода для уравнения первого порядка (или ``None``)."""
    from .ode_cards import first_order_card

    return first_order_card(problem, equation, dep, ind, kind, conditions)


def _add_condition_steps(
    ctx: SolveContext,
    conditions: list[tuple[int, sympy.Expr, sympy.Expr, CoreNode, CoreNode]],
    dep: str,
    ind: str,
) -> None:
    """Показать каждое начальное условие отдельным шагом."""
    for derivative_order, _, _, x_zero_node, y_zero_node in conditions:
        condition = CoreNode.node(
            T.EVALUATE_EXPRESSION,
            _derivative_node(derivative_order, dep),
            x_zero_node,
        )
        ctx.result.add(
            Step(
                left=None,
                right=None,
                key="diff_eq_use_init_condition",
                args=[
                    condition,
                    y_zero_node,
                    _derivative_node(derivative_order, dep),
                    x_zero_node,
                    CoreNode.variable(ind),
                ],
            )
        )


def _derivative_node(order: int, dep: str) -> CoreNode:
    """Узел производной порядка ``order`` от переменной ``dep``."""
    if order >= 2:
        return CoreNode.node(T.DERIVATION2_PRIME, CoreNode.variable(dep))
    if order == 1:
        return CoreNode.node(T.PRIME, CoreNode.variable(dep))
    return CoreNode.variable(dep)


def _command_conditions(
    args: list[CoreNode],
) -> list[tuple[int, sympy.Expr, sympy.Expr, CoreNode, CoreNode]]:
    """Условия из аргументов команды: ``[x₀, y₀]`` — это ``y(x₀) = y₀``."""
    if not args:
        return []
    if len(args) != 2:
        raise SolveError("начальное условие задаётся парой (x₀, y₀)")
    x_zero, y_zero = args
    return [(0, _number(x_zero), _number(y_zero), x_zero, y_zero)]


def _derivative_at(
    order: int, point: sympy.Expr, function: sympy.AppliedUndef, xsym: sympy.Symbol
) -> sympy.Basic:
    """``y(x₀)``, ``y′(x₀)``, … в виде ключа для ``dsolve(ics=…)``."""
    if order == 0:
        return function.subs(xsym, point)
    return sympy.Derivative(function, (xsym, order)).subs(xsym, point)


def _dsolve_with_fallback(
    equation: sympy.Eq,
    function: sympy.AppliedUndef,
    ics: dict[sympy.Basic, sympy.Expr] | None,
    kind: str,
) -> sympy.Basic | list[sympy.Basic]:
    """``dsolve`` с подсказкой по методу; при несовпадении — общий вызов."""
    hint = _HINTS.get(kind)
    try:
        return _dsolve_limited(equation, function, ics, hint)
    except (NotImplementedError, TypeError, ValueError) as error:
        if hint is None:
            raise SolveError("уравнение не решается") from error
        try:
            return _dsolve_limited(equation, function, ics, None)
        except (NotImplementedError, TypeError, ValueError) as second:
            raise SolveError("уравнение не решается") from second


def _dsolve_limited(
    equation: sympy.Eq,
    func: sympy.AppliedUndef,
    ics: dict[sympy.Basic, sympy.Expr] | None = None,
    hint: _DsolveHint = None,
) -> sympy.Basic | list[sympy.Basic]:
    """Вызвать ``sympy.dsolve`` с дедлайном.

    Превышение ``_DSOLVE_TIMEOUT`` превращается в ``SolveError`` вместо
    вечного зависания. Остановить поток sympy нельзя (``shutdown`` только
    перестаёт его ждать), поэтому зависший вызов продолжает жечь CPU в фоне
    до своего конца — это осознанная плата за живой запрос.
    """
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        kwargs: dict[str, object] = {"ics": ics}
        if hint is not None:
            kwargs["hint"] = hint
        future = pool.submit(sympy.dsolve, equation, func, **kwargs)
        try:
            return future.result(timeout=_DSOLVE_TIMEOUT)
        except FuturesTimeoutError as error:
            raise SolveError("уравнение не решается") from error
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _equations_of(node: CoreNode) -> list[CoreNode]:
    """Равенства внутри узла: само уравнение или строки системы."""
    if node.type is T.SYSTEM:
        return [child for child in node.children if child.type is T.EQUALS]
    if node.type is T.EQUALS:
        return [node]
    return []


def _variables(node: CoreNode) -> list[str]:
    """Свободные переменные в порядке появления (как ``_free_variables``)."""
    constants = frozenset({"e", "π", "pi", "i", "∞"})
    seen: list[str] = []
    for item in node.walk():
        if (
            item.type is T.VARIABLE
            and item.value
            and item.value not in constants
            and item.value not in seen
        ):
            seen.append(item.value)
    return seen


def _independent(variables: list[str], dep: str) -> str:
    """Независимая переменная — первая свободная, кроме зависимой."""
    return next((name for name in variables if name != dep), "x")


def _dependent_of(node: CoreNode) -> str | None:
    """Имя переменной под производной (в том числе вложенной)."""
    current = node
    while current.type in _DERIVATIVE_TYPES and current.children:
        current = current.children[0]
    if current.type is T.VARIABLE and current.value:
        return current.value
    if current.type is T.FUNCTION and current.value:
        return current.value
    return None


def _derivative_order(node: CoreNode) -> int | None:
    """Порядок производного узла; ``PRIME(PRIME(y))`` — второй."""
    if node.type is T.DERIVATION2_PRIME:
        order = 2
    elif node.type in _FIRST_ORDER:
        order = 1
    else:
        return None
    if node.children:
        nested = _derivative_order(node.children[0])
        if nested is not None:
            order += nested
    return order


def _equation_info(
    lhs: CoreNode, rhs: CoreNode, variables: list[str] | None = None
) -> tuple[str, int, str] | None:
    """``(зависимая, порядок, независимая)`` или ``None``, если производной нет."""
    sides = [lhs, rhs]
    derivatives = [item for side in sides for item in side.walk() if item.type in _DERIVATIVE_TYPES]
    if not derivatives:
        return None
    dep = next(
        (name for name in (_dependent_of(item) for item in derivatives) if name),
        None,
    )
    if dep is None:
        return None
    order = max(
        value for value in (_derivative_order(item) for item in derivatives) if value is not None
    )
    names = variables if variables else _variables(lhs) + _variables(rhs)
    ind = _independent(names, dep)
    return dep, order, ind


def _substitute_function(node: CoreNode, dep: str, ind: str) -> CoreNode:
    """Заменить ``y`` функцией ``y(x)`` до перевода в sympy.

    Так ``PRIME(y)`` и ``PRIME(PRIME(y))`` считаются производными функции,
    а не производными символа (``diff(y, y) = 1``). Замена идёт на обеих
    частях уравнения, на любой глубине.
    """
    if node.type is T.VARIABLE and node.value == dep:
        return CoreNode(
            type=T.FUNCTION,
            value=dep,
            children=[CoreNode.variable(ind)],
        )
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[_substitute_function(child, dep, ind) for child in node.children],
    )


def _sympy_equation(problem: CoreNode, dep: str, xsym: sympy.Symbol) -> sympy.Eq:
    """``Eq(lhs − rhs, 0)`` с ``y``, заменённым на ``y(x)``.

    Знаменатели здесь не сокращаются: ``dsolve`` сам приводит уравнение к
    удобному виду, а умножение на знаменатель портит уравнения с ``e^{kx}``.
    Точное уравнение распознаётся отдельно, по форме ``M dx + N dy = 0``
    (см. ``_exact_potential``).
    """
    if problem.type is T.SYSTEM:
        problem = next(
            child
            for child in problem.children
            if child.type is T.EQUALS
            and _equation_info(child.children[0], child.children[1]) is not None
        )
    lhs, rhs = problem.children
    try:
        left = to_sympy(_substitute_function(lhs, dep, xsym.name))
        right = to_sympy(_substitute_function(rhs, dep, xsym.name))
    except SolveError as error:
        raise SolveError("уравнение не выражается") from error
    return sympy.Eq(left - right, 0)


def is_diff_equation(node: CoreNode) -> bool:
    """Уравнение с производной зависимой переменной в любой части.

    Сюда же относится задача Коши, записанная системой: одна строка —
    уравнение, остальные — условия ``y(x₀) = y₀`` / ``y′(x₀) = y₁``.
    """
    if node.type is T.EQUALS and len(node.children) == 2:
        return _equation_info(node.children[0], node.children[1]) is not None
    if node.type is T.SYSTEM:
        return _system_problem(node, None) is not None
    return False


def _condition_parts(row: CoreNode, dep: str) -> tuple[int, sympy.Expr, CoreNode, CoreNode] | None:
    """Разобрать условие ``y(x₀) = y₀`` / ``y′(x₀) = y₁``.

    Редактор присылает ``y(0)`` неявным произведением ``y·(0)``; здесь
    читаются и эта форма, и ``EVALUATE_EXPRESSION``, и произведение
    ``y′·(x₀)``. Возвращает порядок производной, точку, узел точки и узел
    значения.
    """
    if row.type is not T.EQUALS or len(row.children) != 2:
        return None
    lhs, rhs = row.children
    try:
        point_order = _condition_point(lhs, dep)
    except SolveError:
        return None
    if point_order is None:
        return None
    derivative_order, x_zero_node, _point = point_order
    try:
        value = _number(rhs)
    except SolveError:
        return None
    return derivative_order, value, x_zero_node, rhs


def _condition_point(lhs: CoreNode, dep: str) -> tuple[int, CoreNode, sympy.Expr] | None:
    """Порядок производной и точка из левой части условия."""
    if lhs.type is T.EVALUATE_EXPRESSION and len(lhs.children) == 2:
        part, x_zero = lhs.children
        order = _condition_order(part, dep)
        if order is None:
            return None
        return order, x_zero, _number(x_zero)
    if lhs.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) and len(lhs.children) == 2:
        first, second = lhs.children
        bracket = _bracket_of(first)
        part = second
        if bracket is None:
            bracket = _bracket_of(second)
            part = first
        if bracket is None:
            return None
        order = _condition_order(part, dep)
        if order is None:
            return None
        return order, bracket, _number(bracket)
    if lhs.type in _DERIVATIVE_TYPES and len(lhs.children) == 1:
        inner = lhs.children[0]
        bracket = _bracket_of(inner)
        if bracket is not None and _condition_order(inner, dep) is not None:
            # ``(y·(x₀))′`` — производная всей подстановки.
            return _derivative_order(lhs) or 1, bracket, _number(bracket)
    if lhs.type is T.FUNCTION and lhs.value == dep and len(lhs.children) == 1:
        x_zero = lhs.children[0]
        return 0, x_zero, _number(x_zero)
    return None


def _bracket_of(node: CoreNode) -> CoreNode | None:
    """Точка в скобках: ``(x₀)`` как ``BRACKET``."""
    if node.type is T.BRACKET and len(node.children) == 1:
        return node.children[0]
    return None


def _condition_order(part: CoreNode, dep: str) -> int | None:
    """Порядок производной в левой части условия (``y`` — нулевой)."""
    if part.type is T.VARIABLE and part.value == dep:
        return 0
    if part.type is T.FUNCTION and part.value == dep:
        return 0
    if part.type in _DERIVATIVE_TYPES and _dependent_of(part) == dep:
        return _derivative_order(part)
    return None


def _is_condition_row(row: CoreNode) -> bool:
    """Похожа ли строка системы на ``y(x₀) = y₀`` / ``y′(x₀) = y₁``."""
    if row.type is not T.EQUALS or len(row.children) != 2:
        return False
    lhs = row.children[0]
    if lhs.type is T.EVALUATE_EXPRESSION and len(lhs.children) == 2:
        return True
    if lhs.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) and len(lhs.children) == 2:
        return _bracket_of(lhs.children[0]) is not None or _bracket_of(lhs.children[1]) is not None
    if lhs.type in _DERIVATIVE_TYPES and len(lhs.children) == 1:
        child = lhs.children[0]
        return child.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) and any(
            _bracket_of(item) is not None for item in child.children
        )
    return lhs.type is T.FUNCTION and len(lhs.children) == 1


def _system_problem(
    node: CoreNode, variables: list[str] | None
) -> (
    tuple[
        CoreNode,
        str,
        int,
        str,
        list[tuple[int, sympy.Expr, sympy.Expr, CoreNode, CoreNode]],
    ]
    | None
):
    """Разобрать систему ``{ODE, y(x₀)=y₀, …}``.

    Уравнение должно быть одно, а остальные строки — условия для той же
    зависимой переменной. Общие системы дифференциальных уравнений сюда не
    относятся.
    """
    rows = list(node.children)
    if len(rows) < 2 or any(row.type is not T.EQUALS for row in rows):
        return None

    condition_rows = [row for row in rows if _is_condition_row(row)]
    if condition_rows and len(condition_rows) == len(rows):
        return None
    ode_rows = [row for row in rows if row not in condition_rows]
    if len(ode_rows) != 1:
        return None
    ode = ode_rows[0]
    info = _equation_info(ode.children[0], ode.children[1], variables)
    if info is None:
        return None
    dep, order, ind = info
    conditions: list[tuple[int, sympy.Expr, sympy.Expr, CoreNode, CoreNode]] = []
    for row in condition_rows:
        parts = _condition_parts(row, dep)
        if parts is None:
            return None
        derivative_order, value, x_zero_node, y_zero_node = parts
        if derivative_order >= order or derivative_order < 0:
            return None
        conditions.append((derivative_order, _number(x_zero_node), value, x_zero_node, y_zero_node))
    if len(conditions) > order:
        return None
    return ode, dep, order, ind, conditions


def _hints(equation: sympy.Eq, function: sympy.AppliedUndef) -> set[str]:
    """Подсказки ``classify_ode`` (пустое множество при отказе)."""
    try:
        return set(sympy.classify_ode(equation, function))
    except (NotImplementedError, TypeError, ValueError):
        return set()


def _classification(
    equation: sympy.Eq, function: sympy.AppliedUndef, xsym: sympy.Symbol, order: int
) -> tuple[str, sympy.Expr | None]:
    """Ключ метода и (для точного уравнения) потенциал."""
    hints = _hints(equation, function)
    if order == 1:
        if "separable" in hints:
            return _KIND_SEPARATION, None
        # Точное уравнение распознаём по форме M dx + N dy = 0: sympy видит
        # его и как однородное, а общий dsolve на нём может зависнуть (#13).
        potential = _exact_potential(equation, xsym, function)
        if potential is not None:
            return _KIND_EXACT, potential
        if any(hint.startswith("1st_homogeneous_coeff") for hint in hints):
            return _KIND_HOMOGENEOUS, None
        if "1st_linear" in hints:
            return _KIND_LINEAR, None
        if "Bernoulli" in hints:
            return _KIND_BERNOULLI, None
        if "1st_exact" in hints:
            return _KIND_EXACT, None
        return _KIND_GENERAL, None

    if "nth_algebraic" in hints:
        # ``y″ = f(x)``: порядок понижается двукратным интегрированием.
        return _KIND_REDUCTION, None
    if any(hint.startswith(("nth_order_reducible", "Liouville")) for hint in hints):
        return _KIND_REDUCIBLE, None
    if "nth_linear_constant_coeff_homogeneous" in hints:
        return _KIND_CONSTANT_HOMOGENEOUS, None
    if "nth_linear_constant_coeff_undetermined_coefficients" in hints:
        return _KIND_CONSTANT_SPECIAL, None
    if "nth_linear_constant_coeff_variation_of_parameters" in hints:
        return _KIND_VARIATION, None
    return _KIND_GENERAL, None


def _exact_potential(
    equation: sympy.Eq, xsym: sympy.Symbol, function: sympy.AppliedUndef
) -> sympy.Expr | None:
    """Потенциал ``F(x, y)`` точного уравнения ``M dx + N dy = 0``.

    Возвращает ``None``, если уравнение не точное. Потенциал считается
    напрямую (``∫M dx + ∫(N − ∂/∂y∫M dx) dy``), потому что ``dsolve``
    с подсказкой ``1st_exact`` на рациональной записи не укладывается в
    дедлайн (#13).
    """
    expression = sympy.together(equation.lhs - equation.rhs)
    numerator, _ = sympy.fraction(expression)
    ysym = sympy.Symbol("_y_exact")
    derivative = sympy.Derivative(function, xsym)
    try:
        m_part = sympy.simplify(numerator.subs(derivative, 0).subs(function, ysym))
        n_part = sympy.simplify(numerator.diff(derivative).subs(function, ysym))
        if m_part == 0 or n_part == 0:
            return None
        difference = sympy.simplify(sympy.diff(m_part, ysym) - sympy.diff(n_part, xsym))
        if difference != 0:
            return None
        first = sympy.integrate(m_part, xsym)
        remainder = sympy.simplify(n_part - sympy.diff(first, ysym))
        if remainder.has(xsym) or first.has(sympy.Integral) or remainder.has(sympy.Integral):
            return None
        second = sympy.integrate(remainder, ysym)
        if second.has(sympy.Integral):
            return None
        potential = sympy.simplify(first + second)
    except (NotImplementedError, TypeError, ValueError):
        return None
    if potential.could_extract_minus_sign():
        potential = -potential
    return potential.subs(ysym, function)


def _real_branches(equations: list[sympy.Basic]) -> list[sympy.Basic]:
    """Убрать ветви с мнимой единицей, если есть действительная.

    ``dsolve`` для ``y′ = y/x + x/y`` возвращает три кубические ветви, две из
    них комплексные; в ответе нужна действительная.
    """
    real = [entry for entry in equations if not entry.has(sympy.I)]
    return real or equations


def _solution_node(
    solution: sympy.Basic | list[sympy.Basic], dep: str, xsym: sympy.Symbol, order: int
) -> CoreNode:
    """Ответ из результата ``dsolve`` (явный ``y = …`` или неявный)."""
    equations = solution if isinstance(solution, list) else [solution]
    equations = _real_branches(equations)
    nodes: list[CoreNode] = []
    for entry in equations:
        if isinstance(entry, sympy.Eq):
            left, right = entry.lhs, entry.rhs
        else:
            left, right = sympy.Function(dep)(xsym), entry
        if left == sympy.Function(dep)(xsym) or left == sympy.Symbol(dep):
            cleaned = _clean_expression(right, xsym, order)
            nodes.append(CoreNode.node(T.EQUALS, CoreNode.variable(dep), from_sympy(cleaned)))
            continue
        # Неявное решение: ``F(x, y) = C``; ``y(x)`` рисуем как ``y``.
        left_expr = _clean_expression(left, xsym, order).subs(
            sympy.Function(dep)(xsym), sympy.Symbol(dep)
        )
        right_expr = _clean_expression(right, xsym, order)
        nodes.append(CoreNode.node(T.EQUALS, from_sympy(left_expr), from_sympy(right_expr)))
    if len(nodes) == 1:
        return nodes[0]
    return CoreNode.node(T.LIST, *nodes)


def _exact_answer(
    potential: sympy.Expr,
    conditions: list[tuple[int, sympy.Expr, sympy.Expr, CoreNode, CoreNode]],
    dep: str,
    xsym: sympy.Symbol,
    function: sympy.AppliedUndef,
) -> CoreNode:
    """Неявный ответ ``F(x, y) = C`` (или ``= F(x₀, y₀)`` для Коши)."""
    if conditions:
        _, x_zero, y_zero, _, _ = conditions[0]
        value = sympy.simplify(
            potential.subs(xsym, x_zero).subs(function.subs(xsym, x_zero), y_zero)
        )
    else:
        value = sympy.Symbol("C")
    left = _clean_expression(potential, xsym, 1).subs(function, sympy.Symbol(dep))
    right = _clean_expression(value, xsym, 1)
    return CoreNode.node(T.EQUALS, from_sympy(left), from_sympy(right))


def _clean_expression(expression: sympy.Expr, xsym: sympy.Symbol, order: int) -> sympy.Expr:
    """Привести форму ответа к учебной и переименовать постоянные."""
    expression = sympy.sympify(expression)
    if order <= 1:
        expression = expression.subs(sympy.Symbol("C1"), sympy.Symbol(_CONSTANT_NAMES[0]))
    with contextlib.suppress(NotImplementedError, TypeError, ValueError):
        expression = sympy.simplify(expression)
        expression = sympy.trigsimp(expression)
    expression = _real_root_ratio(expression)
    with contextlib.suppress(NotImplementedError, TypeError, ValueError):
        expression = sympy.simplify(expression)
    return _abs_logs(expression, xsym)


def _real_root_ratio(expression: sympy.Expr) -> sympy.Expr:
    """Убрать мнимую на вид пару ``√A/√B``: ``√A/√B = A/√(AB)``.

    Для ``y′·cos x = y`` это превращает ``√(sin x+1)/√(sin x−1)`` в
    ``(1+sin x)/cos x`` (ответ ``C(tg x + sec x)``).
    """
    if not isinstance(expression, sympy.Mul):
        return expression
    if not any(symbol.name.startswith("C") for symbol in expression.free_symbols):
        return expression
    factors = list(expression.args)
    tops = [
        item for item in factors if isinstance(item, sympy.Pow) and item.exp == sympy.Rational(1, 2)
    ]
    bottoms = [
        item
        for item in factors
        if isinstance(item, sympy.Pow) and item.exp == sympy.Rational(-1, 2)
    ]
    for top in tops:
        for bottom in bottoms:
            a_part = top.args[0]
            b_part = bottom.base
            for candidate_b in (b_part, -b_part):
                product = sympy.simplify(a_part * candidate_b)
                if not (isinstance(product, sympy.Pow) and product.exp == 2):
                    continue
                rest = factors.copy()
                rest.remove(top)
                rest.remove(bottom)
                candidate = sympy.Mul(*rest) * a_part / sympy.sqrt(product)
                return sympy.powdenest(candidate, force=True)
    return expression


def _abs_logs(expression: sympy.Expr, xsym: sympy.Symbol) -> sympy.Expr:
    """``ln x`` -> ``ln|x|``, когда аргумент — ``x`` или линейное по ``x``."""
    for logarithm in sorted(expression.atoms(sympy.log), key=str):
        if len(logarithm.args) != 1:
            continue
        argument = logarithm.args[0]
        if argument == xsym or _linear_in(argument, xsym):
            expression = expression.subs(logarithm, sympy.log(sympy.Abs(argument)))
    return expression


def _linear_in(expression: sympy.Expr, xsym: sympy.Symbol) -> bool:
    """Выражение линейно по ``xsym`` и не содержит других переменных."""
    if expression.free_symbols - {xsym}:
        return False
    try:
        return bool(sympy.Poly(expression, xsym).degree() == 1)
    except sympy.PolynomialError:
        return False


def _singular_solution(
    equation: sympy.Eq,
    function: sympy.AppliedUndef,
    dep: str,
    xsym: sympy.Symbol,
    kind: str,
    answer: CoreNode,
) -> CoreNode | None:
    """Найти потерянное особое решение ``y = 0``.

    При разделении переменных и в уравнении Бернулли делят на ``y``; если
    ``y = 0`` решает уравнение и не получается из общего решения ни при
    каком значении постоянной, его показывают отдельно (#10).
    """
    if kind not in (_KIND_SEPARATION, _KIND_BERNOULLI):
        return None
    try:
        if sympy.simplify(equation.lhs.subs(function, 0)) != 0:
            return None
    except (TypeError, ValueError, NotImplementedError):
        return None
    if _zero_reachable(answer):
        return None
    return CoreNode.node(T.EQUALS, CoreNode.variable(dep), CoreNode.constant("0"))


def _zero_reachable(answer: CoreNode) -> bool:
    """Получается ли ``y = 0`` из семейства при нулевых постоянных."""
    branches = answer.children if answer.type is T.LIST else [answer]
    for branch in branches:
        if branch.type is not T.EQUALS:
            continue
        try:
            right = to_sympy(branch.children[1])
        except SolveError:
            continue
        constants = [symbol for symbol in right.free_symbols if symbol.name.startswith("C")]
        if not constants:
            continue
        try:
            if sympy.simplify(right.subs({symbol: 0 for symbol in constants})) == 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _number(node: CoreNode) -> sympy.Expr:
    """Число из узла (точка или значение начального условия)."""
    value = to_sympy(node)
    if value.is_number is not True:
        raise SolveError("начальное условие должно быть числом")
    return value


__all__ = [
    "diff_eq",
    "is_diff_equation",
]
