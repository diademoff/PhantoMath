"""Тесты чётности/нечётности (E): команда ``even_odd``.

Шаг-заключение ``function_even_simple`` / ``function_odd_simple`` /
``function_not_even_nor_odd_simple``; ответ — исходное выражение.

Ключи без аргументов: подробный вариант (``function_even``) требует в ARG1
условие (``f(−x) = f(x)``), которого решатель не строит, и текст показывал бы
служебную метку.
"""

from __future__ import annotations

from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import solve


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source), command="even_odd").result.vertical()
    assert vertical is not None
    return vertical


def step_keys(source: str) -> list[str]:
    return [sub.description.type for step in _vertical(source).steps for sub in step.substeps]


class TestEvenOdd:
    def test_even(self) -> None:
        assert step_keys("{x^2}") == ["function_even_odd_notation", "function_even_simple"]

    def test_odd(self) -> None:
        assert step_keys("{x^3}") == ["function_even_odd_notation", "function_odd_simple"]

    def test_neither(self) -> None:
        assert step_keys("{x^2+x}") == [
            "function_even_odd_notation",
            "function_not_even_nor_odd_simple",
        ]

    def test_cosine_even(self) -> None:
        assert step_keys("{cos({x})}") == ["function_even_odd_notation", "function_even_simple"]

    def test_sine_odd(self) -> None:
        assert step_keys("{sin({x})}") == ["function_even_odd_notation", "function_odd_simple"]

    def test_answer_is_expression(self) -> None:
        answer = _vertical("{x^2}").solution
        assert answer is not None and answer.type is T.POWER
