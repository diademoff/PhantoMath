"""Тригонометрия: единицы угла, значения и упрощения.

Модуль обслуживает прямое, обратное и гиперболическое семейства функций
Photomath (``SIN`` … ``ACSCH``) и узлы-обёртки единиц угла
(``DEGREE``, ``RADIAN``).

Единица угла берётся из обёртки аргумента прямой функции: ``sin(30°)`` --
градусы (узел ``DEGREE`` вокруг ``30``), ``sin(π/6)`` -- радианы. Аргумент
без обёртки считается радианной мерой -- так же, как в математической
записи. Обратные функции принимают число (отношение) и возвращают угол в
радианах, кратным ``π``: ``arcsin(1/2) = π/6``.

Обработка функции идёт цепочкой, и каждый шаг даёт своё пояснение:

1. **чётность/нечётность** -- ``sin(-x) = -sin(x)``, ``cos(-x) = cos(x)``;
2. **периодичность** -- числовой угол приводится к наименьшему
   котерминальному: ``sin(390°) = sin(30°)``, ``sin(13π/6) = sin(π/6)``;
3. **значение** -- точное значение через sympy: ``sin(π/6) = 1/2``.

Если точного значения нет (``sin(1)``, ``sin(x)``), узел возвращается без
изменений: символьное выражение сохраняется, как и у корней (``√2``).

Неопределённые значения (``tan(π/2)``, ``cot(0)``, ``acosh(0)``) -- ошибка
решения с ключом ``trig_err_undef``, а не молчаливый пропуск.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step, fold_semantically, solver_for
from .sympy_bridge import from_sympy, to_sympy

# Ключи шагов.
_KEY_TABLE = "trig_table_calc"
_KEY_CALC = "trig_func_calc"
_KEY_UNDEF = "trig_err_undef"
_KEY_COTERMINAL = "trig_rewrite_coterminal_pos"

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


@solver_for(*_ALL)
def solve_function(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить функцию: чётность, периодичность, затем значение."""
    if len(node.children) != 1:
        raise SolveError("тригонометрическая функция должна иметь один аргумент")
    return _evaluate(node, ctx)


def _evaluate(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Пошагово упростить и вычислить функцию."""
    # 1. Чётность/нечётность: вынести знак аргумента.
    if node.type in _PARITY_KEY:
        positive = _positive_argument(node.children[0])
        if positive is not None:
            rewritten = CoreNode.node(node.type, positive)
            result = _evaluate(rewritten, ctx)
            if node.type in _ODD:
                result = CoreNode.node(T.NEGATIVE, result)
            ctx.result.add(Step(left=node, right=result, key=_PARITY_KEY[node.type]))
            return result

    # 2. Периодичность: наименьший положительный котерминальный угол.
    if node.type in _PERIOD_FACTOR:
        reduced = _reduce_angle(node)
        if reduced is not None:
            ctx.result.add(Step(left=node, right=reduced, key=_KEY_COTERMINAL))
            return _evaluate(reduced, ctx)

    # 3. Значение.
    return _value(node, ctx)


def _value(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Точное значение функции или сам узел, если значения нет.

    Аргумент сворачивается заранее: ``sin(1+1)`` даёт шаг ``1+1 = 2`` и
    ответ ``sin(2)``. Чётность и периодичность при этом уже отработали —
    сворачивание здесь не мешает им вынести знак или привести угол.
    """
    argument = fold_semantically(node.children[0], ctx)
    node = CoreNode.node(node.type, argument)
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
    ctx.result.add(Step(left=node, right=result, key=_STEP_KEY[node.type]))
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
    else:
        return None

    if wrapper is None:
        return positive
    return CoreNode.node(wrapper, positive)


def _reduce_angle(node: CoreNode) -> CoreNode | None:
    """Привести числовой угол к наименьшему котерминальному или ``None``.

    Работает только с точными числами: градусы -- целые и дробные, радианы
    -- рациональные кратные ``π``. Символьный аргумент остается как есть.
    """
    argument = node.children[0]
    factor = _PERIOD_FACTOR[node.type]

    if argument.type is T.DEGREE and len(argument.children) == 1:
        value = to_sympy(argument.children[0])
        if not value.is_rational:
            return None
        reduced = sympy.Mod(value, 180 * factor)
        if reduced == value:
            return None
        return CoreNode.node(node.type, CoreNode.node(T.DEGREE, from_sympy(reduced)))

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
    reduced_inner = from_sympy(reduced_coefficient * sympy.pi)
    if argument.type is T.RADIAN:
        return CoreNode.node(node.type, CoreNode.node(T.RADIAN, reduced_inner))
    return CoreNode.node(node.type, reduced_inner)


__all__ = [
    "solve_angle_unit",
    "solve_function",
]
