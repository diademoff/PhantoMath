"""Тесты операций над матрицами (команды).

Матрица -- узел ``MATRIX`` со строками ``MATRIX_ROW``. Операции -- команды
(``matrix_add``, ``matrix_subtract``, ``matrix_multiply``, ``matrix_scale``,
``matrix_transpose``, ``matrix_inverse``, ``matrix_determinant``); второй
операнд приходит в ``args``. Значения сверяются через sympy.
"""

from __future__ import annotations

import sympy

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.solver import SolveError, solve
from mymath_backend.solver.sympy_bridge import to_sympy


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def row(*cells: CoreNode) -> CoreNode:
    return CoreNode.node(T.MATRIX_ROW, *cells)


def mat(*rows: CoreNode) -> CoreNode:
    return CoreNode.node(T.MATRIX, *rows)


def run(node: CoreNode, command: str, args: list[CoreNode] | None = None) -> sympy.Matrix:
    vertical = solve(node, command=command, args=args).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return to_sympy(vertical.solution)


def step_key(node: CoreNode, command: str, args: list[CoreNode] | None = None) -> str:
    vertical = solve(node, command=command, args=args).result.vertical()
    assert vertical is not None
    return next(sub.description.type for step in vertical.steps for sub in step.substeps)


A = mat(row(c("1"), c("2")), row(c("3"), c("4")))
B = mat(row(c("5"), c("6")), row(c("7"), c("8")))


class TestOperations:
    def test_add(self) -> None:
        assert run(A, "matrix_add", [B]) == sympy.Matrix([[6, 8], [10, 12]])
        assert step_key(A, "matrix_add", [B]) == "matrix_add"

    def test_subtract(self) -> None:
        assert run(A, "matrix_subtract", [B]) == sympy.Matrix([[-4, -4], [-4, -4]])

    def test_multiply(self) -> None:
        assert run(A, "matrix_multiply", [B]) == sympy.Matrix([[19, 22], [43, 50]])
        assert step_key(A, "matrix_multiply", [B]) == "matrix_mul"

    def test_scale(self) -> None:
        assert run(A, "matrix_scale", [c("2")]) == sympy.Matrix([[2, 4], [6, 8]])

    def test_transpose(self) -> None:
        assert run(A, "matrix_transpose") == sympy.Matrix([[1, 3], [2, 4]])

    def test_inverse(self) -> None:
        expected = sympy.Matrix(
            [[sympy.Rational(-2), 1], [sympy.Rational(3, 2), sympy.Rational(-1, 2)]]
        )
        assert run(A, "matrix_inverse") == expected
        assert step_key(A, "matrix_inverse") == "matrix_inv_find_formula"

    def test_determinant(self) -> None:
        assert run(A, "matrix_determinant") == -2
        assert step_key(A, "matrix_determinant") == "matrix_det_rewrite"

    def test_non_square_shape(self) -> None:
        tall = mat(row(c("1"), c("2")), row(c("3"), c("4")), row(c("5"), c("6")))
        assert to_sympy(solve(tall).result.vertical().solution) == sympy.Matrix(
            [[1, 2], [3, 4], [5, 6]]
        )


class TestRowOperations:
    def test_multiply_row(self) -> None:
        result = to_sympy(
            solve(A, command="matrix_mul_row", args=[c("1"), c("2")]).result.vertical().solution
        )
        assert result == sympy.Matrix([[2, 4], [3, 4]])
        assert step_key(A, "matrix_mul_row", [c("1"), c("2")]) == "mat_mul_row"

    def test_divide_row(self) -> None:
        result = to_sympy(
            solve(A, command="matrix_divide_row", args=[c("2"), c("2")]).result.vertical().solution
        )
        assert result == sympy.Matrix([[1, 2], [sympy.Rational(3, 2), 2]])

    def test_add_row(self) -> None:
        result = to_sympy(
            solve(A, command="matrix_add_row", args=[c("1"), c("2"), c("2")])
            .result.vertical()
            .solution
        )
        assert result == sympy.Matrix([[1, 2], [5, 8]])
        assert step_key(A, "matrix_add_row", [c("1"), c("2"), c("2")]) == "mul_row_add"

    def test_row_out_of_range(self) -> None:
        try:
            solve(A, command="matrix_mul_row", args=[c("5"), c("2")])
        except SolveError as err:
            assert "вне матрицы" in str(err)
        else:
            raise AssertionError("ожидалась ошибка")


class TestErrors:
    def test_add_size_mismatch(self) -> None:
        tall = mat(row(c("1"), c("2")), row(c("3"), c("4")), row(c("5"), c("6")))
        try:
            solve(A, command="matrix_add", args=[tall])
        except SolveError as err:
            assert err.explanation_key == "matrix_diff_size_error"
        else:
            raise AssertionError("ожидалась ошибка")

    def test_multiply_size_mismatch(self) -> None:
        tall = mat(row(c("1"), c("2")), row(c("3"), c("4")), row(c("5"), c("6")))
        try:
            solve(A, command="matrix_multiply", args=[tall])
        except SolveError as err:
            assert err.explanation_key == "matrix_mul_diff_size_error"
        else:
            raise AssertionError("ожидалась ошибка")

    def test_inverse_singular(self) -> None:
        singular = mat(row(c("1"), c("2")), row(c("2"), c("4")))
        try:
            solve(singular, command="matrix_inverse")
        except SolveError as err:
            assert err.explanation_key == "matrix_inv_det_zero"
        else:
            raise AssertionError("ожидалась ошибка")

    def test_determinant_non_square(self) -> None:
        tall = mat(row(c("1"), c("2")), row(c("3"), c("4")), row(c("5"), c("6")))
        try:
            solve(tall, command="matrix_determinant")
        except SolveError as err:
            assert err.explanation_key == "matrix_det_undef"
        else:
            raise AssertionError("ожидалась ошибка")
