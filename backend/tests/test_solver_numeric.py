"""Тесты численного решения смешанных трансцендентных уравнений.

``sin x = x`` и ``x*sin x = 1`` не решаются аналитически: корни ищутся по
смене знака на сетке с уточнением бисекцией. Проверяются значения корней,
отсев полюсов (``tan x = x`` меняет знак на asymptote -- это не корень),
сортировка и симметрия, и что выданные ключи есть в словаре объяснений.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mymath_backend import load_explanations
from mymath_backend.input import parse_protocol
from mymath_backend.solver import SolveError, solve

EXPLANATIONS = Path(__file__).resolve().parents[2] / "truth" / "data" / "explanations.json"


def roots_of(source: str) -> list[str]:
    vertical = solve(parse_protocol(source)).result.vertical()
    assert vertical is not None and vertical.solution is not None
    solution = vertical.solution
    if solution.type.value == "LIST":
        return [child.children[1].value or "" for child in solution.children]
    assert solution.type.value == "EQUALS"
    return [solution.children[1].value or ""]


def step_keys(source: str) -> list[str]:
    vertical = solve(parse_protocol(source)).result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


class TestNumericRoots:
    def test_sine_equals_x(self) -> None:
        assert roots_of("{=({sin({x})},{x})}") == ["0"]

    def test_log_plus_linear_is_exact(self) -> None:
        # ``solve`` даёт точный корень -- приближение не нужно.
        assert roots_of("{=({ln({x})+x},{1})}") == ["1"]

    def test_power_in_both_bases(self) -> None:
        assert roots_of("{=({x^x},{2})}") == ["1.55961"]

    def test_two_roots_of_abs_plus_sine(self) -> None:
        assert roots_of("{=({abs({x})+sin({x})},{1})}") == ["-1.934563", "0.510973"]

    def test_many_roots_sorted_and_symmetric(self) -> None:
        roots = [float(value) for value in roots_of("{=({x*sin({x})},{1})}")]
        assert roots == sorted(roots)
        assert len(roots) % 2 == 0
        for low, high in zip(roots, reversed(roots), strict=True):
            assert pytest.approx(low, abs=1e-4) == -high

    def test_poles_are_not_roots(self) -> None:
        # tan x = x: на π/2 знак меняется через полюс -- это не корень.
        roots = [float(value) for value in roots_of("{=({tan({x})},{x})}")]
        import math

        assert 0.0 in roots
        assert all(abs(r - math.pi / 2) > 1e-3 for r in roots)
        assert 4.493409 in roots

    def test_steps_are_explained(self) -> None:
        keys = step_keys("{=({sin({x})},{x})}")
        assert keys == ["graph_solution", "calculate"]

    def test_factorial_equation_is_refused_not_crashed(self) -> None:
        # lambdify factorial(float) бросает TypeError: точка пропускается,
        # корней нет — честный отказ исходного модуля, а не падение.
        with pytest.raises(SolveError):
            solve(parse_protocol("{=({factorial({x})},{6})}"))


class TestFallbackPriority:
    def test_periodic_single_sine_stays_analytic(self) -> None:
        # Численный модуль не перехватывает то, что решает тригонометрия.
        keys = step_keys("{=({sin({x})},{1/2})}")
        assert keys == [
            "trig_eq_two_sollutions",
            "trig_eq_isolate",
            "trig_eq_isolate",
            "trig_arcus",
            "trig_arcus",
            "trig_eq_fun_period",
            "trig_eq_fun_period",
            "eq_linear",
            "trig_eq_positive_period",
            "solution_eq_num",
        ]


class TestExplanationKeys:
    def test_keys_exist(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        for key in ("graph_solution", "calculate", "calculate_plural"):
            assert key in explanations
            assert explanations.arity(key) == 0
