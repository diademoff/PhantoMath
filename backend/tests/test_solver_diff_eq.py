"""Тесты дифференциальных уравнений (I): команда ``diff_eq``.

``y′ = f(x, y)`` (узел ``PRIME``); уравнение первого порядка показывает
карточку метода (разделяющиеся переменные, однородное, линейное, Бернулли,
в полных дифференциалах), второго — карточку понижения порядка,
характеристического уравнения или специальной правой части. Ответ — ``y = …``;
с аргументами ``[x₀, y₀]`` — частное решение (шаг «Начальное условие»).
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import SolveError, solve

_SEPARABLE = [
    "lesson_calc_ode_sep_derivative",
    "lesson_calc_ode_sep_separate",
    "lesson_calc_ode_sep_integrate",
    "lesson_calc_ode_sep_primitive",
    "lesson_calc_ode_sep_express_log",
]
_LINEAR = [
    "lesson_calc_ode_lin_substitute",
    "lesson_calc_ode_lin_insert",
    "lesson_calc_ode_lin_choose_v",
    "lesson_calc_ode_lin_v",
    "lesson_calc_ode_lin_v_value",
    "lesson_calc_ode_lin_u_equation",
    "lesson_calc_ode_lin_u",
    "lesson_calc_ode_lin_u_value",
    "lesson_calc_ode_lin_back",
    "lesson_calc_ode_lin_simplify",
]
_CONDITION = [
    "lesson_calc_ode_condition",
    "lesson_calc_ode_condition_substitute",
    "lesson_calc_ode_condition_value",
    "lesson_calc_ode_condition_answer",
]


def _vertical(source: str, args: list[str] | None = None) -> CoreSolverVerticalResult:
    vertical = solve(
        parse_protocol(source),
        command="diff_eq",
        args=[parse_protocol(arg) for arg in args or []],
    ).result.vertical()
    assert vertical is not None
    return vertical


def step_keys(source: str, args: list[str] | None = None) -> list[str]:
    return [sub.description.type for step in _vertical(source, args).steps for sub in step.substeps]


def answer(source: str, args: list[str] | None = None) -> CoreNode:
    solution = _vertical(source, args).solution
    assert solution is not None
    return solution


class TestDiffEq:
    def test_separation(self) -> None:
        source = "{=({prime({y})},{y})}"
        assert step_keys(source) == _SEPARABLE
        solution = answer(source)
        assert solution.type is T.EQUALS and solution.children[0].value == "y"

    def test_separation_polynomial(self) -> None:
        assert answer("{=({prime({y})},{x^2})}").children[1].type is T.ADD

    def test_linear(self) -> None:
        source = "{=({prime({y})},{x+y})}"
        assert step_keys(source) == _LINEAR

    def test_initial_condition(self) -> None:
        source = "{=({prime({y})},{y})}"
        assert step_keys(source, ["{0}", "{1}"]) == [*_SEPARABLE, *_CONDITION]
        # y′ = y, y(0) = 1 -> y = eˣ (константа определена).
        assert answer(source, ["{0}", "{1}"]).children[1].type is T.EXP

    def test_second_order(self) -> None:
        node = CoreNode.node(
            T.EQUALS,
            CoreNode.node(T.DERIVATION2_PRIME, CoreNode.variable("y")),
            CoreNode.constant("0"),
        )
        vertical = solve(node, command="diff_eq").result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.children[1].type is T.ADD

    def test_not_equation(self) -> None:
        with pytest.raises(SolveError):
            solve(parse_protocol("{y}"), command="diff_eq")

    def test_no_derivative(self) -> None:
        with pytest.raises(SolveError):
            solve(parse_protocol("{=({y},{x})}"), command="diff_eq")

    def test_hard_equation_times_out_instead_of_hanging(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Дедлайн превращает зависший dsolve в SolveError.

        Настоящий пример — маятник ``y″ = sin(y)`` (проверен вручную: виснет
        навсегда, с дедлайном — ``SolveError``). Здесь вместо sympy — спящий
        фейк: ``time.sleep`` отпускает GIL, поэтому утёкший поток не жжёт CPU
        и не тормозит остальную сюиту.
        """
        import time

        from mymath_backend.solver import diff_equations

        def hanging_dsolve(*args: object, **kwargs: object) -> object:
            time.sleep(5)
            raise AssertionError("недостижимо: дедлайн срабатывает раньше")

        monkeypatch.setattr(diff_equations.sympy, "dsolve", hanging_dsolve)
        monkeypatch.setattr(diff_equations, "_DSOLVE_TIMEOUT", 0.5)
        with pytest.raises(SolveError, match="не решается"):
            solve(
                parse_protocol("{=({derivation2_prime({y})},{sin({y})})}"),
                command="diff_eq",
            )


class TestDiffEqWithoutCommand:
    """Уравнения с y′/y″ вводит клавиатура напрямую — команда не нужна."""

    @pytest.mark.parametrize(
        ("source", "first_step"),
        [
            ("{=({prime({y})},{y})}", "lesson_calc_ode_sep_derivative"),
            ("{=({prime({y})},{x+y})}", "lesson_calc_ode_lin_substitute"),
            ("{=({derivation2_prime({y})},{y})}", "lesson_ode_constant_coeff_homogeneous"),
        ],
    )
    def test_auto_routing(self, source: str, first_step: str) -> None:
        vertical = solve(parse_protocol(source)).result.vertical()
        assert vertical is not None and vertical.solution is not None
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        assert keys[0] == first_step
        assert vertical.solution.type is T.EQUALS
        assert vertical.solution.children[0].value == "y"
