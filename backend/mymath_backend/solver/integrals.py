"""Интегралы: неопределённый и определённый.

Модуль зарегистрирован на ``INTEGRAL`` (первообразная) и
``INTEGRAL_DEFINITE`` (``[нижний, верхний, выражение]``). Считает sympy:
первообразная ищется ``integrate``, результат переводится обратно в
``CoreNode`` мостом :mod:`~mymath_backend.solver.sympy_bridge`.

Перед вычислением подбирается метод и добавляется шаг-пояснение:

* ``integrate_partial`` — по частям (произведение многочлена с ``exp``/``sin``/
  ``cos`` либо логарифм/арктангенс);
* ``integrate_using_substitution`` — замена (сложная функция, ``1/(x+a)``);
* ``integrate_sep_frac_short`` — простейшие дроби (знаменатель раскладывается);
* ``integrate_imp_evaluate`` — несобственный (бесконечный предел).

Если элементарной первообразной нет (``∫e^{x²}dx``), поднимается
:class:`SolveError` — это ожидаемый исход, а не сбой. Финальный шаг —
``integrate_calc``.
"""

from __future__ import annotations

import itertools

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step, solver_for
from .sympy_bridge import from_sympy, to_sympy


def _variable(ctx: SolveContext) -> sympy.Symbol:
    """Переменная интегрирования: единственная свободная или ``x``."""
    return sympy.Symbol(ctx.variables[0] if ctx.variables else "x")


@solver_for(T.INTEGRAL, T.INTEGRAL_DEFINITE)
def solve_integral(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Взять интеграл через sympy."""
    if node.type is T.INTEGRAL:
        ctx.require(len(ctx.variables) <= 1, "поддерживается одно неизвестное")
        return _indefinite_integral(node, ctx)
    ctx.require(len(node.children) == 3, "определённый интеграл: пределы и выражение")
    if node.children[2].type is T.INTEGRAL_DEFINITE:
        return _iterated_integral(node, ctx)
    ctx.require(len(ctx.variables) <= 1, "поддерживается одно неизвестное")
    return _definite_integral(node, ctx)


def _indefinite_integral(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Неопределённый интеграл: первообразная."""
    symbol = _variable(ctx)
    ctx.require(len(node.children) >= 1, "интеграл без подынтегрального выражения")
    expression = to_sympy(node.children[-1])
    method_key = _integral_method(expression, symbol)
    antiderivative = sympy.integrate(expression, symbol)
    if antiderivative.has(sympy.Integral):
        raise SolveError("первообразная не выражается через элементарные функции")
    try:
        result = from_sympy(sympy.simplify(antiderivative))
    except SolveError as err:
        # sympy вернул специальную функцию (erfi, Ei, …): элементарной
        # первообразной нет, и в наш AST это не переводится.
        raise SolveError("первообразная не выражается через элементарные функции") from err
    if method_key is not None:
        ctx.result.add(Step(left=node, right=None, key=method_key))
    ctx.result.add(Step(left=node, right=result, key="integrate_calc"))
    return result


def _definite_integral(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Определённый интеграл; несобственный — с разрывом или бесконечным пределом."""
    symbol = _variable(ctx)
    lower, upper, expression_node = node.children
    lower_value, upper_value = to_sympy(lower), to_sympy(upper)
    expression = to_sympy(expression_node)
    infinite = lower_value in (sympy.oo, -sympy.oo) or upper_value in (sympy.oo, -sympy.oo)
    discontinuous = (
        [] if infinite else _real_singularities(expression, symbol, lower_value, upper_value)
    )
    improper = infinite or bool(discontinuous)
    method_key = "integrate_imp_evaluate" if improper else _integral_method(expression, symbol)
    if discontinuous:
        ctx.result.add(Step(left=node, right=None, key="integrate_imp_find_discon_point"))
    try:
        value = sympy.integrate(expression, (symbol, lower_value, upper_value))
    except (TypeError, ValueError, NotImplementedError) as error:
        raise SolveError("определённый интеграл не вычисляется") from error
    if value.has(sympy.Integral):
        raise SolveError("определённый интеграл не вычисляется")
    if _diverges(value):
        if improper:
            ctx.result.add(Step(left=node, right=None, key="integrate_imp_evaluate"))
            ctx.result.add(Step(left=node, right=None, key="integrate_imp_diverges_simple"))
            raise SolveError("несобственный интеграл расходится", "integrate_imp_diverges_simple")
        raise SolveError("определённый интеграл не вычисляется")
    result = from_sympy(sympy.simplify(value))
    if method_key is not None:
        ctx.result.add(Step(left=node, right=None, key=method_key))
    ctx.result.add(Step(left=node, right=None, key="integrate_def_bounds"))
    ctx.result.add(Step(left=node, right=result, key="integrate_calc"))
    return result


def _iterated_integral(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Повторный (двойной) интеграл: внутренний, затем внешний.

    Порядок переменных задаёт появление в дереве: внешняя — первая, внутренняя
    — последняя (``∫∫ f dy dx`` при обнаружении ``x``, затем ``y``). Это
    ограничение представления: дифференциалы в узле не хранятся.
    """
    ctx.require(len(ctx.variables) == 2, "повторный интеграл: две переменные")
    outer_var = sympy.Symbol(ctx.variables[0])
    inner_var = sympy.Symbol(ctx.variables[1])
    outer_lower, outer_upper, inner = node.children
    inner_lower, inner_upper, inner_expression = inner.children
    expression = to_sympy(inner_expression)
    inner_value = sympy.integrate(
        expression, (inner_var, to_sympy(inner_lower), to_sympy(inner_upper))
    )
    ctx.result.add(Step(left=node, right=None, key="integrate_iterated"))
    ctx.result.add(Step(left=node, right=None, key="integrate_iterated_inner"))
    value = sympy.integrate(inner_value, (outer_var, to_sympy(outer_lower), to_sympy(outer_upper)))
    if _diverges(value) or value.has(sympy.Integral):
        raise SolveError("повторный интеграл не вычисляется")
    result = from_sympy(sympy.simplify(value))
    ctx.result.add(Step(left=node, right=result, key="integrate_calc"))
    return result


@solver_for(T.INTEGRAL_RIGHT_DASH)
def solve_right_dash(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Подстановка пределов в записи ``F(x)|ₐᵇ``.

    Дети — ``[выражение, нижний предел, верхний предел]`` (как рисует
    Photomath: вертикальная черта с пределами). Значение — разность
    ``F(b) − F(a)``; шаг ``integrate_def_bounds``.
    """
    ctx.require(len(node.children) == 3, "подстановка пределов: выражение и границы")
    expression_node, lower, upper = node.children
    symbol = _variable(ctx)
    expression = to_sympy(expression_node)
    value = expression.subs(symbol, to_sympy(upper)) - expression.subs(symbol, to_sympy(lower))
    result = from_sympy(sympy.simplify(value))
    ctx.result.add(Step(left=node, right=result, key="integrate_def_bounds"))
    return result


def _real_singularities(
    expression: sympy.Expr, symbol: sympy.Symbol, lower: sympy.Expr, upper: sympy.Expr
) -> list[sympy.Expr]:
    """Действительные точки разрыва внутри ``[lower, upper]``."""
    try:
        found = sympy.singularities(expression, symbol)
    except (TypeError, ValueError, NotImplementedError):
        return []
    if not isinstance(found, sympy.FiniteSet):
        return []
    points: list[sympy.Expr] = []
    try:
        low, high = float(sympy.N(lower)), float(sympy.N(upper))
    except (TypeError, ValueError):
        return []
    for point in found:
        if point.is_real is not True:
            continue
        try:
            value = float(sympy.N(point))
        except (TypeError, ValueError):
            continue
        if low <= value <= high:
            points.append(point)
    return points


def _diverges(value: sympy.Expr) -> bool:
    """Расходится ли значение интеграла (бесконечность или не число)."""
    if value is sympy.nan or value in (sympy.oo, -sympy.oo, sympy.zoo):
        return True
    return value.is_real is False


def _integral_method(expression: sympy.Expr, symbol: sympy.Symbol) -> str | None:
    """Подходящий метод интегрирования или ``None`` (табличный случай)."""
    if expression.has(sympy.log) or expression.has(sympy.atan):
        return "integrate_partial"
    if _is_rational(expression, symbol):
        _, denominator = sympy.fraction(expression)
        degree = _polynomial_degree(denominator, symbol)
        if (
            degree is not None
            and degree >= 2
            and len(sympy.factor(denominator).as_ordered_factors()) >= 2
        ):
            return "integrate_sep_frac_short"
        return None
    factors = expression.args if isinstance(expression, sympy.Mul) else (expression,)
    if _has_polynomial_factor(factors, symbol) and any(
        factor.has(sympy.exp) or factor.has(sympy.sin) or factor.has(sympy.cos)
        for factor in factors
    ):
        return "integrate_partial"
    if _has_composite(expression, symbol):
        return "integrate_using_substitution"
    return None


def _is_rational(expression: sympy.Expr, symbol: sympy.Symbol) -> bool:
    """Рациональная ли функция (числитель и знаменатель — многочлены)."""
    numerator, denominator = sympy.fraction(expression)
    return (
        _polynomial_degree(numerator, symbol) is not None
        and _polynomial_degree(denominator, symbol) is not None
    )


def _polynomial_degree(expression: sympy.Expr, symbol: sympy.Symbol) -> int | None:
    """Степень многочлена или ``None``, если это не многочлен."""
    try:
        return int(sympy.degree(expression, symbol))
    except (TypeError, ValueError, sympy.PolynomialError):
        return None


def _has_polynomial_factor(factors: tuple[sympy.Expr, ...], symbol: sympy.Symbol) -> bool:
    """Есть ли среди множителей многочлен степени ≥ 1."""
    for factor in factors:
        if not factor.has(symbol):
            continue
        degree = _polynomial_degree(factor, symbol)
        if degree is not None and degree >= 1:
            return True
    return False


def _has_composite(expression: sympy.Expr, symbol: sympy.Symbol) -> bool:
    """Есть ли вложенная функция (замена): ``sin(2x)``, ``1/(x+1)``."""
    for function in expression.atoms(sympy.Function):
        arguments = function.args
        if arguments and arguments[0] != symbol and arguments[0].has(symbol):
            return True
    for power in expression.atoms(sympy.Pow):
        if power.base != symbol and power.base.has(symbol):
            return True
    return False


def area(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Общая площадь под кривой: интеграл модуля функции на отрезке.

    Команда ``area`` принимает определённый интеграл ``∫_a^b f dx`` и считает
    ``∫_a^b |f| dx``: промежуток разбивается корнями ``f``, на каждом куске
    берётся модуль интеграла. Ответ — площадь (число/выражение).
    """
    del args
    ctx.require(node.type is T.INTEGRAL_DEFINITE, "площадь берётся у определённого интеграла")
    ctx.require(len(node.children) == 3, "определённый интеграл: пределы и выражение")
    ctx.require(len(ctx.variables) <= 1, "поддерживается одно неизвестное")
    symbol = _variable(ctx)

    lower_node, upper_node, expression_node = node.children
    lower = to_sympy(lower_node)
    upper = to_sympy(upper_node)
    expression = to_sympy(expression_node)
    if not (lower.is_real is True and upper.is_real is True):
        raise SolveError("пределы площади должны быть числами")
    if lower > upper:
        lower, upper = upper, lower

    breakpoints = [lower, *_roots_inside(expression, symbol, lower, upper), upper]
    total = sympy.Integer(0)
    for start, end in itertools.pairwise(breakpoints):
        piece = sympy.integrate(expression, (symbol, start, end))
        total += sympy.Abs(piece)
    result = from_sympy(sympy.simplify(total))
    ctx.result.add(Step(left=node, right=None, key="total_area"))
    ctx.result.add(Step(left=node, right=result, key="integrate_calc"))
    return result


def _roots_inside(
    expression: sympy.Expr, symbol: sympy.Symbol, lower: sympy.Expr, upper: sympy.Expr
) -> list[sympy.Expr]:
    """Действительные корни выражения внутри ``(lower, upper)`` по возрастанию."""
    try:
        found = sympy.solve(sympy.Eq(expression, 0), symbol)
    except (TypeError, ValueError, NotImplementedError):
        return []
    inside: list[sympy.Expr] = []
    for root in found:
        if root.is_real is False:
            continue
        try:
            value = float(sympy.N(root))
        except (TypeError, ValueError):
            continue
        if float(sympy.N(lower)) < value < float(sympy.N(upper)):
            inside.append(root)
    inside.sort(key=lambda item: float(sympy.N(item)))
    return inside


__all__ = [
    "area",
    "solve_integral",
]
