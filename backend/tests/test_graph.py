"""Тесты семплирования графика."""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.graph import free_variable, graph_annotations, sample
from mymath_backend.solver.base import SolveError


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def var(name: str = "x") -> CoreNode:
    return CoreNode.variable(name)


def node(t: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(t, *children)


class TestSample:
    def test_parabola(self) -> None:
        problem = node(T.POWER, var(), c("2"))
        data = sample(problem, -2.0, 2.0, samples=5)
        assert data["variable"] == "x"
        assert data["points"] == [[-2.0, 4.0], [-1.0, 1.0], [0.0, 0.0], [1.0, 1.0], [2.0, 4.0]]
        assert data["yMin"] == 0.0
        assert data["yMax"] == 4.0

    def test_square_root_skips_negatives(self) -> None:
        problem = node(T.ROOT2, var())
        data = sample(problem, -1.0, 1.0, samples=5)
        assert all(point[0] >= 0 for point in data["points"])
        assert data["points"][-1] == [1.0, 1.0]

    def test_free_variable_defaults_to_x(self) -> None:
        assert free_variable(c("5")) == "x"
        assert free_variable(node(T.ADD, var("t"), c("1"))) == "t"


class TestAnnotations:
    def test_parabola(self) -> None:
        data = graph_annotations(node(T.POWER, var(), c("2")), -5.0, 5.0)
        assert data["roots"] == [[0.0, 0.0]]
        assert data["yIntercept"] == [0.0, 0.0]
        assert data["minima"] == [[0.0, 0.0]]

    def test_shifted_parabola(self) -> None:
        expression = node(T.SUBTRACT, node(T.POWER, var(), c("2")), c("4"))
        data = graph_annotations(expression, -5.0, 5.0)
        assert [point[0] for point in data["roots"]] == [-2.0, 2.0]
        assert data["minima"] == [[0.0, -4.0]]

    def test_hyperbola_asymptotes(self) -> None:
        expression = node(T.DIVIDE, c("1"), node(T.SUBTRACT, var(), c("2")))
        data = graph_annotations(expression, -5.0, 5.0)
        assert data["verticalAsymptotes"] == [2.0]
        assert data["horizontalAsymptotes"] == [0.0]

    def test_included_in_sample(self) -> None:
        data = sample(node(T.POWER, var(), c("2")), -2.0, 2.0, samples=5)
        assert "annotations" in data
        assert data["annotations"]["minima"] == [[0.0, 0.0]]


class TestErrors:
    def test_bad_range(self) -> None:
        with pytest.raises(SolveError, match="диапазон"):
            sample(var(), 1.0, 1.0)

    def test_no_real_values(self) -> None:
        with pytest.raises(SolveError, match="вещественных"):
            sample(node(T.ROOT2, c("-1")), -1.0, 1.0, samples=5)

    def test_bad_sample_count(self) -> None:
        with pytest.raises(SolveError, match="точек"):
            sample(var(), -1.0, 1.0, samples=1)
