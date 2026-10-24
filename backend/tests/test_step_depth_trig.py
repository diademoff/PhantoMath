"""Глубина шагов тригонометрии и тригонометрических уравнений.

Каждый кейс — вход протокола и последовательность ключей подшагов: ключ
верхнего подшага и, если у него есть экран подробностей (``subresult``), ключи
этого экрана. Заголовки шагов не проверяются — сравнение идёт по ключам
действий.

Дополнительно каждый ключ проверяется по словарю объяснений: ключ существует и
арность совпадает с числом ``ARGn`` в шаблоне (иначе на экране останется
«ARG1»).
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

# (имя, вход, [(ключ, [ключи экрана подробностей]), ...])
CASES: list[tuple[str, str, list[tuple[str, list[str]]]]] = [
    (
        "trig_value_degrees",
        "{sin({deg({30})})}",
        [("trig_table_first", [])],
    ),
    (
        "trig_value_radians",
        "{sin({pi/6})}",
        [("trig_table_first", [])],
    ),
    (
        "trig_product_zero",
        "{cos({2*0})}",
        [("mul_with_zero", []), ("trig_table_first", [])],
    ),
    (
        "trig_coterminal_degrees",
        "{sin({deg({390})})}",
        [("write_as_sum_trig", []), ("using_sim", []), ("trig_table_first", [])],
    ),
    (
        "trig_coterminal_radians",
        "{sin({13pi/6})}",
        [("write_as_sum_trig", []), ("using_sim", []), ("trig_table_first", [])],
    ),
    (
        "trig_coterminal_tangent",
        "{tan({5pi/4})}",
        [("write_as_sum_trig", []), ("using_sim", []), ("trig_table_first", [])],
    ),
    (
        "arcus_first",
        "{asin({frac({1},{2})})}",
        [("trig_arcus_first", [])],
    ),
    (
        "arcus_fourth",
        "{asin({-frac({1},{2})})}",
        [("trig_arcus_fourth", [])],
    ),
    (
        "sine_half",
        "{=({sin({x})},{frac({1},{2})})}",
        [
            ("trig_eq_two_sollutions", []),
            ("trig_eq_isolate", []),
            ("trig_eq_isolate", []),
            ("trig_arcus_first", []),
            ("trig_arcus_first", []),
            ("trig_eq_fun_period", []),
            ("trig_eq_fun_period", []),
            ("eq_linear", ["rel_move_right_const_eq", "calc_diff", "eq_linear_neg"]),
            ("trig_eq_positive_period", []),
            ("solution_eq_num", []),
        ],
    ),
    (
        "cosine_half",
        "{=({cos({x})},{frac({1},{2})})}",
        [
            ("trig_eq_two_sollutions", []),
            ("trig_eq_isolate", []),
            ("trig_eq_isolate", []),
            ("trig_arcus_first", []),
            ("trig_arcus_first", []),
            ("trig_eq_fun_period", []),
            ("trig_eq_fun_period", []),
            ("eq_linear", ["rel_move_right_const_eq", "calc_diff", "eq_linear_neg"]),
            ("trig_eq_positive_period", []),
            ("solution_eq_num", []),
        ],
    ),
    (
        "tangent_one",
        "{=({tan({x})},{1})}",
        [
            (
                "rel_restrictions_range",
                ["trig_eq_exclude_restricted", "rel_restrictions_range_complement"],
            ),
            ("trig_eq_isolate", []),
            ("trig_arcus_first", []),
            ("trig_eq_fun_period", []),
            ("rel_restrictions_intersect", []),
        ],
    ),
    (
        "linear_argument",
        "{=({sin({2x})},{frac({1},{2})})}",
        [
            ("trig_eq_two_sollutions", []),
            ("trig_eq_isolate", []),
            ("trig_eq_isolate", []),
            ("trig_arcus_first", []),
            ("trig_arcus_first", []),
            ("trig_eq_fun_period", []),
            ("trig_eq_fun_period", []),
            (
                "eq_linear",
                [
                    "eq_linear_div",
                    "div_with_self",
                    "mul_bracket",
                    "frac_int_div",
                    "quotient",
                    "frac_mul",
                ],
            ),
            ("eq_linear", ["rel_move_right_const_eq", "calc_diff", "eq_linear_div"]),
            ("trig_eq_positive_period", []),
            ("solution_eq_num", []),
        ],
    ),
    (
        "out_of_range",
        "{=({sin({x})},{2})}",
        [("trig_eq_interval_real", [])],
    ),
]


def _entries(proto: str) -> list[CoreSolverVerticalResult]:
    """Все способы решения одного входа, по порядку."""
    data = solve(parse_protocol(proto))
    group = data.result.group(ResultGroupType.VERTICAL)
    assert group is not None, f"{proto}: нет вертикальной ветки"
    return [
        CoreSolverVerticalResult.from_contract(entry.result)
        for entry in group.entries
        if entry.result and "steps" in entry.result
    ]


def _outline(vertical: CoreSolverVerticalResult) -> list[tuple[str, list[str]]]:
    """Ключ каждого подшага и ключи его экрана подробностей."""
    outline: list[tuple[str, list[str]]] = []
    for step in vertical.steps:
        for sub in step.substeps:
            assert sub.description is not None, "подшаг без пояснения"
            detail: list[str] = []
            if sub.subresult is not None:
                detail = [
                    nested.description.type
                    for nested_step in sub.subresult.steps
                    for nested in nested_step.substeps
                    if nested.description is not None
                ]
            outline.append((sub.description.type, detail))
    return outline


@pytest.mark.parametrize(("name", "proto", "expected"), CASES, ids=[case[0] for case in CASES])
def test_step_depth_matches(name: str, proto: str, expected: list[tuple[str, list[str]]]) -> None:
    entries = _entries(proto)
    assert len(entries) == 1, f"{name}: способов {len(entries)}, ожидался один"
    assert _outline(entries[0]) == expected, f"{name}"


def test_each_trig_transformation_is_its_own_card() -> None:
    """Решатель показывает запись суммой, упрощение и таблицу отдельными шагами."""
    entries = _entries("{sin({deg({390})})}")
    vertical = entries[0]
    assert len(vertical.steps) == 3
    assert [len(step.substeps) for step in vertical.steps] == [1, 1, 1]


def _all_keys(vertical: CoreSolverVerticalResult) -> list[tuple[str, int]]:
    """Все ключи с числом переданных аргументов, включая экраны подробностей."""
    keys: list[tuple[str, int]] = []
    for step in vertical.steps:
        for sub in step.substeps:
            assert sub.description is not None
            keys.append((sub.description.type, len(sub.description.args)))
            if sub.subresult is not None:
                keys.extend(_all_keys(sub.subresult))
    return keys


@pytest.mark.parametrize(("name", "proto", "_expected"), CASES, ids=[case[0] for case in CASES])
def test_every_used_key_exists_with_matching_arity(name: str, proto: str, _expected: Any) -> None:
    explanations = load_explanations(str(EXPLANATIONS))
    problems: list[str] = []
    for entry in _entries(proto):
        for key, arguments in _all_keys(entry):
            if key not in explanations:
                problems.append(f"{name}: ключа {key!r} нет в словаре")
                continue
            template = explanations.raw_template(key, DEFAULT_LOCALE) or ""
            used = {int(match) for match in re.findall(r"ARG(\d+)", template)}
            declared = explanations.arity(key)
            if declared != max(used, default=0):
                problems.append(f"{name}: у {key!r} арность {declared}, шаблон использует {used}")
            if arguments != declared:
                problems.append(
                    f"{name}: у {key!r} передано {arguments} аргументов, нужно {declared}"
                )
    assert problems == []
