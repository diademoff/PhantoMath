"""Тесты модуля арифметики.

Проверяются три вещи: правильность значения, порядок шагов (снизу вверх, как
порядок действий) и то, что ключи пояснений существуют в словаре объяснений
и имеют ту арность, с которой их вызывает решатель.
"""

from __future__ import annotations

import re
from fractions import Fraction
from pathlib import Path

import pytest

from mymath_backend import CoreNode, load_explanations
from mymath_backend import CoreNodeType as T
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.input import parse_protocol
from mymath_backend.solver import SolveError, registered_types, solve
from mymath_backend.solver.base import SolveContext, SolveResult, route

EXPLANATIONS = Path(__file__).resolve().parents[2] / "truth" / "data" / "explanations.json"


def answer_of(source: str) -> str | None:
    """Значение ответа для строки протокола."""
    data = solve(parse_protocol(source))
    vertical = data.result.vertical()
    assert vertical is not None
    return vertical.solution.value if vertical.solution else None


def steps_of(source: str) -> list[tuple[str | None, str | None, str]]:
    """Подшаги в виде ``(left, right, ключ пояснения)``."""
    data = solve(parse_protocol(source))
    vertical = data.result.vertical()
    assert vertical is not None
    out: list[tuple[str | None, str | None, str]] = []
    for step in vertical.steps:
        for sub in step.substeps:
            out.append(
                (
                    sub.left.value if sub.left else None,
                    sub.right.value if sub.right else None,
                    sub.description.type,
                )
            )
    return out


class TestValues:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("{42}", "42"),
            ("{2+3}", "5"),
            ("{2-3}", "-1"),
            ("{2*3}", "6"),
            ("{8/2}", "4"),
            ("{2+3*4}", "14"),
            ("{2*3+4}", "10"),
            ("{2+3+4}", "9"),
            ("{2+3*4-5}", "9"),
            ("{2*(3+4)}", "14"),
            ("{(2+3)*4}", "20"),
            ("{2^3}", "8"),
            ("{2^3^2}", "512"),
            ("{-2}", "-2"),
            ("{2.5+0.5}", "3"),
            ("{1/3+1/6}", "1/2"),
            ("{1/2*2}", "1"),
            ("{10/4}", "5/2"),
        ],
    )
    def test_value(self, source: str, expected: str) -> None:
        assert answer_of(source) == expected

    def test_exact_rationals_not_floats(self) -> None:
        """Дроби считаются точно: 1/3+1/3 не превращается в 0.666…."""
        assert answer_of("{1/3+1/3}") == "2/3"
        assert Fraction(answer_of("{0.1+0.2}")) == Fraction(3, 10)

    def test_fraction_format(self) -> None:
        assert answer_of("{4/2}") == "2"
        assert answer_of("{3/4}") == "3/4"


class TestErrors:
    @pytest.mark.parametrize("source", ["{5/0}", "{2/(1-1)}"])
    def test_division_by_zero(self, source: str) -> None:
        with pytest.raises(SolveError):
            solve(parse_protocol(source))

    @pytest.mark.parametrize("source", ["{pow({0},{-1})}", "{pow({0},{-2})}", "{0^-3}"])
    def test_zero_in_negative_power(self, source: str) -> None:
        """Ноль в отрицательной степени — деление на ноль, а не падение."""
        with pytest.raises(SolveError, match="деление на ноль"):
            solve(parse_protocol(source))

    def test_deep_expression_is_solve_error(self) -> None:
        """600 уровней — SolveError, а не RecursionError наружу."""
        deep: CoreNode = CoreNode.constant("1")
        for _ in range(600):
            deep = CoreNode.node(T.ADD, deep, CoreNode.constant("1"))
        with pytest.raises(SolveError, match="глубокое"):
            solve(deep)

    def test_variable_is_reported_as_missing_module(self) -> None:
        """Арифметика не решает уравнения -- это разные модули."""
        with pytest.raises(SolveError, match="нужен модуль уравнений"):
            solve(parse_protocol("{2x+3}"))

    def test_huge_exponent_is_rejected(self) -> None:
        with pytest.raises(SolveError, match="показатель степени"):
            solve(parse_protocol("{2^99999}"))

    def test_unsupported_shape_is_reported(self) -> None:
        # Нереализованных типов узлов больше нет (все 143 зарегистрированы),
        # но некорректная форма узла по-прежнему даёт понятную ошибку.
        with pytest.raises(SolveError, match="среднее"):
            solve(CoreNode.node(T.MEAN))


class TestStepOrder:
    def test_innermost_first(self) -> None:
        """``2+3*4``: сначала умножение, потом сложение."""
        assert steps_of("{2+3*4}") == [
            (None, "12", "mul"),
            (None, "14", "add"),
        ]

    def test_power_before_multiplication(self) -> None:
        assert [key for _, _, key in steps_of("{2^3*4}")] == ["calculate_short", "mul"]

    def test_bracket_step_precedes_outer(self) -> None:
        keys = [key for _, _, key in steps_of("{2*(3+4)}")]
        assert keys == ["add", "mul"]

    def test_explanations_for_special_cases(self) -> None:
        assert steps_of("{7/1}")[0][2] == "div_with_one"
        assert steps_of("{3-3}")[0][2] == "sub_with_self"


class TestExplanationKeys:
    """Каждый ключ, который выдаёт решатель, обязан быть в словаре."""

    def test_all_keys_exist_with_matching_arity(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        problems: list[str] = []
        for source in (
            "{2+3}",
            "{2-3}",
            "{2*3}",
            "{8/2}",
            "{2^3}",
            "{7/1}",
            "{3-3}",
            "{2+3*4}",
            "{1/3+1/6}",
        ):
            for _, _, key in steps_of(source):
                if key not in explanations:
                    problems.append(f"{source}: ключа {key} нет в словаре")
                    continue
                declared = explanations.arity(key)
                template = explanations.raw_template(key, DEFAULT_LOCALE) or ""
                used = {int(m) for m in re.findall(r"ARG(\d+)", template)}
                highest = max(used) if used else 0
                if declared != highest:
                    problems.append(
                        f"{source}: у {key} арность {declared}, а шаблон использует {highest}"
                    )
        assert problems == []


class TestRegistration:
    def test_coverage(self) -> None:
        """Модуль зарегистрирован на все типы, которые умеет считать."""
        assert {
            T.CONSTANT,
            T.ADD,
            T.SUBTRACT,
            T.MULTIPLY,
            T.MULTIPLY_IMPLICIT,
            T.DIVIDE,
            T.POWER,
            T.NEGATIVE,
            T.POSITIVE,
            T.BRACKET,
        } <= registered_types()

    def test_geometry_type_registered(self) -> None:
        """Отрезок и его длина (геометрия APK) есть в реестре."""
        assert T.LINE_SEGMENT in registered_types()
        assert T.LINE_SEGMENT_LENGTH in registered_types()

    def test_all_node_types_registered(self) -> None:
        """Все 143 типа узлов контракта имеют модуль решателя."""
        assert registered_types() == set(T)


def test_minus_a_negative_bracket_opens_it_then_sums_on_one_row() -> None:
    # Photomath 7.10.0 on device: -3-(-5) is "open the bracket", then one summing row.
    ctx = SolveContext(SolveResult())
    route(parse_protocol("{-3-(-5)}"), ctx)
    assert [step.key for step in ctx.result] == ["neg_neg_arg", "calc_sum"]


def test_bracket_times_number_offers_the_distributive_property() -> None:
    # Photomath 7.10.0 on device: (2+3)*4 has a second card that distributes the 4.
    group = solve(parse_protocol("{(2+3)*4}")).result.groups[0]
    assert len(group.entries) == 2
    assert solve(parse_protocol("{(2+3)*4*5}")).result.groups[0].select_method_text is None


def test_three_term_sum_with_a_product_is_one_row_after_the_product() -> None:
    # Photomath 7.10.0 on device: 2+3*4-5 is the product, then one row for the whole sum.
    ctx = SolveContext(SolveResult())
    route(parse_protocol("{2+3*4-5}"), ctx)
    assert [step.key for step in ctx.result] == ["mul", "sum"]
