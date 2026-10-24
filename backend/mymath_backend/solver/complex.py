"""Комплексные числа.

Мнимая единица — константа ``i`` (**CONSTANT** ``"i"``). Модуль
зарегистрирован на ``REAL`` (``Re``), ``IMAGINARY`` (``Im``) и ``CONJUGATE``
(сопряжение): все три считаются через sympy мостом.

Арифметику с ``i`` берёт на себя тот же мост: выражение с ``i`` решается
``sympy.simplify`` (в ``solver/__init__.py`` есть отдельная ветка), поэтому
``(1+2i)(3−i)`` приводится к стандартному виду.

Ключи шагов: ``complex_rewrite`` (Re/Im), ``complex_conjugate`` (сопряжение),
``complex_convert_std_form`` (арифметика с ``i``).

Карточки арифметики строятся по частям числа: сумма и разность группируют
действительные и мнимые части (``complex_separate``), произведение идёт по
распределительному закону, частное освобождается от знаменателя сопряжённым
числом (``complex_rationalize_mul``), степени — по периоду ``i``
(``complex_i_period``) или формуле Муавра (``complex_pow_polar_moivre``).
Корни извлекаются по тригонометрической форме (``complex_root_formula``), а
команда ``polar`` пишет в этой форме любое число, включая действительное.
"""

from __future__ import annotations

from fractions import Fraction
from math import isqrt

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .arithmetic import as_fraction, format_number
from .base import SolveContext, SolveError, SolveResult, Step, solver_for
from .sympy_bridge import from_sympy, to_sympy

_IMAGINARY = "i"

_KEY: dict[T, str] = {
    T.REAL: "complex_rewrite",
    T.IMAGINARY: "complex_rewrite",
    T.CONJUGATE: "complex_conjugate",
}


def contains_imaginary(node: CoreNode) -> bool:
    """Есть ли в выражении мнимая единица."""
    return any(
        item.type is T.CONSTANT and (item.value or "").strip() == _IMAGINARY for item in node.walk()
    )


def _number(value: Fraction) -> CoreNode:
    return CoreNode.constant(format_number(value))


def _unit() -> CoreNode:
    return CoreNode.constant(_IMAGINARY)


def _iterm(coefficient: Fraction) -> CoreNode:
    """``3i`` (``i`` for 1, ``−i`` for −1) as a product term."""
    if coefficient == 1:
        return _unit()
    if coefficient == -1:
        return CoreNode.node(T.NEGATIVE, _unit())
    return CoreNode.node(T.MULTIPLY_IMPLICIT, _number(coefficient), _unit())


def _complex_node(real: Fraction, imaginary: Fraction) -> CoreNode:
    if imaginary == 0:
        return _number(real)
    if real == 0:
        return _iterm(imaginary)
    if imaginary > 0:
        return CoreNode.node(T.ADD, _number(real), _iterm(imaginary))
    return CoreNode.node(T.SUBTRACT, _number(real), _iterm(-imaginary))


def _parts(node: CoreNode) -> tuple[Fraction, Fraction] | None:
    """``(a, b)`` of ``a + bi`` (brackets allowed, real part first or last)."""
    inner = node
    if inner.type is T.BRACKET and len(inner.children) == 1:
        inner = inner.children[0]
    if inner.type not in (T.ADD, T.SUBTRACT) or len(inner.children) != 2:
        return None
    first, second = inner.children
    sign = 1 if inner.type is T.ADD else -1
    real_node = first
    if _is_unit_node(first):
        real_node = second
        imag_coefficient = Fraction(1)
    elif _is_unit_node(second):
        imag_coefficient = Fraction(1)
    else:
        parsed = _imag_coefficient(second)
        if parsed is not None:
            imag_coefficient = parsed
        else:
            parsed = _imag_coefficient(first)
            if parsed is None:
                return None
            imag_coefficient = parsed
            real_node = second
    try:
        real = as_fraction(real_node)
    except SolveError:
        return None
    return real, sign * imag_coefficient


def _is_unit_node(node: CoreNode) -> bool:
    return (node.type is T.CONSTANT and (node.value or "").strip() == _IMAGINARY) or (
        node.type is T.IMAGINARY and all(child.type is T.EMPTY for child in node.children)
    )


def _imag_coefficient(node: CoreNode) -> Fraction | None:
    """``b`` of ``bi`` or ``i``; ``None`` when the node is not an imaginary term."""
    if _is_unit_node(node):
        return Fraction(1)
    if node.type is T.NEGATIVE and len(node.children) == 1 and _is_unit_node(node.children[0]):
        return Fraction(-1)
    if node.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) and len(node.children) == 2:
        first, second = node.children
        if _is_unit_node(second):
            try:
                return as_fraction(first)
            except SolveError:
                return None
        if _is_unit_node(first):
            try:
                return as_fraction(second)
            except SolveError:
                return None
    return None


def _imag_terms(coefficients: list[tuple[Fraction, CoreNode]]) -> CoreNode:
    nodes = [_iterm(value) for value, _ in coefficients]
    if len(nodes) == 1:
        return nodes[0]
    return CoreNode.node(T.ADD, *nodes)


def _sum_suffix_detail(
    coefficients: list[Fraction],
    total: Fraction,
    detail_key: str = "sum_suffix_add_detail",
) -> SolveResult:
    """The imaginary coefficients collected: ``i + 3i = i(1 + 3) = 4i``."""
    eq = CoreNode.node
    detail = SolveResult()
    units = [value for value in coefficients if abs(value) == 1]
    unit = units[0] if units else None
    if unit is not None:
        key = "sum_suffix_add_one" if unit > 0 else "sum_suffix_add_neg_one"
        before = CoreNode.node(T.ADD, *[_iterm(value) for value in coefficients])
        expanded = CoreNode.node(
            T.ADD, *[CoreNode.node(T.MULTIPLY, _unit(), _number(value)) for value in coefficients]
        )
        detail.add_group(
            CoreRichText(
                type="sum_one_coeff",
                args=[_number(Fraction(1 if unit > 0 else -1))],
            ),
            Step(before, expanded, key, [_number(Fraction(1 if unit > 0 else -1))]),
        )
        collected = CoreNode.node(
            T.MULTIPLY, _unit(), CoreNode.node(T.ADD, *[_number(value) for value in coefficients])
        )
        detail.add_group("sum_suffix", Step(expanded, collected, detail_key))
    else:
        collected = CoreNode.node(
            T.MULTIPLY, _unit(), CoreNode.node(T.ADD, *[_number(value) for value in coefficients])
        )
        before = CoreNode.node(T.ADD, *[_iterm(value) for value in coefficients])
        detail.add_group("sum_suffix", Step(before, collected, detail_key))
    inside = CoreNode.node(T.ADD, *[_number(value) for value in coefficients])
    final_key = "add" if all(value > 0 for value in coefficients) else "calc_sum"
    detail.add_group("calculate_short", Step(collected, _iterm(total), final_key))
    _ = inside, eq
    detail.set_solution(_iterm(total))
    return detail


def _value(expr: sympy.Expr) -> CoreNode:
    """A number or a symbolic value as a node."""
    return from_sympy(sympy.simplify(expr))


def _numeric_parts(node: CoreNode) -> tuple[sympy.Expr, sympy.Expr] | None:
    """``(a, b)`` of ``a + bi`` when the node is a number, ``None`` otherwise.

    Unlike :func:`_parts` it accepts irrational parts (``√3``) and fractions:
    the cards need the parts of any numeric complex number, not only integers.
    """
    try:
        value = to_sympy(node)
    except SolveError:
        return None
    if value.is_number is not True:
        return None
    real, imaginary = value.as_real_imag()
    return sympy.simplify(real), sympy.simplify(imaginary)


def _complex_expr(real: sympy.Expr, imaginary: sympy.Expr) -> CoreNode:
    """``a + bi`` in the algebraic form the keyboard writes."""
    return from_sympy(sympy.simplify(real + imaginary * sympy.I))


def _standard(expr: sympy.Expr) -> CoreNode:
    """A complex number in the algebraic form ``a + bi`` (denominator rationalized)."""
    value = sympy.radsimp(sympy.simplify(expr))
    real, imaginary = value.as_real_imag()
    return _complex_expr(sympy.simplify(real), sympy.simplify(imaginary))


def _imaginary_term(coefficient: sympy.Expr) -> CoreNode:
    """``bi`` as a term: ``i`` for 1, ``−i`` for −1, ``3i`` otherwise."""
    if coefficient == 1:
        return _unit()
    if coefficient == -1:
        return CoreNode.node(T.NEGATIVE, _unit())
    return CoreNode.node(T.MULTIPLY_IMPLICIT, _value(coefficient), _unit())


def _bracket(node: CoreNode) -> CoreNode:
    """Brackets around a sum or a negative number, so a factor reads correctly."""
    if node.type in (T.ADD, T.SUBTRACT, T.NEGATIVE):
        return CoreNode.node(T.BRACKET, node)
    if node.type is T.CONSTANT and (node.value or "").lstrip().startswith(("-", "−")):
        return CoreNode.node(T.BRACKET, node)
    return node


def _sum_node(left: sympy.Expr, right: sympy.Expr, sign: int) -> CoreNode:
    """``left ± right`` with the sign folded into the second term."""
    term = sign * right
    if term < 0:
        return CoreNode.node(T.SUBTRACT, _value(left), _value(-term))
    return CoreNode.node(T.ADD, _value(left), _value(term))


def _polar_node(radius: sympy.Expr, angle: sympy.Expr) -> CoreNode:
    """``r(cos φ + i sin φ)``."""
    inner = CoreNode.node(
        T.ADD,
        CoreNode.node(T.COS, _value(angle)),
        CoreNode.node(T.MULTIPLY_IMPLICIT, _unit(), CoreNode.node(T.SIN, _value(angle))),
    )
    return CoreNode.node(T.MULTIPLY_IMPLICIT, _value(radius), CoreNode.node(T.BRACKET, inner))


def _modulus_argument(node: CoreNode, radius: sympy.Expr, angle: sympy.Expr) -> Step:
    """The row that names the modulus and the argument of a complex number."""
    return Step(
        node,
        CoreNode.node(
            T.LIST,
            CoreNode.node(T.EQUALS, CoreNode.variable("r"), _value(radius)),
            CoreNode.node(T.EQUALS, CoreNode.variable("φ"), _value(angle)),
        ),
        "complex_mod_arg",
        [node, _value(radius), _value(angle)],
    )


def _modulus_rows(
    node: CoreNode, parts: tuple[Fraction, Fraction], ctx: SolveContext
) -> CoreNode | None:
    real, imaginary = parts
    squared = real * real + imaginary * imaginary
    root = isqrt(int(squared)) if squared.denominator == 1 else 0
    if root == 0 or root * root != squared:
        return None
    eq = CoreNode.node
    result = _number(Fraction(root))
    powered = eq(
        T.ROOT2,
        eq(
            T.ADD,
            eq(T.POWER, _number(real), _number(Fraction(2))),
            eq(T.POWER, _number(imaginary), _number(Fraction(2))),
        ),
    )
    a, b = CoreNode.variable("a"), CoreNode.variable("b")
    law = eq(
        T.EQUALS,
        eq(T.ABS, eq(T.ADD, a, eq(T.MULTIPLY, b, _unit()))),
        eq(
            T.ROOT2,
            eq(T.ADD, eq(T.POWER, a, _number(Fraction(2))), eq(T.POWER, b, _number(Fraction(2)))),
        ),
    )
    ctx.result.add_group("complex_mod", Step(node, powered, "complex_mod_formula", [law]))
    detail = SolveResult()
    first = eq(
        T.ROOT2,
        eq(
            T.ADD,
            _number(real * real),
            eq(T.POWER, _number(imaginary), _number(Fraction(2))),
        ),
    )
    detail.add_group("evaluate", Step(powered, first, "pow"))
    second = eq(
        T.ROOT2,
        eq(T.ADD, _number(real * real), _number(imaginary * imaginary)),
    )
    detail.add_group("evaluate", Step(first, second, "pow"))
    summed = eq(T.ROOT2, _number(Fraction(squared)))
    detail.add_group("calculate_short", Step(second, summed, "add"))
    detail.add_group("calculate_short", Step(summed, result, "root_square"))
    detail.set_solution(result)
    ctx.result.add_group(
        "calculate_short",
        Step(powered, result, "calculate_direct", subresult=detail),
    )
    return result


def _difference_rows(
    node: CoreNode,
    left: tuple[Fraction, Fraction],
    right: tuple[Fraction, Fraction],
    ctx: SolveContext,
) -> CoreNode:
    eq = CoreNode.node
    a, b = left
    c, d = right
    opened = eq(T.SUBTRACT, _complex_node(a, b), _complex_node(c, d))
    minus_right = eq(T.ADD, _iterm(-d), eq(T.SUBTRACT, _complex_node(a, b), _number(c)))
    grouped = eq(
        T.ADD,
        _number(a - c),
        _iterm(b),
        _iterm(-d),
    )
    final = _complex_node(a - c, b - d)
    ctx.result.add_group(
        ["rewrite", "remove_bracket_short"],
        Step(node, opened, "remove_bracket"),
        Step(opened, minus_right, "neg_neg_arg", [CoreNode.constant("-")]),
    )
    detail = _sum_suffix_detail([b, -d], b - d)
    ctx.result.add_group(
        ["calculate_short", "sum_suffix"],
        Step(minus_right, grouped, "sub"),
        Step(grouped, final, "sum_suffix", subresult=detail),
    )
    return final


def _product_rows(
    node: CoreNode,
    left: tuple[Fraction, Fraction],
    right: tuple[Fraction, Fraction],
    ctx: SolveContext,
) -> CoreNode:
    eq = CoreNode.node
    a, b = left
    c, d = right
    real = a * c
    imag_first = a * d
    imag_second = b * c
    square_coefficient = b * d
    squared = eq(T.POWER, _unit(), _number(Fraction(2)))
    crossed = eq(
        T.ADD,
        eq(T.ADD, _number(real), _iterm(imag_first)),
        eq(T.ADD, _iterm(imag_second), eq(T.MULTIPLY, _number(square_coefficient), squared)),
    )
    ctx.result.add_group("mul_bracket_cross", Step(node, crossed, "mul_bracket_cross_each"))
    after_first = eq(
        T.ADD,
        eq(T.ADD, _number(real), _iterm(imag_first)),
        eq(T.ADD, _number(imag_second), eq(T.MULTIPLY, _number(square_coefficient), squared)),
    )
    first_detail = SolveResult()
    first_detail.add_group(
        "multiply",
        Step(
            eq(T.MULTIPLY, _iterm(b), _number(c)),
            _number(imag_second),
            "mul",
        ),
    )
    first_detail.set_solution(_number(imag_second))
    squared_terms = eq(
        T.MULTIPLY, _number(square_coefficient), eq(T.POWER, _unit(), _number(Fraction(2)))
    )
    after_second = eq(
        T.ADD,
        eq(T.ADD, _number(real), _iterm(imag_first)),
        eq(T.ADD, _number(imag_second), squared_terms),
    )
    second_detail = SolveResult()
    raw = eq(T.MULTIPLY, _unit(), _unit(), _number(square_coefficient))
    one_i = eq(
        T.MULTIPLY, _unit(), _number(square_coefficient), eq(T.POWER, _unit(), _number(Fraction(1)))
    )
    both_i = eq(
        T.MULTIPLY,
        _number(square_coefficient),
        eq(T.POWER, _unit(), _number(Fraction(1))),
        eq(T.POWER, _unit(), _number(Fraction(1))),
    )
    combined = eq(
        T.MULTIPLY,
        _number(square_coefficient),
        eq(T.POWER, _unit(), eq(T.ADD, _number(Fraction(1)), _number(Fraction(1)))),
    )
    second_detail.add_group(
        CoreRichText(type="pow_one_exp", args=[_number(Fraction(1))]),
        Step(raw, one_i, "pow_implicit_exp", [_number(Fraction(1))]),
        Step(one_i, both_i, "pow_implicit_exp", [_number(Fraction(1))]),
    )
    second_detail.add_group("product", Step(both_i, combined, "pow_same_base_mul"))
    second_detail.add_group(
        "calculate_short",
        Step(
            combined,
            squared_terms,
            "add",
        ),
    )
    second_detail.set_solution(squared_terms)
    ctx.result.add_group(
        "calculate_short",
        Step(crossed, after_first, "product", subresult=first_detail),
        Step(after_first, after_second, "product", subresult=second_detail),
    )
    law = eq(
        T.EQUALS,
        eq(T.POWER, _unit(), _number(Fraction(2))),
        CoreNode.node(T.NEGATIVE, _number(Fraction(1))),
    )
    defined = eq(
        T.ADD,
        eq(T.ADD, _number(real), _iterm(imag_first)),
        eq(
            T.ADD,
            _number(imag_second),
            eq(
                T.MULTIPLY,
                _number(square_coefficient),
                CoreNode.node(T.NEGATIVE, _number(Fraction(1))),
            ),
        ),
    )
    ctx.result.add_group("calculate_short", Step(after_second, defined, "by_definition", [law]))
    negated = eq(
        T.ADD,
        eq(T.ADD, _number(real), _iterm(imag_first)),
        eq(
            T.ADD,
            _number(imag_second),
            eq(
                T.MULTIPLY,
                CoreNode.node(T.NEGATIVE, _number(Fraction(1))),
                _number(square_coefficient),
            ),
        ),
    )
    negative_detail = SolveResult()
    la, lb = CoreNode.variable("a"), CoreNode.variable("b")
    negative_law = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.MULTIPLY, CoreNode.node(T.NEGATIVE, la), CoreNode.node(T.NEGATIVE, lb)),
        CoreNode.node(T.MULTIPLY, la, lb),
    )
    negative_detail.add_group(
        "neg_mul_msg",
        Step(
            eq(
                T.MULTIPLY,
                CoreNode.node(T.NEGATIVE, _number(Fraction(1))),
                _number(square_coefficient),
            ),
            eq(T.MULTIPLY, _number(Fraction(1)), _number(-square_coefficient)),
            "mul_neg_neg",
            [negative_law],
        ),
    )
    negative_detail.add_group(
        "multiply",
        Step(
            eq(T.MULTIPLY, _number(Fraction(1)), _number(-square_coefficient)),
            _number(-square_coefficient),
            "mul",
        ),
    )
    negative_detail.set_solution(_number(-square_coefficient))
    ctx.result.add_group(
        "product",
        Step(
            defined,
            negated,
            "mul_with_neg_one",
            [CoreNode.node(T.NEGATIVE, _number(Fraction(1)))],
            subresult=negative_detail,
        ),
    )
    real_total = real - square_coefficient
    summed = eq(
        T.ADD,
        _number(real_total),
        _iterm(imag_first),
        _iterm(imag_second),
    )
    final = _complex_node(real_total, imag_first + imag_second)
    ctx.result.add_group("calculate_short", Step(negated, summed, "add"))
    detail = _sum_suffix_detail(
        [imag_first, imag_second], imag_first + imag_second, "sum_suffix_detail"
    )
    ctx.result.add_group(
        ["calculate_short", "sum_suffix"],
        Step(summed, final, "sum_suffix", subresult=detail),
    )
    return final


def _sum_rows(
    node: CoreNode,
    left: tuple[sympy.Expr, sympy.Expr],
    right: tuple[sympy.Expr, sympy.Expr],
    ctx: SolveContext,
    *,
    subtract: bool,
) -> CoreNode:
    """``(a + bi) ± (c + di)``: the parts are grouped, then added separately."""
    a, b = left
    c, d = right
    sign = -1 if subtract else 1
    real = a + sign * c
    imaginary = b + sign * d
    real_group = CoreNode.node(T.BRACKET, _sum_node(a, c, sign))
    imaginary_group = CoreNode.node(T.BRACKET, _sum_node(b, d, sign))
    grouped = CoreNode.node(T.ADD, real_group, CoreNode.node(T.MULTIPLY, imaginary_group, _unit()))
    final = _complex_expr(real, imaginary)
    ctx.result.add_group("complex_separate", Step(node, grouped, "complex_separate"))
    detail = SolveResult()
    detail.add_group(
        "calculate_short",
        Step(real_group, _value(real), "add" if sign * c >= 0 else "calc_diff"),
        Step(imaginary_group, _value(imaginary), "add" if sign * d >= 0 else "calc_diff"),
    )
    detail.set_solution(_value(imaginary))
    ctx.result.add_group(
        ["calculate_short", "sum_suffix"],
        Step(grouped, final, "sum_suffix", subresult=detail),
    )
    return final


def _division_rows(
    node: CoreNode,
    top: tuple[sympy.Expr, sympy.Expr],
    bottom: tuple[sympy.Expr, sympy.Expr],
    ctx: SolveContext,
) -> CoreNode | None:
    """``(a + bi)/(c + di)``: the denominator is cleared with its conjugate."""
    a, b = top
    c, d = bottom
    if c == 0 and d == 0:
        return None
    top_node = _complex_expr(a, b)
    bottom_node = _complex_expr(c, d)
    conjugate = _complex_expr(c, -d)
    top_product = CoreNode.node(T.MULTIPLY, _bracket(top_node), _bracket(conjugate))
    bottom_product = CoreNode.node(T.MULTIPLY, _bracket(bottom_node), _bracket(conjugate))
    conjugated = CoreNode.node(T.FRACTION, top_product, bottom_product)
    ctx.result.add_group(
        "complex_rationalize_mul", Step(node, conjugated, "complex_rationalize_mul")
    )
    numerator = _complex_expr(a * c + b * d, b * c - a * d)
    expanded = CoreNode.node(T.FRACTION, numerator, bottom_product)
    ctx.result.add_group("mul_bracket_cross", Step(conjugated, expanded, "mul_bracket_cross_each"))
    denominator = _value(c * c + d * d)
    with_square = CoreNode.node(T.FRACTION, numerator, denominator)
    left, right = CoreNode.variable("a"), CoreNode.variable("b")
    left_term = CoreNode.node(T.MULTIPLY, right, _unit())
    law = CoreNode.node(
        T.EQUALS,
        CoreNode.node(
            T.MULTIPLY,
            CoreNode.node(T.BRACKET, CoreNode.node(T.ADD, left, left_term)),
            CoreNode.node(T.BRACKET, CoreNode.node(T.SUBTRACT, left, left_term)),
        ),
        CoreNode.node(
            T.ADD,
            CoreNode.node(T.POWER, left, _number(Fraction(2))),
            CoreNode.node(T.POWER, right, _number(Fraction(2))),
        ),
    )
    ctx.result.add_group(
        "factorise_inv_sim", Step(expanded, with_square, "factorise_inv_sim", [law])
    )
    final = _standard((a + b * sympy.I) / (c + d * sympy.I))
    if not final.structural_eq(with_square):
        ctx.result.add_group(
            "complex_convert_std_form", Step(with_square, final, "complex_convert_std_form")
        )
    return final


def _unit_power_rows(
    node: CoreNode, coefficient: sympy.Expr, exponent: int, ctx: SolveContext
) -> CoreNode:
    """``(c i)^n``: the modulus is powered, the unit goes through its period 4."""
    reduced = exponent % 4
    reduced_node = CoreNode.node(T.POWER, _unit(), _value(reduced))
    coefficient_power = coefficient**exponent
    current = node
    if coefficient != 1:
        split = CoreNode.node(
            T.MULTIPLY,
            CoreNode.node(T.POWER, _value(coefficient), _value(exponent)),
            CoreNode.node(T.POWER, _unit(), _value(exponent)),
        )
        ctx.result.add_group("complex_pow_split", Step(node, split, "complex_pow_split"))
        current = split
        period = CoreNode.node(T.MULTIPLY, _value(coefficient_power), reduced_node)
    else:
        period = reduced_node
    ctx.result.add_group("complex_i_period", Step(current, period, "complex_i_period"))
    powered = coefficient_power * sympy.I**reduced
    final = _complex_expr(*sympy.simplify(powered).as_real_imag())
    law = CoreNode.node(
        T.EQUALS, CoreNode.node(T.POWER, _unit(), _value(reduced)), _value(sympy.I**reduced)
    )
    ctx.result.add_group("calculate_short", Step(period, final, "by_definition", [law]))
    return final


def _square_rows(
    node: CoreNode, real: sympy.Expr, imaginary: sympy.Expr, ctx: SolveContext
) -> CoreNode:
    """``(a + bi)^2`` by the square of a binomial."""
    a, b = CoreNode.variable("a"), CoreNode.variable("b")
    squared_binomial = CoreNode.node(T.BRACKET, CoreNode.node(T.ADD, a, b))
    formula = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.POWER, squared_binomial, _number(Fraction(2))),
        CoreNode.node(
            T.ADD,
            CoreNode.node(
                T.ADD,
                CoreNode.node(T.POWER, a, _number(Fraction(2))),
                CoreNode.node(
                    T.MULTIPLY_IMPLICIT,
                    _number(Fraction(2)),
                    CoreNode.node(T.MULTIPLY_IMPLICIT, a, b),
                ),
            ),
            CoreNode.node(T.POWER, b, _number(Fraction(2))),
        ),
    )
    square_real = CoreNode.node(T.POWER, _value(real), _number(Fraction(2)))
    square_imaginary = CoreNode.node(T.POWER, _value(imaginary), _number(Fraction(2)))
    doubled = _imaginary_term(2 * real * imaginary)
    squared_unit = CoreNode.node(T.POWER, _unit(), _number(Fraction(2)))
    expanded = CoreNode.node(
        T.ADD,
        CoreNode.node(T.ADD, square_real, doubled),
        CoreNode.node(T.MULTIPLY, square_imaginary, squared_unit),
    )
    defined = CoreNode.node(
        T.SUBTRACT, CoreNode.node(T.ADD, square_real, doubled), square_imaginary
    )
    computed = CoreNode.node(
        T.SUBTRACT,
        CoreNode.node(T.ADD, _value(real * real), doubled),
        _value(imaginary * imaginary),
    )
    final = _complex_expr(real * real - imaginary * imaginary, 2 * real * imaginary)
    ctx.result.add_group("expand_msg", Step(node, expanded, "using_expand", [formula]))
    ctx.result.add_group(
        "calculate_short",
        Step(
            expanded,
            defined,
            "by_definition",
            [
                CoreNode.node(
                    T.EQUALS,
                    CoreNode.node(T.POWER, _unit(), _number(Fraction(2))),
                    CoreNode.node(T.NEGATIVE, _number(Fraction(1))),
                )
            ],
        ),
    )
    ctx.result.add_group("pow", Step(defined, computed, "pow"))
    ctx.result.add_group("sum_suffix", Step(computed, final, "sum_suffix"))
    return final


def _moivre_rows(node: CoreNode, value: sympy.Expr, exponent: int, ctx: SolveContext) -> CoreNode:
    """``z^n`` through the trigonometric form and De Moivre's formula."""
    radius = sympy.simplify(sympy.Abs(value))
    angle = sympy.simplify(sympy.arg(value))
    polar = _polar_node(radius, angle)
    powered = CoreNode.node(T.POWER, CoreNode.node(T.BRACKET, polar), _value(exponent))
    base = node.children[0] if node.children else node
    while base.type is T.BRACKET and len(base.children) == 1:
        base = base.children[0]
    detail = SolveResult()
    detail.add_group("complex_trig_form_simple", _modulus_argument(base, radius, angle))
    detail.set_solution(polar)
    ctx.result.add_group(
        "complex_trig_form", Step(node, powered, "complex_trig_form", subresult=detail)
    )
    r, angle_variable, n = (
        CoreNode.variable("r"),
        CoreNode.variable("θ"),
        CoreNode.variable("n"),
    )
    polar_formula = CoreNode.node(T.BRACKET, _polar_node_symbolic(r, angle_variable))
    formula = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.POWER, polar_formula, n),
        CoreNode.node(
            T.MULTIPLY_IMPLICIT,
            CoreNode.node(T.POWER, r, n),
            CoreNode.node(
                T.BRACKET,
                CoreNode.node(
                    T.ADD,
                    CoreNode.node(T.COS, CoreNode.node(T.MULTIPLY, n, angle_variable)),
                    CoreNode.node(
                        T.MULTIPLY_IMPLICIT,
                        _unit(),
                        CoreNode.node(T.SIN, CoreNode.node(T.MULTIPLY, n, angle_variable)),
                    ),
                ),
            ),
        ),
    )
    moivre = _polar_node(sympy.simplify(radius**exponent), sympy.simplify(exponent * angle))
    ctx.result.add_group(
        "complex_pow_polar_moivre",
        Step(powered, moivre, "complex_pow_polar_moivre", [formula]),
    )
    final = _standard(sympy.expand(value**exponent))
    ctx.result.add_group(
        "complex_convert_std_form", Step(moivre, final, "complex_convert_std_form")
    )
    return final


def _polar_node_symbolic(radius: CoreNode, angle: CoreNode) -> CoreNode:
    """``r(cos θ + i sin θ)`` built from the given nodes (for a formula)."""
    return CoreNode.node(
        T.MULTIPLY_IMPLICIT,
        radius,
        CoreNode.node(
            T.BRACKET,
            CoreNode.node(
                T.ADD,
                CoreNode.node(T.COS, angle),
                CoreNode.node(T.MULTIPLY_IMPLICIT, _unit(), CoreNode.node(T.SIN, angle)),
            ),
        ),
    )


def _inverse_power_rows(
    node: CoreNode, value: sympy.Expr, exponent: int, ctx: SolveContext
) -> CoreNode | None:
    """``z^(−m)``: the reciprocal of ``z^m``, computed as a division."""
    degree = -exponent
    base = _complex_expr(*value.as_real_imag())
    powered = CoreNode.node(T.POWER, _bracket(base), _value(degree))
    reciprocal = CoreNode.node(T.FRACTION, _number(Fraction(1)), powered)
    detail = SolveResult()
    source = node.children[0] if node.children else node
    if not source.structural_eq(base):
        detail.add_group(
            "complex_convert_std_form",
            Step(source, base, "complex_convert_std_form"),
        )
    scratch = SolveContext(result=detail)
    positive = _power_rows(powered, value, degree, scratch)
    if positive is None:
        return None
    ctx.result.add_group(
        "complex_pow_inverse",
        Step(node, reciprocal, "complex_pow_inverse", subresult=detail),
    )
    positive_value = sympy.simplify(value**degree)
    standard = CoreNode.node(
        T.FRACTION, _number(Fraction(1)), _complex_expr(*positive_value.as_real_imag())
    )
    if not standard.structural_eq(reciprocal):
        ctx.result.add_group(
            "complex_convert_std_form", Step(reciprocal, standard, "complex_convert_std_form")
        )
    parts = positive_value.as_real_imag()
    return _division_rows(
        standard,
        (sympy.Integer(1), sympy.Integer(0)),
        (sympy.simplify(parts[0]), sympy.simplify(parts[1])),
        ctx,
    )


def _power_rows(
    node: CoreNode, value: sympy.Expr, exponent: int, ctx: SolveContext
) -> CoreNode | None:
    """An integer power of a numeric complex number, as a textbook does it."""
    if value.is_number is not True:
        return None
    real, imaginary = (sympy.simplify(item) for item in value.as_real_imag())
    if imaginary == 0:
        return None
    if exponent < 0:
        return _inverse_power_rows(node, value, exponent, ctx)
    if exponent == 0:
        return None
    if real == 0:
        return _unit_power_rows(node, imaginary, exponent, ctx)
    if exponent == 2:
        return _square_rows(node, real, imaginary, ctx)
    return _moivre_rows(node, value, exponent, ctx)


def _integer_exponent(node: CoreNode) -> int | None:
    """The integer exponent of a ``POWER`` node, ``None`` for anything else."""
    if node.type is not T.POWER or len(node.children) != 2:
        return None
    exponent = node.children[1]
    sign = 1
    while exponent.type is T.BRACKET and len(exponent.children) == 1:
        exponent = exponent.children[0]
    if exponent.type is T.NEGATIVE and len(exponent.children) == 1:
        sign, exponent = -1, exponent.children[0]
        while exponent.type is T.BRACKET and len(exponent.children) == 1:
            exponent = exponent.children[0]
    if exponent.type is not T.CONSTANT or exponent.value is None:
        return None
    text = exponent.value.strip()
    if not text.isdigit():
        return None
    return sign * int(text)


def complex_power_card(node: CoreNode, ctx: SolveContext) -> CoreNode | None:
    """Power card for a numeric complex base; ``None`` outside that family."""
    exponent = _integer_exponent(node)
    if exponent is None:
        return None
    return _power_rows(node, to_sympy(node.children[0]), exponent, ctx)


def complex_rationalize(node: CoreNode, ctx: SolveContext) -> CoreNode | None:
    """Division card for a numeric complex fraction; ``None`` outside that family."""
    if node.type not in (T.FRACTION, T.DIVIDE) or len(node.children) != 2:
        return None
    top = _numeric_parts(node.children[0])
    bottom = _numeric_parts(node.children[1])
    if top is None or bottom is None:
        return None
    return _division_rows(node, top, bottom, ctx)


def polar_form(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Тригонометрическая форма ``r(cos φ + i sin φ)`` любого числа."""
    value = to_sympy(node)
    if value.is_number is not True:
        raise SolveError("полярная форма — у комплексного числа")
    radius = sympy.simplify(sympy.Abs(value))
    angle = sympy.simplify(sympy.arg(value))
    result = _polar_node(radius, angle)
    parts = CoreNode.node(
        T.LIST,
        CoreNode.node(T.EQUALS, CoreNode.variable("r"), _value(radius)),
        CoreNode.node(T.EQUALS, CoreNode.variable("φ"), _value(angle)),
    )
    ctx.result.add_group("complex_calculate_polar", Step(node, parts, "complex_calculate_polar"))
    ctx.result.add_group("write_polar_form", Step(node, result, "write_polar_form"))
    return result


def solve_imaginary_arithmetic(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Арифметика с ``i``: карточки по строкам, иначе стандартный вид через sympy."""
    if ctx.depth == 0:
        if node.type is T.POWER and _is_unit_node(node.children[0]) and len(node.children) == 2:
            exponent = node.children[1]
            if exponent.type is T.CONSTANT and (exponent.value or "").strip() == "2":
                result = CoreNode.constant("-1")
                law = CoreNode.node(
                    T.EQUALS,
                    CoreNode.node(T.POWER, _unit(), _number(Fraction(2))),
                    CoreNode.node(T.NEGATIVE, _number(Fraction(1))),
                )
                ctx.result.add_group("calculate_short", Step(node, result, "by_definition", [law]))
                return result
        if node.type is T.ABS and len(node.children) == 1:
            parts = _parts(node.children[0])
            if parts is not None:
                answer = _modulus_rows(node, parts, ctx)
                if answer is not None:
                    return answer
        if node.type is T.SUBTRACT and len(node.children) == 2:
            left, right = _parts(node.children[0]), _parts(node.children[1])
            if left is not None and right is not None:
                return _difference_rows(node, left, right, ctx)
        if node.type in (T.ADD, T.SUBTRACT) and len(node.children) == 2:
            first = _numeric_parts(node.children[0])
            second = _numeric_parts(node.children[1])
            if first is not None and second is not None:
                return _sum_rows(node, first, second, ctx, subtract=node.type is T.SUBTRACT)
        if node.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) and len(node.children) == 2:
            left, right = _parts(node.children[0]), _parts(node.children[1])
            if left is not None and right is not None:
                return _product_rows(node, left, right, ctx)
        if node.type in (T.FRACTION, T.DIVIDE):
            answer = complex_rationalize(node, ctx)
            if answer is not None:
                return answer
        if node.type is T.POWER:
            answer = complex_power_card(node, ctx)
            if answer is not None:
                return answer
    result = from_sympy(sympy.simplify(to_sympy(node)))
    ctx.result.add(Step(left=node, right=result, key="complex_convert_std_form"))
    return result


def complex_power(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Возвести комплексное число в целую степень (формула Муавра).

    Аргумент команды — целый показатель; шаг ``complex_pow_polar_moivre_simple``.
    """
    exponent = _integer_argument(args)
    value = to_sympy(node)
    if value.is_number is not True or value.is_real is True:
        raise SolveError("степень берётся у комплексного числа")
    # The app shows the conjugate, modulus and parts before the power card.
    conjugate = from_sympy(sympy.simplify(sympy.conjugate(value)))
    ctx.result.add_group(
        "complex_conjugate",
        Step(node, conjugate, "complex_conjugate_find", [node, conjugate]),
    )
    parts = _parts(node)
    if parts is not None:
        real, imaginary = parts
        absolute = CoreNode.node(T.ABS, node)
        ctx.result.add_group("abs_value", Step(node, absolute, "complex_add_bars"))
        squared = CoreNode.node(
            T.ADD,
            CoreNode.node(T.POWER, _number(real), _number(Fraction(2))),
            CoreNode.node(T.POWER, _number(imaginary), _number(Fraction(2))),
        )
        modulus = CoreNode.node(T.ROOT2, squared)
        a, b = CoreNode.variable("a"), CoreNode.variable("b")
        law = CoreNode.node(
            T.EQUALS,
            CoreNode.node(
                T.ABS,
                CoreNode.node(T.ADD, a, CoreNode.node(T.MULTIPLY_IMPLICIT, b, _unit())),
            ),
            CoreNode.node(
                T.ROOT2,
                CoreNode.node(
                    T.ADD,
                    CoreNode.node(T.POWER, a, _number(Fraction(2))),
                    CoreNode.node(T.POWER, b, _number(Fraction(2))),
                ),
            ),
        )
        ctx.result.add_group("complex_mod", Step(node, modulus, "complex_mod_formula", [law]))
        pair = CoreNode.node(
            T.LIST,
            CoreNode.node(T.EQUALS, CoreNode.variable("Re"), _number(real)),
            CoreNode.node(T.EQUALS, CoreNode.variable("Im"), _number(imaginary)),
        )
        ctx.result.add_group(
            "complex_number",
            Step(
                node,
                pair,
                "complex_find_parts_pair",
                [node, _number(real), _number(imaginary)],
            ),
        )
    result = from_sympy(sympy.simplify(value**exponent))
    ctx.result.add(Step(left=node, right=result, key="complex_pow_polar_moivre_simple"))
    return result


def complex_polar_multiply(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Умножение комплексных чисел через тригонометрическую форму (шаг ``complex_mul_polar``)."""
    result = _polar_operation(node, args, divide=False)
    ctx.result.add(Step(left=node, right=result, key="complex_mul_polar", args=[args[0]]))
    return result


def complex_polar_divide(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Деление комплексных чисел через тригонометрическую форму (шаг ``complex_divide_polar``)."""
    result = _polar_operation(node, args, divide=True)
    ctx.result.add(Step(left=node, right=result, key="complex_divide_polar", args=[args[0]]))
    return result


def _polar_operation(node: CoreNode, args: list[CoreNode], *, divide: bool) -> CoreNode:
    """Общий код умножения/деления двух комплексных чисел."""
    if not args:
        raise SolveError("нужен второй комплексный множитель")
    first, second = to_sympy(node), to_sympy(args[0])
    if first.is_real is True or second.is_real is True:
        raise SolveError("в полярной форме — комплексные числа")
    if divide and second == 0:
        raise SolveError("деление на ноль")
    value = first / second if divide else first * second
    return from_sympy(sympy.simplify(value))


def complex_roots(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Извлечь корни n-й степени из комплексного числа.

    Аргумент — натуральная степень ``n`` (без аргумента берём квадратный
    корень); ответ — множество из ``n`` корней (шаг ``complex_find_root_polar``).
    """
    degree = 2 if not args else _integer_argument(args)
    if degree < 1:
        raise SolveError("степень корня — натуральное число")
    value = to_sympy(node)
    if value.is_number is not True:
        raise SolveError("корни извлекаются из числа")
    roots = _polar_roots(value, degree)
    if not roots:
        raise SolveError("корни не выражаются")
    answer = from_sympy(sympy.FiniteSet(*roots))
    detail = _root_polar_detail(node, value, degree)
    ctx.result.add_group(
        "complex_find_root_polar",
        Step(node, answer, "complex_find_root_polar", subresult=detail),
    )
    return answer


def _polar_roots(value: sympy.Expr, degree: int) -> list[sympy.Expr]:
    """Все ``degree`` корней по формуле Муавра, в алгебраической форме."""
    radius = sympy.simplify(sympy.Abs(value))
    angle = sympy.simplify(sympy.arg(value))
    root_radius = sympy.simplify(sympy.root(radius, degree))
    found: list[sympy.Expr] = []
    for index in range(degree):
        angle_of_root = sympy.simplify((angle + 2 * sympy.pi * index) / degree)
        found.append(
            sympy.simplify(
                sympy.expand_complex(
                    root_radius * (sympy.cos(angle_of_root) + sympy.I * sympy.sin(angle_of_root))
                )
            )
        )
    # FiniteSet sorts the roots the same way for every caller: the app keeps a stable order.
    return list(sympy.FiniteSet(*found))


def _root_polar_detail(node: CoreNode, value: sympy.Expr, degree: int) -> SolveResult:
    """Модуль и аргумент подкоренного числа и его корни в тригонометрической форме."""
    radius = sympy.simplify(sympy.Abs(value))
    angle = sympy.simplify(sympy.arg(value))
    root_radius = sympy.simplify(sympy.root(radius, degree))
    polar_roots = [
        _polar_node(root_radius, sympy.simplify((angle + 2 * sympy.pi * index) / degree))
        for index in range(degree)
    ]
    detail = SolveResult()
    detail.add_group("complex_trig_form_simple", _modulus_argument(node, radius, angle))
    r, phi, n, k = (CoreNode.variable(name) for name in ("r", "φ", "n", "k"))
    shifted = CoreNode.node(T.ADD, phi, CoreNode.node(T.MULTIPLY_IMPLICIT, _value(2 * sympy.pi), k))
    root_angle = CoreNode.node(T.FRACTION, shifted, n)
    formula = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.POWER, CoreNode.node(T.BRACKET, _polar_node_symbolic(r, phi)), n),
        CoreNode.node(
            T.MULTIPLY_IMPLICIT,
            CoreNode.node(T.POWER, r, CoreNode.node(T.FRACTION, _number(Fraction(1)), n)),
            CoreNode.node(
                T.BRACKET,
                CoreNode.node(
                    T.ADD,
                    CoreNode.node(T.COS, root_angle),
                    CoreNode.node(
                        T.MULTIPLY_IMPLICIT,
                        _unit(),
                        CoreNode.node(T.SIN, CoreNode.node(T.FRACTION, shifted, n)),
                    ),
                ),
            ),
        ),
    )
    detail.add_group(
        "complex_root_formula",
        Step(node, CoreNode.node(T.LIST, *polar_roots), "complex_root_formula", [formula]),
    )
    detail.set_solution(CoreNode.node(T.LIST, *polar_roots))
    return detail


def _integer_argument(args: list[CoreNode]) -> int:
    """Целый аргумент команды."""
    if len(args) != 1 or args[0].type is not T.CONSTANT or args[0].value is None:
        raise SolveError("нужен целый аргумент")
    text = args[0].value.strip()
    if not text.lstrip("-").isdigit():
        raise SolveError("нужен целый аргумент")
    return int(text)


@solver_for(T.REAL, T.IMAGINARY, T.CONJUGATE)
def solve_complex(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Re, Im или сопряжение комплексного числа."""
    ctx.require(len(node.children) == 1, "операция над комплексным числом")
    value = to_sympy(node.children[0])
    if node.type is T.REAL:
        computed = sympy.re(value)
    elif node.type is T.IMAGINARY:
        computed = sympy.im(value)
    else:
        computed = sympy.conjugate(value)

    if node.type in (T.REAL, T.IMAGINARY):
        ctx.result.add(Step(left=node, right=None, key="complex_find_parts"))
    result = from_sympy(sympy.simplify(computed))
    ctx.result.add(Step(left=node, right=result, key=_KEY[node.type]))
    return result


__all__ = [
    "complex_polar_divide",
    "complex_polar_multiply",
    "complex_power",
    "complex_power_card",
    "complex_rationalize",
    "complex_roots",
    "contains_imaginary",
    "polar_form",
    "solve_complex",
    "solve_imaginary_arithmetic",
]
