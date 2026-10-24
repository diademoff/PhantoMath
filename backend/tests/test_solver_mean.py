"""Тесты среднего арифметического (R): узел ``MEAN``.

Среднее — сумма значений, делённая на их число; шаг ``calculate_short``.
"""

from __future__ import annotations

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.solver import solve


def run(source: str) -> tuple[list[str], CoreNode]:
    vertical = solve(parse_protocol(source)).result.vertical()
    assert vertical is not None and vertical.solution is not None
    keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
    return keys, vertical.solution


class TestMean:
    def test_integers(self) -> None:
        keys, solution = run("{mean({2},{4},{6})}")
        assert keys == ["calculate_short"]
        assert solution.value == "4"

    def test_fraction(self) -> None:
        assert run("{mean({1},{2})}")[1].value == "3/2"

    def test_single(self) -> None:
        assert run("{mean({5})}")[1].value == "5"

    def test_node_type(self) -> None:
        problem = CoreNode.node(T.MEAN, CoreNode.constant("1"), CoreNode.constant("2"))
        vertical = solve(problem).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.value == "3/2"
