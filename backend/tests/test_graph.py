"""Тесты семплирования графика."""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.graph import free_variable, sample
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
