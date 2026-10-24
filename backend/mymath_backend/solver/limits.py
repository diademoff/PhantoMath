"""Пределы функций.

Модуль зарегистрирован на ``LIMIT``, ``LIMIT_LEFT`` и ``LIMIT_RIGHT``.
Дети: точка и выражение (``[to, expr]``). Предел считает sympy, поэтому
работают пределы в конечной точке, на бесконечности и односторонние,
включая раскрытие неопределённостей.

Результат переводится обратно в ``CoreNode`` мостом; ``∞`` даёт константу
«∞». Если предел не существует, карточка объясняет причину и ответа-узла нет;
вычислить предел не удалось — :class:`SolveError`.

Первая карточка называет учебный метод (разложение и сокращение, деление на
старшую степень, замечательные пределы, сопряжённое, знак одностороннего
предела, отсутствие предела); Лопиталь остаётся альтернативой
(см. :mod:`mymath_backend.solver.limit_cards`).
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, SolveResult, Step, route, solver_for
from .limit_cards import cards_for
from .methods import method_provider
from .sympy_bridge import from_sympy, to_sympy

_LIMITS = (T.LIMIT, T.LIMIT_LEFT, T.LIMIT_RIGHT)

# Направление подхода: слева «-», справа и двусторонний «+».
_DIRECTION: dict[T, str] = {
    T.LIMIT: "+",
    T.LIMIT_LEFT: "-",
    T.LIMIT_RIGHT: "+",
}


def _two_sided(expression: sympy.Expr, symbol: sympy.Symbol, point: sympy.Expr) -> sympy.Expr:
    """Двусторонний предел в конечной точке: стороны обязаны совпасть.

    Раньше двусторонний предел считался как правосторонний (``dir="+"``),
    поэтому ``1/x`` при ``x → 0`` давал ``∞`` вместо «не существует».
    """
    # Вызывается только для T.LIMIT в конечной точке (см. solve_limit).
    try:
        left = sympy.limit(expression, symbol, point, "-")
        right = sympy.limit(expression, symbol, point, "+")
    except (TypeError, ValueError, NotImplementedError):
        raise SolveError("предел не существует или не вычисляется") from None
    if left != right:
        raise SolveError("предел не существует или не вычисляется")
    return right


@solver_for(*_LIMITS)
def solve_limit(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить предел через sympy."""
    ctx.require(len(node.children) == 2, "предел задаётся точкой и выражением")
    ctx.require(len(ctx.variables) <= 1, "поддерживается одно неизвестное")
    var = ctx.variables[0] if ctx.variables else "x"
    point, expression = node.children
    symbol = sympy.Symbol(var)
    point_value = to_sympy(point)
    expression_value = to_sympy(expression)

    if node.type is T.LIMIT and point_value not in (sympy.oo, -sympy.oo):
        value = _two_sided(expression_value, symbol, point_value)
    else:
        value = sympy.limit(expression_value, symbol, point_value, _DIRECTION[node.type])
    if not isinstance(value, sympy.Expr) or value is sympy.nan or value.has(sympy.Limit):
        raise SolveError("предел не существует или не вычисляется")

    if (
        _power_at_point(node, expression, point, var, ctx)
        or _linear_at_point(node, expression, point, var, ctx)
        or _inverse_power_at_infinity(node, expression, point, var, ctx)
        or _log_at_zero_right(node, expression, point, var, from_sympy(sympy.simplify(value)), ctx)
    ):
        return from_sympy(sympy.simplify(value))

    classification = _classification(expression_value, symbol, point_value, value, node.type, var)
    if classification is not None:
        key, classification_args = classification
        headers: list[CoreRichText] = []
        if key == "limit_solve_const":
            headers.append(CoreRichText(type="limit_solve_const_msg"))
        elif key.startswith("limit_poly_"):
            headers.append(CoreRichText(type="limit_poly_msg"))
        ctx.result.add(Step(left=node, right=None, key=key, args=classification_args), headers)

    try:
        result = from_sympy(sympy.simplify(value))
    except SolveError as err:
        # Неопределённая форма вроде AccumBounds: предела нет.
        raise SolveError("предел не существует или не вычисляется") from err
    ctx.result.add(Step(left=node, right=result, key="limit_solve"))
    return result


def _linear_at_point(
    node: CoreNode,
    expression: CoreNode,
    point: CoreNode,
    var: str,
    ctx: SolveContext,
) -> bool:
    """``lim x->a (k x + m)``: the sum law, the constant, then substitution."""
    from .equations import _simple_side

    sides = _simple_side(expression, var)
    if not (
        node.type in _LIMITS
        and sides is not None
        and point.type is T.CONSTANT
        and (point.value or "").isdigit()
        and sides[0].denominator == sides[1].denominator == 1
        and sides[0] >= 1
        and sides[1] != 0
    ):
        return False
    k, m = int(sides[0]), int(sides[1])
    num = CoreNode.node
    limit_type = node.type
    constant = CoreNode.constant(str(abs(m)))
    x_node = CoreNode.variable(var)
    left = num(limit_type, point, x_node)
    constant_limit = num(limit_type, point, constant)
    combine = T.ADD if m > 0 else T.SUBTRACT

    if k == 1:
        substituted = num(combine, point, constant)
        after_insert = num(combine, point, constant_limit)
        linear_limit = left
    else:
        substituted = num(combine, num(T.MULTIPLY, CoreNode.constant(str(k)), point), constant)
        linear_limit = num(limit_type, point, num(T.MULTIPLY, CoreNode.constant(str(k)), x_node))
        after_insert = num(
            combine, num(T.MULTIPLY, CoreNode.constant(str(k)), point), constant_limit
        )

    scaled_linear = num(T.MULTIPLY, CoreNode.constant(str(k)), left)
    split = num(combine, linear_limit, constant_limit)
    sum_law = num(
        T.EQUALS,
        num(limit_type, point, num(combine, x_node, constant)),
        num(combine, num(limit_type, point, x_node), num(limit_type, point, constant)),
    )
    detail = SolveResult()
    detail.add_group("trans_msg", Step(node, split, "using_trans", [sum_law]))
    where = num(T.EQUALS, x_node, point)
    if k == 1:
        detail.add_group(
            [
                CoreRichText(type="limit_solve_insert_value_msg", args=[where]),
                "limit_solve_const_msg",
            ],
            Step(split, after_insert, "limit_solve_insert_value", [where]),
            Step(after_insert, substituted, "limit_solve_const"),
        )
    else:
        scale_law = num(
            T.EQUALS,
            num(limit_type, point, num(T.MULTIPLY, CoreNode.constant(str(k)), x_node)),
            scaled_linear,
        )
        detail.add_group(
            ["rewrite", "limit_solve_const_msg"],
            Step(
                split,
                num(combine, scaled_linear, constant_limit),
                "using_trans",
                [scale_law],
            ),
            Step(
                num(combine, scaled_linear, constant_limit),
                num(combine, scaled_linear, constant),
                "limit_solve_const",
            ),
        )
        detail.add_group(
            CoreRichText(type="limit_solve_insert_value_msg", args=[where]),
            Step(
                num(combine, scaled_linear, constant),
                substituted,
                "limit_solve_insert_value",
                [where],
            ),
        )
    detail.set_solution(substituted)
    ctx.result.add_group("find_value", Step(node, substituted, "limit_solve", subresult=detail))
    value = _as_int(point)
    total = CoreNode.constant(str(k * value + m)) if value is not None else substituted
    if node.type is T.LIMIT:
        evaluation = SolveResult()
        route(substituted, SolveContext(result=evaluation))
        evaluation.set_solution(total)
        ctx.result.add_group(
            "calculate_short", Step(substituted, total, "calculate_direct", subresult=evaluation)
        )
    else:
        ctx.result.add_group(
            CoreRichText(type="remove_zero", args=[CoreNode.constant("0")]),
            Step(substituted, total, "add_with_zero", [CoreNode.constant("0")]),
        )
    return True


def _as_int(node: CoreNode) -> int | None:
    if node.type is not T.CONSTANT or node.value is None:
        return None
    try:
        return int(node.value)
    except ValueError:
        return None


def _inverse_power_at_infinity(
    node: CoreNode, expression: CoreNode, point: CoreNode, var: str, ctx: SolveContext
) -> bool:
    """``lim x->oo 1/x^p``: the one row quoting the law ``1/x^p -> 0``."""
    base = expression.children[1] if expression.type is T.FRACTION else None
    if not (
        node.type is T.LIMIT
        and base is not None
        and expression.children[0].type is T.CONSTANT
        and expression.children[0].value == "1"
        and (base.children[0] if base.type is T.POWER else base).value == var
        and (base.type is T.POWER or base.type is T.VARIABLE)
        and point.type is T.CONSTANT
        and (point.value or "").lstrip("+-") == "∞"
    ):
        return False
    p = CoreNode.variable("p")
    law = CoreNode.node(
        T.EQUALS,
        CoreNode.node(
            T.LIMIT,
            point,
            CoreNode.node(
                T.FRACTION,
                expression.children[0],
                CoreNode.node(T.POWER, base.children[0] if base.type is T.POWER else base, p),
            ),
        ),
        CoreNode.constant("0"),
    )
    ctx.result.header = "evaluate_of_common_function"
    ctx.result.add_group(
        "limit_common_msg", Step(node, CoreNode.constant("0"), "limit_common", [law])
    )
    return True


def _log_at_zero_right(
    node: CoreNode,
    expression: CoreNode,
    point: CoreNode,
    var: str,
    answer: CoreNode,
    ctx: SolveContext,
) -> bool:
    """``lim x->0+ ln x = -∞``: the app's one row quoting the common limit."""
    if not (
        node.type is T.LIMIT_RIGHT
        and point.type is T.CONSTANT
        and point.value == "0"
        and expression.type is T.LN
        and len(expression.children) == 1
        and expression.children[0].type is T.VARIABLE
        and expression.children[0].value == var
    ):
        return False
    law = CoreNode.node(T.EQUALS, node, answer)
    ctx.result.header = "evaluate_of_common_function"
    ctx.result.add_group("limit_common_msg", Step(node, answer, "limit_common", [law]))
    return True


def _power_at_point(
    node: CoreNode,
    expression: CoreNode,
    point: CoreNode,
    var: str,
    ctx: SolveContext,
) -> bool:
    """``lim x->a x^n`` (integer a, n >= 2), the rows: substitute, then evaluate."""
    if not (
        node.type is T.LIMIT
        and expression.type is T.POWER
        and expression.children[0].type is T.VARIABLE
        and expression.children[0].value == var
        and expression.children[1].type is T.CONSTANT
        and (expression.children[1].value or "").isdigit()
        and int(expression.children[1].value or "0") >= 2
        and point.type is T.CONSTANT
        and (point.value or "").isdigit()
    ):
        return False
    substituted = CoreNode.node(T.POWER, point, expression.children[1])
    x_node = CoreNode.variable(var)
    trans_law = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.LIMIT, point, CoreNode.node(T.POWER, x_node, CoreNode.variable("a"))),
        CoreNode.node(
            T.POWER,
            CoreNode.node(T.BRACKET, CoreNode.node(T.LIMIT, point, x_node)),
            CoreNode.variable("a"),
        ),
    )
    after_trans = CoreNode.node(
        T.POWER,
        CoreNode.node(T.BRACKET, CoreNode.node(T.LIMIT, point, x_node)),
        expression.children[1],
    )
    detail = SolveResult()
    detail.add_group("trans_msg", Step(node, after_trans, "using_trans", [trans_law]))
    where = CoreNode.node(T.EQUALS, x_node, point)
    detail.add_group(
        CoreRichText(type="limit_solve_insert_value_msg", args=[where]),
        Step(
            after_trans,
            substituted,
            "limit_solve_insert_value",
            [where],
        ),
    )
    detail.set_solution(substituted)
    ctx.result.add_group("find_value", Step(node, substituted, "limit_solve", subresult=detail))
    evaluation = SolveResult()
    route(substituted, SolveContext(result=evaluation, depth=1))
    ctx.result.add_group("find_value", *list(evaluation))
    return True


def _classification(
    expression: sympy.Expr,
    symbol: sympy.Symbol,
    point: sympy.Expr,
    value: sympy.Expr,
    node_type: T,
    variable: str,
) -> tuple[str, list[CoreNode]] | None:
    """Шаг с видом предела (константа, подстановка, многочлен, односторонний, Лопиталь)."""
    if not expression.has(symbol):
        return "limit_solve_const", []
    if _indeterminate(expression, symbol, point):
        return "limit_lhopital_long", []
    if node_type in (T.LIMIT_LEFT, T.LIMIT_RIGHT) and value.is_finite is True:
        key = "limit_common_left" if node_type is T.LIMIT_LEFT else "limit_common_right"
        return key, [
            from_sympy(expression),
            from_sympy(value),
            CoreNode.variable(variable),
            from_sympy(point),
        ]
    if point not in (sympy.oo, -sympy.oo):
        substituted = expression.subs(symbol, point)
        if substituted.is_finite is True:
            return "limit_solve_insert_value", [from_sympy(point)]
        return None
    if _is_polynomial(expression, symbol):
        return _poly_key(expression, symbol, point, value)
    return None


def _poly_key(
    expression: sympy.Expr, symbol: sympy.Symbol, point: sympy.Expr, value: sympy.Expr
) -> tuple[str, list[CoreNode]]:
    """Ключ предела многочлена на бесконечности (степень и старший коэффициент)."""
    polynomial = sympy.Poly(expression, symbol)
    leading = polynomial.LC()
    degree = polynomial.degree()
    if point is sympy.oo:
        key = "limit_poly_pos_inf_pos_lead" if leading > 0 else "limit_poly_pos_inf_neg_lead"
    else:
        even = degree % 2 == 0
        if leading > 0:
            key = "limit_poly_neg_inf_pos_lead_even" if even else "limit_poly_neg_inf_pos_lead_odd"
        else:
            key = "limit_poly_neg_inf_neg_lead_even" if even else "limit_poly_neg_inf_neg_lead_odd"
    return key, [from_sympy(point), from_sympy(value)]


def _is_polynomial(expression: sympy.Expr, symbol: sympy.Symbol) -> bool:
    """Многочлен ли выражение по переменной."""
    try:
        sympy.Poly(expression, symbol)
    except sympy.PolynomialError:
        return False
    return True


def _indeterminate(expression: sympy.Expr, symbol: sympy.Symbol, point: sympy.Expr) -> bool:
    """Есть ли неопределённость ``0/0`` или ``∞/∞`` (применимо правило Лопиталя)."""
    numerator, denominator = sympy.fraction(sympy.together(expression))
    if denominator == 1 or not denominator.has(symbol):
        return False
    try:
        top = sympy.limit(numerator, symbol, point)
        bottom = sympy.limit(denominator, symbol, point)
    except (TypeError, ValueError, NotImplementedError):
        return False
    zero_over_zero = top == 0 and bottom == 0
    infinity_over_infinity = top in (sympy.oo, -sympy.oo) and bottom in (sympy.oo, -sympy.oo)
    return bool(zero_over_zero or infinity_over_infinity)


def _is_sin_over_x_at_zero(node: CoreNode) -> bool:
    """``lim x->0 sin(x)/x``, the limit worked out by hand with two cards."""
    if node.type is not T.LIMIT or len(node.children) != 2:
        return False
    point, expression = node.children
    if not (
        point.type is T.CONSTANT
        and point.value == "0"
        and expression.type in (T.FRACTION, T.DIVIDE)
        and len(expression.children) == 2
    ):
        return False
    top, bottom = expression.children
    return (
        top.type is T.SIN
        and top.children[0].type is T.VARIABLE
        and bottom.type is T.VARIABLE
        and top.children[0].value == bottom.value
    )


def _nested(
    left: CoreNode, right: CoreNode, key: str, args: list[CoreNode] | None = None
) -> SolveResult:
    detail = SolveResult()
    detail.add_group(key, Step(left, right, key, list(args or [])))
    detail.set_solution(right)
    return detail


@method_provider(*_LIMITS)
def limit_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """Textbook method first, L'Hôpital as the alternative."""
    if _is_sin_over_x_at_zero(node):
        return _sin_over_x_cards(node)
    return cards_for(node, variables)


def _sin_over_x_cards(node: CoreNode) -> list[SolveResult]:
    """``lim sin(x)/x``: the common-limit law, and L'Hopital's rule."""
    num = CoreNode.node
    point, expression = node.children
    sine, x = expression.children
    zero, one = CoreNode.constant("0"), CoreNode.constant("1")

    def diff(part: CoreNode) -> CoreNode:
        return num(T.DERIVATION1_DIFF, x, part)

    def lim(expression_part: CoreNode) -> CoreNode:
        return num(T.LIMIT, point, expression_part)

    # card 1: the law lim sin(x)/x = 1
    law = num(T.EQUALS, node, one)
    common = SolveResult(header="evaluate_of_common_function")
    common.add_group("limit_common_msg", Step(node, one, "limit_common", [law]))
    common.set_solution(one)

    # card 2: L'Hopital's rule, with its own detail screens
    cosine = num(T.COS, x)
    d_sine, d_x = diff(sine), diff(x)
    hopital = lim(num(T.FRACTION, d_sine, d_x))
    half = lim(num(T.FRACTION, cosine, d_x))
    full = lim(num(T.FRACTION, cosine, one))
    divided = lim(cosine)
    at_zero = num(T.COS, zero)

    pl_detail = SolveResult()
    vertical = num(T.VERTICAL_LIST, lim(sine), lim(x))
    pl_detail.add_group("limit_solve_pl", Step(node, vertical, "limit_evaluate_num_den"))
    pl_detail.add_group(
        "evaluate",
        Step(vertical, num(T.VERTICAL_LIST, zero, lim(x)), "limit_solve"),
        Step(num(T.VERTICAL_LIST, zero, lim(x)), num(T.VERTICAL_LIST, zero, zero), "limit_solve"),
    )
    pl_detail.add_group(
        "try_trans",
        Step(
            num(T.VERTICAL_LIST, zero, zero),
            node,
            "limit_transform",
            [num(T.FRACTION, zero, zero)],
        ),
    )
    f, g = CoreNode.variable("f"), CoreNode.variable("g")
    hopital_law = num(
        T.EQUALS,
        lim(num(T.FRACTION, f, g)),
        lim(num(T.FRACTION, diff(f), diff(g))),
    )
    pl_detail.add_group("limit_lhopital_msg", Step(node, hopital, "limit_lhopital", [hopital_law]))
    pl_detail.set_solution(hopital)

    lhopital = SolveResult(header="evaluate_using_lhopital")
    lhopital.add_group(
        "limit_lhopital_msg",
        Step(node, hopital, "limit_lhopital_long", subresult=pl_detail),
    )
    sine_page = SolveResult()
    sine_page.add_group(
        "derive",
        Step(d_sine, cosine, "derive_table_desc", [num(T.EQUALS, d_sine, cosine)]),
    )
    sine_page.set_solution(cosine)
    x_page = SolveResult()
    x_page.add_group("derive", Step(d_x, one, "derive_var", [one]))
    x_page.set_solution(one)
    lhopital.add_group(
        "differentiate",
        Step(hopital, half, "derive", subresult=sine_page),
        Step(half, full, "derive", subresult=x_page),
    )
    lhopital.add_group("divide", Step(full, divided, "div_with_one", [one]))

    evaluate_detail = SolveResult()
    cos_law = num(T.EQUALS, lim(num(T.COS, f)), num(T.COS, lim(f)))
    after_trans = num(T.COS, lim(x))
    evaluate_detail.add_group("trans_msg", Step(divided, after_trans, "using_trans", [cos_law]))
    where = num(T.EQUALS, x, zero)
    evaluate_detail.add_group(
        CoreRichText(type="limit_solve_insert_value_msg", args=[where]),
        Step(
            after_trans,
            at_zero,
            "limit_solve_insert_value",
            [where],
        ),
    )
    evaluate_detail.set_solution(at_zero)
    lhopital.add_group("evaluate", Step(divided, at_zero, "limit_solve", subresult=evaluate_detail))
    lhopital.add_group("calculate_expressions", Step(at_zero, one, "trig_table_first"))
    lhopital.set_solution(one)
    return [common, lhopital]


__all__ = [
    "solve_limit",
]
