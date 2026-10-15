"""Область определения выражения (команда ``domain``).

Область определения — множество значений переменной, при которых выражение
определено (знаменатель не ноль, подкоренное выражение неотрицательно,
аргумент логарифма положителен и т.д.). Считает sympy
(``continuous_domain``), ответ выражается промежутками, их объединением или
разностью; всё множество действительных чисел — промежуток ``(-∞, +∞)``.

Шаг — ``domain_find``. Если область определения не выражается промежутками
(например, у ``tan`` она задаётся вычитанием периодического множества) —
:class:`SolveError`.
"""

from __future__ import annotations

import sympy
from sympy.calculus.util import continuous_domain

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step
from .sympy_bridge import from_sympy, to_sympy

_KEY = "domain_find"
_KEY_RESTRICTIONS = "rel_restrictions_find"


def all_reals() -> CoreNode:
    """Область определения как промежуток ``(-∞, +∞)``."""
    return from_sympy(sympy.S.Reals)


def domain(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Найти область определения выражения."""
    del args
    if node.type is T.EQUALS:
        raise SolveError("область определения берётся у выражения, а не у уравнения")

    expression = to_sympy(node)
    symbols = sorted(expression.free_symbols, key=lambda symbol: symbol.name)
    if len(symbols) > 1:
        raise SolveError("область определения: поддерживается одна переменная")

    if symbols:
        classification = _classification(expression, symbols[0])
        if classification is not None:
            key, classification_args = classification
            ctx.result.add(Step(left=node, right=None, key=key, args=classification_args))

    answer = all_reals() if not symbols else _domain_of(expression, symbols[0])
    if symbols:
        ctx.result.add(Step(left=node, right=None, key="domain_find_defined"))
    ctx.result.add(Step(left=node, right=answer, key=_KEY))
    return answer


def _classification(
    expression: sympy.Expr, symbol: sympy.Symbol
) -> tuple[str, list[CoreNode]] | None:
    """Шаг с видом ограничения области определения (или ``None``)."""
    variable = CoreNode.variable(str(symbol))
    zero = CoreNode.constant("0")
    if any(
        isinstance(power, sympy.Pow)
        and power.exp == sympy.Rational(1, 2)
        and power.base.has(symbol)
        for power in expression.atoms(sympy.Pow)
    ):
        return "domain_even_root", [variable, zero]
    if any(logarithm.args[0].has(symbol) for logarithm in expression.atoms(sympy.log)):
        return "domain_log", [variable]
    _, denominator = sympy.fraction(sympy.together(expression))
    if denominator.has(symbol):
        return "domain_rational", [variable, zero]
    try:
        sympy.Poly(expression, symbol)
    except sympy.PolynomialError:
        return None
    return "domain_poly_real", []


def restrictions(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Найти недопустимые значения выражения (дополнение области определения).

    Знаменатель, аргумент логарифма, подкоренное выражение и т.п. дают
    значения, при которых выражение не определено. Ответ — множество
    (промежуток, объединение или конечное множество точек); если таких нет —
    ``EMPTY``.
    """
    del args
    if node.type is T.EQUALS:
        raise SolveError("недопустимые значения берутся у выражения, а не у уравнения")

    expression = to_sympy(node)
    symbols = sorted(expression.free_symbols, key=lambda symbol: symbol.name)
    if len(symbols) > 1:
        raise SolveError("недопустимые значения: поддерживается одна переменная")

    forbidden = sympy.EmptySet if not symbols else _forbidden(expression, symbols[0])
    answer = from_sympy(forbidden)
    key = "rel_restrictions_none" if answer.type is T.EMPTY else _KEY_RESTRICTIONS
    ctx.result.add(Step(left=node, right=answer, key=key))
    return answer


def add_restriction_steps(
    node: CoreNode, variables: list[str], ctx: SolveContext, expression: sympy.Expr
) -> bool:
    """Добавить шаги ОДЗ (``rel_restrictions_*``) для ограничений выражения.

    Ограничения — знаменатель дроби, подкоренное выражение и аргумент
    логарифма, зависящие от переменной. Возвращает ``True``, если хотя бы одно
    найдено (тогда в результат добавлены ``rel_restrictions_find`` и по шагу на
    каждое условие); ``False`` — выражение ограничений не имеет (например,
    многочлен), и результат не меняется.

    Нужен модулям уравнений и неравенств: они показывают ОДЗ до решения, а
    затем отсеивают посторонние корни (``rel_restrictions_check``).
    """
    if len(variables) != 1:
        return False
    var = variables[0]
    symbol = sympy.Symbol(var)
    conditions: list[tuple[str, list[CoreNode]]] = []
    seen: set[str] = set()

    def remember(key: str, args: list[CoreNode]) -> None:
        marker = "|".join([key, *(arg.to_contract().__repr__() for arg in args)])
        if marker not in seen:
            seen.add(marker)
            conditions.append((key, args))

    _, denominator = sympy.fraction(sympy.together(expression))
    if denominator.has(symbol):
        remember(
            "rel_restrictions_den_zero",
            [CoreNode.variable(var), CoreNode.constant("0"), from_sympy(denominator)],
        )
    for power in expression.atoms(sympy.Pow):
        if power.exp == sympy.Rational(1, 2) and power.base.has(symbol):
            remember(
                "rel_restrictions_root_base_neg",
                [CoreNode.variable(var), from_sympy(power.base)],
            )
    for logarithm in expression.atoms(sympy.log):
        if logarithm.args[0].has(symbol):
            remember(
                "rel_restrictions_log_arg",
                [
                    CoreNode.variable(var),
                    from_sympy(logarithm.args[0]),
                    CoreNode.constant("0"),
                ],
            )

    if not conditions:
        return False
    ctx.result.add(Step(left=node, right=None, key="rel_restrictions_find"))
    for key, args in conditions:
        ctx.result.add(Step(left=node, right=None, key=key, args=args))
    return True


def _forbidden(expression: sympy.Expr, symbol: sympy.Symbol) -> sympy.Set:
    """Множество недопустимых значений: дополнение области определения."""
    try:
        allowed = continuous_domain(expression, symbol, sympy.S.Reals)
        return sympy.simplify(sympy.Complement(sympy.S.Reals, allowed))
    except (NotImplementedError, ValueError) as error:
        raise SolveError("недопустимые значения не выражаются") from error


def _domain_of(expression: sympy.Expr, symbol: sympy.Symbol) -> CoreNode:
    """Область определения выражения относительно переменной."""
    try:
        values = continuous_domain(expression, symbol, sympy.S.Reals)
        return from_sympy(values)
    except (NotImplementedError, ValueError) as error:
        raise SolveError("область определения не выражается промежутками") from error
    except SolveError as error:
        raise SolveError("область определения не выражается промежутками") from error


__all__ = [
    "add_restriction_steps",
    "all_reals",
    "domain",
    "restrictions",
]
