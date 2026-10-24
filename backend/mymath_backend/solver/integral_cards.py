"""The textbook card of an indefinite integral.

The first card a student sees names the Demidovich method and shows its formula:

* a table integral (also with a linear argument ``kx+b``);
* linearity of a sum, each piece's table integral behind its own «Подробнее»;
* substitution ``t = g(x)``, ``dt = g'(x) dx``, the integral in ``t``,
  back substitution and ``+ C``;
* the half-angle formula for ``sin²x`` and the identity ``sin³x = (1−cos²x)sin x``.

The card is built from the same expression the solver integrates and every
answer is checked with ``sympy.diff`` before it is offered.  When no transparent
card is available (by parts, partial fractions) the builder returns ``None`` and
the verified card stays the answer, as before.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .base import SolveError, SolveResult, Step
from .book_style import book_card, book_products
from .sympy_bridge import from_sympy, ordered_terms, tidy, to_sympy

_HEADER_TABLE = "lesson_calc_header_int_table"
_HEADER_LINEAR = "lesson_calc_header_int_linear"
_HEADER_SUM = "lesson_calc_header_int_sum"
_HEADER_SUBSTITUTION = "lesson_calc_header_int_substitution"
_HEADER_HALF_ANGLE = "lesson_calc_header_int_half_angle"
_HEADER_IDENTITY = "lesson_calc_header_int_identity"
_HEADER_PARTS = "lesson_calc_header_int_parts"
_HEADER_PARTS_FIRST = "lesson_calc_header_int_parts_first"
_HEADER_PARTS_SECOND = "lesson_calc_header_int_parts_second"
_HEADER_PARTS_NEXT = "lesson_calc_header_int_parts_next"
_HEADER_FRACTION = "lesson_calc_header_int_frac"
_HEADER_SQUARE = "lesson_calc_header_int_square"
_HEADER_NONELEM = "lesson_calc_header_int_nonelementary"

KEY_TABLE = "lesson_calc_int_table_rule"
KEY_ANSWER = "lesson_calc_int_answer"
KEY_LINEAR = "lesson_calc_int_linear_rule"
KEY_SUM = "lesson_calc_int_sum_rule"
KEY_EXPAND = "lesson_calc_int_expand"
KEY_SUBSTITUTE = "lesson_calc_int_substitute"
KEY_DIFFERENTIAL = "lesson_calc_int_differential"
KEY_REWRITE = "lesson_calc_int_rewrite"
KEY_INNER_TABLE = "lesson_calc_int_inner_table"
KEY_TERM_TABLE = "lesson_calc_int_term_table"
KEY_BACK = "lesson_calc_int_back_sub"
KEY_IDENTITY = "lesson_calc_int_identity"
KEY_SINE_HALF = "lesson_calc_int_sine_half_angle"
KEY_HALF_ANGLE = "lesson_calc_int_half_angle"
KEY_DX_EXPR = "lesson_calc_int_dx_expr"
KEY_FROM_SUB = "lesson_calc_int_from_substitution"

KEY_PARTS_FORMULA = "lesson_calc_int_parts_formula"
KEY_PARTS_CHOOSE = "lesson_calc_int_parts_choose"
KEY_PARTS_DIFFERENTIAL = "lesson_calc_int_parts_differential"
KEY_PARTS_APPLY = "lesson_calc_int_parts_apply"
KEY_PARTS_REMAINDER = "lesson_calc_int_parts_remainder"
KEY_PARTS_ANSWER = "lesson_calc_int_parts_answer"
KEY_PARTS_DEFINE = "lesson_calc_int_parts_cyclic_define"
KEY_PARTS_EQUATION = "lesson_calc_int_parts_cyclic_equation"
KEY_PARTS_MOVE = "lesson_calc_int_parts_cyclic_move"
KEY_PARTS_VALUE = "lesson_calc_int_parts_cyclic_value"

KEY_FRAC_DIVIDE = "lesson_calc_int_frac_divide"
KEY_FRAC_FACTOR = "lesson_calc_int_frac_factor"
KEY_FRAC_FORM = "lesson_calc_int_frac_form"
KEY_FRAC_EQUATIONS = "lesson_calc_int_frac_equations"
KEY_FRAC_COEFFS = "lesson_calc_int_frac_coeffs"
KEY_FRAC_NUMBERS = "lesson_calc_int_frac_numbers"
KEY_FRAC_SQUARE = "lesson_calc_int_frac_square"
KEY_FRAC_SPLIT = "lesson_calc_int_frac_split"
KEY_FRAC_LN = "lesson_calc_int_frac_ln"
KEY_NONELEM = "lesson_calc_int_nonelementary"


# ── small node helpers ────────────────────────────────────────────────


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


def _ordered(expression: sympy.Expr) -> CoreNode:
    """A polynomial in page order: ``x³ + 1``, not ``1 + x³``."""
    token = ordered_terms.set(True)
    try:
        return from_sympy(expression)
    finally:
        ordered_terms.reset(token)


def _sum_from_terms(expression: sympy.Expr) -> CoreNode:
    """An additive expression in sympy's own order (``−x cos x + sin x``)."""
    terms = list(expression.as_ordered_terms())
    result: CoreNode | None = None
    for term in terms:
        negative = bool(term.could_extract_minus_sign())
        piece = from_sympy(-term if negative else term)
        if result is None:
            result = _node(T.NEGATIVE, piece) if negative else piece
        elif negative:
            result = _node(T.SUBTRACT, result, piece)
        else:
            result = _node(T.ADD, result, piece)
    return result if result is not None else _num(0)


def _with_differential(expression: sympy.Expr, name: str) -> CoreNode:
    """``k dx`` with the coefficient ±1 dropped (``dt = −dx``)."""
    if expression == 1:
        return _var(name)
    if expression == -1:
        return _node(T.NEGATIVE, _var(name))
    factor = _ordered(expression)
    if expression.is_Add:
        factor = _node(T.BRACKET, factor)
    return _node(T.MULTIPLY, factor, _var(name))


def _fraction_node(numerator: CoreNode, denominator: sympy.Expr) -> CoreNode:
    return _node(T.FRACTION, numerator, from_sympy(denominator))


def _product_node(expression: sympy.Expr) -> CoreNode:
    """A product with each additive factor in parentheses (``x·(x + 1)``)."""
    if expression.is_Mul:
        pieces = [
            _node(T.BRACKET, _ordered(factor)) if factor.is_Add else _ordered(factor)
            for factor in expression.as_ordered_factors()
        ]
        return _node(T.MULTIPLY, *pieces)
    if expression.is_Add:
        return _node(T.BRACKET, _ordered(expression))
    return _ordered(expression)


def _rule(expression: sympy.Expr, primitive: sympy.Expr, variable: sympy.Symbol) -> CoreNode:
    """``∫ f dv = F`` as a math node with the concrete function and answer."""
    return _eq(_integral(_ordered(expression)), _ordered(primitive))


def _linear_rule(variable: sympy.Symbol) -> CoreNode:
    """``∫f(kx+b)dx = F(kx+b)/k``: the rule, not the concrete answer."""
    inner = _node(
        T.ADD,
        _node(T.MULTIPLY, _var("k"), _var(str(variable))),
        _var("b"),
    )
    left = _integral(CoreNode(type=T.FUNCTION, value="f", children=[inner]))
    right = _node(
        T.FRACTION,
        CoreNode(type=T.FUNCTION, value="F", children=[inner]),
        _var("k"),
    )
    return _eq(left, right)


def _member() -> CoreNode:
    return _node(T.ELEMENT_OF, _var("C"), _var("ℝ"))


def _answer(
    expression: sympy.Expr, variable: sympy.Symbol, source: sympy.Expr | None = None
) -> CoreNode:
    """The answer a student writes: a polynomial expanded, a trig form kept.

    Only an expanded polynomial integrand is expanded back: ``x²(x³+1)⁵`` keeps
    the back-substituted ``(x³+1)⁶/18`` instead of an 18th-degree polynomial.
    """
    expression = _plain_positive_logs(expression, variable)
    if source is not None and not source.is_Add:
        return _ordered(expression)
    try:
        sympy.Poly(expression, variable)
    except (sympy.PolynomialError, TypeError):
        return _ordered(expression)
    return tidy(expression)


def _with_constant(card: SolveResult, primitive: CoreNode) -> CoreNode:
    """The last stage of every indefinite card: ``F`` -> ``F + C, C ∈ ℝ``."""
    member = _member()
    answer = _node(T.LIST, _node(T.ADD, primitive, _var("C")), member)
    card.add_group(
        CoreRichText(type="add_arg", args=[member]),
        Step(primitive, answer, "integrate_msg_addc", [member]),
    )
    return answer


def _detail(*steps: Step, header: str = _HEADER_TABLE) -> SolveResult:
    card = SolveResult(header=header)
    card.add_group("find_integral", *steps)
    card.set_solution(steps[-1].right or steps[-1].left or _num(0))
    return card


def _fact(key: str, *nodes: CoreNode, args: list[CoreNode] | None = None) -> Step:
    """A stage that states a fact: the fact itself is the only formula.

    ``t = 3x``, ``dt = 3 dx``, ``u = x, dv = eˣ dx`` are statements, not
    transformations of the integral, so they have no arrow (no ``right``).
    The text of such a stage is arg-free: the formula below it is the statement,
    and a chip that also passed it would repeat the same formula.
    """
    shown = nodes[0] if len(nodes) == 1 else _node(T.LIST, *nodes)
    return Step(shown, None, key, list(args or []))


def _transform(
    key: str,
    left: CoreNode,
    right: CoreNode,
    args: list[CoreNode] | None = None,
    *,
    subresult: SolveResult | None = None,
) -> Step | None:
    """A transforming stage ``left -> right``; nothing to show if it is a no-op."""
    if left.structural_eq(right):
        return None
    return Step(left, right, key, list(args or []), subresult=subresult)


def _coefficient(expression: sympy.Expr, variable: sympy.Symbol) -> tuple[sympy.Expr, sympy.Expr]:
    """``sin(t)/3 -> (1/3, sin(t))`` so the card writes ``⅓∫sin t dt``."""
    coefficient, body = expression.as_coeff_Mul()
    if body == 1 or coefficient.is_number is not True:
        return sympy.Integer(1), expression
    return coefficient, body


# ── table entries ─────────────────────────────────────────────────────


def _positive_for_real(expression: sympy.Expr, variable: sympy.Symbol) -> bool:
    """Provably positive for every real ``variable`` (``1 + x²``, ``eˣ``)."""
    try:
        answer = sympy.ask(sympy.Q.positive(expression), sympy.Q.real(variable))
    except (TypeError, ValueError):
        answer = None
    if answer is not None:
        return answer is True
    try:
        poly = sympy.Poly(expression, variable)
    except (sympy.PolynomialError, TypeError):
        return False
    try:
        if poly.degree() % 2 or poly.LC() <= 0:
            return False
        roots = sympy.solve(sympy.Eq(expression, 0), variable)
    except (TypeError, ValueError, NotImplementedError):
        return False
    return bool(roots) and all(root.is_real is False for root in roots)


def _plain_positive_logs(expression: sympy.Expr, variable: sympy.Symbol) -> sympy.Expr:
    """``ln|1+x²|`` -> ``ln(1+x²)``: the absolute value is redundant."""

    def plain(argument: sympy.Expr) -> sympy.Expr:
        if isinstance(argument, sympy.Abs) and _positive_for_real(argument.args[0], variable):
            return sympy.log(argument.args[0])
        return sympy.log(argument)

    return expression.replace(sympy.log, plain)


def _derivative_matches(
    primitive: sympy.Expr, expression: sympy.Expr, variable: sympy.Symbol
) -> bool:
    """``d/dx F == f``; ``|·|`` is dropped (ln|u| and ln u share the derivative)."""

    def real(value: sympy.Expr) -> sympy.Expr:
        value = value.replace(lambda node: isinstance(node, sympy.Abs), lambda node: node.args[0])
        return value.subs(
            {symbol: sympy.Symbol(str(symbol), real=True) for symbol in value.free_symbols}
        )

    try:
        real_variable = sympy.Symbol(str(variable), real=True)
        difference = sympy.simplify(sympy.diff(real(primitive), real_variable) - real(expression))
        return bool(difference == 0)
    except (TypeError, ValueError):
        return False


def _table_core(expression: sympy.Expr, variable: sympy.Symbol) -> tuple[sympy.Expr, bool] | None:
    """``(primitive, linear_argument)`` for one textbook table entry."""
    x = variable
    if expression == x:
        return x**2 / 2, False
    if isinstance(expression, sympy.Pow):
        base, exponent = expression.base, expression.exp
        if base == x and exponent.is_number and exponent != -1:
            return x ** (exponent + 1) / (exponent + 1), False
        if base == x and exponent == -1:
            return sympy.log(sympy.Abs(x)), False
        if exponent == x and base.is_number and base > 0 and base != 1:
            return base**x / sympy.log(base), False
    if expression == sympy.exp(x):
        return sympy.exp(x), False
    if expression == sympy.sin(x):
        return -sympy.cos(x), False
    if expression == sympy.cos(x):
        return sympy.sin(x), False
    if expression == sympy.cos(x) ** -2:
        return sympy.tan(x), False
    if expression == sympy.sin(x) ** -2:
        return -sympy.cot(x), False
    if expression == 1 / (1 + x**2):
        return sympy.atan(x), False
    if expression == 1 / sympy.sqrt(1 - x**2):
        return sympy.asin(x), False
    matched = _table_with_parameter(expression, x)
    if matched is not None:
        return matched, False
    linear = _linear_argument(expression, x)
    if linear is not None:
        primitive = _table_core_exact(linear[0], x, linear[1])
        if primitive is not None:
            return primitive, True
    return None


def _table_with_parameter(
    expression: sympy.Expr, variable: sympy.Symbol, argument: sympy.Expr | None = None
) -> sympy.Expr | None:
    """``1/(x²+a²)``, ``1/√(a²−x²)`` and their linear-argument forms."""
    argument = variable if argument is None else argument
    slope = sympy.diff(argument, variable)
    if slope == 0 or slope.has(variable):
        return None
    pattern = sympy.Wild("a", exclude=[variable])
    inverse_square = expression.match(1 / (argument**2 + pattern**2))
    if inverse_square is not None:
        a = inverse_square[pattern]
        if a.is_real is False or a.is_zero is True:
            return None
        return sympy.atan(argument / a) / (a * slope)
    inverse_root = expression.match(1 / sympy.sqrt(pattern**2 - argument**2))
    if inverse_root is not None:
        a = inverse_root[pattern]
        if a.is_real is False or a.is_zero is True:
            return None
        return sympy.asin(argument / a) / slope
    return None


def _linear_argument(
    expression: sympy.Expr, variable: sympy.Symbol
) -> tuple[sympy.Expr, sympy.Expr] | None:
    """``(f(u), u)`` where ``u = k·variable + b`` is linear and ``f`` is a table entry."""
    for function, argument in _function_and_argument(expression):
        slope = sympy.diff(argument, variable)
        if slope == 0 or slope.has(variable) or slope.is_number is not True:
            continue
        base = function(argument)
        if _table_core_exact(base, variable, argument) is not None:
            return base, argument
    return None


def _function_and_argument(
    expression: sympy.Expr,
) -> Iterator[tuple[Callable[[sympy.Expr], sympy.Expr], sympy.Expr]]:
    """Candidate ``(f, u)`` pairs for ``f(u)`` in a linear-argument table entry."""
    pairs = [
        (sympy.sin, None),
        (sympy.cos, None),
        (sympy.exp, None),
    ]
    for function, _ in pairs:
        if expression.func is function:
            yield function, expression.args[0]
    if isinstance(expression, sympy.Pow) and expression.exp.is_number:
        yield lambda u: u**expression.exp, expression.base


def _table_core_exact(
    expression: sympy.Expr, variable: sympy.Symbol, argument: sympy.Expr
) -> sympy.Expr | None:
    """The primitive of a table entry with a linear argument, divided by its slope."""
    slope = sympy.diff(argument, variable)
    form = expression.subs({argument: sympy.Symbol("u")})
    if form == sympy.sin(sympy.Symbol("u")):
        return -sympy.cos(argument) / slope
    if form == sympy.cos(sympy.Symbol("u")):
        return sympy.sin(argument) / slope
    if form == sympy.exp(sympy.Symbol("u")):
        return sympy.exp(argument) / slope
    if form == 1 / sympy.Symbol("u"):
        return sympy.log(sympy.Abs(argument)) / slope
    if isinstance(form, sympy.Pow) and form.base == sympy.Symbol("u"):
        exponent = form.exp
        if exponent.is_number and exponent != -1:
            return argument ** (exponent + 1) / ((exponent + 1) * slope)
    if form == sympy.cos(sympy.Symbol("u")) ** -2:
        return sympy.tan(argument) / slope
    if form == sympy.sin(sympy.Symbol("u")) ** -2:
        return -sympy.cot(argument) / slope
    return None


def _table_entry(
    expression: sympy.Expr, variable: sympy.Symbol
) -> tuple[sympy.Expr, CoreNode, bool] | None:
    """``(F, formula, linear_argument)`` for one term of a table integral."""
    coefficient, body = expression.as_coeff_Mul()
    if body == 1:
        primitive = coefficient * variable
        formula = _rule(expression, primitive, variable)
        return primitive, formula, False
    core = _table_core(body, variable)
    if core is None:
        return None
    primitive = coefficient * core[0]
    formula = _rule(expression, primitive, variable)
    return primitive, formula, core[1]


def is_table(expression: sympy.Expr, variable: sympy.Symbol) -> bool:
    """A single table entry, with or without a constant factor."""
    return _table_entry(expression, variable) is not None


def is_linear_table(expression: sympy.Expr, variable: sympy.Symbol) -> bool:
    """A table entry with a linear inner argument, ``f(kx+b)``."""
    entry = _table_entry(expression, variable)
    return entry is not None and entry[2]


def is_special_substitution(expression: sympy.Expr, variable: sympy.Symbol) -> bool:
    """``1/sin x``: the textbook substitution ``t = tg(x/2)``."""
    return bool(expression == 1 / sympy.sin(variable))


def is_table_sum(expression: sympy.Expr, variable: sympy.Symbol) -> bool:
    """A sum whose every term is a table entry (linearity applies)."""
    if not expression.is_Add:
        return False
    return all(_table_entry(term, variable) is not None for term in expression.as_ordered_terms())


def _primitive(expression: sympy.Expr, variable: sympy.Symbol) -> sympy.Expr | None:
    """The table primitive of a sum of table entries (used after substitution)."""
    expression = sympy.expand(expression)
    if expression.is_Add:
        parts = [_primitive(term, variable) for term in expression.as_ordered_terms()]
        if any(part is None for part in parts):
            return None
        return sympy.Add(*parts)
    entry = _table_entry(expression, variable)
    return None if entry is None else entry[0]


# ── substitution ──────────────────────────────────────────────────────


def _candidates(expression: sympy.Expr, variable: sympy.Symbol) -> list[sympy.Expr]:
    """Inner functions ``g`` worth trying in ``t = g(x)``."""
    found: list[sympy.Expr] = []
    for power in expression.atoms(sympy.Pow):
        if not power.base.has(variable) or power.base == variable:
            continue
        if power.exp.is_Integer:
            found.append(power)
            found.append(power.base)
        else:
            # √(x+1): substituting the root itself is the textbook move, not x+1.
            found.append(power)
    for function in expression.atoms(sympy.Function):
        if not function.has(variable):
            continue
        if function.args and function.args[0].has(variable) and function.args[0] != variable:
            found.append(function.args[0])
        if function != expression:
            found.append(function)
    unique: list[sympy.Expr] = []
    seen: set[sympy.Expr] = set()
    for candidate in found:
        if candidate in seen or candidate == variable or candidate is sympy.S.NaN:
            continue
        seen.add(candidate)
        unique.append(candidate)
    return unique


def _in_t(
    expression: sympy.Expr, inner: sympy.Expr, variable: sympy.Symbol, t: sympy.Symbol
) -> sympy.Expr | None:
    """Rewrite ``expression`` entirely in ``t = inner``, or ``None``."""
    direct = sympy.simplify(expression.subs(inner, t))
    if not direct.has(variable) and direct.free_symbols <= {t}:
        return direct
    if isinstance(inner, sympy.Pow) and inner.exp.is_number and inner.exp.is_negative:
        # t = 1/Q would need the radical roots of Q; the base candidate covers it.
        return None
    # Solving for x is only a textbook move for a square root (x = t² − 1).
    # A cubic denominator produces radical roots and a needlessly slow simplify.
    if inner.is_polynomial(variable):
        try:
            if int(sympy.degree(inner, variable)) > 2:
                return None
        except (TypeError, ValueError, sympy.PolynomialError):
            return None
    try:
        solutions = sympy.solve(sympy.Eq(inner, t), variable)
    except (TypeError, ValueError, NotImplementedError):
        return None
    for solution in solutions:
        if solution.has(variable):
            continue
        candidate = sympy.simplify(expression.subs(variable, solution))
        if not candidate.has(variable) and candidate.free_symbols <= {t}:
            return candidate
    return None


def find_substitution(
    expression: sympy.Expr, variable: sympy.Symbol
) -> tuple[sympy.Expr, sympy.Expr, sympy.Expr] | None:
    """``(g, g', h(t))`` for ``∫ f(g(x))g'(x)dx`` with ``h`` a table integral.

    Candidates are scored so the textbook ``t`` wins: the simplest integral in
    ``t`` first (one term, no nested linear argument), then the simplest ``g``
    (``t = cos x`` rather than ``t = 1/cos x``).
    """
    t = sympy.Symbol("t", real=True)
    best: tuple[sympy.Expr, sympy.Expr, sympy.Expr] | None = None
    best_score: tuple[int, bool, int, int] | None = None
    for inner in _candidates(expression, variable):
        slope = sympy.diff(inner, variable)
        if slope == 0:
            continue
        reduced = sympy.simplify(expression / slope)
        rewritten = _in_t(reduced, inner, variable, t)
        if rewritten is None:
            continue
        rewritten = sympy.expand(sympy.simplify(rewritten))
        if rewritten == 0:
            continue
        entry = _table_entry(rewritten, t)
        if entry is not None:
            terms, linear = 1, entry[2]
        elif rewritten.is_Add:
            parts = [_table_entry(term, t) for term in rewritten.as_ordered_terms()]
            if any(part is None for part in parts):
                continue
            terms, linear = len(parts), False
        else:
            continue
        score = (terms, linear, sympy.count_ops(inner), len(str(inner)))
        if best_score is None or score < best_score:
            best, best_score = (inner, slope, rewritten), score
    return best


def _substitution_card(
    node: CoreNode,
    expression: sympy.Expr,
    variable: sympy.Symbol,
    substitution: tuple[sympy.Expr, sympy.Expr, sympy.Expr],
    *,
    header: str,
    extra: list[Step] | None = None,
    linear_rule: bool | None = None,
    start: CoreNode | None = None,
) -> SolveResult | None:
    inner, slope, rewritten = substitution
    t = sympy.Symbol("t", real=True)
    coefficient, body = _coefficient(rewritten, t)
    primitive_body = _primitive(body, t)
    if primitive_body is None:
        return None
    primitive_t = primitive_body if coefficient == 1 else coefficient * primitive_body
    primitive = primitive_t.subs(t, inner)
    primitive = _plain_positive_logs(primitive, variable)
    if not _derivative_matches(primitive, expression, variable):
        return None
    t_node, x_node = _var("t"), _var(str(variable))
    card = SolveResult(header=header)
    steps = list(extra or [])
    linear = is_linear_table(expression, variable) if linear_rule is None else linear_rule
    if linear:
        steps.append(_fact(KEY_LINEAR, _linear_rule(variable)))
    steps.append(_fact(KEY_SUBSTITUTE, _eq(t_node, _ordered(inner))))
    if isinstance(inner, sympy.Pow) and not inner.exp.is_Integer:
        # x = t² − 1 for t = √(x + 1); the integrand cannot be rewritten without it.
        try:
            solutions = sympy.solve(sympy.Eq(inner, t), variable)
        except (TypeError, ValueError, NotImplementedError):
            solutions = []
        for solution in solutions:
            if not solution.has(variable):
                steps.append(_fact(KEY_FROM_SUB, _eq(x_node, _ordered(solution))))
                break
    steps.append(
        _fact(
            KEY_DIFFERENTIAL,
            _eq(_var("dt"), _with_differential(sympy.simplify(slope), "dx")),
        )
    )
    if not linear and isinstance(inner, sympy.Pow) and not inner.exp.is_Integer:
        # t = √(x+1): express dx = 2t dt; nothing else in these cards needs it.
        try:
            inverse = sympy.simplify(1 / slope)
        except (TypeError, ValueError, ZeroDivisionError):
            inverse = None
        if inverse is not None and inverse.has(variable):
            inverse = _in_t(inverse, inner, variable, t)
        if inverse is not None and not inverse.has(variable):
            steps.append(
                _fact(
                    KEY_DX_EXPR,
                    _eq(_var("dx"), _with_differential(inverse, "dt")),
                )
            )
    table_node = _integral(_ordered(body))
    target = table_node
    if coefficient != 1:
        target = _node(T.MULTIPLY, from_sympy(coefficient), table_node)
    source = _integral(_ordered(expression)) if start is None else start
    rewrite = _transform(KEY_REWRITE, source, target)
    if rewrite is not None:
        steps.append(rewrite)
    detail = _detail(
        Step(table_node, from_sympy(primitive_body), KEY_INNER_TABLE),
        header=_HEADER_TABLE,
    )
    steps.append(
        Step(
            target,
            _ordered(primitive_t),
            KEY_INNER_TABLE,
            subresult=detail,
        )
    )
    steps.append(Step(_ordered(primitive_t), _ordered(primitive), KEY_BACK))
    card.add_group(["find_integral"], *steps)
    answer = _with_constant(card, _answer(primitive, variable, expression))
    card.set_solution(answer)
    return card


# ── linearity ─────────────────────────────────────────────────────────


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
    return result or _num(0)


def _in_page_order(terms: list[sympy.Expr], order: list[sympy.Expr]) -> list[sympy.Expr]:
    """Keep the caller's order (the decomposition), not sympy's ordering."""
    remaining = list(terms)
    out: list[sympy.Expr] = []
    for wanted in order:
        for index, term in enumerate(remaining):
            if sympy.simplify(term - wanted) == 0:
                out.append(term)
                remaining.pop(index)
                break
    return out + remaining


def _sum_card(
    node: CoreNode,
    expression: sympy.Expr,
    variable: sympy.Symbol,
    *,
    header: str = _HEADER_SUM,
    extra: list[Step] | None = None,
    page_answer: bool = False,
    order: list[sympy.Expr] | None = None,
) -> SolveResult | None:
    terms = list(expression.as_ordered_terms())
    if order:
        terms = _in_page_order(terms, order)
    entries = [_table_entry(term, variable) for term in terms]
    if any(entry is None for entry in entries):
        return None
    primitives = [entry[0] for entry in entries if entry is not None]
    total = sympy.Add(*primitives)
    if not _derivative_matches(total, expression, variable):
        return None

    card = SolveResult(header=header)
    steps = list(extra or [])
    parts: list[tuple[bool, CoreNode]] = []
    for term in terms:
        coefficient, body = term.as_coeff_Mul()
        negative = coefficient.could_extract_minus_sign()
        magnitude = -coefficient if negative else coefficient
        piece = _integral(_ordered(body))
        if magnitude != 1:
            piece = _node(T.MULTIPLY, from_sympy(magnitude), piece)
        parts.append((negative, piece))
    split = _chain(parts)
    steps.append(Step(_integral(_display(expression, variable)), split, KEY_SUM))
    current = split
    for index, (term, entry) in enumerate(zip(terms, entries, strict=True)):
        assert entry is not None
        coefficient, body = term.as_coeff_Mul()
        negative = coefficient.could_extract_minus_sign()
        magnitude = -coefficient if negative else coefficient
        primitive, _, _ = entry
        body_primitive = primitive / coefficient
        # The page replaces this term's integral by its primitive.
        parts[index] = (negative, _ordered(magnitude * body_primitive))
        page = _chain(parts)
        detail = _detail(
            Step(
                _integral(_ordered(body)),
                _ordered(body_primitive),
                KEY_TABLE,
            ),
            header=_HEADER_TABLE,
        )
        steps.append(
            Step(
                current,
                page,
                KEY_TERM_TABLE,
                subresult=detail,
            )
        )
        current = page
    answer_node = _sum_from_terms(total) if page_answer else _answer(total, variable, expression)
    if not current.structural_eq(answer_node):
        stage = _transform(KEY_ANSWER, current, answer_node)
        if stage is not None:
            steps.append(stage)
    card.add_group("find_integral", *steps)
    answer = _with_constant(card, answer_node)
    card.set_solution(answer)
    return card


# ── special functions ─────────────────────────────────────────────────


def _is_sin_square(expression: sympy.Expr, variable: sympy.Symbol) -> bool:
    return bool(expression == sympy.sin(variable) ** 2)


def _is_cos_square(expression: sympy.Expr, variable: sympy.Symbol) -> bool:
    return bool(expression == sympy.cos(variable) ** 2)


def _is_sin_cube(expression: sympy.Expr, variable: sympy.Symbol) -> bool:
    return bool(expression == sympy.sin(variable) ** 3)


def _is_tangent(expression: sympy.Expr, variable: sympy.Symbol) -> bool:
    return bool(expression == sympy.tan(variable))


def _is_cosecant(expression: sympy.Expr, variable: sympy.Symbol) -> bool:
    return bool(expression == 1 / sympy.sin(variable))


# ── integration by parts ──────────────────────────────────────────────


@dataclass(slots=True)
class _PartsApplication:
    """One application of ``∫u dv = uv − ∫v du``.

    ``remaining`` is the integrand of the integral that stays, with the sign it
    has when the formula is applied literally: for ``x sin x`` the remaining
    integral is ``+∫cos x dx`` (``v du = −cos x``), never ``−∫cos x dx``.
    """

    source: sympy.Expr
    u: sympy.Expr
    dv: sympy.Expr
    du: sympy.Expr
    v: sympy.Expr
    remaining: sympy.Expr
    negative: bool
    family: str


def _linear_inner(expression: sympy.Expr, variable: sympy.Symbol) -> bool:
    """``sin(2x)``, ``e^x``: a function of a linear argument with a constant slope."""
    if not expression.args:
        return False
    argument = expression.args[0]
    if not argument.has(variable):
        return False
    slope = sympy.diff(argument, variable)
    return slope != 0 and not slope.has(variable)


def _log_like(factor: sympy.Expr, variable: sympy.Symbol) -> bool:
    """``ln x``, ``ln²x``, ``arctg x``: the LIATE ``u`` of a by-parts application."""
    base = factor.base if isinstance(factor, sympy.Pow) else factor
    return base in (sympy.log(variable), sympy.atan(variable))


def _parts_application(expression: sympy.Expr, variable: sympy.Symbol) -> _PartsApplication | None:
    """LIATE: a logarithm or arctangent is ``u``, otherwise the polynomial is."""
    coefficient, body = expression.as_coeff_Mul()
    factors = list(body.args) if body.is_Mul else [body]
    for factor in factors:
        if _log_like(factor, variable):
            rest = body / factor
            if rest.is_polynomial(variable):
                return _parts_from(factor, coefficient * rest, expression, variable, "log")
    for factor in factors:
        if (
            isinstance(factor, sympy.Function)
            and factor.func in (sympy.exp, sympy.sin, sympy.cos)
            and _linear_inner(factor, variable)
        ):
            rest = body / factor
            if rest.is_polynomial(variable):
                family = "poly_exp" if factor.func is sympy.exp else "poly_trig"
                return _parts_from(coefficient * rest, factor, expression, variable, family)
    return None


def _parts_from(
    u: sympy.Expr,
    dv: sympy.Expr,
    source: sympy.Expr,
    variable: sympy.Symbol,
    family: str,
) -> _PartsApplication:
    du = sympy.diff(u, variable)
    v = sympy.integrate(dv, variable)
    inner = sympy.simplify(v * du)
    negative = bool(inner.could_extract_minus_sign())
    remaining = sympy.simplify(-inner) if negative else inner
    return _PartsApplication(
        source=source,
        u=u,
        dv=dv,
        du=du,
        v=v,
        remaining=remaining,
        negative=negative,
        family=family,
    )


def _parts_expr(application: _PartsApplication, variable: sympy.Symbol) -> sympy.Expr:
    """The same application as a sympy expression (an ``Integral`` atom stays)."""
    product = sympy.simplify(application.u * application.v)
    integral = sympy.Integral(application.remaining, variable)
    return product + integral if application.negative else product - integral


def _parts_state(expression: sympy.Expr, variable: sympy.Symbol) -> CoreNode:
    """A node for an expression that may contain unevaluated integrals."""
    if isinstance(expression, sympy.Integral):
        return _integral(from_sympy(expression.function))
    if isinstance(expression, sympy.Add):
        terms = list(expression.as_ordered_terms())
        terms.sort(key=lambda term: 1 if term.has(sympy.Integral) else 0)
        result: CoreNode | None = None
        for term in terms:
            negative = bool(term.could_extract_minus_sign())
            piece = _parts_state(-term if negative else term, variable)
            if result is None:
                result = _node(T.NEGATIVE, piece) if negative else piece
            elif negative:
                result = _node(T.SUBTRACT, result, piece)
            else:
                result = _node(T.ADD, result, piece)
        return result if result is not None else _num(0)
    if isinstance(expression, sympy.Mul):
        factors = list(expression.as_ordered_factors())
        negative = -1 in factors
        pieces = [_parts_state(factor, variable) for factor in factors if factor != -1]
        product = pieces[0]
        for piece in pieces[1:]:
            product = _node(T.MULTIPLY, product, piece)
        return _node(T.NEGATIVE, product) if negative else product
    return _ordered(expression)


def _parts_stages(
    application: _PartsApplication,
    variable: sympy.Symbol,
    left: CoreNode,
    right: CoreNode,
) -> list[Step]:
    """The u/dv, du/v and applied-formula stages of one application."""
    u_eq = _eq(_var("u"), _ordered(application.u))
    dv_eq = _eq(_var("dv"), _with_differential(application.dv, "dx"))
    du_eq = _eq(_var("du"), _with_differential(application.du, "dx"))
    v_eq = _eq(_var("v"), _ordered(application.v))
    return [
        _fact(KEY_PARTS_CHOOSE, u_eq, dv_eq),
        _fact(KEY_PARTS_DIFFERENTIAL, du_eq, v_eq),
        Step(left, right, KEY_PARTS_APPLY),
    ]


def _drop_add_constant(card: SolveResult) -> None:
    """A nested «Подробнее» shows the primitive, not its ``+ C``."""
    while card._steps:
        _heads, steps = card._steps[-1]
        if len(steps) == 1 and steps[0].key == "integrate_msg_addc":
            card._steps.pop()
        else:
            break


def _detail_for(
    expression: sympy.Expr, variable: sympy.Symbol, primitive: sympy.Expr
) -> SolveResult | None:
    """The table/substitution card of the remaining integral, without ``+ C``."""
    detail = textbook_card(_integral(from_sympy(expression)), [str(variable)])
    if detail is None:
        return None
    _drop_add_constant(detail)
    detail.solution = from_sympy(primitive)
    return detail


def _parts_answer(total: sympy.Expr, family: str, variable: sympy.Symbol) -> CoreNode:
    """Demidovich's answer form: ``eˣ(x − 1)``, ``−x cos x + sin x``."""
    total = _absolute_logs(total, variable)
    if family == "poly_exp":
        factored = sympy.factor(total)
        coefficient, body = factored.as_coeff_Mul()
        factors = body.args if body.is_Mul else (body,)
        for factor in factors:
            if isinstance(factor, sympy.exp):
                rest = coefficient * (body / factor)
                rest_node = _ordered(rest) if rest.is_polynomial(variable) else from_sympy(rest)
                return _node(T.MULTIPLY, rest_node, from_sympy(factor))
        return from_sympy(factored)
    return _sum_from_terms(sympy.expand(total))


def _substitution_detail(
    expression: sympy.Expr, variable: sympy.Symbol, primitive: sympy.Expr
) -> SolveResult | None:
    """The nested substitution card of ``(2x+p)/(x²+px+q)``, without ``+ C``."""
    substitution = find_substitution(expression, variable)
    if substitution is None:
        return None
    detail = _substitution_card(
        _integral(from_sympy(expression)),
        expression,
        variable,
        substitution,
        header=_HEADER_SUBSTITUTION,
    )
    if detail is None:
        return None
    _drop_add_constant(detail)
    detail.solution = from_sympy(primitive)
    return detail


def _parts_card(
    node: CoreNode, expression: sympy.Expr, variable: sympy.Symbol
) -> SolveResult | None:
    current = expression
    applications: list[_PartsApplication] = []
    while len(applications) < 8:
        if is_table(current, variable) or is_table_sum(current, variable):
            break
        application = _parts_application(current, variable)
        if application is None:
            break
        applications.append(application)
        current = application.remaining
    if not applications:
        return None
    total = sympy.integrate(expression, variable)
    if total.has(sympy.Integral) or not _derivative_matches(total, expression, variable):
        return None
    card = SolveResult(header=_HEADER_PARTS)
    formula = CoreNode(type=T.TEXT, value="∫u dv = uv − ∫v du")
    groups: list[tuple[str, list[Step]]] = []
    state = sympy.Integral(expression, variable)
    for index, application in enumerate(applications):
        after = state.subs(
            sympy.Integral(application.source, variable),
            _parts_expr(application, variable),
        )
        stages = _parts_stages(
            application,
            variable,
            _parts_state(state, variable),
            _parts_state(after, variable),
        )
        if index == 0:
            # The formula belongs to the first application, wherever it is shown.
            stages.insert(0, _fact(KEY_PARTS_FORMULA, formula))
        if len(applications) == 1:
            groups.append(("find_integral", stages))
        else:
            titles = (_HEADER_PARTS_FIRST, _HEADER_PARTS_SECOND, _HEADER_PARTS_NEXT)
            groups.append((titles[min(index, 2)], stages))
        state = after
    last = applications[-1]
    tail: list[Step] = []
    if last.remaining != 0:
        primitive = sympy.integrate(last.remaining, variable)
        after = state.subs(sympy.Integral(last.remaining, variable), primitive)
        if after.has(sympy.Integral):
            return None
        detail = _detail_for(last.remaining, variable, primitive)
        tail.append(
            Step(
                _parts_state(state, variable),
                _parts_state(after, variable),
                KEY_PARTS_REMAINDER,
                subresult=detail,
            )
        )
        state = after
    answer_node = _parts_answer(total, applications[0].family, variable)
    final = _parts_state(state, variable)
    # Compare the formulas the student sees: the card is drawn in book style
    # (``x²cos x``, not ``x² \cdot cos x``), and after two applications the
    # answer stage may differ only by the dot — a stage that changes nothing.
    shown_final, shown_answer = book_products(final), book_products(answer_node)
    if (
        shown_final is not None
        and shown_answer is not None
        and not shown_final.structural_eq(shown_answer)
    ):
        stage = _transform(KEY_PARTS_ANSWER, final, answer_node)
        if stage is not None:
            tail.append(stage)
    if len(applications) == 1:
        groups[0][1].extend(tail)
    elif tail:
        groups.append(("find_integral", tail))
    for title, stages in groups:
        card.add_group(title, *stages)
    answer = _with_constant(card, answer_node)
    card.set_solution(answer)
    return card


@dataclass(slots=True)
class _CyclicPlan:
    """``e^{ax}·sin(bx)``: two applications return the original integral."""

    a: sympy.Expr
    b: sympy.Expr
    cosine: bool


def _cyclic_plan(expression: sympy.Expr, variable: sympy.Symbol) -> _CyclicPlan | None:
    _, body = expression.as_coeff_Mul()
    factors = list(body.args) if body.is_Mul else [body]
    exponentials = [
        factor
        for factor in factors
        if isinstance(factor, sympy.exp) and _linear_inner(factor, variable)
    ]
    trig = [
        factor
        for factor in factors
        if isinstance(factor, sympy.Function)
        and factor.func in (sympy.sin, sympy.cos)
        and _linear_inner(factor, variable)
    ]
    if len(exponentials) != 1 or len(trig) != 1 or len(factors) != 2:
        return None
    a = sympy.diff(exponentials[0].args[0], variable)
    b = sympy.Abs(sympy.diff(trig[0].args[0], variable))
    if a == 0 or b == 0:
        return None
    return _CyclicPlan(a=a, b=b, cosine=trig[0].func is sympy.cos)


def _cyclic_card(
    node: CoreNode, expression: sympy.Expr, variable: sympy.Symbol, plan: _CyclicPlan
) -> SolveResult | None:
    coefficient, body = expression.as_coeff_Mul()
    factors = list(body.args)
    exponential = next(factor for factor in factors if isinstance(factor, sympy.exp))
    trig = next(
        factor
        for factor in factors
        if isinstance(factor, sympy.Function) and factor.func in (sympy.sin, sympy.cos)
    )
    first = _parts_from(trig, coefficient * exponential, expression, variable, "cyclic")
    second = _parts_from(
        _other_trig(trig, variable),
        coefficient * exponential,
        first.remaining,
        variable,
        "cyclic",
    )
    total = sympy.integrate(expression, variable)
    if total.has(sympy.Integral) or not _derivative_matches(total, expression, variable):
        return None
    a, b = plan.a, plan.b
    expected = sympy.simplify(
        coefficient
        * sympy.exp(a * variable)
        * (
            a * sympy.cos(b * variable) + b * sympy.sin(b * variable)
            if plan.cosine
            else a * sympy.sin(b * variable) - b * sympy.cos(b * variable)
        )
        / (a**2 + b**2)
    )
    if not _derivative_matches(expected, expression, variable):
        return None

    card = SolveResult(header=_HEADER_PARTS)
    formula = CoreNode(type=T.TEXT, value="∫u dv = uv − ∫v du")
    formula_step = _fact(KEY_PARTS_FORMULA, formula)
    u1, dv1 = (
        _eq(_var("u"), from_sympy(first.u)),
        _eq(_var("dv"), _with_differential(first.dv, "dx")),
    )
    du1, v1 = (
        _eq(_var("du"), _with_differential(first.du, "dx")),
        _eq(_var("v"), from_sympy(first.v)),
    )
    u2, dv2 = (
        _eq(_var("u"), from_sympy(second.u)),
        _eq(_var("dv"), _with_differential(second.dv, "dx")),
    )
    du2, v2 = (
        _eq(_var("du"), _with_differential(second.du, "dx")),
        _eq(_var("v"), from_sympy(second.v)),
    )
    card.add_group(
        _HEADER_PARTS_FIRST,
        formula_step,
        _fact(KEY_PARTS_CHOOSE, u1, dv1),
        _fact(KEY_PARTS_DIFFERENTIAL, du1, v1),
    )
    card.add_group(
        _HEADER_PARTS_SECOND,
        _fact(KEY_PARTS_CHOOSE, u2, dv2),
        _fact(KEY_PARTS_DIFFERENTIAL, du2, v2),
    )

    exp_node = from_sympy(sympy.exp(a * variable))
    inner = (
        a * sympy.cos(b * variable) + b * sympy.sin(b * variable)
        if plan.cosine
        else a * sympy.sin(b * variable) - b * sympy.cos(b * variable)
    )
    inner_node = _node(T.BRACKET, _ordered(inner))
    factors_node = [exp_node, inner_node]
    if coefficient != 1:
        factors_node.insert(0, from_sympy(coefficient))
    product = _node(T.MULTIPLY, *factors_node)
    intermediate = product if a**2 == 1 else _fraction_node(product, a**2)
    ratio = sympy.simplify(b**2 / a**2)
    equation_right = (
        _node(T.SUBTRACT, intermediate, _var("I"))
        if ratio == 1
        else _node(
            T.SUBTRACT,
            intermediate,
            _node(T.MULTIPLY, from_sympy(ratio), _var("I")),
        )
    )
    integral_node = _integral(from_sympy(expression))
    define = _eq(_var("I"), integral_node)
    equation = _eq(_var("I"), equation_right)
    moved_left = _node(T.MULTIPLY, from_sympy(sympy.simplify(1 + ratio)), _var("I"))
    moved_right = product
    moved = _eq(moved_left, moved_right)
    value = (
        _fraction_node(_node(T.MULTIPLY, exp_node, inner_node), sympy.simplify(a**2 + b**2))
        if coefficient == 1
        else from_sympy(expected)
    )
    solved = _eq(_var("I"), value)
    card.add_group(
        "find_integral",
        _fact(KEY_PARTS_DEFINE, define),
        _fact(KEY_PARTS_EQUATION, equation),
        _fact(KEY_PARTS_MOVE, moved),
        _fact(KEY_PARTS_VALUE, solved),
    )
    answer = _with_constant(card, value)
    card.set_solution(answer)
    return card


def _other_trig(trig: sympy.Expr, variable: sympy.Symbol) -> sympy.Expr:
    """The partner of ``sin`` or ``cos`` with the same argument."""
    argument = trig.args[0]
    return sympy.cos(argument) if trig.func is sympy.sin else sympy.sin(argument)


# ── rational functions ────────────────────────────────────────────────


def _absolute_logs(expression: sympy.Expr, variable: sympy.Symbol) -> sympy.Expr:
    """``ln u`` -> ``ln|u|`` unless ``u`` is provably positive."""

    def wrap(argument: sympy.Expr) -> sympy.Expr:
        return (
            sympy.log(argument)
            if _positive_for_real(argument, variable)
            else sympy.log(sympy.Abs(argument))
        )

    return expression.replace(sympy.log, wrap)


def _rational_parts(
    expression: sympy.Expr, variable: sympy.Symbol
) -> tuple[sympy.Expr, sympy.Expr, sympy.Expr] | None:
    """``(quotient, proper, denominator)`` for a non-polynomial rational function."""
    numerator, denominator = sympy.fraction(sympy.together(expression))
    if numerator.is_polynomial(variable) is not True:
        return None
    if denominator.is_polynomial(variable) is not True:
        return None
    try:
        degree = int(sympy.degree(denominator, variable))
    except (TypeError, ValueError, sympy.PolynomialError):
        return None
    numerator_degree = int(sympy.degree(numerator, variable))
    # A single linear factor is a partial-fraction case only when the fraction is
    # improper: 1/(x−1) stays the linear-argument table entry.
    if degree < 2 and not (degree == 1 and numerator_degree >= 1):
        return None
    if numerator_degree >= degree:
        quotient, remainder = sympy.div(numerator, denominator, variable)
    else:
        quotient, remainder = sympy.Integer(0), numerator
    proper = sympy.cancel(remainder / denominator)
    return sympy.expand(quotient), proper, sympy.expand(denominator)


def _linear_denominator(expression: sympy.Expr, variable: sympy.Symbol) -> bool:
    """``x²/(x − 1)``: a polynomial over a single linear factor."""
    numerator, denominator = sympy.fraction(sympy.together(expression))
    if numerator.is_polynomial(variable) is not True:
        return False
    if denominator.is_polynomial(variable) is not True:
        return False
    try:
        return (
            int(sympy.degree(denominator, variable)) == 1
            and int(sympy.degree(numerator, variable)) >= 2
        )
    except (TypeError, ValueError, sympy.PolynomialError):
        return False


def _improper_rational(expression: sympy.Expr, variable: sympy.Symbol) -> bool:
    """A rational function whose numerator degree reaches the denominator's."""
    numerator, denominator = sympy.fraction(sympy.together(expression))
    if numerator.is_polynomial(variable) is not True:
        return False
    if denominator.is_polynomial(variable) is not True:
        return False
    try:
        numerator_degree = int(sympy.degree(numerator, variable))
        denominator_degree = int(sympy.degree(denominator, variable))
        if denominator_degree < 1 or numerator_degree < denominator_degree:
            return False
        # A monomial denominator is expanded term by term (x + 2 + 1/x), not
        # divided into partial fractions.
        return not sympy.Poly(denominator, variable).is_monomial
    except (TypeError, ValueError, sympy.PolynomialError):
        return False


def _cancelled(expression: sympy.Expr, variable: sympy.Symbol) -> sympy.Expr:
    """``(x−1)/(x²−3x+2)`` -> ``1/(x−2)`` when a polynomial factor cancels."""
    numerator, denominator = sympy.fraction(sympy.together(expression))
    if numerator.is_polynomial(variable) is not True:
        return expression
    if denominator.is_polynomial(variable) is not True:
        return expression
    try:
        canceled = sympy.cancel(expression)
        if sympy.degree(sympy.fraction(canceled)[1], variable) < sympy.degree(
            denominator, variable
        ):
            return canceled
    except (TypeError, ValueError, sympy.PolynomialError):
        return expression
    return expression


def _rational_card(
    node: CoreNode, expression: sympy.Expr, variable: sympy.Symbol
) -> SolveResult | None:
    parts = _rational_parts(expression, variable)
    if parts is None:
        return None
    quotient, proper, denominator = parts
    if proper == 0:
        return None
    factored = sympy.factor(denominator)
    factors = list(factored.args) if factored.is_Mul else [factored]
    linear: list[tuple[sympy.Expr, int]] = []
    for factor in factors:
        base, exponent = factor.as_base_exp()
        if base.is_polynomial(variable) is True and sympy.degree(base, variable) == 1:
            linear.append((base, int(exponent)))
        else:
            linear = []
            break
    if linear:
        return _linear_factors_card(
            node, expression, variable, quotient, proper, denominator, factored, linear
        )
    if len(factors) == 1 and sympy.degree(factored, variable) == 2:
        return _quadratic_card(node, expression, variable, proper, denominator)
    return None


def _apart_coefficients(expression: sympy.Expr) -> dict[tuple[sympy.Expr, int], sympy.Expr]:
    """``(−1)/(x+1)²`` -> ``{(x+1, 2): −1}`` from ``apart``."""
    found: dict[tuple[sympy.Expr, int], sympy.Expr] = {}
    for term in sympy.apart(expression).as_ordered_terms():
        coefficient, body = term.as_coeff_Mul()
        base, exponent = body.as_base_exp()
        if exponent.is_negative:
            found[(base, int(-exponent))] = coefficient
    return found


def _unknown_chain(terms: list[tuple[CoreNode, bool]]) -> CoreNode:
    result: CoreNode | None = None
    for piece, negative in terms:
        if result is None:
            result = _node(T.NEGATIVE, piece) if negative else piece
        elif negative:
            result = _node(T.SUBTRACT, result, piece)
        else:
            result = _node(T.ADD, result, piece)
    return result or _num(0)


def _linear_factors_card(
    node: CoreNode,
    expression: sympy.Expr,
    variable: sympy.Symbol,
    quotient: sympy.Expr,
    proper: sympy.Expr,
    denominator: sympy.Expr,
    factored: sympy.Expr,
    linear: list[tuple[sympy.Expr, int]],
) -> SolveResult | None:
    def root_order(item: tuple[sympy.Expr, int]) -> float:
        try:
            return -float(sympy.N(sympy.solve(item[0], variable)[0]))
        except (IndexError, TypeError, ValueError, NotImplementedError):
            return 0.0

    ordered_linear = sorted(linear, key=root_order)
    factor_terms = [
        (base, power)
        for base, multiplicity in ordered_linear
        for power in range(1, multiplicity + 1)
    ]
    if len(factor_terms) == 1 and quotient != 0:
        # A single linear factor needs no letters: divide and split the sum
        # (x²/(x − 1) = x + 1 + 1/(x − 1)).
        expanded = sympy.expand(quotient + sympy.apart(proper, variable))
        if not is_table_sum(expanded, variable):
            return None
        step = _fact(
            KEY_FRAC_DIVIDE,
            _eq(_display(expression, variable), _ordered(expanded)),
        )
        return _sum_card(
            node,
            expanded,
            variable,
            header=_HEADER_FRACTION,
            extra=[step],
            page_answer=True,
        )
    coefficients = _apart_coefficients(proper)
    if any((base, power) not in coefficients for base, power in factor_terms):
        return None
    letters = "ABCDEFGH"
    if len(factor_terms) > len(letters):
        return None
    unknown: list[CoreNode] = []
    terms: list[tuple[CoreNode, bool]] = []
    for index, (base, power) in enumerate(factor_terms):
        letter = _var(letters[index])
        unknown.append(letter)
        denominator_node = (
            _ordered(base) if power == 1 else _node(T.POWER, _ordered(base), _num(power))
        )
        terms.append((_node(T.FRACTION, letter, denominator_node), False))
    decomposition = _unknown_chain(terms)

    identity_terms: list[tuple[CoreNode, bool]] = []
    for index, (base, power) in enumerate(factor_terms):
        multiplier = sympy.prod(
            other ** (multiplicity - (power if other == base else 0))
            for other, multiplicity in ordered_linear
        )
        multiplier_node = _product_node(multiplier)
        piece = (
            unknown[index]
            if multiplier == 1
            else _node(T.MULTIPLY, unknown[index], multiplier_node)
        )
        identity_terms.append((piece, False))

    values = [
        _eq(unknown[index], from_sympy(sympy.simplify(coefficients[(base, power)])))
        for index, (base, power) in enumerate(factor_terms)
    ]
    factor_nodes: list[CoreNode] = []
    for base, multiplicity in ordered_linear:
        if multiplicity == 1:
            base_node = _ordered(base)
            if base.is_Add:
                base_node = _node(T.BRACKET, base_node)
            factor_nodes.append(base_node)
        else:
            factor_nodes.append(_node(T.POWER, _ordered(base), _num(multiplicity)))
    factored_node = factor_nodes[0] if len(factor_nodes) == 1 else _node(T.MULTIPLY, *factor_nodes)
    steps: list[Step] = []
    if quotient != 0:
        proper_node = _ordered(proper)
        steps.append(
            _fact(
                KEY_FRAC_DIVIDE,
                _eq(
                    _display(expression, variable),
                    _node(T.ADD, _ordered(quotient), proper_node),
                ),
            )
        )
    steps.append(_fact(KEY_FRAC_FACTOR, _eq(_ordered(denominator), factored_node)))
    steps.append(_fact(KEY_FRAC_FORM, _eq(_ordered(proper), decomposition)))
    equation_numerator = sympy.fraction(proper)[0]
    steps.append(
        _fact(
            KEY_FRAC_EQUATIONS,
            _eq(_ordered(equation_numerator), _unknown_chain(identity_terms)),
        )
    )
    steps.append(_fact(KEY_FRAC_COEFFS, _node(T.LIST, *values)))
    numbers = sympy.apart(proper, variable)
    number_pieces: list[tuple[CoreNode, bool]] = []
    for base, power in factor_terms:
        coefficient = coefficients[(base, power)]
        negative = bool(coefficient.could_extract_minus_sign())
        magnitude = -coefficient if negative else coefficient
        denominator_node = (
            _ordered(base) if power == 1 else _node(T.POWER, _ordered(base), _num(power))
        )
        fraction = _node(T.FRACTION, _num(1), denominator_node)
        piece = fraction if magnitude == 1 else _node(T.MULTIPLY, from_sympy(magnitude), fraction)
        number_pieces.append((piece, negative))
    numbers_node = _unknown_chain(number_pieces)
    steps.append(_fact(KEY_FRAC_NUMBERS, _eq(_ordered(proper), numbers_node)))
    expanded = sympy.Add(quotient, numbers) if quotient != 0 else numbers
    # The table stages run in the order of the decomposition on the page.
    order = [coefficients[(base, power)] / base**power for base, power in factor_terms]
    order = (list(quotient.as_ordered_terms()) if quotient != 0 else []) + order
    return _sum_card(node, expanded, variable, header=_HEADER_FRACTION, extra=steps, order=order)


def _completed_square(
    denominator: sympy.Expr, variable: sympy.Symbol
) -> tuple[sympy.Expr, sympy.Expr, sympy.Expr] | None:
    """``x²+px+q`` -> ``(x+α)²+β²`` with ``α = p/2``, ``β² = q − p²/4``."""
    try:
        coefficients = sympy.Poly(denominator, variable).all_coeffs()
    except (sympy.PolynomialError, TypeError):
        return None
    if len(coefficients) != 3 or coefficients[0] != 1:
        return None
    p, q = coefficients[1], coefficients[2]
    alpha = p / 2
    beta_squared = sympy.simplify(q - p**2 / 4)
    if beta_squared.is_positive is not True:
        return None
    return alpha, beta_squared, sympy.sqrt(beta_squared)


def _square_detail(
    denominator: sympy.Expr, variable: sympy.Symbol, primitive: sympy.Expr
) -> SolveResult | None:
    """The nested card of ``∫dx/(x²+px+q)`` (complete square + table)."""
    return _detail_for(1 / denominator, variable, primitive)


def _completed_node(
    variable: sympy.Symbol, alpha: sympy.Expr, beta_squared: sympy.Expr
) -> CoreNode:
    """``(x + alpha)² + beta²`` with the polynomial written in page order."""
    x = _var(str(variable))
    inner = x if alpha == 0 else _node(T.ADD, x, from_sympy(alpha))
    square = _node(T.POWER, inner, _num(2)) if alpha != 0 else _node(T.POWER, x, _num(2))
    if beta_squared == 0:
        return square
    return _node(T.ADD, square, _ordered(beta_squared))


def _atan_node(variable: sympy.Symbol, alpha: sympy.Expr, beta: sympy.Expr) -> CoreNode:
    """``arctg((x + alpha)/beta)`` - the completed-square argument, not ``1/2 + x/2``."""
    x = _var(str(variable))
    numerator = x if alpha == 0 else _node(T.ADD, x, from_sympy(alpha))
    if beta == 1:
        return _node(T.ATAN, numerator)
    return _node(T.ATAN, _node(T.FRACTION, numerator, from_sympy(beta)))


def _log_node(argument: sympy.Expr, variable: sympy.Symbol) -> CoreNode:
    """``ln|argument|`` unless the argument is positive for every real variable."""
    ordered = _ordered(argument)
    if _positive_for_real(argument, variable):
        return _node(T.LN, ordered)
    return _node(T.LN, _node(T.ABS, ordered))


def _integrand_fraction(numerator: sympy.Expr, denominator: CoreNode) -> CoreNode:
    return _node(T.FRACTION, _ordered(numerator), denominator)


def _quadratic_card(
    node: CoreNode,
    expression: sympy.Expr,
    variable: sympy.Symbol,
    proper: sympy.Expr,
    denominator: sympy.Expr,
) -> SolveResult | None:
    square = _completed_square(denominator, variable)
    if square is None:
        return None
    alpha, beta_squared, beta = square
    numerator, _ = sympy.fraction(proper)
    if numerator.is_polynomial(variable) is not True:
        return None
    degree = int(sympy.degree(numerator, variable))
    if degree > 1:
        return None
    p = 2 * alpha
    a = sympy.diff(numerator, variable) if degree == 1 else sympy.Integer(0)
    split = sympy.Rational(a, 2) if a != 0 else sympy.Integer(0)
    constant = sympy.simplify(sympy.Poly(numerator, variable).coeff_monomial(1) - a * alpha)
    if a == 0:
        return _pure_square_card(node, expression, variable, denominator, constant, alpha, beta)
    if constant == 0:
        # The numerator is exactly the derivative of the denominator: that is the
        # substitution card's job, and a split here would add a 0·∫ term.
        return None
    ln_primitive = sympy.log(denominator)
    arctan_primitive = sympy.atan((variable + alpha) / beta)
    total = sympy.simplify(split * ln_primitive + constant / beta * arctan_primitive)
    if not _derivative_matches(total, expression, variable):
        return None

    card = SolveResult(
        header=_HEADER_SQUARE if (alpha != 0 or beta_squared != 1) else _HEADER_FRACTION
    )
    completed = _completed_node(variable, alpha, beta_squared)
    denominator_node = _ordered(denominator)
    square_left = _integral(_integrand_fraction(numerator, denominator_node))
    square_right = _integral(_integrand_fraction(numerator, completed))
    stages: list[Step] = []
    stage = _transform(KEY_FRAC_SQUARE, square_left, square_right)
    if stage is not None:
        stages.append(stage)

    derivative_inner = (
        _node(T.MULTIPLY, _num(2), _var(str(variable)))
        if p == 0
        else _node(T.ADD, _node(T.MULTIPLY, _num(2), _var(str(variable))), from_sympy(p))
    )
    if split == 1:
        derivative_part = derivative_inner
    elif split == -1:
        derivative_part = _node(T.NEGATIVE, derivative_inner)
    else:
        derivative_part = _node(
            T.MULTIPLY,
            _node(T.FRACTION, from_sympy(a), _num(2)),
            _node(T.BRACKET, derivative_inner),
        )
    split_terms: list[tuple[CoreNode, bool]] = [(derivative_part, False)]
    if constant != 0:
        split_terms.append((_ordered(abs(constant)), bool(constant.could_extract_minus_sign())))
    split_sum = _unknown_chain(split_terms)
    numerator_node = _ordered(numerator)
    if not numerator_node.structural_eq(split_sum):
        stages.append(_fact(KEY_FRAC_SPLIT, _eq(numerator_node, split_sum)))

    derivative_expression = 2 * variable + p
    first_integrand = sympy.simplify(split * derivative_expression / denominator)
    second_integrand = sympy.simplify(constant / denominator)
    log_node = _log_node(denominator, variable)
    first_primitive_node = (
        log_node if split == 1 else _node(T.MULTIPLY, from_sympy(split), log_node)
    )
    # The sign of the second term is carried by the subtraction chain below,
    # so this node keeps the magnitude (a negative numerator must not flip twice).
    second_coefficient = sympy.simplify(abs(constant) / beta)
    second_primitive_node = _node(
        T.MULTIPLY,
        from_sympy(second_coefficient),
        _atan_node(variable, alpha, beta),
    )
    if second_coefficient == 1:
        second_primitive_node = _atan_node(variable, alpha, beta)
    # The split keeps what «Разобьём числитель» found: the constant ½|a| stays in
    # front of ∫(2x + p)/Q dx, so the ln stage can name t = Q and its derivative.
    first_piece: CoreNode = _integral(
        _node(T.FRACTION, _ordered(derivative_expression), denominator_node)
    )
    if split == -1:
        first_piece = _node(T.NEGATIVE, first_piece)
    elif split != 1:
        first_piece = _node(T.MULTIPLY, from_sympy(split), first_piece)
    # The second fraction is the completed square itself: no |·| ever appears
    # around it (the magnitude of the coefficient carries the sign).
    second_piece: CoreNode = _integral(_node(T.FRACTION, _num(1), completed))
    if abs(constant) != 1:
        second_piece = _node(T.MULTIPLY, from_sympy(abs(constant)), second_piece)
    second_negative = bool(second_integrand.could_extract_minus_sign())
    split_integrals = _unknown_chain([(first_piece, False), (second_piece, second_negative)])
    sum_stage = _transform(KEY_SUM, square_right, split_integrals)
    if sum_stage is not None:
        stages.append(sum_stage)

    first_detail = _substitution_detail(first_integrand, variable, ln_primitive)
    ln_stage = _transform(
        KEY_FRAC_LN,
        split_integrals,
        _unknown_chain(
            [
                (first_primitive_node, False),
                (second_piece, second_negative),
            ]
        ),
        [_eq(_var("t"), denominator_node)],
        subresult=first_detail,
    )
    if ln_stage is not None:
        stages.append(ln_stage)

    second_detail = _square_detail(denominator, variable, arctan_primitive)
    arctan_stage = _transform(
        KEY_TERM_TABLE,
        _unknown_chain(
            [
                (first_primitive_node, False),
                (second_piece, second_negative),
            ]
        ),
        _unknown_chain(
            [
                (first_primitive_node, False),
                (second_primitive_node, second_negative),
            ]
        ),
        subresult=second_detail,
    )
    if arctan_stage is not None:
        stages.append(arctan_stage)
    card.add_group("find_integral", *stages)
    answer_node = _unknown_chain(
        [(first_primitive_node, False), (second_primitive_node, second_negative)]
    )
    answer = _with_constant(card, answer_node)
    card.set_solution(answer)
    return card


def _pure_square_card(
    node: CoreNode,
    expression: sympy.Expr,
    variable: sympy.Symbol,
    denominator: sympy.Expr,
    coefficient: sympy.Expr,
    alpha: sympy.Expr,
    beta: sympy.Expr,
) -> SolveResult | None:
    primitive = sympy.simplify(coefficient / beta * sympy.atan((variable + alpha) / beta))
    if not _derivative_matches(primitive, expression, variable):
        return None
    card = SolveResult(header=_HEADER_SQUARE)
    completed = _completed_node(variable, alpha, beta**2)
    denominator_node = _ordered(denominator)
    square_left = _integral(_integrand_fraction(coefficient, denominator_node))
    square_right = _integral(_integrand_fraction(coefficient, completed))
    stages: list[Step] = []
    stage = _transform(KEY_FRAC_SQUARE, square_left, square_right)
    if stage is not None:
        stages.append(stage)
    t = sympy.Symbol("t", real=True)
    if alpha != 0:
        stages.append(
            _fact(
                KEY_SUBSTITUTE,
                _eq(_var("t"), _node(T.ADD, _var(str(variable)), _ordered(alpha))),
            )
        )
        stages.append(_fact(KEY_DIFFERENTIAL, _eq(_var("dt"), _var("dx"))))
        t_completed = _completed_node(t, sympy.Integer(0), beta**2)
    else:
        t = variable
        t_completed = completed
    rewritten = _integrand_fraction(sympy.Integer(1), t_completed)
    target = _integral(rewritten)
    if coefficient != 1:
        target = _node(T.MULTIPLY, from_sympy(coefficient), target)
    rewrite = _transform(KEY_REWRITE, square_right, target)
    if rewrite is not None:
        stages.append(rewrite)
    primitive_t = _node(
        T.MULTIPLY,
        from_sympy(sympy.simplify(coefficient / beta)),
        _atan_node(t, sympy.Integer(0), beta),
    )
    if sympy.simplify(coefficient / beta) == 1:
        primitive_t = _atan_node(t, sympy.Integer(0), beta)
    table_detail = _detail(
        Step(
            _integral(rewritten),
            _atan_node(t, sympy.Integer(0), beta),
            KEY_INNER_TABLE,
        )
    )
    inner = _transform(
        KEY_INNER_TABLE,
        target,
        primitive_t,
        subresult=table_detail,
    )
    if inner is not None:
        stages.append(inner)
    if alpha != 0:
        final = primitive_t
        if coefficient != 1 or beta != 1:
            final = _node(
                T.MULTIPLY,
                from_sympy(sympy.simplify(coefficient / beta)),
                _atan_node(variable, alpha, beta),
            )
            if sympy.simplify(coefficient / beta) == 1:
                final = _atan_node(variable, alpha, beta)
        back = _transform(KEY_BACK, primitive_t, final)
        if back is not None:
            stages.append(back)
    else:
        final = primitive_t
    card.add_group("find_integral", *stages)
    answer_node = final
    answer = _with_constant(card, answer_node)
    card.set_solution(answer)
    return card


# ── public builder ────────────────────────────────────────────────────


def _non_elementary_card(
    node: CoreNode, expression: sympy.Expr, variable: sympy.Symbol
) -> SolveResult | None:
    """An answer card when the antiderivative is not elementary (no SolveError)."""
    if isinstance(expression, sympy.Abs):
        # ``∫|x| dx`` has an elementary primitive; the verified card computes it.
        return None
    try:
        antiderivative = sympy.integrate(expression, variable)
    except (TypeError, ValueError, NotImplementedError):
        antiderivative = sympy.Integral(expression, variable)
    if not antiderivative.has(sympy.Integral):
        try:
            from_sympy(antiderivative)
        except SolveError:
            pass
        else:
            return None
    reason = CoreNode(type=T.TEXT, value="не выражается через элементарные функции")
    card = SolveResult(header=_HEADER_NONELEM)
    card.add_group(
        "find_integral",
        Step(_integral(from_sympy(expression)), reason, KEY_NONELEM),
    )
    card.set_solution(reason)
    return card


def textbook_detail(node: CoreNode, variables: list[str]) -> SolveResult | None:
    """The textbook card of an indefinite integral without its ``+ C`` stage."""
    detail = textbook_card(node, variables)
    if detail is None:
        return None
    _drop_add_constant(detail)
    detail.solution = _last_right(detail)
    return detail


def _last_right(card: SolveResult) -> CoreNode | None:
    for _heads, steps in reversed(card._steps):
        for step in reversed(steps):
            if step.right is not None:
                return step.right
    return None


def textbook_card(node: CoreNode, variables: list[str]) -> SolveResult | None:
    """The first card of an indefinite integral, or ``None`` when not covered.

    The formulas are written as in the book (``Ce^{−x}``, ``(x − 1)eˣ``): the
    cards nested in the ODE ones go through here too.
    """
    card = _textbook_card(node, variables)
    return None if card is None else book_card(card)


def _textbook_card(node: CoreNode, variables: list[str]) -> SolveResult | None:
    """The card builder: one branch per textbook method."""
    if node.type is not T.INTEGRAL or not node.children:
        return None
    expression_node = node.children[-1]
    expression = to_sympy(expression_node)
    symbols = sorted(expression.free_symbols, key=str)
    if len(symbols) > 1:
        return None
    variable = symbols[0] if symbols else sympy.Symbol(variables[0] if variables else "x")
    expression = _cancelled(expression, variable)

    try:
        if _is_cosecant(expression, variable):
            return _cosecant_card(node, variable)
        if _is_sin_square(expression, variable):
            return _half_angle_card(node, variable)
        if _is_cos_square(expression, variable):
            return _half_angle_card(node, variable, cosine=True)
        if _is_sin_cube(expression, variable):
            return _odd_sine_card(node, variable)
        if _is_tangent(expression, variable):
            return _tangent_card(node, variable)
        entry = _table_entry(expression, variable)
        if entry is not None and not entry[2]:
            return _table_card(node, expression, variable, entry)
        if entry is not None and entry[2]:
            substitution = find_substitution(expression, variable)
            if substitution is not None:
                return _substitution_card(
                    node, expression, variable, substitution, header=_HEADER_LINEAR
                )
        cyclic = _cyclic_plan(expression, variable)
        if cyclic is not None:
            return _cyclic_card(node, expression, variable, cyclic)
        parts = _parts_card(node, expression, variable)
        if parts is not None:
            return parts
        if is_table_sum(expression, variable):
            return _sum_card(node, expression, variable)
        if _improper_rational(expression, variable):
            # x²/(x − 1): divide first, as the textbook does; substitution would
            # leave a stray constant next to + C.
            rational = _rational_card(node, expression, variable)
            if rational is not None:
                return rational
        if _linear_denominator(expression, variable):
            # 1/(x − 1): t = x − 1 is the textbook move for a proper fraction.
            substitution = find_substitution(expression, variable)
            if substitution is not None:
                return _substitution_card(
                    node, expression, variable, substitution, header=_HEADER_SUBSTITUTION
                )
        expanded = _expanded_fraction(expression, variable)
        if expanded is not None:
            return _expanded_fraction_card(node, expression, variable, expanded)
        substitution = find_substitution(expression, variable)
        if substitution is not None:
            return _substitution_card(
                node, expression, variable, substitution, header=_HEADER_SUBSTITUTION
            )
        rational = _rational_card(node, expression, variable)
        if rational is not None:
            return rational
        return _non_elementary_card(node, expression, variable)
    except (ValueError, TypeError, NotImplementedError, sympy.PolynomialError):
        return None


def _display(expression: sympy.Expr, variable: sympy.Symbol) -> CoreNode:
    """The integrand as written: a polynomial keeps the page order ``3x² − 4x + 5``."""
    try:
        sympy.Poly(expression, variable)
    except (sympy.PolynomialError, TypeError):
        return _ordered(expression)
    token = ordered_terms.set(True)
    try:
        return from_sympy(sympy.expand(expression))
    finally:
        ordered_terms.reset(token)


def _table_card(
    node: CoreNode,
    expression: sympy.Expr,
    variable: sympy.Symbol,
    entry: tuple[sympy.Expr, CoreNode, bool],
) -> SolveResult:
    primitive, _, linear = entry
    card = SolveResult(header=_HEADER_LINEAR if linear else _HEADER_TABLE)
    detail = None
    if (
        isinstance(expression, sympy.Pow)
        and expression.base == variable
        and expression.exp != -1
        and expression.exp.is_number
    ):
        # ∫xⁿ dx: the general rule is the nested «Подробнее» formula itself, so
        # the chip stays arg-free and nothing overflows the phone edge.
        detail = _detail(
            Step(
                _integral(_node(T.POWER, _var(str(variable)), _var("n"))),
                _node(
                    T.FRACTION,
                    _node(T.POWER, _var(str(variable)), _node(T.ADD, _var("n"), _num(1))),
                    _node(T.ADD, _var("n"), _num(1)),
                ),
                KEY_TABLE,
            )
        )
    card.add_group(
        "find_integral",
        Step(
            _integral(_ordered(expression)),
            _ordered(primitive),
            KEY_TABLE,
            subresult=detail,
        ),
    )
    answer = _with_constant(card, _answer(primitive, variable, expression))
    card.set_solution(answer)
    return card


def _expanded_fraction(expression: sympy.Expr, variable: sympy.Symbol) -> sympy.Expr | None:
    """``(x+1)²/x`` -> ``x + 2 + 1/x``: divide a polynomial numerator by a monomial."""
    numerator, denominator = sympy.fraction(sympy.together(expression))
    if denominator == 1 or numerator.is_polynomial(variable) is not True:
        return None
    if denominator.is_polynomial(variable) is not True:
        # 1/(x ln x) is a substitution, not a division of polynomials.
        return None
    try:
        if int(sympy.degree(numerator, variable)) < int(sympy.degree(denominator, variable)):
            return None  # a proper fraction is not expanded by division
    except (TypeError, ValueError, sympy.PolynomialError):
        return None
    quotient, remainder = sympy.div(numerator, denominator, variable)
    expanded = sympy.simplify(quotient + remainder / denominator)
    if expanded == expression or not is_table_sum(expanded, variable):
        return None
    return expanded


def _expanded_fraction_card(
    node: CoreNode,
    expression: sympy.Expr,
    variable: sympy.Symbol,
    expanded: sympy.Expr,
) -> SolveResult | None:
    stage = Step(
        _integral(_display(expression, variable)),
        _integral(_display(expanded, variable)),
        KEY_EXPAND,
        [_display(expanded, variable)],
    )
    return _sum_card(node, expanded, variable, extra=[stage])


def _half_angle_card(
    node: CoreNode, variable: sympy.Symbol, *, cosine: bool = False
) -> SolveResult | None:
    if cosine:
        original = sympy.cos(variable) ** 2
        identity = sympy.Rational(1, 2) + sympy.cos(2 * variable) / 2
    else:
        original = sympy.sin(variable) ** 2
        identity = sympy.Rational(1, 2) - sympy.cos(2 * variable) / 2
    stage = Step(
        _integral(from_sympy(original)),
        _integral(_display(sympy.expand(identity), variable)),
        KEY_HALF_ANGLE,
        [_eq(from_sympy(original), from_sympy(identity))],
    )
    return _sum_card(
        node, sympy.expand(identity), variable, header=_HEADER_HALF_ANGLE, extra=[stage]
    )


def _odd_sine_card(node: CoreNode, variable: sympy.Symbol) -> SolveResult | None:
    rewritten = (1 - sympy.cos(variable) ** 2) * sympy.sin(variable)
    stage = Step(
        _integral(from_sympy(sympy.sin(variable) ** 3)),
        _integral(from_sympy(rewritten)),
        KEY_IDENTITY,
        [_eq(from_sympy(sympy.sin(variable) ** 3), from_sympy(rewritten))],
    )
    substitution = find_substitution(rewritten, variable)
    if substitution is None:
        return None
    return _substitution_card(
        node,
        rewritten,
        variable,
        substitution,
        header=_HEADER_IDENTITY,
        extra=[stage],
        linear_rule=False,
    )


def _tangent_card(node: CoreNode, variable: sympy.Symbol) -> SolveResult | None:
    rewritten = sympy.sin(variable) / sympy.cos(variable)
    stage = Step(
        _integral(from_sympy(sympy.tan(variable))),
        _integral(from_sympy(rewritten)),
        KEY_IDENTITY,
        [_eq(from_sympy(sympy.tan(variable)), from_sympy(rewritten))],
    )
    substitution = find_substitution(rewritten, variable)
    if substitution is None:
        return None
    return _substitution_card(
        node,
        rewritten,
        variable,
        substitution,
        header=_HEADER_SUBSTITUTION,
        extra=[stage],
        linear_rule=False,
    )


def _cosecant_card(node: CoreNode, variable: sympy.Symbol) -> SolveResult | None:
    """``∫dx/sin x`` with ``t = tg(x/2)``: ``sin x = 2t/(1+t²)``, ``dx = 2dt/(1+t²)``."""
    t = sympy.Symbol("t", real=True)
    t_node = _var("t")
    sine = 2 * t / (1 + t**2)
    differential = 2 / (1 + t**2)
    rewritten = sympy.Integer(1) / t
    primitive_t = sympy.log(sympy.Abs(t))
    primitive = primitive_t.subs(t, sympy.tan(variable / 2))
    if not _derivative_matches(primitive, 1 / sympy.sin(variable), variable):
        return None
    card = SolveResult(header=_HEADER_SUBSTITUTION)
    half = variable / 2
    slope = 1 / (2 * sympy.cos(half) ** 2)
    steps = [
        _fact(KEY_SUBSTITUTE, _eq(t_node, from_sympy(sympy.tan(half)))),
        _fact(KEY_DIFFERENTIAL, _eq(_var("dt"), _with_differential(slope, "dx"))),
        _fact(KEY_SINE_HALF, _eq(from_sympy(sympy.sin(variable)), from_sympy(sine))),
        _fact(KEY_DX_EXPR, _eq(_var("dx"), _with_differential(differential, "dt"))),
        Step(node, _integral(from_sympy(rewritten)), KEY_REWRITE),
        Step(
            _integral(from_sympy(rewritten)),
            from_sympy(primitive_t),
            KEY_INNER_TABLE,
            subresult=_detail(
                Step(
                    _integral(from_sympy(rewritten)),
                    from_sympy(primitive_t),
                    KEY_INNER_TABLE,
                )
            ),
        ),
        Step(from_sympy(primitive_t), from_sympy(primitive), KEY_BACK),
    ]
    card.add_group("find_integral", *steps)
    answer = _with_constant(card, _answer(primitive, variable, 1 / sympy.sin(variable)))
    card.set_solution(answer)
    return card


__all__ = [
    "KEY_ANSWER",
    "KEY_BACK",
    "KEY_DIFFERENTIAL",
    "KEY_DX_EXPR",
    "KEY_EXPAND",
    "KEY_FRAC_COEFFS",
    "KEY_FRAC_DIVIDE",
    "KEY_FRAC_EQUATIONS",
    "KEY_FRAC_FACTOR",
    "KEY_FRAC_FORM",
    "KEY_FRAC_LN",
    "KEY_FRAC_NUMBERS",
    "KEY_FRAC_SPLIT",
    "KEY_FRAC_SQUARE",
    "KEY_FROM_SUB",
    "KEY_HALF_ANGLE",
    "KEY_IDENTITY",
    "KEY_INNER_TABLE",
    "KEY_LINEAR",
    "KEY_NONELEM",
    "KEY_PARTS_ANSWER",
    "KEY_PARTS_APPLY",
    "KEY_PARTS_CHOOSE",
    "KEY_PARTS_DEFINE",
    "KEY_PARTS_DIFFERENTIAL",
    "KEY_PARTS_EQUATION",
    "KEY_PARTS_FORMULA",
    "KEY_PARTS_MOVE",
    "KEY_PARTS_REMAINDER",
    "KEY_PARTS_VALUE",
    "KEY_REWRITE",
    "KEY_SINE_HALF",
    "KEY_SUBSTITUTE",
    "KEY_SUM",
    "KEY_TABLE",
    "find_substitution",
    "is_linear_table",
    "is_special_substitution",
    "is_table",
    "is_table_sum",
    "textbook_card",
    "textbook_detail",
]
