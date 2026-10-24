"""Глубина шагов производных и пределов.

У производных проверяется карточка по строкам (у ``derivation_*`` она идёт
второй, после учебной); у пределов — способы по порядку.

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
# (имя, вход, конспекты способов).  Для производных — только карточка по строкам.
DERIVATIVE_CASES: list[tuple[str, str, Outline]] = [
    ("d_5x", "{derivation_diff({x},{5x})}", [("derive_table_desc", [])]),
    (
        "d_3x2",
        "{derivation_diff({x},{3x^2})}",
        [
            ("derive_use_rule", []),
            ("derive_table_desc", ["derive_table_desc", "sub", "pow_with_one"]),
            ("product", ["mul"]),
        ],
    ),
    (
        "d_poly",
        "{derivation_diff({x},{3x^2+2x})}",
        [
            ("derive_use_rule", []),
            ("derive", ["derive_use_rule", "derive_table_desc"]),
            ("derive", ["derive_table_desc"]),
            ("product", ["mul"]),
        ],
    ),
    (
        "d_chain",
        "{derivation_diff({x},{sin({2x})})}",
        [
            ("derive_chain_where", []),
            ("derive", ["derive_table_desc"]),
            ("derive", ["derive_table_desc"]),
            ("sub_msg_ret", []),
            ("var_order", []),
        ],
    ),
    (
        "d_prod2",
        "{derivation_diff({x},{x*sin({x})})}",
        [
            ("derive_use_rule", []),
            ("derive", ["derive_var"]),
            ("derive", ["derive_table_desc"]),
            ("simplify", []),
        ],
    ),
    (
        "d_quot",
        "{derivation_diff({x},{frac({x},{x+1})})}",
        [
            ("derive_use_rule", []),
            ("derive", ["derive_var"]),
            ("derive_sum", ["derive_use_rule", "derive", "derive", "add_with_zero"]),
            (
                "simplify",
                ["mul_with_one", "mul_with_one", "remove_bracket", "sub_with_self_remove_alg"],
            ),
        ],
    ),
    (
        "x-squared",
        "{derivation_prime({x^2})}",
        [("derive_table_desc", []), ("sub", []), ("pow_with_one", [])],
    ),
    (
        "prime-notation",
        "{prime({x^2})}",
        [("derive_table_desc", []), ("sub", []), ("pow_with_one", [])],
    ),
    ("cube", "{derivation_prime({x^3})}", [("derive_table_desc", []), ("sub", [])]),
    ("sine", "{derivation_prime({sin({x})})}", [("derive_table_desc", [])]),
    ("cosine", "{derivation_prime({cos({x})})}", [("derive_table_desc", [])]),
    ("natural-log", "{derivation_prime({ln({x})})}", [("derive_table_desc", [])]),
    ("square-root", "{derivation_prime({root2({x})})}", [("derive_table_desc", [])]),
    ("reciprocal", "{derivation_prime({1/x})}", [("derive_use_rule", []), ("derive_var", [])]),
    (
        "product-rule",
        "{derivation_prime({x*sin({x})})}",
        [
            ("derive_use_rule", []),
            ("derive", ["derive_var"]),
            ("derive", ["derive_table_desc"]),
            ("simplify", []),
        ],
    ),
    (
        "second-prime",
        "{derivation2_prime({x^3})}",
        [
            ("derive_higher_order", []),
            ("derive", ["derive_table_desc", "sub"]),
            ("derive", ["derive_use_rule", "derive_table_desc", "product"]),
        ],
    ),
    (
        "abs-derivative",
        "{derivation_prime({abs({x})})}",
        [
            ("using_trans", []),
            ("derive_chain_where", []),
            ("derive", ["derive_table_desc"]),
            ("derive", ["derive_table_desc", "sub", "pow_with_one"]),
            ("sub_msg_ret", []),
            ("simplify", ["root_reduce", "frac_reduce_out", "product"]),
        ],
    ),
]

LIMIT_CASES: list[tuple[str, str, list[Outline]]] = [
    (
        "lim_x2",
        "{lim({2},{x^2})}",
        [
            [
                ("limit_solve", ["using_trans", "limit_solve_insert_value"]),
                ("pow", ["pow_to_mul", "mul"]),
            ]
        ],
    ),
    (
        "lim_lin",
        "{lim({3},{2x+1})}",
        [
            [
                (
                    "limit_solve",
                    [
                        "using_trans",
                        "using_trans",
                        "limit_solve_const",
                        "limit_solve_insert_value",
                    ],
                ),
                ("calculate_direct", ["mul", "add"]),
            ]
        ],
    ),
    (
        "lim_left_linear",
        "{lim_left({0},{x+1})}",
        [
            [
                (
                    "limit_solve",
                    ["using_trans", "limit_solve_insert_value", "limit_solve_const"],
                ),
                ("add_with_zero", []),
            ]
        ],
    ),
    (
        "lim_right_linear",
        "{lim_right({0},{x+1})}",
        [
            [
                (
                    "limit_solve",
                    ["using_trans", "limit_solve_insert_value", "limit_solve_const"],
                ),
                ("add_with_zero", []),
            ]
        ],
    ),
    ("lim_right_log", "{lim_right({0},{ln({x})})}", [[("limit_common", [])]]),
    (
        "sin_over_x",
        "{lim({0},{sin({x})/x})}",
        [
            [("limit_common", [])],
            [
                (
                    "limit_lhopital_long",
                    [
                        "limit_evaluate_num_den",
                        "limit_solve",
                        "limit_solve",
                        "limit_transform",
                        "limit_lhopital",
                    ],
                ),
                ("derive", ["derive_table_desc"]),
                ("derive", ["derive_var"]),
                ("div_with_one", []),
                ("limit_solve", ["using_trans", "limit_solve_insert_value"]),
                ("trig_table_first", []),
            ],
        ],
    ),
    (
        "sin_over_x_frac",
        "{lim({0},{frac({sin({x})},{x})})}",
        [
            [("limit_common", [])],
            [
                (
                    "limit_lhopital_long",
                    [
                        "limit_evaluate_num_den",
                        "limit_solve",
                        "limit_solve",
                        "limit_transform",
                        "limit_lhopital",
                    ],
                ),
                ("derive", ["derive_table_desc"]),
                ("derive", ["derive_var"]),
                ("div_with_one", []),
                ("limit_solve", ["using_trans", "limit_solve_insert_value"]),
                ("trig_table_first", []),
            ],
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


def _outline(vertical: CoreSolverVerticalResult) -> Outline:
    """Ключ каждого подшага и ключи его экрана подробностей."""
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


@pytest.mark.parametrize(
    ("name", "proto", "expected"), DERIVATIVE_CASES, ids=[case[0] for case in DERIVATIVE_CASES]
)
def test_derivative_card_matches(name: str, proto: str, expected: Outline) -> None:
    entries = _entries(proto)
    assert entries, f"{name}: нет способов"
    # The row card is the alternative after the textbook one.
    assert _outline(entries[-1]) == expected, name


@pytest.mark.parametrize(
    ("name", "proto", "methods"), LIMIT_CASES, ids=[case[0] for case in LIMIT_CASES]
)
def test_limit_cards_match(name: str, proto: str, methods: list[Outline]) -> None:
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


@pytest.mark.parametrize(
    ("name", "proto", "_expected"),
    [(case[0], case[1], case[2]) for case in DERIVATIVE_CASES]
    + [(case[0], case[1], case[2]) for case in LIMIT_CASES],
    ids=[case[0] for case in DERIVATIVE_CASES] + [case[0] for case in LIMIT_CASES],
)
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
