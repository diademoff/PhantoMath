"""Тесты служебных типов узлов (R12): контейнеры и нотация.

``LIST``/``VERTICAL_LIST`` сворачивают содержимое; остальные оформительские типы
возвращаются как есть. Геометрия (``LINE_SEGMENT*``) не регистрируется.
"""

from __future__ import annotations

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.solver import registered_types, solve


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


class TestContainers:
    def test_list_folds(self) -> None:
        # В списке подвыражение 2·3 сворачивается до 6.
        problem = CoreNode.node(
            T.LIST,
            CoreNode.node(T.MULTIPLY, c("2"), c("3")),
            c("5"),
        )
        vertical = solve(problem).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.type is T.LIST
        assert [child.value for child in vertical.solution.children] == ["6", "5"]

    def test_vertical_list_registered(self) -> None:
        assert T.VERTICAL_LIST in registered_types()

    def test_notation_returns_node(self) -> None:
        problem = CoreNode.node(T.APPROXIMATE, c("1/3"), c("0.333"))
        vertical = solve(problem).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.type is T.APPROXIMATE

    def test_geometry_registered(self) -> None:
        assert T.LINE_SEGMENT in registered_types()


class TestAddSubtract:
    def test_numeric_branches(self) -> None:
        problem = CoreNode.node(T.ADD_SUBTRACT, c("2"), c("3"))
        vertical = solve(problem).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.type is T.LIST
        assert [child.value for child in vertical.solution.children] == ["5", "-1"]
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        # "2-3" is a difference that comes out negative -> calc_diff.
        assert keys == ["add", "calc_diff"]

    def test_symbolic_echo(self) -> None:
        problem = CoreNode.node(T.ADD_SUBTRACT, CoreNode.variable("x"), c("2"))
        vertical = solve(problem).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.type is T.ADD_SUBTRACT
