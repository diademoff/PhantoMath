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
from .sympy_bridge import from_sympy, to_sympy

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


def _solve_radical(node: CoreNode, variables: list[str], ctx: SolveContext) -> CoreNode | None:
    """Решить иррациональное уравнение возведением в квадрат.

    Берётся одно возведение в квадрат (один радикал): уравнение ``f = g``
    превращается в ``f² = g²``, решается как многочлен, затем посторонние
    корни отсеиваются подстановкой в исходное ``f - g``. Возвращает ``None``,
    если радикалов нет или одним возведением их не убрать.
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
    squared = CoreNode.node(T.EQUALS, from_sympy(left**2), from_sympy(right**2))
    if _has_radical(to_sympy(squared)):
        return None  # радикал остался — нужно несколько возведений, не берём

    ctx.result.add(Step(left=node, right=squared, key="eq_irrational_simple_square"), [_HEADER])
    answer = solve_equation(squared, ctx)
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
        return "eq_trans", sympy.Eq(left_log[0], left_log[1] ** right)
    if right_log is not None and left.is_number:
        return "eq_trans", sympy.Eq(right_log[0], right_log[1] ** left)

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
    ctx.require(
        len(ctx.variables) == 1,
        "поддерживается одно неизвестное: системы и параметры идут следующими",
    )
    var = ctx.variables[0]
    lhs, rhs = node.children

    try:
        poly = _sub(poly_of(lhs, var), poly_of(rhs, var))
    except SolveError:
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


def solve_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """Способы решения уравнения: первый — основной, дальше — альтернативы.

    Линейное уравнение решается переносом и делением, а если коэффициент при
    ``x`` не единица и есть свободный член — ещё и делением до переноса.
    Квадратное — формулой и, если корни рациональны, разложением на множители.
    Рациональное — приведением к общему знаменателю и решением числителя.
    """
    if len(node.children) != 2 or len(variables) != 1:
        raise SolveError("поддерживается одно неизвестное")
    var = variables[0]
    lhs, rhs = node.children
    try:
        poly = _sub(poly_of(lhs, var), poly_of(rhs, var))
    except SolveError:
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
