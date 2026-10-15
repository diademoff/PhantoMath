"""Модуль, знак и целая часть: точные значения и снятие знака.

Модуль зарегистрирован на узлы ``ABS``, ``SIGN`` и ``FLOOR`` -- три
элементарные функции одного аргумента:

* ``ABS`` -- модуль: ``|-5| = 5``, ``|π| = π``, ``|x²| = x²``;
* ``SIGN`` -- знак: ``sgn(5) = 1``, ``sgn(-3) = -1``, ``sgn(0) = 0``;
* ``FLOOR`` -- целая часть: ``⌊2.7⌋ = 2``, ``⌊-1.5⌋ = -2``, ``⌊π⌋ = 3``.

Значение считает sympy. Где он не справляется, помогают структурные
правила: модуль и знак выражения, заведомо неотрицательного (чётная
степень, корень, ``e^u``, произведение неотрицательных) снимаются.
Модуль такого выражения равен самому выражению; знак считается равным
``1`` -- как в оригинале, **вне нуля** (в нуле знак был бы ``0``, и этот
случай здесь не отделяется).

Символьные аргументы без вывода о знаке (``|x|``, ``sgn(x)``) остаются
без изменений: точного значения у них нет.

Ключи шагов: ``abs`` / ``abs_pos`` (снятие модуля), ``find_sign``,
``calculate_floor``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, SolveResult, Step, solver_for
from .sympy_bridge import from_sympy, to_sympy

# Узел -> функция sympy (она же применяется к значению и для проверки
# «осталась ли функция»). Ключ пояснения хранится отдельно.
_FUNCTIONS: dict[T, Any] = {
    T.ABS: sympy.Abs,
    T.SIGN: sympy.sign,
    T.FLOOR: sympy.floor,
}
_STEP_KEY: dict[T, str] = {
    T.ABS: "abs",
    T.SIGN: "find_sign",
    T.FLOOR: "calculate_floor",
}
_KEY_ABS_POSITIVE = "abs_pos"

# Ключи шагов уравнения с модулем.
_KEY_ABS_BRANCH = "eq_abs_branch"
_KEY_FINAL = "quad_final_single"
_KEY_NO_SOLUTION = "false_statement_solve"


@solver_for(*_FUNCTIONS)
def solve_value_function(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить модуль, знак или целую часть или оставить узел."""
    if len(node.children) != 1:
        raise SolveError("функция должна иметь один аргумент")
    argument = node.children[0]
    result = _resolve(node, argument)
    if result is None:
        return node
    key = _STEP_KEY[node.type]
    if node.type is T.ABS and result.structural_eq(argument):
        key = _KEY_ABS_POSITIVE
    ctx.result.add(Step(left=node, right=result, key=key))
    return result


def _resolve(node: CoreNode, argument: CoreNode) -> CoreNode | None:
    """Итоговое значение узла или ``None``, если он не упрощается."""
    value = _FUNCTIONS[node.type](to_sympy(argument))
    if not value.has(_FUNCTIONS[node.type]):
        # Значение вычислено полностью (число, π, …).
        return from_sympy(value)

    # Функция осталась: применяем структурные правила о неотрицательности.
    if node.type in (T.ABS, T.SIGN) and _nonnegative(argument):
        return argument if node.type is T.ABS else CoreNode.constant("1")

    candidate = from_sympy(value)
    # Частичное упрощение (например, ``|-x| = |x|``) принимаем, если узел
    # действительно изменился.
    return candidate if not candidate.structural_eq(node) else None


def _nonnegative(node: CoreNode) -> bool:
    """Заведомо ли выражение неотрицательно по своей структуре."""
    if node.type in (T.ABS, T.EXP, T.ROOT2):
        return True
    if node.type is T.ROOT and len(node.children) == 2:
        return True
    if node.type is T.POWER and len(node.children) == 2:
        exponent = _integer(node.children[1])
        if exponent is not None and exponent % 2 == 0:
            return True
    if node.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT):
        return all(_nonnegative(child) for child in node.children)
    if node.type in (T.BRACKET, T.POSITIVE) and node.children:
        return _nonnegative(node.children[0])
    if node.type is T.CONSTANT:
        try:
            return bool(to_sympy(node).is_nonnegative)
        except SolveError:
            return False
    return False


def _integer(node: CoreNode) -> int | None:
    """Целое значение константы или ``None``."""
    if node.type is not T.CONSTANT or node.value is None:
        return None
    try:
        return int(node.value.strip())
    except ValueError:
        return None


def solve_abs_equation(node: CoreNode, variables: list[str]) -> SolveResult | None:
    """Решить уравнение ``|f(x)| = g(x)`` или вернуть ``None``.

    Модуль заменяется двумя уравнениями (``f = g`` и ``f = -g``), их корни
    объединяются и проверяются подстановкой в исходное уравнение: ветвь
    ``f = -g`` подходит только при ``g ≥ 0``. Если правая часть —
    отрицательное число, решений нет. Не наш случай -- ``None``.
    """
    if len(variables) != 1:
        return None
    matched = _match_abs(node)
    if matched is None:
        return None
    abs_argument, other = matched
    var = variables[0]

    try:
        left = to_sympy(abs_argument)
        right = to_sympy(other)
    except SolveError:
        return None
    if right.is_number is True and right.is_negative:
        return _no_solution(node)

    targets = [right] if right.is_zero else [right, -right]
    symbol = sympy.Symbol(var)
    residual = sympy.Abs(left) - right
    candidates = _roots(left, targets, symbol)
    if not candidates:
        return None
    roots = [root for root in candidates if _satisfies(residual, symbol, root)]

    result = SolveResult()
    branch_node = _list_node(
        CoreNode.node(T.EQUALS, abs_argument, from_sympy(target)) for target in targets
    )
    result.add(Step(left=node, right=branch_node, key=_KEY_ABS_BRANCH))
    if not roots:
        result.add(Step(left=branch_node, right=None, key=_KEY_NO_SOLUTION))
        result.set_solution(CoreNode.empty())
        return result

    solution = _solution_node(var, roots)
    result.add(Step(left=branch_node, right=solution, key=_KEY_FINAL))
    result.set_solution(solution)
    return result


def _satisfies(residual: sympy.Expr, symbol: sympy.Symbol, root: sympy.Expr) -> bool:
    """Обращается ли ``residual`` в ноль при данном корне."""
    try:
        value = sympy.simplify(residual.subs(symbol, root))
    except (TypeError, ValueError):
        return True
    result = value == 0
    if isinstance(result, bool):
        return result
    return result is sympy.true


def _match_abs(node: CoreNode) -> tuple[CoreNode, CoreNode] | None:
    """``(аргумент модуля, другая часть)`` или ``None``, если это не ``|…| = …``."""
    if node.type is not T.EQUALS or len(node.children) != 2:
        return None
    left, right = node.children
    if left.type is T.ABS and len(left.children) == 1:
        return left.children[0], right
    if right.type is T.ABS and len(right.children) == 1:
        return right.children[0], left
    return None


def _roots(left: sympy.Expr, targets: list[sympy.Expr], symbol: sympy.Symbol) -> list[sympy.Expr]:
    """Корни уравнений ``left = target`` без повторов и комплексных."""
    roots: list[sympy.Expr] = []
    for target in targets:
        try:
            found = sympy.solve(sympy.Eq(left, target), symbol)
        except (TypeError, ValueError, NotImplementedError):
            continue
        for root in found:
            if root.is_real is False:
                continue
            if any(sympy.simplify(root - known) == 0 for known in roots):
                continue
            roots.append(root)
    roots.sort(key=_sort_key)
    return roots


def _sort_key(root: sympy.Expr) -> float:
    """Ключ сортировки корней; нечисловые корни идут первыми."""
    try:
        return float(sympy.N(root))
    except (TypeError, ValueError):
        return 0.0


def _solution_node(var: str, roots: list[sympy.Expr]) -> CoreNode:
    """Ответ ``x = …`` или список таких равенств."""
    return _list_node(
        CoreNode.node(T.EQUALS, CoreNode.variable(var), from_sympy(root)) for root in roots
    )


def _list_node(equations: Iterable[CoreNode]) -> CoreNode:
    """Один узел из перечисления равенств."""
    items = list(equations)
    if len(items) == 1:
        return items[0]
    return CoreNode.node(T.LIST, *items)


def _no_solution(node: CoreNode) -> SolveResult:
    """Модуль не может быть равен отрицательному числу."""
    result = SolveResult()
    result.add(Step(left=node, right=None, key=_KEY_NO_SOLUTION))
    result.set_solution(CoreNode.empty())
    return result


__all__ = [
    "solve_abs_equation",
    "solve_value_function",
]
