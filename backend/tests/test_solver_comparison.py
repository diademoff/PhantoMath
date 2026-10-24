"""Тесты сравнения выражений и упорядочивания (``ORDER``).

Отношение без переменных — утверждение «Истина»/«Ложь» (ключи
``compare_eq_eq``/``compare_eq_neq`` для равенства и ``compare_ineq`` для
неравенства); с переменной — по-прежнему неравенство. Дроби с разными
знаменателями сначала приводятся к общему знаменателю (``frac_expand_lcd_msg``,
``mul_with_one``/``mul``, ``compare_frac_nom``). ``ORDER`` сортирует
элементы по возрастанию без шага.
"""

from __future__ import annotations

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import registered_types, solve


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source)).result.vertical()
    assert vertical is not None
    return vertical


def solution_of(source: str) -> CoreNode:
    vertical = _vertical(source)
    assert vertical.solution is not None
    return vertical.solution


def step_keys(source: str) -> list[str]:
    return [sub.description.type for step in _vertical(source).steps for sub in step.substeps]


def bool_value(source: str) -> str:
    answer = solution_of(source)
    assert answer.type is T.TEXT
    assert len(answer.children) == 1
    assert answer.children[0].type is T.TEXT_KEY
    return answer.children[0].value or ""


class TestComparison:
    def test_less_than_true(self) -> None:
        assert bool_value("{lt({2},{3})}") == "true"
        assert step_keys("{lt({2},{3})}") == ["compare_ineq"]

    def test_less_than_false(self) -> None:
        assert bool_value("{lt({3},{2})}") == "false"

    def test_less_than_equal(self) -> None:
        assert bool_value("{lte({2},{2})}") == "true"
        assert bool_value("{lte({3},{2})}") == "false"

    def test_greater_than(self) -> None:
        assert bool_value("{gt({3},{2})}") == "true"
        assert bool_value("{gt({2},{3})}") == "false"

    def test_equals(self) -> None:
        assert bool_value("{eq({2},{2})}") == "true"
        assert bool_value("{eq({2},{3})}") == "false"
        assert step_keys("{eq({2},{2})}") == ["compare_eq_eq"]
        assert step_keys("{eq({2},{3})}") == ["compare_eq_neq"]

    def test_not_equals(self) -> None:
        assert bool_value("{neq({2},{3})}") == "true"
        assert bool_value("{neq({2},{2})}") == "false"

    def test_fraction_comparison(self) -> None:
        source = "{lt({frac({1},{2})},{frac({2},{3})})}"
        assert bool_value(source) == "true"
        assert step_keys(source) == [
            "frac_expand_lcd_msg",
            "frac_expand_lcd_msg",
            "mul_with_one",
            "mul",
            "mul",
            "mul",
            "compare_frac_nom",
            "compare_ineq",
        ]

    def test_same_denominator_compares_numerators(self) -> None:
        source = "{lt({frac({2},{5})},{frac({3},{5})})}"
        assert bool_value(source) == "true"
        assert step_keys(source) == ["compare_frac_nom", "compare_ineq"]

    def test_fraction_comparison_with_equal_numerators(self) -> None:
        source = "{lt({frac({1},{2})},{frac({1},{3})})}"
        assert bool_value(source) == "false"
        assert step_keys(source) == ["compare_frac_den", "compare_ineq"]

    def test_variable_relation_is_inequality(self) -> None:
        # С переменной сравнение не запускается — работает модуль неравенств.
        answer = solution_of("{lt({x},{2})}")
        assert answer.type is T.LESS_THAN


class TestOrder:
    def test_registered(self) -> None:
        assert T.ORDER in registered_types()

    def test_sorted(self) -> None:
        source = "{order({3},{1},{2})}"
        answer = solution_of(source)
        assert answer.type is T.ORDER
        assert [child.value for child in answer.children] == ["1", "2", "3"]
        assert step_keys(source) == []

    def test_already_sorted(self) -> None:
        answer = solution_of("{order({1},{2},{3})}")
        assert [child.value for child in answer.children] == ["1", "2", "3"]

    def test_children_are_folded(self) -> None:
        source = "{order({1+1},{1})}"
        answer = solution_of(source)
        assert [child.value for child in answer.children] == ["1", "2"]
        assert step_keys(source) == ["add"]
