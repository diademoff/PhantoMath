"""Тригонометрия: единицы угла и точные значения функций.

Модуль обслуживает прямые тригонометрические функции (``SIN``, ``COS``,
``TAN``, ``COT``, ``SEC``, ``CSC``) и узлы-обёртки единиц угла
(``DEGREE``, ``RADIAN``).

Единица угла берётся из обёртки аргумента: ``sin(30°)`` -- градусы (узел
``DEGREE`` вокруг ``30``), ``sin(π/6)`` -- радианы. Аргумент без обёртки
считается радианной мерой -- так же, как в математической записи.

Точное значение считает sympy: ``sin(π/6) = 1/2``, ``cos(30°) = √3/2``,
``tan(π/4) = 1``. Если точного значения нет (``sin(1)``, ``sin(x)``), узел
возвращается без изменений: символьное выражение сохраняется, как и у
корней (``√2``).

Значения, где функция не определена (``tan(π/2)``, ``cot(0)``), -- ошибка
решения с ключом ``trig_err_undef``, а не молчаливый пропуск.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step, solver_for
from .sympy_bridge import from_sympy, to_sympy

_KEY_TABLE = "trig_table_calc"
_KEY_UNDEF = "trig_err_undef"

# Прямые функции: тип узла -> имя функции sympy.
_DIRECT: dict[T, str] = {
    T.SIN: "sin",
    T.COS: "cos",
    T.TAN: "tan",
    T.COT: "cot",
    T.SEC: "sec",
    T.CSC: "csc",
}

# Если эти функции остались в результате sympy, точного значения не нашлось.
_UNRESOLVED = tuple(getattr(sympy, name) for name in _DIRECT.values())

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


@solver_for(*_DIRECT)
def solve_direct(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить точное значение прямой функции или оставить узел.

    Радианную меру аргумента даёт :func:`to_sympy`: он разворачивает
    ``DEGREE``/``RADIAN`` и по умолчанию трактует угол как радианы.
    """
    if len(node.children) != 1:
        raise SolveError("тригонометрическая функция должна иметь один аргумент")

    radians = to_sympy(node.children[0])
    value = getattr(sympy, _DIRECT[node.type])(radians)

    if value in _UNDEFINED:
        raise SolveError(
            f"значение функции {node.type.value.lower()} не определено",
            explanation_key=_KEY_UNDEF,
        )
    if value.has(*_UNRESOLVED):
        # Точного значения нет -- символьный узел остаётся как есть.
        return node

    result = from_sympy(value)
    ctx.result.add(Step(left=node, right=result, key=_KEY_TABLE))
    return result


__all__ = [
    "solve_angle_unit",
    "solve_direct",
]
