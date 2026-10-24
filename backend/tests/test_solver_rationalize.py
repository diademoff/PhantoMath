"""Тесты рационализации (O): команда ``rationalize``.

Иррациональность из знаменателя убирается ``sympy.radsimp`` (шаг
``rationalize_roots``).
"""

from __future__ import annotations

from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import solve


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source), command="rationalize").result.vertical()
    assert vertical is not None
    return vertical


def step_keys(source: str) -> list[str]:
    return [sub.description.type for step in _vertical(source).steps for sub in step.substeps]


class TestRationalize:
    def test_one_over_root(self) -> None:
        answer = _vertical("{frac({1},{root2({2})})}").solution
        assert answer is not None and answer.type is T.FRACTION
        assert answer.children[0].type is T.ROOT2
        assert answer.children[1].value == "2"
        assert step_keys("{frac({1},{root2({2})})}") == ["rationalize_roots"]

    def test_becomes_integer_root(self) -> None:
        answer = _vertical("{frac({3},{root2({3})})}").solution
        assert answer is not None and answer.type is T.ROOT2

    def test_conjugate(self) -> None:
        answer = _vertical("{frac({2},{1+root2({3})})}").solution
        assert answer is not None and answer.type is T.SUBTRACT
