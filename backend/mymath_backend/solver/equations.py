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

Ключи шагов берутся из ``truth/data/explanations.json``: ``move``,
``eq_linar_divide_both_sides``, ``eq_quad_solve_in_r``, заголовок
``eq_solve_short``. Разбор словаря -- ``truth/04-explanations.md``.
"""

from __future__ import annotations

from collections.abc import Callable
from fractions import Fraction
from math import isqrt

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .arithmetic import as_fraction, format_number
from .base import SolveContext, SolveError, SolveResult, Step, solver_for
from .domain import add_restriction_steps
from .methods import method_provider
from .sympy_bridge import from_sympy, to_sympy

# Многочлен: степень -> коэффициент. Нулевые коэффициенты не хранятся,
# поэтому пустой словарь -- это тождественный ноль.
Poly = dict[int, Fraction]

_HEADER = CoreRichText(type="eq_solve_short")
"""Заголовок шага: «Решите уравнение»."""

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
            if number.type is T.CONSTANT and name.type is T.VARIABLE and name.value == var:
                found.append(("x", sign * as_fraction(number)))
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


def _linear_rows(
    node: CoreNode, lhs: CoreNode, rhs: CoreNode, var: str, ctx: SolveContext
) -> CoreNode | None:
    """Photomath 7.10.0 rows for ``a1 x + b1 = a2 x + b2``: move, collect, calculate, divide.

    Returns ``None`` when a side is not a plain ``a x + b`` so the general path is used.
    """
    left, right = _simple_side(lhs, var), _simple_side(rhs, var)
    if left is None or right is None:
        return None
    (a1, b1), (a2, b2) = left, right
    if a1 == 0 or a1 == a2:
        return None
    eq = CoreNode.node
    current, stages = node, []
    cur_l, cur_r = lhs, rhs
    if a2 != 0:  # move the unknown to the left
        term = _x_term(abs(a2), var)
        after_l = eq(T.SUBTRACT if a2 > 0 else T.ADD, cur_l, term)
        after_r = _const(b2)
        balanced = eq(
            T.EQUALS,
            eq(T.SUBTRACT if a2 > 0 else T.ADD, cur_l, term),
            eq(T.SUBTRACT if a2 > 0 else T.ADD, cur_r, term),
        )
        detail = SolveResult()
        detail.add_group("rel_swap_left_var", Step(current, balanced, "rel_swap_left_var"))
        after = eq(T.EQUALS, after_l, after_r)
        detail.add_group("remove_opposites", Step(balanced, after, "remove_opposites"))
        detail.set_solution(after)
        stages.append(Step(current, after, "rel_move_left_var", subresult=detail))
        current, cur_l, cur_r = after, after_l, after_r
    if b1 != 0:  # move the constant to the right
        k = _const(abs(b1))
        sign = T.SUBTRACT if b1 > 0 else T.ADD
        x_part = _x_term(a1, var)
        if a2 != 0:
            x_part = eq(T.SUBTRACT if a2 > 0 else T.ADD, x_part, _x_term(abs(a2), var))
        after_r = _const(-b1) if b2 == 0 else _plus(_const(b2), -b1, k)
        balanced = eq(T.EQUALS, eq(sign, cur_l, k), eq(sign, cur_r, k))
        after = eq(T.EQUALS, x_part, after_r)
        detail = SolveResult()
        detail.add_group("rel_swap_right_const", Step(current, balanced, "rel_swap_right_const"))
        detail.add_group("remove_opposites", Step(balanced, after, "remove_opposites"))
        detail.set_solution(after)
        stages.append(Step(current, after, "rel_move_right_const", subresult=detail))
        current, cur_l, cur_r = after, x_part, after_r
    coefficient, total = a1 - a2, b2 - b1
    if a2 != 0 or b1 != 0:
        header = "move" if len(stages) > 1 or a2 != 0 else "rel_move_right_const_msg"
        ctx.result.add_group(header, *stages)
    two_terms = b1 != 0 and b2 != 0
    if a2 != 0:
        collected = eq(T.EQUALS, _x_term(coefficient, var), cur_r)
        detail_key = "sum_suffix_sub_detail" if a2 > 0 else "sum_suffix_add_detail"
        x = CoreNode.variable(var)
        grouped = eq(
            T.EQUALS,
            eq(
                T.MULTIPLY_IMPLICIT,
                eq(T.BRACKET, eq(T.SUBTRACT if a2 > 0 else T.ADD, _const(a1), _const(abs(a2)))),
                x,
            ),
            cur_r,
        )
        explicit = eq(T.EQUALS, eq(T.MULTIPLY_IMPLICIT, _const(coefficient), x), cur_r)
        detail = SolveResult()
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
            done = eq(T.EQUALS, _x_term(coefficient, var), _const(total))
            sums.append(Step(current, done, "add" if b1 < 0 else "sub"))
            current = done
        ctx.result.add_group(
            ["sum_suffix", "calculate_short"] if two_terms else ["sum_suffix"], *sums
        )
    elif two_terms:
        done = eq(T.EQUALS, _x_term(coefficient, var), _const(total))
        ctx.result.add_group("calculate_short", Step(current, done, "add" if b1 < 0 else "sub"))
        current = done
    solution = _equation(var, _const(total / coefficient))
    if coefficient != 1:
        divided = eq(
            T.EQUALS,
            eq(T.FRACTION, current.children[0], _const(coefficient)),
            eq(T.FRACTION, current.children[1], _const(coefficient)),
        )
        detail = SolveResult()
        detail.add_group(
            "eq_linear_div", Step(current, divided, "eq_linear_div", [_const(coefficient)])
        )
        detail.add_group("divide", Step(divided, solution, "divide"))
        detail.set_solution(solution)
        ctx.result.add_group(
            "divide_both_sides",
            Step(current, solution, "eq_linear_div", [_const(coefficient)], subresult=detail),
        )
    return solution


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

    if not divide_first and (rows := _linear_rows(node, lhs, rhs, var, ctx)) is not None:
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
    if discriminant < 0:
        raise SolveError(
            "квадратное уравнение не имеет действительных корней", "eq_quad_solve_complex"
        )

    exact = _perfect_sqrt(discriminant)
    if factoring and exact is None:
        raise SolveError("разложение на множители с рациональными корнями невозможно")
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
        solution = CoreNode.node(
            T.LIST,
            _equation(var, _quad_root(-b, root, 2 * a, plus=a < 0)),
            _equation(var, _quad_root(-b, root, 2 * a, plus=a > 0)),
        )

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
    if d.is_negative is True:
        raise SolveError(
            "квадратное уравнение не имеет действительных корней", "eq_quad_solve_complex"
        )
    if d.is_nonnegative is not True:
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
    ctx.result.add_group(
        "lesson_roots",
        Step(
            left=substitutions,
            right=solution,
            key="eq_quad_solve_in_r",
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
            "lesson_root_substitute", Step(generic, substituted, "lesson_root_formula")
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
    ctx.result.add(Step(left=node, right=None, key="eq_param_write"), [_HEADER])
    ctx.result.add(
        Step(left=node, right=answer, key="eq_linear_param_j_final", args=[CoreNode.variable(var)]),
        [_HEADER],
    )
    return answer


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
    return methods


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
        combined = sympy.together(to_sympy(lhs) - to_sympy(rhs))
        numerator, denominator = sympy.fraction(combined)
    except SolveError:
        return None
    if not denominator.has(sympy.Symbol(var)):
        return None

    add_restriction_steps(node, variables, ctx, combined)
    zero = CoreNode.constant("0")
    one_side = CoreNode.node(T.EQUALS, from_sympy(combined), zero)
    if not one_side.structural_eq(node):
        ctx.result.add(Step(left=node, right=one_side, key="eq_trans"), [_HEADER])

    numerator_eq = CoreNode.node(T.EQUALS, from_sympy(numerator), zero)
    ctx.result.add(
        Step(left=one_side, right=numerator_eq, key="eq_linear_frac_zero", args=[zero]),
        [_HEADER],
    )
    answer = solve_equation(numerator_eq, ctx)
    return _exclude_poles(answer, denominator, var, ctx)


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

    transformed = _log_exp_transform(left, right)
    if transformed is None:
        if _impossible_exponential(left, right) or _impossible_exponential(right, left):
            # a^x > 0 при a > 0: неположительная правая часть — решений нет.
            ctx.result.add(Step(left=node, right=None, key="false_statement_solve"), [_HEADER])
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


def _log_exp_transform(left: sympy.Expr, right: sympy.Expr) -> tuple[str, sympy.Eq] | None:
    """Преобразовать логарифмическое/показательное уравнение или ``None``."""
    left_log, right_log = _single_log(left), _single_log(right)
    if left_log is not None and right_log is not None and left_log[1] == right_log[1]:
        return "eq_log_equalise", sympy.Eq(left_log[0], right_log[0])
    if left_log is not None and right.is_number:
        return "log_def_solve", sympy.Eq(left_log[0], left_log[1] ** right)
    if right_log is not None and left.is_number:
        return "log_def_solve", sympy.Eq(right_log[0], right_log[1] ** left)

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
    return (
        isinstance(power, sympy.Pow)
        and power.base.is_number
        and power.base.is_positive is True
        and other.is_number is True
        and other.is_positive is False
    )


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


def _solve_high_degree(node: CoreNode, var: str, poly: Poly, ctx: SolveContext) -> CoreNode:
    """Решить уравнение степени выше второй.

    Показывается разложение многочлена на множители (``solve_by_factoring``),
    корни берёт sympy (действительные, по возрастанию). Алгебраические корни
    (``∛``, ``√``) остаются точными узлами.
    """
    expression = _poly_expr(poly, var)
    symbol = sympy.Symbol(var)
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
    if not roots:
        raise SolveError("уравнение не имеет действительных корней", "eq_quad_disc_no_solution")
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
    except SolveError:
        exact_quadratic = _constant_quadratic(node, var, ctx)
        if exact_quadratic is not None:
            return exact_quadratic
        for solver in (_solve_rational, _solve_radical, _solve_transcendental):
            answer = solver(node, ctx.variables, ctx)
            if answer is not None:
                return answer
        raise
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
    return _solve_high_degree(node, var, poly, ctx)


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
    try:
        poly = _sub(poly_of(lhs, var), poly_of(rhs, var))
    except SolveError:
        exact = _alternative_result(
            node, variables, lambda n, v, ctx: _constant_quadratic(n, var, ctx)
        )
        if exact is not None:
            return [exact]
        for solver in (_solve_rational, _solve_radical, _solve_transcendental):
            alternative = _alternative_result(node, variables, solver)
            if alternative is not None:
                return [alternative]
        raise
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
