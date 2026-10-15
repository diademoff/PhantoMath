"""Тесты перевода углов (O): команды ``to_degrees`` и ``to_radians``.

Радианы → узел ``DEGREE`` (шаг ``rewrite_deg``), ``DEGREE`` → радианы
(``rewrite_rad``).
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


def step_keys(source: str, command: str) -> list[str]:
    return [
        sub.description.type for step in _vertical(source, command).steps for sub in step.substeps
    ]


class TestAngle:
    def test_radians_to_degrees(self) -> None:
        answer = _vertical("{frac({pi},{2})}", "to_degrees").solution
        assert answer is not None and answer.type is T.DEGREE
        assert answer.children[0].value == "90"
        assert step_keys("{frac({pi},{2})}", "to_degrees") == ["rewrite_deg"]

    def test_pi_to_degrees(self) -> None:
        answer = _vertical("{pi}", "to_degrees").solution
        assert answer is not None and answer.children[0].value == "180"

    def test_degrees_to_radians(self) -> None:
        answer = _vertical("{deg({90})}", "to_radians").solution
        assert answer is not None and answer.type is T.FRACTION
        assert answer.children[0].value == "π"
        assert step_keys("{deg({90})}", "to_radians") == ["rewrite_rad"]

    def test_full_turn(self) -> None:
        answer = _vertical("{deg({180})}", "to_radians").solution
        assert answer is not None and answer.value == "π"
