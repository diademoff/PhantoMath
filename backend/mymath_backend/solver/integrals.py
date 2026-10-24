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

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, SolveResult, Step, solver_for
from .book_style import book_card
from .definite_cards import (
    definite_area_card,
    definite_cards,
    row_definite_card,
    row_improper_card,
)
from .integral_cards import (
    find_substitution,
    is_linear_table,
    is_special_substitution,
    is_table,
    is_table_sum,
    textbook_card,
)
from .methods import method_provider
from .sympy_bridge import from_sympy, tidy, to_sympy


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


def _legacy_card(node: CoreNode, variables: list[str]) -> SolveResult:
    """The verified the app card (what the module produced before the lesson).

    Raised :class:`SolveError` is meaningful (a non-elementary primitive, a
    divergent integral), so it is not swallowed here.
    """
    result = SolveResult()
    local = SolveContext(result=result, variables=list(variables))
    answer = solve_integral(node, local)
    result.set_solution(answer)
    return result


def _depth(card: SolveResult) -> int:
    """Rows of a card with its nested «Подробнее» screens counted."""
    total = len(card)
    for step in card:
        if step.subresult is not None:
            total += _depth(step.subresult)
    return total


@method_provider(T.INTEGRAL, T.INTEGRAL_DEFINITE)
def integral_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """The textbook card; the verified card only where it adds steps.

    The student sees ``t = g(x)``, ``dt = g'(x)dx`` and the table formula. The
    verified card is the old card of the module, so a switcher offering both
    makes the student choose between the textbook and a worse copy of it. For an
    indefinite integral it stays only when it is a method of its own: it starts
    with the app's integration rows
    (``integrate_msg``/``integrate_msg_mul_const``/``integrate_msg_sum``) or with
    the by-parts preparation row, and is deeper than the lesson with its
    «Подробнее» screens counted — there it is the only card that shows those
    rows (``int_x2``, ``int_poly``, ``int_6x``, ``int_lin``, ``int_3x``, ``int_xsin``).
    A definite integral keeps it as the second method (``tests/corpus`` checks it),
    so its groups get real headings instead.
    """
    lessons: list[SolveResult]
    if node.type is T.INTEGRAL:
        card = textbook_card(node, variables)
        lessons = [card] if card is not None else []
    else:
        try:
            lessons = [book_card(card) for card in definite_cards(node, variables)]
        except (ValueError, TypeError, NotImplementedError, sympy.PolynomialError):
            lessons = []
    lessons = [card for card in lessons if card is not None]
    try:
        legacy = _legacy_card(node, variables)
    except SolveError:
        if not lessons:
            raise
        legacy = None
    if not lessons:
        if legacy is None:
            raise SolveError("интеграл не поддерживается")
        return [legacy]
    if legacy is None:
        return lessons
    if node.type is T.INTEGRAL_DEFINITE:
        legacy.name_groups("find_integral")
        # The app offers «find the total area» for algebraic integrands
        # (∫x, ∫x², ∫x³, ∫1/x); a trigonometric or improper integral keeps
        # only the integration card.
        area_card = None
        if len(node.children) == 3:
            body = to_sympy(node.children[2])
            symbols = sorted(body.free_symbols, key=str)
            if len(symbols) == 1 and body.is_rational_function(symbols[0]):
                area_card = definite_area_card(node, variables)
        if area_card is not None and area_card.solution is not None:
            return [*lessons, legacy, area_card]
        return [*lessons, legacy]
    # The verified card is a row card only when it is a method of its own:
    # it starts with the app's integration rows
    # (``integrate_msg``/``integrate_msg_mul_const``/``integrate_msg_sum``) or with
    # the by-parts preparation row. The generic card (``integrate``/
    # ``integrate_calc``) is a worse copy of the lesson and stays out of the switcher.
    first_step = next(iter(legacy), None)
    card_rows = first_step is not None and first_step.key in {
        "integrate_msg",
        "integrate_msg_mul_const",
        "integrate_msg_sum",
        "integrate_by_parts_prepare",
    }
    if card_rows and _depth(legacy) > _depth(lessons[0]):
        return [*lessons, legacy]
    return lessons


def _power_rule_rows(node: CoreNode, symbol: sympy.Symbol, ctx: SolveContext) -> CoreNode | None:
    """``integral x^n dx`` (integer n >= 2) in the rows.

    The power rule on a detail screen of its own, then the constant of integration.
    """
    body = node.children[-1]
    if not (
        body.type is T.POWER
        and body.children[0].type is T.VARIABLE
        and body.children[0].value == str(symbol)
        and body.children[1].type is T.CONSTANT
        and (body.children[1].value or "").isdigit()
        and int(body.children[1].value or "0") >= 2
    ):
        return None
    n = int(body.children[1].value or "0")
    num, eq = CoreNode.constant, CoreNode.node
    x = body.children[0]
    antiderivative = eq(T.FRACTION, eq(T.POWER, x, num(str(n + 1))), num(str(n + 1)))
    added = eq(T.ADD, num(str(n)), num("1"))
    unsimplified = eq(T.FRACTION, eq(T.POWER, x, added), added)
    after_exponent = eq(T.FRACTION, eq(T.POWER, x, num(str(n + 1))), added)
    letter = CoreNode.variable("n")
    rule = eq(
        T.LIST,
        eq(
            T.EQUALS,
            eq(T.INTEGRAL, eq(T.POWER, x, letter)),
            eq(
                T.FRACTION,
                eq(T.POWER, x, eq(T.ADD, letter, num("1"))),
                eq(T.ADD, letter, num("1")),
            ),
        ),
        eq(T.NOT_EQUALS, letter, eq(T.NEGATIVE, num("1"))),
    )
    detail = SolveResult()
    detail.add_group("integrate_msg", Step(node, unsimplified, "integrate_msg", [rule]))
    # «Подробнее» evaluates the exponent and the denominator separately:
    # (x^(2+1))/(2+1) → x³/(2+1) → x³/3.
    detail.add_group(
        "calculate_short",
        Step(unsimplified, after_exponent, "add"),
        Step(after_exponent, antiderivative, "add"),
    )
    detail.set_solution(antiderivative)
    ctx.result.add_group(
        "find_integral",
        Step(node, antiderivative, "integrate_msg", [rule], subresult=detail),
    )
    constant = CoreNode.variable("C")
    member = eq(T.ELEMENT_OF, constant, CoreNode.variable("ℝ"))
    answer = eq(T.LIST, eq(T.ADD, antiderivative, constant), member)
    ctx.result.add_group(
        CoreRichText(type="add_arg", args=[member]),
        Step(antiderivative, answer, "integrate_msg_addc", [member]),
    )
    return answer


def _constant_multiple_rows(
    node: CoreNode, symbol: sympy.Symbol, ctx: SolveContext
) -> CoreNode | None:
    """``integral k dx`` and ``integral k x dx`` for integers (even ``k`` in the second form).

    The rows shown: a constant becomes ``k x``; ``k x`` takes the
    constant out, integrates ``x``, simplifies, and adds the constant of integration.
    """
    body = node.children[-1]
    num, eq = CoreNode.constant, CoreNode.node
    x = CoreNode.variable(str(symbol))
    letter, member = CoreNode.variable("a"), None
    if body.type is T.CONSTANT and (body.value or "").isdigit() and body.value != "0":
        antiderivative = eq(T.MULTIPLY_IMPLICIT, body, x)
        rule = eq(
            T.EQUALS,
            eq(T.INTEGRAL, letter),
            eq(T.MULTIPLY, letter, x),
        )
        ctx.result.add_group("find_integral", Step(node, antiderivative, "integrate_msg", [rule]))
    elif (
        body.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT)
        and len(body.children) == 2
        and body.children[0].type is T.CONSTANT
        and (body.children[0].value or "").isdigit()
        and int(body.children[0].value or "0") >= 2
        and body.children[1].type is T.VARIABLE
        and body.children[1].value == str(symbol)
    ):
        k = int(body.children[0].value or "0")
        outside = eq(T.MULTIPLY, body.children[0], eq(T.INTEGRAL, x))
        f = CoreNode.variable("f")
        property_rule = eq(
            T.LIST,
            eq(
                T.EQUALS,
                eq(T.INTEGRAL, eq(T.MULTIPLY, letter, eq(T.BRACKET, f))),
                eq(T.MULTIPLY, letter, eq(T.INTEGRAL, eq(T.BRACKET, f))),
            ),
            eq(T.ELEMENT_OF, letter, CoreNode.variable("ℝ")),
        )
        ctx.result.add_group(
            "integrate_use_short", Step(node, outside, "integrate_msg_mul_const", [property_rule])
        )
        square = eq(T.FRACTION, eq(T.POWER, x, num("2")), num("2"))
        table_rule = eq(T.EQUALS, eq(T.INTEGRAL, x), square)
        integrated = eq(T.MULTIPLY, body.children[0], square)
        ctx.result.add_group(
            "find_integral", Step(outside, integrated, "integrate_msg", [table_rule])
        )
        if k % 2 == 0:
            # 6·x²/2: the factor 2 of the denominator cancels, «Упростите».
            antiderivative = eq(T.MULTIPLY_IMPLICIT, num(str(k // 2)), eq(T.POWER, x, num("2")))
            ctx.result.add_group("simplify_msg", Step(integrated, antiderivative, "simplify"))
        else:
            # 3·x²/2: the numerator is multiplied out, «Вычислите произведение».
            antiderivative = eq(
                T.FRACTION,
                eq(T.MULTIPLY_IMPLICIT, num(str(k)), eq(T.POWER, x, num("2"))),
                num("2"),
            )
            ctx.result.add_group("calculate_short", Step(integrated, antiderivative, "product"))
    else:
        return None
    constant = CoreNode.variable("C")
    member = eq(T.ELEMENT_OF, constant, CoreNode.variable("ℝ"))
    answer = eq(T.LIST, eq(T.ADD, antiderivative, constant), member)
    ctx.result.add_group(
        CoreRichText(type="add_arg", args=[member]),
        Step(antiderivative, answer, "integrate_msg_addc", [member]),
    )
    return answer


def _is_monomial(part: CoreNode, name: str) -> bool:
    """``c x^n`` with a positive integer ``c`` and ``n >= 1``."""

    def digits(item: CoreNode) -> bool:
        return item.type is T.CONSTANT and (item.value or "").isdigit() and item.value != "0"

    def power(item: CoreNode) -> bool:
        if item.type is T.VARIABLE:
            return item.value == name
        return (
            item.type is T.POWER
            and item.children[0].type is T.VARIABLE
            and item.children[0].value == name
            and digits(item.children[1])
            and int(item.children[1].value or "0") >= 2
        )

    if power(part):
        return True
    return (
        part.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT)
        and len(part.children) == 2
        and digits(part.children[0])
        and power(part.children[1])
    )


def _term_page_detail(term: CoreNode, symbol: sympy.Symbol) -> SolveResult:
    """The «Подробнее» screen of one term inside an integral of a sum.

    the app: ``∫3x² → 3∫x² → 3·(x³/3) → x³`` — the constant falls
    out, the table rule applies, the product is simplified.
    """
    eq = CoreNode.node
    coefficient, body = None, term
    if (
        term.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT)
        and len(term.children) == 2
        and term.children[0].type is T.CONSTANT
        and (term.children[0].value or "").isdigit()
    ):
        coefficient, body = term.children[0], term.children[1]
    primitive_expr = sympy.integrate(to_sympy(body), symbol)
    primitive = from_sympy(primitive_expr)
    detail = SolveResult()
    if coefficient is not None and int(coefficient.value or "0") >= 2:
        k = int(coefficient.value or "0")
        letter, f = CoreNode.variable("a"), CoreNode.variable("f")
        property_rule = eq(
            T.LIST,
            eq(
                T.EQUALS,
                eq(T.INTEGRAL, eq(T.MULTIPLY, letter, eq(T.BRACKET, f))),
                eq(T.MULTIPLY, letter, eq(T.INTEGRAL, eq(T.BRACKET, f))),
            ),
            eq(T.ELEMENT_OF, letter, CoreNode.variable("ℝ")),
        )
        outside = eq(T.MULTIPLY, coefficient, eq(T.INTEGRAL, body))
        detail.add_group(
            "integrate_use_short",
            Step(eq(T.INTEGRAL, term), outside, "integrate_msg_mul_const", [property_rule]),
        )
        table_rule = eq(T.EQUALS, eq(T.INTEGRAL, body), primitive)
        product = eq(T.MULTIPLY, coefficient, primitive)
        detail.add_group("find_integral", Step(outside, product, "integrate_msg", [table_rule]))
        answer = from_sympy(k * primitive_expr)
        detail.add_group("simplify_msg", Step(product, answer, "simplify"))
        detail.set_solution(answer)
        return detail
    rule = eq(T.EQUALS, eq(T.INTEGRAL, body), primitive)
    detail.add_group(
        "integrate_msg", Step(eq(T.INTEGRAL, body), primitive, "integrate_msg", [rule])
    )
    detail.set_solution(primitive)
    return detail


def _monomial_sum_rows(node: CoreNode, symbol: sympy.Symbol, ctx: SolveContext) -> CoreNode | None:
    """``integral (c1 x^n1 + c2 x^n2 + ...) dx`` in the rows.

    The sum property, one page per term, then the constant of integration.
    """
    body = node.children[-1]
    if not (
        body.type is T.ADD
        and len(body.children) >= 2
        and all(
            _is_monomial(term, str(symbol))
            or (term.type is T.CONSTANT and (term.value or "").isdigit() and term.value != "0")
            for term in body.children
        )
        and any(_is_monomial(term, str(symbol)) for term in body.children)
    ):
        return None
    eq = CoreNode.node
    f, g = CoreNode.variable("f(x)"), CoreNode.variable("g(x)")

    def integral(inner: CoreNode) -> CoreNode:
        return eq(T.INTEGRAL, inner)

    def chain(parts: list[CoreNode]) -> CoreNode:
        out = parts[0]
        for part in parts[1:]:
            out = eq(T.ADD, out, part)
        return out

    rule = eq(
        T.EQUALS,
        integral(eq(T.ADD, f, g)),
        eq(T.ADD, integral(f), integral(g)),
    )
    split = chain([integral(term) for term in body.children])
    ctx.result.add_group("integrate_use_short", Step(node, split, "integrate_msg_sum", [rule]))
    antiderivatives = [
        from_sympy(sympy.integrate(to_sympy(term), symbol)) for term in body.children
    ]
    pages, current = [], split
    for index, term in enumerate(body.children):
        following = chain(
            antiderivatives[: index + 1] + [integral(t) for t in body.children[index + 1 :]]
        )
        if term.type is T.CONSTANT:  # a constant is integrated by the table rule on the page itself
            rule_a = eq(
                T.EQUALS,
                eq(T.INTEGRAL, CoreNode.variable("a")),
                eq(T.MULTIPLY, CoreNode.variable("a"), CoreNode.variable(str(symbol))),
            )
            pages.append(Step(current, following, "integrate_msg", [rule_a]))
            current = following
            continue
        detail = _term_page_detail(term, symbol)
        pages.append(Step(current, following, "integrate", subresult=detail))
        current = following
    ctx.result.add_group("integrate_calc_plural", *pages)
    total = chain(antiderivatives)
    constant = CoreNode.variable("C")
    member = eq(T.ELEMENT_OF, constant, CoreNode.variable("ℝ"))
    answer = eq(T.LIST, eq(T.ADD, total, constant), member)
    ctx.result.add_group(
        CoreRichText(type="add_arg", args=[member]),
        Step(total, answer, "integrate_msg_addc", [member]),
    )
    return answer


def _table_rows(node: CoreNode, symbol: sympy.Symbol, ctx: SolveContext) -> CoreNode | None:
    """``integral sin x dx`` / ``cos x dx``: one table step, then the constant."""
    body = node.children[-1]
    if not (
        body.type in (T.SIN, T.COS)
        and body.children[0].type is T.VARIABLE
        and body.children[0].value == str(symbol)
    ):
        return None
    eq = CoreNode.node
    antiderivative = from_sympy(sympy.integrate(to_sympy(body), symbol))
    rule = eq(T.EQUALS, node, antiderivative)
    ctx.result.add_group("find_integral", Step(node, antiderivative, "integrate_msg", [rule]))
    member = eq(T.ELEMENT_OF, CoreNode.variable("C"), CoreNode.variable("ℝ"))
    answer = eq(T.LIST, eq(T.ADD, antiderivative, CoreNode.variable("C")), member)
    ctx.result.add_group(
        CoreRichText(type="add_arg", args=[member]),
        Step(antiderivative, answer, "integrate_msg_addc", [member]),
    )
    return answer


def _by_parts_rows(node: CoreNode, symbol: sympy.Symbol, ctx: SolveContext) -> CoreNode | None:
    """``integral x f(x) dx`` for ``f`` in sin, cos, e^x: the app's six by-parts rows."""
    body = node.children[-1]
    x = CoreNode.variable(str(symbol))
    if body.type not in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) or len(body.children) != 2:
        return None
    if not body.children[0].structural_eq(x):
        return None
    f = body.children[1]
    eq = CoreNode.node
    one = CoreNode.constant("1")
    if f.type in (T.SIN, T.COS) and f.children[0].structural_eq(x):
        table = {T.SIN: (eq(T.COS, x), True), T.COS: (eq(T.SIN, x), False)}
        v, negative = table[f.type]
    elif f.type is T.EXP and f.children[0].structural_eq(x):
        v, negative = f, False
    else:
        return None

    def integral(part: CoreNode) -> CoreNode:
        return eq(T.INTEGRAL, part)

    u_eq, dv_eq = eq(T.EQUALS, CoreNode.variable("u"), x), eq(T.EQUALS, CoreNode.variable("dv"), f)
    # A fact, not a transformation: the stage's content is u and dv, and
    # ``∫f dx → ∫f dx`` would show the student no change at all.
    ctx.result.add_group(
        "integrate_by_parts_prepare",
        Step(node, None, "integrate_by_parts_prepare", [u_eq, dv_eq]),
    )
    du_eq = eq(T.EQUALS, CoreNode.variable("du"), one)
    v_eq = eq(T.EQUALS, CoreNode.variable("v"), eq(T.NEGATIVE, v) if negative else v)
    du_detail, v_detail = SolveResult(), SolveResult()
    # «Вычислите дифференциал»: the rule is not repeated in the sentence, the
    # stage below already shows u = x → du = 1.
    du_detail.add_group("derive", Step(u_eq, du_eq, "integrate_calc_diff"))
    du_detail.set_solution(du_eq)
    v_detail.add_group("integrate", Step(integral(f), v_eq, "integrate"))
    v_detail.set_solution(v_eq)
    ctx.result.add_group(
        ["integrate_parts_differential", "integrate_parts_integral"],
        Step(node, None, "integrate_parts_differential", [du_eq], subresult=du_detail),
        Step(node, None, "integrate_parts_integral", [v_eq], subresult=v_detail),
    )
    v_shown = eq(T.BRACKET, eq(T.NEGATIVE, v)) if negative else v
    # The integral node draws ``d`` + one free variable, so ∫u dv cannot be a
    # node: it would read ∫u du. The formula is plain text instead.
    parts_formula = CoreNode(type=T.TEXT, value="∫u dv = uv − ∫v du")
    substituted = eq(T.SUBTRACT, eq(T.MULTIPLY, x, v_shown), integral(eq(T.MULTIPLY, one, v_shown)))
    ctx.result.add_group(
        "integrate_parts_sub",
        Step(node, substituted, "integrate_parts_sub", [u_eq, v_eq, du_eq, dv_eq, parts_formula]),
    )
    first = eq(T.MULTIPLY_IMPLICIT, x, v)
    if negative:
        simplified = eq(T.SUBTRACT, eq(T.NEGATIVE, first), integral(eq(T.NEGATIVE, v)))
        extracted = eq(T.ADD, eq(T.NEGATIVE, first), integral(v))
        stages = [
            Step(substituted, simplified, "simplify"),
            Step(
                simplified,
                extracted,
                "integrate_msg_extract_min",
                [
                    eq(
                        T.EQUALS,
                        integral(eq(T.NEGATIVE, CoreNode.variable("f"))),
                        eq(T.NEGATIVE, integral(CoreNode.variable("f"))),
                    )
                ],
            ),
        ]
    else:
        extracted = eq(T.SUBTRACT, first, integral(v))
        stages = [Step(substituted, extracted, "simplify")]
    ctx.result.add_group(["simplify_msg", "integrate_msg_extract_min"][: len(stages)], *stages)
    antiderivative = from_sympy(sympy.integrate(to_sympy(body), symbol))
    rule = eq(T.EQUALS, integral(v), from_sympy(sympy.integrate(to_sympy(v), symbol)))
    ctx.result.add_group("find_integral", Step(extracted, antiderivative, "integrate_msg", [rule]))
    member = eq(T.ELEMENT_OF, CoreNode.variable("C"), CoreNode.variable("ℝ"))
    answer = eq(T.LIST, eq(T.ADD, antiderivative, CoreNode.variable("C")), member)
    ctx.result.add_group(
        CoreRichText(type="add_arg", args=[member]),
        Step(antiderivative, answer, "integrate_msg_addc", [member]),
    )
    return answer


def _indefinite_integral(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Неопределённый интеграл: первообразная."""
    symbol = _variable(ctx)
    ctx.require(len(node.children) >= 1, "интеграл без подынтегрального выражения")
    if (power := _power_rule_rows(node, symbol, ctx)) is not None:
        return power
    if (constant := _constant_multiple_rows(node, symbol, ctx)) is not None:
        return constant
    if (total := _monomial_sum_rows(node, symbol, ctx)) is not None:
        return total
    if (table := _table_rows(node, symbol, ctx)) is not None:
        return table
    if (parts := _by_parts_rows(node, symbol, ctx)) is not None:
        return parts
    expression = to_sympy(node.children[-1])
    ctx.result.add(Step(left=node, right=None, key="integrate"))
    method_key = _integral_method(expression, symbol)
    antiderivative = sympy.integrate(expression, symbol)
    if antiderivative.has(sympy.Integral):
        antiderivative = _abs_antiderivative(expression, symbol)
    if antiderivative.has(sympy.Integral):
        raise SolveError("первообразная не выражается через элементарные функции")
    try:
        result = tidy(_with_abs_logs(antiderivative, symbol))
    except SolveError as err:
        # sympy вернул специальную функцию (erfi, Ei, …): элементарной
        # первообразной нет, и в наш AST это не переводится.
        raise SolveError("первообразная не выражается через элементарные функции") from err
    _prepare_step(node, ctx, method_key)
    if method_key is not None:
        ctx.result.add(Step(left=node, right=None, key=method_key))
    ctx.result.add(Step(left=node, right=result, key="integrate_calc"))
    constant = CoreNode.variable("C")
    member = CoreNode.node(T.ELEMENT_OF, constant, CoreNode.variable("ℝ"))
    answer = CoreNode.node(T.LIST, CoreNode.node(T.ADD, result, constant), member)
    ctx.result.add_group(
        CoreRichText(type="add_arg", args=[member]),
        Step(left=result, right=answer, key="integrate_msg_addc", args=[member]),
    )
    return answer


def _abs_antiderivative(expression: sympy.Expr, symbol: sympy.Symbol) -> sympy.Expr:
    """``integral |u| dx = u |u| / (2 u')`` for a linear ``u``; anything else is left to sympy."""
    if isinstance(expression, sympy.Abs):
        inner = expression.args[0]
        if inner.is_polynomial(symbol) and sympy.degree(inner, symbol) == 1:
            slope = sympy.diff(inner, symbol)
            return inner * sympy.Abs(inner) / (2 * slope)
    return sympy.Integral(expression, symbol)


def _with_abs_logs(expression: sympy.Expr, symbol: sympy.Symbol) -> sympy.Expr:
    """Wrap the argument of ``ln`` in ``|.|`` unless it is provably positive.

    ``1/x`` integrates to ``ln|x|``, ``tg x`` to ``−ln|cos x|`` and ``1/sin x``
    to ``ln|tg(x/2)|``; ``1 + x²`` and ``eˣ`` are positive for every real ``x``,
    so their logarithms keep the plain argument.
    """

    def wrap(argument: sympy.Expr) -> sympy.Expr:
        if argument.is_positive is True:
            return sympy.log(argument)
        try:
            positive = sympy.ask(sympy.Q.positive(argument), sympy.Q.real(symbol))
        except (TypeError, ValueError):
            positive = None
        if positive is True:
            return sympy.log(argument)
        if argument.is_real is False:
            return sympy.log(argument)
        return sympy.log(sympy.Abs(argument))

    return expression.replace(sympy.log, wrap)


def _prepare_step(node: CoreNode, ctx: SolveContext, method_key: str | None) -> None:
    """Подготовительный шаг перед методом интегрирования."""
    if method_key == "integrate_partial":
        ctx.result.add(Step(left=node, right=None, key="integrate_by_parts_prepare_simple"))
    elif method_key == "integrate_using_substitution":
        ctx.result.add(Step(left=node, right=None, key="integrate_differential_sub"))


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
    if improper:
        try:
            value = sympy.integrate(expression, (symbol, lower_value, upper_value))
        except (TypeError, ValueError, NotImplementedError) as error:
            raise SolveError("определённый интеграл не вычисляется") from error
        if value.has(sympy.Integral):
            raise SolveError("определённый интеграл не вычисляется")
        if _diverges(value):
            ctx.result.add(Step(left=node, right=None, key="integrate_imp_evaluate"))
            ctx.result.add(Step(left=node, right=None, key="integrate_imp_diverges_simple"))
            raise SolveError("несобственный интеграл расходится", "integrate_imp_diverges_simple")
        singular = discontinuous[0] if discontinuous else None
        card = row_improper_card(node, ctx.variables, singular)
        if card is not None and card.solution is not None:
            ctx.result.extend(card)
            return card.solution
        ctx.result.add(Step(left=node, right=None, key="integrate_imp_evaluate"))
        result = from_sympy(sympy.simplify(value))
        ctx.result.add(Step(left=node, right=None, key="integrate_def_bounds"))
        ctx.result.add(Step(left=node, right=result, key="integrate_calc"))
        return result
    try:
        value = sympy.integrate(expression, (symbol, lower_value, upper_value))
    except (TypeError, ValueError, NotImplementedError) as error:
        raise SolveError("определённый интеграл не вычисляется") from error
    if value.has(sympy.Integral):
        raise SolveError("определённый интеграл не вычисляется")
    if _diverges(value):
        raise SolveError("определённый интеграл не вычисляется")
    card = row_definite_card(node, ctx.variables)
    if card is not None and card.solution is not None:
        ctx.result.extend(card)
        return card.solution
    result = from_sympy(sympy.simplify(value))
    ctx.result.add(Step(left=node, right=None, key="integrate_def_rewrite"))
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
    inner_result = from_sympy(sympy.simplify(inner_value))
    inner_card = row_definite_card(inner, ctx.variables, variable=inner_var)
    ctx.result.add_group(
        "integrate_iterated_inner_smpl",
        Step(node, inner_result, "integrate_iterated_inner", subresult=inner_card),
    )
    outer = CoreNode.node(T.INTEGRAL_DEFINITE, outer_lower, outer_upper, inner_result)
    value = sympy.integrate(inner_value, (outer_var, to_sympy(outer_lower), to_sympy(outer_upper)))
    if _diverges(value) or value.has(sympy.Integral):
        raise SolveError("повторный интеграл не вычисляется")
    result = from_sympy(sympy.simplify(value))
    outer_card = row_definite_card(outer, ctx.variables, variable=outer_var)
    ctx.result.add_group(
        "integrate_calc",
        Step(outer, result, "integrate_def", subresult=outer_card),
    )
    return result


@solver_for(T.INTEGRAL_RIGHT_DASH)
def solve_right_dash(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Подстановка пределов в записи ``F(x)|ₐᵇ``.

    Дети — ``[выражение, нижний предел, верхний предел]`` (рисуется
    вертикальная черта с пределами). Значение — разность
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
    """The textbook method, checked in Demidovich's order.

    1. a table entry (no method step), also with a linear argument ``kx+b``;
    2. linearity of a sum of table entries;
    3. substitution where ``f'(g(x))`` is present as a factor;
    4. integration by parts;
    5. partial fractions.
    """
    if is_table(expression, symbol):
        if is_linear_table(expression, symbol):
            return "integrate_using_substitution"
        return None
    if is_table_sum(expression, symbol):
        return "integrate_use_short"
    if (
        expression == sympy.tan(symbol)
        or is_special_substitution(expression, symbol)
        or find_substitution(expression, symbol)
    ):
        return "integrate_using_substitution"
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

    card = definite_area_card(node, ctx.variables)
    if card is not None and card.solution is not None:
        if ctx.result.header is None:
            ctx.result.header = card.header
        ctx.result.extend(card)
        return card.solution
    ctx.result.add(Step(left=node, right=None, key="total_area_fun"))
    ctx.result.add(
        Step(
            left=node,
            right=None,
            key="total_area_x_intercept",
            args=[CoreNode.variable(str(symbol))],
        )
    )
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
