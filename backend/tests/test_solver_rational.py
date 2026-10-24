"""Тесты рациональных уравнений (A1).

Уравнение с неизвестным в знаменателе приводится к виду «числитель = 0»,
корни проверяются на полюсы: корень, обращающий знаменатель в ноль,
исключается (шаг ``rel_restrictions_check``). Отсутствие решений даёт ответ
без узла (``solution`` = ``None``), как у прочих уравнений.
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


def root_value(source: str) -> str:
    solution = _vertical(source).solution
    assert solution is not None and solution.type is T.EQUALS
    return solution.children[1].value or ""


class TestRational:
    def test_fraction_equals_number(self) -> None:
        source = "{=({frac({x},{x-2})},{3})}"
        assert root_value(source) == "3"
        assert step_keys(source) == [
            "rel_restrictions_range",
            "eq_mul_direct_denom",
            "mul_bracket",
            "rel_move_left_var",
            "sum_suffix",
            "eq_linear_div",
            "rel_restrictions_check",
        ]

    def test_two_fractions(self) -> None:
        source = "{=({frac({1},{x-1})},{2})}"
        assert root_value(source) == "3/2"

    def test_pole_is_excluded(self) -> None:
        source = "{=({frac({x^2-1},{x-1})},{0})}"
        assert root_value(source) == "-1"
        assert step_keys(source) == [
            "rel_restrictions_range",
            "using_factor",
            "frac_reduce_frac_alg",
            "rel_move_right_const_eq",
            "rel_restrictions_check",
        ]

    def test_no_solution(self) -> None:
        vertical = _vertical("{=({frac({1},{x-1})},{frac({1},{x-2})})}")
        assert vertical.solution is None
        assert step_keys("{=({frac({1},{x-1})},{frac({1},{x-2})})}")[-2:] == [
            "eq_del_opp",
            "rel_el_of_zero",
        ]


class TestStillPolynomial:
    def test_linear_unchanged(self) -> None:
        assert root_value("{=({2x+3},{7})}") == "2"

    def test_quadratic_unchanged(self) -> None:
        assert step_keys("{=({x^2-5x+6},{0})}")[0] == "write_as_diff_fact"
