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
from .base import SolveContext, SolveResult, Step, route

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
    detail.set_solution(route(node, SolveContext(result=detail)))
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
    if q >= 0 or q % lead or c != second * rest:
        return None
    result = SolveResult()

    bracket = _poly([(lead, 1), (rest, 0)], var)
    wrapped = _node(T.BRACKET, bracket)
    split = _eq(_poly([(a, 2), (p, 1), (q, 1), (c, 0)], var), _num(0))
    result.add_group(
        "rewrite_expression",
        Step(f.node, split, "write_as_diff", [_chain([(1 if b > 0 else -1, _mono(b, 1, var))])]),
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
            _chain([(1, head), (-1, _mono(q, 1, var)), (1 if c > 0 else -1, _mono(c, 0, var))]),
            _num(0),
        )
        result.add_group(
            "factorise_call_plural",
            Step(split, headed, "extract_arg", [_mono(g, 1, var)]),
            Step(headed, grouped, "extract_arg", [_num(second)]),
        )

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
    if not ((a == 1 and b < 0 < c) or (a > 1 and b > 0 > c)):
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
            _num(-b), _node(T.SUBTRACT, _num(b * b), _node(T.MULTIPLY, _num(4), _num(c))), _num(2)
        )
        multiplied = state(_num(-b), _node(T.SUBTRACT, _num(b * b), _num(four_ac)), _num(2))
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
                subresult=_evaluate(_node(T.MULTIPLY, _num(4), _num(c))),
            ),
        ]
        header = ["calculate_short", "remove_bracket_short", "find_value"]
        before_root, shown_b = multiplied, _num(-b)
        combine = ("sub", _num(b * b - four_ac))
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
        "root" if a == 1 else "calculate_short",
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


def _is_difference_of_squares(f: _Family) -> bool:
    return f.a == 1 and f.b == 0 and f.c < 0 and isqrt(-f.c) ** 2 == -f.c


def _extraction(f: _Family) -> SolveResult | None:
    """``x^2 - m^2 = 0``: move the constant, take the root of both sides, split the signs."""
    if not _is_difference_of_squares(f):
        return None
    m, x = isqrt(-f.c), f.x
    result = SolveResult()
    square = _node(T.POWER, x, _num(2))
    moved = _eq(square, _num(-f.c))
    balanced = _eq(
        _node(T.ADD, _node(T.SUBTRACT, square, _num(-f.c)), _num(-f.c)),
        _node(T.ADD, _num(0), _num(-f.c)),
    )
    swap = SolveResult()
    swap.add_group("rel_swap_right_const", Step(f.node, balanced, "rel_swap_right_const"))
    swap.add_group("remove_opposites", Step(balanced, moved, "remove_opposites"))
    swap.set_solution(moved)
    result.add_group(
        "rel_move_right_const_msg", Step(f.node, moved, "rel_move_right_const", subresult=swap)
    )
    plus_minus = _eq(x, _node(T.ADD_SUBTRACT, _num(m)))
    rooted = _eq(_node(T.ROOT2, square), _node(T.ADD_SUBTRACT, _node(T.ROOT2, _num(-f.c))))
    take = SolveResult()
    take.add_group("quad_sqrt_sides", Step(moved, rooted, "quad_sqrt_sides"))
    take.add_group("calculate_short", Step(rooted, plus_minus, "root_square"))
    take.set_solution(plus_minus)
    result.add_group("simplify_eq", Step(moved, plus_minus, "quad_sqrt_sides", subresult=take))
    solved = [f.solved(Fraction(-m)), f.solved(Fraction(m))]
    listed = _node(T.LIST, *solved)
    result.add_group("quad_separate", Step(plus_minus, listed, "quad_separate_signs", list(_SIGNS)))
    f.finish(result, solved)
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
    detail.add_group("using_factor", Step(f.node, product, "using_factor", [formula]))
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


def methods(
    node: CoreNode, var: str, a: Fraction, b: Fraction, c: Fraction
) -> list[SolveResult] | None:
    """Photomath's methods for the verified family, or ``None`` to use the general solver."""
    if any(v.denominator != 1 for v in (a, b, c)):
        return None
    ia, ib, ic = int(a), int(b), int(c)
    d = ib * ib - 4 * ia * ic
    if ia == 0 or ic == 0 or d <= 0 or isqrt(d) ** 2 != d:
        return None
    family = _Family(var, ia, ib, ic)
    if ib == 0:
        built = [m for m in (_extraction(family), _difference_of_squares(family)) if m]
        return built or None
    built = [m for m in (_factoring(family), _formula(family)) if m]
    return built or None
