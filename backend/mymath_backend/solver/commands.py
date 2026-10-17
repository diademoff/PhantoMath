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
* ``to_mixed`` — неправильную дробь в смешанное число (``convert_improper_fraction``);
* ``approximate`` — приближённое значение с округлением (``round0``…``round4``);
* ``inverse_function`` — обратная функция (``find_inverse``);
* ``solve_param`` — уравнение с параметрами относительно переменной (``eq_param_write``);
* ``complex_power`` — степень комплексного числа (``complex_pow_polar_moivre_simple``);
* ``complex_roots`` — корни n-й степени из комплексного числа (``complex_find_root_polar``);
* ``complex_polar_multiply``/``complex_polar_divide`` — умножение и деление в полярной форме;
* ``conic_details`` — полный разбор коники (центр, фокусы, вершины, директриса, радиус);
* ``explicit_formula`` — явная формула общего члена последовательности;
* ``slope_intercept`` — линейное уравнение в виде y = kx + b (``slope_and_y_intercept``);
* ``axis_of_symmetry``/``intercept_form`` — ось симметрии и форма по корням параболы;
* ``slant_asymptote`` — наклонная асимптота рациональной функции;
* ``x_intercept_count`` — число пересечений параболы с осью x;
* ``evaluate_function`` — значение функции при данном аргументе (``function_evaluate``);
* ``sequence_convergence`` — сходимость последовательности (``seq_lim_conv``);
* ``ratio_test`` — признак Даламбера для ряда (``series_ratio_test``);
* ``root_test``/``nth_term_test`` — радикальный и необходимый признаки сходимости ряда;
* ``integral_test``/``alt_test`` — интегральный признак и признак Лейбница;
* ``direct_comparison_test``/``limit_comparison_test`` — сравнение с рядом-эталоном;
* ``system_check`` — проверка набора значений на решение системы;
* ``extrema_on_interval`` — наибольшее и наименьшее значение на отрезке;
* ``gcd``/``lcm``/``mod`` — НОД/НОК/остаток; ``prime_factorization``, ``round_place``;
* ``piecewise_value`` — значение кусочно-заданной функции (``PIECEWISE_DEFINITION``);
* ``inequality_on_interval`` — неравенство (в т.ч. тригонометрическое) на отрезке;
* ``radius_of_convergence`` — радиус сходимости степенного ряда;
* ``pseries_test``/``geom_series_test`` — признаки обобщённого гармонического
  и геометрического рядов;
* ``partial_fractions`` — разложение на простейшие дроби (``partial_frac``);
* ``intercepts`` — пересечения графика с осями координат
  (``find_x_intercept``/``find_y_intercept``);
* ``range`` — область значений функции (``graph_rt_info_range``);
* ``periodic_to_frac`` — периодическую дробь в обыкновенную (``periodic_to_frac``);
* ``nth_derivative`` — производная порядка ``n``
  (``second_derivative``/``find_high_order_derivative``).

Для уравнения команда применяется к обеим частям.
"""

from __future__ import annotations

from collections.abc import Callable
from fractions import Fraction

import sympy
from sympy.calculus.util import function_range

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import Command, SolveContext, SolveError, Step, boolean_node
from .complex import (
    complex_polar_divide,
    complex_polar_multiply,
    complex_power,
    complex_roots,
)
from .conics import conic_details
from .derivatives import nth_derivative
from .diff_equations import diff_eq
from .domain import domain, restrictions
from .inequalities import inequality_on_interval
from .integrals import area
from .matrices import MATRIX_COMMANDS
from .piecewise import piecewise_value
from .sequences import explicit_formula, sequence_convergence
from .series import (
    alt_test,
    convergence,
    direct_comparison_test,
    geom_series_test,
    integral_test,
    limit_comparison_test,
    nth_term_test,
    pseries_test,
    radius_of_convergence,
    ratio_test,
    root_test,
)
from .sympy_bridge import from_sympy, to_sympy
from .systems import system_check
from .trigonometry import pythagorean_identity
from .vectors import VECTOR_COMMANDS


def _expression_value(node: CoreNode, message: str) -> sympy.Expr:
    """Значение узла как выражение; отношение и логика отклоняются.

    Команды-преобразования работают с числом или выражением. Без этой проверки
    в sympy уходило ``Equality`` (или ``False``, если обе части — числа):
    ``* 100`` и ``fraction(together(…))`` бросали ``TypeError`` — ответ не
    уходил вовсе, и клиент видел обрыв соединения вместо ошибки; а
    ``simplify`` молча **решал** уравнение (``2x + 3 = 7`` → ``x = 2`` под
    шагом «Выразите радианную меру»).
    """
    value = to_sympy(node)
    if not isinstance(value, sympy.Expr):
        raise SolveError(message)
    return value


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

    def real_quadratic(expression: sympy.Expr) -> sympy.Expr:
        factored = sympy.factor(expression)
        # An irreducible-over-Q quadratic can still have exact real factors.
        # Do not offer a no-op for 2x²+9x+6 after showing its two real roots.
        if factored == expression and len(expression.free_symbols) == 1:
            try:
                polynomial = sympy.Poly(expression, next(iter(expression.free_symbols)))
                if polynomial.degree() == 2 and all(c.is_Rational for c in polynomial.all_coeffs()):
                    a, b, c = polynomial.all_coeffs()
                    discriminant = b * b - 4 * a * c
                    if discriminant.is_positive is True:
                        return sympy.factor(expression, extension=sympy.sqrt(discriminant))
            except (sympy.PolynomialError, ValueError, TypeError):
                pass
        return factored

    return _apply_side(node, ctx, "factorise_call", real_quadratic)


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
    identity = pythagorean_identity(node, ctx)
    if identity is not None:
        return identity
    return _apply_side(node, ctx, "simplify", sympy.simplify)


def to_fraction(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Десятичную дробь — в обыкновенную.

    У уравнения преобразуются обе части (``_apply_side``): это команда-
    перезапись, как ``factor``/``expand``.
    """
    del args
    return _apply_side(node, ctx, "dec_to_frac", sympy.nsimplify)


def _integer_values(node: CoreNode) -> list[int]:
    """Целые значения из узла ``SEQUENCE``."""
    values: list[int] = []
    for child in node.children:
        value = to_sympy(child)
        if value.is_Integer is not True:
            raise SolveError("ожидались целые числа")
        values.append(int(value))
    if len(values) < 2:
        raise SolveError("нужно хотя бы два числа")
    return values


def gcd(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Наибольший общий делитель чисел (``SEQUENCE``)."""
    del args
    values = _integer_values(node)
    result = from_sympy(sympy.Integer(sympy.gcd(values)))
    ctx.result.add(Step(left=node, right=result, key="calculate_short"))
    return result


def lcm(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Наименьшее общее кратное чисел (``SEQUENCE``)."""
    del args
    values = _integer_values(node)
    result = from_sympy(sympy.Integer(sympy.lcm(values)))
    ctx.result.add(Step(left=node, right=result, key="calculate_short"))
    return result


def modulo(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Остаток от деления: ``a mod b`` (``SEQUENCE`` из двух чисел)."""
    del args
    values = _integer_values(node)
    if len(values) != 2 or values[1] == 0:
        raise SolveError("остаток: делимое и ненулевой делитель")
    result = from_sympy(sympy.Integer(values[0] % values[1]))
    ctx.result.add(Step(left=node, right=result, key="calculate_short"))
    return result


def prime_factorization(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Разложение натурального числа на простые множители."""
    del args
    value = to_sympy(node)
    if value.is_Integer is not True or value <= 1:
        raise SolveError("разложение на простые — у натурального числа > 1")
    factors = sympy.factorint(int(value))
    terms = [
        sympy.Pow(sympy.Integer(prime), power, evaluate=False)
        if power > 1
        else sympy.Integer(prime)
        for prime, power in sorted(factors.items())
    ]
    product = terms[0] if len(terms) == 1 else sympy.Mul(*terms, evaluate=False)
    result = from_sympy(product)
    ctx.result.add(Step(left=node, right=result, key="factorise_call"))
    return result


def round_place(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Округлить число до заданного разряда (аргумент — степень десяти)."""
    value = to_sympy(node)
    if value.is_number is not True or value.is_finite is False:
        raise SolveError("округление берётся у числа")
    place = _rounding_digits(args)
    factor = 10**place
    rounded = round(float(sympy.N(value, 20)) / factor) * factor
    result = from_sympy(sympy.Integer(rounded))
    ctx.result.add(Step(left=node, right=result, key="round"))
    return result


def approximate(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Приближённое значение выражения с округлением.

    Аргумент — число знаков после запятой (по умолчанию 0). Ответ — узел
    ``APPROXIMATE[выражение, округлённое значение]``; шаг ``round0``…``round4``
    по числу знаков (дальше — общий ``round``).
    """
    value = to_sympy(node)
    if value.is_number is not True or value.is_finite is False:
        raise SolveError("приближённое значение берётся у числа")
    digits = _rounding_digits(args)
    # Округление через Python: sympy.Float.round() округляет по двоичной
    # мантиссе и даёт 0.3330078125 вместо 0.333.
    text = f"{float(sympy.N(value, 20)):.{digits}f}"
    result = CoreNode.node(T.APPROXIMATE, from_sympy(value), CoreNode.constant(text))
    key = f"round{digits}" if 0 <= digits <= 4 else "round"
    ctx.result.add(Step(left=node, right=result, key=key))
    return result


def _rounding_digits(args: list[CoreNode]) -> int:
    """Число знаков округления из аргументов команды."""
    if not args:
        return 0
    if len(args) != 1 or args[0].type is not T.CONSTANT or args[0].value is None:
        raise SolveError("число знаков округления — целое")
    try:
        number = Fraction(args[0].value)
    except ValueError as error:
        raise SolveError("число знаков округления — целое") from error
    if number.denominator != 1 or number.numerator < 0:
        raise SolveError("число знаков округления — целое")
    return number.numerator


def to_percent(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Число — в проценты."""
    del args
    value = _expression_value(node, "проценты берутся у числа")
    result = CoreNode.node(T.PERCENTAGE, from_sympy(sympy.sympify(value) * 100))
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


def periodic_to_frac(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Периодическую десятичную дробь — в обыкновенную.

    Узел ``PERIODIC[цифры, период]``: ``цифры`` — дробная часть без точки,
    ``период`` — сколько последних цифр повторяются. Для ``0.s(rep)`` со
    ``p`` неповторяющимися цифрами значение равно ``(s − s[:p]) / (10ⁿ − 10ᵖ)``.
    """
    del args
    if node.type is not T.PERIODIC or len(node.children) != 2:
        raise SolveError("периодическая дробь — узел PERIODIC с двумя детьми")
    digits = _periodic_digits(node.children[0])
    repeating = _repeating_length(node.children[1])
    if not 0 < repeating <= len(digits):
        raise SolveError("число повторяющихся цифр больше длины дроби")
    nonrepeating = len(digits) - repeating
    numerator = int(digits) - int(digits[:nonrepeating] or "0")
    denominator = 10 ** len(digits) - 10**nonrepeating
    result = from_sympy(sympy.Rational(numerator, denominator))
    ctx.result.add(Step(left=node, right=result, key="periodic_to_frac"))
    return result


def _periodic_digits(node: CoreNode) -> str:
    """Цифры дробной части без разделителей."""
    if node.type is not T.CONSTANT or node.value is None:
        raise SolveError("цифры периодической дроби должны быть числом")
    digits = "".join(symbol for symbol in node.value if symbol.isdigit())
    if not digits:
        raise SolveError("некорректная периодическая дробь")
    return digits


def _repeating_length(node: CoreNode) -> int:
    """Сколько последних цифр повторяются."""
    if node.type is not T.CONSTANT or node.value is None:
        raise SolveError("период должен быть числом")
    try:
        number = Fraction(node.value)
    except ValueError as error:
        raise SolveError("период должен быть целым числом") from error
    if number.denominator != 1:
        raise SolveError("период должен быть целым числом")
    return number.numerator


def prove(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Проверить, является ли равенство тождеством."""
    del args
    if node.type is not T.EQUALS or len(node.children) != 2:
        raise SolveError("доказывать нужно равенство")
    difference = sympy.simplify(to_sympy(node.children[0]) - to_sympy(node.children[1]))
    identity = difference == 0
    answer = boolean_node(identity)
    key = "prove_identity_true" if identity else "prove_identity_both_false"
    ctx.result.add(Step(left=node, right=None, key="prove_identity"))
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
        key = "function_even_simple"
    elif sympy.simplify(expression + negated) == 0:
        key = "function_odd_simple"
    else:
        key = "function_not_even_nor_odd_simple"
    ctx.result.add(Step(left=node, right=None, key="function_even_odd_notation"))
    ctx.result.add(Step(left=node, right=None, key=key))
    return expression_node


def extrema_on_interval(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Точки наибольшего и наименьшего значения функции на отрезке.

    Аргументы команды — границы отрезка. Критические точки внутри и концы
    сравниваются по значению функции; ответ — ``x = …`` для максимума и
    минимума. Шаги ``extrema_find_critical``, ``extrema_critical_point``,
    ``extrema_endpoint``, ``extrema_calculate_at_point``, ``extrema_final``.
    """
    expression_node = _expression_of(node)
    if len(ctx.variables) != 1:
        raise SolveError("экстремумы на отрезке: поддерживается одна переменная")
    if len(args) != 2:
        raise SolveError("нужны границы отрезка")
    var = ctx.variables[0]
    symbol = sympy.Symbol(var)
    function = to_sympy(expression_node)
    lower, upper = to_sympy(args[0]), to_sympy(args[1])
    if lower.is_real is not True or upper.is_real is not True:
        raise SolveError("границы отрезка должны быть числами")
    if lower > upper:
        lower, upper = upper, lower

    derivative = sympy.diff(function, symbol)
    ctx.result.add(Step(left=node, right=None, key="extrema_find_critical"))
    critical = [root for root in _real_roots(derivative, symbol) if _within(root, lower, upper)]
    ctx.result.add(Step(left=node, right=None, key="extrema_critical_point"))
    candidates = [lower, *critical, upper]
    ctx.result.add(Step(left=node, right=None, key="extrema_endpoint"))
    values = []
    for point in candidates:
        value = sympy.simplify(function.subs(symbol, point))
        values.append((point, value))
        ctx.result.add(
            Step(left=node, right=None, key="extrema_calculate_at_point", args=[from_sympy(point)])
        )
    maximum = max(values, key=lambda item: _numeric(item[1]))
    minimum = min(values, key=lambda item: _numeric(item[1]))
    answer = CoreNode.node(
        T.LIST,
        CoreNode.node(T.EQUALS, CoreNode.variable(var), from_sympy(maximum[0])),
        CoreNode.node(T.EQUALS, CoreNode.variable(var), from_sympy(minimum[0])),
    )
    ctx.result.add(Step(left=node, right=answer, key="extrema_final"))
    return answer


def _within(point: sympy.Expr, lower: sympy.Expr, upper: sympy.Expr) -> bool:
    """Лежит ли точка в отрезке ``[lower, upper]`` (численно)."""
    value = _numeric(point)
    return _numeric(lower) <= value <= _numeric(upper)


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
    if critical:
        ctx.result.add(Step(left=node, right=None, key="extrema_critical_point"))
        ctx.result.add(Step(left=node, right=None, key="extrema_critical_intervals"))
        ctx.result.add(Step(left=node, right=None, key="extrema_interval_points"))

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
    ctx.result.add(Step(left=node, right=None, key="inflection_domain_find"))
    ctx.result.add(Step(left=node, right=None, key="inflection_domain_snd_find"))
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


def _expression_of(node: CoreNode) -> CoreNode:
    """Выражение функции: правая часть ``y = f(x)`` или сам узел."""
    if node.type is T.EQUALS and len(node.children) == 2:
        return node.children[1]
    return node


def intercepts(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Найти пересечения графика функции с осями координат.

    С осью x — корни ``f(x) = 0`` (``find_x_intercept``, подстановка ``y = 0``);
    с осью y — значение ``f(0)`` (``find_y_intercept``, подстановка ``x = 0``).
    Ответ — список ``x = …`` / ``y = …``; несуществующего пересечения нет в
    списке и о нём сообщает ``no_x_intercept``/``no_y_intercept``.
    """
    del args
    expression_node = _expression_of(node)
    if len(ctx.variables) != 1:
        raise SolveError("пересечения с осями: поддерживается одна переменная")
    var = ctx.variables[0]
    symbol = sympy.Symbol(var)
    function = to_sympy(expression_node)
    axis_x = CoreNode.variable(var)
    axis_y = CoreNode.variable("y")

    ctx.result.add(Step(left=node, right=None, key="find_x_intercept", args=[axis_x]))
    ctx.result.add(
        Step(
            left=node,
            right=None,
            key="x_intercept_substitute",
            args=[axis_x, CoreNode.node(T.EQUALS, axis_y, CoreNode.constant("0"))],
        )
    )
    roots = _real_roots(function, symbol)
    points: list[CoreNode] = [CoreNode.node(T.EQUALS, axis_x, from_sympy(root)) for root in roots]
    if not roots:
        ctx.result.add(Step(left=node, right=None, key="no_x_intercept", args=[axis_x]))
    elif len(roots) == 1:
        ctx.result.add(
            Step(
                left=node,
                right=None,
                key="one_x_intercept",
                args=[axis_x, from_sympy(roots[0])],
            )
        )
    else:
        ctx.result.add(
            Step(
                left=node,
                right=None,
                key="two_x_intercepts",
                args=[
                    axis_x,
                    CoreNode.node(T.LIST, *(from_sympy(root) for root in roots)),
                ],
            )
        )

    ctx.result.add(Step(left=node, right=None, key="find_y_intercept", args=[axis_y]))
    ctx.result.add(
        Step(
            left=node,
            right=None,
            key="y_intercept_substitute",
            args=[axis_y, CoreNode.node(T.EQUALS, axis_x, CoreNode.constant("0"))],
        )
    )
    at_zero = function.subs(symbol, sympy.Integer(0))
    if at_zero.is_finite:
        points.append(CoreNode.node(T.EQUALS, axis_y, from_sympy(at_zero)))
    else:
        ctx.result.add(Step(left=node, right=None, key="no_y_intercept", args=[axis_y]))

    if not points:
        raise SolveError("пересечений с осями координат нет")
    if len(points) == 1:
        return points[0]
    return CoreNode.node(T.LIST, *points)


def inverse_function(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Найти обратную функцию ``y = f⁻¹(x)`` для ``f``.

    Выражение ``f(x)`` (или правая часть ``y = f(x)``) решается относительно
    ``x``; свободная переменная результата обозначается ``x``. Однозначная
    обратная функция — один корень; ветвящиеся случаи (``x²``) отклоняются.
    """
    del args
    expression_node = _expression_of(node)
    if len(ctx.variables) != 1:
        raise SolveError("обратная функция: поддерживается одна переменная")
    var = ctx.variables[0]
    target = sympy.Symbol("_y")
    try:
        found = sympy.solve(sympy.Eq(target, to_sympy(expression_node)), sympy.Symbol(var))
    except (NotImplementedError, TypeError, ValueError) as error:
        raise SolveError("обратная функция не выражается") from error
    # Комплексные ветви отбрасываем: у ``x³`` корней три, но действителен один.
    real = [root for root in found if not root.has(sympy.I)]
    if not real:
        raise SolveError("обратная функция не выражается")
    if len(real) > 1:
        raise SolveError("обратная функция не однозначна")
    inverse = from_sympy(real[0].subs(target, sympy.Symbol("x")))
    result = CoreNode.node(T.EQUALS, CoreNode.variable("y"), inverse)
    ctx.result.add(Step(left=node, right=result, key="find_inverse"))
    return result


def solve_param(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Решить уравнение с параметрами относительно указанной переменной.

    Аргумент команды — переменная, относительно которой решаем; остальные
    буквы считаются параметрами. Ответ — ``x = …`` (или список выражений с
    параметрами); шаги ``eq_param_write`` и ``eq_linear_param_j_final``.
    """
    if node.type is not T.EQUALS or len(node.children) != 2:
        raise SolveError("параметрическое уравнение — это равенство")
    if len(args) != 1 or args[0].type is not T.VARIABLE or not args[0].value:
        raise SolveError("нужно указать переменную для решения")
    target = args[0].value
    lhs, rhs = node.children
    try:
        found = sympy.solve(sympy.Eq(to_sympy(lhs), to_sympy(rhs)), sympy.Symbol(target))
    except (NotImplementedError, TypeError, ValueError) as error:
        raise SolveError("уравнение с параметрами не решается") from error
    if not found:
        raise SolveError("нет решений относительно переменной")

    answers = [
        CoreNode.node(T.EQUALS, CoreNode.variable(target), from_sympy(root)) for root in found
    ]
    answer = answers[0] if len(answers) == 1 else CoreNode.node(T.LIST, *answers)
    ctx.result.add(Step(left=node, right=None, key="eq_param_write"))
    ctx.result.add(
        Step(
            left=node,
            right=answer,
            key="eq_linear_param_j_final",
            args=[CoreNode.variable(target)],
        )
    )
    return answer


def partial_fractions(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Разложить рациональное выражение на простейшие дроби.

    Считает sympy (``apart``); шаг ``partial_frac``. Выражение обязано быть
    рациональным (знаменатель зависит от переменной).
    """
    del args
    expression = _expression_value(node, "простейшие дроби берутся у рационального выражения")
    _, denominator = sympy.fraction(sympy.together(expression))
    if denominator == 1 or not denominator.free_symbols:
        raise SolveError("простейшие дроби берутся у рационального выражения")
    decomposed = sympy.apart(expression)
    result = from_sympy(decomposed)
    ctx.result.add(Step(left=node, right=result, key="partial_frac"))
    return result


def evaluate_function(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Вычислить значение функции ``f(a)`` (подстановка значения).

    Шаги ``function_evaluate`` и ``function_evaluate_value`` (с значением).
    """
    if len(args) != 1:
        raise SolveError("нужно значение для подстановки")
    if len(ctx.variables) != 1:
        raise SolveError("значение функции: поддерживается одна переменная")
    symbol = sympy.Symbol(ctx.variables[0])
    result = from_sympy(sympy.simplify(to_sympy(node).subs(symbol, to_sympy(args[0]))))
    ctx.result.add(Step(left=node, right=None, key="function_evaluate"))
    ctx.result.add(Step(left=node, right=result, key="function_evaluate_value", args=[args[0]]))
    return result


def x_intercept_count(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Число пересечений параболы с осью x по дискриминанту.

    Шаги ``function_num_inter_quad`` и ``function_num_inter_quad_empty``/
    ``_one``/``_pl``; ответ — количество (0, 1 или 2).
    """
    del args
    expression_node = _expression_of(node)
    if len(ctx.variables) != 1:
        raise SolveError("число пересечений: поддерживается одна переменная")
    var = ctx.variables[0]
    symbol = sympy.Symbol(var)
    try:
        polynomial = sympy.Poly(to_sympy(expression_node), symbol)
    except sympy.PolynomialError as error:
        raise SolveError("число пересечений — у квадратичной функции") from error
    if polynomial.degree() != 2:
        raise SolveError("число пересечений — у квадратичной функции")
    a = polynomial.coeff_monomial(symbol**2)
    b = polynomial.coeff_monomial(symbol)
    c = polynomial.coeff_monomial(1)
    discriminant = b * b - 4 * a * c

    ctx.result.add(
        Step(
            left=node,
            right=None,
            key="function_num_inter_quad",
            args=[CoreNode.variable(var)],
        )
    )
    if discriminant < 0:
        key, count, step_args = "function_num_inter_quad_empty", 0, [CoreNode.constant("0")]
    elif discriminant == 0:
        key, count, step_args = (
            "function_num_inter_quad_one",
            1,
            [CoreNode.constant("0"), CoreNode.constant("1")],
        )
    else:
        key, count, step_args = (
            "function_num_inter_quad_pl",
            2,
            [CoreNode.constant("0"), CoreNode.constant("2")],
        )
    answer = CoreNode.constant(str(count))
    ctx.result.add(Step(left=node, right=answer, key=key, args=step_args))
    return answer


def slant_asymptote(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Наклонная асимптота ``y = kx + b`` рациональной функции.

    ``k = lim f(x)/x``, ``b = lim (f(x) − kx)`` при ``x → ∞`` (шаги
    ``slope_slant_asymptote``, ``intercept_slant_asymptote``,
    ``def_slant_asymptote``). Если степени числителя и знаменателя не
    различаются на единицу — асимптоты нет.
    """
    del args
    expression_node = _expression_of(node)
    if len(ctx.variables) != 1:
        raise SolveError("наклонная асимптота: поддерживается одна переменная")
    symbol = sympy.Symbol(ctx.variables[0])
    function = to_sympy(expression_node)
    numerator, denominator = sympy.fraction(sympy.together(function))
    # Степень берётся только у многочлена: у ``exp(x)`` она бросает
    # ``PolynomialError``, и ответ не уходил клиенту вовсе.
    if numerator.is_polynomial(symbol) is not True or denominator.is_polynomial(symbol) is not True:
        raise SolveError("наклонная асимптота берётся у рациональной функции")
    if sympy.degree(numerator, symbol) != sympy.degree(denominator, symbol) + 1:
        raise SolveError(
            "наклонной асимптоты нет",
            "no_slope_slant_asymptote",
        )

    slope = sympy.limit(function / symbol, symbol, sympy.oo)
    intercept = sympy.limit(function - slope * symbol, symbol, sympy.oo)
    if slope.is_finite is not True or intercept.is_finite is not True:
        raise SolveError("наклонной асимптоты нет", "no_slope_slant_asymptote")

    line = CoreNode.node(
        T.EQUALS,
        CoreNode.variable("y"),
        from_sympy(sympy.simplify(slope * symbol + intercept)),
    )
    ctx.result.add(
        Step(
            left=node,
            right=None,
            key="slope_slant_asymptote",
            args=[from_sympy(function / symbol)],
        )
    )
    ctx.result.add(
        Step(
            left=node,
            right=None,
            key="intercept_slant_asymptote",
            args=[from_sympy(function - slope * symbol)],
        )
    )
    ctx.result.add(
        Step(
            left=node,
            right=line,
            key="def_slant_asymptote",
            args=[line, from_sympy(slope), from_sympy(intercept)],
        )
    )
    return line


def axis_of_symmetry(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Ось симметрии параболы: ``x = −b/(2a)`` (шаг ``find_axis``)."""
    del args
    expression_node = _expression_of(node)
    if len(ctx.variables) != 1:
        raise SolveError("ось симметрии: поддерживается одна переменная")
    var = ctx.variables[0]
    symbol = sympy.Symbol(var)
    function = to_sympy(expression_node)
    try:
        polynomial = sympy.Poly(function, symbol)
    except sympy.PolynomialError as error:
        raise SolveError("ось симметрии — у квадратичной функции") from error
    if polynomial.degree() != 2:
        raise SolveError("ось симметрии — у квадратичной функции")
    a = polynomial.coeff_monomial(symbol**2)
    b = polynomial.coeff_monomial(symbol)
    answer = CoreNode.node(
        T.EQUALS, CoreNode.variable(var), from_sympy(sympy.simplify(-b / (2 * a)))
    )
    ctx.result.add(Step(left=node, right=answer, key="find_axis"))
    return answer


def intercept_form(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Квадратичную функцию — в форму по корням ``a(x−r₁)(x−r₂)``.

    Шаг ``intercept_form``; ответ — разложение на множители.
    """
    del args
    expression_node = _expression_of(node)
    if len(ctx.variables) != 1:
        raise SolveError("форма по корням: поддерживается одна переменная")
    symbol = sympy.Symbol(ctx.variables[0])
    function = to_sympy(expression_node)
    try:
        polynomial = sympy.Poly(function, symbol)
    except sympy.PolynomialError as error:
        raise SolveError("форма по корням — у квадратичной функции") from error
    if polynomial.degree() != 2:
        raise SolveError("форма по корням — у квадратичной функции")
    result = from_sympy(sympy.factor(function))
    ctx.result.add(Step(left=node, right=result, key="intercept_form"))
    return result


def slope_intercept(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Записать линейное уравнение в виде ``y = kx + b`` и назвать ``k`` и ``b``.

    Из двух неизвестных зависимой считается ``y`` (иначе вторая), независимой —
    оставшаяся. Шаги ``rewrite_in_slope_intercept_form`` и
    ``slope_and_y_intercept`` (угловой коэффициент и пересечение с осью).
    """
    del args
    if node.type is not T.EQUALS or len(node.children) != 2:
        raise SolveError("угловой коэффициент — у линейного уравнения")
    if len(ctx.variables) != 2:
        raise SolveError("нужны две переменные: независимая и зависимая")
    dependent = "y" if "y" in ctx.variables else ctx.variables[1]
    independent = next(name for name in ctx.variables if name != dependent)
    dependent_symbol = sympy.Symbol(dependent)
    independent_symbol = sympy.Symbol(independent)

    lhs, rhs = to_sympy(node.children[0]), to_sympy(node.children[1])
    found = sympy.solve(sympy.Eq(lhs, rhs), dependent_symbol)
    if len(found) != 1:
        raise SolveError("не удалось выразить зависимую переменную")
    expression = sympy.simplify(found[0])
    try:
        polynomial = sympy.Poly(expression, independent_symbol)
    except sympy.PolynomialError as error:
        raise SolveError("уравнение не линейное") from error
    if polynomial.degree() > 1:
        raise SolveError("уравнение не линейное")
    slope = polynomial.coeff_monomial(independent_symbol)
    intercept = polynomial.coeff_monomial(1)

    answer = CoreNode.node(T.EQUALS, CoreNode.variable(dependent), from_sympy(expression))
    ctx.result.add(Step(left=node, right=None, key="rewrite_in_slope_intercept_form"))
    ctx.result.add(
        Step(
            left=node,
            right=None,
            key="identify_y_intercept_as_const_term",
            args=[CoreNode.variable(dependent)],
        )
    )
    ctx.result.add(
        Step(
            left=node,
            right=answer,
            key="slope_and_y_intercept",
            args=[
                from_sympy(slope),
                CoreNode.variable(dependent),
                from_sympy(intercept),
            ],
        )
    )
    return answer


def value_range(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Область значений функции — множество её значений на прямой.

    Считает sympy (``function_range``): для непрерывной функции это промежуток
    или объединение промежутков, ответ отдаётся узлом-множеством.
    """
    del args
    expression_node = _expression_of(node)
    if len(ctx.variables) != 1:
        raise SolveError("область значений: поддерживается одна переменная")
    symbol = sympy.Symbol(ctx.variables[0])
    function = to_sympy(expression_node)
    try:
        values = function_range(function, symbol, sympy.S.Reals)
    except (NotImplementedError, TypeError, ValueError) as error:
        raise SolveError("область значений не определена") from error
    result = from_sympy(values)
    ctx.result.add(Step(left=node, right=result, key="graph_rt_info_range"))
    return result


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
    ctx.result.add(Step(left=node, right=None, key="def_vert_asymptote"))
    if vertical:
        ctx.result.add(Step(left=node, right=None, key="find_vert_asymptote"))
    else:
        ctx.result.add(Step(left=node, right=None, key="no_vert_asymptote"))

    plus = sympy.limit(function, symbol, sympy.oo)
    minus = sympy.limit(function, symbol, -sympy.oo)
    horizontals = [value for value in (plus, minus) if value.is_finite]
    ctx.result.add(Step(left=node, right=None, key="def_hor_asymptote"))
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


def rationalize(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Убрать иррациональность из знаменателя."""
    del args
    return _apply_side(node, ctx, "rationalize_roots", sympy.radsimp)


def polar(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Записать комплексное число в полярной форме ``r(cos φ + i sin φ)``."""
    del args
    value = to_sympy(node)
    if value.is_number is not True or value.is_real is True:
        raise SolveError("полярная форма — у комплексного числа")
    radius = from_sympy(sympy.simplify(sympy.Abs(value)))
    angle = from_sympy(sympy.simplify(sympy.arg(value)))
    imaginary = CoreNode.constant("i")
    trig = CoreNode.node(
        T.ADD,
        CoreNode.node(T.COS, angle),
        CoreNode.node(T.MULTIPLY_IMPLICIT, imaginary, CoreNode.node(T.SIN, angle)),
    )
    result = CoreNode.node(T.MULTIPLY_IMPLICIT, radius, CoreNode.node(T.BRACKET, trig))
    ctx.result.add(Step(left=node, right=None, key="complex_calculate_polar"))
    ctx.result.add(Step(left=node, right=result, key="write_polar_form"))
    return result


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
    value = _expression_value(node, "градусы берутся у угла или числа")
    degrees = sympy.simplify(value * 180 / sympy.pi)
    result = CoreNode.node(T.DEGREE, from_sympy(degrees))
    ctx.result.add(Step(left=node, right=result, key="rewrite_deg"))
    return result


def to_radians(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Градусы — в радианы (узел ``DEGREE`` переводится в число)."""
    del args
    value = _expression_value(node, "радианы берутся у угла или числа")
    result = from_sympy(sympy.simplify(value))
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
    # Вид кривой сообщается без подробностей (уравнение в каноническом виде,
    # радиус, центр): `conics_classify_*` требуют их аргументами, а посчитать
    # их решатель пока не умеет — шаг показывал бы «…в виде ARG1…ARG2».
    # Поэтому берём варианты тех же ключей без аргументов.
    if discriminant < 0:
        key = (
            "conics_represents_circle"
            if left == right and cross == 0
            else "conics_represents_ellipse"
        )
    elif discriminant == 0:
        key = "conics_represents_parabola"
    else:
        key = "conics_represents_hyperbola"
    ctx.result.add(Step(left=node, right=None, key="conics_identify"))
    ctx.result.add(Step(left=node, right=None, key="conics_identify_disc"))
    ctx.result.add(Step(left=node, right=None, key=key))
    return node


COMMANDS: dict[str, Command] = {
    "approximate": approximate,
    "axis_of_symmetry": axis_of_symmetry,
    "intercept_form": intercept_form,
    "x_intercept_count": x_intercept_count,
    "slant_asymptote": slant_asymptote,
    "complex_power": complex_power,
    "complex_roots": complex_roots,
    "complex_polar_multiply": complex_polar_multiply,
    "complex_polar_divide": complex_polar_divide,
    "conic_details": conic_details,
    "gcd": gcd,
    "lcm": lcm,
    "mod": modulo,
    "prime_factorization": prime_factorization,
    "round_place": round_place,
    "explicit_formula": explicit_formula,
    "factor": factor,
    "expand": expand,
    "simplify": simplify,
    "domain": domain,
    "evaluate_function": evaluate_function,
    "restrictions": restrictions,
    "area": area,
    "conic": conic,
    "convergence": convergence,
    "diff_eq": diff_eq,
    "to_degrees": to_degrees,
    "to_radians": to_radians,
    "vertex": vertex,
    "rationalize": rationalize,
    "polar": polar,
    "asymptotes": asymptotes,
    "even_odd": even_odd,
    "extrema": extrema,
    "extrema_on_interval": extrema_on_interval,
    "inflection": inflection,
    "inequality_on_interval": inequality_on_interval,
    "intercepts": intercepts,
    "inverse_function": inverse_function,
    "nth_derivative": nth_derivative,
    "partial_fractions": partial_fractions,
    "piecewise_value": piecewise_value,
    "periodic_to_frac": periodic_to_frac,
    "range": value_range,
    "alt_test": alt_test,
    "integral_test": integral_test,
    "direct_comparison_test": direct_comparison_test,
    "limit_comparison_test": limit_comparison_test,
    "geom_series_test": geom_series_test,
    "pseries_test": pseries_test,
    "radius_of_convergence": radius_of_convergence,
    "ratio_test": ratio_test,
    "root_test": root_test,
    "nth_term_test": nth_term_test,
    "sequence_convergence": sequence_convergence,
    "slope_intercept": slope_intercept,
    "system_check": system_check,
    "solve_param": solve_param,
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
    "approximate",
    "area",
    "asymptotes",
    "axis_of_symmetry",
    "complex_polar_divide",
    "complex_polar_multiply",
    "complex_power",
    "complex_roots",
    "conic",
    "convergence",
    "diff_eq",
    "domain",
    "evaluate_function",
    "even_odd",
    "expand",
    "extrema",
    "extrema_on_interval",
    "factor",
    "gcd",
    "geom_series_test",
    "inequality_on_interval",
    "inflection",
    "intercept_form",
    "intercepts",
    "inverse_function",
    "lcm",
    "limit_comparison_test",
    "modulo",
    "nth_derivative",
    "nth_term_test",
    "partial_fractions",
    "periodic_to_frac",
    "piecewise_value",
    "polar",
    "prime_factorization",
    "prove",
    "pseries_test",
    "radius_of_convergence",
    "ratio_test",
    "rationalize",
    "restrictions",
    "root_test",
    "round_place",
    "simplify",
    "slope_intercept",
    "solve_param",
    "substitute",
    "system_check",
    "to_degrees",
    "to_fraction",
    "to_mixed",
    "to_percent",
    "to_radians",
    "to_sci",
    "value_range",
    "vertex",
    "x_intercept_count",
]
