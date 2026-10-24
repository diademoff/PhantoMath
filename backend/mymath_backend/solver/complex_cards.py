"""``(a + i)(c - i)``: the FOIL and distributive-property cards the app shows.

Worked out for ``(2+i)(1-i)``; positive integers ``a`` and ``c`` follow the same rows.
Anything else (other signs, ``bi`` with ``b > 1``, three factors) is left to the general path.
"""

from __future__ import annotations

from fractions import Fraction

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveResult, Step
from .complex import (
    _complex_node,
    _iterm,
    _sum_suffix_detail,
    solve_imaginary_arithmetic,
)
from .complex import (
    _parts as _complex_parts,
)
from .methods import method_provider
from .quadratic_cards import _SIGNS, _chain, _detail, _num


def _node(kind: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(kind, *children)


def _is_integer(node: CoreNode) -> bool:
    return node.type is T.CONSTANT and (node.value or "").isdigit() and node.value != "0"


def _is_unit(node: CoreNode) -> bool:
    """``i`` as the keyboard sends it (a constant) or as the ``imag`` protocol token writes it."""
    if node.type is T.CONSTANT:
        return node.value == "i"
    return node.type is T.IMAGINARY and all(c.type is T.EMPTY for c in node.children)


def _unit() -> CoreNode:
    return CoreNode.constant("i")


def _times_i(coefficient: int) -> CoreNode:
    return _unit() if coefficient == 1 else _node(T.MULTIPLY_IMPLICIT, _num(coefficient), _unit())


def _parts(node: CoreNode) -> tuple[int, int] | None:
    """``(a, c)`` of ``(a + i) * (c - i)``, or ``None`` outside the verified family."""
    if node.type not in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) or len(node.children) != 2:
        return None
    first, second = node.children
    if first.type is not T.BRACKET or second.type is not T.BRACKET:
        return None
    left, right = first.children[0], second.children[0]
    if not (
        left.type is T.ADD
        and right.type is T.SUBTRACT
        and _is_integer(left.children[0])
        and _is_unit(left.children[1])
        and _is_integer(right.children[0])
        and _is_unit(right.children[1])
    ):
        return None
    return int(left.children[0].value or 0), int(right.children[0].value or 0)


def _tail(result: SolveResult, previous: CoreNode, a: int, c: int) -> CoreNode:
    """The rows shared by both cards: i*i, by definition, brackets, then the sums."""
    head = [(1, _num(a * c)), (-1, _times_i(a)), (1, _times_i(c))]
    squared = _chain([*head, (-1, _node(T.POWER, _unit(), _num(2)))])
    product = _node(T.MULTIPLY, _unit(), _unit())
    result.add_group(
        "calculate_short",
        Step(
            previous,
            squared,
            "product",
            subresult=_detail(product, _node(T.POWER, _unit(), _num(2))),
        ),
    )
    law = _node(T.EQUALS, _node(T.POWER, _unit(), _num(2)), _num(-1))
    definition = _chain([*head, (-1, _node(T.BRACKET, _num(-1)))])
    result.add_group("calculate_short", Step(squared, definition, "by_definition", [law]))
    opened = _chain([*head, (1, _num(1))])
    result.add_group("remove_bracket_short", Step(definition, opened, "neg_neg_arg", [_SIGNS[1]]))
    real = a * c + 1
    summed = _chain([(1, _num(real)), (-1, _times_i(a)), (1, _times_i(c))])
    imaginary = c - a
    final_terms: list[tuple[int, CoreNode]] = [(1, _num(real))]
    if imaginary:
        final_terms.append((1 if imaginary > 0 else -1, _times_i(abs(imaginary))))
    final = _chain(final_terms)
    detail = SolveResult()
    detail.add_group("sum_suffix", Step(summed, final, "sum_suffix"))
    detail.set_solution(final)
    result.add_group(
        ["calculate_short", "sum_suffix"],
        Step(opened, summed, "add"),
        Step(summed, final, "sum_suffix", subresult=detail),
    )
    result.set_solution(final)
    return final


@method_provider(T.MULTIPLY)
def complex_product_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """FOIL and the distributive property for ``(a + i)(c - i)``; ``[]`` for everything else."""
    _ = variables
    parts = _parts(node)
    if parts is None:
        if len(node.children) != 2:
            return []
        left, right = _complex_parts(node.children[0]), _complex_parts(node.children[1])
        if left is None or right is None:
            return []
        return _general_product_cards(node, left, right) or []
    a, c = parts
    head = [(1, _num(a * c)), (-1, _times_i(a)), (1, _times_i(c))]

    foil = SolveResult()
    crossed = _chain([*head, (-1, _node(T.MULTIPLY, _unit(), _unit()))])
    foil.add_group("mul_bracket_cross", Step(node, crossed, "mul_bracket_cross_each"))
    _tail(foil, crossed, a, c)

    distributive = SolveResult()
    second = node.children[1]
    spread = _node(
        T.ADD,
        _node(T.MULTIPLY_IMPLICIT, _num(a), second),
        _node(T.MULTIPLY, _unit(), second),
    )
    distributive.add_group(
        "mul_bracket_distributive_prop", Step(node, spread, "mul_bracket_cross_each_distributive")
    )
    after_first = _chain(
        [(1, _num(a * c)), (-1, _times_i(a)), (1, _node(T.MULTIPLY, _unit(), second))]
    )
    after_second = _chain([*head, (-1, _node(T.POWER, _unit(), _num(2)))])
    distributive.add_group(
        "remove_bracket_short",
        Step(spread, after_first, "mul_bracket", [_num(a)]),
        Step(
            after_first,
            after_second,
            "mul_bracket",
            [_unit()],
            subresult=_detail(_node(T.MULTIPLY, _unit(), second), after_second),
        ),
    )
    _tail_after_square(distributive, after_second, a, c)
    return [foil, distributive]


def _general_product_cards(
    node: CoreNode, left: tuple[Fraction, Fraction], right: tuple[Fraction, Fraction]
) -> list[SolveResult] | None:
    """FOIL + distribution for ``(a+bi)(c+di)`` with numeric integer parts."""
    a, b = left
    c, d = right
    if not all(isinstance(value, Fraction) and value.denominator == 1 for value in (a, b, c, d)):
        return None
    foil = SolveResult()
    scratch = SolveContext(result=foil)
    answer = solve_imaginary_arithmetic(node, scratch)
    foil.set_solution(answer)

    second = _complex_node(c, d)
    imaginary_factor = _iterm(b)
    spread = _node(
        T.ADD,
        _node(T.MULTIPLY, _num(int(a)), second),
        _node(T.MULTIPLY, imaginary_factor, second),
    )
    card = SolveResult()
    card.add_group(
        "mul_bracket_distributive_prop",
        Step(node, spread, "mul_bracket_cross_each_distributive"),
    )
    current = spread
    stages: list[Step] = []
    if a == 1:
        reduced_first = second
        after_one = _node(T.ADD, reduced_first, _node(T.MULTIPLY, imaginary_factor, second))
        stages.append(Step(current, after_one, "mul_with_one", [_num(1)]))
        current = after_one
    product_i = _iterm(b * c)
    product_square = _node(T.MULTIPLY, _num(int(b * d)), _node(T.POWER, _unit(), _num(2)))
    after_bracket = _node(T.ADD, second, _node(T.ADD, product_i, product_square))
    detail = SolveResult()
    detail.add_group(
        CoreRichText(type="mul_bracket_each_short", args=[imaginary_factor]),
        Step(
            _node(T.MULTIPLY, imaginary_factor, second),
            _node(T.ADD, product_i, product_square),
            "mul_bracket_each",
            [imaginary_factor],
        ),
    )
    detail.add_group(
        "calculate_short",
        Step(
            _node(T.ADD, product_i, product_square),
            _node(T.ADD, product_i, product_square),
            "product",
        ),
        Step(
            _node(T.ADD, product_i, product_square),
            _node(T.ADD, product_i, product_square),
            "product",
        ),
    )
    detail.set_solution(after_bracket)
    stages.append(
        Step(
            current,
            after_bracket,
            "mul_bracket",
            [imaginary_factor],
            subresult=detail,
        )
    )
    current = after_bracket
    law = _node(T.EQUALS, _node(T.POWER, _unit(), _num(2)), _num(-1))
    defined_square = _node(T.MULTIPLY, _num(int(b * d)), _num(-1))
    after_definition = _node(T.ADD, second, _node(T.ADD, product_i, defined_square))
    stages.append(Step(current, after_definition, "by_definition", [law]))
    current = after_definition
    product_value = -b * d
    after_negative = _node(T.ADD, second, _node(T.ADD, product_i, _num(int(product_value))))
    negative_detail = SolveResult()
    negative_detail.add_group(
        "neg_mul_msg",
        Step(
            _node(T.MULTIPLY, _num(-1), _num(int(b * d))),
            _node(T.MULTIPLY, _num(1), _num(int(-b * d))),
            "mul_neg_neg",
            [
                _node(
                    T.EQUALS,
                    _node(T.MULTIPLY, CoreNode.variable("a"), CoreNode.variable("b")),
                    _node(T.MULTIPLY, CoreNode.variable("b"), CoreNode.variable("a")),
                )
            ],
        ),
    )
    negative_detail.add_group(
        "multiply",
        Step(
            _node(T.MULTIPLY, _num(1), _num(int(-b * d))),
            _num(int(product_value)),
            "mul",
        ),
    )
    negative_detail.set_solution(_num(int(product_value)))
    stages.append(
        Step(
            current,
            after_negative,
            "mul_with_neg_one",
            [_node(T.NEGATIVE, _num(1))],
            subresult=negative_detail,
        )
    )
    card.add_group(["multiply", "remove_bracket_short"], *stages)
    real_total = a * c + product_value
    imaginary_total = a * d + b * c
    summed = _node(
        T.ADD,
        _num(int(real_total)),
        _iterm(a * d),
        product_i,
    )
    card.add_group("calculate_short", Step(after_negative, summed, "add"))
    suffix_detail = _sum_suffix_detail([a * d, b * c], imaginary_total, "sum_suffix_detail")
    final = _complex_node(real_total, imaginary_total)
    card.add_group(
        ["calculate_short", "sum_suffix"],
        Step(summed, final, "sum_suffix", subresult=suffix_detail),
    )
    card.set_solution(final)
    return [foil, card]


def _tail_after_square(result: SolveResult, squared: CoreNode, a: int, c: int) -> None:
    """The distributive card already has ``i^2``: continue from the definition row."""
    head = [(1, _num(a * c)), (-1, _times_i(a)), (1, _times_i(c))]
    law = _node(T.EQUALS, _node(T.POWER, _unit(), _num(2)), _num(-1))
    definition = _chain([*head, (-1, _node(T.BRACKET, _num(-1)))])
    result.add_group("calculate_short", Step(squared, definition, "by_definition", [law]))
    opened = _chain([*head, (1, _num(1))])
    result.add_group("remove_bracket_short", Step(definition, opened, "neg_neg_arg", [_SIGNS[1]]))
    real = a * c + 1
    summed = _chain([(1, _num(real)), (-1, _times_i(a)), (1, _times_i(c))])
    imaginary = c - a
    final_terms: list[tuple[int, CoreNode]] = [(1, _num(real))]
    if imaginary:
        final_terms.append((1 if imaginary > 0 else -1, _times_i(abs(imaginary))))
    final = _chain(final_terms)
    detail = SolveResult()
    detail.add_group("sum_suffix", Step(summed, final, "sum_suffix"))
    detail.set_solution(final)
    result.add_group(
        ["calculate_short", "sum_suffix"],
        Step(opened, summed, "add"),
        Step(summed, final, "sum_suffix", subresult=detail),
    )
    result.set_solution(final)


def _pi_over(k: int, n: int) -> CoreNode:
    """``k pi / n`` written the way the keyboard does: ``pi/4``, ``7 pi/4``."""
    top = (
        CoreNode.constant("π")
        if k == 1
        else _node(T.MULTIPLY_IMPLICIT, _num(k), CoreNode.constant("π"))
    )
    return _node(T.FRACTION, top, _num(n))


def _polar(radius: CoreNode, cosine: CoreNode, sine: CoreNode | None = None) -> CoreNode:
    """``r (cos a + i sin b)``; the sine takes the cosine's angle unless one is given."""
    inner = _node(
        T.ADD,
        _node(T.COS, cosine),
        _node(T.MULTIPLY, _unit(), _node(T.SIN, sine if sine is not None else cosine)),
    )
    return _node(T.MULTIPLY_IMPLICIT, radius, _node(T.BRACKET, inner))


def _bare(cosine: CoreNode, sine: CoreNode) -> CoreNode:
    return _node(
        T.ADD,
        _node(T.COS, cosine),
        _node(T.MULTIPLY, _unit(), _node(T.SIN, sine)),
    )


def _trig_form_rows(
    node: CoreNode, polar: CoreNode, *, add_period: CoreNode | None = None
) -> SolveResult:
    """The trigonometric-form card: modulus/argument, the angle, the substitution."""
    detail = SolveResult()
    radius, cosine, sine = (CoreNode.variable(v) for v in ("r", "cosφ", "sinφ"))
    detail.add_group(
        "complex_trig_form_simple",
        Step(node, polar, "complex_trig_form_pair_msg", [radius, cosine, sine]),
    )
    detail.add_group(
        "simplify_msg",
        Step(polar, polar, "simplify"),
        Step(polar, polar, "simplify"),
    )
    if add_period is not None:
        detail.add_group(
            CoreRichText(type="add_arg", args=[add_period]),
            Step(polar, polar, "complex_trig_add_two_pi", [add_period]),
        )
        detail.add_group("calculate_short", Step(polar, polar, "calc_sum"))
    detail.add_group(
        CoreRichText(type="complex_trig_form_sub_simple", args=[polar]),
        Step(polar, polar, "complex_trig_form_sub", [polar]),
    )
    detail.set_solution(polar)
    return detail


def _expand_detail(node: CoreNode, expanded: CoreNode, formula: CoreNode) -> SolveResult:
    """The squared-binomial page: the formula, ``1²`` and ``2·1·i``."""
    from .base import Step as _Step

    detail = SolveResult()
    detail.add_group("expand_msg", _Step(node, expanded, "using_expand", [formula]))
    detail.add_group("pow", _Step(node, node, "pow_one", [_num(1)]))
    detail.add_group("calculate_short", _Step(node, expanded, "product"))
    detail.set_solution(expanded)
    return detail


def _angle_detail(before: CoreNode, after: CoreNode) -> SolveResult:
    """The angle difference's page: common denominator, like terms, sign, reduction."""
    detail = SolveResult()
    detail.add_group("trans_msg", Step(before, after, "frac_sum_join"))
    detail.add_group("sum_suffix", Step(after, after, "sum_suffix"))
    detail.add_group("rewrite", Step(after, after, "frac_extract_neg", [_num(-1)]))
    detail.add_group("reduce", Step(after, after, "frac_reduce_frac_alg", [_num(2)]))
    detail.set_solution(after)
    return detail


def _quotient_polar(node: CoreNode) -> SolveResult:
    """``(1+i)/(1-i)`` through the polar forms and the period of the circle."""
    sqrt2, two_pi = (
        _node(T.ROOT2, _num(2)),
        _node(T.MULTIPLY_IMPLICIT, _num(2), CoreNode.constant("π")),
    )
    top, bottom = node.children
    a, b = _pi_over(1, 4), _pi_over(7, 4)
    polar_top, polar_bottom = _polar(sqrt2, a), _polar(sqrt2, b)
    result = SolveResult()
    first = _node(T.FRACTION, polar_top, bottom)
    both = _node(T.FRACTION, polar_top, polar_bottom)
    result.add_group(
        ["complex_trig_form", "complex_trig_form"],
        Step(node, first, "complex_trig_form", subresult=_trig_form_rows(top, polar_top)),
        Step(
            first,
            both,
            "complex_trig_form",
            subresult=_trig_form_rows(bottom, polar_bottom, add_period=two_pi),
        ),
    )
    difference = _node(T.SUBTRACT, a, b)
    ratio = _node(T.FRACTION, sqrt2, sqrt2)
    r1, r2, t1, t2 = (CoreNode.variable(v) for v in ("r_1", "r_2", "θ_1", "θ_2"))
    formula = _node(
        T.EQUALS,
        _node(
            T.FRACTION,
            _polar(r1, t1),
            _polar(r2, t2),
        ),
        _node(
            T.MULTIPLY_IMPLICIT,
            _node(T.FRACTION, r1, r2),
            _node(T.BRACKET, _bare(_node(T.SUBTRACT, t1, t2), _node(T.SUBTRACT, t1, t2))),
        ),
    )
    divided = _polar(ratio, difference)
    result.add_group(
        ["complex_divide_step", "complex_divide_step_simple"],
        Step(both, divided, "complex_divide_step", [formula]),
    )
    one = _num(1)
    unit = _polar(one, difference)
    result.add_group("div_with_self", Step(divided, unit, "div_with_self", [one]))
    minus_three = _node(T.NEGATIVE, _pi_over(3, 2))
    stage_a = _bare(difference, difference)
    stage_b = _bare(minus_three, difference)
    stage_c = _bare(minus_three, minus_three)
    result.add_group(
        ["mul_with_one", "calc_diff", "calc_diff"],
        Step(unit, stage_a, "mul_with_one", [one]),
        Step(stage_a, stage_b, "calc_diff", subresult=_angle_detail(difference, minus_three)),
        Step(stage_b, stage_c, "calc_diff", subresult=_angle_detail(difference, minus_three)),
    )
    half = _pi_over(1, 2)
    shifted = _node(T.SUBTRACT, half, two_pi)
    rewritten_cos = _bare(shifted, minus_three)
    rewritten = _bare(shifted, shifted)
    result.add_group(
        [
            CoreRichText(type="write_as_diff", args=[minus_three]),
            CoreRichText(type="write_as_diff", args=[minus_three]),
        ],
        Step(stage_c, rewritten_cos, "write_as_diff_trig", [minus_three]),
        Step(rewritten_cos, rewritten, "write_as_diff_trig", [minus_three]),
    )
    x = CoreNode.variable("x")
    period = _node(T.EQUALS, _node(T.COS, _node(T.SUBTRACT, x, two_pi)), _node(T.COS, x))
    reduced_cos = _bare(half, shifted)
    final = _bare(half, half)
    result.add_group(
        ["using_sim", "using_sim"],
        Step(rewritten, reduced_cos, "using_sim", [period]),
        Step(reduced_cos, final, "using_sim", [period]),
    )
    result.set_solution(final)
    return result


def _square_polar(node: CoreNode) -> SolveResult:
    """``(1+i)^2`` by De Moivre's formula."""
    sqrt2, two = _node(T.ROOT2, _num(2)), _num(2)
    a = _pi_over(1, 4)
    base = node.children[0].children[0]
    polar = _polar(sqrt2, a)
    result = SolveResult()
    rewritten = _node(T.POWER, _node(T.BRACKET, polar), two)
    trig_detail = SolveResult()
    radius, cosine, sine = (
        CoreNode.variable("r"),
        CoreNode.variable("cosφ"),
        CoreNode.variable("sinφ"),
    )
    trig_detail.add_group(
        "complex_trig_form_simple",
        Step(base, polar, "complex_trig_form_pair_msg", [radius, cosine, sine]),
    )
    trig_detail.add_group(
        "simplify_msg",
        Step(polar, polar, "simplify"),
        Step(polar, polar, "simplify"),
    )
    trig_detail.add_group(
        CoreRichText(type="complex_trig_form_sub_simple", args=[_node(T.ABS, polar)]),
        Step(polar, polar, "complex_trig_form_sub", [_node(T.ABS, polar)]),
    )
    trig_detail.set_solution(polar)
    result.add_group(
        "complex_rewrite", Step(node, rewritten, "complex_trig_form", subresult=trig_detail)
    )
    r, n, t = CoreNode.variable("r"), CoreNode.variable("n"), CoreNode.variable("θ")
    formula = _node(
        T.EQUALS,
        _node(T.POWER, _node(T.BRACKET, _polar(r, t)), n),
        _node(
            T.MULTIPLY_IMPLICIT,
            _node(T.POWER, r, n),
            _node(
                T.BRACKET,
                _bare(_node(T.MULTIPLY, n, t), _node(T.MULTIPLY, n, t)),
            ),
        ),
    )
    doubled = _node(T.MULTIPLY, two, a)
    moivre = _polar(_node(T.POWER, sqrt2, two), doubled)
    result.add_group(
        "complex_pow_polar_moivre", Step(rewritten, moivre, "complex_pow_polar_moivre", [formula])
    )
    reduced_root = _polar(two, doubled)
    half = _pi_over(1, 2)
    cos_half = _node(T.MULTIPLY_IMPLICIT, two, _node(T.BRACKET, _bare(half, doubled)))
    final = _polar(two, half)
    result.add_group(
        ["root_reduce", "frac_reduce_out", "frac_reduce_out"],
        Step(moivre, reduced_root, "root_reduce", [two]),
        Step(reduced_root, cos_half, "frac_reduce_out", [two]),
        Step(cos_half, final, "frac_reduce_out", [two]),
    )
    result.set_solution(final)
    return result


def _is_one_plus_i_squared(node: CoreNode) -> bool:
    """``(1 + i)^2``, the one square worked out by hand."""
    if node.type is not T.POWER or len(node.children) != 2:
        return False
    base, exponent = node.children
    inner = base.children[0] if base.type is T.BRACKET and base.children else None
    return (
        inner is not None
        and inner.type is T.ADD
        and inner.children[0].type is T.CONSTANT
        and inner.children[0].value == "1"
        and _is_unit(inner.children[1])
        and exponent.type is T.CONSTANT
        and exponent.value == "2"
    )


@method_provider(T.POWER)
def complex_square_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """``(1 + i)^2`` by the formula and as a product of brackets."""
    _ = variables
    if (
        node.type is T.POWER
        and len(node.children) == 2
        and _is_unit(node.children[0])
        and node.children[1].type is T.CONSTANT
        and node.children[1].value == "2"
    ):
        one = _num(1)
        law = _node(T.EQUALS, _node(T.POWER, _unit(), _num(2)), _num(-1))
        definition = SolveResult()
        definition.add_group("calculate_short", Step(node, _num(-1), "by_definition", [law]))
        definition.set_solution(_num(-1))
        theta = _pi_over(1, 2)
        base_polar = _polar(one, theta)
        rewritten = _node(T.POWER, _node(T.BRACKET, base_polar), _num(2))
        r, b, angle = (
            CoreNode.variable("r"),
            CoreNode.variable("b"),
            CoreNode.variable("θ"),
        )
        variables_list = _node(
            T.LIST,
            _node(T.EQUALS, r, one),
            _node(T.EQUALS, angle, theta),
        )
        trig_detail = SolveResult()
        trig_detail.add_group(
            "complex_trig_form_simple",
            Step(
                _unit(),
                variables_list,
                "complex_trig_form_msg",
                [
                    r,
                    _node(T.MULTIPLY_IMPLICIT, b, _unit()),
                    _node(T.GREATER_THAN, b, _num(0)),
                    _node(T.ABS, b),
                    angle,
                    theta,
                ],
            ),
        )
        trig_detail.add_group(
            CoreRichText(type="complex_trig_form_sub_simple", args=[_polar(r, angle)]),
            Step(
                variables_list,
                base_polar,
                "complex_trig_form_sub",
                [_polar(r, angle)],
            ),
        )
        trig_detail.set_solution(base_polar)
        polar = SolveResult()
        polar.add_group(
            "complex_rewrite",
            Step(node, rewritten, "complex_trig_form", subresult=trig_detail),
        )
        doubled = _node(T.MULTIPLY, _num(2), theta)
        moivre = _polar(_node(T.POWER, one, _num(2)), doubled)
        formula = _node(
            T.EQUALS,
            _node(
                T.POWER,
                _node(T.BRACKET, _polar(r, angle)),
                CoreNode.variable("n"),
            ),
            _node(
                T.MULTIPLY_IMPLICIT,
                _node(T.POWER, r, CoreNode.variable("n")),
                _node(
                    T.BRACKET,
                    _bare(
                        _node(T.MULTIPLY, CoreNode.variable("n"), angle),
                        _node(T.MULTIPLY, CoreNode.variable("n"), angle),
                    ),
                ),
            ),
        )
        polar.add_group(
            "complex_pow_polar_moivre_simple",
            Step(rewritten, moivre, "complex_pow_polar_moivre", [formula]),
        )
        bare = _node(T.BRACKET, _bare(doubled, doubled))
        with_one = _node(T.MULTIPLY, one, bare)
        polar.add_group("pow", Step(moivre, with_one, "pow_one", [one]))
        polar.add_group("multiply", Step(with_one, bare, "mul_with_one", [one]))
        pi = CoreNode.constant("π")
        first_reduction = _bare(pi, doubled)
        final = _bare(pi, pi)
        polar.add_group(
            "reduce",
            Step(bare, first_reduction, "frac_reduce_out", [_num(2)]),
            Step(first_reduction, final, "frac_reduce_out", [_num(2)]),
        )
        polar.set_solution(final)
        return [definition, polar]
    if not _is_one_plus_i_squared(node):
        return []
    one, i, i_squared = _num(1), _unit(), _node(T.POWER, _unit(), _num(2))
    law = _node(T.EQUALS, i_squared, _num(-1))
    final = _times_i(2)
    # card 1: (a+b)^2 = a^2 + 2ab + b^2, the definition i^2 = -1, the opposite terms drop out
    a, b = CoreNode.variable("a"), CoreNode.variable("b")
    formula = _node(
        T.EQUALS,
        _node(T.POWER, _node(T.BRACKET, _node(T.ADD, a, b)), _num(2)),
        _chain(
            [
                (1, _node(T.POWER, a, _num(2))),
                (1, _node(T.MULTIPLY_IMPLICIT, _num(2), _node(T.MULTIPLY_IMPLICIT, a, b))),
                (1, _node(T.POWER, b, _num(2))),
            ]
        ),
    )
    expanded = _chain([(1, one), (1, _times_i(2)), (1, i_squared)])
    defined = _chain([(1, one), (1, _times_i(2)), (-1, one)])
    powered = _chain(
        [
            (1, _node(T.POWER, one, _num(2))),
            (1, _node(T.MULTIPLY, _num(2), one, i)),
            (1, i_squared),
        ]
    )
    after_power = _chain([(1, one), (1, _node(T.MULTIPLY, _num(2), one, i)), (1, i_squared)])
    inner = SolveResult()
    inner.add_group("expand_msg", Step(node, powered, "using_expand", [formula]))
    inner.add_group(
        "pow",
        Step(_node(T.POWER, one, _num(2)), one, "pow_one", [_num(1)]),
    )
    inner.add_group(
        "calculate_short",
        Step(
            _node(T.MULTIPLY, _num(2), one, i),
            _times_i(2),
            "product",
        ),
    )
    _ = after_power
    inner.set_solution(expanded)
    by_formula = SolveResult()
    by_formula.add_group(
        "expand_msg",
        Step(node, expanded, "using_expand", [formula], subresult=inner),
    )
    by_formula.add_group("calculate_short", Step(expanded, defined, "by_definition", [law]))
    by_formula.add_group("remove_opposites", Step(defined, final, "sub_with_self_remove_num"))
    by_formula.set_solution(final)
    # card 2: the product of two brackets
    bracket = _node(T.BRACKET, _node(T.ADD, one, i))
    product = _node(T.MULTIPLY, bracket, bracket)
    crossed = _chain([(1, one), (1, i), (1, i), (1, _node(T.MULTIPLY, i, i))])
    squared = _chain([(1, one), (1, i), (1, i), (1, i_squared)])
    unit_defined = _chain([(1, one), (1, i), (1, i), (-1, one)])
    pair = _chain([(1, i), (1, i)])
    with_one = _chain([(1, _node(T.MULTIPLY_IMPLICIT, i, _num(1))), (1, i)])
    both_one = _chain(
        [
            (1, _node(T.MULTIPLY_IMPLICIT, i, _num(1))),
            (1, _node(T.MULTIPLY_IMPLICIT, i, _num(1))),
        ]
    )
    combined = _node(T.MULTIPLY_IMPLICIT, i, _node(T.ADD, _num(1), _num(1)))
    like = SolveResult()
    like.add_group(
        CoreRichText(type="sum_one_coeff", args=[_num(1)]),
        Step(pair, with_one, "sum_suffix_add_one", [_num(1)]),
        Step(with_one, both_one, "sum_suffix_add_one", [_num(1)]),
    )
    like.add_group("sum_suffix", Step(both_one, combined, "sum_suffix_add_detail"))
    like.add_group("calculate_short", Step(combined, final, "add"))
    like.set_solution(final)
    power_detail = SolveResult()
    raw = _node(T.MULTIPLY, i, i)
    first_power = _node(T.MULTIPLY, i, _node(T.POWER, i, _num(1)))
    both_powers = _node(T.MULTIPLY, _node(T.POWER, i, _num(1)), _node(T.POWER, i, _num(1)))
    added = _node(T.POWER, i, _node(T.ADD, _num(1), _num(1)))
    power_detail.add_group(
        CoreRichText(type="pow_one_exp", args=[_num(1)]),
        Step(raw, first_power, "pow_implicit_exp", [_num(1)]),
        Step(first_power, both_powers, "pow_implicit_exp", [_num(1)]),
    )
    power_detail.add_group("product", Step(both_powers, added, "pow_same_base_mul"))
    power_detail.add_group("calculate_short", Step(added, i_squared, "add"))
    power_detail.set_solution(i_squared)
    by_product = SolveResult()
    by_product.add_group("rewrite", Step(node, product, "write_as_product"))
    by_product.add_group("mul_bracket_cross", Step(product, crossed, "mul_bracket_cross_each"))
    by_product.add_group(
        "calculate_short",
        Step(crossed, squared, "product", subresult=power_detail),
    )
    by_product.add_group("calculate_short", Step(squared, unit_defined, "by_definition", [law]))
    by_product.add_group(
        ["remove_opposites", "sum_suffix"],
        Step(unit_defined, pair, "sub_with_self_remove_num"),
        Step(pair, final, "sum_suffix", subresult=like),
    )
    by_product.set_solution(final)
    return [by_formula, by_product, _square_polar(node)]


def _is_one_plus_minus_i(node: CoreNode, sign: T) -> bool:
    inner = node.children[0] if node.type is T.BRACKET else node
    return (
        inner.type is sign
        and len(inner.children) == 2
        and inner.children[0].type is T.CONSTANT
        and inner.children[0].value == "1"
        and _is_unit(inner.children[1])
    )


@method_provider(T.FRACTION)
def complex_quotient_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """``(1 + i) / (1 - i)`` by the conjugate (the "Выполнить деление" card).

    shortcut: only the verified quotient; other quotients use the standard-form step.
    """
    _ = variables
    if len(node.children) != 2:
        return []
    top, bottom = node.children
    if not (_is_one_plus_minus_i(top, T.ADD) and _is_one_plus_minus_i(bottom, T.SUBTRACT)):
        return []
    one, i, two = _num(1), _unit(), _num(2)
    i_squared = _node(T.POWER, i, two)
    plus = _node(T.BRACKET, _node(T.ADD, one, i))
    minus = _node(T.BRACKET, _node(T.SUBTRACT, one, i))

    def fraction(up: CoreNode, down: CoreNode) -> CoreNode:
        return _node(T.FRACTION, up, down)

    conjugated = fraction(_node(T.MULTIPLY, plus, plus), _node(T.MULTIPLY, minus, plus))
    powered = fraction(_node(T.POWER, plus, two), _node(T.MULTIPLY, minus, plus))
    one_minus_square = _node(T.SUBTRACT, one, i_squared)
    simpler = fraction(_node(T.POWER, plus, two), one_minus_square)
    expanded_top = _chain([(1, one), (1, _times_i(2)), (1, i_squared)])
    expanded = fraction(expanded_top, one_minus_square)
    law = _node(T.EQUALS, i_squared, _num(-1))
    defined_bottom = fraction(expanded_top, _node(T.SUBTRACT, one, _node(T.BRACKET, _num(-1))))
    top_defined = _chain([(1, one), (1, _times_i(2)), (-1, one)])
    both_defined = fraction(top_defined, _node(T.SUBTRACT, one, _node(T.BRACKET, _num(-1))))
    opened = fraction(top_defined, _node(T.ADD, one, one))
    dropped = fraction(_times_i(2), _node(T.ADD, one, one))
    summed = fraction(_times_i(2), two)
    final = _unit()
    formula = _node(
        T.EQUALS,
        _node(
            T.POWER,
            _node(T.BRACKET, _node(T.ADD, CoreNode.variable("a"), CoreNode.variable("b"))),
            two,
        ),
        _chain(
            [
                (1, _node(T.POWER, CoreNode.variable("a"), two)),
                (
                    1,
                    _node(
                        T.MULTIPLY_IMPLICIT,
                        two,
                        _node(T.MULTIPLY_IMPLICIT, CoreNode.variable("a"), CoreNode.variable("b")),
                    ),
                ),
                (1, _node(T.POWER, CoreNode.variable("b"), two)),
            ]
        ),
    )
    difference = _node(
        T.EQUALS,
        _node(
            T.MULTIPLY,
            _node(T.BRACKET, _node(T.SUBTRACT, CoreNode.variable("a"), CoreNode.variable("b"))),
            _node(T.BRACKET, _node(T.ADD, CoreNode.variable("a"), CoreNode.variable("b"))),
        ),
        _node(
            T.SUBTRACT,
            _node(T.POWER, CoreNode.variable("a"), two),
            _node(T.POWER, CoreNode.variable("b"), two),
        ),
    )
    card = SolveResult()
    card.add_group("complex_rationalize_mul", Step(node, conjugated, "complex_rationalize_mul"))
    power_detail = SolveResult()
    raw_pair = _node(T.MULTIPLY, i, i)
    first_power = _node(T.MULTIPLY, i, _node(T.POWER, i, _num(1)))
    both_powers = _node(T.MULTIPLY, _node(T.POWER, i, _num(1)), _node(T.POWER, i, _num(1)))
    added_powers = _node(T.POWER, i, _node(T.ADD, _num(1), _num(1)))
    power_detail.add_group(
        CoreRichText(type="pow_one_exp", args=[_num(1)]),
        Step(raw_pair, first_power, "pow_implicit_exp", [_num(1)]),
        Step(first_power, both_powers, "pow_implicit_exp", [_num(1)]),
    )
    power_detail.add_group("product", Step(both_powers, added_powers, "pow_same_base_mul"))
    power_detail.add_group("calculate_short", Step(added_powers, i_squared, "add"))
    power_detail.set_solution(i_squared)
    factor_detail = SolveResult()
    factor_detail.add_group(
        "mul_simplify_prod",
        Step(_node(T.MULTIPLY, minus, plus), one_minus_square, "factorise_inv_sim", [difference]),
    )
    factor_detail.add_group("pow", Step(one_minus_square, one_minus_square, "pow_one", [_num(1)]))
    factor_detail.set_solution(one_minus_square)
    card.add_group(
        ["mul_to_pow", "factorise_inv_sim"],
        Step(conjugated, powered, "mul_to_pow", subresult=power_detail),
        Step(
            powered,
            simpler,
            "factorise_inv_sim",
            [difference],
            subresult=factor_detail,
        ),
    )
    card.add_group(
        ["using_expand", "by_definition"],
        Step(
            simpler,
            expanded,
            "using_expand",
            [formula],
            subresult=_expand_detail(_node(T.POWER, plus, two), expanded_top, formula),
        ),
        Step(expanded, defined_bottom, "by_definition", [law]),
    )
    card.add_group(
        ["by_definition", "remove_bracket_short"],
        Step(defined_bottom, both_defined, "by_definition", [law]),
        Step(both_defined, opened, "neg_neg_arg", [_SIGNS[1]]),
    )
    card.add_group(
        ["remove_opposites", "add"],
        Step(opened, dropped, "sub_with_self_remove_num"),
        Step(dropped, summed, "add"),
    )
    card.add_group("frac_reduce_frac", Step(summed, final, "frac_reduce_frac_alg", [two]))
    card.set_solution(final)
    return [card, _quotient_polar(node)]


__all__ = ["complex_product_methods", "complex_quotient_methods", "complex_square_methods"]
