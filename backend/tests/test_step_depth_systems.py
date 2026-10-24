"""Глубина шагов систем.

Микрошаги: арифметика ячеек строки Гаусса (``mul_with_one``,
``sub_with_self_num``, ``mul_with_zero``, …), раскрытие определителей Крамера,
сложение уравнений (``system_2x2_add_eqs``) и проверка подстановкой
(``compare_solve_eq`` по строке на уравнение).

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

SYS_LIN = "{system({=({x+y},{3})},{=({x-y},{1})})}"
SYS_MUL = "{system({=({2x+3y},{8})},{=({x+y},{3})})}"
THREE_UNKNOWNS = "system({=({x+y+z},{6})},{=({x-y},{0})},{=({y-z},{0})})"

# (имя, вход, {заголовок способа: [(ключ, [ключи экрана подробностей]), ...]})
CASES: list[tuple[str, str, dict[str, list[tuple[str, list[str]]]]]] = [
    (
        "sys_lin",
        SYS_LIN,
        {
            "system_2x2_solve_elimination_simple": [
                (
                    "system_2x2_sum",
                    ["system_2x2_add_eqs", "sub_with_self_remove_alg", "sum_suffix", "add"],
                ),
                ("eq_linear_div", ["eq_linear_div"]),
                ("system_substitute_value", []),
                ("eq_linear", ["rel_move_right_const_eq", "sub", "eq_linear_div"]),
                ("system_2x2_res", []),
                ("system_2x2_check", []),
                ("system_ver", ["compare_solve_eq", "compare_solve_eq"]),
                ("system_2x2_check_t", []),
            ],
            "system_gauss_jordan_solve": [
                ("system_write_coeffs_to_mat", []),
                (
                    "row_elim_out",
                    [
                        "mul_row_add",
                        "mul_with_one",
                        "sub_with_self_num",
                        "mul_with_one",
                        "remove_bracket",
                        "pos_neg_arg",
                        "calc_diff",
                        "mul_with_neg_one",
                        "calc_sum",
                    ],
                ),
                (
                    "mat_divide_row",
                    [
                        "mat_divide_row_element",
                        "div_zero",
                        "div_neg_neg",
                        "div_with_self",
                        "div_neg_neg",
                        "div_with_self",
                    ],
                ),
                (
                    "row_elim_out",
                    [
                        "mul_row_add",
                        "mul_with_zero",
                        "add_with_zero",
                        "mul_with_one",
                        "sub_with_self_num",
                        "mul_with_one",
                        "remove_bracket",
                        "calc_sum",
                    ],
                ),
                ("system_convert_mat_to_eq", []),
                ("system_2x2_res", []),
                ("system_2x2_check", []),
                ("system_ver", ["compare_solve_eq", "compare_solve_eq"]),
                ("system_2x2_check_t", []),
            ],
            "system_cramer_solve": [
                ("system_2x2_cramer_rule", []),
                (
                    "det_evaluate",
                    [
                        "det2_determinant_rule",
                        "mul_with_one",
                        "mul_with_one",
                        "remove_bracket",
                        "calc_diff",
                    ],
                ),
                (
                    "det_evaluate",
                    ["det2_determinant_rule", "mul_with_neg_one", "mul_with_one", "calc_diff"],
                ),
                (
                    "det_evaluate",
                    ["det2_determinant_rule", "mul_with_one", "mul_with_one", "calc_diff"],
                ),
                (
                    "system_2x2_cramer_apply_rule",
                    ["system_2x2_cramer_apply_rule", "calculate_direct", "calculate_direct"],
                ),
                ("system_2x2_res", []),
                ("system_2x2_check", []),
                ("system_ver", ["compare_solve_eq", "compare_solve_eq"]),
                ("system_2x2_check_t", []),
            ],
            "system_2x2_inv_matrix_solve": [
                ("system_2x2_inv_matrix_write_as_mat_eq", []),
                ("system_2x2_inv_matrix_identify", []),
                (
                    "system_2x2_inv_matrix_find_inv",
                    [
                        "matrix_det_rewrite",
                        "det2_determinant_rule",
                        "mul_with_one",
                        "mul_with_one",
                        "remove_bracket",
                        "calc_diff",
                        "matrix_inv_formula_apply",
                        "mul_with_neg_one",
                        "mul_with_neg_one",
                        "calculate_direct",
                        "matrix_mul_by",
                    ],
                ),
                ("system_2x2_inv_matrix_sub_eq", []),
                (
                    "matrix_mul",
                    [
                        "matrix_mul_row_col",
                        "matrix_mul_row_col",
                        "matrix_mul_row_col_simple",
                        "matrix_mul_row_col_simple",
                    ],
                ),
                ("matrix_eq_set_elements_equal", []),
                ("system_2x2_res", []),
                ("system_2x2_check", []),
                ("system_ver", ["compare_solve_eq", "compare_solve_eq"]),
                ("system_2x2_check_t", []),
            ],
        },
    ),
    (
        "sys_mul",
        SYS_MUL,
        {
            "system_2x2_solve_elimination_simple": [
                ("eq_mul_direct_eq", ["eq_mul_direct_eq", "mul_bracket", "mul"]),
                (
                    "system_2x2_sum",
                    ["system_2x2_add_eqs", "sub_with_self_remove_alg", "sum_suffix", "sub"],
                ),
                ("system_substitute_value", []),
                ("eq_linear", ["rel_move_right_const_eq", "sub"]),
                ("system_2x2_res", []),
                ("system_2x2_check", []),
                ("system_ver", ["compare_solve_eq", "compare_solve_eq"]),
                ("system_2x2_check_t", []),
            ],
            "system_cramer_solve": [
                ("system_2x2_cramer_rule", []),
                (
                    "det_evaluate",
                    ["det2_determinant_rule", "mul_with_one", "mul_with_one", "calc_diff"],
                ),
                ("det_evaluate", ["det2_determinant_rule", "mul_with_one", "mul", "calc_diff"]),
                ("det_evaluate", ["det2_determinant_rule", "mul", "mul_with_one", "calc_diff"]),
                (
                    "system_2x2_cramer_apply_rule",
                    ["system_2x2_cramer_apply_rule", "div_with_one", "div_with_one"],
                ),
                ("system_2x2_res", []),
                ("system_2x2_check", []),
                ("system_ver", ["compare_solve_eq", "compare_solve_eq"]),
                ("system_2x2_check_t", []),
            ],
            "system_2x2_inv_matrix_solve": [
                ("system_2x2_inv_matrix_write_as_mat_eq", []),
                ("system_2x2_inv_matrix_identify", []),
                (
                    "system_2x2_inv_matrix_find_inv",
                    [
                        "matrix_det_rewrite",
                        "det2_determinant_rule",
                        "mul_with_one",
                        "mul_with_one",
                        "calc_diff",
                        "matrix_inv_formula_apply",
                        "mul_with_one",
                        "mul_with_one",
                        "calculate_direct",
                        "matrix_mul_neg_one",
                    ],
                ),
                ("system_2x2_inv_matrix_sub_eq", []),
                (
                    "matrix_mul",
                    [
                        "matrix_mul_row_col",
                        "matrix_mul_row_col",
                        "matrix_mul_row_col_simple",
                        "matrix_mul_row_col_simple",
                    ],
                ),
                ("matrix_eq_set_elements_equal", []),
                ("system_2x2_res", []),
                ("system_2x2_check", []),
                ("system_ver", ["compare_solve_eq", "compare_solve_eq"]),
                ("system_2x2_check_t", []),
            ],
        },
    ),
    (
        "three_unknowns",
        THREE_UNKNOWNS,
        {
            "system_gauss_jordan": [
                ("system_write_coeffs_to_mat", []),
                (
                    "row_elim_out",
                    [
                        "mul_row_add",
                        "mul_with_one",
                        "sub_with_self_num",
                        "mul_with_neg_one",
                        "add",
                        "mul_with_zero",
                        "add_with_zero",
                        "mul_with_zero",
                        "add_with_zero",
                    ],
                ),
                (
                    "row_elim",
                    [
                        "row_elim_add",
                        "mul_with_zero",
                        "sub_with_self_num",
                        "mul_with_one",
                        "add",
                        "mul_with_one",
                        "sub_with_self_num",
                        "mul_with_one",
                        "add_with_zero",
                    ],
                ),
                (
                    "mat_divide_row",
                    ["mat_divide_row_element", "div_zero", "div_with_self", "div_zero", "quotient"],
                ),
                (
                    "row_elim_out",
                    [
                        "mul_row_add",
                        "mul_with_zero",
                        "sub_with_self_num",
                        "mul_with_one",
                        "sub_with_self_num",
                        "mul_with_zero",
                        "add_with_zero",
                        "mul",
                        "calc_sum",
                    ],
                ),
                (
                    "row_elim",
                    [
                        "row_elim_add",
                        "mul_with_zero",
                        "add_with_zero",
                        "mul_with_one",
                        "sub_with_self_num",
                        "mul_with_zero",
                        "sub_with_self_num",
                        "mul_with_one",
                        "add_with_zero",
                    ],
                ),
                ("system_convert_mat_to_eq", []),
                ("system_3x3_possible_sol", []),
                ("system_3x3_check_sol", []),
                ("system_ver", ["compare_solve_eq", "compare_solve_eq", "compare_solve_eq"]),
                ("system_3x3_check_t", []),
            ],
            "system_cramer_solve": [
                ("system_3x3_cramer_rule", []),
                (
                    "det_evaluate",
                    [
                        "det_laplace_rule_row",
                        "mul_with_one",
                        "det2_determinant_rule",
                        "neg_neg_arg",
                        "mul_with_neg_one",
                        "det2_determinant_rule",
                        "neg_neg_arg",
                        "mul_with_zero",
                        "add",
                        "add_with_zero",
                    ],
                ),
                (
                    "det_evaluate",
                    [
                        "det_laplace_rule_row",
                        "mul_with_zero",
                        "mul_with_neg_one",
                        "det2_determinant_rule",
                        "neg_neg_arg",
                        "mul_with_zero",
                        "add_with_zero",
                        "add_with_zero",
                    ],
                ),
                (
                    "det_evaluate",
                    [
                        "det_laplace_rule_row",
                        "mul_with_one",
                        "det2_determinant_rule",
                        "neg_neg_arg",
                        "mul_with_zero",
                        "mul_with_zero",
                        "add_with_zero",
                        "add_with_zero",
                    ],
                ),
                (
                    "det_evaluate",
                    [
                        "det_laplace_rule_row",
                        "mul_with_zero",
                        "mul_with_one",
                        "det2_determinant_rule",
                        "neg_neg_arg",
                        "mul_with_zero",
                        "add_with_zero",
                        "add_with_zero",
                    ],
                ),
                (
                    "system_3x3_cramer_apply_rule",
                    [
                        "system_3x3_cramer_apply_rule",
                        "frac_reduce_frac_num",
                        "frac_reduce_frac_num",
                        "frac_reduce_frac_num",
                    ],
                ),
                ("system_3x3_possible_sol", []),
                ("system_3x3_check_sol", []),
                ("system_ver", ["compare_solve_eq", "compare_solve_eq", "compare_solve_eq"]),
                ("system_3x3_check_t", []),
            ],
        },
    ),
]


def _entries(proto: str) -> list[CoreSolverVerticalResult]:
    data = solve(parse_protocol(proto))
    assert data.result is not None
    group = data.result.group(ResultGroupType.VERTICAL)
    assert group is not None, f"{proto}: нет вертикальной ветки"
    return [
        CoreSolverVerticalResult.from_contract(entry.result)
        for entry in group.entries
        if entry.result and "steps" in entry.result
    ]


def _outline(vertical: CoreSolverVerticalResult) -> list[tuple[str, list[str]]]:
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


def _card(proto: str, header: str) -> CoreSolverVerticalResult:
    for entry in _entries(proto):
        if entry.header is not None and entry.header.type == header:
            return entry
    raise AssertionError(f"{proto}: нет карточки {header}")


@pytest.mark.parametrize(("name", "proto", "cards"), CASES, ids=[case[0] for case in CASES])
def test_step_depth_matches(
    name: str, proto: str, cards: dict[str, list[tuple[str, list[str]]]]
) -> None:
    for header, expected in cards.items():
        assert _outline(_card(proto, header)) == expected, f"{name}: {header}"


@pytest.mark.parametrize(
    ("proto", "equations"),
    [(SYS_LIN, 2), (SYS_MUL, 2), (THREE_UNKNOWNS, 3)],
    ids=["sys_lin", "sys_mul", "three_unknowns"],
)
def test_every_check_simplifies_one_equation_per_row(proto: str, equations: int) -> None:
    """``system_ver``/``system_3x3_check_sol``: по строке на уравнение."""
    for entry in _entries(proto):
        check = next(
            (
                sub
                for sub in _flat(entry)
                if sub.description and sub.description.type == "system_ver"
            ),
            None,
        )
        assert check is not None and check.subresult is not None
        keys = [
            sub.description.type
            for step in check.subresult.steps
            for sub in step.substeps
            if sub.description is not None
        ]
        assert keys == ["compare_solve_eq"] * equations


def _flat(vertical: CoreSolverVerticalResult) -> list[Any]:
    return [sub for step in vertical.steps for sub in step.substeps]


def _all_keys(vertical: CoreSolverVerticalResult) -> list[tuple[str, int]]:
    keys: list[tuple[str, int]] = []
    for step in vertical.steps:
        for sub in step.substeps:
            assert sub.description is not None
            keys.append((sub.description.type, len(sub.description.args)))
            if sub.subresult is not None:
                keys.extend(_all_keys(sub.subresult))
    return keys


@pytest.mark.parametrize(("name", "proto", "_cards"), CASES, ids=[case[0] for case in CASES])
def test_every_used_key_exists_with_matching_arity(name: str, proto: str, _cards: Any) -> None:
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


def test_priority_microsteps_appear_in_system_cards() -> None:
    """Восемь целевых ключей есть в наших карточках систем."""
    keys = {
        key
        for proto in (SYS_LIN, SYS_MUL, THREE_UNKNOWNS)
        for entry in _entries(proto)
        for key, _arguments in _all_keys(entry)
    }
    assert {
        "mul_with_one",
        "compare_solve_eq",
        "eq_linear",
        "sub_with_self_num",
        "mul_with_neg_one",
        "mul_with_zero",
        "sub_with_self_remove_alg",
        "add_with_zero",
    } <= keys


@pytest.mark.parametrize(
    "proto",
    [
        "system({lt({x},{3})},{gt({x},{1})})",
        "system({lte({x},{3})},{gte({x},{1})})",
        "system({gt({x},{2})},{lt({x},{0})})",
    ],
    ids=["open", "closed", "empty"],
)
def test_inequality_system_is_an_intersection(proto: str) -> None:
    """The app names the system-of-inequalities answer row «intersection»."""
    entries = _entries(proto)
    assert len(entries) == 1
    assert [key for key, _detail in _outline(entries[0])] == ["intersection"]


def test_three_unknowns_substitution_collects_like_terms() -> None:
    card = _card(THREE_UNKNOWNS, "system_subs_method_solve")
    simplify = next(
        sub
        for sub in _flat(card)
        if sub.description is not None and sub.description.type == "simplify"
    )
    assert simplify.subresult is not None
    assert [
        sub.description.type
        for step in simplify.subresult.steps
        for sub in step.substeps
        if sub.description is not None
    ] == [
        "sum_suffix_add_one",
        "sum_suffix_add_one",
        "sum_suffix_add_detail",
        "add",
    ]


def test_nonlinear_unique_system_gets_the_check_tail() -> None:
    card = _card("system({=({x*y},{1})},{=({x+y},{2})})", "system_2x2_solve_substitution")
    keys = [key for key, _detail in _outline(card)]
    assert keys[-4:] == [
        "system_2x2_res",
        "system_2x2_check",
        "system_ver",
        "system_2x2_check_t",
    ]
    check = next(
        sub for sub in _flat(card) if sub.description and sub.description.type == "system_ver"
    )
    assert check.subresult is not None
    assert [
        sub.description.type
        for step in check.subresult.steps
        for sub in step.substeps
        if sub.description is not None
    ] == ["compare_solve_eq", "compare_solve_eq"]


def test_sarrus_for_a_zero_free_three_by_three_determinant() -> None:
    card = _card(
        "{system({=({x+y+z},{6})},{=({2x-y+3z},{9})},{=({x+2y-z},{1})})}",
        "system_cramer_solve",
    )
    pages = [
        sub
        for sub in _flat(card)
        if sub.description is not None and sub.description.type == "det_evaluate"
    ]
    assert len(pages) == 4
    for page in pages:
        assert page.subresult is not None
        keys = [
            sub.description.type
            for step in page.subresult.steps
            for sub in step.substeps
            if sub.description is not None
        ]
        assert keys[0] == "det3_sarrus_extend"
        assert "det3_sarrus_rule" in keys


def test_comparison_flip_shows_sign_steps() -> None:
    card = _card("{system({=({2x+y},{5})},{=({x-y},{1})})}", "solve_using_comparison")
    flip = next(
        sub
        for sub in _flat(card)
        if sub.description is not None and sub.description.type == "eq_mul_direct_one"
    )
    assert flip.subresult is not None
    keys = [
        sub.description.type
        for step in flip.subresult.steps
        for sub in step.substeps
        if sub.description is not None
    ]
    assert keys.count("mul_neg_neg") == 2
    assert keys.count("mul_with_one") == 2
    assert "mul_bracket" in keys


def test_standardized_system_orders_the_terms() -> None:
    card = _card("{system({=({y},{2x})},{=({x+y},{6})})}", "system_2x2_solve_elimination_simple")
    standard = next(
        sub
        for sub in _flat(card)
        if sub.description is not None and sub.description.type == "simplify"
    )
    assert standard.subresult is not None
    keys = [
        sub.description.type
        for step in standard.subresult.steps
        for sub in step.substeps
        if sub.description is not None
    ]
    assert keys == ["rel_move_left_var", "var_order"]


def _rich_keys(value: Any) -> set[str]:
    """Every ``CoreRichText`` key in a contract tree (headers and group titles too)."""
    keys: set[str] = set()
    if isinstance(value, dict):
        if "args" in value and isinstance(value.get("type"), str) and "children" not in value:
            keys.add(value["type"])
        for item in value.values():
            keys |= _rich_keys(item)
    elif isinstance(value, list):
        for item in value:
            keys |= _rich_keys(item)
    return keys


def _all_rich_keys(proto: str) -> set[str]:
    from mymath_backend import service

    data = service.solve_request(parse_protocol(proto).to_contract(), render=False, locale="ru")
    return _rich_keys(data["result"])


def test_method_headers_and_verdicts_use_the_keys() -> None:
    keys = _all_rich_keys(SYS_LIN) | _all_rich_keys(THREE_UNKNOWNS)
    assert {
        "solve_using_substitution",
        "system_2x2_solve_elimination_simple",
        "solve_using_comparison",
        "system_gauss_jordan_solve",
        "system_2x2_pair_is_sol",
        "system_3x3_triple_is_sol",
        "system_add_equations",
    } <= keys


def test_no_solution_system_gets_the_full_method_set() -> None:
    proto = "system({=({x+y},{1})},{=({x+y},{2})})"
    cards = {entry.header.type: entry for entry in _entries(proto) if entry.header}
    assert {
        "system_gauss_jordan",
        "solve_using_substitution",
        "system_2x2_solve_elimination_simple",
        "system_2x2_inv_matrix_solve",
        "system_cramer_solve",
    } <= set(cards)
    substitution = [key for key, _detail in _outline(cards["solve_using_substitution"])]
    assert "system_2x2_no_sol2" in substitution
    elimination = [key for key, _detail in _outline(cards["system_2x2_solve_elimination_simple"])]
    assert "system_nxn_no_sol" in elimination
    cramer = [key for key, _detail in _outline(cards["system_cramer_solve"])]
    assert cramer[-1] == "system_2x2_cramer_not_applicable"
    inverse = [key for key, _detail in _outline(cards["system_2x2_inv_matrix_solve"])]
    assert "system_2x2_inv_matrix_no_uniq_sol" in inverse


def test_parametric_system_gets_any_solution_cards() -> None:
    proto = "system({=({x+y},{2})},{=({2x+2y},{4})})"
    cards = {entry.header.type: entry for entry in _entries(proto) if entry.header}
    substitution = [key for key, _detail in _outline(cards["solve_using_substitution"])]
    assert "system_2x2_any_sol" in substitution
    any_sol = next(
        sub
        for sub in _flat(cards["solve_using_substitution"])
        if sub.description and sub.description.type == "system_2x2_any_sol"
    )
    assert any_sol.subresult is not None
    nested = [
        sub.description.type
        for step in any_sol.subresult.steps
        for sub in step.substeps
        if sub.description is not None
    ]
    assert {"system_2x2_any_sol_init", "system_2x2_any_sol_fin"} <= set(nested)
    gauss = [key for key, _detail in _outline(cards["system_gauss_jordan_solve"])]
    assert "system_convert_mat_to_eq_eq" in gauss
    assert "system_2x2_any_sol_param" in gauss


def test_singular_three_by_three_gets_invalid_and_cramer_cards() -> None:
    inconsistent = "system({=({x+y+z},{1})},{=({x+y+z},{2})},{=({x-y},{0})})"
    cards = {entry.header.type: entry for entry in _entries(inconsistent) if entry.header}
    assert "system_cramer_solve" in cards
    cramer = [key for key, _detail in _outline(cards["system_cramer_solve"])]
    assert cramer[-1] == "system_3x3_cramer_not_applicable"
    keys = _all_rich_keys(inconsistent)
    assert "system_nxn_invalid" in keys

    dependent = "system({=({x+y+z},{1})},{=({2x+2y+2z},{2})},{=({x-y},{0})})"
    dependent_keys = _all_rich_keys(dependent)
    assert {"system_remove_double_eq", "system_remove_double_eq_arg"} <= dependent_keys


def test_two_solution_system_checks_both_pairs() -> None:
    proto = "system({=({x^2+y^2},{5})},{=({x-y},{1})})"
    card = _card(proto, "system_2x2_solve_substitution")
    keys = [key for key, _detail in _outline(card)]
    assert keys[-4:] == [
        "system_2x2_res_pl",
        "system_2x2_check_pl",
        "system_ver",
        "system_2x2_check_t_pl",
    ]
    assert "system_2x2_pairs_are_sol" in _all_rich_keys(proto)


@pytest.mark.parametrize(
    "proto",
    [
        "system({=({x+y},{1})},{=({x+y},{2})})",
        "system({=({x+y},{2})},{=({2x+2y},{4})})",
        "system({=({x^2+y^2},{5})},{=({x-y},{1})})",
        "system({=({x+y+z},{1})},{=({x+y+z},{2})},{=({x-y},{0})})",
        "system({=({x+y+z},{1})},{=({2x+2y+2z},{2})},{=({x-y},{0})})",
    ],
    ids=["no-solution", "parametric", "two-solutions", "invalid-3x3", "dependent-3x3"],
)
def test_new_cards_use_known_keys_with_matching_arity(proto: str) -> None:
    explanations = load_explanations(str(EXPLANATIONS))
    problems: list[str] = []
    for entry in _entries(proto):
        for key, arguments in _all_keys(entry):
            if key not in explanations:
                problems.append(f"ключа {key!r} нет в словаре")
                continue
            template = explanations.raw_template(key, DEFAULT_LOCALE) or ""
            used = {int(match) for match in re.findall(r"ARG(\d+)", template)}
            declared = explanations.arity(key)
            if declared != max(used, default=0):
                problems.append(f"у {key!r} арность {declared}, шаблон использует {used}")
            if arguments != declared:
                problems.append(f"у {key!r} передано {arguments} аргументов, нужно {declared}")
    assert problems == []
