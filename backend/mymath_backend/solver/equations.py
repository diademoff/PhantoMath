"""Решение уравнений: линейные, квадратные и рациональные, одно неизвестное.

Модуль зарегистрирован на узел ``EQUALS``. Уравнение сначала приводится к
виду ``p(x) = 0``, где ``p`` -- многочлен с рациональными коэффициентами;
степень определяет метод:

* степень 1 -- переносим свободный член, затем делим на коэффициент при ``x``;
* степень 2 -- дискриминант и корни (точные рациональные, если возможно,
  иначе через знак корня);
* степень 0 -- либо нет решений, либо решений бесконечно много;
* степень 3 и выше -- разложение на множители (``solve_by_factoring``),
  корни берёт sympy (только действительные, по возрастанию).

Если многочлен не строится, а неизвестное стоит в знаменателе, уравнение
решается как **рациональное**: приводится к виду ``числитель / знаменатель =
0``, решается числитель, корни-полюсы исключаются. Уравнение с квадратным
корнем решается как **иррациональное**: обе части возводятся в квадрат,
посторонние корни отсеиваются подстановкой. Уравнение с логарифмом или
степенью решается как **показательное/логарифмическое**: части приводятся к
общему основанию, корни проверяются на области определения.

Ключи шагов: ``move``, ``eq_linar_divide_both_sides``,
``eq_quad_solve_in_r``, заголовок ``eq_solve_short``.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from fractions import Fraction
from math import gcd, isqrt

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from ..results import CoreSolverVerticalResult
from . import quadratic_cards
from .arithmetic import as_fraction, format_number, number_of
from .base import (
    SolveContext,
    SolveError,
    SolveResult,
    Step,
    UndefinedError,
    route,
    solver_for,
)
from .domain import add_restriction_steps, restriction_range_card
from .methods import method_provider, methods_for
from .sympy_bridge import from_sympy, to_sympy

# Многочлен: степень -> коэффициент. Нулевые коэффициенты не хранятся,
# поэтому пустой словарь -- это тождественный ноль.
Poly = dict[int, Fraction]

_HEADER = CoreRichText(type="eq_solve_short")
"""Заголовок шага: «Решите уравнение»."""


class _MethodTitleResult(SolveResult):
    """Карточка, чей заголовок способа требует аргумента.

    ``SolveResult.header`` хранит только ключ, а ``CoreRichText`` заголовка
    может нести аргументы; переопределяем сборку, чтобы подпись способа
    отрисовалась полностью (``find_slope_and_y_intercept(y)``).
    """

    __slots__ = ("title",)

    def __init__(self, title: CoreRichText) -> None:
        """Создать карточку с готовым заголовком способа."""
        super().__init__(header=title.type)
        self.title = title

    def to_vertical(self) -> CoreSolverVerticalResult:
        """Собрать вертикальный результат, подменив заголовок способа."""
        vertical = super().to_vertical()
        vertical.header = self.title
        return vertical


_MAX_DEGREE = 16
"""Потолок степени при построении многочлена: защита от роста вычислений."""

_MAX_SQUARINGS = 4
"""Потолок возведений в квадрат у иррационального уравнения: по одному на радикал."""

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
        raise SolveError(
            f"переменная {node.value!r} не поддерживается: одно неизвестное", "eq_param"
        )
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
    if node.type in (T.DIVIDE, T.FRACTION):
        if len(node.children) != 2:
            raise SolveError("деление ожидает два операнда")
        numerator = poly_of(node.children[0], var)
        denominator = poly_of(node.children[1], var)
        if _degree(denominator) != 0:
            raise SolveError("деление на выражение с неизвестным пока не решается")
        if _coeff(denominator, 0) == 0:
            # Деление на ноль — не «пока не решается», а определённый ответ
            # «Не определено» с пояснением div_with_zero.
            raise UndefinedError(
                "деление на ноль", "div_with_zero", explanation_args=[CoreNode.constant("0")]
            )
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


def _const(value: Fraction | int) -> CoreNode:
    return CoreNode.constant(format_number(Fraction(value)))


def _not_in_reals(var: str) -> CoreNode:
    """``x ∉ ℝ``: ответ, когда действительных корней нет."""
    return CoreNode.node(T.ELEMENT_NOT_OF, CoreNode.variable(var), CoreNode.variable("ℝ"))


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


def _ordered_polynomial(coefficients: list[sympy.Expr], var: str) -> CoreNode:
    """Teaching form: descending powers, not SymPy's positive-terms-first order."""
    expression: CoreNode | None = None
    for index, coefficient in enumerate(coefficients):
        if coefficient == 0:
            continue
        degree = len(coefficients) - index - 1
        negative = coefficient.is_negative is True
        magnitude = -coefficient if negative else coefficient
        term = from_sympy(magnitude)
        if degree:
            base = CoreNode.variable(var)
            if degree > 1:
                base = CoreNode.node(T.POWER, base, CoreNode.constant(str(degree)))
            term = (
                base
                if magnitude == 1
                else CoreNode.node(
                    T.MULTIPLY_IMPLICIT,
                    CoreNode.node(T.BRACKET, term) if term.type in (T.ADD, T.SUBTRACT) else term,
                    base,
                )
            )
        elif negative and term.type in (T.ADD, T.SUBTRACT):
            term = CoreNode.node(T.BRACKET, term)
        if expression is None:
            expression = CoreNode.node(T.NEGATIVE, term) if negative else term
        else:
            expression = CoreNode.node(T.SUBTRACT if negative else T.ADD, expression, term)
    return expression if expression is not None else CoreNode.constant("0")


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


def _simple_side(node: CoreNode, var: str) -> tuple[Fraction, Fraction] | None:
    """``(a, b)`` for a side written as at most one ``a*x`` term and one constant, else ``None``."""
    found: list[tuple[str, Fraction]] = []

    def visit(part: CoreNode, sign: int) -> bool:
        if part.type is T.ADD or part.type is T.SUBTRACT:
            if len(part.children) != 2:
                return False
            second = -sign if part.type is T.SUBTRACT else sign
            return visit(part.children[0], sign) and visit(part.children[1], second)
        if part.type is T.NEGATIVE:
            return visit(part.children[0], -sign)
        if part.type is T.CONSTANT:
            found.append(("c", sign * as_fraction(part)))
            return True
        if part.type is T.VARIABLE and part.value == var:
            found.append(("x", Fraction(sign)))
            return True
        if part.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) and len(part.children) == 2:
            number, name = part.children
            negative = number.type is T.NEGATIVE and len(number.children) == 1
            if negative:
                number = number.children[0]
            if number.type is T.CONSTANT and name.type is T.VARIABLE and name.value == var:
                found.append(("x", (-sign if negative else sign) * as_fraction(number)))
                return True
        return False

    if (
        not visit(node, 1)
        or [k for k, _ in found].count("x") > 1
        or [k for k, _ in found].count("c") > 1
    ):
        return None
    return (
        sum((v for k, v in found if k == "x"), Fraction(0)),
        sum((v for k, v in found if k == "c"), Fraction(0)),
    )


def _plus(base: CoreNode, amount: Fraction, term: CoreNode) -> CoreNode:
    """``base + term`` for a positive amount, ``base - term`` for a negative one (|amount| term)."""
    return CoreNode.node(T.ADD if amount > 0 else T.SUBTRACT, base, term)


def _collect_key(b1: Fraction, b2: Fraction) -> str:
    """The app's name for the row that adds the two constants after the move."""
    if b1 > 0:
        return "calc_diff" if b2 < 0 else "sub"
    return "add" if b2 > 0 else "calc_sum"


def _difference_detail(moved: CoreNode, total: Fraction) -> SolveResult:
    """The app page for ``-1 - 5``: take out the minus, then add the magnitudes."""
    detail = SolveResult()
    parts = moved.children if moved.type in (T.ADD, T.SUBTRACT) else []
    values = [as_fraction(part) for part in parts if part.type is T.CONSTANT]
    if len(values) == 2 and total < 0:
        addends = CoreNode.node(T.ADD, _const(abs(values[0])), _const(abs(values[1])))
    else:
        addends = _const(abs(total))
    negated = CoreNode.node(T.NEGATIVE, addends)
    detail.add_group("extract_minus", Step(moved, negated, "extract_minus"))
    detail.add_group("calculate_short", Step(negated, _const(total), "add"))
    detail.set_solution(_const(total))
    return detail


def _has_unknown(node: CoreNode, var: str) -> bool:
    """Есть ли в поддереве неизвестное ``var`` (не переводимые узлы считаются содержащими)."""
    try:
        return bool(to_sympy(node).has(sympy.Symbol(var)))
    except SolveError:
        return True


def _rational_value(node: CoreNode) -> Fraction | None:
    """Рациональное значение числового узла или ``None``."""
    try:
        return number_of(node)
    except (SolveError, UndefinedError):
        return None


def _affine_side(node: CoreNode, var: str) -> tuple[Fraction, list[tuple[int, CoreNode]]] | None:
    """``a x + b`` для стороны уравнения: коэффициент при ``x`` и слагаемые ``b``.

    В отличие от :func:`_simple_side` свободный член остаётся **узлом**: у
    уравнения с иррациональной константой (``2x + 1 = 1/e``) его нельзя свести
    к дроби. ``None`` — сторона не «одно слагаемое с ``x`` плюс константы».
    """
    total = Fraction(0)
    terms: list[tuple[int, CoreNode]] = []

    def visit(part: CoreNode, sign: int) -> bool:
        nonlocal total
        if part.type in (T.ADD, T.SUBTRACT) and len(part.children) == 2:
            second = -sign if part.type is T.SUBTRACT else sign
            return visit(part.children[0], sign) and visit(part.children[1], second)
        if part.type is T.NEGATIVE and len(part.children) == 1:
            return visit(part.children[0], -sign)
        if part.type in (T.POSITIVE, T.BRACKET) and len(part.children) == 1:
            return visit(part.children[0], sign)
        if part.type is T.VARIABLE and part.value == var:
            total += sign
            return True
        if part.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) and len(part.children) == 2:
            for coefficient, name in (part.children, tuple(reversed(part.children))):
                if name.type is T.VARIABLE and name.value == var:
                    value = _rational_value(coefficient)
                    if value is not None:
                        total += sign * value
                        return True
        if not _has_unknown(part, var):
            terms.append((sign, part))
            return True
        return False

    if not visit(node, 1):
        return None
    return total, terms


def _side_constant_terms(node: CoreNode, var: str) -> list[tuple[int, CoreNode]]:
    """Свободные слагаемые стороны (``_affine_side`` не дал сторону — пусто)."""
    side = _affine_side(node, var)
    return [] if side is None else side[1]


def _terms_node(terms: list[tuple[int, CoreNode]]) -> CoreNode | None:
    """Собрать свободные слагаемые обратно в узел (``1/e - 1``), ``None`` если пусто."""
    current: CoreNode | None = None
    for sign, part in terms:
        if current is None:
            current = part if sign > 0 else CoreNode.node(T.NEGATIVE, part)
        else:
            current = CoreNode.node(T.ADD if sign > 0 else T.SUBTRACT, current, part)
    return current


def _negative_power(exponent: CoreNode) -> int | None:
    """Положительный показатель ``n`` для ``x^(-n)``, иначе ``None``."""
    while exponent.type in (T.BRACKET, T.POSITIVE) and len(exponent.children) == 1:
        exponent = exponent.children[0]
    if exponent.type is T.NEGATIVE and len(exponent.children) == 1:
        inner = _rational_value(exponent.children[0])
        if inner is not None and inner.denominator == 1 and inner > 0:
            return int(inner)
        return None
    value = _rational_value(exponent)
    if value is not None and value.denominator == 1 and value < 0:
        return int(-value)
    return None


def _flip_negative_powers(node: CoreNode) -> CoreNode:
    """``a^(-n)`` -> ``1 / a^n``: строка ``pow_flip_one`` для уравнения с ``e^(-1)``."""
    if node.type is T.POWER and len(node.children) == 2:
        base, exponent = node.children
        power = _negative_power(exponent)
        if power is not None:
            denominator = base if power == 1 else CoreNode.node(T.POWER, base, _const(power))
            return CoreNode.node(T.FRACTION, _const(1), denominator)
        return CoreNode.node(T.POWER, _flip_negative_powers(base), _flip_negative_powers(exponent))
    if node.children:
        return CoreNode(
            type=node.type,
            children=[_flip_negative_powers(child) for child in node.children],
            value=node.value,
        )
    return node


def _ratio_node(value: Fraction) -> CoreNode:
    """Рациональное число как узел: целое — константа, иначе дробь со знаком."""
    if value.denominator == 1:
        return _const(value)
    fraction = CoreNode.node(T.FRACTION, _const(abs(value.numerator)), _const(value.denominator))
    return CoreNode.node(T.NEGATIVE, fraction) if value < 0 else fraction


def _scale_denominator(denominator: CoreNode, factor: int) -> CoreNode:
    """``denominator * factor``: число перемножаем, иррациональность пишем как ``2·e``."""
    value = _rational_value(denominator)
    if value is not None:
        return _ratio_node(value * factor)
    if factor == 1:
        return denominator
    return CoreNode.node(T.MULTIPLY, _const(factor), denominator)


def _divide_node(node: CoreNode, divisor: int) -> CoreNode:
    """Разделить обе части на число: ``(1/e - 1)/2 = 1/(2e) - 1/2``.

    Сумма распределяется, знаменатель дроби домножается — так строка
    ``eq_linear_div`` выглядит у уравнения с иррациональной константой.
    """
    if node.type in (T.ADD, T.SUBTRACT):
        return CoreNode.node(node.type, *[_divide_node(child, divisor) for child in node.children])
    if node.type is T.NEGATIVE and len(node.children) == 1:
        return CoreNode.node(T.NEGATIVE, _divide_node(node.children[0], divisor))
    if node.type is T.BRACKET and len(node.children) == 1:
        return _divide_node(node.children[0], divisor)
    if node.type is T.FRACTION and len(node.children) == 2:
        numerator, denominator = node.children
        return CoreNode.node(T.FRACTION, numerator, _scale_denominator(denominator, divisor))
    value = _rational_value(node)
    if value is not None:
        return _ratio_node(value / divisor)
    return CoreNode.node(T.FRACTION, node, _const(divisor))


def _symbolic_linear_rows(
    node: CoreNode, variables: list[str], ctx: SolveContext
) -> CoreNode | None:
    """Линейное уравнение с иррациональной константой: ``2x + 1 = 1/e`` -> ``x = 1/(2e) - 1/2``.

    Обычный путь (:func:`poly_of`) требует рациональных коэффициентов, поэтому
    ``ln(2x+1) = -1`` после перехода к степени давал график и приближение.
    Здесь свободные члены остаются формулами: отрицательная степень
    переворачивается (``pow_flip_one``), константа переносится, обе части делятся.
    """
    if len(variables) != 1 or node.type is not T.EQUALS or len(node.children) != 2:
        return None
    var = variables[0]
    lhs, rhs = node.children
    left = _affine_side(lhs, var)
    right = _affine_side(rhs, var)
    if left is None or right is None:
        return None
    a1, _terms1 = left
    a2, _terms2 = right
    if a2 != 0:
        # переносить неизвестное из правой части — отдельный (общий) сценарий
        return None
    if a1 == 0:
        return None
    current, cur_lhs, cur_rhs = node, lhs, rhs
    flipped_lhs, flipped_rhs = _flip_negative_powers(lhs), _flip_negative_powers(rhs)
    if not flipped_lhs.structural_eq(lhs) or not flipped_rhs.structural_eq(rhs):
        flipped = CoreNode.node(T.EQUALS, flipped_lhs, flipped_rhs)
        ctx.result.add_group(
            "pow_exp_msg", Step(node, flipped, "pow_flip_one", [_const(Fraction(-1))])
        )
        current, cur_lhs, cur_rhs = flipped, flipped_lhs, flipped_rhs
    b1 = _terms_node(_side_constant_terms(cur_lhs, var))
    b2 = _terms_node(_side_constant_terms(cur_rhs, var))
    if b1 is not None:
        after_right = _subtract_node(b2, b1)
        after = CoreNode.node(T.EQUALS, _x_term(a1, var), after_right)
        ctx.result.add_group(
            "rel_move_right_const_msg", Step(current, after, "rel_move_right_const_eq")
        )
        current = after
    right_node = _terms_node(_side_constant_terms(current.children[1], var)) or _const(Fraction(0))
    if a1 == 1:
        return current
    answer = CoreNode.node(T.EQUALS, CoreNode.variable(var), _divide_node(right_node, int(a1)))
    ctx.result.add_group(
        "divide_both_sides",
        Step(current, answer, "eq_linear_div", [_const(a1)]),
    )
    return answer


def _subtract_node(left: CoreNode | None, right: CoreNode) -> CoreNode:
    """``left - right`` узлами: ``None - b = -b``, ``a - (-b) = a + b``."""
    if left is None:
        return CoreNode.node(T.NEGATIVE, right)
    if right.type is T.NEGATIVE and len(right.children) == 1:
        return CoreNode.node(T.ADD, left, right.children[0])
    return CoreNode.node(T.SUBTRACT, left, right)


def _linear_rows(
    node: CoreNode,
    lhs: CoreNode,
    rhs: CoreNode,
    var: str,
    ctx: SolveContext,
    *,
    relation: T = T.EQUALS,
    flipped: T | None = None,
) -> CoreNode | None:
    """The app rows for ``a1 x + b1 = a2 x + b2``: move, collect, calculate, divide.

    ``relation`` is ``=`` or an inequality sign (``flipped`` is the sign after dividing by a
    negative number); inequalities are produced for an unknown on the left only.
    Returns ``None`` when a side is not a plain ``a x + b`` so the general path is used.
    """
    left, right = _simple_side(lhs, var), _simple_side(rhs, var)
    if left is None or right is None:
        return None
    (a1, b1), (a2, b2) = left, right
    if a1 == 0 or a1 == a2:
        return None
    eq = CoreNode.node
    equality = relation is T.EQUALS
    # The app names the rows of an equation with the ``_eq`` suffix; inequalities keep
    # the old keys (they are solved by a different card).
    move_key = "rel_move_right_const_eq" if equality else "rel_move_right_const"
    x = CoreNode.variable(var)
    current, stages = node, []
    cur_l, cur_r = lhs, rhs
    if a2 != 0:  # move the unknown to the left
        term = _x_term(abs(a2), var)
        after_l = eq(T.SUBTRACT if a2 > 0 else T.ADD, cur_l, term)
        after_r = _const(b2)
        balanced = eq(
            relation,
            eq(T.SUBTRACT if a2 > 0 else T.ADD, cur_l, term),
            eq(T.SUBTRACT if a2 > 0 else T.ADD, cur_r, term),
        )
        detail = SolveResult()
        detail.add_group("rel_swap_left_var", Step(current, balanced, "rel_swap_left_var"))
        after = eq(relation, after_l, after_r)
        removed = "sub_with_self_remove_alg" if equality else "remove_opposites"
        detail.add_group("remove_opposites", Step(balanced, after, removed))
        detail.set_solution(after)
        stages.append(Step(current, after, "rel_move_left_var", subresult=detail))
        current, cur_l, cur_r = after, after_l, after_r
    if equality and a2 == 0 and a1 == 1 and b1 != 0 and b2 == 0:
        # ``x + b = 0``: The app moves the constant and simplifies both sides as two rows.
        k = _const(abs(b1))
        sign = T.SUBTRACT if b1 > 0 else T.ADD
        balanced = eq(relation, eq(sign, cur_l, k), eq(sign, cur_r, k))
        after = eq(relation, x, _const(-b1))
        ctx.result.add_group(
            "rel_move_right_const_msg", Step(current, balanced, "rel_swap_right_const")
        )
        ctx.result.add_group(
            ["remove_opposites", CoreRichText(type="remove_zero", args=[_const(Fraction(0))])],
            Step(balanced, after, "sub_with_self_remove_num"),
            Step(balanced, after, "add_with_zero", [_const(Fraction(0))]),
        )
        return after
    if b1 != 0:  # move the constant to the right
        k = _const(abs(b1))
        sign = T.SUBTRACT if b1 > 0 else T.ADD
        x_part = _x_term(a1, var)
        if a2 != 0:
            x_part = eq(T.SUBTRACT if a2 > 0 else T.ADD, x_part, _x_term(abs(a2), var))
        after_r = _const(-b1) if b2 == 0 else _plus(_const(b2), -b1, k)
        balanced = eq(relation, eq(sign, cur_l, k), eq(sign, cur_r, k))
        after = eq(relation, x_part, after_r)
        detail = SolveResult()
        detail.add_group("rel_swap_right_const", Step(current, balanced, "rel_swap_right_const"))
        detail.add_group(
            "remove_opposites",
            Step(
                balanced,
                after,
                "sub_with_self_remove_num" if equality else "remove_opposites",
            ),
        )
        detail.set_solution(after)
        # ``x + b = c`` has no division row; a zero right side has no pair to remove
        flat = equality and (b2 == 0 or (a1 == 1 and a2 == 0))
        stages.append(Step(current, after, move_key, subresult=None if flat else detail))
        current, cur_l, cur_r = after, x_part, after_r
    coefficient, total = a1 - a2, b2 - b1
    if a2 != 0 or b1 != 0:
        header = "move" if len(stages) > 1 or a2 != 0 else "rel_move_right_const_msg"
        ctx.result.add_group(header, *stages)
    two_terms = b1 != 0 and b2 != 0
    if a2 != 0:
        collected = eq(relation, _x_term(coefficient, var), cur_r)
        grouped = eq(
            relation,
            eq(
                T.MULTIPLY_IMPLICIT,
                eq(T.BRACKET, eq(T.SUBTRACT if a2 > 0 else T.ADD, _const(a1), _const(abs(a2)))),
                x,
            ),
            cur_r,
        )
        explicit = eq(relation, eq(T.MULTIPLY_IMPLICIT, _const(coefficient), x), cur_r)
        detail = SolveResult()
        if equality and a2 < 0:
            # ``-x - 2x``: the missing coefficient of ``-x`` is written as ``-1`` first
            negated = eq(
                relation,
                eq(
                    T.SUBTRACT,
                    eq(T.MULTIPLY_IMPLICIT, _const(Fraction(-1)), x),
                    _x_term(abs(a2), var),
                ),
                cur_r,
            )
            detail.add_group(
                "sum_suffix_add_neg_one",
                Step(current, negated, "sum_suffix_add_neg_one", [_const(Fraction(-1))]),
            )
            detail.add_group("sum_suffix_detail", Step(negated, grouped, "sum_suffix_detail"))
            detail.add_group("calculate_short", Step(grouped, explicit, "calc_diff"))
        elif equality:
            removed_term = _x_term(abs(a2), var)
            signed_first = eq(
                relation,
                eq(
                    T.SUBTRACT if a1 > 0 else T.ADD,
                    eq(
                        T.MULTIPLY_IMPLICIT,
                        _const(Fraction(a1 if abs(a1) == 1 else abs(a1))),
                        x,
                    ),
                    removed_term,
                ),
                cur_r,
            )
            if a1 < 0:
                detail.add_group(
                    "sum_suffix_add_neg_one",
                    Step(current, signed_first, "sum_suffix_add_neg_one", [_const(Fraction(-1))]),
                )
                detail.add_group(
                    "sum_suffix_detail", Step(signed_first, grouped, "sum_suffix_detail")
                )
                detail.add_group(
                    "calculate_short",
                    Step(grouped, explicit, "calc_diff" if coefficient < 0 else "add"),
                )
            elif a1 == 1 and coefficient < 0:
                detail.add_group(
                    "sum_suffix_add_one",
                    Step(current, signed_first, "sum_suffix_add_one", [_const(Fraction(1))]),
                )
                detail.add_group(
                    "sum_suffix_sub_detail",
                    Step(signed_first, grouped, "sum_suffix_sub_detail"),
                )
                detail.add_group("calculate_short", Step(grouped, explicit, "calc_diff"))
            else:
                detail.add_group(
                    "sum_suffix_sub_detail", Step(current, grouped, "sum_suffix_sub_detail")
                )
                detail.add_group("calculate_short", Step(grouped, explicit, "sub"))
            if coefficient == 1:
                detail.add_group(
                    "sum_suffix_del_one",
                    Step(explicit, collected, "sum_suffix_del_one", [_const(Fraction(1))]),
                )
        else:
            detail_key = "sum_suffix_sub_detail" if a2 > 0 else "sum_suffix_add_detail"
            detail.add_group(detail_key, Step(current, grouped, detail_key))
            detail.add_group("calculate_short", Step(grouped, explicit, "calculate_short"))
            if coefficient == 1:
                detail.add_group(
                    "sum_suffix_del_one_short",
                    Step(explicit, collected, "sum_suffix_del_one_short", [_const(Fraction(1))]),
                )
        detail.set_solution(collected)
        sums = [Step(current, collected, "sum_suffix", subresult=detail)]
        current = collected
        if two_terms:
            done = eq(relation, _x_term(coefficient, var), _const(total))
            if b2 < 0 < b1:  # -1 - 5: The app names it "calculate the difference" with a detail
                sums.append(
                    Step(
                        current,
                        done,
                        "calc_diff",
                        subresult=_difference_detail(cur_r, total),
                    )
                )
            else:
                sums.append(Step(current, done, _collect_key(b1, b2)))
            current = done
        ctx.result.add_group(
            ["sum_suffix", "calculate_short"] if two_terms else ["sum_suffix"], *sums
        )
    elif two_terms:
        done = eq(relation, _x_term(coefficient, var), _const(total))
        collect_key = _collect_key(b1, b2)
        ctx.result.add_group(
            "calculate_short",
            Step(
                current,
                done,
                collect_key,
                subresult=(
                    _difference_detail(cur_r, total) if collect_key == "calc_diff" else None
                ),
            ),
        )
        current = done
    divide_key = "eq_linear_div"
    final = relation
    if relation is not T.EQUALS:
        divide_key = "ineq_linear_div_neg" if coefficient < 0 else "ineq_linear_div"
        final = flipped if coefficient < 0 and flipped is not None else relation
    solution = eq(final, CoreNode.variable(var), _const(total / coefficient))
    if equality and coefficient != 1 and b2 == 0:
        # the moved side was zero, so the app shows the division as a single row
        ctx.result.add_group(
            "divide_both_sides",
            Step(current, solution, divide_key, [_const(coefficient)]),
        )
        return solution
    if coefficient != 1:
        divided = eq(
            final,
            eq(T.FRACTION, current.children[0], _const(coefficient)),
            eq(T.FRACTION, current.children[1], _const(coefficient)),
        )
        if equality:
            # Промежуточная строка должна сохранять корень: x = 4/2, а не x = 4.
            by_self = eq(
                final,
                x,
                eq(T.FRACTION, current.children[1], _const(coefficient)),
            )
            last_key = "quotient" if (total / coefficient).denominator == 1 else "div_to_frac"
            # nothing was moved and the root is a fraction: The app shows two flat rows
            if not stages and last_key == "div_to_frac":
                ctx.result.add_group(
                    "divide_both_sides",
                    Step(current, divided, divide_key, [_const(coefficient)]),
                )
                ctx.result.add_group(
                    "divide",
                    Step(divided, by_self, "div_with_self", [_const(Fraction(1))]),
                    Step(by_self, solution, last_key),
                )
                return solution
            detail = SolveResult()
            detail.add_group(
                CoreRichText(type=divide_key, args=[_const(coefficient)]),
                Step(current, divided, divide_key, [_const(coefficient)]),
            )
            rows = [Step(divided, by_self, "div_with_self", [_const(Fraction(1))])]
            by_sign = by_self
            if total < 0 or coefficient < 0:
                numerator, denominator = abs(total), abs(coefficient)
                fraction = eq(T.FRACTION, _const(numerator), _const(denominator))
                negative = (total < 0) != (coefficient < 0)
                by_sign = eq(final, x, eq(T.NEGATIVE, fraction) if negative else fraction)
                sign_key = (
                    "div_neg_neg"
                    if total < 0 and coefficient < 0
                    else ("div_pos_neg" if total > 0 else "div_neg_pos")
                )
                rows.append(
                    Step(by_self, by_sign, sign_key, [CoreNode.variable("−" if negative else "+")])
                )
            quotient_key = "quotient" if (total / coefficient).denominator == 1 else "div_to_frac"
            rows.append(Step(by_sign, solution, quotient_key))
            detail.add_group("divide", *rows)
            detail.set_solution(solution)
            ctx.result.add_group(
                "divide_both_sides",
                Step(
                    current,
                    solution,
                    divide_key,
                    [_const(coefficient)],
                    subresult=detail,
                ),
            )
            return solution
        if relation is not T.EQUALS and coefficient < 0 < total:
            # the flip is its own row, then the quotient is explained page by page
            by_self = eq(
                final,
                CoreNode.variable(var),
                eq(T.FRACTION, current.children[1], _const(coefficient)),
            )
            by_sign = eq(
                final,
                CoreNode.variable(var),
                eq(T.NEGATIVE, eq(T.FRACTION, _const(total), _const(-coefficient))),
            )
            ctx.result.add_group(
                "divide_both_sides", Step(current, divided, divide_key, [_const(coefficient)])
            )
            ctx.result.add_group(
                "divide",
                Step(divided, by_self, "div_with_self", [_const(Fraction(1))]),
                Step(by_self, by_sign, "div_pos_neg", [CoreNode.variable("−")]),
                Step(by_sign, solution, "quotient"),
            )
            return solution
        detail = SolveResult()
        detail.add_group(
            CoreRichText(type=divide_key, args=[_const(coefficient)]),
            Step(current, divided, divide_key, [_const(coefficient)]),
        )
        detail.add_group("divide", Step(divided, solution, "divide"))
        detail.set_solution(solution)
        ctx.result.add_group(
            "divide_both_sides",
            Step(
                current,
                solution,
                divide_key,
                [_const(coefficient)],
                subresult=detail,
            ),
        )
    return solution


def _multiply_first(node: CoreNode, var: str) -> SolveResult | None:
    """``x / d = c`` with ``c > 0``: multiply both sides by ``d`` at once (the first card)."""
    fraction, number = node.children
    d = fraction.children[1]
    if number.type is not T.CONSTANT or not (number.value or "").isdigit() or number.value == "0":
        return None
    x = CoreNode.variable(var)
    eq = CoreNode.node
    scaled = eq(T.EQUALS, eq(T.MULTIPLY, d, fraction), eq(T.MULTIPLY, d, number))
    cleared = eq(T.EQUALS, x, eq(T.MULTIPLY, d, number))
    value = _const(Fraction(int(d.value or 1) * int(number.value or 0)))
    solution = _equation(var, value)
    result = SolveResult()
    result.add_group("multiply_both_sides", Step(node, scaled, "eq_mul_direct_denom", [d]))
    result.add_group(
        ["frac_reduce_frac", "calculate_short"],
        Step(scaled, cleared, "frac_reduce_out", [d]),
        Step(cleared, solution, "mul"),
    )
    result.set_solution(solution)
    return result


def _unknown_over_number(node: CoreNode, var: str, variables: list[str]) -> SolveResult | None:
    """``x / d = c`` for integers ``d > 1`` and ``c != 0``: move the constant, multiply both sides.

    The rows shown; every other linear equation takes the general path.
    """
    fraction, number = node.children
    if not (
        fraction.type is T.FRACTION
        and fraction.children[0].type is T.VARIABLE
        and fraction.children[0].value == var
        and fraction.children[1].type is T.CONSTANT
        and fraction.children[1].value is not None
        and fraction.children[1].value.isdigit()
        and int(fraction.children[1].value) > 1
    ):
        return None
    try:
        known = to_sympy(number)
    except SolveError:
        return None
    if not (known.is_Rational and known != 0):
        return None
    d = fraction.children[1]
    c = Fraction(int(known.p), int(known.q))
    eq = CoreNode.node
    x = CoreNode.variable(var)
    zero = CoreNode.constant("0")
    shifted = eq(T.SUBTRACT if c > 0 else T.ADD, fraction, _const(abs(c)))
    moved = eq(T.EQUALS, shifted, zero)
    balanced = eq(
        T.EQUALS,
        eq(T.SUBTRACT if c > 0 else T.ADD, fraction, _const(abs(c))),
        eq(T.SUBTRACT if c > 0 else T.ADD, number, _const(abs(c))),
    )
    solution = _equation(var, _const(c * int(d.value or 1)))

    result = SolveResult()
    swap = SolveResult()
    swap.add_group("rel_swap_left_const", Step(node, balanced, "rel_swap_left_const"))
    swap.add_group(
        "remove_opposites", Step(balanced, moved, "sub_with_self_num", [_const(Fraction(0))])
    )
    swap.set_solution(moved)
    result.add_group(
        "rel_move_left_const_msg", Step(node, moved, "rel_move_left_const", subresult=swap)
    )
    scaled = eq(
        T.EQUALS,
        eq(T.MULTIPLY, eq(T.BRACKET, shifted), d),
        eq(T.MULTIPLY, zero, d),
    )
    cleared = eq(
        T.EQUALS,
        eq(T.SUBTRACT if c > 0 else T.ADD, x, _const(abs(c) * int(d.value or 1))),
        zero,
    )
    multiply = SolveResult()
    multiply.add_group(
        CoreRichText(type="eq_mul_direct_denom", args=[d]),
        Step(moved, scaled, "eq_mul_direct_denom", [d]),
    )
    distributed = eq(
        T.EQUALS,
        eq(
            T.SUBTRACT if c > 0 else T.ADD,
            eq(T.MULTIPLY, shifted, d),
            eq(T.MULTIPLY, _const(abs(c)), d),
        ),
        eq(T.MULTIPLY, zero, d),
    )
    without_zero = eq(
        T.EQUALS,
        eq(
            T.SUBTRACT if c > 0 else T.ADD,
            eq(T.MULTIPLY, shifted, d),
            eq(T.MULTIPLY, _const(abs(c)), d),
        ),
        zero,
    )
    multiply.add_group(
        "mul_bracket",
        Step(scaled, distributed, "mul_bracket", [d]),
        Step(distributed, without_zero, "mul_with_zero", [_const(Fraction(0))]),
    )
    multiply.add_group(
        CoreRichText(type="frac_reduce_out", args=[d]),
        Step(without_zero, cleared, "frac_reduce_out", [d]),
    )
    multiply.add_group(
        "calculate_short",
        Step(cleared, solution, "mul"),
    )
    multiply.set_solution(solution)
    result.add_group(
        "multiply_both_sides",
        Step(moved, solution, "eq_mul_direct_denom", [d], subresult=multiply),
    )
    result.set_solution(solution)
    return result


def _bracket_times_number(node: CoreNode, var: str) -> SolveResult | None:
    """``k (x + m) = c`` with integers, ``k > 1`` dividing ``c``: divide, move ``m``, calculate.

    The three rows the card shows; other bracket forms take the general path.
    """
    left, right = node.children
    if not (
        left.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT)
        and right.type is T.CONSTANT
        and left.children[0].type is T.CONSTANT
        and left.children[1].type is T.BRACKET
    ):
        return None
    inner = left.children[1].children[0]
    if not (
        inner.type in (T.ADD, T.SUBTRACT)
        and inner.children[0].type is T.VARIABLE
        and inner.children[0].value == var
        and inner.children[1].type is T.CONSTANT
    ):
        return None
    try:
        k, c, m = (int(n.value or "x") for n in (left.children[0], right, inner.children[1]))
    except ValueError:
        return None
    if k < 2 or m == 0 or c % k:
        return None
    eq = CoreNode.node
    sign = T.SUBTRACT if inner.type is T.ADD else T.ADD
    divided = eq(T.EQUALS, inner, _const(Fraction(c // k)))
    shift = _const(Fraction(m))
    balanced = eq(T.EQUALS, eq(sign, inner, shift), eq(sign, divided.children[1], shift))
    moved = eq(T.EQUALS, CoreNode.variable(var), eq(sign, divided.children[1], shift))
    value = c // k - m if inner.type is T.ADD else c // k + m
    solution = _equation(var, _const(Fraction(value)))

    result = SolveResult()
    divide = SolveResult()
    divide.add_group(
        CoreRichText(type="eq_linear_div", args=[_const(Fraction(k))]),
        Step(node, divided, "eq_linear_div", [_const(Fraction(k))]),
    )
    divide.add_group(
        "divide",
        Step(
            eq(
                T.EQUALS,
                eq(T.FRACTION, node.children[0], _const(Fraction(k))),
                eq(T.FRACTION, node.children[1], _const(Fraction(k))),
            ),
            eq(T.EQUALS, inner, eq(T.FRACTION, _const(Fraction(c)), _const(Fraction(k)))),
            "div_with_self",
            [_const(Fraction(1))],
        ),
        Step(
            eq(T.EQUALS, inner, eq(T.FRACTION, _const(Fraction(c)), _const(Fraction(k)))),
            divided,
            "quotient",
        ),
    )
    divide.set_solution(divided)
    result.add_group(
        "divide_both_sides",
        Step(node, divided, "eq_linear_div", [_const(Fraction(k))], subresult=divide),
    )
    swap = SolveResult()
    swap.add_group("rel_swap_right_const", Step(divided, balanced, "rel_swap_right_const"))
    swap.add_group("remove_opposites", Step(balanced, moved, "sub_with_self_remove_num"))
    swap.set_solution(moved)
    result.add_group(
        "rel_move_right_const_msg",
        Step(divided, moved, "rel_move_right_const_eq", subresult=swap),
    )
    result.add_group(
        "calculate_short", Step(moved, solution, "sub" if inner.type is T.ADD else "add")
    )
    result.set_solution(solution)
    return result


def _negative_linear_methods(node: CoreNode, var: str) -> list[SolveResult] | None:
    """``-a x + b = c`` (integers, ``a >= 2``, ``b > 0``, ``c > b``): the two extra cards.

    the app shows, beside the ordinary rows, a "standard form" card that divides by
    ``a`` and then changes both signs, and an "implicit form" card that moves ``c`` left first.
    """
    left, right = _simple_side(node.children[0], var), _simple_side(node.children[1], var)
    if left is None or right is None or right[0] != 0:
        return None
    (a, b), c = left, right[1]
    if any(v.denominator != 1 for v in (a, b, c)) or not (a <= -2 and b > 0 and c > b):
        return None
    rest = c - b
    if rest % -a:
        return None
    eq = CoreNode.node
    x = CoreNode.variable(var)
    k, half = -a, rest / -a

    def system(left_side: CoreNode, right_side: CoreNode) -> CoreNode:
        return eq(T.EQUALS, left_side, right_side)

    def swap_detail(
        before: CoreNode,
        balanced: CoreNode,
        after: CoreNode,
        key: str,
        removed: str = "sub_with_self_remove_num",
        removed_args: list[CoreNode] | None = None,
    ) -> SolveResult:
        detail = SolveResult()
        detail.add_group(key, Step(before, balanced, key))
        detail.add_group(
            "remove_opposites", Step(balanced, after, removed, list(removed_args or []))
        )
        detail.set_solution(after)
        return detail

    def divide_detail(
        before: CoreNode, after: CoreNode, divisor: Fraction, *, implicit: bool = False
    ) -> SolveResult:
        detail = SolveResult()
        detail.add_group(
            CoreRichText(type="eq_linear_div", args=[_const(divisor)]),
            Step(before, after, "eq_linear_div", [_const(divisor)]),
        )
        if implicit:
            detail.add_group(
                "divide",
                Step(before, before, "mul_bracket", [_const(Fraction(abs(divisor)))]),
                Step(before, before, "div_zero", [_const(Fraction(0))]),
                Step(before, before, "div_neg_neg", [CoreNode.variable("+")]),
                Step(before, after, "quotient"),
                Step(before, after, "div_neg_neg", [CoreNode.variable("+")]),
                Step(before, after, "quotient"),
            )
        else:
            detail.add_group(
                "divide",
                Step(before, after, "quotient"),
                Step(before, after, "quotient"),
            )
        detail.set_solution(after)
        return detail

    term, three, seven, four = _x_term(a, var), _const(b), _const(c), _const(rest)

    # -- standard form: move 3, subtract, divide by 2, change the signs
    standard = SolveResult()
    moved = system(term, eq(T.SUBTRACT, seven, three))
    balanced = system(eq(T.SUBTRACT, node.children[0], three), eq(T.SUBTRACT, seven, three))
    standard.add_group(
        "rel_move_right_const_msg",
        Step(
            node,
            moved,
            "rel_move_right_const_eq",
            subresult=swap_detail(node, balanced, moved, "rel_swap_right_const"),
        ),
    )
    calculated = system(term, four)
    standard.add_group("calculate_short", Step(moved, calculated, "sub"))
    negated = system(_x_term(Fraction(-1), var), _const(half))
    standard.add_group(
        "divide_both_sides",
        Step(
            calculated,
            negated,
            "eq_linear_div",
            [_const(Fraction(k))],
            subresult=divide_detail(calculated, negated, Fraction(k)),
        ),
    )
    answer = _equation(var, _const(-half))
    flip = SolveResult()
    minus_one = _const(Fraction(-1))
    flip.add_group(
        "neg_flip",
        Step(negated, negated, "eq_mul_direct_one", [minus_one]),
        Step(negated, negated, "mul_with_neg_one", [minus_one]),
        Step(negated, answer, "mul_with_one", [_const(Fraction(1))]),
    )
    flip.set_solution(answer)
    standard.add_group("rel_linear_neg_msg", Step(negated, answer, "eq_linear_neg", subresult=flip))
    standard.set_solution(answer)

    # -- implicit form: move 7 to the left, subtract, divide by -2
    implicit = SolveResult()
    zero_form = system(eq(T.SUBTRACT, node.children[0], seven), _const(Fraction(0)))
    balanced = system(eq(T.SUBTRACT, node.children[0], seven), eq(T.SUBTRACT, seven, seven))
    implicit.add_group(
        "rel_move_left_const_msg",
        Step(
            node,
            zero_form,
            "rel_move_left_const",
            subresult=swap_detail(
                node,
                balanced,
                zero_form,
                "rel_swap_left_const",
                "sub_with_self_num",
                [_const(Fraction(0))],
            ),
        ),
    )
    reduced = system(eq(T.SUBTRACT, term, four), _const(Fraction(0)))
    inner = eq(T.SUBTRACT, three, seven)
    calc_page = SolveResult()
    calc_page.add_group("add_sign_sub", Step(inner, inner, "add_sign_sub"))
    calc_page.add_group("calculate_short", Step(inner, _const(Fraction(-rest)), "sub"))
    calc_page.set_solution(_const(Fraction(-rest)))
    implicit.add_group(
        "calculate_short",
        Step(zero_form, reduced, "calc_diff", subresult=calc_page),
    )
    final = system(eq(T.ADD, x, _const(half)), _const(Fraction(0)))
    implicit.add_group(
        "divide_both_sides",
        Step(
            reduced,
            final,
            "eq_linear_div",
            [_const(a)],
            subresult=divide_detail(reduced, final, a, implicit=True),
        ),
    )
    implicit.set_solution(final)
    implicit.header = "rewrite_in_implicit_form"
    return [standard, implicit]


def _both_sides_negative_methods(node: CoreNode, var: str) -> SolveResult | None:
    """``-a x + b = c x + d`` with ``c > 0`` and a negative net coefficient: the implicit-form card.

    the app (-x+5=2x-1): move the whole right side left, collect, add, divide by the
    magnitude of the coefficient, then change both signs.
    """
    left, right = _simple_side(node.children[0], var), _simple_side(node.children[1], var)
    if left is None or right is None:
        return None
    (a1, b1), (a2, b2) = left, right
    if any(v.denominator != 1 for v in (a1, b1, a2, b2)) or not (a2 > 0 and a1 - a2 < 0):
        return None
    k, total = int(a1 - a2), int(b1 - b2)
    if total % k:
        return None
    eq = CoreNode.node

    def side(coefficient: int, constant: int) -> CoreNode:
        out = _x_term(Fraction(coefficient), var)
        if constant:
            out = eq(T.ADD if constant > 0 else T.SUBTRACT, out, _const(Fraction(abs(constant))))
        return out

    moved = eq(
        T.EQUALS,
        eq(
            T.ADD if -b2 > 0 else T.SUBTRACT,
            eq(T.SUBTRACT, node.children[0], _x_term(Fraction(a2), var)),
            _const(Fraction(abs(b2))),
        ),
        _const(Fraction(0)),
    )
    collected_pre = eq(
        T.EQUALS,
        eq(
            T.ADD if b1 > 0 else T.SUBTRACT,
            _x_term(Fraction(k), var),
            _const(Fraction(abs(b1))),
        ),
        _const(Fraction(0)),
    )
    summed = eq(T.EQUALS, side(k, total), _const(Fraction(0)))
    divisor = -k
    divided = eq(
        T.EQUALS, side(-1, total // divisor * -1 if False else total // -k * 1), _const(Fraction(0))
    )
    divided = eq(T.EQUALS, side(k // divisor, total // divisor), _const(Fraction(0)))
    flipped = eq(T.EQUALS, side(1, -(total // divisor)), _const(Fraction(0)))

    def detail(
        before: CoreNode, after: CoreNode, key: str, args: list[CoreNode] | None = None
    ) -> SolveResult:
        inner = SolveResult()
        inner.add_group(key, Step(before, after, key, list(args or [])))
        inner.set_solution(after)
        return inner

    result = SolveResult()
    move_page = SolveResult()
    move_page.add_group("rel_swap_left", Step(node, moved, "rel_swap_left"))
    move_page.add_group(
        "remove_opposites",
        Step(moved, moved, "sub_with_self_alg", [_const(Fraction(0))]),
    )
    move_page.set_solution(moved)
    result.add_group(
        "rel_move_left_msg",
        Step(node, moved, "rel_move_left", subresult=move_page),
    )
    like_page = SolveResult()
    like_page.add_group(
        "sum_suffix_add_neg_one",
        Step(moved, moved, "sum_suffix_add_neg_one", [_const(Fraction(-1))]),
    )
    like_page.add_group("sum_suffix_detail", Step(moved, moved, "sum_suffix_detail"))
    like_page.add_group("calculate_short", Step(moved, collected_pre, "calc_diff"))
    like_page.set_solution(collected_pre)
    result.add_group(
        ["sum_suffix", "calculate_short"],
        Step(moved, collected_pre, "sum_suffix", subresult=like_page),
        Step(collected_pre, summed, "add"),
    )
    divide_page = SolveResult()
    divide_page.add_group(
        CoreRichText(type="eq_linear_div", args=[_const(Fraction(divisor))]),
        Step(summed, divided, "eq_linear_div", [_const(Fraction(divisor))]),
    )
    divide_page.add_group(
        "divide",
        Step(summed, summed, "mul_bracket", [_const(Fraction(abs(divisor)))]),
        Step(summed, summed, "div_zero", [_const(Fraction(0))]),
        Step(summed, divided, "quotient"),
        Step(summed, divided, "quotient"),
    )
    divide_page.set_solution(divided)
    result.add_group(
        "divide_both_sides",
        Step(
            summed,
            divided,
            "eq_linear_div",
            [_const(Fraction(divisor))],
            subresult=divide_page,
        ),
    )
    neg_page = SolveResult()
    minus_one = _const(Fraction(-1))
    neg_page.add_group(
        "neg_flip",
        Step(divided, divided, "eq_mul_direct_one", [minus_one]),
        Step(divided, divided, "mul_with_neg_one", [minus_one]),
        Step(divided, divided, "mul_with_one", [_const(Fraction(1))]),
        Step(divided, flipped, "mul_with_zero", [_const(Fraction(0))]),
    )
    neg_page.set_solution(flipped)
    result.add_group(
        "rel_linear_neg_msg",
        Step(divided, flipped, "eq_linear_neg", subresult=neg_page),
    )
    result.set_solution(flipped)
    return result


def _decimal_coefficient(node: CoreNode, var: str) -> list[SolveResult] | None:
    """``d x = c`` for a one-digit decimal ``d`` and an integer ``c``: two the app cards.

    Worked out for ``0,5x = 2``: divide by the decimal, or move ``c`` left, scale by 10, divide.
    """
    left, right = node.children
    if not (
        left.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT)
        and len(left.children) == 2
        and left.children[0].type is T.CONSTANT
        and left.children[1].type is T.VARIABLE
        and left.children[1].value == var
        and right.type is T.CONSTANT
        and (right.value or "").isdigit()
        and right.value != "0"
    ):
        return None
    text = left.children[0].value or ""
    whole, _, tail = text.partition(".")
    if not (whole.isdigit() and len(tail) == 1 and tail.isdigit() and text.replace(".", "") != "0"):
        return None
    d, c = Fraction(text), int(right.value or 0)
    a_int, c_int = int(d * 10), c * 10
    if c_int % a_int:
        return None
    eq = CoreNode.node
    x = CoreNode.variable(var)
    divisor = left.children[0]
    scaled = eq(
        T.EQUALS,
        eq(T.DIVIDE, left, divisor),
        eq(T.DIVIDE, right, divisor),
    )
    mid = eq(T.EQUALS, x, eq(T.DIVIDE, right, divisor))
    value = Fraction(c) / d
    solution = _equation(var, _const(value))
    primary = SolveResult()
    primary.add_group("divide_both_sides", Step(node, scaled, "eq_linear_div", [divisor]))
    primary.add_group(
        "divide",
        Step(scaled, mid, "div_with_self", [_const(Fraction(1))]),
        Step(mid, solution, "div"),
    )
    primary.set_solution(solution)

    implicit = SolveResult()
    zero = _const(Fraction(0))
    moved = eq(T.EQUALS, eq(T.SUBTRACT, left, right), zero)
    balanced = eq(T.EQUALS, eq(T.SUBTRACT, left, right), eq(T.SUBTRACT, right, right))
    swap = SolveResult()
    swap.add_group("rel_swap_left_const", Step(node, balanced, "rel_swap_left_const"))
    swap.add_group("remove_opposites", Step(balanced, moved, "sub_with_self_num", [zero]))
    swap.set_solution(moved)
    implicit.add_group(
        "rel_move_left_const_msg", Step(node, moved, "rel_move_left_const", subresult=swap)
    )
    ten = _const(Fraction(10))
    scaled_up = eq(
        T.EQUALS,
        eq(T.SUBTRACT, _x_term(Fraction(a_int), var), _const(Fraction(c_int))),
        zero,
    )
    mul_detail = SolveResult()
    mul_detail.add_group(
        CoreRichText(type="eq_mul_direct_eq", args=[ten]),
        Step(moved, scaled_up, "eq_mul_direct_eq", [ten]),
    )
    distributed = eq(
        T.EQUALS,
        eq(T.SUBTRACT, eq(T.MULTIPLY, left, ten), eq(T.MULTIPLY, right, ten)),
        eq(T.MULTIPLY, zero, ten),
    )
    without_zero = eq(
        T.EQUALS,
        eq(T.SUBTRACT, eq(T.MULTIPLY, left, ten), eq(T.MULTIPLY, right, ten)),
        zero,
    )
    mul_detail.add_group(
        "mul_bracket",
        Step(scaled_up, distributed, "mul_bracket", [ten]),
        Step(distributed, without_zero, "mul_with_zero", [zero]),
    )
    mul_detail.add_group("product", Step(without_zero, scaled_up, "product"))
    mul_detail.add_group("calculate_short", Step(scaled_up, scaled_up, "mul"))
    mul_detail.set_solution(scaled_up)
    implicit.add_group(
        "multiply_both_sides",
        Step(moved, scaled_up, "eq_mul_direct_eq", [ten], subresult=mul_detail),
    )
    final = eq(T.EQUALS, eq(T.SUBTRACT, x, _const(Fraction(c_int // a_int))), zero)
    div_detail = SolveResult()
    div_detail.add_group(
        CoreRichText(type="eq_linear_div", args=[_const(Fraction(a_int))]),
        Step(scaled_up, final, "eq_linear_div", [_const(Fraction(a_int))]),
    )
    split = eq(
        T.EQUALS,
        eq(
            T.SUBTRACT,
            eq(T.DIVIDE, _x_term(Fraction(a_int), var), _const(Fraction(a_int))),
            eq(T.DIVIDE, _const(Fraction(c_int)), _const(Fraction(a_int))),
        ),
        eq(T.DIVIDE, zero, _const(Fraction(a_int))),
    )
    cleared_div = eq(
        T.EQUALS,
        eq(
            T.SUBTRACT,
            eq(T.DIVIDE, _x_term(Fraction(a_int), var), _const(Fraction(a_int))),
            eq(T.DIVIDE, _const(Fraction(c_int)), _const(Fraction(a_int))),
        ),
        zero,
    )
    div_detail.add_group(
        "mul_bracket",
        Step(scaled_up, split, "mul_bracket", [_const(Fraction(a_int))]),
        Step(split, cleared_div, "div_zero", [zero]),
    )
    div_detail.add_group(
        "divide",
        Step(cleared_div, final, "quotient"),
        Step(final, final, "quotient"),
    )
    div_detail.set_solution(final)
    implicit.add_group(
        "divide_both_sides",
        Step(
            scaled_up,
            final,
            "eq_linear_div",
            [_const(Fraction(a_int))],
            subresult=div_detail,
        ),
    )
    implicit.set_solution(final)
    implicit.header = "rewrite_in_implicit_form"
    return [primary, implicit]


def _unknown_plus_integer(node: CoreNode, var: str) -> int | None:
    """``x`` -> 0, ``x + k`` -> k, ``x - k`` -> -k (integer ``k``); anything else -> None."""
    if node.type is T.VARIABLE and node.value == var:
        return 0
    if node.type in (T.ADD, T.SUBTRACT) and len(node.children) == 2:
        first, second = node.children
        if (
            first.type is T.VARIABLE
            and first.value == var
            and second.type is T.CONSTANT
            and (second.value or "").isdigit()
        ):
            return int(second.value or 0) * (1 if node.type is T.ADD else -1)
    return None


def _power_equation(node: CoreNode, var: str) -> SolveResult | None:
    """``b^x = b^n`` and ``x^m = c`` (odd ``m``): the two rows the app shows."""
    left, right = node.children
    if (
        right.type is not T.CONSTANT
        or not (right.value or "").isdigit()
        or left.type is not T.POWER
    ):
        return None
    base, exponent = left.children
    if exponent.type is T.BRACKET:
        exponent = exponent.children[0]
    target = int(right.value or 0)
    eq = CoreNode.node
    result = SolveResult()
    if (
        base.type is T.CONSTANT
        and (base.value or "").isdigit()
        and int(base.value or 0) >= 2
        and _unknown_plus_integer(exponent, var) is not None
    ):
        b = int(base.value or 0)
        n = 0
        while b**n < target:
            n += 1
        if n < 2 or b**n != target:
            return None
        same = eq(T.EQUALS, left, eq(T.POWER, base, _const(Fraction(n))))
        shift = _unknown_plus_integer(exponent, var) or 0
        value = n - shift
        solution = _equation(var, _const(Fraction(value)))
        result.add_group("write_as_exp_short", Step(node, same, "pow_to_same_base", [base]))
        if shift == 0:
            result.add_group("pow_equalize_exponents", Step(same, solution, "exp_eq_exp_equalise"))
            result.set_solution(solution)
            return result
        equal = eq(T.EQUALS, exponent, _const(Fraction(n)))
        moved = eq(
            T.EQUALS,
            CoreNode.variable(var),
            eq(
                T.SUBTRACT if shift > 0 else T.ADD,
                _const(Fraction(n)),
                _const(Fraction(abs(shift))),
            ),
        )
        sign = T.SUBTRACT if shift > 0 else T.ADD
        k = _const(Fraction(abs(shift)))
        balanced = eq(T.EQUALS, eq(sign, exponent, k), eq(sign, _const(Fraction(n)), k))
        swap = SolveResult()
        swap.add_group("rel_swap_right_const", Step(equal, balanced, "rel_swap_right_const"))
        swap.add_group("remove_opposites", Step(balanced, moved, "sub_with_self_remove_num"))
        swap.set_solution(moved)
        result.add_group("pow_equalize_exponents", Step(same, equal, "exp_eq_exp_equalise"))
        result.add_group(
            "rel_move_right_const_msg",
            Step(equal, moved, "rel_move_right_const_eq", subresult=swap),
        )
        result.add_group("sub", Step(moved, solution, "sub"))
        result.set_solution(solution)
        return result
    if (
        base.type is T.VARIABLE
        and base.value == var
        and exponent.type is T.CONSTANT
        and (exponent.value or "").isdigit()
        and int(exponent.value or 0) >= 3
        and int(exponent.value or 0) % 2 == 1
    ):
        m = int(exponent.value or 0)
        root = round(target ** (1 / m))
        if root < 2 or root**m != target:
            return None
        same = eq(T.EQUALS, left, eq(T.POWER, _const(Fraction(root)), exponent))
        solution = _equation(var, _const(Fraction(root)))
        result.add_group("write_as_exp_short", Step(node, same, "write_as_num_arg", [exponent]))
        detail = SolveResult()
        detail.add_group("eq_root", Step(same, solution, "eq_root"))
        detail.add_group("calculate_short", Step(same, solution, "root_reduce", [exponent]))
        detail.set_solution(solution)
        result.add_group("simplify_eq", Step(same, solution, "eq_root", subresult=detail))
        result.set_solution(solution)
        return result
    return None


def _numeric_fraction(node: CoreNode) -> Fraction | None:
    if node.type is not T.FRACTION:
        return None
    top, bottom = node.children
    if not all(c.type is T.CONSTANT and (c.value or "").isdigit() for c in (top, bottom)):
        return None
    return Fraction(int(top.value or 0), int(bottom.value or 1)) if bottom.value != "0" else None


def _fraction_constant_equation(node: CoreNode, var: str) -> list[SolveResult] | None:
    """``x + p/q = r/s`` (either order, or ``x - p/q``): move the fraction, then add or subtract."""
    left, right = node.children
    if left.type not in (T.ADD, T.SUBTRACT) or len(left.children) != 2:
        return None
    first, second = left.children
    if first.type is T.FRACTION and left.type is T.ADD:
        first, second = second, first
    k, target = _numeric_fraction(second), _numeric_fraction(right)
    if not (first.type is T.VARIABLE and first.value == var and k and target):
        return None
    adding = left.type is T.SUBTRACT  # moving a subtracted fraction adds it to the right side
    eq, fraction = CoreNode.node, _fraction_node
    x = CoreNode.variable(var)
    moved = eq(T.EQUALS, x, eq(T.ADD if adding else T.SUBTRACT, right, second))
    answer = target + k if adding else target - k
    solution = _equation(var, fraction(answer))
    balanced = eq(T.EQUALS, eq(T.ADD if adding else T.SUBTRACT, left, second), moved.children[1])
    swap = SolveResult()
    swap.add_group("rel_swap_right_const", Step(node, balanced, "rel_swap_right_const"))
    swap.add_group("remove_opposites", Step(balanced, moved, "sub_with_self_remove_num"))
    swap.set_solution(moved)
    key = "frac_add" if adding else "frac_sub"
    detail = quadratic_cards._fraction_page(moved.children[1], solution)
    result = SolveResult()
    result.add_group(
        "rel_move_right_const_msg",
        Step(node, moved, "rel_move_right_const_eq", subresult=swap),
    )
    result.add_group(key, Step(moved, solution, key, subresult=detail))
    result.set_solution(solution)
    if answer.denominator == 1:
        return [result]
    return [result, *_fraction_forms(node, var, moved, solution, answer)]


def _fraction_forms(
    node: CoreNode, var: str, moved: CoreNode, solution: CoreNode, answer: Fraction
) -> list[SolveResult]:
    """The "standard form" (``6x = 1``) and "implicit form" (``6x - 1 = 0``) cards.

    Worked out for ``2/3 + x = 5/6``: both start by moving the constant, subtract the fractions and
    multiply both sides by the common denominator; the implicit form ends with the commutative law.
    """
    eq, d, x = CoreNode.node, answer.denominator, CoreNode.variable(var)
    times = _const(Fraction(d))

    def multiply(before: CoreNode, after: CoreNode, *, distributed: bool = False) -> Step:
        detail = SolveResult()
        detail.add_group("eq_mul_direct_denom", Step(before, after, "eq_mul_direct_denom", [times]))
        if distributed:
            detail.add_group("mul_bracket", Step(before, before, "mul_bracket", [times]))
            detail.add_group(
                "mul_with_zero", Step(before, before, "mul_with_zero", [_const(Fraction(0))])
            )
        detail.add_group("frac_reduce_out", Step(before, after, "frac_reduce_out", [times]))
        detail.set_solution(after)
        return Step(before, after, "eq_mul_direct_denom", [times], subresult=detail)

    def subtract(before: CoreNode, after: CoreNode, name: str) -> Step:
        detail = quadratic_cards._fraction_page(before.children[1], after)
        return Step(before, after, name, subresult=detail)

    # standard form: x = 5/6 - 2/3 -> x = 1/6 -> 6x = 1
    scaled = eq(T.EQUALS, eq(T.MULTIPLY_IMPLICIT, times, x), _const(Fraction(answer.numerator)))
    swap = SolveResult()
    swap.add_group("rel_swap_right_const", Step(node, moved, "rel_swap_right_const"))
    swap.add_group("remove_opposites", Step(moved, moved, "sub_with_self_remove_num"))
    swap.set_solution(moved)
    standard = SolveResult()
    standard.add_group(
        "rel_move_right_const_msg",
        Step(node, moved, "rel_move_right_const_eq", subresult=swap),
    )
    adding = moved.children[1].type is T.ADD
    name = "frac_add" if adding else "frac_sub"
    standard.add_group(name, subtract(moved, solution, name))
    standard.add_group("multiply_both_sides", multiply(solution, scaled))
    standard.set_solution(scaled)

    # implicit form: the constant goes left, the fractions combine, then the order is fixed
    left = node.children[0]
    right = node.children[1]
    to_left = eq(T.EQUALS, eq(T.SUBTRACT, left, right), _const(Fraction(0)))
    constant = -answer
    c_node = _fraction_node(constant)
    combined = eq(T.EQUALS, eq(T.ADD, c_node, x), _const(Fraction(0)))
    cleared_constant = constant * d
    cleared = eq(
        T.EQUALS,
        _chain_terms(
            [
                (1 if cleared_constant > 0 else -1, _const(abs(cleared_constant))),
                (1, eq(T.MULTIPLY_IMPLICIT, times, x)),
            ]
        ),
        _const(Fraction(0)),
    )
    ordered = eq(
        T.EQUALS,
        _chain_terms(
            [
                (1, eq(T.MULTIPLY_IMPLICIT, times, x)),
                (1 if cleared_constant > 0 else -1, _const(abs(cleared_constant))),
            ]
        ),
        _const(Fraction(0)),
    )
    swap_left = SolveResult()
    swap_left.add_group("rel_swap_left_const", Step(node, to_left, "rel_swap_left_const"))
    swap_left.add_group(
        "remove_opposites", Step(to_left, to_left, "sub_with_self_num", [_const(Fraction(0))])
    )
    swap_left.set_solution(to_left)
    implicit = SolveResult()
    implicit.add_group(
        "rel_move_left_const_msg", Step(node, to_left, "rel_move_left_const", subresult=swap_left)
    )
    moved_rhs = moved.children[1]
    if moved_rhs.type is T.SUBTRACT and len(moved_rhs.children) == 2:
        page_expr = eq(T.SUBTRACT, moved_rhs.children[1], moved_rhs.children[0])
    elif moved_rhs.type is T.ADD and len(moved_rhs.children) == 2:
        page_expr = eq(T.ADD, moved_rhs.children[1], moved_rhs.children[0])
    else:
        page_expr = moved_rhs
    implicit.add_group(
        name,
        Step(to_left, combined, name, subresult=quadratic_cards._fraction_page(page_expr, c_node)),
    )
    implicit.add_group("multiply_both_sides", multiply(combined, cleared, distributed=True))
    implicit.add_group("var_order", Step(cleared, ordered, "var_order"))
    implicit.set_solution(ordered)
    implicit.header = "rewrite_in_implicit_form"
    return [standard, implicit]


def _chain_terms(items: list[tuple[int, CoreNode]]) -> CoreNode:
    sign, first = items[0]
    out = CoreNode.node(T.NEGATIVE, first) if sign < 0 else first
    for sign, term in items[1:]:
        out = CoreNode.node(T.SUBTRACT if sign < 0 else T.ADD, out, term)
    return out


def _fraction_node(value: Fraction) -> CoreNode:
    if value.denominator == 1:
        return _const(value)
    node = CoreNode.node(
        T.FRACTION, _const(Fraction(abs(value.numerator))), _const(Fraction(value.denominator))
    )
    return CoreNode.node(T.NEGATIVE, node) if value < 0 else node


def _fraction_sum_equation(node: CoreNode, var: str) -> list[SolveResult] | None:
    """``x/a + x/b = c``: clear the denominators, or add the fractions first (three cards).

    Worked out for ``x/2 + x/3 = 5``: multiply by the common denominator; write the sum as
    ``5/6 x`` and multiply by ``6/5``; or move ``c`` left, scale, divide.
    """
    left, right = node.children
    if not (
        left.type is T.ADD
        and len(left.children) == 2
        and right.type is T.CONSTANT
        and (right.value or "").isdigit()
        and right.value != "0"
    ):
        return None
    dens = []
    for part in left.children:
        if not (
            part.type is T.FRACTION
            and part.children[0].type is T.VARIABLE
            and part.children[0].value == var
            and part.children[1].type is T.CONSTANT
            and (part.children[1].value or "").isdigit()
            and int(part.children[1].value or 0) >= 2
        ):
            return None
        dens.append(int(part.children[1].value or 0))
    a, b = dens
    if a == b:
        return None
    c = int(right.value or 0)
    lcm = a * b // gcd(a, b)
    coefficient = Fraction(1, a) + Fraction(1, b)
    p_num, q_den = coefficient.numerator, coefficient.denominator
    if (c * lcm) % (lcm // a + lcm // b) or (c * q_den) % p_num:
        return None
    eq = CoreNode.node
    x = CoreNode.variable(var)
    zero = _const(Fraction(0))
    big = _const(Fraction(lcm))
    cleared_left = eq(T.ADD, _x_term(Fraction(lcm // a), var), _x_term(Fraction(lcm // b), var))
    cleared = eq(T.EQUALS, cleared_left, _const(Fraction(c * lcm)))
    total = lcm // a + lcm // b
    like = eq(T.EQUALS, _x_term(Fraction(total), var), _const(Fraction(c * lcm)))
    solution = _equation(var, _const(Fraction(c * lcm, total)))

    def one_step(key: str, before: CoreNode, after: CoreNode, *args: CoreNode) -> SolveResult:
        inner = SolveResult()
        inner.add_group(key, Step(before, after, key, list(args)))
        inner.set_solution(after)
        return inner

    def fraction_sum_page(before: CoreNode, after: CoreNode) -> SolveResult:
        inner = SolveResult()
        for title in (
            "frac_sum_expand",
            "frac_sum_expand",
            "mul",
            "mul",
            "frac_sum_join",
            "sum_suffix",
        ):
            inner.add_group(title, Step(before, before, title))
        inner.add_group(
            "frac_sep_n",
            Step(before, after, "frac_sep_n", [quadratic_cards._fraction_node(coefficient)]),
        )
        inner.set_solution(after)
        return inner

    def page(
        rows: list[tuple[str, str, list[CoreNode]]], before: CoreNode, after: CoreNode
    ) -> SolveResult:
        inner = SolveResult()
        for title, key, args in rows:
            inner.add_group(title, Step(before, after, key, args))
        inner.set_solution(after)
        return inner

    primary = SolveResult()
    primary.add_group(
        "multiply_both_sides",
        Step(
            node,
            cleared,
            "eq_mul_direct_denom",
            [big],
            subresult=page(
                [
                    ("eq_mul_direct_denom", "eq_mul_direct_denom", [big]),
                    ("mul_bracket", "mul_bracket", [big]),
                    ("calculate_short", "mul", []),
                    ("frac_reduce_out", "frac_reduce_out", [big]),
                    ("frac_reduce_out", "frac_reduce_out", [big]),
                ],
                node,
                cleared,
            ),
        ),
    )
    primary.add_group(
        "sum_suffix",
        Step(
            cleared,
            like,
            "sum_suffix",
            subresult=page(
                [
                    ("sum_suffix_add_detail", "sum_suffix_add_detail", []),
                    ("calculate_short", "add", []),
                ],
                cleared,
                like,
            ),
        ),
    )
    primary.add_group(
        "divide_both_sides",
        Step(
            like,
            solution,
            "eq_linear_div",
            [_const(Fraction(total))],
            subresult=page(
                [
                    ("eq_linear_div", "eq_linear_div", [_const(Fraction(total))]),
                    ("divide", "div_with_self", [_const(Fraction(1))]),
                    ("divide", "quotient", []),
                ],
                like,
                solution,
            ),
        ),
    )
    primary.set_solution(solution)

    summed = eq(
        T.EQUALS,
        eq(T.MULTIPLY_IMPLICIT, quadratic_cards._fraction_node(coefficient), x),
        right,
    )
    inverse = quadratic_cards._fraction_node(1 / coefficient)
    standard = SolveResult()
    standard.add_group(
        "calculate_short",
        Step(node, summed, "calc_sum", subresult=fraction_sum_page(node, summed)),
    )
    standard.add_group(
        "multiply_both_sides",
        Step(
            summed,
            solution,
            "eq_mul_direct_denom",
            [inverse],
            subresult=page(
                [
                    ("eq_mul_direct_denom", "eq_mul_direct_denom", [inverse]),
                    ("frac_reduce_out", "frac_reduce_out", [inverse]),
                    ("frac_reduce_out", "frac_reduce_out", [inverse]),
                    ("frac_reduce_out", "frac_reduce_out", [inverse]),
                ],
                summed,
                solution,
            ),
        ),
    )
    standard.set_solution(solution)

    implicit = SolveResult()
    implicit.add_group(
        "calculate_short",
        Step(node, summed, "calc_sum", subresult=fraction_sum_page(node, summed)),
    )
    moved = eq(T.EQUALS, eq(T.SUBTRACT, summed.children[0], right), zero)
    implicit.add_group(
        "rel_move_left_const_msg",
        Step(
            summed,
            moved,
            "rel_move_left_const",
            subresult=page(
                [
                    ("rel_swap_left_const", "rel_swap_left_const", []),
                    ("remove_opposites", "sub_with_self_num", [zero]),
                ],
                summed,
                moved,
            ),
        ),
    )
    scaled = eq(
        T.EQUALS,
        eq(T.SUBTRACT, _x_term(Fraction(p_num), var), _const(Fraction(c * q_den))),
        zero,
    )
    q_node = _const(Fraction(q_den))
    implicit.add_group(
        "multiply_both_sides",
        Step(
            moved,
            scaled,
            "eq_mul_direct_denom",
            [q_node],
            subresult=page(
                [
                    ("eq_mul_direct_denom", "eq_mul_direct_denom", [q_node]),
                    ("mul_bracket", "mul_bracket", [q_node]),
                    ("mul_with_zero", "mul_with_zero", [zero]),
                    ("frac_reduce_out", "frac_reduce_out", [q_node]),
                    ("calculate_short", "mul", []),
                ],
                moved,
                scaled,
            ),
        ),
    )
    final = eq(T.EQUALS, eq(T.SUBTRACT, x, _const(Fraction(c * q_den, p_num))), zero)
    p_node = _const(Fraction(p_num))
    implicit.add_group(
        "divide_both_sides",
        Step(
            scaled,
            final,
            "eq_linear_div",
            [p_node],
            subresult=page(
                [
                    ("eq_linear_div", "eq_linear_div", [p_node]),
                    ("mul_bracket", "mul_bracket", [p_node]),
                    ("div_zero", "div_zero", [zero]),
                    ("divide", "quotient", []),
                    ("divide", "quotient", []),
                ],
                scaled,
                final,
            ),
        ),
    )
    implicit.set_solution(final)
    implicit.header = "rewrite_in_implicit_form"
    return [primary, standard, implicit]


def _reciprocal_equation(node: CoreNode, var: str) -> SolveResult | None:
    """``1 / x = d`` for an integer ``d >= 2``: restriction, multiply, swap, divide, check.

    The five rows the card shows; other rational equations stay general.
    """
    left, right = node.children
    if not (
        left.type is T.FRACTION
        and left.children[0].type is T.CONSTANT
        and left.children[0].value == "1"
        and left.children[1].type is T.VARIABLE
        and left.children[1].value == var
        and right.type is T.CONSTANT
        and (right.value or "").isdigit()
        and int(right.value or 0) >= 2
    ):
        return None
    d = Fraction(int(right.value or 0))
    eq, x, zero = CoreNode.node, CoreNode.variable(var), _const(Fraction(0))

    def restricted(equation: CoreNode) -> CoreNode:
        return eq(T.LIST, equation, eq(T.NOT_EQUALS, x, zero))

    start = restricted(node)
    multiplied = restricted(eq(T.EQUALS, _const(Fraction(1)), _x_term(d, var)))
    swapped = restricted(eq(T.EQUALS, _x_term(d, var), _const(Fraction(1))))
    root = _const(1 / d)
    divided = restricted(eq(T.EQUALS, x, root))
    solution = _equation(var, root)

    result = SolveResult()
    domain = SolveResult()
    forbidden = eq(T.NOT_EQUALS, x, zero)
    domain.add_group(
        CoreRichText(type="rel_restrictions_den_zero", args=[x, zero, x]),
        Step(node, forbidden, "rel_restrictions_den_zero", [x, zero, x]),
    )
    domain.add_group(
        "rel_restrictions_range_complement",
        Step(forbidden, start, "rel_restrictions_range_complement"),
    )
    domain.set_solution(start)
    result.add_group(
        "rel_restrictions_range",
        Step(node, start, "rel_restrictions_range", subresult=domain),
    )
    multiply = SolveResult()
    multiply.add_group(
        CoreRichText(type="eq_mul_direct_denom", args=[x]),
        Step(start, multiplied, "eq_mul_direct_denom", [x]),
    )
    multiply.add_group(
        CoreRichText(type="frac_reduce_out", args=[x]),
        Step(start, multiplied, "frac_reduce_out_expr", [x]),
    )
    multiply.set_solution(multiplied)
    result.add_group(
        "multiply_both_sides",
        Step(start, multiplied, "eq_mul_direct_denom", [x], subresult=multiply),
    )
    result.add_group("rel_switch", Step(multiplied, swapped, "rel_swap_eq"))
    divide = SolveResult()
    divide.add_group(
        CoreRichText(type="eq_linear_div", args=[_const(d)]),
        Step(swapped, divided, "eq_linear_div", [_const(d)]),
    )
    divide.add_group(
        "divide",
        Step(swapped, divided, "div_with_self", [_const(Fraction(1))]),
        Step(swapped, divided, "div_to_frac"),
    )
    divide.set_solution(divided)
    result.add_group(
        "divide_both_sides",
        Step(swapped, divided, "eq_linear_div", [_const(d)], subresult=divide),
    )
    result.add_group("solution_check_sol", Step(divided, solution, "rel_restrictions_check"))
    result.set_solution(solution)
    return result


def _log10_equation(node: CoreNode, var: str) -> list[SolveResult] | None:
    """``log10(x) = n`` for an integer ``n >= 1``: the two cards the app shows."""
    left, right = node.children
    if not (
        left.type is T.LOG10
        and left.children[0].type is T.VARIABLE
        and left.children[0].value == var
        and right.type is T.CONSTANT
        and (right.value or "").isdigit()
        and int(right.value or 0) >= 1
    ):
        return None
    n = int(right.value or 0)
    eq, x, zero, ten = (
        CoreNode.node,
        CoreNode.variable(var),
        _const(Fraction(0)),
        _const(Fraction(10)),
    )
    power = eq(T.POWER, ten, right)
    converted = _equation(var, power)
    law = eq(
        T.EQUALS,
        eq(T.LOG, CoreNode.variable("x"), CoreNode.variable("a")),
        CoreNode.variable("b"),
    )
    law_power = eq(
        T.EQUALS,
        CoreNode.variable("x"),
        eq(T.POWER, CoreNode.variable("a"), CoreNode.variable("b")),
    )
    convert = Step(node, converted, "eq_log_formula_convert", [law, law_power])

    def restricted(equation: CoreNode) -> CoreNode:
        return eq(T.LIST, equation, eq(T.GREATER_THAN, x, zero))

    start = restricted(node)
    domain = SolveResult()
    domain.add_group(
        CoreRichText(type="rel_restrictions_log_arg", args=[x, x, zero]),
        Step(node, eq(T.GREATER_THAN, x, zero), "rel_restrictions_log_arg", [x, x, zero]),
    )
    domain.add_group(
        "rel_restrictions_range_complement",
        Step(eq(T.GREATER_THAN, x, zero), start, "rel_restrictions_range_complement"),
    )
    domain.set_solution(start)
    primary = SolveResult()
    primary.add_group(
        "rel_restrictions_range",
        Step(node, start, "rel_restrictions_range", subresult=domain),
    )
    with_domain = restricted(converted)
    primary.add_group(
        "log_convert_to_exp",
        Step(start, with_domain, "eq_log_formula_convert", [law, law_power]),
    )
    value = _equation(var, _const(Fraction(10**n)))
    solved = restricted(value)
    primary.add_group(
        "calculate_short",
        Step(
            with_domain,
            solved,
            "pow",
            subresult=quadratic_cards._detail(power, _const(Fraction(10**n))),
        ),
    )
    primary.add_group("solution_check_sol", Step(solved, value, "rel_restrictions_check"))
    primary.set_solution(value)
    rewrite = SolveResult()
    rewrite.add_group("log_convert_to_exp", convert)
    rewrite.set_solution(converted)
    return [primary, rewrite]


def _distribute_bracket(
    node: CoreNode, var: str, ctx: SolveContext
) -> tuple[CoreNode, CoreNode, CoreNode] | None:
    """``k (x + m) = ...`` with an unknown on the right: distribute ``k`` on a row of its own.

    The first row the app shows for ``3(x-2)=2x+1``; the rest are the plain linear rows.
    """
    lhs, rhs = node.children
    right_form = _simple_side(rhs, var)
    if right_form is None or right_form[0] == 0:
        return None
    if not (
        lhs.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT)
        and lhs.children[0].type is T.CONSTANT
        and (lhs.children[0].value or "").isdigit()
        and int(lhs.children[0].value or 0) >= 2
        and lhs.children[1].type is T.BRACKET
    ):
        return None
    inner = lhs.children[1].children[0]
    if not (
        inner.type in (T.ADD, T.SUBTRACT)
        and inner.children[0].type is T.VARIABLE
        and inner.children[0].value == var
        and inner.children[1].type is T.CONSTANT
        and (inner.children[1].value or "").isdigit()
    ):
        return None
    k, m = int(lhs.children[0].value or 0), int(inner.children[1].value or 0)
    eq = CoreNode.node
    opened = eq(inner.type, _x_term(Fraction(k), var), _const(Fraction(k * m)))
    changed = eq(T.EQUALS, opened, rhs)
    detail = SolveResult()
    detail.add_group(
        "remove_bracket_short",
        Step(node, opened, "mul_bracket_each", [_const(Fraction(k))]),
    )
    detail.add_group("calculate_short", Step(opened, changed, "mul"))
    detail.set_solution(changed)
    ctx.result.add_group(
        "remove_bracket_short",
        Step(node, changed, "mul_bracket", [_const(Fraction(k))], subresult=detail),
    )
    return changed, opened, rhs


def _standard_form_method(node: CoreNode, var: str) -> SolveResult:
    """``a x = c`` written as ``a x - c = 0``: the app's second card for ``3x = 1``."""
    eq = CoreNode.node
    lhs, rhs = node.children
    balanced = eq(T.EQUALS, eq(T.SUBTRACT, lhs, rhs), eq(T.SUBTRACT, rhs, rhs))
    final = eq(T.EQUALS, eq(T.SUBTRACT, lhs, rhs), _const(Fraction(0)))
    result = SolveResult()
    result.add_group("rel_swap_left_const", Step(node, balanced, "rel_swap_left_const"))
    result.add_group(
        "remove_opposites", Step(balanced, final, "sub_with_self_num", [_const(Fraction(0))])
    )
    result.set_solution(final)
    result.header = "rewrite_in_implicit_form"
    return result


def _fraction_zero_parts(node: CoreNode, var: str) -> tuple[CoreNode, CoreNode] | None:
    """``(fraction, numerator equation)`` for ``frac(numerator, number) = 0``."""
    lhs, rhs = node.children
    if lhs.type is T.FRACTION:
        fraction, other = lhs, rhs
    elif rhs.type is T.FRACTION:
        fraction, other = rhs, lhs
    else:
        return None
    if other.type is not T.CONSTANT or other.value != "0":
        return None
    numerator, denominator = fraction.children
    try:
        denominator_symbols = to_sympy(denominator).free_symbols
        numerator_symbols = to_sympy(numerator).free_symbols
    except SolveError:
        return None
    symbol = sympy.Symbol(var)
    if symbol in denominator_symbols or symbol not in numerator_symbols:
        return None
    return fraction, CoreNode.node(T.EQUALS, numerator, _const(Fraction(0)))


def _fraction_zero_rows(
    node: CoreNode, lhs: CoreNode, rhs: CoreNode, var: str, ctx: SolveContext
) -> CoreNode | None:
    """``frac(numerator, number) = 0``: the numerator is zero (worked out for x/2 = 0)."""
    parts = _fraction_zero_parts(node, var)
    if parts is None:
        return None
    _, numerator_eq = parts
    ctx.result.add_group(
        "frac_set_num_zero",
        Step(node, numerator_eq, "eq_linear_frac_zero", [_const(Fraction(0))]),
    )
    return solve_equation(numerator_eq, ctx)


def _fraction_zero_method(node: CoreNode, var: str, variables: list[str]) -> SolveResult | None:
    """The standalone ``x/2 = 0`` card: the numerator row, then the linear solve."""
    parts = _fraction_zero_parts(node, var)
    if parts is None:
        return None
    _, numerator_eq = parts
    card = SolveResult()
    card.add_group(
        "frac_set_num_zero",
        Step(node, numerator_eq, "eq_linear_frac_zero", [_const(Fraction(0))]),
    )
    inner = solve_methods(numerator_eq, variables)[0]
    card.extend(inner)
    card.set_solution(inner.solution or numerator_eq)
    return card


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

    if not divide_first:
        opened = _distribute_bracket(node, var, ctx)
        if opened is not None:
            node, lhs, rhs = opened
        if (rows := _linear_rows(node, lhs, rhs, var, ctx)) is not None:
            return rows
    if divide_first:
        after_divide = CoreNode(
            type=T.EQUALS,
            children=[
                CoreNode(type=T.DIVIDE, children=[lhs, _const(a)]),
                CoreNode(type=T.DIVIDE, children=[rhs, _const(a)]),
            ],
        )
        detail = SolveResult()
        divided = CoreNode.node(
            T.EQUALS,
            from_sympy(to_sympy(lhs) / sympy.Rational(a)),
            from_sympy(to_sympy(rhs) / sympy.Rational(a)),
        )
        detail.add_group(
            "lesson_divide",
            Step(node, after_divide, "lesson_divide_sides", [_const(a)]),
            Step(after_divide, divided, "lesson_simplify"),
        )
        detail.set_solution(divided)
        ctx.result.add_group(
            "lesson_divide",
            Step(
                left=node,
                right=after_divide,
                key="eq_linar_divide_both_sides",
                args=[_const(a)],
                subresult=detail,
            ),
        )
        ctx.result.add_group(
            "lesson_isolate",
            Step(left=divided, right=solution, key="move", subresult=_linear_balance(divided, var)),
        )
        return solution

    after_move = CoreNode(type=T.EQUALS, children=[_x_term(a, var), _const(-b)])
    already = poly_of(lhs, var) == {1: a} and poly_of(rhs, var) == ({0: -b} if b else {})

    left = node
    if not already:
        ctx.result.add_group(
            "lesson_isolate",
            Step(left=node, right=after_move, key="move", subresult=_linear_balance(node, var)),
        )
        left = after_move
    if a != 1:
        divided = CoreNode.node(
            T.EQUALS,
            CoreNode.node(T.FRACTION, left.children[0], _const(a)),
            CoreNode.node(T.FRACTION, left.children[1], _const(a)),
        )
        detail = SolveResult()
        detail.add_group(
            "lesson_divide",
            Step(left, divided, "lesson_divide_sides", [_const(a)]),
            Step(divided, solution, "lesson_simplify"),
        )
        detail.set_solution(solution)
        ctx.result.add_group(
            "lesson_divide",
            Step(
                left=left,
                right=solution,
                key="eq_linar_divide_both_sides",
                args=[_const(a)],
                subresult=detail,
            ),
        )
    return solution


def _linear_balance(node: CoreNode, var: str) -> SolveResult:
    """Show the actual operation on BOTH sides, including variables on the right."""
    detail = SolveResult()
    left, right = (poly_of(child, var) for child in node.children)
    current = node
    normalized = CoreNode.node(
        T.EQUALS,
        *[
            _ordered_polynomial([sympy.Rational(_coeff(p, 1)), sympy.Rational(_coeff(p, 0))], var)
            for p in (left, right)
        ],
    )
    if not current.structural_eq(normalized):
        detail.add_group("lesson_isolate", Step(current, normalized, "lesson_collect"))
        current = normalized
    for operand in (_x_term(_coeff(right, 1), var), _const(_coeff(left, 0))):
        if to_sympy(operand) == 0:
            continue
        balanced = CoreNode.node(
            T.EQUALS,
            *[
                CoreNode.node(T.SUBTRACT, child, CoreNode.node(T.BRACKET, operand))
                for child in current.children
            ],
        )
        simplified = CoreNode.node(
            T.EQUALS, *[from_sympy(sympy.expand(to_sympy(child))) for child in balanced.children]
        )
        detail.add_group(
            "lesson_isolate",
            Step(current, balanced, "lesson_balance", [operand]),
            Step(balanced, simplified, "lesson_simplify"),
        )
        current = simplified
    detail.set_solution(current)
    return detail


def _quadratic_solution(
    node: CoreNode, var: str, poly: Poly, ctx: SolveContext, *, factoring: bool = False
) -> CoreNode:
    """Квадратное уравнение: дискриминант и корни.

    ``factoring`` выбирает способ: разложение на множители вместо формулы
    (корни те же, меняется только пояснение шага).
    """
    a, b, c = _coeff(poly, 2), _coeff(poly, 1), _coeff(poly, 0)
    discriminant = b * b - 4 * a * c
    no_real_roots = discriminant < 0
    exact = None if no_real_roots else _perfect_sqrt(discriminant)
    if factoring and exact is None and not no_real_roots:
        raise SolveError("разложение на множители с рациональными корнями невозможно")
    solution: CoreNode | None = None
    if not no_real_roots:
        if exact is not None:
            low, high = sorted(((-b - exact) / (2 * a), (-b + exact) / (2 * a)))
            if low == high:
                solution = _equation(var, _const(low))
            else:
                solution = CoreNode.node(
                    T.LIST, _equation(var, _const(low)), _equation(var, _const(high))
                )
        else:
            root = _sqrt_node(discriminant)
            if a < 0:  # (-b + r)/(2a) = (b - r)/(-2a): never leave a minus in the denominator
                solution = CoreNode.node(
                    T.LIST,
                    _equation(var, _quad_root(b, root, -2 * a, plus=False)),
                    _equation(var, _quad_root(b, root, -2 * a, plus=True)),
                )
            else:
                solution = CoreNode.node(
                    T.LIST,
                    _equation(var, _quad_root(-b, root, 2 * a, plus=False)),
                    _equation(var, _quad_root(-b, root, 2 * a, plus=True)),
                )
            if sympy.sqrt(sympy.Rational(discriminant)).args[0] != sympy.Rational(discriminant):
                # sqrt(8) = 2 sqrt(2): write the answer as a student expects, -1 ± sqrt(2)
                roots = [
                    sympy.simplify(
                        (-sympy.Rational(b) + sign * sympy.sqrt(sympy.Rational(discriminant)))
                        / (2 * sympy.Rational(a))
                    )
                    for sign in (-1, 1)
                ]
                roots.sort(key=lambda value: float(value.evalf()))
                solution = CoreNode.node(T.LIST, *[_equation(var, from_sympy(r)) for r in roots])

    normalized = CoreNode.node(
        T.EQUALS,
        _ordered_polynomial([sympy.Rational(a), sympy.Rational(b), sympy.Rational(c)], var),
        CoreNode.constant("0"),
    )
    normalization = SolveResult()
    normalization.add_group("lesson_standard", Step(node, normalized, "lesson_normalize"))
    normalization.set_solution(normalized)
    ctx.result.add_group(
        "lesson_standard",
        Step(
            left=node,
            right=normalized,
            key="eq_quad_coeff_identify",
            args=[_const(a), _const(b), _const(c)],
            subresult=normalization if not node.structural_eq(normalized) else None,
        ),
    )
    disc_expression = CoreNode.node(
        T.SUBTRACT,
        CoreNode.node(T.POWER, CoreNode.node(T.BRACKET, _const(b)), CoreNode.constant("2")),
        CoreNode.node(
            T.MULTIPLY,
            CoreNode.node(T.MULTIPLY, CoreNode.constant("4"), CoreNode.node(T.BRACKET, _const(a))),
            CoreNode.node(T.BRACKET, _const(c)),
        ),
    )
    disc_substitution = CoreNode.node(T.EQUALS, CoreNode.variable("D"), disc_expression)
    disc_value = CoreNode.node(T.EQUALS, CoreNode.variable("D"), _const(discriminant))
    ctx.result.add_group(
        "lesson_discriminant",
        Step(left=_discriminant_formula(), right=disc_substitution, key="eq_quad_disc"),
        Step(
            left=disc_substitution,
            right=disc_value,
            key="eq_quad_disc_calculate",
            args=[_const(discriminant)],
            subresult=_discriminant_detail(
                _const(a), _const(b), _const(c), disc_substitution, disc_value
            ),
        ),
    )
    key = "solve_by_factoring" if factoring else "eq_quad_solve_in_r"
    substituted = _quadratic_substitution(a, b, discriminant, var)
    if no_real_roots:
        # корень из отрицательного дискриминанта — «x ∉ ℝ»,
        # а не ошибка. Complex roots stay in the methods (see ``solve_methods``).
        answer = _not_in_reals(var)
        ctx.result.add_group("expr_not_def_in_r", Step(substituted, answer, "root_sqr_neg"))
        return answer
    assert solution is not None
    if factoring:
        substituted = CoreNode.node(
            T.EQUALS, from_sympy(sympy.factor(_poly_expr(poly, var))), CoreNode.constant("0")
        )
    ctx.result.add_group(
        "lesson_roots",
        Step(
            left=substituted,
            right=solution,
            key=key,
            args=[] if factoring else [_zero_discriminant()],
            subresult=_quadratic_detail(
                _const(a),
                _const(b),
                _const(discriminant),
                solution,
                substituted,
                factoring=factoring,
                var=var,
            ),
        ),
    )
    return solution


def _general_quadratic(var: str) -> CoreNode:
    """``ax² + bx + c = 0``: the formula the roots come from, written with letters."""
    square = CoreNode.node(T.POWER, CoreNode.variable(var), CoreNode.constant("2"))
    # Letters multiply without a dot, as in the book: aλ² + bλ + c.
    linear = CoreNode.node(T.MULTIPLY_IMPLICIT, CoreNode.variable("b"), CoreNode.variable(var))
    polynomial = CoreNode.node(
        T.ADD,
        CoreNode.node(
            T.ADD,
            CoreNode.node(T.MULTIPLY_IMPLICIT, CoreNode.variable("a"), square),
            linear,
        ),
        CoreNode.variable("c"),
    )
    return CoreNode.node(T.EQUALS, polynomial, CoreNode.constant("0"))


def _nonzero_a() -> CoreNode:
    """``a ≠ 0``: a formula part, not typed text, in the sentence about the formula."""
    return CoreNode.node(T.NOT_EQUALS, CoreNode.variable("a"), CoreNode.constant("0"))


def _zero_discriminant() -> CoreNode:
    """``D = 0``: the case the sentence mentions, as a part."""
    return CoreNode.node(T.EQUALS, CoreNode.variable("D"), CoreNode.constant("0"))


def _discriminant_formula() -> CoreNode:
    return CoreNode.node(
        T.EQUALS,
        CoreNode.variable("D"),
        CoreNode.node(
            T.SUBTRACT,
            CoreNode.node(T.POWER, CoreNode.variable("b"), CoreNode.constant("2")),
            CoreNode.node(
                T.MULTIPLY,
                CoreNode.constant("4"),
                CoreNode.node(T.MULTIPLY, CoreNode.variable("a"), CoreNode.variable("c")),
            ),
        ),
    )


def _constant_quadratic(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """Exact quadratic formula for real constant coefficients such as pi/sqrt(2).

    Rational coefficients continue through the established arithmetic solver.
    Do not turn rational/transcendental equations into polynomials by cancelling
    their domain restrictions.
    """
    symbol = sympy.Symbol(var)
    for part in node.walk():
        if (
            part.type in (T.DIVIDE, T.FRACTION)
            and len(part.children) == 2
            and any(n.type is T.VARIABLE and n.value == var for n in part.children[1].walk())
        ):
            return None
    try:
        expression = to_sympy(node.children[0]) - to_sympy(node.children[1])
        polynomial = sympy.Poly(expression, symbol)
    except (SolveError, sympy.PolynomialError, ValueError, TypeError):
        return None
    if polynomial.degree() != 2:
        return None
    a, b, c = polynomial.all_coeffs()
    if not all(
        value.is_number and value.is_real is True and value.is_finite is True for value in (a, b, c)
    ):
        return None
    d = sympy.simplify(b * b - 4 * a * c)
    negative = d.is_negative is True
    if not negative and d.is_nonnegative is not True:
        return None
    coeff = [from_sympy(value) for value in (a, b, c)]
    normalized = CoreNode.node(
        T.EQUALS, _ordered_polynomial([a, b, c], var), CoreNode.constant("0")
    )
    normalization = SolveResult()
    normalization.add_group("lesson_standard", Step(node, normalized, "lesson_normalize"))
    normalization.set_solution(normalized)
    ctx.result.add_group(
        "lesson_standard",
        Step(
            node,
            normalized,
            "eq_quad_coeff_identify",
            args=coeff,
            subresult=normalization if not node.structural_eq(normalized) else None,
        ),
    )
    disc = CoreNode.node(
        T.EQUALS,
        CoreNode.variable("D"),
        CoreNode.node(
            T.SUBTRACT,
            CoreNode.node(T.POWER, CoreNode.node(T.BRACKET, coeff[1]), CoreNode.constant("2")),
            CoreNode.node(
                T.MULTIPLY,
                CoreNode.constant("4"),
                CoreNode.node(
                    T.MULTIPLY,
                    CoreNode.node(T.BRACKET, coeff[0]),
                    CoreNode.node(T.BRACKET, coeff[2]),
                ),
            ),
        ),
    )
    calculated = CoreNode.node(T.EQUALS, CoreNode.variable("D"), from_sympy(d))
    substitutions = CoreNode.node(
        T.LIST,
        *[
            _equation(
                var,
                CoreNode.node(
                    T.FRACTION,
                    CoreNode.node(
                        operation,
                        CoreNode.node(T.NEGATIVE, CoreNode.node(T.BRACKET, coeff[1])),
                        CoreNode.node(T.ROOT2, from_sympy(d)),
                    ),
                    CoreNode.node(
                        T.MULTIPLY, CoreNode.constant("2"), CoreNode.node(T.BRACKET, coeff[0])
                    ),
                ),
            )
            for operation in (T.SUBTRACT, T.ADD)
        ],
    )
    ctx.result.add_group(
        "lesson_discriminant",
        Step(left=_discriminant_formula(), right=disc, key="eq_quad_disc"),
        Step(
            left=disc,
            right=calculated,
            key="eq_quad_disc_calculate",
            args=[from_sympy(d)],
            subresult=_discriminant_detail(coeff[0], coeff[1], coeff[2], disc, calculated),
        ),
    )
    if negative:
        # корень из отрицательного дискриминанта — «x ∉ ℝ».
        answer = _not_in_reals(var)
        ctx.result.add_group("expr_not_def_in_r", Step(substitutions, answer, "root_sqr_neg"))
        return answer
    roots = sorted(
        set(
            (
                sympy.simplify((-b - sympy.sqrt(d)) / (2 * a)),
                sympy.simplify((-b + sympy.sqrt(d)) / (2 * a)),
            )
        ),
        key=lambda value: float(value.evalf()),
    )
    equations = [_equation(var, from_sympy(value)) for value in roots]
    solution = equations[0] if len(equations) == 1 else CoreNode.node(T.LIST, *equations)
    ctx.result.add_group(
        "lesson_roots",
        Step(
            left=substitutions,
            right=solution,
            key="eq_quad_solve_in_r",
            args=[_zero_discriminant()],
            subresult=_quadratic_detail(
                coeff[0], coeff[1], from_sympy(d), solution, substitutions, factoring=False, var=var
            ),
        ),
    )
    return solution


def _quadratic_substitution(a: Fraction, b: Fraction, d: Fraction, var: str) -> CoreNode:
    """Две ветви формулы с подставленными коэффициентами и дискриминантом."""
    roots = []
    for operation in (T.SUBTRACT, T.ADD):
        numerator = CoreNode.node(
            operation,
            CoreNode.node(T.NEGATIVE, CoreNode.node(T.BRACKET, _const(b))),
            CoreNode.node(T.ROOT2, _const(d)),
        )
        denominator = CoreNode.node(
            T.MULTIPLY, CoreNode.constant("2"), CoreNode.node(T.BRACKET, _const(a))
        )
        roots.append(_equation(var, CoreNode.node(T.FRACTION, numerator, denominator)))
    return CoreNode.node(T.LIST, *roots)


def _discriminant_detail(
    a: CoreNode, b: CoreNode, c: CoreNode, start: CoreNode, end: CoreNode
) -> SolveResult:
    detail = SolveResult()
    square = from_sympy(sympy.simplify(to_sympy(b) ** 2))
    product = from_sympy(sympy.simplify(4 * to_sympy(a) * to_sympy(c)))
    expression = start.children[1]
    squared = CoreNode.node(
        T.EQUALS, CoreNode.variable("D"), CoreNode.node(T.SUBTRACT, square, expression.children[1])
    )
    multiplied = CoreNode.node(
        T.EQUALS,
        CoreNode.variable("D"),
        CoreNode.node(T.SUBTRACT, square, CoreNode.node(T.BRACKET, product)),
    )
    detail.add_group(
        "lesson_discriminant",
        Step(start, squared, "lesson_disc_square"),
        Step(squared, multiplied, "lesson_disc_product"),
        Step(multiplied, end, "lesson_disc_subtract"),
    )
    detail.set_solution(end)
    return detail


def _quadratic_detail(
    a: CoreNode,
    b: CoreNode,
    discriminant: CoreNode,
    solution: CoreNode,
    substituted: CoreNode,
    *,
    factoring: bool,
    var: str,
) -> SolveResult:
    """Actual arithmetic for each branch, not a repetition of the final answer."""
    detail = SolveResult(header="lesson_roots")
    if factoring:
        equations = solution.children if solution.type is T.LIST else [solution]
        zero_equations = [
            CoreNode.node(
                T.EQUALS,
                CoreNode.node(T.SUBTRACT, CoreNode.variable(var), eq.children[1]),
                CoreNode.constant("0"),
            )
            for eq in equations
        ]
        branches = (
            zero_equations[0]
            if len(zero_equations) == 1
            else CoreNode.node(T.LIST, *zero_equations)
        )
        detail.add_group(
            "lesson_roots",
            Step(substituted, branches, "lesson_factor_zero"),
            Step(branches, solution, "lesson_simplify"),
        )
    else:
        # The general formula uses two explicit branches rather than a literal
        # ± token, retaining an ordinary, editable AST at every level.
        def branch(
            operation: T, minus_b: CoreNode, radical: CoreNode, denominator: CoreNode
        ) -> CoreNode:
            return _equation(
                var,
                CoreNode.node(T.FRACTION, CoreNode.node(operation, minus_b, radical), denominator),
            )

        generic = CoreNode.node(
            T.LIST,
            *[
                branch(
                    op,
                    CoreNode.node(T.NEGATIVE, CoreNode.variable("b")),
                    CoreNode.node(T.ROOT2, CoreNode.variable("D")),
                    CoreNode.node(T.MULTIPLY, CoreNode.constant("2"), CoreNode.variable("a")),
                )
                for op in (T.SUBTRACT, T.ADD)
            ],
        )
        detail.add_group(
            "lesson_root_substitute",
            Step(
                generic,
                substituted,
                "lesson_root_formula",
                [_general_quadratic(var), _nonzero_a()],
            ),
        )
        for branch_index, original in enumerate(substituted.children):
            current = original
            fraction = original.children[1]
            numerator, denominator = fraction.children
            radical = from_sympy(sympy.sqrt(to_sympy(discriminant)))
            sqrt_step = _equation(
                var,
                CoreNode.node(
                    T.FRACTION,
                    CoreNode.node(numerator.type, numerator.children[0], radical),
                    denominator,
                ),
            )
            numeric_numerator = from_sympy(sympy.simplify(to_sympy(numerator)))
            numerator_step = _equation(
                var, CoreNode.node(T.FRACTION, numeric_numerator, denominator)
            )
            denominator_step = _equation(
                var, CoreNode.node(T.FRACTION, numeric_numerator, from_sympy(2 * to_sympy(a)))
            )
            final = _equation(var, from_sympy(sympy.simplify(to_sympy(fraction))))
            stages = []
            for next_node, key in (
                (sqrt_step, "lesson_root_sqrt"),
                (numerator_step, "lesson_root_numerator"),
                (denominator_step, "lesson_root_denominator"),
                (final, "lesson_root_reduce"),
            ):
                if not current.structural_eq(next_node):
                    stages.append(Step(current, next_node, key))
                    current = next_node
            if stages:
                detail.add_group(
                    "lesson_root_minus" if branch_index == 0 else "lesson_root_plus", *stages
                )
    detail.set_solution(solution)
    return detail


def _quad_root(
    minus_b: Fraction, sqrt_node: CoreNode, denominator: Fraction, *, plus: bool
) -> CoreNode:
    """Корень квадратного уравнения по формуле с знаком корня.

    При ``b = 0`` слагаемое ``-b`` равно нулю, но знак перед корнем всё
    равно важен: без него обе ветви дают один и тот же положительный корень
    (``x² − 2 = 0`` терял ``−√2``).
    """
    if minus_b == 0:
        numerator = sqrt_node if plus else CoreNode(type=T.NEGATIVE, children=[sqrt_node])
    else:
        numerator = CoreNode(
            type=T.ADD if plus else T.SUBTRACT,
            children=[_const(minus_b), sqrt_node],
        )
    if denominator == 1:
        return numerator
    return CoreNode(type=T.FRACTION, children=[numerator, _const(denominator)])


def _pick_primary(variables: list[str]) -> str:
    """Неизвестное для параметрического решения: x предпочитается остальным."""
    return "x" if "x" in variables else variables[0]


def _solve_parametric(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode:
    """Решить уравнение относительно одной буквы, остальные считать параметрами.

    ``a*x + b = 0`` -> ``x = -b/a`` с шагами ``eq_param_write`` и
    ``eq_linear_param_j_final`` (аргумент -- переменная). Корни берёт sympy;
    явно комплексные отбрасываются, проверка подстановкой мягкая: выражение
    с параметром может не упроститься к нулю.
    """
    lhs, rhs = node.children
    symbol = sympy.Symbol(var)
    try:
        expression = to_sympy(lhs) - to_sympy(rhs)
    except SolveError as error:
        raise SolveError("уравнение с параметрами не решается") from error
    try:
        found = sympy.solve(expression, symbol)
    except (NotImplementedError, TypeError, ValueError) as error:
        raise SolveError("уравнение с параметрами не решается") from error
    if not found:
        raise SolveError("нет решений относительно переменной", "eq_linear_param_sol_simple")

    roots: list[sympy.Expr] = []
    for root in found:
        if root.is_real is False:
            continue
        if any(sympy.simplify(root - known) == 0 for known in roots):
            continue
        roots.append(root)
    if not roots:
        raise SolveError("нет действительных решений относительно переменной")
    roots.sort(key=_sort_key)

    equations = [
        CoreNode.node(T.EQUALS, CoreNode.variable(var), from_sympy(root)) for root in roots
    ]
    answer = equations[0] if len(equations) == 1 else CoreNode.node(T.LIST, *equations)
    other_names = [name for name in ctx.variables if name != var]
    if len(ctx.variables) == 2 and len(other_names) == 1 and len(roots) == 1:
        try:
            expanded = sympy.expand(expression)
            degree = sympy.degree(expanded, symbol)
            coefficient = expanded.coeff(symbol)
        except (TypeError, ValueError):
            degree, coefficient = 0, None
        if degree == 1 and coefficient == 1:
            # x + y = 1 -> x = 1 - y, then the parameter's domain (verified card)
            other_node = CoreNode.variable(other_names[0])
            answer_eq = CoreNode.node(T.EQUALS, CoreNode.variable(var), from_sympy(roots[0]))
            swapped = CoreNode.node(
                T.EQUALS,
                CoreNode.node(T.SUBTRACT, lhs, other_node),
                CoreNode.node(T.SUBTRACT, rhs, other_node),
            )
            detail = SolveResult()
            detail.add_group("rel_swap_right_var", Step(node, swapped, "rel_swap_right_var"))
            detail.add_group(
                "remove_opposites",
                Step(swapped, answer_eq, "sub_with_self_remove_alg"),
            )
            detail.set_solution(answer_eq)
            ctx.result.add_group(
                "rel_move_right_var_msg",
                Step(node, answer_eq, "rel_move_right_var", subresult=detail),
            )
            answer = CoreNode.node(
                T.LIST,
                answer_eq,
                CoreNode.node(T.ELEMENT_OF, other_node, CoreNode.variable("ℝ")),
            )
            ctx.result.add_group(
                CoreRichText(type="eq_linear_param_sol_simple"),
                Step(
                    answer_eq,
                    answer,
                    "eq_linear_param_sol",
                    [CoreNode.variable(var)],
                ),
            )
            return answer
    ctx.result.add(Step(left=node, right=None, key="eq_param_write"), [_HEADER])
    ctx.result.add(
        Step(left=node, right=answer, key="eq_linear_param_j_final", args=[CoreNode.variable(var)]),
        [CoreRichText(type="eq_linear_param_sol_simple")],
    )
    return answer


def _parametric_extra_cards(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """The app's rewrite cards and the slope card for ``x + y = c``.

    Worked out for ``x + y = 1``: implicit form, slope-intercept form, then the
    slope/y-intercept card. The method header of the last one needs an argument,
    which ``SolveResult.header`` cannot carry, so it stays unnamed.
    """
    if len(node.children) != 2 or len(variables) != 2:
        return []
    primary = _pick_primary(variables)
    dependent = next((name for name in variables if name != primary), None)
    if dependent is None:
        return []
    lhs, rhs = node.children
    x_sym, y_sym = sympy.Symbol(primary), sympy.Symbol(dependent)
    try:
        expression = sympy.expand(to_sympy(lhs) - to_sympy(rhs))
        if sympy.degree(expression, x_sym) != 1 or sympy.degree(expression, y_sym) != 1:
            return []
        if expression.coeff(x_sym) != 1 or expression.coeff(y_sym) != 1:
            return []
        found = sympy.solve(sympy.Eq(to_sympy(lhs), to_sympy(rhs)), y_sym)
    except (SolveError, TypeError, ValueError, NotImplementedError):
        return []
    if len(found) != 1:
        return []
    zero = _const(Fraction(0))
    dep, indep = CoreNode.variable(dependent), CoreNode.variable(primary)
    moved_y = CoreNode.node(T.EQUALS, dep, from_sympy(found[0]))

    # -- implicit form: (x + y) - 1 = 0
    shifted = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.SUBTRACT, lhs, rhs),
        CoreNode.node(T.SUBTRACT, rhs, rhs),
    )
    final = CoreNode.node(T.EQUALS, CoreNode.node(T.SUBTRACT, lhs, rhs), zero)
    implicit = SolveResult(header="rewrite_in_implicit_form")
    implicit.add_group("rel_move_left_const_msg", Step(node, shifted, "rel_swap_left_const"))
    implicit.add_group("sub_with_self_del", Step(shifted, final, "sub_with_self_num", [zero]))
    implicit.set_solution(final)

    # -- slope-intercept form: y = 1 - x -> y = -x + 1
    swapped = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.SUBTRACT, lhs, dep),
        CoreNode.node(T.SUBTRACT, rhs, dep),
    )
    move_detail = SolveResult()
    move_detail.add_group("rel_swap_right_var", Step(node, swapped, "rel_swap_right_var"))
    move_detail.add_group("remove_opposites", Step(swapped, moved_y, "sub_with_self_remove_alg"))
    move_detail.set_solution(moved_y)
    constant = expression.subs({x_sym: 0, y_sym: 0})
    slope = Fraction(-1)
    intercept = Fraction(-constant)
    slope_node, intercept_node = _const(slope), _const(intercept)
    reordered = CoreNode.node(
        T.EQUALS,
        dep,
        CoreNode.node(T.ADD, CoreNode.node(T.NEGATIVE, indep), intercept_node),
    )
    slope_intercept = SolveResult(header="rewrite_in_slope_intercept_form")
    slope_intercept.add_group(
        "rel_move_right_var_msg",
        Step(node, moved_y, "rel_move_right_var", subresult=move_detail),
    )
    slope_intercept.add_group("reorder", Step(moved_y, reordered, "var_order"))
    slope_intercept.set_solution(reordered)

    # -- slope and y-intercept: y = -1·x + 1
    explicit = CoreNode.node(
        T.EQUALS,
        dep,
        CoreNode.node(T.ADD, CoreNode.node(T.MULTIPLY, slope_node, indep), intercept_node),
    )
    m, b = CoreNode.variable("m"), CoreNode.variable("b")
    slope_eq, intercept_eq = (
        CoreNode.node(T.EQUALS, m, slope_node),
        CoreNode.node(T.EQUALS, b, intercept_node),
    )
    rewrite_page = SolveResult()
    rewrite_page.add_group(
        "rel_move_right_var_msg",
        Step(node, reordered, "rel_move_right_var", subresult=move_detail),
    )
    rewrite_page.add_group("reorder", Step(reordered, reordered, "var_order"))
    rewrite_page.set_solution(reordered)
    with_slope = CoreNode.node(T.LIST, explicit, slope_eq)
    with_intercept = CoreNode.node(T.LIST, explicit, slope_eq, intercept_eq)
    answer = CoreNode.node(T.LIST, slope_eq, intercept_eq)
    slope_card = _MethodTitleResult(CoreRichText(type="find_slope_and_y_intercept", args=[dep]))
    slope_card.add_group(
        "eq_trans",
        Step(node, reordered, "rewrite_eq_in_slope_intercept", subresult=rewrite_page),
    )
    slope_card.add_group(
        CoreRichText(type="sum_one_coeff", args=[_const(Fraction(1))]),
        Step(reordered, explicit, "sum_suffix_add_neg_one", [_const(Fraction(-1))]),
    )
    slope_card.add_group(
        "identify_slope",
        Step(
            explicit,
            with_slope,
            "identify_slope_as_coef",
            [
                CoreNode.node(
                    T.EQUALS,
                    dep,
                    CoreNode.node(
                        T.ADD,
                        CoreNode.node(T.MULTIPLY, m, indep),
                        b,
                    ),
                ),
                indep,
            ],
        ),
    )
    slope_card.add_group(
        CoreRichText(type="identify_y_intercept", args=[dep]),
        Step(with_slope, with_intercept, "identify_y_intercept_as_const_term", [dep]),
    )
    slope_card.add_group(
        CoreRichText(type="slope_and_y_intercept", args=[slope_eq, dep, intercept_eq]),
        Step(
            with_intercept,
            answer,
            "slope_line_and_y_intercept",
            [slope_eq, dep, intercept_eq],
        ),
    )
    slope_card.set_solution(answer)

    polar: list[SolveResult] = []
    if {primary, dependent} == {"x", "y"} and lhs.type is T.ADD:
        names = {child.value for child in lhs.children if child.type is T.VARIABLE}
        if names == {"x", "y"} and len(lhs.children) == 2:
            polar = [_polar_card(node, lhs, rhs)]
    return [implicit, slope_intercept, *polar, slope_card]


def _polar_card(node: CoreNode, lhs: CoreNode, rhs: CoreNode) -> SolveResult:
    """``x + y = 1`` in polar coordinates: ``r(cos θ + sin θ) = 1`` (verified card)."""
    theta, r = CoreNode.variable("θ"), CoreNode.variable("r")
    cos, sin = CoreNode.node(T.COS, theta), CoreNode.node(T.SIN, theta)
    polar_x = CoreNode.node(T.MULTIPLY, r, cos)
    polar_y = CoreNode.node(T.MULTIPLY, r, sin)
    substituted = CoreNode.node(T.EQUALS, CoreNode.node(T.ADD, polar_x, polar_y), rhs)
    denominator = CoreNode.node(T.ADD, cos, sin)
    factored = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.MULTIPLY_IMPLICIT, CoreNode.node(T.BRACKET, denominator), r),
        rhs,
    )
    answer = CoreNode.node(T.EQUALS, r, CoreNode.node(T.FRACTION, _const(Fraction(1)), denominator))
    division = SolveResult()
    division.add_group("divide_both_sides", Step(factored, answer, "eq_linear_div", [denominator]))
    division.add_group(
        "divide",
        Step(answer, answer, "div_with_self", [_const(Fraction(1))]),
        Step(answer, answer, "div_to_frac"),
    )
    division.set_solution(answer)
    result = SolveResult(header="rewrite_in_polar")
    result.add_group(
        "trig_use_substitution",
        Step(
            node,
            substituted,
            "eq_substitute_polar_two",
            [
                polar_x,
                CoreNode.variable("x"),
                polar_y,
                CoreNode.variable("y"),
            ],
        ),
    )
    result.add_group("factorise_call", Step(substituted, factored, "extract_arg", [r]))
    result.add_group(
        "divide_both_sides",
        Step(factored, answer, "eq_linear_div", [denominator], subresult=division),
    )
    result.set_solution(answer)
    return result


def _parametric_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """Способы параметрического решения: основной -- относительно x, дальше -- по буквам.

    ``x + y = 1`` даёт два способа: «относительно x» (``x = 1 - y``) и
    «относительно y». Букв больше трёх -- берём первые три: переключатель
    способов не резиновый.
    """
    primary = _pick_primary(variables)
    order = [primary, *[var for var in variables if var != primary][:2]]
    methods: list[SolveResult] = []
    last_error: SolveError | None = None
    for var in order:

        def action(n: CoreNode, c: SolveContext, *, target: str = var) -> CoreNode:
            return _solve_parametric(n, target, c)

        try:
            methods.append(_run(node, variables, action))
        except SolveError as error:
            last_error = error
    if not methods:
        assert last_error is not None
        raise last_error
    # The first card stays the solution relative to x: our flat vertical branch takes the
    # answer from it, while the app keeps the rewrite cards in a separate group.
    extras = _parametric_extra_cards(node, variables)
    return methods + extras


def _alternative_result(
    node: CoreNode,
    variables: list[str],
    solver: Callable[[CoreNode, list[str], SolveContext], CoreNode | None],
) -> SolveResult | None:
    """Решить уравнение отдельным способом (рациональное, иррациональное).

    ``None`` — способ не подошёл; тогда пробуется следующий.
    """
    result = SolveResult()
    ctx = SolveContext(result=result, variables=list(variables))
    answer = solver(node, variables, ctx)
    if answer is None:
        return None
    if answer.type is T.EMPTY:
        # Нет решений: ответ-узла нет, как и у других уравнений (решение #19).
        return result
    result.set_solution(answer)
    return result


def _rational_denominator(frac: CoreNode, var: str) -> CoreNode | None:
    """Denominator of a fraction that depends on the unknown, else ``None``."""
    if frac.type is not T.FRACTION or len(frac.children) != 2:
        return None
    denominator = frac.children[1]
    if not any(part.type is T.VARIABLE and part.value == var for part in denominator.walk()):
        return None
    return denominator


def _single_root(expression: CoreNode, var: str) -> sympy.Expr | None:
    """The only real root of ``expression = 0``, or ``None``."""
    try:
        found = sympy.solve(sympy.Eq(to_sympy(expression), 0), sympy.Symbol(var))
    except (TypeError, ValueError, NotImplementedError):
        return None
    real = [root for root in found if _is_real_root(root)]
    if len(real) != 1:
        return None
    return real[0]


def _domain_card(
    node: CoreNode, var: str, denominators: list[CoreNode], ctx: SolveContext
) -> tuple[CoreNode, CoreNode] | None:
    """The domain card for rational equations; returns (restricted node, condition)."""
    x, zero = CoreNode.variable(var), _const(Fraction(0))
    roots: list[sympy.Expr] = []
    for denominator in denominators:
        root = _single_root(denominator, var)
        if root is None:
            return None
        roots.append(root)
    conditions: list[CoreNode] = []
    rows: list[Step] = []
    for denominator, root in zip(denominators, roots, strict=True):
        solved = _equation(var, from_sympy(root))
        rows.append(
            Step(
                left=CoreNode.node(T.EQUALS, denominator, zero),
                right=solved,
                key="eq_linear",
                args=[x],
            )
        )
        conditions.append(CoreNode.node(T.NOT_EQUALS, x, from_sympy(root)))
    condition = conditions[0] if len(conditions) == 1 else CoreNode.node(T.LIST, *conditions)
    restricted, detail = restriction_range_card(
        node,
        var,
        [("rel_restrictions_den_zero", [x, zero, denominator]) for denominator in denominators],
        condition,
        extra_rows=rows,
    )
    ctx.result.add_group(
        "rel_restrictions_range",
        Step(node, restricted, "rel_restrictions_range", subresult=detail),
    )
    return restricted, condition


def _rational_multiply_rows(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """Fraction = number: restriction, multiply by the denominator, then the linear rows."""
    lhs, rhs = node.children
    if (denominator := _rational_denominator(lhs, var)) is not None:
        fraction, other = lhs, rhs
    elif (denominator := _rational_denominator(rhs, var)) is not None:
        fraction, other = rhs, lhs
    else:
        return None
    if (
        other.type is not T.CONSTANT
        or denominator.type not in (T.ADD, T.SUBTRACT)
        or denominator.children[0].type is not T.VARIABLE
        or denominator.children[1].type is not T.CONSTANT
    ):
        return None
    numerator = fraction.children[0]
    if numerator.type not in (T.VARIABLE, T.CONSTANT):
        return None
    card = _domain_card(node, var, [denominator], ctx)
    if card is None:
        return None
    restricted, condition = card
    bracket = CoreNode.node(T.BRACKET, denominator)
    product = CoreNode.node(T.MULTIPLY, other, bracket)
    multiplied = CoreNode.node(T.EQUALS, numerator, product)
    multiply_page = SolveResult()
    multiply_page.add_group(
        CoreRichText(type="eq_mul_direct_denom", args=[denominator]),
        Step(restricted, multiplied, "eq_mul_direct_denom", [denominator]),
    )
    multiply_page.add_group(
        CoreRichText(type="frac_reduce_reduce", args=[denominator]),
        Step(restricted, multiplied, "frac_reduce_out_expr", [denominator]),
    )
    multiply_page.set_solution(multiplied)
    ctx.result.add_group(
        "multiply_both_sides",
        Step(restricted, multiplied, "eq_mul_direct_denom", [denominator], subresult=multiply_page),
    )
    try:
        scale = as_fraction(other)
        shift = as_fraction(denominator.children[1])
    except SolveError:
        return None
    sign = 1 if denominator.type is T.ADD else -1
    expanded_rhs = quadratic_cards._chain(
        [
            (1 if scale > 0 else -1, _x_term(abs(scale), var)),
            (1 if sign * scale > 0 else -1, _const(abs(scale * shift))),
        ]
    )
    expanded = CoreNode.node(T.EQUALS, numerator, expanded_rhs)
    detail = None
    if numerator.type is T.VARIABLE:
        expand_page = SolveResult()
        expand_page.add_group(
            "mul_bracket_each", Step(product, expanded_rhs, "mul_bracket_each", [other])
        )
        expand_page.add_group("calculate_short", Step(expanded_rhs, expanded_rhs, "mul"))
        expand_page.set_solution(expanded)
        detail = expand_page
    ctx.result.add_group(
        "remove_bracket_short",
        Step(multiplied, expanded, "mul_bracket", [other], subresult=detail),
    )
    if numerator.type is T.VARIABLE:
        answer = _linear_rows(expanded, numerator, expanded_rhs, var, ctx)
    else:
        moved_lhs = CoreNode.node(T.SUBTRACT, numerator, _x_term(abs(scale), var))
        moved_rhs = _const(-scale * shift if sign < 0 else scale * shift)
        moved = CoreNode.node(T.EQUALS, moved_lhs, moved_rhs)
        swap = SolveResult()
        swap.add_group(
            "rel_swap_left_var",
            Step(expanded, CoreNode.node(T.EQUALS, moved_lhs, expanded_rhs), "rel_swap_left_var"),
        )
        swap.add_group(
            "remove_opposites",
            Step(
                CoreNode.node(T.EQUALS, moved_lhs, expanded_rhs),
                moved,
                "sub_with_self_remove_alg",
            ),
        )
        swap.set_solution(moved)
        ctx.result.add_group("move", Step(expanded, moved, "rel_move_left_var", subresult=swap))
        answer = _linear_rows(moved, moved_lhs, moved_rhs, var, ctx)
    if answer is None:
        return None
    return _rational_check(ctx, answer, condition)


def _rational_check(ctx: SolveContext, answer: CoreNode, condition: CoreNode) -> CoreNode:
    """The last row: the solution is inside the domain."""
    restricted = CoreNode.node(T.LIST, answer, condition)
    ctx.result.add_group("solution_check_sol", Step(restricted, answer, "rel_restrictions_check"))
    return answer


def _rational_equal_numerators(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """``1/(x-1) = 1/(x-2)``: equal numerators, then the denominators are compared."""
    lhs, rhs = node.children
    left_den = _rational_denominator(lhs, var)
    right_den = _rational_denominator(rhs, var)
    if left_den is None or right_den is None:
        return None
    if not lhs.children[0].structural_eq(rhs.children[0]):
        return None
    if _single_root(left_den, var) is None or _single_root(right_den, var) is None:
        return None
    card = _domain_card(node, var, [left_den, right_den], ctx)
    if card is None:
        return None
    restricted, _condition = card
    x, zero = CoreNode.variable(var), _const(Fraction(0))
    compared = CoreNode.node(T.EQUALS, left_den, right_den)
    ctx.result.add_group("eq_linear_set_den_equal", Step(restricted, compared, "eq_linear_eq_num"))
    reduced = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.SUBTRACT, _const(Fraction(1)), _const(Fraction(2))),
        zero,
    )
    ctx.result.add_group("eq_del_opp", Step(compared, reduced, "eq_del_opp"))
    ctx.result.add_group("rel_el_of_zero", Step(reduced, None, "rel_el_of_zero", [x]))
    return CoreNode.empty()


def _rational_factor_cancel_rows(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """``(x² - 1)/(x - 1) = 0``: factor the numerator, cancel, solve the remaining factor."""
    lhs, rhs = node.children
    denominator = _rational_denominator(lhs, var)
    if denominator is None or rhs.type is not T.CONSTANT or as_fraction(rhs) != 0:
        return None
    numerator = lhs.children[0]
    if not (
        numerator.type is T.SUBTRACT
        and numerator.children[0].type is T.POWER
        and numerator.children[0].children[0].type is T.VARIABLE
        and numerator.children[0].children[1].type is T.CONSTANT
        and numerator.children[0].children[1].value == "2"
        and numerator.children[1].type is T.CONSTANT
    ):
        return None
    c = int(numerator.children[1].value or 0)
    k = isqrt(c)
    if k < 1 or k * k != c:
        return None
    if not (
        denominator.type is T.SUBTRACT
        and denominator.children[0].type is T.VARIABLE
        and denominator.children[1].type is T.CONSTANT
        and int(denominator.children[1].value or 0) == k
    ):
        return None
    card = _domain_card(node, var, [denominator], ctx)
    if card is None:
        return None
    restricted, condition = card
    x, zero, two = CoreNode.variable(var), _const(Fraction(0)), _const(Fraction(2))
    a, b = CoreNode.variable("a"), CoreNode.variable("b")
    formula = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.SUBTRACT, CoreNode.node(T.POWER, a, two), CoreNode.node(T.POWER, b, two)),
        CoreNode.node(
            T.MULTIPLY,
            CoreNode.node(T.BRACKET, CoreNode.node(T.SUBTRACT, a, b)),
            CoreNode.node(T.BRACKET, CoreNode.node(T.ADD, a, b)),
        ),
    )
    written = CoreNode.node(
        T.SUBTRACT, numerator.children[0], CoreNode.node(T.POWER, _const(k), two)
    )
    factored = CoreNode.node(
        T.MULTIPLY,
        CoreNode.node(T.BRACKET, CoreNode.node(T.SUBTRACT, x, _const(k))),
        CoreNode.node(T.BRACKET, CoreNode.node(T.ADD, x, _const(k))),
    )
    page = SolveResult()
    page.add_group("write_as_num_arg", Step(numerator, written, "write_as_num_arg", [two]))
    page.add_group("using_factor", Step(written, factored, "using_factor", [formula]))
    page.set_solution(factored)
    factored_fraction = CoreNode.node(
        T.EQUALS, CoreNode.node(T.FRACTION, factored, denominator), zero
    )
    ctx.result.add_group(
        "factorise_call",
        Step(restricted, factored_fraction, "using_factor", [formula], subresult=page),
    )
    remaining = CoreNode.node(T.ADD, x, _const(k))
    cancelled = CoreNode.node(T.EQUALS, remaining, zero)
    ctx.result.add_group(
        "frac_reduce_frac",
        Step(factored_fraction, cancelled, "frac_reduce_frac_alg", [denominator]),
    )
    balanced = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.SUBTRACT, remaining, _const(k)),
        CoreNode.node(T.SUBTRACT, zero, _const(k)),
    )
    moved = CoreNode.node(T.EQUALS, x, _const(-k))
    move_page = SolveResult()
    move_page.add_group("rel_swap_right_const", Step(cancelled, balanced, "rel_swap_right_const"))
    move_page.add_group(
        "remove_opposites",
        Step(balanced, moved, "sub_with_self_remove_num"),
        Step(balanced, moved, "add_with_zero", [zero]),
    )
    move_page.set_solution(moved)
    ctx.result.add_group(
        "rel_move_right_const_msg",
        Step(cancelled, moved, "rel_move_right_const_eq", subresult=move_page),
    )
    return _rational_check(ctx, moved, condition)


def _solve_rational(node: CoreNode, variables: list[str], ctx: SolveContext) -> CoreNode | None:
    """Решить уравнение с неизвестным в знаменателе.

    Приводит к виду ``числитель / знаменатель = 0``, приравнивает числитель к
    нулю и решает его как многочлен, после чего исключает корни, обращающие
    знаменатель в ноль. Возвращает ``None``, если знаменатель не зависит от
    неизвестного (это не рациональное уравнение).
    """
    var = variables[0]
    lhs, rhs = node.children
    try:
        difference = to_sympy(lhs) - to_sympy(rhs)
        combined = sympy.together(difference)
        numerator, denominator = sympy.fraction(combined)
    except SolveError:
        return None
    if not denominator.has(sympy.Symbol(var)):
        return _degenerate_rational(node, difference, var, variables, ctx)
    if (rows := _rational_factor_cancel_rows(node, var, ctx)) is not None:
        return rows
    if (rows := _rational_multiply_rows(node, var, ctx)) is not None:
        return rows
    if (rows := _rational_equal_numerators(node, var, ctx)) is not None:
        return rows

    add_restriction_steps(node, variables, ctx, combined)
    zero = CoreNode.constant("0")
    one_side = CoreNode.node(T.EQUALS, from_sympy(combined), zero)
    if not one_side.structural_eq(node):
        ctx.result.add(Step(left=node, right=one_side, key="eq_trans"), [_HEADER])

    numerator_eq = CoreNode.node(T.EQUALS, from_sympy(numerator), zero)
    ctx.result.add(
        Step(left=one_side, right=numerator_eq, key="eq_linear_frac_zero", args=[zero]),
        [CoreRichText(type="frac_set_num_zero")],
    )
    if sympy.expand(numerator) == 0:  # (x^2-1)/(x-1) = x+1: true wherever the fraction exists
        ctx.result.add(Step(left=numerator_eq, right=None, key="solutions_inf_many"), [_HEADER])
        return _all_real_except(sympy.solve(denominator, sympy.Symbol(var)))
    answer = solve_equation(numerator_eq, ctx)
    return _exclude_poles(answer, denominator, var, ctx)


def _degenerate_rational(
    node: CoreNode,
    difference: sympy.Expr,
    var: str,
    variables: list[str],
    ctx: SolveContext,
) -> CoreNode | None:
    """``(2x+2)/(x+1) = 2``: the fractions cancel, so it is true everywhere the fraction exists.

    A constant non-zero difference means no solutions; a zero one means every real number except
    the zeros of the denominators. Anything else is not a rational equation.
    """
    symbol = sympy.Symbol(var)
    poles: list[sympy.Expr] = []
    shown_fraction = False
    for part in node.walk():
        if part.type in (T.FRACTION, T.DIVIDE) and len(part.children) == 2:
            denominator = to_sympy(part.children[1])
            if denominator.has(symbol):
                shown_fraction = True
                poles.extend(sympy.solve(denominator, symbol))
    if not shown_fraction:
        return None
    value = sympy.simplify(difference)
    add_restriction_steps(node, variables, ctx, difference)
    if value == 0:
        ctx.result.add(Step(left=node, right=None, key="solutions_inf_many"), [_HEADER])
        return _all_real_except(poles)
    if value.is_number:
        ctx.result.add(Step(left=node, right=None, key="false_statement_solve"), [_HEADER])
        return CoreNode.empty()
    return None


def _all_real_except(poles: list[sympy.Expr]) -> CoreNode:
    """Every real number but the given points, written as a union of open intervals."""
    real = sorted({float(sympy.N(p)): p for p in poles if sympy.N(p).is_real}.items())
    if not real:
        return CoreNode.node(T.OPEN_OPEN_INTERVAL, _neg_infinity(), _positive_infinity())
    bounds = [_neg_infinity(), *[from_sympy(p) for _, p in real], _positive_infinity()]
    pieces = [
        CoreNode.node(T.OPEN_OPEN_INTERVAL, bounds[i], bounds[i + 1])
        for i in range(len(bounds) - 1)
    ]
    union = pieces[0]
    for piece in pieces[1:]:
        union = CoreNode.node(T.UNION, union, piece)
    return union


def _neg_infinity() -> CoreNode:
    return CoreNode.node(T.NEGATIVE, CoreNode.constant("∞"))


def _positive_infinity() -> CoreNode:
    return CoreNode.constant("∞")


def _exclude_poles(
    answer: CoreNode, denominator: sympy.Expr, var: str, ctx: SolveContext
) -> CoreNode:
    """Убрать корни, обращающие знаменатель в ноль."""
    symbol = sympy.Symbol(var)
    roots = _roots_of(answer, var)
    if not roots:
        return answer

    kept: list[CoreNode] = []
    excluded = False
    for value in roots:
        try:
            pole = denominator.subs(symbol, to_sympy(value)) == 0
        except (TypeError, ValueError):
            pole = False
        if pole is True:
            excluded = True
        else:
            kept.append(value)
    if not excluded:
        return answer

    ctx.result.add(Step(left=answer, right=None, key="rel_restrictions_intersect"), [_HEADER])
    filtered = _solutions_node(var, kept)
    ctx.result.add(Step(left=answer, right=filtered, key="rel_restrictions_check"), [_HEADER])
    return filtered


def _roots_of(answer: CoreNode, var: str) -> list[CoreNode]:
    """Значения из ответа ``x = …`` или списка таких равенств."""
    if answer.type is T.EMPTY:
        return []
    items = answer.children if answer.type is T.LIST else [answer]
    roots: list[CoreNode] = []
    for item in items:
        if item.type is not T.EQUALS or len(item.children) != 2:
            continue
        left, right = item.children
        if left.type is T.VARIABLE and left.value == var:
            roots.append(right)
    return roots


def _contradiction_rows(node: CoreNode, var: str, constant: Fraction, result: SolveResult) -> None:
    """The app rows for ``x + 1 = x + 2``: drop the equal terms, then declare it false."""
    x = CoreNode.variable(var)
    reduced = CoreNode.node(T.EQUALS, _const(constant), _const(Fraction(0)))
    result.add_group("eq_del_opp", Step(left=node, right=reduced, key="eq_del_opp"))
    result.add_group(
        "rel_el_of_zero", Step(left=reduced, right=None, key="rel_el_of_zero", args=[x])
    )


def _solutions_node(var: str, values: list[CoreNode]) -> CoreNode:
    """Собрать ответ из значений: одно решение, список или ``EMPTY``."""
    if not values:
        return CoreNode.empty()
    if len(values) == 1:
        return _equation(var, values[0])
    return CoreNode.node(T.LIST, *[_equation(var, value) for value in values])


def _has_radical(expression: sympy.Expr) -> bool:
    """Есть ли в выражении квадратный корень."""
    return any(
        isinstance(power, sympy.Pow) and power.exp == sympy.Rational(1, 2)
        for power in expression.atoms(sympy.Pow)
    )


def _isolate_and_square(lhs: sympy.Expr, rhs: sympy.Expr) -> tuple[sympy.Expr, sympy.Expr] | None:
    """Изолировать слагаемое с радикалом и возвести обе части в квадрат.

    Уравнение ``f = g`` приводится к виду ``r = -h``, где ``r`` -- первое
    слагаемое разности ``f - g`` с радикалом, ``h`` -- остальные слагаемые;
    затем ``r² = h²``. ``None`` -- слагаемого с радикалом нет.
    """
    expr = sympy.expand(lhs - rhs)
    terms = expr.args if isinstance(expr, sympy.Add) else (expr,)
    for term in terms:
        if _has_radical(term):
            rest = expr - term
            return sympy.expand(term**2), sympy.expand(rest**2)
    return None


def _root_equals_negative(node: CoreNode) -> bool:
    """``√f = c`` with a negative constant ``c``: there are no solutions."""
    if node.type is not T.EQUALS or len(node.children) != 2:
        return False
    for root, other in (node.children, tuple(reversed(node.children))):
        if root.type is T.ROOT2 and other.type in (T.CONSTANT, T.NEGATIVE):
            try:
                value = to_sympy(other)
            except SolveError:
                continue
            if value.is_number is True and value.is_negative:
                return True
    return False


def _zero_root_equation(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """``sqrt(f) = 0``: the radicand is zero (worked out for sqrt(x) = 0)."""
    root, number = node.children
    if number.type is T.ROOT2:
        root, number = number, root
    if not (root.type is T.ROOT2 and number.type is T.CONSTANT and number.value == "0"):
        return None
    argument = root.children[0]
    symbol = sympy.Symbol(var)
    try:
        found = sympy.solve(sympy.Eq(to_sympy(argument), 0), symbol)
    except (TypeError, ValueError, NotImplementedError):
        return None
    if len(found) != 1 or found[0].free_symbols:
        return None
    value = from_sympy(found[0])
    eq, zero = CoreNode.node, _const(Fraction(0))
    solution = eq(T.EQUALS, CoreNode.variable(var), value)
    argument_eq = eq(T.EQUALS, argument, zero)
    substituted = from_sympy(to_sympy(argument).subs(symbol, found[0]))
    checked = eq(T.EQUALS, CoreNode.node(T.ROOT2, substituted), zero)
    equal = eq(T.EQUALS, zero, zero)
    ctx.result.add_group(
        "root_set_rad_zero",
        Step(node, argument_eq, "eq_irrational_simple_equals_zero", [zero]),
    )
    ctx.result.add_group("solution_check_sol", Step(solution, checked, "solution_check_sub"))
    ctx.result.add_group("root", Step(checked, equal, "root_zero", [zero]))
    ctx.result.add_group("solution_is", Step(equal, solution, "solution_check_t", [solution]))
    return solution


def _simple_root_equation(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """``sqrt(x) = c`` for a positive integer ``c``, in the rows.

    Square both sides, check the value by substitution, evaluate the root, conclude.
    """
    root, number = node.children
    if number.type is T.ROOT2:
        root, number = number, root
    if not (
        root.type is T.ROOT2
        and root.children[0].type is T.VARIABLE
        and root.children[0].value == var
        and number.type is T.CONSTANT
        and number.value is not None
        and number.value.isdigit()
        and int(number.value) > 0
    ):
        return None
    c = int(number.value)
    x, num = CoreNode.variable(var), CoreNode.constant
    squared_value = num(str(c * c))
    solution = CoreNode.node(T.EQUALS, x, squared_value)
    both = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.POWER, CoreNode.node(T.BRACKET, root), num("2")),
        CoreNode.node(T.POWER, num(str(c)), num("2")),
    )
    detail = SolveResult()
    detail.add_group("eq_irrational_simple_square", Step(node, both, "eq_irrational_simple_square"))
    detail.add_group(
        "calculate_short",
        Step(both, solution, "root_reduce", [_const(Fraction(2))]),
        Step(both, solution, "pow"),
    )
    detail.set_solution(solution)
    ctx.result.add_group(
        "simplify_eq",
        Step(node, solution, "eq_irrational_simple_square", subresult=detail),
    )
    checked = CoreNode.node(T.EQUALS, CoreNode.node(T.ROOT2, squared_value), num(str(c)))
    ctx.result.add_group("solution_check_sol", Step(solution, checked, "solution_check_sub"))
    evaluation = SolveResult()
    evaluation.set_solution(route(checked.children[0], SolveContext(result=evaluation)))
    equal = CoreNode.node(T.EQUALS, num(str(c)), num(str(c)))
    ctx.result.add_group(
        "calculate_short", Step(checked, equal, "root_square", subresult=evaluation)
    )
    ctx.result.add_group(
        CoreRichText(type="solution_check_t", args=[squared_value]),
        Step(equal, solution, "solution_check_t", [squared_value]),
    )
    return solution


def _two_radical_rows(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """``√x + √(x + k) = c``: square twice, collect, divide, check (worked out for c=2, k=1)."""
    lhs, rhs = node.children
    if lhs.type is not T.ADD or len(lhs.children) != 2 or rhs.type is not T.CONSTANT:
        return None
    first, second = lhs.children
    if second.type is T.ROOT2 and first.type is not T.ROOT2:
        first, second = second, first
    if first.type is not T.ROOT2 or second.type is not T.ROOT2:
        return None
    plain, shifted = first.children[0], second.children[0]
    if not (plain.type is T.VARIABLE and plain.value == var):
        return None
    if not (
        shifted.type is T.ADD
        and shifted.children[0].type is T.VARIABLE
        and shifted.children[0].value == var
        and shifted.children[1].type is T.CONSTANT
    ):
        return None
    k = int(shifted.children[1].value or 0)
    try:
        c = as_fraction(rhs)
    except SolveError:
        return None
    if k <= 0 or c.denominator != 1 or c <= k:
        return None
    total = c * c - k
    root = (total / (2 * c)) ** 2
    if total <= 0:
        return None
    eq, chain = CoreNode.node, quadratic_cards._chain
    x = CoreNode.variable(var)
    k_node, total_node = _const(Fraction(k)), _const(total)
    x2 = eq(T.POWER, x, _const(Fraction(2)))
    inner = chain([(1, x2), (1, x)])
    middle = eq(
        T.MULTIPLY,
        _const(Fraction(2)),
        eq(T.ROOT2, eq(T.MULTIPLY, x, eq(T.BRACKET, shifted))),
    )
    squared = eq(T.EQUALS, chain([(1, x), (1, middle), (1, x), (1, k_node)]), _const(c * c))
    rule_plus = eq(
        T.EQUALS,
        eq(
            T.POWER,
            eq(T.BRACKET, eq(T.ADD, CoreNode.variable("a"), CoreNode.variable("b"))),
            _const(Fraction(2)),
        ),
        quadratic_cards._chain(
            [
                (1, eq(T.POWER, CoreNode.variable("a"), _const(Fraction(2)))),
                (
                    1,
                    _node_product(
                        _const(Fraction(2)), CoreNode.variable("a"), CoreNode.variable("b")
                    ),
                ),
                (1, eq(T.POWER, CoreNode.variable("b"), _const(Fraction(2)))),
            ]
        ),
    )
    detail = SolveResult()
    detail.add_group(
        "eq_irrational_simple_square", Step(node, squared, "eq_irrational_simple_square")
    )
    detail.add_group(
        "calculate_short",
        Step(node, squared, "using_expand", [rule_plus]),
        Step(eq(T.POWER, rhs, _const(Fraction(2))), _const(c * c), "pow"),
    )
    detail.set_solution(squared)
    ctx.result.add_group(
        "simplify_eq", Step(node, squared, "eq_irrational_simple_square", subresult=detail)
    )
    # inside the root: x·(x+k) → x² + kx
    middle_plain = eq(T.MULTIPLY, _const(Fraction(2)), eq(T.ROOT2, eq(T.BRACKET, inner)))
    reduced = eq(T.EQUALS, chain([(1, x2), (1, middle_plain), (1, x), (1, k_node)]), _const(c * c))
    mul_page = SolveResult()
    mul_page.add_group(
        "mul_bracket_each",
        Step(eq(T.MULTIPLY, x, shifted), inner, "mul_bracket_each", [x]),
    )
    mul_page.add_group("calculate_short", Step(inner, inner, "product"))
    mul_page.set_solution(inner)
    ctx.result.add_group(
        "simplify_eq",
        Step(squared, reduced, "mul_bracket", [x], subresult=mul_page),
    )
    # x + x = 2x, the constant stays
    twice = eq(T.MULTIPLY, _const(Fraction(2)), x)
    collected = eq(T.EQUALS, chain([(1, middle_plain), (1, twice), (1, k_node)]), _const(c * c))
    like_page = SolveResult()
    like_page.add_group(
        "sum_suffix_add_one",
        Step(twice, twice, "sum_suffix_add_one", [_const(Fraction(1))]),
        Step(twice, twice, "sum_suffix_add_one", [_const(Fraction(1))]),
    )
    like_page.add_group("sum_suffix_add_detail", Step(twice, twice, "sum_suffix_add_detail"))
    like_page.add_group("calculate_short", Step(twice, twice, "add"))
    like_page.set_solution(twice)
    ctx.result.add_group("sum_suffix", Step(reduced, collected, "sum_suffix", subresult=like_page))
    # move everything but the radical to the right
    right_before = chain([(1, eq(T.SUBTRACT, _const(c * c), twice)), (-1, k_node)])
    moved = eq(T.EQUALS, middle_plain, right_before)
    move_page = SolveResult()
    move_page.add_group("rel_swap_right", Step(collected, collected, "rel_swap_right"))
    move_page.add_group(
        "remove_opposites",
        Step(collected, collected, "sub_with_self_remove_alg"),
        Step(collected, collected, "sub_with_self_remove_num"),
    )
    move_page.set_solution(moved)
    ctx.result.add_group(
        "rel_move_right_msg", Step(collected, moved, "rel_move_right", subresult=move_page)
    )
    simplified_right = chain([(1, total_node), (-1, eq(T.MULTIPLY, _const(Fraction(2)), x))])
    simplified_move = eq(T.EQUALS, middle_plain, simplified_right)
    ctx.result.add_group("simplify_eq", Step(moved, simplified_move, "sub"))
    # square again: 4(x²+kx) = ((total² - 4 total x) + 4x²)
    four_left = eq(T.MULTIPLY, _const(Fraction(4)), eq(T.BRACKET, inner))
    four_x2 = eq(T.MULTIPLY, _const(Fraction(4)), x2)
    four_x = eq(T.MULTIPLY, _const(Fraction(4)), x)
    right_chain = chain(
        [
            (
                1,
                eq(
                    T.SUBTRACT,
                    _const(total * total),
                    eq(
                        T.MULTIPLY,
                        _const(Fraction(4)),
                        eq(T.MULTIPLY, total_node, x),
                    ),
                ),
            ),
            (1, four_x2),
        ]
    )
    squared_again = eq(T.EQUALS, four_left, right_chain)
    rule_minus = eq(
        T.EQUALS,
        eq(
            T.POWER,
            eq(T.BRACKET, eq(T.SUBTRACT, CoreNode.variable("a"), CoreNode.variable("b"))),
            _const(Fraction(2)),
        ),
        quadratic_cards._chain(
            [
                (1, eq(T.POWER, CoreNode.variable("a"), _const(Fraction(2)))),
                (
                    -1,
                    _node_product(
                        _const(Fraction(2)), CoreNode.variable("a"), CoreNode.variable("b")
                    ),
                ),
                (1, eq(T.POWER, CoreNode.variable("b"), _const(Fraction(2)))),
            ]
        ),
    )
    square_page = SolveResult()
    square_page.add_group(
        "eq_irrational_simple_square",
        Step(simplified_move, squared_again, "eq_irrational_simple_square"),
    )
    square_page.add_group(
        "calculate_short",
        Step(simplified_move, squared_again, "pow_mul"),
        Step(simplified_move, squared_again, "using_expand", [rule_minus]),
    )
    square_page.set_solution(squared_again)
    ctx.result.add_group(
        "simplify_eq",
        Step(simplified_move, squared_again, "eq_irrational_simple_square", subresult=square_page),
    )
    opened_left = chain([(1, four_x2), (1, four_x)])
    opened = eq(T.EQUALS, opened_left, right_chain)
    ctx.result.add_group(
        "remove_bracket_short", Step(squared_again, opened, "mul_bracket", [_const(Fraction(4))])
    )
    cancelled = eq(T.EQUALS, four_x, simplified_right)
    ctx.result.add_group("simplify_eq", Step(opened, cancelled, "eq_del_opp"))
    moved_left = eq(
        T.EQUALS,
        chain([(1, four_x), (1, eq(T.MULTIPLY, total_node, x))]),
        total_node,
    )
    move_page2 = SolveResult()
    move_page2.add_group("rel_swap_left_var", Step(cancelled, cancelled, "rel_swap_left_var"))
    move_page2.add_group(
        "remove_opposites", Step(cancelled, moved_left, "sub_with_self_remove_alg")
    )
    move_page2.set_solution(moved_left)
    ctx.result.add_group(
        "rel_move_left_msg", Step(cancelled, moved_left, "rel_move_left_var", subresult=move_page2)
    )
    coefficient = Fraction(4) + total
    collected2 = eq(T.EQUALS, eq(T.MULTIPLY, _const(coefficient), x), total_node)
    like_page2 = SolveResult()
    like_page2.add_group(
        "sum_suffix_add_detail", Step(moved_left, collected2, "sum_suffix_add_detail")
    )
    like_page2.add_group("calculate_short", Step(collected2, collected2, "add"))
    like_page2.set_solution(collected2)
    ctx.result.add_group(
        "sum_suffix", Step(moved_left, collected2, "sum_suffix", subresult=like_page2)
    )
    solution = _equation(var, _const(root))
    divide_page = SolveResult()
    divide_page.add_group(
        CoreRichText(type="eq_linear_div", args=[_const(coefficient)]),
        Step(collected2, solution, "eq_linear_div", [_const(coefficient)]),
    )
    divide_page.add_group(
        "divide",
        Step(collected2, solution, "div_with_self", [_const(Fraction(1))]),
        Step(collected2, solution, "div_to_frac"),
    )
    divide_page.set_solution(solution)
    ctx.result.add_group(
        "divide_both_sides",
        Step(collected2, solution, "eq_linear_div", [_const(coefficient)], subresult=divide_page),
    )
    checked = eq(
        T.EQUALS,
        chain(
            [
                (1, eq(T.ROOT2, _fraction_node(root))),
                (1, eq(T.ROOT2, _fraction_node(root + k))),
            ]
        ),
        _const(c),
    )
    ctx.result.add_group("solution_check_sol", Step(solution, checked, "solution_check_sub"))
    simplification = SolveResult()
    simplification.add_group(
        "calculate_short",
        Step(checked, checked, "root_square"),
        Step(checked, checked, "calc_sum"),
        Step(checked, checked, "root_square"),
        Step(checked, checked, "frac_add"),
    )
    simplification.set_solution(checked)
    ctx.result.add_group(
        "simplify_eq", Step(checked, checked, "simplify", subresult=simplification)
    )
    ctx.result.add_group(
        CoreRichText(type="solution_is", args=[solution]),
        Step(checked, checked, "solution_check_t", [solution]),
    )
    return solution


def _affine_radical_rows(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """``√(x + k) = x + m`` with ``k = m²`` and ``m < 0``: the verified radical chain.

    the app (``√(x+1) = x-1``): square both sides with the expansion of the
    right side, cancel equal terms, collect, factor, split, solve, then check both roots
    in the original equation and drop the extraneous one.
    """
    lhs, rhs = node.children
    root_side, other = (lhs, rhs) if lhs.type is T.ROOT2 else (rhs, lhs)
    if root_side.type is not T.ROOT2 or not root_side.children:
        return None
    inner = root_side.children[0]
    if not (inner.type in (T.ADD, T.SUBTRACT) and len(inner.children) == 2):
        return None
    first, second = inner.children
    if first.type is not T.VARIABLE or first.value != var or second.type is not T.CONSTANT:
        return None
    k = int(second.value or 0) * (1 if inner.type is T.ADD else -1)
    if other.type is T.VARIABLE and other.value == var:
        m = 0
    elif (
        other.type in (T.ADD, T.SUBTRACT)
        and other.children[0].type is T.VARIABLE
        and other.children[0].value == var
        and other.children[1].type is T.CONSTANT
    ):
        m = int(other.children[1].value or 0) * (1 if other.type is T.ADD else -1)
    else:
        return None
    if m >= 0 or k != m * m:
        return None
    root = 1 - 2 * m
    eq = CoreNode.node
    x, zero = CoreNode.variable(var), _const(Fraction(0))
    sx = _x_term(Fraction(1), var)
    # x² + 2m x + m²
    expanded_rhs = quadratic_cards._chain(
        [
            (1, eq(T.POWER, x, _const(Fraction(2)))),
            (1 if 2 * m > 0 else -1, _x_term(Fraction(abs(2 * m)), var)),
            (1, _const(Fraction(m * m))),
        ]
    )
    rhs_square = eq(T.POWER, eq(T.BRACKET, other), _const(Fraction(2)))
    identity = eq(
        T.EQUALS,
        rhs_square,
        quadratic_cards._chain(
            [
                (1, eq(T.POWER, CoreNode.variable("a"), _const(Fraction(2)))),
                (
                    -1 if m < 0 else 1,
                    _node_product(
                        _const(Fraction(2)), CoreNode.variable("a"), CoreNode.variable("b")
                    ),
                ),
                (1, eq(T.POWER, CoreNode.variable("b"), _const(Fraction(2)))),
            ]
        ),
    )
    squared = eq(T.EQUALS, inner, expanded_rhs)
    detail = SolveResult()
    detail.add_group(
        "eq_irrational_simple_square", Step(node, squared, "eq_irrational_simple_square")
    )
    detail.add_group(
        "calculate_short",
        Step(inner, inner, "root_reduce", [_const(Fraction(2))]),
        Step(rhs_square, expanded_rhs, "using_expand", [identity]),
    )
    detail.set_solution(squared)
    ctx.result.add_group(
        "simplify_eq", Step(node, squared, "eq_irrational_simple_square", subresult=detail)
    )
    cancelled = eq(T.EQUALS, sx, _x_term(Fraction(1), var))
    cancelled = eq(
        T.EQUALS,
        sx,
        quadratic_cards._chain(
            [
                (1, eq(T.POWER, x, _const(Fraction(2)))),
                (1 if 2 * m > 0 else -1, _x_term(Fraction(abs(2 * m)), var)),
            ]
        ),
    )
    ctx.result.add_group("simplify_eq", Step(squared, cancelled, "eq_del_opp"))
    moved_lhs = eq(
        T.SUBTRACT if -2 * m > 0 else T.ADD,
        eq(T.SUBTRACT, sx, eq(T.POWER, x, _const(Fraction(2)))),
        sx if False else _x_term(Fraction(abs(-2 * m)), var),
    )
    moved = eq(T.EQUALS, moved_lhs, zero)
    swap = SolveResult()
    swap.add_group(
        "rel_swap_left_vars",
        Step(
            cancelled,
            eq(
                T.EQUALS,
                eq(T.SUBTRACT, sx, eq(T.POWER, x, _const(Fraction(2)))),
                _x_term(Fraction(abs(2 * m)), var),
            ),
            "rel_swap_left_vars",
        ),
    )
    swap.add_group(
        "remove_opposites",
        Step(
            eq(
                T.EQUALS,
                eq(T.SUBTRACT, sx, eq(T.POWER, x, _const(Fraction(2)))),
                _x_term(Fraction(abs(2 * m)), var),
            ),
            moved,
            "sub_with_self_alg",
            [zero],
        ),
    )
    swap.set_solution(moved)
    ctx.result.add_group(
        "rel_move_left_var_msg", Step(cancelled, moved, "rel_move_left_vars", subresult=swap)
    )
    coefficient = 1 - 2 * m
    collected = eq(
        T.EQUALS,
        quadratic_cards._chain(
            [
                (1 if coefficient > 0 else -1, _x_term(Fraction(abs(coefficient)), var)),
                (-1, eq(T.POWER, x, _const(Fraction(2)))),
            ]
        ),
        zero,
    )
    grouped_like = eq(
        T.EQUALS,
        eq(
            T.MULTIPLY,
            eq(
                T.BRACKET,
                quadratic_cards._chain([(1, _const(Fraction(1))), (1, _const(Fraction(-2 * m)))]),
            ),
            x,
        ),
        zero,
    )
    like_page = SolveResult()
    like_page.add_group(
        "sum_suffix_add_one",
        Step(moved, moved, "sum_suffix_add_one", [_const(Fraction(1))]),
    )
    like_page.add_group("sum_suffix_add_detail", Step(moved, grouped_like, "sum_suffix_add_detail"))
    like_page.add_group("calculate_short", Step(grouped_like, collected, "add"))
    like_page.set_solution(collected)
    ctx.result.add_group("sum_suffix", Step(moved, collected, "sum_suffix", subresult=like_page))
    bracket = eq(T.SUBTRACT, _const(Fraction(coefficient)), x)
    factored = eq(T.EQUALS, eq(T.MULTIPLY, x, eq(T.BRACKET, bracket)), zero)
    ctx.result.add_group("factorise_call", Step(collected, factored, "extract_arg", [x]))
    cases = eq(T.LIST, eq(T.EQUALS, x, zero), eq(T.EQUALS, bracket, zero))
    ctx.result.add_group(
        "eq_separate_short", Step(factored, cases, "quad_separate_zero_product", [zero])
    )
    solved_branch = eq(T.EQUALS, x, _const(Fraction(root)))
    branch_page = SolveResult()
    branch_page.add_group(
        "rel_move_right_const_eq",
        Step(
            eq(T.EQUALS, eq(T.SUBTRACT, _const(Fraction(coefficient)), x), zero),
            eq(T.EQUALS, eq(T.NEGATIVE, x), _const(Fraction(-coefficient))),
            "rel_move_right_const_eq",
        ),
    )
    branch_page.add_group(
        "rel_linear_neg",
        Step(
            eq(T.EQUALS, eq(T.NEGATIVE, x), _const(Fraction(-coefficient))),
            solved_branch,
            "eq_linear_neg",
        ),
    )
    branch_page.set_solution(solved_branch)
    solved_list = eq(T.LIST, eq(T.EQUALS, x, zero), solved_branch)
    ctx.result.add_group(
        "eq_solve_short", Step(cases, solved_list, "eq_linear", [x], subresult=branch_page)
    )
    # check both roots in the original equation
    checked_zero = eq(T.EQUALS, from_sympy(sympy.sqrt(int(k))), _const(Fraction(m)))
    checked_root = eq(
        T.EQUALS,
        from_sympy(sympy.sqrt(int(k + root))),
        _const(Fraction(root + m)),
    )
    first_check = eq(T.LIST, checked_zero, eq(T.EQUALS, x, solved_branch.children[1]))
    second_check = eq(T.LIST, checked_zero, checked_root)
    ctx.result.add_group(
        "solution_check_sol",
        Step(solved_list, first_check, "solution_check_sub"),
        Step(first_check, second_check, "solution_check_sub"),
    )
    false_page = SolveResult()
    false_page.add_group(
        "simplify_one",
        Step(checked_zero, checked_zero, "add_with_zero", [zero]),
        Step(checked_zero, checked_zero, "root_one", [_const(Fraction(1))]),
        Step(checked_zero, checked_zero, "add_with_zero", [zero]),
    )
    false_page.set_solution(checked_zero)
    true_page = SolveResult()
    true_page.add_group(
        "calculate_short",
        Step(first_check, checked_root, "add"),
        Step(first_check, checked_root, "sub"),
        Step(first_check, checked_root, "root_square"),
    )
    true_page.set_solution(checked_root)
    simplified_list = eq(T.LIST, checked_zero, checked_root)
    ctx.result.add_group(
        ["simplify", "simplify"],
        Step(second_check, simplified_list, "simplify", subresult=false_page),
        Step(second_check, simplified_list, "simplify", subresult=true_page),
    )
    rejected = eq(T.LIST, eq(T.NOT_EQUALS, x, zero), checked_root)
    accepted = eq(T.LIST, eq(T.NOT_EQUALS, x, zero), solved_branch)
    ctx.result.add_group(
        [
            CoreRichText(type="solution_is_not", args=[eq(T.EQUALS, x, zero)]),
            CoreRichText(type="solution_is", args=[solved_branch]),
        ],
        Step(simplified_list, rejected, "solution_check_f", [eq(T.EQUALS, x, zero)]),
        Step(rejected, accepted, "solution_check_t", [solved_branch]),
    )
    ctx.result.add_group("solution_check_one", Step(accepted, solved_branch, "solution_eq_one"))
    return solved_branch


def _node_product(coefficient: CoreNode, *factors: CoreNode) -> CoreNode:
    """``coefficient·f1·f2`` with an explicit multiplication (display helper)."""
    out = CoreNode.node(T.MULTIPLY, coefficient, factors[0])
    for factor in factors[1:]:
        out = CoreNode.node(T.MULTIPLY, out, factor)
    return out


def _solve_radical(node: CoreNode, variables: list[str], ctx: SolveContext) -> CoreNode | None:
    """Решить иррациональное уравнение возведением в квадрат.

    Каждое возведение снимает один радикал: уравнение ``f = g`` превращается
    в ``r² = h²`` и так до многочлена без корней (не более
    ``_MAX_SQUARINGS`` возведений). Полученное уравнение решается как
    многочлен, посторонние корни отсеиваются подстановкой в исходное
    ``f - g``. Возвращает ``None``, если радикалов нет или снять их не
    удаётся.
    """
    var = variables[0]
    lhs, rhs = node.children
    if _root_equals_negative(node):
        # ``√x = -1``: the root is never negative, so there is nothing to solve.
        ctx.result.add(
            Step(
                left=node,
                right=None,
                key="rel_terminators_root_no_sol",
                args=[CoreNode.variable(var), _const(Fraction(0))],
            ),
            [_HEADER],
        )
        return CoreNode.empty()
    if (zero := _zero_root_equation(node, var, ctx)) is not None:
        return zero
    if (simple := _simple_root_equation(node, var, ctx)) is not None:
        return simple
    if (affine := _affine_radical_rows(node, var, ctx)) is not None:
        return affine
    if (two_radical := _two_radical_rows(node, var, ctx)) is not None:
        return two_radical
    try:
        left, right = to_sympy(lhs), to_sympy(rhs)
    except SolveError:
        return None
    if not (_has_radical(left) or _has_radical(right)):
        return None

    add_restriction_steps(node, variables, ctx, left - right)
    current = node
    pair = (left, right)
    for _ in range(_MAX_SQUARINGS):
        if not _has_radical(pair[0] - pair[1]):
            break
        isolated = _isolate_and_square(*pair)
        if isolated is None:
            break
        squared = CoreNode.node(T.EQUALS, from_sympy(isolated[0]), from_sympy(isolated[1]))
        ctx.result.add(
            Step(left=current, right=squared, key="eq_irrational_simple_square"), [_HEADER]
        )
        current, pair = squared, isolated

    if _has_radical(pair[0] - pair[1]):
        return None  # радикал остался — нужно больше возведений, чем позволяем

    answer = solve_equation(current, ctx)
    return _verify_roots(answer, left - right, var, ctx)


def _verify_roots(answer: CoreNode, residual: sympy.Expr, var: str, ctx: SolveContext) -> CoreNode:
    """Оставить только корни, обращающие ``residual`` в ноль."""
    values = _roots_of(answer, var)
    if not values:
        return answer

    symbol = sympy.Symbol(var)
    kept: list[CoreNode] = []
    excluded = False
    for value in values:
        if _satisfies(residual, symbol, value):
            kept.append(value)
        else:
            excluded = True
    if not excluded:
        return answer

    ctx.result.add(Step(left=answer, right=None, key="rel_restrictions_intersect"), [_HEADER])
    filtered = _solutions_node(var, kept)
    ctx.result.add(Step(left=answer, right=filtered, key="rel_restrictions_check"), [_HEADER])
    return filtered


def _satisfies(residual: sympy.Expr, symbol: sympy.Symbol, value: CoreNode) -> bool:
    """Обращается ли ``residual`` в ноль при данном значении переменной."""
    try:
        difference = sympy.simplify(residual.subs(symbol, to_sympy(value)))
    except (TypeError, ValueError):
        return True
    result = difference == 0
    if isinstance(result, bool):
        return result
    return result is sympy.true


def _solve_transcendental(
    node: CoreNode, variables: list[str], ctx: SolveContext
) -> CoreNode | None:
    """Решить показательное или логарифмическое уравнение.

    Шаг-преобразование показывает эквивалентную форму: ``eq_log_equalise``
    (одинаковые основания логарифмов → приравнять аргументы), ``eq_pow_eq``
    (одинаковые основания степеней → приравнять показатели) или ``eq_trans``
    (переход логарифм ↔ степень). Корни берёт sympy из исходного уравнения и
    проверяет подстановкой (область определения логарифма). Не такой случай —
    ``None``.
    """
    var = variables[0]
    lhs, rhs = node.children
    try:
        left, right = to_sympy(lhs), to_sympy(rhs)
    except SolveError:
        return None
    if (rows := _log_rows(node, var, ctx)) is not None:
        return rows
    if (rows := _log_substitution_rows(node, var, ctx)) is not None:
        return rows
    if (rows := _exp_equation_rows(node, variables, ctx)) is not None:
        return rows

    transformed = _log_exp_transform(left, right)
    if transformed is None:
        if _impossible_exponential(left, right) or _impossible_exponential(right, left):
            # a^x > 0 при a > 0: неположительная правая часть — решений нет.
            ctx.result.add(
                Step(
                    left=node,
                    right=None,
                    key="exp_eq_no_sol_eq",
                    args=[CoreNode.variable(var)],
                ),
                [_HEADER],
            )
            return CoreNode.empty()
        return None
    key, equation = transformed

    add_restriction_steps(node, variables, ctx, left - right)
    symbol = sympy.Symbol(var)
    try:
        found = sympy.solve(sympy.Eq(left, right), symbol)
    except (TypeError, ValueError, NotImplementedError):
        return None

    roots: list[sympy.Expr] = []
    rejected = False
    for root in found:
        if not _is_real_root(root):
            continue
        if not _satisfies(left - right, symbol, from_sympy(root)):
            rejected = True
            continue
        if any(sympy.simplify(root - known) == 0 for known in roots):
            continue
        roots.append(root)
    roots.sort(key=_sort_key)

    ctx.result.add(Step(left=node, right=from_sympy(equation), key=key), [_HEADER])
    if rejected:
        ctx.result.add(Step(left=node, right=None, key="rel_restrictions_check"), [_HEADER])
    if not roots:
        return CoreNode.empty()
    return _solutions_node(var, [from_sympy(root) for root in roots])


def _sort_key(root: sympy.Expr) -> float:
    """Ключ сортировки корней; нечисловые корни идут первыми."""
    try:
        return float(sympy.N(root))
    except (TypeError, ValueError):
        return 0.0


def _log_law() -> tuple[CoreNode, CoreNode]:
    """``log(a, x) = b  ⇔  x = a^b`` as the explanation argument pair."""
    law = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.LOG, CoreNode.variable("x"), CoreNode.variable("a")),
        CoreNode.variable("b"),
    )
    law_power = CoreNode.node(
        T.EQUALS,
        CoreNode.variable("x"),
        CoreNode.node(T.POWER, CoreNode.variable("a"), CoreNode.variable("b")),
    )
    return law, law_power


def _inverse_power_law() -> CoreNode:
    """``1/aⁿ = a⁻ⁿ`` — the law behind ``write_as_exp`` (``(1/2)ˣ = 2⁻ˣ``)."""
    a, n = CoreNode.variable("a"), CoreNode.variable("n")
    return CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.FRACTION, _const(Fraction(1)), CoreNode.node(T.POWER, a, n)),
        CoreNode.node(T.POWER, a, CoreNode.node(T.NEGATIVE, n)),
    )


def _power_of_power_law() -> CoreNode:
    """``(aᵐ)ⁿ = (aⁿ)ᵐ`` — the law behind ``using_trans`` for ``4ˣ = (2ˣ)²``."""
    a, m, n = (CoreNode.variable(name) for name in ("a", "m", "n"))
    return CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.POWER, CoreNode.node(T.BRACKET, CoreNode.node(T.POWER, a, m)), n),
        CoreNode.node(T.POWER, CoreNode.node(T.BRACKET, CoreNode.node(T.POWER, a, n)), m),
    )


def _log_of_power_law() -> CoreNode:
    """``log_a(aˣ) = x`` — the law behind ``using_sim`` after taking a logarithm."""
    a, x = CoreNode.variable("a"), CoreNode.variable("x")
    return CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.LOG, CoreNode.node(T.POWER, a, x), a),
        x,
    )


def _log_sum_law(template: CoreNode, minus: bool) -> CoreNode:
    """``log_a x + log_a y = log_a(xy)`` — the law behind the ``using_sim`` join."""

    def log_of(argument: CoreNode) -> CoreNode:
        if template.type is T.LOG10:
            return CoreNode.node(T.LOG10, argument)
        if template.type is T.LN:
            return CoreNode.node(T.LN, argument)
        return CoreNode.node(T.LOG, argument, _log_base_node(template))

    x, y = CoreNode.variable("x"), CoreNode.variable("y")
    joined = (
        CoreNode.node(T.FRACTION, x, y)
        if minus
        else CoreNode.node(T.BRACKET, CoreNode.node(T.MULTIPLY, x, y))
    )
    return CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.SUBTRACT if minus else T.ADD, log_of(x), log_of(y)),
        log_of(joined),
    )


def _diff_squares_law() -> CoreNode:
    """``(a − b)(a + b) = a² − b²`` — the law behind ``factorise_inv_sim``."""
    a, b = CoreNode.variable("a"), CoreNode.variable("b")
    return CoreNode.node(
        T.EQUALS,
        CoreNode.node(
            T.MULTIPLY_IMPLICIT,
            CoreNode.node(T.BRACKET, CoreNode.node(T.SUBTRACT, a, b)),
            CoreNode.node(T.BRACKET, CoreNode.node(T.ADD, a, b)),
        ),
        CoreNode.node(
            T.SUBTRACT,
            CoreNode.node(T.POWER, a, _const(Fraction(2))),
            CoreNode.node(T.POWER, b, _const(Fraction(2))),
        ),
    )


def _power_value_page(base: CoreNode, exponent: int, value: CoreNode) -> SolveResult | None:
    """Detail page for ``2^3``: repeated multiplication, then the product."""
    if base.type is not T.CONSTANT or exponent < 2:
        return None
    detail = SolveResult()
    power = CoreNode.node(T.POWER, base, _const(Fraction(exponent)))
    product = base
    for _ in range(exponent - 1):
        product = CoreNode.node(T.MULTIPLY, product, base)
    detail.add_group("pow_to_mul", Step(power, product, "pow_to_mul"))
    detail.add_group("calculate_short", Step(product, value, "mul"))
    detail.set_solution(value)
    return detail


def _log_argument_node(log_side: CoreNode) -> CoreNode:
    """Аргумент логарифма как узел."""
    return log_side.children[0]


def _log_base_node(log_side: CoreNode) -> CoreNode:
    """Основание логарифма как узел (``10`` у ``lg``, ``e`` у ``ln``)."""
    if log_side.type is T.LOG and len(log_side.children) == 2:
        return log_side.children[1]
    if log_side.type is T.LOG10:
        return _const(Fraction(10))
    return CoreNode.constant("e")


def _condition_node(set_expr: sympy.Set, x: CoreNode) -> CoreNode:
    """Множество значений как условие на ``x``.

    Полубесконечный промежуток читается неравенством (``x > 1/2``), остальное —
    ``x ∈ …`` (объединение промежутков, отрезок, отдельные точки).
    """
    if isinstance(set_expr, sympy.Interval):
        if set_expr.start is -sympy.oo:
            kind = T.LESS_THAN if set_expr.right_open else T.LESS_THAN_EQUAL
            return CoreNode.node(kind, x, from_sympy(set_expr.end))
        if set_expr.end is sympy.oo:
            kind = T.GREATER_THAN if set_expr.left_open else T.GREATER_THAN_EQUAL
            return CoreNode.node(kind, x, from_sympy(set_expr.start))
    return CoreNode.node(T.ELEMENT_OF, x, from_sympy(set_expr))


def _log_domain(
    node: CoreNode,
    var: str,
    logs: list[tuple[CoreNode, tuple[sympy.Expr, sympy.Expr]]],
) -> tuple[CoreNode | None, SolveResult, list[sympy.Basic]]:
    """The app's domain card for ``log_b f(x) = c``: the argument and the base.

    Each restriction is shown as the rejected values (the argument is ``≤ 0``; the base is
    ``≤ 0`` or ``= 1``), the ordinary inequality row solves them, and the complement is the
    condition the equation is solved under. ``logs`` is ``[(log node, (argument, base))]``
    — one entry per logarithm of the equation, so both arguments count.

    Returns the condition (``None`` when nothing restricts ``x``), the detail screen and the
    conditions every root has to satisfy.
    """
    symbol = sympy.Symbol(var)
    x, zero, one = CoreNode.variable(var), _const(Fraction(0)), _const(Fraction(1))
    detail = SolveResult()
    find_steps: list[Step] = []
    parts: list[CoreNode] = []
    solved_parts: list[bool] = []  # whether the restriction still needs an inequality row
    rejected: list[sympy.Set] = []
    constraints: list[sympy.Basic] = []
    seen_arguments: set[str] = set()
    seen_bases: set[str] = set()
    for side, (argument, base) in logs:
        if argument.has(symbol) and sympy.srepr(argument) not in seen_arguments:
            seen_arguments.add(sympy.srepr(argument))
            constraints.append(sympy.Gt(argument, 0))
            try:
                forbidden = sympy.solve_univariate_inequality(
                    sympy.Le(argument, 0), symbol, relational=False
                )
            except (NotImplementedError, TypeError, ValueError):
                return None, detail, constraints
            forbidden = sympy.simplify(forbidden)
            if forbidden is sympy.EmptySet:
                continue
            rejected.append(forbidden)
            argument_node = _log_argument_node(side)
            condition = CoreNode.node(T.LESS_THAN_EQUAL, argument_node, zero)
            parts.append(condition)
            # for `log_b x` the rejected set already is `x ≤ c`; a compound argument needs
            # the ordinary inequality row that turns it into one
            solved_parts.append(argument != symbol)
            find_steps.append(Step(node, condition, "rel_restrictions_log_arg", [x, side, zero]))
        if base.has(symbol) and sympy.srepr(base) not in seen_bases:
            seen_bases.add(sympy.srepr(base))
            constraints.extend([sympy.Gt(base, 0), sympy.Ne(base, 1)])
            base_node = _log_base_node(side)
            conditions = [
                CoreNode.node(T.LESS_THAN_EQUAL, base_node, zero),
                CoreNode.node(T.EQUALS, base_node, one),
            ]
            rejected.append(
                sympy.Union(sympy.Interval(-sympy.oo, 0, right_open=False), sympy.FiniteSet(1))
            )
            parts.extend(conditions)
            solved_parts.extend([True, True])
            find_steps.append(
                Step(
                    node,
                    CoreNode.node(T.VERTICAL_LIST, *conditions),
                    "rel_restrictions_log_base",
                    [x, zero, one, side],
                )
            )
    if not rejected:
        return None, detail, constraints
    # every restriction lives in one «find the excluded values» step, as the app groups them
    detail.add_group("rel_restrictions_find", *find_steps)
    forbidden = sympy.simplify(sympy.Union(*rejected))
    solved = _condition_node(forbidden, x)
    if len(parts) > 1:
        detail.add_group("union", Step(CoreNode.node(T.VERTICAL_LIST, *parts), solved, "union"))
    elif solved_parts[0]:
        detail.add_group("ineq_solve_short", Step(parts[0], solved, "ineq_linear", [x]))
    condition = _condition_node(sympy.simplify(sympy.Complement(sympy.S.Reals, forbidden)), x)
    restricted = CoreNode.node(T.LIST, node, condition)
    detail.add_group(
        "exclude_values",
        Step(solved, restricted, "rel_restrictions_range_complement"),
    )
    detail.set_solution(restricted)
    return condition, detail, constraints


def _keep_in_domain(answer: CoreNode, var: str, constraints: list[sympy.Basic]) -> CoreNode:
    """Drop the roots that fail the domain (``x = -4`` for a base ``x``)."""
    if not constraints:
        return answer
    symbol = sympy.Symbol(var)
    roots = _roots_of(answer, var)
    kept: list[CoreNode] = []
    for root in roots:
        value = to_sympy(root)
        try:
            allowed = all(
                sympy.simplify(item.subs(symbol, value)) is sympy.true for item in constraints
            )
        except (TypeError, ValueError):
            allowed = True
        if allowed:
            kept.append(root)
    if len(kept) == len(roots):
        return answer
    if not kept:
        return CoreNode.empty()
    return _solutions_node(var, kept)


def _log_rows(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """Logarithmic equation in the app's rows: domain card, conversion, check.

    Worked out on: ``ln x = ln 3`` (equalise the arguments) and ``log(2, x) = 3``
    (rewrite ``f(x) = b^c``, solve that equation with the ordinary rows, check the domain).
    """
    lhs, rhs = node.children
    try:
        left, right = to_sympy(lhs), to_sympy(rhs)
    except SolveError:
        return None
    if (sum_rows := _log_sum_rows(node, var, ctx)) is not None:
        return sum_rows
    transform = _log_exp_transform(left, right)
    if transform is None or transform[0] not in ("eq_log_equalise", "log_def_solve"):
        return None
    left_log, right_log = _single_log(left), _single_log(right)
    log_side = lhs if left_log is not None else rhs
    logs = [(side, pair) for side, pair in ((lhs, left_log), (rhs, right_log)) if pair is not None]
    condition, detail, constraints = _log_domain(node, var, logs)
    if condition is not None:
        restricted = CoreNode.node(T.LIST, node, condition)
        ctx.result.add_group(
            "rel_restrictions_range",
            Step(node, restricted, "rel_restrictions_range", subresult=detail),
        )
    else:
        restricted = node
    key, transformed = transform
    if key == "log_def_solve":
        pair = left_log or right_log
        if pair is None:
            return None
        base = pair[1]
        other = right if left_log is not None else left
        argument_node, base_node = _log_argument_node(log_side), _log_base_node(log_side)
        if other.is_zero:
            # log_b(f) = 0 -> the argument is b^0 = 1 (worked out for log(x) = 0)
            one = _const(Fraction(1))
            converted = CoreNode.node(T.EQUALS, argument_node, one)
            ctx.result.add_group(
                CoreRichText(type="log_set_arg_zero", args=[one]),
                Step(
                    restricted,
                    _with_condition(converted, condition),
                    "eq_log_zero_msg",
                    [_const(Fraction(0)), one],
                ),
            )
            equation = converted
        else:
            power = CoreNode.node(T.POWER, base_node, from_sympy(other))
            converted = CoreNode.node(T.EQUALS, argument_node, power)
            law, law_power = _log_law()
            ctx.result.add_group(
                "log_convert_to_exp",
                Step(restricted, converted, "eq_log_formula_convert", [law, law_power]),
            )
            equation = converted
            if other.is_Integer and base.is_Rational and (base**other).is_Rational:
                # 3^2 = 9: The app evaluates the power on its own row and then solves f(x) = 9
                value = from_sympy(base**other)
                equation = CoreNode.node(T.EQUALS, argument_node, value)
                page = None if other == 1 else _power_value_page(base_node, int(other), value)
                ctx.result.add_group(
                    "calculate_short",
                    Step(
                        converted,
                        equation,
                        "pow_with_one" if other == 1 else "pow",
                        [from_sympy(other)] if other == 1 else [],
                        subresult=page,
                    ),
                )
    else:
        pair = left_log or right_log
        if pair is None:
            return None
        converted = from_sympy(transformed)
        ctx.result.add_group(
            "eq_log_set_arg_equal",
            Step(restricted, _with_condition(converted, condition), "eq_log_equalise"),
        )
        equation = converted
    if not _has_unknown(equation.children[0], var) and _has_unknown(equation.children[1], var):
        # ``16 = x²``: The app swaps the sides before solving (``rel_swap_eq``)
        swapped = CoreNode.node(T.EQUALS, equation.children[1], equation.children[0])
        ctx.result.add_group("rel_switch", Step(equation, swapped, "rel_swap_eq"))
        equation = swapped
    # The ordinary card of the converted equation: the very steps the app shows for it.
    scratch = SolveResult()
    answer: CoreNode | None = None
    try:
        methods = methods_for(equation, [var])
    except SolveError:
        methods = None
    if methods:
        scratch, answer = methods[0], methods[0].solution
    if answer is None:
        try:
            answer = solve_equation(equation, SolveContext(result=scratch, variables=[var]))
        except SolveError:
            symbol = sympy.Symbol(var)
            try:
                found = sympy.solve(sympy.Eq(left, right), symbol)
            except (TypeError, ValueError, NotImplementedError):
                return None
            found = [root for root in found if _is_real_root(root)]
            if not found:
                return None
            answer = _solutions_node(var, [from_sympy(root) for root in found])
            scratch = SolveResult()
    ctx.result.extend(scratch)
    answer = _exp_form(answer, var)
    kept = _keep_in_domain(answer, var, constraints)
    ctx.result.add_group(
        "solution_check_sol",
        Step(_with_condition(answer, condition), kept, "rel_restrictions_check"),
    )
    return kept


def _exp_form(answer: CoreNode, var: str) -> CoreNode:
    """``x = e^k`` reads as the ``EXP`` node (``ln x = 2`` -> ``x = e²``)."""
    if (
        answer.type is T.EQUALS
        and answer.children[0].type is T.VARIABLE
        and answer.children[0].value == var
        and answer.children[1].type is T.POWER
        and answer.children[1].children[0].type is T.CONSTANT
        and answer.children[1].children[0].value == "e"
    ):
        exponent = answer.children[1].children[1]
        return CoreNode.node(
            T.EQUALS, answer.children[0], from_sympy(sympy.exp(to_sympy(exponent)))
        )
    return answer


def _collect_log_nodes(side: CoreNode) -> list[CoreNode]:
    """Все логарифмы внутри стороны уравнения, в порядке появления."""
    return [part for part in side.walk() if part.type in (T.LOG, T.LOG10, T.LN)]


def _signed_terms(node: CoreNode) -> list[tuple[int, CoreNode]]:
    """Слагаемые суммы со знаками: ``+log₂(x+1)``, ``−log₂(x−1)``."""
    out: list[tuple[int, CoreNode]] = []

    def visit(part: CoreNode, sign: int) -> None:
        if part.type in (T.ADD, T.SUBTRACT) and len(part.children) == 2:
            visit(part.children[0], sign)
            visit(part.children[1], -sign if part.type is T.SUBTRACT else sign)
            return
        if part.type is T.NEGATIVE and len(part.children) == 1:
            visit(part.children[0], -sign)
            return
        out.append((sign, part))

    visit(node, 1)
    return out


def _bracket_if_sum(node: CoreNode) -> CoreNode:
    """Аргумент логарифма: сумму берём в скобки."""
    if node.type in (T.ADD, T.SUBTRACT):
        return CoreNode.node(T.BRACKET, node)
    return node


def _log_like(argument: CoreNode, template: CoreNode) -> CoreNode:
    """``log``/``lg``/``ln`` от нового аргумента — как у образца.

    Произведение берётся в скобки: ``log₂(x+1)·(x−1)`` иначе читается как
    ``log₂(x+1)`` умножить на ``(x−1)``.
    """
    if argument.type is T.MULTIPLY:
        argument = CoreNode.node(T.BRACKET, argument)
    if template.type is T.LOG10:
        return CoreNode.node(T.LOG10, argument)
    if template.type is T.LN:
        return CoreNode.node(T.LN, argument)
    return CoreNode.node(T.LOG, argument, _log_base_node(template))


def _joined_argument(terms: list[tuple[int, CoreNode]]) -> sympy.Expr:
    """Произведение аргументов (со знаками): ``(x+1)(x−1)``."""
    result: sympy.Expr = sympy.Integer(1)
    for sign, term in terms:
        argument = to_sympy(_log_argument_node(term))
        result *= argument if sign > 0 else 1 / argument
    return result


def _is_conjugate_pair(terms: list[tuple[int, CoreNode]]) -> bool:
    """``(x+1)`` и ``(x−1)``: разность квадратов (ключ ``factorise_inv_sim``)."""
    if len(terms) != 2 or any(sign < 0 for sign, _ in terms):
        return False
    first = sympy.expand(to_sympy(_log_argument_node(terms[0][1])))
    second = sympy.expand(to_sympy(_log_argument_node(terms[1][1])))
    total = sympy.expand(first + second)
    difference = sympy.expand(first - second)
    if not bool(difference.is_number):
        return False
    # ``a + b`` и ``a − b``: сумма даёт ``2a`` без свободного члена
    return bool(total.free_symbols) and total.subs({item: 0 for item in total.free_symbols}) == 0


def _solve_converted(
    equation: CoreNode,
    condition: CoreNode,
    constraints: list[sympy.Basic],
    var: str,
    ctx: SolveContext,
) -> CoreNode | None:
    """Обычные строки для уравнения после перехода и проверка области определения."""
    equation = _pre_move_constant(equation, var, ctx)
    scratch = SolveResult()
    answer: CoreNode | None = None
    try:
        methods = methods_for(equation, [var])
    except SolveError:
        methods = None
    if methods:
        scratch, answer = methods[0], methods[0].solution
    if answer is None:
        try:
            answer = solve_equation(equation, SolveContext(result=scratch, variables=[var]))
        except SolveError:
            return None
    ctx.result.extend(scratch)
    roots_before = len(_roots_of(answer, var))
    kept = _keep_in_domain(answer, var, constraints)
    if roots_before > 1 and len(_roots_of(kept, var)) <= 1:
        # the domain check kept a single root: The app drops the numbering row
        _drop_group(ctx.result, "solution_eq_num")
    ctx.result.add_group(
        "solution_check_sol",
        Step(_with_condition(answer, condition), kept, "rel_restrictions_check"),
    )
    return kept


def _pre_move_constant(equation: CoreNode, var: str, ctx: SolveContext) -> CoreNode:
    """``f(x) − k = c``: move the constant to the right (``rel_move_right_const_eq``, ``add``).

    The ordinary quadratic card starts at ``f(x) = c + k``, so the row that performs the
    move would be missing; The app shows it (``x² − 1 = 8`` → ``x² = 8 + 1`` → ``x² = 9``).
    """
    lhs, rhs = equation.children
    if lhs.type is not T.SUBTRACT or len(lhs.children) != 2:
        return equation
    inner, subtrahend = lhs.children
    if _rational_value(subtrahend) is None or not _has_unknown(inner, var):
        return equation
    try:
        value = to_sympy(rhs)
    except SolveError:
        return equation
    if not value.is_number:
        return equation
    moved = CoreNode.node(T.EQUALS, inner, CoreNode.node(T.ADD, rhs, subtrahend))
    ctx.result.add_group(
        "rel_move_right_const_msg", Step(equation, moved, "rel_move_right_const_eq")
    )
    evaluated = CoreNode.node(
        T.EQUALS, inner, from_sympy(sympy.simplify(value + to_sympy(subtrahend)))
    )
    ctx.result.add_group("calculate_short", Step(moved, evaluated, "add"))
    return evaluated


def _drop_group(result: SolveResult, key: str) -> None:
    """Убрать группу с данным заголовком (нумерация корней, когда корень остался один)."""
    result._steps = [entry for entry in result._steps if not any(h.type == key for h in entry[0])]


def _log_sum_rows(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """``log_a f + log_a g = c``: ОДЗ каждого логарифма, объединение, переход, обычные строки."""
    lhs, rhs = node.children
    try:
        left, right = to_sympy(lhs), to_sympy(rhs)
    except SolveError:
        return None
    if right.is_number:
        log_side, number_side = lhs, rhs
    elif left.is_number:
        log_side, number_side = rhs, lhs
    else:
        return None
    terms = _signed_terms(log_side)
    if len(terms) < 2 or any(term.type not in (T.LOG, T.LOG10, T.LN) for _, term in terms):
        return None
    bases = {to_sympy(_log_base_node(term)) for _, term in terms}
    if len(bases) != 1:
        return None
    base = next(iter(bases))
    logs = [(term, (to_sympy(_log_argument_node(term)), base)) for _, term in terms]
    condition, detail, constraints = _log_domain(node, var, logs)
    if condition is None:
        return None
    restricted = CoreNode.node(T.LIST, node, condition)
    ctx.result.add_group(
        "rel_restrictions_range",
        Step(node, restricted, "rel_restrictions_range", subresult=detail),
    )
    numerator = [term for sign, term in terms if sign > 0]
    denominator = [term for sign, term in terms if sign < 0]
    if not numerator:
        return None

    def product(items: list[CoreNode]) -> CoreNode:
        nodes = [_bracket_if_sum(_log_argument_node(item)) for item in items]
        result = nodes[0]
        for item in nodes[1:]:
            result = CoreNode.node(T.MULTIPLY, result, item)
        return result

    joined_arg = product(numerator)
    if denominator:
        joined_arg = CoreNode.node(T.FRACTION, joined_arg, product(denominator))
    joined = CoreNode.node(T.EQUALS, _log_like(joined_arg, terms[0][1]), number_side)
    ctx.result.add_group(
        "simplify", Step(restricted, joined, "using_sim", [_log_sum_law(terms[0][1], False)])
    )
    try:
        expanded_arg = sympy.expand(_joined_argument(terms))
    except (TypeError, ValueError):
        return None
    expanded = CoreNode.node(
        T.EQUALS, _log_like(from_sympy(expanded_arg), terms[0][1]), number_side
    )
    conjugate = _is_conjugate_pair(terms)
    key = "factorise_inv_sim" if conjugate else "mul_bracket"
    if conjugate:
        args = [_diff_squares_law()]
    else:
        args = [_bracket_if_sum(_log_argument_node(numerator[0]))]
    title = "mul_simplify_prod" if conjugate else "remove_bracket_short"
    ctx.result.add_group(title, Step(joined, expanded, key, args))
    bound = to_sympy(number_side)
    if not bound.is_Integer:
        return None
    base_node = _log_base_node(terms[0][1])
    power = CoreNode.node(T.POWER, base_node, from_sympy(bound))
    converted = CoreNode.node(T.EQUALS, from_sympy(expanded_arg), power)
    law, law_power = _log_law()
    ctx.result.add_group(
        "log_convert_to_exp",
        Step(
            expanded,
            _with_condition(converted, condition),
            "eq_log_formula_convert",
            [law, law_power],
        ),
    )
    equation = converted
    if base.is_Rational and (base**bound).is_Rational:
        value = from_sympy(base**bound)
        equation = CoreNode.node(T.EQUALS, from_sympy(expanded_arg), value)
        if bound == 1:
            ctx.result.add_group(
                "pow",
                Step(converted, equation, "pow_with_one", [from_sympy(bound)]),
            )
        else:
            ctx.result.add_group(
                "evaluate",
                Step(
                    converted,
                    equation,
                    "pow",
                    subresult=_power_value_page(base_node, int(bound), value),
                ),
            )
    return _solve_converted(equation, condition, constraints, var, ctx)


def _log_substitution_rows(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """``log²ₐx + p·logₐx + q = 0``: замена ``t = logₐx``, квадратное, обратная замена."""
    lhs, rhs = node.children
    try:
        expr = to_sympy(lhs) - to_sympy(rhs)
    except SolveError:
        return None
    symbol = sympy.Symbol(var)
    log_nodes: list[CoreNode] = []
    for side in (lhs, rhs):
        for part in side.walk():
            if part.type in (T.LOG, T.LOG10, T.LN) and not any(
                part.structural_eq(seen) for seen in log_nodes
            ):
                log_nodes.append(part)
    if len(log_nodes) != 1:
        return None
    log_node = log_nodes[0]
    argument = to_sympy(_log_argument_node(log_node))
    base = to_sympy(_log_base_node(log_node))
    if not argument.has(symbol):
        return None
    dummy = sympy.Dummy("u")
    atom = sympy.log(argument)
    replacement = dummy if base == sympy.E else dummy * sympy.log(base)
    substituted = sympy.simplify(sympy.expand(expr.xreplace({atom: replacement})))
    if substituted.has(symbol):
        return None
    try:
        poly = sympy.Poly(substituted, dummy)
    except sympy.PolynomialError:
        return None
    if poly.degree() != 2:
        return None
    coefficients = [
        poly.coeff_monomial(dummy**2),
        poly.coeff_monomial(dummy),
        poly.coeff_monomial(1),
    ]
    if any(not coefficient.is_Rational for coefficient in coefficients):
        return None
    condition, detail, constraints = _log_domain(node, var, [(log_node, (argument, base))])
    if condition is None:
        return None
    restricted = CoreNode.node(T.LIST, node, condition)
    ctx.result.add_group(
        "rel_restrictions_range",
        Step(node, restricted, "rel_restrictions_range", subresult=detail),
    )
    t = CoreNode.variable("t")
    polynomial = _sum_terms(
        [(coefficients[0], CoreNode.node(T.POWER, t, _const(Fraction(2)))), (coefficients[1], t)],
        coefficients[2],
    )
    substituted_eq = CoreNode.node(T.EQUALS, polynomial, _const(Fraction(0)))
    substitution = CoreNode.node(T.EQUALS, t, log_node)
    ctx.result.add_group(
        "eq_solve_sub", Step(restricted, substituted_eq, "eq_solve_sub", [substitution])
    )
    solved = _exp_append(substituted_eq, "t", ctx)
    if solved is None:
        return None
    polynomial_in_t = sum(
        c * dummy**power for c, power in zip(coefficients, (2, 1, 0), strict=True)
    )
    values = sympy.solve(sympy.Eq(polynomial_in_t, 0), dummy)
    values = [value for value in values if value.is_real]
    if not values:
        return None
    back = CoreNode.node(
        T.LIST,
        *[CoreNode.node(T.EQUALS, log_node, from_sympy(value)) for value in values],
    )
    ctx.result.add_group("sub_msg_ret", Step(solved, back, "sub_msg_ret", [substitution]))
    roots = [
        CoreNode.node(T.EQUALS, CoreNode.variable(var), from_sympy(base**value)) for value in values
    ]
    roots_list = CoreNode.node(T.LIST, *roots)
    ctx.result.add_group("eq_solve_short_plural", Step(back, roots_list, "eq_linear", [t]))
    kept = _keep_in_domain(roots_list, var, constraints)
    ctx.result.add_group(
        "solution_check_sol",
        Step(_with_condition(roots_list, condition), kept, "rel_restrictions_check"),
    )
    if not kept.structural_eq(roots_list):
        ctx.result.add_group(
            CoreRichText(type="solution_eq_num", args=[_const(Fraction(len(roots)))]),
            Step(roots_list, kept, "solution_eq_num", [_const(Fraction(len(roots)))]),
        )
    return kept


def _with_condition(equation: CoreNode, condition: CoreNode | None) -> CoreNode:
    """The equation alone, or ``[equation, condition]`` when the domain is restricted."""
    if condition is None:
        return equation
    return CoreNode.node(T.LIST, equation, condition)


def _log_rewrite_card(node: CoreNode, var: str) -> SolveResult | None:
    """The second card the app shows for a single logarithm: ``log(a, x) = b ⇒ x = a^b``."""
    lhs, rhs = node.children
    try:
        left, right = to_sympy(lhs), to_sympy(rhs)
    except SolveError:
        return None
    pair = _single_log(left) or _single_log(right)
    if pair is None:
        return None
    argument, base = pair
    if argument != sympy.Symbol(var):
        return None
    other = right if _single_log(left) is not None else left
    if other.free_symbols:
        return None
    converted = _equation(var, from_sympy(sympy.Pow(base, other, evaluate=False)))
    law, law_power = _log_law()
    result = SolveResult()
    result.add_group(
        "log_convert_to_exp",
        Step(node, converted, "eq_log_formula_convert", [law, law_power]),
    )
    result.set_solution(converted)
    return result


def _log_equation_methods(node: CoreNode, variables: list[str]) -> list[SolveResult] | None:
    """The app's two cards for a single logarithm, or ``None``."""
    if len(variables) != 1 or node.type is not T.EQUALS:
        return None
    lhs, rhs = node.children
    try:
        left, right = to_sympy(lhs), to_sympy(rhs)
    except SolveError:
        return None
    transform = _log_exp_transform(left, right)
    if transform is None or transform[0] not in ("eq_log_equalise", "log_def_solve"):
        return None
    primary = _run(
        node,
        variables,
        lambda n, c: _solve_transcendental(n, variables, c) or CoreNode.empty(),
    )
    if primary.solution is None or primary.solution.type is T.EMPTY:
        return None
    rewrite = _log_rewrite_card(node, variables[0])
    if rewrite is not None:
        rewrite.header = "rewrite_in_expo"
    return [primary, rewrite] if rewrite is not None else [primary]


def _unwrap(node: CoreNode) -> CoreNode:
    """Убрать скобки/унарный плюс, оставив формулу."""
    while node.type in (T.BRACKET, T.POSITIVE) and len(node.children) == 1:
        node = node.children[0]
    return node


def _base_node(value: sympy.Expr) -> CoreNode:
    """Основание степени как узел: дробь — в скобках (``(2/3)^x``)."""
    node = from_sympy(value)
    if node.type in (T.FRACTION, T.NEGATIVE):
        return CoreNode.node(T.BRACKET, node)
    return node


def _log_node(value_node: CoreNode, base: sympy.Expr) -> CoreNode:
    """``log_b v`` как узел (``ln``/``lg``/``log``)."""
    if base == sympy.E:
        return CoreNode.node(T.LN, value_node)
    if base == 10:
        return CoreNode.node(T.LOG10, value_node)
    return CoreNode.node(T.LOG, value_node, _base_node(base))


def _variable_powers(expr: sympy.Expr, symbol: sympy.Symbol) -> list[tuple[sympy.Expr, sympy.Expr]]:
    """Пары ``(основание, показатель)`` степеней, где показатель зависит от неизвестного."""
    found: list[tuple[sympy.Expr, sympy.Expr]] = []
    for power in expr.atoms(sympy.Pow):
        base, exponent = power.base, power.exp
        if exponent.has(symbol) and not base.has(symbol):
            found.append((base, exponent))
    for function in expr.atoms(sympy.exp):
        if function.args[0].has(symbol):
            found.append((sympy.E, function.args[0]))
    unique: list[tuple[sympy.Expr, sympy.Expr]] = []
    for item in found:
        if item not in unique:
            unique.append(item)
    return unique


def _base_candidates(values: list[sympy.Expr]) -> set[sympy.Expr]:
    """Кандидаты в общее основание: сами числа и их простые делители."""
    candidates: set[sympy.Expr] = set()
    for value in values:
        if not (value.is_Rational and value > 0):
            continue
        candidates.add(value)
        candidates.add(1 / value)
        for part in (int(value.p), int(value.q)):
            for prime in sympy.factorint(part):
                candidates.add(sympy.Integer(prime))
                candidates.add(sympy.Rational(1, prime))
    return candidates


def _log_ratio(value: sympy.Expr, base: sympy.Expr) -> Fraction | None:
    """Рациональный показатель ``m`` с ``value == base^m`` или ``None``."""
    if value == base:
        return Fraction(1)
    if value == 1:
        return Fraction(0)
    try:
        ratio = sympy.log(value, base)
    except (TypeError, ValueError, NotImplementedError):
        return None
    if ratio.is_Rational:
        return Fraction(int(ratio.p), int(ratio.q))
    return None


def _common_base(bases: list[sympy.Expr]) -> tuple[sympy.Expr, list[Fraction]] | None:
    """Общее основание ``B`` и показатели ``m_i`` (``b_i = B^m_i``) или ``None``."""
    best: tuple[tuple[int, float], sympy.Expr, list[Fraction]] | None = None
    for base in _base_candidates(bases):
        if base == 1 or base <= 0:
            continue
        ratios: list[Fraction] = []
        for item in bases:
            ratio = _log_ratio(item, base)
            if ratio is None:
                ratios = []
                break
            ratios.append(ratio)
        if not ratios:
            continue
        score = (0 if (base.is_Integer and base > 1) else 1, float(sympy.N(base)))
        if best is None or score < best[0]:
            best = (score, base, ratios)
    if best is None:
        return None
    return best[1], best[2]


def _power_coefficients(
    expr: sympy.Expr, powers: list[tuple[sympy.Expr, sympy.Expr]]
) -> tuple[sympy.Poly, list[sympy.Expr]]:
    """Коэффициенты при степенях: подставить каждую степень мнимой переменной."""
    dummies = [sympy.Dummy(f"u{index}") for index in range(len(powers))]
    substituted = expr
    for (base, exponent), dummy in zip(powers, dummies, strict=True):
        substituted = substituted.xreplace({base**exponent: dummy})
    return sympy.Poly(sympy.expand(substituted), *dummies), dummies


def _find_power_node(side: CoreNode, base: sympy.Expr, exponent: sympy.Expr) -> CoreNode | None:
    """Узел степени ``base^exponent`` внутри стороны уравнения."""
    for part in side.walk():
        if part.type is T.POWER and len(part.children) == 2:
            try:
                part_base = to_sympy(part.children[0])
                part_exp = to_sympy(_unwrap(part.children[1]))
            except SolveError:
                continue
            if part_base == base and part_exp == exponent:
                return part
    return None


def _exp_append(equation: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """Решить вспомогательное уравнение обычными строками и вернуть ответ."""
    try:
        methods = methods_for(equation, [var])
    except SolveError:
        methods = None
    if methods:
        ctx.result.extend(methods[0])
        return methods[0].solution
    scratch = SolveResult()
    try:
        answer = solve_equation(equation, SolveContext(result=scratch, variables=[var]))
    except SolveError:
        return None
    ctx.result.extend(scratch)
    return answer


def _exp_scaled_exponent(exponent_node: CoreNode, factor: Fraction) -> CoreNode:
    """Показатель ``m·e``: единица не пишется, минус единица даёт ``-e``."""
    if factor == 1:
        return exponent_node
    if factor == -1:
        return CoreNode.node(T.NEGATIVE, exponent_node)
    return from_sympy(
        sympy.Rational(factor.numerator, factor.denominator) * to_sympy(exponent_node)
    )


def _exp_single(
    node: CoreNode,
    var: str,
    base: sympy.Expr,
    exponent: sympy.Expr,
    ctx: SolveContext,
) -> CoreNode | None:
    """``b^f = V``: общее основание и приравнивание показателей или взятие логарифма."""
    symbol = sympy.Symbol(var)
    try:
        expr = to_sympy(node.children[0]) - to_sympy(node.children[1])
    except SolveError:
        return None
    dummy = sympy.Dummy("u")
    substituted = sympy.expand(expr.xreplace({base**exponent: dummy}))
    if substituted.has(symbol):
        return None
    try:
        poly = sympy.Poly(substituted, dummy)
    except sympy.PolynomialError:
        return None
    coefficient = poly.coeff_monomial(dummy)
    constant = poly.coeff_monomial(1)
    if coefficient == 0:
        return None
    value = sympy.simplify(-constant / coefficient)
    if value.is_positive is not True:
        return None
    side = 0 if to_sympy(node.children[0]).has(symbol) else 1
    power_node = _find_power_node(node.children[side], base, exponent)
    exponent_node = (
        _unwrap(power_node.children[1]) if power_node is not None else from_sympy(exponent)
    )
    if base == sympy.E:
        equation = CoreNode.node(T.EQUALS, exponent_node, _log_node(from_sympy(value), sympy.E))
        ctx.result.add_group("trans_msg", Step(node, equation, "log_take_natural"))
        return _exp_append(equation, var, ctx)
    common = _common_base([base, value])
    if common is None:
        power = CoreNode.node(T.POWER, _base_node(base), exponent_node)
        logged = _log_node(power, base)
        value_log = _log_node(from_sympy(value), base)
        first = CoreNode.node(T.EQUALS, logged, value_log)
        equation = CoreNode.node(T.EQUALS, exponent_node, value_log)
        ctx.result.add_group("simplify_eq", Step(node, first, "log_take_both_side"))
        ctx.result.add_group("simplify", Step(first, equation, "using_sim", [_log_of_power_law()]))
        return _exp_append(equation, var, ctx)
    canonical, ratios = common
    m, k = ratios[0], ratios[1]
    canonical_node = _base_node(canonical)
    scaled = _exp_scaled_exponent(exponent_node, m)
    steps: list[Step] = []
    current = node
    if m != 1:
        new_power = CoreNode.node(T.POWER, canonical_node, scaled)
        rewritten = (
            CoreNode.node(T.EQUALS, new_power, node.children[1])
            if side == 0
            else CoreNode.node(T.EQUALS, node.children[0], new_power)
        )
        key = "write_as_exp" if (base.is_Rational and base.q != 1) else "pow_to_same_base"
        steps.append(Step(current, rewritten, key, [canonical_node]))
        current = rewritten
    value_power = CoreNode.node(T.POWER, canonical_node, from_sympy(k))
    same_base = (
        CoreNode.node(T.EQUALS, current.children[0], value_power)
        if side == 0
        else CoreNode.node(T.EQUALS, value_power, current.children[1])
    )
    steps.append(Step(current, same_base, "pow_to_same_base", [canonical_node]))
    ctx.result.add_group("write_as_exp_short", *steps)
    equalised = CoreNode.node(T.EQUALS, scaled, from_sympy(k))
    ctx.result.add_group(
        "pow_equalize_exponents", Step(same_base, equalised, "exp_eq_exp_equalise")
    )
    return _exp_append(equalised, var, ctx)


def _exp_equal_exponents(
    node: CoreNode,
    var: str,
    powers: list[tuple[sympy.Expr, sympy.Expr]],
    ctx: SolveContext,
) -> CoreNode | None:
    """``a^f = b^f``: разделить обе части на ``b^f`` и приравнять показатели к нулю."""
    left_power = right_power = None
    for base, exponent in powers:
        if _find_power_node(node.children[0], base, exponent) is not None:
            left_power = (base, exponent)
        if _find_power_node(node.children[1], base, exponent) is not None:
            right_power = (base, exponent)
    if left_power is None or right_power is None:
        return None
    base0, exponent0 = left_power
    base1 = right_power[0]
    if base0 == base1:
        return None
    ratio = sympy.simplify(base0 / base1)
    left_node = CoreNode.node(T.POWER, _base_node(ratio), _exponent_node(node, base0, exponent0))
    divided = CoreNode.node(T.EQUALS, left_node, _const(Fraction(1)))
    divisor = CoreNode.node(T.POWER, _base_node(base1), _exponent_node(node, base1, right_power[1]))
    ctx.result.add_group("divide_both_sides", Step(node, divided, "eq_linear_div", [divisor]))
    return _exp_single(divided, var, ratio, exponent0, ctx)


def _exponent_node(node: CoreNode, base: sympy.Expr, exponent: sympy.Expr) -> CoreNode:
    """Узел показателя степени ``base^exponent`` внутри уравнения."""
    for side in node.children:
        found = _find_power_node(side, base, exponent)
        if found is not None:
            return _unwrap(found.children[1])
    return from_sympy(exponent)


def _replace_node(root: CoreNode, target: CoreNode, replacement: CoreNode) -> CoreNode:
    """Заменить поддерево, равное ``target`` структурно."""
    if root.structural_eq(target):
        return replacement
    if not root.children:
        return root
    return CoreNode(
        type=root.type,
        children=[_replace_node(child, target, replacement) for child in root.children],
        value=root.value,
    )


def _exp_multi(
    node: CoreNode,
    var: str,
    expr: sympy.Expr,
    powers: list[tuple[sympy.Expr, sympy.Expr]],
    ctx: SolveContext,
) -> CoreNode | None:
    """Две и более степеней: вынесение множителя или замена ``t = a^x``."""
    symbol = sympy.Symbol(var)
    bases = [base for base, _ in powers]
    common = _common_base(bases)
    if common is not None:
        canonical, ratios = common
        exponents = [ratio * exponent for ratio, (_, exponent) in zip(ratios, powers, strict=True)]
        try:
            poly, dummies = _power_coefficients(expr, powers)
        except sympy.PolynomialError:
            return None
        coefficients = [poly.coeff_monomial(dummy) for dummy in dummies]
        constant = poly.coeff_monomial(1)
        if len(powers) == 2:
            difference = sympy.simplify(exponents[0] - exponents[1])
            if not difference.has(symbol) and difference.is_Rational and difference != 0:
                return _exp_factor(
                    node,
                    var,
                    canonical,
                    exponents,
                    coefficients,
                    constant,
                    difference,
                    powers,
                    ctx,
                )
            unit = _common_exponent(exponents, symbol)
            if unit is not None:
                return _exp_substitute(
                    node, var, canonical, unit, exponents, coefficients, constant, powers, ctx
                )
        return None
    if len(powers) == 2 and sympy.simplify(powers[0][1] - powers[1][1]) == 0:
        return _exp_equal_exponents(node, var, powers, ctx)
    return None


def _common_exponent(exponents: list[sympy.Expr], symbol: sympy.Symbol) -> sympy.Expr:
    """Общий показатель ``u``, кратный каждому (``2x, x`` -> ``x``) или ``None``."""
    for candidate in exponents:
        if not candidate.has(symbol):
            continue
        ratios = [sympy.simplify(item / candidate) for item in exponents]
        if all(ratio.is_Integer for ratio in ratios) and any(ratio != 1 for ratio in ratios):
            return candidate
    return None


def _exp_factor(
    node: CoreNode,
    var: str,
    canonical: sympy.Expr,
    exponents: list[sympy.Expr],
    coefficients: list[sympy.Expr],
    constant: sympy.Expr,
    difference: sympy.Expr,
    powers: list[tuple[sympy.Expr, sympy.Expr]],
    ctx: SolveContext,
) -> CoreNode | None:
    """``c1 a^(f+k) + c2 a^f = d``: вынести ``a^f`` и решить ``a^f = V``."""
    low, high = 0, 1
    if difference.is_positive:
        low, high = 1, 0
    shift = sympy.simplify(exponents[high] - exponents[low])
    c_high, c_low = coefficients[high], coefficients[low]
    if not c_low.is_number or c_low == 0:
        return None
    base_node = _base_node(canonical)
    shift_node = base_node if shift == 1 else CoreNode.node(T.POWER, base_node, from_sympy(shift))
    inner = (
        CoreNode.node(T.ADD, shift_node, _const(Fraction(c_low)))
        if c_high == 1
        else CoreNode.node(
            T.ADD,
            CoreNode.node(T.MULTIPLY, from_sympy(c_high), shift_node),
            _const(Fraction(c_low)),
        )
    )
    power_node = _find_power_node(node.children[0], powers[low][0], powers[low][1])
    if power_node is None:
        power_node = _find_power_node(node.children[1], powers[low][0], powers[low][1])
    if power_node is None:
        return None
    factored_left = CoreNode.node(T.MULTIPLY, CoreNode.node(T.BRACKET, inner), power_node)
    other = node.children[1] if _has_unknown(node.children[0], var) else node.children[0]
    factored = CoreNode.node(T.EQUALS, factored_left, other)
    ctx.result.add_group("factorise_call", Step(node, factored, "factorise_call"))
    total = sympy.simplify(c_high * canonical**shift + c_low)
    value = sympy.simplify(-constant / total)
    summed = CoreNode.node(
        T.EQUALS, CoreNode.node(T.MULTIPLY, from_sympy(total), power_node), other
    )
    ctx.result.add_group("add", Step(factored, summed, "add"))
    if not value.is_positive:
        return None
    divided = CoreNode.node(T.EQUALS, power_node, from_sympy(value))
    ctx.result.add_group(
        "divide_both_sides", Step(summed, divided, "eq_linear_div", [from_sympy(total)])
    )
    return _exp_single(divided, var, canonical, exponents[low], ctx)


def _exp_substitute(
    node: CoreNode,
    var: str,
    canonical: sympy.Expr,
    unit: sympy.Expr,
    exponents: list[sympy.Expr],
    coefficients: list[sympy.Expr],
    constant: sympy.Expr,
    powers: list[tuple[sympy.Expr, sympy.Expr]],
    ctx: SolveContext,
) -> CoreNode | None:
    """``c1 a^(k f) + c2 a^f = d``: замена ``t = a^f``, квадратное, обратная замена."""
    base_node = _base_node(canonical)
    multipliers = [sympy.simplify(item / unit) for item in exponents]
    if any(not item.is_Integer or item <= 0 for item in multipliers):
        return None
    steps: list[Step] = []
    current = node
    for index, (base, exponent) in enumerate(powers):
        multiplier = multipliers[index]
        if base == canonical:
            continue
        power_node = _find_power_node(node.children[0], base, exponent)
        if power_node is None:
            power_node = _find_power_node(node.children[1], base, exponent)
        if power_node is None:
            return None
        exponent_node = _unwrap(power_node.children[1])
        same = CoreNode.node(
            T.POWER,
            CoreNode.node(T.BRACKET, CoreNode.node(T.POWER, base_node, from_sympy(multiplier))),
            exponent_node,
        )
        rewritten = _replace_node(current, power_node, same)
        steps.append(Step(current, rewritten, "pow_to_same_base", [base_node]))
        current = rewritten
        combined = CoreNode.node(
            T.POWER,
            CoreNode.node(T.BRACKET, CoreNode.node(T.POWER, base_node, exponent_node)),
            from_sympy(multiplier),
        )
        raised = _replace_node(current, same, combined)
        steps.append(Step(current, raised, "using_trans", [_power_of_power_law()]))
        current = raised
    ctx.result.add_group("write_as_exp_short", *steps)
    unit_node = _find_power_node(current, canonical, unit)
    if unit_node is None:
        return None
    unit_exponent = _unwrap(unit_node.children[1])
    t = CoreNode.variable("t")
    ordered = sorted(zip(multipliers, coefficients, strict=True), key=lambda item: -item[0])
    t_terms: list[tuple[sympy.Expr, CoreNode]] = []
    for multiplier, coefficient in ordered:
        term = t if multiplier == 1 else CoreNode.node(T.POWER, t, from_sympy(multiplier))
        t_terms.append((coefficient, term))
    polynomial = _sum_terms(t_terms, constant)
    substituted = CoreNode.node(T.EQUALS, polynomial, _const(Fraction(0)))
    substitution = CoreNode.node(T.EQUALS, t, unit_node)
    ctx.result.add_group("eq_solve_sub", Step(current, substituted, "eq_solve_sub", [substitution]))
    solved = _exp_append(substituted, "t", ctx)
    if solved is None:
        return None
    values = sympy.solve(
        sympy.Eq(sympy.expand(_poly_from_terms(t_terms, constant)), 0), sympy.Symbol("t")
    )
    values = [item for item in values if item.is_real]
    if not values:
        return None
    back = CoreNode.node(
        T.LIST,
        *[
            CoreNode.node(
                T.EQUALS, CoreNode.node(T.POWER, base_node, unit_exponent), from_sympy(item)
            )
            for item in values
        ],
    )
    ctx.result.add_group("sub_msg_ret", Step(solved, back, "sub_msg_ret", [substitution]))
    roots: list[CoreNode] = []
    for item in values:
        branch = CoreNode.node(
            T.EQUALS, CoreNode.node(T.POWER, base_node, unit_exponent), from_sympy(item)
        )
        answer = _exp_single(branch, var, canonical, unit, ctx)
        if answer is None:
            return None
        roots.append(answer)
    ordered_roots = sorted(roots, key=lambda part: _sort_key(to_sympy(part.children[1])))
    final = ordered_roots[0] if len(ordered_roots) == 1 else CoreNode.node(T.LIST, *ordered_roots)
    ctx.result.add_group(
        CoreRichText(type="solution_eq_num", args=[_const(Fraction(len(ordered)))]),
        Step(back, final, "solution_eq_num", [_const(Fraction(len(ordered)))]),
    )
    return final


def _sum_terms(terms: list[tuple[sympy.Expr, CoreNode]], constant: sympy.Expr) -> CoreNode:
    """Собрать многочлен в убывающем порядке степеней: ``t^2 - 3t + 2``."""
    pieces: list[tuple[int, CoreNode]] = []
    for coefficient, term in terms:
        if coefficient == 0:
            continue
        magnitude = abs(coefficient)
        node = (
            term
            if magnitude == 1
            else CoreNode.node(T.MULTIPLY_IMPLICIT, from_sympy(magnitude), term)
        )
        pieces.append((1 if coefficient > 0 else -1, node))
    if constant != 0:
        pieces.append((1 if constant > 0 else -1, from_sympy(abs(constant))))
    result: CoreNode | None = None
    for sign, node in pieces:
        if result is None:
            result = node if sign > 0 else CoreNode.node(T.NEGATIVE, node)
        else:
            result = CoreNode.node(T.ADD if sign > 0 else T.SUBTRACT, result, node)
    return result if result is not None else _const(Fraction(0))


def _poly_from_terms(terms: list[tuple[sympy.Expr, CoreNode]], constant: sympy.Expr) -> sympy.Expr:
    """Многочлен sympy из списка слагаемых ``t``."""
    expression: sympy.Expr = sympy.Integer(0)
    for coefficient, term in terms:
        expression += coefficient * to_sympy(term)
    return expression + constant


def _exp_equation_rows(node: CoreNode, variables: list[str], ctx: SolveContext) -> CoreNode | None:
    """Показательное уравнение: строки карточек вместо графика и приближения.

    Одно основание: ``pow_to_same_base``, ``exp_eq_exp_equalise`` и обычные строки;
    если точной степени нет — логарифмирование. Две степени: вынесение множителя
    (``factorise_call``) или замена ``t = a^x`` (``eq_solve_sub``).
    """
    if len(variables) != 1 or node.type is not T.EQUALS or len(node.children) != 2:
        return None
    var = variables[0]
    try:
        expr = to_sympy(node.children[0]) - to_sympy(node.children[1])
    except SolveError:
        return None
    symbol = sympy.Symbol(var)
    if not expr.has(symbol):
        return None
    powers = _variable_powers(expr, symbol)
    if not powers:
        return None
    if len(powers) == 1:
        return _exp_single(node, var, powers[0][0], powers[0][1], ctx)
    return _exp_multi(node, var, expr, powers, ctx)


def _exponential_methods(node: CoreNode, variables: list[str]) -> list[SolveResult] | None:
    """Способ для показательного уравнения или ``None``, если случай не наш."""
    result = SolveResult()
    ctx = SolveContext(result=result, variables=list(variables))
    answer = _exp_equation_rows(node, variables, ctx)
    if answer is None:
        return None
    result.set_solution(answer)
    return [result]


def _log_exp_transform(left: sympy.Expr, right: sympy.Expr) -> tuple[str, sympy.Eq] | None:
    """Преобразовать логарифмическое/показательное уравнение или ``None``."""
    left_log, right_log = _single_log(left), _single_log(right)
    if left_log is not None and right_log is not None and left_log[1] == right_log[1]:
        return "eq_log_equalise", sympy.Eq(left_log[0], right_log[0])
    if left_log is not None and right.is_number:
        return "log_def_solve", sympy.Eq(left_log[0], left_log[1] ** right)
    if right_log is not None and left.is_number:
        return "log_def_solve", sympy.Eq(right_log[0], right_log[1] ** left)

    # e^f is sympy.exp (not Pow), so the number e needs its own cases
    left_exp, right_exp = isinstance(left, sympy.exp), isinstance(right, sympy.exp)
    if left_exp and right_exp:
        return "eq_pow_eq", sympy.Eq(left.args[0], right.args[0])
    if left_exp and right.is_number and right.is_positive:
        return "eq_trans", sympy.Eq(left.args[0], sympy.log(right))
    if right_exp and left.is_number and left.is_positive:
        return "eq_trans", sympy.Eq(right.args[0], sympy.log(left))
    atoms = {a for a in (*left.atoms(sympy.exp), *right.atoms(sympy.exp)) if a.free_symbols}
    if len(atoms) == 1 and not (left_exp or right_exp):
        # a e^f + b = c: solve for e^f, then take the logarithm
        atom = next(iter(atoms))
        unknown = sympy.Dummy("u")
        values = sympy.solve(left.subs(atom, unknown) - right.subs(atom, unknown), unknown)
        if len(values) == 1 and values[0].is_number and values[0].is_positive:
            return "eq_trans", sympy.Eq(atom.args[0], sympy.log(values[0]))
    left_pow, right_pow = isinstance(left, sympy.Pow), isinstance(right, sympy.Pow)
    if left_pow and right_pow and left.base == right.base and left.base.is_number:
        return "eq_pow_eq", sympy.Eq(left.exp, right.exp)
    if left_pow and left.base.is_number and right.is_number and right.is_positive:
        return "eq_trans", sympy.Eq(left.exp, sympy.log(right, left.base))
    if right_pow and right.base.is_number and left.is_number and left.is_positive:
        return "eq_trans", sympy.Eq(right.exp, sympy.log(left, right.base))
    return None


def _single_log(expression: sympy.Expr) -> tuple[sympy.Expr, sympy.Expr] | None:
    """``(аргумент, основание)``, если выражение — один логарифм.

    Логарифм с явным основанием sympy хранит как ``log(f)/log(b)``; этот и
    простой ``log(f)`` (основание ``e``) распознаются как один логарифм.
    """
    if isinstance(expression, sympy.log):
        return expression.args[0], _log_base(expression)
    numerator, denominator = sympy.fraction(expression)
    if isinstance(numerator, sympy.log) and isinstance(denominator, sympy.log):
        return numerator.args[0], denominator.args[0]
    return None


def _impossible_exponential(power: sympy.Expr, other: sympy.Expr) -> bool:
    """Верно ли, что ``a^f = other`` невозможно (неположительная правая часть)."""
    positive_power = isinstance(power, sympy.exp) or (
        isinstance(power, sympy.Pow) and power.base.is_number and power.base.is_positive is True
    )
    return positive_power and other.is_number is True and other.is_positive is False


def _log_base(logarithm: sympy.Expr) -> sympy.Expr:
    """Основание логарифма; для ``ln`` — число ``e``."""
    return logarithm.args[1] if len(logarithm.args) > 1 else sympy.E


def _poly_expr(poly: Poly, var: str) -> sympy.Expr:
    """Многочлен из словаря коэффициентов в выражение sympy."""
    symbol = sympy.Symbol(var)
    terms = [
        sympy.Rational(coeff.numerator, coeff.denominator) * symbol**degree
        for degree, coeff in poly.items()
    ]
    return sympy.Add(*terms)


def _cubic_rows(node: CoreNode, var: str, poly: Poly, ctx: SolveContext) -> CoreNode | None:
    """Cubic with three integer roots: split the middle terms, factor by grouping, solve.

    The card the card shows (worked out for ``x^3 - 6x^2 + 11x - 6 = 0``).
    """
    if _degree(poly) != 3 or _coeff(poly, 3) != 1:
        return None
    b, c, d = _coeff(poly, 2), _coeff(poly, 1), _coeff(poly, 0)
    if any(value.denominator != 1 for value in (b, c, d)):
        return None
    symbol = sympy.Symbol(var)
    try:
        found = sympy.solve(_poly_expr(poly, var), symbol)
    except (TypeError, ValueError, NotImplementedError):
        return None
    roots = sorted((root for root in found if _is_real_root(root)), key=_sort_key)
    if len(roots) != 3 or any(root.is_Integer is not True for root in roots):
        return None
    values = [int(root) for root in roots]
    if any(value <= 0 for value in values):
        return None
    first_root, second_root, third_root = values
    bi, ci, di = int(b), int(c), int(d)
    quotient_b = bi + first_root
    quotient_c = ci + quotient_b * first_root
    split_c = ci - quotient_c
    if quotient_b != -(second_root + third_root) or quotient_c != second_root * third_root:
        return None
    if first_root * quotient_c != -di:
        return None
    eq, chain = CoreNode.node, quadratic_cards._chain
    x = CoreNode.variable(var)
    zero = _const(Fraction(0))
    square = eq(T.POWER, x, _const(Fraction(2)))
    cube = eq(T.POWER, x, _const(Fraction(3)))
    bracket = eq(T.BRACKET, eq(T.SUBTRACT, x, _const(Fraction(first_root))))
    quadratic = chain(
        [
            (1, square),
            (1 if quotient_b > 0 else -1, _mono_node(abs(quotient_b), 1, var)),
            (1 if quotient_c > 0 else -1, _const(abs(quotient_c))),
        ]
    )

    def chain_of(terms: list[tuple[int, CoreNode]]) -> CoreNode:
        return eq(T.EQUALS, chain(terms), zero)

    def sign_of(value: int) -> int:
        return 1 if value > 0 else -1

    written_first = chain_of(
        [
            (1, cube),
            (sign_of(-first_root), _mono_node(abs(first_root), 2, var)),
            (sign_of(quotient_b), _mono_node(abs(quotient_b), 2, var)),
            (sign_of(ci), _mono_node(abs(ci), 1, var)),
            (sign_of(di), _const(abs(di))),
        ]
    )
    written_second = chain_of(
        [
            (1, cube),
            (sign_of(-first_root), _mono_node(abs(first_root), 2, var)),
            (sign_of(quotient_b), _mono_node(abs(quotient_b), 2, var)),
            (sign_of(split_c), _mono_node(abs(split_c), 1, var)),
            (sign_of(quotient_c), _mono_node(abs(quotient_c), 1, var)),
            (sign_of(di), _const(abs(di))),
        ]
    )
    grouped_square = eq(T.MULTIPLY, square, bracket)
    grouped_linear = eq(T.MULTIPLY, _mono_node(abs(quotient_b), 1, var), bracket)
    grouped_const = eq(T.MULTIPLY, _const(abs(quotient_c)), bracket)
    after_square = chain_of(
        [
            (1, grouped_square),
            (sign_of(quotient_b), _mono_node(abs(quotient_b), 2, var)),
            (sign_of(split_c), _mono_node(abs(split_c), 1, var)),
            (sign_of(quotient_c), _mono_node(abs(quotient_c), 1, var)),
            (sign_of(di), _const(abs(di))),
        ]
    )
    after_linear = chain_of(
        [
            (1, grouped_square),
            (-sign_of(quotient_b), grouped_linear),
            (sign_of(quotient_c), _mono_node(abs(quotient_c), 1, var)),
            (sign_of(di), _const(abs(di))),
        ]
    )
    after_const = chain_of(
        [
            (1, grouped_square),
            (-sign_of(quotient_b), grouped_linear),
            (sign_of(di), grouped_const),
        ]
    )
    factored = eq(T.EQUALS, eq(T.MULTIPLY, bracket, eq(T.BRACKET, quadratic)), zero)
    ctx.result.add_group(
        "rewrite_expression",
        Step(node, written_first, "write_as_diff_fact", [_mono_node(abs(bi), 2, var)]),
        Step(written_first, written_second, "write_as_sum_fact", [_mono_node(abs(ci), 1, var)]),
    )
    ctx.result.add_group(
        "factorise_call_plural",
        Step(written_second, after_square, "extract_arg", [square]),
        Step(after_square, after_linear, "extract_arg", [_mono_node(abs(quotient_b), 1, var)]),
        Step(after_linear, after_const, "extract_arg", [_const(abs(quotient_c))]),
    )
    ctx.result.add_group("factorise_call", Step(after_const, factored, "extract_arg", [bracket]))
    # the quadratic factor: split the middle term by the other two roots
    quadratic_split = chain(
        [
            (1, square),
            (sign_of(-second_root), _mono_node(abs(second_root), 1, var)),
            (sign_of(-third_root), _mono_node(abs(third_root), 1, var)),
            (sign_of(quotient_c), _const(abs(quotient_c))),
        ]
    )
    quadratic_product = eq(T.MULTIPLY, bracket, eq(T.BRACKET, quadratic))
    split_product = eq(T.EQUALS, eq(T.MULTIPLY, bracket, eq(T.BRACKET, quadratic_split)), zero)
    first_factor = eq(
        T.MULTIPLY,
        x,
        eq(T.BRACKET, eq(T.SUBTRACT, x, _const(Fraction(second_root)))),
    )
    quadratic_after_x = chain(
        [
            (1, first_factor),
            (sign_of(-third_root), _mono_node(abs(third_root), 1, var)),
            (sign_of(quotient_c), _const(abs(quotient_c))),
        ]
    )
    second_factor = eq(
        T.MULTIPLY,
        _const(abs(third_root)),
        eq(T.BRACKET, eq(T.SUBTRACT, x, _const(Fraction(second_root)))),
    )
    quadratic_done = chain([(1, first_factor), (-sign_of(-third_root), second_factor)])
    done_product = eq(
        T.MULTIPLY,
        eq(
            T.MULTIPLY,
            bracket,
            eq(T.BRACKET, eq(T.SUBTRACT, x, _const(Fraction(second_root)))),
        ),
        eq(T.BRACKET, eq(T.SUBTRACT, x, _const(Fraction(third_root)))),
    )
    ctx.result.add_group(
        "factorise_call_plural",
        Step(
            eq(T.EQUALS, quadratic_product, zero),
            split_product,
            "write_as_diff_fact",
            [_mono_node(abs(quotient_b), 1, var)],
        ),
    )
    ctx.result.add_group(
        "factorise_call_plural",
        Step(split_product, eq(T.EQUALS, quadratic_after_x, zero), "extract_arg", [x]),
        Step(
            eq(T.EQUALS, quadratic_after_x, zero),
            eq(T.EQUALS, quadratic_done, zero),
            "extract_arg",
            [_const(abs(third_root))],
        ),
    )
    ctx.result.add_group(
        "factorise_call",
        Step(
            eq(T.EQUALS, quadratic_done, zero),
            eq(T.EQUALS, done_product, zero),
            "extract_arg",
            [eq(T.BRACKET, eq(T.SUBTRACT, x, _const(Fraction(second_root))))],
        ),
    )
    cases = eq(
        T.LIST,
        *[eq(T.EQUALS, eq(T.SUBTRACT, x, _const(Fraction(value))), zero) for value in values],
    )
    ctx.result.add_group(
        "eq_separate_short",
        Step(eq(T.EQUALS, done_product, zero), cases, "quad_separate_zero_product", [zero]),
    )
    pages = []
    for value in values:
        case = eq(T.EQUALS, eq(T.SUBTRACT, x, _const(Fraction(value))), zero)
        page = _flat_page(solve_methods(case, [var])[0])
        pages.append(
            Step(
                cases,
                eq(T.EQUALS, x, _const(Fraction(value))),
                "eq_linear",
                [x],
                subresult=page,
            )
        )
    ctx.result.add_group("eq_solve_short_plural", *pages)
    answer = eq(T.LIST, *[eq(T.EQUALS, x, _const(Fraction(value))) for value in values])
    count = _const(Fraction(len(values)))
    ctx.result.add_group(
        CoreRichText(type="solution_eq_num", args=[count]),
        Step(cases, answer, "solution_eq_num", [count]),
    )
    return answer


def _flat_page(page: SolveResult) -> SolveResult:
    """The same rows without their detail screens (verified pages are flat)."""
    for step in page:
        step.subresult = None
    return page


def _biquadratic_rows(node: CoreNode, var: str, poly: Poly, ctx: SolveContext) -> CoreNode | None:
    """``x^4 + b x^2 + c = 0``: substitute ``t = x^2``, solve in ``t``, substitute back.

    The card the card shows (worked out for ``x^4 - 5x^2 + 4 = 0``).
    """
    if _degree(poly) != 4 or _coeff(poly, 3) != 0 or _coeff(poly, 1) != 0:
        return None
    a, b, c = _coeff(poly, 4), _coeff(poly, 2), _coeff(poly, 0)
    if a != 1 or b == 0 or c <= 0:
        return None
    discriminant = b * b - 4 * c
    if discriminant < 0 or discriminant.denominator != 1:
        return None
    root = isqrt(int(discriminant))
    if root * root != discriminant:
        return None
    values = sorted({Fraction(-b - root, 2), Fraction(-b + root, 2)})
    if len(values) != 2 or any(value.denominator != 1 or value < 0 for value in values):
        return None
    family = quadratic_cards._Family("t", 1, int(b), int(c))
    scratch = SolveResult()
    rows = quadratic_cards._factor_rows(family, scratch, None)
    if rows is None:
        return None
    product, bracket, other = rows
    eq = CoreNode.node
    t, x = CoreNode.variable("t"), CoreNode.variable(var)
    sub = eq(T.EQUALS, t, eq(T.POWER, x, _const(Fraction(2))))
    two = _const(Fraction(2))
    squared = eq(T.POWER, eq(T.BRACKET, eq(T.POWER, x, two)), two)
    chain = quadratic_cards._chain
    written = eq(
        T.EQUALS,
        chain(
            [
                (1, eq(T.POWER, x, eq(T.MULTIPLY, two, two))),
                (1 if b > 0 else -1, _mono_node(abs(b), 2, var)),
                (1 if c > 0 else -1, _const(abs(c))),
            ]
        ),
        _const(Fraction(0)),
    )
    substituted = eq(
        T.EQUALS,
        chain(
            [
                (1, eq(T.POWER, t, two)),
                (1 if b > 0 else -1, _mono_node(abs(b), 1, "t")),
                (1 if c > 0 else -1, _const(abs(c))),
            ]
        ),
        _const(Fraction(0)),
    )
    rule = eq(
        T.EQUALS,
        eq(
            T.POWER,
            CoreNode.variable("a"),
            eq(T.MULTIPLY, CoreNode.variable("m"), CoreNode.variable("n")),
        ),
        eq(
            T.POWER,
            eq(T.BRACKET, eq(T.POWER, CoreNode.variable("a"), CoreNode.variable("m"))),
            CoreNode.variable("n"),
        ),
    )
    detail = SolveResult()
    detail.add_group("factor_number", Step(node, written, "factor_number", [_const(c)]))
    detail.add_group("using_trans", Step(written, squared, "using_trans", [rule]))
    detail.add_group("eq_solve_sub", Step(squared, substituted, "eq_solve_sub", [sub]))
    detail.set_solution(substituted)
    ctx.result.add_group(
        "eq_quad_substitute", Step(node, substituted, "eq_quad_substitute", [sub], subresult=detail)
    )

    factor_detail = SolveResult()
    for step in scratch:
        factor_detail.add(step)
    cases = eq(T.LIST, eq(T.EQUALS, bracket, _const(0)), eq(T.EQUALS, other, _const(0)))
    factor_detail.add_group(
        "quad_separate", Step(product, cases, "quad_separate_zero_product", [_const(0)])
    )
    solved = eq(
        T.LIST,
        eq(T.EQUALS, t, _const(values[0])),
        eq(T.EQUALS, t, _const(values[1])),
    )
    pages = []
    for case, value in zip((bracket, other), values, strict=True):
        page = _flat_page(solve_methods(case, ["t"])[0])
        pages.append(Step(cases, eq(T.EQUALS, t, _const(value)), "eq_linear", [t], subresult=page))
    factor_detail.add_group("eq_solve_short_plural", *pages)
    factor_detail.set_solution(solved)
    ctx.result.add_group(
        "eq_solve_short", Step(substituted, solved, "eq_linear", [t], subresult=factor_detail)
    )

    squared_values = eq(
        T.LIST,
        eq(T.EQUALS, eq(T.POWER, x, two), _const(values[0])),
        eq(T.EQUALS, eq(T.POWER, x, two), _const(values[1])),
    )
    ctx.result.add_group("sub_msg_ret", Step(solved, squared_values, "sub_msg_ret", [sub]))

    roots: list[CoreNode] = []
    current = squared_values
    branch_steps: list[Step] = []
    for value in values:
        unit = Fraction(isqrt(int(value)))
        plus, minus = _const(unit), _const(-unit)
        rooted = eq(T.EQUALS, x, eq(T.ADD_SUBTRACT, plus))
        branches = eq(T.LIST, eq(T.EQUALS, x, minus), eq(T.EQUALS, x, plus))
        page = SolveResult()
        page.add_group(
            "quad_sqrt_sides",
            Step(eq(T.EQUALS, eq(T.POWER, x, two), _const(value)), rooted, "quad_sqrt_sides"),
        )
        page.add_group(
            "quad_separate",
            Step(rooted, branches, "quad_separate_signs", list(quadratic_cards._SIGNS)),
        )
        page.set_solution(branches)
        roots.extend(branches.children)
        current = eq(T.LIST, *roots)
        branch_steps.append(Step(squared_values, current, "eq_linear", [x], subresult=page))
    ctx.result.add_group("eq_solve_short_plural", *branch_steps)
    ordered = sorted(roots, key=lambda part: _sort_key(to_sympy(part.children[1])))
    answer = eq(T.LIST, *ordered)
    count = _const(Fraction(len(ordered)))
    ctx.result.add_group(
        CoreRichText(type="solution_eq_num", args=[count]),
        Step(current, answer, "solution_eq_num", [count]),
    )
    return answer


def _mono_node(coefficient: Fraction | int, degree: int, var: str) -> CoreNode:
    """``|c| x^degree`` with the coefficient written out (``5x^2``)."""
    base = (
        CoreNode.variable(var)
        if degree == 1
        else CoreNode.node(T.POWER, CoreNode.variable(var), _const(Fraction(degree)))
    )
    return CoreNode.node(T.MULTIPLY_IMPLICIT, _const(Fraction(coefficient)), base)


def _extract_root(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """``x^n = c``: The app takes the root of both sides instead of factoring."""
    if node.type is not T.EQUALS or len(node.children) != 2:
        return None
    for left, right in (node.children, tuple(reversed(node.children))):
        if not (
            left.type is T.POWER
            and len(left.children) == 2
            and left.children[0].type is T.VARIABLE
            and left.children[0].value == var
            and left.children[1].type is T.CONSTANT
            and right.type is T.CONSTANT
        ):
            continue
        try:
            degree = int(as_fraction(left.children[1]))
            value = as_fraction(right)
        except (ValueError, ZeroDivisionError):
            continue
        if degree < 2:
            continue
        try:
            found = sympy.solve(sympy.Eq(to_sympy(left), to_sympy(right)), sympy.Symbol(var))
        except (TypeError, ValueError, NotImplementedError):
            continue
        real = [root for root in found if _is_real_root(root)]
        if len(real) != 1:
            continue
        root = real[0]
        radical = CoreNode.node(T.ROOT, _const(Fraction(degree)), _const(value))
        rooted = _equation(var, from_sympy(root) if root != 1 else radical)
        ctx.result.add_group("eq_root", Step(left=node, right=rooted, key="eq_root"))
        if root == 1:
            answer = _equation(var, _const(Fraction(1)))
            ctx.result.add_group(
                "root_one",
                Step(left=rooted, right=answer, key="root_one", args=[_const(Fraction(1))]),
            )
            return answer
        return rooted
    return None


def _solve_high_degree(node: CoreNode, var: str, poly: Poly, ctx: SolveContext) -> CoreNode:
    """Решить уравнение степени выше второй.

    Показывается разложение многочлена на множители (``solve_by_factoring``),
    корни берёт sympy (действительные, по возрастанию). Алгебраические корни
    (``∛``, ``√``) остаются точными узлами.
    """
    expression = _poly_expr(poly, var)
    symbol = sympy.Symbol(var)
    if (cubic := _cubic_rows(node, var, poly, ctx)) is not None:
        return cubic
    if (biquadratic := _biquadratic_rows(node, var, poly, ctx)) is not None:
        return biquadratic
    if (pure := _extract_root(node, var, ctx)) is not None:
        return pure
    factored = sympy.factor(expression)
    factored_equation = CoreNode.node(T.EQUALS, from_sympy(factored), CoreNode.constant("0"))
    if not factored_equation.structural_eq(node):
        ctx.result.add(
            Step(left=node, right=factored_equation, key="solve_by_factoring"), [_HEADER]
        )

    try:
        found = sympy.solve(sympy.Eq(expression, 0), symbol)
    except (TypeError, ValueError, NotImplementedError) as error:
        raise SolveError("уравнение выше второй степени не решается") from error
    roots = [root for root in found if _is_real_root(root)]
    roots.sort(key=_sort_key)
    return _solutions_node(var, [from_sympy(root) for root in roots])


def _is_real_root(root: sympy.Expr) -> bool:
    """Действительный ли корень.

    ``is_real`` у алгебраических выражений может быть ``None``, поэтому
    сомнительные корни проверяются численно по мнимой части.
    """
    if root.is_real is True:
        return True
    if root.is_real is False:
        return False
    try:
        return abs(complex(sympy.N(root)).imag) < 1e-9
    except (TypeError, ValueError):
        return False


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
    if len(ctx.variables) > 1:
        # Больше одной буквы: решаем относительно основной, остальные -- параметры.
        return _solve_parametric(node, _pick_primary(ctx.variables), ctx)
    ctx.require(
        len(ctx.variables) == 1,
        "поддерживается одно неизвестное: системы и параметры идут следующими",
    )
    var = ctx.variables[0]
    lhs, rhs = node.children

    try:
        poly = _sub(poly_of(lhs, var), poly_of(rhs, var))
    except UndefinedError:
        raise
    except SolveError:
        exact_quadratic = _constant_quadratic(node, var, ctx)
        if exact_quadratic is not None:
            return exact_quadratic
        for solver in (
            _symbolic_linear_rows,
            _solve_rational,
            _solve_radical,
            _solve_transcendental,
        ):
            answer = solver(node, ctx.variables, ctx)
            if answer is not None:
                return answer
        raise
    degree = _degree(poly)

    if degree == 0:
        # Уравнение не зависит от неизвестного: либо тождество, либо противоречие.
        if _coeff(poly, 0) == 0:
            ctx.result.add(Step(left=node, right=None, key="solutions_inf_many"))
        else:
            _contradiction_rows(node, var, _coeff(poly, 0), ctx.result)
        return CoreNode.empty()
    if degree == 1:
        if (fraction_zero := _fraction_zero_rows(node, lhs, rhs, var, ctx)) is not None:
            return fraction_zero
        return _linear_solution(node, lhs, rhs, var, poly, ctx)
    if degree == 2:
        return _quadratic_solution(node, var, poly, ctx)
    return _solve_high_degree(node, var, poly, ctx)


def _complex_quadratic_method(
    var: str, a: Fraction, b: Fraction, c: Fraction
) -> SolveResult | None:
    """The complex roots as an alternative way, as the app keeps them.

    With a negative discriminant the top answer is ``x ∉ ℝ``; the complex roots
    still belong in the methods, labelled ``eq_quad_solve_complex``.
    """
    symbol = sympy.Symbol(var)
    expression = (
        sympy.Rational(a.numerator, a.denominator) * symbol**2
        + sympy.Rational(b.numerator, b.denominator) * symbol
        + sympy.Rational(c.numerator, c.denominator)
    )
    try:
        roots = [sympy.simplify(root) for root in sympy.solve(expression, symbol)]
    except (sympy.SympifyError, NotImplementedError, ValueError, TypeError):
        return None
    if not roots or not any(root.has(sympy.I) for root in roots):
        return None
    roots.sort(key=lambda value: (sympy.re(value), sympy.im(value)))
    equations = [_equation(var, from_sympy(root)) for root in roots]
    solution = equations[0] if len(equations) == 1 else CoreNode.node(T.LIST, *equations)
    result = SolveResult()
    result.header = "eq_quad_solve_complex"
    result.add_group(
        "solution_eq_num",
        Step(
            CoreNode.node(T.EQUALS, from_sympy(sympy.expand(expression)), CoreNode.constant("0")),
            solution,
            "solution_eq_num",
            [_const(len(equations))],
        ),
    )
    result.set_solution(solution)
    return result


def _run(
    node: CoreNode, variables: list[str], action: Callable[[CoreNode, SolveContext], CoreNode]
) -> SolveResult:
    """Выполнить стратегию в отдельном накопителе и вернуть готовый результат."""
    result = SolveResult()
    ctx = SolveContext(result=result, variables=list(variables))
    result.set_solution(action(node, ctx))
    return result


@method_provider(T.EQUALS)
def solve_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """Способы решения уравнения: первый — основной, дальше — альтернативы.

    Линейное уравнение решается переносом и делением, а если коэффициент при
    ``x`` не единица и есть свободный член — ещё и делением до переноса.
    Квадратное — формулой и, если корни рациональны, разложением на множители.
    Рациональное — приведением к общему знаменателю и решением числителя.
    """
    if len(node.children) != 2:
        raise SolveError("уравнение должно связывать две части")
    if len(variables) > 1:
        # Больше одной буквы: каждый способ решает относительно своей;
        # переключатель selectMethodText позволяет выбрать неизвестное.
        return _parametric_methods(node, variables)
    if len(variables) != 1:
        raise SolveError("поддерживается одно неизвестное")
    var = variables[0]
    lhs, rhs = node.children
    if (zero := _fraction_zero_method(node, var, variables)) is not None:
        return [zero]
    if (over := _unknown_over_number(node, var, variables)) is not None:
        return [*([direct] if (direct := _multiply_first(node, var)) else []), over]
    if (bracket := _bracket_times_number(node, var)) is not None:
        return [bracket]
    if (reciprocal := _reciprocal_equation(node, var)) is not None:
        return [reciprocal]
    if (powered := _power_equation(node, var)) is not None:
        return [powered]
    if (logarithm := _log10_equation(node, var)) is not None:
        return logarithm
    if (logarithms := _log_equation_methods(node, variables)) is not None:
        return logarithms
    if (exponential := _exponential_methods(node, variables)) is not None:
        return exponential
    if (decimal := _decimal_coefficient(node, var)) is not None:
        return decimal
    if (fractions := _fraction_sum_equation(node, var)) is not None:
        return fractions
    if (constant := _fraction_constant_equation(node, var)) is not None:
        return constant
    try:
        poly = _sub(poly_of(lhs, var), poly_of(rhs, var))
    except UndefinedError:
        raise
    except SolveError:
        exact = _alternative_result(
            node, variables, lambda n, v, ctx: _constant_quadratic(n, var, ctx)
        )
        if exact is not None:
            return [exact]
        symbolic = _alternative_result(node, variables, _symbolic_linear_rows)
        if symbolic is not None:
            return [symbolic]
        for solver in (_solve_rational, _solve_radical, _solve_transcendental):
            alternative = _alternative_result(node, variables, solver)
            if alternative is not None:
                return [alternative]
        raise
    degree = _degree(poly)

    if degree == 0:
        # Ответ — сам текст шага: решений либо нет, либо бесконечно много.
        special = SolveResult()
        if _coeff(poly, 0) == 0:
            special.add(Step(left=node, right=None, key="solutions_inf_many"), [_HEADER])
        else:
            _contradiction_rows(node, var, _coeff(poly, 0), special)
        return [special]
    if degree == 1:
        methods = [_run(node, variables, lambda n, c: _linear_solution(n, lhs, rhs, var, poly, c))]
        a, b = _coeff(poly, 1), _coeff(poly, 0)
        already = poly_of(lhs, var) == {1: a} and poly_of(rhs, var) == {0: -b}
        # Второй способ — сначала разделить обе части на коэффициент; он
        # отличается от первого, только если есть что переносить и делить.
        if (extra := _negative_linear_methods(node, var)) is not None:
            return methods[:1] + extra
        if (implicit := _both_sides_negative_methods(node, var)) is not None:
            return [methods[0], methods[0], implicit]
        left_form, right_form = _simple_side(lhs, var), _simple_side(rhs, var)
        if (
            a > 1
            and b != 0
            and left_form == (a, Fraction(0))
            and right_form == (Fraction(0), -b)
            and (-b) % a
        ):
            methods.append(_standard_form_method(node, var))
            return methods
        if a != 1 and b != 0 and not already:
            with contextlib.suppress(SolveError):  # the second way is optional
                methods.append(
                    _run(
                        node,
                        variables,
                        lambda n, c: _linear_solution(n, lhs, rhs, var, poly, c, divide_first=True),
                    )
                )
        return methods
    if degree == 2:
        a, b, c = _coeff(poly, 2), _coeff(poly, 1), _coeff(poly, 0)
        if (shown := quadratic_cards.methods(node, var, a, b, c)) is not None:
            return shown
        methods = [_run(node, variables, lambda n, c: _quadratic_solution(n, var, poly, c))]
        if b * b - 4 * a * c < 0:
            # «x ∉ ℝ» — верхний ответ; комплексные корни остаются способом.
            if (complex_method := _complex_quadratic_method(var, a, b, c)) is not None:
                methods.append(complex_method)
            return methods
        if _perfect_sqrt(b * b - 4 * a * c) is not None:
            methods.append(
                _run(
                    node,
                    variables,
                    lambda n, c: _quadratic_solution(n, var, poly, c, factoring=True),
                )
            )
        return methods
    result = SolveResult()
    high_ctx = SolveContext(result=result, variables=list(variables))
    result.set_solution(_solve_high_degree(node, var, poly, high_ctx))
    return [result]


__all__ = [
    "Poly",
    "poly_of",
    "solve_equation",
    "solve_methods",
]
