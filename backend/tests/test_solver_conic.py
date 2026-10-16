"""Тесты конических сечений (F): команда ``conic``.

Тип определяется по дискриминанту ``B² − 4AC`` общего уравнения второй степени:
окружность/эллипс, парабола, гипербола (шаги ``conics_represents_*``). Ответ —
исходное уравнение.

Ключи без аргументов: ``conics_classify_*`` требуют в ARG уравнение в
каноническом виде, радиус и центр, которых решатель пока не считает, и текст
показывал бы служебные метки.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import SolveError, solve


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source), command="conic").result.vertical()
    assert vertical is not None
    return vertical


def step_keys(source: str) -> list[str]:
    return [sub.description.type for step in _vertical(source).steps for sub in step.substeps]


class TestConic:
    def test_circle(self) -> None:
        assert step_keys("{=({x^2+y^2},{1})}") == [
            "conics_identify",
            "conics_identify_disc",
            "conics_represents_circle",
        ]

    def test_ellipse(self) -> None:
        assert step_keys("{=({x^2+2y^2},{1})}") == [
            "conics_identify",
            "conics_identify_disc",
            "conics_represents_ellipse",
        ]

    def test_hyperbola(self) -> None:
        assert step_keys("{=({x^2-y^2},{1})}") == [
            "conics_identify",
            "conics_identify_disc",
            "conics_represents_hyperbola",
        ]

    def test_parabola(self) -> None:
        assert step_keys("{=({y},{x^2})}") == [
            "conics_identify",
            "conics_identify_disc",
            "conics_represents_parabola",
        ]

    def test_answer_is_equation(self) -> None:
        answer = _vertical("{=({x^2+y^2},{1})}").solution
        assert answer is not None and answer.type is T.EQUALS

    def test_requires_equation(self) -> None:
        with pytest.raises(SolveError):
            solve(CoreNode.variable("x"), command="conic")
