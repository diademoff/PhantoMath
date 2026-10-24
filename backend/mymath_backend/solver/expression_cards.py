"""Bare expressions: factoring, expanding and cancelling as the app shows them.

the app treats ``x^2 - 9`` as "factor", ``(x + 2)(x - 3)`` as
"expand" and ``(x^2 - 1)/(x - 1)`` as "simplify" plus "excluded values", not as an equation.
Only the verified shapes are covered; anything else returns ``None`` and takes the old path.
"""

from __future__ import annotations

from math import isqrt
from typing import Any

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, SolveResult, Step
from .equations import poly_of
from .powers import solve_logarithm
from .quadratic_cards import _chain, _factor_rows, _Family, _mono, _node, _num
from .sympy_bridge import from_sympy, to_sympy


def _variable(node: CoreNode) -> str | None:
    names = {
        n.value
        for n in node.walk()
        if n.type is T.VARIABLE and n.value and n.value not in ("e", "π", "pi", "i")
    }
    return next(iter(names)) if len(names) == 1 else None


def _difference_formula() -> CoreNode:
    a, b, two = CoreNode.variable("a"), CoreNode.variable("b"), _num(2)
    return _node(
        T.EQUALS,
        _node(T.SUBTRACT, _node(T.POWER, a, two), _node(T.POWER, b, two)),
        _node(
            T.MULTIPLY,
            _node(T.BRACKET, _node(T.SUBTRACT, a, b)),
            _node(T.BRACKET, _node(T.ADD, a, b)),
        ),
    )


def _square_difference(node: CoreNode, var: str) -> list[SolveResult] | None:
    """``x^2 - k^2``: write ``k^2``, then factor by the formula."""
    if not (
        node.type is T.SUBTRACT
        and node.children[0].type is T.POWER
        and node.children[0].children[0].type is T.VARIABLE
        and node.children[0].children[1].type is T.CONSTANT
        and node.children[0].children[1].value == "2"
        and node.children[1].type is T.CONSTANT
        and (node.children[1].value or "").isdigit()
    ):
        return None
    c = int(node.children[1].value or 0)
    k = isqrt(c)
    if k < 2 or k * k != c:
        return None
    x = CoreNode.variable(var)
    written = _node(T.SUBTRACT, node.children[0], _node(T.POWER, _num(k), _num(2)))
    product = _node(
        T.MULTIPLY,
        _node(T.BRACKET, _node(T.SUBTRACT, x, _num(k))),
        _node(T.BRACKET, _node(T.ADD, x, _num(k))),
    )
    result = SolveResult()
    result.add_group("write_as_exp_short", Step(node, written, "write_as_num_arg", [_num(2)]))
    result.add_group(
        "factorise_call", Step(written, product, "using_factor", [_difference_formula()])
    )
    result.set_solution(product)
    return [result]


def _trinomial(node: CoreNode, var: str) -> list[SolveResult] | None:
    """``x^2 + b x + c`` with two different non-zero integer roots."""
    try:
        coefficients = poly_of(node, var)
    except SolveError:
        return None
    if set(coefficients) != {0, 1, 2} or coefficients[2] != 1:
        return None
    if coefficients[1].denominator != 1 or coefficients[0].denominator != 1:
        return None
    b, c = int(coefficients[1]), int(coefficients[0])
    d = b * b - 4 * c
    if d <= 0 or isqrt(d) ** 2 != d:
        return None
    family = _Family(var, 1, b, c)
    family.node = node
    result = SolveResult()
    rows = _factor_rows(family, result, None)
    if rows is None:
        return None
    result.set_solution(rows[0])
    return [result]


def _foil_terms(a: int, b: int, var: str) -> list[tuple[int, CoreNode]]:
    """``x*x + b x + a x + a*b`` as the app writes the cross product (|a|, |b| >= 2)."""
    x = CoreNode.variable(var)
    return [
        (1, _node(T.MULTIPLY, x, x)),
        (1 if b > 0 else -1, _mono(abs(b), 1, var)),
        (1 if a > 0 else -1, _mono(abs(a), 1, var)),
        (1 if a * b > 0 else -1, _node(T.MULTIPLY, _num(abs(a)), _num(abs(b)))),
    ]


def _bracket_product(node: CoreNode, var: str) -> list[SolveResult] | None:
    """FOIL and the distributive property for ``(x+a)(x+b)``, ``|a|, |b| >= 2``, ``a+b != 0``."""
    if node.type not in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) or len(node.children) != 2:
        return None
    ints: list[int] = []
    for bracket in node.children:
        if bracket.type is not T.BRACKET:
            return None
        inner = bracket.children[0]
        if not (
            inner.type in (T.ADD, T.SUBTRACT)
            and inner.children[0].type is T.VARIABLE
            and inner.children[0].value == var
            and inner.children[1].type is T.CONSTANT
            and (inner.children[1].value or "").isdigit()
        ):
            return None
        value = int(inner.children[1].value or 0)
        ints.append(value if inner.type is T.ADD else -value)
    a, b = ints
    if abs(a) < 2 or abs(b) < 2 or a + b == 0:
        return None
    x = CoreNode.variable(var)
    second = node.children[1]
    square = _node(T.POWER, x, _num(2))
    middle = a + b
    final_terms = [(1, square)]
    final_terms.append((1 if middle > 0 else -1, _mono(abs(middle), 1, var)))
    final_terms.append((1 if a * b > 0 else -1, _num(abs(a * b))))
    final = _chain(final_terms)
    terms = _foil_terms(a, b, var)
    crossed = _chain(terms)
    # FOIL
    foil = SolveResult()
    foil.add_group("mul_bracket_cross", Step(node, crossed, "mul_bracket_cross_each"))
    squared = _chain([(1, square), *terms[1:]])
    done = _chain([(1, square), *terms[1:3], (terms[3][0], _num(abs(a * b)))])
    foil.add_group(
        ["calculate_short", "calculate_short"],
        Step(crossed, squared, "product", subresult=_products_page(var, square)),
        Step(
            squared,
            done,
            "mul",
            subresult=_signed_product_page(terms[3][1], _num(abs(a * b)), same_sign=a * b > 0),
        ),
    )
    foil.add_group(
        "sum_suffix",
        Step(done, final, "sum_suffix", subresult=_collect_page(var, b, a)),
    )
    foil.set_solution(final)
    # distributive property: x(x+b) + a(x+b)
    spread = SolveResult()
    second_term = _node(T.MULTIPLY_IMPLICIT, _num(abs(a)), second)
    parts = _node(T.ADD if a > 0 else T.SUBTRACT, _node(T.MULTIPLY, x, second), second_term)
    spread.add_group(
        "mul_bracket_distributive_prop",
        Step(node, parts, "mul_bracket_cross_each_distributive"),
    )
    after_x = _chain(
        [
            (1, square),
            (1 if b > 0 else -1, _mono(abs(b), 1, var)),
            (1 if a > 0 else -1, second_term),
        ]
    )
    after_both = _chain([(1, square), *terms[1:3], (terms[3][0], _num(abs(a * b)))])
    x_opened = _chain(
        [
            (1, _node(T.MULTIPLY, x, x)),
            (1 if b > 0 else -1, _node(T.MULTIPLY, x, _mono(abs(b), 0, var))),
        ]
    )
    a_opened = _chain(
        [
            (1, _node(T.MULTIPLY, _num(abs(a)), x)),
            (1 if b > 0 else -1, _num(abs(a * b))),
        ]
    )
    spread.add_group(
        "remove_bracket_short",
        Step(
            parts,
            after_x,
            "mul_bracket",
            [x],
            subresult=_bracket_product_page(
                _node(T.MULTIPLY, x, second),
                x_opened,
                _chain([(1, square), (1 if b > 0 else -1, _mono(abs(b), 1, var))]),
                x,
                "product",
            ),
        ),
        Step(
            after_x,
            after_both,
            "mul_bracket",
            [_num(abs(a))],
            subresult=_bracket_product_page(
                second_term,
                a_opened,
                _chain([(1, _mono(abs(a), 1, var)), (1 if b > 0 else -1, _num(abs(a * b)))]),
                _num(abs(a)),
                "mul",
            ),
        ),
    )
    spread.add_group(
        "sum_suffix",
        Step(after_both, final, "sum_suffix", subresult=_collect_page(var, b, a)),
    )
    spread.set_solution(final)
    return [foil, spread]


def _products_page(var: str, squared: CoreNode) -> SolveResult:
    """Detail page for ``x·x``: implicit exponents, same-base rule, add the exponents."""
    one, x = _num(1), CoreNode.variable(var)
    first = _node(T.MULTIPLY, _node(T.POWER, x, one), x)
    second = _node(T.MULTIPLY, _node(T.POWER, x, one), _node(T.POWER, x, one))
    same = _node(T.POWER, x, _node(T.ADD, one, one))
    detail = SolveResult()
    detail.add_group(
        "pow_implicit_exp", Step(_node(T.MULTIPLY, x, x), first, "pow_implicit_exp", [one])
    )
    detail.add_group("pow_implicit_exp", Step(first, second, "pow_implicit_exp", [one]))
    detail.add_group("product", Step(second, same, "pow_same_base_mul"))
    detail.add_group("calculate_short", Step(same, squared, "add"))
    detail.set_solution(squared)
    return detail


def _collect_page(var: str, first: int, second: int) -> SolveResult:
    """Detail page for adding like terms: ``3x + 3x``, ``-3x + 2x``, ``x + x``."""
    x = CoreNode.variable(var)
    total = first + second
    one_x = _mono(1, 1, var)
    first_term = _mono(first, 1, var) if first >= 0 else _node(T.NEGATIVE, _mono(-first, 1, var))
    expression = _node(T.ADD if second >= 0 else T.SUBTRACT, first_term, _mono(abs(second), 1, var))
    grouped = _node(
        T.MULTIPLY,
        _node(T.BRACKET, _chain([(1, _num(first)), (1 if second > 0 else -1, _num(abs(second)))])),
        x,
    )
    total_node = _mono(total, 1, var) if total >= 0 else _node(T.NEGATIVE, _mono(-total, 1, var))
    detail = SolveResult()
    written = expression
    if abs(first) == 1:
        signed = _node(T.ADD if second > 0 else T.SUBTRACT, one_x, _mono(abs(second), 1, var))
        if first > 0:
            written = signed
            detail.add_group(
                "sum_suffix_add_one", Step(expression, written, "sum_suffix_add_one", [_num(1)])
            )
        else:
            written = _node(T.SUBTRACT, _node(T.NEGATIVE, one_x), _mono(abs(second), 1, var))
            detail.add_group(
                "sum_suffix_add_neg_one",
                Step(expression, written, "sum_suffix_add_neg_one", [_num(-1)]),
            )
    if abs(second) == 1:
        after = _node(T.ADD if second > 0 else T.SUBTRACT, _mono(abs(first), 1, var), one_x)
        if second > 0:
            detail.add_group(
                "sum_suffix_add_one", Step(written, after, "sum_suffix_add_one", [_num(1)])
            )
        else:
            detail.add_group(
                "sum_suffix_add_neg_one",
                Step(written, after, "sum_suffix_add_neg_one", [_num(-1)]),
            )
        written = after
    if first > 0 and second > 0:
        detail.add_group("sum_suffix_add_detail", Step(written, grouped, "sum_suffix_add_detail"))
        detail.add_group("calculate_short", Step(grouped, total_node, "add"))
    elif first < 0 and second < 0:
        detail.add_group("sum_suffix_detail", Step(written, grouped, "sum_suffix_detail"))
        detail.add_group("calculate_short", Step(grouped, total_node, "calc_diff"))
    else:
        detail.add_group("sum_suffix_detail", Step(written, grouped, "sum_suffix_detail"))
        detail.add_group("calculate_short", Step(grouped, total_node, "calc_sum"))
    if total == -1:
        detail.add_group(
            CoreRichText(type="sum_suffix_del_one", args=[_num(-1)]),
            Step(total_node, _node(T.NEGATIVE, x), "sum_suffix_del_neg_one", [_num(-1)]),
        )
    elif total == 1 and first != second:
        detail.add_group(
            CoreRichText(type="sum_suffix_del_one", args=[_num(1)]),
            Step(total_node, x, "sum_suffix_del_one", [_num(1)]),
        )
    detail.set_solution(total_node)
    return detail


def _like_terms_page(var: str, coefficient: int, total: CoreNode) -> SolveResult:
    """Detail page for ``3x + 3x`` (a special case of the general like-terms screen)."""
    del total
    return _collect_page(var, coefficient, coefficient)


def _power_page(base: CoreNode, exponent: CoreNode, value: CoreNode) -> SolveResult:
    """Detail page for ``3²``: repeated multiplication, then the product."""
    detail = SolveResult()
    power = _node(T.POWER, base, exponent)
    try:
        times = int(exponent.value or 0)
    except ValueError:
        times = 2
    product = base
    for _ in range(max(times - 1, 1)):
        product = _node(T.MULTIPLY, product, base)
    detail.add_group("pow_to_mul", Step(power, product, "pow_to_mul"))
    detail.add_group("calculate_short", Step(product, value, "mul"))
    detail.set_solution(value)
    return detail


def _bracket_product_page(
    source: CoreNode, each_term: CoreNode, final: CoreNode, coefficient: CoreNode, key: str
) -> SolveResult:
    """Detail page for ``2(x-3)``: distribute the factor, then compute the row."""
    detail = SolveResult()
    detail.add_group(
        "mul_bracket_each",
        Step(source, each_term, "mul_bracket_each", [coefficient]),
    )
    detail.add_group("calculate_short", Step(each_term, final, key))
    detail.set_solution(final)
    return detail


def _one_product_page(expression: CoreNode, value: CoreNode) -> SolveResult:
    """Multiplying by one: ``2x·1 = 2x``."""
    detail = SolveResult()
    detail.add_group("mul_with_one", Step(expression, value, "mul_with_one", [_num(1)]))
    detail.set_solution(value)
    return detail


def _plain_product_page(expression: CoreNode, value: CoreNode) -> SolveResult:
    """Multiplying two numbers: one row."""
    detail = SolveResult()
    detail.add_group("calculate_short", Step(expression, value, "mul"))
    detail.set_solution(value)
    return detail


def _signed_product_page(expression: CoreNode, value: CoreNode, *, same_sign: bool) -> SolveResult:
    """Detail page for a product with a negative factor (`mul_neg_pos` / `mul_neg_neg`)."""
    detail = SolveResult()
    key = "mul_neg_neg" if same_sign else "mul_neg_pos"
    detail.add_group(key, Step(expression, expression, key, [CoreNode.variable("+")]))
    detail.add_group("calculate_short", Step(expression, value, "mul"))
    detail.set_solution(value)
    return detail


def _square_of_sum(node: CoreNode, var: str) -> list[SolveResult] | None:
    """``(x+k)^2``, ``k >= 1``: the (a+b)^2 formula and the product of two brackets."""
    if not (
        node.type is T.POWER
        and node.children[1].type is T.CONSTANT
        and node.children[1].value == "2"
        and node.children[0].type is T.BRACKET
    ):
        return None
    inner = node.children[0].children[0]
    if not (
        inner.type is T.ADD
        and inner.children[0].type is T.VARIABLE
        and inner.children[0].value == var
        and inner.children[1].type is T.CONSTANT
        and (inner.children[1].value or "").isdigit()
        and int(inner.children[1].value or 0) >= 1
    ):
        return None
    k = int(inner.children[1].value or 0)
    x, kn, two = CoreNode.variable(var), _num(k), _num(2)
    square = _node(T.POWER, x, two)
    middle = _mono(2 * k, 1, var)
    final = _chain([(1, square), (1, middle), (1, _num(k * k))])
    # card 1: the formula
    a, b = CoreNode.variable("a"), CoreNode.variable("b")
    formula = _node(
        T.EQUALS,
        _node(T.POWER, _node(T.BRACKET, _node(T.ADD, a, b)), two),
        _chain(
            [
                (1, _node(T.POWER, a, two)),
                (1, _node(T.MULTIPLY_IMPLICIT, two, _node(T.MULTIPLY_IMPLICIT, a, b))),
                (1, _node(T.POWER, b, two)),
            ]
        ),
    )
    twice = _node(T.MULTIPLY, _mono(2, 1, var), kn)
    kk = _node(T.POWER, kn, two)
    written = _chain([(1, square), (1, twice), (1, kk)])
    by_formula = SolveResult()
    by_formula.add_group("expand_msg", Step(node, written, "using_expand", [formula]))
    multiplied = _chain([(1, square), (1, _mono(2 * k, 1, var)), (1, kk)])
    powered = final
    product_page = (
        _one_product_page(twice, _mono(2 * k, 1, var))
        if k == 1
        else _plain_product_page(twice, _mono(2 * k, 1, var))
    )
    stages = [Step(written, multiplied, "product", subresult=product_page)]
    if k == 1:
        stages.append(Step(multiplied, final, "pow_one", [_num(1)]))
    else:
        stages.append(
            Step(
                multiplied,
                powered,
                "pow",
                subresult=_power_page(_num(2), _num(k), _num(k * k)),
            )
        )
    by_formula.add_group(["calculate_short", "pow" if k == 1 else "find_value"], *stages)
    by_formula.set_solution(final)
    # card 2: write as a product of brackets and multiply them out
    bracket = _node(T.BRACKET, inner)
    product = _node(T.MULTIPLY, bracket, bracket)
    crossed = _chain(
        [
            (1, _node(T.MULTIPLY, x, x)),
            (1, _mono(k, 1, var)),
            (1, _mono(k, 1, var)),
            (1, _node(T.MULTIPLY, kn, kn) if k > 1 else kn),
        ]
    )
    squared = _chain(
        [(1, square), (1, _mono(k, 1, var)), (1, _mono(k, 1, var)), (1, crossed.children[1])]
    )
    by_product = SolveResult()
    by_product.add_group("write_as_product", Step(node, product, "write_as_product"))
    by_product.add_group("mul_bracket_cross", Step(product, crossed, "mul_bracket_cross_each"))
    row = [
        Step(
            crossed,
            squared,
            "product",
            subresult=_products_page(var, square),
        )
    ]
    if k > 1:
        done = _chain([(1, square), (1, _mono(k, 1, var)), (1, _mono(k, 1, var)), (1, _num(k * k))])
        row.append(
            Step(
                squared,
                done,
                "mul",
                subresult=_plain_product_page(_node(T.MULTIPLY, _num(k), _num(k)), _num(k * k)),
            )
        )
    else:
        done = squared
    by_product.add_group(["calculate_short", "calculate_short"][: len(row)], *row)
    by_product.add_group(
        "sum_suffix",
        Step(done, final, "sum_suffix", subresult=_like_terms_page(var, k, _mono(2 * k, 1, var))),
    )
    by_product.set_solution(final)
    return [by_formula, by_product, _pascal(node, k, var), _sigma(node, k, var)]


def _pascal(node: CoreNode, k: int, var: str) -> SolveResult:
    """``(x+k)^2`` through the coefficients 1 2 1 of Pascal's triangle."""
    x, kn, two, one, zero = CoreNode.variable(var), _num(k), _num(2), _num(1), _num(0)

    def pw(base: CoreNode, exponent: CoreNode) -> CoreNode:
        return _node(T.POWER, base, exponent)

    def m(*factors: CoreNode) -> CoreNode:
        return _node(T.MULTIPLY, *factors)

    def imp(c: CoreNode, base: CoreNode) -> CoreNode:
        return _node(T.MULTIPLY_IMPLICIT, c, base)

    def total(terms: list[CoreNode]) -> CoreNode:
        return _chain([(1, t) for t in terms])

    template = total(
        [m(CoreNode.variable("?"), pw(x, _num(2 - r)), pw(kn, _num(r))) for r in range(3)]
    )
    terms = [
        m(imp(one, pw(x, two)), pw(kn, zero)),
        m(imp(two, x), pw(kn, one)),
        m(imp(one, pw(x, zero)), pw(kn, two)),
    ]
    terms[1] = m(imp(two, pw(x, one)), pw(kn, one))
    result = SolveResult()
    start = _node(T.POWER, _node(T.BRACKET, _node(T.ADD, x, kn)), two)
    result.add_group(
        "expand_binomial_triangle",
        Step(start, template, "expand_binomial_triangle", [x, kn, two, zero]),
    )
    result.add_group(
        "coeff_sub",
        Step(
            template,
            total(terms),
            "expand_binomial_triangle_substitute",
            [two, total([one, two, one])],
        ),
    )
    mono, square = _mono(2 * k, 1, var), _num(k * k)

    def run(title: str, ops: list[tuple[Any, ...]]) -> None:
        stages = []
        for index, new, key, args, *sub in ops:
            before = total(terms)
            terms[index] = new
            stages.append(Step(before, total(terms), key, args, subresult=sub[0] if sub else None))
        result.add_group(title, *stages)

    x2, kk = pw(x, two), pw(kn, two)
    if k == 1:
        run(
            "eval_pow_plural",
            [
                (0, m(x2, pw(kn, zero)), "mul_with_one", [one]),
                (0, m(x2, one), "pow_one", [one]),
                (1, m(imp(two, x), pw(kn, one)), "pow_with_one", [one]),
                (1, m(imp(two, x), one), "pow_one", [one]),
                (2, m(one, one, kk), "pow_with_zero", [zero, one]),
                (2, m(one, one, one), "pow_one", [one]),
            ],
        )
        run(
            "product_plural",
            [
                (0, x2, "mul_with_one", [one]),
                (1, imp(two, x), "mul_with_one", [one]),
                (2, m(one, one), "mul_with_one", [one]),
                (2, one, "mul_with_one", [one]),
            ],
        )
    else:
        run(
            "eval_pow_plural",
            [
                (0, m(x2, pw(kn, zero)), "mul_with_one", [one]),
                (2, m(pw(x, zero), kk), "mul_with_one", [one]),
                (0, m(x2, one), "pow_with_zero", [zero, one]),
                (1, m(imp(two, x), pw(kn, one)), "pow_with_one", [one]),
                (1, m(imp(two, x), kn), "pow_with_one", [one]),
                (2, m(one, kk), "pow_with_zero", [zero, one]),
            ],
        )
        twice = m(imp(two, x), kn)
        run(
            "product_plural",
            [
                (0, x2, "mul_with_one", [one]),
                (2, kk, "mul_with_one", [one]),
                (1, mono, "product", [], _plain_product_page(twice, mono)),
                (2, square, "pow", [], _power_page(kn, two, square)),
            ],
        )
    result.set_solution(total(terms))
    return result


def _sigma(node: CoreNode, k: int, var: str) -> SolveResult:
    """``(x+k)^2`` as the binomial sum ``sum C(2, r) x^(2-r) k^r``."""
    x, r = CoreNode.variable(var), CoreNode.variable("r")
    a, b, n = x, _num(k), _num(2)
    general = _node(
        T.EQUALS,
        _node(
            T.POWER,
            _node(T.BRACKET, _node(T.ADD, CoreNode.variable("a"), CoreNode.variable("b"))),
            CoreNode.variable("n"),
        ),
        CoreNode.variable("Σ"),
    )
    body = _node(
        T.MULTIPLY,
        _node(T.CHOOSE_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT, n, r),
        _node(T.POWER, x, _node(T.SUBTRACT, n, r)),
        _node(T.POWER, b, r),
    )
    summed = _node(T.SIGMA_DEFINITE, r, _num(0), n, body)
    result = SolveResult()
    result.header = "rewrite_using_sigma"
    result.add_group("expand_sigma_simple", Step(node, summed, "expand_sigma", [general, a, b, n]))
    result.set_solution(summed)
    return result


def _square_of_difference(node: CoreNode, var: str) -> list[SolveResult] | None:
    """``(x-k)^2``, ``k >= 2``: the four cards of ``(x+k)^2`` with the signs the app shows."""
    if not (
        node.type is T.POWER
        and node.children[1].type is T.CONSTANT
        and node.children[1].value == "2"
        and node.children[0].type is T.BRACKET
    ):
        return None
    inner = node.children[0].children[0]
    if not (
        inner.type is T.SUBTRACT
        and inner.children[0].type is T.VARIABLE
        and inner.children[0].value == var
        and inner.children[1].type is T.CONSTANT
        and (inner.children[1].value or "").isdigit()
        and int(inner.children[1].value or 0) >= 2
    ):
        return None
    k = int(inner.children[1].value or 0)
    x, kn, two = CoreNode.variable(var), _num(k), _num(2)
    bk = _node(T.BRACKET, _node(T.NEGATIVE, kn))
    x2, kk, mk, mono = (
        _node(T.POWER, x, two),
        _node(T.POWER, kn, two),
        _mono(k, 1, var),
        _mono(2 * k, 1, var),
    )
    final = _chain([(1, x2), (-1, mono), (1, _num(k * k))])

    def m(*factors: CoreNode) -> CoreNode:
        return _node(T.MULTIPLY, *factors)

    def imp(c: CoreNode, base: CoreNode) -> CoreNode:
        return _node(T.MULTIPLY_IMPLICIT, c, base)

    def pw(base: CoreNode, exponent: CoreNode) -> CoreNode:
        return _node(T.POWER, base, exponent)

    # card 1: the formula (a-b)^2 = a^2 - 2ab + b^2
    a, b = CoreNode.variable("a"), CoreNode.variable("b")
    formula = _node(
        T.EQUALS,
        pw(_node(T.BRACKET, _node(T.SUBTRACT, a, b)), two),
        _chain([(1, pw(a, two)), (-1, imp(two, imp(a, b))), (1, pw(b, two))]),
    )
    twice = m(imp(two, x), kn)
    written = _chain([(1, x2), (-1, twice), (1, kk)])
    by_formula = SolveResult()
    by_formula.add_group("expand_msg", Step(node, written, "using_expand", [formula]))
    multiplied = _chain([(1, x2), (-1, mono), (1, kk)])
    by_formula.add_group(
        ["calculate_short", "find_value"],
        Step(
            written,
            multiplied,
            "product",
            subresult=_signed_product_page(twice, mono, same_sign=False),
        ),
        Step(multiplied, final, "pow", subresult=_power_page(_num(2), _num(k), _num(k * k))),
    )
    by_formula.set_solution(final)
    # card 2: brackets multiplied out
    product = m(_node(T.BRACKET, inner), _node(T.BRACKET, inner))
    cross = m(kn, bk)
    crossed = _chain([(1, m(x, x)), (-1, mk), (-1, mk), (-1, cross)])
    squared = _chain([(1, x2), (-1, mk), (-1, mk), (-1, cross)])
    done = _chain([(1, x2), (-1, mk), (-1, mk), (1, _num(k * k))])
    by_product = SolveResult()
    by_product.add_group("write_as_product", Step(node, product, "write_as_product"))
    by_product.add_group("mul_bracket_cross", Step(product, crossed, "mul_bracket_cross_each"))
    by_product.add_group(
        ["calculate_short", "calculate_short"],
        Step(crossed, squared, "product", subresult=_products_page(var, x2)),
        Step(
            squared,
            done,
            "mul",
            subresult=_signed_product_page(cross, _num(k * k), same_sign=True),
        ),
    )
    by_product.add_group(
        "sum_suffix",
        Step(
            done,
            final,
            "sum_suffix",
            subresult=_like_terms_page(var, -k, _mono(-2 * k, 1, var)),
        ),
    )
    by_product.set_solution(final)
    return [
        by_formula,
        by_product,
        _pascal_difference(node, k, var),
        _sigma_difference(node, k, var),
    ]


def _pascal_difference(node: CoreNode, k: int, var: str) -> SolveResult:
    """Pascal's triangle for ``(x-k)^2``: the base is the bracket ``(-k)``."""
    x, kn, one, two, zero = CoreNode.variable(var), _num(k), _num(1), _num(2), _num(0)
    bk = _node(T.BRACKET, _node(T.NEGATIVE, kn))

    def m(*factors: CoreNode) -> CoreNode:
        return _node(T.MULTIPLY, *factors)

    def imp(c: CoreNode, base: CoreNode) -> CoreNode:
        return _node(T.MULTIPLY_IMPLICIT, c, base)

    def pw(base: CoreNode, exponent: CoreNode) -> CoreNode:
        return _node(T.POWER, base, exponent)

    def total(terms: list[CoreNode]) -> CoreNode:
        return _chain([(-1, t.children[0]) if t.type is T.NEGATIVE else (1, t) for t in terms])

    x2, kk = pw(x, two), pw(kn, two)
    template = total(
        [m(CoreNode.variable("?"), pw(x, _num(2 - r)), pw(bk, _num(r))) for r in range(3)]
    )
    terms = [
        m(imp(one, x2), pw(bk, zero)),
        m(imp(two, pw(x, one)), pw(bk, one)),
        m(imp(one, pw(x, zero)), pw(bk, two)),
    ]
    result = SolveResult()
    start = _node(T.POWER, _node(T.BRACKET, _node(T.SUBTRACT, x, kn)), two)
    result.add_group(
        "expand_binomial_triangle",
        Step(start, template, "expand_binomial_triangle", [x, _node(T.NEGATIVE, kn), two, zero]),
    )
    result.add_group(
        "coeff_sub",
        Step(
            template,
            total(terms),
            "expand_binomial_triangle_substitute",
            [two, total([one, two, one])],
        ),
    )

    def run(title: list[str], ops: list[tuple[Any, ...]]) -> None:
        stages = []
        for index, new, key, args, *sub in ops:
            before = total(terms)
            terms[index] = new
            stages.append(Step(before, total(terms), key, args, subresult=sub[0] if sub else None))
        result.add_group(title, *stages)

    run(
        ["eval_pow_plural", "sign_find_short"],
        [
            (0, m(x2, pw(bk, zero)), "mul_with_one", [one]),
            (2, m(pw(x, zero), pw(bk, two)), "mul_with_one", [one]),
            (0, m(x2, one), "pow_with_zero", [zero, one]),
            (1, m(imp(two, x), pw(bk, one)), "pow_with_one", [one]),
            (1, m(imp(two, x), bk), "pow_with_one", [one]),
            (2, m(one, pw(bk, two)), "pow_with_zero", [zero, one]),
            (2, m(one, kk), "pow_even", []),
        ],
    )
    mono = _mono(2 * k, 1, var)
    negative = _node(T.NEGATIVE, m(imp(two, x), kn))
    run(
        ["product_plural"],
        [
            (0, x2, "mul_with_one", [one]),
            (2, kk, "mul_with_one", [one]),
            (1, negative, "mul_pos_neg", [negative]),
            (
                1,
                _node(T.NEGATIVE, mono),
                "product",
                [],
                _signed_product_page(negative.children[0], mono, same_sign=False),
            ),
            (2, _num(k * k), "pow", [], _power_page(kn, _num(2), _num(k * k))),
        ],
    )
    result.set_solution(total(terms))
    return result


def _sigma_difference(node: CoreNode, k: int, var: str) -> SolveResult:
    """Subtraction as adding the opposite, then the binomial sum."""
    x, r, n = CoreNode.variable(var), CoreNode.variable("r"), _num(2)
    bk = _node(T.BRACKET, _node(T.NEGATIVE, _num(k)))
    sum_form = _node(T.POWER, _node(T.BRACKET, _node(T.ADD, x, bk)), n)
    general = _node(
        T.EQUALS,
        _node(
            T.POWER,
            _node(T.BRACKET, _node(T.ADD, CoreNode.variable("a"), CoreNode.variable("b"))),
            CoreNode.variable("n"),
        ),
        CoreNode.variable("Σ"),
    )
    body = _node(
        T.MULTIPLY,
        _node(T.CHOOSE_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT, n, r),
        _node(T.POWER, x, _node(T.SUBTRACT, n, r)),
        _node(T.POWER, bk, r),
    )
    summed = _node(T.SIGMA_DEFINITE, r, _num(0), n, body)
    result = SolveResult()
    result.add_group("sub_as_add", Step(node, sum_form, "sub_as_add"))
    result.add_group(
        "expand_sigma_simple", Step(sum_form, summed, "expand_sigma", [general, x, bk, n])
    )
    result.set_solution(summed)
    return result


def _signed_terms(node: CoreNode) -> list[tuple[int, CoreNode]] | None:
    """``a + b - c`` as ``[(+1, a), (+1, b), (-1, c)]``, or ``None`` for anything else."""
    if node.type is T.ADD or node.type is T.SUBTRACT:
        left = _signed_terms(node.children[0])
        if left is None or len(node.children) != 2:
            return None
        return [*left, (1 if node.type is T.ADD else -1, node.children[1])]
    return [(1, node)]


def _monomial_term(term: CoreNode, var: str) -> tuple[int, int] | None:
    """``c x^k`` with an integer ``c >= 1`` written as ``x``, ``c x``, ``c x^k``; ``(c, k)``."""
    x = CoreNode.variable(var)
    if term.type is T.MULTIPLY_IMPLICIT and len(term.children) == 2:
        coefficient, power = term.children
        if coefficient.type is T.CONSTANT and (coefficient.value or "").isdigit():
            inner = _monomial_term(power, var)
            return (int(coefficient.value or 0) * inner[0], inner[1]) if inner else None
        return None
    if term.structural_eq(x):
        return 1, 1
    if (
        term.type is T.POWER
        and term.children[0].structural_eq(x)
        and term.children[1].type is T.CONSTANT
        and (term.children[1].value or "").isdigit()
    ):
        return 1, int(term.children[1].value or 0)
    return None


def _like_terms(node: CoreNode, var: str) -> list[SolveResult] | None:
    """``2x + 3x``: group the like terms by their coefficients, then add the numbers."""
    signed = _signed_terms(node)
    if signed is None or len(signed) < 2:
        return None
    parsed = [(sign, _monomial_term(term, var)) for sign, term in signed]
    if any(m is None for _, m in parsed) or len({m[1] for _, m in parsed if m}) != 1:
        return None
    degree = next(m[1] for _, m in parsed if m)
    coefficients = [(sign, m[0]) for sign, m in parsed if m]
    total = sum(sign * c for sign, c in coefficients)
    shown = _chain([(sign, _num(c)) for sign, c in coefficients])
    power = _mono(1, degree, var)
    grouped = _node(T.MULTIPLY_IMPLICIT, _node(T.BRACKET, shown), power)
    result = (
        _chain([(1 if total >= 0 else -1, _mono(abs(total), degree, var))]) if total else _num(0)
    )
    kinds = {sign for sign, _ in coefficients[1:]}
    key = (
        "sum_suffix_add_detail"
        if kinds == {1}
        else "sum_suffix_sub_detail"
        if kinds == {-1}
        else "sum_suffix_detail"
    )
    card = SolveResult()
    card.add_group("sum_suffix", Step(node, grouped, key))
    card.add_group("calculate_short", Step(grouped, result, "add" if kinds == {1} else "sub"))
    card.set_solution(result)
    return [card]


def _cancel_fraction(node: CoreNode, var: str) -> list[SolveResult] | None:
    """``(x^2 - k^2) / (x - k)``: factor and cancel, plus the excluded value ``x = k``."""
    if node.type is not T.FRACTION or len(node.children) != 2:
        return None
    top, bottom = node.children
    if not (
        top.type is T.SUBTRACT
        and top.children[0].type is T.POWER
        and top.children[1].type is T.CONSTANT
        and bottom.type is T.SUBTRACT
        and bottom.children[0].type is T.VARIABLE
        and bottom.children[1].type is T.CONSTANT
        and (top.children[1].value or "").isdigit()
        and bottom.children[1].value is not None
        and int(top.children[1].value or 0) == int(bottom.children[1].value or 0) ** 2
        and int(bottom.children[1].value or 0) >= 1
    ):
        return None
    k = int(bottom.children[1].value or 0)
    x = CoreNode.variable(var)
    plus = _node(T.ADD, x, _num(k))
    factored = _node(
        T.FRACTION,
        _node(T.MULTIPLY, _node(T.BRACKET, bottom), _node(T.BRACKET, plus)),
        bottom,
    )
    written = _node(T.SUBTRACT, top.children[0], _node(T.POWER, _num(k), _num(2)))
    detail = SolveResult()
    detail.add_group("write_as_num_arg", Step(top, written, "write_as_num_arg", [_num(2)]))
    detail.add_group(
        "factorise_call",
        Step(written, factored.children[0], "using_factor", [_difference_formula()]),
    )
    detail.set_solution(factored.children[0])
    simplify = SolveResult()
    simplify.add_group(
        "factorise_call",
        Step(node, factored, "using_factor", [_difference_formula()], subresult=detail),
    )
    simplify.add_group("frac_reduce_frac", Step(factored, plus, "frac_reduce_frac_alg", [bottom]))
    simplify.set_solution(plus)
    excluded = SolveResult()
    equation = _node(T.EQUALS, bottom, _num(0))
    excluded.add_group(
        CoreRichText(type="excluded_values_denom_smpl", args=[_num(0)]),
        Step(node, equation, "excluded_values_denom", [_num(0)]),
    )
    solved = _node(T.EQUALS, x, _num(k))
    balanced = _node(T.EQUALS, _node(T.ADD, bottom, _num(k)), _node(T.ADD, _num(0), _num(k)))
    swap = SolveResult()
    swap.add_group("rel_swap_right_const", Step(equation, balanced, "rel_swap_right_const"))
    swap.add_group(
        "remove_opposites",
        Step(balanced, solved, "sub_with_self_remove_num"),
        Step(balanced, solved, "add_with_zero", [_num(0)]),
    )
    swap.set_solution(solved)
    excluded.add_group(
        "rel_move_right_const_msg",
        Step(equation, solved, "rel_move_right_const_eq", subresult=swap),
    )
    excluded.set_solution(solved)
    return [simplify, excluded]


def _log_base_node(node: CoreNode) -> CoreNode | None:
    """Основание логарифма как узел (``10`` у ``lg``, ``e`` у ``ln``)."""
    if node.type is T.LOG and len(node.children) == 2:
        return node.children[1]
    if node.type is T.LOG10:
        return _num(10)
    if node.type is T.LN:
        return CoreNode.constant("e")
    return None


def _log_argument(node: CoreNode) -> CoreNode | None:
    """Аргумент логарифма (``None``, если узел — не логарифм)."""
    if node.type is T.LOG and len(node.children) == 2:
        return node.children[0]
    if node.type in (T.LOG10, T.LN) and len(node.children) == 1:
        return node.children[0]
    return None


def _log_terms(node: CoreNode) -> list[tuple[int, CoreNode]] | None:
    """``[(знак, логарифм), …]`` для ``log_b a ± log_b c ± …`` с одним основанием."""
    terms: list[tuple[int, CoreNode]] = []

    def collect(part: CoreNode, sign: int) -> bool:
        if part.type is T.ADD and len(part.children) == 2:
            return collect(part.children[0], sign) and collect(part.children[1], sign)
        if part.type is T.SUBTRACT and len(part.children) == 2:
            return collect(part.children[0], sign) and collect(part.children[1], -sign)
        if _log_argument(part) is None:
            return False
        terms.append((sign, part))
        return True

    if not collect(node, 1) or len(terms) < 2:
        return None
    base = _log_base_node(terms[0][1])
    for _, part in terms[1:]:
        other = _log_base_node(part)
        if base is None or other is None or not base.structural_eq(other):
            return None
    return terms


def _product(nodes: list[CoreNode]) -> CoreNode | None:
    """Произведение узлов (``None`` для пустого списка)."""
    result = None
    for part in nodes:
        result = part if result is None else _node(T.MULTIPLY, result, part)
    return result


def _log_sum_rule(template: CoreNode, minus: bool) -> CoreNode:
    """``log a ± log b = log(ab)`` / ``log(a/b)`` — подпись к преобразованию."""
    a, x, y = CoreNode.variable("a"), CoreNode.variable("x"), CoreNode.variable("y")

    def log_of(argument: CoreNode) -> CoreNode:
        if template.type is T.LOG10:
            return _node(T.LOG10, argument)
        if template.type is T.LN:
            return _node(T.LN, argument)
        return _node(T.LOG, argument, a)

    joined = _node(T.FRACTION, x, y) if minus else _node(T.BRACKET, _node(T.MULTIPLY, x, y))
    return _node(
        T.EQUALS,
        _node(T.SUBTRACT if minus else T.ADD, log_of(x), log_of(y)),
        log_of(joined),
    )


def _log_like(template: CoreNode, argument: CoreNode) -> CoreNode:
    """Тот же вид логарифма (``lg``/``ln``/``log_b``) с другим аргументом."""
    if argument.type is T.MULTIPLY:
        # log₆ 4·9 would read as (log₆ 4)·9: the joined product is one argument
        argument = _node(T.BRACKET, argument)
    if template.type is T.LOG10:
        return _node(T.LOG10, argument)
    if template.type is T.LN:
        # sympy folds e²·e³ into exp(5); write it as e⁵ so «ln eᵗ» stays recognisable
        if argument.type is T.EXP:
            argument = _node(T.POWER, CoreNode.constant("e"), argument.children[0])
        return _node(T.LN, argument)
    return _node(T.LOG, argument, template.children[1])


def _log_sum(node: CoreNode) -> list[SolveResult] | None:
    """``log_b a ± log_b c ± …``: join the logarithms, then evaluate the result.

    the app: one row joins them with the product/quotient rule, then the
    joined logarithm goes through the ordinary «write as a power» rows.
    """
    terms = _log_terms(node)
    if terms is None:
        return None
    template = terms[0][1]
    positive = [_log_argument(part) for sign, part in terms if sign > 0]
    negative = [_log_argument(part) for sign, part in terms if sign < 0]
    product = _product([part for part in positive if part is not None])
    divisor = _product([part for part in negative if part is not None])
    if divisor is not None:
        argument, minus = _node(T.FRACTION, product or _num(1), divisor), True
    else:
        if product is None:
            return None
        argument, minus = product, False
    joined = _log_like(template, argument)
    try:
        value = to_sympy(argument)
    except SolveError:
        value = None
    evaluated = from_sympy(sympy.simplify(value)) if value is not None and value.is_number else None
    final = _log_like(template, evaluated) if evaluated is not None else joined
    detail = SolveResult()
    detail.header = "calculate_expressions"
    detail.add_group("simplify", Step(node, joined, "using_sim", [_log_sum_rule(template, minus)]))
    if evaluated is not None:
        detail.add_group(
            "calculate_short",
            Step(
                joined,
                final,
                "frac_reduce_frac_num" if minus else "mul",
                [divisor] if minus and divisor is not None else [],
            ),
        )
    detail.set_solution(final)
    card = SolveResult()
    card.header = "simplify_msg"
    key = "log_sum_resolve_minus" if minus else "log_sum_resolve_plus"
    card.add_group(key, Step(node, final, key, subresult=detail))
    answer = solve_logarithm(final, SolveContext(result=card, variables=[]))
    card.set_solution(answer)
    return [card]


def _derivative_factor(node: CoreNode, var: str) -> list[SolveResult] | None:
    """``d/dx(x^n) * f``: the derivative is taken by the power rule, then the product is tidied."""
    if node.type not in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) or len(node.children) != 2:
        return None
    first, factor = node.children
    if first.type is not T.DERIVATION1_DIFF or any(
        n.type is T.DERIVATION1_DIFF for n in factor.walk()
    ):
        return None
    variable, power = first.children
    if not (
        variable.type is T.VARIABLE
        and variable.value == var
        and power.type is T.POWER
        and power.children[0].structural_eq(variable)
        and power.children[1].type is T.CONSTANT
        and (power.children[1].value or "").isdigit()
        and int(power.children[1].value or 0) >= 2
    ):
        return None
    n = int(power.children[1].value or 0)
    x, one = CoreNode.variable(var), _num(1)
    letter = CoreNode.variable("n")
    rule = _node(
        T.EQUALS,
        _node(T.DERIVATION1_DIFF, x, _node(T.POWER, x, letter)),
        _node(
            T.MULTIPLY,
            letter,
            _node(T.POWER, x, _node(T.SUBTRACT, letter, one)),
        ),
    )

    def times(term: CoreNode) -> CoreNode:
        return _node(T.MULTIPLY, term, factor)

    unevaluated = _node(
        T.MULTIPLY_IMPLICIT, _num(n), _node(T.POWER, x, _node(T.SUBTRACT, _num(n), one))
    )
    reduced = _node(T.MULTIPLY_IMPLICIT, _num(n), _node(T.POWER, x, _num(n - 1)))
    result = SolveResult()
    result.add_group("derive", Step(node, times(unevaluated), "derive_table_desc", [rule]))
    if n == 2:
        result.add_group("calculate_short", Step(times(unevaluated), times(reduced), "sub"))
        final = times(_mono(2, 1, var))
        result.add_group("pow", Step(times(reduced), final, "pow_with_one", [one]))
    else:
        final = times(reduced)
        result.add_group("calculate_short", Step(times(unevaluated), final, "sub"))
    result.set_solution(final)
    return [result]


def _cube_cards(node: CoreNode, var: str) -> list[SolveResult] | None:
    from .cube_cards import cube_methods

    return cube_methods(node, var)


def methods(node: CoreNode) -> tuple[str, list[SolveResult]] | None:
    """``(kind, cards)`` for a bare expression (kind ``factor`` or ``other``), else ``None``."""
    if (logs := _log_sum(node)) is not None:
        return "other", logs
    var = _variable(node)
    if var is None:
        return None
    for kind, builder in (
        ("other", _derivative_factor),
        ("other", _cube_cards),
        ("other", _cancel_fraction),
        ("other", _like_terms),
        ("other", _bracket_product),
        ("other", _square_of_sum),
        ("other", _square_of_difference),
        ("factor", _square_difference),
        ("factor", _trinomial),
    ):
        cards = builder(node, var)
        if cards:
            return kind, cards
    return None


__all__ = ["methods"]
