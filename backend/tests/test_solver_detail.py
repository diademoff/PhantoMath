"""Тесты раскрываемого углублённого пояснения шага (``subresult``).

Вложенный результат не меняет ключи и ответ верхнего уровня, поэтому корпус
его не ловит; здесь проверяем, что детали действительно порождаются для
производной (почленно) и квадратного уравнения (дискриминант и корни).
"""

from __future__ import annotations

from mymath_backend.ast import CoreNode
from mymath_backend.node_types import CoreNodeType as T
from mymath_backend.solver import solve


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def x() -> CoreNode:
    return CoreNode.variable("x")


def substeps(node: CoreNode) -> list[CoreNode]:
    vertical = solve(node).result.vertical()
    assert vertical is not None
    return [s for st in vertical.steps for s in st.substeps]


def detail_keys(sub: CoreNode) -> list[str]:
    assert sub.subresult is not None, "у шага нет раскрываемого пояснения"
    return [y.description.type for step in sub.subresult.steps for y in step.substeps]


class TestDetail:
    def test_derivative_sum_terms(self) -> None:
        expression = CoreNode.node(T.ADD, CoreNode.node(T.POWER, x(), c("2")), x())
        derivative = CoreNode.node(T.DERIVATION1, expression)
        steps = {sub.description.type: sub for sub in substeps(derivative)}
        # The sum card has one named rule stage and a nested screen per term.
        assert "lesson_calc_rule_sum" in steps
        assert detail_keys(steps["lesson_calc_part_first"]) == [
            "lesson_calc_rule_power",
            "lesson_calc_simplify_result",
        ]
        assert detail_keys(steps["lesson_calc_part_second"]) == ["derive_var"]

    def test_quadratic_discriminant_and_roots(self) -> None:
        # 0.5x^2 + 5x + 1 = 0 keeps the discriminant/roots-formula flow (irrational roots;
        # integer coefficients now get the app's card set instead).
        polynomial = CoreNode.node(
            T.ADD,
            CoreNode.node(
                T.ADD,
                CoreNode.node(T.MULTIPLY_IMPLICIT, c("0.5"), CoreNode.node(T.POWER, x(), c("2"))),
                CoreNode.node(T.MULTIPLY_IMPLICIT, c("5"), x()),
            ),
            c("1"),
        )
        equation = CoreNode.node(T.EQUALS, polynomial, c("0"))
        with_detail = [sub for sub in substeps(equation) if sub.subresult is not None]
        assert with_detail, "итоговый шаг корней раскрывается"
        keys = detail_keys(with_detail[-1])
        assert "lesson_root_formula" in keys
        assert "lesson_root_numerator" in keys
        assert "lesson_root_denominator" in keys
        assert "lesson_root_reduce" in keys
        disc = next(
            sub for sub in substeps(equation) if sub.description.type == "eq_quad_disc_calculate"
        )
        assert detail_keys(disc) == [
            "lesson_disc_square",
            "lesson_disc_product",
            "lesson_disc_subtract",
        ]
