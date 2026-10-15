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
        assert step_keys(source) == ["series_test_group", "convergent"]

    def test_harmonic(self) -> None:
        source = "{sigma_def({n},{1},{inf},{frac({1},{n})})}"
        assert bool_value(source) == "false"
        assert step_keys(source) == ["series_test_group", "divergent"]

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


class TestIntegralTest:
    def _run(self, source: str, command: str) -> tuple[list[str], str]:
        vertical = solve(parse_protocol(source), command=command).result.vertical()
        assert vertical is not None and vertical.solution is not None
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        return keys, vertical.solution.children[0].value or ""

    def test_not_summable(self) -> None:
        # Σ 1/(n·ln n) — замкнутой суммы нет, ряд расходится.
        source = "{sigma_def({n},{2},{inf},{frac({1},{muli({n},{ln({n})})})})}"
        keys, value = self._run(source, "convergence")
        assert keys == [
            "series_test_group",
            "series_integral_test",
            "series_integral_test_use_smpl",
            "series_integral_test_diverges",
        ]
        assert value == "false"

    def test_converges(self) -> None:
        source = "{sigma_def({n},{1},{inf},{frac({1},{n^2})})}"
        keys, value = self._run(source, "integral_test")
        assert keys[-1] == "series_integral_test_converges"
        assert value == "true"


class TestAltTest:
    def _run(self, source: str) -> tuple[list[str], str]:
        vertical = solve(parse_protocol(source), command="alt_test").result.vertical()
        assert vertical is not None and vertical.solution is not None
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        return keys, vertical.solution.children[0].value or ""

    def test_converges(self) -> None:
        # Σ (−1)ⁿ/n — признак Лейбница.
        keys, value = self._run("{sigma_def({n},{1},{inf},{frac({(-1)^n},{n})})}")
        assert keys == ["series_alt_test", "series_alt_test_converges"]
        assert value == "true"

    def test_diverges(self) -> None:
        # Σ (−1)ⁿ·n/(n+1) — общий член не стремится к нулю.
        keys, value = self._run("{sigma_def({n},{1},{inf},{frac({(-1)^n*n},{n+1})})}")
        assert keys[-1] == "series_nth_term_test_lim_nozero"
        assert value == "false"


class TestComparisonTests:
    def _run(self, source: str, reference: str, command: str) -> tuple[list[str], str]:
        vertical = solve(
            parse_protocol(source),
            command=command,
            args=[parse_protocol(reference)],
        ).result.vertical()
        assert vertical is not None and vertical.solution is not None
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        return keys, vertical.solution.children[0].value or ""

    def test_direct_converges(self) -> None:
        source = "{sigma_def({n},{1},{inf},{frac({1},{n^2+n})})}"
        reference = "{sigma_def({n},{1},{inf},{frac({1},{n^2})})}"
        keys, value = self._run(source, reference, "direct_comparison_test")
        assert keys == [
            "series_direct_comp_test",
            "series_direct_comp_test_use",
            "series_direct_comp_test_converges",
        ]
        assert value == "true"

    def test_limit_converges(self) -> None:
        source = "{sigma_def({n},{1},{inf},{frac({1},{n^2+n})})}"
        reference = "{sigma_def({n},{1},{inf},{frac({1},{n^2})})}"
        keys, value = self._run(source, reference, "limit_comparison_test")
        assert keys == [
            "series_limit_test",
            "series_limit_test_use_conv",
            "series_limit_test_converges",
        ]
        assert value == "true"

    def test_direct_requires_comparison(self) -> None:
        # 1/n ≥ 1/n², поэтому сравнение с 1/n² не даёт сходимости.
        source = "{sigma_def({n},{1},{inf},{frac({1},{n})})}"
        reference = "{sigma_def({n},{1},{inf},{frac({1},{n^2})})}"
        with pytest.raises(SolveError, match="не меньше"):
            solve(
                parse_protocol(source),
                command="direct_comparison_test",
                args=[parse_protocol(reference)],
            )


class TestPSeries:
    def _run(self, source: str, command: str) -> tuple[list[str], str]:
        vertical = solve(parse_protocol(source), command=command).result.vertical()
        assert vertical is not None and vertical.solution is not None
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        return keys, vertical.solution.children[0].value or ""

    def test_converges(self) -> None:
        source = "{sigma_def({n},{1},{inf},{frac({1},{n^2})})}"
        keys, value = self._run(source, "pseries_test")
        assert keys == [
            "series_pseries_test",
            "series_pseries_test_use",
            "series_pseries_test_converges",
        ]
        assert value == "true"

    def test_diverges(self) -> None:
        source = "{sigma_def({n},{1},{inf},{frac({1},{n})})}"
        keys, value = self._run(source, "pseries_test")
        assert keys[-1] == "series_pseries_test_diverges"
        assert value == "false"

    def test_geometric_converges(self) -> None:
        source = "{sigma_def({n},{1},{inf},{frac({1},{2^n})})}"
        keys, value = self._run(source, "geom_series_test")
        assert keys == ["series_geom_series_test", "series_geom_series_test_converges"]
        assert value == "true"

    def test_geometric_diverges(self) -> None:
        source = "{sigma_def({n},{1},{inf},{2^n})}"
        keys, value = self._run(source, "geom_series_test")
        assert keys[-1] == "series_geom_series_test_diverges"
        assert value == "false"


class TestRadiusOfConvergence:
    def test_finite_radius(self) -> None:
        source = "{sigma_def({n},{0},{inf},{frac({x^n},{2^n})})}"
        vertical = solve(parse_protocol(source), command="radius_of_convergence").result.vertical()
        assert vertical is not None and vertical.solution is not None
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        assert keys == [
            "convergence_radius_find",
            "convergence_radius_abs",
            "convergence_radius_limit",
            "convergence_radius_conv",
        ]
        assert vertical.solution.value == "2"

    def test_infinite_radius(self) -> None:
        source = "{sigma_def({n},{0},{inf},{frac({x^n},{factorial({n})})})}"
        vertical = solve(parse_protocol(source), command="radius_of_convergence").result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.value == "∞"


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
