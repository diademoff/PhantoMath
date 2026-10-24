"""Комплексные числа.

Мнимая единица — константа ``i`` (**CONSTANT** ``"i"``). Модуль
зарегистрирован на ``REAL`` (``Re``), ``IMAGINARY`` (``Im``) и ``CONJUGATE``
(сопряжение): все три считаются через sympy мостом.

Арифметику с ``i`` берёт на себя тот же мост: выражение с ``i`` решается
``sympy.simplify`` (в ``solver/__init__.py`` есть отдельная ветка), поэтому
``(1+2i)(3−i)`` приводится к стандартному виду.

Ключи шагов: ``complex_rewrite`` (Re/Im), ``complex_conjugate`` (сопряжение),
``complex_convert_std_form`` (арифметика с ``i``).
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
        if node.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) and len(node.children) == 2:
            left, right = _parts(node.children[0]), _parts(node.children[1])
            if left is not None and right is not None:
                return _product_rows(node, left, right, ctx)
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

    Аргумент — натуральная степень ``n``; ответ — множество из ``n`` корней
    (шаг ``complex_find_root_polar``).
    """
    degree = _integer_argument(args)
    if degree < 1:
        raise SolveError("степень корня — натуральное число")
    value = to_sympy(node)
    if value.is_number is not True:
        raise SolveError("корни извлекаются из числа")
    unknown = sympy.Symbol("_z")
    try:
        found = sympy.solve(sympy.Eq(unknown**degree, value), unknown)
    except (NotImplementedError, TypeError, ValueError) as error:
        raise SolveError("корни не выражаются") from error
    if not found:
        raise SolveError("корни не выражаются")
    answer = from_sympy(sympy.FiniteSet(*found))
    ctx.result.add(Step(left=node, right=answer, key="complex_find_root_polar"))
    return answer


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
    "complex_roots",
    "contains_imaginary",
    "solve_complex",
    "solve_imaginary_arithmetic",
]
