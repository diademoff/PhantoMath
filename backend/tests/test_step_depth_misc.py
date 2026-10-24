"""Глубина шагов остальных разделов.

Степени и корни, матрицы, комбинаторика, комплексные числа, дроби и арифметика.

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

Outline = list[tuple[str, list[str]]]

# (имя, вход, [контур способа 0, способа 1, ...])
CASES: list[tuple[str, str, list[Outline]]] = [
    # ── степени, корни, логарифмы ──────────────────────────────────────
    ("sqrt-zero", "{root2({0})}", [[("root_zero", [])]]),
    ("exp-0", "{exp({0})}", [[("pow_with_zero", [])]]),
    ("log10-one", "{log10({1})}", [[("log_arg_one", [])]]),
    ("ln-1", "{ln({1})}", [[("log_arg_one", [])], [("log_rewrite", [])]]),
    ("ln-e", "{ln({\\e})}", [[("log_same_base_arg_ln", [])]]),
    (
        "root-perfect",
        "{root2({16})}",
        [
            [("pow_to_same_base", []), ("root_reduce", [])],
            [("pow_to_same_base", []), ("root_reduce", [])],
        ],
    ),
    (
        "log2-8",
        "{log({8},{2})}",
        [
            [
                ("pow_to_same_base", []),
                ("using_sim", ["using_trans", "log_same_base_arg", "mul_with_one"]),
            ]
        ],
    ),
    (
        "log1000",
        "{log10({1000})}",
        [
            [
                ("pow_to_same_base", []),
                ("using_sim", ["using_trans", "log_same_base_arg", "mul_with_one"]),
            ]
        ],
    ),
    (
        "fourth-root-16",
        "{root({4},{16})}",
        [[("pow_to_same_base", []), ("root_reduce", [])]],
    ),
    (
        "sqrt-of-fraction",
        "{root2({frac({4},{9})})}",
        [
            [
                ("root_frac_each", []),
                ("pow_to_same_base", []),
                ("pow_to_same_base", []),
                ("root_reduce", []),
                ("root_reduce", []),
            ]
        ],
    ),
    (
        "non-square-fraction",
        "{root2({frac({1},{2})})}",
        [
            [
                ("root_frac_each", ["root_frac_each", "root_one"]),
                ("frac_mul_expand_root", []),
                ("frac_mul_join", []),
                ("mul_with_one", []),
                ("root2_sqr", []),
            ]
        ],
    ),
    (
        "sqrt-27",
        "{root2({27})}",
        [
            [
                ("pow_to_same_base", []),
                ("root_partial_split_sum", []),
                ("using_expand", []),
                ("pow_with_one", []),
                ("root_mul_each", []),
                ("root_reduce", ["root_reduce", "abs_real"]),
            ]
        ],
    ),
    (
        "root-irrational",
        "{root2({12})}",
        [
            [
                ("root_partial_split_arg", []),
                ("root_mul_each", []),
                ("root_reduce", ["root_reduce", "abs_real"]),
            ]
        ],
    ),
    # ── определители и матрицы ─────────────────────────────────────────
    (
        "det2",
        "{det2({1},{2},{3},{4})}",
        [
            [
                (
                    "det2_determinant_rule",
                    ["lesson_disc_det2_expand", "lesson_disc_arithmetic"],
                ),
                ("mul_with_one", []),
                ("mul", ["mul_neg_pos", "mul"]),
                ("calc_diff", ["add_sign_sub", "sub"]),
            ]
        ],
    ),
    (
        "det3",
        "{det3({1},{2},{3},{4},{5},{6},{7},{8},{10})}",
        [
            [
                (
                    "det_laplace_rule_row",
                    [
                        "lesson_disc_det_expand",
                        "lesson_disc_minor",
                        "lesson_disc_minor",
                        "lesson_disc_minor",
                        "lesson_disc_arithmetic",
                    ],
                ),
                ("mul_with_one", []),
                ("det_evaluate", ["det2_determinant_rule", "mul", "mul", "sub"]),
                ("det_evaluate", ["det2_determinant_rule", "mul", "mul", "calc_diff"]),
                ("det_evaluate", ["det2_determinant_rule", "mul", "mul", "calc_diff"]),
                ("mul", ["mul_neg_neg", "mul"]),
                ("mul", ["mul_pos_neg", "mul"]),
                ("sum", ["sum_real_positive", "calc_diff"]),
            ],
            [
                ("det3_sarrus_extend", []),
                (
                    "det3_sarrus_rule",
                    [
                        "lesson_disc_det_expand",
                        "lesson_disc_minor",
                        "lesson_disc_minor",
                        "lesson_disc_minor",
                        "lesson_disc_arithmetic",
                    ],
                ),
                ("mul_with_one", []),
                ("mul_with_one", []),
                ("mul", []),
                ("mul", []),
                ("product", ["mul", "mul"]),
                ("product", ["mul", "mul"]),
                ("product", ["mul", "mul"]),
                ("product", ["mul", "mul"]),
                ("sum_real_positive", ["add", "add"]),
                ("sum", ["sum_real_positive", "calc_diff"]),
            ],
        ],
    ),
    (
        "det4-identity",
        "{det4({1},{0},{0},{0},{0},{1},{0},{0},{0},{0},{1},{0},{0},{0},{0},{1})}",
        [
            [
                (
                    "det_laplace_rule_row",
                    ["lesson_disc_det_expand_row", "lesson_disc_minor", "lesson_disc_arithmetic"],
                ),
                ("mul_with_one", []),
                (
                    "det_evaluate",
                    [
                        "det_laplace_rule_row",
                        "mul_with_one",
                        "det_evaluate",
                        "mul_with_zero",
                        "mul_with_zero",
                        "sum_real_positive",
                    ],
                ),
                ("mul_with_zero", []),
                ("mul_with_zero", []),
                ("mul_with_zero", []),
                ("sum_real_positive", ["add_with_zero"]),
            ]
        ],
    ),
    (
        "det-zero-row",
        "{det3({1},{2},{3},{0},{0},{0},{4},{5},{6})}",
        [[("det_zero", [])]],
    ),
    (
        "mat-add",
        "{mat({mat_row({1},{2})},{mat_row({3},{4})})+mat({mat_row({1},{0})},{mat_row({0},{1})})}",
        [
            [
                ("matrix_add_elements", []),
                ("add", []),
                ("add_with_zero", []),
                ("add_with_zero", []),
                ("add", []),
            ]
        ],
    ),
    (
        "bare-det2",
        "{mat({mat_row({1},{2})},{mat_row({3},{4})})}",
        [
            [
                (
                    "matrix_det_rewrite",
                    ["lesson_disc_det2_expand", "lesson_disc_arithmetic"],
                ),
                (
                    "det2_determinant_rule",
                    ["lesson_disc_det2_expand", "lesson_disc_arithmetic"],
                ),
                ("mul_with_one", []),
                ("mul", ["mul_neg_pos", "mul"]),
                ("calc_diff", ["add_sign_sub", "sub"]),
            ],
            [
                ("matrix_inv_find_formula", []),
                (
                    "lesson_disc_adj_det",
                    ["det2_determinant_rule", "mul_with_one", "mul", "calc_diff"],
                ),
                ("lesson_disc_adj_cofactors", []),
                ("lesson_disc_adj_transpose", []),
                ("lesson_disc_adj_formula", []),
                ("frac_div_rec_neg_one", []),
                ("matrix_mul_scalar", []),
                ("mul", []),
                ("mul", []),
                ("mul", []),
                ("mul", []),
                (
                    "matrix_inv_eq_mul_by_inv",
                    [
                        "matrix_mul_row_col",
                        "matrix_mul_row_col",
                        "matrix_mul_row_col",
                        "matrix_mul_row_col",
                    ],
                ),
                ("matrix_inv_eq_set_identity", []),
            ],
        ],
    ),
    # ── комбинаторика ──────────────────────────────────────────────────
    (
        "factorial-5",
        "{factorial({5})}",
        [
            [
                ("factorial_formula", []),
                (
                    "product",
                    ["mul_with_one", "mul_real_clever", "mul_real_clever", "mul"],
                ),
            ]
        ],
    ),
    ("factorial-0", "{factorial({0})}", [[("by_definition", [])]]),
    (
        "choose-5-2",
        "{choose({5},{2})}",
        [
            [
                ("choose_expand", []),
                ("using_expand", []),
                ("sub", []),
                ("frac_reduce_frac_alg", []),
                ("mul", []),
                ("factorial_calculate", ["factorial_formula", "product"]),
                (
                    "frac_reduce_frac_num",
                    ["frac_div_num", "div", "div", "div_with_one"],
                ),
            ]
        ],
    ),
    (
        "choose-6-3",
        "{choose({6},{3})}",
        [
            [
                ("choose_expand", []),
                ("using_expand", []),
                ("sub", []),
                ("frac_reduce_frac_alg", []),
                ("product", ["mul", "mul"]),
                ("factorial_calculate", ["factorial_formula", "product"]),
                (
                    "frac_reduce_frac_num",
                    ["frac_div_num", "div", "div", "div_with_one"],
                ),
            ]
        ],
    ),
    ("choose-5-5", "{choose({5},{5})}", [[("choose_def_same", [])]]),
    (
        "permutation-5-2",
        "{permutation({5},{2})}",
        [
            [
                ("permutation_expand", []),
                ("using_expand", []),
                ("sub", []),
                ("frac_reduce_frac_alg", []),
                ("mul", []),
            ]
        ],
    ),
    (
        "permutation-3-3",
        "{permutation({3},{3})}",
        [
            [
                ("permutation_def_same", []),
                ("factorial_calculate", ["factorial_formula", "product"]),
            ]
        ],
    ),
    # ── комплексные числа ──────────────────────────────────────────────
    (
        "complex-difference",
        "{(2+\\i)-(1-3\\i)}",
        [
            [
                ("remove_bracket", []),
                ("neg_neg_arg", []),
                ("sub", []),
                (
                    "sum_suffix",
                    ["sum_suffix_add_one", "sum_suffix_add_detail", "add"],
                ),
            ]
        ],
    ),
    (
        "complex-modulus",
        "{abs({3+4\\i})}",
        [
            [
                ("complex_mod_formula", []),
                ("calculate_direct", ["pow", "pow", "add", "root_square"]),
            ]
        ],
    ),
    (
        "complex-product",
        "{(1+2\\i)*(3-\\i)}",
        [
            [
                ("mul_bracket_cross_each", []),
                ("product", ["mul"]),
                (
                    "product",
                    ["pow_implicit_exp", "pow_implicit_exp", "pow_same_base_mul", "add"],
                ),
                ("by_definition", []),
                ("mul_with_neg_one", ["mul_neg_neg", "mul"]),
                ("add", []),
                (
                    "sum_suffix",
                    ["sum_suffix_add_neg_one", "sum_suffix_detail", "calc_sum"],
                ),
            ],
            [
                ("mul_bracket_cross_each_distributive", []),
                ("mul_with_one", []),
                (
                    "mul_bracket",
                    ["mul_bracket_each", "product", "product"],
                ),
                ("by_definition", []),
                ("mul_with_neg_one", ["mul_neg_neg", "mul"]),
                ("add", []),
                (
                    "sum_suffix",
                    ["sum_suffix_add_neg_one", "sum_suffix_detail", "calc_sum"],
                ),
            ],
        ],
    ),
    (
        "complex-i-squared",
        "{\\i^2}",
        [
            [("by_definition", [])],
            [
                (
                    "complex_trig_form",
                    ["complex_trig_form_msg", "complex_trig_form_sub"],
                ),
                ("complex_pow_polar_moivre", []),
                ("pow_one", []),
                ("mul_with_one", []),
                ("frac_reduce_out", []),
                ("frac_reduce_out", []),
            ],
        ],
    ),
    (
        "complex-square",
        "{(1+\\i)^2}",
        [
            [
                ("using_expand", ["using_expand", "pow_one", "product"]),
                ("by_definition", []),
                ("sub_with_self_remove_num", []),
            ],
            [
                ("write_as_product", []),
                ("mul_bracket_cross_each", []),
                (
                    "product",
                    ["pow_implicit_exp", "pow_implicit_exp", "pow_same_base_mul", "add"],
                ),
                ("by_definition", []),
                ("sub_with_self_remove_num", []),
                (
                    "sum_suffix",
                    [
                        "sum_suffix_add_one",
                        "sum_suffix_add_one",
                        "sum_suffix_add_detail",
                        "add",
                    ],
                ),
            ],
            [
                (
                    "complex_trig_form",
                    [
                        "complex_trig_form_pair_msg",
                        "simplify",
                        "simplify",
                        "complex_trig_form_sub",
                    ],
                ),
                ("complex_pow_polar_moivre", []),
                ("root_reduce", []),
                ("frac_reduce_out", []),
                ("frac_reduce_out", []),
            ],
        ],
    ),
    # ── дроби и арифметика ─────────────────────────────────────────────
    (
        "nested-numerator",
        "{frac({1+1},{4})}",
        [
            [
                ("add", []),
                ("frac_reduce_frac_num", ["frac_div_num", "div", "div"]),
            ]
        ],
    ),
    (
        "fraction-reduce-percent",
        "{frac({6},{8})}",
        [
            [("frac_div_num", []), ("div", []), ("div", [])],
            [
                (
                    "frac_reduce_frac_num",
                    ["frac_div_num", "div", "div"],
                ),
                (
                    "write_as_decimal_frac",
                    ["frac_mul_expand", "frac_mul_join", "mul", "mul", "by_definition"],
                ),
            ],
        ],
    ),
    (
        "fraction-integer-percent",
        "{frac({6},{2})}",
        [
            [
                ("frac_div_num", []),
                ("div", []),
                ("div", []),
                ("div_with_one", []),
            ],
            [
                (
                    "write_as_decimal_frac",
                    ["frac_mul_expand", "frac_mul_join", "mul", "mul", "by_definition"],
                ),
            ],
        ],
    ),
    (
        "fraction-denominator-one-percent",
        "{frac({6},{1})}",
        [
            [("div_with_one", [])],
            [
                (
                    "write_as_decimal_frac",
                    [
                        "frac_mul_expand",
                        "frac_mul_join",
                        "mul",
                        "mul_with_one",
                        "by_definition",
                    ],
                ),
            ],
        ],
    ),
    (
        "divide-by-one-percent",
        "{7/1}",
        [
            [("div_with_one", [])],
            [
                (
                    "write_as_decimal_frac",
                    [
                        "frac_mul_expand",
                        "frac_mul_join",
                        "mul",
                        "mul_with_one",
                        "by_definition",
                    ],
                ),
            ],
        ],
    ),
    (
        "mixed-number-decimal",
        "{mfrac({2},{1},{3})}",
        [
            [("mfrac_to_frac", []), ("mul", []), ("add", [])],
            [
                (
                    "mfrac_to_frac",
                    ["mfrac_to_frac", "mul", "add"],
                ),
                ("calculate", []),
                ("round4", []),
                (
                    "write_as_decimal_frac",
                    ["limit_expand_expression", "product", "mul"],
                ),
                ("by_definition", []),
            ],
            [("calculate", [])],
        ],
    ),
    (
        "sqrt-product",
        "{root2({8})*root2({2})}",
        [
            [
                ("product", ["root_mul", "mul"]),
                ("root_square", ["pow_to_same_base", "root_reduce"]),
            ]
        ],
    ),
    (
        "fraction-product-negative-powers",
        "{frac({1},{2})*frac({1},{3})}",
        [
            [("frac_mul_join", []), ("mul_with_one", []), ("mul", [])],
            [
                ("using_trans", []),
                ("using_trans", []),
                (
                    "pow_same_exp_mul",
                    ["pow_same_exp_mul", "mul"],
                ),
            ],
        ],
    ),
    (
        "decimal-compensation",
        "{1.5*4}",
        [
            [("mul", [])],
            [
                ("write_as_diff", []),
                ("mul_bracket", []),
                ("mul", []),
                ("mul", ["mul_neg_pos", "mul"]),
                ("sub", []),
            ],
        ],
    ),
]


def _entries(proto: str) -> list[CoreSolverVerticalResult]:
    data = solve(parse_protocol(proto))
    group = data.result.group(ResultGroupType.VERTICAL)
    assert group is not None, f"{proto}: нет вертикальной ветки"
    return [
        CoreSolverVerticalResult.from_contract(entry.result)
        for entry in group.entries
        if entry.result and "steps" in entry.result
    ]


def _outline(vertical: CoreSolverVerticalResult) -> Outline:
    outline: Outline = []
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


@pytest.mark.parametrize(("name", "proto", "methods"), CASES, ids=[case[0] for case in CASES])
def test_step_depth_matches(name: str, proto: str, methods: list[Outline]) -> None:
    entries = _entries(proto)
    assert len(entries) == len(methods), (
        f"{name}: способов {len(entries)}, ожидалось {len(methods)}"
    )
    for index, (entry, expected) in enumerate(zip(entries, methods, strict=True)):
        assert _outline(entry) == expected, f"{name}: способ {index}"


def _all_keys(vertical: CoreSolverVerticalResult) -> list[tuple[str, int]]:
    keys: list[tuple[str, int]] = []
    for step in vertical.steps:
        for sub in step.substeps:
            assert sub.description is not None
            keys.append((sub.description.type, len(sub.description.args)))
            if sub.subresult is not None:
                keys.extend(_all_keys(sub.subresult))
    return keys


def test_log_sum_card_uses_the_simplify_formula() -> None:
    """``log10 2 + log10 5``: the card joins the logs with a formula, then evaluates.

    The card is produced by the expressions layer, so the service entry point is
    used here (``solve`` itself takes the generic simplification path).
    """
    from mymath_backend import service

    data = service.solve_request(
        parse_protocol("{log10({2})+log10({5})}").to_contract(), locale="ru", render=False
    )
    entries = [
        CoreSolverVerticalResult.from_contract(entry["result"])
        for group in data["result"]["groups"]
        for entry in group["entries"]
        if entry.get("result") and "steps" in entry["result"]
    ]
    assert len(entries) == 1
    assert _outline(entries[0]) == [
        ("log_sum_resolve_plus", ["using_sim", "mul"]),
        ("log_same_base_arg", []),
    ]


@pytest.mark.parametrize(("name", "proto", "_methods"), CASES, ids=[case[0] for case in CASES])
def test_every_used_key_exists_with_matching_arity(name: str, proto: str, _methods: Any) -> None:
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
