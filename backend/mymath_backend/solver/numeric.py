"""Численное решение уравнений: смешанные трансцендентные случаи.

Уравнения вида ``sin x = x`` или ``x*sin x = 1`` не решаются аналитически:
алгебраическая и тригонометрическая части не разделяются. ``solveset``
возвращает ``ConditionSet``, ``solve`` бросает ``NotImplementedError``.
Для них корни ищутся численно:

* точные корни берёт ``sympy.solve`` -- если выражение не периодическое
  (у периодического ``solve`` молча теряет ``+2πk``) и корень проходит
  проверку подстановкой;
* иначе по сетке на ``[-_SCAN_LIMIT, _SCAN_LIMIT]`` ищутся смены знака,
  каждая уточняется бисекцией; полюсы отсеиваются проверкой значения.

Ответ -- приближённые значения; шаги ``graph_solution`` («Начертите») и
``calculate`` / ``calculate_plural`` («Вычислите приближённое значение»).
"""

from __future__ import annotations

import math
from collections.abc import Callable

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .base import SolveError, SolveResult, Step
from .sympy_bridge import to_sympy

_HEADER = CoreRichText(type="eq_solve_short")
"""Заголовок шага: «Решите уравнение»."""

_SCAN_LIMIT = 20.0
"""Границы отрезка поиска численных корней."""

_SCAN_POINTS = 2000
"""Число узлов сетки: шаг 0.02 на [-20; 20]."""

_MAX_ROOTS = 12
"""Потолок числа выводимых корней: защита от сильно осциллирующих функций."""


def solve_numeric_equation(node: CoreNode, variables: list[str]) -> SolveResult | None:
    """Решить уравнение численно или вернуть ``None``.

    ``None`` означает «случай не для этого модуля»: не равенство, переменных
    не одна, выражение не переводится в sympy или корней не нашлось.
    """
    if node.type is not T.EQUALS or len(node.children) != 2 or len(variables) != 1:
        return None

    var = variables[0]
    symbol = sympy.Symbol(var)
    lhs, rhs = node.children
    try:
        expression = to_sympy(lhs) - to_sympy(rhs)
    except SolveError:
        return None
    if not expression.free_symbols <= {symbol}:
        return None

    exact = _exact_roots(expression, symbol)
    if exact is not None:
        return _result(node, var, exact, headers=True)

    values = _numeric_roots(expression, symbol)
    if not values:
        return None
    return _result(node, var, values, headers=False)


def _exact_roots(expression: sympy.Expr, symbol: sympy.Symbol) -> list[str] | None:
    """Точные корни через ``solve``; ``None``, если путь не подходит.

    Для периодических выражений ``solve`` возвращает лишь главные ветви без
    ``+2πk`` -- такие ответы не принимаем (их решает модуль тригонометрии).
    """
    if sympy.periodicity(expression, symbol) is not None:
        return None
    try:
        found = sympy.solve(expression, symbol)
    except (NotImplementedError, TypeError, ValueError):
        return None
    if not found:
        return None

    roots: list[str] = []
    for root in found:
        if not root.is_real:
            continue
        if not _satisfies(expression, symbol, root):
            continue
        roots.append(_render(root))
    if not roots:
        return None
    return sorted(set(roots), key=_sort_number)


def _numeric_roots(expression: sympy.Expr, symbol: sympy.Symbol) -> list[str]:
    """Корни перебором смен знака по сетке с уточнением бисекцией."""
    function = _as_float_function(expression, symbol)
    if function is None:
        return []

    step = (2 * _SCAN_LIMIT) / _SCAN_POINTS
    candidates: list[float] = []
    previous_x = -_SCAN_LIMIT
    previous_y = _evaluate(function, previous_x)
    index = 0
    while index <= _SCAN_POINTS:
        point = -_SCAN_LIMIT + index * step
        value = _evaluate(function, point)
        if value is None:
            previous_x, previous_y = point, None
            index += 1
            continue
        if value == 0.0:
            candidates.append(point)
        elif previous_y is not None and math.copysign(1.0, value) != math.copysign(1.0, previous_y):
            candidates.append(_bisect(function, previous_x, point))
        previous_x, previous_y = point, value
        index += 1

    roots: list[float] = []
    for candidate in sorted(candidates, key=abs):
        if any(abs(candidate - known) < 1e-6 for known in roots):
            continue
        value = _evaluate(function, candidate)
        if value is None or abs(value) >= 1e-6:
            continue  # смена знака через полюс, не корень
        roots.append(candidate)
        if len(roots) >= _MAX_ROOTS:
            break
    roots.sort()
    return [_render(value) for value in roots]


def _as_float_function(
    expression: sympy.Expr, symbol: sympy.Symbol
) -> Callable[[float], object] | None:
    """Числовая функция выражения; ``None``, если sympy не скомпилировал её."""
    try:
        function = sympy.lambdify(symbol, expression, modules="math")
    except (TypeError, ValueError, NameError):
        return None
    return function  # type: ignore[no-any-return]


def _evaluate(function: Callable[[float], object], point: float) -> float | None:
    """Значение в точке; ``None`` при провале (полюс, область определения)."""
    try:
        value = function(point)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
    if not isinstance(value, (int, float)):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return float(value)


def _bisect(function: Callable[[float], object], low: float, high: float) -> float:
    """Утонение корня на отрезке смены знака."""
    left, right = low, high
    left_value = _evaluate(function, left) or 0.0
    for _ in range(80):
        middle = (left + right) / 2
        middle_value = _evaluate(function, middle)
        if middle_value is None:
            break
        if middle_value == 0.0 or right - left < 1e-13:
            return middle
        if math.copysign(1.0, middle_value) == math.copysign(1.0, left_value):
            left, left_value = middle, middle_value
        else:
            right = middle
    return (left + right) / 2


def _satisfies(expression: sympy.Expr, symbol: sympy.Symbol, root: sympy.Expr) -> bool:
    """Обращает ли корень выражение в ноль (численно)."""
    try:
        value = complex(sympy.N(expression.subs(symbol, root)))
    except (TypeError, ValueError):
        return False
    return abs(value) < 1e-9


def _render(value: sympy.Expr | float) -> str:
    """Число для узла: целое без дроби, иначе шесть знаков после запятой."""
    number = float(sympy.N(value)) if isinstance(value, sympy.Basic) else float(value)
    if abs(number - round(number)) < 1e-10:
        return str(round(number))
    text = f"{number:.6f}".rstrip("0").rstrip(".")
    return text


def _sort_number(text: str) -> float:
    try:
        return float(text)
    except ValueError:
        return 0.0


def _result(node: CoreNode, var: str, values: list[str], *, headers: bool) -> SolveResult:
    """Собрать результат: шаг-пояснение и список корней ``x = значение``."""
    equations = [
        CoreNode.node(T.EQUALS, CoreNode.variable(var), CoreNode.constant(value))
        for value in values
    ]
    answer = equations[0] if len(equations) == 1 else CoreNode.node(T.LIST, *equations)

    result = SolveResult()
    headers_group = [_HEADER] if headers else []
    result.add(Step(left=node, right=None, key="graph_solution"), headers_group)
    key = "calculate" if len(equations) == 1 else "calculate_plural"
    result.add(Step(left=node, right=answer, key=key), headers_group)
    result.set_solution(answer)
    return result


__all__ = ["solve_numeric_equation"]
