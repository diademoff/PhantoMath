"""Глубина шагов уравнений.

Учебные карточки (``lesson_*``) при сверке экранов подробностей пропускаются.

Каждый кейс — вход протокола и последовательность ключей подшагов: ключ
верхнего подшага и, если у него есть экран подробностей (``subresult``), ключи
этого экрана. Заголовки шагов не проверяются — сравнение идёт по ключам
действий.

Дополнительно каждый ключ проверяется по словарю объяснений: ключ существует и
арность совпадает с числом ``ARGn`` в шаблоне (иначе на экране останется
«ARG1»).
"""

from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from mymath_backend import load_explanations
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.input import parse_protocol
from mymath_backend.node_types import CoreNodeType as T
from mymath_backend.results import CoreSolverVerticalResult, ResultGroupType
from mymath_backend.solver import expression_cards, solve
from mymath_backend.solver.base import SolveError

EXPLANATIONS = Path(__file__).resolve().parents[1] / "mymath_backend" / "data" / "explanations.json"

# (имя, вход, [(номер способа, [(ключ, [ключи экрана подробностей])])])
CASES: list[tuple[str, str, list[tuple[int, list[tuple[str, list[str]]]]]]] = [
    (
        "linear_move_divide",
        "{=({2x+3},{7})}",
        [
            (
                0,
                [
                    (
                        "rel_move_right_const_eq",
                        ["rel_swap_right_const", "sub_with_self_remove_num"],
                    ),
                    ("sub", []),
                    ("eq_linear_div", ["eq_linear_div", "div_with_self", "quotient"]),
                ],
            )
        ],
    ),
    (
        "linear_both_sides",
        "{=({3x-1},{2x+4})}",
        [
            (
                0,
                [
                    (
                        "rel_move_left_var",
                        ["rel_swap_left_var", "sub_with_self_remove_alg"],
                    ),
                    (
                        "rel_move_right_const_eq",
                        ["rel_swap_right_const", "sub_with_self_remove_num"],
                    ),
                    (
                        "sum_suffix",
                        ["sum_suffix_sub_detail", "sub", "sum_suffix_del_one"],
                    ),
                    ("add", []),
                ],
            )
        ],
    ),
    (
        "linear_divide_bracket",
        "{=({2*(x+1)},{8})}",
        [
            (
                0,
                [
                    ("eq_linear_div", ["eq_linear_div", "div_with_self", "quotient"]),
                    (
                        "rel_move_right_const_eq",
                        ["rel_swap_right_const", "sub_with_self_remove_num"],
                    ),
                    ("sub", []),
                ],
            )
        ],
    ),
    (
        "linear_negative_coefficient",
        "{=({-2x+3},{7})}",
        [
            (
                0,
                [
                    (
                        "rel_move_right_const_eq",
                        ["rel_swap_right_const", "sub_with_self_remove_num"],
                    ),
                    ("sub", []),
                    (
                        "eq_linear_div",
                        ["eq_linear_div", "div_with_self", "div_pos_neg", "quotient"],
                    ),
                ],
            )
        ],
    ),
    (
        "linear_unknown_over_number",
        "{=({frac({x},{2})},{5})}",
        [(0, [("eq_mul_direct_denom", []), ("frac_reduce_out", []), ("mul", [])])],
    ),
    (
        "linear_decimal_coefficient",
        "{=({0.5x},{2})}",
        [(0, [("eq_linear_div", []), ("div_with_self", []), ("div", [])])],
    ),
    (
        "quadratic_factoring",
        "{=({x^2-5x+6},{0})}",
        [
            (
                0,
                [
                    ("write_as_diff_fact", []),
                    ("extract_arg", []),
                    ("extract_arg", []),
                    ("extract_arg", []),
                    ("quad_separate_zero_product", []),
                    (
                        "eq_linear",
                        ["rel_swap_right_const", "sub_with_self_remove_num", "add_with_zero"],
                    ),
                    (
                        "eq_linear",
                        ["rel_swap_right_const", "sub_with_self_remove_num", "add_with_zero"],
                    ),
                    ("solution_eq_num", []),
                ],
            ),
            (
                3,
                [
                    (
                        "rel_move_right_const_eq",
                        ["rel_swap_right_const", "sub_with_self_remove_num", "add_with_zero"],
                    ),
                    ("conics_complete_square_both", []),
                    (
                        "conics_complete_square",
                        ["write_as_mul_expr_two_f", "conics_add_middle", "product", "pow_frac"],
                    ),
                    ("conics_add_other_lr", []),
                    (
                        "using_factor",
                        [
                            "write_as_mul_expr_two_f",
                            "write_as_num_arg",
                            "write_as_num_arg",
                            "log_frac_power",
                            "using_factor",
                        ],
                    ),
                    ("calc_sum", ["frac_sum_join", "calc_sum"]),
                    (
                        "eq_linear",
                        ["quad_sqrt_sides", "eq_separate", "eq_linear", "eq_linear"],
                    ),
                    ("solution_eq_num", []),
                ],
            ),
        ],
    ),
    (
        "quadratic_extraction",
        "{=({x^2-4},{0})}",
        [
            (
                0,
                [
                    (
                        "rel_move_right_const_eq",
                        ["rel_swap_right_const", "sub_with_self_remove_num", "add_with_zero"],
                    ),
                    ("quad_sqrt_sides", ["quad_sqrt_sides", "root_square"]),
                    ("quad_separate_signs", []),
                    ("solution_eq_num", []),
                ],
            )
        ],
    ),
    (
        "absolute_two_branches",
        "{=({abs({2x-1})},{5})}",
        [
            (
                0,
                [
                    ("eq_abs_branch", []),
                    (
                        "eq_linear",
                        ["rel_move_right_const_eq", "add", "eq_linear_div"],
                    ),
                    (
                        "eq_linear",
                        ["rel_move_right_const_eq", "calc_sum", "eq_linear_div"],
                    ),
                    ("solution_eq_num", []),
                ],
            )
        ],
    ),
    (
        "contradiction",
        "{=({x+1},{x+2})}",
        [(0, [("eq_del_opp", []), ("rel_el_of_zero", [])])],
    ),
    (
        "degree_nine",
        "{=({x^9},{1})}",
        [(0, [("eq_root", []), ("root_one", [])])],
    ),
    (
        "cube_root",
        "{=({x^3},{2})}",
        [(0, [("eq_root", [])])],
    ),
    (
        "radical_no_solution",
        "{=({root2({x})},{-1})}",
        [(0, [("rel_terminators_root_no_sol", [])])],
    ),
    (
        "exponential_no_solution",
        "{=({2^x},{-1})}",
        [(0, [("exp_eq_no_sol_eq", [])])],
    ),
    (
        "absolute_negative_right",
        "{=({abs({x})},{-2})}",
        [(0, [("rel_terminators_abs_no_sol", [])])],
    ),
    (
        "quadratic_pq_scaled",
        "{=({3x^2-7x+2},{0})}",
        [
            (
                2,
                [
                    (
                        "eq_linear_div",
                        [
                            "eq_linear_div",
                            "mul_bracket",
                            "div_zero",
                            "quotient",
                            "div_to_frac",
                            "div_to_frac",
                        ],
                    ),
                    ("quad_formula_pq", []),
                    ("frac_resolve_neg", ["frac_extract_neg", "neg_neg_arg"]),
                    ("frac_extract_neg", []),
                    (
                        "frac_complex_resolve_call",
                        ["frac_to_div", "frac_int_div", "frac_mul_join", "mul_with_one", "mul"],
                    ),
                    (
                        "frac_complex_resolve_call",
                        ["frac_to_div", "frac_int_div", "frac_mul_join", "mul_with_one", "mul"],
                    ),
                    ("pow_frac", ["pow_even", "pow_frac", "pow", "pow"]),
                    ("frac_sub", ["frac_sum_common", "sub"]),
                    (
                        "root_square",
                        [
                            "root_frac_each",
                            "pow_to_same_base",
                            "pow_to_same_base",
                            "root_reduce",
                            "root_reduce",
                        ],
                    ),
                    ("quad_separate_signs", []),
                    ("frac_add", ["frac_sum_join", "add", "frac_reduce_frac_num"]),
                    ("frac_sub", ["frac_sum_join", "sub", "frac_reduce_frac_num"]),
                    ("solution_eq_num", []),
                ],
            )
        ],
    ),
    (
        "quadratic_pq_and_discriminant",
        "{=({2x^2+3x-2},{0})}",
        [
            (
                2,
                [
                    (
                        "eq_linear_div",
                        [
                            "eq_linear_div",
                            "mul_bracket",
                            "div_zero",
                            "quotient",
                            "div_to_frac",
                            "quotient",
                        ],
                    ),
                    ("quad_formula_pq", []),
                    (
                        "frac_complex_resolve_call",
                        ["frac_to_div", "frac_int_div", "frac_mul_join", "mul_with_one", "mul"],
                    ),
                    (
                        "frac_complex_resolve_call",
                        ["frac_to_div", "frac_int_div", "frac_mul_join", "mul_with_one", "mul"],
                    ),
                    ("neg_neg_arg", []),
                    ("pow_frac", ["pow_frac", "pow", "pow"]),
                    ("calc_sum", ["frac_sum_join", "add"]),
                    (
                        "root_square",
                        [
                            "root_frac_each",
                            "pow_to_same_base",
                            "pow_to_same_base",
                            "root_reduce",
                            "root_reduce",
                        ],
                    ),
                    ("quad_separate_signs", []),
                    ("calc_sum", ["frac_sum_join", "calc_sum", "frac_reduce_frac_num"]),
                    (
                        "calc_diff",
                        ["frac_sum_join", "calc_diff", "frac_extract_neg", "frac_reduce_frac_num"],
                    ),
                    ("solution_eq_num", []),
                ],
            ),
            (
                4,
                [
                    ("eq_quad_coeff_identify", ["sub_as_add", "eq_quad_coeff_identify"]),
                    ("eq_quad_eval_disc_sub", []),
                    ("calculate_direct", ["pow", "product", "add"]),
                    ("eq_quad_disc_solution_all_gt", []),
                ],
            ),
            (
                5,
                [
                    ("eq_quad_coeff_identify", ["sub_as_add", "eq_quad_coeff_identify"]),
                    ("eq_quad_eval_disc_sub", []),
                    ("calculate_direct", ["pow", "product", "add"]),
                ],
            ),
        ],
    ),
    (
        "rational_linear_fraction",
        "{=({frac({x},{x-2})},{3})}",
        [
            (
                0,
                [
                    (
                        "rel_restrictions_range",
                        [
                            "rel_restrictions_den_zero",
                            "eq_linear",
                            "rel_restrictions_range_complement",
                        ],
                    ),
                    ("eq_mul_direct_denom", ["eq_mul_direct_denom", "frac_reduce_out_expr"]),
                    ("mul_bracket", ["mul_bracket_each", "mul"]),
                    ("rel_move_left_var", ["rel_swap_left_var", "sub_with_self_remove_alg"]),
                    (
                        "sum_suffix",
                        ["sum_suffix_add_one", "sum_suffix_sub_detail", "calc_diff"],
                    ),
                    (
                        "eq_linear_div",
                        ["eq_linear_div", "div_with_self", "div_neg_neg", "quotient"],
                    ),
                    ("rel_restrictions_check", []),
                ],
            )
        ],
    ),
    (
        "rational_pole_excluded",
        "{=({frac({x^2-1},{x-1})},{0})}",
        [
            (
                0,
                [
                    (
                        "rel_restrictions_range",
                        [
                            "rel_restrictions_den_zero",
                            "eq_linear",
                            "rel_restrictions_range_complement",
                        ],
                    ),
                    ("using_factor", ["write_as_num_arg", "using_factor"]),
                    ("frac_reduce_frac_alg", []),
                    (
                        "rel_move_right_const_eq",
                        ["rel_swap_right_const", "sub_with_self_remove_num", "add_with_zero"],
                    ),
                    ("rel_restrictions_check", []),
                ],
            )
        ],
    ),
    (
        "linear_decimal_implicit",
        "{=({0.5x},{2})}",
        [
            (
                1,
                [
                    ("rel_move_left_const", ["rel_swap_left_const", "sub_with_self_num"]),
                    (
                        "eq_mul_direct_eq",
                        ["eq_mul_direct_eq", "mul_bracket", "mul_with_zero", "product", "mul"],
                    ),
                    (
                        "eq_linear_div",
                        ["eq_linear_div", "mul_bracket", "div_zero", "quotient", "quotient"],
                    ),
                ],
            )
        ],
    ),
    (
        "linear_fraction_constant",
        "{=({frac({2},{3})+x},{frac({5},{6})})}",
        [
            (
                0,
                [
                    (
                        "rel_move_right_const_eq",
                        ["rel_swap_right_const", "sub_with_self_remove_num"],
                    ),
                    ("frac_sub", ["frac_sum_common", "sub"]),
                ],
            ),
            (
                2,
                [
                    ("rel_move_left_const", ["rel_swap_left_const", "sub_with_self_num"]),
                    (
                        "frac_sub",
                        ["frac_sum_common", "calc_diff", "frac_extract_neg"],
                    ),
                    (
                        "eq_mul_direct_denom",
                        ["eq_mul_direct_denom", "mul_bracket", "mul_with_zero", "frac_reduce_out"],
                    ),
                    ("var_order", []),
                ],
            ),
        ],
    ),
    (
        "linear_fraction_sum",
        "{=({frac({x},{2})+frac({x},{3})},{5})}",
        [
            (
                0,
                [
                    (
                        "eq_mul_direct_denom",
                        [
                            "eq_mul_direct_denom",
                            "mul_bracket",
                            "mul",
                            "frac_reduce_out",
                            "frac_reduce_out",
                        ],
                    ),
                    ("sum_suffix", ["sum_suffix_add_detail", "add"]),
                    ("eq_linear_div", ["eq_linear_div", "div_with_self", "quotient"]),
                ],
            ),
            (
                2,
                [
                    (
                        "calc_sum",
                        [
                            "frac_sum_expand",
                            "frac_sum_expand",
                            "mul",
                            "mul",
                            "frac_sum_join",
                            "sum_suffix",
                            "frac_sep_n",
                        ],
                    ),
                    ("rel_move_left_const", ["rel_swap_left_const", "sub_with_self_num"]),
                    (
                        "eq_mul_direct_denom",
                        [
                            "eq_mul_direct_denom",
                            "mul_bracket",
                            "mul_with_zero",
                            "frac_reduce_out",
                            "mul",
                        ],
                    ),
                    (
                        "eq_linear_div",
                        ["eq_linear_div", "mul_bracket", "div_zero", "quotient", "quotient"],
                    ),
                ],
            ),
        ],
    ),
    (
        "radical_square_both_sides",
        "{=({root2({x})},{2})}",
        [
            (
                0,
                [
                    (
                        "eq_irrational_simple_square",
                        ["eq_irrational_simple_square", "root_reduce", "pow"],
                    ),
                    ("solution_check_sub", []),
                    ("root_square", ["pow_to_same_base", "root_reduce"]),
                    ("solution_check_t", []),
                ],
            )
        ],
    ),
    (
        "linear_distribute_first",
        "{=({3*(x-2)},{2x+1})}",
        [
            (
                0,
                [
                    ("mul_bracket", ["mul_bracket_each", "mul"]),
                    ("rel_move_left_var", ["rel_swap_left_var", "sub_with_self_remove_alg"]),
                    (
                        "rel_move_right_const_eq",
                        ["rel_swap_right_const", "sub_with_self_remove_num"],
                    ),
                    ("sum_suffix", ["sum_suffix_sub_detail", "sub", "sum_suffix_del_one"]),
                    ("add", []),
                ],
            )
        ],
    ),
    (
        "linear_negative_implicit",
        "{=({-2x+3},{7})}",
        [
            (
                2,
                [
                    ("rel_move_left_const", ["rel_swap_left_const", "sub_with_self_num"]),
                    ("calc_diff", ["add_sign_sub", "sub"]),
                    (
                        "eq_linear_div",
                        [
                            "eq_linear_div",
                            "mul_bracket",
                            "div_zero",
                            "div_neg_neg",
                            "quotient",
                            "div_neg_neg",
                            "quotient",
                        ],
                    ),
                ],
            )
        ],
    ),
    (
        "biquadratic_substitution",
        "{=({x^4-5x^2+4},{0})}",
        [
            (
                0,
                [
                    ("eq_quad_substitute", ["factor_number", "using_trans", "eq_solve_sub"]),
                    (
                        "eq_linear",
                        [
                            "write_as_diff_fact",
                            "extract_arg",
                            "extract_arg",
                            "extract_arg",
                            "quad_separate_zero_product",
                            "eq_linear",
                            "eq_linear",
                        ],
                    ),
                    ("sub_msg_ret", []),
                    ("eq_linear", ["quad_sqrt_sides", "quad_separate_signs"]),
                    ("eq_linear", ["quad_sqrt_sides", "quad_separate_signs"]),
                    ("solution_eq_num", []),
                ],
            )
        ],
    ),
    (
        "cubic_by_grouping",
        "{=({x^3-6x^2+11x-6},{0})}",
        [
            (
                0,
                [
                    ("write_as_diff_fact", []),
                    ("write_as_sum_fact", []),
                    ("extract_arg", []),
                    ("extract_arg", []),
                    ("extract_arg", []),
                    ("extract_arg", []),
                    ("write_as_diff_fact", []),
                    ("extract_arg", []),
                    ("extract_arg", []),
                    ("extract_arg", []),
                    ("quad_separate_zero_product", []),
                    (
                        "eq_linear",
                        ["rel_swap_right_const", "sub_with_self_remove_num", "add_with_zero"],
                    ),
                    (
                        "eq_linear",
                        ["rel_swap_right_const", "sub_with_self_remove_num", "add_with_zero"],
                    ),
                    (
                        "eq_linear",
                        ["rel_swap_right_const", "sub_with_self_remove_num", "add_with_zero"],
                    ),
                    ("solution_eq_num", []),
                ],
            )
        ],
    ),
    (
        "log_same_base",
        "{=({ln({x})},{ln({3})})}",
        [
            (
                0,
                [
                    (
                        "rel_restrictions_range",
                        ["rel_restrictions_log_arg", "rel_restrictions_range_complement"],
                    ),
                    ("eq_log_equalise", []),
                    ("rel_restrictions_check", []),
                ],
            ),
            (1, [("eq_log_formula_convert", [])]),
        ],
    ),
    (
        "log_with_base",
        "{=({log({x},{2})},{3})}",
        [
            (
                0,
                [
                    (
                        "rel_restrictions_range",
                        ["rel_restrictions_log_arg", "rel_restrictions_range_complement"],
                    ),
                    ("eq_log_formula_convert", []),
                    ("pow", ["pow_to_mul", "mul"]),
                    ("rel_restrictions_check", []),
                ],
            ),
            (1, [("eq_log_formula_convert", [])]),
        ],
    ),
    (
        "expand_square_of_sum",
        "{(x+1)^2}",
        [
            (
                0,
                [
                    ("using_expand", []),
                    ("product", ["mul_with_one"]),
                    ("pow_one", []),
                ],
            ),
            (
                1,
                [
                    ("write_as_product", []),
                    ("mul_bracket_cross_each", []),
                    (
                        "product",
                        ["pow_implicit_exp", "pow_implicit_exp", "pow_same_base_mul", "add"],
                    ),
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
            ),
        ],
    ),
    (
        "expand_square_of_difference",
        "{(x-2)^2}",
        [
            (
                0,
                [
                    ("using_expand", []),
                    ("product", ["mul_neg_pos", "mul"]),
                    ("pow", ["pow_to_mul", "mul"]),
                ],
            ),
            (
                1,
                [
                    ("write_as_product", []),
                    ("mul_bracket_cross_each", []),
                    (
                        "product",
                        ["pow_implicit_exp", "pow_implicit_exp", "pow_same_base_mul", "add"],
                    ),
                    ("mul", ["mul_neg_neg", "mul"]),
                    ("sum_suffix", ["sum_suffix_detail", "calc_diff"]),
                ],
            ),
        ],
    ),
    (
        "expand_product_of_brackets",
        "{(x+2)*(x-3)}",
        [
            (
                0,
                [
                    ("mul_bracket_cross_each", []),
                    (
                        "product",
                        ["pow_implicit_exp", "pow_implicit_exp", "pow_same_base_mul", "add"],
                    ),
                    ("mul", ["mul_neg_pos", "mul"]),
                    (
                        "sum_suffix",
                        ["sum_suffix_detail", "calc_sum", "sum_suffix_del_neg_one"],
                    ),
                ],
            ),
            (
                1,
                [
                    ("mul_bracket_cross_each_distributive", []),
                    ("mul_bracket", ["mul_bracket_each", "product"]),
                    ("mul_bracket", ["mul_bracket_each", "mul"]),
                    (
                        "sum_suffix",
                        ["sum_suffix_detail", "calc_sum", "sum_suffix_del_neg_one"],
                    ),
                ],
            ),
        ],
    ),
    (
        "quadratic_scaled_square_cards",
        "{=({3x^2},{12})}",
        [
            (
                1,
                [
                    ("eq_linear_div", ["eq_linear_div", "div_with_self", "quotient"]),
                    ("rel_move_left_const", ["rel_swap_left_const", "sub_with_self_num"]),
                    ("using_factor", ["write_as_num_arg", "using_factor"]),
                    ("quad_separate_zero_product", []),
                    (
                        "eq_linear",
                        ["rel_swap_right_const", "sub_with_self_remove_num", "add_with_zero"],
                    ),
                    (
                        "eq_linear",
                        ["rel_swap_right_const", "sub_with_self_remove_num", "add_with_zero"],
                    ),
                    ("solution_eq_num", []),
                ],
            ),
            (
                2,
                [
                    ("eq_linear_div", ["eq_linear_div", "div_with_self", "quotient"]),
                    ("rel_move_left_const", ["rel_swap_left_const", "sub_with_self_num"]),
                    ("quad_formula_abc", []),
                    ("add_with_zero", []),
                    ("mul_with_one", []),
                    ("mul_with_one", []),
                    ("pow_zero", []),
                    ("mul", ["mul_neg_neg", "mul"]),
                    ("add_with_zero", []),
                    ("root_square", ["pow_to_same_base", "root_reduce"]),
                    ("quad_separate_signs", []),
                    (
                        "frac_reduce_frac_num",
                        ["frac_div_num", "div", "div", "div_with_one"],
                    ),
                    (
                        "frac_reduce_frac_num",
                        ["frac_div_num", "div", "div", "div_with_one"],
                    ),
                    ("solution_eq_num", []),
                ],
            ),
            (
                3,
                [
                    ("eq_linear_div", ["eq_linear_div", "div_with_self", "quotient"]),
                    ("rel_move_left_const", ["rel_swap_left_const", "sub_with_self_num"]),
                    ("quad_formula_pq", []),
                    ("div_zero", []),
                    ("calculate_direct", []),
                    ("add_with_zero", []),
                    ("quad_separate_signs", []),
                    ("solution_eq_num", []),
                ],
            ),
        ],
    ),
    (
        "radical_extraneous_chain",
        "{=({root2({x+1})},{x-1})}",
        [
            (
                0,
                [
                    (
                        "eq_irrational_simple_square",
                        ["eq_irrational_simple_square", "root_reduce", "using_expand"],
                    ),
                    ("eq_del_opp", []),
                    ("rel_move_left_vars", ["rel_swap_left_vars", "sub_with_self_alg"]),
                    ("sum_suffix", ["sum_suffix_add_one", "sum_suffix_add_detail", "add"]),
                    ("extract_arg", []),
                    ("quad_separate_zero_product", []),
                    ("eq_linear", ["rel_move_right_const_eq", "eq_linear_neg"]),
                    ("solution_check_sub", []),
                    ("solution_check_sub", []),
                    ("simplify", ["add_with_zero", "root_one", "add_with_zero"]),
                    ("simplify", ["add", "sub", "root_square"]),
                    ("solution_check_f", []),
                    ("solution_check_t", []),
                    ("solution_eq_one", []),
                ],
            )
        ],
    ),
    (
        "two_radicals_chain",
        "{=({root2({x})+root2({x+1})},{2})}",
        [
            (
                0,
                [
                    (
                        "eq_irrational_simple_square",
                        ["eq_irrational_simple_square", "using_expand", "pow"],
                    ),
                    ("mul_bracket", ["mul_bracket_each", "product"]),
                    (
                        "sum_suffix",
                        [
                            "sum_suffix_add_one",
                            "sum_suffix_add_one",
                            "sum_suffix_add_detail",
                            "add",
                        ],
                    ),
                    (
                        "rel_move_right",
                        ["rel_swap_right", "sub_with_self_remove_alg", "sub_with_self_remove_num"],
                    ),
                    ("sub", []),
                    (
                        "eq_irrational_simple_square",
                        ["eq_irrational_simple_square", "pow_mul", "using_expand"],
                    ),
                    ("mul_bracket", []),
                    ("eq_del_opp", []),
                    ("rel_move_left_var", ["rel_swap_left_var", "sub_with_self_remove_alg"]),
                    ("sum_suffix", ["sum_suffix_add_detail", "add"]),
                    ("eq_linear_div", ["eq_linear_div", "div_with_self", "div_to_frac"]),
                    ("solution_check_sub", []),
                    (
                        "simplify",
                        ["root_square", "calc_sum", "root_square", "frac_add"],
                    ),
                    ("solution_check_t", []),
                ],
            )
        ],
    ),
    (
        "rational_simplify_cards",
        "{frac({x^2-1},{x-1})}",
        [
            (
                0,
                [
                    ("using_factor", ["write_as_num_arg", "using_factor"]),
                    ("frac_reduce_frac_alg", []),
                ],
            ),
            (
                1,
                [
                    ("excluded_values_denom", []),
                    (
                        "rel_move_right_const_eq",
                        ["rel_swap_right_const", "sub_with_self_remove_num", "add_with_zero"],
                    ),
                ],
            ),
        ],
    ),
    (
        "linear_standard_form",
        "{=({3x},{1})}",
        [
            (0, [("eq_linear_div", []), ("div_with_self", []), ("div_to_frac", [])]),
            (1, [("rel_swap_left_const", []), ("sub_with_self_num", [])]),
        ],
    ),
    (
        "cube_expansion_cards",
        "{(x+1)^3}",
        [
            (
                0,
                [
                    ("using_expand", []),
                    ("product", ["mul_with_one"]),
                    ("pow_one", []),
                    ("pow_one", []),
                    ("product", ["mul_with_one"]),
                ],
            ),
            (
                1,
                [
                    ("write_as_product", []),
                    ("mul_bracket_cross_each", []),
                    (
                        "product",
                        ["pow_implicit_exp", "pow_implicit_exp", "pow_same_base_mul", "add"],
                    ),
                    (
                        "sum_suffix",
                        [
                            "sum_suffix_add_one",
                            "sum_suffix_add_one",
                            "sum_suffix_add_detail",
                            "add",
                        ],
                    ),
                    ("mul_bracket_cross_each_no_foil", []),
                    ("product", ["pow_implicit_exp", "pow_same_base_mul", "add"]),
                    (
                        "product",
                        ["pow_implicit_exp", "pow_implicit_exp", "pow_same_base_mul", "add"],
                    ),
                    ("sum_suffix", ["sum_suffix_add_one", "sum_suffix_add_detail", "add"]),
                    ("sum_suffix", ["sum_suffix_add_one", "sum_suffix_add_detail", "add"]),
                ],
            ),
            (
                3,
                [
                    ("expand_binomial_pascal", []),
                    ("sigma_sum_convert", []),
                    ("choose_def_zero", []),
                    ("simplify", ["add_with_zero", "pow_one", "mul_with_one"]),
                    ("choose_def_one", []),
                    ("simplify", ["sub", "pow_one", "mul_with_one"]),
                    ("choose_simplify_minus_one", []),
                    ("simplify", ["sub", "pow_one", "mul_with_one", "pow_with_one"]),
                    ("choose_def_same", []),
                    ("simplify", ["sub_with_self_num", "pow_one", "mul_with_one", "pow_with_zero"]),
                    ("simplify", []),
                    ("mul_with_one", []),
                ],
            ),
            (4, [("expand_sigma", [])]),
        ],
    ),
    (
        "absolute_quadratic_inside",
        "{=({abs({x^2-4})},{3})}",
        [
            (
                0,
                [
                    ("eq_abs_branch", []),
                    (
                        "eq_linear",
                        [
                            "rel_move_right_const_eq",
                            "add",
                            "quad_sqrt_sides",
                            "quad_separate_signs",
                        ],
                    ),
                    (
                        "eq_linear",
                        [
                            "rel_move_right_const_eq",
                            "calc_sum",
                            "quad_sqrt_sides",
                            "quad_separate_signs",
                        ],
                    ),
                    ("solution_eq_num", []),
                ],
            )
        ],
    ),
    (
        "absolute_variable_right",
        "{=({abs({x-1})},{x})}",
        [
            (
                0,
                [
                    ("rel_move_left_var", ["rel_swap_left_var", "sub_with_self_alg"]),
                    ("eq_separate", []),
                    ("eq_linear", ["sub_with_self_remove_alg", "rel_el_of_zero"]),
                    (
                        "ineq_linear",
                        ["rel_swap_right_const", "sub_with_self_remove_num", "add_with_zero"],
                    ),
                    (
                        "eq_linear",
                        ["neg_neg_arg", "sum_suffix", "rel_move_right_const_eq", "eq_linear_div"],
                    ),
                    (
                        "ineq_linear",
                        ["rel_swap_right_const", "sub_with_self_remove_num", "add_with_zero"],
                    ),
                    ("intersection", []),
                    ("intersection", []),
                    ("union", []),
                ],
            )
        ],
    ),
    (
        "absolute_quadratic_right",
        "{=({abs({x})},{x^2-2})}",
        [
            (
                0,
                [
                    (
                        "rel_move_left_var",
                        ["rel_swap_left_var", "sub_with_self_remove_alg"],
                    ),
                    ("eq_separate", []),
                    (
                        "eq_linear",
                        [
                            "rel_move_left_const",
                            "var_order",
                            "eq_linear_neg",
                            "write_as_diff_fact",
                            "extract_arg",
                            "extract_arg",
                            "extract_arg",
                            "quad_separate_zero_product",
                            "eq_linear",
                            "eq_linear",
                        ],
                    ),
                    (
                        "eq_linear",
                        [
                            "rel_move_left_const",
                            "var_order",
                            "eq_linear_neg",
                            "write_as_diff_fact",
                            "extract_minus",
                            "extract_arg",
                            "extract_arg",
                            "quad_separate_zero_product",
                            "eq_linear",
                            "eq_linear",
                        ],
                    ),
                    ("intersection", []),
                    ("intersection", []),
                    ("solution_eq_num", []),
                ],
            )
        ],
    ),
    (
        "cube_root_equation",
        "{=({x^3},{8})}",
        [(0, [("write_as_num_arg", []), ("eq_root", ["eq_root", "root_reduce"])])],
    ),
    (
        "exponential_shifted",
        "{=({2^(x+1)},{8})}",
        [
            (
                0,
                [
                    ("pow_to_same_base", []),
                    ("exp_eq_exp_equalise", []),
                    (
                        "rel_move_right_const_eq",
                        ["rel_swap_right_const", "sub_with_self_remove_num"],
                    ),
                    ("sub", []),
                ],
            )
        ],
    ),
    (
        "absolute_zero",
        "{=({abs({x-2})},{0})}",
        [
            (
                0,
                [
                    ("eq_abs_as_linear", []),
                    (
                        "rel_move_right_const_eq",
                        [
                            "rel_swap_right_const",
                            "sub_with_self_remove_num",
                            "add_with_zero",
                        ],
                    ),
                ],
            )
        ],
    ),
    (
        "radical_zero",
        "{=({root2({x})},{0})}",
        [
            (
                0,
                [
                    ("eq_irrational_simple_equals_zero", []),
                    ("solution_check_sub", []),
                    ("root_zero", []),
                    ("solution_check_t", []),
                ],
            )
        ],
    ),
    (
        "fraction_zero",
        "{=({frac({x},{2})},{0})}",
        [(0, [("eq_linear_frac_zero", [])])],
    ),
]


def _entries(proto: str) -> list[CoreSolverVerticalResult]:
    """Все способы решения одного входа, по порядку."""
    node = parse_protocol(proto)
    if node.type is not T.EQUALS:
        # bare expressions are expanded by their own module, not by the equation router
        with contextlib.suppress(SolveError):
            shown = expression_cards.methods(node)
            if shown is not None and shown[1]:
                return [card.to_vertical() for card in shown[1]]
    data = solve(node)
    group = data.result.group(ResultGroupType.VERTICAL)
    assert group is not None, f"{proto}: нет вертикальной ветки"
    return [
        CoreSolverVerticalResult.from_contract(entry.result)
        for entry in group.entries
        if entry.result and "steps" in entry.result
    ]


def _outline(vertical: CoreSolverVerticalResult) -> list[tuple[str, list[str]]]:
    """Ключ каждого подшага и ключи его экрана подробностей.

    Учебные карточки (``lesson_*``) на экране подробностей пропускаются.
    """
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
def test_step_depth_matches(
    name: str, proto: str, methods: list[tuple[int, list[tuple[str, list[str]]]]]
) -> None:
    entries = _entries(proto)
    for index, expected in methods:
        assert index < len(entries), f"{name}: нет способа решения с индексом {index}"
        assert _outline(entries[index]) == expected, f"{name}: способ {index}"


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
def test_every_used_key_exists_with_matching_arity(
    name: str, proto: str, _methods: list[tuple[int, list[tuple[str, list[str]]]]]
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


# The counting card is on screen only where the app shows it: a non-monic quadratic
# with a linear term (cases ``q_a2_pos``, ``q_a3``) or complex roots
# (``quad_complex``). A monic quadratic with integer roots (x²−5x+6, x²+4x+3,
# x²−4x+4) has four cards and no counting card.
COUNTING_ANSWERS: list[tuple[str, str, list[str]]] = [
    ("{=({2x^2+5x+2},{0})}", "eq_quad_disc_solution_two", ["2"]),
    ("{=({3x^2-7x+2},{0})}", "eq_quad_disc_solution_two", ["2"]),
    ("{=({x^2+2x+5},{0})}", "eq_quad_disc_solution_zero", []),
    ("{=({x^2+2x+5},{0})}", "eq_quad_disc_solution_imag", ["2"]),
]


def _solutions(proto: str) -> list[dict[str, Any]]:
    data = solve(parse_protocol(proto))
    group = data.result.group(ResultGroupType.VERTICAL)
    assert group is not None, f"{proto}: нет вертикальной ветки"
    return [
        entry.result["solutionNode"]
        for entry in group.entries
        if entry.result and "solutionNode" in entry.result
    ]


@pytest.mark.parametrize(("proto", "key", "arguments"), COUNTING_ANSWERS)
def test_counting_card_answers_with_a_text_key(proto: str, key: str, arguments: list[str]) -> None:
    """The counting card answers ``TEXT[TEXT_KEY(key), args]``, not the bare number of roots."""
    texts = [
        node for node in _solutions(proto) if isinstance(node, dict) and node.get("type") == "TEXT"
    ]
    expected = {"type": "TEXT_KEY", "value": key, "children": []}
    assert any(
        node["children"][0] == expected
        and [child.get("value") for child in node["children"][1:]] == arguments
        for node in texts
    ), f"{proto}: нет TEXT[{key}] среди {[node.get('type') for node in texts]}"


def test_counting_card_text_is_rendered_in_the_requested_locale() -> None:
    """The service resolves the key to a word: no raw ``eq_quad_disc_*`` reaches the app."""
    from mymath_backend.service import solve_request

    contract = parse_protocol("{=({2x^2+5x+2},{0})}").to_contract()
    ru = json.dumps(solve_request(contract, locale="ru"), ensure_ascii=False)
    en = json.dumps(solve_request(contract, locale="en"), ensure_ascii=False)
    assert "Действительных корней: 2" in ru
    assert "2 real roots" in en
    assert "eq_quad_disc_solution_two" not in ru
    assert "eq_quad_disc_solution_two" not in en
