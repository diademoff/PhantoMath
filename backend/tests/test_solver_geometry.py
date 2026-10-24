"""Отрезок и длина отрезка.

Типы узлов ``LINE_SEGMENT`` и ``LINE_SEGMENT_LENGTH``. Длина считается как
расстояние между координатными точками или ``|a − b|`` на числовой прямой.
"""

from __future__ import annotations

from mymath_backend.ast import CoreNode
from mymath_backend.input import parse_protocol
from mymath_backend.node_types import CoreNodeType as T
from mymath_backend.solver import solve


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def var(name: str) -> CoreNode:
    return CoreNode.variable(name)


def point(*coordinates: str) -> CoreNode:
    return CoreNode.node(T.LIST, *(c(value) for value in coordinates))


def segment(first: CoreNode, second: CoreNode) -> CoreNode:
    return CoreNode.node(T.LINE_SEGMENT, first, second)


def length(*children: CoreNode) -> CoreNode:
    return CoreNode.node(T.LINE_SEGMENT_LENGTH, *children)


def run(node: CoreNode) -> tuple[list[str], CoreNode]:
    vertical = solve(node).result.vertical()
    assert vertical is not None and vertical.solution is not None
    keys = [s.description.type for st in vertical.steps for s in st.substeps]
    return keys, vertical.solution


class TestSegmentLength:
    def test_distance_between_points(self) -> None:
        keys, solution = run(length(point("1", "1"), point("4", "5")))
        assert keys == ["calculate_short"]
        assert solution.value == "5"

    def test_distance_surd(self) -> None:
        _keys, solution = run(length(point("0", "0"), point("1", "1")))
        assert solution.type is T.ROOT2
        assert solution.children[0].value == "2"

    def test_segment_on_number_line(self) -> None:
        keys, solution = run(length(c("3"), c("8")))
        assert keys == ["abs"]
        assert solution.value == "5"

    def test_segment_between_labels_is_symbolic(self) -> None:
        _keys, solution = run(length(segment(var("A"), var("B"))))
        assert solution.type is T.LINE_SEGMENT_LENGTH

    def test_segment_node_is_symbolic(self) -> None:
        vertical = solve(segment(var("A"), var("B"))).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.type is T.LINE_SEGMENT


class TestProtocol:
    def test_tokens(self) -> None:
        parsed = parse_protocol("{length({3},{8})}")
        assert parsed.type is T.LINE_SEGMENT_LENGTH
        assert parse_protocol("{segment({A},{B})}").type is T.LINE_SEGMENT
