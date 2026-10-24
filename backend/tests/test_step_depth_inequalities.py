"""Глубина шагов неравенств.

Экраны учебных карточек (``lesson_*``) в ожидание не входят: лишние ключи
уроков расхождением не считаются.

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

_LINEAR_DIVISION = ["ineq_linear_div", "div_with_self", "quotient"]
_MOVE_CONSTANT = ["rel_swap_right_const", "sub_with_self_remove_num"]
_MOVE_CONSTANT_ZERO = [*_MOVE_CONSTANT, "add_with_zero"]
_STEP_ROOT = [
    ("ineq_pow_sqrt_root", ["ineq_pow_sqrt_root", "root_reduce", "root_square"]),
]
_FACTORED = [
    ("write_as_diff_fact", []),
    ("extract_arg", []),
    ("extract_arg", []),
    ("extract_arg", []),
    ("ineq_product_p_two", []),
    ("ineq_linear", _MOVE_CONSTANT_ZERO),
    ("ineq_linear", _MOVE_CONSTANT_ZERO),
    ("ineq_linear", _MOVE_CONSTANT_ZERO),
    ("ineq_linear", _MOVE_CONSTANT_ZERO),
    ("intersection", []),
    ("intersection", []),
    ("union", []),
]

# (имя, вход, [(ключ, [ключи экрана подробностей]), ...] по способам решения)
CASES: list[tuple[str, str, list[list[tuple[str, list[str]]]]]] = [
    (
        "ineq_lin",
        "{<({2x+1},{5})}",
        [
            [
                ("rel_move_right_const_ineq", _MOVE_CONSTANT),
                ("sub", []),
                ("ineq_linear_div", _LINEAR_DIVISION),
            ]
        ],
    ),
    (
        "ineq_gt",
        "{>({3x-2},{7})}",
        [
            [
                ("rel_move_right_const_ineq", _MOVE_CONSTANT),
                ("add", []),
                ("ineq_linear_div", _LINEAR_DIVISION),
            ]
        ],
    ),
    (
        "ineq_neg",
        "{<({-2x},{4})}",
        [
            [
                ("ineq_linear_div_neg", []),
                ("div_with_self", []),
                ("div_pos_neg", []),
                ("quotient", []),
            ]
        ],
    ),
    (
        "ineq_both",
        "{<({3x-2},{x+4})}",
        [
            [
                (
                    "rel_move_left_var",
                    ["rel_swap_left_var", "sub_with_self_remove_alg"],
                ),
                ("rel_move_right_const_ineq", _MOVE_CONSTANT),
                (
                    "sum_suffix",
                    ["sum_suffix_add_neg_one", "sum_suffix_sub_detail", "sub"],
                ),
                ("add", []),
                ("ineq_linear_div", _LINEAR_DIVISION),
            ]
        ],
    ),
    (
        "ineq_both2",
        "{>({2x-5},{x+3})}",
        [
            [
                (
                    "rel_move_left_var",
                    ["rel_swap_left_var", "sub_with_self_remove_alg"],
                ),
                ("rel_move_right_const_ineq", _MOVE_CONSTANT),
                (
                    "sum_suffix",
                    [
                        "sum_suffix_add_neg_one",
                        "sum_suffix_sub_detail",
                        "sub",
                        "sum_suffix_del_one",
                    ],
                ),
                ("add", []),
            ]
        ],
    ),
    (
        "less_or_equal",
        "{<=({3x},{6})}",
        [[("ineq_linear_div", []), ("div_with_self", []), ("quotient", [])]],
    ),
    (
        "greater_than_move",
        "{>({x+3},{5})}",
        [[("rel_move_right_const_ineq", _MOVE_CONSTANT), ("sub", [])]],
    ),
    (
        "ineq_div",
        "{>({frac({x},{2})},{3})}",
        [[("ineq_mul_direct", []), ("frac_reduce_out", []), ("mul", [])]],
    ),
    (
        "quad_less",
        "{lt({x^2-5x+6},{0})}",
        [_FACTORED],
    ),
    (
        "quad_greater",
        "{gt({x^2-5x+6},{0})}",
        [_FACTORED],
    ),
    (
        "quad_less_equal",
        "{lte({x^2-5x+6},{0})}",
        [_FACTORED],
    ),
    (
        "square_below",
        "{<({x^2-9},{0})}",
        [
            [
                ("rel_move_right_const_ineq", _MOVE_CONSTANT_ZERO),
                *_STEP_ROOT,
                ("ineq_separate_abs", []),
                ("intersection", []),
                ("ineq_linear", ["ineq_mul_direct_neg", "mul_with_neg_one", "mul_with_one"]),
                ("intersection", []),
                ("union", []),
            ]
        ],
    ),
    (
        "square_above",
        "{>({x^2-4},{0})}",
        [
            [
                ("rel_move_right_const_ineq", _MOVE_CONSTANT_ZERO),
                *_STEP_ROOT,
                ("ineq_separate_abs", []),
                ("intersection", []),
                ("ineq_linear", ["ineq_mul_direct_neg", "mul_with_neg_one", "mul_with_one"]),
                ("intersection", []),
                ("union", []),
            ]
        ],
    ),
    (
        "square_always_positive",
        "{>({x^2+1},{0})}",
        [
            [
                ("rel_move_right_const_ineq", _MOVE_CONSTANT_ZERO),
                ("rel_terminators_pow_all_sol", []),
            ]
        ],
    ),
    (
        "square_never_negative",
        "{<({x^2+1},{0})}",
        [
            [
                ("rel_move_right_const_ineq", _MOVE_CONSTANT_ZERO),
                ("rel_terminators_pow_no_sol", []),
            ]
        ],
    ),
    (
        "abs_less_than",
        "{lt({abs({x})},{2})}",
        [
            [
                ("ineq_separate_abs", []),
                ("intersection", []),
                ("ineq_linear", ["ineq_mul_direct_neg", "mul_with_neg_one", "mul_with_one"]),
                ("intersection", []),
                ("union", []),
            ]
        ],
    ),
    (
        "abs_greater_union",
        "{gt({abs({x})},{3})}",
        [
            [
                ("ineq_separate_abs", []),
                ("intersection", []),
                ("ineq_linear", ["ineq_mul_direct_neg", "mul_with_neg_one", "mul_with_one"]),
                ("intersection", []),
                ("union", []),
            ]
        ],
    ),
    (
        "abs_shifted",
        "{lte({abs({x-1})},{2})}",
        [
            [
                ("ineq_separate_abs", []),
                ("ineq_linear", ["rel_move_right_const_ineq", "add"]),
                ("ineq_linear", _MOVE_CONSTANT_ZERO),
                (
                    "ineq_linear",
                    ["ineq_linear_neg", "rel_move_right_const_ineq", "calc_sum"],
                ),
                ("ineq_linear", _MOVE_CONSTANT_ZERO),
                ("intersection", []),
                ("intersection", []),
                ("union", []),
            ]
        ],
    ),
    (
        "comparison_equals",
        "{eq({2},{2})}",
        [[("compare_eq_eq", [])]],
    ),
    (
        # The app also offers cross-multiplication as a second way; the entry point
        # currently shows one way per comparison, so the default (LCD) card is pinned.
        "comparison_fractions",
        "{lt({frac({1},{2})},{frac({2},{3})})}",
        [
            [
                ("frac_expand_lcd_msg", []),
                ("frac_expand_lcd_msg", []),
                ("mul_with_one", []),
                ("mul", []),
                ("mul", []),
                ("mul", []),
                ("compare_frac_nom", []),
                ("compare_ineq", []),
            ]
        ],
    ),
    (
        "quotient_inside",
        "{gte({frac({x-1},{x+1})},{0})}",
        [
            [
                ("ineq_quotient_gte", []),
                ("ineq_linear", _MOVE_CONSTANT_ZERO),
                ("ineq_linear", _MOVE_CONSTANT_ZERO),
                ("ineq_linear", _MOVE_CONSTANT_ZERO),
                ("ineq_linear", _MOVE_CONSTANT_ZERO),
                ("intersection", []),
                ("intersection", []),
                ("union", []),
            ]
        ],
    ),
    (
        "rational_constant_over_linear",
        "{lt({frac({1},{x-1})},{2})}",
        [
            [
                (
                    "rel_restrictions_range",
                    [
                        "rel_restrictions_den_zero",
                        "eq_linear",
                        "rel_restrictions_range_complement",
                    ],
                ),
                ("rel_move_left_const", ["rel_swap_left_const", "sub_with_self_num"]),
                (
                    "frac_sum_join",
                    ["frac_expand_int", "frac_sum_expand", "mul_with_one", "frac_sum_join"],
                ),
                ("mul_bracket", ["mul_bracket_each", "mul_with_neg_one"]),
                ("add", []),
                ("ineq_quotient_lt", []),
                ("ineq_linear", ["rel_move_right_const_ineq", "ineq_linear_div_neg"]),
                ("ineq_linear", _MOVE_CONSTANT_ZERO),
                ("ineq_linear", ["rel_move_right_const_ineq", "ineq_linear_div_neg"]),
                ("ineq_linear", _MOVE_CONSTANT_ZERO),
                ("intersection", []),
                ("intersection", []),
                ("union", []),
                ("rel_restrictions_intersect", []),
            ]
        ],
    ),
    (
        "rational_variable_over_difference",
        "{gt({frac({x},{x-2})},{3})}",
        [
            [
                (
                    "rel_restrictions_range",
                    [
                        "rel_restrictions_den_zero",
                        "eq_linear",
                        "rel_restrictions_range_complement",
                    ],
                ),
                ("rel_move_left_const", ["rel_swap_left_const", "sub_with_self_num"]),
                (
                    "frac_sum_join",
                    ["frac_expand_int", "frac_sum_expand", "mul_with_one", "frac_sum_join"],
                ),
                ("mul_bracket", ["mul_bracket_each", "mul"]),
                (
                    "sum_suffix",
                    ["sum_suffix_add_one", "sum_suffix_sub_detail", "calc_diff"],
                ),
                ("extract_arg", []),
                ("ineq_quotient_gt", []),
                ("ineq_linear", ["ineq_linear_div_neg", "rel_move_right_const_ineq"]),
                ("ineq_linear", _MOVE_CONSTANT_ZERO),
                ("ineq_linear", ["ineq_linear_div_neg", "rel_move_right_const_ineq"]),
                ("ineq_linear", _MOVE_CONSTANT_ZERO),
                ("intersection", []),
                ("intersection", []),
                ("union", []),
                ("rel_restrictions_intersect", []),
            ]
        ],
    ),
    (
        "transcendental_exponential",
        "{lt({2^x},{8})}",
        [[("pow_to_same_base", []), ("compare_exp_alg", [])]],
    ),
    (
        "transcendental_logarithmic",
        "{gte({log({x},{2})},{3})}",
        [
            [
                (
                    "rel_restrictions_range",
                    ["rel_restrictions_log_arg", "rel_restrictions_range_complement"],
                ),
                ("ineq_log_formula_gt_xab_pow", []),
                ("pow", ["pow_to_mul", "mul"]),
                ("rel_restrictions_intersect", []),
            ]
        ],
    ),
    (
        "transcendental_irrational",
        "{lt({root2({x+1})},{x-1})}",
        [
            [
                (
                    "rel_restrictions_range",
                    [
                        "rel_restrictions_root_base_neg",
                        "ineq_linear",
                        "rel_restrictions_range_complement",
                    ],
                ),
                ("ineq_separate_root", []),
                ("ineq_linear", ["ineq_irrational_square", "ineq_linear"]),
                ("ineq_linear", _MOVE_CONSTANT_ZERO),
                ("rel_terminators_pos_zero_neg_false", []),
                ("ineq_linear", _MOVE_CONSTANT_ZERO),
                ("intersection", []),
                ("intersection", []),
                ("union", []),
                ("rel_restrictions_intersect", []),
            ]
        ],
    ),
    (
        "ineq_delete_opposite_terms",
        "{>({3x-2},{-2})}",
        [
            [
                ("ineq_del_opp", []),
                ("ineq_linear_div", ["ineq_linear_div", "div_with_self", "div_zero"]),
            ]
        ],
    ),
    (
        "abs_less_than_zero",
        "{<({abs({x})},{0})}",
        [[("rel_terminators_left_pos_zero_false", [])]],
    ),
    (
        "square_above_zero",
        "{>({x^2-0},{0})}",
        [
            [
                ("add_with_zero", []),
                ("rel_terminators_left_pos_zero_true_except", []),
                ("eq_linear", ["eq_quad_exp_zero"]),
                ("ineq_pow_diff", []),
            ]
        ],
    ),
    (
        "odd_cube_root",
        "{>({x^3+1},{0})}",
        [
            [
                (
                    "rel_move_right_const_ineq",
                    ["rel_swap_right_const", "sub_with_self_remove_num", "add_with_zero"],
                ),
                ("ineq_pow_root_var", ["ineq_pow_root_var", "root_reduce", "root_cube"]),
            ]
        ],
    ),
    (
        "negative_odd_power",
        "{>({x^-3+1},{0})}",
        [
            [
                (
                    "rel_restrictions_range",
                    ["rel_restrictions_base_zero_neg", "rel_restrictions_range_complement"],
                ),
                ("pow_flip_msg", []),
                (
                    "frac_sum_join",
                    [
                        "frac_expand_int",
                        "frac_sum_expand",
                        "mul_with_one",
                        "mul_with_one",
                        "frac_sum_join",
                    ],
                ),
                ("ineq_quotient_gt", []),
                ("ineq_linear", ["rel_move_right_const_ineq", "ineq_pow_root_var"]),
                ("ineq_linear", ["ineq_pow_odd_zero"]),
                ("ineq_linear", ["rel_move_right_const_ineq", "ineq_pow_root_var"]),
                ("ineq_linear", ["ineq_pow_odd_zero"]),
                ("intersection", []),
                ("intersection", []),
                ("union", []),
                ("rel_restrictions_intersect", []),
            ]
        ],
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
    """Ключ каждого подшага и ключи его экрана подробностей (без наших ``lesson_*``)."""
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
                    and not nested.description.type.startswith("lesson_")
                ]
            outline.append((sub.description.type, detail))
    return outline


@pytest.mark.parametrize(("name", "proto", "methods"), CASES, ids=[case[0] for case in CASES])
def test_inequality_step_depth_matches(
    name: str, proto: str, methods: list[list[tuple[str, list[str]]]]
) -> None:
    entries = _entries(proto)
    assert len(entries) == len(methods), (
        f"{name}: способов {len(entries)}, ожидалось {len(methods)}"
    )
    for index, (entry, expected) in enumerate(zip(entries, methods, strict=True)):
        assert _outline(entry) == expected, f"{name}: способ {index}"


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


@pytest.mark.parametrize(("name", "proto", "_methods"), CASES, ids=[case[0] for case in CASES])
def test_every_inequality_key_exists_with_matching_arity(
    name: str, proto: str, _methods: Any
) -> None:
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


POWER_RESTRICTIONS = [
    ("power-zero", "{<({x^0-5x+6},{0})}", "rel_restrictions_base_zero_zero"),
    ("power-negative", "{<({x^-1-5x+6},{0})}", "rel_restrictions_base_zero_neg"),
    ("power-fractional", "{<({x^0.5-5x+6},{0})}", "rel_restrictions_exp_neg_base"),
]


@pytest.mark.parametrize(
    ("name", "proto", "find_key"), POWER_RESTRICTIONS, ids=[case[0] for case in POWER_RESTRICTIONS]
)
def test_power_restriction_card_comes_first(name: str, proto: str, find_key: str) -> None:
    """The domain card of the verified power variants.

    Only this card is ours: the rewriting rows that follow
    (``pow_with_zero``/``pow_flip_one``/``using_trans``) live in the powers module.
    """
    entry = _entries(proto)[0]
    first = entry.steps[0]
    assert [header.type for header in first.step_headers] == ["rel_restrictions_range"], name
    sub = first.substeps[0]
    assert sub.description is not None and sub.description.type == "rel_restrictions_range"
    detail = [
        nested.description.type
        for nested_step in (sub.subresult.steps if sub.subresult else [])
        for nested in nested_step.substeps
        if nested.description is not None
    ]
    assert detail == [find_key, "rel_restrictions_range_complement"], name
    top_level = [
        item.description.type
        for step in entry.steps
        for item in step.substeps
        if item.description is not None
    ]
    assert "rel_restrictions_find" not in top_level, name


WAVE4_KEYS = [
    (
        "quadratic-find-a",
        "{<({x^2-5x+6},{-3})}",
        ["ineq_quad_to_eq_quad", "eq_linear", "ineq_quad_find_a", "ineq_quad_lead_pos_f"],
    ),
    (
        "quadratic-substitute-roots",
        "{<({x^2-5x+6},{3})}",
        ["ineq_quad_substitute_expr_no_coeff", "ineq_product_p_two"],
    ),
    (
        "negative-even-power-true",
        "{>({x^-2+1},{0})}",
        ["rel_restrictions_range", "rel_terminators_left_pos_true"],
    ),
]


@pytest.mark.parametrize(
    ("name", "proto", "expected"), WAVE4_KEYS, ids=[case[0] for case in WAVE4_KEYS]
)
def test_wave4_quadratic_and_terminator_keys(name: str, proto: str, expected: list[str]) -> None:
    """Keys of the partial cards; the remaining the app rows live in other modules."""
    entry = _entries(proto)[0]
    keys = [
        sub.description.type
        for step in entry.steps
        for sub in step.substeps
        if sub.description is not None
    ]
    missing = [key for key in expected if key not in keys]
    assert not missing, f"{name}: нет ключей {missing} в {keys}"
