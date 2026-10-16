"""Конические сечения: полный разбор (команда ``conic_details``).

Для уравнения второй степени ``A x² + B xy + C y² + D x + E y + F = 0``
выделяются полные квадраты (осевые коники) либо делается поворот осей,
гасящий член ``xy`` (повёрнутые коники). Находятся канонический вид, центр,
вершины, сопряжённые вершины, фокусы, директриса, асимптоты и радиус.
Осевые случаи решаются в рациональных числах; при повороте коэффициенты
уходят в радикалы (собственные векторы квадратичной формы).

Шаги: ``conics_identify``, ``conics_identify_std_form`` (повёрнутые),
``conics_since_circle``/``_ellipse``/``_hyperbola``/``_parabola`` (с
каноническим видом) и метки ``graph_rt_info_center``,
``graph_rt_info_radius``, ``graph_rt_info_vertices``,
``graph_rt_info_co_vertices``, ``graph_rt_info_foci``,
``graph_rt_info_vertex``, ``graph_rt_info_focus``,
``graph_rt_info_directrix``, ``graph_rt_info_asymptotes``.
"""

from __future__ import annotations

from collections.abc import Callable

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step
from .sympy_bridge import from_sympy, to_sympy

ZERO = sympy.Integer(0)

_Back = Callable[[sympy.Expr, sympy.Expr], CoreNode]
"""Функция «точка новых осей -> точка исходных осей»."""


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
        return _rotated(node, ctx, x, y, a, b, c, d, e, f)
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
    ctx.result.add(Step(left=node, right=None, key="conics_complete_square_both"))
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


# -- Повёрнутые коники (член xy) ------------------------------------------


def _frame_names(variables: list[str]) -> tuple[sympy.Symbol, sympy.Symbol]:
    """Имена новых осей после поворота: первые свободные из пар-кандидатов."""
    taken = set(variables)
    for first, second in (("u", "v"), ("s", "t"), ("p", "q")):
        if first not in taken and second not in taken:
            return sympy.Symbol(first), sympy.Symbol(second)
    return sympy.Symbol("u_1"), sympy.Symbol("v_1")


def _directions(a: sympy.Expr, b: sympy.Expr, c: sympy.Expr) -> tuple[sympy.Matrix, sympy.Matrix]:
    """Орты новых осей: собственные векторы формы ``[[A, B/2], [B/2, C]]``.

    Симметричная матрица даёт ортогональный базис -- смешанный член после
    поворота исчезает. Векторы нормируются и упорядочиваются по возрастанию
    собственного числа; при отражении (``det < 0``) вторая ось разворачивается,
    чтобы получился именно поворот.
    """
    matrix = sympy.Matrix([[a, b / 2], [b / 2, c]])
    result: list[sympy.Matrix] = []
    for _, _, basis in sorted(matrix.eigenvects(), key=lambda item: float(sympy.N(item[0]))):
        vector = basis[0]
        norm = vector.norm()
        result.append(vector.applyfunc(lambda part, n=norm: sympy.simplify(part / n)))
    if len(result) != 2:
        raise SolveError("квадратичная форма коники не задаёт поворот осей")
    frame = sympy.Matrix.hstack(*result)
    if frame.det() < 0:
        result[1] = -result[1]
    return result[0], result[1]


def _back_to_original(
    center: tuple[sympy.Expr, sympy.Expr] | None, first: sympy.Matrix, second: sympy.Matrix
) -> _Back:
    """Функция перевода точки ``(u, v)`` новых осей в исходные координаты."""
    shift_x, shift_y = center if center is not None else (ZERO, ZERO)

    def build(u: sympy.Expr, v: sympy.Expr) -> CoreNode:
        x = sympy.simplify(shift_x + first[0] * u + second[0] * v)
        y = sympy.simplify(shift_y + first[1] * u + second[1] * v)
        return _point(x, y)

    return build


def _rotated(
    node: CoreNode,
    ctx: SolveContext,
    x: sympy.Symbol,
    y: sympy.Symbol,
    a: sympy.Expr,
    b: sympy.Expr,
    c: sympy.Expr,
    d: sympy.Expr,
    e: sympy.Expr,
    f: sympy.Expr,
) -> CoreNode:
    """Повёрнутая коника: гасим ``xy`` поворотом и решаем в новых осях.

    Центр ищем из системы ``∂F/∂x = ∂F/∂y = 0``; если она несовместна,
    матрица формы вырождена -- это парабола, её разворачиваем без переноса.
    """
    first, second = _directions(a, b, c)
    u, v = _frame_names([str(x), str(y)])
    solution = sympy.solve([2 * a * x + b * y + d, b * x + 2 * c * y + e], [x, y])
    center: tuple[sympy.Expr, sympy.Expr] | None = None
    if isinstance(solution, dict):
        center = (sympy.simplify(solution[x]), sympy.simplify(solution[y]))
        shift = {
            x: center[0] + first[0] * u + second[0] * v,
            y: center[1] + first[1] * u + second[1] * v,
        }
    else:
        shift = {x: first[0] * u + second[0] * v, y: first[1] * u + second[1] * v}

    expression = sympy.expand((a * x * x + b * x * y + c * y * y + d * x + e * y + f).subs(shift))
    try:
        polynomial = sympy.Poly(expression, u, v, domain="EX")
    except sympy.PolynomialError as error:
        raise SolveError("не коническое уравнение") from error
    a_new = sympy.simplify(polynomial.coeff_monomial(u**2))
    c_new = sympy.simplify(polynomial.coeff_monomial(v**2))
    d_new = sympy.simplify(polynomial.coeff_monomial(u))
    e_new = sympy.simplify(polynomial.coeff_monomial(v))
    f_new = sympy.simplify(polynomial.coeff_monomial(1))
    if sympy.simplify(polynomial.coeff_monomial(u * v)) != 0:
        raise SolveError("коники с членом xy не сводится поворотом")

    ctx.result.add(Step(left=node, right=None, key="conics_identify"))
    ctx.result.add(Step(left=node, right=None, key="conics_identify_std_form"))
    back = _back_to_original(center, first, second)

    if a_new == 0 and c_new == 0:
        raise SolveError("это не коника: нет квадратичных членов")
    if a_new == 0 or c_new == 0:
        # a_new == 0: чётная координата v, ось -- u (первый орт); иначе наоборот.
        if a_new == 0:
            return _rotated_parabola(
                node, ctx, x, y, back, first, u, v, False, c_new, e_new, d_new, f_new
            )
        return _rotated_parabola(
            node, ctx, x, y, back, second, u, v, True, a_new, d_new, e_new, f_new
        )
    return _rotated_central(node, ctx, x, y, u, v, back, first, second, center, a_new, c_new, f_new)


def _rotated_central(
    node: CoreNode,
    ctx: SolveContext,
    x: sympy.Symbol,
    y: sympy.Symbol,
    u: sympy.Symbol,
    v: sympy.Symbol,
    back: _Back,
    first: sympy.Matrix,
    second: sympy.Matrix,
    center: tuple[sympy.Expr, sympy.Expr] | None,
    a_new: sympy.Expr,
    c_new: sympy.Expr,
    f_new: sympy.Expr,
) -> CoreNode:
    """Эллипс, окружность или гипербола после поворота: ``λ₁u² + λ₂v² = R``."""
    radius_squared = sympy.simplify(-f_new / a_new)
    conjugate_squared = sympy.simplify(-f_new / c_new)
    if center is not None:
        ctx.result.add(Step(left=node, right=_point(*center), key="graph_rt_info_center"))

    if radius_squared > 0 and conjugate_squared > 0:
        if a_new == c_new:
            canonical = sympy.Eq(u**2 + v**2, radius_squared)
            answer = from_sympy(canonical)
            ctx.result.add(Step(left=node, right=answer, key="conics_since_circle", args=[answer]))
            ctx.result.add(
                Step(
                    left=node,
                    right=from_sympy(sympy.sqrt(radius_squared)),
                    key="graph_rt_info_radius",
                )
            )
            return answer
        canonical = sympy.Eq(u**2 / radius_squared + v**2 / conjugate_squared, 1)
        answer = from_sympy(canonical)
        ctx.result.add(Step(left=node, right=answer, key="conics_since_ellipse", args=[answer]))
        if radius_squared >= conjugate_squared:
            major, minor = sympy.sqrt(radius_squared), sympy.sqrt(conjugate_squared)
            offset = sympy.sqrt(radius_squared - conjugate_squared)
            vertices = [back(-major, ZERO), back(major, ZERO)]
            co_vertices = [back(ZERO, -minor), back(ZERO, minor)]
            foci = [back(-offset, ZERO), back(offset, ZERO)]
        else:
            major, minor = sympy.sqrt(conjugate_squared), sympy.sqrt(radius_squared)
            offset = sympy.sqrt(conjugate_squared - radius_squared)
            vertices = [back(ZERO, -major), back(ZERO, major)]
            co_vertices = [back(-minor, ZERO), back(minor, ZERO)]
            foci = [back(ZERO, -offset), back(ZERO, offset)]
        ctx.result.add(Step(left=node, right=_points(vertices), key="graph_rt_info_vertices"))
        ctx.result.add(Step(left=node, right=_points(foci), key="graph_rt_info_foci"))
        ctx.result.add(Step(left=node, right=_points(co_vertices), key="graph_rt_info_co_vertices"))
        return answer

    if (radius_squared > 0) == (conjugate_squared > 0):
        raise SolveError("коника не имеет действительных точек (мнимый случай)")

    canonical = sympy.Eq(u**2 / radius_squared + v**2 / conjugate_squared, 1)
    answer = from_sympy(canonical)
    ctx.result.add(Step(left=node, right=answer, key="conics_since_hyperbola", args=[answer]))
    if radius_squared > 0:
        transverse = sympy.sqrt(radius_squared)
        conjugate = sympy.sqrt(-conjugate_squared)
        vertices = [back(-transverse, ZERO), back(transverse, ZERO)]
        focal_offset = sympy.sqrt(radius_squared - conjugate_squared)
        foci = [back(-focal_offset, ZERO), back(focal_offset, ZERO)]
        directions = [
            (transverse, conjugate),
            (transverse, -conjugate),
        ]
    else:
        transverse = sympy.sqrt(conjugate_squared)
        conjugate = sympy.sqrt(-radius_squared)
        vertices = [back(ZERO, -transverse), back(ZERO, transverse)]
        focal_offset = sympy.sqrt(conjugate_squared - radius_squared)
        foci = [back(ZERO, -focal_offset), back(ZERO, focal_offset)]
        directions = [
            (conjugate, transverse),
            (-conjugate, transverse),
        ]
    ctx.result.add(Step(left=node, right=_points(vertices), key="graph_rt_info_vertices"))
    ctx.result.add(Step(left=node, right=_points(foci), key="graph_rt_info_foci"))

    origin_x, origin_y = center if center is not None else (ZERO, ZERO)
    lines = [
        _asymptote_equation(x, y, origin_x, origin_y, du, dv, first, second)
        for du, dv in directions
    ]
    ctx.result.add(
        Step(
            left=node,
            right=CoreNode.node(T.LIST, *[from_sympy(line) for line in lines]),
            key="graph_rt_info_asymptotes",
        )
    )
    return answer


def _asymptote_equation(
    x: sympy.Symbol,
    y: sympy.Symbol,
    origin_x: sympy.Expr,
    origin_y: sympy.Expr,
    du: sympy.Expr,
    dv: sympy.Expr,
    first: sympy.Matrix,
    second: sympy.Matrix,
) -> sympy.Eq:
    """Асимптота: прямая через центр с направлением ``(du, dv)`` новых осей."""
    delta_x = sympy.simplify(first[0] * du + second[0] * dv)
    delta_y = sympy.simplify(first[1] * du + second[1] * dv)
    if delta_x == 0:
        return sympy.Eq(x, origin_x)
    if delta_y == 0:
        return sympy.Eq(y, origin_y)
    slope = sympy.simplify(delta_y / delta_x)
    return sympy.Eq(y - origin_y, slope * (x - origin_x))


def _rotated_parabola(
    node: CoreNode,
    ctx: SolveContext,
    x: sympy.Symbol,
    y: sympy.Symbol,
    back: _Back,
    axis: sympy.Matrix,
    u: sympy.Symbol,
    v: sympy.Symbol,
    sq_is_u: bool,
    a_coeff: sympy.Expr,
    d_coeff: sympy.Expr,
    e_coeff: sympy.Expr,
    f_coeff: sympy.Expr,
) -> CoreNode:
    """Парабола после поворота: ``A sq² + D sq + E lin + F = 0``.

    Одно из собственных чисел формы равно нулю: квадрат есть по одной новой
    координате (``sq``), ось направлена по второй (``lin``). Полный квадрат
    выделяется сдвигом по ``sq``, вершина/фокус/директриса считаются в новых
    осях и возвращаются в исходные: ``axis`` -- орт оси параболы.
    """
    if e_coeff == 0:
        raise SolveError("уравнение не задаёт параболу (вырожденный случай)")

    square_at = sympy.simplify(-d_coeff / (2 * a_coeff))
    axis_at = sympy.simplify(d_coeff * d_coeff / (4 * a_coeff * e_coeff) - f_coeff / e_coeff)
    four_p = sympy.simplify(-e_coeff / a_coeff)
    p = four_p / 4

    canonical = sympy.Eq(
        (u - square_at) ** 2 if sq_is_u else (v - square_at) ** 2,
        four_p * ((v - axis_at) if sq_is_u else (u - axis_at)),
    )
    answer = from_sympy(canonical)
    ctx.result.add(Step(left=node, right=answer, key="conics_since_parabola", args=[answer]))

    vertex = back(square_at, axis_at) if sq_is_u else back(axis_at, square_at)
    focus = back(square_at, axis_at + p) if sq_is_u else back(axis_at + p, square_at)
    ctx.result.add(Step(left=node, right=vertex, key="graph_rt_info_vertex"))
    ctx.result.add(Step(left=node, right=focus, key="graph_rt_info_focus"))
    directrix = sympy.Eq(sympy.simplify(axis[0] * x + axis[1] * y), sympy.simplify(axis_at - p))
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
