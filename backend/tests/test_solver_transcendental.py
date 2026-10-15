"""Тесты показательных и логарифмических уравнений (A3).

Логарифмы с одним основанием приравнивают аргументы (``eq_log_equalise``),
остальные показательные и логарифмические уравнения сводятся к виду
``x = …`` (``eq_trans``). Типы узлов ``EXP``/``LN`` в ответе допустимы.
"""

from __future__ import annotations

from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import solve


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source)).result.vertical()
    assert vertical is not None
    return vertical


def step_keys(source: str) -> list[str]:
    return [sub.description.type for step in _vertical(source).steps for sub in step.substeps]


def right_side(source: str) -> str:
    solution = _vertical(source).solution
    assert solution is not None and solution.type is T.EQUALS
    return solution.children[1].value or ""


class TestTranscendental:
    def test_exponential(self) -> None:
        source = "{=({2^x},{8})}"
        assert right_side(source) == "3"
        assert step_keys(source) == ["eq_trans"]

    def test_exponential_different_exponent(self) -> None:
        assert right_side("{=({2^(x+1)},{8})}") == "2"

    def test_log_same_base(self) -> None:
        source = "{=({ln({x})},{ln({3})})}"
        assert right_side(source) == "3"
        assert step_keys(source) == ["eq_log_equalise"]

    def test_log_with_base(self) -> None:
        source = "{=({log({x},{2})},{3})}"
        assert right_side(source) == "8"

    def test_log_of_exponential_right(self) -> None:
        # ln x = 2 -> x = e^2 (ответ — узел EXP).
        solution = _vertical("{=({ln({x})},{2})}").solution
        assert solution is not None and solution.type is T.EQUALS
        assert solution.children[1].type is T.EXP

    def test_impossible_exponential(self) -> None:
        vertical = _vertical("{=({2^x},{-1})}")
        assert vertical.solution is None
        assert step_keys("{=({2^x},{-1})}") == ["false_statement_solve"]
