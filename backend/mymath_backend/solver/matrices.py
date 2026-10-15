"""Определители матриц.

Модуль зарегистрирован на ``DETERMINANT2``, ``DETERMINANT3``,
``DETERMINANT3_SARRUS``, ``DETERMINANT4``, ``DETERMINANT5`` и общий
``DETERMINANT``. Дети — элементы в порядке «по строкам» (``row = i / n``,
``col = i % n``); это видно в нативном решателе (``c/a/a/l/h/v/f.java``).
Допустимы и строки ``MATRIX_ROW``: их элементы разворачиваются в тот же
порядок.

Определитель считается разложением по первой строке (для 2×2 и 3×3 это
совпадает с формулой и правилом Саррюса). Элементы должны быть числами.

Ключи шагов: ``det2_calc`` (2×2), ``det3_sarrus_eval`` (3×3),
``det3_cofactor_eval`` (4×4, 5×5).
"""

from __future__ import annotations

from fractions import Fraction
from math import isqrt

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .arithmetic import as_fraction, format_number
from .base import SolveContext, Step, route, solver_for

_DETERMINANTS = (
    T.DETERMINANT,
    T.DETERMINANT2,
    T.DETERMINANT3,
    T.DETERMINANT3_SARRUS,
    T.DETERMINANT4,
    T.DETERMINANT5,
)

_MAX_SIZE = 6


def _elements(node: CoreNode) -> list[CoreNode]:
    """Плоский список элементов: строки ``MATRIX_ROW`` разворачиваются."""
    if node.children and all(child.type is T.MATRIX_ROW for child in node.children):
        return [element for row in node.children for element in row.children]
    return list(node.children)


def _determinant(values: list[Fraction], size: int) -> Fraction:
    """Определитель ``size × size`` разложением по первой строке."""
    if size == 1:
        return values[0]
    total = Fraction(0)
    for column in range(size):
        minor = [
            values[row * size + col]
            for row in range(1, size)
            for col in range(size)
            if col != column
        ]
        total += (1 if column % 2 == 0 else -1) * values[column] * _determinant(minor, size - 1)
    return total


def _key_for(size: int) -> str:
    if size == 2:
        return "det2_calc"
    if size == 3:
        return "det3_sarrus_eval"
    return "det3_cofactor_eval"


@solver_for(*_DETERMINANTS)
def solve_determinant(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить определитель квадратной числовой матрицы."""
    elements = _elements(node)
    size = isqrt(len(elements))
    ctx.require(
        size > 0 and size * size == len(elements),
        "определитель определён только для квадратной матрицы",
    )
    ctx.require(size <= _MAX_SIZE, "матрица слишком большая")
    values = [as_fraction(route(element, ctx)) for element in elements]

    result = CoreNode.constant(format_number(_determinant(values, size)))
    ctx.result.add(Step(left=node, right=result, key=_key_for(size)))
    return result


__all__ = [
    "solve_determinant",
]
