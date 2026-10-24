"""Quadratic equations with integer coefficients, as the app shows them.

Every method the app offers becomes a card (rows are main steps, the steps inside a
row are its stages): factoring by splitting the middle term, the roots formula, the
PQ formula, completing the square and the two counting cards. The verified device
families keep their exact rows; the rest are built from the same rows and generalized
to irrational and complex roots, a missing constant, a constant on the right side
and the square-extraction families. Only inputs outside that surface (decimal
coefficients, ``x^0``/``x^-1``/``x^0.5``, a negative lead with complex roots — those
keep the two-card general path) do not get this card set.
"""

from __future__ import annotations

from fractions import Fraction
from math import gcd, isqrt

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .arithmetic import format_number
from .base import SolveContext, SolveError, SolveResult, Step, route
from .sympy_bridge import from_sympy

_SIGNS = (
    CoreNode.variable("+"),
    CoreNode.variable("−"),
)  # arguments of "one with + and one with -"


def _num(value: int | Fraction) -> CoreNode:
    return CoreNode.constant(format_number(Fraction(value)))


def _number(value: int | Fraction) -> CoreNode:
    """A value as the app writes it here: ``3`` but ``0.5``/``6.5``, not ``1/2``."""
    value = Fraction(value)
    if value.denominator == 1:
        return _num(value)
    return CoreNode.constant(str(float(value)))


def _node(kind: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(kind, *children)


def _paren(value: int | Fraction) -> CoreNode:
    value = Fraction(value)
    inner = _num(value) if value.denominator == 1 else _fraction_node(value)
    return _node(T.BRACKET, inner) if value < 0 else inner


def _decimal_paren(value: int | Fraction) -> CoreNode:
    """Bracketed decimal for the counting cards (``(-0.5)``), where the app keeps ``0.5``."""
    return _node(T.BRACKET, _number(value)) if value < 0 else _number(value)


def _eq(left: CoreNode, right: CoreNode) -> CoreNode:
    return _node(T.EQUALS, left, right)


def _mono(coefficient: int | Fraction, degree: int, var: str) -> CoreNode:
    """``|c| x^degree``; a coefficient of 1 is left out."""
    x = CoreNode.variable(var)
    base = {2: _node(T.POWER, x, _num(2)), 1: x}.get(degree)
    size = abs(Fraction(coefficient))
    magnitude = _num(size) if size.denominator == 1 else _fraction_node(size)
    if base is None:
        return magnitude
    return base if size == 1 else _node(T.MULTIPLY_IMPLICIT, magnitude, base)


def _chain(items: list[tuple[int, CoreNode]]) -> CoreNode:
    """``±t1 ± t2 …`` as a left-leaning chain; a leading minus is a NEGATIVE node."""
    sign, first = items[0]
    out = _node(T.NEGATIVE, first) if sign < 0 else first
    for sign, term in items[1:]:
        out = _node(T.SUBTRACT if sign < 0 else T.ADD, out, term)
    return out


def _poly(terms: list[tuple[int | Fraction, int]], var: str) -> CoreNode:
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


def _number_value(node: CoreNode) -> Fraction | None:
    """Value of a numeric part (``3``, ``-3`` or ``−3``), ``None`` for anything else."""
    sign = 1
    if node.type is T.NEGATIVE and node.children:
        sign, node = -1, node.children[0]
    if node.type is not T.CONSTANT or node.value is None:
        return None
    try:
        return sign * Fraction(str(node.value).replace("−", "-"))
    except (ValueError, ZeroDivisionError):
        return None


def _root_values(a: int, b: int, c: int | Fraction) -> list[sympy.Basic]:
    """Both roots as sympy values, low first (for complex ones: minus the imaginary part)."""
    difference = Fraction(b * b) - 4 * Fraction(a) * Fraction(c)
    d = sympy.Rational(difference.numerator, difference.denominator)
    values = [
        sympy.simplify((sympy.Rational(-b) + sign * sympy.sqrt(d)) / sympy.Rational(2 * a))
        for sign in (-1, 1)
    ]
    values.sort(key=lambda value: (float(sympy.re(value)), float(sympy.im(value))))
    return values


def _root_nodes(a: int, b: int, c: int | Fraction) -> list[CoreNode]:
    """Both roots as the app writes them, low first."""
    return [from_sympy(value) for value in _root_values(a, b, c)]


def _imaginary(value: CoreNode) -> CoreNode:
    """``k`` -> ``k i``; a bare ``i`` for ``1``."""
    unit = CoreNode.constant("i")
    if value.type is T.CONSTANT and str(value.value) == "1":
        return unit
    return _node(T.MULTIPLY_IMPLICIT, value, unit)


def _surd(value: Fraction) -> CoreNode:
    """``√value`` in the short form the app writes (``2√2``, ``√13/2``)."""
    return from_sympy(sympy.sqrt(sympy.Rational(value)))


class _Family:
    """``a x^2 + b x + c = 0``; ``a`` and ``b`` are integers, ``c`` may be a fraction.

    The app keeps a decimal constant as a fraction in the PQ and completing-the-square
    cards (``0.5`` → ``1/2``), so those builders take ``c`` as a ``Fraction``; the
    discriminant stays an integer because a one-decimal ``c`` is a half.
    """

    def __init__(
        self,
        var: str,
        a: int,
        b: int,
        c: int | Fraction,
        typed_rhs: Fraction | None = None,
    ) -> None:
        self.var, self.a, self.b = var, a, b
        self.c = Fraction(c).numerator if Fraction(c).denominator == 1 else Fraction(c)
        self.typed_rhs = typed_rhs
        # ``a`` and ``b`` are integers, so a one-decimal ``c`` gives an integer discriminant
        self.d: int = int(b * b - 4 * a * self.c)
        self.root = isqrt(self.d) if self.d >= 0 else 0
        self.x = CoreNode.variable(var)
        self.node = _eq(_poly([(a, 2), (b, 1), (c, 0)], var), _num(0))
        self.low, self.high = sorted(
            (Fraction(-b - self.root, 2 * a), Fraction(-b + self.root, 2 * a))
        )

    @property
    def exact(self) -> bool:
        """Whether the discriminant has an integer square root."""
        return self.d >= 0 and isqrt(self.d) ** 2 == self.d

    def solved(self, root: Fraction) -> CoreNode:
        return _eq(self.x, _num(root))

    def roots(self) -> list[CoreNode]:
        """``x = …`` for both roots, irrational and complex ones included."""
        if self.exact:
            return [self.solved(self.low), self.solved(self.high)]
        return [_eq(self.x, value) for value in _root_nodes(self.a, self.b, self.c)]

    def finish(self, result: SolveResult, cases: list[CoreNode]) -> None:
        solution = _node(T.LIST, self.solved(self.low), self.solved(self.high))
        result.add_group(
            CoreRichText(type="solution_eq_num", args=[_num(2)]),
            Step(_node(T.LIST, *cases), solution, "solution_eq_num", [_num(2)]),
        )
        result.set_solution(solution)

    def finish_roots(self, result: SolveResult, before: CoreNode) -> CoreNode:
        """Last row: the two ``x = …`` from :meth:`roots`; returns the answer node."""
        solution = _node(T.LIST, *self.roots())
        result.add_group(
            CoreRichText(type="solution_eq_num", args=[_num(2)]),
            Step(before, solution, "solution_eq_num", [_num(2)]),
        )
        result.set_solution(solution)
        return solution


def _factor_rows(
    f: _Family, result: SolveResult, relation: T | None
) -> tuple[CoreNode, CoreNode, CoreNode] | None:
    """The three rows that turn ``a x^2 + b x + c (relation) 0`` into a product of brackets."""
    a, b, c, var = f.a, f.b, f.c, f.var

    def link(left: CoreNode, right: CoreNode) -> CoreNode:
        return left if relation is None else _node(relation, left, right)

    p, q = (b + f.root) // 2, (b - f.root) // 2  # p + q = b, p q = a c, p > q
    g = gcd(a, abs(p))
    lead, rest = a // g, p // g
    second = q // lead
    # positive terms were worked out for a = 1: x^2 + 4x + 3 and, as an expression, x^2 + 5x + 6
    if q == 0 or q % lead or c != second * rest:
        return None
    bracket = _poly([(lead, 1), (rest, 0)], var)
    wrapped = _node(T.BRACKET, bracket)
    split = link(_poly([(a, 2), (p, 1), (q, 1), (c, 0)], var), _num(0))
    result.add_group(
        "rewrite_expression",
        Step(
            f.node,
            split,
            "write_as_sum_fact" if q > 0 else "write_as_diff_fact",
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


def _formula(f: _Family, real_only: bool = False) -> SolveResult | None:
    a, b, c, x = f.a, f.b, f.c, f.x
    if a == 1 and b > 0 and c > 0 and isinstance(c, int):  # complex-root builder
        shown = _negative_discriminant(f.node, f.var, b, c)
        if shown:
            return shown[0]
    if c == 0 or a <= 0:
        return None
    if a == 1 and b == 0 and c < 0:
        return None  # ``x² − k`` belongs to the extraction family
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

    def merged_radicand() -> CoreNode:
        """``b^2 - 4ac`` after the product: a negative ``4ac`` turns into a plus."""
        if c > 0:
            return _node(T.SUBTRACT, _num(b * b), _num(four_ac))
        return _node(T.ADD, _num(b * b), _num(-four_ac))

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
            Step(flipped, powered, "pow", [], subresult=_squared_page(b_sq, b, b * b)),
            Step(
                powered,
                multiplied,
                "mul",
                [],
                subresult=_product_page(
                    _node(T.MULTIPLY, _num(4), _paren(c)), 4 * c, subtracted=c > 0
                ),
            ),
        ]
        header = ["calculate_short", "remove_bracket_short", "find_value"]
        before_root, shown_b = multiplied, _num(-b)
        if b > 0:  # worked out for x^2 + x - 6: -b keeps its sign, the power page is "1^n = 1"
            powered = state(minus_b, _node(T.SUBTRACT, _num(b * b), short.children[1]), _num(2))
            multiplied = state(minus_b, merged, _num(2))
            power_page = (
                Step(no_one, powered, "pow_one", [_num(1)])
                if b == 1
                else Step(
                    no_one,
                    powered,
                    "pow",
                    [],
                    subresult=_squared_page(b_sq, b, b * b),
                )
            )
            pages = [
                Step(start, no_denominator_one, "mul_with_one", [_num(1)]),
                Step(no_denominator_one, no_one, "mul_with_one", [_num(1)]),
                power_page,
                Step(
                    powered,
                    multiplied,
                    "mul",
                    [],
                    subresult=_product_page(
                        _node(T.MULTIPLY, _num(4), _paren(c)), 4 * c, subtracted=c > 0
                    ),
                ),
            ]
            header = ["calculate_short", "find_value"]
            before_root, shown_b = multiplied, minus_b
        combine = ("sub" if c > 0 else "add", _num(f.d))
    else:
        powered = state(
            minus_b,
            _node(T.SUBTRACT, _num(b * b), _node(T.MULTIPLY, _num(4), _num(a), _paren(c))),
            _node(T.MULTIPLY, _num(2), _num(a)),
        )
        multiplied = state(minus_b, merged_radicand(), _node(T.MULTIPLY, _num(2), _num(a)))
        denominator = state(minus_b, merged_radicand(), _num(2 * a))
        pages = [
            Step(start, powered, "pow", [], subresult=_squared_page(b_sq, b, b * b)),
            Step(powered, multiplied, "product", [], subresult=_product_pow_page(a, c)),
            Step(multiplied, denominator, "mul"),
        ]
        header = ["find_value", "calculate_short"]
        before_root, shown_b = denominator, minus_b
        if b < 0:  # worked out for 2x^2 - x - 1: -(-b) loses its brackets on the first page
            flipped = state(_num(-b), full, _node(T.MULTIPLY, _num(2), _num(a)))

            def after(radicand: CoreNode) -> CoreNode:
                return state(_num(-b), radicand, _node(T.MULTIPLY, _num(2), _num(a)))

            powered = after(
                _node(T.SUBTRACT, _num(b * b), _node(T.MULTIPLY, _num(4), _num(a), _paren(c)))
            )
            multiplied = after(merged_radicand())
            denominator = state(_num(-b), merged_radicand(), _num(2 * a))
            pages = [
                Step(start, flipped, "neg_neg_arg", [_num(-1)]),
                Step(flipped, powered, "pow", [], subresult=_squared_page(b_sq, b, b * b)),
                Step(powered, multiplied, "product", [], subresult=_product_pow_page(a, c)),
                Step(multiplied, denominator, "mul"),
            ]
            header = ["remove_bracket_short", "find_value", "calculate_short"]
            before_root, shown_b = denominator, _num(-b)
        combine = ("add" if c < 0 else "sub", _num(f.d))
    result.add_group(header, *pages)

    summed = state(shown_b, combine[1], _num(2 * a))
    result.add_group("calculate_short", Step(before_root, summed, combine[0]))
    exact = f.d >= 0 and isqrt(f.d) ** 2 == f.d
    if not exact:
        return _formula_irrational(f, result, summed, shown_b, real_only)
    r = f.root
    rooted = _eq(x, _node(T.FRACTION, _node(T.ADD_SUBTRACT, shown_b, _num(r)), _num(2 * a)))
    result.add_group(
        "root" if f.d == 1 else "calculate_short",
        Step(
            summed,
            rooted,
            "root_one" if f.d == 1 else "root_square",
            [_num(1)] if f.d == 1 else [],
            subresult=(
                None
                if f.d == 1
                else _root_page(f.d, f.root)
                if isqrt(f.d) ** 2 == f.d
                else _evaluate(_node(T.ROOT2, _num(f.d)))
            ),
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
                "simplify"
                if _branch_key(-b, 1 if _numerator_sign(branch) > 0 else -1, f.root) == "sub"
                and value.denominator != 1
                else "calculate_direct",
                [],
                subresult=_branch_page(
                    -b,
                    1 if _numerator_sign(branch) > 0 else -1,
                    f.root,
                    2 * a,
                    value,
                ),
            )
            for branch, value in zip(branches, roots, strict=True)
        ],
    )
    f.finish(result, [f.solved(value) for value in roots])
    return result


def _formula_irrational(
    f: _Family, result: SolveResult, summed: CoreNode, shown_b: CoreNode, real_only: bool
) -> SolveResult:
    """Roots formula when ``√D`` does not evaluate: a surd, or an imaginary root.

    The app keeps the same rows and ends with ``root_partial`` (``√8 = 2√2``) or
    ``root_square`` (``√−11 = √11i``), then splits the signs and simplifies each branch.
    """
    x, two_a = f.x, _num(2 * f.a)
    if f.d < 0:
        radicand = _node(T.NEGATIVE, _num(-f.d))
        radical = _imaginary(from_sympy(sympy.sqrt(-f.d)))
        root_group, root_key = "calculate_short", "root_square"
        end_group, end_key = "separate", "complex_separate"
    else:
        radicand = _num(f.d)
        radical = _surd(Fraction(f.d))
        root_group, root_key = "simplify", "root_partial"
        end_group, end_key = "simplify_msg", "simplify"
    carried = _eq(x, _node(T.FRACTION, _node(T.ADD_SUBTRACT, shown_b, radical), two_a))
    result.add_group(
        "root_simplify" if f.d < 0 else root_group,
        Step(summed, carried, root_key, [], subresult=_evaluate(_node(T.ROOT2, radicand))),
    )
    branches = [
        _eq(x, _node(T.FRACTION, _node(sign, shown_b, radical), two_a))
        for sign in (T.ADD, T.SUBTRACT)
    ]
    listed = _node(T.LIST, *branches)
    result.add_group("quad_separate", Step(carried, listed, "quad_separate_signs", list(_SIGNS)))
    if real_only:
        result.add_group("expr_not_def_in_r", Step(listed, listed, "root_sqr_neg"))
        result.set_solution(CoreNode.empty())
        return result
    values = list(reversed(_root_nodes(f.a, f.b, f.c)))
    result.add_group(
        end_group,
        *[
            Step(
                listed,
                _eq(x, value),
                end_key,
                [],
                subresult=_fraction_page(branch.children[1], value, reduce_result=f.d > 0),
            )
            for branch, value in zip(branches, values, strict=True)
        ],
    )
    f.finish_roots(result, listed)
    return result


def _detail(expression: CoreNode, value: CoreNode) -> SolveResult:
    """A detail screen: our arithmetic steps for ``expression``, or one step when it has none."""
    detail = _evaluate(expression)
    if not detail:
        detail = SolveResult()
        detail.add_group("calculate_short", Step(expression, value, "calculate_short"))
        detail.set_solution(value)
    return detail


def _signed_sum_page(expression: CoreNode, value: CoreNode, key: str) -> SolveResult:
    """Detail page for an addition with a negative term: pull out the sign, then compute."""
    detail = SolveResult()
    detail.add_group("add_sign_sub", Step(expression, expression, "add_sign_sub"))
    detail.add_group("calculate_short", Step(expression, value, key))
    detail.set_solution(value)
    return detail


def _squared_page(expression: CoreNode, base: int, value: int) -> SolveResult:
    """The app page for a numeric square: ``(-5)² = 5² = 5·5 = 25``."""
    detail = SolveResult()
    current = expression
    if base < 0:
        positive_square = _node(T.POWER, _num(-base), _num(2))
        detail.add_group("pow_even", Step(current, positive_square, "pow_even"))
        current = positive_square
    if abs(base) == 1:
        detail.add_group("calculate_short", Step(current, _num(1), "pow_one", [_num(1)]))
        detail.set_solution(_num(1))
        return detail
    expanded = _node(T.MULTIPLY, _num(abs(base)), _num(abs(base)))
    detail.add_group("pow_to_mul", Step(current, expanded, "pow_to_mul"))
    detail.add_group("calculate_short", Step(expanded, _num(value), "mul"))
    detail.set_solution(_num(value))
    return detail


def _product_page(expression: CoreNode, value: int | Fraction, subtracted: bool) -> SolveResult:
    """The app page for ``4·c``: a subtracted product is pulled out with a minus first."""
    detail = SolveResult()
    if not subtracted:
        detail.add_group(
            "mul_neg_neg",
            Step(expression, expression, "mul_neg_neg", [CoreNode.variable("−")]),
        )
        detail.add_group("calculate_short", Step(expression, _num(-value), "mul"))
        detail.set_solution(_num(-value))
        return detail
    # The app (quad_complex): (−4)·5 → −(4·5) → −20; the row outside shows 4 − 20
    factors = list(expression.children) if expression.type is T.MULTIPLY else [expression]
    signed = _node(T.MULTIPLY, _node(T.NEGATIVE, factors[0]), *factors[1:])
    pulled = _node(T.NEGATIVE, _node(T.BRACKET, expression))
    detail.add_group("mul_neg_pos", Step(signed, pulled, "mul_neg_pos", [CoreNode.variable("−")]))
    detail.add_group("calculate_short", Step(pulled, _num(-value), "mul"))
    detail.set_solution(_num(-value))
    return detail


def _numerator_sign(branch: CoreNode) -> int:
    """Sign of the ``±`` in ``x = (… ± √D) / 2a`` (the numerator of the branch)."""
    numerator = branch.children[1]
    if numerator.type is T.FRACTION and numerator.children:
        numerator = numerator.children[0]
    return 1 if numerator.type is T.ADD else -1


def _branch_key(shown: int, sign: int, root: int) -> str:
    """Arithmetic row of a formula branch: ``add``/``calc_sum``/``sub``/``calc_diff``."""
    numerator = shown + sign * root
    if sign > 0:
        return "add" if shown > 0 else "calc_sum"
    return "calc_diff" if numerator < 0 else "sub"


def _pq_power_page(squared: CoreNode, value: CoreNode, *, numerator_one: bool) -> SolveResult:
    """Detail page for ``(b/2)^2`` in the PQ formula: the fraction, then both powers."""
    base = squared.children[0]
    inner = base.children[0] if base.type is T.BRACKET and base.children else base
    fraction = inner.children[0] if inner.type is T.NEGATIVE and inner.children else inner
    numerator, denominator = fraction.children
    split = _node(
        T.FRACTION,
        _node(T.POWER, numerator, _num(2)),
        _node(T.POWER, denominator, _num(2)),
    )
    detail = SolveResult()
    detail.add_group("pow_frac", Step(squared, split, "pow_frac"))
    if numerator_one:
        detail.add_group("calculate_short", Step(split, split, "pow_one", [_num(1)]))
        detail.add_group("pow", Step(split, value, "pow"))
    else:
        detail.add_group(
            "pow",
            Step(
                split,
                _fraction_node(
                    Fraction(int(numerator.value or 0) ** 2, int(denominator.value or 1) ** 2)
                ),
                "pow",
            ),
        )
        detail.add_group("pow", Step(split, value, "pow"))
    detail.set_solution(value)
    return detail


def _signed_branch_page(expression: CoreNode, value: CoreNode) -> SolveResult:
    """Detail page for a branch like ``-2 + 1`` or ``2 - 3``: pull the sign out, then compute."""
    detail = SolveResult()
    first = expression.children[0] if expression.children else expression
    parts = _fraction_parts(first)
    first_negative = parts is not None and parts[0] < 0
    if expression.type is T.ADD or not first_negative:
        detail.add_group("add_sign_sub", Step(expression, expression, "add_sign_sub"))
        detail.add_group("calculate_short", Step(expression, value, "sub"))
    else:
        detail.add_group("extract_minus", Step(expression, expression, "extract_minus"))
        detail.add_group("calculate_short", Step(expression, value, "add"))
    detail.set_solution(value)
    return detail


def _branch_page(
    shown: int, sign: int, root: int, denominator: int, value: Fraction
) -> SolveResult:
    """The app page for one root: add or subtract in the fraction, then reduce it."""
    detail = SolveResult()
    numerator = shown + sign * root
    expression = _node(T.ADD if sign > 0 else T.SUBTRACT, _num(shown), _num(root))
    fraction = _node(T.FRACTION, _num(numerator), _num(denominator))
    key = (
        ("add" if shown > 0 else "calc_sum")
        if sign > 0
        else ("calc_diff" if shown + sign * root < 0 else "sub")
    )
    if numerator == 0:
        detail.add_group(
            "calculate_short", Step(expression, fraction, "sub_with_self_num", [_num(0)])
        )
        detail.add_group("divide", Step(fraction, _num(value), "div_zero", [_num(0)]))
        detail.set_solution(_num(value))
        return detail
    detail.add_group("calculate_short", Step(expression, fraction, key))
    if numerator == -denominator:
        detail.add_group("divide", Step(fraction, _num(value), "div_with_self_neg", [_num(-1)]))
    elif numerator == denominator:
        detail.add_group("divide", Step(fraction, _num(value), "div_with_self", [_num(1)]))
    else:
        factor = gcd(abs(numerator), abs(denominator)) or 1
        detail.add_group(
            "divide",
            Step(fraction, _num(value), "frac_reduce_frac_num", [_num(factor)]),
        )
        if numerator < 0 and value.denominator != 1:
            detail.add_group(
                "frac_extract_neg",
                Step(_num(value), _num(value), "frac_extract_neg", [_extract_rule()]),
            )
    detail.set_solution(_num(value))
    return detail


def _root_page(radicand: int, root: int) -> SolveResult:
    """The app page for ``√k`` with an exact root: ``√k = √(m²) = m``."""
    detail = SolveResult()
    inside = _node(T.ROOT2, _num(radicand))
    squared = _node(T.ROOT2, _node(T.POWER, _num(root), _num(2)))
    detail.add_group("pow_to_same_base", Step(inside, squared, "pow_to_same_base", [_num(root)]))
    detail.add_group("root", Step(squared, _num(root), "root_reduce", [_num(root)]))
    detail.set_solution(_num(root))
    return detail


def _sum_chain(items: list[tuple[int, CoreNode]]) -> CoreNode:
    """``±t1 ± t2 …`` as a left-leaning chain; a leading minus is a NEGATIVE node."""
    sign, first = items[0]
    out = _node(T.NEGATIVE, first) if sign < 0 else first
    for sign, term in items[1:]:
        out = _node(T.SUBTRACT if sign < 0 else T.ADD, out, term)
    return out


def _fraction_division_page(expression: CoreNode, value: CoreNode) -> SolveResult | None:
    """``(a/b) / c``: fraction to division, reciprocal, multiply, cancel the ones."""
    base = expression.children[0] if expression.type is T.NEGATIVE else expression
    if base.type is not T.FRACTION or len(base.children) != 2:
        return None
    top, bottom = base.children
    if top.type is not T.FRACTION or bottom.type is not T.CONSTANT:
        return None
    numerator, denominator = top.children
    if numerator.type is not T.CONSTANT or denominator.type is not T.CONSTANT:
        return None
    dividend = _node(T.DIVIDE, top, bottom)
    reciprocal = _node(T.MULTIPLY, top, _node(T.FRACTION, _num(1), bottom))
    joined = _node(
        T.FRACTION, _node(T.MULTIPLY, numerator, _num(1)), _node(T.MULTIPLY, denominator, bottom)
    )
    one_removed = _node(T.FRACTION, numerator, _node(T.MULTIPLY, denominator, bottom))
    detail = SolveResult()
    detail.add_group("frac_to_div", Step(base, dividend, "frac_to_div"))
    detail.add_group("frac_int_div", Step(dividend, reciprocal, "frac_int_div"))
    detail.add_group("frac_mul_join", Step(reciprocal, joined, "frac_mul_join"))
    detail.add_group("mul_with_one", Step(joined, one_removed, "mul_with_one", [_num(1)]))
    detail.add_group("calculate_short", Step(one_removed, value, "mul"))
    detail.set_solution(value)
    return detail


def _fraction_power_page(expression: CoreNode, value: CoreNode) -> SolveResult | None:
    """``(a/b)²``: even power, then numerator and denominator separately."""
    if expression.type is not T.POWER or not expression.children:
        return None
    base = expression.children[0]
    inner = base.children[0] if base.type is T.BRACKET and base.children else base
    negative = inner.type is T.NEGATIVE and bool(inner.children)
    fraction = inner.children[0] if negative else inner
    if fraction.type is not T.FRACTION or len(fraction.children) != 2:
        return None
    numerator, denominator = fraction.children
    if numerator.type is not T.CONSTANT or denominator.type is not T.CONSTANT:
        return None
    if str(numerator.value or "").startswith("-"):
        negative = True
        fraction = _node(T.FRACTION, _num(-int(numerator.value or 0)), denominator)
        numerator, denominator = fraction.children
    detail = SolveResult()
    positive = _node(T.POWER, _node(T.BRACKET, fraction), _num(2))
    current = expression
    if negative:
        detail.add_group("pow_even", Step(current, positive, "pow_even"))
        current = positive
    split = _node(
        T.FRACTION, _node(T.POWER, numerator, _num(2)), _node(T.POWER, denominator, _num(2))
    )
    detail.add_group("pow_frac", Step(current, split, "pow_frac"))
    powered = _node(
        T.FRACTION,
        _node(T.POWER, numerator, _num(2)),
        _node(T.POWER, denominator, _num(2)),
    )
    numerator_one = numerator.type is T.CONSTANT and str(numerator.value) in ("1", "−1")
    detail.add_group(
        "calculate_short",
        Step(split, powered, "pow_one", [_num(1)])
        if numerator_one
        else Step(split, powered, "pow"),
    )
    detail.add_group("pow", Step(powered, value, "pow"))
    detail.set_solution(value)
    return detail


def _fraction_parts(node: CoreNode) -> tuple[int, int] | None:
    """``(numerator, denominator)`` for a number, a fraction or a negated one."""
    sign = 1
    if node.type is T.NEGATIVE and node.children:
        sign, node = -1, node.children[0]
    if node.type is T.CONSTANT:
        try:
            return sign * int(node.value or 0), 1
        except ValueError:
            return None
    if node.type is T.FRACTION and len(node.children) == 2:
        top, bottom = node.children
        if top.type is not T.CONSTANT or bottom.type is not T.CONSTANT:
            return None
        try:
            return sign * int(top.value or 0), int(bottom.value or 0)
        except ValueError:
            return None
    return None


def _fraction_sum_page(
    expression: CoreNode, value: CoreNode, *, reduce_result: bool
) -> SolveResult | None:
    """Adding or subtracting fractions: common denominator, then the numerator."""
    if expression.type not in (T.ADD, T.SUBTRACT) or len(expression.children) != 2:
        return None
    left, right = expression.children
    left_parts, right_parts = _fraction_parts(left), _fraction_parts(right)
    if left_parts is None or right_parts is None:
        return None
    left_num, left_den = left_parts
    right_num, right_den = right_parts
    if left_den == 1 and right_den == 1:
        return None
    sign = 1 if expression.type is T.ADD else -1
    common = int(sympy.ilcm(left_den, right_den))
    numerator = left_num * (common // left_den) + sign * right_num * (common // right_den)
    detail = SolveResult()
    if left_den == right_den or left_den == 1 or right_den == 1:
        detail.add_group("frac_sum_join", Step(expression, expression, "frac_sum_join"))
    else:
        detail.add_group(
            "frac_sum_common", Step(expression, expression, "frac_sum_common", [_num(common)])
        )
    same_sign = (left_num >= 0) == (right_num >= 0)
    if expression.type is T.ADD:
        key = "add" if same_sign else "calc_sum"
    else:
        key = "sub" if numerator > 0 else "calc_diff"
    detail.add_group(
        "calculate_short", Step(expression, _fraction_node(Fraction(numerator, common)), key)
    )
    if not reduce_result and numerator < 0:
        detail.add_group(
            "frac_extract_neg",
            Step(
                _fraction_node(Fraction(numerator, common)),
                _fraction_node(Fraction(numerator, common)),
                "frac_extract_neg",
                [_extract_rule()],
            ),
        )
    if reduce_result:
        if numerator == common:
            detail.add_group("divide", Step(value, value, "div_with_self", [_num(1)]))
        else:
            factor = gcd(abs(numerator), common) or 1
            current = _fraction_node(Fraction(numerator, common))
            if numerator < 0:
                detail.add_group(
                    "frac_extract_neg",
                    Step(current, current, "frac_extract_neg", [_extract_rule()]),
                )
            detail.add_group(
                "frac_reduce_frac",
                Step(current, value, "frac_reduce_frac_num", [_num(factor)]),
            )
    detail.set_solution(value)
    return detail


def _fraction_value(value: CoreNode) -> CoreNode:
    """Узел дроби для промежуточного экрана (``Fraction`` как ``a/b``)."""
    return value


def _fraction_root_page(expression: CoreNode, value: CoreNode) -> SolveResult | None:
    """``√(a/b)`` with exact roots: split the root, write both numbers as squares, reduce."""
    if expression.type is not T.ROOT2 or not expression.children:
        return None
    radicand = expression.children[0]
    if radicand.type is not T.FRACTION:
        return None
    numerator, denominator = radicand.children
    if numerator.type is not T.CONSTANT or denominator.type is not T.CONSTANT:
        return None
    try:
        num = int(numerator.value or 0)
        den = int(denominator.value or 0)
    except ValueError:
        return None
    num_root, den_root = isqrt(num), isqrt(den)
    if num_root * num_root != num or den_root * den_root != den:
        return None
    split = _node(T.FRACTION, _node(T.ROOT2, numerator), _node(T.ROOT2, denominator))
    num_square = _node(
        T.FRACTION,
        _node(T.ROOT2, _node(T.POWER, _num(num_root), _num(2))),
        _node(T.ROOT2, denominator),
    )
    both_squares = _node(
        T.FRACTION,
        _node(T.ROOT2, _node(T.POWER, _num(num_root), _num(2))),
        _node(T.ROOT2, _node(T.POWER, _num(den_root), _num(2))),
    )
    num_reduced = _node(
        T.FRACTION,
        _num(num_root),
        _node(T.ROOT2, _node(T.POWER, _num(den_root), _num(2))),
    )
    detail = SolveResult()
    detail.add_group("root_frac_each", Step(expression, split, "root_frac_each"))
    if num == 1:
        one_over_root = _node(T.FRACTION, _num(1), _node(T.ROOT2, denominator))
        detail.add_group("root_one", Step(split, one_over_root, "root_one", [_num(1)]))
        detail.add_group(
            "pow_to_same_base",
            Step(
                one_over_root,
                _node(T.FRACTION, _num(1), _node(T.ROOT2, _node(T.POWER, _num(den_root), _num(2)))),
                "pow_to_same_base",
                [_num(den_root)],
            ),
        )
        detail.add_group("root_reduce", Step(one_over_root, value, "root_reduce", [_num(2)]))
        detail.set_solution(value)
        return detail
    detail.add_group(
        "pow_to_same_base", Step(split, num_square, "pow_to_same_base", [_num(num_root)])
    )
    detail.add_group(
        "pow_to_same_base",
        Step(num_square, both_squares, "pow_to_same_base", [_num(den_root)]),
    )
    detail.add_group("root_reduce", Step(both_squares, num_reduced, "root_reduce", [_num(2)]))
    detail.add_group("root_reduce", Step(num_reduced, value, "root_reduce", [_num(2)]))
    detail.set_solution(value)
    return detail


def _fraction_page(
    expression: CoreNode, value: CoreNode, *, reduce_result: bool = False
) -> SolveResult:
    """The detail screen for rational arithmetic, or our arithmetic screen as a fallback."""
    page = _fraction_division_page(expression, value)
    if page is None:
        page = _fraction_power_page(expression, value)
    if page is None:
        page = _fraction_root_page(expression, value)
    if page is None:
        page = _fraction_sum_page(expression, value, reduce_result=reduce_result)
    return page if page is not None else _detail(expression, value)


def _sign_flip_page(expression: CoreNode, value: CoreNode) -> SolveResult:
    """Detail page for ``-a/b``: pull the minus out, then drop the double negation."""
    detail = SolveResult()
    negative = (
        expression.children[0]
        if expression.type is T.NEGATIVE and expression.children
        else expression
    )
    wrapped = _node(T.NEGATIVE, negative)
    detail.add_group(
        "frac_extract_neg",
        Step(expression, wrapped, "frac_extract_neg", [_extract_rule()]),
    )
    detail.add_group("neg_neg_arg", Step(wrapped, value, "neg_neg_arg", [_num(-1)]))
    detail.set_solution(value)
    return detail


def _product_pow_page(a: int, c: int | Fraction) -> SolveResult:
    """Detail page for ``4·a·c``: repeated factors become powers, otherwise plain multiplication."""
    detail = SolveResult()
    size = abs(Fraction(c))
    expression = _node(T.MULTIPLY, _num(4), _num(a), _paren(c))
    current = expression

    def positive(value: CoreNode) -> CoreNode:
        return value

    if c < 0:
        detail.add_group(
            "resolve_neg_pos",
            Step(current, current, "resolve_neg_pos"),
        )
    if a == size:
        pairs = _node(T.MULTIPLY, _num(4), _node(T.POWER, _num(a), _num(2)))
        detail.add_group("mul_to_pow", Step(current, pairs, "mul_to_pow"))
        squared = _node(T.MULTIPLY, _num(4), _num(a * a))
        detail.add_group("pow", Step(pairs, squared, "pow"))
        if c < 0:  # 4·4 has its own pair of equal factors
            final_power = _node(T.POWER, _num(4), _num(2))
            detail.add_group("mul_to_pow", Step(squared, final_power, "mul_to_pow"))
            detail.add_group("pow", Step(final_power, _num(16), "pow"))
        else:
            detail.add_group("calculate_short", Step(squared, _num(4 * a * a), "mul"))
    else:
        if size == 1 and c < 0:
            one_product = _node(T.MULTIPLY, _num(4 * a), _paren(c))
            detail.add_group(
                "calculate_short",
                Step(current, one_product, "mul_with_one", [_num(1)]),
            )
            detail.add_group("calculate_short", Step(one_product, _num(4 * a), "mul"))
            return detail
        if a == 1 and c < 0:
            one_product = _node(T.MULTIPLY, _num(4), _paren(c))
            detail.add_group(
                "calculate_short",
                Step(current, one_product, "mul_with_one", [_num(1)]),
            )
            detail.add_group("calculate_short", Step(one_product, _num(4 * size), "mul"))
            return detail
        first = _node(T.MULTIPLY, _num(4 * a), _paren(c) if c < 0 else _num(size))
        detail.add_group("calculate_short", Step(current, first, "mul"))
        if a > 1:
            detail.add_group("calculate_short", Step(first, _num(4 * a * size), "mul"))
    return detail


def _signed_product_page(expression: CoreNode, value: CoreNode) -> SolveResult:
    """Detail page for ``4·(-4)``: two negatives give a plus, then the numbers multiply."""
    detail = SolveResult()

    def unwrap(child: CoreNode) -> CoreNode:
        return child.children[0] if child.type is T.BRACKET and child.children else child

    def negated(child: CoreNode) -> bool:
        if child.type is T.NEGATIVE:
            return True
        return child.type is T.CONSTANT and str(child.value or "").startswith("-")

    def positive(child: CoreNode) -> CoreNode:
        if child.type is T.NEGATIVE:
            return child.children[0]
        if negated(child):
            return _num(-Fraction(str(child.value or "0").replace("−", "-")))
        return child

    children = (
        [unwrap(child) for child in expression.children] if expression.type is T.MULTIPLY else []
    )
    negatives = sum(1 for child in children if negated(child))
    value_negative = value.type is T.CONSTANT and str(value.value or "").startswith("-")
    # one negative factor is enough when the surrounding row already changed the sign
    two_negatives = negatives == 2 or (negatives == 1 and not value_negative)
    if expression.type is T.MULTIPLY and two_negatives:
        positives = _node(T.MULTIPLY, *[positive(child) for child in children])
        detail.add_group(
            "mul_neg_neg",
            Step(expression, positives, "mul_neg_neg", [CoreNode.variable("+")]),
        )
        detail.add_group("calculate_short", Step(positives, value, "mul"))
        detail.set_solution(value)
        return detail
    return _evaluate(expression)


def _quadratic_by_a_page(
    node: CoreNode,
    var: str,
    a: int,
    b: int,
    c: int | Fraction,
    *,
    moved: bool = False,
) -> SolveResult:
    """The app page for dividing the whole quadratic by ``a``.

    ``moved`` is the form after the constant went right (``a x² + b x = -c``), where the
    constant is not divided and the right side becomes a fraction.
    """
    divisor = _num(a)
    left, right = node.children
    x = CoreNode.variable(var)
    squared = _node(T.POWER, x, _num(2))
    terms = [
        (1, _node(T.DIVIDE, _mono(a, 2, var), divisor)),
        (1 if b > 0 else -1, _node(T.DIVIDE, _mono(abs(b), 1, var), divisor)),
    ]
    if not moved:
        terms.append(
            (1 if c > 0 else -1, _node(T.DIVIDE, _fraction_node(abs(Fraction(c))), divisor))
        )
    division = _eq(_node(T.DIVIDE, left, divisor), _node(T.DIVIDE, right, divisor))
    detail = SolveResult()
    detail.add_group(
        CoreRichText(type="eq_linear_div", args=[divisor]),
        Step(node, division, "eq_linear_div", [divisor]),
    )
    distributed = _eq(_sum_chain(terms), _node(T.DIVIDE, right, divisor))
    detail.add_group("mul_bracket", Step(division, distributed, "mul_bracket", [divisor]))
    ratio = Fraction(b, a)
    constant = Fraction(c, a)
    if moved:
        on_right = _eq(_sum_chain(terms), _fraction_node(-constant))
        if -constant == 1:
            detail.add_group("divide", Step(distributed, on_right, "div_with_self", [_num(1)]))
        elif (-constant).denominator == 1:
            detail.add_group("divide", Step(distributed, on_right, "quotient"))
        else:
            detail.add_group("divide", Step(distributed, on_right, "div_to_frac"))
        current = on_right
    else:
        zeroed = _eq(_sum_chain(terms), _num(0))
        detail.add_group("div_zero", Step(distributed, zeroed, "div_zero", [_num(0)]))
        current = zeroed
    without_square = list(terms)
    without_square[0] = (1, squared)
    quotient = _eq(_sum_chain(without_square), current.children[1])
    detail.add_group("divide", Step(current, quotient, "quotient"))
    current = quotient
    if ratio.denominator != 1:
        # the sign comes from b/a, not b: a < 0 flips it
        linear_terms = [without_square[0], (1 if ratio > 0 else -1, _mono(abs(ratio), 1, var))]
        if not moved:
            linear_terms.append(without_square[2])
        with_fraction = _eq(_sum_chain(linear_terms), current.children[1])
        detail.add_group("divide", Step(current, with_fraction, "div_to_frac"))
        current = with_fraction
        without_square = linear_terms
    if not moved:
        final_terms = [
            without_square[0],
            without_square[1],
            (1 if constant > 0 else -1, _fraction_node(abs(constant))),
        ]
        cleared = _eq(_sum_chain(final_terms), _num(0))
        if constant == 1:
            detail.add_group("divide", Step(current, cleared, "div_with_self", [_num(1)]))
        elif constant.denominator == 1:
            detail.add_group("divide", Step(current, cleared, "quotient"))
        else:
            detail.add_group("divide", Step(current, cleared, "div_to_frac"))
        detail.set_solution(cleared)
    else:
        detail.set_solution(current)
    return detail


def _fraction_node(value: Fraction) -> CoreNode:
    if value.denominator == 1:
        return _num(value.numerator)
    return _node(T.FRACTION, _num(value.numerator), _num(value.denominator))


def _pq_even_negative(f: _Family) -> SolveResult | None:
    """``x^2 - 2k x - q = 0`` (``q > 0``): ``p/2`` reduces to an integer, the root is exact.

    Worked out for ``x^2 - 4x - 5 = 0``: reduce, evaluate the radical, open the brackets, split,
    add and subtract.
    """
    b, c, x = f.b, f.c, f.x
    if not isinstance(c, int):  # a decimal c never reaches these verified families
        return None
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

    half, r = -b // 2, isqrt(b * b // 4 - c)
    b_half = _node(T.FRACTION, _num(b), two)
    squared = _node(T.POWER, _node(T.BRACKET, b_half), two)
    radicand = _node(T.SUBTRACT, squared, _paren(c))
    start = state(_node(T.NEGATIVE, b_half), radicand)
    result = SolveResult()
    result.add_group(
        "quad_formula_abc_simple", Step(f.node, start, "quad_formula_pq", [standard, template])
    )
    minus_half = _node(T.NEGATIVE, _paren(-half))
    reduced = state(minus_half, radicand)
    value = _eq(x, _node(T.ADD_SUBTRACT, minus_half, _num(r)))
    result.add_group(
        ["frac_reduce_frac", "calculate_direct"],
        Step(
            start,
            reduced,
            "frac_reduce_frac_num",
            [two],
            subresult=_detail(b_half, _num(-half)),
        ),
        Step(reduced, value, "calculate_direct"),
    )
    opened = _eq(x, _node(T.ADD_SUBTRACT, _num(half), _num(r)))
    result.add_group("remove_bracket_short", Step(value, opened, "neg_neg_arg", [_num(-1)]))
    plus = _eq(x, _node(T.ADD, _num(half), _num(r)))
    minus = _eq(x, _node(T.SUBTRACT, _num(half), _num(r)))
    listed = _node(T.LIST, plus, minus)
    result.add_group("quad_separate", Step(opened, listed, "quad_separate_signs", list(_SIGNS)))
    result.add_group(
        ["add", "calc_diff"],
        Step(listed, f.solved(Fraction(half + r)), "add"),
        Step(
            listed,
            f.solved(Fraction(half - r)),
            "calc_diff",
            subresult=_signed_branch_page(minus.children[1], _num(half - r)),
        ),
    )
    f.finish(result, [f.solved(Fraction(half + r)), f.solved(Fraction(half - r))])
    return result


def _pq_odd_positive(f: _Family) -> SolveResult | None:
    """``x^2 + p x - q = 0`` with odd ``p > 0``: ``p/2`` stays a fraction (e.g. x^2+x-6)."""
    b, c, x = f.b, f.c, f.x
    if not isinstance(c, int):  # a decimal c never reaches these verified families
        return None
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

    def state(inner: CoreNode) -> CoreNode:
        return _eq(x, _node(T.ADD_SUBTRACT, lead, _node(T.ROOT2, inner)))

    b_half = _node(T.FRACTION, _num(b), two)
    lead = _node(T.NEGATIVE, b_half)
    squared = _node(T.POWER, _node(T.BRACKET, b_half), two)
    quarter = _fraction_node(Fraction(b * b, 4))
    start = state(_node(T.SUBTRACT, squared, _paren(c)))
    result = SolveResult()
    result.add_group(
        "quad_formula_abc_simple", Step(f.node, start, "quad_formula_pq", [standard, template])
    )
    powered = state(_node(T.SUBTRACT, quarter, _paren(c)))
    flipped = state(_node(T.ADD, quarter, _num(-c)))
    result.add_group(
        ["pow_frac", "remove_bracket_short"],
        Step(
            start,
            powered,
            "pow_frac",
            subresult=_pq_power_page(squared, quarter, numerator_one=True),
        ),
        Step(powered, flipped, "neg_neg_arg", [_num(-1)]),
    )
    radicand = Fraction(b * b, 4) - c
    summed = state(_fraction_node(radicand))
    result.add_group(
        "calc_sum",
        Step(
            flipped,
            summed,
            "calc_sum",
            subresult=_detail(_node(T.ADD, quarter, _num(-c)), _fraction_node(radicand)),
        ),
    )
    r = Fraction(f.root, 2)
    half = Fraction(-b, 2)
    rooted = _eq(x, _node(T.ADD_SUBTRACT, lead, _fraction_node(r)))
    result.add_group(
        "root_square",
        Step(
            summed,
            rooted,
            "root_square",
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
            "calc_sum",
            subresult=_fraction_page(
                plus.children[1], _fraction_node(half + r), reduce_result=True
            ),
        ),
        Step(
            listed,
            f.solved(half - r),
            "calc_diff",
            subresult=_fraction_page(
                minus.children[1], _fraction_node(half - r), reduce_result=True
            ),
        ),
    )
    f.finish(result, [f.solved(half + r), f.solved(half - r)])
    return result


def _pq_roots_tail(
    f: _Family, result: SolveResult, before: CoreNode, lead: CoreNode, real_only: bool
) -> None:
    """Root row, sign split and the two answers of a PQ card with an exact root.

    Used when ``√((p/2)² − q)`` is a surd or an imaginary number: The app keeps the
    same rows and ends with ``root_frac_each``/``root_square`` and two simplifications.
    """
    x = f.x
    radicand = Fraction(f.d, 4 * f.a * f.a)
    if real_only:
        result.add_group("expr_not_def_in_r", Step(before, before, "root_sqr_neg"))
        result.set_solution(CoreNode.empty())
        return
    if f.d < 0:
        radical = _imaginary(_surd(-radicand))
        key = "root_square"
    else:
        radical = _surd(radicand)
        key = "root_frac_each" if radicand.denominator != 1 else "root_square"
    rooted = _eq(x, _node(T.ADD_SUBTRACT, lead, radical))
    page = (
        _fraction_root_page(_node(T.ROOT2, _fraction_node(radicand)), radical)
        if radicand > 0
        else None
    )
    result.add_group(
        "root_simplify",
        Step(
            before,
            rooted,
            key,
            [],
            subresult=page
            if page is not None
            else _detail(_node(T.ROOT2, _fraction_node(radicand)), radical),
        ),
    )
    branches = [_eq(x, _node(sign, lead, radical)) for sign in (T.ADD, T.SUBTRACT)]
    listed = _node(T.LIST, *branches)
    result.add_group("quad_separate", Step(rooted, listed, "quad_separate_signs", list(_SIGNS)))
    values = list(reversed(_root_nodes(f.a, f.b, f.c)))
    group = "simplify" if f.d > 0 else "separate"
    result.add_group(
        group,
        *[
            Step(
                listed,
                _eq(x, value),
                "simplify" if f.d > 0 else "complex_separate",
                [],
                subresult=_fraction_page(branch.children[1], value, reduce_result=f.d > 0),
            )
            for branch, value in zip(branches, values, strict=True)
        ],
    )
    f.finish_roots(result, listed)


def _pq_nonexact(f: _Family, real_only: bool = False) -> SolveResult | None:
    """PQ formula with a surd or an imaginary root (``D`` is not a perfect square)."""
    a, b, c, x = f.a, f.b, f.c, f.x
    if a == 0 or f.d == 0:
        return None
    two = _num(2)
    result = SolveResult()
    start_node = f.node
    big_p, big_q = Fraction(b, a), Fraction(c, a)
    if a != 1:
        divided = _eq(_poly([(1, 2), (big_p, 1), (big_q, 0)], f.var), _num(0))
        result.add_group(
            CoreRichText(type="divide_both_sides", args=[]),
            Step(
                f.node,
                divided,
                "eq_linear_div",
                [_num(a)],
                subresult=_quadratic_by_a_page(f.node, f.var, a, b, c),
            ),
        )
        start_node = divided
    p, q = CoreNode.variable("p"), CoreNode.variable("q")
    standard = _eq(
        _node(T.ADD, _node(T.ADD, _node(T.POWER, x, two), _node(T.MULTIPLY_IMPLICIT, p, x)), q),
        _num(0),
    )
    p_half_letter = _node(T.FRACTION, p, two)
    template = _eq(
        x,
        _node(
            T.ADD_SUBTRACT,
            _node(T.NEGATIVE, p_half_letter),
            _node(
                T.ROOT2,
                _node(T.SUBTRACT, _node(T.POWER, _node(T.BRACKET, p_half_letter), two), q),
            ),
        ),
    )

    def state(lead: CoreNode, inner: CoreNode) -> CoreNode:
        return _eq(x, _node(T.ADD_SUBTRACT, lead, _node(T.ROOT2, inner)))

    half = big_p / 2
    half_node = _fraction_node(half)
    squared = _node(T.POWER, _node(T.BRACKET, half_node), two)
    lead = _fraction_node(-half)
    if half < 0:  # The app keeps −p/2 as a negated fraction and flips it on the next row
        start_lead = _node(T.NEGATIVE, half_node)
    else:  # the unreduced fraction (−b)/(2a), reduced on the next row
        start_lead = _node(T.FRACTION, _num(-b), two if a == 1 else _node(T.MULTIPLY, two, _num(a)))
    start = state(start_lead, _node(T.SUBTRACT, squared, _fraction_node(big_q)))
    result.add_group(
        "quad_formula_pq_simple",
        Step(start_node, start, "quad_formula_pq", [standard, template]),
    )
    pages: list[Step] = []
    titles: list[str] = []
    reduced = state(lead, _node(T.SUBTRACT, squared, _fraction_node(big_q)))
    if start_lead.to_contract() != lead.to_contract():
        if half.denominator == 1:
            pages.append(
                Step(
                    start,
                    reduced,
                    "frac_reduce_frac_num",
                    [two],
                    subresult=_detail(start_lead, lead),
                )
            )
            titles.append("reduce")
        else:
            pages.append(
                Step(
                    start,
                    reduced,
                    "frac_resolve_neg",
                    [],
                    subresult=_sign_flip_page(start_lead, lead),
                )
            )
            titles.append("sign_find_short")
    squared_value = _fraction_node(half * half)
    current = pages[-1].right if pages else start
    pages.append(
        Step(
            current,
            state(lead, _node(T.SUBTRACT, squared_value, _fraction_node(big_q))),
            "pow_frac" if half.denominator != 1 else "pow",
            [],
            subresult=(
                _pq_power_page(squared, squared_value, numerator_one=half.numerator == 1)
                if half.denominator != 1
                else _detail(squared, squared_value)
            ),
        )
    )
    titles.append("pow_frac" if half.denominator != 1 else "evaluate")
    radicand = half * half - big_q
    if big_q < 0:
        pages.append(
            Step(
                pages[-1].right,
                state(lead, _node(T.ADD, squared_value, _fraction_node(-big_q))),
                "neg_neg_arg",
                [_num(-1)],
            )
        )
        titles.append("remove_bracket_short")
    combined = state(lead, _fraction_node(radicand))
    pages.append(
        Step(
            pages[-1].right,
            combined,
            "frac_add" if big_q < 0 else "calc_diff",
            [],
            subresult=_fraction_page(
                _node(T.ADD, squared_value, _fraction_node(-big_q))
                if big_q < 0
                else _node(T.SUBTRACT, squared_value, _fraction_node(big_q)),
                _fraction_node(radicand),
            ),
        )
    )
    titles.append("calculate_short")
    result.add_group(titles, *pages)
    _pq_roots_tail(f, result, combined, lead, real_only)
    return result


def _pq_formula(f: _Family, real_only: bool = False) -> SolveResult | None:
    """``x^2 + p x + q = 0`` by the PQ formula, as worked out for a = 1 and b < 0."""
    if not f.exact:
        return _pq_nonexact(f, real_only)
    if f.a == 1 and f.b > 0 and f.b % 2 == 1 and f.c < 0:
        return _pq_odd_positive(f)
    if f.a == 1 and f.b > 0 and f.b % 2 == 0 and f.c > 0:
        return _pq_positive(f)
    if f.a == 1 and f.b < 0 and f.b % 2 == 0 and f.c < 0:
        return _pq_even_negative(f)
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

    b_half = _node(T.FRACTION, _num(b), two)
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
            subresult=_sign_flip_page(_node(T.NEGATIVE, b_half), lead),
        ),
        Step(
            signed,
            powered,
            "pow_frac",
            [],
            subresult=_pq_power_page(
                squared, _fraction_node(Fraction(b * b, 4)), numerator_one=False
            ),
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
            subresult=_fraction_root_page(
                _node(T.ROOT2, _fraction_node(radicand)), _fraction_node(r)
            ),
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
            subresult=_fraction_page(
                plus.children[1], _fraction_node(half + r), reduce_result=True
            ),
        ),
        Step(
            listed,
            f.solved(half - r),
            "frac_sub",
            [],
            subresult=_fraction_page(
                minus.children[1], _fraction_node(half - r), reduce_result=True
            ),
        ),
    )
    f.finish(result, [f.solved(half + r), f.solved(half - r)])
    return result


def _pq_positive(f: _Family) -> SolveResult | None:
    """``x^2 + p x + q = 0`` with an even ``p > 0`` and ``q > 0``, e.g. x^2 + 4x + 3."""
    b, c, x = f.b, f.c, f.x
    if not isinstance(c, int):  # a decimal c never reaches these verified families
        return None
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
            "frac_reduce_frac_num",
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
            subresult=_signed_branch_page(plus.children[1], _num(high)),
        ),
        Step(
            listed,
            f.solved(Fraction(low)),
            "calc_diff",
            [],
            subresult=_signed_branch_page(minus.children[1], _num(low)),
        ),
    )
    f.finish(result, [f.solved(Fraction(high)), f.solved(Fraction(low))])
    return result


def _completing_square(f: _Family, real_only: bool = False) -> SolveResult | None:
    """Completing the square: ``a = 1`` for three sign families, ``a > 1`` for ``b > 0 > c``."""
    negative = f.d < 0
    if negative and (f.a <= 0 or f.b == 0 or f.c == 0):
        return None  # the square-extraction families have no such card
    if not negative and f.a < 0 and f.a != -1:
        return None
    a, x, var = f.a, f.x, f.var
    c: int | Fraction = f.c
    b = Fraction(f.b, a)  # the middle coefficient once the equation is divided by a
    half = b / 2
    left = _poly([(1, 2), (b, 1)], var)
    head = _poly([(a, 2), (f.b, 1)], var)
    hole = CoreNode.variable("?")
    new = _fraction_node(half * half)
    result = SolveResult()

    moved = _eq(head, _fraction_node(Fraction(-f.c)))
    balanced = _eq(
        _node(
            T.ADD if c < 0 else T.SUBTRACT, f.node.children[0], _fraction_node(abs(Fraction(f.c)))
        ),
        _node(T.ADD if c < 0 else T.SUBTRACT, _num(0), _fraction_node(abs(Fraction(f.c)))),
    )
    typed_rhs = getattr(f, "typed_rhs", None)
    typed_c = f.c + typed_rhs if typed_rhs else f.c
    if f.c != 0 and typed_rhs and typed_c != 0:
        # ``a x² + b x + c = rhs``: the typed constant moves right as written
        # (``1/2 − 4``) and is combined on the next row (``−7/2``).
        opened = _eq(
            head,
            _node(
                T.ADD if typed_c < 0 else T.SUBTRACT,
                _fraction_node(typed_rhs),
                _fraction_node(abs(typed_c)),
            ),
        )
        result.add_group(
            "rel_move_right_const_msg", Step(f.node, opened, "rel_move_right_const_eq")
        )
        result.add_group(
            "calculate_short",
            Step(opened, moved, "calc_sum" if typed_c < 0 else "calc_diff"),
        )
    elif f.c != 0 and not typed_rhs:
        swap = SolveResult()
        swap.add_group("rel_swap_right_const", Step(f.node, balanced, "rel_swap_right_const"))
        swap.add_group(
            "remove_opposites",
            Step(balanced, moved, "sub_with_self_remove_num"),
            Step(balanced, moved, "add_with_zero", [_num(0)]),
        )
        swap.set_solution(moved)
        result.add_group(
            "rel_move_right_const_msg",
            Step(f.node, moved, "rel_move_right_const_eq", subresult=swap),
        )
    divided = _eq(left, _fraction_node(Fraction(-c, a)))
    if a != 1:
        # a < 0: «Умножьте обе части уравнения на -1» (the eq_mul_direct_one, the
        # same row the negative-lead cards show); a > 1: «Разделите обе стороны».
        key = "eq_linear_div" if a > 0 else "eq_mul_direct_one"
        divide = _quadratic_by_a_page(moved, var, a, f.b, f.c, moved=True)
        if a < 0:
            # «Умножьте обе части уравнения на -1» opens on «Раскрыть скобки»,
            # then «Вычислить» (case ``q_negA``, card «…полного квадрата»).
            sign = _num(a)
            wrapped = [
                side if side.type is T.CONSTANT else _node(T.BRACKET, side)
                for side in moved.children
            ]
            negated = _eq(*[_node(T.MULTIPLY, sign, side) for side in wrapped])
            divide = SolveResult()
            divide.add_group("mul_bracket", Step(moved, negated, "mul_bracket", [sign]))
            divide.add_group("calculate_short", Step(negated, divided, "mul"))
            divide.set_solution(divided)
        result.add_group(
            "divide_both_sides" if a > 0 else "multiply_both_sides",
            Step(moved, divided, key, [_num(a)], subresult=divide),
        )
        moved = divided
        c = Fraction(c, a)
    both = _eq(_node(T.ADD, left, hole), _node(T.ADD, _fraction_node(-Fraction(c)), hole))
    result.add_group("conics_add_both", Step(moved, both, "conics_complete_square_both"))
    root = _node(T.BRACKET, _node(T.SUBTRACT if b < 0 else T.ADD, x, _fraction_node(abs(half))))
    identity = _eq(_node(T.ADD, left, new), _node(T.POWER, root, _num(2)))
    # the middle term is written as ``2·x·(b/2)`` before the square is completed
    written_middle = _node(
        T.SUBTRACT if b < 0 else T.ADD,
        _node(T.POWER, x, _num(2)),
        _node(T.MULTIPLY, _node(T.MULTIPLY, _num(2), x), _fraction_node(abs(half))),
    )
    half_node = _fraction_node(abs(half))
    written = _node(T.ADD, written_middle, hole)
    middle_squared = _node(
        T.ADD, written_middle, _node(T.POWER, _node(T.BRACKET, half_node), _num(2))
    )
    joined = _node(T.ADD, left, _node(T.POWER, _node(T.BRACKET, half_node), _num(2)))
    added = _eq(_node(T.ADD, left, new), _node(T.ADD, _fraction_node(-Fraction(c)), hole))
    explain = SolveResult()
    explain.add_group(
        CoreRichText(type="write_as_mul_expr_two_f", args=[_num(2), x]),
        Step(both, written, "write_as_mul_expr_two_f", [_num(2), x]),
    )
    explain.add_group(
        CoreRichText(
            type="eq_add_exp",
            args=[_node(T.POWER, new, _num(2))],
        ),
        Step(written, middle_squared, "conics_add_middle", [half_node, new]),
    )
    explain.add_group("product", Step(middle_squared, joined, "product"))
    square_key = "pow" if half.denominator == 1 else "pow_frac"
    explain.add_group(square_key, Step(joined, _node(T.ADD, left, new), square_key))
    explain.set_solution(_node(T.ADD, left, new))
    result.add_group(
        CoreRichText(type="eq_add_exp", args=[new]),
        Step(
            both,
            added,
            "conics_complete_square",
            [identity, new],
            subresult=explain,
        ),
    )
    right = _node(T.ADD, _fraction_node(-Fraction(c)), new)
    equal = _eq(_node(T.ADD, left, new), right)
    result.add_group(
        CoreRichText(type="conics_add_other_lr", args=[new]),
        Step(added, equal, "conics_add_other_lr", [new]),
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
    # ``(b/2)²`` is written as ``b²/4`` and then as ``b²/2²`` before the square is folded
    half_abs = abs(half)
    exponent = 2
    numerator, denominator = half_abs.numerator, half_abs.denominator
    written_factor = _node(T.ADD, written_middle, new)
    squared_numerator = _node(
        T.FRACTION, _node(T.POWER, _num(numerator), _num(exponent)), _num(denominator)
    )
    squared_both = _node(
        T.FRACTION,
        _node(T.POWER, _num(numerator), _num(exponent)),
        _node(T.POWER, _num(denominator), _num(exponent)),
    )
    as_power = _node(T.POWER, _node(T.BRACKET, half_node), _num(exponent))
    factor_detail = SolveResult()
    factor_detail.add_group(
        "write_as_mul_expr_two_f",
        Step(equal, written_factor, "write_as_mul_expr_two_f", [x, half_node]),
    )
    factor_detail.add_group(
        "write_as_num_arg",
        Step(
            written_factor,
            _node(T.ADD, written_middle, squared_numerator),
            "write_as_num_arg",
            [_num(exponent)],
        ),
    )
    factor_detail.add_group(
        "write_as_num_arg",
        Step(
            _node(T.ADD, written_middle, squared_numerator),
            _node(T.ADD, written_middle, squared_both),
            "write_as_num_arg",
            [_num(exponent)],
        ),
    )
    factor_detail.add_group(
        "pow_frac_short",
        Step(
            _node(T.ADD, written_middle, squared_both),
            _node(T.ADD, written_middle, as_power),
            "log_frac_power",
        ),
    )
    factor_detail.add_group(
        CoreRichText(type="using_factor", args=[formula]),
        Step(_node(T.ADD, written_middle, as_power), factored, "using_factor", [formula]),
    )
    factor_detail.set_solution(factored)
    left_value = Fraction(-c)
    sum_key = "calc_sum"
    sum_detail = SolveResult()
    if f.c == 0:
        sum_detail = SolveResult()
    elif left_value.denominator == 1 and half.denominator == 1:
        if left_value < 0:
            sum_detail = _signed_sum_page(right, _fraction_node(total), "sub")
        else:
            sum_key = "add"
    elif left_value.denominator != 1 and half.denominator != 1:
        if left_value > 0:
            sum_key = "frac_add"
            sum_detail = _fraction_page(right, _fraction_node(total))
        else:
            common = int(sympy.ilcm(left_value.denominator, half.denominator**2))
            sum_detail.add_group(
                "frac_sum_common", Step(right, right, "frac_sum_common", [_num(common)])
            )
            sum_detail.add_group("calculate_short", Step(right, _fraction_node(total), "calc_sum"))
    else:
        sum_detail = _fraction_page(right, _fraction_node(total))
    result.add_group(
        ["frac_reduce_frac", "calculate_short"],
        Step(equal, factored, "using_factor", [formula], subresult=factor_detail),
        Step(factored, reduced, sum_key, [], subresult=sum_detail),
    )
    if negative:
        return _complex_square_ending(f, result, reduced, root, total, real_only)
    if not f.exact:
        return _irrational_square_ending(f, result, reduced, root, total)
    r = Fraction(f.root, 2 * a)
    sides = _eq(
        _node(T.ROOT2, _node(T.POWER, root, _num(2))),
        _node(T.ADD_SUBTRACT, _node(T.ROOT2, _fraction_node(total))),
    )
    pm_row = _eq(root, _node(T.ADD_SUBTRACT, _fraction_node(r)))
    solved = _node(T.LIST, f.solved(f.low), f.solved(f.high))
    branches = _node(
        T.LIST,
        _eq(root, _node(T.NEGATIVE, _fraction_node(r))),
        _eq(root, _fraction_node(r)),
    )
    half_done = _node(T.LIST, f.solved(f.low), branches.children[1])
    solve = SolveResult()
    solve.add_group("quad_sqrt_sides", Step(reduced, sides, "quad_sqrt_sides"))
    solve.add_group("eq_separate", Step(pm_row, branches, "eq_separate", [_num(2)]))
    solve.add_group(
        "eq_solve_short_plural",
        Step(branches, half_done, "eq_linear", [x]),
        Step(half_done, solved, "eq_linear", [x]),
    )
    solve.set_solution(solved)
    result.add_group("eq_solve_short", Step(reduced, solved, "eq_linear", [x], subresult=solve))
    f.finish(result, [f.solved(f.low), f.solved(f.high)])
    return result


def _complex_square_ending(
    f: _Family,
    result: SolveResult,
    reduced: CoreNode,
    root: CoreNode,
    total: Fraction,
    real_only: bool,
) -> SolveResult:
    """Last row(s) of completing the square when ``(x + h)^2`` equals a negative number."""
    x, two = f.x, _num(2)
    sides = _eq(
        _node(T.ROOT2, _node(T.POWER, root, two)),
        _node(T.ADD_SUBTRACT, _node(T.ROOT2, _fraction_node(total))),
    )
    imaginary = _imaginary(_surd(-total))
    solve = SolveResult()
    solve.add_group("quad_sqrt_sides", Step(reduced, sides, "quad_sqrt_sides"))
    if real_only:
        solve.add_group("expr_not_def_in_r", Step(sides, sides, "root_sqr_neg"))
        solve.set_solution(CoreNode.empty())
        result.add_group("eq_solve_short", Step(reduced, sides, "eq_linear", [x], subresult=solve))
        result.set_solution(CoreNode.empty())
        return result
    pm_row = _eq(root, _node(T.ADD_SUBTRACT, imaginary))
    solve.add_group("calculate_short", Step(sides, pm_row, "root_square"))
    shift = Fraction(-f.b, 2 * f.a)
    roots = [_eq(x, _node(sign, _fraction_node(shift), imaginary)) for sign in (T.ADD, T.SUBTRACT)]
    solved = _node(T.LIST, *roots)
    solve.add_group("quad_separate", Step(pm_row, solved, "quad_separate_signs", list(_SIGNS)))
    solve.set_solution(solved)
    result.add_group("eq_solve_short", Step(reduced, solved, "eq_linear", [x], subresult=solve))
    result.add_group(
        CoreRichText(type="solution_eq_num", args=[two]),
        Step(solved, solved, "solution_eq_num", [two]),
    )
    result.set_solution(solved)
    return result


def _irrational_square_ending(
    f: _Family, result: SolveResult, reduced: CoreNode, root: CoreNode, total: Fraction
) -> SolveResult:
    """Last rows of completing the square when ``(x + h)²`` equals a surd."""
    x, two = f.x, _num(2)
    radical = from_sympy(sympy.sqrt(sympy.Rational(total)))
    sides = _eq(
        _node(T.ROOT2, _node(T.POWER, root, two)),
        _node(T.ADD_SUBTRACT, _node(T.ROOT2, _fraction_node(total))),
    )
    pm_row = _eq(root, _node(T.ADD_SUBTRACT, radical))
    roots = f.roots()
    solved = _node(T.LIST, *roots)
    branches = _node(
        T.LIST,
        _eq(root, _node(T.NEGATIVE, radical)),
        _eq(root, radical),
    )
    half_done = _node(T.LIST, roots[0], branches.children[1])
    solve = SolveResult()
    solve.add_group("quad_sqrt_sides", Step(reduced, sides, "quad_sqrt_sides"))
    solve.add_group("eq_separate", Step(pm_row, branches, "eq_separate", [_num(2)]))
    solve.add_group(
        "eq_solve_short_plural",
        Step(branches, half_done, "eq_linear", [x]),
        Step(half_done, solved, "eq_linear", [x]),
    )
    solve.set_solution(solved)
    result.add_group("eq_solve_short", Step(reduced, solved, "eq_linear", [x], subresult=solve))
    f.finish_roots(result, solved)
    return result


def _pq_scaled(f: _Family) -> SolveResult | None:
    """The PQ formula after dividing by ``a`` (worked out for a > 1, b > 0, c < 0, c/a integral)."""
    a, b, c, x = f.a, f.b, f.c, f.x
    if a == 1 or b <= 0 or c % a:
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
            T.SUBTRACT if big_q < 0 else T.ADD,
            _node(T.ADD, _node(T.POWER, x, two), _node(T.MULTIPLY_IMPLICIT, p_node, x)),
            num(-int(big_q)) if big_q < 0 else num(int(big_q)),
        ),
        num(0),
    )
    result.add_group(
        CoreRichText(type="divide_both_sides", args=[]),
        Step(
            f.node,
            divided,
            "eq_linear_div",
            [num(a)],
            subresult=_quadratic_by_a_page(f.node, f.var, a, b, c),
        ),
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
    flipped_pages = [Step(second_page, third_page, "neg_neg_arg", [num(-1)])] if big_q < 0 else []
    result.add_group(
        ["simplify", "simplify", "remove_bracket_short"][: 2 + len(flipped_pages)],
        Step(
            start,
            first_page,
            "frac_complex_resolve_call",
            [],
            subresult=_fraction_page(_node(T.NEGATIVE, half_p), _node(T.NEGATIVE, h_node)),
        ),
        Step(
            first_page,
            second_page,
            "frac_complex_resolve_call",
            [],
            subresult=_fraction_page(half_p, h_node),
        ),
        *flipped_pages,
    )
    squared_value = _fraction_node(h * h)
    last_page = third_page if big_q < 0 else second_page
    powered = (
        state(_node(T.NEGATIVE, h_node), squared_value, num(-int(big_q)))
        if big_q < 0
        else state_minus(_node(T.NEGATIVE, h_node), squared_value, q_paren)
    )
    result.add_group(
        "pow_exp_msg",
        Step(
            last_page, powered, "pow_frac", [], subresult=_fraction_page(squared_h, squared_value)
        ),
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
            "calc_sum" if big_q < 0 else "calc_diff",
            [],
            subresult=_fraction_page(
                _node(T.ADD, squared_value, num(-int(big_q)))
                if big_q < 0
                else _node(T.SUBTRACT, squared_value, q_paren),
                _fraction_node(radicand),
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
            subresult=_fraction_page(_node(T.ROOT2, _fraction_node(radicand)), _fraction_node(r)),
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
            subresult=_fraction_page(
                plus.children[1], _fraction_node(values[0]), reduce_result=True
            ),
        ),
        Step(
            listed,
            f.solved(values[1]),
            "calc_diff",
            [],
            subresult=_fraction_page(
                minus.children[1], _fraction_node(values[1]), reduce_result=True
            ),
        ),
    )
    f.finish(result, [f.solved(values[1]), f.solved(values[0])])
    return result


def _extract_rule() -> CoreNode:
    """``-a/b = a/-b = -(a/b)``, the rule the app cites when it rewrites a negative fraction."""
    a, b = CoreNode.variable("a"), CoreNode.variable("b")
    minus_a = _node(T.FRACTION, _node(T.NEGATIVE, a), b)
    return _eq(
        _eq(minus_a, _node(T.FRACTION, a, _node(T.NEGATIVE, b))),
        _node(T.NEGATIVE, _node(T.FRACTION, a, b)),
    )


def _pq_scaled_negative(f: _Family) -> SolveResult | None:
    """PQ formula after dividing by ``a`` for ``a > 1, b < 0, c > 0`` (e.g. 3x^2-7x+2=0)."""
    a, b, c, x = f.a, f.b, f.c, f.x
    if a == 1 or b >= 0 or c == 0:
        return None
    big_p, big_q = Fraction(b, a), Fraction(c, a)
    h = -big_p / 2
    r = Fraction(f.root, 2 * a)
    two, num = _num(2), _num
    result = SolveResult()
    p_node = _fraction_node(big_p)
    negative_q = big_q < 0
    abs_q = _fraction_node(abs(big_q))
    # the constant as written under the root: "- (-1/2)" when it is negative
    q_node = _node(T.BRACKET, _node(T.NEGATIVE, abs_q)) if negative_q else _fraction_node(big_q)
    x_part = _node(
        T.SUBTRACT,
        _node(T.POWER, x, two),
        _node(T.MULTIPLY_IMPLICIT, _fraction_node(-big_p), x),
    )
    divided = _eq(_node(T.SUBTRACT if negative_q else T.ADD, x_part, abs_q), num(0))
    result.add_group(
        CoreRichText(type="divide_both_sides", args=[]),
        Step(
            f.node,
            divided,
            "eq_linear_div",
            [num(a)],
            subresult=_quadratic_by_a_page(f.node, f.var, a, b, c),
        ),
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

    def state(first: CoreNode, inner: CoreNode) -> CoreNode:
        return _eq(x, _node(T.ADD_SUBTRACT, first, _node(T.ROOT2, inner)))

    half_p = _node(T.FRACTION, p_node, two)
    squared = _node(T.POWER, _node(T.BRACKET, half_p), two)
    minus_q = _node(T.SUBTRACT, squared, q_node)
    start = state(_node(T.NEGATIVE, half_p), minus_q)
    result.add_group(
        "quad_formula_abc_simple", Step(divided, start, "quad_formula_pq", [p_standard, template])
    )
    h_node = _fraction_node(h)
    compound = _node(T.FRACTION, _fraction_node(h * 2), two)  # (7/3) / 2
    after_sign = state(compound, minus_q)
    inner_rewritten = _node(
        T.POWER,
        _node(T.BRACKET, _node(T.NEGATIVE, compound)),
        two,
    )
    rewritten = state(compound, _node(T.SUBTRACT, inner_rewritten, q_node))
    sign_steps = [
        Step(
            start,
            after_sign,
            "frac_resolve_neg",
            subresult=_sign_flip_page(_node(T.NEGATIVE, half_p), compound),
        ),
        Step(after_sign, rewritten, "frac_extract_neg", [_extract_rule()]),
    ]
    titles = ["frac_resolve_neg", "frac_extract_neg"]
    tail = _node(T.SUBTRACT, inner_rewritten, q_node)
    if negative_q:  # -(-q) loses its brackets on the same row
        tail = _node(T.ADD, inner_rewritten, abs_q)
        opened = state(compound, tail)
        sign_steps.append(Step(rewritten, opened, "neg_neg_arg", [num(-1)]))
        titles.append("remove_bracket_short")
        rewritten = opened
    result.add_group(titles, *sign_steps)
    reduced_lead = state(h_node, tail)
    reduced_inner = _node(T.POWER, _node(T.BRACKET, _fraction_node(-h)), two)
    reduced_tail = (
        _node(T.ADD, reduced_inner, abs_q)
        if negative_q
        else _node(T.SUBTRACT, reduced_inner, q_node)
    )
    reduced_both = state(h_node, reduced_tail)
    result.add_group(
        ["frac_complex_resolve_call", "frac_complex_resolve_call"],
        Step(
            rewritten,
            reduced_lead,
            "frac_complex_resolve_call",
            subresult=_fraction_page(compound, h_node),
        ),
        Step(
            reduced_lead,
            reduced_both,
            "frac_complex_resolve_call",
            subresult=_fraction_page(_node(T.NEGATIVE, compound), _fraction_node(-h)),
        ),
    )
    squared_value = _fraction_node(h * h)
    powered = state(
        h_node,
        _node(T.ADD, squared_value, abs_q)
        if negative_q
        else _node(T.SUBTRACT, squared_value, q_node),
    )
    result.add_group(
        "pow_exp_msg",
        Step(
            reduced_both,
            powered,
            "pow_frac",
            subresult=_fraction_page(reduced_inner, squared_value),
        ),
    )
    radicand = h * h - big_q
    summed = state(h_node, _fraction_node(radicand))
    sum_key = "frac_add" if negative_q else "frac_sub"
    combined = (
        _node(T.ADD, squared_value, abs_q)
        if negative_q
        else _node(T.SUBTRACT, squared_value, q_node)
    )
    result.add_group(
        "calculate_short",
        Step(
            powered, summed, sum_key, subresult=_fraction_page(combined, _fraction_node(radicand))
        ),
    )
    rooted = _eq(x, _node(T.ADD_SUBTRACT, h_node, _fraction_node(r)))
    result.add_group(
        "calculate_short",
        Step(
            summed,
            rooted,
            "root_square",
            subresult=_fraction_page(_node(T.ROOT2, _fraction_node(radicand)), _fraction_node(r)),
        ),
    )
    plus = _eq(x, _node(T.ADD, h_node, _fraction_node(r)))
    minus = _eq(x, _node(T.SUBTRACT, h_node, _fraction_node(r)))
    listed = _node(T.LIST, plus, minus)
    result.add_group("quad_separate", Step(rooted, listed, "quad_separate_signs", list(_SIGNS)))
    values = [h + r, h - r]
    result.add_group(
        ["frac_add", "frac_sub"],
        Step(
            listed,
            f.solved(values[0]),
            "frac_add",
            subresult=_fraction_page(
                plus.children[1], _fraction_node(values[0]), reduce_result=True
            ),
        ),
        Step(
            listed,
            f.solved(values[1]),
            "frac_sub",
            subresult=_fraction_page(
                minus.children[1], _fraction_node(values[1]), reduce_result=True
            ),
        ),
    )
    f.finish(result, [f.solved(values[0]), f.solved(values[1])])
    return result


def _is_difference_of_squares(f: _Family) -> bool:
    if not isinstance(f.c, int):
        return False
    return f.a == 1 and f.b == 0 and f.c < 0 and isqrt(-f.c) ** 2 == -f.c


def _extraction(node: CoreNode, var: str, c: int, moved_already: bool = False) -> SolveResult:
    """``x^2 + c = 0`` with ``c < 0``: move the constant, take the root, split the signs.

    ``moved_already`` is for ``x^2 = k``, where the app takes the root straight away.
    """
    x, size = CoreNode.variable(var), -c
    exact = isqrt(size) ** 2 == size
    simplified = None if exact else sympy.sqrt(size)  # 2*sqrt(3) for 12; sqrt(2) stays a root
    reducible = simplified is not None and simplified.is_Mul
    root = (
        _num(isqrt(size))
        if exact
        else from_sympy(simplified)
        if reducible
        else _node(T.ROOT2, _num(size))
    )
    result = SolveResult()
    square = _node(T.POWER, x, _num(2))
    moved = _eq(square, _num(size))
    balanced = _eq(
        _node(T.ADD, _node(T.SUBTRACT, square, _num(size)), _num(size)),
        _node(T.ADD, _num(0), _num(size)),
    )
    swap = SolveResult()
    swap.add_group("rel_swap_right_const", Step(node, balanced, "rel_swap_right_const"))
    swap.add_group(
        "remove_opposites",
        Step(balanced, moved, "sub_with_self_remove_num"),
        Step(balanced, moved, "add_with_zero", [_num(0)]),
    )
    swap.set_solution(moved)
    if not moved_already:
        result.add_group(
            "rel_move_right_const_msg",
            Step(node, moved, "rel_move_right_const_eq", subresult=swap),
        )
    plus_minus = _eq(x, _node(T.ADD_SUBTRACT, root))
    rooted = _eq(_node(T.ROOT2, square), _node(T.ADD_SUBTRACT, _node(T.ROOT2, _num(size))))
    take = None
    if exact or reducible:  # the root is evaluated on a detail screen of its own
        take = SolveResult()
        take.add_group("quad_sqrt_sides", Step(moved, rooted, "quad_sqrt_sides"))
        take.add_group("calculate_short", Step(rooted, plus_minus, "root_square"))
        take.set_solution(plus_minus)
    result.add_group("simplify_eq", Step(moved, plus_minus, "quad_sqrt_sides", subresult=take))
    negative = _num(-isqrt(size)) if exact else _node(T.NEGATIVE, root)  # -2*sqrt(3) as a minus
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
    m, var, x = isqrt(-int(f.c)), f.var, f.x
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
    squared = _eq(
        _node(T.SUBTRACT, _node(T.POWER, x, _num(2)), _node(T.POWER, _num(m), _num(2))),
        _num(0),
    )
    detail = SolveResult()
    detail.add_group("write_as_num_arg", Step(f.node, squared, "write_as_num_arg", [_num(2)]))
    detail.add_group(
        CoreRichText(type="using_factor", args=[formula]),
        Step(squared, product, "using_factor", [formula]),
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
    """``x² ± 2m x + m² = 0`` (D = 0): factoring, roots formula, PQ formula (verified shapes)."""
    m = isqrt(c) if c > 0 else 0
    if m * m != c or m == 0 or b not in (-2 * m, 2 * m):
        return None
    x, zero, two, num = CoreNode.variable(var), _num(0), _num(2), _num
    value = Fraction(-b, 2)
    root = num(int(value))
    solution = _eq(x, root)
    base = _node(T.ADD, x, num(m)) if b > 0 else _node(T.SUBTRACT, x, num(m))
    offset = num(m)

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
        CoreRichText(type="write_as_mul_expr_two_f", args=[two, x]),
        Step(node, node, "write_as_mul_expr_two_f", [two, x]),
    )
    factor_detail.add_group("write_as_num_arg", Step(node, node, "write_as_num_arg", [two]))
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
    balanced = _eq(_node(T.ADD, base, offset), _node(T.ADD, zero, offset))
    move = SolveResult()
    move.add_group("rel_swap_right_const", Step(equated, balanced, "rel_swap_right_const"))
    move.add_group("remove_opposites", Step(balanced, solution, "sub_with_self_remove_num"))
    move.add_group(
        CoreRichText(type="remove_zero", args=[zero]),
        Step(balanced, solution, "add_with_zero", [zero]),
    )
    move.set_solution(solution)
    factoring.add_group(
        "rel_move_right_const_msg",
        Step(equated, solution, "rel_move_right_const_eq", subresult=move),
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
        Step(flipped, powered, "pow", [], subresult=_squared_page(b_sq, b, b * b)),
        Step(
            powered,
            multiplied,
            "mul",
            [],
            subresult=_product_page(_node(T.MULTIPLY, num(4), _paren(c)), 4 * c, subtracted=True),
        ),
    )
    cancelled = state(num(-b), num(0), two)
    formula_m.add_group(
        "sub_with_self_del_num",
        Step(multiplied, cancelled, "sub_with_self_num", [num(0)]),
    )
    rooted = _eq(x, _node(T.FRACTION, _node(T.ADD_SUBTRACT, num(-b), num(0)), two))
    formula_m.add_group("root", Step(cancelled, rooted, "root_zero", [num(0)]))
    halved = _eq(x, _node(T.FRACTION, num(-b), two))
    formula_m.add_group(
        CoreRichText(type="remove_zero", args=[num(0)]),
        Step(rooted, halved, "add_with_zero", [num(0)]),
    )
    formula_m.add_group(
        "frac_reduce_frac",
        Step(
            halved,
            solution,
            "frac_reduce_frac_num",
            [two],
            subresult=_detail(_node(T.FRACTION, num(-b), two), solution),
        ),
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
    half_p = _paren(b // 2)  # p/2: (−m) for the verified x² − 2mx + m², m for x² + 2mx + m²
    lead = _node(T.NEGATIVE, half_p) if b < 0 else num(int(value))
    first = _eq(
        x,
        _node(
            T.ADD_SUBTRACT,
            lead,
            _node(
                T.ROOT2, _node(T.SUBTRACT, _node(T.POWER, _node(T.BRACKET, half_b), two), num(c))
            ),
        ),
    )
    second = _eq(x, _node(T.ADD_SUBTRACT, lead, zero))
    pq.add_group(
        ["frac_reduce_frac", "calculate_short"],
        Step(
            p_start,
            first,
            "frac_reduce_frac_num",
            [two],
            subresult=_detail(half_b, half_p),
        ),
        Step(first, second, "calculate_direct"),
    )
    plain = second
    if b < 0:
        plain = _eq(x, _node(T.ADD_SUBTRACT, num(int(value)), zero))
        pq.add_group("remove_bracket_short", Step(second, plain, "neg_neg_arg", [num(-1)]))
    pq.add_group(
        CoreRichText(type="remove_zero", args=[num(0)]),
        Step(plain, solution, "add_with_zero", [num(0)]),
    )
    pq.set_solution(solution)
    # A monic double root is always «obvious» (:func:`_obvious_discriminant`): case
    # ``quad_double`` (x²−4x+4) shows the three solving cards only.
    return [factoring, formula_m, pq]


def _text_answer(key: str, *args: CoreNode) -> CoreNode:
    """``TEXT[TEXT_KEY(key), args…]`` — the contract form of a text answer."""
    return CoreNode.node(T.TEXT, CoreNode(type=T.TEXT_KEY, value=key), *args)


def _discriminant_cards(
    node: CoreNode,
    var: str,
    a: int,
    b: int,
    c: int | Fraction,
    verdict: tuple[str | CoreRichText, str, list[CoreNode]],
    count: CoreNode,
) -> tuple[SolveResult, SolveResult]:
    """The app's "number of solutions" and "discriminant" cards; ``verdict`` is the last row.

    A decimal constant stays a decimal here (``6.5``), as the app writes it.
    """
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
            _node(T.MULTIPLY, _num(4), _num(a), _decimal_paren(c)),
        ),
    )
    value = b * b - 4 * a * c
    computed = _eq(letters, _num(value))
    coefficients = [_num(a), _num(b), _number(c)]

    standard = node
    if node.type is T.EQUALS and _number_value(node.children[1]) not in (None, 0):
        terms = [
            (1, _mono(a, 2, var)),
            (1 if b > 0 else -1, _mono(abs(b), 1, var)),
            (1 if c > 0 else -1, _number(abs(Fraction(c)))),
        ]
        standard = _eq(
            _chain([term for term in terms if term[1].type is not T.CONSTANT or c != 0]),
            _num(0),
        )

    def rows(result: SolveResult) -> None:
        if standard is not node:
            standard_page = SolveResult()
            standard_page.add_group(
                "rel_swap_left_const", Step(node, standard, "rel_swap_left_const")
            )
            standard_page.add_group(
                "remove_opposites",
                Step(standard, standard, "sub_with_self_num", [_num(0)]),
            )
            standard_page.set_solution(standard)
            result.add_group(
                "rewrite_eq",
                Step(node, standard, "eq_quad_std_form", subresult=standard_page),
            )
        detail = SolveResult()
        if a == 1:
            detail.add_group(
                "sum_suffix_add_one",
                Step(standard, template, "sum_suffix_add_one", [_num(1)]),
            )
        if b == 1:
            detail.add_group(
                "sum_suffix_add_one",
                Step(standard, template, "sum_suffix_add_one", [_num(1)]),
            )
        if b == 0:
            detail.add_group(
                "extrema_coeff_missing",
                Step(
                    standard,
                    template,
                    "extrema_coeff_missing",
                    [CoreNode.variable(var), _num(0)],
                ),
            )
        if b == -1 or a == -1:
            detail.add_group(
                "sum_suffix_add_neg_one",
                Step(standard, template, "sum_suffix_add_neg_one", [_num(-1)]),
            )
        detail.add_group("sub_as_add", Step(standard, template, "sub_as_add"))
        if b < 0 and c < 0:
            detail.add_group("sub_as_add", Step(standard, template, "sub_as_add"))
        if c == 0:
            detail.add_group("add_with_zero", Step(standard, template, "add_with_zero", [_num(0)]))
        detail.add_group(
            "extrema_coeff_smpl", Step(template, template, "eq_quad_coeff_identify", coefficients)
        )
        detail.set_solution(template)
        result.add_group(
            "extrema_coeff_smpl",
            Step(standard, template, "eq_quad_coeff_identify", coefficients, subresult=detail),
        )
        letters_in_order = [
            _eq(la, _num(a)),
            _eq(lb, _num(b)),
            _eq(lc, _number(c)),
            substituted.children[1],
        ]
        result.add_group(
            "coeff_sub",
            Step(template, substituted, "eq_quad_eval_disc_sub", letters_in_order),
        )
        calculate = SolveResult()
        squared = _node(T.POWER, _paren(b) if b < 0 else _num(b), two)
        if b == 0:
            calculate.add_group(
                "calculate_short", Step(substituted.children[1], _num(0), "pow_zero", [_num(0)])
            )
        else:
            if not (a == 1 and c != 0):
                calculate.add_group(
                    "calculate_short", Step(substituted.children[1], squared, "pow")
                )
        product = _node(T.MULTIPLY, _num(4), _num(a), _decimal_paren(c))
        if c == 0:
            calculate.add_group(
                "calculate_short", Step(squared, squared, "mul_with_zero", [_num(0)])
            )
            calculate.add_group(
                "calculate_short",
                Step(substituted.children[1], computed, "add_with_zero", [_num(0)]),
            )
        elif b == 0:
            if a == 1:
                calculate.add_group(
                    "calculate_short", Step(_num(0), product, "mul_with_one", [_num(1)])
                )
                calculate.add_group("calculate_short", Step(product, product, "mul"))
            else:
                calculate.add_group("calculate_short", Step(_num(0), product, "product"))
            calculate.add_group(
                "calculate_short",
                Step(substituted.children[1], computed, "add_with_zero", [_num(0)]),
            )
        elif a == 1:
            four = _node(T.MULTIPLY, _num(4), _num(1))
            calculate.add_group(
                "calculate_short",
                Step(substituted.children[1], four, "mul_with_one", [_num(1)]),
            )
            calculate.add_group(
                "calculate_short",
                Step(
                    substituted.children[1],
                    squared,
                    "pow_one" if b == 1 else "pow",
                    [_num(1)] if b == 1 else [],
                ),
            )
            calculate.add_group("calculate_short", Step(squared, product, "mul"))
            calculate.add_group(
                "calculate_short",
                Step(
                    substituted.children[1],
                    computed,
                    "sub_with_self_num" if value == 0 else ("sub" if 4 * a * c > 0 else "add"),
                    [_num(0)] if value == 0 else [],
                ),
            )
        else:
            calculate.add_group("calculate_short", Step(squared, product, "product"))
            calculate.add_group(
                "calculate_short",
                Step(
                    substituted.children[1],
                    computed,
                    "sub_with_self_num" if value == 0 else ("sub" if 4 * a * c > 0 else "add"),
                    [_num(0)] if value == 0 else [],
                ),
            )
        calculate.set_solution(computed)
        result.add_group(
            "calculate_short",
            Step(substituted, computed, "calculate_direct", [], subresult=calculate),
        )

    discriminant = SolveResult()
    rows(discriminant)
    discriminant.set_solution(_num(value))
    counting = SolveResult()
    rows(counting)
    title, key, args = verdict
    counting.add_group(title, Step(computed, count, key, args))
    # the app's answer to the counting card is a text card, not the number of roots
    text_answers = {
        "eq_quad_disc_solution_all_gt": ("two", [count]),
        "eq_quad_disc_solution_all_eq": ("one", [count]),
        "eq_quad_disc_no_solution_var_lt": ("zero", []),
        "eq_quad_disc_imag_solution_var_lt": ("imag", [count]),
    }
    suffix, text_args = text_answers.get(key, ("two", [count]))
    counting.set_solution(_text_answer(f"eq_quad_disc_solution_{suffix}", *text_args))
    return counting, discriminant


def _pq_negative(node: CoreNode, var: str, b: int, c: int) -> list[SolveResult]:
    """PQ formula for ``x^2 + p x + q = 0`` (even ``p > 0``, ``D < 0``): complex and real cards."""
    half = b // 2
    k2 = c - half * half
    k = isqrt(k2)
    if b % 2 or half * half >= c or k * k != k2:
        return []
    x, two, num = CoreNode.variable(var), _num(2), _num
    p, q = CoreNode.variable("p"), CoreNode.variable("q")
    standard = _eq(
        _node(T.ADD, _node(T.ADD, _node(T.POWER, x, two), _node(T.MULTIPLY_IMPLICIT, p, x)), q),
        num(0),
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

    def state(first: CoreNode, inner: CoreNode) -> CoreNode:
        return _eq(x, _node(T.ADD_SUBTRACT, first, _node(T.ROOT2, inner)))

    def build(result: SolveResult) -> CoreNode:
        b_half = _node(T.FRACTION, num(b), two)
        start = state(
            _node(T.NEGATIVE, b_half),
            _node(T.SUBTRACT, _node(T.POWER, _node(T.BRACKET, b_half), two), num(c)),
        )
        result.add_group(
            "quad_formula_abc_simple", Step(node, start, "quad_formula_pq", [standard, template])
        )
        first = state(
            num(-half), _node(T.SUBTRACT, _node(T.POWER, _node(T.BRACKET, b_half), two), num(c))
        )
        second = state(num(-half), _node(T.SUBTRACT, _node(T.POWER, num(half), two), num(c)))
        # verified x² + 2x + 5: b/2 = 2/2 is «divide by itself»; any other b reduces the fraction
        reduce_key, reduce_args = (
            ("div_with_self", [num(1)]) if half == 1 else ("frac_reduce_frac_num", [two])
        )
        result.add_group(
            "divide",
            Step(start, first, reduce_key, reduce_args),
            Step(first, second, reduce_key, reduce_args),
        )
        third = state(num(-half), _node(T.SUBTRACT, num(half * half), num(c)))
        if half == 1:
            result.add_group(
                ["pow_one", "calculate_short"], Step(second, third, "pow_one", [num(1)])
            )
        else:
            result.add_group("calculate_short", Step(second, third, "pow"))
        negative = _node(T.NEGATIVE, num(k2))
        fourth = state(num(-half), negative)
        result.add_group(
            "calculate_short",
            Step(
                third,
                fourth,
                "calc_diff",
                [],
                subresult=_detail(_node(T.SUBTRACT, num(half * half), num(c)), negative),
            ),
        )
        return fourth

    unit = CoreNode.constant("i")
    root_value = unit if k == 1 else _node(T.MULTIPLY_IMPLICIT, num(k), unit)
    complex_result = SolveResult()
    fourth = build(complex_result)
    rooted = _eq(x, _node(T.ADD_SUBTRACT, num(-half), root_value))
    complex_result.add_group(
        "calculate_short",
        Step(
            fourth,
            rooted,
            "root_square",
            [],
            subresult=_detail(_node(T.ROOT2, _node(T.NEGATIVE, num(k2))), root_value),
        ),
    )
    roots = [_eq(x, _node(sign, num(-half), root_value)) for sign in (T.ADD, T.SUBTRACT)]
    listed = _node(T.LIST, *roots)
    complex_result.add_group(
        "quad_separate", Step(rooted, listed, "quad_separate_signs", list(_SIGNS))
    )
    complex_result.add_group(
        CoreRichText(type="solution_eq_num", args=[two]),
        Step(listed, listed, "solution_eq_num", [two]),
    )
    complex_result.set_solution(listed)
    real_result = SolveResult()
    fourth = build(real_result)
    real_result.add_group("expr_not_def_in_r", Step(fourth, fourth, "root_sqr_neg"))
    real_result.set_solution(CoreNode.empty())
    return [complex_result, real_result]


def _negative_discriminant(node: CoreNode, var: str, b: int, c: int) -> list[SolveResult] | None:
    """``x^2 + b x + c = 0`` with D = -m^2 < 0 (worked out for b > 0, c > 0).

    Four methods: the roots formula to complex roots, the same formula ending at "the root of a
    negative number is not defined", and the two discriminant cards.
    """
    d = b * b - 4 * c
    m = isqrt(abs(d))
    if b <= 0 or c <= 0 or d == 0 or m * m != abs(d):
        return None
    x, two, num = CoreNode.variable(var), _num(2), _num
    unit = CoreNode.constant("i")

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
                subresult=_product_page(
                    _node(T.MULTIPLY, num(4), _paren(c)), 4 * c, subtracted=c > 0
                ),
            ),
        )
        negative = _node(T.NEGATIVE, num(-d)) if d < 0 else num(d)
        subtracted = state(minus_b, negative, two)
        # a negative difference has a detail screen of its own; a positive one does not
        detail = _detail(_node(T.SUBTRACT, num(b * b), num(4 * c)), negative) if d < 0 else None
        result.add_group(
            "calculate_short",
            Step(
                multiplied,
                subtracted,
                "calc_diff" if d < 0 else "sub",
                [],
                subresult=detail,
            ),
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
    if d > 0:
        real_roots = [Fraction(-b + m, 2), Fraction(-b - m, 2)]
        complex_result.add_group(
            "calculate_direct",
            *[
                Step(
                    listed,
                    _eq(x, _fraction_node(root)),
                    "simplify"
                    if _branch_key(-b, 1 if index == 0 else -1, m) == "sub"
                    and root.denominator != 1
                    else "calculate_direct",
                    [],
                    subresult=_branch_page(-b, 1 if index == 0 else -1, m, 2, root),
                )
                for index, root in enumerate(real_roots)
            ],
        )
    else:
        complex_result.add_group(
            "simplify",
            *[
                Step(
                    listed,
                    root,
                    "simplify",
                    [],
                    subresult=_detail(part.children[1], root.children[1]),
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
    if d > 0:  # real roots: the app's formula card only
        return [complex_result]

    # -- the same formula, stopping where the real numbers end
    real_result = SolveResult()
    subtracted = common_rows(real_result)
    real_result.add_group("expr_not_def_in_r", Step(subtracted, subtracted, "root_sqr_neg"))
    real_result.set_solution(CoreNode.empty())

    counting, discriminant = _discriminant_cards(
        node,
        var,
        1,
        b,
        c,
        ("eq_quad_disc_no_solution_simple", "eq_quad_disc_no_solution_var_lt", [num(0)]),
        CoreNode.empty(),
    )
    imaginary_count, _ = _discriminant_cards(
        node,
        var,
        1,
        b,
        c,
        (
            CoreRichText(type="eq_quad_disc_imag_solution_simple", args=[two]),
            "eq_quad_disc_imag_solution_var_lt",
            [num(0), two],
        ),
        two,
    )
    family = _Family(var, 1, b, c)
    squares = [
        m for m in (_completing_square(family), _completing_square(family, real_only=True)) if m
    ]
    return [
        complex_result,
        real_result,
        *_pq_negative(node, var, b, c),
        *squares,
        counting,
        imaginary_count,
        discriminant,
    ]


def _obvious_discriminant(a: int, b: int, d: int) -> bool:
    """Whether the app leaves «Количество решений»/«Вычислите дискриминант» out.

    The app shows those two cards only where the number of real roots is not
    visible at a glance: a non-monic equation with a linear term (2x²+5x+2,
    3x²−7x+2, 2x²−x−1, 2x²+3x−2) or irrational roots (x²−2). For a monic
    equation with integer roots (x²−5x+6, x²+4x+3, x²−x=0, −x²+5x−6,
    x²−4x+4) and for the extraction family (x²=9, x²−4, 3x²=12) it does not
    (cases ``quad_factor``, ``quad_double``, ``eq_3x2`` vs ``q_a2_pos``,
    ``quad_irr``).
    """
    square = isqrt(d) ** 2 == d if d >= 0 else False
    return square and (abs(a) == 1 or b == 0)


def _two_real_cards(node: CoreNode, var: str, a: int, b: int, c: int) -> list[SolveResult]:
    """The app's «Количество решений» and «Вычислите дискриминант» cards."""
    if _obvious_discriminant(a, b, b * b - 4 * a * c):
        return []
    two = _num(2)
    verdict = (
        CoreRichText(type="eq_quad_disc_solution_plural_simple", args=[two]),
        "eq_quad_disc_solution_all_gt",
        [_num(0), two],
    )
    return list(_discriminant_cards(node, var, a, b, c, verdict, two))


def inequality_rows(
    node: CoreNode, var: str, a: int, b: int, c: int, result: SolveResult, answer: CoreNode
) -> bool:
    """``x^2 + b x + c < 0`` with b < 0 < c and rational roots, as the app shows it.

    Factor into brackets, split into two sign cases, solve each inequality, intersect, unite.
    Returns ``False`` without touching ``result`` outside the verified family.
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


def _after_moving_left(
    node: CoreNode, zero_form: CoreNode, result: SolveResult | None
) -> SolveResult | None:
    """``x^2 = k`` for the cards that work on ``x^2 - k = 0``: one row moving ``k`` to the left."""
    if result is None:
        return None
    constant = node.children[1]
    balanced = _eq(
        _node(T.SUBTRACT, node.children[0], constant), _node(T.SUBTRACT, constant, constant)
    )
    swap = SolveResult()
    swap.add_group("rel_swap_left_const", Step(node, balanced, "rel_swap_left_const"))
    swap.add_group("remove_opposites", Step(balanced, zero_form, "sub_with_self_num", [_num(0)]))
    swap.set_solution(zero_form)
    moved = SolveResult()
    moved.add_group(
        "rel_move_left_const_msg",
        Step(node, zero_form, "rel_move_left_const", subresult=swap),
    )
    moved.extend(result)
    moved.set_solution(result.solution or zero_form)
    return moved


def _scaled_square(node: CoreNode, var: str, k: int, n: int) -> list[SolveResult] | None:
    """``k x^2 = k n`` with ``n`` a perfect square: divide by ``k``, then the ``x^2 = n`` cards.

    the app (3x^2 = 12): the root card starts with the division, the other three move
    the constant left and divide before they continue on ``x^2 - n = 0``.
    """
    if isqrt(n) ** 2 != n:
        return None
    x, kk = CoreNode.variable(var), _num(k)
    square = _node(T.POWER, x, _num(2))
    base = _eq(square, _num(n))

    def division(before: CoreNode, after: CoreNode) -> tuple[str | CoreRichText, Step]:
        detail = SolveResult()
        detail.add_group(
            CoreRichText(type="eq_linear_div", args=[kk]),
            Step(before, after, "eq_linear_div", [kk]),
        )
        detail.add_group(
            "divide",
            Step(after, after, "div_with_self", [_num(1)]),
            Step(after, after, "quotient"),
        )
        detail.set_solution(after)
        return "divide_both_sides", Step(before, after, "eq_linear_div", [kk], subresult=detail)

    root_card = SolveResult()
    title, step = division(node, base)
    root_card.add_group(title, step)
    extracted = _extraction(base, var, -n, moved_already=True)
    root_card.extend(extracted)
    root_card.solution = extracted.solution
    family = _Family(var, 1, 0, -n)
    scaled = _eq(_poly([(k, 2), (-k * n, 0)], var), _num(0))
    moved = _after_moving_left(node, scaled, SolveResult())
    if moved is None:
        return None
    title, step = division(scaled, family.node)
    prefix = SolveResult()
    prefix.add_group(title, step)
    prefix.extend(moved)
    cards = [root_card]
    for built in [_difference_of_squares(family), *_pure_square_formulas(family.node, var, -n)]:
        if built is None:
            continue
        card = SolveResult()
        card.extend(prefix)
        card.extend(built)
        card.solution = built.solution
        cards.append(card)
    return cards


def _has_zero_term(node: CoreNode) -> bool:
    """Whether a literal ``+0`` / ``−0`` stands in the equation (as typed)."""
    if node.type is not T.EQUALS:
        return False
    return any(
        part.type is T.CONSTANT and _number_value(part) == 0 for part in node.children[0].walk()
    )


def _x_squared_minus_x(node: CoreNode, var: str, a: int = 1, b: int = -1) -> list[SolveResult]:
    """``a x² + b x = 0``: factoring, roots formula, PQ formula and completing the square.

    The four cards the app shows for ``x² − x = 0`` and for every other
    missing constant; ``c = 0`` has rows of its own (the constant is simply absent), so this
    family is built by hand rather than from the generic rows.
    """
    x, two, num = CoreNode.variable(var), _num(2), _num
    zero, one = num(0), num(1)
    la, lb, lc = (CoreNode.variable(v) for v in "abc")
    p, q = CoreNode.variable("p"), CoreNode.variable("q")
    values = sorted((Fraction(0), Fraction(-b, a)))
    solved = _node(T.LIST, _eq(x, num(values[0])), _eq(x, num(values[1])))
    answer = _node(T.LIST, _eq(x, num(Fraction(-b, a))), _eq(x, zero))
    count = [CoreRichText(type="solution_eq_num", args=[two])]

    def finish(result: SolveResult, before: CoreNode, result_node: CoreNode) -> None:
        result.add_group(count[0], Step(before, result_node, "solution_eq_num", [two]))
        result.set_solution(result_node)

    # -- factoring
    factoring = SolveResult()
    bracket = _poly([(a, 1), (b, 0)], var)
    product = _eq(_node(T.MULTIPLY, x, _node(T.BRACKET, bracket)), zero)
    factoring.add_group("factorise_call", Step(node, product, "extract_arg", [x]))
    cases = [_eq(x, zero), _eq(bracket, zero)]
    listed = _node(T.LIST, *cases)
    factoring.add_group(
        "eq_separate_short", Step(product, listed, "quad_separate_zero_product", [zero])
    )
    factoring.add_group(
        "eq_solve_short",
        Step(
            listed,
            solved,
            "eq_linear",
            [x],
            subresult=_solve_linear(cases[1], var),
        ),
    )
    finish(factoring, solved, solved)

    # -- roots formula
    formula = SolveResult()
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

    def fraction_state(first: CoreNode, inner: CoreNode, denominator: CoreNode) -> CoreNode:
        return _eq(
            x,
            _node(
                T.FRACTION,
                _node(T.ADD_SUBTRACT, first, _node(T.ROOT2, inner)),
                denominator,
            ),
        )

    paren_b = _paren(b)
    bracket_square = _node(T.POWER, paren_b, two)
    square_value = num(b * b)
    four_ac = _node(T.MULTIPLY, num(4), num(a), zero)
    start = fraction_state(
        _node(T.NEGATIVE, paren_b),
        _node(T.SUBTRACT, bracket_square, four_ac),
        _node(T.MULTIPLY, two, num(a)),
    )
    formula.add_group(
        "quad_formula_abc_simple", Step(node, start, "quad_formula_abc", [standard, template])
    )
    denominator = two if a == 1 else _node(T.MULTIPLY, two, num(a))
    pages = []
    current = start
    if a == 1:
        no_one = fraction_state(
            _node(T.NEGATIVE, paren_b), _node(T.SUBTRACT, bracket_square, four_ac), two
        )
        pages.append(Step(current, no_one, "mul_with_one", [one]))
        current = no_one
    if b < 0:
        flipped = fraction_state(num(-b), _node(T.SUBTRACT, bracket_square, four_ac), denominator)
        pages.append(Step(current, flipped, "neg_neg_arg", [num(-1)]))
        current = flipped
    if abs(b) == 1:
        powered = fraction_state(num(-b), _node(T.SUBTRACT, one, four_ac), denominator)
        pages.append(
            Step(
                current,
                powered,
                "pow",
                [],
                subresult=_squared_page(bracket_square, b, b * b),
            )
        )
        current = powered
    zeroed = fraction_state(num(-b), _node(T.SUBTRACT, square_value, zero), denominator)
    pages.append(Step(current, zeroed, "mul_with_zero", [zero]))
    formula.add_group(["calculate_short", "remove_bracket_short", "find_value"], *pages)
    cleared = fraction_state(num(-b), square_value, denominator)
    formula.add_group(
        CoreRichText(type="remove_zero", args=[zero]),
        Step(zeroed, cleared, "add_with_zero", [zero]),
    )
    root_value = isqrt(b * b)
    rooted = _eq(
        x,
        _node(
            T.FRACTION,
            _node(T.ADD_SUBTRACT, num(-b), num(root_value)),
            denominator,
        ),
    )
    formula.add_group(
        ["root", "calculate_short"],
        Step(
            cleared,
            rooted,
            "root_one" if root_value == 1 else "root_reduce",
            [one] if root_value == 1 else [two],
            subresult=None if root_value == 1 else _root_page(b * b, root_value),
        ),
    )
    plus_value = Fraction(-b + root_value, 2 * a)
    minus_value = Fraction(-b - root_value, 2 * a)
    plus = _eq(x, _node(T.FRACTION, _node(T.ADD, num(-b), num(root_value)), denominator))
    minus = _eq(x, _node(T.FRACTION, _node(T.SUBTRACT, num(-b), num(root_value)), denominator))
    pair = _node(T.LIST, plus, minus)
    formula.add_group("quad_separate", Step(rooted, pair, "quad_separate_signs", list(_SIGNS)))
    formula.add_group(
        "calculate_short",
        Step(
            pair,
            answer,
            "calculate_direct",
            subresult=_branch_page(-b, 1, root_value, 2 * a, plus_value),
        ),
        Step(
            pair,
            answer,
            "calculate_direct",
            subresult=_branch_page(-b, -1, root_value, 2 * a, minus_value),
        ),
    )
    finish(formula, answer, answer)

    # -- PQ formula
    pq = SolveResult()
    p_half = _node(T.FRACTION, p, two)
    pq_standard = _eq(
        _node(T.ADD, _node(T.ADD, _node(T.POWER, x, two), _node(T.MULTIPLY_IMPLICIT, p, x)), q),
        zero,
    )
    pq_template = _eq(
        x,
        _node(
            T.ADD_SUBTRACT,
            _node(T.NEGATIVE, p_half),
            _node(T.ROOT2, _node(T.SUBTRACT, _node(T.POWER, _node(T.BRACKET, p_half), two), q)),
        ),
    )
    half_value = Fraction(b, 2 * a)  # p = b/a once the equation is divided by a
    half = _fraction_node(half_value)
    abs_half = _fraction_node(abs(half_value))
    squared = _node(T.POWER, _node(T.BRACKET, half), two)

    def pq_state(first: CoreNode, inner: CoreNode | None) -> CoreNode:
        tail = _node(T.ROOT2, inner) if inner is not None else half
        return _eq(x, _node(T.ADD_SUBTRACT, first, tail))

    pq_start = pq_state(_node(T.NEGATIVE, half), _node(T.SUBTRACT, squared, zero))
    pq_from = node
    if a != 1:
        pq_from = _eq(_poly([(1, 2), (Fraction(b, a), 1)], var), zero)
        pq.add_group(
            CoreRichText(type="eq_linear_div", args=[num(a)]),
            Step(
                node,
                pq_from,
                "eq_linear_div",
                [num(a)],
                subresult=_quadratic_by_a_page(
                    _eq(_poly([(a, 2), (b, 1)], var), zero), var, a, b, 0, moved=True
                ),
            ),
        )
    pq.add_group(
        "quad_formula_abc_simple",
        Step(pq_from, pq_start, "quad_formula_pq", [pq_standard, pq_template]),
    )
    kept = pq_state(_node(T.NEGATIVE, half), squared)
    pq.add_group(
        CoreRichText(type="remove_zero", args=[zero]),
        Step(pq_start, kept, "add_with_zero", [zero]),
    )
    cancelled = _eq(x, _node(T.ADD_SUBTRACT, _node(T.NEGATIVE, half), abs_half))
    reduced = _eq(x, _node(T.ADD_SUBTRACT, abs_half, abs_half))
    root_page = SolveResult()
    root_page.add_group("root_reduce", Step(kept, kept, "root_reduce", [_num(2)]))
    root_page.add_group("abs_neg", Step(kept, cancelled, "abs_neg", [_num(-1)]))
    root_page.set_solution(cancelled)
    if half_value < 0:
        pq.add_group(
            ["sign_find_short", "frac_reduce_frac"],
            Step(
                kept,
                cancelled,
                "frac_resolve_neg",
                [],
                subresult=_sign_flip_page(_node(T.NEGATIVE, half), abs_half),
            ),
            Step(cancelled, reduced, "root_reduce", [two], subresult=root_page),
        )
    else:
        # p > 0: −p/2 is already negative, only the root is taken (x² + 4x + 0)
        reduced = cancelled
        pq.add_group("calculate_short", Step(kept, cancelled, "root_reduce", [two]))
    pq_pair = _node(
        T.LIST,
        _eq(x, _node(T.ADD, _node(T.NEGATIVE, half), abs_half)),
        _eq(x, _node(T.SUBTRACT, _node(T.NEGATIVE, half), abs_half)),
    )
    pq.add_group("quad_separate", Step(reduced, pq_pair, "quad_separate_signs", list(_SIGNS)))
    plus_branch = -half_value + abs(half_value)
    # the + branch is the non-zero root only when p < 0
    pq_answer = _node(T.LIST, _eq(x, num(plus_branch)), _eq(x, num(-half_value - abs(half_value))))
    pq.add_group(
        ["calc_sum", "calc_diff"],
        Step(
            pq_pair,
            pq_answer,
            "frac_add",
            subresult=_fraction_page(
                pq_pair.children[0].children[1], num(plus_branch), reduce_result=True
            ),
        ),
        Step(pq_pair, pq_answer, "frac_sub"),
    )
    finish(pq, pq_answer, answer)

    # -- completing the square
    square = SolveResult()
    left = _poly([(1, 2), (-1, 1)], var)
    hole = CoreNode.variable("?")
    quarter = _fraction_node(Fraction(1, 4))
    both = _eq(_node(T.ADD, left, hole), _node(T.ADD, zero, hole))
    square.add_group("conics_add_both", Step(node, both, "conics_add_both"))
    added = _eq(_node(T.ADD, left, quarter), _node(T.ADD, zero, hole))
    root_form = _node(T.BRACKET, _node(T.SUBTRACT, x, _fraction_node(Fraction(1, 2))))
    identity = _eq(_node(T.ADD, left, quarter), _node(T.POWER, root_form, two))
    explain = SolveResult()
    explain.add_group(
        CoreRichText(type="eq_add_exp", args=[quarter]),
        Step(both, added, "eq_add_exp", [identity]),
    )
    explain.set_solution(added)
    square.add_group(
        CoreRichText(type="eq_add_exp", args=[quarter]),
        Step(both, added, "eq_add_exp", [identity], subresult=explain),
    )
    full = _eq(_node(T.ADD, left, quarter), _node(T.ADD, zero, quarter))
    square.add_group(
        CoreRichText(type="conics_add_right", args=[quarter]),
        Step(added, full, "conics_add_right", [quarter]),
    )
    factored = _eq(_node(T.POWER, root_form, two), _node(T.ADD, zero, quarter))
    rule = _eq(
        _node(
            T.ADD,
            _node(
                T.SUBTRACT,
                _node(T.POWER, CoreNode.variable("a"), two),
                _node(T.MULTIPLY, two, CoreNode.variable("a"), CoreNode.variable("b")),
            ),
            _node(T.POWER, CoreNode.variable("b"), two),
        ),
        _node(
            T.POWER,
            _node(T.BRACKET, _node(T.SUBTRACT, CoreNode.variable("a"), CoreNode.variable("b"))),
            two,
        ),
    )
    reduced_square = _eq(_node(T.POWER, root_form, two), quarter)
    using = SolveResult()
    using.add_group(
        CoreRichText(type="using_factor", args=[rule]), Step(full, factored, "using_factor", [rule])
    )
    using.set_solution(factored)
    square.add_group(
        ["frac_reduce_frac", "calculate_short"],
        Step(full, factored, "using_factor", [rule], subresult=using),
        Step(factored, reduced_square, "calc_sum"),
    )
    sides = _eq(
        _node(T.ROOT2, _node(T.POWER, root_form, two)),
        _node(T.ADD_SUBTRACT, _node(T.ROOT2, quarter)),
    )
    row = _eq(root_form, _node(T.ADD_SUBTRACT, _fraction_node(Fraction(1, 2))))
    solving = SolveResult()
    solving.add_group("quad_sqrt_sides", Step(reduced_square, sides, "quad_sqrt_sides"))
    solving.add_group("calculate_short", Step(sides, row, "root_square"))
    solving.add_group("quad_separate", Step(row, answer, "quad_separate_signs", list(_SIGNS)))
    solving.set_solution(answer)
    square.add_group(
        "eq_solve_short", Step(reduced_square, answer, "eq_linear", [x], subresult=solving)
    )
    finish(square, answer, answer)
    family = _Family(var, a, b, 0)
    conics = _completing_square(family)
    cards = [factoring, formula, pq, conics if conics is not None else square]
    cards.extend(_two_real_cards(node, var, a, b, 0))
    if _has_zero_term(node):
        without = _eq(_poly([(a, 2), (b, 1)], var), zero)
        prefixed: list[SolveResult] = []
        for card in cards:
            moved = SolveResult()
            moved.add_group(
                CoreRichText(type="remove_zero", args=[zero]),
                Step(node, without, "add_with_zero", [zero]),
            )
            moved.extend(card)
            moved.solution = card.solution
            if card.header is not None:
                moved.header = card.header
            prefixed.append(moved)
        cards = prefixed
    return cards


def _scaled_cards(node: CoreNode, var: str, k: int, n: int) -> list[SolveResult] | None:
    """The four extracted cards plus the app's two discriminant cards."""
    cards = _scaled_square(node, var, k, n)
    if cards is None:
        return None
    return [*cards, *_two_real_cards(node, var, k, 0, -k * n)]


def _negative_linear_page(
    equation: CoreNode, x: CoreNode, root: CoreNode, index: int
) -> SolveResult:
    """Detail pages for ``k - x = 0`` and ``k + x = 0``: move the constant, or swap the sides."""
    page = SolveResult()
    if index == 0:
        page.add_group(
            "rel_move_right_const_msg",
            Step(equation, equation, "rel_move_right_const_eq"),
        )
        page.add_group("eq_linear_neg", Step(equation, equation, "eq_linear_neg"))
    else:
        page.add_group("rel_swap_right_const", Step(equation, equation, "rel_swap_right_const"))
        page.add_group("remove_opposites", Step(equation, equation, "sub_with_self_remove_num"))
        page.add_group(
            CoreRichText(type="remove_zero", args=[_num(0)]),
            Step(equation, equation, "add_with_zero", [_num(0)]),
        )
    solution = _eq(x, root)
    page.set_solution(solution)
    return page


def _product_square_page(expression: CoreNode, value: CoreNode) -> SolveResult:
    """Detail page for ``4·(-1)·c``: the minus pair, the one, then the square."""
    detail = SolveResult()
    detail.add_group("resolve_neg_pos", Step(expression, expression, "resolve_neg_pos"))
    detail.add_group("mul_with_one", Step(expression, expression, "mul_with_one", [_num(1)]))
    detail.add_group("mul_to_pow", Step(expression, expression, "mul_to_pow"))
    detail.add_group("pow", Step(expression, value, "pow"))
    detail.set_solution(value)
    return detail


def _mul_neg_page(expression: CoreNode, value: CoreNode) -> SolveResult:
    """Detail page for ``2·(-1)``: a positive times a negative, then the product."""
    detail = SolveResult()
    detail.add_group(
        CoreRichText(type="mul_pos_neg", args=[expression]),
        Step(expression, expression, "mul_pos_neg", [expression]),
    )
    detail.add_group("mul", Step(expression, value, "mul"))
    detail.set_solution(value)
    return detail


def _division_page(expression: CoreNode, value: CoreNode) -> SolveResult:
    """Detail page for a fraction that reduces to an integer: divide, then pull the sign out."""
    detail = SolveResult()
    detail.add_group(
        "frac_reduce_frac", Step(expression, expression, "frac_reduce_frac_num", [_num(2)])
    )
    detail.add_group("neg_neg_arg", Step(expression, value, "neg_neg_arg", [_num(-1)]))
    detail.set_solution(value)
    return detail


def _negative_lead_square(node: CoreNode, var: str, k: int) -> list[SolveResult]:
    """``-x^2 + k^2 = 0``: the four cards the app shows for ``-x^2 + 4 = 0``."""
    x, two, num = CoreNode.variable(var), _num(2), _num
    zero, c = num(0), k * k
    square = _node(T.POWER, x, two)
    negative_square = _node(T.NEGATIVE, square)
    original = node

    def swap_detail(before: CoreNode, balanced: CoreNode, after: CoreNode, key: str) -> SolveResult:
        inner = SolveResult()
        inner.add_group(key, Step(before, balanced, key))
        inner.add_group("remove_opposites", Step(balanced, after, "sub_with_self_remove_num"))
        inner.add_group(
            CoreRichText(type="remove_zero", args=[num(0)]),
            Step(balanced, after, "add_with_zero", [num(0)]),
        )
        inner.set_solution(after)
        return inner

    def one_step(key: str, before: CoreNode, after: CoreNode, *args: CoreNode) -> SolveResult:
        inner = SolveResult()
        inner.add_group(key, Step(before, after, key, list(args)))
        inner.set_solution(after)
        return inner

    # -- extraction: move 4, change the signs, take the root
    root_card = SolveResult()
    moved = _eq(negative_square, num(-c))
    balanced = _eq(_node(T.SUBTRACT, original.children[0], num(c)), _node(T.SUBTRACT, zero, num(c)))
    root_card.add_group(
        "rel_move_right_const_msg",
        Step(
            original,
            moved,
            "rel_move_right_const_eq",
            subresult=swap_detail(original, balanced, moved, "rel_swap_right_const"),
        ),
    )
    positive = _eq(square, num(c))
    negate = SolveResult()
    negate.add_group("eq_mul_direct_one", Step(moved, positive, "eq_mul_direct_one", [num(-1)]))
    negate.add_group("mul_with_neg_one", Step(moved, positive, "mul_with_neg_one", [num(-1)]))
    negate.add_group("mul_with_neg_one", Step(moved, positive, "mul_with_neg_one", [num(-1)]))
    negate.set_solution(positive)
    root_card.add_group(
        "rel_linear_neg_msg",
        Step(moved, positive, "eq_linear_neg", subresult=negate),
    )
    extracted = _extraction(positive, var, -c, moved_already=True)
    root_card.extend(extracted)
    root_card.solution = extracted.solution

    # -- factoring: reorder, difference of squares, cases, solve
    factoring = SolveResult()
    reordered = _eq(_node(T.SUBTRACT, num(c), square), zero)
    factoring.add_group("reorder", Step(original, reordered, "var_order"))
    first = _node(T.SUBTRACT, num(k), x)
    second = _node(T.ADD, num(k), x)
    product = _eq(_node(T.MULTIPLY, _node(T.BRACKET, first), _node(T.BRACKET, second)), zero)
    a, b = CoreNode.variable("a"), CoreNode.variable("b")
    formula = _eq(
        _node(T.SUBTRACT, _node(T.POWER, a, two), _node(T.POWER, b, two)),
        _node(
            T.MULTIPLY,
            _node(T.BRACKET, _node(T.SUBTRACT, a, b)),
            _node(T.BRACKET, _node(T.ADD, a, b)),
        ),
    )
    detail = SolveResult()
    detail.add_group("write_as_num_arg", Step(reordered, reordered, "write_as_num_arg", [_num(2)]))
    detail.add_group(
        CoreRichText(type="using_factor", args=[formula]),
        Step(reordered, product, "using_factor", [formula]),
    )
    detail.set_solution(product)
    factoring.add_group(
        "factorise_call", Step(reordered, product, "using_factor", [formula], subresult=detail)
    )
    cases = [_eq(first, zero), _eq(second, zero)]
    listed = _node(T.LIST, *cases)
    factoring.add_group(
        "eq_separate_short", Step(product, listed, "quad_separate_zero_product", [zero])
    )
    roots = (k, -k)
    answer = _node(T.LIST, _eq(x, num(-k)), _eq(x, num(k)))
    factoring.add_group(
        "eq_solve_short_plural",
        *[
            Step(
                listed,
                _eq(x, num(root)),
                "eq_linear",
                [x],
                subresult=_negative_linear_page(case, x, num(root), index),
            )
            for index, (case, root) in enumerate(zip(cases, roots, strict=True))
        ],
    )
    factoring.add_group(
        CoreRichText(type="solution_eq_num", args=[two]),
        Step(answer, answer, "solution_eq_num", [two]),
    )
    factoring.set_solution(answer)

    # -- roots formula with a = -1
    formula_card = SolveResult()
    la, lb, lc = (CoreNode.variable(v) for v in "abc")
    standard = _eq(
        _node(
            T.ADD,
            _node(
                T.ADD,
                _node(T.MULTIPLY_IMPLICIT, la, square),
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

    def state(first_part: CoreNode, inner: CoreNode, denominator: CoreNode) -> CoreNode:
        return _eq(
            x,
            _node(
                T.FRACTION,
                _node(T.ADD_SUBTRACT, first_part, _node(T.ROOT2, inner)),
                denominator,
            ),
        )

    minus_one = _paren(-1)
    wide = _node(T.MULTIPLY, two, minus_one)
    radicand = _node(
        T.SUBTRACT,
        _node(T.POWER, zero, two),
        _node(T.MULTIPLY, num(4), minus_one, num(c)),
    )
    start = state(_node(T.NEGATIVE, zero), radicand, wide)
    formula_card.add_group(
        "quad_formula_abc_simple", Step(original, start, "quad_formula_abc", [standard, template])
    )

    def plus_minus(inner: CoreNode, denominator: CoreNode) -> CoreNode:
        return _eq(
            x,
            _node(
                T.FRACTION,
                _node(T.ADD_SUBTRACT, _node(T.ROOT2, inner)),
                denominator,
            ),
        )

    p1 = plus_minus(radicand, wide)
    p2 = plus_minus(_node(T.SUBTRACT, zero, _node(T.MULTIPLY, num(4), minus_one, num(c))), wide)
    p3 = plus_minus(_node(T.ADD, zero, num(4 * c)), wide)
    p4 = plus_minus(_node(T.ADD, zero, num(4 * c)), num(-2))
    formula_card.add_group(
        "calculate_short",
        Step(start, p1, "add_with_zero", [zero]),
        Step(p1, p2, "pow_zero", [zero]),
        Step(
            p2,
            p3,
            "product",
            subresult=_product_square_page(
                _node(T.MULTIPLY, num(4), minus_one, num(c)), num(-4 * -c)
            ),
        ),
        Step(
            p3,
            p4,
            "mul_with_neg_one",
            [minus_one],
            subresult=_mul_neg_page(wide, num(-2)),
        ),
    )
    p5 = plus_minus(num(4 * c), num(-2))
    formula_card.add_group(
        CoreRichText(type="remove_zero", args=[zero]), Step(p4, p5, "add_with_zero", [zero])
    )
    p6 = _eq(x, _node(T.FRACTION, _node(T.ADD_SUBTRACT, num(2 * k)), num(-2)))
    formula_card.add_group(
        "calculate_short",
        Step(p5, p6, "root_square", subresult=_detail(_node(T.ROOT2, num(4 * c)), num(2 * k))),
    )
    law = _eq(
        _node(T.FRACTION, CoreNode.variable("a"), _node(T.NEGATIVE, CoreNode.variable("b"))),
        _node(T.NEGATIVE, _node(T.FRACTION, CoreNode.variable("a"), CoreNode.variable("b"))),
    )
    p7 = _eq(
        x,
        _node(T.NEGATIVE, _node(T.FRACTION, _node(T.ADD_SUBTRACT, num(2 * k)), two)),
    )
    formula_card.add_group("frac_extract_neg_msg", Step(p6, p7, "frac_extract_neg", [law]))
    plus = _eq(x, _node(T.NEGATIVE, _node(T.FRACTION, num(2 * k), two)))
    minus = _eq(x, _node(T.NEGATIVE, _node(T.FRACTION, num(-2 * k), two)))
    pair = _node(T.LIST, plus, minus)
    formula_card.add_group("quad_separate", Step(p7, pair, "quad_separate_signs", list(_SIGNS)))
    half = _node(T.LIST, _eq(x, num(-k)), minus)
    formula_card.add_group(
        ["frac_reduce_frac", "calculate_short"],
        Step(
            pair,
            half,
            "frac_reduce_frac_num",
            [two],
            subresult=_detail(plus.children[1], num(-k)),
        ),
        Step(
            half,
            answer,
            "calculate_direct",
            subresult=_division_page(minus.children[1], num(k)),
        ),
    )
    formula_card.add_group(
        CoreRichText(type="solution_eq_num", args=[two]),
        Step(answer, answer, "solution_eq_num", [two]),
    )
    formula_card.set_solution(answer)

    # -- PQ formula: multiply by -1, then the x^2 - k^2 rows
    zero_form = _eq(_node(T.SUBTRACT, square, num(c)), zero)
    pq_rows = _pure_square_formulas(zero_form, var, -c)[1]
    pq_card = SolveResult()
    scaled = _eq(_node(T.SUBTRACT, square, num(c)), zero)
    square_negate = SolveResult()
    square_negate.add_group(
        "eq_mul_direct_one", Step(original, scaled, "eq_mul_direct_one", [num(-1)])
    )
    square_negate.add_group("mul_bracket", Step(original, scaled, "mul_bracket", [num(-1)]))
    square_negate.add_group("mul_with_zero", Step(original, scaled, "mul_with_zero", [num(0)]))
    square_negate.add_group("mul_neg_neg", Step(original, scaled, "mul_neg_neg", [num(-1)]))
    square_negate.add_group("mul_with_one", Step(original, scaled, "mul_with_one", [num(1)]))
    square_negate.set_solution(scaled)
    pq_card.add_group(
        "multiply_both_sides",
        Step(original, scaled, "eq_mul_direct_one", [num(-1)], subresult=square_negate),
    )
    pq_card.extend(pq_rows)
    pq_card.solution = pq_rows.solution
    return [root_card, factoring, formula_card, pq_card, *_two_real_cards(node, var, -1, 0, c)]


def _complex_general(node: CoreNode, var: str, a: int, b: int, c: int) -> list[SolveResult] | None:
    """Any ``a x^2 + b x + c = 0`` with ``D < 0``: the formula to complex roots (plus a real twin).

    The app shows the formula, the discriminant, the imaginary root and the two simplified roots;
    only ``x^2 + 2x + 5`` was worked out by hand, so other coefficients follow the same rows.
    """
    d = b * b - 4 * a * c
    if d >= 0 or a == 0:
        return None
    x, two, num = CoreNode.variable(var), _num(2), _num
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

    def state(first: CoreNode, inner: CoreNode, denominator: CoreNode) -> CoreNode:
        return _eq(
            x, _node(T.FRACTION, _node(T.ADD_SUBTRACT, first, _node(T.ROOT2, inner)), denominator)
        )

    def signed(value: int) -> CoreNode:
        return _paren(value)

    start = state(
        _node(T.NEGATIVE, signed(b)),
        _node(
            T.SUBTRACT,
            _node(T.POWER, signed(b), two),
            _node(T.MULTIPLY, num(4), signed(a), signed(c)),
        ),
        _node(T.MULTIPLY, two, signed(a)),
    )
    negative = _node(T.NEGATIVE, num(-d))
    evaluated = state(num(-b), negative, num(2 * a))
    big = isqrt(-d)
    scale = max(k for k in range(1, big + 1) if (-d) % (k * k) == 0)
    rest = (-d) // (scale * scale)
    unit = CoreNode.constant("i")

    def magnitude() -> CoreNode:
        """``scale * sqrt(rest)`` written the short way."""
        if rest == 1:
            return num(scale)
        radical = _node(T.ROOT2, num(rest))
        return radical if scale == 1 else _node(T.MULTIPLY_IMPLICIT, num(scale), radical)

    def imaginary_unit_times(value: CoreNode) -> CoreNode:
        return (
            unit
            if value.type is T.CONSTANT and value.value == "1"
            else _node(T.MULTIPLY_IMPLICIT, value, unit)
        )

    root_value = _node(T.MULTIPLY_IMPLICIT, magnitude(), unit)
    rooted = _eq(
        x,
        _node(T.FRACTION, _node(T.ADD_SUBTRACT, num(-b), root_value), num(2 * a)),
    )

    def common(result: SolveResult) -> CoreNode:
        result.add_group(
            "quad_formula_abc_simple", Step(node, start, "quad_formula_abc", [standard, template])
        )
        result.add_group(
            "calculate_short",
            Step(
                start,
                evaluated,
                "calc_diff",
                [],
                subresult=_detail(
                    _node(
                        T.SUBTRACT,
                        _node(T.POWER, signed(b), two),
                        _node(T.MULTIPLY, num(4), signed(a), signed(c)),
                    ),
                    negative,
                ),
            ),
        )
        return evaluated

    complex_result = SolveResult()
    after = common(complex_result)
    complex_result.add_group(
        "calculate_short",
        Step(
            after,
            rooted,
            "root_square",
            [],
            subresult=_detail(_node(T.ROOT2, negative), root_value),
        ),
    )
    real = Fraction(-b, 2 * a)
    imag = Fraction(scale, 2 * abs(a))

    def imaginary_part() -> CoreNode:
        coefficient_node = (
            _node(T.FRACTION, magnitude(), num(2 * abs(a)))
            if imag.denominator != 1 or rest != 1
            else num(imag)
        )
        if rest == 1 and imag.denominator != 1:
            coefficient_node = _fraction_node(imag)
        return _node(T.MULTIPLY_IMPLICIT, coefficient_node, unit)

    listed = _node(
        T.LIST,
        *[
            _eq(
                x,
                _node(
                    T.FRACTION,
                    _node(sign, num(-b), root_value),
                    num(2 * a),
                ),
            )
            for sign in (T.ADD, T.SUBTRACT)
        ],
    )
    complex_result.add_group(
        "quad_separate", Step(rooted, listed, "quad_separate_signs", list(_SIGNS))
    )
    roots = []
    for sign in (T.ADD, T.SUBTRACT):
        parts = [imaginary_part()] if real == 0 else [_fraction_node(real), imaginary_part()]
        value = (
            parts[0]
            if real == 0 and sign is T.ADD
            else (_node(T.NEGATIVE, parts[0]) if real == 0 else _node(sign, *parts))
        )
        roots.append(_eq(x, value))
    complex_result.add_group(
        "simplify",
        *[
            Step(
                listed, root, "simplify", [], subresult=_detail(part.children[1], root.children[1])
            )
            for part, root in zip(listed.children, roots, strict=True)
        ],
    )
    answer = _node(T.LIST, *roots)
    complex_result.add_group(
        CoreRichText(type="solution_eq_num", args=[two]),
        Step(listed, answer, "solution_eq_num", [two]),
    )
    complex_result.set_solution(answer)

    real_result = SolveResult()
    after = common(real_result)
    real_result.add_group("expr_not_def_in_r", Step(after, after, "root_sqr_neg"))
    real_result.set_solution(CoreNode.empty())
    _ = imaginary_unit_times
    return [complex_result, real_result]


def _square_split(n: int) -> tuple[int, int]:
    """``n = big^2 * small`` with the largest ``big``."""
    big = max(d for d in range(1, isqrt(n) + 1) if n % (d * d) == 0)
    return big, n // (big * big)


def _square_split_number(value: Fraction) -> tuple[int, int]:
    """``√value = big·√small / value.denominator`` (``value`` positive)."""
    if value.denominator == 1:
        return _square_split(value.numerator)
    return _square_split(value.numerator * value.denominator)


def _rational_sqrt(value: Fraction) -> Fraction | None:
    """``√value`` when it is rational, else ``None`` (``value >= 0``)."""
    numerator, denominator = value.numerator, value.denominator
    if numerator < 0:
        return None
    top, bottom = isqrt(numerator), isqrt(denominator)
    if top * top == numerator and bottom * bottom == denominator:
        return Fraction(top, bottom)
    return None


def _pure_square_formulas(
    node: CoreNode, var: str, c: int | Fraction, *, pq_always: bool = False
) -> list[SolveResult]:
    """``x^2 - k^2 = 0`` by the roots formula and the PQ formula, as worked out for x^2 - 4 = 0."""
    value = Fraction(-c)
    exact_root = _rational_sqrt(value)
    exact = exact_root is not None
    if value <= 0:
        return []
    k = exact_root if exact_root is not None else Fraction(0)
    n = value
    big, _small = _square_split_number(n)
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
            subresult=_signed_product_page(_node(T.MULTIPLY, num(4), _paren(c)), num(-4 * c)),
        ),
    )
    plain = fraction(pm(num(-4 * c)), two)
    formula.add_group(
        CoreRichText(type="remove_zero", args=[zero]), Step(summed, plain, "add_with_zero", [zero])
    )
    if exact:
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
        formula.add_group(
            "quad_separate", Step(rooted, listed, "quad_separate_signs", list(_SIGNS))
        )
        low, high = _eq(x, num(-k)), _eq(x, num(k))
        answer = _node(T.LIST, high, low)
        formula.add_group(
            "frac_reduce_frac",
            Step(
                listed,
                _node(T.LIST, high, minus),
                "frac_reduce_frac_num",
                [two],
                subresult=_detail(plus.children[1], num(k)),
            ),
            Step(
                _node(T.LIST, high, minus),
                answer,
                "frac_reduce_frac_num",
                [two],
                subresult=_detail(_node(T.FRACTION, num(2 * k), two), num(-k)),
            ),
        )
        formula.add_group(
            CoreRichText(type="solution_eq_num", args=[two]),
            Step(answer, answer, "solution_eq_num", [two]),
        )
        formula.set_solution(answer)
    else:
        radicand = num(4 * n)
        radical = from_sympy(sympy.sqrt(sympy.Rational(4 * n)))
        plain_inner = _node(T.ROOT2, radicand)
        pair_form = _node(
            T.LIST,
            fraction(radical, two),
            fraction(_node(T.NEGATIVE, radical), two),
        )
        if radical.to_contract() != plain_inner.to_contract():
            formula.add_group(
                "simplify",
                Step(
                    plain,
                    fraction(_node(T.ADD_SUBTRACT, radical), two),
                    "root_partial",
                    [],
                    subresult=_detail(plain_inner, radical),
                ),
            )
        formula.add_group(
            "quad_separate",
            Step(
                fraction(_node(T.ADD_SUBTRACT, radical), two),
                pair_form,
                "quad_separate_signs",
                list(_SIGNS),
            ),
        )
        root_value = from_sympy(sympy.sqrt(sympy.Rational(n)))
        half_state = _node(T.LIST, _eq(x, root_value), pair_form.children[1])
        answer = _node(T.LIST, _eq(x, root_value), _eq(x, _node(T.NEGATIVE, root_value)))
        formula.add_group(
            "simplify_msg",
            Step(pair_form, half_state, "simplify"),
            Step(half_state, answer, "simplify"),
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
    if exact:
        divided = _eq(
            x,
            _node(
                T.ADD_SUBTRACT,
                _node(T.NEGATIVE, zero),
                _node(
                    T.ROOT2,
                    _node(T.SUBTRACT, _node(T.POWER, _node(T.BRACKET, zero), two), _paren(c)),
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
            CoreRichText(type="solution_eq_num", args=[two]),
            Step(pair, pair, "solution_eq_num", [two]),
        )
        pq.set_solution(pair)
    else:
        no_one = _node(T.NEGATIVE, zero)
        n_node = _fraction_node(n)
        root_of = _node(T.ROOT2, n_node)

        def pq_state(first_part: CoreNode, inner_part: CoreNode) -> CoreNode:
            return _eq(x, _node(T.ADD_SUBTRACT, first_part, _node(T.ROOT2, inner_part)))

        half_sq = _node(T.POWER, _node(T.BRACKET, zero_half), two)
        step1 = pq_state(no_one, _node(T.SUBTRACT, half_sq, _paren(c)))
        step2 = pq_state(no_one, _node(T.SUBTRACT, _node(T.POWER, zero, two), _paren(c)))
        step3 = pq_state(no_one, _node(T.ADD, _node(T.POWER, zero, two), n_node))
        pq.add_group(
            ["divide", "remove_bracket_short"],
            Step(first, step1, "div_zero", [zero]),
            Step(step1, step2, "div_zero", [zero]),
            Step(step2, step3, "neg_neg_arg", [num(-1)]),
        )
        step4 = _eq(
            x,
            _node(T.ADD_SUBTRACT, _node(T.ROOT2, _node(T.ADD, _node(T.POWER, zero, two), n_node))),
        )
        step5 = _eq(x, _node(T.ADD_SUBTRACT, _node(T.ROOT2, _node(T.ADD, zero, n_node))))
        pq.add_group(
            [CoreRichText(type="remove_zero", args=[zero]), "pow_zero"],
            Step(step3, step4, "add_with_zero", [zero]),
            Step(step4, step5, "pow_zero", [zero]),
        )
        step6 = _eq(x, _node(T.ADD_SUBTRACT, root_of))
        pq.add_group(
            CoreRichText(type="remove_zero", args=[zero]),
            Step(step5, step6, "add_with_zero", [zero]),
        )
        if n.denominator != 1:
            # √(a/b) → √a/√b, and rationalise when the denominator keeps a root
            root_node = _node(
                T.FRACTION,
                _num(isqrt(n.numerator))
                if isqrt(n.numerator) ** 2 == n.numerator
                else _node(T.ROOT2, num(n.numerator)),
                _num(isqrt(n.denominator))
                if isqrt(n.denominator) ** 2 == n.denominator
                else _node(T.ROOT2, num(n.denominator)),
            )
            split = _eq(x, _node(T.ADD_SUBTRACT, root_node))
            pq.add_group("root_frac_each", Step(step6, split, "root_frac_each"))
            step6 = split
            if isqrt(n.denominator) ** 2 != n.denominator:
                simplified = from_sympy(sympy.sqrt(sympy.Rational(n)))
                rationalised = _eq(x, _node(T.ADD_SUBTRACT, simplified))
                pq.add_group("rationalize_roots", Step(step6, rationalised, "rationalize_roots"))
                step6, root_of = rationalised, simplified
            else:
                root_of = root_node
        pair = _node(T.LIST, _eq(x, root_of), _eq(x, _node(T.NEGATIVE, root_of)))
        pq.add_group("quad_separate", Step(step6, pair, "quad_separate_signs", list(_SIGNS)))
        pq.add_group(
            CoreRichText(type="solution_eq_num", args=[two]),
            Step(pair, pair, "solution_eq_num", [two]),
        )
        pq.set_solution(pair)
    # the PQ card was worked out for a square-free n only (x^2 - 2)
    return [formula, pq] if exact or big == 1 or pq_always else [formula]


def _negative_lead_cards(
    node: CoreNode, var: str, a: int, b: int, c: int
) -> list[SolveResult] | None:
    """``a < 0``: every card starts by changing the signs of both sides (e.g. -x^2+5x-6)."""
    positive = _Family(var, -a, -b, -c)
    cards = methods(positive.node, var, Fraction(-a), Fraction(-b), Fraction(-c))
    if not cards:
        return None
    original = _Family(var, a, b, c)
    detail = SolveResult()
    detail.add_group(
        "eq_mul_direct_one",
        Step(original.node, positive.node, "eq_mul_direct_one", [_num(-1)]),
    )
    detail.add_group(
        "mul_with_neg_one",
        Step(original.node, positive.node, "mul_with_neg_one", [_num(-1)]),
    )
    detail.add_group("mul_with_one", Step(original.node, positive.node, "mul_with_one", [_num(1)]))
    detail.add_group(
        "mul_with_neg_one",
        Step(original.node, positive.node, "mul_with_neg_one", [_num(-1)]),
    )
    detail.add_group(
        "mul_with_zero", Step(original.node, positive.node, "mul_with_zero", [_num(0)])
    )
    detail.set_solution(positive.node)
    built: list[SolveResult] = []
    for card in cards[:3]:
        prefixed = SolveResult()
        prefixed.add_group(
            "eq_linear_neg",
            Step(original.node, positive.node, "eq_linear_neg", subresult=detail),
        )
        prefixed.extend(card)
        if card.solution is not None:
            prefixed.set_solution(card.solution)
        built.append(prefixed)
    cards = list(built)
    # The card ``_completing_square`` builds for ``a < 0`` already multiplies both
    # sides by −1 (case ``q_negA``: 8 rows, the second one is that multiply), so
    # it takes no extra prefix row.
    square = _completing_square(original)
    if square is not None:
        cards.append(square)
    cards += _two_real_cards(node, var, a, b, c)
    return cards


def _complex_counting(
    node: CoreNode, var: str, a: int, b: int, c: int | Fraction
) -> list[SolveResult]:
    """«Количество решений» (real and imaginary) and «Вычислите дискриминант»."""
    two, num = _num(2), _num
    counting, evaluate_card = _discriminant_cards(
        node,
        var,
        a,
        b,
        c,
        ("eq_quad_disc_no_solution_simple", "eq_quad_disc_no_solution_var_lt", [num(0)]),
        CoreNode.empty(),
    )
    imaginary_count, _ = _discriminant_cards(
        node,
        var,
        a,
        b,
        c,
        (
            CoreRichText(type="eq_quad_disc_imag_solution_simple", args=[two]),
            "eq_quad_disc_imag_solution_var_lt",
            [num(0), two],
        ),
        two,
    )
    return [counting, imaginary_count, evaluate_card]


def _complex_cards(node: CoreNode, var: str, a: int, b: int, c: int) -> list[SolveResult] | None:
    """Nine cards for a positive-lead quadratic with ``D < 0`` (complex and real twins).

    The app shows the formula, the PQ formula and the completed square twice — once to
    the complex roots and once stopping where the real numbers end — plus the two
    counting cards and the discriminant. The builders are the same ones the real
    families use; the ``real_only`` flag stops them at the impossible root.
    """
    family = _Family(var, a, b, c)
    built = [
        _formula(family),
        _formula(family, real_only=True),
        _pq_formula(family),
        _pq_formula(family, real_only=True),
        _completing_square(family),
        _completing_square(family, real_only=True),
    ]
    cards = [card for card in built if card]
    if len(cards) != 6:
        return None
    return [*cards, *_complex_counting(node, var, a, b, c)]


def _square_prefix(node: CoreNode, var: str, a: int, c: int | Fraction, k: Fraction) -> SolveResult:
    """Rows that bring ``a x² + c = 0`` (as typed) to ``x² = k``."""
    x = CoreNode.variable(var)
    square = _node(T.POWER, x, _num(2))
    moved = _eq(square, _fraction_node(Fraction(k)))
    prefix = SolveResult()
    if a != 1:
        detail = SolveResult()
        detail.add_group(
            CoreRichText(type="eq_linear_div", args=[_num(a)]),
            Step(node, moved, "eq_linear_div", [_num(a)]),
        )
        detail.add_group(
            "divide",
            Step(moved, moved, "div_with_self", [_num(1)]),
            Step(moved, moved, "quotient"),
        )
        detail.set_solution(moved)
        prefix.add_group(
            "divide_both_sides",
            Step(node, moved, "eq_linear_div", [_num(a)], subresult=detail),
        )
        return prefix
    left = node.children[0] if node.type is T.EQUALS else node
    current = node
    if left.type is not T.POWER:
        constant = left.children[1] if len(left.children) == 2 else None
        value = _number_value(constant) if constant is not None else None
        if value is not None and value < 0:  # x² - (-3): the double negative goes first
            flattened = _eq(_poly([(1, 2), (-value, 0)], var), node.children[1])
            prefix.add_group(
                "remove_bracket_short", Step(node, flattened, "neg_neg_arg", [_num(-1)])
            )
            current = flattened
            left = current.children[0]
            constant = left.children[1] if len(left.children) == 2 else None
            value = _number_value(constant) if constant is not None else None
        if value is not None:
            signed = value if left.type is T.ADD else -value
            constant_node = _num(signed) if signed > 0 else _paren(signed)
            balanced = _eq(
                _node(T.SUBTRACT, left, constant_node),
                _node(T.SUBTRACT, current.children[1], constant_node),
            )
            detail = SolveResult()
            detail.add_group(
                "rel_move_right_const_msg", Step(current, balanced, "rel_swap_right_const")
            )
            detail.add_group("remove_opposites", Step(balanced, moved, "sub_with_self_remove_num"))
            detail.set_solution(moved)
            prefix.add_group(
                "rel_move_right_const_msg",
                Step(current, moved, "rel_move_right_const_eq", subresult=detail),
            )
    return prefix


def _square_root_card(
    node: CoreNode,
    var: str,
    a: int,
    c: int | Fraction,
    *,
    prefix: SolveResult | None = None,
    before: CoreNode | None = None,
) -> SolveResult:
    """«Решите путем извлечения квадратного корня» for ``a x² + c = 0``.

    ``prefix``/``before`` let a decimal input supply its own rows (the decimal is
    divided out first) and the ``x² = k`` form they end with.
    """
    k = Fraction(-c, a)
    x = CoreNode.variable(var)
    square = _node(T.POWER, x, _num(2))
    root = from_sympy(sympy.sqrt(sympy.Rational(k)))
    result = SolveResult()
    result.extend(prefix if prefix is not None else _square_prefix(node, var, a, c, k))
    before = before if before is not None else _eq(square, _fraction_node(k))
    plus_minus = _eq(x, _node(T.ADD_SUBTRACT, root))
    sides = _eq(_node(T.ROOT2, square), _node(T.ADD_SUBTRACT, _node(T.ROOT2, _fraction_node(k))))
    take = SolveResult()
    take.add_group("quad_sqrt_sides", Step(before, sides, "quad_sqrt_sides"))
    take.add_group("calculate_short", Step(sides, plus_minus, "root_square"))
    take.set_solution(plus_minus)
    result.add_group("simplify_eq", Step(before, plus_minus, "quad_sqrt_sides", subresult=take))
    listed = _node(T.LIST, _eq(x, _node(T.NEGATIVE, root)), _eq(x, root))
    result.add_group("quad_separate", Step(plus_minus, listed, "quad_separate_signs", list(_SIGNS)))
    result.add_group(
        CoreRichText(type="solution_eq_num", args=[_num(2)]),
        Step(listed, listed, "solution_eq_num", [_num(2)]),
    )
    result.set_solution(listed)
    return result


def _no_real_root_card(
    node: CoreNode,
    var: str,
    a: int,
    c: int | Fraction,
    *,
    prefix: SolveResult | None = None,
    before: CoreNode | None = None,
) -> SolveResult:
    """«Уравнение не имеет действительных корней» for ``x² = k`` with ``k < 0``."""
    k = Fraction(-c, a)
    x = CoreNode.variable(var)
    square = _node(T.POWER, x, _num(2))
    result = SolveResult()
    result.extend(prefix if prefix is not None else _square_prefix(node, var, a, c, k))
    before = before if before is not None else _eq(square, _fraction_node(k))
    no_real = _node(T.ELEMENT_NOT_OF, x, CoreNode.variable("ℝ"))
    result.add_group(
        CoreRichText(type="rel_el_of_zero", args=[x]),
        Step(before, no_real, "rel_terminators_pow_no_sol", [x, _num(0)]),
    )
    result.set_solution(no_real)
    return result


def _after_moving_left_cards(
    node: CoreNode, zero_form: CoreNode, cards: list[SolveResult]
) -> list[SolveResult]:
    """The ``x² + c = 0`` cards for input typed as ``x² = k``: each moves ``k`` left first."""
    built = []
    for card in cards:
        moved = _after_moving_left(node, zero_form, card)
        if moved is not None:
            built.append(moved)
    return built


def _square_cards(node: CoreNode, var: str, a: int, c: int) -> list[SolveResult] | None:
    """``a x² = k`` with ``k`` negative: extraction, formula, PQ and the counting cards."""
    family = _Family(var, a, 0, c)
    cards = [_no_real_root_card(node, var, a, c), _square_root_card(node, var, a, c)]
    rest = [card for card in (_formula(family), _pq_formula(family)) if card]
    if len(rest) != 2:
        return None
    if node.type is T.EQUALS and _number_value(node.children[1]) not in (None, 0):
        rest = _after_moving_left_cards(node, family.node, rest)
    cards.extend(rest)
    cards.extend(_complex_counting(node, var, a, 0, c))
    return cards


def _scaled_square_cards(node: CoreNode, var: str, a: int, c: int) -> list[SolveResult] | None:
    """``a x² = k`` with ``k > 0`` outside the verified perfect-square family."""
    family = _Family(var, a, 0, c)
    cards = [_square_root_card(node, var, a, c)]
    rest = [card for card in (_formula(family), _pq_formula(family)) if card]
    if len(rest) != 2:
        return None
    if node.type is T.EQUALS and _number_value(node.children[1]) not in (None, 0):
        rest = _after_moving_left_cards(node, family.node, rest)
    cards.extend(rest)
    cards.extend(_two_real_cards(node, var, a, 0, c))
    return cards


_DECIMAL_SCALE = Fraction(1, 2)


def _decimal_typed(
    node: CoreNode, var: str, a: int, b: int, typed_c: Fraction, rhs: Fraction
) -> CoreNode:
    """The typed equation with its decimal constant(s) written as fractions."""
    left = _poly([(a, 2), (b, 1), (typed_c, 0)], var)
    right = _fraction_node(rhs) if rhs.denominator != 1 else _num(rhs)
    return _eq(left, right)


def _dec_to_frac_card(before: CoreNode, after: CoreNode, value: Fraction) -> SolveResult:
    """One row turning a decimal into a fraction, with the app's ``5/10 → 1/2`` detail."""
    result = SolveResult()
    magnitude = abs(Fraction(value))
    tenths = _node(T.FRACTION, _num(int(magnitude * 10)), _num(10))
    target = _fraction_node(magnitude)
    detail = SolveResult()
    detail.add_group("convert_expression", Step(_number(magnitude), tenths, "dec_to_frac"))
    factor = gcd(int(magnitude * 10), 10)
    detail.add_group("divide", Step(tenths, target, "frac_reduce_frac_num", [_num(factor)]))
    detail.set_solution(target)
    result.add_group("convert_expression", Step(before, after, "dec_to_frac", subresult=detail))
    return result


def _decimal_square_prefix(
    node: CoreNode, var: str, a: int, c: Fraction, rhs: Fraction
) -> tuple[SolveResult, CoreNode]:
    """Rows that bring a decimal ``a x² + c = rhs`` to ``x² = k``, and that form."""
    x = CoreNode.variable(var)
    square = _node(T.POWER, x, _num(2))
    k = Fraction(-c, a)
    before = _eq(square, _fraction_node(k))
    prefix = SolveResult()
    typed_c = c + rhs
    if typed_c == 0:
        # ``x² = 0.5``: the decimal on the right becomes a fraction, then divide by ``a``
        current = node
        if rhs.denominator != 1:
            fraction_typed = _eq(_mono(a, 2, var), _fraction_node(rhs))
            prefix.extend(_dec_to_frac_card(node, fraction_typed, rhs))
            current = fraction_typed
        if a != 1:
            prefix.add_group("divide_both_sides", Step(current, before, "eq_linear_div", [_num(a)]))
        return prefix, before
    # ``x² − 0.5 = 0``: dividing both sides by 0.5 clears the decimal (×2)
    scaled = _eq(_poly([(2 * a, 2), (2 * typed_c, 0)], var), _num(2 * rhs))
    prefix.add_group(
        "divide_both_sides",
        Step(node, scaled, "eq_linear_div", [_number(_DECIMAL_SCALE)]),
    )
    left = _mono(2 * a, 2, var)
    combined = _eq(left, _num(2 * rhs - 2 * typed_c))
    if 2 * rhs == 0:
        prefix.add_group(
            "rel_move_right_const_msg", Step(scaled, combined, "rel_move_right_const_eq")
        )
    else:
        opened = _eq(
            left,
            _node(
                T.ADD if typed_c < 0 else T.SUBTRACT,
                _num(2 * rhs),
                _num(abs(2 * typed_c)),
            ),
        )
        prefix.add_group(
            "rel_move_right_const_msg", Step(scaled, opened, "rel_move_right_const_eq")
        )
        prefix.add_group(
            "calculate_short",
            Step(opened, combined, "add" if typed_c < 0 else "sub"),
        )
    prefix.add_group("divide_both_sides", Step(combined, before, "eq_linear_div", [_num(2 * a)]))
    return prefix, before


def _prefixed(cards: list[SolveResult], prefix: SolveResult) -> list[SolveResult]:
    """The same cards, each starting with ``prefix`` (the typed equation's own rows)."""
    built: list[SolveResult] = []
    for card in cards:
        moved = SolveResult()
        moved.extend(prefix)
        moved.extend(card)
        if card.solution is not None:
            moved.solution = card.solution
        if card.header is not None:
            moved.header = card.header
        built.append(moved)
    return built


def _decimal_integer_formula(
    node: CoreNode,
    var: str,
    a: int,
    b: int,
    c: Fraction,
    rhs: Fraction,
    real_only: bool = False,
) -> SolveResult | None:
    """Roots formula for a decimal input: divide by 0.5, then the integer card.

    The app scales ``x² − x − 0.5 = 0`` to ``2x² − 2x − 1 = 0`` (dividing both
    sides by 0.5) and substitutes the scaled coefficients in the formula.
    """
    scaled_typed = _eq(_poly([(2 * a, 2), (2 * b, 1), (2 * (c + rhs), 0)], var), _num(2 * rhs))
    result = SolveResult()
    result.add_group(
        "divide_both_sides",
        Step(node, scaled_typed, "eq_linear_div", [_number(_DECIMAL_SCALE)]),
    )
    if 2 * rhs != 0:
        zero = _eq(_poly([(2 * a, 2), (2 * b, 1), (2 * c, 0)], var), _num(0))
        result.extend(
            _right_const_prefix(
                scaled_typed,
                zero,
                var,
                2 * a,
                2 * b,
                2 * c,
                Fraction(2 * rhs),
            )
        )
    body = _formula(_Family(var, 2 * a, 2 * b, 2 * c), real_only=real_only)
    if body is None:
        return None
    result.extend(body)
    result.solution = body.solution
    return result


def _decimal_pq(
    node: CoreNode, var: str, a: int, b: int, c: Fraction, rhs: Fraction, real_only: bool = False
) -> SolveResult | None:
    """PQ card for a decimal input: ``0.5`` → ``1/2``, then the fraction PQ rows."""
    typed_c = c + rhs
    decimal = typed_c if typed_c.denominator != 1 else rhs
    fraction_typed = _decimal_typed(node, var, a, b, typed_c, rhs)
    zero_form = _eq(_poly([(a, 2), (b, 1), (c, 0)], var), _num(0))
    result = _dec_to_frac_card(node, fraction_typed, decimal)
    if rhs != 0:
        result.extend(_right_const_prefix(fraction_typed, zero_form, var, a, b, c, rhs))
    family = _Family(var, a, b, c)
    family.node = zero_form
    body = _pq_nonexact(family, real_only=real_only)
    if body is None:
        return None
    if family.d < 0 and not real_only:
        _replace_complex_answer(body, var, a, b, family.d)
    result.extend(body)
    result.solution = body.solution
    return result


def _replace_complex_answer(card: SolveResult, var: str, a: int, b: int, d: int) -> None:
    """Write the two complex roots as ``-b/2a ± (√−D/2a)i``, as the app does.

    ``_root_nodes`` writes ``i√…/2``; The app keeps the fraction first and the
    unit after it, and the answer comparison is textual for the imaginary unit.
    """
    x = CoreNode.variable(var)
    imaginary = _imaginary(_surd(Fraction(-d, 4 * a * a)))
    real = _fraction_node(Fraction(-b, 2 * a))
    answer = _node(
        T.LIST,
        _eq(x, _node(T.ADD, real, imaginary)),
        _eq(x, _node(T.SUBTRACT, real, imaginary)),
    )
    for _headers, subs in reversed(card._steps):
        if subs:
            subs[-1].right = answer
            break
    card.solution = answer


def _decimal_square_pq(
    node: CoreNode, var: str, a: int, c: Fraction, rhs: Fraction
) -> SolveResult | None:
    """PQ card for a decimal ``a x² + c = rhs``: fraction first, then ``x² = k`` rows.

    The app divides by ``a`` on the card itself (``3x² = 0.5`` → ``x² = 1/6``) and
    then uses the PQ rows of ``x² = k`` with a fraction constant.
    """
    typed_c = c + rhs
    decimal = typed_c if typed_c.denominator != 1 else rhs
    fraction_typed = _decimal_typed(node, var, a, 0, typed_c, rhs)
    zero_form = _eq(_poly([(a, 2), (c, 0)], var), _num(0))
    result = _dec_to_frac_card(node, fraction_typed, decimal)
    if rhs != 0:
        result.extend(_right_const_prefix(fraction_typed, zero_form, var, a, 0, c, rhs))
    constant = Fraction(c, a)
    base = _eq(_poly([(1, 2), (constant, 0)], var), _num(0))
    if a != 1:
        result.add_group("divide_both_sides", Step(zero_form, base, "eq_linear_div", [_num(a)]))
    built = _pure_square_formulas(base, var, constant, pq_always=True)
    body = built[1] if len(built) > 1 else None
    if body is None:
        return None
    result.extend(body)
    result.solution = body.solution
    return result


def _decimal_cs(
    node: CoreNode, var: str, a: int, b: int, c: Fraction, rhs: Fraction, real_only: bool = False
) -> SolveResult | None:
    """Completing the square for a decimal input: ``0.5`` → ``1/2``, then the square rows."""
    typed_c = c + rhs
    decimal = typed_c if typed_c.denominator != 1 else rhs
    fraction_typed = _decimal_typed(node, var, a, b, typed_c, rhs)
    result = _dec_to_frac_card(node, fraction_typed, decimal)
    family = _Family(var, a, b, c, typed_rhs=rhs)
    family.node = fraction_typed
    body = _completing_square(family, real_only=real_only)
    if body is None:
        return None
    result.extend(body)
    result.solution = body.solution
    return result


def _counting_cards(node: CoreNode, var: str, a: int, b: int, c: Fraction) -> list[SolveResult]:
    """«Количество решений» and «Вычислите дискриминант» for a decimal input."""
    d = b * b - 4 * a * c
    two, one = _num(2), _num(1)
    if d > 0:
        verdict = (
            CoreRichText(type="eq_quad_disc_solution_plural_simple", args=[two]),
            "eq_quad_disc_solution_all_gt",
            [_num(0), two],
        )
        return list(_discriminant_cards(node, var, a, b, c, verdict, two))
    if d == 0:
        verdict = (
            CoreRichText(type="eq_quad_disc_solution_simple", args=[one]),
            "eq_quad_disc_solution_all_eq",
            [_num(0), one],
        )
        return list(_discriminant_cards(node, var, a, b, c, verdict, one))
    return _complex_counting(node, var, a, b, c)


def _real_domain_end(card: SolveResult, var: str) -> SolveResult:
    """Finish a real-domain twin card on «x ∉ ℝ», as the app's twin rows do."""
    no_real = _node(T.ELEMENT_NOT_OF, CoreNode.variable(var), CoreNode.variable("ℝ"))
    for _headers, subs in reversed(card._steps):
        if subs:
            subs[-1].right = no_real
            break
    card.solution = no_real
    return card


def _decimal_cards(
    node: CoreNode, var: str, a: int, b: int, c: Fraction, rhs: Fraction
) -> list[SolveResult] | None:
    """The cards the app shows for a quadratic with one-decimal coefficients.

    A decimal on the left is cleared by dividing both sides by 0.5 (the formula
    card) or kept as a fraction (PQ, completing the square); a decimal on the
    right is turned into a fraction first and moved left. The bodies are the
    integer and fraction builders: only the prefix rows are new.
    """
    typed_c = c + rhs
    d = b * b - 4 * a * c
    cards: list[SolveResult] = []
    if b == 0:
        prefix, before = _decimal_square_prefix(node, var, a, c, rhs)
        if d < 0:
            # ``x² + 0.5 = 0``: «нет действительных корней» comes first, as for integers
            cards.append(_no_real_root_card(node, var, a, c, prefix=prefix, before=before))
        root_card = _square_root_card(node, var, a, c, prefix=prefix, before=before)
        root_card.header = "solve_using_sqrt"
        cards.append(root_card)
        fraction_typed = _decimal_typed(node, var, a, b, typed_c, rhs)
        zero_form = _eq(_poly([(a, 2), (b, 1), (c, 0)], var), _num(0))
        if typed_c == 0:
            # ``x² = 0.5``: the formula keeps the fraction; the PQ card divides by ``a``
            start = _dec_to_frac_card(node, fraction_typed, rhs)
            start.add_group(
                "rel_move_left_const_msg",
                Step(fraction_typed, zero_form, "rel_move_left_const"),
            )
            built: list[SolveResult] = []
            if a == 1:
                built = _pure_square_formulas(zero_form, var, c, pq_always=True)[:1]
            else:
                fraction_formula = _formula(_Family(var, a, 0, c))
                built = [fraction_formula] if fraction_formula is not None else []
            cards.extend(_prefixed(built, start))
        else:
            square_formula = _decimal_integer_formula(node, var, a, 0, c, rhs)
            if square_formula is not None:
                cards.append(square_formula)
        square_pq = (
            _decimal_square_pq(node, var, a, c, rhs)
            if c < 0
            else _decimal_pq(node, var, a, 0, c, rhs)
        )
        if square_pq is not None:
            cards.append(square_pq)
    else:
        # The app shows the real-domain twin cards first, then the complex ones
        for real_only in (True, False) if d < 0 else (False,):
            formula_card = _decimal_integer_formula(node, var, a, b, c, rhs, real_only=real_only)
            if formula_card is not None:
                cards.append(_real_domain_end(formula_card, var) if real_only else formula_card)
            pq_card = _decimal_pq(node, var, a, b, c, rhs, real_only=real_only)
            if pq_card is not None:
                cards.append(_real_domain_end(pq_card, var) if real_only else pq_card)
            cs_card = _decimal_cs(node, var, a, b, c, rhs, real_only=real_only)
            if cs_card is not None:
                cards.append(_real_domain_end(cs_card, var) if real_only else cs_card)
    cards.extend(_counting_cards(node, var, a, b, c))
    return cards or None


def _card_header(card: SolveResult) -> str | None:
    """The app's method header for a verified card, by the rows it contains."""
    keys = [sub.key for _, subs in card._steps for sub in subs]
    if any(
        key.startswith("eq_quad_disc_solution")
        or key.startswith("eq_quad_disc_no_solution")
        or key.startswith("eq_quad_disc_imag_solution")
        for key in keys
    ):
        if "eq_quad_disc_solution_imag" in keys or "eq_quad_disc_imag_solution_var_lt" in keys:
            return "find_num_of_imag_solutions"
        if "eq_quad_disc_solution_all_gt" in keys:
            return "find_num_of_solutions"
        return "find_num_of_real_solutions"
    if "quad_formula_abc" in keys:
        return "eq_quad_formula"
    if "quad_formula_pq" in keys:
        return "eq_quad_pq"
    if any(
        key in keys for key in ("conics_complete_square_both", "conics_add_other_lr", "eq_add_exp")
    ):
        return "eq_quad_cs"
    if "eq_quad_eval_disc_sub" in keys:
        return "evaluate"
    return card.header


def methods(
    node: CoreNode, var: str, a: Fraction, b: Fraction, c: Fraction
) -> list[SolveResult] | None:
    """The app's methods for the verified family, with the verified card headers."""
    cards = _methods_impl(node, var, a, b, c)
    if cards:
        for card in cards:
            header = _card_header(card)
            if header is not None:
                card.header = header
    return cards


def _right_const_prefix(
    node: CoreNode,
    zero: CoreNode,
    var: str,
    a: int,
    b: int,
    c: int | Fraction,
    rhs: Fraction,
) -> SolveResult:
    """Rows that bring the typed equation with a right-hand constant to ``… = 0``."""
    result = SolveResult()
    typed_c = c + rhs  # ``c`` is already the constant of the standard form
    if typed_c == rhs:
        # x² + 4x + 3 = 3: the constant cancels on both sides
        result.add_group("rel_del_term", Step(node, zero, "eq_del_opp"))
        return result
    combined = _eq(_poly([(a, 2), (b, 1), (typed_c, 0), (-rhs, 0)], var), _num(0))
    balanced = _eq(
        _node(T.SUBTRACT, node.children[0], node.children[1]),
        _node(T.SUBTRACT, node.children[1], node.children[1]),
    )
    detail = SolveResult()
    detail.add_group("rel_move_left_const_msg", Step(node, balanced, "rel_swap_left_const"))
    detail.add_group("sub_with_self_del", Step(balanced, combined, "sub_with_self_num", [_num(0)]))
    detail.set_solution(combined)
    result.add_group(
        "rel_move_left_const_msg",
        Step(node, combined, "rel_move_left_const", subresult=detail),
    )
    if typed_c == 0:
        # x² − 4x = 5: there is no typed constant to combine with the moved one
        return result
    result.add_group(
        "calculate_short",
        Step(
            combined,
            zero,
            "calc_sum" if rhs < 0 else "calc_diff",
            [],
            subresult=_detail(combined.children[0], zero.children[0]),
        ),
    )
    return result


def _moved_cards(
    node: CoreNode, var: str, a: int, b: int, c: int, rhs: Fraction
) -> list[SolveResult] | None:
    """The cards for an equation whose constant stands on the right.

    The app first moves it left (``x² − x − 6 = 1`` → ``x² − x − 7 = 0``) and then
    shows the ordinary cards; the counting cards describe the standard form themselves.
    """
    zero = _eq(_poly([(a, 2), (b, 1), (c, 0)], var), _num(0))
    cards = _cards(zero, var, a, b, c, source=node)
    if not cards:
        return None
    prefix = _right_const_prefix(node, zero, var, a, b, c, rhs)
    built: list[SolveResult] = []
    for card in cards:
        header = _card_header(card)
        if (
            header
            in {
                "find_num_of_solutions",
                "find_num_of_imag_solutions",
                "find_num_of_real_solutions",
                "evaluate",
            }
            or header == "eq_quad_cs"
        ):
            built.append(card)  # these cards already start from the standard form
            continue
        moved = SolveResult()
        moved.extend(prefix)
        moved.extend(card)
        if card.solution is not None:
            moved.solution = card.solution
        if card.header is not None:
            moved.header = card.header
        built.append(moved)
    return built


def _methods_impl(
    node: CoreNode, var: str, a: Fraction, b: Fraction, c: Fraction
) -> list[SolveResult] | None:
    """The app's methods for the verified family, or ``None`` to use the general solver."""
    if a.denominator != 1 or b.denominator != 1:
        return None  # a decimal lead or linear coefficient is outside the cards
    if any(value.denominator not in (1, 2) for value in (a, b, c)):
        return None
    ia, ib = int(a), int(b)
    if ia == 0:
        return None
    rhs = _number_value(node.children[1]) if node.type is T.EQUALS else None
    if rhs is not None and rhs.denominator not in (1, 2):
        return None
    if c.denominator != 1 or (rhs is not None and rhs.denominator != 1):
        # one-decimal coefficients: 0.5, 1.5, 6.5 … (see ``_decimal_cards``)
        if rhs is None or c == 0:
            return None
        return _decimal_cards(node, var, ia, ib, c, rhs)
    ic = int(c)
    if ib != 0 and rhs is not None and rhs != 0:
        return _moved_cards(node, var, ia, ib, ic, rhs)
    return _cards(node, var, ia, ib, ic)


def _cards(
    node: CoreNode, var: str, ia: int, ib: int, ic: int, source: CoreNode | None = None
) -> list[SolveResult] | None:
    """The card list for the standard form ``a x² + b x + c = 0``."""
    source = node if source is None else source
    d = ib * ib - 4 * ia * ic
    if ia > 1 and ib == 0 and ic < 0 and ic % ia == 0 and node.children[1].type is T.CONSTANT:
        return _scaled_cards(node, var, ia, -ic // ia)
    if ib != 0 and ic == 0 and ia > 0:
        return _x_squared_minus_x(node, var, ia, ib)
    if ia == -1 and ib == 0 and ic > 0 and isqrt(ic) ** 2 == ic and isqrt(ic) >= 2:
        if _number_value(node.children[1]) == 0:
            return _negative_lead_square(node, var, isqrt(ic))
        # −x² + 1 = −3: the cards are built for −x² + 4 = 0, so the constant moves left first
        zero_form = _Family(var, ia, ib, ic).node
        return _after_moving_left_cards(
            node, zero_form, _negative_lead_square(zero_form, var, isqrt(ic))
        )
    if d == 0 and ia == 1 and (double := _double_root(node, var, ib, ic)) is not None:
        return double
    if d < 0 and ia == 1 and (negative := _negative_discriminant(node, var, ib, ic)) is not None:
        return negative
    if ib == 0 and ic < 0 and ia > 1:
        adjusted = _scaled_square_cards(node, var, ia, ic)
        if adjusted is not None:
            return adjusted
    if ib == 0 and ic < 0 and ia == 1:
        direct = node.children[1].type is T.CONSTANT and node.children[1].value != "0"
        zero_form = _Family(var, ia, ib, ic).node
        cards: list[SolveResult] = [_extraction(node, var, ic, moved_already=direct)]
        others: list[SolveResult | None]
        if isqrt(-ic) ** 2 == -ic:
            others = [_difference_of_squares(_Family(var, ia, ib, ic))]
            others.extend(_pure_square_formulas(zero_form, var, ic))
        else:
            others = [*_pure_square_formulas(node, var, ic)]
        for card in others:
            if card is None:
                continue
            moved = _after_moving_left(node, zero_form, card) if direct else card
            if moved is not None:
                cards.append(moved)
        cards.extend(_two_real_cards(source, var, ia, ib, ic))
        return cards
    if ib == 0 and ic > 0:
        return _square_cards(node, var, ia, ic)
    if d < 0 and ia > 0:
        complex_cards = _complex_cards(source, var, ia, ib, ic)
        if complex_cards is not None:
            return complex_cards
    if d < 0 and ia != 0:
        return _complex_general(source, var, ia, ib, ic)
    if ia < 0 and ib != 0 and ic != 0 and d > 0 and isqrt(d) ** 2 == d:
        return _negative_lead_cards(node, var, ia, ib, ic)
    if ib != 0 and ic != 0 and d > 0 and isqrt(d) ** 2 != d:
        # irrational real roots: the formula cards carry the surd and the counting cards
        family = _Family(var, ia, ib, ic)
        irrational: list[SolveResult] = [
            m
            for m in (_formula(family), _pq_formula(family), _completing_square(family))
            if m is not None
        ]
        if len(irrational) != 3:
            return None
        return [*irrational, *_two_real_cards(source, var, ia, ib, ic)]
    if ia == 0 or ib == 0 or ic == 0 or d <= 0 or isqrt(d) ** 2 != d:
        return None
    family = _Family(var, ia, ib, ic)
    primary: list[SolveResult] = [
        m for m in (_factoring(family), _formula(family)) if m is not None
    ]
    if not primary:  # outside the verified sign families the general solver explains it
        return None
    cards = list(primary)
    for card in (
        _pq_formula(family),
        _pq_scaled(family),
        _pq_scaled_negative(family),
        _completing_square(family),
    ):
        if card is not None:
            cards.append(card)
    if ia > 0:  # The app shows the two discriminant cards on the verified positive families
        cards += _two_real_cards(source, var, ia, ib, ic)
    return cards or None
