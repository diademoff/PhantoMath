"""Тесты функций как объектов: ``FUNCTION`` и ``FUNCTION_INVERSE``.

Узел ``FUNCTION`` хранит имя функции в ``value``, а аргумент — в детях.
Определения нет, поэтому значение не вычисляется: узел нормализует аргумент
и остаётся символьным, а ``to_sympy``/``from_sympy`` умеют обе стороны.
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


def function(name: str, argument: CoreNode) -> CoreNode:
    return CoreNode(type=T.FUNCTION, value=name, children=[argument])


def substep_keys(node: CoreNode) -> list[str]:
    vertical = solve(node).result.vertical()
    assert vertical is not None
    return [s.description.type for st in vertical.steps for s in st.substeps]


class TestFunction:
    def test_symbolic_no_steps(self) -> None:
        vertical = solve(function("f", x())).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.type is T.FUNCTION
        assert vertical.solution.value == "f"
        assert substep_keys(function("f", x())) == []

    def test_argument_is_folded(self) -> None:
        argument = CoreNode.node(T.ADD, c("2"), c("3"))
        vertical = solve(function("f", argument)).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert substep_keys(function("f", argument)) == ["add"]
        assert vertical.solution.children[0].value == "5"

    def test_inverse(self) -> None:
        node = CoreNode(type=T.FUNCTION_INVERSE, value="f", children=[x()])
        vertical = solve(node).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.type is T.FUNCTION_INVERSE
        assert vertical.solution.value == "f"

    def test_sympy_roundtrip(self) -> None:
        node = function("g", x())
        restored = from_sympy(to_sympy(node))
        assert restored.type is T.FUNCTION
        assert restored.value == "g"
        assert restored.children[0].value == "x"


def linear_definition() -> CoreNode:
    """``f(x) = 2x + 1``."""
    body = CoreNode.node(
        T.ADD,
        CoreNode.node(T.MULTIPLY_IMPLICIT, c("2"), x()),
        c("1"),
    )
    return CoreNode.node(T.EQUALS, function("f", x()), body)


def run_with(node: CoreNode, definition: CoreNode) -> tuple[list[str], CoreNode]:
    vertical = solve(node, definitions=[definition]).result.vertical()
    assert vertical is not None and vertical.solution is not None
    keys = [s.description.type for st in vertical.steps for s in st.substeps]
    return keys, vertical.solution


class TestDefinitions:
    def test_definition_is_echoed(self) -> None:
        vertical = solve(linear_definition()).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.type is T.EQUALS
        keys = [s.description.type for st in vertical.steps for s in st.substeps]
        assert keys == ["function"]

    def test_evaluation(self) -> None:
        keys, solution = run_with(function("f", c("2")), linear_definition())
        assert keys[0] == "function_evaluate_value"
        assert solution.value == "5"

    def test_derivative_through_definition(self) -> None:
        node = CoreNode.node(T.DERIVATION1, function("f", x()))
        _keys, solution = run_with(node, linear_definition())
        assert solution.value == "2"

    def test_inverse(self) -> None:
        node = CoreNode(type=T.FUNCTION_INVERSE, value="f", children=[c("1")])
        _keys, solution = run_with(node, linear_definition())
        assert solution.value == "0", "2x+1 = 1 -> x = 0"

    def test_without_definition_stays_symbolic(self) -> None:
        vertical = solve(function("f", c("2"))).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.type is T.FUNCTION
