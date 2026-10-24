"""Тесты модуля уравнений.

Проверяются: значения ответа (для линейных и квадратных), порядок и ключи
шагов и то, что каждый выданный ключ есть в словаре объяснений с нужной
арностью. Корни читаются из узла ответа: ``EQUALS`` для одного корня и
``LIST`` из ``EQUALS`` для двух.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import sympy

from mymath_backend import CoreNode, load_explanations
from mymath_backend import CoreNodeType as T
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverGroup, CoreSolverVerticalResult
from mymath_backend.service import solve_request
from mymath_backend.solver import registered_types, solve
from mymath_backend.solver.sympy_bridge import to_sympy

EXPLANATIONS = Path(__file__).resolve().parents[1] / "mymath_backend" / "data" / "explanations.json"


def vertical_of(source: str) -> CoreSolverVerticalResult:
    data = solve(parse_protocol(source))
    vertical = data.result.vertical()
    assert vertical is not None
    return vertical


def step_keys(source: str) -> list[str]:
    vertical = vertical_of(source)
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


def roots_of(source: str) -> list[str]:
    """Значения корней: по одному на каждое ``x = …`` в ответе."""
    solution = vertical_of(source).solution
    assert solution is not None
    if solution.type is T.LIST:
        return [eq.children[1].value or "" for eq in solution.children]
    if solution.type is T.EQUALS:
        return [solution.children[1].value or ""]
    raise AssertionError(f"неожиданный узел ответа: {solution.type}")


def root_values(source: str) -> set[object]:
    """Корни ответа как значения sympy (для сюрдов и дробей)."""
    solution = vertical_of(source).solution
    assert solution is not None and solution.type is T.LIST
    return {sympy.simplify(to_sympy(eq.children[1])) for eq in solution.children}


class TestUnknownOverNumber:
    def test_rows_keep_the_root_through_every_equation(self) -> None:
        # multiply both sides at once; the second card moves 5 first.
        source = "{=({frac({x},{2})},{5})}"
        assert step_keys(source) == ["eq_mul_direct_denom", "frac_reduce_out", "mul"]
        second = _method_keys(_group(source).entries[1])
        assert second == ["rel_move_left_const", "eq_mul_direct_denom"]
        vertical = vertical_of(source)
        assert vertical.solution is not None and vertical.solution.children[1].value == "10"
        symbol = sympy.Symbol("x")
        for step in vertical.steps:
            for sub in step.substeps:
                for side in (sub.left, sub.right):
                    if side is not None and side.type is T.EQUALS:
                        residual = to_sympy(side.children[0]) - to_sympy(side.children[1])
                        assert sympy.solve(residual, symbol) == [10]

    def test_negative_constant_is_added(self) -> None:
        assert step_keys("{=({frac({x},{3})},{-2})}") == [
            "rel_move_left_const",
            "eq_mul_direct_denom",
        ]


class TestLinear:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("{=({2x+3},{7})}", "2"),
            ("{=({x+1},{3})}", "2"),
            ("{=({3x},{12})}", "4"),
            ("{=({x},{5})}", "5"),
            ("{=({2x},{0})}", "0"),
            ("{=({x-3},{0})}", "3"),
            ("{=({5-x},{2})}", "3"),
            ("{=({x/2},{3})}", "6"),
        ],
    )
    def test_roots(self, source: str, expected: str) -> None:
        assert roots_of(source) == [expected]

    def test_answer_is_equation_x_equals(self) -> None:
        vertical = vertical_of("{=({2x+3},{7})}")
        assert vertical.solution is not None
        assert vertical.solution.type is T.EQUALS
        assert vertical.solution.children[0].value == "x"
        assert vertical.solution.children[1].value == "2"

    def test_steps_move_then_divide(self) -> None:
        assert step_keys("{=({2x+3},{7})}") == ["rel_move_right_const_eq", "sub", "eq_linear_div"]

    def test_only_move_when_coefficient_is_one(self) -> None:
        assert step_keys("{=({x+1},{3})}") == ["rel_move_right_const_eq", "sub"]

    def test_only_divide_when_already_isolated(self) -> None:
        assert step_keys("{=({3x},{12})}") == ["eq_linear_div"]

    def test_no_steps_for_trivial_equation(self) -> None:
        assert step_keys("{=({x},{5})}") == []

    def test_header_on_every_step(self) -> None:
        vertical = vertical_of("{=({2x+3},{7})}")
        assert [[h.type for h in step.step_headers] for step in vertical.steps] == [
            ["rel_move_right_const_msg"],
            ["calculate_short"],
            ["divide_both_sides"],
        ]


class TestQuadratic:
    def test_two_rational_roots_are_sorted(self) -> None:
        assert roots_of("{=({x^2-5x+6},{0})}") == ["2", "3"]

    def test_difference_of_squares(self) -> None:
        assert roots_of("{=({x^2},{4})}") == ["-2", "2"]

    def test_double_root(self) -> None:
        # x^2 - 4x + 4 = (x-2)^2
        assert roots_of("{=({x^2-4x+4},{0})}") == ["2"]

    def test_irrational_roots_stay_exact(self) -> None:
        vertical = vertical_of("{=({x^2-2},{0})}")
        assert vertical.solution is not None
        assert vertical.solution.type is T.LIST
        assert step_keys("{=({x^2-2},{0})}") == [
            "rel_move_right_const_eq",
            "quad_sqrt_sides",
            "quad_separate_signs",
            "solution_eq_num",
        ]

    def test_zero_b_keeps_both_signs(self) -> None:
        # x^2 - 2 = 0: корни -√2 и +√2, а не √2 дважды.
        vertical = vertical_of("{=({x^2-2},{0})}")
        assert vertical.solution is not None and vertical.solution.type is T.LIST
        minus, plus = (eq.children[1] for eq in vertical.solution.children)
        assert minus.type is T.NEGATIVE and minus.children[0].type is T.ROOT2
        assert plus.type is T.ROOT2

    def test_negative_discriminant_gives_complex_roots(self) -> None:
        # the app: x^2 + 1 = 0 has no real root — the answer is «x ∉ ℝ», and the
        # complex roots x = -i and x = i live in the methods.
        vertical = vertical_of("{=({x^2+1},{0})}")
        assert vertical.solution is not None and vertical.solution.type is T.ELEMENT_NOT_OF
        answers = [
            entry.result["solutionNode"]
            for entry in _group("{=({x^2+1},{0})}").entries
            if entry.result and "solutionNode" in entry.result
        ]
        assert any(answer.get("type") == "LIST" for answer in answers)


class TestUnsupported:
    def test_degree_above_two_is_solved(self) -> None:
        # Кубические уравнения поддержаны (A4): x^3 = 1 -> x = 1.
        assert roots_of("{=({x^3},{1})}") == ["1"]

    def test_two_variables(self) -> None:
        # Больше одной буквы: параметрическое решение относительно x, альтернатива -- y.
        group = _group("{=({x+y},{1})}")
        assert group.select_method_text is not None
        assert group.select_method_text.type == "select_method"
        assert len(group.entries) == 6
        assert _method_keys(group.entries[0]) == ["rel_move_right_var", "eq_linear_param_sol"]
        assert _method_keys(group.entries[1]) == ["rel_move_right_var", "eq_linear_param_sol"]
        assert _method_keys(group.entries[2]) == ["rel_swap_left_const", "sub_with_self_num"]
        assert _method_keys(group.entries[3]) == ["rel_move_right_var", "var_order"]
        assert _method_keys(group.entries[4]) == [
            "eq_substitute_polar_two",
            "extract_arg",
            "eq_linear_div",
        ]
        assert group.entries[4].result["header"]["type"] == "rewrite_in_polar"
        assert _method_keys(group.entries[5])[0] == "rewrite_eq_in_slope_intercept"
        slope_header = group.entries[5].result["header"]
        assert slope_header["type"] == "find_slope_and_y_intercept"
        assert slope_header["args"] == [{"type": "VARIABLE", "value": "y"}]
        solution = CoreSolverVerticalResult.from_contract(group.entries[0].result).solution
        assert solution is not None and solution.type is T.LIST
        answer = solution.children[0]
        assert answer.type is T.EQUALS and answer.children[0].value == "x"
        assert answer.children[1].type is T.SUBTRACT
        assert solution.children[1].type is T.ELEMENT_OF

    def test_logarithm_equal_to_zero_sets_the_argument_to_one(self) -> None:
        # log10(x) = 0 -> the argument is 10^0 = 1.
        vertical = vertical_of("{=({log10({x})},{0})}")
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        assert "eq_log_zero_msg" in keys
        assert [h.type for h in vertical.steps[1].step_headers] == ["log_set_arg_zero"]
        assert roots_of("{=({log10({x})},{0})}") == ["1"]

    def test_rational_equation_is_solved(self) -> None:
        # 1/x = 2 -> x = 1/2; рациональные уравнения поддержаны (A1).
        assert roots_of("{=({1/x},{2})}") == ["1/2"]


class TestExplanationKeys:
    def test_steps_keys_exist_with_matching_arity(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        problems: list[str] = []
        for source in (
            "{=({2x+3},{7})}",
            "{=({3x},{12})}",
            "{=({x+1},{3})}",
            "{=({x^2-5x+6},{0})}",
        ):
            for key in step_keys(source):
                if key not in explanations:
                    problems.append(f"{source}: ключа {key} нет в словаре")
                    continue
                template = explanations.raw_template(key, DEFAULT_LOCALE) or ""
                used = {int(m) for m in re.findall(r"ARG(\d+)", template)}
                highest = max(used) if used else 0
                if highest != explanations.arity(key):
                    problems.append(f"{source}: у {key} арность {explanations.arity(key)}")
        assert problems == []


class TestRegistration:
    def test_equals_is_registered(self) -> None:
        assert T.EQUALS in registered_types()


def _group(source: str) -> CoreSolverGroup:
    return solve(parse_protocol(source)).result.groups[0]


def _method_keys(entry: object) -> list[str]:
    steps = entry.result["steps"]  # type: ignore[index]
    return [
        sub["description"]["type"]
        for step in steps
        for sub in step["substeps"]  # type: ignore[index]
    ]


class TestMethods:
    """Выбор способа решения: несколько записей вертикальной ветки."""

    def test_factorable_quadratic_has_four_methods(self) -> None:
        # The app shows the four solving methods; the helper cards are not on screen.
        group = _group("{=({x^2-5x+6},{0})}")
        assert len(group.entries) == 4
        assert group.select_method_text is not None
        assert group.select_method_text.type == "select_method"

    def test_row_family_is_factoring_then_formula(self) -> None:
        # x^2 - 5x + 6 = 0 opens with factoring.
        group = _group("{=({x^2-5x+6},{0})}")
        assert [len(_method_keys(e)) for e in group.entries] == [8, 12, 9, 8]
        assert _method_keys(group.entries[0])[0] == "write_as_diff_fact"
        assert _method_keys(group.entries[1])[0] == "quad_formula_abc"

    def test_difference_of_squares_has_root_extraction_then_factoring(self) -> None:
        # x^2 - 4 = 0.
        group = _group("{=({x^2-4},{0})}")
        assert _method_keys(group.entries[0]) == [
            "rel_move_right_const_eq",
            "quad_sqrt_sides",
            "quad_separate_signs",
            "solution_eq_num",
        ]
        assert _method_keys(group.entries[1]) == [
            "using_factor",
            "quad_separate_zero_product",
            "eq_linear",
            "eq_linear",
            "solution_eq_num",
        ]

    def test_positive_terms_are_written_as_a_sum(self) -> None:
        # x^2 + 4x + 3 = 0 splits 4x into 3x + x.
        group = _group("{=({x^2+4x+3},{0})}")
        assert _method_keys(group.entries[0]) == [
            "write_as_sum_fact",
            "extract_arg",
            "extract_arg",
            "quad_separate_zero_product",
            "eq_linear",
            "eq_linear",
            "solution_eq_num",
        ]

    def test_formula_with_a_negative_c_adds_under_the_root(self) -> None:
        # x^2 - x - 6 = 0 -> sqrt(1 + 24) -> 5.
        group = _group("{=({x^2-x-6},{0})}")
        assert _method_keys(group.entries[1]) == [
            "quad_formula_abc",
            "mul_with_one",
            "mul_with_one",
            "neg_neg_arg",
            "pow",
            "mul",
            "add",
            "root_square",
            "quad_separate_signs",
            "calculate_direct",
            "calculate_direct",
            "solution_eq_num",
        ]

    def test_pq_formula_divides_by_the_leading_coefficient_first(self) -> None:
        # 2x^2 + 3x - 2 = 0 -> x^2 + (3/2)x - 1 = 0 -> PQ.
        group = _group("{=({2x^2+3x-2},{0})}")
        assert _method_keys(group.entries[2]) == [
            "eq_linear_div",
            "quad_formula_pq",
            "frac_complex_resolve_call",
            "frac_complex_resolve_call",
            "neg_neg_arg",
            "pow_frac",
            "calc_sum",
            "root_square",
            "quad_separate_signs",
            "calc_sum",
            "calc_diff",
            "solution_eq_num",
        ]

    def test_negative_discriminant_gives_complex_roots_and_the_discriminant_cards(self) -> None:
        # x^2 + 2x + 5 = 0 has the roots -1 +- 2i.
        group = _group("{=({x^2+2x+5},{0})}")
        assert len(group.entries) == 9
        assert _method_keys(group.entries[0]) == [
            "quad_formula_abc",
            "mul_with_one",
            "mul_with_one",
            "pow",
            "mul",
            "calc_diff",
            "root_square",
            "quad_separate_signs",
            "simplify",
            "simplify",
            "solution_eq_num",
        ]
        assert _method_keys(group.entries[1])[-1] == "root_sqr_neg"
        # верхний ответ — «x ∉ ℝ», комплексные корни остаются в способе.
        service = solve_request(parse_protocol("{=({x^2+2x+5},{0})}").to_contract(), locale="ru")[
            "result"
        ]
        top = CoreNode.from_contract(service["solution"])
        assert top.type is T.ELEMENT_NOT_OF
        assert [child.value for child in top.children] == ["x", "ℝ"]
        first = group.entries[0].result
        assert first is not None and first["solutionNode"]["type"] == "LIST"

    def test_positive_leading_coefficient_quadratic_has_the_cards(self) -> None:
        # 2x^2+5x+2=0 is factoring, formula, PQ, square, 2 helpers.
        group = _group("{=({2x^2+5x+2},{0})}")
        assert len(group.entries) == 6
        assert _method_keys(group.entries[0])[0] == "write_as_sum_fact"
        assert _method_keys(group.entries[1])[:2] == ["quad_formula_abc", "pow"]
        assert _method_keys(group.entries[2])[:2] == ["eq_linear_div", "quad_formula_pq"]

    def test_irrational_quadratic_has_the_extraction_and_the_discriminant_cards(self) -> None:
        group = _group("{=({x^2-2},{0})}")
        assert len(group.entries) == 5
        assert _method_keys(group.entries[3])[-1] == "eq_quad_disc_solution_all_gt"

    def test_bracket_times_number_is_divide_move_calculate(self) -> None:
        # 2(x+1)=8 is three rows and a single method.
        group = _group("{=({2*(x+1)},{8})}")
        assert len(group.entries) == 1
        assert _method_keys(group.entries[0]) == [
            "eq_linear_div",
            "rel_move_right_const_eq",
            "sub",
        ]
        assert vertical_of("{=({2*(x-3)},{8})}").solution is not None

    def test_linear_has_two_methods(self) -> None:
        group = _group("{=({2x+3},{7})}")
        assert len(group.entries) == 2
        assert _method_keys(group.entries[0]) == ["rel_move_right_const_eq", "sub", "eq_linear_div"]
        assert _method_keys(group.entries[1]) == ["eq_linar_divide_both_sides", "move"]

    def test_linear_without_constant_has_one_method(self) -> None:
        # 3x = 12: делить до переноса нечего, способ один.
        group = _group("{=({3x},{12})}")
        assert len(group.entries) == 1


class TestDegenerate:
    """Тождество и противоречие: ответ — текст шага, без узла ответа."""

    def test_no_solution(self) -> None:
        group = _group("{=({2x+3},{2x+5})}")
        assert _method_keys(group.entries[0]) == ["eq_del_opp", "rel_el_of_zero"]
        assert "solutionNode" not in group.entries[0].result

    def test_identity(self) -> None:
        group = _group("{=({x+1},{x+1})}")
        assert _method_keys(group.entries[0]) == ["solutions_inf_many"]
        assert "solutionNode" not in group.entries[0].result


def test_reciprocal_equation_has_the_five_rows() -> None:
    group = _group("{=({frac({1},{x})},{2})}")
    assert len(group.entries) == 1
    assert _method_keys(group.entries[0]) == [
        "rel_restrictions_range",
        "eq_mul_direct_denom",
        "rel_swap_eq",
        "eq_linear_div",
        "rel_restrictions_check",
    ]


def test_negative_leading_coefficient_adds_standard_and_implicit_form_cards() -> None:
    # -2x+3=7 has the ordinary card plus two more.
    group = _group("{=({-2x+3},{7})}")
    assert len(group.entries) == 3
    assert _method_keys(group.entries[1])[-1] == "eq_linear_neg"
    assert _method_keys(group.entries[2])[0] == "rel_move_left_const"


def test_positive_sum_quadratic_has_four_methods() -> None:
    # factoring, formula, PQ formula and the square.
    group = _group("{=({x^2+4x+3},{0})}")
    assert len(group.entries) == 4
    assert _method_keys(group.entries[1])[:2] == ["quad_formula_abc", "mul_with_one"]
    assert _method_keys(group.entries[2])[0] == "quad_formula_pq"


def test_difference_of_squares_equation_has_four_methods() -> None:
    # x^2-4=0 is extraction, factoring, roots formula, PQ formula.
    group = _group("{=({x^2-4},{0})}")
    assert len(group.entries) == 4
    assert _method_keys(group.entries[2])[0] == "quad_formula_abc"
    assert _method_keys(group.entries[3])[0] == "quad_formula_pq"


def test_completing_the_square_divides_by_a_first_when_a_is_above_one() -> None:
    # 2x^2+3x-2=0 divides both sides by 2 after moving the constant.
    group = _group("{=({2x^2+3x-2},{0})}")
    square = _method_keys(group.entries[3])
    assert square[:3] == ["rel_move_right_const_eq", "eq_linear_div", "conics_complete_square_both"]


def test_square_equal_to_a_number_moves_the_constant_only_on_the_other_cards() -> None:
    # x^2=9 takes the root at once, the other cards move 9 left first.
    group = _group("{=({x^2},{9})}")
    assert len(group.entries) == 4
    assert _method_keys(group.entries[0])[0] == "quad_sqrt_sides"
    assert all(_method_keys(entry)[0] == "rel_move_left_const" for entry in group.entries[1:])


def test_scaled_square_divides_first_on_every_card() -> None:
    # 3x^2=12 has four cards that all divide by 3 early.
    group = _group("{=({3x^2},{12})}")
    assert len(group.entries) == 4
    assert _method_keys(group.entries[0])[0] == "eq_linear_div"
    assert _method_keys(group.entries[1])[:2] == ["eq_linear_div", "rel_move_left_const"]


def test_irrational_roots_get_the_five_cards() -> None:
    # quad_gap: x^2 + 4x + 2 = 0 (D = 8) — formula, PQ, the square and the two helpers.
    source = "{=({x^2+4x+2},{0})}"
    group = _group(source)
    assert [(entry.result or {}).get("header", {}).get("type") for entry in group.entries] == [
        "eq_quad_formula",
        "eq_quad_pq",
        "eq_quad_cs",
        "find_num_of_solutions",
        "evaluate",
    ]
    first = _method_keys(group.entries[0])
    assert first[:3] == ["quad_formula_abc", "mul_with_one", "mul_with_one"]
    assert "root_partial" in _method_keys(group.entries[0])
    assert set(root_values(source)) == {-2 - sympy.sqrt(2), -2 + sympy.sqrt(2)}


def test_right_side_constant_moves_left_on_every_card() -> None:
    # quad_gap: x^2 - x - 6 = 1 -> x^2 - x - 7 = 0; The app opens each card with the move.
    source = "{=({x^2-x-6},{1})}"
    group = _group(source)
    assert len(group.entries) == 5
    assert _method_keys(group.entries[0])[:2] == ["rel_move_left_const", "calc_diff"]
    assert _method_keys(group.entries[1])[:2] == ["rel_move_left_const", "calc_diff"]
    assert _method_keys(group.entries[3])[0] == "eq_quad_std_form"
    assert set(root_values(source)) == {
        (1 - sympy.sqrt(29)) / 2,
        (1 + sympy.sqrt(29)) / 2,
    }


def test_right_side_constant_without_a_typed_one_has_nothing_to_combine() -> None:
    # The app (explog/x03): x² − 4x = 5 → x² − 4x − 5 = 0, then the factoring rows; no calc_diff.
    group = _group("{=({x^2-4x},{5})}")
    assert _method_keys(group.entries[0])[:2] == ["rel_move_left_const", "write_as_diff_fact"]


def test_missing_constant_keeps_the_common_factor_cards() -> None:
    # quad_gap: x^2 - 4x + 0 = 0 — four solving cards, each dropping the typed +0 first.
    source = "{=({x^2-4x+0},{0})}"
    group = _group(source)
    assert len(group.entries) == 4
    assert _method_keys(group.entries[0])[:2] == ["add_with_zero", "extract_arg"]
    assert _method_keys(group.entries[1])[:2] == ["add_with_zero", "quad_formula_abc"]
    assert roots_of(source) == ["0", "4"]


def test_complex_roots_with_any_lead_have_the_nine_cards() -> None:
    # quad_gap: 2x^2 + 3x + 3 = 0 (D = -15) — every method twice, plus the counting cards.
    source = "{=({2x^2+3x+3},{0})}"
    group = _group(source)
    assert [(entry.result or {}).get("header", {}).get("type") for entry in group.entries] == [
        "eq_quad_formula",
        "eq_quad_formula",
        "eq_quad_pq",
        "eq_quad_pq",
        "eq_quad_cs",
        "eq_quad_cs",
        "find_num_of_real_solutions",
        "find_num_of_imag_solutions",
        "evaluate",
    ]
    assert _method_keys(group.entries[1])[-1] == "root_sqr_neg"
    top = solve_request(parse_protocol(source).to_contract(), locale="ru")["result"]["solution"]
    assert CoreNode.from_contract(top).type is T.ELEMENT_NOT_OF


def test_square_equal_to_a_negative_or_surd_number_has_the_square_cards() -> None:
    # quad_gap: x^2 = -2 (no real root, seven cards) and 3x^2 = 1 (a surd, five cards).
    negative = _group("{=({x^2},{-2})}")
    assert [(entry.result or {}).get("header", {}).get("type") for entry in negative.entries] == [
        None,
        None,
        "eq_quad_formula",
        "eq_quad_pq",
        "find_num_of_real_solutions",
        "find_num_of_imag_solutions",
        "evaluate",
    ]
    assert _method_keys(negative.entries[0]) == ["rel_terminators_pow_no_sol"]
    assert _method_keys(negative.entries[1])[:2] == ["quad_sqrt_sides", "quad_separate_signs"]

    surd = _group("{=({3x^2},{1})}")
    assert [(entry.result or {}).get("header", {}).get("type") for entry in surd.entries] == [
        None,
        "eq_quad_formula",
        "eq_quad_pq",
        "find_num_of_solutions",
        "evaluate",
    ]
    assert _method_keys(surd.entries[0])[:2] == ["eq_linear_div", "quad_sqrt_sides"]
    assert root_values("{=({3x^2},{1})}") == {-sympy.sqrt(3) / 3, sympy.sqrt(3) / 3}


def test_decimal_constant_gets_the_five_cards() -> None:
    # dec_gap: x^2 - x - 0.5 = 0 — the formula card divides by 0.5, the PQ and the
    # square keep the fraction; the counting cards show the decimal itself.
    source = "{=({x^2-x-0.5},{0})}"
    group = _group(source)
    assert [(entry.result or {}).get("header", {}).get("type") for entry in group.entries] == [
        "eq_quad_formula",
        "eq_quad_pq",
        "eq_quad_cs",
        "find_num_of_solutions",
        "evaluate",
    ]
    assert _method_keys(group.entries[0])[:2] == ["eq_linear_div", "quad_formula_abc"]
    assert _method_keys(group.entries[1])[0] == "dec_to_frac"
    assert _method_keys(group.entries[2])[:2] == ["dec_to_frac", "rel_move_right_const_eq"]
    assert root_values(source) == {
        (1 - sympy.sqrt(3)) / 2,
        (1 + sympy.sqrt(3)) / 2,
    }


def test_decimal_constant_with_a_leading_coefficient_divides_by_a() -> None:
    # dec_gap: 2x^2 + 3x - 0.5 = 0 — the PQ card divides by 2 before the PQ rows.
    source = "{=({2x^2+3x-0.5},{0})}"
    group = _group(source)
    assert len(group.entries) == 5
    assert _method_keys(group.entries[0])[:2] == ["eq_linear_div", "quad_formula_abc"]
    assert _method_keys(group.entries[1])[:3] == [
        "dec_to_frac",
        "eq_linear_div",
        "quad_formula_pq",
    ]
    assert root_values(source) == {
        (-3 - sympy.sqrt(13)) / 4,
        (-3 + sympy.sqrt(13)) / 4,
    }


def test_decimal_on_the_right_moves_left_after_doubling() -> None:
    # dec_gap: x^2 - x - 6 = 0.5 — the formula card doubles first, then moves 1 left;
    # the PQ card turns 0.5 into 1/2 and the square card moves the constant right.
    source = "{=({x^2-x-6},{0.5})}"
    group = _group(source)
    assert len(group.entries) == 5
    assert _method_keys(group.entries[0])[:4] == [
        "eq_linear_div",
        "rel_move_left_const",
        "calc_diff",
        "quad_formula_abc",
    ]
    assert _method_keys(group.entries[1])[:3] == [
        "dec_to_frac",
        "rel_move_left_const",
        "calc_diff",
    ]
    assert _method_keys(group.entries[2])[:3] == [
        "dec_to_frac",
        "rel_move_right_const_eq",
        "calc_sum",
    ]
    assert root_values(source) == {
        (1 - 3 * sympy.sqrt(3)) / 2,
        (1 + 3 * sympy.sqrt(3)) / 2,
    }


def test_decimal_square_is_extracted_from_a_fraction() -> None:
    # dec_gap: x^2 = 0.5 — 0.5 → 1/2, then the root card; formula and PQ keep the fraction.
    group = _group("{=({x^2},{0.5})}")
    assert [(entry.result or {}).get("header", {}).get("type") for entry in group.entries] == [
        "solve_using_sqrt",
        "eq_quad_formula",
        "eq_quad_pq",
        "find_num_of_solutions",
        "evaluate",
    ]
    assert _method_keys(group.entries[0])[:2] == ["dec_to_frac", "quad_sqrt_sides"]
    assert root_values("{=({x^2},{0.5})}") == {
        -sympy.sqrt(2) / 2,
        sympy.sqrt(2) / 2,
    }


def test_decimal_square_with_a_leading_coefficient_divides() -> None:
    # dec_gap: 3x^2 = 0.5 — 0.5 → 1/2, then divide by 3 before taking the root.
    source = "{=({3x^2},{0.5})}"
    group = _group(source)
    assert len(group.entries) == 5
    assert _method_keys(group.entries[0])[:3] == [
        "dec_to_frac",
        "eq_linear_div",
        "quad_sqrt_sides",
    ]
    assert root_values(source) == {-sympy.sqrt(6) / 6, sympy.sqrt(6) / 6}


def test_decimal_constant_on_the_left_is_cleared_by_dividing_by_a_half() -> None:
    # dec_gap: x^2 - 0.5 = 0 — divide by 0.5, move 1 right, divide by 2, then take the root.
    group = _group("{=({x^2-0.5},{0})}")
    assert len(group.entries) == 5
    assert _method_keys(group.entries[0])[:4] == [
        "eq_linear_div",
        "rel_move_right_const_eq",
        "eq_linear_div",
        "quad_sqrt_sides",
    ]
    assert root_values("{=({x^2-0.5},{0})}") == {
        -sympy.sqrt(2) / 2,
        sympy.sqrt(2) / 2,
    }


def test_decimal_complex_roots_put_the_real_domain_cards_first() -> None:
    # dec_gap: x^2 + 2x + 5 = 0.5 — the app's nine cards, the real-domain triple first.
    source = "{=({x^2+2x+5},{0.5})}"
    group = _group(source)
    assert [(entry.result or {}).get("header", {}).get("type") for entry in group.entries] == [
        "eq_quad_formula",
        "eq_quad_pq",
        "eq_quad_cs",
        "eq_quad_formula",
        "eq_quad_pq",
        "eq_quad_cs",
        "find_num_of_real_solutions",
        "find_num_of_imag_solutions",
        "evaluate",
    ]
    assert _method_keys(group.entries[0])[-1] == "root_sqr_neg"
    top = solve_request(parse_protocol(source).to_contract(), locale="ru")["result"]["solution"]
    assert CoreNode.from_contract(top).type is T.ELEMENT_NOT_OF
    answers = [entry.result.get("solutionNode") for entry in group.entries if entry.result]
    assert any(answer is not None and answer["type"] == "LIST" for answer in answers)


def test_log10_equation_has_the_solve_and_rewrite_cards() -> None:
    # log10(x)=2 is four rows plus a "rewrite as a power" card.
    group = _group("{=({log10({x})},{2})}")
    assert len(group.entries) == 2
    assert _method_keys(group.entries[0]) == [
        "rel_restrictions_range",
        "eq_log_formula_convert",
        "pow",
        "rel_restrictions_check",
    ]
    assert _method_keys(group.entries[1]) == ["eq_log_formula_convert"]


def test_x_squared_minus_x_has_four_cards() -> None:
    # x^2-x=0 is factoring, formula, PQ and the square.
    group = _group("{=({x^2-x},{0})}")
    assert len(group.entries) == 4
    assert _method_keys(group.entries[0]) == [
        "extract_arg",
        "quad_separate_zero_product",
        "eq_linear",
        "solution_eq_num",
    ]
    assert roots_of("{=({x^2-x},{0})}") == ["0", "1"]


def test_unknown_on_both_sides_with_a_negative_net_coefficient_has_three_cards() -> None:
    # -x+5=2x-1 repeats the plain rows and adds an implicit-form card.
    group = _group("{=({-x+5},{2x-1})}")
    assert len(group.entries) == 3
    assert _method_keys(group.entries[2])[0] == "rel_move_left"
    assert roots_of("{=({-x+5},{2x-1})}") == ["2"]


def test_bracket_with_the_unknown_on_the_other_side_is_distributed_first() -> None:
    # 3(x-2)=2x+1 opens the bracket, moves terms, collects.
    assert step_keys("{=({3*(x-2)},{2x+1})}")[0] == "mul_bracket"
    assert roots_of("{=({3*(x-2)},{2x+1})}") == ["7"]


def test_decimal_coefficient_equation_has_a_divide_card_and_an_implicit_card() -> None:
    # 0,5x=2 divides by 0,5 or scales by 10 first.
    group = _group("{=({0.5x},{2})}")
    assert len(group.entries) == 2
    assert _method_keys(group.entries[0]) == ["eq_linear_div", "div_with_self", "div"]
    assert roots_of("{=({0.5x},{2})}") == ["4"]


def test_negative_leading_square_has_four_cards() -> None:
    # extraction, factoring, formula and PQ formula.
    group = _group("{=({-x^2+4},{0})}")
    assert len(group.entries) == 4
    assert _method_keys(group.entries[0])[:2] == ["rel_move_right_const_eq", "eq_linear_neg"]
    assert _method_keys(group.entries[1])[0] == "var_order"
    assert roots_of("{=({-x^2+4},{0})}") == ["-2", "2"]


def test_sum_of_two_unknown_fractions_has_three_cards() -> None:
    # x/2 + x/3 = 5 clears denominators, or adds the fractions first.
    group = _group("{=({frac({x},{2})+frac({x},{3})},{5})}")
    assert len(group.entries) == 3
    assert _method_keys(group.entries[0]) == ["eq_mul_direct_denom", "sum_suffix", "eq_linear_div"]
    assert roots_of("{=({frac({x},{2})+frac({x},{3})},{5})}") == ["6"]


def test_quadratic_roots_with_a_square_factor_in_the_discriminant_are_simplified() -> None:
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    solution = solve(parse_protocol("{=({x^2+2x-1},{0})}")).result.vertical().solution
    assert solution is not None and "ROOT2(8)" not in repr(solution.to_contract()).replace("'", "")
    values = [child.children[1] for child in solution.children]
    assert all(v.type.name in ("SUBTRACT", "ADD") for v in values)


def test_fractions_with_numeric_denominators_give_an_exact_answer() -> None:
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    source = "{=({frac({2x-1},{3})-frac({x+2},{4})},{1})}"
    solution = solve(parse_protocol(source)).result.vertical().solution
    assert solution is not None and solution.children[1].value == "22/5"


def test_formula_card_for_a_leading_coefficient_above_one_and_negative_b() -> None:
    from mymath_backend.input import parse_protocol
    from mymath_backend.solver import solve

    entries = solve(parse_protocol("{=({2x^2-x-1},{0})}")).result.groups[0].entries
    formula = next(
        e
        for e in entries
        if e.result["steps"][0]["substeps"][0]["description"]["type"] == "quad_formula_abc"
    )
    first_pages = [len(st["substeps"]) for st in formula.result["steps"]]
    assert first_pages[:2] == [
        1,
        4,
    ]  # the formula, then four pages starting with the bracket removal


def test_unknown_plus_a_fraction_moves_it_then_subtracts_fractions() -> None:
    vertical = solve(parse_protocol("{=({frac({2},{3})+x},{frac({5},{6})})}")).result.vertical()
    assert vertical is not None and vertical.solution is not None
    assert [s.description.type for st in vertical.steps for s in st.substeps] == [
        "rel_move_right_const_eq",
        "frac_sub",
    ]
    answer = vertical.solution.children[1]
    assert answer.type is T.FRACTION and [c.value for c in answer.children] == ["1", "6"]


def test_power_with_a_shifted_exponent_equalises_then_moves_the_constant() -> None:
    vertical = solve(parse_protocol("{=({2^(x+1)},{8})}")).result.vertical()
    assert vertical is not None and vertical.solution is not None
    assert [s.description.type for st in vertical.steps for s in st.substeps] == [
        "pow_to_same_base",
        "exp_eq_exp_equalise",
        "rel_move_right_const_eq",
        "sub",
    ]
    assert vertical.solution.children[1].value == "2"


def test_pq_formula_with_an_even_p_reduces_the_fraction_and_opens_the_brackets() -> None:
    # x^2-4x-5=0, third card.
    group = _group("{=({x^2-4x-5},{0})}")
    assert _method_keys(group.entries[2]) == [
        "quad_formula_pq",
        "frac_reduce_frac_num",
        "calculate_direct",
        "neg_neg_arg",
        "quad_separate_signs",
        "add",
        "calc_diff",
        "solution_eq_num",
    ]


def test_x_squared_plus_x_minus_six_has_formula_and_pq_cards_with_a_positive_p() -> None:
    # factoring, formula, PQ formula and the square.
    group = _group("{=({x^2+x-6},{0})}")
    assert len(group.entries) == 4
    assert _method_keys(group.entries[1])[:3] == [
        "quad_formula_abc",
        "mul_with_one",
        "mul_with_one",
    ]
    assert _method_keys(group.entries[2])[:3] == ["quad_formula_pq", "pow_frac", "neg_neg_arg"]


def test_three_x_squared_minus_seven_x_plus_two_has_six_cards() -> None:
    # factoring, formula, PQ (after dividing by 3), square, two helpers.
    group = _group("{=({3x^2-7x+2},{0})}")
    assert len(group.entries) == 6
    assert _method_keys(group.entries[2])[:2] == ["eq_linear_div", "quad_formula_pq"]
    assert _method_keys(group.entries[3])[:2] == ["rel_move_right_const_eq", "eq_linear_div"]
    assert _method_keys(group.entries[3])[-1] == "solution_eq_num"


def test_negative_leading_coefficient_cards_start_by_changing_the_signs() -> None:
    # -x^2+5x-6=0 -> four cards, each opens with the sign change.
    group = _group("{=({-x^2+5x-6},{0})}")
    assert len(group.entries) == 4
    assert all(_method_keys(entry)[0] == "eq_linear_neg" for entry in group.entries[:3])
    # The square card moves the constant first, then changes the signs (one row, not two).
    assert _method_keys(group.entries[3])[:2] == ["rel_move_right_const_eq", "eq_mul_direct_one"]
    vertical = vertical_of("{=({-x^2+5x-6},{0})}")
    assert vertical.solution is not None
    assert sorted(e.children[1].value for e in vertical.solution.children) == ["2", "3"]


def test_negative_leading_square_changes_the_signs_on_a_single_row() -> None:
    # Case ``q_negA``, card «…полного квадрата»: eight rows, the second one is
    # «Умножить обе части уравнения на -1». An extra prefix row repeated it,
    # which made the card one row longer than the app's.
    group = _group("{=({-x^2+5x-6},{0})}")
    square = group.entries[3].result["steps"]
    assert len(square) == 8
    assert [sub["description"]["type"] for sub in square[1]["substeps"]] == ["eq_mul_direct_one"]
    assert square[1]["substeps"][0]["subresult"] is not None


def test_helper_cards_follow_the_app_not_the_native_solver() -> None:
    # The native solver returns «Количество решений» and «Вычислите дискриминант»
    # for every quadratic; the app shows them only where the roots are not
    # obvious (cases ``q_a2_pos``/``quad_irr`` vs ``quad_factor``/``eq_3x2``).
    def variants(source: str) -> list[str]:
        group = _group(source)
        return [(entry.result or {}).get("header", {}).get("type") for entry in group.entries]

    assert "find_num_of_solutions" in variants("{=({2x^2+5x+2},{0})}")
    assert "evaluate" in variants("{=({2x^2+5x+2},{0})}")
    for monic in ("{=({x^2-5x+6},{0})}", "{=({x^2+4x+3},{0})}", "{=({x^2-4x+4},{0})}"):
        assert "find_num_of_solutions" not in variants(monic), monic
    assert "find_num_of_solutions" not in variants("{=({3x^2},{12})}")


def test_two_x_squared_minus_x_minus_one_has_the_scaled_pq_card_with_a_negative_q() -> None:
    # the PQ card opens the brackets of -(-1/2) on the sign row.
    group = _group("{=({2x^2-x-1},{0})}")
    keys = next(
        k for k in map(_method_keys, group.entries) if k[:2] == ["eq_linear_div", "quad_formula_pq"]
    )
    assert keys[2:5] == ["frac_resolve_neg", "frac_extract_neg", "neg_neg_arg"]


def test_fractional_linear_equation_also_has_standard_and_implicit_forms() -> None:
    # 2/3 + x = 5/6 -> three cards; the last one ends with 6x - 1 = 0.
    group = _group("{=({frac({2},{3})+x},{frac({5},{6})})}")
    assert len(group.entries) == 3
    assert _method_keys(group.entries[1])[-1] == "eq_mul_direct_denom"
    assert _method_keys(group.entries[2])[-1] == "var_order"


def test_equations_with_the_number_e_are_solved_exactly_with_a_logarithm() -> None:
    for source, argument in (
        ("{=({\\e^x},{5})}", "5"),
        ("{=({2*\\e^x},{8})}", "4"),
        ("{=({5*\\e^x-2},{8})}", "2"),
    ):
        solution = vertical_of(source).solution
        assert solution is not None and solution.children[1].type is T.LN
        assert solution.children[1].children[0].value == argument


def test_irrational_roots_never_have_a_negative_denominator() -> None:
    for source in ("{=({-x^2+3x-1},{0})}", "{=({-2x^2+x+5},{0})}"):
        solution = vertical_of(source).solution
        assert solution is not None
        for equation in solution.children:
            denominator = equation.children[1].children[1]
            assert denominator.type is T.CONSTANT and int(denominator.value or 0) > 0
    assert vertical_of("{=({\\e^x},{-1})}").solution is None


def test_fractions_that_cancel_give_all_reals_but_the_poles_or_nothing() -> None:
    union = vertical_of("{=({frac({2x+2},{x+1})},{2})}").solution
    assert union is not None and union.type is T.UNION
    assert union.children[0].children[1].value == "-1"
    assert vertical_of("{=({frac({x^2-1},{x-1})},{x+1})}").solution is not None
    assert vertical_of("{=({frac({x+1},{x+1})},{3})}").solution is None


def test_quadratic_cards_carry_method_headers() -> None:
    # the app: the cards are titled by their method, and the count card by its verdict.
    group = _group("{=({x^2-5x+6},{0})}")
    headers = [(entry.result or {}).get("header", {}).get("type") for entry in group.entries]
    assert headers == [None, "eq_quad_formula", "eq_quad_pq", "eq_quad_cs"]


def test_complex_counting_cards_have_real_and_imaginary_headers() -> None:
    group = _group("{=({x^2+2x+5},{0})}")
    headers = [(entry.result or {}).get("header", {}).get("type") for entry in group.entries]
    assert "find_num_of_real_solutions" in headers
    assert "find_num_of_imag_solutions" in headers


def test_completing_square_steps_use_the_eq_add_exp_header() -> None:
    # The app titles the square-completion step with eq_add_exp, not with the row key.
    group = _group("{=({x^2+2x+5},{0})}")
    headers = [
        header["type"]
        for entry in group.entries
        for step in entry.result["steps"]
        for header in step.get("headers") or []
    ]
    assert "eq_add_exp" in headers


def test_implicit_form_and_log_rewrite_cards_have_headers() -> None:
    assert _group("{=({3x},{1})}").entries[1].result["header"]["type"] == "rewrite_in_implicit_form"
    assert (
        _group("{=({ln({x})},{ln({3})})}").entries[1].result["header"]["type"] == "rewrite_in_expo"
    )


def test_fraction_equal_to_zero_is_its_numerator_card() -> None:
    vertical = vertical_of("{=({frac({x},{2})},{0})}")
    assert [h.type for step in vertical.steps for h in step.step_headers] == ["frac_set_num_zero"]
    assert [sub.description.type for step in vertical.steps for sub in step.substeps] == [
        "eq_linear_frac_zero"
    ]


def test_root_equal_to_zero_is_its_radicand_card() -> None:
    vertical = vertical_of("{=({root2({x})},{0})}")
    assert [h.type for step in vertical.steps for h in step.step_headers] == [
        "root_set_rad_zero",
        "solution_check_sol",
        "root",
        "solution_is",
    ]
    assert [sub.description.type for step in vertical.steps for sub in step.substeps] == [
        "eq_irrational_simple_equals_zero",
        "solution_check_sub",
        "root_zero",
        "solution_check_t",
    ]


def _equation_rows(tree: object) -> list[dict]:
    """Every ``EQUALS`` row of a card and its detail pages, each ``±`` split into + and −."""
    rows: list[dict] = []
    if isinstance(tree, dict):
        if tree.get("type") == "EQUALS" and "children" in tree:
            rows.append(tree)
        for value in tree.values():
            rows.extend(_equation_rows(value))
    elif isinstance(tree, list):
        for value in tree:
            rows.extend(_equation_rows(value))
    split: list[dict] = []
    for row in rows:
        pending = [json.dumps(row)]
        while pending:
            text = pending.pop()
            if '"ADD_SUBTRACT"' in text:
                for kind in ('"ADD"', '"SUBTRACT"'):
                    pending.append(text.replace('"ADD_SUBTRACT"', kind, 1))
            else:
                split.append(json.loads(text))
    return split


@pytest.mark.parametrize(
    "source",
    [
        # dividing by a once wrote 2x² − 5x − 6 = 0 as x² − 5/2 x + 3 = 0
        "{=({2x^2-5x-6},{0})}",
        "{=({-2x^2-4x+6},{0})}",
        # the c = 0 PQ card used p = b, not b/a, and turned −2 ± 2 into 2 ± 2
        "{=({2x^2-5x},{0})}",
        "{=({x^2+4x},{0})}",
        # −x² + k² = 0 cards were built on the typed constant of −x² + 1 = −3
        "{=({-x^2+1},{-3})}",
        # q = −5/2 was written as +2 after «−(−q)»
        "{=({2x^2-5x-5},{0})}",
        # rows built for p/2 = 1 (x² + 2x + 5) and for b < 0 (x² − 4x + 4)
        "{=({x^2+4x+5},{0})}",
        "{=({x^2+4x+4},{0})}",
        # one-decimal constants (P4F): the formula card doubles, PQ and the square keep a fraction
        "{=({x^2-x-0.5},{0})}",
        "{=({x^2-x-6},{0.5})}",
        "{=({x^2},{0.5})}",
    ],
)
def test_every_card_row_keeps_the_roots(source: str) -> None:
    x = sympy.Symbol("x")
    original = parse_protocol(source)
    roots = set(sympy.solve(to_sympy(original.children[0]) - to_sympy(original.children[1]), x))
    checked = 0
    for entry in _group(source).entries:
        for row in _equation_rows((entry.result or {}).get("steps", [])):
            try:
                node = CoreNode.from_contract(row)
                difference = sympy.expand(to_sympy(node.children[0]) - to_sympy(node.children[1]))
            except Exception:  # rows with «?» or a list are not equations in x
                continue
            if difference.free_symbols != {x} or not difference.is_polynomial(x):
                continue
            checked += 1
            assert set(sympy.solve(difference, x)) <= roots, (source, row)
    assert checked > 10


def test_subtracted_product_page_keeps_its_value() -> None:
    # «16 − 4·3»: the page once read −4·3 → −4·3 → 12; now: (−4)·3 → −(4·3) → −12.
    result = solve_request(parse_protocol("{=({x^2+4x+3},{0})}").to_contract(), locale="ru")
    pages = []

    def walk(tree: object) -> None:
        if isinstance(tree, dict):
            steps = (tree.get("subresult") or {}).get("steps", [])
            keys = [sub["description"]["type"] for step in steps for sub in step["substeps"]]
            if keys[:1] == ["mul_neg_pos"]:
                pages.append([sub for step in steps for sub in step["substeps"]])
            for value in tree.values():
                walk(value)
        elif isinstance(tree, list):
            for value in tree:
                walk(value)

    walk(result)
    assert pages
    for rows in pages:
        values = [to_sympy(CoreNode.from_contract(rows[0]["left"]))]
        values += [to_sympy(CoreNode.from_contract(row["right"])) for row in rows]
        assert len(set(values)) == 1 and values[0] < 0
