"""Глубина шагов интегралов и рядов.

У неопределённого интеграла первый способ — урок («Табличный интеграл»,
линейность, замена), второй — карточка по строкам; у ряда все способы —
карточки по строкам.

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
from collections.abc import Iterator
from pathlib import Path

import pytest

from mymath_backend import load_explanations
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult, ResultGroupType
from mymath_backend.solver import solve

EXPLANATIONS = Path(__file__).resolve().parents[1] / "mymath_backend" / "data" / "explanations.json"

# (имя, вход, [(ключ, [ключи экрана подробностей]), ...] по способам)
CASES: list[tuple[str, str, list[list[tuple[str, list[str]]]]]] = [
    (
        # ∫x² dx: the lesson keeps its arg-free table chip; the verified card is
        # its own row with the power-rule page (two «Добавить» rows).
        "int_x2",
        "{integral({x^2})}",
        [
            [
                ("lesson_calc_int_table_rule", ["lesson_calc_int_table_rule"]),
                ("integrate_msg_addc", []),
            ],
            [
                ("integrate_msg", ["integrate_msg", "add", "add"]),
                ("integrate_msg_addc", []),
            ],
        ],
    ),
    (
        # ∫3x² + 2x dx: the sum property, one page per term, each page carries
        # «вынести множитель → таблица → упростить».
        "int_poly",
        "{integral({3x^2+2x})}",
        [
            [
                ("lesson_calc_int_sum_rule", []),
                ("lesson_calc_int_term_table", ["lesson_calc_int_table_rule"]),
                ("lesson_calc_int_term_table", ["lesson_calc_int_table_rule"]),
                ("integrate_msg_addc", []),
            ],
            [
                ("integrate_msg_sum", []),
                ("integrate", ["integrate_msg_mul_const", "integrate_msg", "simplify"]),
                ("integrate", ["integrate_msg_mul_const", "integrate_msg", "simplify"]),
                ("integrate_msg_addc", []),
            ],
        ],
    ),
    (
        # ∫2x + 3 dx: the constant term is one table row, not a factor page.
        "int_lin",
        "{integral({2x+3})}",
        [
            [
                ("lesson_calc_int_sum_rule", []),
                ("lesson_calc_int_term_table", ["lesson_calc_int_table_rule"]),
                ("lesson_calc_int_term_table", ["lesson_calc_int_table_rule"]),
                ("integrate_msg_addc", []),
            ],
            [
                ("integrate_msg_sum", []),
                ("integrate", ["integrate_msg_mul_const", "integrate_msg", "simplify"]),
                ("integrate_msg", []),
                ("integrate_msg_addc", []),
            ],
        ],
    ),
    (
        # ∫3x dx: odd factor → «Вычислите произведение», not «Упростите».
        "int_3x",
        "{integral({3x})}",
        [
            [
                ("lesson_calc_int_table_rule", []),
                ("integrate_msg_addc", []),
            ],
            [
                ("integrate_msg_mul_const", []),
                ("integrate_msg", []),
                ("product", []),
                ("integrate_msg_addc", []),
            ],
        ],
    ),
    (
        # ∫sin x dx: the app's card is one table row + C. The lesson chip stays
        # arg-free (its formula lives in the stage theory), so their key differs;
        # this row is the known gap of the report.
        "int_sin",
        "{integral({sin({x})})}",
        [
            [
                ("lesson_calc_int_table_rule", []),
                ("integrate_msg_addc", []),
            ]
        ],
    ),
    (
        # ∫₀¹ x dx: indefinite integral → primitive → bounds → F(b) − F(a) →
        # «Вычислите значение» with powers of 1/0, 0/2 and x − 0.
        "int_def_linear",
        "{integral_def({0},{1},{x})}",
        [
            [
                ("lesson_calc_int_newton_formula", []),
                ("lesson_calc_int_newton_primitive", ["lesson_calc_int_table_rule"]),
                ("lesson_calc_int_newton_bounds", []),
                ("lesson_calc_int_newton_subst", []),
                ("lesson_calc_int_newton_upper", []),
                ("lesson_calc_int_newton_lower", []),
                ("lesson_calc_int_newton_calc", []),
            ],
            [
                ("integrate_def_solve_undefined", []),
                ("integrate_msg", []),
                ("integrate_def_bounds", []),
                ("integrate_def_msg_range", []),
                (
                    "calculate_direct",
                    ["pow_one", "pow_zero", "div_zero", "add_with_zero"],
                ),
            ],
            [
                ("total_area_fun", []),
                (
                    "total_area_x_intercept",
                    ["x_intercept_substitute", "rel_swap_eq", "eq_quad_exp_zero"],
                ),
                ("total_area_endpoint_zero", []),
                (
                    "integrate_def",
                    [
                        "integrate_def_solve_undefined",
                        "integrate_msg",
                        "integrate_def_bounds",
                        "integrate_def_msg_range",
                        "calculate_direct",
                    ],
                ),
                ("abs_neg", []),
                ("total_area_final", []),
            ],
        ],
    ),
    (
        # ∫₀^π sin x dx: trigonometric values, double minus, then the sum.
        "int_def_sine",
        "{integral_def({0},{pi},{sin({x})})}",
        [
            [
                ("lesson_calc_int_newton_formula", []),
                ("lesson_calc_int_newton_primitive", ["lesson_calc_int_table_rule"]),
                ("lesson_calc_int_newton_bounds", []),
                ("lesson_calc_int_newton_subst", []),
                ("lesson_calc_int_newton_upper", []),
                ("lesson_calc_int_newton_lower", []),
                ("lesson_calc_int_newton_calc", []),
            ],
            [
                ("integrate_def_solve_undefined", []),
                ("integrate_msg", []),
                ("integrate_def_bounds", []),
                ("integrate_def_msg_range", []),
                (
                    "simplify",
                    [
                        "trig_table_third",
                        "neg_neg_arg",
                        "neg_neg_arg",
                        "trig_table_first",
                        "add",
                    ],
                ),
            ],
        ],
    ),
    (
        # ∫₁² dx/x: |·| dropped, ln 1 = 0, x − 0 = x.
        "int_def_reciprocal",
        "{integral_def({1},{2},{1/x})}",
        [
            [
                ("lesson_calc_int_newton_formula", []),
                ("lesson_calc_int_newton_primitive", ["lesson_calc_int_table_rule"]),
                ("lesson_calc_int_newton_bounds", []),
                ("lesson_calc_int_newton_subst", []),
                ("lesson_calc_int_newton_upper", []),
                ("lesson_calc_int_newton_lower", []),
                ("lesson_calc_int_newton_calc", []),
            ],
            [
                ("integrate_def_solve_undefined", []),
                ("integrate_msg", []),
                ("integrate_def_bounds", []),
                ("integrate_def_msg_range", []),
                ("simplify", ["abs_real", "abs_real", "log_arg_one", "add_with_zero"]),
            ],
            [
                ("total_area_fun", []),
                (
                    "total_area_x_intercept",
                    [
                        "x_intercept_substitute",
                        "rel_restrictions_range",
                        "rel_swap_eq",
                        "eq_linear_frac_zero",
                        "rel_el_of_zero",
                    ],
                ),
                ("total_area_no_zeros", []),
                (
                    "integrate_def",
                    [
                        "integrate_def_solve_undefined",
                        "integrate_msg",
                        "integrate_def_bounds",
                        "integrate_def_msg_range",
                        "simplify",
                    ],
                ),
                ("abs_neg", []),
                ("total_area_final", []),
            ],
        ],
    ),
    (
        # ∫₁^∞ dx/x²: rewrite as lim, the inner chain, then the limit.
        "int_improper",
        "{integral_def({1},{inf},{frac({1},{x^2})})}",
        [
            [
                ("lesson_calc_int_imp_formula", []),
                ("lesson_calc_int_imp_rewrite", []),
                ("lesson_calc_int_imp_primitive", ["lesson_calc_int_table_rule"]),
                ("lesson_calc_int_imp_value", []),
                ("lesson_calc_int_imp_value", []),
            ],
            [
                ("integrate_imp_rewrite_using_lim", []),
                (
                    "integrate_def",
                    [
                        "integrate_def_solve_undefined",
                        "integrate_msg",
                        "integrate_def_bounds",
                        "integrate_def_msg_range",
                        "simplify",
                    ],
                ),
                ("limit_solve", ["limit_solve", "add_with_zero"]),
            ],
        ],
    ),
    (
        # ∫₀¹ dx/√x: the discontinuity at the lower bound is a one-sided limit.
        "int_improper_discontinuity",
        "{integral_def({0},{1},{frac({1},{root2({x})})})}",
        [
            [
                ("lesson_calc_int_imp_formula", []),
                ("lesson_calc_int_imp_rewrite", []),
                ("lesson_calc_int_imp_primitive", ["lesson_calc_int_table_rule"]),
                ("lesson_calc_int_imp_value", []),
            ],
            [
                (
                    "integrate_imp_rewrite_using_lim_sided_msg",
                    ["integrate_imp_discon_lower", "integrate_imp_rewrite_using_lim_sided"],
                ),
                (
                    "integrate_def",
                    [
                        "integrate_def_solve_undefined",
                        "integrate_msg",
                        "integrate_def_bounds",
                        "integrate_def_msg_range",
                        "simplify",
                    ],
                ),
                ("limit_solve", ["limit_solve", "calculate_direct"]),
            ],
        ],
    ),
    (
        # Σi, i = 1..5: formula card, arithmetic progression, plain substitution.
        "series_sum_i",
        "{sigma_def({i},{1},{5},{i})}",
        [
            [
                ("series_formula_pos_int", []),
                ("calculate_direct", ["add", "frac_reduce_frac_num", "mul"]),
            ],
            [
                ("series_sigma_find_fst_last", []),
                ("series_sigma_arith_write_rule", []),
                ("series_sigma_sub", []),
                ("calculate_direct", ["add", "frac_reduce_frac_num", "mul"]),
            ],
            [
                ("sigma_sum_convert", []),
                ("sum_real_positive", ["add", "add", "add", "add"]),
            ],
        ],
    ),
    (
        # Σi², i = 1..4: no arithmetic card, the substitution card is calculate_direct.
        "series_sum_squares",
        "{sigma_def({i},{1},{4},{i^2})}",
        [
            [
                ("series_formula_square", []),
                (
                    "calculate_direct",
                    [
                        "add",
                        "mul",
                        "frac_reduce_frac_alg",
                        "add",
                        "frac_reduce_frac_num",
                        "product",
                    ],
                ),
            ],
            [
                ("sigma_sum_convert", []),
                (
                    "calculate_direct",
                    ["pow_one", "pow", "pow", "pow", "sum_real_positive"],
                ),
            ],
        ],
    ),
    (
        # Σ2ⁿ, n = 0..3: number of terms, first term and ratio, geometric rule.
        "series_geometric",
        "{sigma_def({n},{0},{3},{2^n})}",
        [
            [
                ("series_sigma_calc_n", []),
                ("sum", ["add_with_zero", "add"]),
                ("series_sigma_find_fst_ratio", []),
                ("pow_with_zero", []),
                ("series_sigma_geom_write_rule", []),
                ("series_sigma_sub", []),
                (
                    "calculate_direct",
                    ["mul_with_one", "pow", "calc_diff", "calc_diff", "div_with_neg_one"],
                ),
            ],
            [
                ("sigma_sum_convert", []),
                (
                    "calculate_direct",
                    ["pow_with_zero", "pow_with_one", "pow", "pow", "sum_real_positive"],
                ),
            ],
        ],
    ),
    (
        # Σ(2n+1), n = 1..3: arithmetic progression with the terms evaluated.
        "series_linear_term",
        "{sigma_def({n},{1},{3},{2n+1})}",
        [
            [
                ("series_sigma_find_fst_last", ["calculate_direct", "calculate_direct"]),
                ("series_sigma_arith_write_rule", []),
                ("series_sigma_sub", []),
                ("calculate_direct", ["add", "frac_reduce_frac_num", "mul"]),
            ],
            [
                ("sigma_sum_convert", []),
                (
                    "calculate_direct",
                    [
                        "mul_with_one",
                        "add",
                        "mul",
                        "mul",
                        "add",
                        "add",
                        "sum_real_positive",
                    ],
                ),
            ],
        ],
    ),
    (
        # Σ3, n = 1..4: write the constant as a product, take it out, Σ1 = n.
        "series_constant_term",
        "{sigma_def({n},{1},{4},{3})}",
        [
            [
                ("write_as_mul", []),
                ("series_sigma_rewrite_extract", []),
                ("series_sigma_const_one", []),
                ("mul", []),
            ]
        ],
    ),
    (
        # Σi, i = 1..10: «Упростите» pulls the factor out of the fraction, and the
        # plain card pairs the ends to make tens (add_real_clever).
        "series_ten_terms",
        "{sigma_def({n},{1},{10},{n})}",
        [
            [
                ("series_formula_pos_int", []),
                ("calculate_direct", ["add", "frac_reduce_frac_num", "mul"]),
            ],
            [
                ("series_sigma_find_fst_last", []),
                ("series_sigma_arith_write_rule", []),
                ("series_sigma_sub", []),
                ("calculate_direct", ["add", "frac_reduce_out", "mul"]),
            ],
            [
                ("sigma_sum_convert", []),
                (
                    "sum_real_positive",
                    [
                        "add_real_clever",
                        "add_real_clever",
                        "add_real_clever",
                        "add",
                        "add_real_clever",
                        "add",
                        "add_real_clever",
                        "add",
                        "add",
                    ],
                ),
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


def test_the_power_rule_page_is_two_separate_additions() -> None:
    """``(x^(2+1))/(2+1) → x³/(2+1) → x³/3`` — one «Добавить» row each."""
    entry = _entries("{integral({x^2})}")[1]
    detail = entry.steps[0].substeps[0].subresult
    assert detail is not None
    assert [len(step.substeps) for step in detail.steps] == [1, 2]


def test_a_term_page_carries_the_three_rows_of_a_constant_factor() -> None:
    """``∫3x² → 3∫x² → 3·(x³/3) → x³``."""
    entry = _entries("{integral({3x^2+2x})}")[1]
    detail = entry.steps[1].substeps[0].subresult
    assert detail is not None
    assert [step.substeps[0].description.type for step in detail.steps] == [
        "integrate_msg_mul_const",
        "integrate_msg",
        "simplify",
    ]


def test_an_arithmetic_progression_evaluates_both_terms() -> None:
    """``a₁ = 2·1+1`` and ``a₃ = 2·3+1`` each get «вычислить значение»."""
    entry = _entries("{sigma_def({n},{1},{3},{2n+1})}")[0]
    detail = entry.steps[0].substeps[0].subresult
    assert detail is not None
    nested = [sub for step in detail.steps for sub in step.substeps]
    assert [sub.description.type for sub in nested] == ["calculate_direct", "calculate_direct"]
    assert all(sub.subresult is not None for sub in nested)
    assert [
        inner.description.type
        for sub in nested
        for step in sub.subresult.steps
        for inner in step.substeps
    ] == ["mul_with_one", "add", "mul", "add"]


def test_the_definite_screen_is_five_rows_in_order() -> None:
    entry = _entries("{integral_def({0},{1},{x})}")[1]
    assert [sub.description.type for step in entry.steps for sub in step.substeps] == [
        "integrate_def_solve_undefined",
        "integrate_msg",
        "integrate_def_bounds",
        "integrate_def_msg_range",
        "calculate_direct",
    ]


@pytest.mark.parametrize(("name", "proto", "_methods"), CASES, ids=[case[0] for case in CASES])
def test_rendered_stages_have_no_raw_placeholders(name: str, proto: str, _methods: object) -> None:
    """Every stage renders its explanation: no ``ARG1``, no ``?? step_… ??``."""
    from mymath_backend import service

    data = service.solve_request(parse_protocol(proto).to_contract(), render=True, locale="ru")
    leftovers = [text for text in _texts(data) if _RAW.search(text)]
    assert leftovers == [], name


_RAW = re.compile(r"ARG\d|\?\?\s*step_|\bNone\b|\b[A-Z][A-Z_0-9]{2,}\(")


def _texts(value: object) -> Iterator[str]:
    if isinstance(value, dict):
        explanation = value.get("explanation")
        if isinstance(explanation, dict) and explanation.get("text"):
            yield explanation["text"]
        for child in value.values():
            yield from _texts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _texts(child)


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
def test_every_used_key_exists_with_matching_arity(name: str, proto: str, _methods: object) -> None:
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
