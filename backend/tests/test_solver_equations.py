"""Тесты модуля уравнений.

Проверяются: значения ответа (для линейных и квадратных), порядок и ключи
шагов и то, что каждый выданный ключ есть в словаре объяснений с нужной
арностью. Корни читаются из узла ответа: ``EQUALS`` для одного корня и
``LIST`` из ``EQUALS`` для двух.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from mymath_backend import CoreNodeType as T
from mymath_backend import load_explanations
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverGroup, CoreSolverVerticalResult
from mymath_backend.solver import SolveError, registered_types, solve

EXPLANATIONS = Path(__file__).resolve().parents[2] / "truth" / "data" / "explanations.json"


def vertical_of(source: str) -> CoreSolverVerticalResult:
    data = solve(parse_protocol(source))
    vertical = data.result.vertical()
    assert vertical is not None
    return vertical


def step_keys(source: str) -> list[str]:
    vertical = vertical_of(source)
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


def roots_of(source: str) -> list[str]:
    """Значения корней: по одному на каждое ``x = …`` в ответе."""
    solution = vertical_of(source).solution
    assert solution is not None
    if solution.type is T.LIST:
        return [eq.children[1].value or "" for eq in solution.children]
    if solution.type is T.EQUALS:
        return [solution.children[1].value or ""]
    raise AssertionError(f"неожиданный узел ответа: {solution.type}")


class TestLinear:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("{=({2x+3},{7})}", "2"),
            ("{=({x+1},{3})}", "2"),
            ("{=({3x},{12})}", "4"),
            ("{=({x},{5})}", "5"),
            ("{=({2x},{0})}", "0"),
            ("{=({x-3},{0})}", "3"),
            ("{=({5-x},{2})}", "3"),
            ("{=({x/2},{3})}", "6"),
        ],
    )
    def test_roots(self, source: str, expected: str) -> None:
        assert roots_of(source) == [expected]

    def test_answer_is_equation_x_equals(self) -> None:
        vertical = vertical_of("{=({2x+3},{7})}")
        assert vertical.solution is not None
        assert vertical.solution.type is T.EQUALS
        assert vertical.solution.children[0].value == "x"
        assert vertical.solution.children[1].value == "2"

    def test_steps_move_then_divide(self) -> None:
        assert step_keys("{=({2x+3},{7})}") == ["move", "eq_linar_divide_both_sides"]

    def test_only_move_when_coefficient_is_one(self) -> None:
        assert step_keys("{=({x+1},{3})}") == ["move"]

    def test_only_divide_when_already_isolated(self) -> None:
        assert step_keys("{=({3x},{12})}") == ["eq_linar_divide_both_sides"]

    def test_no_steps_for_trivial_equation(self) -> None:
        assert step_keys("{=({x},{5})}") == []

    def test_header_on_every_step(self) -> None:
        vertical = vertical_of("{=({2x+3},{7})}")
        for step in vertical.steps:
            assert [h.type for h in step.step_headers] == ["eq_solve_short"]


class TestQuadratic:
    def test_two_rational_roots_are_sorted(self) -> None:
        assert roots_of("{=({x^2-5x+6},{0})}") == ["2", "3"]

    def test_difference_of_squares(self) -> None:
        assert roots_of("{=({x^2},{4})}") == ["-2", "2"]

    def test_double_root(self) -> None:
        # x^2 - 4x + 4 = (x-2)^2
        assert roots_of("{=({x^2-4x+4},{0})}") == ["2"]

    def test_irrational_roots_stay_exact(self) -> None:
        vertical = vertical_of("{=({x^2-2},{0})}")
        assert vertical.solution is not None
        assert vertical.solution.type is T.LIST
        assert step_keys("{=({x^2-2},{0})}") == ["eq_quad_solve_in_r"]

    def test_zero_b_keeps_both_signs(self) -> None:
        # x^2 - 2 = 0: корни -√2 и +√2, а не √2 дважды.
        vertical = vertical_of("{=({x^2-2},{0})}")
        assert vertical.solution is not None and vertical.solution.type is T.LIST
        minus, plus = (eq.children[1] for eq in vertical.solution.children)
        assert minus.children[0].type is T.NEGATIVE
        assert plus.children[0].type is T.ROOT2

    def test_negative_discriminant_is_reported(self) -> None:
        with pytest.raises(SolveError, match="действительных корней"):
            solve(parse_protocol("{=({x^2+1},{0})}"))


class TestUnsupported:
    def test_degree_above_two(self) -> None:
        with pytest.raises(SolveError, match="второй степени"):
            solve(parse_protocol("{=({x^3},{1})}"))

    def test_two_variables(self) -> None:
        with pytest.raises(SolveError, match="одно неизвестное"):
            solve(parse_protocol("{=({x+y},{1})}"))

    def test_rational_equation_is_solved(self) -> None:
        # 1/x = 2 -> x = 1/2; рациональные уравнения поддержаны (A1).
        assert roots_of("{=({1/x},{2})}") == ["1/2"]


class TestExplanationKeys:
    def test_steps_keys_exist_with_matching_arity(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        problems: list[str] = []
        for source in (
            "{=({2x+3},{7})}",
            "{=({3x},{12})}",
            "{=({x+1},{3})}",
            "{=({x^2-5x+6},{0})}",
        ):
            for key in step_keys(source):
                if key not in explanations:
                    problems.append(f"{source}: ключа {key} нет в словаре")
                    continue
                template = explanations.raw_template(key, DEFAULT_LOCALE) or ""
                used = {int(m) for m in re.findall(r"ARG(\d+)", template)}
                highest = max(used) if used else 0
                if highest != explanations.arity(key):
                    problems.append(f"{source}: у {key} арность {explanations.arity(key)}")
        assert problems == []


class TestRegistration:
    def test_equals_is_registered(self) -> None:
        assert T.EQUALS in registered_types()


def _group(source: str) -> CoreSolverGroup:
    return solve(parse_protocol(source)).result.groups[0]


def _method_keys(entry: object) -> list[str]:
    steps = entry.result["steps"]  # type: ignore[index]
    return [
        sub["description"]["type"]
        for step in steps
        for sub in step["substeps"]  # type: ignore[index]
    ]


class TestMethods:
    """Выбор способа решения: несколько записей вертикальной ветки."""

    def test_factorable_quadratic_has_two_methods(self) -> None:
        group = _group("{=({x^2-5x+6},{0})}")
        assert len(group.entries) == 2
        assert group.select_method_text is not None
        assert group.select_method_text.type == "select_method"

    def test_first_method_is_formula_second_factoring(self) -> None:
        group = _group("{=({x^2-5x+6},{0})}")
        assert _method_keys(group.entries[0]) == ["eq_quad_solve_in_r"]
        assert _method_keys(group.entries[1]) == ["solve_by_factoring"]

    def test_irrational_quadratic_has_one_method(self) -> None:
        group = _group("{=({x^2-2},{0})}")
        assert len(group.entries) == 1
        assert group.select_method_text is None

    def test_linear_has_two_methods(self) -> None:
        group = _group("{=({2x+3},{7})}")
        assert len(group.entries) == 2
        assert _method_keys(group.entries[0]) == ["move", "eq_linar_divide_both_sides"]
        assert _method_keys(group.entries[1]) == ["eq_linar_divide_both_sides", "move"]

    def test_linear_without_constant_has_one_method(self) -> None:
        # 3x = 12: делить до переноса нечего, способ один.
        group = _group("{=({3x},{12})}")
        assert len(group.entries) == 1


class TestDegenerate:
    """Тождество и противоречие: ответ — текст шага, без узла ответа."""

    def test_no_solution(self) -> None:
        group = _group("{=({2x+3},{2x+5})}")
        assert _method_keys(group.entries[0]) == ["false_statement_solve"]
        assert "solutionNode" not in group.entries[0].result

    def test_identity(self) -> None:
        group = _group("{=({x+1},{x+1})}")
        assert _method_keys(group.entries[0]) == ["solutions_inf_many"]
        assert "solutionNode" not in group.entries[0].result
