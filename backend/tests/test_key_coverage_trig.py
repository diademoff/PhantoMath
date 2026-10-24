"""Ключи карточек тригонометрии.

Проверяются карточки:

* перевод угла по формуле (``trig_convert_formula`` /
  ``trig_convert_deg_to_rad``) и подпись способа
  (``trig_convert_formula_msg`` / ``trig_convert_deg_to_rad_msg``);
* положительный и отрицательный котерминальные углы
  (``trig_add_multiple_full``, ``trig_sub_multiple_full``,
  ``trig_coter_add_multiple``, ``trig_coter_sub_multiple``,
  ``trig_angle_add_coter``, ``trig_angle_sub_coter``,
  ``trig_add_rotation_msg``, ``trig_sub_rotation_short``,
  ``trig_pos_conteminal``, ``trig_neg_conteminal``);
* подпись способа вычисления значения ``trig_func_calc``;
* простое тригонометрическое уравнение ``trig_eq_simple_solution``;
* нули знаменателя в ``sin x = cos x``: ``trig_eq_find_restricted_zero``.

Ключи графика (``graph_rt_info_*``/``graph_rt_annotation_*``) сюда не входят:
они живут в ``info``/``plot``, которых наш контракт не несёт.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from mymath_backend import load_explanations
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult, ResultGroupType
from mymath_backend.solver import solve

EXPLANATIONS = Path(__file__).resolve().parents[1] / "mymath_backend" / "data" / "explanations.json"

TRIG_KEYS = {
    "trig_add_multiple_full",
    "trig_add_rotation_msg",
    "trig_angle_add_coter",
    "trig_angle_sub_coter",
    "trig_convert_deg_to_rad",
    "trig_convert_deg_to_rad_msg",
    "trig_convert_formula",
    "trig_convert_formula_msg",
    "trig_coter_add_multiple",
    "trig_coter_sub_multiple",
    "trig_eq_find_restricted_zero",
    "trig_eq_simple_solution",
    "trig_func_calc",
    "trig_neg_conteminal",
    "trig_pos_conteminal",
    "trig_sub_multiple_full",
    "trig_sub_rotation_short",
}


def _methods(source: str, command: str | None = None) -> list[CoreSolverVerticalResult]:
    data = solve(parse_protocol(source), command=command)
    group = data.result.group(ResultGroupType.VERTICAL)
    assert group is not None, f"{source}: нет вертикальной ветки"
    return [
        CoreSolverVerticalResult.from_contract(entry.result)
        for entry in group.entries
        if entry.result and "steps" in entry.result
    ]


def _substep_keys(vertical: CoreSolverVerticalResult) -> list[str]:
    return [
        sub.description.type
        for step in vertical.steps
        for sub in step.substeps
        if sub.description is not None
    ]


def _rich_text_keys(value: Any, out: set[str]) -> None:
    """Все ключи ``CoreRichText`` в контракте, включая заголовки методов."""
    if isinstance(value, dict):
        if "args" in value and isinstance(value.get("type"), str) and "children" not in value:
            out.add(value["type"])
        for item in value.values():
            _rich_text_keys(item, out)
    elif isinstance(value, list):
        for item in value:
            _rich_text_keys(item, out)


def _all_rich_keys(source: str, command: str | None = None) -> set[str]:
    data = solve(parse_protocol(source), command=command)
    out: set[str] = set()
    _rich_text_keys(data.to_contract(), out)
    return out


class TestAngleConversion:
    def test_degrees_conversion_rows(self) -> None:
        methods = _methods("{frac({pi},{2})}", "to_degrees")
        assert [method.header.type for method in methods if method.header] == [
            "rewrite_in_deg",
            "trig_pos_conteminal",
            "trig_neg_conteminal",
        ]
        assert _substep_keys(methods[0]) == [
            "trig_convert_formula",
            "frac_reduce_out_expr",
            "frac_reduce_out_expr",
        ]
        assert methods[0].steps[0].step_headers[0].type == "trig_convert_formula_msg"

    def test_pi_conversion_has_one_reduction(self) -> None:
        methods = _methods("{pi}", "to_degrees")
        assert _substep_keys(methods[0]) == ["trig_convert_formula", "frac_reduce_out_expr"]

    def test_radians_conversion_rows(self) -> None:
        methods = _methods("{deg({90})}", "to_radians")
        assert methods[0].header is not None
        assert methods[0].header.type == "rewrite_in_rad"
        assert _substep_keys(methods[0]) == ["trig_convert_deg_to_rad", "simplify"]
        assert methods[0].steps[0].step_headers[0].type == "trig_convert_deg_to_rad_msg"

    @pytest.mark.parametrize(
        ("source", "command"),
        [
            ("{pi}", "to_degrees"),
            ("{frac({pi},{2})}", "to_degrees"),
            ("{deg({90})}", "to_radians"),
        ],
    )
    def test_coterminal_methods(self, source: str, command: str) -> None:
        methods = _methods(source, command)
        positive, negative = methods[1], methods[2]
        assert _substep_keys(positive) == [
            "trig_coter_add_multiple",
            "trig_angle_add_coter",
            "mul_with_one",
            "sum_suffix" if source == "{pi}" else "calc_sum",
        ]
        assert [step.step_headers[0].type for step in positive.steps] == [
            "trig_add_multiple_full",
            "trig_add_rotation_msg",
            "calculate_short",
            "sum_suffix" if source == "{pi}" else "calculate_short",
        ]
        assert _substep_keys(negative) == [
            "trig_coter_sub_multiple",
            "trig_angle_sub_coter",
            "mul_with_one",
            "sum_suffix" if source == "{pi}" else "calc_diff",
        ]
        assert [step.step_headers[0].type for step in negative.steps] == [
            "trig_sub_multiple_full",
            "trig_sub_rotation_short",
            "calculate_short",
            "sum_suffix" if source == "{pi}" else "calculate_short",
        ]


class TestTrigEquationKeys:
    def test_simple_zero_solution(self) -> None:
        methods = _methods("{=({sin({x})},{0})}")
        assert len(methods) == 1
        substep = methods[0].steps[0].substeps[0]
        assert substep.description is not None
        assert substep.description.type == "trig_eq_simple_solution"
        assert len(substep.description.args) == 4
        assert methods[0].solution is not None
        assert methods[0].solution.type.value == "EQUALS"

    def test_two_sided_restricted_zero(self) -> None:
        methods = _methods("{=({sin({x})},{cos({x})})}")
        assert len(methods) == 1
        leading = methods[0].steps[0].substeps[0]
        assert leading.description is not None
        assert leading.description.type == "eq_linear_div"
        assert leading.subresult is not None
        detail = [
            nested.description.type
            for step in leading.subresult.steps
            for nested in step.substeps
            if nested.description is not None
        ]
        assert detail == [
            "trig_eq_find_restricted_zero",
            "eq_linear",
            "trig_eq_exclude_restricted",
            "using_trans",
        ]
        assert _substep_keys(methods[0]) == [
            "eq_linear_div",
            "trig_eq_isolate",
            "trig_arcus_first",
            "trig_eq_fun_period",
            "rel_restrictions_intersect",
        ]


class TestTrigValueHeader:
    @pytest.mark.parametrize("source", ["{sin({pi/6})}", "{cos({deg({30})})}"])
    def test_value_method_header(self, source: str) -> None:
        methods = _methods(source)
        assert len(methods) == 1
        assert methods[0].header is not None
        assert methods[0].header.type == "trig_func_calc"


def _all_keys(vertical: CoreSolverVerticalResult) -> list[tuple[str, int]]:
    """Ключи с числом аргументов, включая заголовки и экраны подробностей."""
    keys: list[tuple[str, int]] = []
    if vertical.header is not None:
        keys.append((vertical.header.type, len(vertical.header.args)))
    for step in vertical.steps:
        for header in step.step_headers:
            keys.append((header.type, len(header.args)))
        for sub in step.substeps:
            assert sub.description is not None
            keys.append((sub.description.type, len(sub.description.args)))
            if sub.subresult is not None:
                keys.extend(_all_keys(sub.subresult))
    return keys


@pytest.mark.parametrize(
    ("source", "command"),
    [
        ("{pi}", "to_degrees"),
        ("{frac({pi},{2})}", "to_degrees"),
        ("{deg({90})}", "to_radians"),
        ("{sin({pi/6})}", None),
        ("{=({sin({x})},{0})}", None),
        ("{=({sin({x})},{cos({x})})}", None),
    ],
)
def test_new_trig_keys_exist_with_matching_arity(source: str, command: str | None) -> None:
    explanations = load_explanations(str(EXPLANATIONS))
    problems: list[str] = []
    for vertical in _methods(source, command):
        for key, arguments in _all_keys(vertical):
            if key not in explanations:
                problems.append(f"{source}: ключа {key!r} нет в словаре")
                continue
            template = explanations.raw_template(key, DEFAULT_LOCALE) or ""
            used = {int(match) for match in re.findall(r"ARG(\d+)", template)}
            declared = explanations.arity(key)
            if declared != max(used, default=0):
                problems.append(f"{source}: у {key!r} арность {declared}, шаблон использует {used}")
            if arguments != declared:
                problems.append(
                    f"{source}: у {key!r} передано {arguments} аргументов, нужно {declared}"
                )
    assert problems == []


def test_sample_inputs_cover_every_trig_key() -> None:
    """Набор входов волны действительно доходит до всех 17 тригонометрических ключей."""
    emitted: set[str] = set()
    for source, command in [
        ("{pi}", "to_degrees"),
        ("{frac({pi},{2})}", "to_degrees"),
        ("{deg({90})}", "to_radians"),
        ("{sin({pi/6})}", None),
        ("{=({sin({x})},{0})}", None),
        ("{=({sin({x})},{cos({x})})}", None),
    ]:
        emitted |= _all_rich_keys(source, command)
    assert emitted >= TRIG_KEYS, sorted(TRIG_KEYS - emitted)
