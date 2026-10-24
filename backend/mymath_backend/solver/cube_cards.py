"""The four cards for ``(x + 1)^3`` and ``(x - 1)^3``.

The formula, the product of three brackets, Pascal's triangle and the binomial theorem were
worked out for ``(x - 1)^3``; the ``+`` variants follow the same rows (their stage counts
match ``(x + 1)^3``).

shortcut: only ``k = 1``; the order in which Pascal's rows simplify the coefficient ones is
inferred from the stage counts, and a test checks that every intermediate state equals the cube.
"""

from __future__ import annotations

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveResult, Step
from .expression_cards import _collect_page, _products_page, _signed_product_page
from .quadratic_cards import _chain, _num


def _mul_one_page(value: CoreNode) -> SolveResult:
    detail = SolveResult()
    detail.add_group("mul_with_one", Step(value, value, "mul_with_one", [_num(1)]))
    detail.set_solution(value)
    return detail


def _powers_page(first_power: int, second_power: int, value: CoreNode, var: str) -> SolveResult:
    """Detail page for ``x²·x`` / ``2x·x``: implicit exponents, then the same base."""
    x, one = CoreNode.variable(var), _num(1)
    detail = SolveResult()
    current = _m(_pw(x, _num(first_power)), _pw(x, _num(second_power)))
    for _ in range(1 if first_power > 1 else 2):
        written = _m(_pw(x, one), _pw(x, one))
        detail.add_group("pow_implicit_exp", Step(written, written, "pow_implicit_exp", [one]))
    combined = _pw(x, _num(first_power + second_power))
    detail.add_group("product", Step(current, combined, "pow_same_base_mul"))
    detail.add_group("calculate_short", Step(combined, value, "add"))
    detail.set_solution(value)
    return detail


def _power_sign_page(base: CoreNode, exponent: int, value: CoreNode) -> SolveResult:
    """Detail page for ``(-1)²`` / ``(-1)³``: even/odd sign, then the power of one."""
    inner = base
    if inner.type is T.BRACKET and inner.children:
        inner = inner.children[0]
    negative = inner.type is T.NEGATIVE or (
        inner.type is T.CONSTANT and str(inner.value or "").startswith("-")
    )
    detail = SolveResult()
    current = _pw(base, _num(exponent))
    if negative:
        positive = _node(T.BRACKET, _num(1))
        key = "pow_even" if exponent % 2 == 0 else "pow_odd"
        detail.add_group(key, Step(current, _pw(positive, _num(exponent)), key))
        current = _pw(positive, _num(exponent))
    detail.add_group("calculate_short", Step(current, value, "pow_one", [_num(1)]))
    detail.set_solution(value)
    return detail


def _node(kind: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(kind, *children)


def _pw(base: CoreNode, exponent: CoreNode) -> CoreNode:
    return _node(T.POWER, base, exponent)


def _m(*factors: CoreNode) -> CoreNode:
    return _node(T.MULTIPLY, *factors)


def _imp(coefficient: CoreNode, base: CoreNode) -> CoreNode:
    return _node(T.MULTIPLY_IMPLICIT, coefficient, base)


class _Terms:
    """A sum written term by term; ``apply`` rewrites one term and returns the step."""

    def __init__(self, terms: list[CoreNode], signs: list[int] | None = None) -> None:
        self.terms = list(terms)
        self.signs = signs or [1] * len(terms)

    def node(self) -> CoreNode:
        return _chain(list(zip(self.signs, self.terms, strict=True)))

    def apply(
        self,
        index: int,
        new: CoreNode,
        key: str,
        args: list[CoreNode] | None = None,
        sub: SolveResult | None = None,
        sign: int | None = None,
    ) -> Step:
        before = self.node()
        self.terms[index] = new
        if sign is not None:
            self.signs[index] = sign
        return Step(before, self.node(), key, args or [], subresult=sub)


def cube_methods(node: CoreNode, var: str) -> list[SolveResult] | None:
    """The four cards of ``(x +- 1)^3``, else ``None``."""
    if not (
        node.type is T.POWER
        and node.children[1].type is T.CONSTANT
        and node.children[1].value == "3"
        and node.children[0].type is T.BRACKET
    ):
        return None
    inner = node.children[0].children[0]
    if not (
        inner.type in (T.ADD, T.SUBTRACT)
        and inner.children[0].type is T.VARIABLE
        and inner.children[0].value == var
        and inner.children[1].type is T.CONSTANT
        and inner.children[1].value == "1"
    ):
        return None
    minus = inner.type is T.SUBTRACT
    return [
        _formula(node, var, minus),
        _product(node, inner, var, minus),
        _pascal(node, var, minus),
        _binomial(node, var, minus),
        _sigma(node, var, minus),
    ]


def _formula(node: CoreNode, var: str, minus: bool) -> SolveResult:
    x, one, two, three = CoreNode.variable(var), _num(1), _num(2), _num(3)
    s = -1 if minus else 1
    a, b = CoreNode.variable("a"), CoreNode.variable("b")
    formula = _node(
        T.EQUALS,
        _pw(_node(T.BRACKET, _node(T.SUBTRACT if minus else T.ADD, a, b)), three),
        _chain(
            [
                (1, _pw(a, three)),
                (s, _imp(three, _imp(_pw(a, two), b))),
                (1, _imp(three, _imp(a, _pw(b, two)))),
                (s, _pw(b, three)),
            ]
        ),
    )
    x3, x2 = _pw(x, three), _pw(x, two)
    three_x2, three_x = _imp(three, x2), _imp(three, x)
    rows = _Terms(
        [x3, _m(three_x2, one), _m(three_x, _pw(one, two)), _pw(one, three)], [1, s, 1, s]
    )
    start = rows.node()
    result = SolveResult()
    result.add_group("expand_msg", Step(node, start, "using_expand", [formula]))
    result.add_group(
        ["product", "pow_one", "pow_one"],
        rows.apply(1, three_x2, "product", sub=_mul_one_page(three_x2)),
        rows.apply(2, _m(three_x, one), "pow_one", [one]),
        rows.apply(3, one, "pow_one", [one]),
    )
    final = rows.apply(2, three_x, "product", sub=_mul_one_page(three_x))
    result.add_group("product", final)
    assert final.right is not None
    result.set_solution(final.right)
    return result


def _product(node: CoreNode, inner: CoreNode, var: str, minus: bool) -> SolveResult:
    x, one, two, three = CoreNode.variable(var), _num(1), _num(2), _num(3)
    s = -1 if minus else 1
    bracket = _node(T.BRACKET, inner)
    x2, x3 = _pw(x, two), _pw(x, three)
    two_x, three_x, three_x2 = _imp(two, x), _imp(three, x), _imp(three, x2)
    opposite = _node(T.BRACKET, _num(-1))
    result = SolveResult()
    start = _m(bracket, bracket, bracket)
    result.add_group("write_as_product", Step(node, start, "write_as_product"))

    # (x -+ 1)(x -+ 1): the four products
    corner = _m(one, opposite) if minus else _m(one, one)
    cross = _Terms([_m(x, x), x, x, corner], [1, s, s, s])
    crossed = _m(_node(T.BRACKET, cross.node()), bracket)
    result.add_group("mul_bracket_cross", Step(start, crossed, "mul_bracket_cross_each"))

    def wrap(rows: _Terms) -> CoreNode:
        return _m(_node(T.BRACKET, rows.node()), bracket)

    if minus:
        before_first = wrap(cross)
        cross.terms[0] = x2
        after_first = wrap(cross)
        before_second = after_first
        cross.terms[3], cross.signs[3] = one, 1
        stages = [
            Step(before_first, after_first, "product", subresult=_products_page(var, x2)),
            Step(
                before_second,
                wrap(cross),
                "mul_with_neg_one",
                [_num(-1)],
                subresult=_signed_product_page(corner, one, same_sign=True),
            ),
        ]
        result.add_group(["product", "mul_with_neg_one"], *stages)
    else:
        before_first = wrap(cross)
        cross.terms[0], cross.terms[3] = x2, one
        result.add_group(
            "product",
            Step(before_first, wrap(cross), "product", subresult=_products_page(var, x2)),
        )
    after = wrap(cross)

    like = _Terms([x2, two_x, one], [1, s, 1])
    final_pair = _m(_node(T.BRACKET, like.node()), bracket)
    result.add_group(
        "sum_suffix",
        Step(after, final_pair, "sum_suffix", subresult=_collect_page(var, s, s)),
    )

    # (x^2 -+ 2x + 1)(x -+ 1): every term of the first bracket times the second
    rows = _Terms(
        [_m(x2, x), x2, _m(two_x, x), _m(two_x, opposite) if minus else two_x, x, one],
        [1, s, s, s, 1, s],
    )
    if not minus:
        rows.signs = [1, 1, 1, 1, 1, 1]
    start_rows = rows.node()
    result.add_group(
        "mul_bracket_cross_no_foil",
        Step(final_pair, start_rows, "mul_bracket_cross_each_no_foil"),
    )
    steps = [
        rows.apply(0, x3, "product", sub=_powers_page(2, 1, x3, var)),
        rows.apply(2, _imp(two, x2), "product", sub=_powers_page(1, 1, _imp(two, x2), var)),
    ]
    if minus:
        positive = _m(two_x, one)
        steps.append(rows.apply(3, positive, "mul_neg_neg", [_num(-1)], sign=1))
        steps.append(rows.apply(3, two_x, "product", sub=_mul_one_page(two_x)))
    result.add_group(["product"] * len(steps), *steps)
    before = rows.node()
    three_x2_term = three_x2
    ready_rows = _Terms([x3, three_x2_term, two_x, x, one], [1, s, 1, 1, s])
    ready = ready_rows.node()
    final_rows = _Terms([x3, three_x2_term, three_x, one], [1, s, 1, s])
    final = final_rows.node()
    first = _collect_page(var, s, 2 * s)
    second = _collect_page(var, 2, 1)
    result.add_group(
        ["sum_suffix", "sum_suffix"],
        Step(before, ready, "sum_suffix", subresult=first),
        Step(ready, final, "sum_suffix", subresult=second),
    )
    result.set_solution(final)
    return result


def _pascal(node: CoreNode, var: str, minus: bool) -> SolveResult:
    x, one, zero, two, three = CoreNode.variable(var), _num(1), _num(0), _num(2), _num(3)
    s = -1 if minus else 1
    base = _node(T.BRACKET, _num(-1)) if minus else one
    template = _chain(
        [(1, _m(CoreNode.variable("?"), _pw(x, _num(3 - r)), _pw(base, _num(r)))) for r in range(4)]
    )
    rows = _Terms(
        [
            _m(_imp(one, _pw(x, three)), _pw(base, zero)),
            _m(_imp(three, _pw(x, two)), _pw(base, one)),
            _m(_imp(three, _pw(x, one)), _pw(base, two)),
            _m(_imp(one, _pw(x, zero)), _pw(base, three)),
        ]
    )
    result = SolveResult()
    result.add_group(
        "expand_binomial_triangle",
        Step(node, template, "expand_binomial_triangle", [x, one, three, zero]),
    )
    result.add_group(
        "coeff_sub",
        Step(
            template,
            rows.node(),
            "expand_binomial_triangle_substitute",
            [three, _chain([(1, _num(c)) for c in (1, 3, 3, 1)])],
        ),
    )
    x3, x2 = _pw(x, three), _pw(x, two)
    three_x2, three_x = _imp(three, x2), _imp(three, x)
    if minus:
        steps = [
            rows.apply(0, _m(x3, _pw(base, zero)), "mul_with_one", [one]),
            rows.apply(3, _m(_pw(x, zero), _pw(base, three)), "mul_with_one", [one]),
            rows.apply(0, _m(x3, one), "pow_with_zero", [zero, one]),
            rows.apply(1, _m(three_x2, base), "pow_with_one", [one]),
            rows.apply(2, _m(three_x, _pw(base, two)), "pow_with_one", [one]),
            rows.apply(2, _m(three_x, one), "pow", sub=_power_sign_page(base, 2, one)),
            rows.apply(3, _m(one, _pw(base, three)), "pow_with_zero", [zero, one]),
            rows.apply(3, _m(one, base), "pow", sub=_power_sign_page(base, 3, base)),
        ]
    else:
        steps = [
            rows.apply(0, _m(x3, _pw(base, zero)), "mul_with_one", [one]),
            rows.apply(0, _m(x3, one), "pow_one", [one]),
            rows.apply(1, _m(three_x2, one), "pow_one", [one]),
            rows.apply(2, _m(three_x, _pw(base, two)), "pow_with_one", [one]),
            rows.apply(2, _m(three_x, one), "pow_one", [one]),
            rows.apply(3, _m(one, one, _pw(base, three)), "pow_with_zero", [zero, one]),
            rows.apply(3, _m(one, one, one), "pow_one", [one]),
        ]
    result.add_group(["eval_pow_plural"] * len(steps), *steps)
    if minus:
        more = [
            rows.apply(0, x3, "mul_with_one", [one]),
            rows.apply(2, three_x, "mul_with_one", [one]),
            rows.apply(3, _m(one, base), "mul_with_one", [one]),
            rows.apply(1, _m(_node(T.NEGATIVE, three_x2), one), "mul_pos_neg", [_num(-1)]),
            rows.apply(1, _node(T.NEGATIVE, three_x2), "mul_with_one", [one]),
        ]
        final_rows = _Terms([x3, three_x2, three_x, one], [1, -1, 1, -1])
        more.append(Step(rows.node(), final_rows.node(), "pos_neg_arg", [_num(1)]))
    else:
        more = [
            rows.apply(0, x3, "mul_with_one", [one]),
            rows.apply(1, three_x2, "mul_with_one", [one]),
            rows.apply(2, three_x, "mul_with_one", [one]),
            rows.apply(3, _m(one, one), "mul_with_one", [one]),
            rows.apply(3, one, "mul_with_one", [one]),
        ]
        final_rows = rows
    result.add_group(["product_plural"] * len(more), *more)
    result.set_solution(final_rows.node())
    del s
    return result


def _sigma_rule(index: CoreNode) -> CoreNode:
    """``(a+b)^n = Σ choose(n,k) a^(n-k) b^k`` as the explanation argument."""
    a, b, n, zero = (
        CoreNode.variable("a"),
        CoreNode.variable("b"),
        CoreNode.variable("n"),
        _num(0),
    )
    return _node(
        T.EQUALS,
        _pw(_node(T.BRACKET, _node(T.ADD, a, b)), n),
        _node(
            T.SIGMA_DEFINITE,
            index,
            zero,
            n,
            _m(
                _node(T.CHOOSE_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT, n, index),
                _m(_pw(a, _node(T.SUBTRACT, n, index)), _pw(b, index)),
            ),
        ),
    )


def _sigma(node: CoreNode, var: str, minus: bool) -> SolveResult:
    """The binomial-theorem card: the cube written as a single sigma."""
    x, one, zero, three = CoreNode.variable(var), _num(1), _num(0), _num(3)
    base = _node(T.BRACKET, _num(-1)) if minus else one
    index = CoreNode.variable("r")
    term = _m(
        _node(T.CHOOSE_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT, three, index),
        _m(_pw(x, _node(T.SUBTRACT, three, index)), _pw(base, index)),
    )
    summed = _node(T.SIGMA_DEFINITE, index, zero, three, term)
    rule = _sigma_rule(index)
    result = SolveResult()
    current = node
    if minus:
        current = _pw(_node(T.BRACKET, _node(T.ADD, x, _num(-1))), three)
        result.add_group("sub_as_add", Step(node, current, "sub_as_add"))
    result.add_group(
        "expand_sigma_simple",
        Step(current, summed, "expand_sigma", [rule, x, base, three]),
    )
    result.set_solution(summed)
    return result


def _binomial(node: CoreNode, var: str, minus: bool) -> SolveResult:
    x, one, zero, two, three = CoreNode.variable(var), _num(1), _num(0), _num(2), _num(3)
    k = CoreNode.variable("k")
    base = _node(T.BRACKET, _num(-1)) if minus else one

    def choose(index: CoreNode) -> CoreNode:
        return _node(T.CHOOSE_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT, three, index)

    def term(index: CoreNode) -> CoreNode:
        return _m(choose(index), _pw(x, _node(T.SUBTRACT, three, index)), _pw(base, index))

    general = _sigma_rule(k)
    summed = _node(T.SIGMA_DEFINITE, k, zero, three, term(k))
    result = SolveResult()
    result.add_group(
        "expand_binomial_pascal_msg",
        Step(node, summed, "expand_binomial_pascal", [general]),
    )
    rows = _Terms([term(_num(i)) for i in range(4)])
    result.add_group(
        "sigma_sum_convert", Step(summed, rows.node(), "sigma_sum_convert", [zero, three])
    )
    x3, x2 = _pw(x, three), _pw(x, two)
    s = -1 if minus else 1
    three_x2 = _m(three, _node(T.BRACKET, _node(T.NEGATIVE, x2))) if minus else _imp(three, x2)
    three_x = _imp(three, x)
    last = _m(one, base) if minus else _m(one, one)
    after_choose = [
        _m(one, _pw(x, _node(T.SUBTRACT, three, zero)), _pw(base, zero)),
        _m(three, _pw(x, _node(T.SUBTRACT, three, one)), _pw(base, one)),
        _m(three, _pw(x, _node(T.SUBTRACT, three, two)), _pw(base, two)),
        _m(one, _pw(x, _node(T.SUBTRACT, three, three)), _pw(base, three)),
    ]
    definitions = [
        ("choose_def_zero", _node(T.EQUALS, choose(zero), one)),
        ("choose_def_one", _node(T.EQUALS, choose(one), three)),
        ("choose_simplify_minus_one", _node(T.EQUALS, choose(two), three)),
        ("choose_def_same", _node(T.EQUALS, choose(three), one)),
    ]

    def page(rows: list[tuple[str, list[CoreNode]]]) -> SolveResult:
        detail = SolveResult()
        for key, args in rows:
            detail.add_group(key, Step(after_choose[0], after_choose[0], key, args))
        detail.set_solution(after_choose[0])
        return detail

    if minus:
        simplify_pages = [
            page(
                [("add_with_zero", [zero]), ("pow_with_zero", [zero, one]), ("mul_with_one", [one])]
            ),
            page(
                [
                    ("sub", []),
                    ("pow_with_one", [one]),
                    ("mul_pos_neg", [_num(-1)]),
                    ("mul_with_one", [one]),
                ]
            ),
            page([("sub", []), ("pow", []), ("mul_with_one", [one]), ("pow_with_one", [one])]),
            page(
                [
                    ("sub_with_self_num", [zero]),
                    ("pow", []),
                    ("pow_with_zero", [zero, one]),
                    ("mul_with_one", [one]),
                ]
            ),
        ]
    else:
        simplify_pages = [
            page([("add_with_zero", [zero]), ("pow_one", [one]), ("mul_with_one", [one])]),
            page([("sub", []), ("pow_one", [one]), ("mul_with_one", [one])]),
            page(
                [("sub", []), ("pow_one", [one]), ("mul_with_one", [one]), ("pow_with_one", [one])]
            ),
            page(
                [
                    ("sub_with_self_num", [zero]),
                    ("pow_one", [one]),
                    ("mul_with_one", [one]),
                    ("pow_with_zero", [zero, one]),
                ]
            ),
        ]
    simplified = [_imp(one, x3), three_x2, three_x, last]
    steps: list[Step] = []
    for index, (key, law) in enumerate(definitions):
        steps.append(rows.apply(index, after_choose[index], key, [law]))
        steps.append(rows.apply(index, simplified[index], "simplify", sub=simplify_pages[index]))
    result.add_group([title for d in definitions for title in (d[0], "simplify")], *steps)
    tail = [
        rows.apply(0, x3, "simplify"),
        rows.apply(1, _imp(three, x2), "simplify", sign=s) if minus else None,
    ]
    group = [step for step in tail if step is not None]
    if minus:
        rows.terms[1] = _imp(three, x2)
        rows.signs[1] = -1
        group.append(
            Step(
                rows.node(),
                _chain([(1, x3), (-1, _imp(three, x2)), (1, three_x), (-1, one)]),
                "mul_with_neg_one",
                [_num(-1)],
                subresult=_mul_one_page(_num(-1)),
            )
        )
        final = group[-1].right
        assert final is not None
    else:
        group.append(rows.apply(3, one, "mul_with_one", [_num(1)]))
        final = rows.node()
    result.add_group(["simplify"] * len(group), *group)
    result.set_solution(final)
    return result
