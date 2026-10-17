"""Original, bounded calculus lessons built from verifiable intermediate work.

This layer never changes a solver answer. Unsupported methods deliberately retain
their existing details instead of presenting a CAS answer as a derivation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

import sympy

from .ast import CoreNode
from .node_types import CoreNodeType as T

if TYPE_CHECKING:
    from .solver.base import SolveResult, Step


class _Template(TypedDict):
    arity: int
    templates: dict[str, str]


class _Article(TypedDict):
    title: str
    summary: str
    formula: str
    conditions: str
    example: str
    mistake: str


_TEXT = {
    "derivative": ("Вычисление производной", "Evaluate the derivative"),
    "integral": ("Вычисление интеграла", "Evaluate the integral"),
    "limit": ("Вычисление предела", "Evaluate the limit"),
    "sigma": ("Вычисление конечной суммы", "Evaluate the finite sum"),
    "sum_rule": ("Примените правило суммы или разности", "Apply the sum or difference rule"),
    "product_rule": ("Примените правило произведения", "Apply the product rule"),
    "quotient_rule": ("Примените правило частного", "Apply the quotient rule"),
    "chain_rule": ("Примените правило цепочки", "Apply the chain rule"),
    "power_rule": ("Примените правило степени", "Apply the power rule"),
    "basic_derivative": ("Вычислите табличную производную", "Evaluate the basic derivative"),
    "compose": ("Подставьте вычисленные производные", "Insert the computed derivatives"),
    "simplify": ("Упростите выражение", "Simplify the expression"),
    "domain": ("Сохраните ограничение области определения", "Keep the domain restriction"),
    "power_integral": ("Интегрируйте одночлен по правилу степени", "Integrate the monomial"),
    "linear_integral": (
        "Примените табличный интеграл и разделите на производную линейного аргумента",
        "Use the basic integral and divide by the derivative of the linear argument",
    ),
    "integral_sum": ("Сложите первообразные слагаемых", "Add the term antiderivatives"),
    "constant": (
        "Добавьте произвольную постоянную: её производная равна нулю",
        "Add an arbitrary constant: its derivative is zero",
    ),
    "check_primitive": (
        "Проверьте первообразную производной",
        "Differentiate to check the primitive",
    ),
    "newton": ("Примените формулу Ньютона — Лейбница", "Apply the fundamental theorem"),
    "upper": ("Подставьте верхний предел", "Substitute the upper bound"),
    "lower": ("Подставьте нижний предел", "Substitute the lower bound"),
    "subtract": ("Вычтите значение на нижнем пределе", "Subtract the lower-bound value"),
    "factor": ("Разложите числитель и знаменатель", "Factor numerator and denominator"),
    "cancel": (
        "Сократите общий множитель вне исключённых точек",
        "Cancel the common factor away from excluded points",
    ),
    "substitute": ("Подставьте предельное значение", "Substitute the limiting value"),
    "term": ("Подставьте значение индекса", "Substitute the index value"),
    "expand": ("Раскройте конечную сумму", "Expand the finite sum"),
}

TEMPLATES: dict[str, _Template] = {
    f"lesson_calc_{key}": {"arity": 0, "templates": {"ru": ru, "default": en}}
    for key, (ru, en) in _TEXT.items()
}


def _article(
    title: str, summary: str, formula: str, conditions: str, example: str, mistake: str
) -> _Article:
    return {
        "title": title,
        "summary": summary,
        "formula": formula,
        "conditions": conditions,
        "example": example,
        "mistake": mistake,
    }


ARTICLES: dict[str, dict[str, _Article]] = {
    "calculus_derivative_sum": {
        "ru": _article(
            "Производная суммы",
            "Дифференцируйте каждое слагаемое по одной переменной.",
            "(u ± v)' = u' ± v'",
            "Обе функции дифференцируемы в рассматриваемой точке.",
            "d(x² + 3x)/dx = 2x + 3",
            "Не заменяйте производную суммы произведением.",
        ),
        "en": _article(
            "Derivative of a sum",
            "Differentiate each term with respect to the same variable.",
            "(u ± v)' = u' ± v'",
            "Both terms must be differentiable at the point.",
            "d(x² + 3x)/dx = 2x + 3",
            "Do not turn a sum into a product of derivatives.",
        ),
    },
    "calculus_derivative_product": {
        "ru": _article(
            "Правило произведения",
            "По очереди дифференцируйте каждый множитель.",
            "(uv)' = u'v + uv'",
            "Множители дифференцируемы; остальные сохраняются.",
            "d(x sin x)/dx = sin x + x cos x",
            "Ответ u'v' неверен: нужны два слагаемых.",
        ),
        "en": _article(
            "Product rule",
            "Differentiate one factor at a time and keep the other factors.",
            "(uv)' = u'v + uv'",
            "The factors must be differentiable.",
            "d(x sin x)/dx = sin x + x cos x",
            "u'v' is not the derivative of uv.",
        ),
    },
    "calculus_derivative_quotient": {
        "ru": _article(
            "Правило частного",
            "В числителе вычитайте произведения в правильном порядке.",
            "(u/v)' = (u'v − uv')/v²",
            "v ≠ 0; обе функции дифференцируемы.",
            "d(x/(x+1))/dx = 1/(x+1)², x ≠ −1",
            "Не меняйте порядок вычитания.",
        ),
        "en": _article(
            "Quotient rule",
            "Subtract the cross products in the stated order.",
            "(u/v)' = (u'v − uv')/v²",
            "v must be nonzero; both functions differentiable.",
            "d(x/(x+1))/dx = 1/(x+1)², x ≠ −1",
            "Reversing the subtraction changes the sign.",
        ),
    },
    "calculus_derivative_chain": {
        "ru": _article(
            "Правило цепочки",
            "Производную внешней функции умножьте на производную внутренней.",
            "d f(g(x))/dx = f'(g(x))g'(x)",
            "Обе нужные производные существуют.",
            "d sin(x²)/dx = cos(x²)·2x",
            "Не теряйте множитель g'(x).",
        ),
        "en": _article(
            "Chain rule",
            "Multiply the outer derivative by the inner derivative.",
            "d f(g(x))/dx = f'(g(x))g'(x)",
            "Both required derivatives must exist.",
            "d sin(x²)/dx = cos(x²)·2x",
            "Do not omit g'(x).",
        ),
    },
    "calculus_derivative": {
        "ru": _article(
            "Переменная дифференцирования",
            "В записи d/dx остальные переменные постоянны.",
            "d(xⁿ)/dx = nxⁿ⁻¹; dc/dx = 0",
            "Правило степени действует в области функции.",
            "d(yx²)/dx = 2yx",
            "d(y)/dx = 0, если y не зависит от x.",
        ),
        "en": _article(
            "Differentiation variable",
            "In d/dx, independent other variables are constants.",
            "d(xⁿ)/dx = nxⁿ⁻¹; dc/dx = 0",
            "Use the power rule within the function's domain.",
            "d(yx²)/dx = 2yx",
            "d(y)/dx is zero when y is independent of x.",
        ),
    },
    "calculus_integral": {
        "ru": _article(
            "Первообразная многочлена",
            "Интегрируйте одночлены и добавьте постоянную.",
            "∫ axⁿ dx = axⁿ⁺¹/(n+1) + C",
            "Для многочлена n — целое неотрицательное число.",
            "∫ (3x² + 2) dx = x³ + 2x + C",
            "Не забывайте делить на новую степень.",
        ),
        "en": _article(
            "Polynomial antiderivative",
            "Integrate the monomials and add a constant.",
            "∫ axⁿ dx = axⁿ⁺¹/(n+1) + C",
            "For polynomials n is a nonnegative integer.",
            "∫ (3x² + 2) dx = x³ + 2x + C",
            "Divide by the new exponent, not the old one.",
        ),
    },
    "calculus_definite_integral": {
        "ru": _article(
            "Формула Ньютона — Лейбница",
            "Найдите первообразную и вычтите значения на границах.",
            "∫ₐᵇ f(x) dx = F(b) − F(a)",
            "f непрерывна на отрезке, F' = f.",
            "∫₁² x² dx = 8/3 − 1/3 = 7/3",
            "Вычитайте нижнее значение из верхнего; C сокращается.",
        ),
        "en": _article(
            "Fundamental theorem of calculus",
            "Evaluate an antiderivative at both bounds.",
            "∫ₐᵇ f(x) dx = F(b) − F(a)",
            "f is continuous on the interval and F' = f.",
            "∫₁² x² dx = 8/3 − 1/3 = 7/3",
            "Use upper minus lower; the arbitrary constant cancels.",
        ),
    },
    "calculus_linear_integral": {
        "ru": _article(
            "Интеграл с линейным аргументом",
            "Линейная замена даёт постоянный множитель.",
            "∫ sin(ax+b) dx = −cos(ax+b)/a + C; ∫ exp(ax+b) dx = exp(ax+b)/a + C",
            "a и b постоянны, a ≠ 0; d(ax+b)/dx = a.",
            "∫ cos(3x+1) dx = sin(3x+1)/3 + C",
            "При интегрировании делите на a; при дифференцировании умножайте на a.",
        ),
        "en": _article(
            "Integrals with a linear argument",
            "A linear substitution gives a constant factor.",
            "∫ sin(ax+b) dx = −cos(ax+b)/a + C; ∫ exp(ax+b) dx = exp(ax+b)/a + C",
            "a and b are constant, a ≠ 0; d(ax+b)/dx = a.",
            "∫ cos(3x+1) dx = sin(3x+1)/3 + C",
            "Divide by a when integrating; multiply by a when differentiating.",
        ),
    },
    "calculus_limit": {
        "ru": _article(
            "Подстановка и сокращение в пределе",
            "Непрерывность позволяет подставить точку.",
            "limₓ→ₐ f(x) = f(a) для непрерывной f",
            "Сокращение допустимо только там, где сокращаемый множитель не равен нулю.",
            "limₓ→₁ (x²−1)/(x−1) = limₓ→₁ (x+1) = 2",
            "0/0 — неопределённость, не число; исходная функция при x=1 не определена.",
        ),
        "en": _article(
            "Substitution and cancellation in limits",
            "Continuity permits direct substitution.",
            "limₓ→ₐ f(x) = f(a) when f is continuous at a",
            "Cancel a factor only where it is nonzero, retaining the original domain.",
            "limₓ→₁ (x²−1)/(x−1) = limₓ→₁ (x+1) = 2",
            "0/0 is indeterminate, not a number; the original function is undefined at 1.",
        ),
    },
    "calculus_sigma": {
        "ru": _article(
            "Конечная сумма",
            "Подставьте каждый целый индекс от нижней до верхней границы.",
            "Σₖ₌ₐᵇ f(k) = f(a) + … + f(b)",
            "Границы целые, a ≤ b; все члены определены.",
            "Σₖ₌₁³ k² = 1 + 4 + 9 = 14",
            "Обе границы включены: членов b−a+1.",
        ),
        "en": _article(
            "Finite summation",
            "Substitute every integer index between the two bounds.",
            "Σₖ₌ₐᵇ f(k) = f(a) + … + f(b)",
            "Integer bounds, a ≤ b; every term must be defined.",
            "Σₖ₌₁³ k² = 1 + 4 + 9 = 14",
            "Include both bounds: there are b−a+1 terms.",
        ),
    },
}

RULE_TOPICS = {
    "derive_sum": "calculus_derivative_sum",
    "derive_prod": "calculus_derivative_product",
    "derive_quot": "calculus_derivative_quotient",
    "derive_chain": "calculus_derivative_chain",
    "derive_const": "calculus_derivative",
    "derive_var": "calculus_derivative",
    "find_derivative": "calculus_derivative",
    "find_derivative_with_respect": "calculus_derivative",
    "integrate": "calculus_integral",
    "integrate_calc": "calculus_integral",
    "integrate_def_rewrite": "calculus_definite_integral",
    "integrate_def_bounds": "calculus_definite_integral",
    "limit_solve": "calculus_limit",
    "limit_solve_insert_value": "calculus_limit",
    "series_sigma_find_sub": "calculus_sigma",
}
for _key in _TEXT:
    _topic = "calculus_derivative"
    if _key in {"integral", "power_integral", "integral_sum", "constant", "check_primitive"}:
        _topic = "calculus_integral"
    elif _key == "linear_integral":
        _topic = "calculus_linear_integral"
    elif _key in {"newton", "upper", "lower", "subtract"}:
        _topic = "calculus_definite_integral"
    elif _key in {"limit", "factor", "cancel", "substitute", "domain"}:
        _topic = "calculus_limit"
    elif _key in {"sigma", "term", "expand"}:
        _topic = "calculus_sigma"
    elif _key in {"sum_rule", "product_rule", "quotient_rule", "chain_rule"}:
        _topic = f"calculus_derivative_{_key.removesuffix('_rule')}"
    RULE_TOPICS[f"lesson_calc_{_key}"] = _topic


class _UnsupportedError(Exception):
    """No transparent lesson is available for this expression."""


def _node(kind: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(kind, *children)


def _num(value: int) -> CoreNode:
    return CoreNode.constant(str(value))


def _fold(kind: T, nodes: list[CoreNode]) -> CoreNode:
    if not nodes:
        return _num(0 if kind is T.ADD else 1)
    value = nodes[0]
    for node in nodes[1:]:
        value = _node(kind, value, node)
    return value


def _substitute(node: CoreNode, variable: str, value: CoreNode) -> CoreNode:
    if node.type is T.VARIABLE and node.value == variable:
        return value
    if not node.children:
        return node
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[_substitute(child, variable, value) for child in node.children],
    )


def _emit(result: SolveResult, left: CoreNode | None, right: CoreNode, key: str) -> None:
    from .solver.base import Step

    result.add(Step(left, right, f"lesson_calc_{key}"))


def _symbol(expression: CoreNode) -> sympy.Symbol:
    from .solver.sympy_bridge import to_sympy

    symbols = to_sympy(expression).free_symbols
    if len(symbols) > 1:
        raise _UnsupportedError
    return next(iter(symbols), sympy.Symbol("x"))


def _derivation(expression: CoreNode, variable: sympy.Symbol) -> CoreNode:
    return _node(T.DERIVATION1_DIFF, CoreNode.variable(str(variable)), expression)


def _derive(
    expression: CoreNode, variable: sympy.Symbol, detail: SolveResult, depth: int = 0
) -> CoreNode:
    """Apply only explicit elementary rules; recursively expose their operands."""
    from .solver.sympy_bridge import from_sympy, to_sympy

    if depth > 12 or len(detail) > 100:
        raise _UnsupportedError
    value = to_sympy(expression)
    left = _derivation(expression, variable)
    if not value.has(variable) or expression.type is T.VARIABLE:
        answer = _num(1 if value == variable else 0)
        _emit(detail, left, answer, "basic_derivative")
        return answer
    kind, children = expression.type, expression.children
    if kind in (T.BRACKET, T.POSITIVE) and len(children) == 1:
        return _derive(children[0], variable, detail, depth + 1)
    placeholders = [_derivation(child, variable) for child in children]
    if kind in (T.ADD, T.SUBTRACT, T.MULTIPLY, T.MULTIPLY_IMPLICIT) and len(children) >= 2:
        is_sum = kind in (T.ADD, T.SUBTRACT)

        def compose(parts: list[CoreNode]) -> CoreNode:
            if is_sum:
                return _fold(kind, parts)
            return _fold(
                T.ADD,
                [
                    _fold(
                        T.MULTIPLY,
                        [parts[i] if i == j else child for j, child in enumerate(children)],
                    )
                    for i in range(len(children))
                ],
            )

        rule_key = "sum_rule" if is_sum else "product_rule"
        raw_rule = compose(placeholders)
        _emit(detail, left, raw_rule, rule_key)
        parts = [_derive(child, variable, detail, depth + 1) for child in children]
        raw = compose(parts)
    elif kind in (T.FRACTION, T.DIVIDE) and len(children) == 2:
        u, v = children
        _emit(detail, None, _node(T.NOT_EQUALS, v, _num(0)), "domain")

        def quotient(parts: list[CoreNode]) -> CoreNode:
            return _node(
                T.FRACTION,
                _node(T.SUBTRACT, _node(T.MULTIPLY, parts[0], v), _node(T.MULTIPLY, u, parts[1])),
                _node(T.POWER, v, _num(2)),
            )

        raw_rule = quotient(placeholders)
        _emit(detail, left, raw_rule, "quotient_rule")
        raw = quotient([_derive(child, variable, detail, depth + 1) for child in children])
    elif kind is T.NEGATIVE and len(children) == 1:
        raw_rule = _node(T.NEGATIVE, placeholders[0])
        _emit(detail, left, raw_rule, "sum_rule")
        raw = _node(T.NEGATIVE, _derive(children[0], variable, detail, depth + 1))
    else:
        if not children:
            raise _UnsupportedError
        inner = children[0]
        u = to_sympy(inner)
        if kind is T.POWER and len(children) == 2:
            exponent = to_sympy(children[1])
            if exponent.has(variable) or exponent.is_number is not True:
                raise _UnsupportedError
            outer = _node(
                T.MULTIPLY,
                children[1],
                _node(T.POWER, inner, _node(T.SUBTRACT, children[1], _num(1))),
            )
            rule_key = "power_rule"
        elif kind in (T.SIN, T.COS, T.TAN, T.EXP, T.LN, T.ROOT2) and len(children) == 1:
            formulas = {
                T.SIN: sympy.cos(u),
                T.COS: -sympy.sin(u),
                T.TAN: 1 / sympy.cos(u) ** 2,
                T.EXP: sympy.exp(u),
                T.LN: 1 / u,
                T.ROOT2: 1 / (2 * sympy.sqrt(u)),
            }
            outer = from_sympy(formulas[kind])
            rule_key = "chain_rule"
        else:
            raise _UnsupportedError
        raw_rule = _node(T.MULTIPLY, outer, placeholders[0])
        _emit(detail, left, raw_rule, rule_key)
        raw = _node(T.MULTIPLY, outer, _derive(inner, variable, detail, depth + 1))
    _emit(detail, raw_rule, raw, "compose")
    answer = from_sympy(sympy.simplify(to_sympy(raw)))
    _emit(detail, raw, answer, "simplify")
    return answer


def _polynomial_primitive(
    expression: CoreNode, variable: sympy.Symbol, detail: SolveResult
) -> CoreNode:
    from .solver.sympy_bridge import from_sympy, to_sympy

    value = to_sympy(expression)
    if value.is_polynomial(variable) is not True:
        raise _UnsupportedError
    terms = sympy.Poly(value, variable).terms()
    if len(terms) > 12:
        raise _UnsupportedError
    primitives = []
    for (degree,), coefficient in terms:
        term = from_sympy(coefficient * variable**degree)
        raw = _node(
            T.MULTIPLY,
            _node(T.FRACTION, from_sympy(coefficient), _node(T.ADD, _num(degree), _num(1))),
            _node(T.POWER, CoreNode.variable(str(variable)), _node(T.ADD, _num(degree), _num(1))),
        )
        _emit(detail, _node(T.INTEGRAL, term), raw, "power_integral")
        primitive = from_sympy(coefficient * variable ** (degree + 1) / (degree + 1))
        _emit(detail, raw, primitive, "simplify")
        primitives.append(primitive)
    total = _fold(T.ADD, primitives)
    answer = from_sympy(sympy.simplify(to_sympy(total)))
    _emit(detail, total, answer, "integral_sum")
    return answer


def _integral(step: Step, detail: SolveResult) -> None:
    from .solver.sympy_bridge import from_sympy, to_sympy

    node = step.left
    if node is None:
        raise _UnsupportedError
    if node.type is T.INTEGRAL and node.children:
        expression = node.children[-1]
        variable = _symbol(expression)
        primitive = _polynomial_primitive(expression, variable, detail)
        if (
            step.right is not None
            and sympy.simplify(to_sympy(primitive) - to_sympy(step.right)) != 0
        ):
            raise _UnsupportedError
        _emit(detail, _derivation(primitive, variable), expression, "check_primitive")
        names = {str(symbol) for symbol in to_sympy(expression).free_symbols}
        name = "C"
        while name in names:
            name += "_"
        family = _node(T.ADD, primitive, CoreNode.variable(name))
        _emit(detail, _node(T.INTEGRAL, expression), family, "constant")
        detail.set_solution(family)
        return
    if node.type is T.INTEGRAL_RIGHT_DASH and len(node.children) == 3:
        primitive, lower, upper = node.children
        variable = _symbol(primitive)
    elif node.type is T.INTEGRAL_DEFINITE and len(node.children) == 3:
        lower, upper, expression = node.children
        variable = _symbol(expression)
        # These explicit rules all produce continuous integrands on the real line.
        if to_sympy(expression).is_polynomial(variable):
            primitive = _polynomial_primitive(expression, variable, detail)
        else:
            primitive = _linear_primitive(expression, variable, detail)
    else:
        raise _UnsupportedError
    lo, hi = to_sympy(lower), to_sympy(upper)
    if lo.is_finite is not True or hi.is_finite is not True:
        raise _UnsupportedError
    if lo.is_real is not True or hi.is_real is not True:
        raise _UnsupportedError
    value = to_sympy(primitive)
    upper_sub = _substitute(primitive, str(variable), upper)
    lower_sub = _substitute(primitive, str(variable), lower)
    difference = _node(T.SUBTRACT, upper_sub, lower_sub)
    bounds = _node(T.INTEGRAL_RIGHT_DASH, primitive, lower, upper)
    _emit(detail, node, bounds, "newton")
    _emit(detail, bounds, difference, "substitute")
    upper_value = from_sympy(value.subs(variable, hi))
    lower_value = from_sympy(value.subs(variable, lo))
    _emit(detail, upper_sub, upper_value, "upper")
    _emit(detail, lower_sub, lower_value, "lower")
    answer = from_sympy(sympy.simplify(value.subs(variable, hi) - value.subs(variable, lo)))
    if step.right is not None and sympy.simplify(to_sympy(answer) - to_sympy(step.right)) != 0:
        raise _UnsupportedError
    _emit(detail, _node(T.SUBTRACT, upper_value, lower_value), answer, "subtract")
    detail.set_solution(answer)


def _linear_primitive(
    expression: CoreNode, variable: sympy.Symbol, detail: SolveResult
) -> CoreNode:
    """Recognize only the stated sine/cosine/exponential linear-argument table."""
    from .solver.sympy_bridge import from_sympy, to_sympy

    value = to_sympy(expression)
    coefficient, function = value.as_coeff_Mul()
    if function.func not in (sympy.sin, sympy.cos, sympy.exp) or len(function.args) != 1:
        raise _UnsupportedError
    argument = function.args[0]
    slope = sympy.diff(argument, variable)
    if slope.has(variable) or slope.is_real is not True or slope.is_zero is not False:
        raise _UnsupportedError
    offset = sympy.simplify(argument - slope * variable)
    if offset.has(variable) or offset.is_real is not True:
        raise _UnsupportedError
    _derive(from_sympy(argument), variable, detail)
    table = {
        sympy.sin: -sympy.cos(argument),
        sympy.cos: sympy.sin(argument),
        sympy.exp: sympy.exp(argument),
    }
    raw = _node(
        T.FRACTION,
        _node(T.MULTIPLY, from_sympy(coefficient), from_sympy(table[function.func])),
        from_sympy(slope),
    )
    _emit(detail, _node(T.INTEGRAL, expression), raw, "linear_integral")
    primitive = from_sympy(sympy.simplify(to_sympy(raw)))
    _emit(detail, raw, primitive, "simplify")
    if sympy.simplify(sympy.diff(to_sympy(primitive), variable) - value) != 0:
        raise _UnsupportedError
    _emit(detail, _derivation(primitive, variable), expression, "check_primitive")
    return primitive


def _limit(step: Step, detail: SolveResult) -> None:
    from .solver.sympy_bridge import from_sympy, to_sympy

    node = step.left
    if node is None or len(node.children) != 2:
        raise _UnsupportedError
    point_node, expression = node.children
    variable = _symbol(expression)
    point = to_sympy(point_node)
    if point.is_finite is not True or point.is_real is not True:
        raise _UnsupportedError
    value = to_sympy(expression)
    numerator, denominator = sympy.fraction(sympy.together(value))
    # Preserve a syntactic denominator: SymPy eagerly turns x/x into 1.
    if expression.type in (T.FRACTION, T.DIVIDE) and len(expression.children) == 2:
        numerator, denominator = (to_sympy(child) for child in expression.children)
    reduced = value
    if denominator.subs(variable, point) == 0:
        if not numerator.is_polynomial(variable) or not denominator.is_polynomial(variable):
            raise _UnsupportedError
        common = sympy.gcd(numerator, denominator)
        if common == 1 or numerator.subs(variable, point) != 0:
            raise _UnsupportedError
        reduced = sympy.cancel(value)
        _, reduced_denominator = sympy.fraction(reduced)
        if reduced_denominator.subs(variable, point) == 0:
            raise _UnsupportedError
        _emit(detail, None, _node(T.NOT_EQUALS, from_sympy(denominator), _num(0)), "domain")
        factored = _node(
            T.FRACTION, from_sympy(sympy.factor(numerator)), from_sympy(sympy.factor(denominator))
        )
        _emit(detail, expression, factored, "factor")
        expression = from_sympy(reduced)
        _emit(detail, factored, expression, "cancel")
    elif denominator != 1:
        _emit(detail, None, _node(T.NOT_EQUALS, from_sympy(denominator), _num(0)), "domain")
    # A finite value alone does not prove continuity (e.g. sign/branch functions).
    domain = sympy.calculus.util.continuous_domain(reduced, variable, sympy.S.Reals)
    if domain.interior.contains(point) is not sympy.true:
        raise _UnsupportedError
    substituted = _substitute(expression, str(variable), point_node)
    answer_value = sympy.simplify(reduced.subs(variable, point))
    if answer_value.is_finite is not True or answer_value.is_real is not True:
        raise _UnsupportedError
    if step.right is not None and sympy.simplify(answer_value - to_sympy(step.right)) != 0:
        raise _UnsupportedError
    answer = from_sympy(answer_value)
    _emit(detail, _node(node.type, point_node, expression), substituted, "substitute")
    _emit(detail, substituted, answer, "simplify")
    detail.set_solution(answer)


def _sigma(step: Step, detail: SolveResult) -> None:
    from .solver.sympy_bridge import from_sympy, to_sympy

    node = step.left
    if node is None:
        raise _UnsupportedError
    if len(node.children) == 4:
        index, lower, upper, expression = node.children
        if index.type is not T.VARIABLE or not index.value:
            raise _UnsupportedError
    elif len(node.children) == 3:
        lower, upper, expression = node.children
        index = CoreNode.variable("n")
    else:
        raise _UnsupportedError
    lo, hi = to_sympy(lower), to_sympy(upper)
    if not isinstance(lo, sympy.Integer) or not isinstance(hi, sympy.Integer):
        raise _UnsupportedError
    if not 1 <= int(hi - lo + 1) <= 12:
        raise _UnsupportedError
    substituted_terms, terms = [], []
    for integer in range(int(lo), int(hi) + 1):
        substituted = _substitute(expression, index.value or "n", _num(integer))
        value = sympy.simplify(to_sympy(substituted))
        if value.is_finite is not True:
            raise _UnsupportedError
        term = from_sympy(value)
        substituted_terms.append(substituted)
        terms.append(term)
        _emit(detail, substituted, term, "term")
    expansion = _fold(T.ADD, substituted_terms)
    _emit(detail, node, expansion, "expand")
    total = _fold(T.ADD, terms)
    _emit(detail, expansion, total, "substitute")
    answer = from_sympy(sympy.simplify(to_sympy(total)))
    if step.right is not None and sympy.simplify(to_sympy(answer) - to_sympy(step.right)) != 0:
        raise _UnsupportedError
    _emit(detail, total, answer, "simplify")
    detail.set_solution(answer)


def enrich(step: Step) -> str | None:
    """Attach genuine intermediate calculations without changing the public step."""
    from .solver.base import SolveError, SolveResult
    from .solver.sympy_bridge import to_sympy

    if step.key.startswith("lesson_calc_") or step.left is None:
        return None
    detail = SolveResult()
    try:
        if step.key in {"find_derivative", "find_derivative_with_respect"}:
            node = step.left
            if node.type is T.DERIVATION1_DIFF and len(node.children) == 2:
                index, expression = node.children
                if index.type is not T.VARIABLE or not index.value:
                    return None
                variable = sympy.Symbol(index.value)
            elif (
                node.type in (T.DERIVATION, T.DERIVATION1, T.PRIME, T.DERIVATION1_PRIME)
                and len(node.children) == 1
            ):
                expression = node.children[0]
                variable = _symbol(expression)
            else:
                return None
            answer = _derive(expression, variable, detail)
            if step.right is None or sympy.simplify(to_sympy(answer) - to_sympy(step.right)) != 0:
                return None
            detail.set_solution(answer)
            title = "derivative"
        elif step.key in {"integrate_calc", "integrate_def_bounds"}:
            _integral(step, detail)
            title = "integral"
        elif step.key == "limit_solve":
            _limit(step, detail)
            title = "limit"
        elif step.key == "series_sigma_find_sub":
            _sigma(step, detail)
            title = "sigma"
        else:
            return None
    except (
        _UnsupportedError,
        SolveError,
        ValueError,
        TypeError,
        NotImplementedError,
        sympy.PolynomialError,
    ):
        return None
    step.subresult = detail
    return f"lesson_calc_{title}"


__all__ = ["ARTICLES", "RULE_TOPICS", "TEMPLATES", "enrich"]
