"""Тесты модуля дробей.

Дроби приходят узлом ``FRACTION`` (из редактора) или ``FRACTION_MIXED``, а
не знаком ``/``: знак ``/`` разбирается арифметикой как деление. Проверяем,
что дробь сворачивается в число, сокращается с нужным шагом и что смешанное
число переводится в неправильную дробь.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from mymath_backend import CoreNode, load_explanations
from mymath_backend import CoreNodeType as T
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import SolveError, registered_types, solve

EXPLANATIONS = Path(__file__).resolve().parents[2] / "truth" / "data" / "explanations.json"


def frac(num: CoreNode, den: CoreNode) -> CoreNode:
    return CoreNode.node(T.FRACTION, num, den)


def vertical(source: CoreNode) -> CoreSolverVerticalResult:
    vertical_ = solve(source).result.vertical()
    assert vertical_ is not None
    return vertical_


def value_of(node: CoreNode) -> str | None:
    solution = vertical(node).solution
    assert solution is not None
    return solution.value


def step_keys(node: CoreNode) -> list[str]:
    vertical_ = vertical(node)
    return [sub.description.type for step in vertical_.steps for sub in step.substeps]


def args_of(node: CoreNode) -> list[list[str]]:
    vertical_ = vertical(node)
    return [
        [arg.value or "" for arg in sub.description.args]
        for step in vertical_.steps
        for sub in step.substeps
    ]


C2 = CoreNode.constant("2")
C4 = CoreNode.constant("4")


class TestFractions:
    def test_integer_result(self) -> None:
        assert value_of(frac(CoreNode.constant("6"), C2)) == "3"

    def test_reduced_to_lowest_terms(self) -> None:
        assert value_of(frac(CoreNode.constant("6"), CoreNode.constant("8"))) == "3/4"

    def test_already_reduced_has_no_step(self) -> None:
        assert step_keys(frac(CoreNode.constant("1"), CoreNode.constant("3"))) == []

    def test_reduction_uses_gcd_step(self) -> None:
        keys = step_keys(frac(C4, CoreNode.constant("8")))
        assert keys == ["frac_reduce_reduce", "frac_reduce_out"]
        assert args_of(frac(C4, CoreNode.constant("8"))) == [[], ["4"]]

    def test_reduction_marks_crossed_parts(self) -> None:
        """Микро-анимация: сокращаемые числитель и знаменатель зачёркнуты."""
        step = next(
            sub for s in vertical(frac(C4, CoreNode.constant("8"))).steps for sub in s.substeps
        )
        assert step.left is not None
        assert [child.crossed for child in step.left.children] == [True, True]

    def test_nested_numerator_is_folded_first(self) -> None:
        numerator = CoreNode.node(T.ADD, CoreNode.constant("1"), CoreNode.constant("1"))
        keys = step_keys(frac(numerator, C4))
        assert keys == ["add", "frac_reduce_reduce", "frac_reduce_out"]
        assert value_of(frac(numerator, C4)) == "1/2"

    def test_division_by_zero(self) -> None:
        with pytest.raises(SolveError):
            solve(frac(CoreNode.constant("1"), CoreNode.constant("0")))

    def test_variable_in_fraction_is_rejected(self) -> None:
        with pytest.raises(SolveError):
            solve(frac(CoreNode.variable("x"), C2))


class TestWithArithmetic:
    def test_fractions_are_added(self) -> None:
        node = CoreNode.node(
            T.ADD,
            frac(CoreNode.constant("1"), CoreNode.constant("3")),
            frac(CoreNode.constant("1"), CoreNode.constant("6")),
        )
        assert value_of(node) == "1/2"

    def test_fraction_times_number(self) -> None:
        node = CoreNode.node(
            T.MULTIPLY,
            frac(CoreNode.constant("2"), CoreNode.constant("3")),
            CoreNode.constant("3"),
        )
        assert value_of(node) == "2"


class TestMixed:
    def test_mixed_to_improper(self) -> None:
        node = CoreNode.node(
            T.FRACTION_MIXED,
            CoreNode.constant("2"),
            CoreNode.constant("1"),
            CoreNode.constant("3"),
        )
        assert value_of(node) == "7/3"
        assert step_keys(node) == ["convert_mixed_number"]


class TestExplanationKeys:
    def test_keys_exist_with_matching_arity(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        problems: list[str] = []
        samples = [
            frac(C4, CoreNode.constant("8")),
            CoreNode.node(
                T.FRACTION_MIXED,
                CoreNode.constant("2"),
                CoreNode.constant("1"),
                CoreNode.constant("3"),
            ),
        ]
        for node in samples:
            for key in step_keys(node):
                if key not in explanations:
                    problems.append(f"ключа {key} нет в словаре")
                    continue
                template = explanations.raw_template(key, DEFAULT_LOCALE) or ""
                used = {int(m) for m in re.findall(r"ARG(\d+)", template)}
                highest = max(used) if used else 0
                if highest != explanations.arity(key):
                    problems.append(f"у {key} арность {explanations.arity(key)}")
        assert problems == []


class TestRegistration:
    def test_registered(self) -> None:
        assert {T.FRACTION, T.FRACTION_MIXED} <= registered_types()
