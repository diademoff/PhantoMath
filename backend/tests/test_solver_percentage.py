"""Тесты модуля процентов (O).

``p% = p / 100`` сворачивается в обыкновенную дробь (шаг ``percent_to_frac``);
процент участвует и в арифметике.
"""

from __future__ import annotations

from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import registered_types, solve


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source)).result.vertical()
    assert vertical is not None
    return vertical


def value_of(source: str) -> str:
    solution = _vertical(source).solution
    assert solution is not None
    return solution.value or ""


def step_keys(source: str) -> list[str]:
    return [sub.description.type for step in _vertical(source).steps for sub in step.substeps]


class TestPercentage:
    def test_registered(self) -> None:
        assert T.PERCENTAGE in registered_types()

    def test_half(self) -> None:
        source = "{percent({50})}"
        assert value_of(source) == "1/2"
        assert step_keys(source) == ["by_definition", "frac_reduce"]

    def test_eighth(self) -> None:
        assert value_of("{percent({12.5})}") == "1/8"

    def test_integer(self) -> None:
        assert value_of("{percent({200})}") == "2"

    def test_quarter(self) -> None:
        assert value_of("{percent({25})}") == "1/4"

    def test_percent_of_number(self) -> None:
        source = "{percent({50})*200}"
        assert value_of(source) == "100"
        assert step_keys(source) == ["by_definition", "frac_reduce", "frac_reduce_out"]
