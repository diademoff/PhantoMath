"""Textbook cards of a definite integral.

The first card a student sees names the theorem and shows its formula:

* Newton–Leibniz: ``∫ₐᵇ f dx = F(b) − F(a)``, the antiderivative from the
  indefinite textbook card (nested «Подробнее» without ``+ C``), the bounds
  ``F(x)|ₐᵇ``, ``F(b)``, ``F(a)`` and their difference;
* substitution: ``t = g(x)`` with the changed limits, the integral in ``t`` and
  no back substitution;
* parity on a symmetric interval: an odd function integrates to zero, an even
  one is ``2∫₀ᵃ`` (Newton–Leibniz stays the second card);
* improper integrals: a LIMIT node with the bound variable, a convergent value
  or an answer card «Интеграл расходится» instead of ``SolveError``;
* the Euler–Poisson integral ``∫₀^∞ e^(−x²) dx = √π/2``.

Every value is checked against ``sympy.integrate`` before the card is offered.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .base import SolveResult, Step
from .integral_cards import (
    KEY_DIFFERENTIAL,
    KEY_SUBSTITUTE,
    _coefficient,
    _fact,
    _ordered,
    _primitive,
    _transform,
    _with_differential,
    find_substitution,
    is_linear_table,
    is_table,
    textbook_detail,
)
from .sympy_bridge import from_sympy, to_sympy

HEADER_NEWTON = "lesson_calc_header_int_newton"
HEADER_PARITY = "lesson_calc_header_int_parity"
HEADER_IMPROPER = "lesson_calc_header_int_improper"
HEADER_DIVERGES = "lesson_calc_header_int_diverges"
HEADER_EULER = "lesson_calc_header_int_euler_poisson"
HEADER_SUB_LIMITS = "lesson_calc_header_int_subst_limits"

KEY_FORMULA = "lesson_calc_int_newton_formula"
KEY_PRIMITIVE = "lesson_calc_int_newton_primitive"
KEY_BOUNDS = "lesson_calc_int_newton_bounds"
KEY_SUBST = "lesson_calc_int_newton_subst"
KEY_UPPER = "lesson_calc_int_newton_upper"
KEY_LOWER = "lesson_calc_int_newton_lower"
KEY_CALC = "lesson_calc_int_newton_calc"
KEY_SUB_LIMITS = "lesson_calc_int_newton_sub_limits"
KEY_SUB_REWRITE = "lesson_calc_int_newton_sub_rewrite"

KEY_IMP_FORMULA = "lesson_calc_int_imp_formula"
KEY_IMP_REWRITE = "lesson_calc_int_imp_rewrite"
KEY_IMP_PRIMITIVE = "lesson_calc_int_imp_primitive"
KEY_IMP_VALUE = "lesson_calc_int_imp_value"
KEY_IMP_DIVERGES = "lesson_calc_int_imp_diverges"

KEY_PARITY_ODD = "lesson_calc_int_parity_odd"
KEY_PARITY_EVEN = "lesson_calc_int_parity_even"
KEY_PARITY_ZERO = "lesson_calc_int_parity_zero"
KEY_PARITY_CALC = "lesson_calc_int_parity_even_calc"

KEY_EULER = "lesson_calc_int_euler_poisson"

_DIVERGES_TEXT = "Интеграл расходится"


def _node(kind: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(kind, *children)


def _num(value: int) -> CoreNode:
    return CoreNode.constant(str(value))


def _var(name: str) -> CoreNode:
    return CoreNode.variable(name)


def _integral(expression: CoreNode) -> CoreNode:
    return _node(T.INTEGRAL, expression)


def _function(name: str, variable: str) -> CoreNode:
    return CoreNode(type=T.FUNCTION, value=name, children=[_var(variable)])


def _substitute_node(node: CoreNode, variable: sympy.Symbol, value: CoreNode) -> CoreNode:
    if node.type is T.VARIABLE and node.value == str(variable):
        return value
    if not node.children:
        return node
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[_substitute_node(child, variable, value) for child in node.children],
    )


def _positive_names(*names: str) -> set[str]:
    """Bounds the card knows to be positive (``b → ∞``, ``ε → 0+``)."""
    return {name for name in names if name}


def _substituted_node(
    primitive_node: CoreNode,
    variable: sympy.Symbol,
    value_node: CoreNode,
    positive: set[str] | None = None,
) -> CoreNode:
    """``F(b)``: the primitive with the bound in place, ``|·|`` dropped if positive.

    A fixed endpoint stays a number and is evaluated in this same stage, so
    ``2√1`` becomes ``2``; ``ln 1`` is kept (see :func:`_simplify_numbers`).
    """
    node = _substitute_node(primitive_node, variable, value_node)
    node = _drop_positive_abs(node, positive or set())
    return _simplify_numbers(node)


def _drop_positive_abs(node: CoreNode, positive: set[str]) -> CoreNode:
    """``ln|b|`` -> ``ln b`` for a positive bound; a constant argument is positive too."""
    if node.type is T.ABS and node.children:
        argument = node.children[0]
        if _provably_positive(argument, positive):
            return _drop_positive_abs(argument, positive)
    if not node.children:
        return node
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[_drop_positive_abs(child, positive) for child in node.children],
    )


def _provably_positive(node: CoreNode, positive: set[str]) -> bool:
    try:
        expression = to_sympy(node)
    except Exception:
        return False
    substitutions = {
        sympy.Symbol(name): sympy.Symbol(name, positive=True)
        for name in positive
        if name in {str(symbol) for symbol in expression.free_symbols}
    }
    expression = expression.subs(substitutions)
    try:
        return sympy.ask(sympy.Q.positive(expression)) is True
    except (TypeError, ValueError):
        return False


def _simplify_numbers(node: CoreNode) -> CoreNode:
    """Evaluate constant pieces (``2√1`` -> ``2``), leaving ``ln 1`` visible."""
    if node.type in (T.LN, T.LOG, T.LOG10):
        # A logarithm of a trivial bound stays as written: the textbook writes
        # ``ln b − ln 1``, not ``ln b``.
        return node
    if not node.children:
        return node
    rebuilt = CoreNode(
        type=node.type,
        value=node.value,
        children=[_simplify_numbers(child) for child in node.children],
    )
    try:
        value = to_sympy(rebuilt)
    except Exception:
        return rebuilt
    if value.free_symbols or not value.is_number:
        return rebuilt
    try:
        return from_sympy(sympy.simplify(value))
    except Exception:
        return rebuilt


def _difference(upper: CoreNode, lower: CoreNode) -> CoreNode:
    """``F(b) − F(a)`` with a negative value written as a sum (``+ 1``, not ``− −1``)."""
    if lower.type is T.NEGATIVE and len(lower.children) == 1:
        return _node(T.ADD, upper, lower.children[0])
    return _node(T.SUBTRACT, upper, lower)


def _shifted(node: CoreNode, delta: CoreNode, *, add: bool) -> CoreNode:
    """``a + ε`` / ``b − ε`` with a zero bound written as the shift itself."""
    zero = node.type is T.CONSTANT and node.value in ("0", "0.0", "-0")
    if add:
        return delta if zero else _node(T.ADD, node, delta)
    if zero:
        return _node(T.NEGATIVE, delta)
    return _node(T.SUBTRACT, node, delta)


def _variable_of(expression: sympy.Expr, variables: list[str]) -> sympy.Symbol | None:
    symbols = sorted(expression.free_symbols, key=str)
    if len(symbols) > 1:
        return None
    if symbols:
        return symbols[0]
    return sympy.Symbol(variables[0] if variables else "x")


def _formula_node() -> CoreNode:
    """``∫ₐᵇ f(x) dx = F(b) − F(a)``."""
    left = _node(
        T.INTEGRAL_DEFINITE,
        _var("a"),
        _var("b"),
        _function("f", "x"),
    )
    right = _node(T.SUBTRACT, _function("F", "b"), _function("F", "a"))
    return _node(T.EQUALS, left, right)


def _primitive_and_detail(
    body_node: CoreNode, variables: list[str], expression: sympy.Expr, variable: sympy.Symbol
) -> tuple[CoreNode, sympy.Expr, SolveResult | None] | None:
    """The antiderivative node, its sympy value and the nested lesson card."""
    detail = textbook_detail(_integral(body_node), variables)
    if detail is not None and detail.solution is not None:
        try:
            return detail.solution, to_sympy(detail.solution), detail
        except Exception:
            pass
    try:
        antiderivative = sympy.integrate(expression, variable)
    except (TypeError, ValueError, NotImplementedError):
        return None
    if antiderivative.has(sympy.Integral) or antiderivative.has(sympy.erf):
        return None
    try:
        node = from_sympy(antiderivative)
    except Exception:
        return None
    return node, antiderivative, None


def _value_node(value: sympy.Expr) -> CoreNode:
    return _ordered(sympy.together(sympy.simplify(value)))


def _plain_node(value: sympy.Expr) -> CoreNode:
    """A node without simplification (``1 − 1/b`` stays a difference)."""
    return _ordered(value)


def _newton_card(
    body_node: CoreNode,
    expression: sympy.Expr,
    variable: sympy.Symbol,
    lower_node: CoreNode,
    upper_node: CoreNode,
    lower: sympy.Expr,
    upper: sympy.Expr,
    variables: list[str],
) -> SolveResult | None:
    primitives = _primitive_and_detail(body_node, variables, expression, variable)
    if primitives is None:
        return None
    primitive_node, primitive, detail = primitives
    upper_sub = _substitute_node(primitive_node, variable, upper_node)
    lower_sub = _substitute_node(primitive_node, variable, lower_node)
    try:
        upper_value = sympy.simplify(primitive.subs(variable, upper))
        lower_value = sympy.simplify(primitive.subs(variable, lower))
        answer_value = sympy.simplify(upper_value - lower_value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if answer_value.has(sympy.Integral) or answer_value.is_real is not True:
        return None
    try:
        upper_value_node = _value_node(upper_value)
        lower_value_node = _value_node(lower_value)
        answer_node = _value_node(answer_value)
    except Exception:
        return None

    card = SolveResult(header=HEADER_NEWTON)
    steps = [
        _fact(KEY_FORMULA, _formula_node()),
        Step(_integral(body_node), primitive_node, KEY_PRIMITIVE, subresult=detail),
    ]
    dash = _node(T.INTEGRAL_RIGHT_DASH, primitive_node, lower_node, upper_node)
    stage = _transform(KEY_BOUNDS, primitive_node, dash)
    if stage is not None:
        steps.append(stage)
    difference = _difference(upper_sub, lower_sub)
    stage = _transform(KEY_SUBST, dash, difference)
    if stage is not None:
        steps.append(stage)
    steps.append(_fact(KEY_UPPER, _node(T.EQUALS, upper_sub, upper_value_node)))
    steps.append(_fact(KEY_LOWER, _node(T.EQUALS, lower_sub, lower_value_node)))
    stage = _transform(KEY_CALC, difference, answer_node)
    if stage is not None:
        steps.append(stage)
    card.add_group("find_integral", *steps)
    card.set_solution(answer_node)
    return card


def _definite_node(lower_node: CoreNode, upper_node: CoreNode, body_node: CoreNode) -> CoreNode:
    return _node(T.INTEGRAL_DEFINITE, lower_node, upper_node, body_node)


# ── the verified card ───────────────────────────────────────
#
# the app evaluates a definite integral in four stages on one screen:
# the indefinite integral, its primitive, the primitive at the bounds
# (``F(x)|ₐᵇ``) and ``F(b) − F(a)``; the last arithmetic has a «Подробнее»
# screen of microsteps (powers of 1/0, ``ln 1``, trigonometric values,
# ``x − 0``).  The rows below are that screen, verified from the device.


def _abs(value: CoreNode) -> CoreNode:
    return _node(T.ABS, value)


def _bracket(value: CoreNode) -> CoreNode:
    return _node(T.BRACKET, value)


def _dash_formula_node() -> CoreNode:
    """``F(x)|ₐᵇ = F(b) − F(a)``."""
    left = _node(T.INTEGRAL_RIGHT_DASH, _function("F", "x"), _var("a"), _var("b"))
    right = _node(T.SUBTRACT, _function("F", "b"), _function("F", "a"))
    return _node(T.EQUALS, left, right)


def _equals_rule(expression: sympy.Expr, primitive: sympy.Expr, variable: sympy.Symbol) -> CoreNode:
    """``∫ f dx = F`` with the concrete function and its primitive."""
    return _node(T.EQUALS, _integral(_ordered(expression)), _ordered(primitive))


def _rewrite_first(
    node: CoreNode, rule: Callable[[CoreNode], CoreNode | None]
) -> tuple[CoreNode, bool]:
    """Replace the first subexpression ``rule`` answers for (left to right)."""
    replacement = rule(node)
    if replacement is not None:
        return replacement, True
    if not node.children:
        return node, False
    children = list(node.children)
    for index, child in enumerate(children):
        changed_child, changed = _rewrite_first(child, rule)
        if changed:
            children[index] = changed_child
            return CoreNode(type=node.type, value=node.value, children=children), True
    return node, False


def _rewrite_all(
    node: CoreNode, rule: Callable[[CoreNode], CoreNode | None]
) -> tuple[CoreNode, list[tuple[CoreNode, CoreNode]]]:
    """Apply ``rule`` everywhere; return the node and the ``(before, after)`` pairs."""
    pairs: list[tuple[CoreNode, CoreNode]] = []

    def walk(current: CoreNode) -> CoreNode:
        replacement = rule(current)
        if replacement is not None:
            pairs.append((current, replacement))
            return replacement
        if not current.children:
            return current
        return CoreNode(
            type=current.type,
            value=current.value,
            children=[walk(child) for child in current.children],
        )

    return walk(node), pairs


def _constant_of(node: CoreNode, value: str) -> bool:
    return node.type is T.CONSTANT and node.value == value


def _same_value(first: CoreNode, second: CoreNode) -> bool:
    """Equal as written, or equal as numbers/expressions (``1/2`` vs ``frac(1,2)``)."""
    if first.structural_eq(second):
        return True
    try:
        return bool(sympy.simplify(to_sympy(first) - to_sympy(second)) == 0)
    except (TypeError, ValueError, sympy.SympifyError):
        return False


def _arithmetic_detail(difference: CoreNode, answer_node: CoreNode) -> SolveResult | None:
    """``(1²)/2 − (0²)/2 → 1/2 − 0/2 → 1/2 − 0 → 1/2`` (verified ``∫₀¹ x dx``)."""
    current = difference
    groups: list[list[Step]] = []

    def power_of(base: str) -> Callable[[CoreNode], CoreNode | None]:
        def rule(node: CoreNode) -> CoreNode | None:
            if (
                node.type is T.POWER
                and _constant_of(node.children[0], base)
                and node.children[1].type is T.CONSTANT
            ):
                try:
                    return _num(int(base) ** int(node.children[1].value or 0))
                except ValueError:
                    return None
            return None

        return rule

    powers: list[Step] = []
    for base, key in (("1", "pow_one"), ("0", "pow_zero")):
        changed, pairs = _rewrite_all(current, power_of(base))
        for before, after in pairs:
            powers.append(Step(before, after, key, [_num(int(base))]))
        current = changed
    if powers:
        groups.append(powers)

    def zero_numerator(node: CoreNode) -> CoreNode | None:
        if node.type in (T.FRACTION, T.DIVIDE) and _constant_of(node.children[0], "0"):
            return _num(0)
        return None

    changed, pairs = _rewrite_all(current, zero_numerator)
    if pairs:
        groups.append([Step(before, after, "div_zero", [_num(0)]) for before, after in pairs])
        current = changed

    def zero_summand(node: CoreNode) -> CoreNode | None:
        if node.type is T.SUBTRACT and _constant_of(node.children[1], "0"):
            return node.children[0]
        if node.type is T.ADD:
            if _constant_of(node.children[1], "0"):
                return node.children[0]
            if _constant_of(node.children[0], "0"):
                return node.children[1]
        return None

    changed, pairs = _rewrite_all(current, zero_summand)
    if pairs:
        groups.append([Step(before, after, "add_with_zero", [_num(0)]) for before, after in pairs])
        current = changed
    if not groups:
        return None
    if not _same_value(current, answer_node):
        groups.append([Step(current, answer_node, "add")])
    detail = SolveResult()
    for group in groups:
        detail.add_group("calculate_short", *group)
    detail.set_solution(answer_node)
    return detail


def _log_detail(
    upper_node: CoreNode, lower_node: CoreNode, answer_node: CoreNode
) -> SolveResult | None:
    """``ln|2| − ln|1| → ln 2 − ln 1 → ln 2 − 0 → ln 2`` (verified ``∫₁² dx/x``)."""
    upper_abs = _node(T.LN, _abs(upper_node))
    lower_abs = _node(T.LN, _abs(lower_node))
    current = _node(T.SUBTRACT, upper_abs, lower_abs)
    groups: list[list[Step]] = []

    def drop_abs(node: CoreNode) -> CoreNode | None:
        if node.type is T.ABS and node.children and node.children[0].type is T.CONSTANT:
            return node.children[0]
        return None

    dropped, pairs = _rewrite_all(current, drop_abs)
    if pairs:
        groups.append([Step(before, after, "abs_real") for before, after in pairs])
        current = dropped

    def log_one(node: CoreNode) -> CoreNode | None:
        if node.type is T.LN and _constant_of(node.children[0], "1"):
            return _num(0)
        return None

    logged, pairs = _rewrite_all(current, log_one)
    if pairs:
        groups.append(
            [Step(before, after, "log_arg_one", [_num(1), _num(0)]) for before, after in pairs]
        )
        current = logged

    def zero_summand(node: CoreNode) -> CoreNode | None:
        if node.type is T.SUBTRACT and _constant_of(node.children[1], "0"):
            return node.children[0]
        if node.type is T.ADD:
            if _constant_of(node.children[1], "0"):
                return node.children[0]
            if _constant_of(node.children[0], "0"):
                return node.children[1]
        return None

    summed, pairs = _rewrite_all(current, zero_summand)
    if pairs:
        groups.append([Step(before, after, "add_with_zero", [_num(0)]) for before, after in pairs])
        current = summed
    if not groups:
        return None
    if not _same_value(current, answer_node):
        groups.append([Step(current, answer_node, "simplify")])
    detail = SolveResult()
    for group in groups:
        detail.add_group("calculate_short", *group)
    detail.set_solution(answer_node)
    return detail


def _sine_detail(lower: sympy.Expr, upper: sympy.Expr, answer_node: CoreNode) -> SolveResult | None:
    """``−cos π − (−cos 0) → 1 + cos 0 → 1 + 1 → 2`` (verified ``∫₀^π sin x dx``)."""
    if not (lower == 0 and upper == sympy.pi):
        return None
    pi = CoreNode.constant("π")
    zero = _num(0)
    start = _node(
        T.SUBTRACT,
        _node(T.NEGATIVE, _node(T.COS, pi)),
        _bracket(_node(T.NEGATIVE, _node(T.COS, zero))),
    )
    after_third = _node(
        T.SUBTRACT,
        _node(T.NEGATIVE, _bracket(_node(T.NEGATIVE, _num(1)))),
        _bracket(_node(T.NEGATIVE, _node(T.COS, zero))),
    )
    after_switch = _node(
        T.ADD, _node(T.NEGATIVE, _bracket(_node(T.NEGATIVE, _num(1)))), _node(T.COS, zero)
    )
    after_double = _node(T.ADD, _num(1), _node(T.COS, zero))
    after_table = _node(T.ADD, _num(1), _num(1))
    detail = SolveResult()
    detail.add_group(
        "calculate_short",
        Step(start, after_third, "trig_table_third"),
        Step(after_third, after_switch, "neg_neg_arg", [CoreNode(type=T.TEXT, value="−")]),
    )
    detail.add_group(
        "calculate_short",
        Step(after_switch, after_double, "neg_neg_arg", [CoreNode(type=T.TEXT, value="−")]),
        Step(after_double, after_table, "trig_table_first"),
    )
    detail.add_group("calculate_short", Step(after_table, answer_node, "add"))
    detail.set_solution(answer_node)
    return detail


def _evaluation_detail(
    primitive: sympy.Expr,
    difference: CoreNode,
    answer_node: CoreNode,
    lower_node: CoreNode,
    upper_node: CoreNode,
) -> SolveResult | None:
    """The «Подробнее» screen of the last row of a definite integral."""
    if primitive.has(sympy.log):
        return _log_detail(upper_node, lower_node, answer_node)
    if primitive.has(sympy.sin) or primitive.has(sympy.cos):
        lower = to_sympy(lower_node)
        upper = to_sympy(upper_node)
        return _sine_detail(lower, upper, answer_node)
    return _arithmetic_detail(difference, answer_node)


def _row_steps(
    definite_node: CoreNode,
    body_node: CoreNode,
    expression: sympy.Expr,
    variable: sympy.Symbol,
    lower_node: CoreNode,
    upper_node: CoreNode,
    lower: sympy.Expr,
    upper: sympy.Expr,
    *,
    evaluate: bool = True,
) -> tuple[CoreNode, list[Step]] | None:
    """The five rows the app shows for ``∫ₐᵇ f dx`` (without a card wrapper)."""
    primitives = _primitive_and_detail(body_node, [str(variable)], expression, variable)
    if primitives is None:
        return None
    primitive_node, primitive, _lesson = primitives
    upper_sub = _substitute_node(primitive_node, variable, upper_node)
    lower_sub = _substitute_node(primitive_node, variable, lower_node)
    try:
        answer_value = sympy.simplify(
            primitive.subs(variable, upper) - primitive.subs(variable, lower)
        )
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if answer_value.has(sympy.Integral) or _diverges(answer_value):
        return None
    answer_node = _value_node(answer_value)
    # The app shows the bounds substituted without evaluating them yet:
    # ``(1²)/2 − (0²)/2`` and ``ln|2| − ln|1|``; the last row evaluates them.
    difference = _node(
        T.SUBTRACT,
        upper_sub,
        _bracket(lower_sub) if lower_sub.type is T.NEGATIVE else lower_sub,
    )
    dash = _node(T.INTEGRAL_RIGHT_DASH, primitive_node, lower_node, upper_node)
    # Решатель says «Вычислите значение» when only numbers are left and
    # «Упростите» when functions (trigonometric values, logarithms) or a
    # symbolic bound remain.
    numeric = not answer_value.free_symbols and not (
        primitive.has(sympy.sin) or primitive.has(sympy.cos) or primitive.has(sympy.log)
    )
    key = "calculate_direct" if numeric else "simplify"
    rows = _primitive_rows(body_node, expression, variable, primitive, primitive_node)
    if rows is None:
        rows = [
            Step(
                _integral(body_node),
                primitive_node,
                "integrate_msg",
                [_equals_rule(expression, primitive, variable)],
            )
        ]
    steps = [
        Step(definite_node, _integral(body_node), "integrate_def_solve_undefined"),
        *rows,
        Step(primitive_node, dash, "integrate_def_bounds"),
        Step(dash, difference, "integrate_def_msg_range", [_dash_formula_node()]),
    ]
    if evaluate:
        detail = _evaluation_detail(primitive, difference, answer_node, lower_node, upper_node)
        steps.append(Step(difference, answer_node, key, subresult=detail))
    else:
        # The nested chain of an improper integral ends on «Упростите»; its
        # screen has no further rows.
        steps.append(Step(difference, answer_node, key))
    return answer_node, steps


def _primitive_rows(
    body_node: CoreNode,
    expression: sympy.Expr,
    variable: sympy.Symbol,
    primitive: sympy.Expr,
    primitive_node: CoreNode,
) -> list[Step] | None:
    """The app's substitution rows when the primitive needs ``t = g(x)``.

    A table entry (also a linear argument ``kx + b``) keeps its single
    ``integrate_msg`` row; a composite integrand such as ``1/(x ln x)`` is
    rewritten in ``t``, integrated there and back-substituted.
    """
    if is_table(expression, variable) or is_linear_table(expression, variable):
        return None
    substitution = find_substitution(expression, variable)
    if substitution is None:
        return None
    inner, _slope, rewritten = substitution
    t = sympy.Symbol("t", real=True)
    coefficient, table_body = _coefficient(rewritten, t)
    primitive_body = _primitive(table_body, t)
    if primitive_body is None:
        return None
    primitive_t = primitive_body if coefficient == 1 else coefficient * primitive_body
    try:
        restored = sympy.simplify(primitive_t.subs(t, inner) - primitive)
    except (TypeError, ValueError):
        return None
    if restored != 0:
        return None
    t_node = _var("t")
    t_rule = _node(T.EQUALS, t_node, _ordered(inner))
    dt_rule = _node(
        T.EQUALS,
        _var("dt"),
        _with_differential(sympy.simplify(_slope), "dx"),
    )
    derivation = SolveResult()
    derivation.add_group(
        "integrate_differential_sub",
        Step(
            t_rule,
            dt_rule,
            "integrate_subs_substep",
            [
                dt_rule,
                t_rule,
                _node(
                    T.EQUALS,
                    _var("t'"),
                    from_sympy(sympy.simplify(_slope)),
                ),
            ],
        ),
    )
    derivation.set_solution(dt_rule)
    t_integral = _integral(_ordered(rewritten))
    table_right: CoreNode = _ordered(primitive_t)
    if coefficient != 1:
        t_integral = _node(T.MULTIPLY, from_sympy(coefficient), t_integral)
    return [
        Step(
            _integral(body_node),
            t_integral,
            "integrate_subs_subproc",
            [t_rule],
            subresult=derivation,
        ),
        Step(
            t_integral,
            table_right,
            "integrate_msg",
            [_equals_rule(table_body, primitive_body, t)],
        ),
        Step(table_right, primitive_node, "sub_msg_ret", [t_rule]),
    ]


def _nil_out(node: CoreNode, bind: str, *, over_infinity: bool) -> CoreNode:
    """Put the limit's value into the expression: ``a → 0`` or ``1/a → 0``."""
    if over_infinity and node.type in (T.FRACTION, T.DIVIDE):
        denominator = node.children[1]
        if denominator.type is T.VARIABLE and denominator.value == bind:
            return _num(0)
    if node.type is T.VARIABLE and node.value == bind:
        return _num(0)
    if not node.children:
        return node
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[_nil_out(child, bind, over_infinity=over_infinity) for child in node.children],
    )


def _limit_detail(
    inner_node: CoreNode,
    answer_node: CoreNode,
    bind: str,
    *,
    over_infinity: bool,
) -> SolveResult:
    """The two rows of the app's «Вычислите предел» screen."""
    replaced = _nil_out(inner_node, bind, over_infinity=over_infinity)
    detail = SolveResult()
    detail.add_group("calculate_short", Step(inner_node, replaced, "limit_solve"))
    if over_infinity:
        detail.add_group("calculate_short", Step(replaced, answer_node, "add_with_zero", [_num(0)]))
    else:
        detail.add_group("calculate_short", Step(replaced, answer_node, "calculate_direct"))
    detail.set_solution(answer_node)
    return detail


# the app's step headings of the definite chain (the keys are the dictionary's).
_CHAIN_HEADINGS = {
    "integrate_def_solve_undefined": "integrate",
    "integrate_msg": "integrate_calc",
    "integrate_def_bounds": "integrate_def_bounds_short",
    "integrate_def_msg_range": "calculate_expressions",
    "calculate_direct": "calculate_short",
    "simplify": "simplify_msg",
    "integrate_imp_rewrite_using_lim": "integrate_imp_evaluate",
    "integrate_imp_rewrite_using_lim_sided_msg": "integrate_imp_rewrite",
    "integrate_def": "integrate_calc",
    "limit_solve": "evaluate",
    "integrate_subs_subproc": "trans_msg",
    "sub_msg_ret": "substitute_return_one_short",
}


def _row_card(steps: list[Step], answer_node: CoreNode) -> SolveResult:
    """A card whose rows are the verified rows, one step each."""
    card = SolveResult()
    for step in steps:
        card.add_group(_CHAIN_HEADINGS.get(step.key, "find_integral"), step)
    card.set_solution(answer_node)
    return card


def row_definite_card(
    node: CoreNode, variables: list[str], variable: sympy.Symbol | None = None
) -> SolveResult | None:
    """The verified card of a proper definite integral (the app's five rows).

    ``variable`` is the integration variable when the body names more than one
    (an iterated integral); otherwise it is the body's only free symbol.
    """
    if node.type is not T.INTEGRAL_DEFINITE or len(node.children) != 3:
        return None
    lower_node, upper_node, body_node = node.children
    try:
        expression = to_sympy(body_node)
        lower, upper = to_sympy(lower_node), to_sympy(upper_node)
    except Exception:
        return None
    variable = variable if variable is not None else _variable_of(expression, variables)
    if variable is None:
        return None
    built = _row_steps(node, body_node, expression, variable, lower_node, upper_node, lower, upper)
    if built is None:
        return None
    answer_node, steps = built
    return _row_card(steps, answer_node)


def row_improper_card(
    node: CoreNode, variables: list[str], singular: sympy.Expr | None = None
) -> SolveResult | None:
    """The verified card of an improper integral (rewrite, inner chain, limit)."""
    if node.type is not T.INTEGRAL_DEFINITE or len(node.children) != 3:
        return None
    lower_node, upper_node, body_node = node.children
    try:
        expression = to_sympy(body_node)
        lower, upper = to_sympy(lower_node), to_sympy(upper_node)
    except Exception:
        return None
    variable = _variable_of(expression, variables)
    if variable is None:
        return None
    bind_node = _var("a")
    bind = sympy.Symbol("a", positive=True)
    if singular is not None:
        if sympy.simplify(singular - lower) == 0:
            inner = _definite_node(bind_node, upper_node, body_node)
            inner_lower_node, inner_upper_node = bind_node, upper_node
            inner_lower, inner_upper = bind, upper
        else:
            inner = _definite_node(lower_node, bind_node, body_node)
            inner_lower_node, inner_upper_node = lower_node, bind_node
            inner_lower, inner_upper = lower, bind
        kind, point_node = T.LIMIT_RIGHT, _num(0)
        limit = _node(kind, point_node, inner)
    elif upper in (sympy.oo, -sympy.oo):
        inner = _definite_node(lower_node, bind_node, body_node)
        inner_lower_node, inner_upper_node = lower_node, bind_node
        inner_lower, inner_upper = lower, bind
        kind, point_node = T.LIMIT, CoreNode.constant("∞")
        limit = _node(kind, point_node, inner)
    elif lower in (sympy.oo, -sympy.oo):
        inner = _definite_node(bind_node, upper_node, body_node)
        inner_lower_node, inner_upper_node = bind_node, upper_node
        inner_lower, inner_upper = bind, upper
        kind, point_node = T.LIMIT, _node(T.NEGATIVE, CoreNode.constant("∞"))
        limit = _node(kind, point_node, inner)
    else:
        return None

    built = _row_steps(
        inner,
        body_node,
        expression,
        variable,
        inner_lower_node,
        inner_upper_node,
        inner_lower,
        inner_upper,
        evaluate=False,
    )
    if built is None:
        return None
    difference_node, chain = built
    chain_card = _row_card(chain, difference_node)
    steps = [Step(node, limit, "integrate_imp_rewrite_using_lim")]
    if singular is not None:
        discon = _node(T.LIST, node, _node(T.EQUALS, _var("c"), from_sympy(singular)))
        detail = SolveResult()
        detail.add_group(
            "integrate_imp_discon_lower_simple",
            Step(
                node,
                discon,
                "integrate_imp_discon_lower",
                [_node(T.EQUALS, _var("c"), from_sympy(singular))],
            ),
        )
        detail.add_group(
            "find_integral", Step(discon, limit, "integrate_imp_rewrite_using_lim_sided")
        )
        steps = [
            Step(
                node,
                limit,
                "integrate_imp_rewrite_using_lim_sided_msg",
                subresult=detail,
            )
        ]
    studied = _node(kind, point_node, difference_node)
    steps.append(Step(limit, studied, "integrate_def", subresult=chain_card))
    try:
        total = sympy.integrate(expression, (variable, lower, upper))
    except (TypeError, ValueError, NotImplementedError):
        return None
    if total.has(sympy.Integral):
        return None
    answer_node = _value_node(total)
    detail = _limit_detail(difference_node, answer_node, "a", over_infinity=singular is None)
    steps.append(Step(studied, answer_node, "limit_solve", subresult=detail))
    return _row_card(steps, answer_node)


def _coefficient_in_front(coefficient: sympy.Expr, node: CoreNode) -> CoreNode:
    if coefficient == 1:
        return node
    if node.type in (T.ADD, T.SUBTRACT):
        node = _node(T.BRACKET, node)
    return _node(T.MULTIPLY, from_sympy(coefficient), node)


def _substitution_card(
    node: CoreNode,
    body_node: CoreNode,
    expression: sympy.Expr,
    variable: sympy.Symbol,
    lower_node: CoreNode,
    upper_node: CoreNode,
    lower: sympy.Expr,
    upper: sympy.Expr,
    substitution: tuple[sympy.Expr, sympy.Expr, sympy.Expr],
    variables: list[str],
) -> SolveResult | None:
    inner, slope, rewritten = substitution
    t = sympy.Symbol("t", real=True)
    coefficient, body = _coefficient(rewritten, t)
    primitive_body = _primitive(body, t)
    if primitive_body is None:
        return None
    try:
        new_lower = sympy.simplify(inner.subs(variable, lower))
        new_upper = sympy.simplify(inner.subs(variable, upper))
    except (TypeError, ValueError):
        return None
    if new_lower.has(variable) or new_upper.has(variable):
        return None
    try:
        value = sympy.simplify(
            coefficient * (primitive_body.subs(t, new_upper) - primitive_body.subs(t, new_lower))
        )
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if value.has(sympy.Integral) or value.is_real is not True:
        return None
    try:
        answer_node = _value_node(value)
        new_lower_node, new_upper_node = from_sympy(new_lower), from_sympy(new_upper)
    except Exception:
        return None
    primitive_body_node = from_sympy(primitive_body)

    card = SolveResult(header=HEADER_SUB_LIMITS)
    steps = [
        _fact(KEY_FORMULA, _formula_node()),
        _fact(KEY_SUBSTITUTE, _node(T.EQUALS, _var("t"), from_sympy(inner))),
        _fact(
            KEY_DIFFERENTIAL,
            _node(T.EQUALS, _var("dt"), _node(T.MULTIPLY, from_sympy(slope), _var("dx"))),
        ),
    ]
    # «x = 0, t = 0» and «x = 1, t = 1»: two facts, not one four-row list.
    steps.append(
        _fact(
            KEY_SUB_LIMITS,
            _node(
                T.LIST,
                _node(T.EQUALS, _var(str(variable)), lower_node),
                _node(T.EQUALS, _var("t"), new_lower_node),
            ),
        )
    )
    steps.append(
        _fact(
            KEY_SUB_LIMITS,
            _node(
                T.LIST,
                _node(T.EQUALS, _var(str(variable)), upper_node),
                _node(T.EQUALS, _var("t"), new_upper_node),
            ),
        )
    )
    target = _coefficient_in_front(
        coefficient,
        _definite_node(new_lower_node, new_upper_node, from_sympy(body)),
    )
    stage = _transform(KEY_SUB_REWRITE, node, target)
    if stage is not None:
        steps.append(stage)
    dash = _node(T.INTEGRAL_RIGHT_DASH, primitive_body_node, new_lower_node, new_upper_node)
    dash_with_coefficient = _coefficient_in_front(coefficient, dash)
    detail = textbook_detail(_integral(from_sympy(body)), ["t"])
    # This stage finds the antiderivative; the bounds are substituted next.
    stage = _transform(KEY_PRIMITIVE, target, dash_with_coefficient, subresult=detail)
    if stage is not None:
        steps.append(stage)
    upper_sub = _substitute_node(primitive_body_node, t, new_upper_node)
    lower_sub = _substitute_node(primitive_body_node, t, new_lower_node)
    difference = _coefficient_in_front(coefficient, _difference(upper_sub, lower_sub))
    stage = _transform(KEY_BOUNDS, dash_with_coefficient, difference)
    if stage is not None:
        steps.append(stage)
    try:
        upper_value_node = _value_node(primitive_body.subs(t, new_upper))
        lower_value_node = _value_node(primitive_body.subs(t, new_lower))
    except Exception:
        upper_value_node = upper_sub
        lower_value_node = lower_sub
    steps.append(_fact(KEY_UPPER, _node(T.EQUALS, upper_sub, upper_value_node)))
    steps.append(_fact(KEY_LOWER, _node(T.EQUALS, lower_sub, lower_value_node)))
    stage = _transform(KEY_CALC, difference, answer_node)
    if stage is not None:
        steps.append(stage)
    card.add_group("find_integral", *steps)
    card.set_solution(answer_node)
    return card


def _parity_check(
    body_node: CoreNode, variable: sympy.Symbol, reflected: sympy.Expr, *, odd: bool
) -> CoreNode:
    """``f(−x) = (−x)³ = −x³ = −f(x)``: the concrete check as one EQUALS chain."""
    x = _var(str(variable))
    minus_x = _node(T.NEGATIVE, x)
    f_neg = CoreNode(type=T.FUNCTION, value="f", children=[minus_x])
    f_x = CoreNode(type=T.FUNCTION, value="f", children=[x])
    concrete = _substitute_node(body_node, variable, minus_x)
    simplified = _ordered(sympy.simplify(reflected))
    last = _node(T.NEGATIVE, f_x) if odd else f_x
    pieces = [f_neg, concrete, simplified, last]
    chain: list[CoreNode] = []
    for piece in pieces:
        if not chain or not chain[-1].structural_eq(piece):
            chain.append(piece)
    return _node(T.EQUALS, *chain)


def _parity_cards(
    node: CoreNode,
    body_node: CoreNode,
    expression: sympy.Expr,
    variable: sympy.Symbol,
    lower_node: CoreNode,
    upper_node: CoreNode,
    lower: sympy.Expr,
    upper: sympy.Expr,
    variables: list[str],
) -> list[SolveResult]:
    if lower + upper != 0 or lower == 0:
        return []
    try:
        reflected = sympy.simplify(expression.subs(variable, -variable))
    except (TypeError, ValueError):
        return []
    cards: list[SolveResult] = []
    if sympy.simplify(reflected + expression) == 0:
        card = SolveResult(header=HEADER_PARITY)
        steps = [_fact(KEY_PARITY_ODD, _parity_check(body_node, variable, reflected, odd=True))]
        stage = _transform(KEY_PARITY_ZERO, node, _num(0))
        if stage is not None:
            steps.append(stage)
        card.add_group("find_integral", *steps)
        card.set_solution(_num(0))
        cards.append(card)
    elif sympy.simplify(reflected - expression) == 0:
        half = _definite_node(_num(0), upper_node, body_node)
        doubled = _node(T.MULTIPLY, _num(2), half)
        card = SolveResult(header=HEADER_PARITY)
        steps = [_fact(KEY_PARITY_EVEN, _parity_check(body_node, variable, reflected, odd=False))]
        stage = _transform(KEY_PARITY_CALC, node, doubled)
        if stage is not None:
            steps.append(stage)
        try:
            value = sympy.integrate(expression, (variable, lower, upper))
        except (TypeError, ValueError, NotImplementedError):
            return cards
        if value.has(sympy.Integral) or value.is_real is not True:
            return cards
        answer_node = _value_node(value)
        # «… и его Ньютон–Лейбниц»: evaluate 2∫₀ᵃ with the primitive at both bounds.
        primitives = _primitive_and_detail(body_node, variables, expression, variable)
        current = doubled
        if primitives is not None and primitives[2] is not None:
            primitive_node = primitives[0]
            dash = _node(T.INTEGRAL_RIGHT_DASH, primitive_node, _num(0), upper_node)
            bounds = _node(T.MULTIPLY, _num(2), dash)
            stage = _transform(KEY_PARITY_CALC, current, bounds)
            if stage is not None:
                steps.append(stage)
                upper_sub = _substituted_node(primitive_node, variable, upper_node)
                lower_sub = _substituted_node(primitive_node, variable, _num(0))
                difference = _node(T.MULTIPLY, _num(2), _difference(upper_sub, lower_sub))
                stage = _transform(KEY_PARITY_CALC, bounds, difference)
                if stage is not None:
                    steps.append(stage)
                    current = difference
        stage = _transform(KEY_PARITY_CALC, current, answer_node)
        if stage is not None:
            steps.append(stage)
        card.add_group("find_integral", *steps)
        card.set_solution(answer_node)
        cards.append(card)
    else:
        return []
    newton = _newton_card(
        body_node, expression, variable, lower_node, upper_node, lower, upper, variables
    )
    if newton is not None:
        cards.append(newton)
    return cards


def _limit_node(point: CoreNode, expression: CoreNode) -> CoreNode:
    return _node(T.LIMIT, point, expression)


def _placeholder(name: str) -> CoreNode:
    """A generic bound written as a letter: ``a``/``b`` are not the integration variable.

    The app draws ``lim`` with the single free variable of its expression, so only
    the bound that moves is a VARIABLE; the fixed ones are letters of a CONSTANT.
    """
    return CoreNode.constant(name)


def _improper_formula_node(kind: str = "upper") -> CoreNode:
    """The rule the card applies, with the bound that actually moves.

    ``kind``: ``upper`` (``∫ₐ^∞``), ``lower`` (``∫₋∞^a``), ``both``
    (``∫₋∞^∞``) or ``discontinuity`` (``∫ₐ^b`` with ``ε → 0+``).
    """
    body = _function("f", "x")
    bound = _var("ε") if kind == "discontinuity" else _var("b")
    if kind == "upper":
        left = _node(T.INTEGRAL_DEFINITE, _placeholder("a"), CoreNode.constant("∞"), body)
        inner = _node(T.INTEGRAL_DEFINITE, _placeholder("a"), bound, body)
        point = CoreNode.constant("∞")
        lim = _limit_node(point, inner)
    elif kind == "lower":
        left = _node(
            T.INTEGRAL_DEFINITE,
            _node(T.NEGATIVE, CoreNode.constant("∞")),
            _placeholder("a"),
            body,
        )
        inner = _node(T.INTEGRAL_DEFINITE, bound, _placeholder("a"), body)
        lim = _limit_node(_node(T.NEGATIVE, CoreNode.constant("∞")), inner)
    elif kind == "both":
        left = _node(
            T.INTEGRAL_DEFINITE,
            _node(T.NEGATIVE, CoreNode.constant("∞")),
            CoreNode.constant("∞"),
            body,
        )
        inner = _node(
            T.INTEGRAL_DEFINITE,
            _node(T.NEGATIVE, bound),
            bound,
            body,
        )
        lim = _limit_node(CoreNode.constant("∞"), inner)
    else:
        # A discontinuity at an endpoint: ∫ₐ^b f dx = lim_{ε→0+}∫_{a+ε}^b f dx
        # (the upper endpoint: ∫ₐ^{b−ε}).
        left = _node(
            T.INTEGRAL_DEFINITE,
            _placeholder("a"),
            _placeholder("b"),
            body,
        )
        if kind == "discontinuity_upper":
            above = _node(T.SUBTRACT, _placeholder("b"), bound)
            inner = _node(T.INTEGRAL_DEFINITE, _placeholder("a"), above, body)
        else:
            below = _node(T.ADD, _placeholder("a"), bound)
            inner = _node(T.INTEGRAL_DEFINITE, below, _placeholder("b"), body)
        lim = _node(T.LIMIT_RIGHT, _num(0), inner)
    return _node(T.EQUALS, left, lim)


def _diverges(value: sympy.Expr) -> bool:
    return value in (sympy.oo, -sympy.oo, sympy.zoo, sympy.nan) or value.is_real is False


def _improper_card(
    node: CoreNode,
    body_node: CoreNode,
    expression: sympy.Expr,
    variable: sympy.Symbol,
    lower_node: CoreNode,
    upper_node: CoreNode,
    lower: sympy.Expr,
    upper: sympy.Expr,
    variables: list[str],
    singular: sympy.Expr | None = None,
) -> SolveResult | None:
    primitives = _primitive_and_detail(body_node, variables, expression, variable)
    if primitives is None:
        return None
    primitive_node, primitive, detail = primitives
    try:
        total = sympy.integrate(expression, (variable, lower, upper))
    except (TypeError, ValueError, NotImplementedError):
        return None
    diverges = _diverges(total)

    positive: set[str] = set()
    if singular is not None:
        # The bound that moves is ε: «eps» is not a variable a student reads.
        bind = sympy.Symbol("ε", positive=True)
        bind_node = _var("ε")
        point, point_node, kind = sympy.Integer(0), _num(0), T.LIMIT_RIGHT
        if sympy.simplify(singular - lower) == 0:
            inner = _definite_node(_shifted(lower_node, bind_node, add=True), upper_node, body_node)
            high_expr, low_expr = upper, lower + bind
            high_node, low_node = upper_node, _shifted(lower_node, bind_node, add=True)
            formula_kind = "discontinuity"
        else:
            inner = _definite_node(
                lower_node, _shifted(upper_node, bind_node, add=False), body_node
            )
            high_expr, low_expr = upper - bind, lower
            high_node, low_node = _shifted(upper_node, bind_node, add=False), lower_node
            formula_kind = "discontinuity_upper"
        direction = "+"
        positive = _positive_names("ε")
    elif lower == -sympy.oo and upper == sympy.oo:
        bind = sympy.Symbol("b", positive=True)
        bind_node = _var("b")
        point, point_node, kind = sympy.oo, CoreNode.constant("∞"), T.LIMIT
        inner = _definite_node(_node(T.NEGATIVE, bind_node), bind_node, body_node)
        high_expr, low_expr, high_node, low_node = (
            bind,
            -bind,
            bind_node,
            _node(T.NEGATIVE, bind_node),
        )
        direction = "+"
        formula_kind = "both"
        positive = _positive_names("b")
    elif lower in (-sympy.oo, sympy.oo):
        bind = sympy.Symbol("a", positive=True)
        bind_node = _var("a")
        point, point_node, kind = -sympy.oo, _node(T.NEGATIVE, CoreNode.constant("∞")), T.LIMIT
        inner = _definite_node(bind_node, upper_node, body_node)
        high_expr, low_expr, high_node, low_node = upper, bind, upper_node, bind_node
        direction = "-"
        formula_kind = "lower"
        positive = _positive_names("a")
    elif upper in (sympy.oo, -sympy.oo):
        bind = sympy.Symbol("b", positive=True)
        bind_node = _var("b")
        point, point_node, kind = sympy.oo, CoreNode.constant("∞"), T.LIMIT
        inner = _definite_node(lower_node, bind_node, body_node)
        high_expr, low_expr, high_node, low_node = bind, lower, bind_node, lower_node
        direction = "+"
        formula_kind = "upper"
        positive = _positive_names("b")
    else:
        return None

    limit = _node(kind, point_node, inner)
    card = SolveResult(header=HEADER_IMPROPER)
    steps = [_fact(KEY_IMP_FORMULA, _improper_formula_node(formula_kind))]
    stage = _transform(KEY_IMP_REWRITE, node, limit)
    if stage is not None:
        steps.append(stage)
    # A positive bound drops |·|; a numeric endpoint is evaluated right here.
    if singular is not None:
        # ε is a shift of the endpoint: evaluate the bound of the primitive as a
        # whole, so √(1 − (1 − ε)) is written √ε and 2√1 is written 2.
        inside = sympy.simplify(
            primitive.subs(variable, high_expr) - primitive.subs(variable, low_expr)
        )
        difference = _plain_node(inside)
    else:
        upper_sub = _substituted_node(primitive_node, variable, high_node, positive)
        lower_sub = _substituted_node(primitive_node, variable, low_node, positive)
        difference = _difference(upper_sub, lower_sub)
    studied = _node(kind, point_node, difference)
    stage = _transform(KEY_IMP_PRIMITIVE, limit, studied, subresult=detail)
    if stage is not None:
        steps.append(stage)

    inside_node = difference
    limit_value: sympy.Expr | None = None
    try:
        inside_expr = primitive.subs(variable, high_expr) - primitive.subs(variable, low_expr)
        if inside_expr.has(sympy.Integral):
            inside_expr = None
    except (TypeError, ValueError, ZeroDivisionError):
        inside_expr = None
    if inside_expr is not None:
        try:
            inside_node = _plain_node(inside_expr)
            stage = _transform(KEY_IMP_VALUE, studied, _node(kind, point_node, inside_node))
            if stage is not None:
                steps.append(stage)
            studied = _node(kind, point_node, inside_node)
        except Exception:
            pass
        try:
            limit_value = sympy.limit(inside_expr, bind, point, direction)
        except (TypeError, ValueError, NotImplementedError):
            limit_value = None

    if diverges or (limit_value is not None and _diverges(limit_value)):
        card.header = HEADER_DIVERGES
        fact = _node(T.EQUALS, studied, CoreNode.constant("∞"))
        steps.append(_fact(KEY_IMP_DIVERGES, fact))
        card.add_group("find_integral", *steps)
        card.set_solution(CoreNode(type=T.TEXT, value=_DIVERGES_TEXT))
        return card
    if _diverges(total):
        card.add_group("find_integral", *steps)
        return card
    try:
        answer_node = _value_node(total)
    except Exception:
        return None
    stage = _transform(KEY_IMP_VALUE, studied, answer_node)
    if stage is not None:
        steps.append(stage)
    card.add_group("find_integral", *steps)
    card.set_solution(answer_node)
    return card


def _euler_poisson_card(
    node: CoreNode,
    expression: sympy.Expr,
    variable: sympy.Symbol,
    lower: sympy.Expr,
    upper: sympy.Expr,
) -> SolveResult | None:
    if expression != sympy.exp(-(variable**2)) or lower != 0 or upper != sympy.oo:
        return None
    try:
        value = sympy.integrate(expression, (variable, lower, upper))
    except (TypeError, ValueError, NotImplementedError):
        return None
    if value.has(sympy.Integral) or _diverges(value):
        return None
    answer_node = _value_node(value)
    card = SolveResult(header=HEADER_EULER)
    fact = _node(T.EQUALS, node, answer_node)
    card.add_group("find_integral", _fact(KEY_EULER, fact))
    card.set_solution(answer_node)
    return card


def definite_cards(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """Textbook cards of a definite integral (main method first), or ``[]``."""
    if node.type is not T.INTEGRAL_DEFINITE or len(node.children) != 3:
        return []
    lower_node, upper_node, body_node = node.children
    try:
        expression = to_sympy(body_node)
        lower, upper = to_sympy(lower_node), to_sympy(upper_node)
    except Exception:
        return []
    variable = _variable_of(expression, variables)
    if variable is None:
        return []
    euler = _euler_poisson_card(node, expression, variable, lower, upper)
    if euler is not None:
        return [euler]
    infinite = lower in (sympy.oo, -sympy.oo) or upper in (sympy.oo, -sympy.oo)
    singular = None
    if not infinite:
        singular = _endpoint_singularity(expression, variable, lower, upper)
        if singular is None and _real_singularities(expression, variable, lower, upper):
            return _interior_divergence(node, expression, variable, lower, upper)
    elif lower == -sympy.oo and upper == sympy.oo:
        try:
            if sympy.simplify(expression.subs(variable, -variable) - expression) != 0:
                return []
        except (TypeError, ValueError):
            return []
    if infinite or singular is not None:
        card = _improper_card(
            node,
            body_node,
            expression,
            variable,
            lower_node,
            upper_node,
            lower,
            upper,
            variables,
            singular,
        )
        return [card] if card is not None else []
    parity = _parity_cards(
        node, body_node, expression, variable, lower_node, upper_node, lower, upper, variables
    )
    if parity:
        return parity
    cards: list[SolveResult] = []
    if not is_table(expression, variable) or is_linear_table(expression, variable):
        substitution = find_substitution(expression, variable)
        if substitution is not None:
            card = _substitution_card(
                node,
                body_node,
                expression,
                variable,
                lower_node,
                upper_node,
                lower,
                upper,
                substitution,
                variables,
            )
            if card is not None:
                cards.append(card)
    newton = _newton_card(
        body_node, expression, variable, lower_node, upper_node, lower, upper, variables
    )
    if newton is not None:
        cards.append(newton)
    return cards


def _real_singularities(
    expression: sympy.Expr, variable: sympy.Symbol, lower: sympy.Expr, upper: sympy.Expr
) -> list[sympy.Expr]:
    """Real points where the integrand is undefined, strictly inside the interval."""
    try:
        found = sympy.singularities(expression, variable)
    except (TypeError, ValueError, NotImplementedError):
        return []
    if not isinstance(found, sympy.FiniteSet):
        return []
    inside: list[sympy.Expr] = []
    for point in found:
        if point.is_real is not True:
            continue
        if sympy.simplify(point - lower) == 0 or sympy.simplify(point - upper) == 0:
            continue
        try:
            if float(sympy.N(lower)) < float(sympy.N(point)) < float(sympy.N(upper)):
                inside.append(point)
        except (TypeError, ValueError):
            continue
    return inside


def _interior_divergence(
    node: CoreNode,
    expression: sympy.Expr,
    variable: sympy.Symbol,
    lower: sympy.Expr,
    upper: sympy.Expr,
) -> list[SolveResult]:
    """A discontinuity inside the interval: mostly an answer card «расходится»."""
    try:
        total = sympy.integrate(expression, (variable, lower, upper))
    except (TypeError, ValueError, NotImplementedError):
        return []
    if not _diverges(total):
        return []
    card = SolveResult(header=HEADER_DIVERGES)
    fact = _node(T.EQUALS, node, CoreNode.constant("∞"))
    card.add_group("find_integral", _fact(KEY_IMP_DIVERGES, fact))
    card.set_solution(CoreNode(type=T.TEXT, value=_DIVERGES_TEXT))
    return [card]


def _endpoint_singularity(
    expression: sympy.Expr, variable: sympy.Symbol, lower: sympy.Expr, upper: sympy.Expr
) -> sympy.Expr | None:
    """The point where the integrand is undefined, only at an endpoint."""
    try:
        found = sympy.singularities(expression, variable)
    except (TypeError, ValueError, NotImplementedError):
        return None
    if not isinstance(found, sympy.FiniteSet):
        return None
    for point in found:
        if point.is_real is not True:
            continue
        if sympy.simplify(point - lower) == 0 or sympy.simplify(point - upper) == 0:
            return point
    return None


# ── the verified «find total area» card ───────────────────────────────
#
# f(x) from the integral, its x-intercepts, the
# interval split at those points (or the note that there are none), the
# absolute values of the pieces, their sum and the final «… square units».

_AREA_INITIAL = "total_area_initial"
_AREA_SEP = "total_area_sep_smpl"
_AREA_X_INTERCEPT = "total_area_x_intercept_smpl"
_AREA_FUN = "total_area_fun_smpl"
_AREA_FINAL = "total_area_final_smpl"


def _function_f(variable: sympy.Symbol) -> CoreNode:
    return CoreNode(type=T.FUNCTION, value="f", children=[_var(str(variable))])


def _closed_interval(low: CoreNode, high: CoreNode) -> CoreNode:
    return _node(T.CLOSED_CLOSED_INTERVAL, low, high)


def _fold_sum(values: list[CoreNode]) -> CoreNode:
    result = values[0]
    for value in values[1:]:
        result = _node(T.ADD, result, value)
    return result


def _area_roots(
    expression: sympy.Expr, variable: sympy.Symbol, lower: sympy.Expr, upper: sympy.Expr
) -> list[sympy.Expr]:
    """Real x-intercepts of ``f`` inside ``[lower, upper]``, in page order."""
    try:
        found = sympy.solve(sympy.Eq(expression, 0), variable)
    except (TypeError, ValueError, NotImplementedError):
        return []
    inside: list[sympy.Expr] = []
    for root in found:
        if root.is_real is False:
            continue
        try:
            value = float(sympy.N(root))
        except (TypeError, ValueError):
            continue
        if float(sympy.N(lower)) <= value <= float(sympy.N(upper)):
            inside.append(root)
    inside.sort(key=lambda item: float(sympy.N(item)))
    return inside


def _area_x_intercept(
    body_node: CoreNode, roots: list[sympy.Expr], variable: sympy.Symbol
) -> tuple[CoreNode, SolveResult]:
    """The «find the x-intercepts» screen and its result node."""
    x = _var(str(variable))
    zero = _num(0)
    f_eq = _node(T.EQUALS, _function_f(variable), body_node)
    substituted = _node(T.EQUALS, zero, body_node)
    detail = SolveResult()
    detail.add_group(
        CoreRichText(type="substitute", args=[f_eq]),
        Step(
            f_eq,
            substituted,
            "x_intercept_substitute",
            [x, _node(T.EQUALS, _function_f(variable), zero)],
        ),
    )
    if not roots:
        flipped = _node(T.EQUALS, body_node, zero)
        guarded = _node(T.LIST, flipped, _node(T.NOT_EQUALS, x, zero))
        detail.add_group(
            "rel_restrictions_range",
            Step(substituted, guarded, "rel_restrictions_range"),
        )
        detail.add_group("rel_switch", Step(guarded, flipped, "rel_swap_eq"))
        numerator = sympy.fraction(sympy.together(to_sympy(body_node)))[0]
        trivial = _node(T.EQUALS, from_sympy(numerator), zero)
        detail.add_group("rel_switch", Step(flipped, trivial, "eq_linear_frac_zero", [zero]))
        result = _node(T.ELEMENT_OF, x, CoreNode(type=T.EMPTY))
        detail.add_group("rel_switch", Step(trivial, result, "rel_el_of_zero", [x]))
        detail.set_solution(result)
        return result, detail
    flipped = _node(T.EQUALS, body_node, zero)
    detail.add_group("rel_switch", Step(substituted, flipped, "rel_swap_eq"))
    if len(roots) == 1:
        result = _node(T.EQUALS, x, from_sympy(roots[0]))
        detail.add_group(
            CoreRichText(type="log_set_base_zero", args=[zero]),
            Step(flipped, result, "eq_quad_exp_zero", [zero]),
        )
    else:
        result = _node(T.VERTICAL_LIST, *[_node(T.EQUALS, x, from_sympy(root)) for root in roots])
        detail.add_group("rel_switch", Step(flipped, result, "rel_swap_eq"))
    detail.set_solution(result)
    return result, detail


def _area_piece(
    body_node: CoreNode,
    expression: sympy.Expr,
    variable: sympy.Symbol,
    low_node: CoreNode,
    high_node: CoreNode,
    low: sympy.Expr,
    high: sympy.Expr,
) -> tuple[CoreNode, sympy.Expr, SolveResult] | None:
    """One piece: its definite node, its signed value and the app's chain."""
    piece_node = _definite_node(low_node, high_node, body_node)
    built = _row_steps(piece_node, body_node, expression, variable, low_node, high_node, low, high)
    if built is None:
        return None
    _value_node, steps = built
    try:
        value = sympy.simplify(sympy.integrate(expression, (variable, low, high)))
    except (TypeError, ValueError, NotImplementedError):
        return None
    if value.has(sympy.Integral) or _diverges(value):
        return None
    return piece_node, value, _row_card(steps, from_sympy(value))


def definite_area_card(node: CoreNode, variables: list[str]) -> SolveResult | None:
    """The verified «find total area» card (the answer is «… square units»)."""
    if node.type is not T.INTEGRAL_DEFINITE or len(node.children) != 3:
        return None
    lower_node, upper_node, body_node = node.children
    try:
        expression = to_sympy(body_node)
        lower, upper = to_sympy(lower_node), to_sympy(upper_node)
    except Exception:
        return None
    if not (lower.is_real is True and upper.is_real is True and lower < upper):
        return None
    variable = _variable_of(expression, variables)
    if variable is None or expression == 0:
        return None
    roots = _area_roots(expression, variable, lower, upper)
    inside = [
        root
        for root in roots
        if sympy.simplify(root - lower) != 0 and sympy.simplify(root - upper) != 0
    ]
    points: list[sympy.Expr] = [lower, *inside, upper] if inside else [lower, upper]
    pieces = []
    for start, end in itertools.pairwise(points):
        piece = _area_piece(
            body_node,
            expression,
            variable,
            from_sympy(start),
            from_sympy(end),
            start,
            end,
        )
        if piece is None:
            return None
        pieces.append(piece)
    total = sympy.simplify(sum(sympy.Abs(piece[1]) for piece in pieces))
    answer = _node(
        T.TEXT,
        CoreNode(type=T.TEXT_KEY, value="square_units"),
        _node(T.EQUALS, _var("A"), from_sympy(total)),
    )
    x = _var(str(variable))
    f_eq = _node(T.EQUALS, _function_f(variable), body_node)
    card = SolveResult(header="total_area")
    card.add_group(_AREA_FUN, Step(node, f_eq, "total_area_fun"))
    intercept, intercept_detail = _area_x_intercept(body_node, roots, variable)
    card.add_group(
        CoreRichText(type=_AREA_X_INTERCEPT, args=[x]),
        Step(f_eq, intercept, "total_area_x_intercept", [x], subresult=intercept_detail),
    )
    integral_node = _integral(body_node)
    if not inside:
        bounds = _closed_interval(lower_node, upper_node)
        endpoint = any(sympy.simplify(root - lower) == 0 for root in roots)
        if endpoint:
            key, args = "total_area_endpoint_zero", [lower_node, bounds]
        else:
            key, args = "total_area_no_zeros", [bounds]
        first = _node(T.EQUALS, _var("A"), _node(T.ABS, integral_node))
        card.add_group(_AREA_INITIAL, Step(intercept, first, key, args))
        _piece_node, value, chain = pieces[0]
        with_value = _node(T.EQUALS, _var("A"), _node(T.ABS, from_sympy(value)))
        card.add_group("integrate_calc", Step(first, with_value, "integrate_def", subresult=chain))
        stripped = _node(T.EQUALS, _var("A"), from_sympy(sympy.Abs(value)))
        card.add_group("abs", Step(with_value, stripped, "abs_neg"))
        card.add_group(
            _AREA_FINAL,
            Step(
                _node(T.EQUALS, _var("A"), from_sympy(total)),
                answer,
                "total_area_final",
            ),
        )
        card.set_solution(answer)
        return card

    intervals = [
        _closed_interval(from_sympy(start), from_sympy(end))
        for start, end in itertools.pairwise(points)
    ]
    listed = _node(T.VERTICAL_LIST, *intervals)
    card.add_group(
        CoreRichText(
            type=_AREA_SEP,
            args=[_closed_interval(lower_node, upper_node)],
        ),
        Step(
            intercept,
            listed,
            "total_area_sep_interval_zero",
            [_closed_interval(lower_node, upper_node), from_sympy(inside[0])],
        ),
    )
    letters = [_var(f"A_{number}") for number in range(1, len(pieces) + 1)]

    def item(index: int, integrated: bool, absolute: bool) -> CoreNode:
        letter = letters[index]
        piece_node = pieces[index][0]
        if integrated:
            value = (
                from_sympy(sympy.Abs(pieces[index][1]))
                if absolute
                else from_sympy(pieces[index][1])
            )
            if absolute:
                return _node(T.EQUALS, letter, value)
            return _node(T.EQUALS, letter, _node(T.ABS, value))
        return _node(T.EQUALS, letter, _node(T.ABS, _integral(piece_node.children[2])))

    current = listed
    for index in range(len(pieces)):
        bits = [
            item(other, other < index, True)
            if other < index
            else item(index, False, False)
            if other == index
            else intervals[other]
            for other in range(len(pieces))
        ]
        created = _node(T.VERTICAL_LIST, *bits)
        card.add_group(
            CoreRichText(type="total_area_define", args=[letters[index]]),
            Step(
                current,
                created,
                "total_area_create",
                [letters[index], intervals[index]],
            ),
        )
        current = created
    for index in range(len(pieces)):
        bits = [
            item(other, other <= index, True) if other <= index else intervals[other]
            for other in range(len(pieces))
        ]
        # The current piece keeps its symbolic abs until its own integration row.
        bits[index] = item(index, False, False)
        evaluated = _node(T.VERTICAL_LIST, *bits)
        card.add_group(
            "integrate_calc_plural",
            Step(current, evaluated, "integrate_def", subresult=pieces[index][2]),
        )
        current = evaluated
    for _ in range(len(pieces)):
        bits = [item(other, True, True) for other in range(len(pieces))]
        stripped = _node(T.VERTICAL_LIST, *bits)
        if not current.structural_eq(stripped):
            card.add_group("calculate_abs_plural", Step(current, stripped, "abs_neg"))
            current = stripped
    values = [from_sympy(sympy.Abs(piece[1])) for piece in pieces]
    summed = _node(T.EQUALS, _var("A"), _fold_sum(values))
    card.add_group(
        "integrate_parts_sub_smpl",
        Step(
            current,
            summed,
            "total_area_sum",
            [
                _var("A"),
                _node(T.LIST, *letters),
                _node(T.EQUALS, _var("A"), _fold_sum(values)),
            ],
        ),
    )
    total_node = from_sympy(total)
    if not _fold_sum(values).structural_eq(total_node):
        card.add_group(
            "calc_sum",
            Step(summed, _node(T.EQUALS, _var("A"), total_node), "frac_add"),
        )
    card.add_group(
        _AREA_FINAL,
        Step(_node(T.EQUALS, _var("A"), total_node), answer, "total_area_final"),
    )
    card.set_solution(answer)
    return card


__all__ = [
    "definite_area_card",
    "definite_cards",
    "row_definite_card",
    "row_improper_card",
]
