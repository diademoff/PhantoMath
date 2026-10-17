"""Тесты иррациональных уравнений (A2).

Уравнение с квадратным корнем возводится в квадрат и решается; посторонние
корни отсеиваются подстановкой в исходное уравнение (шаг
``rel_restrictions_check``). Если корней нет — ответ без узла.
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


def root_values(source: str) -> list[str]:
    solution = _vertical(source).solution
    assert solution is not None
    items = solution.children if solution.type is T.LIST else [solution]
    return [item.children[1].value or "" for item in items]


class TestRadical:
    def test_simple(self) -> None:
        source = "{=({root2({x})},{2})}"
        assert root_values(source) == ["4"]
        assert step_keys(source) == [
            "eq_irrational_simple_square",
            "solution_check_sub",
            "root_square",
            "solution_check_t",
        ]

    def test_extraneous_root_excluded(self) -> None:
        source = "{=({root2({x+1})},{x-1})}"
        assert root_values(source) == ["3"]
        assert "rel_restrictions_check" in step_keys(source)

    def test_no_solution(self) -> None:
        source = "{=({root2({x})},{-1})}"
        assert _vertical(source).solution is None
        assert step_keys(source) == [
            "rel_restrictions_find",
            "rel_restrictions_root_base_neg",
            "eq_irrational_simple_square",
            "rel_restrictions_intersect",
            "rel_restrictions_check",
        ]

    def test_non_radical_untouched(self) -> None:
        assert root_values("{=({2x+3},{7})}") == ["2"]
