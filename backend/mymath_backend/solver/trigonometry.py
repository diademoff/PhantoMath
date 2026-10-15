"""Тригонометрия: единицы угла и точные значения функций.

Модуль обслуживает прямое, обратное и гиперболическое семейства функций
Photomath (``SIN`` … ``ACSCH``) и узлы-обёртки единиц угла
(``DEGREE``, ``RADIAN``).

Единица угла берётся из обёртки аргумента прямой функции: ``sin(30°)`` --
градусы (узел ``DEGREE`` вокруг ``30``), ``sin(π/6)`` -- радианы. Аргумент
без обёртки считается радианной мерой -- так же, как в математической
записи. Обратные функции принимают число (отношение) и возвращают угол в
радианах, кратным ``π``: ``arcsin(1/2) = π/6``.

Точное значение считает sympy: ``sin(π/6) = 1/2``, ``cos(30°) = √3/2``,
``arcsin(1/2) = π/6``, ``sinh(0) = 0``, ``atanh(1/2) = ln(3)/2``. Если
точного значения нет (``sin(1)``, ``sin(x)``), узел возвращается без
изменений: символьное выражение сохраняется, как и у корней (``√2``).

Неопределённые значения (``tan(π/2)``, ``cot(0)``, ``acosh(0)``) -- ошибка
решения с ключом ``trig_err_undef``, а не молчаливый пропуск.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step, solver_for
from .sympy_bridge import from_sympy, to_sympy

# Ключ шага для значений «по таблице» (прямые функции).
_KEY_TABLE = "trig_table_calc"
# Ключ шага для остальных вычислений (обратные, гиперболические).
_KEY_CALC = "trig_func_calc"
_KEY_UNDEF = "trig_err_undef"

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
    """Вычислить точное значение функции или оставить узел.

    Радианную меру аргумента даёт :func:`to_sympy`: он разворачивает
    ``DEGREE``/``RADIAN`` и по умолчанию трактует угол как радианы.
    Обратные функции принимают не угол, а отношение, поэтому к ним
    обёртки не применяются -- ``to_sympy`` просто возвращает число.
    """
    if len(node.children) != 1:
        raise SolveError("тригонометрическая функция должна иметь один аргумент")

    radians = to_sympy(node.children[0])
    value = getattr(sympy, _ALL[node.type])(radians)

    if value in _UNDEFINED or value.has(sympy.I):
        # Комплексное значение -- признак выхода из области определения.
        raise SolveError(
            f"значение функции {node.type.value.lower()} не определено",
            explanation_key=_KEY_UNDEF,
        )
    if value.has(*_UNRESOLVED):
        # Точного значения нет -- символьный узел остаётся как есть.
        return node

    result = from_sympy(value)
    ctx.result.add(Step(left=node, right=result, key=_STEP_KEY[node.type]))
    return result


__all__ = [
    "solve_angle_unit",
    "solve_function",
]
