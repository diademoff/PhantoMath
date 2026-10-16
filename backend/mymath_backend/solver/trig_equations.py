"""Тригонометрические уравнения.

Уравнение с одним неизвестным, в котором встречается прямая
тригонометрическая функция (``sin`` … ``csc``). Общее решение -- **серии**:
``x = π/6 + 2πk``, ``x = 5π/6 + 2πk``. Параметр серии -- переменная ``k``.
Если задан промежуток, из серий отбираются корни.

Сами серии строит sympy (``solveset``): это надёжно покрывает и одну
функцию с константой (``sin x = 1/2``), и функции с двух сторон
(``sin x = cos x``), и линейный аргумент (``sin 2x = 1/2``). Буквы, кроме
неизвестной, считаются параметрами: ``sin x = a`` даёт серии с ``asin(a)``
(``solveset`` прячет их за ``ConditionSet`` -- условие по параметру мы
снимаем, решение по ``x`` остаётся). Шаги описания строятся нами: общее
решение и отбор на промежутке.

Серии бывают и нелинейны по параметру (``sin(x²) = 0`` -> ``x = ±√(πk)``):
такие записываются как есть, формулой от ``k``.

Уравнение, которое ``solveset`` не берёт вовсе (``sin x = x`` -- там
``ConditionSet`` по самому неизвестному), не считается тригонометрическим:
решение продолжается обычным путём и попадает в численный модуль.
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

_MAX_SERIES = 32
"""Потолок числа серий: защита от неожиданного множества решений."""

_MAX_PARAMETER = 64
"""Диапазон перебора параметра при нелинейных сериях и отборе корней."""

Interval = tuple[CoreNode, CoreNode]
"""Промежуток отбора корней: левая и правая границы."""

Family = tuple[sympy.Expr, sympy.Expr]
"""Одна серия: выражение от параметра и сам параметр."""


def looks_trigonometric(node: CoreNode) -> bool:
    """Есть ли в уравнении прямая тригонометрическая функция."""
    return any(child.type in _TRIG for child in node.walk())


def unknown_of(node: CoreNode, variables: list[str]) -> str | None:
    """Неизвестное тригонометрического уравнения.

    Это переменная внутри тригонометрической функции; остальные буквы --
    параметры. Если внутри несколько разных букв (``sin x = cos y``),
    неизвестным становится та, что встречается в аргументах чаще; при равных
    счётах предпочтение ``x``, затем -- первая по порядку появления.
    """
    counts: dict[str, int] = {}
    for child in node.walk():
        if child.type not in _TRIG:
            continue
        for deeper in child.walk():
            if deeper.type is T.VARIABLE and deeper.value in variables:
                counts[deeper.value] = counts.get(deeper.value, 0) + 1
    if not counts:
        return None
    best = max(counts.values())
    top = [name for name, count in counts.items() if count == best]
    return "x" if "x" in top else top[0]


def solve_trig_equation(
    node: CoreNode, variables: list[str], interval: Interval | None = None
) -> SolveResult | None:
    """Решить тригонометрическое уравнение или вернуть ``None``.

    ``None`` означает «это не наше уравнение»: нет единственного
    неизвестного внутри тригонометрической функции или ``solveset`` не
    справился. Тогда вызывающий решает обычным путём.
    """
    var = unknown_of(node, variables)
    if var is None or not looks_trigonometric(node):
        return None

    symbol = sympy.Symbol(var)
    lhs, rhs = node.children
    try:
        expression = to_sympy(lhs) - to_sympy(rhs)
        solution_set = sympy.solveset(expression, symbol, domain=sympy.S.Reals)
    except (SolveError, ValueError, TypeError):
        return None

    solution_set = _unwrap(solution_set, symbol)
    if solution_set is sympy.S.Reals:
        return _terminal(node, _KEY_INF_MANY)
    if solution_set is sympy.S.EmptySet:
        return _terminal(node, _KEY_NO_SOLUTION)

    families = _families(solution_set)
    if not families:
        return None

    series = [_linear(expression, parameter) for expression, parameter in families]
    if all(item is not None for item in series):
        ordered = sorted([item for item in series if item is not None], key=_series_sort_key)
        general = _series_node(var, ordered)
        # Аргумент «Запишите общее решение, используя ARG1» -- период серии.
        general_arg = from_sympy(ordered[0][0])
        selected = _select_interval(var, ordered, interval) if interval is not None else None
    else:
        general = _raw_node(var, families)
        first = sorted(families, key=_family_sort_key)[0]
        general_arg = from_sympy(_at_zero(first))
        selected = _select_raw(var, families, interval) if interval is not None else None

    result = SolveResult()
    result.add(Step(left=node, right=None, key="trig_find_period"))
    result.add(Step(left=node, right=general, key=_KEY_GENERAL, args=[general_arg]))
    result.set_solution(general)

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


def _unwrap(solution_set: sympy.Set, symbol: sympy.Symbol) -> sympy.Set:
    """Снять ограничения по параметрам: ``ConditionSet`` и ``Intersection``.

    ``ConditionSet`` с условием, не зависящим от неизвестного, -- это то же
    множество решений с оговоркой про параметры (``sin x = a`` требует
    ``|a| <= 1``): берём базовое множество. ``Intersection`` с ``Reals``
    размыкаем в ``FiniteSet`` из решений с параметрами.
    """
    if isinstance(solution_set, sympy.ConditionSet):
        if symbol in solution_set.condition.free_symbols:
            return solution_set
        return _unwrap(solution_set.base_set, symbol)
    if isinstance(solution_set, sympy.Intersection):
        parts = [part for part in solution_set.args if part is not sympy.S.Reals]
        if len(parts) == 1:
            return _unwrap(parts[0], symbol)
    return solution_set


def _terminal(node: CoreNode, key: str) -> SolveResult:
    """Ответ без узла: тождество или отсутствие решений."""
    result = SolveResult()
    result.add(Step(left=node, right=None, key=key))
    result.set_solution(CoreNode.empty())
    return result


def _families(solution_set: sympy.Set) -> list[tuple[sympy.Expr, sympy.Expr]]:
    """Разложить множество решений на серии ``(выражение, параметр)``."""
    images = solution_set.args if isinstance(solution_set, sympy.Union) else (solution_set,)
    if len(images) > _MAX_SERIES:
        return []

    families: list[tuple[sympy.Expr, sympy.Expr]] = []
    for image in images:
        if not isinstance(image, sympy.ImageSet):
            return []
        if len(image.lamda.variables) != 1:
            return []
        parameter = image.lamda.variables[0]
        families.append((sympy.expand(image.lamda.expr), parameter))
    return families


def _linear(
    expression: sympy.Expr, parameter: sympy.Symbol
) -> tuple[sympy.Expr, sympy.Expr] | None:
    """``(период, смещение)`` линейной серии ``period*k + offset`` или ``None``."""
    period = expression.coeff(parameter)
    if period == 0:
        return None
    offset = expression.subs(parameter, 0)
    if sympy.simplify(expression - (period * parameter + offset)) != 0:
        return None
    return period, offset


def _at_zero(family: Family) -> sympy.Expr:
    """Значение серии при параметре, равном нулю."""
    return sympy.simplify(family[0].subs(family[1], 0))


def _series_node(var: str, series: list[tuple[sympy.Expr, sympy.Expr]]) -> CoreNode:
    """Узел общего решения: ``x = смещение + период·k`` (или список таких)."""
    parameter = sympy.Symbol(_PARAMETER)
    equations = []
    for period, offset in sorted(series, key=_series_sort_key):
        right = from_sympy(offset + period * parameter)
        equations.append(CoreNode.node(T.EQUALS, CoreNode.variable(var), right))
    if len(equations) == 1:
        return equations[0]
    return CoreNode.node(T.LIST, *equations)


def _raw_node(var: str, families: list[Family]) -> CoreNode:
    """Общее решение нелинейных серий: ``x = формула(от k)`` как есть."""
    parameter = sympy.Symbol(_PARAMETER)
    ordered = sorted(families, key=lambda family: _family_sort_key(family))
    equations = []
    for expression, source in ordered:
        right = from_sympy(expression.subs(source, parameter))
        equations.append(CoreNode.node(T.EQUALS, CoreNode.variable(var), right))
    if len(equations) == 1:
        return equations[0]
    return CoreNode.node(T.LIST, *equations)


def _series_sort_key(series: tuple[sympy.Expr, sympy.Expr]) -> float:
    try:
        return float(sympy.N(series[1]))
    except (TypeError, ValueError):
        return 0.0


def _family_sort_key(family: Family) -> float:
    return _series_sort_key((family[0], _at_zero(family)))


def _select_interval(
    var: str, series: list[tuple[sympy.Expr, sympy.Expr]], interval: Interval
) -> list[CoreNode] | None:
    """Отобрать корни линейных серий на промежутке или ``None``, если он нечисловой."""
    low, high = to_sympy(interval[0]), to_sympy(interval[1])
    if not (low.is_number and high.is_number):
        return None

    values: list[sympy.Expr] = []
    for period, offset in series:
        if not (period.is_number and offset.is_number):
            return None
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


def _select_raw(var: str, families: list[Family], interval: Interval) -> list[CoreNode] | None:
    """Отобрать корни нелинейных серий перебором параметра на промежутке."""
    low, high = to_sympy(interval[0]), to_sympy(interval[1])
    if not (low.is_number and high.is_number):
        return None

    values: list[sympy.Expr] = []
    for expression, parameter in families:
        for index in range(-_MAX_PARAMETER, _MAX_PARAMETER + 1):
            value = expression.subs(parameter, index)
            if not value.is_number:
                continue
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
    "unknown_of",
]
