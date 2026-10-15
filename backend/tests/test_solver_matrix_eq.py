"""Тесты матричных уравнений и обратной матрицы методом Гаусса (M).

``matrix_equation`` решает ``A·X = B`` и ``X·A = B`` (неизвестная матрица —
та, что содержит переменные); ``matrix_inverse_gauss`` находит обратную
матрицу через расширенную ``[A | E]``. Ответы сверяются через sympy.
"""

from __future__ import annotations

import sympy

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.solver import solve
from mymath_backend.solver.sympy_bridge import to_sympy


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def row(*cells: CoreNode) -> CoreNode:
    return CoreNode.node(T.MATRIX_ROW, *cells)


def mat(*rows: CoreNode) -> CoreNode:
    return CoreNode.node(T.MATRIX, *rows)


def var(name: str) -> CoreNode:
    return CoreNode.variable(name)


def run(node: CoreNode, command: str) -> tuple[list[str], CoreNode]:
    vertical = solve(node, command=command).result.vertical()
    assert vertical is not None and vertical.solution is not None
    keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
    return keys, vertical.solution


A = mat(row(c("1"), c("2")), row(c("3"), c("4")))
B = mat(row(c("5"), c("6")), row(c("7"), c("8")))
X = mat(row(var("x"), var("z")), row(var("y"), var("w")))
SINGULAR = mat(row(c("1"), c("2")), row(c("2"), c("4")))


class TestMatrixEquation:
    def test_a_times_x(self) -> None:
        node = CoreNode.node(T.EQUALS, CoreNode.node(T.MULTIPLY, A, X), B)
        keys, solution = run(node, "matrix_equation")
        assert keys == ["matrix_eq_mul", "matrix_eq_set_elements_equal"]
        assert to_sympy(solution) == sympy.Matrix([[-3, -4], [4, 5]])

    def test_x_times_a(self) -> None:
        node = CoreNode.node(T.EQUALS, CoreNode.node(T.MULTIPLY, X, A), B)
        _, solution = run(node, "matrix_equation")
        assert to_sympy(solution) == sympy.Matrix([[-1, 2], [-2, 3]])

    def test_no_solution(self) -> None:
        node = CoreNode.node(T.EQUALS, CoreNode.node(T.MULTIPLY, SINGULAR, X), B)
        keys, solution = run(node, "matrix_equation")
        assert keys == ["matrix_eq_system_no_sol"]
        assert solution.type is T.EMPTY


class TestInverseGauss:
    def test_inverse(self) -> None:
        keys, solution = run(A, "matrix_inverse_gauss")
        assert keys == [
            "matrix_inv_use_notation",
            "matrix_inv_write_right",
            "matrix_inv_find_identity",
            "matrix_inv_right_is_inv",
        ]
        assert to_sympy(solution) == sympy.Matrix(
            [[-2, 1], [sympy.Rational(3, 2), -sympy.Rational(1, 2)]]
        )

    def test_singular(self) -> None:
        keys, solution = run(SINGULAR, "matrix_inverse_gauss")
        assert keys == [
            "matrix_inv_use_notation",
            "matrix_inv_write_right",
            "matrix_inv_find_identity",
            "matrix_inv_no_inv",
        ]
        assert solution.type is T.EMPTY

    def test_protocol_inverse(self) -> None:
        node = parse_protocol("{mat({mat_row({1},{2})},{mat_row({3},{4})})}")
        _, solution = run(node, "matrix_inverse_gauss")
        assert to_sympy(solution).det() != 0
