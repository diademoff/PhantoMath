"""Мост между ``CoreNode`` и sympy.

Новые модули (интегралы, разложение многочленов, векторы) требуют символьных
преобразований и результата-выражения, а не числа. Для этого дерево переводится
в sympy, там упрощается/преобразуется, и переводится обратно в ``CoreNode``.

Функции:

* :func:`to_sympy` -- ``CoreNode`` -> ``sympy.Expr``;
* :func:`from_sympy` -- ``sympy.Expr`` -> ``CoreNode`` (константы и
  переменные, бинарные сумма/разность/произведение, дробь, степень/корень,
  функции, ``π``/``e``);
* :func:`simplify_node` -- упрощение дерева через sympy.

Обратный перевод даёт **бинарные** узлы (``ADD`` на два ребёнка и т. п.),
потому что рендер формул рассчитан на позиционные плейсхолдеры ``$0``/``$1``.
Знак выносится в ``SUBTRACT``/``NEGATIVE``, чтобы результат читался как
``2x - 3``, а не ``2x + (-3)``.
"""

from __future__ import annotations

from fractions import Fraction

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .arithmetic import format_number
from .base import SolveError

_FUNCTIONS: dict[T, str] = {
    T.SIN: "sin",
    T.COS: "cos",
    T.TAN: "tan",
    T.COT: "cot",
    T.SEC: "sec",
    T.CSC: "csc",
    T.ASIN: "asin",
    T.ACOS: "acos",
    T.ATAN: "atan",
    T.ACOT: "acot",
    T.SINH: "sinh",
    T.COSH: "cosh",
    T.TANH: "tanh",
    T.COTH: "coth",
}

_SYMPY_TO_NODE: dict[object, T] = {
    getattr(sympy, name): node_type for node_type, name in _FUNCTIONS.items()
}


def _number(value: Fraction) -> CoreNode:
    return CoreNode.constant(format_number(value))


def to_sympy(node: CoreNode) -> sympy.Expr:
    """Перевести узел в выражение sympy."""
    node_type = node.type
    if node_type is T.CONSTANT:
        text = (node.value or "").strip()
        if text in ("π", "pi"):
            return sympy.pi
        if text == "e":
            return sympy.E
        if text == "∞":
            return sympy.oo
        try:
            return sympy.Rational(text)
        except (ValueError, TypeError):
            return sympy.Symbol(text)
    if node_type is T.VARIABLE:
        return sympy.Symbol(node.value or "")
    if node_type is T.ADD:
        return sympy.Add(*(to_sympy(child) for child in node.children))
    if node_type is T.SUBTRACT:
        values = [to_sympy(child) for child in node.children]
        result = values[0]
        for value in values[1:]:
            result -= value
        return result
    if node_type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT):
        return sympy.Mul(*(to_sympy(child) for child in node.children))
    if node_type in (T.DIVIDE, T.FRACTION):
        return to_sympy(node.children[0]) / to_sympy(node.children[1])
    if node_type is T.POWER:
        return to_sympy(node.children[0]) ** to_sympy(node.children[1])
    if node_type is T.NEGATIVE:
        return -to_sympy(node.children[0])
    if node_type in (T.POSITIVE, T.BRACKET):
        return to_sympy(node.children[0])
    if node_type is T.ROOT2:
        return sympy.sqrt(to_sympy(node.children[-1]))
    if node_type is T.ROOT:
        return sympy.root(to_sympy(node.children[-1]), to_sympy(node.children[0]))
    if node_type is T.ABS:
        return sympy.Abs(to_sympy(node.children[0]))
    if node_type is T.EXP:
        return sympy.exp(to_sympy(node.children[0]))
    if node_type is T.LN:
        return sympy.log(to_sympy(node.children[0]))
    if node_type is T.LOG10:
        return sympy.log(to_sympy(node.children[0]), 10)
    if node_type is T.LOG:
        return sympy.log(to_sympy(node.children[0]), to_sympy(node.children[1]))
    if node_type is T.FACTORIAL:
        return sympy.factorial(to_sympy(node.children[0]))
    if node_type is T.EQUALS:
        return sympy.Eq(*(to_sympy(child) for child in node.children))
    if node_type in _FUNCTIONS:
        function = getattr(sympy, _FUNCTIONS[node_type])
        return function(to_sympy(node.children[0]))
    raise SolveError(f"узел {node_type} не переводится в sympy")


def from_sympy(expr: sympy.Expr) -> CoreNode:
    """Перевести выражение sympy обратно в узел."""
    expr = sympy.sympify(expr)

    if expr is sympy.oo:
        return CoreNode.constant("∞")
    if expr is sympy.pi:
        return CoreNode.constant("π")
    if expr is sympy.E:
        return CoreNode.constant("e")
    if expr.is_Integer:
        return CoreNode.constant(str(int(expr)))
    if expr.is_Rational:
        return _number(Fraction(int(expr.p), int(expr.q)))
    if expr.is_Float:
        return CoreNode.constant(str(float(expr)))
    if expr.is_Symbol:
        return CoreNode.variable(str(expr))

    if isinstance(expr, sympy.Add):
        return _from_add(expr)
    if isinstance(expr, sympy.Mul):
        return _from_mul(expr)
    if isinstance(expr, sympy.Pow):
        return _from_pow(expr)
    if isinstance(expr, sympy.Abs):
        return CoreNode.node(T.ABS, from_sympy(expr.args[0]))
    if isinstance(expr, sympy.factorial):
        return CoreNode.node(T.FACTORIAL, from_sympy(expr.args[0]))
    if isinstance(expr, sympy.exp):
        return CoreNode.node(T.EXP, from_sympy(expr.args[0]))
    if isinstance(expr, sympy.log):
        arguments = expr.args
        if len(arguments) == 2:
            return CoreNode.node(T.LOG, from_sympy(arguments[0]), from_sympy(arguments[1]))
        return CoreNode.node(T.LN, from_sympy(arguments[0]))
    if isinstance(expr, sympy.Eq):
        return CoreNode.node(T.EQUALS, from_sympy(expr.lhs), from_sympy(expr.rhs))
    if type(expr) in _SYMPY_TO_NODE:
        return CoreNode.node(_SYMPY_TO_NODE[type(expr)], from_sympy(expr.args[0]))
    raise SolveError(f"выражение sympy {expr} не переводится в узел")


def _from_add(expr: sympy.Expr) -> CoreNode:
    """Сумма: сначала положительные слагаемые, затем вычитаемые.

    Порядок детерминированный и не зависит от сортировки sympy, поэтому
    ``2x - 3`` читается как вычитание, а не как ``-3 + 2x``.
    """
    terms = list(expr.args)
    positives = [term for term in terms if not term.could_extract_minus_sign()]
    negatives = [term for term in terms if term.could_extract_minus_sign()]

    result: CoreNode | None = None
    for term in [*positives, *negatives]:
        negative = bool(term.could_extract_minus_sign())
        piece = from_sympy(-term if negative else term)
        if result is None:
            result = CoreNode.node(T.NEGATIVE, piece) if negative else piece
        elif negative:
            result = CoreNode.node(T.SUBTRACT, result, piece)
        else:
            result = CoreNode.node(T.ADD, result, piece)
    if result is None:
        return CoreNode.constant("0")
    return result


def _from_mul(expr: sympy.Expr) -> CoreNode:
    numerator: list[sympy.Expr] = []
    denominator: list[sympy.Expr] = []
    for factor in expr.args:
        if isinstance(factor, sympy.Pow) and factor.exp.is_Integer and factor.exp < 0:
            denominator.append(factor.base ** (-factor.exp))
        else:
            numerator.append(factor)

    top = _product(numerator)
    if not denominator:
        return top
    bottom = _product(denominator)
    return CoreNode.node(T.FRACTION, top, bottom)


def _product(factors: list[sympy.Expr]) -> CoreNode:
    if not factors:
        return CoreNode.constant("1")
    if len(factors) > 1 and factors[0] is sympy.Integer(-1):
        # Коэффициент -1: пишем как «-…», а не «-1·…».
        return CoreNode.node(T.NEGATIVE, _product(factors[1:]))
    result = from_sympy(factors[0])
    constant_leading = factors[0].is_Number
    for factor in factors[1:]:
        piece = from_sympy(factor)
        kind = T.MULTIPLY_IMPLICIT if constant_leading else T.MULTIPLY
        result = CoreNode.node(kind, result, piece)
        constant_leading = False
    return result


def _from_pow(expr: sympy.Pow) -> CoreNode:
    exponent = expr.exp
    base = expr.base
    if exponent.is_Integer and exponent < 0:
        return CoreNode.node(T.FRACTION, CoreNode.constant("1"), from_sympy(base ** (-exponent)))
    if exponent == sympy.Rational(1, 2):
        return CoreNode.node(T.ROOT2, from_sympy(base))
    if exponent.is_Rational and exponent.p == 1 and exponent.q > 1:
        return CoreNode.node(T.ROOT, from_sympy(sympy.Integer(exponent.q)), from_sympy(base))
    return CoreNode.node(T.POWER, from_sympy(base), from_sympy(exponent))


def simplify_node(node: CoreNode) -> CoreNode:
    """Упростить дерево узлов через sympy."""
    return from_sympy(sympy.simplify(to_sympy(node)))


__all__ = [
    "from_sympy",
    "simplify_node",
    "to_sympy",
]
