"""Тесты сходимости рядов (H): команда ``convergence``.

Сумма с бесконечным пределом вычисляется sympy: конечное значение —
``convergent``, бесконечное/неопределённое — ``divergent``. Ответ —
``TEXT[TEXT_KEY("true"/"false")]``.
"""

from __future__ import annotations

from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import solve


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source), command="convergence").result.vertical()
    assert vertical is not None
    return vertical


def bool_value(source: str) -> str:
    answer = _vertical(source).solution
    assert answer is not None and answer.type is T.TEXT
    return answer.children[0].value or ""


def step_keys(source: str) -> list[str]:
    return [sub.description.type for step in _vertical(source).steps for sub in step.substeps]


class TestConvergence:
    def test_p_series(self) -> None:
        source = "{sigma_def({n},{1},{inf},{frac({1},{n^2})})}"
        assert bool_value(source) == "true"
        assert step_keys(source) == ["convergent"]

    def test_harmonic(self) -> None:
        source = "{sigma_def({n},{1},{inf},{frac({1},{n})})}"
        assert bool_value(source) == "false"
        assert step_keys(source) == ["divergent"]

    def test_geometric(self) -> None:
        assert bool_value("{sigma_def({n},{1},{inf},{frac({1},{2^n})})}") == "true"
