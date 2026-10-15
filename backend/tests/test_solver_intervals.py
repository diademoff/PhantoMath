"""Тесты модуля промежутков.

Проверяются четыре типа интервалов, ввод токенами протокола
(``ooint``/``ocint``/``coint``/``ccint``), свёртка границ, нормализация
пустого промежутка и перевод в sympy и обратно.
"""

from __future__ import annotations

import sympy

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import registered_types, solve
from mymath_backend.solver.sympy_bridge import from_sympy, to_sympy


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source)).result.vertical()
    assert vertical is not None
    return vertical


def solution_of(source: str) -> CoreNode:
    vertical = _vertical(source)
    assert vertical.solution is not None
    return vertical.solution


def step_keys(source: str) -> list[str]:
    return [sub.description.type for step in _vertical(source).steps for sub in step.substeps]


class TestTypes:
    def test_all_four_registered(self) -> None:
        assert {
            T.OPEN_OPEN_INTERVAL,
            T.OPEN_CLOSED_INTERVAL,
            T.CLOSED_OPEN_INTERVAL,
            T.CLOSED_CLOSED_INTERVAL,
        } <= registered_types()

    def test_protocol_tokens(self) -> None:
        cases = {
            "{ooint({0},{1})}": T.OPEN_OPEN_INTERVAL,
            "{ocint({0},{1})}": T.OPEN_CLOSED_INTERVAL,
            "{coint({0},{1})}": T.CLOSED_OPEN_INTERVAL,
            "{ccint({0},{1})}": T.CLOSED_CLOSED_INTERVAL,
        }
        for source, expected in cases.items():
            assert parse_protocol(source).type is expected


class TestNormalization:
    def test_unchanged_interval_has_no_step(self) -> None:
        problem = parse_protocol("{ooint({2},{5})}")
        assert solution_of("{ooint({2},{5})}").structural_eq(problem)
        assert step_keys("{ooint({2},{5})}") == []

    def test_bounds_are_folded(self) -> None:
        answer = solution_of("{ooint({1+1},{5})}")
        assert answer.type is T.OPEN_OPEN_INTERVAL
        assert [child.value for child in answer.children] == ["2", "5"]
        assert step_keys("{ooint({1+1},{5})}") == ["add", "rewrite_interval"]

    def test_point_interval_is_not_empty(self) -> None:
        answer = solution_of("{ccint({1},{1})}")
        assert answer.type is T.CLOSED_CLOSED_INTERVAL
        assert step_keys("{ccint({1},{1})}") == []


class TestEmpty:
    def test_reversed_bounds_are_empty(self) -> None:
        assert solution_of("{ooint({2},{1})}").type is T.EMPTY
        assert step_keys("{ooint({2},{1})}") == ["rewrite_interval"]

    def test_equal_bounds_with_open_edge_are_empty(self) -> None:
        assert solution_of("{ooint({1},{1})}").type is T.EMPTY
        assert solution_of("{ocint({1},{1})}").type is T.EMPTY
        assert solution_of("{coint({1},{1})}").type is T.EMPTY

    def test_folded_reversed_bounds_are_empty(self) -> None:
        assert solution_of("{ooint({3-1},{1})}").type is T.EMPTY
        assert step_keys("{ooint({3-1},{1})}") == ["sub", "rewrite_interval"]


class TestSympyBridge:
    def test_round_trip(self) -> None:
        sources = (
            "{ooint({0},{1})}",
            "{ocint({0},{1})}",
            "{coint({0},{1})}",
            "{ccint({0},{1})}",
        )
        for source in sources:
            node = parse_protocol(source)
            assert from_sympy(to_sympy(node)).structural_eq(node)

    def test_infinite_bound(self) -> None:
        node = parse_protocol("{coint({0},{inf})}")
        assert to_sympy(node) == sympy.Interval(0, sympy.oo)

    def test_empty_expression_maps_to_empty_node(self) -> None:
        assert from_sympy(sympy.Interval(2, 1)).type is T.EMPTY
