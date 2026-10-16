"""Тесты модуля множеств и отношений.

Проверяются конечные множества и операции над ними (объединение, пересечение,
разность), объединение промежутков, вхождение и включение, а также
представление булева ответа узлом ``TEXT[TEXT_KEY]`` как в APK.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import SolveError, registered_types, solve
from mymath_backend.solver.sympy_bridge import from_sympy, to_sympy

_SET_TYPES = {
    T.SET,
    T.UNION,
    T.INTERSECTION,
    T.DIFFERENCE,
    T.ELEMENT_OF,
    T.ELEMENT_NOT_OF,
    T.SUBSET_OR_EQUALS,
    T.PROPER_SUBSET,
    T.NOT_PROPER_SUBSET,
    T.SUPERSET_OR_EQUALS,
    T.PROPER_SUPERSET,
    T.NOT_PROPER_SUPERSET,
}


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


def expected_set(*values: str) -> CoreNode:
    return CoreNode.node(T.SET, *(CoreNode.constant(v) for v in values))


def bool_value(source: str) -> str:
    """Ключ булева ответа ``TEXT[TEXT_KEY]``."""
    answer = solution_of(source)
    assert answer.type is T.TEXT
    assert len(answer.children) == 1
    key = answer.children[0]
    assert key.type is T.TEXT_KEY
    return key.value or ""


class TestRegistration:
    def test_all_types_registered(self) -> None:
        assert registered_types() >= _SET_TYPES

    def test_protocol_keys_are_known(self) -> None:
        for source in (
            "{set({1})}",
            "{union({set({1})},{set({2})})}",
            "{intsec({set({1})},{set({2})})}",
            "{intersection({set({1})},{set({2})})}",
            "{setminus({set({1})},{set({2})})}",
            "{elem_of({1},{set({1})})}",
            "{elem_not_of({1},{set({1})})}",
            "{subseteq({set({1})},{set({1})})}",
            "{subset({set({1})},{set({1})})}",
            "{supseteq({set({1})},{set({1})})}",
            "{supset({set({1})},{set({1})})}",
        ):
            parse_protocol(source)


class TestSetOperations:
    def test_literal_kept(self) -> None:
        assert solution_of("{set({1},{2},{3})}").structural_eq(expected_set("1", "2", "3"))
        assert step_keys("{set({1},{2},{3})}") == []

    def test_union_of_finite_sets(self) -> None:
        source = "{union({set({1},{2})},{set({2},{3})})}"
        assert solution_of(source).structural_eq(expected_set("1", "2", "3"))
        assert step_keys(source) == ["union"]

    def test_intersection_of_finite_sets(self) -> None:
        source = "{intsec({set({1},{2})},{set({2},{3})})}"
        assert solution_of(source).structural_eq(expected_set("2"))
        assert step_keys(source) == ["intersection"]

    def test_difference_has_no_step(self) -> None:
        source = "{setminus({set({1},{2},{3})},{set({2})})}"
        assert solution_of(source).structural_eq(expected_set("1", "3"))
        assert step_keys(source) == []

    def test_overlapping_intervals_merge(self) -> None:
        source = "{union({coint({0},{2})},{ooint({1},{3})})}"
        answer = solution_of(source)
        assert answer.type is T.CLOSED_OPEN_INTERVAL
        assert [child.value for child in answer.children] == ["0", "3"]
        assert step_keys(source) == ["union"]

    def test_disjoint_intervals_stay_union(self) -> None:
        source = "{union({ooint({0},{1})},{ooint({1},{2})})}"
        assert solution_of(source).type is T.UNION
        assert step_keys(source) == []


class TestMembership:
    def test_true(self) -> None:
        assert bool_value("{elem_of({2},{set({1},{2},{3})})}") == "true"
        assert step_keys("{elem_of({2},{set({1},{2},{3})})}") == []

    def test_false(self) -> None:
        assert bool_value("{elem_of({5},{set({1},{2})})}") == "false"

    def test_element_not_of(self) -> None:
        assert bool_value("{elem_not_of({5},{set({1},{2})})}") == "true"
        assert bool_value("{elem_not_of({2},{set({1},{2})})}") == "false"

    @pytest.mark.parametrize(
        "source",
        [
            "{union({1},{2})}",
            "{intersection({1},{2})}",
            "{setminus({1},{2})}",
            "{elem_of({1},{2})}",
            "{subseteq({1},{2})}",
        ],
    )
    def test_non_sets_rejected(self, source: str) -> None:
        """Операции и отношения требуют множеств, а не падают на sympy."""
        with pytest.raises(SolveError):
            solve(parse_protocol(source))


class TestInclusion:
    def test_subset_or_equals(self) -> None:
        assert bool_value("{subseteq({set({1},{2})},{set({1},{2},{3})})}") == "true"

    def test_proper_subset_needs_strict(self) -> None:
        assert bool_value("{subset({set({1},{2})},{set({1},{2},{3})})}") == "true"
        assert bool_value("{subset({set({1},{2})},{set({1},{2})})}") == "false"

    def test_superset(self) -> None:
        assert bool_value("{supseteq({set({1},{2},{3})},{set({1},{2})})}") == "true"
        assert bool_value("{supset({set({1},{2})},{set({1},{2})})}") == "false"


class TestSympyBridge:
    def test_finite_set_round_trip(self) -> None:
        node = parse_protocol("{set({1},{2},{3})}")
        assert from_sympy(to_sympy(node)).structural_eq(node)

    def test_operations_round_trip(self) -> None:
        for source in (
            "{union({set({1},{2})},{set({3})})}",
            "{intsec({set({1},{2})},{set({2})})}",
            "{setminus({set({1},{2},{3})},{set({2})})}",
        ):
            node = parse_protocol(source)
            assert from_sympy(to_sympy(node)).structural_eq(solution_of(source))

    def test_unknown_membership_is_error(self) -> None:
        # Символьный элемент в интервале: вхождение не определено.
        problem = CoreNode.node(
            T.ELEMENT_OF,
            CoreNode.variable("x"),
            CoreNode.node(T.OPEN_OPEN_INTERVAL, CoreNode.constant("0"), CoreNode.constant("1")),
        )
        try:
            solve(problem)
        except SolveError:
            return
        raise AssertionError("ожидалась SolveError")
