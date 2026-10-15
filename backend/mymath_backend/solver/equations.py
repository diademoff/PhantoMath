"""Решение уравнений: линейные и квадратные, одно неизвестное.

Модуль зарегистрирован на узел ``EQUALS``. Уравнение сначала приводится к
виду ``p(x) = 0``, где ``p`` -- многочлен с рациональными коэффициентами;
степень определяет метод:

* степень 1 -- переносим свободный член, затем делим на коэффициент при ``x``;
* степень 2 -- дискриминант и корни (точные рациональные, если возможно,
  иначе через знак корня);
* степень 0 -- либо нет решений, либо решений бесконечно много (сейчас это
  ошибка: отдельного узла ответа для этих случаев ещё нет);
* степень 3 и выше -- не решается (модули многочленов идут следующими).

Ключи шагов берутся из ``truth/data/explanations.json``: ``move``,
``eq_linar_divide_both_sides``, ``eq_quad_solve_in_r``, заголовок
``eq_solve_short``. Разбор словаря -- ``truth/04-explanations.md``.
"""

from __future__ import annotations

from collections.abc import Callable
from fractions import Fraction
from math import isqrt

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .arithmetic import as_fraction, format_number
from .base import SolveContext, SolveError, SolveResult, Step, solver_for

# Многочлен: степень -> коэффициент. Нулевые коэффициенты не хранятся,
# поэтому пустой словарь -- это тождественный ноль.
Poly = dict[int, Fraction]

_HEADER = CoreRichText(type="eq_solve_short")
"""Заголовок шага: «Решите уравнение»."""

_MAX_DEGREE = 8
"""Потолок степени при построении многочлена: защита от роста вычислений."""

_POLY_ZERO: Poly = {}


def _add(a: Poly, b: Poly) -> Poly:
    out = dict(a)
    for degree, coeff in b.items():
        merged = out.get(degree, Fraction(0)) + coeff
        if merged == 0:
            out.pop(degree, None)
        else:
            out[degree] = merged
    return out


def _neg(a: Poly) -> Poly:
    return {degree: -coeff for degree, coeff in a.items()}


def _sub(a: Poly, b: Poly) -> Poly:
    return _add(a, _neg(b))


def _mul(a: Poly, b: Poly) -> Poly:
    out: Poly = {}
    for da, ca in a.items():
        for db, cb in b.items():
            degree = da + db
            out[degree] = out.get(degree, Fraction(0)) + ca * cb
            if out[degree] == 0:
                del out[degree]
    return out


def _scale(a: Poly, factor: Fraction) -> Poly:
    if factor == 0:
        return {}
    return {degree: coeff * factor for degree, coeff in a.items()}


def _pow(base: Poly, exponent: int) -> Poly:
    result: Poly = {0: Fraction(1)}
    for _ in range(exponent):
        result = _mul(result, base)
    return result


def _degree(poly: Poly) -> int:
    """Степень многочлена; у нулевого -- 0."""
    return max(poly) if poly else 0


def _coeff(poly: Poly, degree: int) -> Fraction:
    return poly.get(degree, Fraction(0))


def poly_of(node: CoreNode, var: str) -> Poly:
    """Привести выражение к многочлену по переменной ``var``.

    Буквы, кроме ``var``, и деление на выражение с ``var`` пока не
    поддерживаются: это отдельные модули (системы, дробно-рациональные).
    """
    if node.type is T.CONSTANT:
        value = as_fraction(node)
        return {} if value == 0 else {0: value}
    if node.type is T.VARIABLE:
        if node.value == var:
            return {1: Fraction(1)}
        raise SolveError(f"переменная {node.value!r} не поддерживается: одно неизвестное")
    if node.type in (T.ADD,):
        result: Poly = _POLY_ZERO
        for child in node.children:
            result = _add(result, poly_of(child, var))
        return result
    if node.type is T.SUBTRACT:
        if len(node.children) < 2:
            raise SolveError("вычитание без двух операндов")
        result = poly_of(node.children[0], var)
        for child in node.children[1:]:
            result = _sub(result, poly_of(child, var))
        return result
    if node.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT):
        result = {0: Fraction(1)}
        for child in node.children:
            result = _mul(result, poly_of(child, var))
        return result
    if node.type is T.DIVIDE:
        if len(node.children) != 2:
            raise SolveError("деление ожидает два операнда")
        numerator = poly_of(node.children[0], var)
        denominator = poly_of(node.children[1], var)
        if _degree(denominator) != 0 or _coeff(denominator, 0) == 0:
            raise SolveError("деление на выражение с неизвестным пока не решается")
        return _scale(numerator, Fraction(1) / _coeff(denominator, 0))
    if node.type is T.POWER:
        if len(node.children) != 2:
            raise SolveError("степень ожидает два операнда")
        base = poly_of(node.children[0], var)
        exponent_node = node.children[1]
        if exponent_node.type is not T.CONSTANT:
            raise SolveError("показатель степени должен быть числом")
        exponent = as_fraction(exponent_node)
        if exponent.denominator != 1 or exponent.numerator < 0:
            raise SolveError("показатель степени должен быть целым неотрицательным")
        if exponent.numerator > _MAX_DEGREE:
            raise SolveError("степень выше поддерживаемой")
        return _pow(base, exponent.numerator)
    if node.type is T.NEGATIVE:
        return _neg(poly_of(node.children[0], var))
    if node.type in (T.POSITIVE, T.BRACKET):
        return poly_of(node.children[0], var)
    raise SolveError(f"уравнение с узлом {node.type} не решается")


def _const(value: Fraction) -> CoreNode:
    return CoreNode.constant(format_number(value))


def _x_term(coefficient: Fraction, var: str) -> CoreNode:
    """Запись ``a*x``: единица не пишется, минус единица даёт ``-x``."""
    x = CoreNode.variable(var)
    if coefficient == 1:
        return x
    if coefficient == -1:
        return CoreNode(type=T.NEGATIVE, children=[x])
    return CoreNode(type=T.MULTIPLY_IMPLICIT, children=[_const(coefficient), x])


def _equation(var: str, right: CoreNode) -> CoreNode:
    return CoreNode(type=T.EQUALS, children=[CoreNode.variable(var), right])


def _perfect_sqrt(value: Fraction) -> Fraction | None:
    """Точный рациональный квадратный корень или ``None``."""
    if value < 0:
        return None
    num, den = isqrt(value.numerator), isqrt(value.denominator)
    if num * num == value.numerator and den * den == value.denominator:
        return Fraction(num, den)
    return None


def _sqrt_node(value: Fraction) -> CoreNode:
    """Корень как узел: точный, если извлекается, иначе ``ROOT2``."""
    exact = _perfect_sqrt(value)
    if exact is not None:
        return _const(exact)
    return CoreNode(type=T.ROOT2, children=[_const(value)])


def _linear_solution(
    node: CoreNode,
    lhs: CoreNode,
    rhs: CoreNode,
    var: str,
    poly: Poly,
    ctx: SolveContext,
    *,
    divide_first: bool = False,
) -> CoreNode:
    """Линейное уравнение: ``a x + b = 0`` -> ``x = -b/a``.

    Два способа записи шагов: перенести свободный член, затем делить
    (``divide_first=False``) — или сначала разделить обе части на ``a``,
    затем перенести (``divide_first=True``).
    """
    a, b = _coeff(poly, 1), _coeff(poly, 0)
    root = -b / a
    solution = _equation(var, _const(root))

    if divide_first:
        after_divide = CoreNode(
            type=T.EQUALS,
            children=[
                CoreNode(type=T.DIVIDE, children=[lhs, _const(a)]),
                CoreNode(type=T.DIVIDE, children=[rhs, _const(a)]),
            ],
        )
        ctx.result.add(
            Step(
                left=node,
                right=after_divide,
                key="eq_linar_divide_both_sides",
                args=[_const(a)],
            ),
            [_HEADER],
        )
        ctx.result.add(Step(left=after_divide, right=solution, key="move"), [_HEADER])
        return solution

    after_move = CoreNode(type=T.EQUALS, children=[_x_term(a, var), _const(-b)])
    already = poly_of(lhs, var) == {1: a} and poly_of(rhs, var) == {0: -b}

    left = node
    if b != 0 and not already:
        ctx.result.add(Step(left=node, right=after_move, key="move"), [_HEADER])
        left = after_move
    if a != 1:
        ctx.result.add(
            Step(
                left=left,
                right=solution,
                key="eq_linar_divide_both_sides",
                args=[_const(a)],
            ),
            [_HEADER],
        )
    return solution


def _quadratic_solution(
    node: CoreNode, var: str, poly: Poly, ctx: SolveContext, *, factoring: bool = False
) -> CoreNode:
    """Квадратное уравнение: дискриминант и корни.

    ``factoring`` выбирает способ: разложение на множители вместо формулы
    (корни те же, меняется только пояснение шага).
    """
    a, b, c = _coeff(poly, 2), _coeff(poly, 1), _coeff(poly, 0)
    discriminant = b * b - 4 * a * c
    if discriminant < 0:
        raise SolveError(
            "квадратное уравнение не имеет действительных корней", "eq_quad_solve_complex"
        )

    exact = _perfect_sqrt(discriminant)
    if factoring and exact is None:
        raise SolveError("разложение на множители с рациональными корнями невозможно")
    if exact is not None:
        low = (-b - exact) / (2 * a)
        high = (-b + exact) / (2 * a)
        if low == high:
            solution = _equation(var, _const(low))
        else:
            solution = CoreNode.node(
                T.LIST, _equation(var, _const(low)), _equation(var, _const(high))
            )
    else:
        root = _sqrt_node(discriminant)
        solution = CoreNode.node(
            T.LIST,
            _equation(var, _quad_root(-b, root, 2 * a, plus=False)),
            _equation(var, _quad_root(-b, root, 2 * a, plus=True)),
        )

    key = "solve_by_factoring" if factoring else "eq_quad_solve_in_r"
    ctx.result.add(Step(left=node, right=solution, key=key), [_HEADER])
    return solution


def _quad_root(
    minus_b: Fraction, sqrt_node: CoreNode, denominator: Fraction, *, plus: bool
) -> CoreNode:
    """Корень квадратного уравнения по формуле с знаком корня."""
    if minus_b == 0:
        numerator = sqrt_node
    else:
        numerator = CoreNode(
            type=T.ADD if plus else T.SUBTRACT,
            children=[_const(minus_b), sqrt_node],
        )
    if denominator == 1:
        return numerator
    return CoreNode(type=T.FRACTION, children=[numerator, _const(denominator)])


@solver_for(T.EQUALS)
def solve_equation(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Решить уравнение с одним неизвестным.

    Возвращает узел ответа (``x = …`` или список таких узлов); шаги
    накоплены в ``ctx.result``. Нерешаемые случаи поднимают :class:`SolveError`.
    """
    ctx.require(
        len(node.children) == 2,
        "уравнение должно связывать две части",
    )
    ctx.require(
        len(ctx.variables) == 1,
        "поддерживается одно неизвестное: системы и параметры идут следующими",
    )
    var = ctx.variables[0]
    lhs, rhs = node.children

    poly = _sub(poly_of(lhs, var), poly_of(rhs, var))
    degree = _degree(poly)

    if degree == 0:
        # Уравнение не зависит от неизвестного: либо тождество, либо противоречие.
        key = "solutions_inf_many" if _coeff(poly, 0) == 0 else "false_statement_solve"
        ctx.result.add(Step(left=node, right=None, key=key))
        return CoreNode.empty()
    if degree == 1:
        return _linear_solution(node, lhs, rhs, var, poly, ctx)
    if degree == 2:
        return _quadratic_solution(node, var, poly, ctx)
    raise SolveError("уравнения выше второй степени пока не решаются")


def _run(
    node: CoreNode, variables: list[str], action: Callable[[CoreNode, SolveContext], CoreNode]
) -> SolveResult:
    """Выполнить стратегию в отдельном накопителе и вернуть готовый результат."""
    result = SolveResult()
    ctx = SolveContext(result=result, variables=list(variables))
    result.set_solution(action(node, ctx))
    return result


def solve_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """Способы решения уравнения: первый — основной, дальше — альтернативы.

    Линейное уравнение решается переносом и делением, а если коэффициент при
    ``x`` не единица и есть свободный член — ещё и делением до переноса.
    Квадратное — формулой и, если корни рациональны, разложением на множители.
    """
    if len(node.children) != 2 or len(variables) != 1:
        raise SolveError("поддерживается одно неизвестное")
    var = variables[0]
    lhs, rhs = node.children
    poly = _sub(poly_of(lhs, var), poly_of(rhs, var))
    degree = _degree(poly)

    if degree == 0:
        # Ответ — сам текст шага: решений либо нет, либо бесконечно много.
        special = SolveResult()
        special_ctx = SolveContext(result=special, variables=list(variables))
        key = "solutions_inf_many" if _coeff(poly, 0) == 0 else "false_statement_solve"
        special_ctx.result.add(Step(left=node, right=None, key=key))
        return [special]
    if degree == 1:
        methods = [_run(node, variables, lambda n, c: _linear_solution(n, lhs, rhs, var, poly, c))]
        a, b = _coeff(poly, 1), _coeff(poly, 0)
        already = poly_of(lhs, var) == {1: a} and poly_of(rhs, var) == {0: -b}
        # Второй способ — сначала разделить обе части на коэффициент; он
        # отличается от первого, только если есть что переносить и делить.
        if a != 1 and b != 0 and not already:
            methods.append(
                _run(
                    node,
                    variables,
                    lambda n, c: _linear_solution(n, lhs, rhs, var, poly, c, divide_first=True),
                )
            )
        return methods
    if degree == 2:
        methods = [_run(node, variables, lambda n, c: _quadratic_solution(n, var, poly, c))]
        a, b, c = _coeff(poly, 2), _coeff(poly, 1), _coeff(poly, 0)
        if _perfect_sqrt(b * b - 4 * a * c) is not None:
            methods.append(
                _run(
                    node,
                    variables,
                    lambda n, c: _quadratic_solution(n, var, poly, c, factoring=True),
                )
            )
        return methods
    raise SolveError("уравнения выше второй степени пока не решаются")


__all__ = [
    "Poly",
    "poly_of",
    "solve_equation",
    "solve_methods",
]
