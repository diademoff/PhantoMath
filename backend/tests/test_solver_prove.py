"""Тесты доказательства тождеств (Q): команда ``prove``.

Равенство считается тождеством, если разность частей упрощается до нуля
(шаг ``prove_identity_true``); иначе ``prove_identity_both_false``. Ответ —
``TEXT[TEXT_KEY("true"/"false")]``.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import SolveError, solve


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source), command="prove").result.vertical()
    assert vertical is not None
    return vertical


def bool_value(source: str) -> str:
    answer = _vertical(source).solution
    assert answer is not None and answer.type is T.TEXT
    return answer.children[0].value or ""


def step_keys(source: str) -> list[str]:
    return [sub.description.type for step in _vertical(source).steps for sub in step.substeps]


class TestProve:
    def test_true_identity(self) -> None:
        source = "{=({sin({x})^2+cos({x})^2},{1})}"
        assert bool_value(source) == "true"
        assert step_keys(source) == ["prove_identity", "prove_identity_true"]

    def test_false_identity(self) -> None:
        source = "{=({sin({x})^2+cos({x})^2},{2})}"
        assert bool_value(source) == "false"
        assert step_keys(source) == ["prove_identity", "prove_identity_both_false"]

    def test_algebraic(self) -> None:
        assert bool_value("{=({(x+1)^2},{x^2+2x+1})}") == "true"

    def test_requires_equation(self) -> None:
        with pytest.raises(SolveError):
            solve(CoreNode.constant("1"), command="prove")
