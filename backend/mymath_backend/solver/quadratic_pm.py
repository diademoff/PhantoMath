"""Quadratic equations with integer coefficients and distinct rational roots.

Two of the ways Photomath 7.10.0 shows on a device (rows are main steps, the steps
inside a row are its stages): factoring by splitting the middle term, and the roots
formula. Only the captured families are produced -- ``x^2 - 5x + 6`` (a = 1, b < 0,
c > 0) and ``2x^2 + 3x - 2`` (a > 1, b > 0, c < 0); everything else returns ``None``
and the general solver runs.
"""

from __future__ import annotations

from fractions import Fraction
from math import gcd, isqrt

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .arithmetic import format_number
from .base import SolveContext, SolveError, SolveResult, Step, route

_SIGNS = (
    CoreNode.variable("+"),
    CoreNode.variable("−"),
)  # arguments of "one with + and one with -"


def _num(value: int | Fraction) -> CoreNode:
    return CoreNode.constant(format_number(Fraction(value)))


def _node(kind: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(kind, *children)


def _paren(value: int) -> CoreNode:
    return _node(T.BRACKET, _num(value)) if value < 0 else _num(value)


def _eq(left: CoreNode, right: CoreNode) -> CoreNode:
    return _node(T.EQUALS, left, right)


def _mono(coefficient: int, degree: int, var: str) -> CoreNode:
    """``|c| x^degree``; a coefficient of 1 is left out."""
    x = CoreNode.variable(var)
    base = {2: _node(T.POWER, x, _num(2)), 1: x}.get(degree)
    if base is None:
        return _num(abs(coefficient))
    return (
        base if abs(coefficient) == 1 else _node(T.MULTIPLY_IMPLICIT, _num(abs(coefficient)), base)
    )


def _chain(items: list[tuple[int, CoreNode]]) -> CoreNode:
    """``±t1 ± t2 …`` as a left-leaning chain; a leading minus is a NEGATIVE node."""
    sign, first = items[0]
    out = _node(T.NEGATIVE, first) if sign < 0 else first
    for sign, term in items[1:]:
        out = _node(T.SUBTRACT if sign < 0 else T.ADD, out, term)
    return out


def _poly(terms: list[tuple[int, int]], var: str) -> CoreNode:
    """Sum of ``(coefficient, degree)`` terms in the given order, zero terms dropped."""
    return _chain([(1 if c > 0 else -1, _mono(c, d, var)) for c, d in terms if c != 0])


def _evaluate(node: CoreNode) -> SolveResult:
    """The steps our arithmetic takes to evaluate ``node``: a real nested screen."""
    detail = SolveResult()
    try:
        detail.set_solution(route(node, SolveContext(result=detail)))
    except SolveError:  # not an expression our arithmetic evaluates (e.g. a bracketed numerator)
        return SolveResult()
    return detail


def _solve_linear(equation: CoreNode, var: str) -> SolveResult:
    from .equations import solve_methods

    return solve_methods(equation, [var])[0]


class _Family:
    """``a x^2 + b x + c = 0`` with integer coefficients and distinct rational roots."""

    def __init__(self, var: str, a: int, b: int, c: int) -> None:
        self.var, self.a, self.b, self.c = var, a, b, c
        self.d = b * b - 4 * a * c
        self.root = isqrt(self.d)
        self.x = CoreNode.variable(var)
        self.node = _eq(_poly([(a, 2), (b, 1), (c, 0)], var), _num(0))
        self.low, self.high = sorted(
            (Fraction(-b - self.root, 2 * a), Fraction(-b + self.root, 2 * a))
        )

    def solved(self, root: Fraction) -> CoreNode:
        return _eq(self.x, _num(root))

    def finish(self, result: SolveResult, cases: list[CoreNode]) -> None:
        solution = _node(T.LIST, self.solved(self.low), self.solved(self.high))
        result.add_group(
            CoreRichText(type="solution_eq_num", args=[_num(2)]),
            Step(_node(T.LIST, *cases), solution, "solution_eq_num", [_num(2)]),
        )
        result.set_solution(solution)


def _factor_rows(
    f: _Family, result: SolveResult, relation: T
) -> tuple[CoreNode, CoreNode, CoreNode] | None:
    """The three rows that turn ``a x^2 + b x + c (relation) 0`` into a product of brackets."""
    a, b, c, var = f.a, f.b, f.c, f.var

    def link(left: CoreNode, right: CoreNode) -> CoreNode:
        return _node(relation, left, right)

    p, q = (b + f.root) // 2, (b - f.root) // 2  # p + q = b, p q = a c, p > q
    g = gcd(a, abs(p))
    lead, rest = a // g, p // g
    second = q // lead
    # a positive second term was captured for a = 1 with a tail equal to the bracket (x^2 + 4x + 3)
    if q == 0 or q % lead or c != second * rest or (q > 0 and (a != 1 or second != 1)):
        return None
    bracket = _poly([(lead, 1), (rest, 0)], var)
    wrapped = _node(T.BRACKET, bracket)
    split = link(_poly([(a, 2), (p, 1), (q, 1), (c, 0)], var), _num(0))
    result.add_group(
        "rewrite_expression",
        Step(
            f.node,
            split,
            "write_as_sum" if q > 0 else "write_as_diff",
            [_chain([(1 if b > 0 else -1, _mono(b, 1, var))])],
        ),
    )

    head = _node(T.MULTIPLY, _mono(g, 1, var), wrapped)
    tail_factor = (
        wrapped if second in (1, -1) else _node(T.MULTIPLY_IMPLICIT, _num(abs(second)), wrapped)
    )
    grouped = link(_chain([(1, head), (1 if second > 0 else -1, tail_factor)]), _num(0))
    pair = _node(T.ADD if p > 0 else T.SUBTRACT, _mono(a, 2, var), _mono(p, 1, var))
    if second == -1:  # the sign goes first: -x - 2 = -(x + 2)
        signed = link(_chain([(1, pair), (-1, wrapped)]), _num(0))
        result.add_group(
            "frac_reduce_frac",
            Step(split, signed, "extract_minus"),
            Step(signed, grouped, "extract_arg", [_mono(g, 1, var)]),
        )
    else:
        headed = link(
            _chain(
                [
                    (1, head),
                    (1 if q > 0 else -1, _mono(q, 1, var)),
                    (1 if c > 0 else -1, _mono(c, 0, var)),
                ]
            ),
            _num(0),
        )
        pages = [Step(split, headed, "extract_arg", [_mono(g, 1, var)])]
        if second != 1:  # a tail that is already the bracket needs no second extraction
            pages.append(Step(headed, grouped, "extract_arg", [_num(second)]))
        else:
            grouped = headed
        result.add_group("factorise_call_plural", *pages)

    other = _poly([(g, 1), (second, 0)], var)
    product = link(_node(T.MULTIPLY, wrapped, _node(T.BRACKET, other)), _num(0))
    result.add_group("factorise_call", Step(grouped, product, "extract_arg", [bracket]))
    return product, bracket, other


def _factoring(f: _Family) -> SolveResult | None:
    result = SolveResult()
    rows = _factor_rows(f, result, T.EQUALS)
    if rows is None:
        return None
    product, bracket, other = rows
    cases = [_eq(bracket, _num(0)), _eq(other, _num(0))]
    listed = _node(T.LIST, *cases)
    result.add_group(
        "eq_separate_short", Step(product, listed, "quad_separate_zero_product", [_num(0)])
    )
    result.add_group(
        "eq_solve_short_plural",
        *[
            Step(listed, f.solved(root), "eq_linear", [f.x], subresult=_solve_linear(case, f.var))
            for case, root in zip(cases, (f.low, f.high), strict=True)
        ],
    )
    f.finish(result, [f.solved(f.low), f.solved(f.high)])
    return result


def _formula(f: _Family) -> SolveResult | None:
    a, b, c, x = f.a, f.b, f.c, f.x
    if a == 1 and b > 0 and c > 0:  # the two-product rows share the complex-root builder
        shown = _negative_discriminant(f.node, f.var, b, c)
        return shown[0] if shown else None
    if not ((a == 1 and b < 0 and c != 0) or (a > 1 and b > 0 > c)):
        return None
    result = SolveResult()
    letters = [CoreNode.variable(v) for v in "abc"]
    la, lb, lc = letters

    def square(n: CoreNode) -> CoreNode:
        return _node(T.POWER, n, _num(2))

    standard = _eq(
        _node(
            T.ADD,
            _node(
                T.ADD, _node(T.MULTIPLY_IMPLICIT, la, square(x)), _node(T.MULTIPLY_IMPLICIT, lb, x)
            ),
            lc,
        ),
        _num(0),
    )
    template = _eq(
        x,
        _node(
            T.FRACTION,
            _node(
                T.ADD_SUBTRACT,
                _node(T.NEGATIVE, lb),
                _node(
                    T.ROOT2,
                    _node(T.SUBTRACT, square(lb), _node(T.MULTIPLY, _num(4), la, lc)),
                ),
            ),
            _node(T.MULTIPLY, _num(2), la),
        ),
    )

    def state(minus_b: CoreNode, radicand: CoreNode, denominator: CoreNode) -> CoreNode:
        return _eq(
            x,
            _node(
                T.FRACTION,
                _node(T.ADD_SUBTRACT, minus_b, _node(T.ROOT2, radicand)),
                denominator,
            ),
        )

    b_sq = square(_paren(b))
    minus_b = _node(T.NEGATIVE, _paren(b))
    four_ac = 4 * a * c
    full = _node(T.SUBTRACT, b_sq, _node(T.MULTIPLY, _num(4), _num(a), _paren(c)))
    start = state(minus_b, full, _node(T.MULTIPLY, _num(2), _num(a)))
    result.add_group(
        "quad_formula_abc_simple", Step(f.node, start, "quad_formula_abc", [standard, template])
    )

    pages: list[Step] = []
    if a == 1:
        no_denominator_one = state(
            minus_b,
            _node(T.SUBTRACT, b_sq, _node(T.MULTIPLY, _num(4), _num(1), _paren(c))),
            _num(2),
        )
        short = _node(T.SUBTRACT, b_sq, _node(T.MULTIPLY, _num(4), _paren(c)))
        no_one = state(minus_b, short, _num(2))
        flipped = state(_num(-b), short, _num(2))
        powered = state(
            _num(-b), _node(T.SUBTRACT, _num(b * b), _node(T.MULTIPLY, _num(4), _paren(c))), _num(2)
        )
        # a negative 4c turns "b^2 - (-24)" into "b^2 + 24" in the same page
        merged = (
            _node(T.SUBTRACT, _num(b * b), _num(four_ac))
            if c > 0
            else _node(T.ADD, _num(b * b), _num(-four_ac))
        )
        multiplied = state(_num(-b), merged, _num(2))
        pages = [
            Step(start, no_denominator_one, "mul_with_one", [_num(1)]),
            Step(no_denominator_one, no_one, "mul_with_one", [_num(1)]),
            Step(no_one, flipped, "neg_neg_arg", [_num(-1)]),
            Step(flipped, powered, "pow", [], subresult=_evaluate(b_sq)),
            Step(
                powered,
                multiplied,
                "mul",
                [],
                subresult=_evaluate(_node(T.MULTIPLY, _num(4), _paren(c))),
            ),
        ]
        header = ["calculate_short", "remove_bracket_short", "find_value"]
        before_root, shown_b = multiplied, _num(-b)
        combine = ("sub" if c > 0 else "add", _num(f.d))
    else:
        powered = state(
            minus_b,
            _node(T.SUBTRACT, _num(b * b), _node(T.MULTIPLY, _num(4), _num(a), _paren(c))),
            _node(T.MULTIPLY, _num(2), _num(a)),
        )
        product = _node(T.MULTIPLY, _num(4), _num(a), _paren(c))
        multiplied = state(
            minus_b, _node(T.ADD, _num(b * b), _num(-four_ac)), _node(T.MULTIPLY, _num(2), _num(a))
        )
        denominator = state(minus_b, _node(T.ADD, _num(b * b), _num(-four_ac)), _num(2 * a))
        pages = [
            Step(start, powered, "pow", [], subresult=_evaluate(b_sq)),
            Step(powered, multiplied, "product", [], subresult=_evaluate(product)),
            Step(multiplied, denominator, "mul"),
        ]
        header = ["find_value", "calculate_short"]
        before_root, shown_b = denominator, minus_b
        combine = ("add", _num(f.d))
    result.add_group(header, *pages)

    summed = state(shown_b, combine[1], _num(2 * a))
    result.add_group("calculate_short", Step(before_root, summed, combine[0]))
    r = f.root
    rooted = _eq(x, _node(T.FRACTION, _node(T.ADD_SUBTRACT, shown_b, _num(r)), _num(2 * a)))
    result.add_group(
        "root" if f.d == 1 else "calculate_short",
        Step(
            summed,
            rooted,
            "root_one" if f.d == 1 else "root_square",
            [_num(1)] if f.d == 1 else [],
            subresult=None if f.d == 1 else _evaluate(_node(T.ROOT2, _num(f.d))),
        ),
    )
    branches = [
        _eq(x, _node(T.FRACTION, _node(sign, shown_b, _num(r)), _num(2 * a)))
        for sign in (T.ADD, T.SUBTRACT)
    ]
    listed = _node(T.LIST, *branches)
    result.add_group(
        "quad_separate", Step(rooted, listed, "quad_separate_signs", [_SIGNS[0], _SIGNS[1]])
    )
    roots = [Fraction(-b + r, 2 * a), Fraction(-b - r, 2 * a)]
    result.add_group(
        "calculate_short",
        *[
            Step(
                listed,
                f.solved(value),
                "calculate_direct",
                [],
                subresult=_evaluate(branch.children[1]),
            )
            for branch, value in zip(branches, roots, strict=True)
        ],
    )
    f.finish(result, [f.solved(value) for value in roots])
    return result


def _detail(expression: CoreNode, value: CoreNode) -> SolveResult:
    """A detail screen: our arithmetic steps for ``expression``, or one step when it has none."""
    detail = _evaluate(expression)
    if not detail:
        detail = SolveResult()
        detail.add_group("calculate_short", Step(expression, value, "calculate_short"))
        detail.set_solution(value)
    return detail


def _fraction_node(value: Fraction) -> CoreNode:
    if value.denominator == 1:
        return _num(value.numerator)
    return _node(T.FRACTION, _num(value.numerator), _num(value.denominator))


def _pq_formula(f: _Family) -> SolveResult | None:
    """``x^2 + p x + q = 0`` by the PQ formula, as captured for a = 1 and b < 0."""
    if f.a == 1 and f.b > 0 and f.b % 2 == 0 and f.c > 0:
        return _pq_positive(f)
    if f.a != 1 or f.b >= 0:
        return None
    b, c, x = f.b, f.c, f.x
    half = Fraction(-b, 2)  # -p/2
    result = SolveResult()
    p, q = CoreNode.variable("p"), CoreNode.variable("q")
    two = _num(2)
    standard = _eq(
        _node(
            T.ADD,
            _node(T.ADD, _node(T.POWER, x, two), _node(T.MULTIPLY_IMPLICIT, p, x)),
            q,
        ),
        _num(0),
    )
    p_half = _node(T.FRACTION, p, two)
    template = _eq(
        x,
        _node(
            T.ADD_SUBTRACT,
            _node(T.NEGATIVE, p_half),
            _node(
                T.ROOT2,
                _node(T.SUBTRACT, _node(T.POWER, _node(T.BRACKET, p_half), two), q),
            ),
        ),
    )

    def state(first: CoreNode, inner: CoreNode) -> CoreNode:
        return _eq(x, _node(T.ADD_SUBTRACT, first, _node(T.ROOT2, inner)))

    b_half = _node(T.FRACTION, _paren(b), two)
    squared = _node(T.POWER, _node(T.BRACKET, b_half), two)
    start = state(_node(T.NEGATIVE, b_half), _node(T.SUBTRACT, squared, _paren(c)))
    result.add_group(
        "quad_formula_abc_simple", Step(f.node, start, "quad_formula_pq", [standard, template])
    )
    lead = _fraction_node(half)
    signed = state(lead, _node(T.SUBTRACT, squared, _paren(c)))
    powered = state(lead, _node(T.SUBTRACT, _fraction_node(Fraction(b * b, 4)), _paren(c)))
    pages = [
        Step(
            start,
            signed,
            "frac_resolve_neg",
            [],
            subresult=_detail(_node(T.NEGATIVE, b_half), lead),
        ),
        Step(
            signed,
            powered,
            "pow_frac",
            [],
            subresult=_detail(squared, _fraction_node(Fraction(b * b, 4))),
        ),
    ]
    header = ["sign_find_short", "frac_reduce_frac"]
    current = powered
    if c < 0:  # -(-6) -> +6 in the same breath
        flipped = state(lead, _node(T.ADD, _fraction_node(Fraction(b * b, 4)), _num(-c)))
        pages.append(Step(powered, flipped, "neg_neg_arg", [_num(-1)]))
        header.append("remove_bracket_short")
        current = flipped
    result.add_group(header, *pages)
    radicand = Fraction(b * b, 4) - c
    summed = state(lead, _fraction_node(radicand))
    combine_expr = (
        _node(T.SUBTRACT, _fraction_node(Fraction(b * b, 4)), _num(c))
        if c > 0
        else _node(T.ADD, _fraction_node(Fraction(b * b, 4)), _num(-c))
    )
    result.add_group(
        "calculate_short",
        Step(
            current,
            summed,
            "calc_diff" if c > 0 else "calc_sum",
            [],
            subresult=_detail(combine_expr, _fraction_node(radicand)),
        ),
    )
    r = Fraction(f.root, 2)
    rooted = _eq(x, _node(T.ADD_SUBTRACT, lead, _fraction_node(r)))
    result.add_group(
        "calculate_short",
        Step(
            summed,
            rooted,
            "root_square",
            [],
            subresult=_detail(_node(T.ROOT2, _fraction_node(radicand)), _fraction_node(r)),
        ),
    )
    plus = _eq(x, _node(T.ADD, lead, _fraction_node(r)))
    minus = _eq(x, _node(T.SUBTRACT, lead, _fraction_node(r)))
    listed = _node(T.LIST, plus, minus)
    result.add_group("quad_separate", Step(rooted, listed, "quad_separate_signs", list(_SIGNS)))
    result.add_group(
        ["calc_sum", "calc_diff"],
        Step(
            listed,
            f.solved(half + r),
            "frac_add",
            [],
            subresult=_detail(plus.children[1], _fraction_node(half + r)),
        ),
        Step(
            listed,
            f.solved(half - r),
            "frac_sub",
            [],
            subresult=_detail(minus.children[1], _fraction_node(half - r)),
        ),
    )
    f.finish(result, [f.solved(half + r), f.solved(half - r)])
    return result


def _pq_positive(f: _Family) -> SolveResult:
    """``x^2 + p x + q = 0`` with an even ``p > 0`` and ``q > 0``, as captured for x^2 + 4x + 3."""
    b, c, x = f.b, f.c, f.x
    p, q, two = CoreNode.variable("p"), CoreNode.variable("q"), _num(2)
    standard = _eq(
        _node(T.ADD, _node(T.ADD, _node(T.POWER, x, two), _node(T.MULTIPLY_IMPLICIT, p, x)), q),
        _num(0),
    )
    p_half = _node(T.FRACTION, p, two)
    template = _eq(
        x,
        _node(
            T.ADD_SUBTRACT,
            _node(T.NEGATIVE, p_half),
            _node(T.ROOT2, _node(T.SUBTRACT, _node(T.POWER, _node(T.BRACKET, p_half), two), q)),
        ),
    )

    def state(first: CoreNode, inner: CoreNode | None) -> CoreNode:
        tail = _node(T.ROOT2, inner) if inner is not None else None
        return _eq(x, _node(T.ADD_SUBTRACT, first, tail) if tail else first)

    half = b // 2
    b_half = _node(T.FRACTION, _num(b), two)
    radicand = _node(T.SUBTRACT, _node(T.POWER, _node(T.BRACKET, b_half), two), _num(c))
    start = state(_node(T.NEGATIVE, b_half), radicand)
    result = SolveResult()
    result.add_group(
        "quad_formula_abc_simple", Step(f.node, start, "quad_formula_pq", [standard, template])
    )
    root = f.root // 2
    reduced = state(_num(-half), radicand)
    rooted = _eq(x, _node(T.ADD_SUBTRACT, _num(-half), _num(root)))
    result.add_group(
        ["frac_reduce_frac", "calculate_short"],
        Step(
            start,
            reduced,
            "frac_reduce",
            [two],
            subresult=_detail(_node(T.NEGATIVE, b_half), _num(-half)),
        ),
        Step(reduced, rooted, "calculate_direct"),
    )
    plus = _eq(x, _node(T.ADD, _num(-half), _num(root)))
    minus = _eq(x, _node(T.SUBTRACT, _num(-half), _num(root)))
    listed = _node(T.LIST, plus, minus)
    result.add_group("quad_separate", Step(rooted, listed, "quad_separate_signs", list(_SIGNS)))
    low, high = -half - root, -half + root
    result.add_group(
        ["calc_sum", "calc_diff"],
        Step(
            listed,
            f.solved(Fraction(high)),
            "calc_sum",
            [],
            subresult=_detail(plus.children[1], _num(high)),
        ),
        Step(
            listed,
            f.solved(Fraction(low)),
            "calc_diff",
            [],
            subresult=_detail(minus.children[1], _num(low)),
        ),
    )
    f.finish(result, [f.solved(Fraction(high)), f.solved(Fraction(low))])
    return result


def _completing_square(f: _Family) -> SolveResult | None:
    """Completing the square for ``x^2 + b x + c = 0`` (a = 1), captured for three sign families."""
    if f.a != 1:
        return None
    b, c, x, var = f.b, f.c, f.x, f.var
    half = Fraction(b, 2)
    left = _poly([(1, 2), (b, 1)], var)
    hole = CoreNode.variable("?")
    new = _fraction_node(half * half)
    result = SolveResult()

    moved = _eq(left, _num(-c))
    balanced = _eq(
        _node(T.ADD if c < 0 else T.SUBTRACT, f.node.children[0], _num(abs(c))),
        _node(T.ADD if c < 0 else T.SUBTRACT, _num(0), _num(abs(c))),
    )
    swap = SolveResult()
    swap.add_group("rel_swap_right_const", Step(f.node, balanced, "rel_swap_right_const"))
    swap.add_group("remove_opposites", Step(balanced, moved, "remove_opposites"))
    swap.set_solution(moved)
    result.add_group(
        "rel_move_right_const_msg", Step(f.node, moved, "rel_move_right_const", subresult=swap)
    )
    both = _eq(_node(T.ADD, left, hole), _node(T.ADD, _num(-c), hole))
    result.add_group("conics_add_both", Step(moved, both, "conics_add_both"))
    root = _node(T.BRACKET, _node(T.SUBTRACT if b < 0 else T.ADD, x, _fraction_node(abs(half))))
    identity = _eq(_node(T.ADD, left, new), _node(T.POWER, root, _num(2)))
    added = _eq(_node(T.ADD, left, new), _node(T.ADD, _num(-c), hole))
    explain = SolveResult()
    explain.add_group(
        CoreRichText(type="eq_add_exp", args=[new]), Step(both, added, "eq_add_exp", [identity])
    )
    explain.set_solution(added)
    result.add_group(
        CoreRichText(type="eq_add_exp", args=[new]),
        Step(both, added, "eq_add_exp", [identity], subresult=explain),
    )
    right = _node(T.ADD, _num(-c), new)
    equal = _eq(_node(T.ADD, left, new), right)
    result.add_group(
        CoreRichText(type="conics_add_right", args=[new]),
        Step(added, equal, "conics_add_right", [new]),
    )
    factored = _eq(_node(T.POWER, root, _num(2)), right)
    total = Fraction(-c) + half * half
    reduced = _eq(_node(T.POWER, root, _num(2)), _fraction_node(total))
    formula = _eq(
        _node(
            T.ADD,
            _node(
                T.SUBTRACT,
                _node(T.POWER, CoreNode.variable("a"), _num(2)),
                _node(T.MULTIPLY, _num(2), CoreNode.variable("a"), CoreNode.variable("b")),
            ),
            _node(T.POWER, CoreNode.variable("b"), _num(2)),
        ),
        _node(
            T.POWER,
            _node(T.BRACKET, _node(T.SUBTRACT, CoreNode.variable("a"), CoreNode.variable("b"))),
            _num(2),
        ),
    )
    factor_detail = SolveResult()
    factor_detail.add_group(
        CoreRichText(type="using_factor", args=[formula]),
        Step(equal, factored, "using_factor", [formula]),
    )
    factor_detail.set_solution(factored)
    result.add_group(
        ["frac_reduce_frac", "calculate_short"],
        Step(equal, factored, "using_factor", [formula], subresult=factor_detail),
        Step(factored, reduced, "calc_sum", [], subresult=_detail(right, _fraction_node(total))),
    )
    r = Fraction(f.root, 2)
    sides = _eq(
        _node(T.ROOT2, _node(T.POWER, root, _num(2))),
        _node(T.ADD_SUBTRACT, _node(T.ROOT2, _fraction_node(total))),
    )
    pm_row = _eq(root, _node(T.ADD_SUBTRACT, _fraction_node(r)))
    solved = _node(T.LIST, f.solved(f.low), f.solved(f.high))
    solve = SolveResult()
    solve.add_group("quad_sqrt_sides", Step(reduced, sides, "quad_sqrt_sides"))
    solve.add_group("calculate_short", Step(sides, pm_row, "root_square"))
    solve.add_group("quad_separate", Step(pm_row, solved, "quad_separate_signs", list(_SIGNS)))
    solve.set_solution(solved)
    result.add_group("eq_solve_short", Step(reduced, solved, "eq_linear", [x], subresult=solve))
    f.finish(result, [f.solved(f.low), f.solved(f.high)])
    return result


def _pq_scaled(f: _Family) -> SolveResult | None:
    """The PQ formula after dividing by ``a`` (captured for a > 1, b > 0, c < 0, c/a integral)."""
    a, b, c, x = f.a, f.b, f.c, f.x
    if a == 1 or b <= 0 or c >= 0 or c % a:
        return None
    big_p, big_q = Fraction(b, a), Fraction(c, a)
    h = big_p / 2  # p/2
    r = Fraction(f.root, 2 * a)  # sqrt((p/2)^2 - q)
    if h * h - big_q != r * r:
        return None
    two, num = _num(2), _num
    result = SolveResult()
    p_node = _fraction_node(big_p)
    divided = _eq(
        _node(
            T.SUBTRACT,
            _node(T.ADD, _node(T.POWER, x, two), _node(T.MULTIPLY_IMPLICIT, p_node, x)),
            num(-int(big_q)),
        ),
        num(0),
    )
    divide = SolveResult()
    divide.add_group(
        CoreRichText(type="eq_linear_div", args=[num(a)]),
        Step(f.node, divided, "eq_linear_div", [num(a)]),
    )
    divide.set_solution(divided)
    result.add_group(
        CoreRichText(type="divide_both_sides", args=[]),
        Step(f.node, divided, "eq_linear_div", [num(a)], subresult=divide),
    )

    p, q = CoreNode.variable("p"), CoreNode.variable("q")
    p_standard = _eq(
        _node(T.ADD, _node(T.ADD, _node(T.POWER, x, two), _node(T.MULTIPLY_IMPLICIT, p, x)), q),
        num(0),
    )
    p_half_template = _node(T.FRACTION, p, two)
    template = _eq(
        x,
        _node(
            T.ADD_SUBTRACT,
            _node(T.NEGATIVE, p_half_template),
            _node(
                T.ROOT2,
                _node(T.SUBTRACT, _node(T.POWER, _node(T.BRACKET, p_half_template), two), q),
            ),
        ),
    )

    def state(first: CoreNode, power: CoreNode, tail: CoreNode) -> CoreNode:
        return _eq(x, _node(T.ADD_SUBTRACT, first, _node(T.ROOT2, _node(T.ADD, power, tail))))

    def state_minus(first: CoreNode, power: CoreNode, tail: CoreNode) -> CoreNode:
        return _eq(x, _node(T.ADD_SUBTRACT, first, _node(T.ROOT2, _node(T.SUBTRACT, power, tail))))

    half_p = _node(T.FRACTION, p_node, two)
    squared = _node(T.POWER, _node(T.BRACKET, half_p), two)
    q_paren = _paren(int(big_q))
    start = state_minus(_node(T.NEGATIVE, half_p), squared, q_paren)
    result.add_group(
        "quad_formula_abc_simple", Step(divided, start, "quad_formula_pq", [p_standard, template])
    )
    h_node = _fraction_node(h)
    squared_h = _node(T.POWER, _node(T.BRACKET, h_node), two)
    first_page = state_minus(_node(T.NEGATIVE, h_node), squared, q_paren)
    second_page = state_minus(_node(T.NEGATIVE, h_node), squared_h, q_paren)
    third_page = state(_node(T.NEGATIVE, h_node), squared_h, num(-int(big_q)))
    result.add_group(
        ["simplify", "remove_bracket_short"],
        Step(
            start,
            first_page,
            "frac_complex_resolve_call",
            [],
            subresult=_detail(_node(T.NEGATIVE, half_p), _node(T.NEGATIVE, h_node)),
        ),
        Step(
            first_page,
            second_page,
            "frac_complex_resolve_call",
            [],
            subresult=_detail(half_p, h_node),
        ),
        Step(second_page, third_page, "neg_neg_arg", [num(-1)]),
    )
    squared_value = _fraction_node(h * h)
    powered = state(_node(T.NEGATIVE, h_node), squared_value, num(-int(big_q)))
    result.add_group(
        "pow_exp_msg",
        Step(third_page, powered, "pow_frac", [], subresult=_detail(squared_h, squared_value)),
    )
    radicand = h * h - big_q
    summed = _eq(
        x,
        _node(T.ADD_SUBTRACT, _node(T.NEGATIVE, h_node), _node(T.ROOT2, _fraction_node(radicand))),
    )
    result.add_group(
        "calculate_short",
        Step(
            powered,
            summed,
            "calc_sum",
            [],
            subresult=_detail(
                _node(T.ADD, squared_value, num(-int(big_q))), _fraction_node(radicand)
            ),
        ),
    )
    rooted = _eq(x, _node(T.ADD_SUBTRACT, _node(T.NEGATIVE, h_node), _fraction_node(r)))
    result.add_group(
        "calculate_short",
        Step(
            summed,
            rooted,
            "root_square",
            [],
            subresult=_detail(_node(T.ROOT2, _fraction_node(radicand)), _fraction_node(r)),
        ),
    )
    plus = _eq(x, _node(T.ADD, _node(T.NEGATIVE, h_node), _fraction_node(r)))
    minus = _eq(x, _node(T.SUBTRACT, _node(T.NEGATIVE, h_node), _fraction_node(r)))
    listed = _node(T.LIST, plus, minus)
    result.add_group("quad_separate", Step(rooted, listed, "quad_separate_signs", list(_SIGNS)))
    values = [-h + r, -h - r]
    result.add_group(
        ["calc_sum", "calc_diff"],
        Step(
            listed,
            f.solved(values[0]),
            "calc_sum",
            [],
            subresult=_detail(plus.children[1], _fraction_node(values[0])),
        ),
        Step(
            listed,
            f.solved(values[1]),
            "calc_diff",
            [],
            subresult=_detail(minus.children[1], _fraction_node(values[1])),
        ),
    )
    f.finish(result, [f.solved(values[1]), f.solved(values[0])])
    return result


def _is_difference_of_squares(f: _Family) -> bool:
    return f.a == 1 and f.b == 0 and f.c < 0 and isqrt(-f.c) ** 2 == -f.c


def _extraction(node: CoreNode, var: str, c: int) -> SolveResult:
    """``x^2 + c = 0`` with ``c < 0``: move the constant, take the root, split the signs."""
    x, size = CoreNode.variable(var), -c
    exact = isqrt(size) ** 2 == size
    root = _num(isqrt(size)) if exact else _node(T.ROOT2, _num(size))
    result = SolveResult()
    square = _node(T.POWER, x, _num(2))
    moved = _eq(square, _num(size))
    balanced = _eq(
        _node(T.ADD, _node(T.SUBTRACT, square, _num(size)), _num(size)),
        _node(T.ADD, _num(0), _num(size)),
    )
    swap = SolveResult()
    swap.add_group("rel_swap_right_const", Step(node, balanced, "rel_swap_right_const"))
    swap.add_group("remove_opposites", Step(balanced, moved, "remove_opposites"))
    swap.set_solution(moved)
    result.add_group(
        "rel_move_right_const_msg", Step(node, moved, "rel_move_right_const", subresult=swap)
    )
    plus_minus = _eq(x, _node(T.ADD_SUBTRACT, root))
    rooted = _eq(_node(T.ROOT2, square), _node(T.ADD_SUBTRACT, _node(T.ROOT2, _num(size))))
    take = None
    if exact:  # the root of a perfect square is evaluated on a detail screen of its own
        take = SolveResult()
        take.add_group("quad_sqrt_sides", Step(moved, rooted, "quad_sqrt_sides"))
        take.add_group("calculate_short", Step(rooted, plus_minus, "root_square"))
        take.set_solution(plus_minus)
    result.add_group("simplify_eq", Step(moved, plus_minus, "quad_sqrt_sides", subresult=take))
    negative = _num(-isqrt(size)) if exact else _node(T.NEGATIVE, root)
    solved = [_eq(x, negative), _eq(x, root)]
    listed = _node(T.LIST, *solved)
    result.add_group("quad_separate", Step(plus_minus, listed, "quad_separate_signs", list(_SIGNS)))
    count = _num(2)
    result.add_group(
        CoreRichText(type="solution_eq_num", args=[count]),
        Step(listed, listed, "solution_eq_num", [count]),
    )
    result.set_solution(listed)
    return result


def _difference_of_squares(f: _Family) -> SolveResult | None:
    """``x^2 - m^2 = (x - m)(x + m)``: factor by the formula, split the cases, solve each."""
    if not _is_difference_of_squares(f):
        return None
    m, var, x = isqrt(-f.c), f.var, f.x
    result = SolveResult()
    minus, plus = _poly([(1, 1), (-m, 0)], var), _poly([(1, 1), (m, 0)], var)
    product = _eq(_node(T.MULTIPLY, _node(T.BRACKET, minus), _node(T.BRACKET, plus)), _num(0))
    a, b = CoreNode.variable("a"), CoreNode.variable("b")
    formula = _eq(
        _node(T.SUBTRACT, _node(T.POWER, a, _num(2)), _node(T.POWER, b, _num(2))),
        _node(
            T.MULTIPLY,
            _node(T.BRACKET, _node(T.SUBTRACT, a, b)),
            _node(T.BRACKET, _node(T.ADD, a, b)),
        ),
    )
    detail = SolveResult()
    detail.add_group(
        CoreRichText(type="using_factor", args=[formula]),
        Step(f.node, product, "using_factor", [formula]),
    )
    detail.set_solution(product)
    result.add_group(
        "factorise_call", Step(f.node, product, "using_factor", [formula], subresult=detail)
    )
    cases = [_eq(minus, _num(0)), _eq(plus, _num(0))]
    listed = _node(T.LIST, *cases)
    result.add_group(
        "eq_separate_short", Step(product, listed, "quad_separate_zero_product", [_num(0)])
    )
    result.add_group(
        "eq_solve_short_plural",
        *[
            Step(
                listed,
                f.solved(Fraction(root)),
                "eq_linear",
                [x],
                subresult=_solve_linear(case, var),
            )
            for case, root in zip(cases, (m, -m), strict=True)
        ],
    )
    f.finish(result, [f.solved(Fraction(-m)), f.solved(Fraction(m))])
    return result


def _double_root(node: CoreNode, var: str, b: int, c: int) -> list[SolveResult] | None:
    """``x^2 - 2m x + m^2 = 0`` (D = 0): factoring, roots formula, PQ formula (captured shapes)."""
    m = isqrt(c) if c > 0 else 0
    if b >= 0 or b != -2 * m or m * m != c or m == 0:
        return None
    x, zero, two, num = CoreNode.variable(var), _num(0), _num(2), _num
    root = num(m)
    solution = _eq(x, root)
    base = _node(T.SUBTRACT, x, root)

    # -- factoring: (x - m)^2 = 0 -> x - m = 0 -> x = m
    a_, b_ = CoreNode.variable("a"), CoreNode.variable("b")
    formula = _eq(
        _node(
            T.ADD,
            _node(T.SUBTRACT, _node(T.POWER, a_, two), _node(T.MULTIPLY, two, a_, b_)),
            _node(T.POWER, b_, two),
        ),
        _node(T.POWER, _node(T.BRACKET, _node(T.SUBTRACT, a_, b_)), two),
    )
    squared = _eq(_node(T.POWER, _node(T.BRACKET, base), two), zero)
    factoring = SolveResult()
    factor_detail = SolveResult()
    factor_detail.add_group(
        CoreRichText(type="using_factor", args=[formula]),
        Step(node, squared, "using_factor", [formula]),
    )
    factor_detail.set_solution(squared)
    factoring.add_group(
        "factorise_call", Step(node, squared, "using_factor", [formula], subresult=factor_detail)
    )
    equated = _eq(base, zero)
    factoring.add_group(
        CoreRichText(type="log_set_base_zero", args=[zero]),
        Step(squared, equated, "eq_quad_exp_zero", [zero]),
    )
    balanced = _eq(_node(T.ADD, base, root), _node(T.ADD, zero, root))
    move = SolveResult()
    move.add_group("rel_swap_right_const", Step(equated, balanced, "rel_swap_right_const"))
    move.add_group("remove_opposites", Step(balanced, solution, "remove_opposites"))
    move.set_solution(solution)
    factoring.add_group(
        "rel_move_right_const_msg",
        Step(equated, solution, "rel_move_right_const", subresult=move),
    )
    factoring.set_solution(solution)

    # -- roots formula
    def state(first: CoreNode, inner: CoreNode | None, denominator: CoreNode) -> CoreNode:
        tail = _node(T.ROOT2, inner) if inner is not None else zero
        return _eq(x, _node(T.FRACTION, _node(T.ADD_SUBTRACT, first, tail), denominator))

    letters = [CoreNode.variable(v) for v in "abc"]
    la, lb, lc = letters
    standard = _eq(
        _node(
            T.ADD,
            _node(
                T.ADD,
                _node(T.MULTIPLY_IMPLICIT, la, _node(T.POWER, x, two)),
                _node(T.MULTIPLY_IMPLICIT, lb, x),
            ),
            lc,
        ),
        zero,
    )
    template = _eq(
        x,
        _node(
            T.FRACTION,
            _node(
                T.ADD_SUBTRACT,
                _node(T.NEGATIVE, lb),
                _node(
                    T.ROOT2,
                    _node(
                        T.SUBTRACT,
                        _node(T.POWER, lb, two),
                        _node(T.MULTIPLY, num(4), la, lc),
                    ),
                ),
            ),
            _node(T.MULTIPLY, two, la),
        ),
    )
    b_sq = _node(T.POWER, _paren(b), two)
    minus_b = _node(T.NEGATIVE, _paren(b))
    start = state(
        minus_b,
        _node(T.SUBTRACT, b_sq, _node(T.MULTIPLY, num(4), num(1), num(c))),
        _node(T.MULTIPLY, two, num(1)),
    )
    formula_m = SolveResult()
    formula_m.add_group(
        "quad_formula_abc_simple", Step(node, start, "quad_formula_abc", [standard, template])
    )
    no_den = state(minus_b, _node(T.SUBTRACT, b_sq, _node(T.MULTIPLY, num(4), num(1), num(c))), two)
    short = _node(T.SUBTRACT, b_sq, _node(T.MULTIPLY, num(4), num(c)))
    no_one = state(minus_b, short, two)
    flipped = state(num(-b), short, two)
    powered = state(num(-b), _node(T.SUBTRACT, num(b * b), _node(T.MULTIPLY, num(4), num(c))), two)
    equal_squares = _node(T.SUBTRACT, num(b * b), num(4 * c))
    multiplied = state(num(-b), equal_squares, two)
    formula_m.add_group(
        ["calculate_short", "remove_bracket_short", "find_value"],
        Step(start, no_den, "mul_with_one", [num(1)]),
        Step(no_den, no_one, "mul_with_one", [num(1)]),
        Step(no_one, flipped, "neg_neg_arg", [num(-1)]),
        Step(flipped, powered, "pow", [], subresult=_evaluate(b_sq)),
        Step(
            powered, multiplied, "mul", [], subresult=_evaluate(_node(T.MULTIPLY, num(4), num(c)))
        ),
    )
    cancelled = state(num(-b), num(0), two)
    formula_m.add_group(
        "sub_with_self_del_num", Step(multiplied, cancelled, "sub_with_self", [num(0)])
    )
    rooted = _eq(x, _node(T.FRACTION, _node(T.ADD_SUBTRACT, num(-b), num(0)), two))
    formula_m.add_group("root", Step(cancelled, rooted, "root_one", [num(0)]))
    halved = _eq(x, _node(T.FRACTION, num(-b), two))
    formula_m.add_group(
        CoreRichText(type="remove_zero", args=[num(0)]),
        Step(rooted, halved, "add_with_zero", [num(0)]),
    )
    reduction = SolveResult()
    reduction.add_group(
        CoreRichText(type="frac_reduce", args=[two]), Step(halved, solution, "frac_reduce", [two])
    )
    reduction.set_solution(solution)
    formula_m.add_group(
        "frac_reduce_frac", Step(halved, solution, "frac_reduce", [two], subresult=reduction)
    )
    formula_m.set_solution(solution)

    # -- PQ formula
    pq = SolveResult()
    p, q = CoreNode.variable("p"), CoreNode.variable("q")
    p_standard = _eq(
        _node(
            T.ADD,
            _node(T.ADD, _node(T.POWER, x, two), _node(T.MULTIPLY_IMPLICIT, p, x)),
            q,
        ),
        zero,
    )
    p_half = _node(T.FRACTION, p, two)
    p_template = _eq(
        x,
        _node(
            T.ADD_SUBTRACT,
            _node(T.NEGATIVE, p_half),
            _node(
                T.ROOT2,
                _node(T.SUBTRACT, _node(T.POWER, _node(T.BRACKET, p_half), two), q),
            ),
        ),
    )
    half_b = _node(T.FRACTION, _paren(b), two)
    p_start = _eq(
        x,
        _node(
            T.ADD_SUBTRACT,
            _node(T.NEGATIVE, half_b),
            _node(
                T.ROOT2, _node(T.SUBTRACT, _node(T.POWER, _node(T.BRACKET, half_b), two), num(c))
            ),
        ),
    )
    pq.add_group(
        "quad_formula_abc_simple", Step(node, p_start, "quad_formula_pq", [p_standard, p_template])
    )
    neg_m = _paren(-m)
    first = _eq(
        x,
        _node(
            T.ADD_SUBTRACT,
            _node(T.NEGATIVE, neg_m),
            _node(
                T.ROOT2, _node(T.SUBTRACT, _node(T.POWER, _node(T.BRACKET, half_b), two), num(c))
            ),
        ),
    )
    second = _eq(x, _node(T.ADD_SUBTRACT, _node(T.NEGATIVE, neg_m), zero))
    pq.add_group(
        ["frac_reduce_frac", "calculate_short"],
        Step(p_start, first, "frac_reduce", [two], subresult=_detail(half_b, neg_m)),
        Step(first, second, "calculate_direct"),
    )
    plain = _eq(x, _node(T.ADD_SUBTRACT, num(m), zero))
    pq.add_group("remove_bracket_short", Step(second, plain, "neg_neg_arg", [num(-1)]))
    pq.add_group(
        CoreRichText(type="remove_zero", args=[num(0)]),
        Step(plain, solution, "add_with_zero", [num(0)]),
    )
    pq.set_solution(solution)
    return [factoring, formula_m, pq]


def _discriminant_cards(
    node: CoreNode,
    a: int,
    b: int,
    c: int,
    verdict: tuple[str | CoreRichText, str, list[CoreNode]],
    count: CoreNode,
) -> tuple[SolveResult, SolveResult]:
    """Photomath's "number of solutions" and "discriminant" cards; ``verdict`` is the last row."""
    two = _num(2)
    la, lb, lc = (CoreNode.variable(v) for v in "abc")
    letters = CoreNode.variable("D")
    template = _eq(
        letters, _node(T.SUBTRACT, _node(T.POWER, lb, two), _node(T.MULTIPLY, _num(4), la, lc))
    )
    substituted = _eq(
        letters,
        _node(
            T.SUBTRACT,
            _node(T.POWER, _paren(b) if b < 0 else _num(b), two),
            _node(T.MULTIPLY, _num(4), _num(a), _paren(c) if c < 0 else _num(c)),
        ),
    )
    value = b * b - 4 * a * c
    computed = _eq(letters, _num(value))
    coefficients = [_num(a), _num(b), _num(c)]

    def rows(result: SolveResult) -> None:
        detail = SolveResult()
        detail.add_group(
            "extrema_coeff_smpl", Step(node, template, "eq_quad_coeff_identify", coefficients)
        )
        detail.set_solution(template)
        result.add_group(
            "extrema_coeff_smpl",
            Step(node, template, "eq_quad_coeff_identify", coefficients, subresult=detail),
        )
        result.add_group("coeff_sub", Step(template, substituted, "eq_quad_eval_disc_sub_smpl"))
        result.add_group(
            "calculate_short",
            Step(
                substituted,
                computed,
                "calculate_direct",
                [],
                subresult=_detail(substituted.children[1], _num(value)),
            ),
        )

    discriminant = SolveResult()
    rows(discriminant)
    discriminant.set_solution(computed)
    counting = SolveResult()
    rows(counting)
    title, key, args = verdict
    counting.add_group(title, Step(computed, count, key, args))
    counting.set_solution(count)
    return counting, discriminant


def _negative_discriminant(node: CoreNode, var: str, b: int, c: int) -> list[SolveResult] | None:
    """``x^2 + b x + c = 0`` with D = -m^2 < 0 (captured for b > 0, c > 0).

    Four methods: the roots formula to complex roots, the same formula ending at "the root of a
    negative number is not defined", and the two discriminant cards.
    """
    d = b * b - 4 * c
    m = isqrt(abs(d))
    if b <= 0 or c <= 0 or d == 0 or m * m != abs(d):
        return None
    x, two, num = CoreNode.variable(var), _num(2), _num
    unit = CoreNode.node(T.IMAGINARY)

    def imaginary(k: Fraction) -> CoreNode:
        return unit if k == 1 else _node(T.MULTIPLY_IMPLICIT, _fraction_node(k), unit)

    def state(first: CoreNode, inner: CoreNode, denominator: CoreNode) -> CoreNode:
        return _eq(
            x, _node(T.FRACTION, _node(T.ADD_SUBTRACT, first, _node(T.ROOT2, inner)), denominator)
        )

    la, lb, lc = (CoreNode.variable(v) for v in "abc")
    standard = _eq(
        _node(
            T.ADD,
            _node(
                T.ADD,
                _node(T.MULTIPLY_IMPLICIT, la, _node(T.POWER, x, two)),
                _node(T.MULTIPLY_IMPLICIT, lb, x),
            ),
            lc,
        ),
        num(0),
    )
    template = _eq(
        x,
        _node(
            T.FRACTION,
            _node(
                T.ADD_SUBTRACT,
                _node(T.NEGATIVE, lb),
                _node(
                    T.ROOT2,
                    _node(T.SUBTRACT, _node(T.POWER, lb, two), _node(T.MULTIPLY, num(4), la, lc)),
                ),
            ),
            _node(T.MULTIPLY, two, la),
        ),
    )

    def common_rows(result: SolveResult) -> CoreNode:
        minus_b = _node(T.NEGATIVE, num(b))
        full = _node(
            T.SUBTRACT, _node(T.POWER, num(b), two), _node(T.MULTIPLY, num(4), num(1), num(c))
        )
        start = state(minus_b, full, _node(T.MULTIPLY, two, num(1)))
        result.add_group(
            "quad_formula_abc_simple", Step(node, start, "quad_formula_abc", [standard, template])
        )
        no_den = state(minus_b, full, two)
        short = _node(T.SUBTRACT, _node(T.POWER, num(b), two), _node(T.MULTIPLY, num(4), num(c)))
        no_one = state(minus_b, short, two)
        powered = state(
            minus_b, _node(T.SUBTRACT, num(b * b), _node(T.MULTIPLY, num(4), num(c))), two
        )
        multiplied = state(minus_b, _node(T.SUBTRACT, num(b * b), num(4 * c)), two)
        result.add_group(
            ["calculate_short", "find_value"],
            Step(start, no_den, "mul_with_one", [num(1)]),
            Step(no_den, no_one, "mul_with_one", [num(1)]),
            Step(no_one, powered, "pow", [], subresult=_evaluate(_node(T.POWER, num(b), two))),
            Step(
                powered,
                multiplied,
                "mul",
                [],
                subresult=_evaluate(_node(T.MULTIPLY, num(4), num(c))),
            ),
        )
        negative = _node(T.NEGATIVE, num(-d)) if d < 0 else num(d)
        subtracted = state(minus_b, negative, two)
        # a negative difference has a detail screen of its own; a positive one does not
        detail = _detail(_node(T.SUBTRACT, num(b * b), num(4 * c)), negative) if d < 0 else None
        result.add_group(
            "calculate_short",
            Step(multiplied, subtracted, "calc_diff", [], subresult=detail),
        )
        return subtracted

    # -- complex roots
    complex_result = SolveResult()
    subtracted = common_rows(complex_result)
    negative_radicand = _node(T.NEGATIVE, num(-d)) if d < 0 else num(d)
    root_value = imaginary(Fraction(m)) if d < 0 else num(m)
    rooted = _eq(
        x, _node(T.FRACTION, _node(T.ADD_SUBTRACT, _node(T.NEGATIVE, num(b)), root_value), two)
    )
    complex_result.add_group(
        "calculate_short",
        Step(
            subtracted,
            rooted,
            "root_square",
            [],
            subresult=_detail(_node(T.ROOT2, negative_radicand), root_value),
        ),
    )
    parts = [
        _eq(x, _node(T.FRACTION, _node(sign, _node(T.NEGATIVE, num(b)), root_value), two))
        for sign in (T.ADD, T.SUBTRACT)
    ]
    listed = _node(T.LIST, *parts)
    complex_result.add_group(
        "quad_separate", Step(rooted, listed, "quad_separate_signs", list(_SIGNS))
    )
    real_part, imaginary_part = Fraction(-b, 2), Fraction(m, 2)

    def value(sign: T) -> CoreNode:
        if d > 0:
            return _fraction_node(
                real_part + (imaginary_part if sign is T.ADD else -imaginary_part)
            )
        return _node(sign, _fraction_node(real_part), imaginary(imaginary_part))

    roots = [_eq(x, value(T.ADD)), _eq(x, value(T.SUBTRACT))]
    complex_result.add_group(
        "simplify",
        *[
            Step(
                listed, root, "simplify", [], subresult=_detail(part.children[1], root.children[1])
            )
            for part, root in zip(parts, roots, strict=True)
        ],
    )
    answer = _node(T.LIST, *roots)
    complex_result.add_group(
        CoreRichText(type="solution_eq_num", args=[two]),
        Step(listed, answer, "solution_eq_num", [two]),
    )
    complex_result.set_solution(answer)
    if d > 0:  # real roots: Photomath's formula card only
        return [complex_result]

    # -- the same formula, stopping where the real numbers end
    real_result = SolveResult()
    subtracted = common_rows(real_result)
    real_result.add_group("expr_not_def_in_r", Step(subtracted, subtracted, "root_sqr_neg"))
    real_result.set_solution(CoreNode.empty())

    counting, discriminant = _discriminant_cards(
        node,
        1,
        b,
        c,
        ("eq_quad_disc_no_solution_simple", "eq_quad_disc_no_solution_var_lt", [num(0)]),
        CoreNode.empty(),
    )
    return [complex_result, real_result, counting, discriminant]


def _two_real_cards(node: CoreNode, a: int, b: int, c: int) -> list[SolveResult]:
    two = _num(2)
    verdict = (
        CoreRichText(type="eq_quad_disc_solution_plural_simple", args=[two]),
        "eq_quad_disc_solution_all_gt",
        [_num(0), two],
    )
    return list(_discriminant_cards(node, a, b, c, verdict, two))


def inequality_rows(
    node: CoreNode, var: str, a: int, b: int, c: int, result: SolveResult, answer: CoreNode
) -> bool:
    """``x^2 + b x + c < 0`` with b < 0 < c and rational roots, as Photomath 7.10.0 shows it.

    Factor into brackets, split into two sign cases, solve each inequality, intersect, unite.
    Returns ``False`` without touching ``result`` outside the captured family.
    """
    d = b * b - 4 * a * c
    if node.type is not T.LESS_THAN or a != 1 or b >= 0 or c <= 0 or d <= 0 or isqrt(d) ** 2 != d:
        return False
    family = _Family(var, a, b, c)
    family.node = node
    factors = _factor_rows(family, result, T.LESS_THAN)
    if factors is None:
        return False
    product, bracket, other = factors
    x, zero = family.x, _num(0)
    low, high = _num(family.low), _num(family.high)
    first, second = bracket, other

    def system(one: T, two: T) -> CoreNode:
        return _node(T.SYSTEM, _node(one, first, zero), _node(two, second, zero))

    cases = _node(T.LIST, system(T.LESS_THAN, T.GREATER_THAN), system(T.GREATER_THAN, T.LESS_THAN))
    result.add_group(
        "eq_separate_short",
        Step(
            product,
            cases,
            "ineq_product_p_two",
            [
                CoreNode.variable("<0"),
                cases.children[0],
                cases.children[1],
                product.children[0],
            ],
        ),
    )

    # x - 2 < 0 -> x < 2 and x - 3 > 0 -> x > 3, and the same for the other case
    sides = [
        (T.LESS_THAN, low, T.GREATER_THAN, high),
        (T.GREATER_THAN, low, T.LESS_THAN, high),
    ]
    pages = []
    state = cases
    for index, (one, lo, two, hi) in enumerate(sides):
        for position, (relation, value, original) in enumerate(
            ((one, lo, first), (two, hi, second))
        ):
            solved_part = _node(relation, x, value)
            items = [list(case.children) for case in state.children]
            items[index][position] = solved_part
            following = _node(T.LIST, *[_node(T.SYSTEM, *pair) for pair in items])
            pages.append(
                Step(
                    state,
                    following,
                    "ineq_linear",
                    [x],
                    subresult=_detail(_node(relation, original, zero), solved_part),
                )
            )
            state = following
    result.add_group("ineq_solve_short_plural", *pages)

    empty = _node(T.ELEMENT_OF, x, CoreNode.empty())
    interval = _node(T.ELEMENT_OF, x, _node(T.OPEN_OPEN_INTERVAL, low, high))
    reduced_first = _node(T.LIST, empty, state.children[1])
    reduced = _node(T.LIST, empty, interval)
    result.add_group(
        "intersection",
        Step(state, reduced_first, "intersection"),
        Step(reduced_first, reduced, "intersection"),
    )
    result.add_group("union", Step(reduced, answer, "union"))
    result.set_solution(answer)
    return True


def _pure_square_formulas(node: CoreNode, var: str, c: int) -> list[SolveResult]:
    """``x^2 - k^2 = 0`` by the roots formula and the PQ formula, as captured for x^2 - 4 = 0."""
    k = isqrt(-c)
    x, two, num = CoreNode.variable(var), _num(2), _num
    la, lb, lc = (CoreNode.variable(v) for v in "abc")
    p, q = CoreNode.variable("p"), CoreNode.variable("q")
    zero = num(0)
    standard = _eq(
        _node(
            T.ADD,
            _node(
                T.ADD,
                _node(T.MULTIPLY_IMPLICIT, la, _node(T.POWER, x, two)),
                _node(T.MULTIPLY_IMPLICIT, lb, x),
            ),
            lc,
        ),
        zero,
    )
    template = _eq(
        x,
        _node(
            T.FRACTION,
            _node(
                T.ADD_SUBTRACT,
                _node(T.NEGATIVE, lb),
                _node(
                    T.ROOT2,
                    _node(T.SUBTRACT, _node(T.POWER, lb, two), _node(T.MULTIPLY, num(4), la, lc)),
                ),
            ),
            _node(T.MULTIPLY, two, la),
        ),
    )
    four_ac = _node(T.MULTIPLY, num(4), num(1), _paren(c))

    def fraction(top: CoreNode, denominator: CoreNode) -> CoreNode:
        return _eq(x, _node(T.FRACTION, top, denominator))

    def pm(inner: CoreNode, with_zero: bool = False) -> CoreNode:
        root = _node(T.ROOT2, inner)
        return _node(T.ADD_SUBTRACT, zero, root) if with_zero else _node(T.ADD_SUBTRACT, root)

    # -- the roots formula
    formula = SolveResult()
    squared = _node(T.SUBTRACT, _node(T.POWER, zero, two), four_ac)
    start = fraction(
        _node(T.ADD_SUBTRACT, _node(T.NEGATIVE, zero), _node(T.ROOT2, squared)),
        _node(T.MULTIPLY, two, num(1)),
    )
    formula.add_group(
        "quad_formula_abc_simple", Step(node, start, "quad_formula_abc", [standard, template])
    )
    no_zero = fraction(pm(squared), _node(T.MULTIPLY, two, num(1)))
    no_den = fraction(pm(squared), two)
    short = _node(T.SUBTRACT, _node(T.POWER, zero, two), _node(T.MULTIPLY, num(4), _paren(c)))
    no_one = fraction(pm(short), two)
    zeroed = fraction(pm(_node(T.SUBTRACT, zero, _node(T.MULTIPLY, num(4), _paren(c)))), two)
    summed = fraction(pm(_node(T.ADD, zero, num(-4 * c))), two)
    formula.add_group(
        "calculate_short",
        Step(start, no_zero, "add_with_zero", [zero]),
        Step(no_zero, no_den, "mul_with_one", [num(1)]),
        Step(no_den, no_one, "mul_with_one", [num(1)]),
        Step(no_one, zeroed, "pow_zero", [zero]),
        Step(
            zeroed,
            summed,
            "mul",
            [],
            subresult=_evaluate(_node(T.MULTIPLY, num(4), _paren(c))),
        ),
    )
    plain = fraction(pm(num(-4 * c)), two)
    formula.add_group(
        CoreRichText(type="remove_zero", args=[zero]), Step(summed, plain, "add_with_zero", [zero])
    )
    rooted = fraction(_node(T.ADD_SUBTRACT, num(2 * k)), two)
    formula.add_group(
        "calculate_short",
        Step(
            plain,
            rooted,
            "root_square",
            [],
            subresult=_detail(_node(T.ROOT2, num(-4 * c)), num(2 * k)),
        ),
    )
    plus = fraction(num(2 * k), two)
    minus = fraction(_node(T.NEGATIVE, num(2 * k)), two)
    listed = _node(T.LIST, plus, minus)
    formula.add_group("quad_separate", Step(rooted, listed, "quad_separate_signs", list(_SIGNS)))
    low, high = _eq(x, num(-k)), _eq(x, num(k))
    answer = _node(T.LIST, high, low)
    formula.add_group(
        "frac_reduce_frac",
        Step(
            listed,
            _node(T.LIST, high, minus),
            "frac_reduce",
            [two],
            subresult=_detail(plus.children[1], num(k)),
        ),
        Step(
            _node(T.LIST, high, minus),
            answer,
            "frac_reduce",
            [two],
            subresult=_detail(minus.children[1], num(-k)),
        ),
    )
    formula.add_group(
        CoreRichText(type="solution_eq_num", args=[two]),
        Step(answer, answer, "solution_eq_num", [two]),
    )
    formula.set_solution(answer)

    # -- the PQ formula
    pq = SolveResult()
    p_half = _node(T.FRACTION, p, two)
    p_standard = _eq(
        _node(T.ADD, _node(T.ADD, _node(T.POWER, x, two), _node(T.MULTIPLY_IMPLICIT, p, x)), q),
        zero,
    )
    p_template = _eq(
        x,
        _node(
            T.ADD_SUBTRACT,
            _node(T.NEGATIVE, p_half),
            _node(T.ROOT2, _node(T.SUBTRACT, _node(T.POWER, _node(T.BRACKET, p_half), two), q)),
        ),
    )
    zero_half = _node(T.FRACTION, zero, two)
    inner = _node(T.SUBTRACT, _node(T.POWER, _node(T.BRACKET, zero_half), two), _paren(c))
    first = _eq(x, _node(T.ADD_SUBTRACT, _node(T.NEGATIVE, zero_half), _node(T.ROOT2, inner)))
    pq.add_group(
        "quad_formula_abc_simple", Step(node, first, "quad_formula_pq", [p_standard, p_template])
    )
    divided = _eq(
        x,
        _node(
            T.ADD_SUBTRACT,
            _node(T.NEGATIVE, zero),
            _node(
                T.ROOT2, _node(T.SUBTRACT, _node(T.POWER, _node(T.BRACKET, zero), two), _paren(c))
            ),
        ),
    )
    valued = _eq(x, _node(T.ADD_SUBTRACT, _node(T.NEGATIVE, zero), num(k)))
    pq.add_group(
        ["divide", "calculate_short"],
        Step(first, divided, "div_zero", [zero]),
        Step(divided, valued, "calculate_direct"),
    )
    cleaned = _eq(x, _node(T.ADD_SUBTRACT, num(k)))
    pq.add_group(
        CoreRichText(type="remove_zero", args=[zero]),
        Step(valued, cleaned, "add_with_zero", [zero]),
    )
    pair = _node(T.LIST, _eq(x, num(k)), _eq(x, num(-k)))
    pq.add_group("quad_separate", Step(cleaned, pair, "quad_separate_signs", list(_SIGNS)))
    pq.add_group(
        CoreRichText(type="solution_eq_num", args=[two]), Step(pair, pair, "solution_eq_num", [two])
    )
    pq.set_solution(pair)
    return [formula, pq]


def methods(
    node: CoreNode, var: str, a: Fraction, b: Fraction, c: Fraction
) -> list[SolveResult] | None:
    """Photomath's methods for the verified family, or ``None`` to use the general solver."""
    if any(v.denominator != 1 for v in (a, b, c)):
        return None
    ia, ib, ic = int(a), int(b), int(c)
    d = ib * ib - 4 * ia * ic
    if d == 0 and ia == 1 and (double := _double_root(node, var, ib, ic)) is not None:
        return double
    if d < 0 and ia == 1 and (negative := _negative_discriminant(node, var, ib, ic)) is not None:
        return negative
    if ia == 1 and ib == 0 and ic < 0:
        shown: list[SolveResult | None] = [_extraction(node, var, ic)]
        if isqrt(-ic) ** 2 == -ic:
            shown.append(_difference_of_squares(_Family(var, ia, ib, ic)))
            shown += _pure_square_formulas(node, var, ic)
        if isqrt(-ic) ** 2 != -ic:
            shown += _two_real_cards(node, ia, ib, ic)
        return [m for m in shown if m]
    if ia == 0 or ib == 0 or ic == 0 or d <= 0 or isqrt(d) ** 2 != d:
        return None
    family = _Family(var, ia, ib, ic)
    primary = [m for m in (_factoring(family), _formula(family)) if m]
    if not primary:  # outside the captured sign families the general solver explains it
        return None
    built = primary + [
        m for m in (_pq_formula(family), _pq_scaled(family), _completing_square(family)) if m
    ]
    if ia > 1:  # Photomath adds the two discriminant cards when the leading coefficient is not 1
        built += _two_real_cards(node, ia, ib, ic)
    return built or None
