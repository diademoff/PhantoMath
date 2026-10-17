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


def _factoring(f: _Family) -> SolveResult | None:
    a, b, c, var = f.a, f.b, f.c, f.var
    p, q = (b + f.root) // 2, (b - f.root) // 2  # p + q = b, p q = a c, p > q
    g = gcd(a, abs(p))
    lead, rest = a // g, p // g
    second = q // lead
    # a positive second term was captured for a = 1 with a tail equal to the bracket (x^2 + 4x + 3)
    if q == 0 or q % lead or c != second * rest or (q > 0 and (a != 1 or second != 1)):
        return None
    result = SolveResult()

    bracket = _poly([(lead, 1), (rest, 0)], var)
    wrapped = _node(T.BRACKET, bracket)
    split = _eq(_poly([(a, 2), (p, 1), (q, 1), (c, 0)], var), _num(0))
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
    grouped = _eq(_chain([(1, head), (1 if second > 0 else -1, tail_factor)]), _num(0))
    pair = _node(T.ADD if p > 0 else T.SUBTRACT, _mono(a, 2, var), _mono(p, 1, var))
    if second == -1:  # the sign goes first: -x - 2 = -(x + 2)
        signed = _eq(_chain([(1, pair), (-1, wrapped)]), _num(0))
        result.add_group(
            "frac_reduce_frac",
            Step(split, signed, "extract_minus"),
            Step(signed, grouped, "extract_arg", [_mono(g, 1, var)]),
        )
    else:
        headed = _eq(
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
    product = _eq(_node(T.MULTIPLY, wrapped, _node(T.BRACKET, other)), _num(0))
    result.add_group("factorise_call", Step(grouped, product, "extract_arg", [bracket]))
    cases = [_eq(bracket, _num(0)), _eq(other, _num(0))]
    listed = _node(T.LIST, *cases)
    result.add_group(
        "eq_separate_short", Step(product, listed, "quad_separate_zero_product", [_num(0)])
    )
    result.add_group(
        "eq_solve_short_plural",
        *[
            Step(listed, f.solved(root), "eq_linear", [f.x], subresult=_solve_linear(case, var))
            for case, root in zip(cases, (f.low, f.high), strict=True)
        ],
    )
    f.finish(result, [f.solved(f.low), f.solved(f.high)])
    return result


def _formula(f: _Family) -> SolveResult | None:
    a, b, c, x = f.a, f.b, f.c, f.x
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
    if ia == 1 and ib == 0 and ic < 0:
        shown: list[SolveResult | None] = [_extraction(node, var, ic)]
        if isqrt(-ic) ** 2 == -ic:
            shown.append(_difference_of_squares(_Family(var, ia, ib, ic)))
        return [m for m in shown if m]
    if ia == 0 or ib == 0 or ic == 0 or d <= 0 or isqrt(d) ** 2 != d:
        return None
    family = _Family(var, ia, ib, ic)
    primary = [m for m in (_factoring(family), _formula(family)) if m]
    if not primary:  # outside the captured sign families the general solver explains it
        return None
    built = primary + [m for m in (_pq_formula(family), _completing_square(family)) if m]
    return built or None
