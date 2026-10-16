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
        keys = detail_keys(steps["find_derivative"])
        assert len(keys) == 2, "производная суммы — по слагаемому на шаг"
        assert all(key == "find_derivative" for key in keys)

    def test_quadratic_discriminant_and_roots(self) -> None:
        equation = CoreNode.node(T.EQUALS, CoreNode.node(T.POWER, x(), c("2")), c("4"))
        with_detail = [sub for sub in substeps(equation) if sub.subresult is not None]
        assert with_detail, "итоговый шаг корней раскрывается"
        keys = detail_keys(with_detail[-1])
        assert "eq_quad_disc_calculate" in keys
        assert any(key in ("quad_final_single", "quad_final_multi") for key in keys)
