"""Тригонометрические уравнения.

Уравнение с одним неизвестным, в котором встречается прямая
тригонометрическая функция (``sin`` … ``csc``). Общее решение -- **серии**:
``x = π/6 + 2πk``, ``x = 5π/6 + 2πk``. Параметр серии -- переменная ``k``.
Если задан промежуток, из серий отбираются корни.

Сами серии строит sympy (``solveset``): это надёжно покрывает и одну
функцию с константой (``sin x = 1/2``), и функции с двух сторон
(``sin x = cos x``), и линейный аргумент (``sin 2x = 1/2``). Шаги описания
строятся нами: общее решение и отбор на промежутке.

Уравнение, которое ``solveset`` не берёт (или где больше одной переменной),
не считается тригонометрическим -- решение продолжается обычным путём.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveError, SolveResult, Step
from .sympy_bridge import from_sympy, to_sympy

_TRIG = frozenset({T.SIN, T.COS, T.TAN, T.COT, T.SEC, T.CSC})

_PARAMETER = "k"
"""Имя параметра серии: ``x = π/6 + 2πk``."""

_KEY_GENERAL = "trig_general_sol"
_KEY_INTERVAL = "trig_find_intervals_smpl"
_KEY_NO_SOLUTION = "false_statement_solve"
_KEY_INF_MANY = "solutions_inf_many"

_MAX_SERIES = 8
"""Потолок числа серий: защита от неожиданного множества решений."""

Interval = tuple[CoreNode, CoreNode]
"""Промежуток отбора корней: левая и правая границы."""


def looks_trigonometric(node: CoreNode) -> bool:
    """Есть ли в уравнении прямая тригонометрическая функция."""
    return any(child.type in _TRIG for child in node.walk())


def solve_trig_equation(
    node: CoreNode, variables: list[str], interval: Interval | None = None
) -> SolveResult | None:
    """Решить тригонометрическое уравнение или вернуть ``None``.

    ``None`` означает «это не наше уравнение»: мало переменных или
    ``solveset`` не справился. Тогда вызывающий решает обычным путём.
    """
    if len(variables) != 1 or not looks_trigonometric(node):
        return None

    var = variables[0]
    symbol = sympy.Symbol(var)
    lhs, rhs = node.children
    try:
        expression = to_sympy(lhs) - to_sympy(rhs)
        solution_set = sympy.solveset(expression, symbol, domain=sympy.S.Reals)
    except (SolveError, ValueError, TypeError):
        return None

    if solution_set is sympy.S.Reals:
        return _terminal(node, _KEY_INF_MANY)
    if solution_set is sympy.S.EmptySet:
        return _terminal(node, _KEY_NO_SOLUTION)

    series = _series(solution_set)
    if not series:
        return None

    general = _series_node(var, series)
    result = SolveResult()
    result.add(Step(left=node, right=None, key="trig_find_period"))
    result.add(Step(left=node, right=general, key=_KEY_GENERAL, args=[from_sympy(series[0][0])]))
    result.set_solution(general)

    selected = _select_interval(var, series, interval) if interval is not None else None
    if selected is not None:
        if selected:
            node_selected = selected[0] if len(selected) == 1 else CoreNode.node(T.LIST, *selected)
            result.add(
                Step(
                    left=general,
                    right=node_selected,
                    key=_KEY_INTERVAL,
                    args=[CoreNode.variable(var)],
                )
            )
            result.set_solution(node_selected)
        else:
            result.add(Step(left=general, right=None, key=_KEY_NO_SOLUTION))
            result.set_solution(CoreNode.empty())

    return result


def _terminal(node: CoreNode, key: str) -> SolveResult:
    """Ответ без узла: тождество или отсутствие решений."""
    result = SolveResult()
    result.add(Step(left=node, right=None, key=key))
    result.set_solution(CoreNode.empty())
    return result


def _series(solution_set: sympy.Set) -> list[tuple[sympy.Expr, sympy.Expr]]:
    """Разложить множество решений на серии ``(период, смещение)``."""
    images = solution_set.args if isinstance(solution_set, sympy.Union) else (solution_set,)
    if len(images) > _MAX_SERIES:
        return []

    series: list[tuple[sympy.Expr, sympy.Expr]] = []
    for image in images:
        if not isinstance(image, sympy.ImageSet):
            return []
        if len(image.lamda.variables) != 1:
            return []
        parameter = image.lamda.variables[0]
        expression = sympy.expand(image.lamda.expr)
        period = expression.coeff(parameter)
        if period == 0:
            return []
        offset = expression.subs(parameter, 0)
        if sympy.simplify(expression - (period * parameter + offset)) != 0:
            return []
        series.append((period, offset))
    series.sort(key=lambda pair: float(sympy.N(pair[1])))
    return series


def _series_node(var: str, series: list[tuple[sympy.Expr, sympy.Expr]]) -> CoreNode:
    """Узел общего решения: ``x = смещение + период·k`` (или список таких)."""
    parameter = sympy.Symbol(_PARAMETER)
    equations = []
    for period, offset in series:
        right = from_sympy(offset + period * parameter)
        equations.append(CoreNode.node(T.EQUALS, CoreNode.variable(var), right))
    if len(equations) == 1:
        return equations[0]
    return CoreNode.node(T.LIST, *equations)


def _select_interval(
    var: str, series: list[tuple[sympy.Expr, sympy.Expr]], interval: Interval
) -> list[CoreNode] | None:
    """Отобрать корни из серий на промежутке или ``None``, если он нечисловой."""
    low, high = to_sympy(interval[0]), to_sympy(interval[1])
    if not (low.is_number and high.is_number):
        return None

    values: list[sympy.Expr] = []
    for period, offset in series:
        first = int(sympy.floor((low - offset) / period))
        last = int(sympy.ceiling((high - offset) / period))
        for index in range(first, last + 1):
            value = offset + period * index
            if not (low <= value <= high):
                continue
            if not any(sympy.simplify(value - existing) == 0 for existing in values):
                values.append(value)

    values.sort(key=lambda value: float(sympy.N(value)))
    return [CoreNode.node(T.EQUALS, CoreNode.variable(var), from_sympy(value)) for value in values]


__all__ = [
    "Interval",
    "looks_trigonometric",
    "solve_trig_equation",
]
