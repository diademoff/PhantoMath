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
    T.ASEC: "asec",
    T.ACSC: "acsc",
    T.SINH: "sinh",
    T.COSH: "cosh",
    T.TANH: "tanh",
    T.COTH: "coth",
    T.SECH: "sech",
    T.CSCH: "csch",
    T.ASINH: "asinh",
    T.ACOSH: "acosh",
    T.ATANH: "atanh",
    T.ACOTH: "acoth",
    T.ASECH: "asech",
    T.ACSCH: "acsch",
}

_SYMPY_TO_NODE: dict[object, T] = {
    getattr(sympy, name): node_type for node_type, name in _FUNCTIONS.items()
}

# Действительная/мнимая часть и сопряжение — по имени класса sympy.
_COMPLEX_CLASSES: dict[str, T] = {
    "re": T.REAL,
    "im": T.IMAGINARY,
    "conjugate": T.CONJUGATE,
}

# Промежутки: тип -> (левый край открыт, правый край открыт). Дети — границы.
INTERVALS: dict[T, tuple[bool, bool]] = {
    T.OPEN_OPEN_INTERVAL: (True, True),
    T.OPEN_CLOSED_INTERVAL: (True, False),
    T.CLOSED_OPEN_INTERVAL: (False, True),
    T.CLOSED_CLOSED_INTERVAL: (False, False),
}


def _number(value: Fraction) -> CoreNode:
    return CoreNode.constant(format_number(value))


def _from_matrix_cell(cell: sympy.Expr) -> CoreNode:
    """Ячейка матрицы: упрощаем значение и переводим в узел."""
    return from_sympy(sympy.simplify(cell))


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
        if text == "i":
            return sympy.I
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
    if node_type is T.SIGN:
        return sympy.sign(to_sympy(node.children[0]))
    if node_type is T.FLOOR:
        return sympy.floor(to_sympy(node.children[0]))
    if node_type is T.REAL:
        return sympy.re(to_sympy(node.children[0]))
    if node_type is T.IMAGINARY:
        return sympy.im(to_sympy(node.children[0]))
    if node_type is T.CONJUGATE:
        return sympy.conjugate(to_sympy(node.children[0]))
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
    if node_type is T.MATRIX:
        # Матрица: дети — строки (``MATRIX_ROW``), у строки — ячейки.
        rows: list[list[sympy.Expr]] = []
        for row in node.children:
            cells = row.children if row.type is T.MATRIX_ROW else [row]
            rows.append([to_sympy(cell) for cell in cells])
        return sympy.Matrix(rows)
    if node_type is T.EQUALS:
        return sympy.Eq(*(to_sympy(child) for child in node.children))
    if node_type is T.SET:
        return sympy.FiniteSet(*(to_sympy(child) for child in node.children))
    if node_type is T.UNION:
        return sympy.Union(*(to_sympy(child) for child in node.children))
    if node_type is T.INTERSECTION:
        return sympy.Intersection(*(to_sympy(child) for child in node.children))
    if node_type is T.DIFFERENCE:
        return sympy.Complement(to_sympy(node.children[0]), to_sympy(node.children[1]))
    if node_type in INTERVALS:
        left_open, right_open = INTERVALS[node_type]
        return sympy.Interval(
            to_sympy(node.children[0]),
            to_sympy(node.children[1]),
            left_open=left_open,
            right_open=right_open,
        )
    if node_type is T.DEGREE:
        # Градусы -- только единица записи: в sympy угол всегда в радианах.
        return to_sympy(node.children[0]) * sympy.pi / 180
    if node_type is T.RADIAN:
        # Радианы -- единица записи без изменения числового значения.
        return to_sympy(node.children[0])
    if node_type in _FUNCTIONS:
        function = getattr(sympy, _FUNCTIONS[node_type])
        return function(to_sympy(node.children[0]))
    raise SolveError(f"узел {node_type} не переводится в sympy")


def from_sympy(expr: sympy.Expr) -> CoreNode:
    """Перевести выражение sympy обратно в узел."""
    expr = sympy.sympify(expr)

    if isinstance(expr, sympy.MatrixBase):
        return CoreNode.node(
            T.MATRIX,
            *[
                CoreNode.node(T.MATRIX_ROW, *[_from_matrix_cell(cell) for cell in row])
                for row in expr.tolist()
            ],
        )
    if expr is sympy.oo:
        return CoreNode.constant("∞")
    if expr is -sympy.oo:
        return CoreNode.node(T.NEGATIVE, CoreNode.constant("∞"))
    if expr is sympy.I:
        return CoreNode.constant("i")
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
    if isinstance(expr, sympy.sign):
        return CoreNode.node(T.SIGN, from_sympy(expr.args[0]))
    if isinstance(expr, sympy.floor):
        return CoreNode.node(T.FLOOR, from_sympy(expr.args[0]))
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
    if isinstance(expr, sympy.Interval):
        return _from_interval(expr)
    if expr is sympy.S.Reals:
        # Всё множество действительных чисел — промежуток (-∞, +∞).
        return CoreNode.node(T.OPEN_OPEN_INTERVAL, from_sympy(-sympy.oo), from_sympy(sympy.oo))
    if expr is sympy.EmptySet:
        return CoreNode.empty()
    if isinstance(expr, sympy.FiniteSet):
        return CoreNode.node(T.SET, *(from_sympy(item) for item in expr.args))
    if isinstance(expr, sympy.Complement):
        return CoreNode.node(T.DIFFERENCE, from_sympy(expr.args[0]), from_sympy(expr.args[1]))
    if isinstance(expr, sympy.Union):
        return _from_set_operation(T.UNION, expr.args)
    if isinstance(expr, sympy.Intersection):
        return _from_set_operation(T.INTERSECTION, expr.args)
    complex_node = _COMPLEX_CLASSES.get(type(expr).__name__)
    if complex_node is not None:
        return CoreNode.node(complex_node, from_sympy(expr.args[0]))
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

    # Рациональный множитель выносим в дробь: ``√3/2`` читается лучше, чем
    # ``1/2·√3``, и это тот же ответ. Целый множитель остаётся в
    # произведении: ``2·x`` -- не дробь.
    coefficient = sympy.Integer(1)
    others: list[sympy.Expr] = []
    for factor in numerator:
        if factor.is_Rational:
            coefficient *= factor
        else:
            others.append(factor)

    if not denominator and (coefficient.q == 1 or not others):
        return _product(numerator)

    top_factors = list(others)
    bottom_factors = list(denominator)
    if abs(coefficient.p) != 1:
        top_factors.insert(0, sympy.Integer(coefficient.p))
    if coefficient.q != 1:
        bottom_factors.insert(0, sympy.Integer(coefficient.q))

    top: CoreNode = _product(top_factors) if top_factors else CoreNode.constant("1")
    if coefficient.p < 0:
        top = CoreNode.node(T.NEGATIVE, top)
    if not bottom_factors:
        return top
    return CoreNode.node(T.FRACTION, top, _product(bottom_factors))


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


def _from_interval(expr: sympy.Interval) -> CoreNode:
    """Промежуток sympy -> узел; тип задаёт открытость краёв."""
    if expr.left_open and expr.right_open:
        node_type = T.OPEN_OPEN_INTERVAL
    elif expr.left_open:
        node_type = T.OPEN_CLOSED_INTERVAL
    elif expr.right_open:
        node_type = T.CLOSED_OPEN_INTERVAL
    else:
        node_type = T.CLOSED_CLOSED_INTERVAL
    return CoreNode.node(node_type, from_sympy(expr.start), from_sympy(expr.end))


def _from_set_operation(node_type: T, args: tuple[sympy.Basic, ...]) -> CoreNode:
    """Объединение/пересечение sympy -> узел; один операнд разворачивается."""
    if len(args) == 1:
        return from_sympy(args[0])
    return CoreNode.node(node_type, *(from_sympy(arg) for arg in args))


def simplify_node(node: CoreNode) -> CoreNode:
    """Упростить дерево узлов через sympy."""
    return from_sympy(sympy.simplify(to_sympy(node)))


__all__ = [
    "INTERVALS",
    "from_sympy",
    "simplify_node",
    "to_sympy",
]
