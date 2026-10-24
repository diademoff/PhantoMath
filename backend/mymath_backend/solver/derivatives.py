"""Производная функции одной переменной.

Модуль зарегистрирован на узлы ``DERIVATION`` и ``DERIVATION1`` (``d/dx`` от
подвыражения). Дифференцирование идёт по правилам над деревом ``CoreNode``,
с локальным упрощением: константы складываются, ``1`` и ``0`` не пишутся,
поэтому производная многочлена выходит сразу в чистом виде:

* сумма/разность -- почленно;
* произведение -- по правилу произведения;
* частное -- по правилу частного;
* степень, ``√``, ``sin``, ``cos``, ``tan``, ``ln``, ``e^u``, ``log`` --
  по таблице с правилом цепочки.

Карточка студента — учебная (``teaching_calculus.derivative_card``): каждая
стадия называет одно правило с его формулой, а производная каждой части
открывается вложенным «Подробнее». Для ``d/dx`` из паритета сохранена и
прежняя карточка — она остаётся альтернативой. Типы, которых нет в
таблице, отклоняются: это следующие модули.
"""

from __future__ import annotations

from collections.abc import Callable
from fractions import Fraction

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .arithmetic import format_number
from .base import SolveContext, SolveError, SolveResult, Step, solver_for
from .methods import method_provider
from .sympy_bridge import from_sympy, tidy, to_sympy

_HEADER = CoreRichText(type="derive_short")


def _const(value: Fraction) -> CoreNode:
    return CoreNode.constant(format_number(value))


def _as_number(node: CoreNode) -> Fraction | None:
    """Число узла, если это числовая константа (``π`` не число)."""
    if node.type is not T.CONSTANT or node.value is None:
        return None
    try:
        return Fraction(node.value.strip())
    except ValueError:
        return None


def _is_const(node: CoreNode, value: Fraction | None = None) -> bool:
    number = _as_number(node)
    if number is None:
        return False
    return value is None or number == value


def _add(left: CoreNode, right: CoreNode) -> CoreNode:
    if _is_const(left, Fraction(0)):
        return right
    if _is_const(right, Fraction(0)):
        return left
    a, b = _as_number(left), _as_number(right)
    if a is not None and b is not None:
        return _const(a + b)
    return CoreNode(type=T.ADD, children=[left, right])


def _sub(left: CoreNode, right: CoreNode) -> CoreNode:
    if _is_const(right, Fraction(0)):
        return left
    if _is_const(left, Fraction(0)):
        return _neg(right)
    a, b = _as_number(left), _as_number(right)
    if a is not None and b is not None:
        return _const(a - b)
    return CoreNode(type=T.SUBTRACT, children=[left, right])


def _neg(node: CoreNode) -> CoreNode:
    if node.type is T.NEGATIVE and len(node.children) == 1:
        return node.children[0]
    number = _as_number(node)
    if number is not None:
        return _const(-number)
    return CoreNode(type=T.NEGATIVE, children=[node])


def _scale_left(coefficient: Fraction, node: CoreNode) -> CoreNode:
    """Умножить выражение на константу, сложив её с ведущим множителем.

    ``3·(2x)`` даёт ``6x``, а не ``3·2·x``: так производная многочлена
    выходит в чистом виде.
    """
    if node.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) and node.children:
        leading = _as_number(node.children[0])
        if leading is not None:
            rest = list(node.children[1:])
            if not rest:
                return _const(coefficient * leading)
            inner = rest[0] if len(rest) == 1 else CoreNode(type=node.type, children=rest)
            return CoreNode(
                type=node.type,
                children=[_const(coefficient * leading), inner],
            )
    return CoreNode(type=T.MULTIPLY_IMPLICIT, children=[_const(coefficient), node])


def _mul(left: CoreNode, right: CoreNode) -> CoreNode:
    if _is_const(left, Fraction(0)) or _is_const(right, Fraction(0)):
        return _const(Fraction(0))
    if _is_const(left, Fraction(1)):
        return right
    if _is_const(right, Fraction(1)):
        return left
    a, b = _as_number(left), _as_number(right)
    if a is not None and b is not None:
        return _const(a * b)
    if a is not None:
        return _neg(right) if a == -1 else _scale_left(a, right)
    if b is not None:
        return _neg(left) if b == -1 else _scale_left(b, left)
    return CoreNode(type=T.MULTIPLY, children=[left, right])


def _div(left: CoreNode, right: CoreNode) -> CoreNode:
    if _is_const(left, Fraction(0)):
        return _const(Fraction(0))
    if _is_const(right, Fraction(1)):
        return left
    a, b = _as_number(left), _as_number(right)
    if a is not None and b is not None and b != 0:
        return _const(a / b)
    return CoreNode(type=T.FRACTION, children=[left, right])


def _int_exponent(node: CoreNode) -> int | None:
    number = _as_number(node)
    if number is None or number.denominator != 1:
        return None
    return number.numerator


def _pow(base: CoreNode, exponent: CoreNode) -> CoreNode:
    if _is_const(exponent, Fraction(0)):
        return _const(Fraction(1))
    if _is_const(exponent, Fraction(1)):
        return base
    a, b = _as_number(base), _as_number(exponent)
    if a is not None and b is not None and b.denominator == 1 and abs(b) <= 64:
        if a == 0 and b.numerator < 0:
            raise SolveError("ноль в отрицательной степени")
        return _const(a**b.numerator)
    return CoreNode(type=T.POWER, children=[base, exponent])


def _chain(outer: CoreNode, inner: CoreNode, ctx: SolveContext) -> CoreNode:
    """Правило цепочки: ``outer(u)`` -> ``outer'(u) · u'``."""
    return _mul(outer, _diff(inner, ctx))


def _diff(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Производная узла по переменной ``ctx.variables[0]``."""
    var = ctx.variables[0] if ctx.variables else "x"
    node_type = node.type

    if node_type is T.CONSTANT:
        return _const(Fraction(0))
    if node_type is T.VARIABLE:
        return _const(Fraction(1) if node.value == var else Fraction(0))
    if node_type is T.NEGATIVE:
        return _neg(_diff(node.children[0], ctx))
    if node_type in (T.POSITIVE, T.BRACKET):
        return _diff(node.children[0], ctx)

    if node_type is T.ADD:
        return _sum([_diff(child, ctx) for child in node.children], subtract=False)
    if node_type is T.SUBTRACT:
        return _sum([_diff(child, ctx) for child in node.children], subtract=True)
    if node_type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT):
        return _product_rule(node.children, ctx)
    if node_type in (T.DIVIDE, T.FRACTION):
        return _quotient_rule(node.children[0], node.children[1], ctx)
    if node_type is T.POWER:
        return _power_rule(node.children[0], node.children[1], ctx)
    if node_type in (T.ROOT2, T.ROOT):
        radicand = node.children[-1]
        outer = _div(_const(Fraction(1)), _mul(_const(Fraction(2)), _sqrt(radicand)))
        return _chain(outer, radicand, ctx)

    return _function_rule(node, ctx)


def _sum(terms: list[CoreNode], *, subtract: bool) -> CoreNode:
    result = terms[0] if terms else _const(Fraction(0))
    for term in terms[1:]:
        result = _sub(result, term) if subtract else _add(result, term)
    return result


def _sqrt(radicand: CoreNode) -> CoreNode:
    return CoreNode(type=T.ROOT2, children=[radicand])


def _product_rule(factors: list[CoreNode], ctx: SolveContext) -> CoreNode:
    """Производная произведения: сумма по одному дифференцируемому множителю."""
    total: CoreNode | None = None
    for index, factor in enumerate(factors):
        term = _diff(factor, ctx)
        for other_index, other in enumerate(factors):
            if other_index != index:
                term = _mul(term, other)
        total = term if total is None else _add(total, term)
    return total if total is not None else _const(Fraction(0))


def _quotient_rule(numerator: CoreNode, denominator: CoreNode, ctx: SolveContext) -> CoreNode:
    top = _sub(
        _mul(_diff(numerator, ctx), denominator),
        _mul(numerator, _diff(denominator, ctx)),
    )
    return _div(top, _pow(denominator, _const(Fraction(2))))


def _power_rule(base: CoreNode, exponent: CoreNode, ctx: SolveContext) -> CoreNode:
    power = _int_exponent(exponent)
    if power is not None:
        # (u^n)' = n · u^(n-1) · u'
        outer = _mul(_const(Fraction(power)), _pow(base, _const(Fraction(power - 1))))
        return _mul(outer, _diff(base, ctx))
    if _is_const(base):
        # (a^u)' = a^u · ln(a) · u'
        outer = _mul(CoreNode(type=T.POWER, children=[base, exponent]), _ln(base))
        return _mul(outer, _diff(exponent, ctx))
    raise SolveError("производная степени с переменными основанием и показателем не поддерживается")


def _ln(argument: CoreNode) -> CoreNode:
    return CoreNode(type=T.LN, children=[argument])


def _function_rule(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Производные функций: таблица внешней производной и правило цепочки."""
    argument = node.children[0] if node.children else CoreNode.empty()

    def outer() -> CoreNode | None:
        match node.type:
            case T.SIN:
                return CoreNode.node(T.COS, argument)
            case T.COS:
                return _neg(CoreNode.node(T.SIN, argument))
            case T.TAN:
                return _div(
                    _const(Fraction(1)), _pow(CoreNode.node(T.COS, argument), _const(Fraction(2)))
                )
            case T.COT:
                return _neg(
                    _div(
                        _const(Fraction(1)),
                        _pow(CoreNode.node(T.SIN, argument), _const(Fraction(2))),
                    )
                )
            case T.SINH:
                return CoreNode.node(T.COSH, argument)
            case T.COSH:
                return CoreNode.node(T.SINH, argument)
            case T.TANH:
                return _div(
                    _const(Fraction(1)), _pow(CoreNode.node(T.COSH, argument), _const(Fraction(2)))
                )
            case T.LN:
                return _div(_const(Fraction(1)), argument)
            case T.EXP:
                return CoreNode.node(T.EXP, argument)
            case T.LOG10:
                return _div(_const(Fraction(1)), _mul(argument, _ln(CoreNode.constant("10"))))
            case T.LOG:
                base = node.children[1] if len(node.children) > 1 else CoreNode.constant("10")
                return _div(_const(Fraction(1)), _mul(argument, _ln(base)))
            case _:
                return None

    derived = outer()
    if derived is None:
        raise SolveError(f"производная узла {node.type} не поддерживается")
    return _mul(derived, _diff(argument, ctx))


@solver_for(T.DERIVATION, T.DERIVATION1)
def solve_derivative(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Взять производную подвыражения.

    Переменная — единственная свободная переменная выражения, иначе ``x``.
    Сначала пробуем собственные правила (они дают аккуратную запись для
    многочленов), а для того, что таблица не знает, зовём sympy.
    """
    ctx.require(len(node.children) == 1, "производная берёт одно выражение")
    expression = node.children[0]
    try:
        result = _diff(expression, ctx)
    except SolveError:
        result = _sympy_derivative(expression, ctx)

    var = ctx.variables[0] if ctx.variables else "x"
    x = CoreNode.variable(var)
    diff_node = CoreNode.node(T.DERIVATION1_DIFF, x, expression)
    if _leibniz_rows(diff_node, x, expression, result, ctx):
        return _collected(result, ctx)

    rule = _rule_step(node, expression, result)
    if rule is not None:
        ctx.result.add(rule, [_HEADER])
    ctx.result.add(
        Step(
            left=node,
            right=result,
            key="find_derivative",
            subresult=_derivative_detail(expression, ctx),
        ),
        [_HEADER],
    )
    return _collected(result, ctx)


def _shortest(result: CoreNode) -> CoreNode:
    try:
        return tidy(to_sympy(result))
    except SolveError:
        return result


def _collected(result: CoreNode, ctx: SolveContext) -> CoreNode:
    """The derivative in its shortest form; a ``simplify`` row records the change."""
    try:
        simple = tidy(to_sympy(result))
    except SolveError:
        return result
    before = sum(1 for n in result.walk() if n.type in _COUNTED)
    after = sum(1 for n in simple.walk() if n.type in _COUNTED)
    if after >= before:
        return result
    ctx.result.add_group("simplify_msg", Step(left=result, right=simple, key="simplify"))
    return simple


_COUNTED = frozenset(
    {T.ADD, T.SUBTRACT, T.MULTIPLY, T.MULTIPLY_IMPLICIT, T.DIVIDE, T.FRACTION, T.POWER, T.NEGATIVE}
)


def _derivative_detail(expression: CoreNode, ctx: SolveContext) -> SolveResult | None:
    """Почленные производные — раскрываемое пояснение для суммы и произведения.

    Для ``(u ± v)'`` и ``(u·v)'`` правило применяется покомпонентно, поэтому
    под шагом видно производную каждого слагаемого/множителя отдельно.
    """
    if expression.type not in (T.ADD, T.SUBTRACT, T.MULTIPLY, T.MULTIPLY_IMPLICIT):
        return None
    if len(expression.children) < 2:
        return None
    detail = SolveResult()
    detail_ctx = SolveContext(result=detail, variables=list(ctx.variables))
    for child in expression.children:
        try:
            derived = _diff(child, detail_ctx)
        except SolveError:
            try:
                derived = _sympy_derivative(child, detail_ctx)
            except SolveError:
                continue
        detail_ctx.step(CoreNode.node(T.DERIVATION1, child), derived, "find_derivative")
    return detail if detail else None


def _rule_step(node: CoreNode, expression: CoreNode, result: CoreNode) -> Step | None:
    """Шаг с названием правила дифференцирования по верхнему узлу."""
    node_type = expression.type
    if node_type is T.CONSTANT:
        return Step(left=node, right=None, key="derive_const", args=[result])
    if node_type is T.VARIABLE:
        return Step(left=node, right=None, key="derive_var", args=[result])
    if node_type in (T.ADD, T.SUBTRACT):
        return Step(left=node, right=None, key="derive_sum")
    if node_type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT):
        return Step(left=node, right=None, key="derive_prod")
    if node_type in (T.DIVIDE, T.FRACTION):
        return Step(left=node, right=None, key="derive_quot")
    argument = expression.children[0] if expression.children else None
    if argument is not None and argument.type is not T.VARIABLE:
        return Step(left=node, right=None, key="derive_chain", args=[argument])
    return None


@solver_for(T.DERIVATION1_DIFF)
def solve_derivative_with_respect(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Производная по явно указанной переменной (запись Лейбница ``d/dx``).

    Узел ``DERIVATION1_DIFF`` хранит детей в порядке ``[переменная, выражение]``
    (рисуется ``d(выражение)/d(переменная)``).
    """
    ctx.require(len(node.children) == 2, "d/dx: переменная и выражение")
    variable_node, expression_node = node.children
    if variable_node.type is not T.VARIABLE or not variable_node.value:
        raise SolveError("дифференцирование возможно только по переменной")
    local = SolveContext(result=ctx.result, variables=[variable_node.value])
    try:
        result = _diff(expression_node, local)
    except SolveError:
        result = _sympy_derivative(expression_node, local)
    if _quotient_parts(expression_node, variable_node) is not None:
        result = _shortest(result)
    if _leibniz_rows(node, variable_node, expression_node, result, ctx):
        return result
    ctx.result.add(
        Step(
            left=node,
            right=result,
            key="find_derivative_with_respect",
            args=[variable_node],
        ),
        [_HEADER],
    )
    return _collected(result, ctx)


def _monomial(node: CoreNode, var: str) -> tuple[int, int] | None:
    """``(c, n)`` for ``c x^n`` with a positive integer ``c`` and ``n >= 1``, else ``None``."""

    def integer(part: CoreNode) -> int | None:
        value = _as_number(part)
        return int(value) if value is not None and value.denominator == 1 and value > 0 else None

    def power(part: CoreNode) -> int | None:
        if part.type is T.VARIABLE and part.value == var:
            return 1
        if (
            part.type is T.POWER
            and part.children[0].type is T.VARIABLE
            and part.children[0].value == var
        ):
            n = integer(part.children[1])
            return n if n is not None and n >= 2 else None
        return None

    if (n := power(node)) is not None:
        return 1, n
    if node.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) and len(node.children) == 2:
        c, n = integer(node.children[0]), power(node.children[1])
        if c is not None and n is not None:
            return c, n
    return None


def _power_node(x: CoreNode, n: int) -> CoreNode:
    """``x`` for the first power, ``x^n`` otherwise."""
    return x if n == 1 else CoreNode.node(T.POWER, x, _const(Fraction(n)))


def _law_sum(diff: Callable[[CoreNode], CoreNode]) -> CoreNode:
    num = CoreNode.node
    f, g = CoreNode.variable("f"), CoreNode.variable("g")
    return num(T.EQUALS, diff(num(T.ADD, f, g)), num(T.ADD, diff(f), diff(g)))


def _law_scale(diff: Callable[[CoreNode], CoreNode]) -> CoreNode:
    num = CoreNode.node
    a, f = CoreNode.variable("a"), CoreNode.variable("f")
    return num(T.EQUALS, diff(num(T.MULTIPLY, a, f)), num(T.MULTIPLY, a, diff(f)))


def _law_linear(diff: Callable[[CoreNode], CoreNode], x: CoreNode) -> CoreNode:
    num = CoreNode.node
    a = CoreNode.variable("a")
    return num(T.EQUALS, diff(num(T.MULTIPLY, a, x)), a)


def _law_power(diff: Callable[[CoreNode], CoreNode], x: CoreNode) -> CoreNode:
    num = CoreNode.node
    n = CoreNode.variable("n")
    return num(
        T.EQUALS,
        diff(num(T.POWER, x, n)),
        num(T.MULTIPLY, n, num(T.POWER, x, num(T.SUBTRACT, n, _const(Fraction(1))))),
    )


def _law_table(
    diff: Callable[[CoreNode], CoreNode], expression: CoreNode, value: CoreNode
) -> CoreNode:
    return CoreNode.node(T.EQUALS, diff(expression), value)


def _monomial_value(c: int, n: int, x: CoreNode, *, keep_product: bool = False) -> CoreNode:
    """``c·n·x^(n-1)``; with ``keep_product`` the ``c·n`` product stays unevaluated."""
    num = CoreNode.node
    if n == 1:
        return _const(Fraction(c))
    rest = _power_node(x, n - 1)
    if keep_product:
        return num(
            T.MULTIPLY_IMPLICIT, num(T.MULTIPLY, _const(Fraction(c)), _const(Fraction(n))), rest
        )
    return num(T.MULTIPLY_IMPLICIT, _const(Fraction(c * n)), rest)


def _power_page(diff: Callable[[CoreNode], CoreNode], x: CoreNode, n: int) -> SolveResult:
    """The app's page for ``d/dx x^n``: table row, ``sub``, and ``pow_with_one``."""
    num = CoreNode.node
    power_rule = _law_power(diff, x)
    unevaluated = num(
        T.MULTIPLY_IMPLICIT,
        _const(Fraction(n)),
        num(T.POWER, x, num(T.SUBTRACT, _const(Fraction(n)), _const(Fraction(1)))),
    )
    page = SolveResult()
    page.add_group(
        "derive", Step(diff(_power_node(x, n)), unevaluated, "derive_table_desc", [power_rule])
    )
    simplified = num(
        T.MULTIPLY_IMPLICIT,
        _const(Fraction(n)),
        num(T.POWER, x, _const(Fraction(1))) if n == 2 else _power_node(x, n - 1),
    )
    page.add_group("calculate_short", Step(unevaluated, simplified, "sub"))
    if n == 2:
        final = num(T.MULTIPLY_IMPLICIT, _const(Fraction(n)), x)
        page.add_group("pow", Step(simplified, final, "pow_with_one", [_const(Fraction(1))]))
        page.set_solution(final)
    else:
        page.set_solution(simplified)
    return page


def _term_page(
    diff: Callable[[CoreNode], CoreNode],
    x: CoreNode,
    term: CoreNode,
    c: int,
    n: int,
) -> SolveResult:
    """The derivative page of one term ``c x^n`` in a sum."""
    num = CoreNode.node
    page = SolveResult()
    if n == 1:
        if c == 1:
            page.add_group(
                "derive", Step(diff(term), _const(Fraction(1)), "derive_var", [_const(Fraction(1))])
            )
            page.set_solution(_const(Fraction(1)))
            return page
        law = _law_linear(diff, x)
        page.add_group("derive", Step(diff(term), _const(Fraction(c)), "derive_table_desc", [law]))
        page.set_solution(_const(Fraction(c)))
        return page
    if c == 1:
        return _power_page(diff, x, n)
    scale_rule, power_rule = _law_scale(diff), _law_power(diff, x)
    pulled = num(T.MULTIPLY, _const(Fraction(c)), diff(_power_node(x, n)))
    value = _monomial_value(c, n, x, keep_product=True)
    page.add_group("derive_short", Step(diff(term), pulled, "derive_use_rule", [scale_rule]))
    page.add_group("derive", Step(pulled, value, "derive_table_desc", [power_rule]))
    page.set_solution(value)
    return page


def _chain_sin_rows(
    node: CoreNode, x: CoreNode, expression: CoreNode, result: CoreNode, ctx: SolveContext
) -> bool:
    """``d/dx sin(k x)``, integer ``k >= 2``, by the chain rule."""
    inner = expression.children[0] if expression.children else None
    if not (
        expression.type is T.SIN
        and inner is not None
        and inner.type in (T.MULTIPLY_IMPLICIT, T.MULTIPLY)
        and len(inner.children) == 2
        and inner.children[0].type is T.CONSTANT
        and (inner.children[0].value or "").isdigit()
        and int(inner.children[0].value or 0) >= 2
        and inner.children[1].structural_eq(x)
    ):
        return False
    eq, g = CoreNode.node, CoreNode.variable("g")
    k = inner.children[0]
    outer = eq(T.DERIVATION1_DIFF, g, eq(T.SIN, g))
    rate = eq(T.DERIVATION1_DIFF, x, inner)
    split = eq(T.MULTIPLY, outer, rate)
    where = eq(T.EQUALS, g, inner)
    letters = CoreNode.variable("f(g)")
    rule = eq(
        T.EQUALS,
        eq(T.DERIVATION1_DIFF, x, letters),
        eq(T.MULTIPLY, eq(T.DERIVATION1_DIFF, g, letters), eq(T.DERIVATION1_DIFF, x, g)),
    )
    ctx.result.add_group(
        ["derive_short", CoreRichText(type="derive_chain", args=[rule])],
        Step(node, split, "derive_chain_where", [where, rule]),
    )
    cosine = eq(T.COS, g)
    first = eq(T.MULTIPLY, cosine, rate)
    second = eq(T.MULTIPLY, cosine, k)
    outer_detail = SolveResult()
    outer_detail.add_group(
        "derive",
        Step(
            outer,
            cosine,
            "derive_table_desc",
            [_law_table(lambda part: eq(T.DERIVATION1_DIFF, g, part), eq(T.SIN, g), cosine)],
        ),
    )
    outer_detail.set_solution(cosine)
    rate_detail = SolveResult()
    rate_detail.add_group(
        "derive",
        Step(
            rate,
            k,
            "derive_table_desc",
            [_law_linear(lambda part: eq(T.DERIVATION1_DIFF, x, part), x)],
        ),
    )
    rate_detail.set_solution(k)
    ctx.result.add_group(
        "differentiate",
        Step(split, first, "derive", subresult=outer_detail),
        Step(first, second, "derive", subresult=rate_detail),
    )
    restored = eq(T.MULTIPLY, eq(T.COS, inner), k)
    ctx.result.add_group(
        "substitute_return_one_short", Step(second, restored, "sub_msg_ret", [where])
    )
    ctx.result.add_group("reorder", Step(restored, result, "var_order"))
    return True


def _is_exp_of(expression: CoreNode, x: CoreNode) -> bool:
    """``e^x`` as typed on the keyboard (a power of the constant ``e``) or as ``EXP(x)``."""
    if expression.type is T.EXP:
        return expression.children[0].structural_eq(x)
    return (
        expression.type is T.POWER
        and expression.children[0].type is T.CONSTANT
        and expression.children[0].value == "e"
        and expression.children[1].structural_eq(x)
    )


def _is_simple_factor(part: CoreNode, x: CoreNode) -> bool:
    """``x``, ``sin x`` or ``cos x``: a factor whose derivative is one table entry."""
    return part.structural_eq(x) or (
        part.type in (T.SIN, T.COS) and part.children[0].structural_eq(x)
    )


def _product_rows(
    node: CoreNode, x: CoreNode, expression: CoreNode, result: CoreNode, ctx: SolveContext
) -> bool:
    """``d/dx (f g)`` of simple factors: the rule row, two derivative pages, then simplify."""
    if expression.type not in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) or len(expression.children) != 2:
        return False
    f, g = expression.children
    if not (_is_simple_factor(f, x) and _is_simple_factor(g, x)) or f.structural_eq(g):
        return False
    num = CoreNode.node

    def diff(part: CoreNode) -> CoreNode:
        return num(T.DERIVATION1_DIFF, x, part)

    letters = CoreNode.variable("f"), CoreNode.variable("g")
    rule = num(
        T.EQUALS,
        diff(num(T.MULTIPLY, *letters)),
        num(
            T.ADD,
            num(T.MULTIPLY, diff(letters[0]), letters[1]),
            num(T.MULTIPLY, letters[0], diff(letters[1])),
        ),
    )
    local = SolveContext(result=SolveResult(), variables=[x.value or "x"])
    d_f, d_g = _diff(f, local), _diff(g, local)
    start = num(T.ADD, num(T.MULTIPLY, diff(f), g), num(T.MULTIPLY, f, diff(g)))
    ctx.result.add_group("derive_short", Step(node, start, "derive_use_rule", [rule]))
    lead = (
        num(T.MULTIPLY_IMPLICIT, d_f, g) if _is_const(d_f, Fraction(1)) else num(T.MULTIPLY, d_f, g)
    )
    middle = num(T.ADD, lead, num(T.MULTIPLY, f, diff(g)))
    last = num(T.ADD, lead, num(T.MULTIPLY, f, d_g))

    def page(factor: CoreNode, value: CoreNode) -> SolveResult:
        detail = SolveResult()
        if factor.type is T.VARIABLE:
            detail.add_group("derive", Step(diff(factor), value, "derive_var", [value]))
        else:
            detail.add_group(
                "derive",
                Step(
                    diff(factor),
                    value,
                    "derive_table_desc",
                    [_law_table(diff, factor, value)],
                ),
            )
        detail.set_solution(value)
        return detail

    ctx.result.add_group(
        "differentiate",
        Step(start, middle, "derive", subresult=page(f, d_f)),
        Step(middle, last, "derive", subresult=page(g, d_g)),
    )
    ctx.result.add_group("simplify_msg", Step(last, result, "simplify"))
    return True


def _is_linear_term(part: CoreNode, x: CoreNode) -> bool:
    """``x + k`` with a numeric ``k``: a sum whose derivative takes the sum rule."""
    return (
        part.type is T.ADD
        and len(part.children) == 2
        and part.children[0].structural_eq(x)
        and part.children[1].type is T.CONSTANT
    )


def _quotient_parts(expression: CoreNode, x: CoreNode) -> tuple[CoreNode, CoreNode] | None:
    if expression.type is not T.FRACTION:
        return None
    f, g = expression.children
    if _is_simple_factor(f, x) and (_is_simple_factor(g, x) or _is_linear_term(g, x)):
        return f, g
    return None


def _quotient_rows(
    node: CoreNode, x: CoreNode, expression: CoreNode, result: CoreNode, ctx: SolveContext
) -> bool:
    """``d/dx (f / g)``, ``f`` simple and ``g = x + k``: the rule row, two pages, then simplify."""
    parts = _quotient_parts(expression, x)
    if parts is None:
        return False
    f, g = parts
    num = CoreNode.node
    two = _const(Fraction(2))

    def diff(part: CoreNode) -> CoreNode:
        return num(T.DERIVATION1_DIFF, x, part)

    letters = CoreNode.variable("f"), CoreNode.variable("g")
    rule = num(
        T.EQUALS,
        diff(num(T.FRACTION, *letters)),
        num(
            T.FRACTION,
            num(
                T.SUBTRACT,
                num(T.MULTIPLY, diff(letters[0]), letters[1]),
                num(T.MULTIPLY, letters[0], diff(letters[1])),
            ),
            num(T.POWER, letters[1], two),
        ),
    )
    local = SolveContext(result=SolveResult(), variables=[x.value or "x"])
    d_f, d_g = _diff(f, local), _diff(g, local)
    bracketed = num(T.BRACKET, g) if g.type is T.ADD else g
    below = num(T.POWER, bracketed, two)

    def quotient(top_f: CoreNode, top_g: CoreNode) -> CoreNode:
        top = num(T.SUBTRACT, num(T.MULTIPLY, top_f, g), num(T.MULTIPLY, f, top_g))
        return num(T.FRACTION, top, below)

    start = quotient(diff(f), diff(g))
    middle = quotient(d_f, diff(g))
    last = quotient(d_f, d_g)
    explicit = _is_const(d_f, Fraction(1)) and _is_const(d_g, Fraction(1))
    display_last = last
    if explicit:
        one = _const(Fraction(1))
        display_last = num(
            T.FRACTION,
            num(
                T.SUBTRACT,
                num(T.MULTIPLY_IMPLICIT, one, bracketed),
                num(T.MULTIPLY, f, one),
            ),
            below,
        )

    def page(factor: CoreNode, value: CoreNode) -> SolveResult:
        detail = SolveResult()
        if factor.type is T.VARIABLE:
            detail.add_group("derive", Step(diff(factor), value, "derive_var", [value]))
        else:
            detail.add_group(
                "derive",
                Step(
                    diff(factor),
                    value,
                    "derive_table_desc",
                    [_law_table(diff, factor, value)],
                ),
            )
        detail.set_solution(value)
        return detail

    def sum_page(part: CoreNode, value: CoreNode) -> SolveResult:
        """``d/dx (u + v)`` as the app opens it: the sum rule, both terms, then ``+0``."""
        a, b = part.children
        inner = SolveResult()
        inner.add_group(
            "derive_short",
            Step(
                diff(part),
                num(T.ADD, diff(a), diff(b)),
                "derive_use_rule",
                [_law_sum(diff)],
            ),
        )
        zero = _const(Fraction(0))
        inner.add_group(
            "differentiate",
            Step(num(T.ADD, diff(a), diff(b)), num(T.ADD, diff(a), zero), "derive"),
            Step(num(T.ADD, diff(a), zero), num(T.ADD, _const(Fraction(1)), zero), "derive"),
        )
        inner.add_group(
            CoreRichText(type="remove_zero", args=[zero]),
            Step(
                num(T.ADD, _const(Fraction(1)), zero),
                value,
                "add_with_zero",
                [zero],
            ),
        )
        inner.set_solution(value)
        return inner

    ctx.result.add_group("derive_short", Step(node, start, "derive_use_rule", [rule]))
    second_key = "derive_sum" if _is_linear_term(g, x) else "derive"
    ctx.result.add_group(
        "differentiate",
        Step(start, middle, "derive", subresult=page(f, d_f)),
        Step(
            middle,
            last,
            second_key,
            subresult=sum_page(g, d_g) if _is_linear_term(g, x) else page(g, d_g),
        ),
    )
    detail = SolveResult()
    if explicit and _is_linear_term(g, x):
        one = _const(Fraction(1))
        without_ones = num(T.FRACTION, num(T.SUBTRACT, bracketed, num(T.MULTIPLY, f, one)), below)
        without_second_one = num(T.FRACTION, num(T.SUBTRACT, bracketed, f), below)
        without_brackets = num(T.FRACTION, num(T.SUBTRACT, g, f), below)
        detail.add_group(
            "multiply",
            Step(display_last, without_ones, "mul_with_one", [one]),
            Step(without_ones, without_second_one, "mul_with_one", [one]),
            Step(without_second_one, without_brackets, "remove_bracket"),
        )
        detail.add_group(
            "remove_opposites",
            Step(without_brackets, result, "sub_with_self_remove_alg"),
        )
    else:
        detail.add_group("simplify_msg", Step(last, result, "simplify"))
    detail.set_solution(result)
    ctx.result.add_group("simplify_msg", Step(display_last, result, "simplify", subresult=detail))
    return True


def _table_rows(
    node: CoreNode, x: CoreNode, expression: CoreNode, result: CoreNode, ctx: SolveContext
) -> bool:
    """One table row for a function of ``x`` itself."""
    if not _is_exp_of(expression, x):
        if not expression.children or not expression.children[0].structural_eq(x):
            return False
        if expression.type not in (T.SIN, T.COS, T.TAN, T.LN, T.EXP, T.ROOT2, T.ROOT):
            return False
    law = CoreNode.node(T.EQUALS, CoreNode.node(T.DERIVATION1_DIFF, x, expression), result)
    ctx.result.add_group("derive", Step(node, result, "derive_table_desc", [law]))
    return True


def _reciprocal_rows(
    node: CoreNode, x: CoreNode, expression: CoreNode, result: CoreNode, ctx: SolveContext
) -> bool:
    """``d/dx 1/f``: the reciprocal rule, then the derivative of ``f``."""
    if expression.type not in (T.FRACTION, T.DIVIDE) or len(expression.children) != 2:
        return False
    top, bottom = expression.children
    if not _is_const(top, Fraction(1)) or not _is_simple_factor(bottom, x):
        return False
    try:
        local = SolveContext(result=SolveResult(), variables=[x.value or "x"])
        d_bottom = _diff(bottom, local)
    except SolveError:
        return False
    num = CoreNode.node

    def diff(part: CoreNode) -> CoreNode:
        return num(T.DERIVATION1_DIFF, x, part)

    squared = num(T.POWER, bottom, _const(Fraction(2)))
    rule = num(
        T.EQUALS,
        diff(num(T.FRACTION, _const(Fraction(1)), bottom)),
        num(T.NEGATIVE, num(T.FRACTION, diff(bottom), squared)),
    )
    after_rule = num(T.NEGATIVE, num(T.FRACTION, diff(bottom), squared))
    ctx.result.add_group("derive_short", Step(node, after_rule, "derive_use_rule", [rule]))
    if bottom.type is T.VARIABLE:
        key: str = "derive_var"
        args = [d_bottom]
    else:
        key = "derive_table_desc"
        args = [_law_table(diff, bottom, d_bottom)]
    ctx.result.add_group(
        "derive",
        Step(after_rule, num(T.NEGATIVE, num(T.FRACTION, d_bottom, squared)), key, args),
    )
    return True


def _abs_rows(
    node: CoreNode, x: CoreNode, expression: CoreNode, result: CoreNode, ctx: SolveContext
) -> bool:
    """``d/dx |x|`` by the app's route: ``|x| = √(x²)``, chain rule, then simplify."""
    if (
        expression.type is not T.ABS
        or len(expression.children) != 1
        or not expression.children[0].structural_eq(x)
    ):
        return False
    num = CoreNode.node
    g = CoreNode.variable("g")
    x2 = num(T.POWER, x, _const(Fraction(2)))
    root = num(T.ROOT2, x2)
    root_g = num(T.ROOT2, g)

    def diff(part: CoreNode) -> CoreNode:
        return num(T.DERIVATION1_DIFF, x, part)

    def dg(part: CoreNode) -> CoreNode:
        return num(T.DERIVATION1_DIFF, g, part)

    law = num(T.EQUALS, num(T.ABS, x), root)
    ctx.result.add_group("trans_msg", Step(node, diff(root), "using_trans", [law]))
    where = num(T.EQUALS, g, x2)
    letters = CoreNode.variable("f(g)")
    chain_law = num(T.EQUALS, diff(letters), num(T.MULTIPLY, dg(letters), diff(g)))
    ctx.result.add_group(
        ["derive_short", CoreRichText(type="derive_chain", args=[chain_law])],
        Step(
            diff(root),
            num(T.MULTIPLY, dg(root_g), diff(x2)),
            "derive_chain_where",
            [where, chain_law],
        ),
    )
    outer_value = num(
        T.FRACTION, _const(Fraction(1)), num(T.MULTIPLY_IMPLICIT, _const(Fraction(2)), root_g)
    )
    inner_value = num(T.MULTIPLY_IMPLICIT, _const(Fraction(2)), x)
    after_outer = num(T.MULTIPLY, outer_value, diff(x2))
    after_inner = num(T.MULTIPLY, outer_value, inner_value)
    outer_detail = SolveResult()
    outer_detail.add_group(
        "derive",
        Step(
            dg(root_g), outer_value, "derive_table_desc", [num(T.EQUALS, dg(root_g), outer_value)]
        ),
    )
    outer_detail.set_solution(outer_value)
    ctx.result.add_group(
        "differentiate",
        Step(diff(root), after_outer, "derive", subresult=outer_detail),
        Step(after_outer, after_inner, "derive", subresult=_power_page(diff, x, 2)),
    )
    root_x = num(T.ROOT2, x2)
    fraction = num(
        T.FRACTION, _const(Fraction(1)), num(T.MULTIPLY_IMPLICIT, _const(Fraction(2)), root_x)
    )
    substituted = num(T.MULTIPLY_IMPLICIT, num(T.MULTIPLY, fraction, _const(Fraction(2))), x)
    ctx.result.add_group(
        "substitute_return_one_short", Step(after_inner, substituted, "sub_msg_ret", [where])
    )
    abs_x = num(T.ABS, x)
    fraction_abs = num(T.FRACTION, _const(Fraction(1)), num(T.MULTIPLY, _const(Fraction(2)), abs_x))
    with_abs = num(T.MULTIPLY_IMPLICIT, num(T.MULTIPLY, fraction_abs, _const(Fraction(2))), x)
    cancelled = num(T.MULTIPLY, num(T.FRACTION, _const(Fraction(1)), abs_x), x)
    simplified = num(T.FRACTION, x, abs_x)
    detail = SolveResult()
    detail.add_group(
        "reduce",
        Step(substituted, with_abs, "root_reduce", [_const(Fraction(2))]),
        Step(with_abs, cancelled, "frac_reduce_out", [_const(Fraction(2))]),
    )
    detail.add_group("calculate_short", Step(cancelled, simplified, "product"))
    detail.set_solution(simplified)
    ctx.result.add_group("simplify_msg", Step(substituted, result, "simplify", subresult=detail))
    return True


def _single_monomial_rows(
    node: CoreNode,
    x: CoreNode,
    c: int,
    n: int,
    result: CoreNode,
    diff: Callable[[CoreNode], CoreNode],
    ctx: SolveContext,
) -> bool:
    """The app rows for one term ``c x^n``."""
    num = CoreNode.node
    if n == 1:
        if c == 1:
            ctx.result.add_group("derive", Step(node, result, "derive_var", [result]))
            return True
        ctx.result.add_group(
            "derive", Step(node, result, "derive_table_desc", [_law_linear(diff, x)])
        )
        return True
    if c == 1:
        power_rule = _law_power(diff, x)
        unevaluated = num(
            T.MULTIPLY_IMPLICIT,
            _const(Fraction(n)),
            num(T.POWER, x, num(T.SUBTRACT, _const(Fraction(n)), _const(Fraction(1)))),
        )
        ctx.result.add_group("derive", Step(node, unevaluated, "derive_table_desc", [power_rule]))
        simplified = (
            num(
                T.MULTIPLY_IMPLICIT,
                _const(Fraction(n)),
                num(T.POWER, x, _const(Fraction(1))),
            )
            if n == 2
            else result
        )
        ctx.result.add_group("calculate_short", Step(unevaluated, simplified, "sub"))
        if n == 2:
            ctx.result.add_group(
                "pow", Step(simplified, result, "pow_with_one", [_const(Fraction(1))])
            )
        return True
    scale_rule, power_rule = _law_scale(diff), _law_power(diff, x)
    pulled = num(T.MULTIPLY, _const(Fraction(c)), diff(_power_node(x, n)))
    value = _monomial_value(c, n, x, keep_product=True)
    ctx.result.add_group("derive_short", Step(node, pulled, "derive_use_rule", [scale_rule]))
    ctx.result.add_group(
        "derive",
        Step(pulled, value, "derive_table_desc", [power_rule], subresult=_power_page(diff, x, n)),
    )
    detail = SolveResult()
    detail.add_group("multiply", Step(value, result, "mul"))
    detail.set_solution(result)
    ctx.result.add_group("calculate_short", Step(value, result, "product", subresult=detail))
    return True


def _leibniz_rows(
    node: CoreNode,
    variable_node: CoreNode,
    expression: CoreNode,
    result: CoreNode,
    ctx: SolveContext,
) -> bool:
    """The app rows for ``d/dx`` of x^n, of sin x / cos x, and of a sum of monomials."""
    var = variable_node.value or "x"
    x = variable_node
    num = CoreNode.node

    def diff(part: CoreNode) -> CoreNode:
        return num(T.DERIVATION1_DIFF, x, part)

    single = _monomial(expression, var)
    if _abs_rows(node, x, expression, result, ctx):
        return True
    if _chain_sin_rows(node, x, expression, result, ctx):
        return True
    if _quotient_rows(node, x, expression, result, ctx):
        return True
    if _product_rows(node, x, expression, result, ctx):
        return True
    if _reciprocal_rows(node, x, expression, result, ctx):
        return True
    if _table_rows(node, x, expression, result, ctx):
        return True
    if single is not None:
        return _single_monomial_rows(node, x, single[0], single[1], result, diff, ctx)
    if expression.type is T.ADD and len(expression.children) >= 2:
        terms = [_monomial(t, var) for t in expression.children]
        if all(t is not None for t in terms):
            return _sum_rows(node, expression, result, [t for t in terms if t], x, diff, ctx)
    return False


def _sum_rows(
    node: CoreNode,
    expression: CoreNode,
    result: CoreNode,
    terms: list[tuple[int, int]],
    x: CoreNode,
    diff: Callable[[CoreNode], CoreNode],
    ctx: SolveContext,
) -> bool:
    """Sum rule, one page per term, then the products (only when a coefficient multiplies)."""
    num = CoreNode.node

    def chain(parts: list[CoreNode]) -> CoreNode:
        out = parts[0]
        for part in parts[1:]:
            out = num(T.ADD, out, part)
        return out

    def value(c: int, n: int) -> CoreNode:
        return _monomial_value(c, n, x, keep_product=c > 1 and n >= 2)

    split = chain([diff(t) for t in expression.children])
    ctx.result.add_group(
        ["derive_short", CoreRichText(type="derive_each", args=[x])],
        Step(node, split, "derive_use_rule", [_law_sum(diff)]),
    )
    current, pages = split, []
    for index, (c, n) in enumerate(terms):
        parts = [value(*t) for t in terms[: index + 1]] + [
            diff(t) for t in expression.children[index + 1 :]
        ]
        following = chain(parts)
        pages.append(
            Step(
                current,
                following,
                "derive",
                subresult=_term_page(diff, x, expression.children[index], c, n),
            )
        )
        current = following
    ctx.result.add_group("differentiate", *pages)
    scaled = [(c, n) for (c, n) in terms if c > 1 and n >= 2]
    if scaled:
        detail = SolveResult()
        for c, n in scaled:
            detail.add_group(
                "multiply",
                Step(
                    _monomial_value(c, n, x, keep_product=True),
                    _monomial_value(c, n, x),
                    "mul",
                ),
            )
        detail.set_solution(result)
        ctx.result.add_group("calculate_short", Step(current, result, "product", subresult=detail))
    return True


def _second_derivative_rows(
    node: CoreNode,
    x: CoreNode,
    c: int,
    n: int,
    result: CoreNode,
    ctx: SolveContext,
) -> bool:
    """The app rows for ``(c x^n)′′``: the first derivative, then the same rows again."""
    if c != 1 or n < 3:
        return False
    num = CoreNode.node

    def diff(part: CoreNode) -> CoreNode:
        return num(T.DERIVATION1_DIFF, x, part)

    expression = _power_node(x, n)
    first = _monomial_value(c, n, x)
    ctx.result.add_group(
        "derive_higher_order",
        Step(node, diff(diff(expression)), "derive_higher_order"),
    )
    ctx.result.add_group(
        "differentiate",
        Step(diff(expression), first, "derive", subresult=_power_page(diff, x, n)),
    )
    scale_rule, power_rule = _law_scale(diff), _law_power(diff, x)
    pulled = num(T.MULTIPLY, _const(Fraction(n)), diff(_power_node(x, n - 1)))
    value = _monomial_value(n, n - 1, x, keep_product=True)
    detail = SolveResult()
    detail.add_group("derive_short", Step(diff(first), pulled, "derive_use_rule", [scale_rule]))
    detail.add_group("derive", Step(pulled, value, "derive_table_desc", [power_rule]))
    detail.add_group("product", Step(value, result, "product"))
    detail.set_solution(result)
    ctx.result.add_group(
        "differentiate",
        Step(diff(first), result, "derive", subresult=detail),
    )
    return True


@solver_for(T.PRIME, T.DERIVATION1_PRIME, T.DERIVATION2_PRIME)
def solve_derivative_notation(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Производная в штриховой записи: ``f′`` (первый порядок) и ``f′′``.

    Дети узла — выражение (штрих ставится справа).
    """
    ctx.require(len(node.children) == 1, "производная берёт одно выражение")
    expression = node.children[0]
    order = 2 if node.type is T.DERIVATION2_PRIME else 1
    var = ctx.variables[0] if ctx.variables else "x"
    x = CoreNode.variable(var)

    result = expression
    for _ in range(order):
        try:
            result = _diff(result, ctx)
        except SolveError:
            result = _sympy_derivative(result, ctx)

    if order == 2:
        single = _monomial(expression, var)
        if single is not None and _second_derivative_rows(
            node, x, single[0], single[1], result, ctx
        ):
            return result
        ctx.result.add(Step(left=node, right=None, key="derive_higher_order"), [_HEADER])
        ctx.result.add(Step(left=node, right=result, key="second_derivative"), [_HEADER])
    elif _leibniz_rows(node, x, expression, result, ctx):
        return result
    else:
        ctx.result.add(Step(left=node, right=result, key="find_derivative"), [_HEADER])
    return result


def nth_derivative(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Производная порядка ``n`` (команда ``nth_derivative``, аргумент ``n``)."""
    if len(args) != 1:
        raise SolveError("нужен порядок производной")
    order = _as_number(args[0])
    if order is None or order.denominator != 1 or order.numerator < 1:
        raise SolveError("порядок производной — натуральное число")
    count = order.numerator

    result = node
    for _ in range(count):
        try:
            result = _diff(result, ctx)
        except SolveError:
            result = _sympy_derivative(result, ctx)

    if count >= 2:
        ctx.result.add(Step(left=node, right=None, key="derive_higher_order"), [_HEADER])
    if count >= 3:
        ctx.result.add(Step(left=node, right=None, key="derive_multi"), [_HEADER])
    if count == 1:
        key = "find_derivative"
    elif count == 2:
        key = "second_derivative"
    else:
        key = "find_high_order_derivative"
    ctx.result.add(Step(left=node, right=result, key=key), [_HEADER])
    return result


# ── textbook cards: one named rule per stage, both inputs ─────────────

_DERIVATIVE_NODES = (
    T.DERIVATION,
    T.DERIVATION1,
    T.DERIVATION1_DIFF,
    T.PRIME,
    T.DERIVATION1_PRIME,
    T.DERIVATION2_PRIME,
)

_NESTED_PRIME = (T.DERIVATION1, T.DERIVATION, T.PRIME, T.DERIVATION1_PRIME)


def _legacy_card(node: CoreNode, variables: list[str]) -> SolveResult | None:
    """The card this module produced before the textbook one."""
    result = SolveResult()
    # its own card titles (they are keys of the explanation dictionary).
    result.header = (
        "derive_evaluate_higher_order" if node.type is T.DERIVATION2_PRIME else "derive_evaluate"
    )
    local = SolveContext(result=result, variables=list(variables))
    try:
        if node.type is T.DERIVATION1_DIFF:
            answer = solve_derivative_with_respect(node, local)
        elif node.type in (T.DERIVATION, T.DERIVATION1):
            answer = solve_derivative(node, local)
        else:
            answer = solve_derivative_notation(node, local)
    except SolveError:
        return None
    result.set_solution(answer)
    return result if result else None


def _derivative_input(
    node: CoreNode, variables: list[str]
) -> tuple[T, CoreNode, CoreNode, str] | None:
    """``(form, notation node, expression, variable)`` for one derivative input."""
    if node.type is T.DERIVATION1_DIFF:
        if len(node.children) != 2:
            raise SolveError("d/dx: переменная и выражение")
        variable_node, expression = node.children
        if variable_node.type is not T.VARIABLE:
            raise SolveError("дифференцирование возможно только по переменной")
        return node.type, node, expression, variable_node.value or "x"
    if len(node.children) != 1:
        raise SolveError("производная берёт одно выражение")
    expression = node.children[0]
    variable = variables[0] if variables else "x"
    return node.type, node, expression, variable


def _textbook_card(node: CoreNode, variables: list[str]) -> SolveResult | None:
    """The textbook derivative card of the node (second derivative included)."""
    from ..teaching_calculus import derivative_card, second_derivative_card

    parsed = _derivative_input(node, variables)
    if parsed is None:
        return None
    form, notation, expression, variable = parsed
    if expression.type in _NESTED_PRIME and len(expression.children) == 1:
        # d/dx(d/dx f) is the second derivative of f.
        built = second_derivative_card(expression.children[0], variable)
    elif form is T.DERIVATION2_PRIME:
        built = second_derivative_card(expression, variable)
    else:
        built = derivative_card(expression, variable)
    if built is None:
        return None
    card, answer = built
    card.set_solution(answer)
    _ = notation
    return card


@method_provider(*_DERIVATIVE_NODES)
def derivative_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """Textbook card first for the phone input; the row card kept as an alternative.

    For ``derivation_diff`` the verified row card stays first and the textbook card is
    added next to it.  The phone sends ``derivation_prime`` (``DERIVATION1``), so
    there the textbook card is the first one a student sees.
    """
    textbook = _textbook_card(node, variables)
    legacy = _legacy_card(node, variables)
    if textbook is None:
        if legacy is None:
            raise SolveError("производная не поддерживается")
        return [legacy]
    if legacy is None:
        return [textbook]
    # The textbook card is the one a student reads; the verified row card
    # stays as the alternative.
    return [textbook, legacy]


def _sympy_derivative(expression: CoreNode, ctx: SolveContext) -> CoreNode:
    """Производная через sympy — на случай, если таблица правил не покрывает.

    Переменная объявляется вещественной: без этого sympy раскладывает
    ``|x|`` через ``re``/``im`` и ``Derivative`` и результат не переводится
    в узлы. С вещественным символом ``d|x|/dx`` даёт ``sign(x)``.
    """
    var = ctx.variables[0] if ctx.variables else "x"
    symbol = sympy.Symbol(var, real=True)
    computed = sympy.simplify(
        sympy.diff(to_sympy(expression).subs(sympy.Symbol(var), symbol), symbol)
    )
    try:
        return from_sympy(computed)
    except SolveError as err:
        raise SolveError("производная не выражается в поддерживаемых узлах") from err


__all__ = [
    "nth_derivative",
    "solve_derivative",
    "solve_derivative_notation",
    "solve_derivative_with_respect",
]
