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

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .arithmetic import as_fraction, format_number
from .base import Command, SolveContext, SolveError, Step, route, solver_for
from .sympy_bridge import from_sympy, to_sympy

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


@solver_for(T.MATRIX, T.MATRIX_ROW)
def solve_matrix(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Матрица как значение не сворачивается: строки и ячейки остаются."""
    _ = ctx
    return node


# ── операции над матрицами (команды) ───────────────────────────────────
# Представление: ``MATRIX``, дети -- строки ``MATRIX_ROW``. Операции --
# команды, как у векторов: второй операнд приходит в ``action.args``.


def _to_matrix(node: CoreNode) -> sympy.Matrix:
    """Узел ``MATRIX`` в символьную матрицу sympy."""
    if node.type is not T.MATRIX or not node.children:
        raise SolveError("ожидалась матрица: узел MATRIX со строками")
    return to_sympy(node)


def _record(node: CoreNode, result: CoreNode, ctx: SolveContext, key: str) -> CoreNode:
    """Добавить шаг и вернуть результат."""
    ctx.result.add(Step(left=node, right=result, key=key))
    return result


def _second_matrix(args: list[CoreNode]) -> sympy.Matrix:
    """Второй операнд команды как матрица."""
    if not args:
        raise SolveError("для операции нужен второй операнд -- матрица")
    return _to_matrix(args[0])


def matrix_add(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Сложение матриц одного размера."""
    left, right = _to_matrix(node), _second_matrix(args)
    ctx.require(left.shape == right.shape, "матрицы разного размера", "matrix_diff_size_error")
    return _record(node, from_sympy(left + right), ctx, "matrix_add")


def matrix_subtract(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Вычитание матриц одного размера."""
    left, right = _to_matrix(node), _second_matrix(args)
    ctx.require(left.shape == right.shape, "матрицы разного размера", "matrix_diff_size_error")
    return _record(node, from_sympy(left - right), ctx, "matrix_sub")


def matrix_multiply(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Умножение матриц: столбцы первой равны строкам второй."""
    left, right = _to_matrix(node), _second_matrix(args)
    ctx.require(
        left.shape[1] == right.shape[0],
        "число столбцов первой матрицы не равно числу строк второй",
        "matrix_mul_diff_size_error",
    )
    return _record(node, from_sympy(left * right), ctx, "matrix_mul")


def matrix_scale(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Умножение матрицы на скаляр."""
    if not args:
        raise SolveError("для умножения на скаляр нужен скаляр")
    scalar = to_sympy(args[0])
    multiplier = _to_matrix(node) * scalar
    result = from_sympy(multiplier)
    ctx.result.add(Step(left=node, right=result, key="matrix_mul_scalar", args=[args[0]]))
    return result


def matrix_transpose(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Транспонирование матрицы."""
    _ = args
    return _record(node, from_sympy(_to_matrix(node).T), ctx, "calculate_short")


def matrix_inverse(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Обратная матрица: только квадратная и с ненулевым определителем."""
    _ = args
    matrix = _to_matrix(node)
    ctx.require(
        matrix.rows == matrix.cols,
        "обратная матрица определена только для квадратной",
        "matrix_inv_undef",
    )
    ctx.require(
        matrix.det() != 0,
        "обратной матрицы не существует: определитель равен нулю",
        "matrix_inv_det_zero",
    )
    return _record(node, from_sympy(matrix.inv()), ctx, "matrix_inv_find_smpl")


def matrix_determinant(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Определитель матрицы."""
    _ = args
    matrix = _to_matrix(node)
    ctx.require(
        matrix.rows == matrix.cols,
        "определитель определён только для квадратной",
        "matrix_det_undef",
    )
    return _record(node, from_sympy(matrix.det()), ctx, "matrix_det_rewrite")


MATRIX_COMMANDS: dict[str, Command] = {
    "matrix_add": matrix_add,
    "matrix_subtract": matrix_subtract,
    "matrix_multiply": matrix_multiply,
    "matrix_scale": matrix_scale,
    "matrix_transpose": matrix_transpose,
    "matrix_inverse": matrix_inverse,
    "matrix_determinant": matrix_determinant,
}


__all__ = [
    "MATRIX_COMMANDS",
    "solve_determinant",
    "solve_matrix",
]
