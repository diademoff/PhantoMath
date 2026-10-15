"""Тесты сходимости рядов (H): команда ``convergence``.

Сумма с бесконечным пределом вычисляется sympy: конечное значение —
``convergent``, бесконечное/неопределённое — ``divergent``. Ответ —
``TEXT[TEXT_KEY("true"/"false")]``.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import SolveError, solve


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


class TestRatioTest:
    def _run(self, source: str) -> tuple[list[str], str]:
        vertical = solve(parse_protocol(source), command="ratio_test").result.vertical()
        assert vertical is not None and vertical.solution is not None
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        return keys, vertical.solution.children[0].value or ""

    def test_converges(self) -> None:
        keys, value = self._run("{sigma_def({n},{1},{inf},{frac({1},{2^n})})}")
        assert keys == ["series_ratio_test", "series_ratio_test_use", "series_ratio_test_lim_ltone"]
        assert value == "true"

    def test_diverges(self) -> None:
        keys, value = self._run("{sigma_def({n},{1},{inf},{frac({2^n},{n})})}")
        assert keys == ["series_ratio_test", "series_ratio_test_use", "series_ratio_test_lim_gtone"]
        assert value == "false"

    def test_inconclusive(self) -> None:
        harmonic = "{sigma_def({n},{1},{inf},{frac({1},{n})})}"
        with pytest.raises(SolveError, match="не даёт ответа"):
            solve(parse_protocol(harmonic), command="ratio_test")


class TestRootTest:
    def test_converges(self) -> None:
        source = "{sigma_def({n},{1},{inf},{frac({1},{2^n})})}"
        vertical = solve(parse_protocol(source), command="root_test").result.vertical()
        assert vertical is not None and vertical.solution is not None
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        assert keys == ["series_root_test", "series_root_test_use", "series_root_test_lim_ltone"]
        assert vertical.solution.children[0].value == "true"


class TestNthTermTest:
    def test_diverges(self) -> None:
        source = "{sigma_def({n},{1},{inf},{frac({n},{n+1})})}"
        vertical = solve(parse_protocol(source), command="nth_term_test").result.vertical()
        assert vertical is not None and vertical.solution is not None
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        assert keys == [
            "series_nth_term_test",
            "series_nth_term_test_use",
            "series_nth_term_test_lim_nozero",
        ]
        assert vertical.solution.children[0].value == "false"
