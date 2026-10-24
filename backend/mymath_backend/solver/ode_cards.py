"""Textbook cards of a first-order differential equation.

The card names the Filippov method and shows its work the way the integral
cards do: a header with the method, one step «Решите уравнение» and stages that
are either facts (``y = ux``, ``dy/y = x dx``, ``v = e^(−x)``) or
transformations ``left → right`` with consecutive transformations chained.

Every integration inside a card is the integral textbook card of
:mod:`integral_cards` (without ``+ C``) attached to the stage as its nested
«Подробнее».  Each answer is checked with ``sympy.checkodesol`` against the
equation built from the same tree before the card is offered; when a card
cannot be built the caller keeps the previous two-step answer.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveError, SolveResult, Step
from .diff_equations import (
    _KIND_BERNOULLI,
    _KIND_EXACT,
    _KIND_HOMOGENEOUS,
    _KIND_LINEAR,
    _KIND_SEPARATION,
    _KIND_SINGULAR,
    _abs_logs,
    _clean_expression,
    _singular_solution,
)
from .integral_cards import textbook_detail
from .sympy_bridge import from_sympy, to_sympy

_HEADER_SEPARABLE = "lesson_calc_ode_header_separable"
_HEADER_HOMOGENEOUS = "lesson_calc_ode_header_homogeneous"
_HEADER_LINEAR = "lesson_calc_ode_header_linear"
_HEADER_BERNOULLI = "lesson_calc_ode_header_bernoulli"
_HEADER_EXACT = "lesson_calc_ode_header_exact"
_HEADER_CONDITION = "lesson_calc_ode_condition_header"

_KEY_SOLVE = "eq_solve_short"

_KEY_SEP_DERIVATIVE = "lesson_calc_ode_sep_derivative"
_KEY_SEP_SEPARATE = "lesson_calc_ode_sep_separate"
_KEY_SEP_INTEGRATE = "lesson_calc_ode_sep_integrate"
_KEY_SEP_PRIMITIVE = "lesson_calc_ode_sep_primitive"
_KEY_SEP_IMPLICIT = "lesson_calc_ode_sep_implicit"
_KEY_SEP_EXPRESS = "lesson_calc_ode_sep_express"
_KEY_SEP_EXPRESS_LOG = "lesson_calc_ode_sep_express_log"
_KEY_SEP_EXPRESS_RENAME = "lesson_calc_ode_sep_express_rename"
_KEY_SEP_EXPRESS_P = "lesson_calc_ode_sep_express_p"
_KEY_SEP_EXPRESS_LOG_P = "lesson_calc_ode_sep_express_log_p"
_KEY_SEP_EXPRESS_RENAME_P = "lesson_calc_ode_sep_express_rename_p"

_KEY_HOM_FORM = "lesson_calc_ode_hom_form"
_KEY_HOM_SUBSTITUTE = "lesson_calc_ode_hom_substitute"
_KEY_HOM_EQUATION = "lesson_calc_ode_hom_equation"
_KEY_HOM_REDUCE = "lesson_calc_ode_hom_reduce"
_KEY_HOM_SEPARATE = "lesson_calc_ode_hom_separate"
_KEY_HOM_INTEGRATE = "lesson_calc_ode_hom_integrate"
_KEY_HOM_PRIMITIVE = "lesson_calc_ode_hom_primitive"
_KEY_HOM_BACK = "lesson_calc_ode_hom_back"

_KEY_LIN_SUBSTITUTE = "lesson_calc_ode_lin_substitute"
_KEY_LIN_SUBSTITUTE_Z = "lesson_calc_ode_lin_substitute_z"
_KEY_LIN_INSERT = "lesson_calc_ode_lin_insert"
_KEY_LIN_INSERT_Z = "lesson_calc_ode_lin_insert_z"
_KEY_LIN_CHOOSE_V = "lesson_calc_ode_lin_choose_v"
_KEY_LIN_V = "lesson_calc_ode_lin_v"
_KEY_LIN_V_VALUE = "lesson_calc_ode_lin_v_value"
_KEY_LIN_U_EQUATION = "lesson_calc_ode_lin_u_equation"
_KEY_LIN_U = "lesson_calc_ode_lin_u"
_KEY_LIN_U_VALUE = "lesson_calc_ode_lin_u_value"
_KEY_LIN_BACK = "lesson_calc_ode_lin_back"
_KEY_LIN_BACK_Z = "lesson_calc_ode_lin_back_z"
_KEY_LIN_SIMPLIFY = "lesson_calc_ode_lin_simplify"

_KEY_BERN_DIVIDE = "lesson_calc_ode_bern_divide"
_KEY_BERN_SUBSTITUTE = "lesson_calc_ode_bern_substitute"
_KEY_BERN_LINEAR = "lesson_calc_ode_bern_linear"
_KEY_BERN_BACK = "lesson_calc_ode_bern_back"

_KEY_EX_PQ = "lesson_calc_ode_ex_pq"
_KEY_EX_DIFFERENTIAL = "lesson_calc_ode_ex_differential"
_KEY_EX_CHECK = "lesson_calc_ode_ex_check"
_KEY_EX_POTENTIAL = "lesson_calc_ode_ex_potential"
_KEY_EX_ANSWER = "lesson_calc_ode_ex_answer"

_KEY_CONDITION = "lesson_calc_ode_condition"
_KEY_CONDITION_SUBSTITUTE = "lesson_calc_ode_condition_substitute"
_KEY_CONDITION_VALUE = "lesson_calc_ode_condition_value"
_KEY_CONDITION_ANSWER = "lesson_calc_ode_condition_answer"

_C = sympy.Symbol("C")
_C0 = sympy.Symbol("C0")
_U = sympy.Symbol("u")
_Z = sympy.Symbol("z")

_CardAnswer = tuple[str, SolveResult, CoreNode]


# ── node helpers ──────────────────────────────────────────────────────


def _node(kind: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(kind, *children)


def _num(value: int) -> CoreNode:
    return CoreNode.constant(str(value))


def _var(name: str) -> CoreNode:
    return CoreNode.variable(name)


def _eq(left: CoreNode, right: CoreNode) -> CoreNode:
    return _node(T.EQUALS, left, right)


def _integral(expression: CoreNode) -> CoreNode:
    return _node(T.INTEGRAL, expression)


def _fraction(numerator: CoreNode, denominator: CoreNode) -> CoreNode:
    return _node(T.FRACTION, numerator, denominator)


def _product(*pieces: CoreNode) -> CoreNode:
    return _node(T.MULTIPLY_IMPLICIT, *pieces)


def _power(base: CoreNode, exponent: CoreNode) -> CoreNode:
    return _node(T.POWER, base, exponent)


def _bracket(node: CoreNode) -> CoreNode:
    return _node(T.BRACKET, node)


def _bracketed(node: CoreNode) -> CoreNode:
    """A product factor in parentheses when it is a sum (``(x² + 3y²) dy``)."""
    return _bracket(node) if node.type in (T.ADD, T.SUBTRACT) else node


def _chain(parts: list[tuple[bool, CoreNode]]) -> CoreNode:
    """Join signed pieces into one ``ADD``/``SUBTRACT`` chain."""
    result: CoreNode | None = None
    for negative, piece in parts:
        if result is None:
            result = _node(T.NEGATIVE, piece) if negative else piece
        elif negative:
            result = _node(T.SUBTRACT, result, piece)
        else:
            result = _node(T.ADD, result, piece)
    return result if result is not None else _num(0)


def _signed(expression: sympy.Expr, xsym: sympy.Symbol) -> tuple[bool, CoreNode]:
    """A node with its leading sign split off, so a chain reads ``− 2v/x``."""
    negative = bool(expression.could_extract_minus_sign())
    return negative, _expr(-expression if negative else expression, xsym)


def _expr(expression: sympy.Expr, xsym: sympy.Symbol) -> CoreNode:
    """The formula of a stage: the textbook form of a sympy expression."""
    cleaned = _clean_expression(expression, xsym, 1)
    numerator, denominator = sympy.fraction(cleaned)
    if (
        cleaned.could_extract_minus_sign()
        and numerator.is_number
        and denominator.is_Add
        and not denominator.has(_C)
    ):
        return _fraction(_expr(-numerator, xsym), _expr(-denominator, xsym))
    return from_sympy(cleaned)


def _plain(expression: sympy.Expr, xsym: sympy.Symbol, symbol: sympy.Symbol) -> CoreNode:
    """A formula without simplification: a bracket keeps its factored shape."""
    return from_sympy(_abs_logs(_log_abs(expression, symbol), xsym))


def _fact(key: str, *nodes: CoreNode, args: list[CoreNode] | None = None) -> Step:
    shown = nodes[0] if len(nodes) == 1 else _node(T.LIST, *nodes)
    return Step(shown, None, key, list(args or []))


def _transform(
    key: str,
    left: CoreNode,
    right: CoreNode,
    *,
    subresult: SolveResult | None = None,
    args: list[CoreNode] | None = None,
) -> Step | None:
    if left.structural_eq(right):
        return None
    return Step(left, right, key, list(args or []), subresult=subresult)


def _stages(
    key: str,
    left: CoreNode,
    right: CoreNode,
    *,
    subresult: SolveResult | None = None,
    args: list[CoreNode] | None = None,
) -> list[Step]:
    stage = _transform(key, left, right, subresult=subresult, args=args)
    return [] if stage is None else [stage]


def _detail(expression: sympy.Expr, variable: sympy.Symbol) -> SolveResult | None:
    """The integral textbook card of ``∫ expression d(variable)``, without ``+ C``."""
    with contextlib.suppress(ValueError, TypeError, NotImplementedError, sympy.PolynomialError):
        return textbook_detail(_integral(from_sympy(expression)), [str(variable)])
    return None


_INTEGRAL_SIDES = (
    "lesson_calc_ode_integral_left",
    "lesson_calc_ode_integral_right",
)


def _combined(*cards: SolveResult | None) -> SolveResult | None:
    """One «Подробнее» holding the integral card of each side of an equation.

    Each side keeps its own heading («Интеграл левой части», «Интеграл правой
    части»): two nested cards headed «Вычислите интеграл» in a row read as a
    mistake, the student cannot tell which side is which.
    """
    out = SolveResult(header="lesson_calc_ode_header_integrals")
    for side, card in zip(_INTEGRAL_SIDES, cards, strict=False):
        if card is not None:
            card.retitle(side)
            out.extend(card)
    if not out:
        return None
    out.solution = next((card.solution for card in reversed(cards) if card is not None), None)
    return out


def _substitute_node(node: CoreNode, variable: str, value: CoreNode) -> CoreNode:
    """Replace a variable in a display tree (no sympy evaluation)."""
    if node.type is T.VARIABLE and node.value == variable:
        return value
    if not node.children:
        return node
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[_substitute_node(child, variable, value) for child in node.children],
    )


def _reduce_constants(node: CoreNode) -> CoreNode:
    """Fold constant arithmetic but keep ``e⁰``/``cos 0`` written as they are.

    ``C·e^x`` with ``x = 0`` must read ``C·e⁰``, so functions of constants are
    never evaluated; ``0²`` and ``0 + C`` do fold.
    """
    children = [_reduce_constants(child) for child in node.children]
    folded = CoreNode(type=node.type, value=node.value, children=children)
    arithmetic = (
        T.ADD,
        T.SUBTRACT,
        T.MULTIPLY,
        T.MULTIPLY_IMPLICIT,
        T.FRACTION,
        T.DIVIDE,
        T.POWER,
        T.NEGATIVE,
    )
    if (
        folded.type in arithmetic
        and children
        and all(child.type is T.CONSTANT for child in children)
    ):
        with contextlib.suppress(SolveError, TypeError, ValueError):
            return from_sympy(to_sympy(folded))
    if folded.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT):
        kept = [
            child for child in children if not (child.type is T.CONSTANT and child.value in ("1",))
        ]
        if not kept:
            return _num(1)
        if len(kept) == 1:
            return kept[0]
        return CoreNode(type=folded.type, value=folded.value, children=kept)
    if folded.type is T.ADD:
        kept = [
            child for child in children if not (child.type is T.CONSTANT and child.value == "0")
        ]
        if not kept:
            return _num(0)
        if len(kept) == 1:
            return kept[0]
        return CoreNode(type=folded.type, value=folded.value, children=kept)
    return folded


def _literal_substitution(node: CoreNode, variable: str, point: CoreNode) -> CoreNode:
    """``C·e^x`` at ``x = 0`` becomes ``C·e⁰`` for the condition stage."""
    return _reduce_constants(_substitute_node(node, variable, point))


def _constants_last(node: CoreNode) -> CoreNode:
    """Order a sum so the terms with the constant ``C`` come last (``x + C``)."""
    if node.type in (T.ADD, T.SUBTRACT):
        parts = _flatten(node)
        parts.sort(key=lambda item: _has_constant(item[1]))
        return _chain(parts)
    if not node.children:
        return node
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[_constants_last(child) for child in node.children],
    )


def _flatten(node: CoreNode, negative: bool = False) -> list[tuple[bool, CoreNode]]:
    if node.type is T.ADD:
        out: list[tuple[bool, CoreNode]] = []
        for child in node.children:
            out.extend(_flatten(child, negative))
        return out
    if node.type is T.SUBTRACT and len(node.children) == 2:
        return [
            *_flatten(node.children[0], negative),
            *_flatten(node.children[1], not negative),
        ]
    if node.type is T.NEGATIVE and len(node.children) == 1:
        return _flatten(node.children[0], not negative)
    return [(negative, node)]


def _has_constant(node: CoreNode) -> bool:
    return any(
        item.type is T.VARIABLE and item.value and item.value.startswith("C")
        for item in node.walk()
    )


def _log_abs(expression: sympy.Expr, symbol: sympy.Symbol) -> sympy.Expr:
    """``ln y`` -> ``ln|y|`` for the logarithm of the dependent variable."""
    return expression.replace(
        lambda item: isinstance(item, sympy.log) and item.args[0].has(symbol),
        lambda item: sympy.log(sympy.Abs(item.args[0])),
    )


def _formula(expression: sympy.Expr, xsym: sympy.Symbol, symbol: sympy.Symbol) -> CoreNode:
    """A stage formula with ``ln|y|`` for the dependent variable."""
    return from_sympy(_clean_expression(_log_abs(expression, symbol), xsym, 1))


def _linear_in(
    expression: sympy.Expr, symbol: sympy.Symbol
) -> tuple[sympy.Expr, sympy.Expr] | None:
    """``(a, b)`` for ``expression = a·symbol + b``, or ``None``."""
    a = sympy.simplify(sympy.diff(expression, symbol))
    if a.has(symbol):
        return None
    b = sympy.simplify(expression - a * symbol)
    if b.has(symbol):
        return None
    return a, b


def _normalize_constant(expression: sympy.Expr) -> sympy.Expr:
    """Absorb a numeric factor of the constant term (``(C·e^(x²) − 1)/2``)."""
    if not expression.has(_C):
        return expression
    derivative = sympy.diff(expression, _C)
    if derivative.has(_C) or (expression - derivative * _C).has(_C):
        return expression
    factor, _rest = derivative.as_coeff_Mul()
    if factor.is_number and factor not in (1, -1):
        with contextlib.suppress(TypeError, ValueError):
            return sympy.simplify(expression.subs(_C, _C / factor))
    return expression


def _rescale_constant(expression: sympy.Expr) -> sympy.Expr:
    """Rename ``C`` by a constant factor to the shortest textbook form.

    ``2x/(x² + 2C)`` is written ``2x/(x² + C)``: the family is the same, and
    the normalized constant carries no meaning for the student.
    """
    if not expression.has(_C):
        return expression
    try:
        best = expression
        best_ops = sympy.count_ops(sympy.simplify(expression))
        for factor in (2, 3, 4, sympy.Rational(1, 2), sympy.Rational(1, 3)):
            candidate = sympy.simplify(expression.subs(_C, _C / factor))
            operations = sympy.count_ops(candidate)
            if operations < best_ops:
                best, best_ops = candidate, operations
    except (TypeError, ValueError):
        return expression
    return best


def _rename_constant(expression: sympy.Expr) -> sympy.Expr:
    """Give the constant of a solved answer the form the textbook uses."""
    if expression.has(sympy.exp(_C0)):
        expression = expression.replace(sympy.exp(_C0), _C)
    if _C0 not in expression.free_symbols:
        return expression
    plain = expression.subs(_C0, _C)
    flipped = expression.subs(_C0, -_C)
    return min((plain, flipped), key=lambda item: (str(item).count("-"), len(str(item))))


# ── the card ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class _Card:
    """A built card: its header, stages, general solution and its answer node."""

    header: str
    stages: list[Step] = field(default_factory=list)
    general: sympy.Expr | sympy.Eq = field(default_factory=lambda: sympy.Integer(0))
    node: CoreNode | None = None
    explicit: bool = True


def _solved_derivative(
    equation: sympy.Eq, yfun: sympy.Function, xsym: sympy.Symbol
) -> sympy.Expr | None:
    """The right side of ``y′ = f(x, y)`` solved from the equation."""
    derivative = sympy.Derivative(yfun(xsym), xsym)
    try:
        solutions = sympy.solve(equation, derivative)
    except (NotImplementedError, TypeError, ValueError):
        return None
    if len(solutions) != 1:
        return None
    return sympy.simplify(solutions[0])


def first_order_card(
    problem: CoreNode,
    equation: sympy.Eq,
    dep: str,
    ind: str,
    kind: str,
    conditions: list[tuple[int, sympy.Expr, sympy.Expr, CoreNode, CoreNode]],
) -> _CardAnswer | None:
    """Build the textbook card of a first-order equation, or ``None``.

    ``problem`` is the equality the student typed, ``equation`` the same as
    ``Eq(lhs − rhs, 0)`` with ``y`` already replaced by ``y(x)``.  When the
    method has no transparent card, or its answer does not pass
    ``checkodesol``, the caller keeps the previous two-step answer.
    """
    if len(conditions) > 1 or (conditions and conditions[0][0] != 0):
        return None
    xsym = sympy.Symbol(ind)
    yfun = sympy.Function(dep)
    symbol = sympy.Symbol(dep)
    derivative = _solved_derivative(equation, yfun, xsym)
    if derivative is None:
        return None
    rhs = derivative.subs(yfun(xsym), symbol)
    if rhs.has(yfun(xsym)):
        return None

    card: _Card | None
    if kind == _KIND_SEPARATION:
        card = _separable_card(problem, rhs, xsym, symbol, dep)
    elif kind == _KIND_HOMOGENEOUS:
        card = _homogeneous_card(problem, rhs, xsym, symbol)
    elif kind == _KIND_LINEAR:
        card = _linear_card(problem, rhs, xsym, symbol, dep, _HEADER_LINEAR)
    elif kind == _KIND_BERNOULLI:
        card = _bernoulli_card(problem, rhs, xsym, symbol, dep)
    elif kind == _KIND_EXACT:
        card = _exact_card(problem, equation, xsym, symbol, yfun, dep)
    else:
        return None
    if card is None or card.node is None:
        return None
    if not _verified(equation, card.general, xsym, yfun, symbol):
        return None

    result = SolveResult(header=card.header)
    answer = card.node
    if conditions:
        applied = _with_condition(card, conditions[0], xsym, symbol, dep)
        if applied is None:
            return None
        particular, stages = applied
        if not _verified(equation, particular, xsym, yfun, symbol):
            return None
        result.add_group(_KEY_SOLVE, *card.stages)
        result.add_group(_HEADER_CONDITION, *stages)
        last = stages[-1].right
        if last is None:
            return None
        answer = last
    else:
        # A lost y = 0 is the last stage of the method, not a nameless note:
        # every stage of a card lives under its owner heading (ODE4 review).
        singular = _singular_solution(equation, yfun(xsym), dep, xsym, kind, answer)
        if singular is not None:
            card.stages.append(_fact(_KIND_SINGULAR, singular))
        result.add_group(_KEY_SOLVE, *card.stages)
    result.set_solution(answer)
    return card.header, result, answer


# ── separable ─────────────────────────────────────────────────────────


def _separable_card(
    problem: CoreNode,
    rhs: sympy.Expr,
    xsym: sympy.Symbol,
    symbol: sympy.Symbol,
    dep: str,
) -> _Card | None:
    expression = sympy.cancel(sympy.together(sympy.expand(rhs)))
    y_part, x_part = expression.as_independent(xsym)
    if y_part.has(xsym) or x_part.has(symbol) or y_part == 0:
        expression = sympy.factor(expression)
        y_part, x_part = expression.as_independent(xsym)
    if y_part.has(xsym) or x_part.has(symbol) or y_part == 0:
        return None
    if sympy.simplify(expression - y_part * x_part) != 0:
        return None
    # The number goes with dx as in the book: dy = 2x dx, dy/y = 2x dx (not dy/2 = x dx).
    coefficient, y_part = y_part.as_coeff_Mul()
    x_part = coefficient * x_part
    left = sympy.integrate(1 / y_part, symbol)
    right = sympy.integrate(x_part, xsym)
    if left.has(sympy.Integral) or right.has(sympy.Integral):
        return None

    card = _Card(_HEADER_SEPARABLE)
    card.stages.append(
        _fact(
            _KEY_SEP_DERIVATIVE,
            _eq(
                _node(T.PRIME, _var(dep)),
                _node(T.DERIVATION1_DIFF, _var(str(xsym)), _var(dep)),
            ),
        )
    )
    separated = _eq(_separated_left(y_part, xsym, dep), _separated_right(x_part, xsym))
    card.stages.append(_fact(_KEY_SEP_SEPARATE, separated))
    left_side, left_detail = _integral(_expr(1 / y_part, xsym)), _detail(1 / y_part, symbol)
    if y_part == 1:
        # ∫1 has no differential slot and would draw dx: y = ∫f(x) dx as in the book.
        left_side, left_detail = _var(dep), None
    both = _eq(left_side, _integral(_expr(x_part, xsym)))
    card.stages.extend(
        _stages(
            _KEY_SEP_INTEGRATE,
            separated,
            both,
            subresult=_combined(left_detail, _detail(x_part, xsym)),
        )
    )

    implicit = _separable_implicit(left, right, xsym, symbol)
    answer: sympy.Expr | None = None
    kind = ""
    if implicit is None:
        answer, kind = _separable_explicit(y_part, left, right, xsym, symbol)
    if implicit is not None:
        answer_left, answer_right = implicit
        primitive = _eq(
            _plain(answer_left, xsym, symbol),
            _plain(answer_right, xsym, symbol),
        )
        primitive = _constants_last(primitive)
        card.stages.extend(_stages(_KEY_SEP_IMPLICIT, both, primitive))
        card.general = sympy.Eq(answer_left, answer_right)
        card.node = primitive
        card.explicit = False
        return card
    if answer is None:
        return None
    primitive = _eq(_formula(left, xsym, symbol), _formula(right + _C0, xsym, symbol))
    primitive = _constants_last(primitive)
    if sympy.simplify(x_part - 1 / sympy.cos(xsym)) == 0:
        primitive = _eq(
            _formula(left, xsym, symbol),
            _formula(sympy.log(sympy.tan(xsym) + 1 / sympy.cos(xsym)) + _C0, xsym, symbol),
        )
        primitive = _constants_last(primitive)
    value = _expr(answer, xsym)
    if answer.is_Add and sympy.diff(answer, _C).is_number:
        value = _terms_in_x_order(answer, xsym, symbol)
    node = _eq(_var(dep), value)
    if y_part == 1:
        # y = ∫f(x) dx gives y with C at once: no C₀ to rename.
        card.stages.extend(_stages(_KEY_SEP_PRIMITIVE, both, node))
        card.general = answer
        card.node = node
        return card
    card.stages.extend(_stages(_KEY_SEP_PRIMITIVE, both, primitive))
    key = {
        "log": _KEY_SEP_EXPRESS_LOG,
        "rename": _KEY_SEP_EXPRESS_RENAME,
    }.get(kind, _KEY_SEP_EXPRESS)
    if dep != "y":
        key = f"{key}_{dep}"
    stages = _stages(key, primitive, node)
    if kind == "log":
        # C = ±e^(C₀) drawn as a formula, not typed in the text.
        for stage in stages:
            stage.args = [_node(T.EXP, _var("C0"))]
    card.stages.extend(stages)
    card.general = answer
    card.node = node
    return card


def _separated_left(y_part: sympy.Expr, xsym: sympy.Symbol, dep: str) -> CoreNode:
    if y_part == 1:
        return _var(f"d{dep}")
    return _fraction(_var(f"d{dep}"), _expr(y_part, xsym))


def _separated_right(x_part: sympy.Expr, xsym: sympy.Symbol) -> CoreNode:
    if x_part == 1:
        return _var("dx")
    numerator, denominator = sympy.fraction(sympy.together(x_part))
    if numerator == 1 and denominator != 1:
        return _fraction(_var("dx"), _expr(denominator, xsym))  # dx/x, not 1/x dx
    if x_part == -1:
        return _node(T.NEGATIVE, _var("dx"))
    return _product(_expr(x_part, xsym), _var("dx"))


def _separable_implicit(
    left: sympy.Expr, right: sympy.Expr, xsym: sympy.Symbol, symbol: sympy.Symbol
) -> tuple[sympy.Expr, sympy.Expr] | None:
    """The implicit answer when the book leaves it (``arctg y = arctg x + C``)."""
    inverse = (sympy.atan, sympy.asin, sympy.acos)
    if any(left.has(function) or right.has(function) for function in inverse):
        return left, right + _C
    try:
        solutions = sympy.solve(sympy.Eq(left, right + _C0), symbol)
    except (NotImplementedError, TypeError, ValueError):
        solutions = []
    if len(solutions) == 1:
        return None
    difference = sympy.factor(sympy.cancel(sympy.together(left - right)))
    if difference.could_extract_minus_sign():
        difference = -difference
    numerator, denominator = sympy.fraction(difference)
    if denominator.is_number and denominator != 1:
        difference = sympy.expand(numerator)
    return difference, _C


def _separable_explicit(
    y_part: sympy.Expr,
    left: sympy.Expr,
    right: sympy.Expr,
    xsym: sympy.Symbol,
    symbol: sympy.Symbol,
) -> tuple[sympy.Expr | None, str]:
    """The explicit answer of a separable equation and the shape of its constant."""
    coefficient, body = left.as_coeff_Mul()
    if isinstance(body, sympy.log) and body.args[0].has(symbol):
        argument = body.args[0]
        slope = sympy.diff(argument, symbol)
        offset = sympy.simplify(argument - slope * symbol)
        if slope != 0 and not slope.has(symbol) and not offset.has(symbol):
            exponent = sympy.simplify(right / coefficient)
            answer = (_C * sympy.exp(exponent) - offset) / slope
            return _normalize_constant(sympy.simplify(answer)), (
                "log" if coefficient == 1 else "rename"
            )

    linear = _linear_in(left, symbol)
    if linear is not None:
        a, b = linear
        if a != 0:
            return _normalize_constant(sympy.simplify((right + _C - b) / a)), ""

    product = sympy.simplify(left * symbol)
    inverse = _linear_in(product, symbol)
    if inverse is not None:
        slope, offset = inverse
        if offset != 0:
            answer = offset / (right + _C - slope)
            return _normalize_constant(sympy.simplify(answer)), ""

    coefficient, body = left.as_coeff_Mul()
    if isinstance(body, sympy.exp):
        argument = body.args[0]
        slope = sympy.diff(argument, symbol)
        offset = sympy.simplify(argument - slope * symbol)
        if slope != 0 and not slope.has(symbol) and not offset.has(symbol):
            exponent = sympy.log((right + _C0) / coefficient)
            answer = _rename_constant(sympy.simplify((exponent - offset) / slope))
            return answer, ""

    try:
        solutions = sympy.solve(sympy.Eq(left, right + _C0), symbol)
    except (NotImplementedError, TypeError, ValueError):
        return None, ""
    if len(solutions) == 1:
        return _rename_constant(sympy.simplify(solutions[0])), ""
    return None, ""


# ── homogeneous ───────────────────────────────────────────────────────


def _homogeneous_card(
    problem: CoreNode, rhs: sympy.Expr, xsym: sympy.Symbol, symbol: sympy.Symbol
) -> _Card | None:
    substituted = sympy.powdenest(sympy.simplify(rhs.subs(symbol, _U * xsym)), force=True)
    function = sympy.cancel(substituted)
    if function.has(xsym) or function.has(symbol):
        return None
    reduced = sympy.simplify(function - _U)
    if reduced == 0:
        return None
    primitive = sympy.integrate(1 / reduced, _U)
    if primitive.has(sympy.Integral):
        return None

    card = _Card(_HEADER_HOMOGENEOUS)
    card.stages.append(
        _fact(
            _KEY_HOM_FORM,
            _eq(_node(T.PRIME, _var("y")), _expr(rhs, xsym)),
        )
    )
    ux = _product(_node(T.PRIME, _var("u")), _var(str(xsym)))
    substituted_y = _eq(_var("y"), _product(_var("u"), _var(str(xsym))))
    card.stages.append(
        _fact(
            _KEY_HOM_SUBSTITUTE,
            substituted_y,
            _eq(_node(T.PRIME, _var("y")), _chain([(False, ux), (False, _var("u"))])),
            args=[substituted_y],
        )
    )
    substituted_equation = _eq(
        _chain([(False, ux), (False, _var("u"))]),
        _expr(function, xsym),
    )
    card.stages.extend(_stages(_KEY_HOM_EQUATION, problem, substituted_equation))
    reduced_equation = _eq(ux, _expr(reduced, xsym))
    card.stages.extend(_stages(_KEY_HOM_REDUCE, substituted_equation, reduced_equation))
    separated = _eq(
        _fraction(_var("du"), _expr(reduced, xsym)),
        _fraction(_var("dx"), _var(str(xsym))),
    )
    card.stages.append(_fact(_KEY_HOM_SEPARATE, separated))
    both = _eq(
        _integral(_expr(1 / reduced, xsym)),
        _integral(_fraction(_num(1), _var(str(xsym)))),
    )
    card.stages.extend(
        _stages(
            _KEY_HOM_INTEGRATE,
            separated,
            both,
            subresult=_combined(
                _detail(1 / reduced, _U),
                _detail(1 / xsym, xsym),
            ),
        )
    )
    solved = _eq(
        _formula(primitive, xsym, _U),
        _chain([(False, _formula(sympy.log(sympy.Abs(xsym)), xsym, symbol)), (False, _var("C"))]),
    )
    card.stages.extend(_stages(_KEY_HOM_PRIMITIVE, both, solved))

    answer = _homogeneous_answer(reduced, primitive, xsym, symbol)
    if answer is None:
        return None
    general, node = answer
    if not node.structural_eq(solved):
        card.stages.extend(_stages(_KEY_HOM_BACK, solved, node))
    card.general = general
    card.node = node
    return card


def _homogeneous_answer(
    reduced: sympy.Expr, primitive: sympy.Expr, xsym: sympy.Symbol, symbol: sympy.Symbol
) -> tuple[sympy.Expr | sympy.Eq, CoreNode] | None:
    """Back-substituted answer in the form of the book (``y² = 2x²(ln|x| + C)``)."""
    if primitive == sympy.asinh(_U):
        # The book form of x·y′ = y + √(x² + y²): the whole left side
        # against Cx², not a fraction with the constant on the right (ODE4).
        node = sympy.Eq(symbol + sympy.sqrt(xsym**2 + symbol**2), _C * xsym**2)
        # checkodesol only accepts the divided form: the multiplied one has an
        # extra C after differentiation, so verification keeps the old shape.
        general = sympy.Eq(
            (symbol + sympy.sqrt(xsym**2 + symbol**2)) / xsym**2,
            _C,
        )
        return general, _constants_last(_equation_node(node, xsym, symbol))
    if sympy.simplify(1 / reduced) == _U:
        general = sympy.Eq(symbol**2 / xsym**2, 2 * (sympy.log(xsym) + _C))
        node = _eq(
            _plain(general.lhs, xsym, symbol),
            _product(
                _num(2),
                _bracket(
                    _chain(
                        [
                            (False, _plain(sympy.log(xsym), xsym, symbol)),
                            (False, _var("C")),
                        ]
                    )
                ),
            ),
        )
        return general, node
    try:
        solutions = sympy.solve(sympy.Eq(primitive, sympy.log(xsym) + _C), _U)
    except (NotImplementedError, TypeError, ValueError):
        solutions = []
    if len(solutions) == 1:
        answer = sympy.simplify(xsym * solutions[0])
        return answer, _constants_last(_eq(_var("y"), _expr(answer, xsym)))
    difference = sympy.simplify(primitive - sympy.log(xsym))
    back = difference.subs(_U, symbol / xsym)
    numerator, denominator = sympy.fraction(sympy.cancel(sympy.together(back)))
    if denominator.is_number and denominator != 1:
        back = sympy.expand(numerator)
    general = sympy.Eq(back, _C)
    return general, _constants_last(_equation_node(general, xsym, symbol))


def _equation_node(equation: sympy.Eq, xsym: sympy.Symbol, symbol: sympy.Symbol) -> CoreNode:
    """An implicit answer as a node, with ``ln|y|`` and ``ln|x|``."""
    return _eq(
        _plain(equation.lhs, xsym, symbol),
        _plain(equation.rhs, xsym, symbol),
    )


def _terms_in_x_order(expression: sympy.Expr, xsym: sympy.Symbol, symbol: sympy.Symbol) -> CoreNode:
    """An additive formula with the highest power of the independent variable first."""
    terms = list(sympy.Add.make_args(sympy.expand(expression)))

    def degree(term: sympy.Expr) -> int:
        try:
            return int(sympy.Poly(term, xsym).degree())
        except (sympy.PolynomialError, TypeError, ValueError):
            return -1

    parts: list[tuple[bool, CoreNode]] = []
    for term in sorted(terms, key=lambda item: (degree(item), str(item)), reverse=True):
        negative = bool(term.could_extract_minus_sign())
        parts.append((negative, _plain(-term if negative else term, xsym, symbol)))
    return _chain(parts)


# ── linear ────────────────────────────────────────────────────────────


def _linear_card(
    problem: CoreNode,
    rhs: sympy.Expr,
    xsym: sympy.Symbol,
    symbol: sympy.Symbol,
    dep: str,
    header: str,
) -> _Card | None:
    linear = _linear_in(rhs, symbol)
    if linear is None:
        return None
    a, q = linear
    p = sympy.simplify(-a)
    if sympy.simplify(q) == 0:
        return None
    primitive_p = sympy.integrate(p, xsym)
    if primitive_p.has(sympy.Integral):
        return None
    v_expr = sympy.simplify(sympy.exp(-primitive_p))
    quotient = sympy.simplify(q / v_expr)
    u_primitive = sympy.integrate(quotient, xsym)
    if u_primitive.has(sympy.Integral):
        return None

    y = _var(dep)
    u, v = _var("u"), _var("v")
    u_prime, v_prime = _node(T.PRIME, u), _node(T.PRIME, v)
    substitute_key = _KEY_LIN_SUBSTITUTE if dep == "y" else _KEY_LIN_SUBSTITUTE_Z
    insert_key = _KEY_LIN_INSERT if dep == "y" else _KEY_LIN_INSERT_Z
    back_key = _KEY_LIN_BACK if dep == "y" else _KEY_LIN_BACK_Z
    card = _Card(header)
    substituted = _eq(y, _product(u, v))
    card.stages.append(
        _fact(
            substitute_key,
            substituted,
            _eq(
                _node(T.PRIME, y),
                _chain([(False, _product(u_prime, v)), (False, _product(u, v_prime))]),
            ),
            args=[substituted],
        )
    )
    p_node = _expr(p, xsym)
    q_node = _expr(q, xsym)
    v_prime_plus = _chain([(False, v_prime), (False, _times(p, v, xsym))])
    inserted = _eq(
        _chain([(False, _product(u_prime, v)), (False, _product(u, _bracket(v_prime_plus)))]),
        q_node,
    )
    card.stages.extend(_stages(insert_key, problem, inserted))
    zero_equation = _eq(_chain([(False, v_prime), (False, _times(p, v, xsym))]), _num(0))
    # The sentence names the rule with p, the stage below shows the problem's own
    # equation: the same formula twice in a row would waste the screen.
    rule = _eq(_chain([(False, v_prime), (False, _product(_var("p"), v))]), _num(0))
    card.stages.append(_fact(_KEY_LIN_CHOOSE_V, zero_equation, args=[rule]))
    symbolic = _eq(v, _node(T.EXP, _node(T.NEGATIVE, _integral(p_node))))
    card.stages.extend(_stages(_KEY_LIN_V, zero_equation, symbolic, subresult=_detail(p, xsym)))
    v_node = _expr(v_expr, xsym)
    card.stages.append(_fact(_KEY_LIN_V_VALUE, _eq(v, v_node)))
    u_equation = _eq(_product(u_prime, v), q_node)
    card.stages.extend(_stages(_KEY_LIN_U_EQUATION, inserted, u_equation))
    u_symbolic = _eq(
        u,
        _chain([(False, _integral(_expr(quotient, xsym))), (False, _var("C"))]),
    )
    card.stages.extend(
        _stages(_KEY_LIN_U, u_equation, u_symbolic, subresult=_detail(quotient, xsym))
    )
    u_plus = _chain([(False, _expr(u_primitive, xsym)), (False, _var("C"))])
    card.stages.append(_fact(_KEY_LIN_U_VALUE, _eq(u, u_plus)))

    general, node = _linear_answer(v_expr, u_primitive, xsym, dep)
    # Substitute u and v into y = uv first, simplify only afterwards: the old
    # single stage jumped from u = … straight to the answer (ODE3 review).
    back_left = _eq(_var(dep), _product(_var("u"), _var("v")))
    back_substituted = _eq(
        _var(dep),
        _product(_bracketed(u_plus), _expr(sympy.simplify(v_expr), xsym)),
    )
    card.stages.extend(_stages(back_key, back_left, back_substituted))
    card.stages.extend(_stages(_KEY_LIN_SIMPLIFY, back_substituted, node))
    card.general = general
    card.node = node
    return card


def _times(coefficient: sympy.Expr, node: CoreNode, xsym: sympy.Symbol) -> CoreNode:
    """``coefficient·node`` without a visible ``1·`` (and with a leading minus)."""
    if coefficient == 1:
        return node
    if coefficient == -1:
        return _node(T.NEGATIVE, node)
    negative = bool(coefficient.could_extract_minus_sign())
    magnitude = -coefficient if negative else coefficient
    piece = _product(_bracketed(_expr(magnitude, xsym)), node)
    return _node(T.NEGATIVE, piece) if negative else piece


def _linear_answer(
    v_expr: sympy.Expr, u_primitive: sympy.Expr, xsym: sympy.Symbol, dep: str
) -> tuple[sympy.Expr, CoreNode]:
    """``y = particular + C·v`` with the particular part first (``x − 1 + Ce^(−x)``)."""
    particular = sympy.simplify(v_expr * u_primitive)
    homogeneous = _normalize_constant(sympy.simplify(v_expr) * _C)
    homogeneous = _rescale_constant(homogeneous)
    y = _var(dep)
    if particular == 0:
        return homogeneous, _eq(y, _expr(homogeneous, xsym))
    if _is_trig(sympy.simplify(v_expr)):
        general = sympy.simplify(homogeneous + particular)
        node = _constants_last(
            _eq(
                y,
                _product(
                    _expr(sympy.simplify(v_expr), xsym),
                    _bracket(
                        _chain(
                            [
                                (False, _expr(sympy.simplify(u_primitive), xsym)),
                                (False, _var("C")),
                            ]
                        )
                    ),
                ),
            )
        )
        return general, node
    homogeneous_node = _expr(homogeneous, xsym)
    general = sympy.simplify(particular + homogeneous)
    particular_node = _terms_in_x_order(particular, xsym, sympy.Symbol(dep))
    if particular.is_number:
        chain = _chain([(False, homogeneous_node), *_flatten(particular_node)])
    else:
        chain = _chain([*_flatten(particular_node), (False, homogeneous_node)])
    return general, _eq(y, chain)


def _is_trig(expression: sympy.Expr) -> bool:
    return bool(expression.atoms(sympy.sin, sympy.cos, sympy.tan))


# ── Bernoulli ─────────────────────────────────────────────────────────


def _bernoulli_card(
    problem: CoreNode, rhs: sympy.Expr, xsym: sympy.Symbol, symbol: sympy.Symbol, dep: str
) -> _Card | None:
    numerator, denominator = sympy.fraction(sympy.cancel(sympy.together(sympy.expand(rhs))))
    if denominator.has(symbol):
        return None
    try:
        polynomial = sympy.Poly(sympy.expand(numerator), symbol)
    except (sympy.PolynomialError, TypeError, ValueError):
        return None
    degrees = {monomial[0] for monomial in polynomial.monoms()}
    if len(degrees) != 2 or 1 not in degrees:
        return None
    n_value = max(degrees)
    if n_value < 2:
        return None
    n = sympy.Integer(n_value)
    q = sympy.simplify(polynomial.coeff_monomial(symbol**n) / denominator)
    p = sympy.simplify(-polynomial.coeff_monomial(symbol) / denominator)
    order = 1 - n

    y = _var(dep)
    y_prime = _node(T.PRIME, y)
    card = _Card(_HEADER_BERNOULLI)
    power = _power(y, _num(int(n)))
    divided = _eq(
        _chain(
            [
                (False, _fraction(y_prime, power)),
                _signed(p * symbol**order, xsym),
            ]
        ),
        _expr(q, xsym),
    )
    card.stages.extend(_stages(_KEY_BERN_DIVIDE, problem, divided))
    z_prime_formula = _fraction(_node(T.PRIME, y), power)
    if order == -1:
        z_prime_formula = _node(T.NEGATIVE, z_prime_formula)
    elif order != 1:
        z_prime_formula = _product(_expr(sympy.Integer(order), xsym), z_prime_formula)
    substituted_z = _eq(_var("z"), _power(y, _expr(sympy.Integer(order), xsym)))
    card.stages.append(
        _fact(
            _KEY_BERN_SUBSTITUTE,
            substituted_z,
            _eq(_node(T.PRIME, _var("z")), z_prime_formula),
            args=[substituted_z],
        )
    )
    z = _var("z")
    z_prime = _node(T.PRIME, z)
    p_z = sympy.simplify(order * p)
    q_z = sympy.simplify(order * q)
    z_equation = _eq(
        _chain([(False, z_prime), _signed(p_z * _Z, xsym)]),
        _expr(q_z, xsym),
    )
    nested_rhs = sympy.simplify(q_z - p_z * _Z)
    nested = _linear_card(z_equation, nested_rhs, xsym, _Z, "z", _HEADER_LINEAR)
    if nested is None or nested.node is None:
        return None
    card.stages.append(
        Step(
            z_equation,
            None,
            _KEY_BERN_LINEAR,
            subresult=_as_card(nested),
        )
    )
    z_solution = nested.general
    if not isinstance(z_solution, sympy.Expr):
        return None
    answer = sympy.simplify(z_solution ** (1 / order))
    answer = _rescale_constant(answer)
    node = _eq(y, _expr(answer, xsym))
    inverse = _eq(y, _power(z, _expr(sympy.Integer(1) / order, xsym)))
    card.stages.extend(_stages(_KEY_BERN_BACK, nested.node, node, args=[inverse]))
    card.general = answer
    card.node = node
    return card


def _as_card(card: _Card) -> SolveResult:
    """The stages of a built card as its own nested result (no «Подробнее» text)."""
    out = SolveResult(header=card.header)
    out.add_group(_KEY_SOLVE, *card.stages)
    out.set_solution(card.node if card.node is not None else _num(0))
    return out


# ── exact ─────────────────────────────────────────────────────────────


def _exact_card(
    problem: CoreNode,
    equation: sympy.Eq,
    xsym: sympy.Symbol,
    symbol: sympy.Symbol,
    yfun: sympy.Function,
    dep: str,
) -> _Card | None:
    expression = sympy.together(equation.lhs - equation.rhs)
    numerator, _denominator = sympy.fraction(expression)
    derivative = sympy.Derivative(yfun(xsym), xsym)
    coefficient = sympy.simplify(numerator.diff(derivative))
    free = sympy.simplify(numerator - coefficient * derivative)
    p = sympy.simplify(free.subs(yfun(xsym), symbol))
    q = sympy.simplify(coefficient.subs(yfun(xsym), symbol))
    if p == 0 or q == 0:
        return None
    if sympy.simplify(sympy.diff(p, symbol) - sympy.diff(q, xsym)) != 0:
        return None
    first = sympy.integrate(p, xsym)
    remainder = sympy.simplify(q - sympy.diff(first, symbol))
    potential = sympy.simplify(first + sympy.integrate(remainder, symbol))
    if potential.has(sympy.Integral):
        return None

    p_node, q_node = _expr(p, xsym), _expr(q, xsym)
    potential_node = _terms_in_x_order(potential, xsym, symbol)
    card = _Card(_HEADER_EXACT)
    differential = _eq(
        _chain(
            [
                (False, _product(_bracketed(p_node), _var("dx"))),
                (False, _product(_bracketed(q_node), _var("dy"))),
            ]
        ),
        _num(0),
    )
    card.stages.extend(_stages(_KEY_EX_DIFFERENTIAL, problem, differential))
    card.stages.append(_fact(_KEY_EX_PQ, _eq(_var("P"), p_node), _eq(_var("Q"), q_node)))
    left_derivative = _node(T.DERIVATION1_DIFF, _var(str(symbol)), p_node)
    right_derivative = _node(T.DERIVATION1_DIFF, _var(str(xsym)), q_node)
    card.stages.append(
        _fact(
            _KEY_EX_CHECK,
            _node(T.EQUALS, left_derivative, right_derivative, _expr(sympy.diff(p, symbol), xsym)),
        )
    )
    card.stages.append(_fact(_KEY_EX_POTENTIAL, _eq(_var("U"), potential_node)))
    general = sympy.Eq(sympy.expand(potential), _C)
    answer = _eq(potential_node, _var("C"))
    card.stages.extend(_stages(_KEY_EX_ANSWER, _eq(_var("U"), potential_node), answer))
    card.general = general
    card.node = answer
    card.explicit = False
    return card


# ── Cauchy condition ──────────────────────────────────────────────────


def _with_condition(
    card: _Card,
    condition: tuple[int, sympy.Expr, sympy.Expr, CoreNode, CoreNode],
    xsym: sympy.Symbol,
    symbol: sympy.Symbol,
    dep: str,
) -> tuple[sympy.Expr | sympy.Eq, list[Step]] | None:
    """Substitute ``y(x₀) = y₀`` into the general solution and find ``C``."""
    _order, x_zero, y_zero, x_zero_node, y_zero_node = condition
    condition_node = _eq(
        _node(T.EVALUATE_EXPRESSION, _var(dep), x_zero_node),
        y_zero_node,
    )
    stages = [_fact(_KEY_CONDITION, condition_node)]
    general = card.general
    if isinstance(general, sympy.Eq):
        fixed = {symbol: y_zero, xsym: x_zero}
        try:
            solutions = sympy.solve(
                sympy.Eq(general.lhs.subs(fixed), general.rhs.subs(fixed)),
                _C,
            )
        except (NotImplementedError, TypeError, ValueError):
            return None
        if len(solutions) != 1:
            return None
        value = sympy.simplify(solutions[0])
        particular = sympy.Eq(general.lhs, sympy.simplify(general.rhs.subs(_C, value)))
        particular_node = _eq(
            _formula(particular.lhs, xsym, symbol),
            _formula(particular.rhs, xsym, symbol),
        )
        substituted = _eq(
            _plain(general.lhs.subs(fixed), xsym, symbol),
            _plain(general.rhs.subs(fixed), xsym, symbol),
        )
    else:
        value_at = sympy.simplify(general.subs(xsym, x_zero))
        try:
            solutions = sympy.solve(sympy.Eq(value_at, y_zero), _C)
        except (NotImplementedError, TypeError, ValueError):
            return None
        if len(solutions) != 1:
            return None
        value = sympy.simplify(solutions[0])
        particular = sympy.simplify(general.subs(_C, value))
        if particular.is_Add:
            particular_node = _eq(
                _var(dep),
                _terms_in_x_order(particular, xsym, symbol),
            )
        else:
            particular_node = _eq(_var(dep), _expr(particular, xsym))
        substituted = _eq(_expr(value_at, xsym), y_zero_node)
        if card.node is not None and card.node.type is T.EQUALS and len(card.node.children) == 2:
            literal = _literal_substitution(card.node.children[1], str(xsym), x_zero_node)
            has_function = any(
                node.type in (T.EXP, T.SIN, T.COS, T.TAN, T.COT, T.LN, T.LOG10)
                for node in literal.walk()
            )
            substituted = _eq(y_zero_node, literal) if has_function else _eq(literal, y_zero_node)
    constant_fact = _eq(_var("C"), _expr(value, xsym))
    if substituted.structural_eq(constant_fact):
        stages.append(_fact(_KEY_CONDITION_VALUE, constant_fact))
    else:
        stages.append(_fact(_KEY_CONDITION_SUBSTITUTE, substituted))
        stages.append(_fact(_KEY_CONDITION_VALUE, constant_fact))
    if card.node is not None:
        stages.extend(_stages(_KEY_CONDITION_ANSWER, card.node, particular_node))
    if stages[-1].right is None:
        return None
    return particular, stages


# ── verification ──────────────────────────────────────────────────────


def _verified(
    equation: sympy.Eq,
    value: sympy.Expr | sympy.Eq,
    xsym: sympy.Symbol,
    yfun: sympy.Function,
    symbol: sympy.Symbol,
) -> bool:
    """Does the answer turn the equation into an identity (``checkodesol``)?"""
    if isinstance(value, sympy.Eq):
        solution = sympy.Eq(
            value.lhs.subs(symbol, yfun(xsym)),
            value.rhs.subs(symbol, yfun(xsym)),
        )
    else:
        solution = sympy.Eq(yfun(xsym), value.subs(symbol, yfun(xsym)))
    try:
        if sympy.checkodesol(equation, solution, solve_for_func=False)[0]:
            return True
    except (NotImplementedError, TypeError, ValueError):
        return False
    positive = sympy.Symbol(str(xsym), positive=True)

    def on_positive(expression: sympy.Basic) -> sympy.Basic:
        return expression.subs(xsym, positive).subs(sympy.Abs(positive), positive)

    try:
        return bool(
            sympy.checkodesol(
                on_positive(equation),
                on_positive(solution),
                solve_for_func=False,
            )[0]
        )
    except (NotImplementedError, TypeError, ValueError):
        return False


__all__ = ["first_order_card"]
