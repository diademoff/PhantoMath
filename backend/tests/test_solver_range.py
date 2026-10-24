"""Тесты области значений (E): команда ``range``.

Область значений — множество значений ``f(x)`` на всей прямой; ответ отдаётся
узлом-промежутком или объединением (шаг ``graph_rt_info_range``).
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import SolveError, solve


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source), command="range").result.vertical()
    assert vertical is not None
    return vertical


def step_keys(source: str) -> list[str]:
    return [sub.description.type for step in _vertical(source).steps for sub in step.substeps]


def solution(source: str) -> CoreNode:
    answer = _vertical(source).solution
    assert answer is not None
    return answer


def _interval(kind: str, low: dict, high: dict) -> dict:
    return {"type": kind, "children": [low, high]}


def _constant(value: str) -> dict:
    return {"type": "CONSTANT", "value": value}


def _neg_inf() -> dict:
    return {"type": "NEGATIVE", "children": [_constant("∞")]}


class TestRange:
    def test_parabola_up(self) -> None:
        assert step_keys("{x^2}") == ["graph_rt_info_range"]
        assert solution("{x^2}").structural_eq(
            CoreNode.from_contract(
                _interval("CLOSED_OPEN_INTERVAL", _constant("0"), _constant("∞"))
            )
        )

    def test_shifted_parabola(self) -> None:
        expected = _interval("CLOSED_OPEN_INTERVAL", _constant("-1"), _constant("∞"))
        assert solution("{x^2-4x+3}").structural_eq(CoreNode.from_contract(expected))

    def test_cubic_all_reals(self) -> None:
        expected = _interval("OPEN_OPEN_INTERVAL", _neg_inf(), _constant("∞"))
        assert solution("{x^3}").structural_eq(CoreNode.from_contract(expected))

    def test_parabola_down(self) -> None:
        expected = _interval("OPEN_CLOSED_INTERVAL", _neg_inf(), _constant("0"))
        assert solution("{-x^2}").structural_eq(CoreNode.from_contract(expected))

    def test_sine(self) -> None:
        expected = _interval("CLOSED_CLOSED_INTERVAL", _constant("-1"), _constant("1"))
        assert solution("{sin({x})}").structural_eq(CoreNode.from_contract(expected))

    def test_bounded(self) -> None:
        expected = _interval("OPEN_CLOSED_INTERVAL", _constant("0"), _constant("1"))
        assert solution("{1/(x^2+1)}").structural_eq(CoreNode.from_contract(expected))

    def test_union(self) -> None:
        expected = {
            "type": "UNION",
            "children": [
                _interval("OPEN_OPEN_INTERVAL", _neg_inf(), _constant("0")),
                _interval("OPEN_OPEN_INTERVAL", _constant("0"), _constant("∞")),
            ],
        }
        assert solution("{1/x}").structural_eq(CoreNode.from_contract(expected))

    def test_two_variables(self) -> None:
        with pytest.raises(SolveError):
            solve(parse_protocol("{x+y}"), command="range")
