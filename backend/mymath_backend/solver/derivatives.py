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

Шаг один -- ключ ``find_derivative`` с заголовком ``derive_short``. Типы,
которых нет в таблице, отклоняются: это следующие модули.
"""

from __future__ import annotations

from fractions import Fraction

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .arithmetic import format_number
from .base import SolveContext, SolveError, SolveResult, Step, solver_for
from .sympy_bridge import from_sympy, to_sympy

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
    ctx.require(len(node.children) >= 1, "производная без выражения")
    expression = node.children[0]
    try:
        result = _diff(expression, ctx)
    except SolveError:
        result = _sympy_derivative(expression, ctx)

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
    return result


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
    (как рисует Photomath: ``d(выражение)/d(переменная)``).
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
    ctx.result.add(
        Step(
            left=node,
            right=result,
            key="find_derivative_with_respect",
            args=[variable_node],
        ),
        [_HEADER],
    )
    return result


@solver_for(T.PRIME, T.DERIVATION1_PRIME, T.DERIVATION2_PRIME)
def solve_derivative_notation(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Производная в штриховой записи: ``f′`` (первый порядок) и ``f′′``.

    Дети узла — выражение (как рисует Photomath: штрих ставится справа).
    """
    ctx.require(len(node.children) >= 1, "производная без выражения")
    expression = node.children[0]
    order = 2 if node.type is T.DERIVATION2_PRIME else 1

    result = expression
    for _ in range(order):
        try:
            result = _diff(result, ctx)
        except SolveError:
            result = _sympy_derivative(result, ctx)

    if order == 2:
        ctx.result.add(Step(left=node, right=None, key="derive_higher_order"), [_HEADER])
        ctx.result.add(Step(left=node, right=result, key="second_derivative"), [_HEADER])
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


def _sympy_derivative(expression: CoreNode, ctx: SolveContext) -> CoreNode:
    """Производная через sympy — на случай, если таблица правил не покрывает."""
    var = ctx.variables[0] if ctx.variables else "x"
    computed = sympy.simplify(sympy.diff(to_sympy(expression), sympy.Symbol(var)))
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
