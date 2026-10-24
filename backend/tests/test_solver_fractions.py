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

EXPLANATIONS = Path(__file__).resolve().parents[1] / "mymath_backend" / "data" / "explanations.json"


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


class TestFractionSums:
    def one(self, n: str) -> CoreNode:
        return CoreNode.constant(n)

    def test_three_fractions_are_one_addition(self) -> None:
        # common denominator, sum of numerators, 6/6 = 1.
        problem = CoreNode.node(
            T.ADD,
            frac(self.one("1"), self.one("2")),
            frac(self.one("1"), self.one("3")),
            frac(self.one("1"), self.one("6")),
        )
        assert step_keys(problem) == ["frac_sum_common", "sum_real_positive", "div_with_self"]
        assert value_of(problem) == "1"

    def test_nested_sum_of_fractions_is_flattened(self) -> None:
        inner = CoreNode.node(
            T.ADD, frac(self.one("1"), self.one("2")), frac(self.one("1"), self.one("3"))
        )
        problem = CoreNode.node(T.ADD, inner, frac(self.one("1"), self.one("6")))
        assert step_keys(problem) == ["frac_sum_common", "sum_real_positive", "div_with_self"]


class TestFractions:
    def test_integer_result(self) -> None:
        assert value_of(frac(CoreNode.constant("6"), C2)) == "3"

    def test_reduced_to_lowest_terms(self) -> None:
        assert value_of(frac(CoreNode.constant("6"), CoreNode.constant("8"))) == "3/4"

    def test_already_reduced_has_no_step(self) -> None:
        assert step_keys(frac(CoreNode.constant("1"), CoreNode.constant("3"))) == []

    def test_denominator_one_gets_step(self) -> None:
        """`frac(6,1)` — то же деление на единицу, что и `6 ÷ 1`.

        Без шага экран «Шаги по решению» оставался пустым, хотя запись
        менялась (`frac(6,1)` → `6`), и одинаковые на вид `6/1` и `6 ÷ 1`
        давали разное число шагов.
        """
        node = frac(CoreNode.constant("6"), CoreNode.constant("1"))
        assert step_keys(node) == ["div_with_one"]
        assert args_of(node) == [["1"]]
        assert value_of(node) == "6"

    def test_reduction_divides_then_performs_both_divisions(self) -> None:
        node = frac(C4, CoreNode.constant("8"))
        assert step_keys(node) == ["frac_div_num", "div", "div"]
        assert args_of(node) == [["4"], [], []]
        # one row divides both parts, the next row has one stage per part.
        assert [len(s.substeps) for s in vertical(node).steps] == [1, 2]

    def test_nested_numerator_is_folded_first(self) -> None:
        numerator = CoreNode.node(T.ADD, CoreNode.constant("1"), CoreNode.constant("1"))
        keys = step_keys(frac(numerator, C4))
        # A computed numerator gets the wrapper card with the reduction nested.
        assert keys == ["add", "frac_reduce_frac_num"]
        assert value_of(frac(numerator, C4)) == "1/2"

    def test_division_by_zero(self) -> None:
        # «Не определено» and the reason, not an error screen.
        problem = frac(CoreNode.constant("1"), CoreNode.constant("0"))
        assert step_keys(problem) == ["div_with_zero"]
        assert vertical(problem).solution is not None
        assert vertical(problem).solution.children[0].value == "undefined"  # type: ignore[union-attr]

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

    def test_fraction_divided_by_a_fraction_has_the_two_rows_of_the_app(self) -> None:
        # (case ``frac_div``: ``- | -``): the app
        # shows «Умножить на обратное значение» and «Сократить числа». The native
        # «запишите дробь в виде частного» and «вычислите произведение» rows are
        # not on screen, so they must not appear here either.
        node = CoreNode.node(
            T.DIVIDE,
            frac(CoreNode.constant("3"), C4),
            frac(CoreNode.constant("1"), C2),
        )
        assert step_keys(node) == ["frac_div_rec", "frac_reduce_out"]
        assert [len(step.substeps) for step in vertical(node).steps] == [1, 1]
        assert value_of(node) == "3/2"

    def test_fraction_division_without_cancellation_opens_the_product(self) -> None:
        # Case ``frac_div_nocancel``: ``- | +`` — the product row has a detail screen.
        node = CoreNode.node(
            T.DIVIDE,
            frac(CoreNode.constant("1"), C2),
            frac(CoreNode.constant("1"), CoreNode.constant("3")),
        )
        assert step_keys(node) == ["frac_div_rec", "product"]
        detail = [step.substeps[0].subresult for step in vertical(node).steps]
        assert detail[0] is None and detail[1] is not None
        assert [
            sub.description.type
            for step in detail[1].steps
            for sub in step.substeps  # type: ignore[union-attr]
        ] == ["frac_mul_join", "mul_with_one", "mul"]
        assert value_of(node) == "3/2"


class TestMixed:
    def test_mixed_to_improper(self) -> None:
        node = CoreNode.node(
            T.FRACTION_MIXED,
            CoreNode.constant("2"),
            CoreNode.constant("1"),
            CoreNode.constant("3"),
        )
        assert value_of(node) == "7/3"
        # the app: ((2*3)+1)/3, then (6+1)/3, then 7/3.
        assert step_keys(node) == ["mfrac_to_frac", "mul", "add"]


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
