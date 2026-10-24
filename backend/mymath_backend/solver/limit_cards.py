"""Textbook-first cards for limits.

The first card a student sees must be the method a textbook teaches, with its
formula and stages: factor and cancel a ``0/0`` fraction, divide by the highest
power for ``∞/∞``, the first/second remarkable limits, the conjugate of a root
difference, the sign of a one-sided limit, or the reason a limit does not
exist.  L'Hôpital is only ever an alternative card: the caller appends it after
the textbook card.

The module builds steps only; it never decides the answer on its own.  Every
card ends with the value computed by :mod:`sympy` through the real limit.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .base import SolveResult, Step
from .sympy_bridge import from_sympy, to_sympy

_LIMITS = (T.LIMIT, T.LIMIT_LEFT, T.LIMIT_RIGHT)


def _node(kind: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(kind, *children)


def _num(value: int) -> CoreNode:
    return CoreNode.constant(str(value))


def _substitute(node: CoreNode, variable: str, value: CoreNode) -> CoreNode:
    """Replace the variable in a node tree (display only)."""
    if node.type is T.VARIABLE and node.value == variable:
        return value
    if not node.children:
        return node
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[_substitute(child, variable, value) for child in node.children],
    )


def _limit_node(node_type: T, point: CoreNode, expression: CoreNode) -> CoreNode:
    return _node(node_type, point, expression)


def _law_first() -> CoreNode:
    """``lim_{u→0} sin u / u = 1``."""
    u = CoreNode.variable("u")
    ratio = _node(T.FRACTION, _node(T.SIN, u), u)
    return _node(T.EQUALS, _limit_node(T.LIMIT, _num(0), ratio), _num(1))


def _law_second() -> CoreNode:
    """``lim_{u→∞} (1 + 1/u)^u = e``."""
    u = CoreNode.variable("u")
    base = _node(T.ADD, _num(1), _node(T.FRACTION, _num(1), u))
    return _node(
        T.EQUALS,
        _limit_node(T.LIMIT, CoreNode.constant("∞"), _node(T.POWER, base, u)),
        CoreNode.constant("e"),
    )


def _stage(
    card: SolveResult, key: str, left: CoreNode | None, right: CoreNode | None, *args: CoreNode
) -> None:
    card.add_group(key, Step(left, right, key, list(args)))


def _stage_with(
    card: SolveResult,
    key: str,
    extra: list[str],
    left: CoreNode | None,
    right: CoreNode | None,
    *args: CoreNode,
) -> None:
    """A stage that also carries its own card-title key as a header."""
    card.add_group([key, *extra], Step(left, right, key, list(args)))


def _answer(value: sympy.Expr) -> CoreNode:
    return from_sympy(sympy.simplify(value))


def limit_variables(node: CoreNode, variables: list[str]) -> list[str]:
    """Free variables of the limit: sum indices are bound and do not count."""
    bound = {
        n.children[0].value
        for n in node.walk()
        if n.type is T.SIGMA_DEFINITE
        and len(n.children) == 4
        and n.children[0].type is T.VARIABLE
        and n.children[0].value
    }
    return [name for name in variables if name not in bound]


def limit_variable(node: CoreNode, variables: list[str]) -> str:
    """The variable the limit runs over; a sum index is a bound dummy.

    ``lim_{n→∞} Σ_{k=1}^{n} …`` mentions both ``k`` and ``n``, but only ``n``
    is free: the sum index must not be mistaken for the limit variable.
    """
    free = limit_variables(node, variables)
    return free[0] if free else (variables[0] if variables else "x")


def expand_sums(node: CoreNode, keep: str | None = None) -> CoreNode:
    """Replace every finite sum whose index is not the limit variable by its closed form.

    ``Σ_{k=1}^{n} 1/4^k`` is a formula in ``n``; the bridge cannot translate a
    ``SIGMA_DEFINITE`` node, so the closed form is what the limit is taken of.
    """
    if node.type is T.SIGMA_DEFINITE and len(node.children) == 4:
        index, lower, upper, term = node.children
        if index.type is T.VARIABLE and index.value and index.value != keep:
            symbol = sympy.Symbol(index.value)
            try:
                closed = sympy.summation(
                    to_sympy(expand_sums(term, keep)),
                    (
                        symbol,
                        to_sympy(expand_sums(lower, keep)),
                        to_sympy(expand_sums(upper, keep)),
                    ),
                )
            except (TypeError, ValueError, NotImplementedError):
                return node
            if not closed.has(sympy.Sum) and not closed.has(symbol):
                try:
                    closed = sympy.expand(sympy.simplify(closed))
                except (TypeError, ValueError):
                    closed = sympy.simplify(closed)
                return from_sympy(closed)
    if not node.children:
        return node
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[expand_sums(child, keep) for child in node.children],
        color=node.color,
        crossed=node.crossed,
    )


def _cards_result(card: SolveResult, value: CoreNode) -> SolveResult:
    card.set_solution(value)
    return card


# ── detection helpers ─────────────────────────────────────────────────


def _fraction_parts(expression: CoreNode, value: sympy.Expr) -> tuple[sympy.Expr, sympy.Expr]:
    """Numerator and denominator, keeping the written fraction when there is one."""
    if expression.type in (T.FRACTION, T.DIVIDE) and len(expression.children) == 2:
        return to_sympy(expression.children[0]), to_sympy(expression.children[1])
    numerator, denominator = sympy.fraction(sympy.together(value))
    return cast(sympy.Expr, numerator), cast(sympy.Expr, denominator)


def _constant_ratio(expression: sympy.Expr, symbol: sympy.Symbol) -> sympy.Expr | None:
    """``expression / symbol`` as a nonzero constant, else ``None``."""
    if not expression.has(symbol):
        return None
    try:
        ratio = sympy.simplify(expression / symbol)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if ratio.has(symbol) or ratio.is_number is not True or ratio.is_zero is not False:
        return None
    return ratio


def _abs_fraction(value: sympy.Expr, symbol: sympy.Symbol) -> bool:
    """``|x| / x``: the shape whose sign must be opened by hand."""
    numerator, denominator = sympy.fraction(sympy.together(value))
    return (
        numerator.func is sympy.Abs
        and len(numerator.args) == 1
        and numerator.args[0] == symbol
        and denominator == symbol
    )


def _has_sqrt(expression: sympy.Expr) -> bool:
    """Is there a square root? SymPy stores ``√u`` as ``u**(1/2)``."""
    return any(
        isinstance(atom, sympy.Pow) and atom.exp == sympy.Rational(1, 2)
        for atom in expression.atoms(sympy.Pow)
    )


def _still_indeterminate(value: sympy.Expr, symbol: sympy.Symbol, point: sympy.Expr) -> bool:
    """Does the expression still give 0/0 at a finite point?"""
    if point.is_finite is not True:
        return False
    numerator, denominator = sympy.fraction(sympy.together(value))
    if denominator == 1:
        return False
    try:
        return bool(numerator.subs(symbol, point) == 0 and denominator.subs(symbol, point) == 0)
    except (TypeError, ValueError):
        return False


def _sqrt_conjugate(expression: sympy.Expr) -> sympy.Expr | None:
    """Flip the sign of the terms that carry no root: ``√(x+1) − 1`` → ``√(x+1) + 1``.

    A difference of two roots (``√A − √B``) is handled as well: its conjugate is
    ``√A + √B``, because ``(√A)² − (√B)²`` is free of roots.
    """
    terms = sympy.Add.make_args(expression)
    roots = [term for term in terms if _has_sqrt(term)]
    plain = [term for term in terms if not _has_sqrt(term)]
    if len(roots) == 1 and plain:
        conjugate = sympy.Add(*roots) - sympy.Add(*plain)
        return None if conjugate == expression else conjugate
    if len(roots) == 2 and not plain:
        conjugate = roots[0] - roots[1]
        return None if conjugate == expression else conjugate
    return None


def _not_real(value: sympy.Expr) -> bool:
    """Is the value complex or undefined (an even root outside its domain)?"""
    return value is sympy.nan or value.has(sympy.I)


def _domain_side(value: sympy.Expr, symbol: sympy.Symbol, point: sympy.Expr) -> str:
    """``+``/``-`` when only one side of the point is real, else ``""``.

    ``√x`` at ``0`` is defined on the right only: for such a problem the
    textbook reads the two-sided limit as the limit over the domain.
    """
    if point.is_finite is not True:
        return ""
    try:
        left = sympy.limit(value, symbol, point, "-")
        right = sympy.limit(value, symbol, point, "+")
    except (TypeError, ValueError, NotImplementedError):
        return ""
    if _not_real(left) and not _not_real(right):
        return "+"
    if _not_real(right) and not _not_real(left):
        return "-"
    return ""


def _is_accumulation(value: sympy.Expr) -> bool:
    return isinstance(value, sympy.AccumBounds) or value is sympy.nan


def _limit_value(
    node_type: T, value: sympy.Expr, symbol: sympy.Symbol, point: sympy.Expr
) -> sympy.Expr | None:
    try:
        if node_type is T.LIMIT_LEFT:
            return sympy.limit(value, symbol, point, "-")
        if node_type in (T.LIMIT, T.LIMIT_RIGHT):
            return sympy.limit(value, symbol, point, _domain_side(value, symbol, point) or "+")
    except NotImplementedError:
        return _bounded_zero(value, symbol, point)
    except (TypeError, ValueError):
        return None
    return None


def _divided_node(
    numerator: sympy.Expr, denominator: sympy.Expr, symbol: sympy.Symbol, power: int
) -> CoreNode:
    """Show the fraction after dividing both parts by ``symbol ** power``."""
    top = sympy.expand(numerator / symbol**power)
    bottom = sympy.expand(denominator / symbol**power)
    if bottom == 1:
        return from_sympy(top)
    return _node(T.FRACTION, from_sympy(top), from_sympy(bottom))


def _power_node(variable: str, power: int) -> CoreNode:
    """``x`` for the first power, ``x^n`` otherwise."""
    base = CoreNode.variable(variable)
    return base if power == 1 else _node(T.POWER, base, _num(power))


# ── L'Hôpital as the alternative card ─────────────────────────────────


def lhopital_card(node: CoreNode, answer: CoreNode) -> SolveResult:
    """The same limit by L'Hôpital: named, but never the first card."""
    card = SolveResult(header="limit_lhopital_msg")
    titles: list[str | CoreRichText] = ["limit_lhopital_long", "evaluate_using_lhopital"]
    if node.type in _LIMITS and len(node.children) == 2:
        point, expression = node.children
        try:
            numerator, denominator = sympy.fraction(to_sympy(expression))
        except (TypeError, ValueError):
            numerator = denominator = sympy.Integer(1)
        if denominator != 1:
            titles.insert(
                0,
                CoreRichText(
                    type="limit_solve_pl_arg",
                    args=[
                        _node(node.type, point, from_sympy(numerator)),
                        _node(node.type, point, from_sympy(denominator)),
                    ],
                ),
            )
    card.add_group(titles, Step(node, None, "limit_lhopital_long"))
    _stage(card, "lesson_calc_limit_result", node, answer, answer)
    return _cards_result(card, answer)


# ── 0/0 rational: factor and cancel ───────────────────────────────────


def _factor_card(
    node: CoreNode,
    point_node: CoreNode,
    expression: CoreNode,
    numerator: sympy.Expr,
    denominator: sympy.Expr,
    reduced: sympy.Expr,
    variable: str,
    symbol: sympy.Symbol,
    point: sympy.Expr,
    answer: sympy.Expr,
) -> SolveResult:
    card = SolveResult(header="lesson_calc_header_factor")
    _stage_with(card, "lesson_calc_uncertainty_00", ["evaluate_using_transformations"], node, None)
    _stage(
        card,
        "lesson_calc_domain",
        None,
        _node(T.NOT_EQUALS, from_sympy(denominator), _num(0)),
    )
    factored = _node(
        T.FRACTION, from_sympy(sympy.factor(numerator)), from_sympy(sympy.factor(denominator))
    )
    _stage(card, "lesson_calc_factor", expression, factored)
    common = sympy.gcd(numerator, denominator)
    _stage(
        card,
        "lesson_calc_cancel_factor",
        factored,
        from_sympy(reduced),
        from_sympy(sympy.factor(common)),
        _node(T.NOT_EQUALS, CoreNode.variable(variable), point_node),
    )
    reduced_node = from_sympy(reduced)
    substituted = _substitute(reduced_node, variable, point_node)
    _stage(
        card,
        "lesson_calc_substitute",
        _limit_node(node.type, point_node, reduced_node),
        substituted,
    )
    answer_node = _answer(answer)
    _stage(card, "lesson_calc_simplify", substituted, answer_node)
    return _cards_result(card, answer_node)


# ── ∞/∞ rational and sequences in n ───────────────────────────────────


def _inf_card(
    node: CoreNode,
    point_node: CoreNode,
    expression: CoreNode,
    numerator: sympy.Expr,
    denominator: sympy.Expr,
    variable: str,
    symbol: sympy.Symbol,
    answer: sympy.Expr,
) -> SolveResult:
    card = SolveResult(header="lesson_calc_header_inf")
    _stage_with(card, "lesson_calc_uncertainty_inf", ["evaluate_using_transformations"], node, None)
    degree_top = sympy.degree(numerator, symbol)
    degree_bottom = sympy.degree(denominator, symbol)
    power = max(degree_top, degree_bottom)
    divided = _divided_node(numerator, denominator, symbol, power)
    _stage(
        card,
        "lesson_calc_divide_highest",
        expression,
        divided,
        _power_node(variable, power),
    )
    _stage(card, "lesson_calc_inf_terms_zero", divided, None)
    answer_node = _answer(answer)
    if degree_top < degree_bottom:
        _stage_with(card, "lesson_calc_inf_deg_lt", ["limit_poly_msg"], divided, answer_node)
    elif degree_top == degree_bottom:
        _stage_with(
            card,
            "lesson_calc_inf_deg_eq",
            ["limit_poly_msg"],
            divided,
            answer_node,
            from_sympy(
                sympy.simplify(
                    sympy.Poly(numerator, symbol).LC() / sympy.Poly(denominator, symbol).LC()
                )
            ),
        )
    else:
        _stage_with(card, "lesson_calc_inf_deg_gt", ["limit_poly_msg"], divided, answer_node)
    return _cards_result(card, answer_node)


# ── n^(1/n) ───────────────────────────────────────────────────────────


def _sequence_root_card(
    node: CoreNode, symbol: sympy.Symbol, answer: sympy.Expr
) -> SolveResult | None:
    value = to_sympy(node.children[1])
    if not (isinstance(value, sympy.Pow) and value.base == symbol and value.exp.has(symbol)):
        return None
    if sympy.simplify(value.exp * symbol) != 1:
        return None
    card = SolveResult(header="lesson_calc_header_sequence_root")
    _stage(card, "lesson_calc_uncertainty_inf_0", node, None)
    _stage(card, "lesson_calc_sequence_root", node, None)
    rewrite = from_sympy(sympy.exp(sympy.log(symbol) / symbol))
    _stage(card, "limit_change_var", node, rewrite)
    _stage(card, "lesson_calc_log_over_n", rewrite, None)
    answer_node = _answer(answer)
    _stage(card, "lesson_calc_limit_result", rewrite, answer_node, answer_node)
    return _cards_result(card, answer_node)


# ── first remarkable limit / equivalent infinitesimals ────────────────


def _remarkable_rewrite(kind: str, offset: sympy.Expr, coefficient: sympy.Expr) -> CoreNode:
    u = from_sympy(offset)
    if kind == "sin":
        inner, factor = _node(T.FRACTION, _node(T.SIN, u), u), coefficient
    elif kind == "tan":
        inner, factor = _node(T.FRACTION, _node(T.TAN, u), u), coefficient
    elif kind == "asin":
        inner, factor = _node(T.FRACTION, _node(T.ASIN, u), u), coefficient
    elif kind == "ln":
        inner = _node(T.FRACTION, _node(T.LN, _node(T.ADD, _num(1), u)), u)
        factor = coefficient
    elif kind == "exp":
        inner = _node(T.FRACTION, _node(T.SUBTRACT, _node(T.EXP, u), _num(1)), u)
        factor = coefficient
    else:  # 1 − cos u over u²
        inner = _node(
            T.FRACTION,
            _node(T.SUBTRACT, _num(1), _node(T.COS, u)),
            _node(T.POWER, u, _num(2)),
        )
        factor = coefficient**2
    return inner if factor == 1 else _node(T.MULTIPLY, from_sympy(factor), inner)


def _first_remarkable(
    node: CoreNode,
    point_node: CoreNode,
    expression: CoreNode,
    value: sympy.Expr,
    symbol: sympy.Symbol,
    point: sympy.Expr,
) -> tuple[str, CoreNode, sympy.Expr] | None:
    """The kind, the rewritten limit expression, and the coefficient."""
    if node.type is not T.LIMIT or point != 0:
        return None
    numerator, denominator = sympy.fraction(sympy.together(value))
    kind = ""
    offset: sympy.Expr | None = None
    if denominator == symbol:
        if numerator.func is sympy.sin:
            kind, offset = "sin", numerator.args[0]
        elif numerator.func is sympy.tan:
            kind, offset = "tan", numerator.args[0]
        elif numerator.func is sympy.asin:
            kind, offset = "asin", numerator.args[0]
        else:
            exponential = numerator.match(sympy.exp(sympy.Wild("u")) - 1)
            if exponential is not None:
                kind, offset = "exp", exponential[sympy.Wild("u")]
            elif numerator.func is sympy.log and len(numerator.args) == 1:
                kind, offset = "ln", sympy.simplify(numerator.args[0] - 1)
    elif denominator == symbol**2:
        match = numerator.match(1 - sympy.cos(sympy.Wild("u")))
        if match is not None:
            kind, offset = "cos", match[sympy.Wild("u")]
    if not kind or offset is None:
        return None
    coefficient = _constant_ratio(offset, symbol)
    if coefficient is None:
        return None
    if kind == "cos":
        # (1 − cos u)/u² не даёт новой формулы через первый замечательный
        # предел: этап «замена переменной» повторял бы исходную дробь.
        # Такие пределы идут через эквивалентные бесконечно малые.
        return None
    return kind, _remarkable_rewrite(kind, offset, coefficient), coefficient


def _remarkable_card(
    node: CoreNode,
    point_node: CoreNode,
    expression: CoreNode,
    rewrite: CoreNode,
    kind: str,
    answer: sympy.Expr,
) -> SolveResult:
    card = SolveResult(header="lesson_calc_header_remarkable")
    _stage_with(card, "lesson_calc_uncertainty_00", ["evaluate_using_transformations"], node, None)
    if kind in {"sin", "tan", "asin"}:
        _stage(card, "lesson_calc_first_remarkable", None, None, _law_first())
    else:
        _stage(card, "lesson_calc_equivalents", None, None)
    _stage(card, "limit_change_var", node, _limit_node(T.LIMIT, point_node, rewrite))
    answer_node = _answer(answer)
    _stage(
        card,
        "lesson_calc_limit_result",
        _limit_node(T.LIMIT, point_node, rewrite),
        answer_node,
        answer_node,
    )
    return _cards_result(card, answer_node)


# ── equivalents in numerator AND denominator ─────────────────────────


_EQUIVALENT_PATTERNS: tuple[tuple[str, sympy.Expr, Callable[..., sympy.Expr]], ...] = ()


def _equivalent_patterns() -> tuple[tuple[str, sympy.Expr, Callable[..., sympy.Expr]], ...]:
    """The equivalents as patterns on a wildcard ``u``.

    ``sin u ~ u``, ``tg u ~ u``, ``arcsin u ~ u``, ``ln(1+u) ~ u``,
    ``e^u − 1 ~ u`` and ``1 − cos u ~ u²/2``.
    """
    global _EQUIVALENT_PATTERNS
    if _EQUIVALENT_PATTERNS:
        return _EQUIVALENT_PATTERNS
    u = sympy.Wild("u")
    _EQUIVALENT_PATTERNS = (
        ("sin", sympy.sin(u), lambda w: w),
        ("tan", sympy.tan(u), lambda w: w),
        ("arcsin", sympy.asin(u), lambda w: w),
        ("ln", sympy.log(1 + u), lambda w: w),
        ("exp", sympy.exp(u) - 1, lambda w: w),
        ("cos", 1 - sympy.cos(u), lambda w: w**2 / 2),
    )
    return _EQUIVALENT_PATTERNS


def _replace_equivalents(
    expression: sympy.Expr,
    symbol: sympy.Symbol,
    point: sympy.Expr,
    used: list[str],
) -> sympy.Expr:
    """Replace every factor that is equivalent to a power of ``u`` as ``u → 0``."""
    for name, pattern, replace in _equivalent_patterns():
        match = expression.match(pattern)
        if match is None:
            continue
        u = match[sympy.Wild("u")]
        try:
            tends_to_zero = sympy.limit(u, symbol, point) == 0
        except (TypeError, ValueError, NotImplementedError):
            tends_to_zero = False
        if u.has(symbol) and tends_to_zero:
            used.append(name)
            return replace(u)
    if not expression.args:
        return expression
    return expression.func(
        *[_replace_equivalents(arg, symbol, point, used) for arg in expression.args]
    )


def _equivalents_card(
    node: CoreNode,
    point_node: CoreNode,
    expression: CoreNode,
    value: sympy.Expr,
    symbol: sympy.Symbol,
    point: sympy.Expr,
    variable: str,
) -> tuple[SolveResult, sympy.Expr] | None:
    """0/0 by equivalents: replace the numerator and the denominator, cancel, answer."""
    if node.type is not T.LIMIT or point != 0:
        return None
    if expression.type not in (T.FRACTION, T.DIVIDE) or len(expression.children) != 2:
        return None
    numerator, denominator = _fraction_parts(expression, value)
    used: list[str] = []
    top = _replace_equivalents(numerator, symbol, point, used)
    bottom = _replace_equivalents(denominator, symbol, point, used)
    if not used or (top == numerator and bottom == denominator):
        return None
    rewritten = sympy.simplify(top / bottom)
    answer = _limit_value(node.type, rewritten, symbol, point)
    original = _limit_value(node.type, value, symbol, point)
    if answer is None or original is None or _is_accumulation(answer):
        return None
    try:
        if sympy.simplify(answer - original) != 0:
            return None
    except (TypeError, ValueError):
        return None

    card = SolveResult(header="lesson_calc_header_equivalents")
    _stage_with(card, "lesson_calc_uncertainty_00", ["evaluate_using_transformations"], node, None)
    _stage(card, "lesson_calc_equivalents", None, None)
    replaced = _node(T.FRACTION, from_sympy(top), from_sympy(bottom))
    formulas = [_equivalence_formula(name) for name in dict.fromkeys(used)]
    _stage(
        card,
        "lesson_calc_equivalents_replace",
        expression,
        replaced,
        formulas[0] if len(formulas) == 1 else _node(T.LIST, *formulas),
    )
    cancelled = from_sympy(rewritten)
    if not cancelled.structural_eq(replaced):
        _stage(card, "lesson_calc_simplify", replaced, cancelled)
    changed = _limit_node(T.LIMIT, point_node, cancelled)
    _stage(card, "limit_change_var", node, changed)
    substituted = _substitute(cancelled, variable, point_node)
    _stage(card, "lesson_calc_substitute", changed, substituted)
    answer_node = _answer(answer)
    _stage(card, "lesson_calc_limit_result", substituted, answer_node, answer_node)
    return _cards_result(card, answer_node), answer


def _equivalence_formula(name: str) -> sympy.Expr:
    """The applied equivalence as a formula node: ``sin u ~ u`` and friends."""
    u = CoreNode.variable("u")
    table = {
        "sin": _node(T.SIN, u),
        "tan": _node(T.TAN, u),
        "arcsin": _node(T.ASIN, u),
        "ln": _node(T.LN, _node(T.ADD, _num(1), u)),
        "exp": _node(T.SUBTRACT, _node(T.EXP, u), _num(1)),
        "cos": _node(T.SUBTRACT, _num(1), _node(T.COS, u)),
    }
    right = u if name != "cos" else _node(T.FRACTION, _node(T.POWER, u, _num(2)), _num(2))
    return _node(T.APPROXIMATE, table[name], right)


# ── roots: multiply by the conjugate ─────────────────────────────────


def _conjugate_card(
    node: CoreNode,
    point_node: CoreNode,
    expression: CoreNode,
    conjugate: sympy.Expr,
    multiplied_top: sympy.Expr,
    multiplied_bottom: sympy.Expr,
    reduced: sympy.Expr,
    variable: str,
    symbol: sympy.Symbol,
    point: sympy.Expr,
    answer: sympy.Expr,
) -> SolveResult:
    card = SolveResult(header="lesson_calc_header_conjugate")
    key = (
        "lesson_calc_uncertainty_00"
        if point.is_finite is True
        else "lesson_calc_uncertainty_inf_minus_inf"
    )
    _stage_with(card, key, ["evaluate_using_transformations"], node, None)
    multiplied = _node(T.FRACTION, from_sympy(multiplied_top), from_sympy(multiplied_bottom))
    _stage(card, "lesson_calc_conjugate_multiply", expression, multiplied, from_sympy(conjugate))
    reduced_node = from_sympy(reduced)
    _stage(card, "lesson_calc_conjugate_simplify", multiplied, reduced_node)
    answer_node = _answer(answer)
    if point.is_finite is True:
        substituted = _substitute(reduced_node, variable, point_node)
        _stage(
            card,
            "lesson_calc_substitute",
            _limit_node(node.type, point_node, reduced_node),
            substituted,
        )
        _stage(card, "lesson_calc_simplify", substituted, answer_node)
    else:
        numerator, denominator = sympy.fraction(reduced)
        divided = _divided_node(numerator, denominator, symbol, 1)
        _stage(
            card,
            "lesson_calc_divide_highest",
            reduced_node,
            divided,
            CoreNode.variable(variable),
        )
        _stage(card, "lesson_calc_inf_terms_zero", divided, answer_node)
    return _cards_result(card, answer_node)


# ── second remarkable limit: 1^∞ ─────────────────────────────────────


def _second_remarkable(
    node: CoreNode, value: sympy.Expr, symbol: sympy.Symbol, point: sympy.Expr
) -> tuple[sympy.Expr, sympy.Expr, sympy.Expr, sympy.Expr] | None:
    """The base, the exponent ``1/(base−1)`` of the reduced power, the outer power, its limit.

    ``(1 + f)^g = [(1 + f)^{1/f}]^{g f}``: the inner limit is ``e``, so the
    answer is ``e^{lim g f}``.  The outer power need not be constant
    (``((19−4x)/(5x−8))^{(16−3x)/(2x−6)}``): only its limit matters.
    """
    if not isinstance(value, sympy.Pow) or not value.exp.has(symbol):
        return None
    base, exponent = value.base, value.exp
    offset = sympy.simplify(base - 1)
    if offset.has(symbol) is False:
        return None
    try:
        if sympy.limit(base, symbol, point) != 1:
            return None
        inner = sympy.simplify(1 / offset)
        power = sympy.simplify(exponent * offset)
    except (TypeError, ValueError, ZeroDivisionError, NotImplementedError):
        return None
    if inner.has(symbol) is False or power.is_zero is True:
        return None
    power_limit = _limit_value(T.LIMIT, power, symbol, point)
    if power_limit is None or _is_accumulation(power_limit) or power_limit.is_finite is not True:
        return None
    return base, inner, power, power_limit


def _second_card(
    node: CoreNode,
    point_node: CoreNode,
    base: sympy.Expr,
    inner_exponent: sympy.Expr,
    power: sympy.Expr,
    power_limit: sympy.Expr,
    answer: sympy.Expr,
) -> SolveResult:
    card = SolveResult(header="lesson_calc_header_second_remarkable")
    _stage_with(
        card, "lesson_calc_uncertainty_1_inf", ["evaluate_using_transformations"], node, None
    )
    _stage(card, "lesson_calc_second_remarkable", None, None, _law_second())
    inner_node = _node(T.POWER, from_sympy(base), from_sympy(sympy.simplify(inner_exponent)))
    if power == 1:
        reduced = inner_node
    else:
        reduced = _node(T.POWER, inner_node, from_sympy(sympy.simplify(power)))
    reduced_limit = _limit_node(T.LIMIT, point_node, reduced)
    _stage(card, "limit_change_var", node, reduced_limit)
    answer_node = _answer(answer)
    if power.is_number:
        if isinstance(answer, sympy.exp) and len(answer.args) == 1:
            _stage(
                card,
                "lesson_calc_limit_result_exp",
                reduced_limit,
                answer_node,
                from_sympy(answer.args[0]),
            )
        else:
            _stage(card, "lesson_calc_limit_result", reduced_limit, answer_node, answer_node)
        return _cards_result(card, answer_node)
    power_limit_node = from_sympy(power_limit)
    _stage(
        card,
        "textbook_second_power",
        _limit_node(T.LIMIT, point_node, from_sympy(sympy.simplify(power))),
        power_limit_node,
        power_limit_node,
    )
    if isinstance(answer, sympy.exp) and len(answer.args) == 1:
        _stage(
            card,
            "lesson_calc_limit_result_exp",
            None,
            answer_node,
            power_limit_node,
        )
    else:
        _stage(card, "lesson_calc_limit_result", None, answer_node, answer_node)
    return _cards_result(card, answer_node)


# ── one-sided limits ──────────────────────────────────────────────────


def _abs_one_sided(
    node: CoreNode, point_node: CoreNode, expression: CoreNode, variable: str, answer: int
) -> SolveResult:
    card = SolveResult(header="lesson_calc_header_one_sided")
    answer_node = _num(answer)
    side = "lesson_calc_abs_right" if node.type is T.LIMIT_RIGHT else "lesson_calc_abs_left"
    common = "limit_common_right" if node.type is T.LIMIT_RIGHT else "limit_common_left"
    _stage(card, side, None, None, CoreNode.variable(variable))
    _stage_with(
        card,
        common,
        ["evaluate_of_common_function"],
        node,
        answer_node,
        expression,
        answer_node,
        CoreNode.variable(variable),
        point_node,
    )
    signed = (
        _node(T.FRACTION, CoreNode.variable(variable), CoreNode.variable(variable))
        if answer > 0
        else _node(
            T.FRACTION,
            _node(T.NEGATIVE, CoreNode.variable(variable)),
            CoreNode.variable(variable),
        )
    )
    _stage(card, "lesson_calc_simplify", signed, answer_node)
    _stage(card, "lesson_calc_limit_result", signed, answer_node, answer_node)
    return _cards_result(card, answer_node)


def _one_sided_infinite(
    node: CoreNode,
    point_node: CoreNode,
    expression: CoreNode,
    denominator: sympy.Expr,
    variable: str,
    answer: sympy.Expr,
) -> SolveResult | None:
    # The sign templates state a positive/negative denominator on the approached
    # side; only use them when that is literally what happens (1/x at 0±).
    if node.type is T.LIMIT_RIGHT and answer is not sympy.oo:
        return None
    if node.type is T.LIMIT_LEFT and answer is not -sympy.oo:
        return None
    card = SolveResult(header="lesson_calc_header_one_sided")
    answer_node = _answer(answer)
    common = "limit_common_right" if node.type is T.LIMIT_RIGHT else "limit_common_left"
    _stage_with(
        card,
        common,
        ["evaluate_of_common_function"],
        node,
        answer_node,
        expression,
        answer_node,
        CoreNode.variable(variable),
        point_node,
    )
    sign = (
        "lesson_calc_one_sided_sign_right"
        if node.type is T.LIMIT_RIGHT
        else "lesson_calc_one_sided_sign_left"
    )
    _stage(card, sign, None, None, from_sympy(denominator))
    _stage(card, "lesson_calc_limit_result", node, answer_node, answer_node)
    return _cards_result(card, answer_node)


# ── limits that do not exist ──────────────────────────────────────────


def _dne_card(
    node: CoreNode,
    point_node: CoreNode,
    expression: CoreNode,
    variable: str,
    left: sympy.Expr | None = None,
    right: sympy.Expr | None = None,
    oscillation: bool = False,
) -> SolveResult:
    card = SolveResult(header="lesson_calc_header_dne")
    value = to_sympy(expression)
    if _abs_fraction(value, sympy.Symbol(variable)):
        _stage(card, "lesson_calc_abs_left", None, None, CoreNode.variable(variable))
        _stage(card, "lesson_calc_abs_right", None, None, CoreNode.variable(variable))
    if oscillation:
        _stage(
            card,
            "lesson_calc_limit_oscillation",
            node,
            None,
            expression,
            CoreNode.variable(variable),
            point_node,
        )
    else:
        assert left is not None and right is not None
        left_node, right_node = from_sympy(left), from_sympy(right)
        _stage(
            card,
            "limit_common_left",
            node,
            left_node,
            expression,
            left_node,
            CoreNode.variable(variable),
            point_node,
        )
        _stage(
            card,
            "limit_common_right",
            node,
            right_node,
            expression,
            right_node,
            CoreNode.variable(variable),
            point_node,
        )
        _stage(card, "limit_does_not_exist", node, None, node)
    _stage(card, "limit_does_not_exist_msg", node, None)
    return card


def _dne_cards(
    node: CoreNode,
    point_node: CoreNode,
    expression: CoreNode,
    value: sympy.Expr,
    variable: str,
    symbol: sympy.Symbol,
    point: sympy.Expr,
) -> SolveResult | None:
    if node.type is not T.LIMIT:
        return None
    if point in (sympy.oo, -sympy.oo):
        try:
            result = sympy.limit(value, symbol, point)
        except (TypeError, ValueError, NotImplementedError):
            return None
        if _is_accumulation(result):
            return _dne_card(node, point_node, expression, variable, oscillation=True)
        return None
    if point.is_finite is not True or point.is_real is not True:
        return None
    try:
        left = sympy.limit(value, symbol, point, "-")
        right = sympy.limit(value, symbol, point, "+")
    except (TypeError, ValueError, NotImplementedError):
        return None
    if _is_accumulation(left) or _is_accumulation(right):
        return _dne_card(node, point_node, expression, variable, oscillation=True)
    if left != right:
        if _not_real(left) != _not_real(right):
            # The function is real on one side of the point only (an even root):
            # that side is the domain, so the limit is not a two-sided jump.
            return None
        return _dne_card(node, point_node, expression, variable, left=left, right=right)
    return None


# ── entry point ───────────────────────────────────────────────────────


def _leading_term(
    expression: sympy.Expr, symbol: sympy.Symbol, point: sympy.Expr
) -> sympy.Expr | None:
    """The first non-zero term of the expansion at the point, or ``None``.

    At infinity the variable is replaced by ``1/t`` (``−1/t`` for ``−∞``) and
    the expansion is read in ``t → 0+``; at a finite point by ``x = a + u``.
    """
    try:
        if point in (sympy.oo, -sympy.oo):
            t = sympy.Symbol("_t", positive=True)
            replacement = 1 / t if point is sympy.oo else -1 / t
            transformed = sympy.simplify(expression.subs(symbol, replacement))
            leading = sympy.simplify(transformed.as_leading_term(t))
            if point is sympy.oo:
                # ``c·t^p`` is ``c·x^(−p)``: keep the canonical power form so the
                # card shows ``x^(-1/6)``, not a root of ``1/x``.
                coefficient, rest = leading.as_coeff_mul(t)
                if not rest:
                    return _real_branch(sympy.simplify(coefficient))
                base, exponent = rest[0].as_base_exp()
                if base == t and exponent.is_rational and not coefficient.has(t) and len(rest) == 1:
                    return _real_branch(sympy.simplify(coefficient * symbol ** (-exponent)))
            back = 1 / symbol if point is sympy.oo else -1 / symbol
            return _real_branch(sympy.simplify(leading.subs(t, back)))
        u = sympy.Symbol("_u", positive=True)
        transformed = sympy.simplify(expression.subs(symbol, point + u))
        leading = sympy.simplify(transformed.as_leading_term(u))
        return _real_branch(sympy.simplify(leading.subs(u, symbol - point)))
    except (
        TypeError,
        ValueError,
        AttributeError,
        ZeroDivisionError,
        NotImplementedError,
        sympy.PoleError,
        sympy.PolynomialError,
    ):
        return None


def _real_branch(expression: sympy.Expr) -> sympy.Expr:
    """Take the real odd root of ``−1``: ``∛(−x⁶)`` is ``−x²``, not ``e^{iπ/3} x²``."""

    def odd_root(power: sympy.Pow) -> sympy.Expr | None:
        exponent = power.exp
        if power.base == -1 and exponent.is_Rational and exponent.q % 2 == 1 and exponent.q != 1:
            return -sympy.Integer(1)
        return None

    return expression.replace(
        lambda atom: isinstance(atom, sympy.Pow) and odd_root(atom) is not None, odd_root
    )


def _asymptotic(
    expression: sympy.Expr, leading: sympy.Expr, symbol: sympy.Symbol, point: sympy.Expr
) -> bool:
    """Is ``expression ~ leading`` at the point (their ratio tends to one)?"""
    if expression == leading:
        return True
    try:
        ratio = sympy.limit(expression / leading, symbol, point)
    except (TypeError, ValueError, NotImplementedError, ZeroDivisionError):
        return False
    return bool(_real_branch(sympy.simplify(ratio)) == 1)


def _leading_rewrite(
    expression: sympy.Expr, symbol: sympy.Symbol, point: sympy.Expr
) -> sympy.Expr | None:
    """Replace every multiplicative factor by its leading term.

    A sum or a single factor is replaced as a whole; a product factor by
    factor.  Every replacement must be asymptotic (the ratio tends to one), so
    a bounded oscillating factor can never be replaced by a power of the
    variable.
    """
    product = _leading_product(expression, symbol, point)
    return None if product is None else product[0]


def _leading_product(
    expression: sympy.Expr, symbol: sympy.Symbol, point: sympy.Expr
) -> tuple[sympy.Expr, CoreNode] | None:
    """The leading term of a product, with the unreduced product as a node."""
    if expression.is_Mul:
        parts: list[sympy.Expr] = []
        nodes: list[CoreNode] = []
        for factor in expression.args:
            leading = _leading_term(factor, symbol, point)
            if leading is None or not _asymptotic(factor, leading, symbol, point):
                return None
            parts.append(leading)
            nodes.append(from_sympy(leading))
        return sympy.Mul(*parts), _node(T.MULTIPLY, *nodes)
    leading = _leading_term(expression, symbol, point)
    if leading is None or not _asymptotic(expression, leading, symbol, point):
        return None
    return leading, from_sympy(leading)


def _form_key(expression: sympy.Expr, symbol: sympy.Symbol, point: sympy.Expr) -> str | None:
    """The name of the indeterminate form, when one is visible."""
    numerator, denominator = sympy.fraction(sympy.together(expression))
    if denominator != 1:
        try:
            top = _real_branch(sympy.limit(numerator, symbol, point))
            bottom = sympy.limit(denominator, symbol, point)
        except (TypeError, ValueError, NotImplementedError):
            top = bottom = None
        if top == 0 and bottom == 0:
            return "lesson_calc_uncertainty_00"
        if top in (sympy.oo, -sympy.oo) and bottom in (sympy.oo, -sympy.oo):
            return "lesson_calc_uncertainty_inf"
    if isinstance(expression, sympy.Add):
        signs = []
        for term in expression.args:
            try:
                value = sympy.limit(term, symbol, point)
            except (TypeError, ValueError, NotImplementedError):
                return None
            if value in (sympy.oo, -sympy.oo):
                signs.append(value)
        if sympy.oo in signs and -sympy.oo in signs:
            return "lesson_calc_uncertainty_inf_minus_inf"
    if isinstance(expression, sympy.Mul):
        limits = []
        for factor in expression.args:
            try:
                limits.append(sympy.limit(factor, symbol, point))
            except (TypeError, ValueError, NotImplementedError):
                return None
        if any(value == 0 for value in limits) and any(
            value in (sympy.oo, -sympy.oo) for value in limits
        ):
            return "textbook_uncertainty_zero_inf"
    return None


def _leading_card(
    node: CoreNode,
    point_node: CoreNode,
    expression: CoreNode,
    value: sympy.Expr,
    symbol: sympy.Symbol,
    point: sympy.Expr,
) -> SolveResult | None:
    """Limits solved by passing to the leading term of every factor."""
    if node.type is not T.LIMIT:
        return None
    answer = _limit_value(node.type, value, symbol, point)
    if answer is None or _is_accumulation(answer):
        return None
    form = _form_key(value, symbol, point)
    numerator, denominator = sympy.fraction(sympy.together(value))
    if denominator != 1:
        top_product = _leading_product(numerator, symbol, point)
        bottom_product = _leading_product(denominator, symbol, point)
        if top_product is None or bottom_product is None:
            return None
        top, top_node = top_product
        bottom, bottom_node = bottom_product
        replaced = _node(T.FRACTION, top_node, bottom_node)
        rewritten = top / bottom
    else:
        product = _leading_product(value, symbol, point)
        if product is None:
            return None
        rewritten, replaced = product
    if form is None and not rewritten.has(symbol):
        # A plain substitution: continuity is not a leading-term argument.
        return None
    if replaced.structural_eq(expression):
        return None
    candidate = _limit_value(T.LIMIT, rewritten, symbol, point)
    if candidate is None or _is_accumulation(candidate):
        return None
    if candidate != answer and sympy.simplify(candidate - answer) != 0:
        return None

    card = SolveResult(header="textbook_header_leading")
    if form is not None:
        _stage_with(card, form, ["evaluate_using_transformations"], node, None)
    _stage(card, "textbook_leading_replace", expression, replaced, replaced)
    simplified = from_sympy(sympy.simplify(rewritten))
    if not simplified.structural_eq(replaced):
        _stage(card, "lesson_calc_simplify", replaced, simplified)
    _stage(
        card,
        "lesson_calc_limit_result",
        _limit_node(T.LIMIT, point_node, simplified),
        _answer(answer),
        _answer(answer),
    )
    return _cards_result(card, _answer(answer))


def _one_sided_leading(
    node: CoreNode,
    point_node: CoreNode,
    value: sympy.Expr,
    symbol: sympy.Symbol,
    point: sympy.Expr,
) -> SolveResult | None:
    """One-sided infinite limits: the side decides the sign of the leading term."""
    if node.type not in (T.LIMIT_LEFT, T.LIMIT_RIGHT):
        return None
    answer = _limit_value(node.type, value, symbol, point)
    if answer not in (sympy.oo, -sympy.oo):
        return None
    leading = _leading_term(value, symbol, point)
    if leading is None or leading == value or not _asymptotic(value, leading, symbol, point):
        return None
    leading_limit = _limit_value(node.type, leading, symbol, point)
    if leading_limit != answer:
        return None
    card = SolveResult(header="lesson_calc_header_one_sided")
    leading_node = from_sympy(leading)
    _stage(
        card,
        "textbook_leading_replace",
        node,
        _limit_node(node.type, point_node, leading_node),
        leading_node,
    )
    _stage(
        card,
        "lesson_calc_limit_result",
        _limit_node(node.type, point_node, leading_node),
        _answer(answer),
        _answer(answer),
    )
    return _cards_result(card, _answer(answer))


def _is_bounded(term: sympy.Expr, symbol: sympy.Symbol) -> bool:
    """A factor whose absolute value never exceeds a constant."""
    if isinstance(term, (sympy.sin, sympy.cos, sympy.atan)):
        return True
    if isinstance(term, sympy.Pow):
        base, exponent = term.base, term.exp
        if base == -1 and exponent.has(symbol):
            return True
        if isinstance(base, (sympy.sin, sympy.cos)) and exponent.is_integer and exponent.is_even:
            return True
    return False


def _bounded_zero(value: sympy.Expr, symbol: sympy.Symbol, point: sympy.Expr) -> sympy.Expr | None:
    """The value ``0`` when a bounded factor meets an infinitesimal, else ``None``.

    ``(−1)^(n−1)(2−n)/(n²+3)`` makes sympy's Gruntz algorithm ask for the sign
    of the imaginary unit; the textbook proof (bounded times infinitesimal) is
    both simpler and correct.
    """
    numerator, _denominator = sympy.fraction(sympy.together(value))
    candidates = list(numerator.args) if numerator.is_Mul else [numerator]
    for candidate in candidates:
        if not _is_bounded(candidate, symbol):
            continue
        rest = sympy.simplify(value / candidate)
        try:
            if sympy.limit(rest, symbol, point) == 0:
                return sympy.Integer(0)
        except (TypeError, ValueError, NotImplementedError):
            continue
    return None


def _bounded_card(
    node: CoreNode,
    value: sympy.Expr,
    symbol: sympy.Symbol,
    point: sympy.Expr,
) -> SolveResult | None:
    """Bounded factor times an infinitesimal has limit zero."""
    if node.type is not T.LIMIT:
        return None
    answer = _limit_value(node.type, value, symbol, point)
    if answer != 0:
        return None
    numerator, _denominator = sympy.fraction(sympy.together(value))
    candidates: list[sympy.Expr] = list(numerator.args) if numerator.is_Mul else [numerator]
    for candidate in candidates:
        if not _is_bounded(candidate, symbol):
            continue
        rest = sympy.simplify(value / candidate)
        rest_limit = _limit_value(T.LIMIT, rest, symbol, point)
        if rest_limit != 0:
            continue
        card = SolveResult(header="textbook_header_bounded")
        factor_node = from_sympy(candidate)
        _stage(card, "textbook_bounded_factor", factor_node, None, factor_node)
        _stage(
            card,
            "textbook_bounded_infinitesimal",
            from_sympy(rest),
            _num(0),
            from_sympy(rest),
        )
        _stage(card, "lesson_calc_limit_result", node, _num(0), _num(0))
        return _cards_result(card, _num(0))
    return None


def _compose_power(base: sympy.Expr, exponent: sympy.Expr) -> sympy.Expr | None:
    """The limit of ``base^exponent`` from the limits of base and exponent."""
    try:
        if exponent.is_finite is True:
            if base.is_finite is True and base.is_positive is True:
                return sympy.simplify(base**exponent)
            if base is sympy.oo and exponent > 0:
                return sympy.oo
            if base == 0 and exponent > 0:
                return sympy.Integer(0)
            return None
        if exponent is sympy.oo:
            if base.is_finite is True:
                if base > 1:
                    return sympy.oo
                if 0 < base < 1:
                    return sympy.Integer(0)
            if base is sympy.oo:
                return sympy.oo
            if base == 0:
                return sympy.Integer(0)
        if exponent is -sympy.oo and base.is_finite is True and base > 1:
            return sympy.Integer(0)
    except (TypeError, ValueError):
        return None
    return None


def _power_card(
    node: CoreNode,
    point_node: CoreNode,
    expression: CoreNode,
    value: sympy.Expr,
    symbol: sympy.Symbol,
    point: sympy.Expr,
) -> SolveResult | None:
    """A power whose base and exponent have their own limits."""
    if node.type is not T.LIMIT or expression.type is not T.POWER:
        return None
    base, exponent = value.base, value.exp
    if not (base.has(symbol) and exponent.has(symbol)):
        return None
    base_limit = _limit_value(T.LIMIT, base, symbol, point)
    exponent_limit = _limit_value(T.LIMIT, exponent, symbol, point)
    if base_limit is None or exponent_limit is None:
        return None
    if _is_accumulation(base_limit) or _is_accumulation(exponent_limit):
        return None
    composed = _compose_power(base_limit, exponent_limit)
    if composed is None:
        return None
    answer = _limit_value(node.type, value, symbol, point)
    if answer is None or _is_accumulation(answer):
        return None
    if composed != answer:
        if composed.is_finite is not True or answer.is_finite is not True:
            return None
        if sympy.simplify(composed - answer) != 0:
            return None
    base_node, exponent_node = expression.children
    card = SolveResult(header="textbook_header_power")
    _stage(
        card,
        "textbook_power_base",
        _limit_node(T.LIMIT, point_node, base_node),
        from_sympy(base_limit),
        from_sympy(base_limit),
    )
    _stage(
        card,
        "textbook_power_exponent",
        _limit_node(T.LIMIT, point_node, exponent_node),
        from_sympy(exponent_limit),
        from_sympy(exponent_limit),
    )
    _stage(card, "lesson_calc_limit_result", node, _answer(answer), _answer(answer))
    return _cards_result(card, _answer(answer))


def _log_power_card(
    node: CoreNode,
    point_node: CoreNode,
    value: sympy.Expr,
    symbol: sympy.Symbol,
    point: sympy.Expr,
) -> SolveResult | None:
    """The ``∞^0`` form: take logarithms, then exponentiate the limit."""
    if node.type is not T.LIMIT or not isinstance(value, sympy.Pow):
        return None
    base, exponent = value.base, value.exp
    if not (base.has(symbol) and exponent.has(symbol)):
        return None
    base_limit = _limit_value(T.LIMIT, base, symbol, point)
    exponent_limit = _limit_value(T.LIMIT, exponent, symbol, point)
    if base_limit is not sympy.oo or exponent_limit != 0:
        return None
    logarithm = sympy.simplify(exponent * sympy.log(base))
    log_limit = _limit_value(T.LIMIT, logarithm, symbol, point)
    if log_limit is None or log_limit.is_finite is not True or _is_accumulation(log_limit):
        return None
    answer = _limit_value(node.type, value, symbol, point)
    if answer is None or sympy.simplify(sympy.exp(log_limit) - answer) != 0:
        return None
    card = SolveResult(header="textbook_header_log_power")
    _stage_with(
        card, "lesson_calc_uncertainty_inf_0", ["evaluate_using_transformations"], node, None
    )
    logarithm_node = from_sympy(logarithm)
    _stage(
        card,
        "textbook_take_log",
        node,
        _limit_node(T.LIMIT, point_node, logarithm_node),
        logarithm_node,
    )
    leading = _leading_rewrite(logarithm, symbol, point)
    if leading is not None and leading != logarithm:
        leading_node = from_sympy(leading)
        _stage(
            card,
            "textbook_leading_replace",
            _limit_node(T.LIMIT, point_node, logarithm_node),
            _limit_node(T.LIMIT, point_node, leading_node),
            leading_node,
        )
    log_limit_node = from_sympy(log_limit)
    _stage(
        card,
        "textbook_log_limit",
        _limit_node(T.LIMIT, point_node, from_sympy(leading if leading is not None else logarithm)),
        log_limit_node,
    )
    answer_node = _answer(answer)
    _stage(card, "lesson_calc_limit_result_exp", None, answer_node, log_limit_node)
    return _cards_result(card, answer_node)


def _vanishing_term(
    expression: sympy.Expr, symbol: sympy.Symbol, point: sympy.Expr
) -> sympy.Expr | None:
    """An additive term that tends to zero, or ``None``."""
    for term in sympy.Add.make_args(expression):
        if not term.has(symbol):
            continue
        try:
            if sympy.limit(term, symbol, point) == 0:
                return term
        except (TypeError, ValueError, NotImplementedError):
            continue
    return None


def _sum_limit_card(
    node: CoreNode,
    point_node: CoreNode,
    expression: CoreNode,
    value: sympy.Expr,
    variable: str,
    symbol: sympy.Symbol,
    point: sympy.Expr,
) -> SolveResult | None:
    """A limit with a finite sum: collapse it to a formula, then take the limit."""
    sums = [
        n
        for n in expression.walk()
        if n.type is T.SIGMA_DEFINITE
        and len(n.children) == 4
        and n.children[0].type is T.VARIABLE
        and n.children[0].value
        and n.children[0].value != variable
    ]
    if not sums:
        return None
    closed = expand_sums(expression, variable)
    if closed.structural_eq(expression):
        return None
    only = len(sums) == 1
    summed = sums[0] if only else expression
    collapsed = expand_sums(sums[0], variable) if only else closed
    answer = _limit_value(node.type, value, symbol, point)
    if answer is None or _is_accumulation(answer):
        return None
    card = SolveResult(header="textbook_header_sum")
    _stage(card, "textbook_sum_formula", summed, collapsed, collapsed)
    reduced = _limit_node(node.type, point_node, closed)
    _stage(card, "textbook_sum_limit", node, reduced, closed)
    inner = cards_for(reduced, [variable])
    closed_value = to_sympy(closed)
    if inner:
        card.extend(inner[0])
    else:
        term = _vanishing_term(closed_value, symbol, point)
        if term is not None and term != closed_value:
            _stage(card, "textbook_sum_decay", from_sympy(term), _num(0), from_sympy(term))
    answer_node = _answer(answer)
    _stage(card, "lesson_calc_limit_result", reduced, answer_node, answer_node)
    return _cards_result(card, answer_node)


def cards_for(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """Textbook cards for a limit; the first one is the method to show.

    Returns ``[]`` when the limit is a plain substitution, so the normal
    solver path keeps showing it as today.
    """
    if node.type not in _LIMITS or len(node.children) != 2:
        return []
    point_node, expression = node.children
    variable = limit_variable(node, variables)
    symbol = sympy.Symbol(variable)
    try:
        point = to_sympy(point_node)
        value = to_sympy(expand_sums(expression, variable))
    except Exception:
        return []

    summed = _sum_limit_card(node, point_node, expression, value, variable, symbol, point)
    if summed is not None:
        return [summed]

    # The sympy value may lose the variable by cancelling (``n²/(3n²)`` is
    # ``1/3``); the written expression still has it, and that is what counts.
    if not any(n.type is T.VARIABLE and n.value == variable for n in expression.walk()):
        return []

    dne = _dne_cards(node, point_node, expression, value, variable, symbol, point)
    if dne is not None:
        return [dne]

    if node.type is T.LIMIT_LEFT or node.type is T.LIMIT_RIGHT:
        if _abs_fraction(value, symbol):
            return [
                _abs_one_sided(
                    node, point_node, expression, variable, 1 if node.type is T.LIMIT_RIGHT else -1
                )
            ]
        try:
            numerator, denominator = _fraction_parts(expression, value)
        except Exception:
            return []
        answer = _limit_value(node.type, value, symbol, point)
        if (
            answer in (sympy.oo, -sympy.oo)
            and point.is_finite is True
            and denominator.subs(symbol, point) == 0
            and numerator.subs(symbol, point) != 0
        ):
            card = _one_sided_infinite(node, point_node, expression, denominator, variable, answer)
            if card is not None:
                return [card]
        one_sided = _one_sided_leading(node, point_node, value, symbol, point)
        if one_sided is not None:
            return [one_sided]
        return []

    try:
        numerator, denominator = _fraction_parts(expression, value)
    except Exception:
        return []

    # 0/0 rational: factor and cancel.
    if (
        point.is_finite is True
        and point.is_real is True
        and numerator.is_polynomial(symbol)
        and denominator.is_polynomial(symbol)
        and denominator != 1
        and numerator.subs(symbol, point) == 0
        and denominator.subs(symbol, point) == 0
    ):
        common = sympy.gcd(numerator, denominator)
        if common != 1:
            reduced = sympy.cancel(value)
            if sympy.fraction(reduced)[1].subs(symbol, point) != 0:
                answer = sympy.simplify(reduced.subs(symbol, point))
                card = _factor_card(
                    node,
                    point_node,
                    expression,
                    numerator,
                    denominator,
                    reduced,
                    variable,
                    symbol,
                    point,
                    answer,
                )
                return [card, lhopital_card(node, _answer(answer))]

    # ∞/∞ rational and sequences in n.
    if (
        point in (sympy.oo, -sympy.oo)
        and numerator.is_polynomial(symbol)
        and denominator.is_polynomial(symbol)
        and denominator != 1
        and sympy.degree(numerator, symbol) > 0
        and sympy.degree(denominator, symbol) > 0
    ):
        answer = _limit_value(node.type, value, symbol, point)
        if answer is not None and not _is_accumulation(answer):
            card = _inf_card(
                node, point_node, expression, numerator, denominator, variable, symbol, answer
            )
            # L'Hôpital is a theorem about functions; for a sequence in n the
            # textbook card stands alone.
            if variable == "n":
                return [card]
            return [card, lhopital_card(node, _answer(answer))]

    sequence_answer = _limit_value(node.type, value, symbol, point)
    if sequence_answer is not None:
        sequence = _sequence_root_card(node, symbol, sequence_answer)
        if sequence is not None:
            return [sequence]

    # 1^∞: the second remarkable limit.
    second = _second_remarkable(node, value, symbol, point)
    if second is not None:
        base, inner, power, power_limit = second
        answer = _limit_value(node.type, value, symbol, point)
        if answer is not None and answer.is_finite is True:
            try:
                same = sympy.simplify(sympy.exp(power_limit) - answer) == 0
            except (TypeError, ValueError):
                same = False
            if same:
                return [_second_card(node, point_node, base, inner, power, power_limit, answer)]

    # First remarkable limit and equivalent infinitesimals.
    remarkable = _first_remarkable(node, point_node, expression, value, symbol, point)
    if remarkable is not None:
        kind, rewrite, _coefficient = remarkable
        answer = _limit_value(node.type, value, symbol, point)
        if answer is not None:
            card = _remarkable_card(node, point_node, expression, rewrite, kind, answer)
            return [card, lhopital_card(node, _answer(answer))]

    # Ratios and products of equivalent infinitesimals: sin u ~ u, tg u ~ u,
    # ln(1 + u) ~ u, e^u − 1 ~ u, 1 − cos u ~ u²/2.
    equivalents = _equivalents_card(node, point_node, expression, value, symbol, point, variable)
    if equivalents is not None:
        card, answer = equivalents
        return [card, lhopital_card(node, _answer(answer))]

    # Roots: multiply and divide by the conjugate.
    if _has_sqrt(value):
        conjugate = None
        top = None
        bottom = None
        if (
            point.is_finite is True
            and expression.type in (T.FRACTION, T.DIVIDE)
            and len(expression.children) == 2
            and _has_sqrt(numerator)
            and numerator.subs(symbol, point) == 0
            and denominator.subs(symbol, point) == 0
        ):
            conjugate = _sqrt_conjugate(numerator)
            if conjugate is not None:
                top = sympy.expand(numerator * conjugate)
                bottom = sympy.expand(denominator * conjugate)
        elif point in (sympy.oo, -sympy.oo) and expression.type not in (T.FRACTION, T.DIVIDE):
            conjugate = _sqrt_conjugate(value)
            if conjugate is not None:
                top = sympy.expand(value * conjugate)
                bottom = conjugate
        if conjugate is not None and top is not None and bottom is not None:
            reduced = sympy.cancel(top / bottom)
            answer = _limit_value(node.type, value, symbol, point)
            indeterminate = point.is_finite is True and _still_indeterminate(reduced, symbol, point)
            if answer is not None and not indeterminate:
                card = _conjugate_card(
                    node,
                    point_node,
                    expression,
                    conjugate,
                    top,
                    bottom,
                    reduced,
                    variable,
                    symbol,
                    point,
                    answer,
                )
                cards = [card]
                if point.is_finite is True:
                    cards.append(lhopital_card(node, _answer(answer)))
                return cards

    # ∞^0: take logarithms, then exponentiate.
    logarithmic = _log_power_card(node, point_node, value, symbol, point)
    if logarithmic is not None:
        return [logarithmic]

    # A power whose base and exponent have their own limits: 2^x, (1/3)^{3x}.
    powered = _power_card(node, point_node, expression, value, symbol, point)
    if powered is not None:
        return [powered]

    # Bounded factor times an infinitesimal: sin(n!)/n², (−1)^n · (1 − n)/n².
    bounded = _bounded_card(node, value, symbol, point)
    if bounded is not None:
        return [bounded]

    # Leading terms: each factor replaced by the first term of its expansion.
    leading = _leading_card(node, point_node, expression, value, symbol, point)
    if leading is not None:
        return [leading]

    return []
