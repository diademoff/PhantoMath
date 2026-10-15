"""Тесты перезаписи представления (O): десятичная↔дробь, проценты.

Команды ``to_fraction`` (``dec_to_frac``) и ``to_percent``
(``rewrite_as_percent``).
"""

from __future__ import annotations

from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import solve


def _vertical(source: str, command: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source), command=command).result.vertical()
    assert vertical is not None
    return vertical


def value_of(source: str, command: str) -> str:
    solution = _vertical(source, command).solution
    assert solution is not None
    return solution.value or ""


class TestRewrite:
    def test_decimal_to_fraction(self) -> None:
        assert value_of("{0.75}", "to_fraction") == "3/4"
        assert value_of("{2.5}", "to_fraction") == "5/2"

    def test_number_to_percent(self) -> None:
        answer = _vertical("{0.5}", "to_percent").solution
        assert answer is not None and answer.type is T.PERCENTAGE
        assert answer.children[0].value == "50"

    def test_fraction_to_percent(self) -> None:
        answer = _vertical("{frac({3},{4})}", "to_percent").solution
        assert answer is not None and answer.type is T.PERCENTAGE
        assert answer.children[0].value == "75"

    def test_equation_sides_transformed(self) -> None:
        # Для уравнения преобразуются обе части (команда-перезапись).
        answer = _vertical("{=({0.5},{0.25})}", "to_fraction").solution
        assert answer is not None and answer.type is T.EQUALS
        assert answer.children[0].value == "1/2"
        assert answer.children[1].value == "1/4"
