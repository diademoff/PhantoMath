"""Тригонометрия: единицы угла, значения и упрощения.

Модуль обслуживает прямое, обратное и гиперболическое семейства функций
Решатель (``SIN`` … ``ACSCH``) и узлы-обёртки единиц угла
(``DEGREE``, ``RADIAN``).

Единица угла берётся из обёртки аргумента прямой функции: ``sin(30°)`` --
градусы (узел ``DEGREE`` вокруг ``30``), ``sin(π/6)`` -- радианы. Аргумент
без обёртки считается радианной мерой -- так же, как в математической
записи. Обратные функции принимают число (отношение) и возвращают угол в
радианах, кратным ``π``: ``arcsin(1/2) = π/6``.

Обработка функции идёт цепочкой, и каждый шаг даёт своё пояснение:

1. **чётность/нечётность** -- ``sin(-x) = -sin(x)``, ``cos(-x) = cos(x)``;
2. **периодичность** -- числовой угол записывается суммой с периодом
   (``write_as_sum_trig``) и сворачивается по периоду (``using_sim``):
   ``sin(390°) = sin(30°)``, ``sin(13π/6) = sin(π/6)``;
3. **значение** -- точное значение по таблице: ``sin(π/6) = 1/2``
   (``trig_table_first``).

У обратных функций табличное значение -- сразу один шаг аркуса
(``trig_arcus_first`` для первой четверти, ``trig_arcus_fourth`` для
отрицательного угла, ``trig_arcus_second`` для второй).

Если точного значения нет (``sin(1)``, ``sin(x)``), узел возвращается без
изменений: символьное выражение сохраняется, как и у корней (``√2``).

Неопределённые значения (``tan(π/2)``, ``cot(0)``, ``acosh(0)``) -- ошибка
решения с ключом ``trig_err_undef``, а не молчаливый пропуск.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, SolveResult, Step, fold_semantically, solver_for
from .sympy_bridge import from_sympy, to_sympy

# Ключи шагов.
_KEY_TABLE = "trig_table_first"
_KEY_CALC = "trig_func_calc"
_KEY_UNDEF = "trig_err_undef"
_KEY_SUM = "write_as_sum_trig"
_KEY_SIM = "using_sim"

# Заголовок карточки: у решателя каждый тригонометрический шаг — отдельный
# шаг с заголовком «Вычислите выражения».
_HEADER = "calculate_expressions"

# Семейства функций: тип узла -> имя функции sympy.
_DIRECT: dict[T, str] = {
    T.SIN: "sin",
    T.COS: "cos",
    T.TAN: "tan",
    T.COT: "cot",
    T.SEC: "sec",
    T.CSC: "csc",
}
_INVERSE: dict[T, str] = {
    T.ASIN: "asin",
    T.ACOS: "acos",
    T.ATAN: "atan",
    T.ACOT: "acot",
    T.ASEC: "asec",
    T.ACSC: "acsc",
}
_HYPERBOLIC: dict[T, str] = {
    T.SINH: "sinh",
    T.COSH: "cosh",
    T.TANH: "tanh",
    T.COTH: "coth",
    T.SECH: "sech",
    T.CSCH: "csch",
}
_INVERSE_HYPERBOLIC: dict[T, str] = {
    T.ASINH: "asinh",
    T.ACOSH: "acosh",
    T.ATANH: "atanh",
    T.ACOTH: "acoth",
    T.ASECH: "asech",
    T.ACSCH: "acsch",
}

_ALL: dict[T, str] = {
    **_DIRECT,
    **_INVERSE,
    **_HYPERBOLIC,
    **_INVERSE_HYPERBOLIC,
}
_STEP_KEY: dict[T, str] = {
    **{node_type: _KEY_TABLE for node_type in _DIRECT},
    **{node_type: _KEY_CALC for node_type in {**_INVERSE, **_HYPERBOLIC, **_INVERSE_HYPERBOLIC}},
}

# Чётность: ключ пояснения есть только у функций с правилом чётности.
# Отсутствие в таблице означает «правило не применяем» (например, ``cos``
# нечётной не бывает, а``acos`` не является ни чётной, ни нечётной).
_PARITY_KEY: dict[T, str] = {
    T.SIN: "trig_neg_sin",
    T.COS: "trig_neg_cos",
    T.TAN: "trig_neg_tan",
    T.COT: "trig_neg_cot",
    T.SEC: "trig_neg_sec",
    T.CSC: "trig_neg_csc",
    T.SINH: "trig_hyp_neg_sinh",
    T.COSH: "trig_hyp_neg_cosh",
    T.TANH: "trig_hyp_neg_tanh",
    T.COTH: "trig_hyp_neg_coth",
    T.SECH: "trig_hyp_neg_sech",
    T.CSCH: "trig_hyp_neg_csch",
    T.ASIN: "trig_neg",
    T.ATAN: "trig_neg",
    T.ACSC: "trig_neg",
    T.ASINH: "trig_hyp_neg",
    T.ATANH: "trig_hyp_neg",
    T.ACSCH: "trig_hyp_neg",
}
# Нечётные функции: при выносе минуса знак меняется. Остальные из таблицы —
# чётные.
_ODD: frozenset[T] = frozenset(
    {
        T.SIN,
        T.TAN,
        T.COT,
        T.CSC,
        T.SINH,
        T.TANH,
        T.COTH,
        T.CSCH,
        T.ASIN,
        T.ATAN,
        T.ACSC,
        T.ASINH,
        T.ATANH,
        T.ACSCH,
    }
)
# Период как доля ``π``: у тангенса и котангенса он вдвое короче.
_PERIOD_FACTOR: dict[T, int] = {
    T.SIN: 2,
    T.COS: 2,
    T.TAN: 1,
    T.COT: 1,
    T.SEC: 2,
    T.CSC: 2,
}

# Если эти функции остались в результате sympy, точного значения не нашлось.
_UNRESOLVED = tuple(getattr(sympy, name) for name in _ALL.values())

# Значения, при которых функция не определена.
_UNDEFINED = (sympy.zoo, sympy.nan, sympy.oo, -sympy.oo)

# Потолок сложности точного значения: у табличных углов (30°, 45°, 60°, 15°)
# это несколько операций, у 3° — десятки вложенных радикалов. Вторые
# Решатель показывает десятичным приближением.
_TABLE_OPS = 12


def pythagorean_identity(node: CoreNode, ctx: SolveContext) -> CoreNode | None:
    """Применить sin²(u) + cos²(u) = 1 только при одинаковом аргументе."""
    if node.type is not T.ADD or len(node.children) != 2:
        return None
    functions: dict[T, CoreNode] = {}
    for term in node.children:
        while term.type is T.BRACKET and len(term.children) == 1:
            term = term.children[0]
        if term.type is not T.POWER or len(term.children) != 2:
            return None
        function, exponent = term.children
        if function.type not in (T.SIN, T.COS) or len(function.children) != 1:
            return None
        if exponent.type is not T.CONSTANT or exponent.value != "2":
            return None
        functions[function.type] = function
    if set(functions) != {T.SIN, T.COS}:
        return None
    sine, cosine = functions[T.SIN], functions[T.COS]
    argument = to_sympy(sine.children[0])
    if argument.has(sympy.zoo, sympy.nan, sympy.oo, -sympy.oo):
        return None
    if argument != to_sympy(cosine.children[0]):
        return None
    angle = CoreNode.variable("u")
    generic_sine = CoreNode.node(T.SIN, angle)
    generic_cosine = CoreNode.node(T.COS, angle)
    generic = CoreNode.node(
        T.EQUALS,
        CoreNode.node(
            T.ADD,
            CoreNode.node(T.POWER, generic_sine, CoreNode.constant("2")),
            CoreNode.node(T.POWER, generic_cosine, CoreNode.constant("2")),
        ),
        CoreNode.constant("1"),
    )
    result = CoreNode.constant("1")
    ctx.step(
        node,
        result,
        "substitute_pythagorean_identity",
        sine,
        generic_sine,
        cosine,
        generic_cosine,
        generic,
    )
    return result


@solver_for(T.DEGREE, T.RADIAN)
def solve_angle_unit(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Единица угла -- обёртка над значением угла.

    Узел не преобразуется: он несёт меру угла (``DEGREE`` -- градусы,
    ``RADIAN`` -- радианы) и нужен тригонометрической функции, а не
    арифметике. Обёртка остаётся в дереве, чтобы ответ читался как ``30°``.

    Модуль нужен только затем, чтобы обёртка не считалась «нереализованным
    типом», когда её встретит маршрутизация.
    """
    _ = ctx
    return node


_DMS_UNITS: dict[T, tuple[tuple[str, tuple[int, int]], ...]] = {
    T.DEGREE_MINUTE: (("deg", (1, 1)), ("min", (1, 60))),
    T.DEGREE_MINUTE_SECOND: (("deg", (1, 1)), ("min", (1, 60)), ("sec", (1, 3600))),
    T.DEGREE_SECOND: (("deg", (1, 1)), ("sec", (1, 3600))),
    T.MINUTE_SECOND: (("min", (1, 60)), ("sec", (1, 3600))),
    T.MINUTE: (("min", (1, 60)),),
    T.SECOND: (("sec", (1, 3600)),),
}


@solver_for(*_DMS_UNITS)
def solve_dms_angle(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Градусы-минуты-секунды в десятичные градусы.

    Дети — компоненты угла в порядке, заданном типом узла (градусы, минуты,
    секунды); шаг ``rewrite_deg``. Ответ остаётся в градусах (узел ``DEGREE``).
    """
    units = _DMS_UNITS[node.type]
    ctx.require(len(node.children) == len(units), "неполная запись угла в градусах")
    total = sympy.Integer(0)
    for (_, (numerator, denominator)), child in zip(units, node.children, strict=True):
        total += to_sympy(child) * sympy.Rational(numerator, denominator)
    result = CoreNode.node(T.DEGREE, from_sympy(sympy.simplify(total)))
    ctx.result.add(Step(left=node, right=result, key="rewrite_deg"))
    return result


@solver_for(*_ALL)
def solve_function(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить функцию: чётность, периодичность, затем значение."""
    if len(node.children) != 1:
        raise SolveError("тригонометрическая функция должна иметь один аргумент")
    if node.type in _DIRECT and ctx.depth == 0 and not ctx.result:
        # Решатель подписывает способ вычисления значения этой карточкой.
        ctx.result.header = "trig_func_calc"
    return _evaluate(node, ctx)


def _evaluate(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Пошагово упростить и вычислить функцию."""
    # 1. Точное значение обратной функции — сразу таблица (аркус
    #    смотрит на четверть ответа), без отдельного шага чётности.
    if node.type in _INVERSE:
        exact = _exact_inverse(node)
        if exact is not None:
            key = _arcus_key(exact)
            result = _signed(exact)
            ctx.result.add_group(_HEADER, Step(node, result, key, args=[node]))
            return result

    # 2. Чётность/нечётность: вынести знак аргумента.
    if node.type in _PARITY_KEY:
        positive = _positive_argument(node.children[0])
        if positive is not None:
            rewritten = CoreNode.node(node.type, positive)
            result = _evaluate(rewritten, ctx)
            if node.type in _ODD:
                result = CoreNode.node(T.NEGATIVE, result)
            ctx.result.add(Step(left=node, right=result, key=_PARITY_KEY[node.type]))
            return result

    # 3. Периодичность: угол = наименьший положительный + период.
    if node.type in _PERIOD_FACTOR:
        reduced = _period_rows(node, ctx)
        if reduced is not None:
            return _evaluate(reduced, ctx)

    # 4. Значение.
    return _value(node, ctx)


def _exact_inverse(node: CoreNode) -> sympy.Expr | None:
    """Точное табличное значение обратной функции или ``None``.

    Аргумент не сворачивается: иначе ``asin(-1/2)`` дал бы лишний шаг
    перевода ``-1/2`` в число, которого у решателя нет.
    """
    value = getattr(sympy, _ALL[node.type])(to_sympy(node.children[0]))
    if value in _UNDEFINED or value.has(sympy.I) or value.has(*_UNRESOLVED):
        return None
    return value


def _signed(value: sympy.Expr) -> CoreNode:
    """Узел значения: отрицательный угол остаётся ``-π/6``, а не ``(-π)/6``."""
    if value.could_extract_minus_sign():
        return CoreNode.node(T.NEGATIVE, from_sympy(-value))
    return from_sympy(value)


def _arcus_key(value: sympy.Expr) -> str:
    """Ключ аркуса по четверти найденного угла.

    Решатель называет шаг по четверти: ``π/6`` — первый, ``-π/6`` —
    четвёртый, ``2π/3`` — второй.
    """
    if value.could_extract_minus_sign():
        return "trig_arcus_fourth"
    if value <= sympy.pi / 2:
        return "trig_arcus_first"
    return "trig_arcus_second"


def _period_rows(node: CoreNode, ctx: SolveContext) -> CoreNode | None:
    """Записать угол как сумму и снять период.

    ``sin 390°``: ``sin(30° + 360°)`` (``write_as_sum_trig``), затем
    ``sin(t + 360°k) = sin t`` (``using_sim``) даёт ``sin 30°``. Каждый шаг —
    отдельная карточка.
    """
    reduction = _reduce_angle(node)
    if reduction is None:
        return None
    reduced_argument, shift, shift_value = reduction
    original = node.children[0]
    argument_type = T.ADD if original.type is T.DEGREE else T.ADD_SUBTRACT
    rewritten_argument = CoreNode.node(argument_type, reduced_argument, shift)
    rewritten = CoreNode.node(node.type, rewritten_argument)
    ctx.result.add_group(
        _HEADER,
        Step(left=node, right=rewritten, key=_KEY_SUM, args=[original]),
    )

    parameter = CoreNode.variable("k")
    angle = CoreNode.variable("t")
    if original.type is T.DEGREE:
        period = CoreNode.node(T.MULTIPLY, parameter, shift)
    else:
        period = from_sympy(shift_value * sympy.Symbol("k"))
    identity = CoreNode.node(
        T.EQUALS,
        CoreNode.node(node.type, CoreNode.node(argument_type, angle, period)),
        CoreNode.node(node.type, angle),
    )
    member = CoreNode.node(T.ELEMENT_OF, parameter, CoreNode.variable("ℤ"))
    simplified = CoreNode.node(node.type, reduced_argument)
    ctx.result.add_group(
        _HEADER,
        Step(
            left=rewritten,
            right=simplified,
            key=_KEY_SIM,
            args=[CoreNode.node(T.LIST, identity, member)],
        ),
    )
    return simplified


def _value(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Точное значение функции или сам узел, если значения нет.

    Аргумент сворачивается заранее: ``sin(1+1)`` даёт шаг ``1+1 = 2`` и
    ответ ``sin(2)``. Чётность и периодичность при этом уже отработали —
    сворачивание здесь не мешает им вынести знак или привести угол.
    """
    argument = fold_semantically(node.children[0], ctx)
    node = CoreNode.node(node.type, argument)
    approximate = _approximate_angle(node, argument, ctx)
    if approximate is not None:
        return approximate
    radians = to_sympy(argument)
    value = getattr(sympy, _ALL[node.type])(radians)

    if value in _UNDEFINED or value.has(sympy.I):
        # Комплексное значение -- признак выхода из области определения.
        raise SolveError(
            f"значение функции {node.type.value.lower()} не определено",
            explanation_key=_KEY_UNDEF,
        )
    if value.has(*_UNRESOLVED):
        # Точного значения нет -- символьный узел остаётся со свёрнутым
        # аргументом.
        return node

    result = from_sympy(value)
    ctx.result.add_group(_HEADER, Step(left=node, right=result, key=_STEP_KEY[node.type]))
    return result


def _approximate_angle(node: CoreNode, argument: CoreNode, ctx: SolveContext) -> CoreNode | None:
    """``sin 2°`` без табличного значения — десятичное приближение.

    Ответ ``≈ 0.0348995`` (6 значащих цифр) с карточкой
    ``calculate_short``. Табличные углы (30°, 45°, 60°, …) сюда не попадают:
    у них есть короткое точное значение. Радианные углы остаются как были.
    """
    if node.type not in _DIRECT or argument.type is not T.DEGREE:
        return None
    if len(argument.children) != 1 or argument.children[0].type is not T.CONSTANT:
        return None
    try:
        degrees = sympy.Rational(str(argument.children[0].value))
    except (TypeError, ValueError):
        return None
    radians = degrees * sympy.pi / 180
    exact = getattr(sympy, _ALL[node.type])(radians)
    if exact in _UNDEFINED or exact.has(sympy.I):
        return None
    if not exact.has(*_UNRESOLVED) and exact.count_ops() <= _TABLE_OPS:
        return None  # табличный угол: точное значение короткое
    text = f"{float(sympy.N(exact, 10)):.6g}"
    result = CoreNode.node(T.APPROXIMATE_SIGN, CoreNode.constant(text))
    ctx.result.add_group("calculate_short", Step(left=node, right=result, key="calculate"))
    if ctx.depth == 0:
        ctx.result.header = "calculate_short"
    return result


def _positive_argument(argument: CoreNode) -> CoreNode | None:
    """Аргумент без ведущего минуса или ``None``, если минуса нет.

    Минус может стоять снаружи обёртки единицы угла (``-30°``) или внутри
    (``(-30)°``); оба случая дают один и тот же положительный угол.
    """
    wrapper: T | None = None
    inner = argument
    if argument.type in (T.DEGREE, T.RADIAN) and len(argument.children) == 1:
        wrapper = argument.type
        inner = argument.children[0]

    if inner.type is T.NEGATIVE and len(inner.children) == 1:
        positive = inner.children[0]
    elif inner.type is T.CONSTANT and inner.value and inner.value.strip().startswith("-"):
        positive = CoreNode.constant(inner.value.strip()[1:])
    elif (
        inner.type is T.FRACTION
        and len(inner.children) == 2
        and inner.children[0].type is T.NEGATIVE
        and len(inner.children[0].children) == 1
    ):
        # ``-π/3`` приходит из sympy как FRACTION(-π, 3): минус стоит в
        # числителе, но это тот же отрицательный угол -- сначала чётность.
        positive = CoreNode.node(T.FRACTION, inner.children[0].children[0], inner.children[1])
    else:
        return None

    if wrapper is None:
        return positive
    return CoreNode.node(wrapper, positive)


def _reduce_angle(node: CoreNode) -> tuple[CoreNode, CoreNode, sympy.Expr] | None:
    """Привести числовой угол к котерминальному или ``None``.

    Возвращает ``(наименьший угол, период, значение периода)``: угол
    раскладывается как ``наименьший + период``. Работает только с точными
    числами: градусы -- целые и дробные, радианы -- рациональные кратные
    ``π``. Символьный аргумент остается как есть.
    """
    argument = node.children[0]
    factor = _PERIOD_FACTOR[node.type]

    if argument.type is T.DEGREE and len(argument.children) == 1:
        value = to_sympy(argument.children[0])
        if not value.is_rational:
            return None
        full_turn = 180 * factor
        reduced = sympy.Mod(value, full_turn)
        if reduced == value:
            return None
        shift = value - reduced
        return (
            CoreNode.node(T.DEGREE, from_sympy(reduced)),
            CoreNode.node(T.DEGREE, from_sympy(shift)),
            shift,
        )

    inner = argument.children[0] if argument.type is T.RADIAN else argument
    value = to_sympy(inner)
    if value == 0:
        return None
    coefficient = value / sympy.pi
    if not coefficient.is_rational:
        return None
    reduced_coefficient = sympy.Mod(coefficient, factor)
    if reduced_coefficient == coefficient:
        return None
    shift_coefficient = coefficient - reduced_coefficient
    reduced_inner = from_sympy(reduced_coefficient * sympy.pi)
    shift_inner = from_sympy(shift_coefficient * sympy.pi)
    if argument.type is T.RADIAN:
        return (
            CoreNode.node(T.RADIAN, reduced_inner),
            CoreNode.node(T.RADIAN, shift_inner),
            shift_coefficient * sympy.pi,
        )
    return reduced_inner, shift_inner, shift_coefficient * sympy.pi


def angle_methods(node: CoreNode, command: str) -> list[SolveResult] | None:
    """Способы для ``to_degrees``/``to_radians``.

    Первый способ — перевод по формуле, второй и третий — положительный и
    отрицательный котерминальные углы (прибавить/вычесть полный оборот).
    ``None`` — вход не угол, команда не наша или представление незнакомо;
    тогда работает обычный обработчик команды.
    """
    if command not in {"to_degrees", "to_radians"}:
        return None
    try:
        value = to_sympy(node)
    except SolveError:
        return None
    if not value.is_number or not value.is_real:
        return None
    if command == "to_degrees":
        conversion = _degrees_rows(node, value)
    else:
        conversion = _radians_rows(node, value)
    if conversion is None:
        return None
    return [
        conversion,
        _coterminal_rows(node, value, positive=True),
        _coterminal_rows(node, value, positive=False),
    ]


def _degrees_rows(node: CoreNode, value: sympy.Expr) -> SolveResult | None:
    """Радианы в градусы: умножить на ``180°/π`` и сократить."""
    degrees = sympy.simplify(value * 180 / sympy.pi)
    converted = CoreNode.node(T.DEGREE, from_sympy(degrees))
    pi = CoreNode.variable("π")
    formula = CoreNode.node(T.FRACTION, CoreNode.node(T.DEGREE, CoreNode.constant("180")), pi)
    product = CoreNode.node(T.MULTIPLY, node, formula)
    result = SolveResult()
    result.header = "rewrite_in_deg"
    result.add_group(
        "trig_convert_formula_msg", Step(node, product, "trig_convert_formula", [formula])
    )
    if node.type in (T.VARIABLE, T.CONSTANT) and node.value == "π":
        result.add_group(
            "trig_convert_formula_msg",
            Step(product, converted, "frac_reduce_out_expr", [pi]),
        )
    elif (
        node.type is T.FRACTION
        and len(node.children) == 2
        and node.children[0].type in (T.VARIABLE, T.CONSTANT)
        and node.children[0].value == "π"
        and node.children[1].type is T.CONSTANT
    ):
        denominator = node.children[1]
        middle = CoreNode.node(
            T.MULTIPLY,
            CoreNode.node(T.FRACTION, CoreNode.constant("1"), denominator),
            CoreNode.node(T.DEGREE, CoreNode.constant("180")),
        )
        result.add_group(
            "trig_convert_formula_msg",
            Step(product, middle, "frac_reduce_out_expr", [pi]),
            Step(middle, converted, "frac_reduce_out_expr", [denominator]),
        )
    else:
        result.add_group("trig_convert_formula_msg", Step(product, converted, "simplify"))
    result.set_solution(converted)
    return result


def _radians_rows(node: CoreNode, value: sympy.Expr) -> SolveResult:
    """Градусы в радианы: умножить на ``π/180°`` и упростить."""
    converted = from_sympy(sympy.simplify(value))
    formula = CoreNode.node(
        T.FRACTION,
        CoreNode.variable("π"),
        CoreNode.node(T.DEGREE, CoreNode.constant("180")),
    )
    product = CoreNode.node(T.MULTIPLY, node, formula)
    result = SolveResult()
    result.header = "rewrite_in_rad"
    result.add_group(
        "trig_convert_deg_to_rad_msg",
        Step(node, product, "trig_convert_deg_to_rad", [formula]),
    )
    result.add_group("simplify_msg", Step(product, converted, "simplify"))
    result.set_solution(converted)
    return result


def _coterminal_rows(node: CoreNode, value: sympy.Expr, *, positive: bool) -> SolveResult:
    """Положительный или отрицательный угол, котерминальный данному."""
    result = SolveResult()
    result.header = "trig_pos_conteminal" if positive else "trig_neg_conteminal"
    parameter = CoreNode.variable("n")
    member = CoreNode.node(T.ELEMENT_OF, parameter, CoreNode.variable("ℤ"))
    degrees = node.type is T.DEGREE
    if degrees:
        unit = CoreNode.node(T.DEGREE, CoreNode.constant("360"))
        period = CoreNode.node(T.MULTIPLY, parameter, unit)
    else:
        unit = CoreNode.node(T.MULTIPLY_IMPLICIT, CoreNode.constant("2"), CoreNode.variable("π"))
        period = CoreNode.node(
            T.MULTIPLY,
            CoreNode.node(T.MULTIPLY, parameter, CoreNode.constant("2")),
            CoreNode.variable("π"),
        )
    combine = T.ADD if positive else T.SUBTRACT
    listed = CoreNode.node(T.LIST, CoreNode.node(combine, node, period), member)
    result.add_group(
        "trig_add_multiple_full" if positive else "trig_sub_multiple_full",
        Step(
            node,
            listed,
            "trig_coter_add_multiple" if positive else "trig_coter_sub_multiple",
            [node, period],
        ),
    )
    with_one = CoreNode.node(combine, node, CoreNode.node(T.MULTIPLY, CoreNode.constant("1"), unit))
    result.add_group(
        "trig_add_rotation_msg" if positive else "trig_sub_rotation_short",
        Step(
            listed,
            with_one,
            "trig_angle_add_coter" if positive else "trig_angle_sub_coter",
            [node],
        ),
    )
    simpler = CoreNode.node(combine, node, unit)
    result.add_group(
        "calculate_short",
        Step(with_one, simpler, "mul_with_one", [CoreNode.constant("1")]),
    )
    final = _coterminal_value(node, value, positive)
    if degrees or (sympy.simplify(value / sympy.pi)).is_Integer:
        _sum_suffix_rows(result, simpler, final, value, positive)
    else:
        result.add_group(
            "calculate_short",
            Step(simpler, final, "calc_sum" if positive else "calc_diff"),
        )
    result.set_solution(final)
    return result


def _coterminal_value(node: CoreNode, value: sympy.Expr, positive: bool) -> CoreNode:
    """Ответ котерминальной карточки: угол ± полный оборот."""
    if node.type is T.DEGREE:
        degrees = sympy.simplify(value * 180 / sympy.pi)
        shifted = sympy.simplify(degrees + 360 if positive else degrees - 360)
        magnitude = CoreNode.node(T.DEGREE, from_sympy(sympy.Abs(shifted)))
        if shifted.could_extract_minus_sign():
            return CoreNode.node(T.NEGATIVE, magnitude)
        return magnitude
    shifted = sympy.simplify(value + 2 * sympy.pi if positive else value - 2 * sympy.pi)
    return _signed(shifted)


def _sum_suffix_rows(
    result: SolveResult, simpler: CoreNode, final: CoreNode, value: sympy.Expr, positive: bool
) -> None:
    """Сложить ``угол ± 2π`` как подобные слагаемые (строки ``sum_suffix``)."""
    coefficient = sympy.simplify(sympy.Abs(value) / sympy.pi)
    if not coefficient.is_Integer or coefficient == 0:
        result.add_group(
            "calculate_short",
            Step(simpler, final, "calc_sum" if positive else "calc_diff"),
        )
        return
    pi = CoreNode.variable("π")
    one = CoreNode.constant("1")
    other = CoreNode.constant("2")
    first = CoreNode.node(T.MULTIPLY, CoreNode.constant(str(coefficient)), pi)
    second = CoreNode.node(T.MULTIPLY, other, pi)
    combine = T.ADD if positive else T.SUBTRACT
    terms = CoreNode.node(combine, first, second)
    total = CoreNode.node(
        combine,
        CoreNode.constant(str(coefficient)),
        other,
    )
    bracket = CoreNode.node(T.MULTIPLY, CoreNode.node(T.BRACKET, total), pi)
    detail = SolveResult()
    detail.add_group("sum_suffix", Step(simpler, terms, "sum_suffix_add_one", [one]))
    if positive:
        detail.add_group("sum_suffix", Step(terms, bracket, "sum_suffix_add_detail"))
        detail.add_group("sum_suffix", Step(bracket, final, "add"))
    else:
        detail.add_group("sum_suffix", Step(terms, bracket, "sum_suffix_sub_detail"))
        remaining = coefficient - 2
        if remaining == -1:
            negative_one = CoreNode.node(T.NEGATIVE, CoreNode.constant("1"))
            minus_pi = CoreNode.node(T.MULTIPLY, negative_one, pi)
            detail.add_group("sum_suffix", Step(bracket, minus_pi, "calc_diff"))
            detail.add_group(
                "sum_suffix",
                Step(minus_pi, final, "sum_suffix_del_neg_one", [negative_one]),
            )
        else:
            detail.add_group("sum_suffix", Step(bracket, final, "calc_diff"))
    result.add_group("sum_suffix", Step(simpler, final, "sum_suffix", subresult=detail))


__all__ = [
    "angle_methods",
    "solve_angle_unit",
    "solve_function",
]
