"""Textbook cards of a second-order differential equation.

The cards follow the same rules as the first-order ones in :mod:`ode_cards`
(Filippov §§ 9–11, 19–21): a header names the method, a stage is either a fact
(no arrow) or a transformation ``left → right``, consecutive transformations
chain, no stage repeats itself and a text never repeats its own formula.
Integrations carry the integral card of :mod:`integral_cards` as their nested
«Подробнее»; the characteristic equation carries the quadratic-equation card.

Four methods are covered:

* reduction of order — ``y″ = f(x)`` (two integrations) and ``y″ = f(x, y′)``
  (``p = y′``, the first-order card for ``p`` nested, then ``y = ∫p dx + C₂``);
* a linear homogeneous equation with constant coefficients — the
  characteristic equation, its roots, the case and the fundamental system;
* a nonhomogeneous equation with a special right side — the homogeneous card,
  the trial form (with the resonance multiplier), the derivatives, the
  substituted equation, the coefficient system and the particular solution;
* the Cauchy problem — the general solution as the first step and the system
  for ``C₁`` and ``C₂`` from the initial conditions.

Every answer is checked with ``sympy.checkodesol`` (and every condition of a
Cauchy problem) before the card is offered; otherwise the caller keeps the
previous short answer.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, SolveResult, Step
from .diff_equations import (
    _KIND_CONSTANT_HOMOGENEOUS,
    _KIND_CONSTANT_SPECIAL,
    _KIND_REDUCIBLE,
    _KIND_REDUCTION,
    _abs_logs,
    _classification,
)
from .equations import solve_equation
from .ode_cards import (
    _bracket,
    _bracketed,
    _chain,
    _detail,
    _eq,
    _fact,
    _flatten,
    _fraction,
    _node,
    _num,
    _power,
    _product,
    _stages,
    _var,
)
from .sympy_bridge import from_sympy, to_sympy

# ── headers, step headings and stage keys ─────────────────────────────

_HEADER_REDUCTION = "lesson_calc_ode_header_reduction"
_HEADER_CONSTANT = "lesson_calc_ode_header_constant"
_HEADER_SPECIAL = "lesson_calc_ode_header_special"
_HEADER_CHARACTERISTIC = "lesson_calc_ode_header_characteristic"

_KEY_SOLVE = "eq_solve_short"
_STEP_HOMOGENEOUS = "lesson_calc_ode_step_homogeneous"
_STEP_PARTICULAR = "lesson_calc_ode_step_particular"
_STEP_GENERAL = "lesson_calc_ode_step_general"
_STEP_CONDITIONS = "lesson_calc_ode_step_conditions"

_KEY_RED_FIRST = "lesson_calc_ode_reduce_first"
_KEY_RED_SECOND = "lesson_calc_ode_reduce_second"
_KEY_RED_SUBSTITUTE = "lesson_calc_ode_reduce_substitute"
_KEY_RED_EQUATION = "lesson_calc_ode_reduce_equation"
_KEY_RED_SOLUTION = "lesson_calc_ode_reduce_solution"
_KEY_RED_INTEGRATE = "lesson_calc_ode_reduce_integrate"

_KEY_CHAR_EQUATION = "lesson_calc_ode_char_equation"
_KEY_CHAR_ROOTS = "lesson_calc_ode_char_roots"
_KEY_CHAR_DISCRIMINANT = "lesson_calc_ode_char_discriminant"
_KEY_CHAR_COMPLEX_ROOTS = "lesson_calc_ode_char_complex_roots"
_KEY_CHAR_CASE_DISTINCT = "lesson_calc_ode_char_case_distinct"
_KEY_CHAR_CASE_DOUBLE = "lesson_calc_ode_char_case_double"
_KEY_CHAR_CASE_COMPLEX = "lesson_calc_ode_char_case_complex"
_KEY_CHAR_GENERAL = "lesson_calc_ode_char_general"

_KEY_SPECIAL_FORM = "lesson_calc_ode_special_form"
_KEY_SPECIAL_FORM_EXP_RESONANCE = "lesson_calc_ode_special_form_exp_resonance"
_KEY_SPECIAL_FORM_TRIG_RESONANCE = "lesson_calc_ode_special_form_trig_resonance"
_KEY_SPECIAL_FORM_POLY_RESONANCE = "lesson_calc_ode_special_form_poly_resonance"
_KEY_SPECIAL_DERIVATIVES = "lesson_calc_ode_special_derivatives"
_KEY_SPECIAL_SUBSTITUTE = "lesson_calc_ode_special_substitute"
_KEY_SPECIAL_EQUATE = "lesson_calc_ode_special_equate"
_KEY_SPECIAL_SOLVE = "lesson_calc_ode_special_solve"
_KEY_SPECIAL_PARTICULAR = "lesson_calc_ode_special_particular"
_KEY_SPECIAL_GENERAL = "lesson_calc_ode_special_general"

_KEY_CONDITIONS_SYSTEM = "lesson_calc_ode_conditions_system"
_KEY_CONDITIONS_VALUES = "lesson_calc_ode_conditions_values"
_KEY_CONDITIONS_ANSWER = "lesson_calc_ode_conditions_answer"

_C1 = sympy.Symbol("C1")
_C2 = sympy.Symbol("C2")
_LAMBDA = sympy.Symbol("λ")
_Y_TILDE = "ỹ"

_Condition = tuple[int, sympy.Expr, sympy.Expr, CoreNode, CoreNode]

_CardAnswer = tuple[str, SolveResult, CoreNode]


@dataclass(slots=True)
class _Card:
    """A built card: header, stage groups, the general solution and the answer."""

    header: str
    groups: list[tuple[str, list[Step]]] = field(default_factory=list)
    general: sympy.Expr = field(default_factory=lambda: sympy.Integer(0))
    node: CoreNode | None = None
    format_particular: Callable[[dict[sympy.Symbol, sympy.Expr]], CoreNode] | None = None


# ── entry point ───────────────────────────────────────────────────────


def second_order_card(
    problem: CoreNode,
    equation: sympy.Eq,
    dep: str,
    xsym: sympy.Symbol,
    kind: str,
    conditions: list[_Condition],
) -> _CardAnswer | None:
    """Build the textbook card of a second-order equation, or ``None``."""
    yfun = sympy.Function(dep)
    symbol = sympy.Symbol(dep)
    second = _second_derivative(equation, yfun, xsym)
    if second is None:
        return None

    if kind == _KIND_REDUCTION:
        card = _reduction_card(problem, second, xsym, dep)
    elif kind == _KIND_REDUCIBLE:
        card = _reducible_card(problem, second, xsym, dep)
    elif kind in (_KIND_CONSTANT_HOMOGENEOUS, _KIND_CONSTANT_SPECIAL):
        parts = _constant_parts(second, yfun, xsym)
        if parts is None:
            return None
        a1, b1, forcing = parts
        if kind == _KIND_CONSTANT_HOMOGENEOUS:
            if sympy.simplify(forcing) != 0:
                return None
            card = _homogeneous_card(problem, a1, b1, xsym, dep)
        else:
            if sympy.simplify(forcing) == 0:
                return None
            card = _special_card(problem, a1, b1, forcing, xsym, dep)
    else:
        return None

    if card is None or card.node is None:
        return None
    if not _verified(equation, card.general, xsym, yfun, symbol):
        return None

    groups = list(card.groups)
    answer = card.node
    if conditions:
        applied = _apply_conditions(card, conditions, xsym, dep)
        if applied is None:
            return None
        particular, stages = applied
        if not _verified(equation, particular, xsym, yfun, symbol):
            return None
        if not _conditions_hold(particular, conditions, xsym):
            return None
        groups.append((_STEP_CONDITIONS, stages))
        particular_answer = stages[-1].right
        if particular_answer is None:
            return None
        answer = particular_answer

    result = SolveResult(header=card.header)
    for heading, stages in groups:
        result.add_group(heading, *stages)
    result.set_solution(answer)
    return card.header, result, answer


# ── common helpers ────────────────────────────────────────────────────


def _sx(expression: sympy.Expr, xsym: sympy.Symbol) -> CoreNode:
    """A formula of a stage, keeping the constants ``C1``/``C2``.

    :func:`ode_cards._expr` renames ``C1`` to ``C`` for first-order answers;
    a second-order card must keep the textbook ``C₁``/``C₂``.
    """
    expression = sympy.sympify(expression)
    with contextlib.suppress(NotImplementedError, TypeError, ValueError):
        expression = sympy.simplify(expression)
        expression = sympy.trigsimp(expression)
    expression = _abs_logs(expression, xsym)
    numerator, denominator = sympy.fraction(expression)
    if expression.could_extract_minus_sign() and numerator.is_number and denominator.is_Add:
        return _fraction(_sx(-numerator, xsym), _sx(-denominator, xsym))
    return from_sympy(expression)


def _stage_expr(expression: sympy.Expr, xsym: sympy.Symbol) -> CoreNode:
    """An expanded stage formula (``x ln|x| − x``, not ``x(ln|x| − 1)``)."""
    expanded = sympy.expand(expression)
    return from_sympy(_abs_logs(expanded, xsym))


def _polynomial_node(expression: sympy.Expr, xsym: sympy.Symbol) -> CoreNode:
    """A polynomial in descending powers: ``λ² − 3λ + 2``."""
    try:
        polynomial = sympy.Poly(expression, xsym)
    except (sympy.PolynomialError, TypeError, ValueError):
        return _sx(expression, xsym)
    parts: list[tuple[bool, CoreNode]] = []
    for (power,), coefficient in sorted(
        polynomial.terms(), key=lambda item: item[0][0], reverse=True
    ):
        negative = bool(coefficient.could_extract_minus_sign())
        magnitude = -coefficient if negative else coefficient
        if power == 0:
            term = _sx(magnitude, xsym)
        elif magnitude == 1:
            term = _power(_var(str(xsym)), _num(int(power))) if power != 1 else _var(str(xsym))
        else:
            base = _var(str(xsym)) if power == 1 else _power(_var(str(xsym)), _num(int(power)))
            term = _product(_sx(magnitude, xsym), base)
        parts.append((negative, term))
    return _chain(parts) if parts else _num(0)


def _second_derivative(
    equation: sympy.Eq, yfun: sympy.Function, xsym: sympy.Symbol
) -> sympy.Expr | None:
    """The right side of ``y″ = …`` solved from the equation."""
    second = sympy.Derivative(yfun(xsym), (xsym, 2))
    try:
        solutions = sympy.solve(equation, second)
    except (NotImplementedError, TypeError, ValueError):
        return None
    if len(solutions) != 1:
        return None
    return sympy.expand(solutions[0])


def _constant_parts(
    second: sympy.Expr, yfun: sympy.Function, xsym: sympy.Symbol
) -> tuple[sympy.Expr, sympy.Expr, sympy.Expr] | None:
    """``(a₁, b₁, f)`` for ``y″ = a₁y′ + b₁y + f`` with constant coefficients."""
    first = sympy.Derivative(yfun(xsym), xsym)
    value = yfun(xsym)
    try:
        a1 = sympy.simplify(sympy.diff(second, first))
        b1 = sympy.simplify(sympy.diff(second, value))
        if a1.has(value, first) or b1.has(value, first):
            return None
        if not (a1.is_number and b1.is_number):
            return None
        forcing = sympy.simplify(second - a1 * first - b1 * value)
    except (NotImplementedError, TypeError, ValueError):
        return None
    if forcing.has(value, first):
        return None
    return a1, b1, forcing


def _exp_node(power: sympy.Expr, xsym: sympy.Symbol) -> CoreNode:
    """``e^(power)`` as a node, with ``e⁰ = 1`` written as just 1."""
    simplified = sympy.simplify(power)
    if simplified == 0:
        return _num(1)
    return _node(T.EXP, _sx(simplified, xsym))


def _term(coefficient: sympy.Expr, xsym: sympy.Symbol) -> tuple[bool, CoreNode]:
    negative = bool(coefficient.could_extract_minus_sign())
    return negative, _sx(-coefficient if negative else coefficient, xsym)


def _sum_node(expressions: list[sympy.Expr], xsym: sympy.Symbol) -> CoreNode:
    """A sum of expressions, each possibly zero (the zero terms are skipped)."""
    parts: list[tuple[bool, CoreNode]] = []
    for expression in expressions:
        simplified = sympy.simplify(expression)
        if simplified == 0:
            continue
        parts.append(_term(simplified, xsym))
    return _chain(parts) if parts else _num(0)


def _particular_signed(expression: sympy.Expr, xsym: sympy.Symbol) -> list[tuple[bool, CoreNode]]:
    """Signed terms of a particular solution, ``(x/2)cos x`` as the book writes it."""
    parts: list[tuple[bool, CoreNode]] = []
    for term in sympy.Add.make_args(sympy.expand(expression)):
        negative = bool(term.could_extract_minus_sign())
        positive = -term if negative else term
        coefficient, rest = positive.as_coeff_Mul()
        remainder = rest.coeff(xsym) if rest.has(xsym) else sympy.Integer(0)
        divisible = remainder != 0 and sympy.simplify(rest - xsym * remainder) == 0
        if isinstance(coefficient, sympy.Rational) and coefficient.q != 1 and divisible:
            numerator = (
                _var(str(xsym))
                if coefficient.p == 1
                else _product(_num(int(coefficient.p)), _var(str(xsym)))
            )
            x_part = _fraction(numerator, _num(int(coefficient.q)))
            parts.append((negative, _product(x_part, _sx(remainder, xsym))))
        else:
            parts.append((negative, _sx(positive, xsym)))
    return parts


# ── reduction of order: y″ = f(x) ─────────────────────────────────────


def _reduction_card(
    problem: CoreNode, second: sympy.Expr, xsym: sympy.Symbol, dep: str
) -> _Card | None:
    first = sympy.Derivative(sympy.Function(dep)(xsym), xsym)
    if second.has(sympy.Function(dep)(xsym), first):
        return None
    try:
        primitive = sympy.integrate(second, xsym)
        twice = sympy.integrate(primitive, xsym)
    except (NotImplementedError, TypeError, ValueError):
        return None
    if primitive.has(sympy.Integral) or twice.has(sympy.Integral):
        return None

    first_side = _sum_node([primitive, _C1], xsym)
    answer_side = _reduction_answer(twice, _C1, _C2, xsym)
    stages = [_fact(_KIND_REDUCTION, problem)]
    stages.extend(
        _stages(
            _KEY_RED_FIRST,
            problem,
            _eq(_node(T.PRIME, _var(dep)), first_side),
            subresult=_detail(second, xsym),
        )
    )
    stages.extend(
        _stages(
            _KEY_RED_SECOND,
            _eq(_node(T.PRIME, _var(dep)), first_side),
            _eq(_var(dep), answer_side),
            subresult=_detail(primitive, xsym),
        )
    )
    if len(stages) < 2:
        return None

    card = _Card(_HEADER_REDUCTION)
    card.groups.append((_KEY_SOLVE, stages))
    card.general = twice + _C1 * xsym + _C2
    card.node = _eq(_var(dep), answer_side)
    card.format_particular = lambda values: _eq(
        _var(dep),
        _reduction_answer(
            twice,
            values.get(_C1, _C1),
            values.get(_C2, _C2),
            xsym,
        ),
    )
    return card


def _reduction_answer(
    primitive: sympy.Expr,
    first_constant: sympy.Expr,
    second_constant: sympy.Expr,
    xsym: sympy.Symbol,
) -> CoreNode:
    """``∫∫f dx dx + C₁x + C₂``: the primitive first, then the constants."""
    parts = _flatten(_stage_expr(primitive, xsym))
    if sympy.simplify(first_constant) != 0:
        parts = parts + _flatten(_stage_expr(first_constant * xsym, xsym))
    if sympy.simplify(second_constant) != 0:
        parts = parts + _flatten(_stage_expr(second_constant, xsym))
    return _chain(parts)


# ── reduction of order: y″ = f(x, y′) ─────────────────────────────────


def _reducible_card(
    problem: CoreNode, second: sympy.Expr, xsym: sympy.Symbol, dep: str
) -> _Card | None:
    from .ode_cards import first_order_card

    first = sympy.Derivative(sympy.Function(dep)(xsym), xsym)
    if not second.has(first):
        return None
    pfun = sympy.Function("p")
    try:
        in_p = sympy.simplify(second.subs(first, pfun(xsym)))
    except (NotImplementedError, TypeError, ValueError):
        return None
    if in_p.has(first) or in_p.has(sympy.Function(dep)(xsym)):
        return None

    p_equation = sympy.Eq(sympy.Derivative(pfun(xsym), xsym) - in_p, 0)
    kind_p, _potential = _classification(p_equation, pfun(xsym), xsym, 1)
    p_right = _sx(in_p.subs(pfun(xsym), sympy.Symbol("p")), xsym)
    p_problem = _eq(_node(T.PRIME, _var("p")), p_right)
    nested = first_order_card(p_problem, p_equation, "p", str(xsym), kind_p, [])
    if nested is None:
        return None
    _header, nested_result, nested_answer = nested
    if nested_answer.type is not T.EQUALS or len(nested_answer.children) != 2:
        return None
    _rename_variable(nested_result, "C", "C1")
    answer_right = _rename_node(nested_answer.children[1], "C", "C1")
    try:
        p_expression = to_sympy(answer_right).subs(sympy.Symbol("C"), _C1)
        primitive = sympy.integrate(p_expression, xsym)
    except (SolveError, NotImplementedError, TypeError, ValueError):
        return None
    if primitive.has(sympy.Integral):
        return None

    p_solution = _eq(_var("p"), answer_right)
    answer_side = _reduction_answer(primitive, sympy.Integer(0), _C2, xsym)
    # «Понизим порядок уравнения заменой y′ = p(x)»: the substitution is a part
    # of the sentence, the stage below states the new pair of variables.
    substitution = _eq(
        _node(T.PRIME, _var(dep)),
        CoreNode(type=T.FUNCTION, value="p", children=[_var(str(xsym))]),
    )
    stages = [
        _fact(_KIND_REDUCIBLE, problem, args=[substitution]),
        _fact(
            _KEY_RED_SUBSTITUTE,
            _eq(_var("p"), _node(T.PRIME, _var(dep))),
            _eq(_node(T.DERIVATION2_PRIME, _var(dep)), _node(T.PRIME, _var("p"))),
            args=[substitution],
        ),
    ]
    stages.extend(
        _stages(
            _KEY_RED_EQUATION,
            problem,
            p_problem,
            subresult=nested_result,
        )
    )
    stages.append(_fact(_KEY_RED_SOLUTION, p_solution))
    stages.extend(
        _stages(
            _KEY_RED_INTEGRATE,
            p_solution,
            _eq(_var(dep), answer_side),
            subresult=_detail(p_expression, xsym),
            args=[_eq(_node(T.PRIME, _var(dep)), _var("p"))],
        )
    )
    if len(stages) < 4:
        return None

    card = _Card(_HEADER_REDUCTION)
    card.groups.append((_KEY_SOLVE, stages))
    card.general = primitive + _C2
    card.node = _eq(_var(dep), answer_side)
    card.format_particular = lambda values: _eq(
        _var(dep),
        _reduction_answer(
            primitive,
            sympy.Integer(0),
            values.get(_C2, _C2),
            xsym,
        ),
    )
    return card


def _rename_node(node: CoreNode, old: str, new: str) -> CoreNode:
    if node.type is T.VARIABLE and node.value == old:
        return _var(new)
    if not node.children:
        return node
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[_rename_node(child, old, new) for child in node.children],
    )


def _rename_variable(result: SolveResult, old: str, new: str) -> None:
    """Rename an integration constant inside a nested card (``C`` → ``C1``)."""
    for step in result:
        if step.left is not None:
            step.left = _rename_node(step.left, old, new)
        if step.right is not None:
            step.right = _rename_node(step.right, old, new)
        step.args = [_rename_node(argument, old, new) for argument in step.args]


# ── constant coefficients ─────────────────────────────────────────────


def _char_equation(a1: sympy.Expr, b1: sympy.Expr) -> sympy.Expr:
    """``λ² − a₁λ − b₁ = 0`` for ``y″ = a₁y′ + b₁y + f``."""
    return _LAMBDA**2 - a1 * _LAMBDA - b1


def _homogeneous_card(
    problem: CoreNode, a1: sympy.Expr, b1: sympy.Expr, xsym: sympy.Symbol, dep: str
) -> _Card | None:
    built = _homogeneous_stages(problem, a1, b1, xsym, dep)
    if built is None:
        return None
    stages, general, node = built
    card = _Card(_HEADER_CONSTANT)
    card.groups.append((_KEY_SOLVE, stages))
    card.general = general
    card.node = node
    return card


def _homogeneous_stages(
    problem: CoreNode,
    a1: sympy.Expr,
    b1: sympy.Expr,
    xsym: sympy.Symbol,
    dep: str,
) -> tuple[list[Step], sympy.Expr, CoreNode] | None:
    """Stages from the characteristic equation to ``y = C₁y₁ + C₂y₂``."""
    characteristic = _char_equation(a1, b1)
    discriminant = sympy.simplify(a1**2 + 4 * b1)
    if discriminant.is_negative is None or discriminant.is_real is not True:
        return None

    char_node = _eq(_polynomial_node(characteristic, _LAMBDA), _num(0))
    stages: list[Step] = [
        _fact(_KIND_CONSTANT_HOMOGENEOUS, problem),
        _fact(_KEY_CHAR_EQUATION, char_node),
    ]

    if discriminant.is_negative:
        alpha = sympy.simplify(a1 / 2)
        beta = sympy.simplify(sympy.sqrt(-discriminant) / 2)
        roots_node = _node(
            T.LIST,
            _eq(_var("λ"), _complex_node(alpha, beta, xsym, +1)),
            _eq(_var("λ"), _complex_node(alpha, beta, xsym, -1)),
        )
        stages.append(
            Step(
                char_node,
                roots_node,
                _KEY_CHAR_ROOTS,
                subresult=_complex_detail(discriminant, alpha, beta, xsym),
            )
        )
        first = _node(T.EXP, _sx(alpha * xsym, xsym))
        cos_node = _node(T.COS, _sx(beta * xsym, xsym))
        sin_node = _node(T.SIN, _sx(beta * xsym, xsym))
        y1 = _product(first, cos_node) if alpha != 0 else cos_node
        y2 = _product(first, sin_node) if alpha != 0 else sin_node
        stages.append(
            Step(
                _node(
                    T.LIST,
                    _eq(_var("y1"), y1),
                    _eq(_var("y2"), y2),
                ),
                None,
                _KEY_CHAR_CASE_COMPLEX,
                args=[_sx(alpha, xsym), _sx(beta, xsym)],
            )
        )
        inner = _chain(
            [
                (False, _product(_var("C1"), cos_node)),
                (False, _product(_var("C2"), sin_node)),
            ]
        )
        if alpha != 0:
            answer_side = _product(first, _bracket(inner))
            general = sympy.exp(alpha * xsym) * (
                _C1 * sympy.cos(beta * xsym) + _C2 * sympy.sin(beta * xsym)
            )
        else:
            answer_side = inner
            general = _C1 * sympy.cos(beta * xsym) + _C2 * sympy.sin(beta * xsym)
    elif discriminant == 0:
        root = sympy.simplify(a1 / 2)
        roots_node = _eq(_var("λ"), _sx(root, xsym))
        stages.extend(
            _stages(
                _KEY_CHAR_ROOTS,
                char_node,
                roots_node,
                subresult=_quadratic_detail(characteristic),
            )
        )
        first = _exp_node(root * xsym, xsym)
        y2 = _product(_var(str(xsym)), first)
        stages.append(
            _fact(
                _KEY_CHAR_CASE_DOUBLE,
                _eq(_var("y1"), first),
                _eq(_var("y2"), y2),
            )
        )
        inner = _chain([(False, _var("C1")), (False, _product(_var("C2"), _var(str(xsym))))])
        answer_side = _product(_bracket(inner), first) if root != 0 else inner
        general = (_C1 + _C2 * xsym) * sympy.exp(root * xsym)
    else:
        square = sympy.sqrt(discriminant)
        first_root, second_root = _ordered_roots(
            [sympy.simplify((a1 - square) / 2), sympy.simplify((a1 + square) / 2)]
        )
        roots_node = _node(
            T.LIST,
            _eq(_var("λ"), _sx(first_root, xsym)),
            _eq(_var("λ"), _sx(second_root, xsym)),
        )
        stages.extend(
            _stages(
                _KEY_CHAR_ROOTS,
                char_node,
                roots_node,
                subresult=_quadratic_detail(characteristic),
            )
        )
        y1_node = _exp_node(first_root * xsym, xsym)
        y2_node = _exp_node(second_root * xsym, xsym)
        stages.append(
            _fact(
                _KEY_CHAR_CASE_DISTINCT,
                _eq(_var("y1"), y1_node),
                _eq(_var("y2"), y2_node),
            )
        )
        answer_side = _chain(
            [
                (False, _product(_var("C1"), y1_node)),
                (False, _product(_var("C2"), y2_node)),
            ]
        )
        general = _C1 * sympy.exp(first_root * xsym) + _C2 * sympy.exp(second_root * xsym)

    node = _eq(_var(dep), answer_side)
    fundamental = stages[-1].left
    if fundamental is None:
        return None
    stages.extend(_stages(_KEY_CHAR_GENERAL, fundamental, node))
    if not any(stage.key == _KEY_CHAR_GENERAL for stage in stages):
        return None
    return stages, general, node


def _ordered_roots(roots: list[sympy.Expr]) -> tuple[sympy.Expr, sympy.Expr]:
    """Textbook order: nonnegative roots first, then the negative ones."""

    def key(value: sympy.Expr) -> tuple[bool, float]:
        return bool(value.is_negative), float(sympy.N(value, 12))

    first, second = sorted(roots, key=key)
    return first, second


def _complex_node(alpha: sympy.Expr, beta: sympy.Expr, xsym: sympy.Symbol, sign: int) -> CoreNode:
    """``α + βi`` or ``α − βi``."""
    imaginary = _var("i") if beta == 1 else _product(_sx(beta, xsym), _var("i"))
    if alpha == 0:
        return imaginary if sign > 0 else _node(T.NEGATIVE, imaginary)
    if sign > 0:
        return _chain([(False, _sx(alpha, xsym)), (False, imaginary)])
    return _chain([(False, _sx(alpha, xsym)), (True, imaginary)])


def _quadratic_detail(characteristic: sympy.Expr) -> SolveResult | None:
    """The quadratic-equation card of ``λ² − a₁λ − b₁ = 0`` as a nested detail."""
    result = SolveResult(header=_HEADER_CHARACTERISTIC)
    ctx = SolveContext(result=result, variables=["λ"])
    equation = _eq(_polynomial_node(characteristic, _LAMBDA), _num(0))
    try:
        answer = solve_equation(equation, ctx)
    except (SolveError, NotImplementedError, TypeError, ValueError):
        return None
    if not result:
        return None
    result.set_solution(answer)
    return _without_noops(result)


def _without_noops(result: SolveResult) -> SolveResult:
    """Drop stages with ``left == right`` from a reused card.

    The quadratic card always starts with «приведём к стандартному виду»;
    for an equation that is already standard that stage would repeat itself,
    and a nested detail must follow the same rules as the outer card.
    """
    out = SolveResult(header=result.header)
    for heads, steps in result._steps:
        kept = [
            step
            for step in steps
            if not (
                step.left is not None
                and step.right is not None
                and step.left.structural_eq(step.right)
            )
        ]
        if not kept:
            continue
        if heads:
            out.add_group(heads, *kept)
        else:
            for step in kept:
                out.add(step)
    out.solution = result.solution
    return out


def _complex_detail(
    discriminant: sympy.Expr,
    alpha: sympy.Expr,
    beta: sympy.Expr,
    xsym: sympy.Symbol,
) -> SolveResult:
    """Discriminant and complex roots: the quadratic card cannot show them."""
    result = SolveResult(header=_HEADER_CHARACTERISTIC)
    roots_node = _node(
        T.LIST,
        _eq(_var("λ1"), _complex_node(alpha, beta, xsym, +1)),
        _eq(_var("λ2"), _complex_node(alpha, beta, xsym, -1)),
    )
    result.add_group(
        _KEY_SOLVE,
        _fact(_KEY_CHAR_DISCRIMINANT, _eq(_var("D"), _sx(discriminant, xsym))),
        _fact(_KEY_CHAR_COMPLEX_ROOTS, roots_node),
    )
    result.set_solution(roots_node)
    return result


# ── special right side ────────────────────────────────────────────────


@dataclass(slots=True)
class _Trial:
    expression: sympy.Expr
    node: CoreNode
    coefficients: list[sympy.Symbol]
    kind: str
    basis: sympy.Expr | None = None
    degree: int = 0
    frequency: sympy.Expr | None = None
    multiplicity: int = 0


def _special_card(
    problem: CoreNode,
    a1: sympy.Expr,
    b1: sympy.Expr,
    forcing: sympy.Expr,
    xsym: sympy.Symbol,
    dep: str,
) -> _Card | None:
    homogeneous = _homogeneous_stages(problem, a1, b1, xsym, dep)
    if homogeneous is None:
        return None
    homogeneous_stages, general_homogeneous, homogeneous_node = homogeneous
    homogeneous_stages = [
        stage for stage in homogeneous_stages if stage.key != _KIND_CONSTANT_HOMOGENEOUS
    ]
    homogeneous_stages.insert(0, _fact(_KIND_CONSTANT_SPECIAL, problem))
    trial = _trial_form(forcing, a1, b1, xsym)
    if trial is None:
        return None
    if homogeneous_node.type is not T.EQUALS or len(homogeneous_node.children) != 2:
        return None
    homogeneous_side = homogeneous_node.children[1]

    trial_node = _eq(_var(_Y_TILDE), trial.node)
    derivatives = [
        _eq(
            _node(T.PRIME, _var(_Y_TILDE)),
            _sx(trial.expression.diff(xsym), xsym),
        ),
        _eq(
            _node(T.DERIVATION2_PRIME, _var(_Y_TILDE)),
            _sx(trial.expression.diff(xsym, 2), xsym),
        ),
    ]

    substituted_left = (
        trial.expression.diff(xsym, 2) - a1 * trial.expression.diff(xsym) - b1 * trial.expression
    )
    substituted_node = _eq(_sx(substituted_left, xsym), _sx(forcing, xsym))
    equations = _coefficient_equations(trial, substituted_left, forcing, xsym)
    if not equations:
        return None
    equations_node = _node(T.LIST, *[_eq(_sx(e.lhs, xsym), _sx(e.rhs, xsym)) for e in equations])
    try:
        solutions = sympy.solve(equations, trial.coefficients, dict=True)
    except (NotImplementedError, TypeError, ValueError):
        return None
    if len(solutions) != 1:
        return None
    values: dict[sympy.Symbol, sympy.Expr] = solutions[0]
    if any(symbol not in values for symbol in trial.coefficients):
        return None
    particular = sympy.simplify(trial.expression.subs(values))
    particular_node = _eq(_var(_Y_TILDE), _chain(_particular_signed(particular, xsym)))
    values_node = _node(
        T.LIST,
        *[_eq(_var(str(symbol)), _sx(values[symbol], xsym)) for symbol in trial.coefficients],
    )

    particular_stages: list[Step] = []
    if trial.multiplicity:
        if trial.kind == "exp":
            assert trial.basis is not None
            multiplier = (
                _var(str(xsym)) if trial.multiplicity == 1 else _power(_var(str(xsym)), _num(2))
            )
            particular_stages.append(
                Step(
                    trial_node,
                    None,
                    _KEY_SPECIAL_FORM_EXP_RESONANCE,
                    args=[_sx(trial.basis, xsym), _num(trial.multiplicity), multiplier],
                )
            )
        elif trial.kind == "trig":
            assert trial.frequency is not None
            particular_stages.append(
                Step(
                    trial_node,
                    None,
                    _KEY_SPECIAL_FORM_TRIG_RESONANCE,
                    args=[_sx(trial.frequency * sympy.I, xsym)],
                )
            )
        else:
            multiplier = (
                _var(str(xsym))
                if trial.multiplicity == 1
                else _power(_var(str(xsym)), _num(trial.multiplicity))
            )
            particular_stages.append(
                Step(
                    trial_node,
                    None,
                    _KEY_SPECIAL_FORM_POLY_RESONANCE,
                    args=[_num(trial.multiplicity), multiplier],
                )
            )
    else:
        particular_stages.append(_fact(_KEY_SPECIAL_FORM, trial_node))
    particular_stages.append(_fact(_KEY_SPECIAL_DERIVATIVES, *derivatives))
    particular_stages.extend(_stages(_KEY_SPECIAL_SUBSTITUTE, problem, substituted_node))
    particular_stages.append(_fact(_KEY_SPECIAL_EQUATE, equations_node))
    particular_stages.extend(_stages(_KEY_SPECIAL_SOLVE, equations_node, values_node))
    particular_stages.extend(_stages(_KEY_SPECIAL_PARTICULAR, values_node, particular_node))

    answer_side = _chain(_flatten(homogeneous_side) + _particular_signed(particular, xsym))
    answer_node = _eq(_var(dep), answer_side)
    general_stages = _stages(_KEY_SPECIAL_GENERAL, homogeneous_node, answer_node)
    if not general_stages:
        return None

    card = _Card(_HEADER_SPECIAL)
    card.groups.append((_STEP_HOMOGENEOUS, homogeneous_stages))
    card.groups.append((_STEP_PARTICULAR, particular_stages))
    card.groups.append((_STEP_GENERAL, general_stages))
    card.general = sympy.simplify(general_homogeneous + particular)
    card.node = answer_node

    def format_particular(values: dict[sympy.Symbol, sympy.Expr]) -> CoreNode:
        homogeneous_part = general_homogeneous.subs(values)
        return _eq(
            _var(dep),
            _chain(_flatten(_sx(homogeneous_part, xsym)) + _particular_signed(particular, xsym)),
        )

    card.format_particular = format_particular
    return card


def _trial_form(
    forcing: sympy.Expr, a1: sympy.Expr, b1: sympy.Expr, xsym: sympy.Symbol
) -> _Trial | None:
    characteristic = _char_equation(a1, b1)
    multiplicity_zero = _root_multiplicity(characteristic, sympy.Integer(0))

    if forcing.is_polynomial(xsym):
        degree = int(sympy.Poly(forcing, xsym).degree())
        if degree > 2 or degree < 0:
            return None
        names = ["A", "B", "C"][: degree + 1]
        symbols_ = [sympy.Symbol(name) for name in names]
        terms: list[CoreNode] = []
        for power in range(degree, -1, -1):
            symbol = symbols_[degree - power]
            if power == 0:
                terms.append(_var(str(symbol)))
            elif power == 1:
                terms.append(_product(_var(str(symbol)), _var(str(xsym))))
            else:
                terms.append(_product(_var(str(symbol)), _power(_var(str(xsym)), _num(power))))
        body = _chain([(False, term) for term in terms])
        expression = sum(symbol * xsym ** (degree - index) for index, symbol in enumerate(symbols_))
        node = body
        if multiplicity_zero:
            multiplier = (
                _var(str(xsym))
                if multiplicity_zero == 1
                else _power(_var(str(xsym)), _num(multiplicity_zero))
            )
            node = _product(multiplier, _bracketed(body))
            expression = xsym**multiplicity_zero * expression
        return _Trial(
            expression,
            node,
            symbols_,
            "poly",
            degree=degree,
            multiplicity=multiplicity_zero,
        )

    _coefficient, body = forcing.as_coeff_Mul()
    if isinstance(body, sympy.exp):
        argument = sympy.expand(body.args[0])
        slope = sympy.simplify(sympy.diff(argument, xsym))
        offset = sympy.simplify(argument - slope * xsym)
        if slope == 0 or slope.has(xsym) or offset != 0:
            return None
        multiplicity = _root_multiplicity(characteristic, slope)
        symbol = sympy.Symbol("A")
        expression = symbol * sympy.exp(slope * xsym)
        exp_node = _exp_node(slope * xsym, xsym)
        if multiplicity:
            multiplier = (
                _var(str(xsym))
                if multiplicity == 1
                else _power(_var(str(xsym)), _num(multiplicity))
            )
            node = _product(multiplier, _var("A"), exp_node)
            expression = xsym**multiplicity * expression
        else:
            node = _product(_var("A"), exp_node)
        return _Trial(expression, node, [symbol], "exp", basis=slope, multiplicity=multiplicity)

    frequency = _trig_frequency(forcing, xsym)
    if frequency is not None:
        multiplicity = 1 if _trig_resonates(a1, b1, frequency) else 0
        symbols_ = [sympy.Symbol("A"), sympy.Symbol("B")]
        cos_node = _node(T.COS, _sx(frequency * xsym, xsym))
        sin_node = _node(T.SIN, _sx(frequency * xsym, xsym))
        body = _chain(
            [
                (False, _product(_var("A"), cos_node)),
                (False, _product(_var("B"), sin_node)),
            ]
        )
        expression = symbols_[0] * sympy.cos(frequency * xsym) + symbols_[1] * sympy.sin(
            frequency * xsym
        )
        node = body
        if multiplicity:
            node = _product(_var(str(xsym)), _bracket(body))
            expression = xsym * expression
        return _Trial(
            expression,
            node,
            symbols_,
            "trig",
            frequency=frequency,
            multiplicity=multiplicity,
        )
    return None


def _root_multiplicity(characteristic: sympy.Expr, root: sympy.Expr) -> int:
    try:
        value = sympy.simplify(characteristic.subs(_LAMBDA, root))
    except (NotImplementedError, TypeError, ValueError):
        return 0
    if value != 0:
        return 0
    derivative = sympy.simplify(sympy.diff(characteristic, _LAMBDA).subs(_LAMBDA, root))
    return 1 if derivative != 0 else 2


def _trig_frequency(forcing: sympy.Expr, xsym: sympy.Symbol) -> sympy.Expr | None:
    """``ω`` when ``f`` is a combination of ``cos ωx`` and ``sin ωx``."""
    expanded = sympy.expand(forcing)
    frequencies: set[sympy.Expr] = set()
    for term in sympy.Add.make_args(expanded):
        found = False
        for function in term.atoms(sympy.cos, sympy.sin):
            argument = function.args[0]
            slope = sympy.simplify(sympy.diff(argument, xsym))
            if slope == 0 or slope.has(xsym):
                return None
            rest = sympy.simplify(argument - slope * xsym)
            if rest != 0:
                return None
            frequencies.add(sympy.Abs(slope))
            found = True
        if not found:
            return None
    if len(frequencies) != 1:
        return None
    return frequencies.pop()


def _trig_resonates(a1: sympy.Expr, b1: sympy.Expr, frequency: sympy.Expr) -> bool:
    return bool(sympy.simplify(a1) == 0 and sympy.simplify(b1 + frequency**2) == 0)


def _coefficient_equations(
    trial: _Trial, left: sympy.Expr, right: sympy.Expr, xsym: sympy.Symbol
) -> list[sympy.Eq]:
    """Equate the coefficients of like terms on the two sides."""
    equations: list[sympy.Eq] = []
    if trial.kind == "poly":
        left_poly = sympy.Poly(sympy.expand(left), xsym)
        right_poly = sympy.Poly(sympy.expand(right), xsym)
        for power in range(trial.degree, -1, -1):
            equations.append(
                sympy.Eq(
                    sympy.simplify(left_poly.coeff_monomial(xsym**power)),
                    sympy.simplify(right_poly.coeff_monomial(xsym**power)),
                )
            )
        return equations
    if trial.kind == "exp":
        assert trial.basis is not None
        factor = sympy.exp(trial.basis * xsym)
        equations.append(sympy.Eq(sympy.simplify(left / factor), sympy.simplify(right / factor)))
        return equations
    assert trial.frequency is not None
    frequency = trial.frequency
    left_expanded = sympy.expand(left)
    right_expanded = sympy.expand(right)
    for function in (sympy.cos(frequency * xsym), sympy.sin(frequency * xsym)):
        equations.append(
            sympy.Eq(
                sympy.simplify(left_expanded.coeff(function)),
                sympy.simplify(right_expanded.coeff(function)),
            )
        )
    return equations


# ── Cauchy conditions ─────────────────────────────────────────────────


def _apply_conditions(
    card: _Card,
    conditions: list[_Condition],
    xsym: sympy.Symbol,
    dep: str,
) -> tuple[sympy.Expr, list[Step]] | None:
    """The system for the constants, their values and the particular solution."""
    ordered = sorted(conditions, key=lambda item: item[0])
    constants = sorted(
        (
            symbol
            for symbol in card.general.free_symbols
            if isinstance(symbol, sympy.Symbol) and symbol.name.startswith("C")
        ),
        key=str,
    )
    if not constants:
        return None
    equations: list[sympy.Eq] = []
    for derivative_order, x_zero, value, _point_node, _value_node in ordered:
        derived = (
            card.general
            if derivative_order == 0
            else sympy.diff(card.general, xsym, derivative_order)
        )
        try:
            equations.append(sympy.Eq(sympy.simplify(derived.subs(xsym, x_zero)), value))
        except (NotImplementedError, TypeError, ValueError):
            return None
    try:
        solutions = sympy.solve(equations, constants, dict=True)
    except (NotImplementedError, TypeError, ValueError):
        return None
    if not solutions:
        return None
    values: dict[sympy.Symbol, sympy.Expr] = solutions[0]
    particular = sympy.simplify(card.general.subs(values))
    free = sorted(
        (
            symbol
            for symbol in particular.free_symbols
            if isinstance(symbol, sympy.Symbol) and symbol.name.startswith("C")
        ),
        key=str,
    )
    if free and len(free) < len(constants):
        particular = particular.subs(
            {old: sympy.Symbol(f"C{index + 1}") for index, old in enumerate(free)}
        )

    stages = [_fact(_KEY_CONDITIONS_SYSTEM, *_condition_nodes(card.general, ordered, xsym, dep))]
    value_nodes = [
        _eq(_var(str(symbol)), _sx(values[symbol], xsym))
        for symbol in constants
        if symbol in values
    ]
    if value_nodes:
        stages.append(_fact(_KEY_CONDITIONS_VALUES, *value_nodes))
    general_node = card.node
    if general_node is None:
        return None
    if card.format_particular is not None:
        particular_node = card.format_particular(values)
    else:
        particular_node = _eq(_var(dep), _sx(particular, xsym))
    stages.extend(_stages(_KEY_CONDITIONS_ANSWER, general_node, particular_node))
    if len(stages) < 2:
        return None
    return particular, stages


def _condition_nodes(
    general: sympy.Expr,
    conditions: list[_Condition],
    xsym: sympy.Symbol,
    dep: str,
) -> list[CoreNode]:
    """``y(0) = C₁ + C₂ = 0`` for every initial condition."""
    nodes: list[CoreNode] = []
    for derivative_order, x_zero, _value, point_node, value_node in conditions:
        if derivative_order == 0:
            left = _node(T.EVALUATE_EXPRESSION, _var(dep), point_node)
        elif derivative_order == 1:
            left = _node(T.EVALUATE_EXPRESSION, _node(T.PRIME, _var(dep)), point_node)
        else:
            left = _node(
                T.EVALUATE_EXPRESSION,
                _node(T.DERIVATION2_PRIME, _var(dep)),
                point_node,
            )
        derived = general if derivative_order == 0 else sympy.diff(general, xsym, derivative_order)
        middle = _sx(sympy.simplify(derived.subs(xsym, x_zero)), xsym)
        nodes.append(_node(T.EQUALS, left, middle, value_node))
    return nodes


def _conditions_hold(value: sympy.Expr, conditions: list[_Condition], xsym: sympy.Symbol) -> bool:
    for derivative_order, x_zero, expected, _point_node, _value_node in conditions:
        derived = value if derivative_order == 0 else sympy.diff(value, xsym, derivative_order)
        try:
            if sympy.simplify(derived.subs(xsym, x_zero) - expected) != 0:
                return False
        except (NotImplementedError, TypeError, ValueError):
            return False
    return True


# ── verification ──────────────────────────────────────────────────────


def _verified(
    equation: sympy.Eq,
    value: sympy.Expr,
    xsym: sympy.Symbol,
    yfun: sympy.Function,
    symbol: sympy.Symbol,
) -> bool:
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
            sympy.checkodesol(on_positive(equation), on_positive(solution), solve_for_func=False)[0]
        )
    except (NotImplementedError, TypeError, ValueError):
        return False


__all__ = ["second_order_card"]
