"""Условное выражение (``CONDITIONAL_EXPRESSION``) и кусочная функция.

Дети условного выражения — ``[условие, ветвь «да», ветвь «нет»]``. Если условие
решается без переменных, выбирается ветвь (шаг ``true``/``false``); иначе узел
остаётся символьным и переводится в ``Piecewise``.
"""

from __future__ import annotations

from mymath_backend.ast import CoreNode
from mymath_backend.node_types import CoreNodeType as T
from mymath_backend.solver import solve
from mymath_backend.solver.sympy_bridge import from_sympy, to_sympy


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def x() -> CoreNode:
    return CoreNode.variable("x")


def conditional(condition: CoreNode, then: CoreNode, otherwise: CoreNode) -> CoreNode:
    return CoreNode.node(T.CONDITIONAL_EXPRESSION, condition, then, otherwise)


def step_keys(node: CoreNode) -> list[str]:
    vertical = solve(node).result.vertical()
    assert vertical is not None
    return [s.description.type for st in vertical.steps for s in st.substeps]


class TestConditional:
    def test_true_branch(self) -> None:
        node = conditional(CoreNode.node(T.LESS_THAN, c("2"), c("3")), c("5"), c("7"))
        vertical = solve(node).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert step_keys(node) == ["true"]
        assert vertical.solution.value == "5"

    def test_false_branch(self) -> None:
        node = conditional(CoreNode.node(T.LESS_THAN, c("3"), c("2")), c("5"), c("7"))
        vertical = solve(node).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert step_keys(node) == ["false"]
        assert vertical.solution.value == "7"

    def test_symbolic_condition_stays(self) -> None:
        node = conditional(CoreNode.node(T.LESS_THAN, x(), c("3")), c("5"), c("7"))
        vertical = solve(node).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.type is T.CONDITIONAL_EXPRESSION

    def test_sympy_roundtrip(self) -> None:
        node = conditional(CoreNode.node(T.LESS_THAN, x(), c("3")), c("5"), c("7"))
        restored = from_sympy(to_sympy(node))
        assert restored.type is T.CONDITIONAL_EXPRESSION
        assert restored.children[0].type is T.LESS_THAN


class TestPiecewise:
    def test_piecewise_is_symbolic(self) -> None:
        node = CoreNode.node(
            T.PIECEWISE_DEFINITION,
            x(),
            CoreNode.node(T.LESS_THAN, x(), c("0")),
            CoreNode.node(T.POWER, x(), c("2")),
            CoreNode.node(T.GREATER_THAN_EQUAL, x(), c("0")),
        )
        vertical = solve(node).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.type is T.PIECEWISE_DEFINITION
