"""Линейные и квадратные неравенства.

Модуль зарегистрирован на знаки отношения ``<``, ``≤``, ``>``, ``≥``, ``≠``.
Неравенство приводится к виду ``p(x) ⋚ 0`` (через ``lhs - rhs``), затем:

* степень 1 — неизвестное выражается: при ``a > 0`` знак сохраняется, при
  ``a < 0`` меняется на противоположный; ответ — ``x < 2``;
* степень 2 — метод интервалов: находятся корни, знак старшего коэффициента
  задаёт промежутки; ответ — промежуток или их объединение;
* степень 0 — утверждение верно для всех или ни для одного значения;
* неизвестное в знаменателе — множество решений даёт ``sympy.solveset``,
  ответ — промежутки/объединение (ключи ``ineq_quotient_*``);
* корень, логарифм или степень с переменным показателем — тоже ``solveset``
  (ключи ``ineq_irr_solve``, ``ineq_solve_short``, ``log_ineq_gt_one``).

Ключи: ``ineq_linear_div``/``ineq_linear_div_neg``, ``move``,
``ineq_quad_to_eq_quad``, ``ineq_quad_lead_*``. Ответ-промежуток — узлы
``OPEN_*_INTERVAL``/``CLOSED_*_INTERVAL`` и ``UNION``.
"""

from __future__ import annotations

import itertools
from fractions import Fraction

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from . import quadratic_pm
from .arithmetic import format_number
from .base import SolveContext, SolveError, Step, solver_for
from .domain import add_restriction_steps
from .equations import _linear_rows, _poly_expr, poly_of
from .sympy_bridge import from_sympy, to_sympy
from .trig_equations import looks_trigonometric

_HEADER = CoreRichText(type="ineq_solve_short")

_PARAMETER = "k"
"""Имя параметра периода в общем решении неравенства: ``π/6 + 2πk < x``."""

_RELATIONS = (
    T.LESS_THAN,
    T.LESS_THAN_EQUAL,
    T.GREATER_THAN,
    T.GREATER_THAN_EQUAL,
    T.NOT_EQUALS,
)

# Смена знака отношения при делении на отрицательное число.
_FLIP: dict[T, T] = {
    T.LESS_THAN: T.GREATER_THAN,
    T.LESS_THAN_EQUAL: T.GREATER_THAN_EQUAL,
    T.GREATER_THAN: T.LESS_THAN,
    T.GREATER_THAN_EQUAL: T.LESS_THAN_EQUAL,
    T.NOT_EQUALS: T.NOT_EQUALS,
}


def _const(value: Fraction) -> CoreNode:
    return CoreNode.constant(format_number(value))


def _x_term(coefficient: Fraction, var: str) -> CoreNode:
    x = CoreNode.variable(var)
    if coefficient == 1:
        return x
    if coefficient == -1:
        return CoreNode(type=T.NEGATIVE, children=[x])
    return CoreNode(type=T.MULTIPLY_IMPLICIT, children=[_const(coefficient), x])


@solver_for(*_RELATIONS)
def solve_inequality(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Решить линейное неравенство с одним неизвестным."""
    ctx.require(len(node.children) >= 2, "неравенство связывает две части")
    ctx.require(len(ctx.variables) == 1, "поддерживается одно неизвестное")
    var = ctx.variables[0]
    if len(node.children) > 2:
        compound = _compound_inequality(node, var, ctx)
        if compound is None:
            raise SolveError("двойное неравенство не решается")
        return compound
    lhs, rhs = node.children

    try:
        poly = poly_of(lhs, var)
        for degree, coeff in poly_of(rhs, var).items():
            poly[degree] = poly.get(degree, Fraction(0)) - coeff
            if poly[degree] == 0:
                del poly[degree]
    except SolveError as error:
        for solver in (
            _rational_inequality,
            _irrational_inequality,
            _abs_inequality,
            _transcendental_inequality,
            _trig_inequality,
        ):
            answer = solver(node, var, ctx)
            if answer is not None:
                return answer
        # Прежний «уравнение с узлом SIN не решается» здесь вводил в заблуждение:
        # это неравенство, и ни один специальный путь его не взял.
        raise SolveError(
            "неравенство не решается: выражение не сводится к многочлену, дроби, "
            "корню, модулю, показателю или периоду"
        ) from error

    degree = max(poly) if poly else 0
    if degree == 0:
        return _constant_inequality(node, poly, ctx)
    if degree == 2:
        return _quadratic_inequality(node, var, poly, ctx)
    ctx.require(degree == 1, "поддерживаются линейные и квадратные неравенства")

    a = poly[1]
    b = poly.get(0, Fraction(0))
    value = -b / a
    # При делении на отрицательное число знак неравенства меняется.
    final_type = node.type if a > 0 else _FLIP[node.type]

    rows = _linear_rows(node, lhs, rhs, var, ctx, relation=node.type, flipped=_FLIP[node.type])
    if rows is not None:
        return rows

    left = node
    already = poly_of(lhs, var) == {1: a} and poly_of(rhs, var) == {0: -b}
    if b != 0 and not already:
        after_move = CoreNode(type=node.type, children=[_x_term(a, var), _const(-b)])
        ctx.result.add(Step(left=node, right=after_move, key="move"), [_HEADER])
        left = after_move

    solution = CoreNode(type=final_type, children=[CoreNode.variable(var), _const(value)])
    if a != 1:
        key = "ineq_linear_div_neg" if a < 0 else "ineq_linear_div"
        ctx.result.add(Step(left=left, right=solution, key=key, args=[_const(a)]), [_HEADER])
    return solution


_QUOTIENT_KEY: dict[T, str] = {
    T.LESS_THAN: "ineq_quotient_lt",
    T.LESS_THAN_EQUAL: "ineq_quotient_lte",
    T.GREATER_THAN: "ineq_quotient_gt",
    T.GREATER_THAN_EQUAL: "ineq_quotient_gte",
}


def _rational_inequality(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """Решить неравенство с неизвестным в знаменателе.

    Множество решений даёт ``sympy.solveset`` на числовой прямой; ответ
    переводится в промежутки/объединение. ``None`` — знаменатель не зависит
    от неизвестного (не рациональное) или отношение не поддерживается.
    """
    lhs, rhs = node.children
    try:
        expression = sympy.together(to_sympy(lhs) - to_sympy(rhs))
        _, denominator = sympy.fraction(expression)
    except SolveError:
        return None
    if not denominator.has(sympy.Symbol(var)):
        return None
    key = _QUOTIENT_KEY.get(node.type)
    if key is None:
        return None

    symbol = sympy.Symbol(var)
    try:
        values = sympy.solveset(_relational(node.type, expression), symbol, sympy.S.Reals)
    except (TypeError, ValueError, NotImplementedError):
        return None

    add_restriction_steps(node, [var], ctx, expression)
    answer = from_sympy(values)
    ctx.result.add(Step(left=node, right=answer, key=key), [_HEADER])
    return answer


def _compound_inequality(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """Двойное (тройное) неравенство ``a ⋚ x ⋚ b`` — пересечение условий.

    Цепочка из трёх и более детей разбирается в ``And`` отношений; множество
    решений даёт ``solveset``, ответ — промежуток.
    """
    try:
        values = [to_sympy(child) for child in node.children]
    except SolveError:
        return None
    symbol = sympy.Symbol(var)
    conditions = [
        _chain_relation(node.type, left, right) for left, right in itertools.pairwise(values)
    ]
    try:
        pieces = [sympy.solveset(condition, symbol, sympy.S.Reals) for condition in conditions]
    except (TypeError, ValueError, NotImplementedError):
        return None
    result_set = pieces[0] if len(pieces) == 1 else sympy.Intersection(*pieces)
    try:
        answer = from_sympy(sympy.simplify(result_set))
    except SolveError:
        return None
    ctx.result.add(Step(left=node, right=answer, key="ineq_solve_separate"), [_HEADER])
    return answer


def _chain_relation(node_type: T, left: sympy.Expr, right: sympy.Expr) -> sympy.Rel:
    """Одно звено цепочки неравенств."""
    if node_type is T.LESS_THAN:
        return sympy.Lt(left, right)
    if node_type is T.LESS_THAN_EQUAL:
        return sympy.Le(left, right)
    if node_type is T.GREATER_THAN:
        return sympy.Gt(left, right)
    if node_type is T.GREATER_THAN_EQUAL:
        return sympy.Ge(left, right)
    return sympy.Ne(left, right)


def _irrational_inequality(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """Иррациональное неравенство: корни, множество решений — ``solveset``."""
    expression = _difference(node)
    if expression is None or not _has_radical(expression):
        return None
    return _inequality_set(node, expression, "ineq_irr_solve", ctx)


def _abs_inequality(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """Неравенство с модулем: два случая, множество решений — ``solveset``."""
    expression = _difference(node)
    if expression is None or not expression.has(sympy.Abs):
        return None
    symbol = sympy.Symbol(var)
    try:
        values = sympy.solveset(_relational(node.type, expression), symbol, sympy.S.Reals)
    except (TypeError, ValueError, NotImplementedError):
        return None
    try:
        answer = from_sympy(values)
    except SolveError:
        return None
    ctx.result.add(
        Step(left=node, right=answer, key="ineq_separate_abs", args=[CoreNode.constant("2")]),
        [_HEADER],
    )
    return answer


def _transcendental_inequality(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """Показательное или логарифмическое неравенство через ``solveset``."""
    expression = _difference(node)
    if expression is None:
        return None
    symbol = sympy.Symbol(var)
    if expression.has(sympy.log):
        key = "ineq_solve_short"
    elif _has_variable_power(expression, symbol):
        key = "log_ineq_gt_one"
    else:
        return None
    return _inequality_set(node, expression, key, ctx)


def _trig_period(expression: sympy.Expr, symbol: sympy.Symbol) -> sympy.Expr | None:
    """Наименьший период выражения: ``periodicity`` или проверка по определению.

    ``sympy.periodicity`` не знает модуль от периода (``|sin x|`` с периодом
    ``π``), поэтому при отказе кандидаты ``π`` и ``2π`` проверяются прямым
    тождеством ``f(x+T) = f(x)``. Подходящий кандидат может быть и больше
    минимального периода -- решение от этого не неверно, лишь не сокращено.
    """
    try:
        period = sympy.periodicity(expression, symbol)
    except (TypeError, ValueError):
        period = None
    if period is not None and period.is_number and period > 0:
        return period
    for candidate in (sympy.pi, 2 * sympy.pi):
        try:
            if sympy.simplify(expression.subs(symbol, symbol + candidate) - expression) == 0:
                return candidate
        except (TypeError, ValueError):
            continue
    return None


def _trig_inequality(node: CoreNode, var: str, ctx: SolveContext) -> CoreNode | None:
    """Периодическое тригонометрическое неравенство: ответ на одном периоде + ``kT``.

    ``sympy.solveset`` на ``Reals`` теряет периодичность (``sin x > 1/2``
    сужает до главного промежутка), поэтому множество решений берут на одном
    периоде ``[0; T]`` и продолжают сдвигом на ``T·k``: границы промежутков
    записываются как ``π/6 + 2πk``. Если ``solveset`` не берёт отношение на
    периоде (``|sin x| > 1/2``), применяют метод интервалов: нули уравнения
    режут период, знак проверяют в серединах дуг. Ключи -- ``trig_find_period``
    и ``trig_general_sol``, ответ -- промежуток или объединение.
    """
    if not looks_trigonometric(node):
        return None
    expression = _difference(node)
    if expression is None:
        return None
    plain = sympy.Symbol(var)
    symbol = sympy.Symbol(var, real=True)
    expression = expression.subs(plain, symbol)
    if expression.free_symbols != {symbol}:
        return None
    period = _trig_period(expression, symbol)
    if period is None:
        return None

    pieces = _period_pieces(node, expression, symbol, period)
    x = CoreNode.variable(var)
    if pieces is None:
        return None
    if not pieces:
        ctx.result.add(Step(left=node, right=None, key="rel_el_of_zero", args=[x]), [_HEADER])
        return CoreNode.empty()

    parameter = sympy.Symbol(_PARAMETER)
    if any(start is sympy.S.NegativeInfinity for start, _, _, _ in pieces):
        answer = _all_reals()
        ctx.result.add(Step(left=node, right=answer, key="rel_el_of_r", args=[x]), [_HEADER])
        return answer
    intervals: list[CoreNode] = []
    for start_value, end_value, left_closed, right_closed in pieces:
        start = from_sympy(start_value + period * parameter)
        end = from_sympy(end_value + period * parameter)
        intervals.append(_interval(start, end, left_closed, right_closed))

    ctx.result.add(Step(left=node, right=None, key="trig_find_period"), [_HEADER])
    answer = intervals[0] if len(intervals) == 1 else _union(intervals)
    ctx.result.add(
        Step(
            left=node,
            right=answer,
            key="trig_general_sol",
            args=[from_sympy(period * parameter)],
        ),
        [_HEADER],
    )
    return answer


def _period_pieces(
    node: CoreNode, expression: sympy.Expr, symbol: sympy.Symbol, period: sympy.Expr
) -> list[tuple[sympy.Expr, sympy.Expr, bool, bool]] | None:
    """Куски решений на одном периоде ``(начало, конец, левый закрыт, правый закрыт)``.

    Сначала ``solveset`` на промежутке ``[0; T]``; его ответ переводят в
    куски. Если ``solveset`` сдаётся (``ConditionSet`` -- так бывает с
    ``|sin x|``), нули уравнения режут период на дуги, и каждая дуга
    проверяется подстановкой середины (метод интервалов). ``None`` -- случай
    не для модуля; пустой список -- решений нет.
    """
    try:
        base = sympy.solveset(
            _relational(node.type, expression), symbol, domain=sympy.Interval(0, period)
        )
    except (TypeError, ValueError, NotImplementedError):
        return None
    if base is sympy.S.EmptySet:
        return []
    if isinstance(base, sympy.Interval) and base.start == 0 and base.end == period:
        return [(sympy.S.NegativeInfinity, sympy.S.Infinity, False, False)]
    if not isinstance(base, sympy.ConditionSet):
        pieces: list[tuple[sympy.Expr, sympy.Expr, bool, bool]] = []
        for piece in base.args if isinstance(base, sympy.Union) else (base,):
            if not isinstance(piece, sympy.Interval):
                return None
            pieces.append((piece.start, piece.end, not piece.left_open, not piece.right_open))
        return pieces

    return _chart_pieces(node, expression, symbol, period)


def _chart_pieces(
    node: CoreNode, expression: sympy.Expr, symbol: sympy.Symbol, period: sympy.Expr
) -> list[tuple[sympy.Expr, sympy.Expr, bool, bool]] | None:
    """Метод интервалов на периоде: нули режут окружность, знак в серединах дуг."""
    try:
        zeros_set = sympy.solveset(
            sympy.Eq(expression, 0), symbol, domain=sympy.Interval(0, period)
        )
    except (TypeError, ValueError, NotImplementedError):
        return None
    if not isinstance(zeros_set, sympy.FiniteSet):
        return None
    zeros = sorted({sympy.simplify(z) for z in zeros_set.args}, key=lambda z: float(sympy.N(z)))
    if any(z == period for z in zeros):
        # x = T совпадает с x = 0 на периодической окружности.
        zeros = [z for z in zeros if z != period]
    if not zeros:
        holds = _relation_holds_value(node, expression, symbol, period / 2)
        if holds is None:
            return None
        return [(sympy.S.NegativeInfinity, sympy.S.Infinity, False, False)] if holds else []

    closed = node.type in (T.LESS_THAN_EQUAL, T.GREATER_THAN_EQUAL)
    count = len(zeros)
    pieces: list[tuple[sympy.Expr, sympy.Expr, bool, bool]] = []
    for index in range(count):
        start = zeros[index]
        end = zeros[(index + 1) % count]
        end_wrapped = end if index + 1 < count else end + period
        middle = (start + end_wrapped) / 2
        holds = _relation_holds_value(node, expression, symbol, middle)
        if holds is None:
            return None
        if holds:
            pieces.append((start, end_wrapped, closed, closed))
    return pieces


def _relation_holds_value(
    node: CoreNode, expression: sympy.Expr, symbol: sympy.Symbol, value: sympy.Expr
) -> bool | None:
    """Верно ли отношение ``f ⋚ 0`` в точке; ``None``, если истина не вычисляется."""
    try:
        difference = sympy.simplify(expression.subs(symbol, value))
        resolved = sympy.simplify(_relational(node.type, difference))
    except (TypeError, ValueError):
        return None
    if resolved is sympy.true:
        return True
    if resolved is sympy.false:
        return False
    return None


def _difference(node: CoreNode) -> sympy.Expr | None:
    """Разность частей неравенства в sympy или ``None``."""
    lhs, rhs = node.children
    try:
        return sympy.together(to_sympy(lhs) - to_sympy(rhs))
    except SolveError:
        return None


def _inequality_set(
    node: CoreNode, expression: sympy.Expr, key: str, ctx: SolveContext
) -> CoreNode | None:
    """Множество решений неравенства через ``sympy.solveset``.

    ``None`` -- sympy вернул множество, которое не переводится в узлы
    (например, ``ConditionSet`` для ``|sin x| > 1/2``): тогда путь не наш и
    вызывающий пробует следующий решатель.
    """
    symbol = sympy.Symbol(ctx.variables[0])
    try:
        values = sympy.solveset(_relational(node.type, expression), symbol, sympy.S.Reals)
    except (TypeError, ValueError, NotImplementedError):
        return None
    try:
        answer = from_sympy(values)
    except SolveError:
        return None
    add_restriction_steps(node, ctx.variables, ctx, expression)
    ctx.result.add(Step(left=node, right=answer, key=key), [_HEADER])
    return answer


def _has_radical(expression: sympy.Expr) -> bool:
    """Есть ли в выражении квадратный корень."""
    return any(
        isinstance(power, sympy.Pow) and power.exp == sympy.Rational(1, 2)
        for power in expression.atoms(sympy.Pow)
    )


def _has_variable_power(expression: sympy.Expr, symbol: sympy.Symbol) -> bool:
    """Есть ли степень с переменной в показателе (показательное выражение)."""
    return any(
        isinstance(power, sympy.Pow) and power.exp.has(symbol)
        for power in expression.atoms(sympy.Pow)
    )


def _relational(node_type: T, expression: sympy.Expr) -> sympy.Rel:
    """Отношение ``выражение ⋚ 0`` для решателя множеств sympy."""
    zero = sympy.Integer(0)
    if node_type is T.LESS_THAN:
        return sympy.Lt(expression, zero)
    if node_type is T.LESS_THAN_EQUAL:
        return sympy.Le(expression, zero)
    if node_type is T.GREATER_THAN:
        return sympy.Gt(expression, zero)
    if node_type is T.GREATER_THAN_EQUAL:
        return sympy.Ge(expression, zero)
    return sympy.Ne(expression, zero)


def _constant_inequality(node: CoreNode, poly: dict[int, Fraction], ctx: SolveContext) -> CoreNode:
    """Неравенство, где неизвестное сократилось: верно для всех или ни для кого."""
    value = poly.get(0, Fraction(0))
    x = CoreNode.variable(ctx.variables[0])
    if _holds(node.type, negative=value < 0, zero=value == 0):
        answer = _all_reals()
        ctx.result.add(Step(left=node, right=answer, key="rel_el_of_r", args=[x]), [_HEADER])
    else:
        answer = CoreNode.empty()
        ctx.result.add(Step(left=node, right=None, key="rel_el_of_zero", args=[x]), [_HEADER])
    return answer


def _quadratic_inequality(
    node: CoreNode, var: str, poly: dict[int, Fraction], ctx: SolveContext
) -> CoreNode:
    """Квадратное неравенство методом интервалов."""
    a = poly.get(2, Fraction(0))
    b = poly.get(1, Fraction(0))
    c = poly.get(0, Fraction(0))
    x = CoreNode.variable(var)
    discriminant = b * b - 4 * a * c
    below = node.type in (T.LESS_THAN, T.LESS_THAN_EQUAL)
    closed = node.type in (T.LESS_THAN_EQUAL, T.GREATER_THAN_EQUAL)

    if discriminant < 0:
        # Знак постоянен: его задаёт старший коэффициент. Утверждение верно
        # для всех, когда требуемый знак совпадает с фактическим.
        positive = a > 0
        true_for_all = positive != below
        key = ("ineq_quad_lead_pos_" if positive else "ineq_quad_lead_neg_") + (
            "t" if true_for_all else "f"
        )
        answer = _all_reals() if true_for_all else CoreNode.empty()
        ctx.result.add(
            Step(left=node, right=answer if true_for_all else None, key=key, args=[x, _const(a)]),
            [_HEADER],
        )
        return answer

    expression = _poly_expr(poly, var)
    symbol = sympy.Symbol(var)
    roots = sorted(sympy.solve(sympy.Eq(expression, 0), symbol), key=_sort_key)
    inside = (a > 0) == below
    answer = _interval_answer(roots[0], roots[-1], inside=inside, closed=closed)
    if (
        discriminant > 0
        and {a.denominator, b.denominator, c.denominator} == {1}
        and quadratic_pm.inequality_rows(node, var, int(a), int(b), int(c), ctx.result, answer)
    ):
        return answer
    right = CoreNode.node(T.EQUALS, from_sympy(expression), CoreNode.constant("0"))
    ctx.result.add(Step(left=node, right=right, key="ineq_quad_to_eq_quad", args=[x]), [_HEADER])
    return answer


def _interval_answer(lo: sympy.Expr, hi: sympy.Expr, *, inside: bool, closed: bool) -> CoreNode:
    """Ответ-промежуток по корням ``lo ≤ hi``."""
    low, high = from_sympy(lo), from_sympy(hi)
    if _is_zero(lo - hi):
        if inside and closed:
            return _interval(low, high, True, True)  # точка [r, r]
        if inside:
            return CoreNode.empty()
        if closed:
            return _all_reals()
        return _union(
            [
                _interval(_neg_inf(), low, False, False),
                _interval(high, _pos_inf(), False, False),
            ]
        )
    if inside:
        return _interval(low, high, closed, closed)
    return _union(
        [
            _interval(_neg_inf(), low, False, closed),
            _interval(high, _pos_inf(), closed, False),
        ]
    )


def _holds(node_type: T, *, negative: bool, zero: bool) -> bool:
    """Верно ли отношение для выражения с известным знаком."""
    if node_type is T.LESS_THAN:
        return negative
    if node_type is T.LESS_THAN_EQUAL:
        return negative or zero
    if node_type is T.GREATER_THAN:
        return not negative and not zero
    if node_type is T.GREATER_THAN_EQUAL:
        return not negative
    return not zero


def _interval(start: CoreNode, end: CoreNode, left_closed: bool, right_closed: bool) -> CoreNode:
    """Узел промежутка по открытости краёв."""
    node_type = {
        (True, True): T.CLOSED_CLOSED_INTERVAL,
        (True, False): T.CLOSED_OPEN_INTERVAL,
        (False, True): T.OPEN_CLOSED_INTERVAL,
        (False, False): T.OPEN_OPEN_INTERVAL,
    }[(left_closed, right_closed)]
    return CoreNode.node(node_type, start, end)


def _all_reals() -> CoreNode:
    """Вся числовая прямая как промежуток ``(-∞, +∞)``."""
    return _interval(_neg_inf(), _pos_inf(), False, False)


def _neg_inf() -> CoreNode:
    return CoreNode.node(T.NEGATIVE, CoreNode.constant("∞"))


def _pos_inf() -> CoreNode:
    return CoreNode.constant("∞")


def _union(nodes: list[CoreNode]) -> CoreNode:
    if len(nodes) == 1:
        return nodes[0]
    return CoreNode.node(T.UNION, *nodes)


def _is_zero(expression: sympy.Expr) -> bool:
    result = sympy.simplify(expression) == 0
    return result is True or result is sympy.true


def _sort_key(root: sympy.Expr) -> float:
    try:
        return float(sympy.N(root))
    except (TypeError, ValueError):
        return 0.0


def inequality_on_interval(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Решить неравенство на отрезке методом интервалов (в т.ч. тригонометрическое).

    Аргументы — границы отрезка. Выражение ``f = lhs − rhs`` разбивается
    точками нулей и разрывов; на каждом промежутке проверяется знак ``f``;
    подходящие промежутки объединяются, концы включаются по нестрогому
    отношению. Ответ — промежуток или объединение.
    """
    ctx.require(node.type in _RELATIONS, "неравенство: знак отношения")
    ctx.require(len(args) == 2, "нужны границы отрезка")
    ctx.require(len(ctx.variables) == 1, "неравенство на отрезке: одна неизвестная")
    symbol = sympy.Symbol(ctx.variables[0])
    lower, upper = to_sympy(args[0]), to_sympy(args[1])
    if lower > upper:
        lower, upper = upper, lower
    if lower.is_real is not True or upper.is_real is not True:
        raise SolveError("границы отрезка должны быть числами")

    expression = sympy.together(to_sympy(node.children[0]) - to_sympy(node.children[1]))
    singular = _real_points(sympy.singularities(expression, symbol), lower, upper)
    roots = [
        root
        for root in _real_points(sympy.solve(sympy.Eq(expression, 0), symbol), lower, upper)
        if not any(sympy.simplify(root - point) == 0 for point in singular)
    ]
    critical = sorted({*singular, *roots}, key=_sort_key)
    boundaries = [lower, *critical, upper]

    atoms: list[sympy.Set] = []
    for start, end in itertools.pairwise(boundaries):
        if _relation_holds(node.type, expression.subs(symbol, (start + end) / 2)):
            left_closed = _relation_holds(node.type, expression.subs(symbol, start))
            right_closed = _relation_holds(node.type, expression.subs(symbol, end))
            atoms.append(
                sympy.Interval(start, end, left_open=not left_closed, right_open=not right_closed)
            )
    for point in critical:
        if _relation_holds(node.type, expression.subs(symbol, point)):
            atoms.append(sympy.Interval(point, point))

    combined = sympy.simplify(sympy.Union(*atoms)) if atoms else sympy.EmptySet
    answer = from_sympy(combined)
    ctx.result.add(Step(left=node, right=answer, key="ineq_solve_short"), [_HEADER])
    return answer


def _real_points(values: object, lower: sympy.Expr, upper: sympy.Expr) -> list[sympy.Expr]:
    """Действительные точки из набора/списка внутри ``(lower, upper)``."""
    if isinstance(values, (sympy.FiniteSet, list, tuple, set)):
        candidates = list(values)
    else:
        return []
    result: list[sympy.Expr] = []
    for point in candidates:
        try:
            if point.is_real is False:
                continue
            value = float(sympy.N(point))
        except (TypeError, ValueError):
            continue
        if float(sympy.N(lower)) < value < float(sympy.N(upper)):
            result.append(point)
    return result


def _relation_holds(node_type: T, value: sympy.Expr) -> bool:
    """Верно ли строгое/нестрогое отношение для значения выражения."""
    try:
        number = float(sympy.N(value))
    except (TypeError, ValueError):
        return False
    if node_type is T.LESS_THAN:
        return number < 0
    if node_type is T.LESS_THAN_EQUAL:
        return number <= 0
    if node_type is T.GREATER_THAN:
        return number > 0
    if node_type is T.GREATER_THAN_EQUAL:
        return number >= 0
    if node_type is T.EQUALS:
        return number == 0
    return number != 0


__all__ = [
    "inequality_on_interval",
    "solve_inequality",
]
