"""Команды над выражением (``CoreAction``).

В Photomath над узлом может выполняться **действие**: ``{ "command": …,
"args": […] }``. Так выражаются операции, у которых нет своего типа узла:
разложить на множители, раскрыть, упростить. Наш ``POST /solve`` принимает
необязательное поле ``action`` с командой.

Имена команд — наши (в APK они не восстановлены, кроме примера ``solve``):

* ``solve`` — решить/вычислить (поведение по умолчанию, без действия);
* ``factor`` — разложить на множители (``factorise_call``);
* ``expand`` — раскрыть (``expand_msg``);
* ``simplify`` — упростить (``simplify``);
* ``domain`` — область определения выражения (``domain_find``);
* ``restrictions`` — недопустимые значения выражения (``rel_restrictions_find``);
* ``to_fraction`` — десятичную дробь в обыкновенную (``dec_to_frac``);
* ``to_percent`` — число в проценты (``rewrite_as_percent``);
* ``to_sci`` — число в экспоненциальную запись (``sci_form_msg``);
* ``to_mixed`` — неправильную дробь в смешанное число (``convert_improper_fraction``).

Для уравнения команда применяется к обеим частям.
"""

from __future__ import annotations

from collections.abc import Callable

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import Command, SolveContext, SolveError, Step, boolean_node
from .domain import domain, restrictions
from .integrals import area
from .matrices import MATRIX_COMMANDS
from .series import convergence
from .sympy_bridge import from_sympy, to_sympy
from .vectors import VECTOR_COMMANDS


def _apply_side(
    node: CoreNode, ctx: SolveContext, key: str, transform: Callable[[sympy.Expr], sympy.Expr]
) -> CoreNode:
    """Применить символьное преобразование к узлу (для уравнения — к частям)."""
    if node.type is T.EQUALS and len(node.children) == 2:
        left = from_sympy(transform(to_sympy(node.children[0])))
        right = from_sympy(transform(to_sympy(node.children[1])))
        result = CoreNode.node(T.EQUALS, left, right)
    else:
        result = from_sympy(transform(to_sympy(node)))
    ctx.result.add(Step(left=node, right=result, key=key))
    return result


def factor(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Разложить выражение на множители."""
    del args
    return _apply_side(node, ctx, "factorise_call", sympy.factor)


def expand(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Раскрыть скобки и формулы углов.

    ``trig=True`` раскрывает и тригонометрические формулы: ``sin(2x)``
    превращается в ``2·sin(x)·cos(x)``. Без него sympy оставил бы функцию
    как есть.
    """
    del args
    return _apply_side(node, ctx, "expand_msg", lambda expr: sympy.expand(expr, trig=True))


def simplify(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Упростить выражение."""
    del args
    return _apply_side(node, ctx, "simplify", sympy.simplify)


def to_fraction(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Десятичную дробь — в обыкновенную."""
    del args
    return _apply_side(node, ctx, "dec_to_frac", sympy.nsimplify)


def to_percent(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Число — в проценты."""
    del args
    result = CoreNode.node(T.PERCENTAGE, from_sympy(sympy.sympify(to_sympy(node)) * 100))
    ctx.result.add(Step(left=node, right=result, key="rewrite_as_percent"))
    return result


def to_sci(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Число — в экспоненциальную запись ``a · 10ⁿ``."""
    del args
    value = to_sympy(node)
    if value.is_real is not True or value.is_number is not True:
        raise SolveError("экспоненциальная запись берётся у числа")
    if value == 0:
        result = CoreNode.constant("0")
    else:
        exponent = int(sympy.floor(sympy.log(abs(value), 10)))
        mantissa = float(value) / (10.0**exponent)
        power = CoreNode.node(T.POWER, CoreNode.constant("10"), CoreNode.constant(str(exponent)))
        result = CoreNode.node(T.MULTIPLY, CoreNode.constant(_trim(mantissa)), power)
    ctx.result.add(Step(left=node, right=result, key="sci_form_msg"))
    return result


def _trim(value: float) -> str:
    """Число без хвостового ``.0``."""
    text = repr(value)
    return text[:-2] if text.endswith(".0") else text


def to_mixed(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Неправильную дробь — в смешанное число."""
    del args
    value = sympy.nsimplify(to_sympy(node))
    if not isinstance(value, sympy.Rational) or value.q == 1:
        raise SolveError("смешанное число — из неправильной дроби")
    whole = sympy.Integer(sympy.floor(abs(value)))
    numerator = sympy.Integer(abs(value.p)) - whole * value.q
    if value < 0:
        whole = -whole
    result = CoreNode.node(
        T.FRACTION_MIXED,
        from_sympy(whole),
        from_sympy(numerator),
        from_sympy(sympy.Integer(value.q)),
    )
    ctx.result.add(Step(left=node, right=result, key="convert_improper_fraction"))
    return result


def prove(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Проверить, является ли равенство тождеством."""
    del args
    if node.type is not T.EQUALS or len(node.children) != 2:
        raise SolveError("доказывать нужно равенство")
    difference = sympy.simplify(to_sympy(node.children[0]) - to_sympy(node.children[1]))
    identity = difference == 0
    answer = boolean_node(identity)
    key = "prove_identity_true" if identity else "prove_identity_both_false"
    ctx.result.add(Step(left=node, right=answer, key=key))
    return answer


def substitute(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Подставить значение переменной в выражение."""
    if len(args) != 1:
        raise SolveError("нужно одно значение для подстановки")
    if len(ctx.variables) != 1:
        raise SolveError("подстановка: поддерживается одна переменная")
    symbol = sympy.Symbol(ctx.variables[0])
    result = from_sympy(sympy.simplify(to_sympy(node).subs(symbol, to_sympy(args[0]))))
    ctx.result.add(Step(left=node, right=result, key="substitute_value"))
    return result


def even_odd(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Определить чётность/нечётность функции."""
    del args
    expression_node = (
        node.children[1] if node.type is T.EQUALS and len(node.children) == 2 else node
    )
    if len(ctx.variables) != 1:
        raise SolveError("чётность: поддерживается одна переменная")
    symbol = sympy.Symbol(ctx.variables[0])
    expression = to_sympy(expression_node)
    negated = expression.subs(symbol, -symbol)
    if sympy.simplify(expression - negated) == 0:
        key = "function_even"
    elif sympy.simplify(expression + negated) == 0:
        key = "function_odd"
    else:
        key = "function_not_even_nor_odd"
    ctx.result.add(Step(left=node, right=None, key=key))
    return expression_node


def extrema(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Найти точки экстремума функции (через производные)."""
    del args
    expression_node = (
        node.children[1] if node.type is T.EQUALS and len(node.children) == 2 else node
    )
    if len(ctx.variables) != 1:
        raise SolveError("экстремумы: поддерживается одна переменная")
    var = ctx.variables[0]
    symbol = sympy.Symbol(var)
    function = to_sympy(expression_node)
    derivative = sympy.diff(function, symbol)
    critical = _real_roots(derivative, symbol)
    ctx.result.add(Step(left=node, right=None, key="extrema_derive"))

    points: list[CoreNode] = []
    for point in critical:
        second = sympy.diff(derivative, symbol).subs(symbol, point)
        if second.is_negative:
            key = "extrema_maximum"
        elif second.is_positive:
            key = "extrema_minimum"
        else:
            continue
        ctx.result.add(Step(left=node, right=None, key=key, args=[from_sympy(point)]))
        points.append(CoreNode.node(T.EQUALS, CoreNode.variable(var), from_sympy(point)))
    if not points:
        raise SolveError("точки экстремума не найдены")
    if len(points) == 1:
        return points[0]
    return CoreNode.node(T.LIST, *points)


def _real_roots(expression: sympy.Expr, symbol: sympy.Symbol) -> list[sympy.Expr]:
    """Действительные корни по возрастанию."""
    try:
        found = sympy.solve(sympy.Eq(expression, 0), symbol)
    except (TypeError, ValueError, NotImplementedError):
        return []
    real = [root for root in found if root.is_real is not False]
    real.sort(key=lambda item: _numeric(item))
    return real


def _numeric(value: sympy.Expr) -> float:
    try:
        return float(sympy.N(value))
    except (TypeError, ValueError):
        return 0.0


def inflection(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Найти точки перегиба функции."""
    del args
    expression_node = (
        node.children[1] if node.type is T.EQUALS and len(node.children) == 2 else node
    )
    if len(ctx.variables) != 1:
        raise SolveError("перегибы: поддерживается одна переменная")
    var = ctx.variables[0]
    symbol = sympy.Symbol(var)
    function = to_sympy(expression_node)
    second = sympy.diff(function, symbol, 2)
    candidates = _real_roots(second, symbol)
    ctx.result.add(Step(left=node, right=None, key="inflection_sec_der"))
    ctx.result.add(Step(left=node, right=None, key="inflection_find"))

    points: list[CoreNode] = []
    for point in candidates:
        if not _sign_changes(second, symbol, point):
            continue
        ctx.result.add(
            Step(left=node, right=None, key="inflection_the_point", args=[from_sympy(point)])
        )
        points.append(CoreNode.node(T.EQUALS, CoreNode.variable(var), from_sympy(point)))
    if not points:
        raise SolveError("точки перегиба не найдены")
    if len(points) == 1:
        return points[0]
    return CoreNode.node(T.LIST, *points)


def _sign_changes(expression: sympy.Expr, symbol: sympy.Symbol, point: sympy.Expr) -> bool:
    """Меняет ли выражение знак в точке (численная проверка слева/справа)."""
    delta = sympy.Rational(1, 1000)
    left = expression.subs(symbol, point - delta)
    right = expression.subs(symbol, point + delta)
    try:
        left_value = float(sympy.N(left))
        right_value = float(sympy.N(right))
    except (TypeError, ValueError):
        return False
    return (left_value < 0 < right_value) or (right_value < 0 < left_value)


def asymptotes(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Найти вертикальные и горизонтальные асимптоты."""
    del args
    expression_node = (
        node.children[1] if node.type is T.EQUALS and len(node.children) == 2 else node
    )
    if len(ctx.variables) != 1:
        raise SolveError("асимптоты: поддерживается одна переменная")
    var = ctx.variables[0]
    symbol = sympy.Symbol(var)
    function = to_sympy(expression_node)

    vertical = _vertical_asymptotes(function, symbol)
    if vertical:
        ctx.result.add(Step(left=node, right=None, key="find_vert_asymptote"))
    else:
        ctx.result.add(Step(left=node, right=None, key="no_vert_asymptote"))

    plus = sympy.limit(function, symbol, sympy.oo)
    minus = sympy.limit(function, symbol, -sympy.oo)
    horizontals = [value for value in (plus, minus) if value.is_finite]
    if horizontals:
        ctx.result.add(
            Step(
                left=node,
                right=None,
                key="find_hor_asymptote",
                args=[from_sympy(plus), from_sympy(minus)],
            )
        )
    else:
        ctx.result.add(Step(left=node, right=None, key="no_hor_asymptote"))

    parts: list[CoreNode] = [
        CoreNode.node(T.EQUALS, CoreNode.variable(var), from_sympy(point)) for point in vertical
    ]
    seen: set[str] = set()
    for value in horizontals:
        node_value = from_sympy(value)
        key = node_value.to_contract().__repr__()
        if key not in seen:
            seen.add(key)
            parts.append(CoreNode.node(T.EQUALS, CoreNode.variable("y"), node_value))
    if not parts:
        raise SolveError("асимптоты не найдены")
    if len(parts) == 1:
        return parts[0]
    return CoreNode.node(T.LIST, *parts)


def _vertical_asymptotes(function: sympy.Expr, symbol: sympy.Symbol) -> list[sympy.Expr]:
    """Точки, где функция терпит бесконечный разрыв (вертикальные асимптоты)."""
    _, denominator = sympy.fraction(sympy.together(function))
    if not denominator.has(symbol):
        return []
    points: list[sympy.Expr] = []
    for root in _real_roots(denominator, symbol):
        limit = sympy.limit(function, symbol, root)
        if limit in (sympy.oo, -sympy.oo):
            points.append(root)
    return points


def vertex(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Найти вершину параболы (для квадратичной функции)."""
    del args
    expression_node = (
        node.children[1] if node.type is T.EQUALS and len(node.children) == 2 else node
    )
    if len(ctx.variables) != 1:
        raise SolveError("вершина: поддерживается одна переменная")
    var = ctx.variables[0]
    symbol = sympy.Symbol(var)
    function = to_sympy(expression_node)
    try:
        polynomial = sympy.Poly(function, symbol)
    except sympy.PolynomialError as error:
        raise SolveError("вершина — у квадратичной функции") from error
    if polynomial.degree() != 2:
        raise SolveError("вершина — у квадратичной функции")
    a = polynomial.coeff_monomial(symbol**2)
    b = polynomial.coeff_monomial(symbol)
    x_vertex = sympy.simplify(-b / (2 * a))
    y_vertex = sympy.simplify(function.subs(symbol, x_vertex))
    ctx.result.add(Step(left=node, right=None, key="find_vertex"))
    return CoreNode.node(
        T.LIST,
        CoreNode.node(T.EQUALS, CoreNode.variable(var), from_sympy(x_vertex)),
        CoreNode.node(T.EQUALS, CoreNode.variable("y"), from_sympy(y_vertex)),
    )


def to_degrees(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Радианы — в градусы: угол оборачивается узлом ``DEGREE``."""
    del args
    degrees = sympy.simplify(to_sympy(node) * 180 / sympy.pi)
    result = CoreNode.node(T.DEGREE, from_sympy(degrees))
    ctx.result.add(Step(left=node, right=result, key="rewrite_deg"))
    return result


def to_radians(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Градусы — в радианы (узел ``DEGREE`` переводится в число)."""
    del args
    result = from_sympy(sympy.simplify(to_sympy(node)))
    ctx.result.add(Step(left=node, right=result, key="rewrite_rad"))
    return result


def conic(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Определить тип конического сечения по общему уравнению."""
    del args
    if node.type is not T.EQUALS or len(node.children) != 2:
        raise SolveError("коника — это уравнение")
    if len(ctx.variables) != 2:
        raise SolveError("коника: нужны две переменные")
    first, second = (sympy.Symbol(name) for name in ctx.variables)
    expression = to_sympy(node.children[0]) - to_sympy(node.children[1])
    try:
        polynomial = sympy.Poly(expression, first, second)
    except sympy.PolynomialError as error:
        raise SolveError("не коническое уравнение") from error

    left = polynomial.coeff_monomial(first**2)
    cross = polynomial.coeff_monomial(first * second)
    right = polynomial.coeff_monomial(second**2)
    discriminant = cross * cross - 4 * left * right
    if discriminant < 0:
        key = (
            "conics_classify_circle" if left == right and cross == 0 else "conics_classify_ellipse"
        )
    elif discriminant == 0:
        key = "conics_classify_parabola"
    else:
        key = "conics_classify_hyperbola"
    ctx.result.add(Step(left=node, right=None, key=key))
    return node


COMMANDS: dict[str, Command] = {
    "factor": factor,
    "expand": expand,
    "simplify": simplify,
    "domain": domain,
    "restrictions": restrictions,
    "area": area,
    "conic": conic,
    "convergence": convergence,
    "to_degrees": to_degrees,
    "to_radians": to_radians,
    "vertex": vertex,
    "asymptotes": asymptotes,
    "even_odd": even_odd,
    "extrema": extrema,
    "inflection": inflection,
    "prove": prove,
    "substitute": substitute,
    "to_fraction": to_fraction,
    "to_mixed": to_mixed,
    "to_percent": to_percent,
    "to_sci": to_sci,
    **VECTOR_COMMANDS,
    **MATRIX_COMMANDS,
}


def apply(
    command: str,
    node: CoreNode,
    ctx: SolveContext,
    args: list[CoreNode] | None = None,
) -> CoreNode:
    """Выполнить команду; неизвестная команда — ошибка."""
    handler = COMMANDS.get(command)
    if handler is None:
        raise SolveError(f"неизвестная команда {command!r}")
    return handler(node, ctx, list(args or []))


__all__ = [
    "COMMANDS",
    "Command",
    "apply",
    "area",
    "asymptotes",
    "conic",
    "convergence",
    "domain",
    "even_odd",
    "expand",
    "extrema",
    "factor",
    "inflection",
    "prove",
    "restrictions",
    "simplify",
    "substitute",
    "to_degrees",
    "to_fraction",
    "to_mixed",
    "to_percent",
    "to_radians",
    "to_sci",
    "vertex",
]
