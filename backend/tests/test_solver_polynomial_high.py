"""Тесты уравнений степени выше второй (A4).

Кубические, биквадратные и прочие многочлены высокой степени решаются
разложением на множители (``solve_by_factoring``); показываются только
действительные корни по возрастанию, неприводимые корни остаются точными.
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


def roots(source: str) -> list[str]:
    solution = _vertical(source).solution
    assert solution is not None
    items = solution.children if solution.type is T.LIST else [solution]
    return [item.children[1].value or "" for item in items]


class TestHighDegree:
    def test_cubic_three_roots(self) -> None:
        source = "{=({x^3-6x^2+11x-6},{0})}"
        assert roots(source) == ["1", "2", "3"]
        assert step_keys(source) == [
            "write_as_diff_fact",
            "write_as_sum_fact",
            "extract_arg",
            "extract_arg",
            "extract_arg",
            "extract_arg",
            "write_as_diff_fact",
            "extract_arg",
            "extract_arg",
            "extract_arg",
            "quad_separate_zero_product",
            "eq_linear",
            "eq_linear",
            "eq_linear",
            "solution_eq_num",
        ]

    def test_biquadratic(self) -> None:
        assert roots("{=({x^4-5x^2+4},{0})}") == ["-2", "-1", "1", "2"]

    def test_cube_root_exact(self) -> None:
        source = "{=({x^3},{2})}"
        solution = _vertical(source).solution
        assert solution is not None and solution.type is T.EQUALS
        assert solution.children[1].type is T.ROOT

    def test_irreducible_cubic_real_root_only(self) -> None:
        # x^3 + x + 1 = 0 — один действительный корень (Кардано), не комплексный.
        result = roots("{=({x^3+x+1},{0})}")
        assert len(result) == 1
