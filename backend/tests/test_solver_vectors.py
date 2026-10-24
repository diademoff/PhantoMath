"""Тесты векторов.

Вектор — узел ``LIST`` с компонентами; операции приходят командой, второй
операнд — в ``args``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sympy

from mymath_backend import CoreNode, load_explanations
from mymath_backend import CoreNodeType as T
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.solver import SolveError, solve
from mymath_backend.solver.sympy_bridge import to_sympy

EXPLANATIONS = Path(__file__).resolve().parents[1] / "mymath_backend" / "data" / "explanations.json"


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def vector(*components: CoreNode) -> CoreNode:
    return CoreNode.node(T.LIST, *components)


def solution_of(problem: CoreNode, command: str, args: list[CoreNode] | None = None) -> CoreNode:
    vertical = solve(problem, command=command, args=args).result.vertical()
    assert vertical is not None and vertical.solution is not None
    return vertical.solution


def components(node: CoreNode) -> list[str]:
    assert node.type is T.LIST
    return [child.value or "" for child in node.children]


class TestOperations:
    def test_length(self) -> None:
        assert solution_of(vector(c("3"), c("4")), "vector_length").value == "5"

    def test_add(self) -> None:
        result = solution_of(vector(c("1"), c("2")), "vector_add", [vector(c("3"), c("4"))])
        assert components(result) == ["4", "6"]

    def test_subtract(self) -> None:
        result = solution_of(vector(c("1"), c("2")), "vector_subtract", [vector(c("3"), c("4"))])
        assert components(result) == ["-2", "-2"]

    def test_scale(self) -> None:
        result = solution_of(vector(c("1"), c("2")), "vector_scale", [c("3")])
        assert components(result) == ["3", "6"]

    def test_dot(self) -> None:
        assert (
            solution_of(vector(c("1"), c("2")), "vector_dot", [vector(c("3"), c("4"))]).value
            == "11"
        )

    def test_cross(self) -> None:
        result = solution_of(
            vector(c("1"), c("0"), c("0")),
            "vector_cross",
            [vector(c("0"), c("1"), c("0"))],
        )
        assert components(result) == ["0", "0", "1"]

    def test_length_with_surd(self) -> None:
        result = solution_of(vector(c("1"), c("1")), "vector_length")
        assert sympy.simplify(to_sympy(result) - sympy.sqrt(2)) == 0


class TestUnsupported:
    def test_length_of_non_vector(self) -> None:
        with pytest.raises(SolveError, match="вектор"):
            solve(c("5"), command="vector_length")

    def test_add_without_second(self) -> None:
        with pytest.raises(SolveError, match="второй вектор"):
            solve(vector(c("1"), c("2")), command="vector_add")

    def test_cross_requires_3d(self) -> None:
        with pytest.raises(SolveError, match="3D"):
            solve(
                vector(c("1"), c("2")),
                command="vector_cross",
                args=[vector(c("3"), c("4"))],
            )

    @pytest.mark.parametrize("command", ["vector_add", "vector_subtract", "vector_dot"])
    def test_mismatched_dimensions(self, command: str) -> None:
        """Векторы разной длины — понятный SolveError, а не ShapeError."""
        with pytest.raises(SolveError, match="одной размерности"):
            solve(
                vector(c("1"), c("2")),
                command=command,
                args=[vector(c("1"), c("2"), c("3"))],
            )


class TestExplanationKeys:
    def test_key_exists(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        assert "calculate_short" in explanations
        assert explanations.arity("calculate_short") == 0
        assert "ARG" not in (explanations.raw_template("calculate_short", DEFAULT_LOCALE) or "")
