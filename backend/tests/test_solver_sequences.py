"""Тесты модуля последовательностей (G).

По первым членам распознаётся арифметическая (шаг ``seq_state_common_diff``)
или геометрическая (``seq_state_common_ratio``) прогрессия; ответ — следующие
четыре члена. Прочие последовательности — ошибка.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import SolveError, registered_types, solve


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source)).result.vertical()
    assert vertical is not None
    return vertical


def next_terms(source: str) -> list[str]:
    solution = _vertical(source).solution
    assert solution is not None and solution.type is T.LIST
    return [child.value or "" for child in solution.children]


def step_keys(source: str) -> list[str]:
    return [sub.description.type for step in _vertical(source).steps for sub in step.substeps]


class TestSequences:
    def test_registered(self) -> None:
        assert T.SEQUENCE in registered_types()

    def test_arithmetic(self) -> None:
        source = "{sequence({2},{4},{6},{8})}"
        assert next_terms(source) == ["10", "12", "14", "16"]
        assert step_keys(source) == [
            "seq_check_arithmetic",
            "seq_state_common_diff",
            "seq_state_next_four",
        ]

    def test_geometric(self) -> None:
        source = "{sequence({3},{6},{12},{24})}"
        assert next_terms(source) == ["48", "96", "192", "384"]
        assert step_keys(source) == [
            "seq_check_geometric",
            "seq_state_common_ratio",
            "seq_state_next_four",
        ]

    def test_fractions(self) -> None:
        # 1, 1/2, 1/4, 1/8 — геометрическая со знаменателем 1/2.
        source = "{sequence({1},{frac({1},{2})},{frac({1},{4})},{frac({1},{8})})}"
        assert next_terms(source)[0] == "1/16"

    def test_not_a_progression(self) -> None:
        with pytest.raises(SolveError):
            solve(parse_protocol("{sequence({1},{2},{4},{5})}"))

    def test_needs_two_terms(self) -> None:
        problem = CoreNode.node(T.SEQUENCE, CoreNode.constant("1"))
        with pytest.raises(SolveError):
            solve(problem)


class TestExplicitFormula:
    def _run(self, source: str) -> tuple[list[str], CoreNode]:
        vertical = solve(parse_protocol(source), command="explicit_formula").result.vertical()
        assert vertical is not None and vertical.solution is not None
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        return keys, vertical.solution

    def test_arithmetic(self) -> None:
        keys, solution = self._run("{sequence({2},{5},{8})}")
        assert keys == [
            "seq_find_first",
            "seq_write_explicit_formula",
            "seq_arithmetic_sub_explicit_formula",
        ]
        assert solution.type is T.SUBTRACT

    def test_geometric(self) -> None:
        keys, solution = self._run("{sequence({3},{6},{12})}")
        assert keys == [
            "seq_find_first",
            "seq_write_explicit_formula",
            "seq_geometric_sub_explicit_formula",
        ]
        assert solution.type is T.MULTIPLY_IMPLICIT


class TestConvergence:
    def _run(self, source: str) -> tuple[list[str], str]:
        vertical = solve(parse_protocol(source), command="sequence_convergence").result.vertical()
        assert vertical is not None and vertical.solution is not None
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        value = vertical.solution.children[0].value or ""
        return keys, value

    def test_geometric_converges(self) -> None:
        keys, value = self._run("{sequence({1},{frac({1},{2})},{frac({1},{4})})}")
        assert keys == ["seq_find_limit", "seq_lim_conv"]
        assert value == "true"

    def test_arithmetic_diverges(self) -> None:
        keys, value = self._run("{sequence({2},{5},{8})}")
        assert keys == ["seq_find_limit", "seq_lim_div"]
        assert value == "false"

    def test_geometric_diverges(self) -> None:
        _, value = self._run("{sequence({2},{4},{8})}")
        assert value == "false"
