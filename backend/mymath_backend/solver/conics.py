"""Конические сечения: полный разбор (команда ``conic_details``).

Для уравнения второй степени ``A x² + B xy + C y² + D x + E y + F = 0`` без
члена ``xy`` (осевые коники) выделяются полные квадраты и находятся
канонический вид, центр, вершины, сопряжённые вершины, фокусы, директриса и
радиус. Уравнение решается в рациональных числах.

Шаги: ``conics_identify``, ``conics_since_circle``/``_ellipse``/``_hyperbola``/
``_parabola`` (с каноническим видом) и метки ``graph_rt_info_center``,
``graph_rt_info_radius``, ``graph_rt_info_vertices``, ``graph_rt_info_co_vertices``,
``graph_rt_info_foci``, ``graph_rt_info_vertex``, ``graph_rt_info_focus``,
``graph_rt_info_directrix``, ``graph_rt_info_asymptotes``.

Повёрнутые коники (член ``xy``) и вырожденные случаи пока отклоняются.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step
from .sympy_bridge import from_sympy, to_sympy

ZERO = sympy.Integer(0)


def conic_details(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Полный разбор конического сечения."""
    del args
    if node.type is not T.EQUALS or len(node.children) != 2:
        raise SolveError("коника — это уравнение")
    if len(ctx.variables) != 2:
        raise SolveError("коника: нужны две переменные")
    x, y = (sympy.Symbol(name) for name in ctx.variables)
    expression = sympy.expand(to_sympy(node.children[0]) - to_sympy(node.children[1]))
    try:
        polynomial = sympy.Poly(expression, x, y)
    except sympy.PolynomialError as error:
        raise SolveError("не коническое уравнение") from error

    a = polynomial.coeff_monomial(x**2)
    b = polynomial.coeff_monomial(x * y)
    c = polynomial.coeff_monomial(y**2)
    d = polynomial.coeff_monomial(x)
    e = polynomial.coeff_monomial(y)
    f = polynomial.coeff_monomial(1)
    if b != 0:
        raise SolveError("коники с членом xy (повёрнутые) пока не разбираются")
    if a == 0 and c == 0:
        raise SolveError("это не коника: нет квадратичных членов")

    ctx.result.add(Step(left=node, right=None, key="conics_identify"))
    if a == 0 or c == 0:
        return _parabola(node, ctx, x, y, a, c, d, e, f)
    return _central(node, ctx, x, y, a, c, d, e, f)


def _central(
    node: CoreNode,
    ctx: SolveContext,
    x: sympy.Symbol,
    y: sympy.Symbol,
    a: sympy.Expr,
    c: sympy.Expr,
    d: sympy.Expr,
    e: sympy.Expr,
    f: sympy.Expr,
) -> CoreNode:
    """Круг, эллипс или гипербола (обе квадратичные координаты присутствуют)."""
    h = sympy.Rational(-d, 2 * a)
    k = sympy.Rational(-e, 2 * c)
    remainder = a * h * h + c * k * k - f
    ctx.result.add(Step(left=node, right=_point(h, k), key="graph_rt_info_center"))

    if a == c:
        return _circle(node, ctx, x, y, h, k, remainder, a)
    if (a > 0) == (c > 0):
        return _ellipse(node, ctx, x, y, a, c, h, k, remainder)
    return _hyperbola(node, ctx, x, y, a, c, h, k, remainder)


def _circle(
    node: CoreNode,
    ctx: SolveContext,
    x: sympy.Symbol,
    y: sympy.Symbol,
    h: sympy.Expr,
    k: sympy.Expr,
    remainder: sympy.Expr,
    a: sympy.Expr,
) -> CoreNode:
    value = sympy.Rational(remainder, a)
    if value < 0:
        raise SolveError("уравнение не задаёт окружность (мнимый радиус)")
    canonical = sympy.Eq((x - h) ** 2 + (y - k) ** 2, value)
    answer = from_sympy(canonical)
    ctx.result.add(Step(left=node, right=answer, key="conics_since_circle", args=[answer]))
    if value > 0:
        ctx.result.add(
            Step(left=node, right=from_sympy(sympy.sqrt(value)), key="graph_rt_info_radius")
        )
    return answer


def _ellipse(
    node: CoreNode,
    ctx: SolveContext,
    x: sympy.Symbol,
    y: sympy.Symbol,
    a: sympy.Expr,
    c: sympy.Expr,
    h: sympy.Expr,
    k: sympy.Expr,
    remainder: sympy.Expr,
) -> CoreNode:
    first = sympy.Rational(remainder, a)
    second = sympy.Rational(remainder, c)
    if first <= 0 or second <= 0:
        raise SolveError("уравнение не задаёт эллипс")
    canonical = sympy.Eq((x - h) ** 2 / first + (y - k) ** 2 / second, 1)
    answer = from_sympy(canonical)
    ctx.result.add(Step(left=node, right=answer, key="conics_since_ellipse", args=[answer]))

    # Большая полуось — где знаменатель больше; фокусы вдоль неё.
    if first >= second:
        major, minor = sympy.sqrt(first), sympy.sqrt(second)
        vertices = [_point(h - major, k), _point(h + major, k)]
        co_vertices = [_point(h, k - minor), _point(h, k + minor)]
        focus_offset = sympy.sqrt(first - second)
        foci = [_point(h - focus_offset, k), _point(h + focus_offset, k)]
    else:
        major, minor = sympy.sqrt(second), sympy.sqrt(first)
        vertices = [_point(h, k - major), _point(h, k + major)]
        co_vertices = [_point(h - minor, k), _point(h + minor, k)]
        focus_offset = sympy.sqrt(second - first)
        foci = [_point(h, k - focus_offset), _point(h, k + focus_offset)]
    ctx.result.add(Step(left=node, right=_points(vertices), key="graph_rt_info_vertices"))
    ctx.result.add(Step(left=node, right=_points(foci), key="graph_rt_info_foci"))
    ctx.result.add(Step(left=node, right=_points(co_vertices), key="graph_rt_info_co_vertices"))
    return answer


def _hyperbola(
    node: CoreNode,
    ctx: SolveContext,
    x: sympy.Symbol,
    y: sympy.Symbol,
    a: sympy.Expr,
    c: sympy.Expr,
    h: sympy.Expr,
    k: sympy.Expr,
    remainder: sympy.Expr,
) -> CoreNode:
    if remainder == 0:
        raise SolveError("уравнение не задаёт гиперболу (вырожденный случай)")
    first = sympy.Rational(remainder, a)
    second = sympy.Rational(remainder, c)
    canonical = sympy.Eq((x - h) ** 2 / first + (y - k) ** 2 / second, 1)
    answer = from_sympy(canonical)
    ctx.result.add(Step(left=node, right=answer, key="conics_since_hyperbola", args=[answer]))

    if first > 0:
        transverse = sympy.sqrt(first)
        conjugate = sympy.sqrt(-second)
        vertices = [_point(h - transverse, k), _point(h + transverse, k)]
        focus_offset = sympy.sqrt(first - second)
        foci = [_point(h - focus_offset, k), _point(h + focus_offset, k)]
        slope = conjugate / transverse
        asymptote_key = True
    else:
        transverse = sympy.sqrt(second)
        conjugate = sympy.sqrt(-first)
        vertices = [_point(h, k - transverse), _point(h, k + transverse)]
        focus_offset = sympy.sqrt(second - first)
        foci = [_point(h, k - focus_offset), _point(h, k + focus_offset)]
        slope = conjugate / transverse
        asymptote_key = False
    ctx.result.add(Step(left=node, right=_points(vertices), key="graph_rt_info_vertices"))
    ctx.result.add(Step(left=node, right=_points(foci), key="graph_rt_info_foci"))
    if asymptote_key:
        first_line = sympy.Eq(y - k, slope * (x - h))
        second_line = sympy.Eq(y - k, -slope * (x - h))
    else:
        first_line = sympy.Eq(x - h, slope * (y - k))
        second_line = sympy.Eq(x - h, -slope * (y - k))
    ctx.result.add(
        Step(
            left=node,
            right=CoreNode.node(T.LIST, from_sympy(first_line), from_sympy(second_line)),
            key="graph_rt_info_asymptotes",
        )
    )
    return answer


def _parabola(
    node: CoreNode,
    ctx: SolveContext,
    x: sympy.Symbol,
    y: sympy.Symbol,
    a: sympy.Expr,
    c: sympy.Expr,
    d: sympy.Expr,
    e: sympy.Expr,
    f: sympy.Expr,
) -> CoreNode:
    """Парабола с вертикальной (нет x²) или горизонтальной (нет y²) осью."""
    if a == 0:
        # C y² + E y + D x + F = 0 -> (y−k)² = 4p·(x−xv)
        if d == 0:
            raise SolveError("уравнение не задаёт параболу (вырожденный случай)")
        k = sympy.Rational(-e, 2 * c)
        vertex_x = sympy.Rational(c * k * k - f, d)
        four_p = sympy.Rational(-d, c)
        canonical = sympy.Eq((y - k) ** 2, four_p * (x - vertex_x))
        vertex = _point(vertex_x, k)
        focus = _point(vertex_x + four_p / 4, k)
        directrix = sympy.Eq(x, vertex_x - four_p / 4)
    else:
        # A x² + D x + E y + F = 0 -> (x−h)² = 4p·(y−yv)
        if e == 0:
            raise SolveError("уравнение не задаёт параболу (вырожденный случай)")
        h = sympy.Rational(-d, 2 * a)
        vertex_y = sympy.Rational(a * h * h - f, e)
        four_p = sympy.Rational(-e, a)
        canonical = sympy.Eq((x - h) ** 2, four_p * (y - vertex_y))
        vertex = _point(h, vertex_y)
        focus = _point(h, vertex_y + four_p / 4)
        directrix = sympy.Eq(y, vertex_y - four_p / 4)

    answer = from_sympy(canonical)
    ctx.result.add(Step(left=node, right=answer, key="conics_since_parabola", args=[answer]))
    ctx.result.add(Step(left=node, right=vertex, key="graph_rt_info_vertex"))
    ctx.result.add(Step(left=node, right=focus, key="graph_rt_info_focus"))
    ctx.result.add(Step(left=node, right=from_sympy(directrix), key="graph_rt_info_directrix"))
    return answer


def _point(first: sympy.Expr, second: sympy.Expr) -> CoreNode:
    """Точка как ``LIST[координата, координата]``."""
    return CoreNode.node(T.LIST, from_sympy(first), from_sympy(second))


def _points(points: list[CoreNode]) -> CoreNode:
    """Список точек как ``LIST``."""
    return CoreNode.node(T.LIST, *points)


__all__ = [
    "conic_details",
]
