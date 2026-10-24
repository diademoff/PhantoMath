"""Глубина шагов арифметики и дробей.

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

# (вход, [(ключ, [ключи экрана подробностей]), ...] по способам решения)
CASES: list[tuple[str, str, list[list[tuple[str, list[str]]]]]] = [
    (
        "arith_order",
        "{2+3*4}",
        [[("mul", []), ("add", [])]],
    ),
    (
        "arith_mixed",
        "{100/4+6}",
        [
            [
                ("frac_reduce_frac_num", ["frac_div_num", "div", "div", "div_with_one"]),
                ("add", []),
            ]
        ],
    ),
    (
        "arith_paren",
        "{2*(3+4)}",
        [
            [("add", []), ("mul", [])],
            [("mul_bracket", []), ("mul", []), ("mul", []), ("add", [])],
        ],
    ),
    (
        "arith3",
        "{2+3*4-5}",
        [[("mul", []), ("sum", ["sum_real_positive", "sub"])]],
    ),
    (
        "neg_arith",
        "{-3-(-5)}",
        [[("neg_neg_arg", []), ("calc_sum", ["add_sign_sub", "sub"])]],
    ),
    (
        "arith_neg",
        "{7-(-3)}",
        [[("neg_neg_arg", []), ("add", [])]],
    ),
    (
        "unary_minus",
        "{-2+5}",
        [[("add_sign_sub", []), ("sub", [])]],
    ),
    (
        "subtract_self",
        "{3-3}",
        [[("sub_with_self_num", [])]],
    ),
    (
        "frac_add",
        "{frac({1},{2})+frac({1},{3})}",
        [
            [
                (
                    "frac_sum_common",
                    [
                        "frac_sum_expand",
                        "frac_sum_expand",
                        "mul_with_one",
                        "mul",
                        "mul_with_one",
                        "mul",
                        "frac_sum_join",
                    ],
                ),
                ("add", []),
            ]
        ],
    ),
    (
        "frac_add_reduce",
        "{frac({1},{2})+frac({1},{6})}",
        [
            [
                (
                    "frac_sum_common",
                    ["frac_sum_expand", "mul_with_one", "mul", "frac_sum_join"],
                ),
                ("add", []),
                ("frac_reduce_frac_num", ["frac_div_num", "div", "div"]),
            ]
        ],
    ),
    (
        "frac_sub",
        "{frac({3},{4})-frac({1},{6})}",
        [
            [
                (
                    "frac_sum_common",
                    [
                        "frac_sum_expand",
                        "frac_sum_expand",
                        "mul",
                        "mul",
                        "mul_with_one",
                        "mul",
                        "frac_sum_join",
                    ],
                ),
                ("sub", []),
            ]
        ],
    ),
    (
        "frac_add3",
        "{frac({1},{2})+frac({1},{3})+frac({1},{6})}",
        [
            [
                (
                    "frac_sum_common",
                    [
                        "frac_sum_expand",
                        "frac_sum_expand",
                        "mul_with_one",
                        "mul",
                        "mul_with_one",
                        "mul",
                        "frac_sum_join",
                    ],
                ),
                ("sum_real_positive", ["add", "add"]),
                ("div_with_self", []),
            ]
        ],
    ),
    (
        "frac_add_int",
        "{frac({1},{2})+1}",
        [
            [
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
                ("add", []),
            ]
        ],
    ),
    (
        "frac_mul",
        "{frac({2},{3})*frac({3},{4})}",
        [[("frac_reduce_out", []), ("frac_reduce_out", [])]],
    ),
    (
        "frac_mul_nocancel",
        "{frac({1},{2})*frac({1},{3})}",
        [
            [("frac_mul_join", []), ("mul_with_one", []), ("mul", [])],
            [
                ("using_trans", []),
                ("using_trans", []),
                ("pow_same_exp_mul", ["pow_same_exp_mul", "mul"]),
            ],
        ],
    ),
    (
        "frac_div",
        "{frac({3},{4})/frac({1},{2})}",
        # The app shows two rows: the reciprocal, then the cancellation. The
        # native «дробь в виде частного»/«произведение» rows are not on screen
        # (case ``frac_div`` = ``- | -``).
        [[("frac_div_rec", []), ("frac_reduce_out", [])]],
    ),
    (
        "frac_div_nocancel",
        "{frac({1},{2})/frac({1},{3})}",
        # Case ``frac_div_nocancel`` = ``- | +``: the product row opens on the join.
        [[("frac_div_rec", []), ("product", ["frac_mul_join", "mul_with_one", "mul"])]],
    ),
    (
        "frac_reduce",
        "{frac({6},{8})}",
        [
            [("frac_div_num", []), ("div", []), ("div", [])],
            [
                ("frac_reduce_frac_num", ["frac_div_num", "div", "div"]),
                (
                    "write_as_decimal_frac",
                    ["frac_mul_expand", "frac_mul_join", "mul", "mul", "by_definition"],
                ),
            ],
        ],
    ),
    (
        "frac_integer_result",
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
        "frac_mixed_number",
        "{mfrac({2},{1},{3})}",
        [
            [("mfrac_to_frac", []), ("mul", []), ("add", [])],
            [
                ("mfrac_to_frac", ["mfrac_to_frac", "mul", "add"]),
                ("calculate", []),
                ("round4", []),
                ("write_as_decimal_frac", ["limit_expand_expression", "product", "mul"]),
                ("by_definition", []),
            ],
            [("calculate", [])],
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


@pytest.mark.parametrize(("name", "proto", "methods"), CASES, ids=[case[0] for case in CASES])
def test_step_depth_matches(
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
