"""«Не определено»: ответ там, где раньше был экран ошибки.

Решатель на деление на ноль, факториал вне области определения и корень из
отрицательного числа отвечает «Не определено» и объясняет причину шагом
(``expr_undefined``/``div_with_zero``, ``expr_not_def_in_r``/``root_sqr_neg``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mymath_backend import CoreNode, load_explanations
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.service import solve_request
from mymath_backend.solver import solve

EXPLANATIONS = Path(__file__).resolve().parents[1] / "mymath_backend" / "data" / "explanations.json"


def vertical_of(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source)).result.vertical()
    assert vertical is not None
    return vertical


def undefined_of(source: str) -> CoreSolverVerticalResult:
    """Ответ «Не определено» целиком."""
    vertical = vertical_of(source)
    assert vertical.solution is not None
    assert vertical.solution.type is T.TEXT
    assert vertical.solution.children[0].value == "undefined"
    return vertical


def stage_keys(vertical: CoreSolverVerticalResult) -> list[str]:
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


def step_headers(vertical: CoreSolverVerticalResult) -> list[str]:
    return [header.type for step in vertical.steps for header in step.step_headers]


class TestDivisionByZero:
    """Деление на ноль: «Не определено» с причиной ``div_with_zero``."""

    @pytest.mark.parametrize(
        "source",
        [
            "{frac({6},{0})}",
            "{100/0+6}",
            "{frac({1},{0})+frac({1},{3})}",
            "{2*frac({3},{0})}",
            "{frac({3},{4})/frac({1},{0})}",
        ],
    )
    def test_expression_is_undefined(self, source: str) -> None:
        vertical = undefined_of(source)
        assert step_headers(vertical) == ["expr_undefined"]
        assert stage_keys(vertical) == ["div_with_zero"]
        arg = vertical.steps[0].substeps[0].description.args[0]
        assert arg.type is T.CONSTANT and arg.value == "0"

    def test_the_whole_expression_is_shown(self) -> None:
        # Решатель показывает виноватое выражение целиком, а не знаменатель.
        vertical = undefined_of("{frac({1},{0})+frac({1},{3})}")
        left = vertical.steps[0].substeps[0].left
        assert left is not None and left.type is T.ADD
        assert left.structural_eq(parse_protocol("{frac({1},{0})+frac({1},{3})}"))

    def test_equation_is_undefined(self) -> None:
        # x/0 = 2: деление на ноль делает неопределённым всё уравнение.
        vertical = undefined_of("{=({frac({x},{0})},{2})}")
        assert step_headers(vertical) == ["expr_undefined"]
        assert stage_keys(vertical) == ["div_with_zero"]
        left = vertical.steps[0].substeps[0].left
        assert left is not None and left.type is T.EQUALS


class TestCombinatoricsOutsideTheDomain:
    def test_negative_factorial(self) -> None:
        vertical = undefined_of("{factorial({-2})}")
        assert step_headers(vertical) == ["expr_undefined"]
        assert stage_keys(vertical) == ["factorial_non_integer"]
        arg = vertical.steps[0].substeps[0].description.args[0]
        assert arg.value == "0"

    def test_fractional_permutation(self) -> None:
        vertical = undefined_of("{permutation({5},{0.5})}")
        assert step_headers(vertical) == ["expr_undefined"]
        assert stage_keys(vertical) == ["permutation_coef_non_integer"]


class TestRootOfNegativeInsideExpression:
    @pytest.mark.parametrize(
        "source",
        ["{root2({-2})+root2({16})}", "{root2({9})+root2({-1})}", "{root2({9})+root2({-3})}"],
    )
    def test_whole_expression_is_undefined(self, source: str) -> None:
        vertical = undefined_of(source)
        assert step_headers(vertical) == ["expr_not_def_in_r"]
        assert stage_keys(vertical) == ["root_sqr_neg"]

    def test_lone_negative_root_is_undefined(self) -> None:
        # (sqrt_neg): the answer is
        # «Не определено», not the empty set — an expression is not a set.
        vertical = undefined_of("{root2({-4})}")
        assert step_headers(vertical) == ["expr_not_def_in_r"]
        assert stage_keys(vertical) == ["root_sqr_neg"]

    def test_positive_square_root_is_untouched(self) -> None:
        vertical = vertical_of("{root2({16})}")
        assert vertical.solution is not None and vertical.solution.value == "4"


class TestLogarithmOutsideItsDomain:
    @pytest.mark.parametrize(
        "source, key",
        [("{log10({0})}", "log_undef_zero"), ("{log10({-3})}", "log_neg_arg")],
    )
    def test_answer_is_undefined(self, source: str, key: str) -> None:
        # Случаи log_1000/0 и /3: «Не определено», а не ∅.
        vertical = undefined_of(source)
        assert step_headers(vertical) == ["expr_not_def_in_r"]
        assert stage_keys(vertical) == [key]

    def test_logarithm_of_zero_shows_the_argument(self) -> None:
        vertical = undefined_of("{log10({0})}")
        arg = vertical.steps[0].substeps[0].description.args[0]
        assert arg.type is T.CONSTANT and arg.value == "0"


class TestUndefinedSideOfAnEquation:
    @pytest.mark.parametrize(
        "source",
        ["{=({sin({x})},{frac({1},{0})})}", "{=({cos({x})},{1/0})}"],
    )
    def test_equation_is_undefined(self, source: str) -> None:
        # Случаи trig_eq/12 и cos_eq/5: одна карточка с
        # пояснением div_with_zero, хотя левая часть не сворачивается в число.
        vertical = undefined_of(source)
        assert step_headers(vertical) == ["expr_undefined"]
        assert stage_keys(vertical) == ["div_with_zero"]


class TestBareMatrixWithNegativeCell:
    def test_determinant_is_computed(self) -> None:
        # Случай mat_det/3: ответ −8, способы — det и inverse.
        result = solve_request(
            parse_protocol("{mat({mat_row({1},{2})},{mat_row({3},{-2})})}").to_contract(),
            locale="ru",
        )["result"]
        answer = CoreNode.from_contract(result["solution"])
        assert answer.type is T.CONSTANT and answer.value == "-8"
        assert len(result["groups"][0]["entries"]) == 2

    @pytest.mark.parametrize(
        "source",
        [
            "{mat({mat_row({1},{-1})},{mat_row({3},{4})})}",
            "{mat({mat_row({frac({1},{2})},{2})},{mat_row({3},{-2})})}",
        ],
    )
    def test_negative_fraction_cells_are_numbers(self, source: str) -> None:
        result = solve_request(parse_protocol(source).to_contract(), locale="ru")["result"]
        assert CoreNode.from_contract(result["solution"]).type is T.CONSTANT


class TestDecimalExponent:
    def test_decimal_exponent_becomes_a_fraction_then_a_root(self) -> None:
        # Случай pow_5sq/13: dec_to_frac, затем правило степени.
        vertical = vertical_of("{5^0.5}")
        assert step_headers(vertical) == ["convert_expression", "trans_msg"]
        assert stage_keys(vertical) == ["dec_to_frac", "using_trans"]
        solution = vertical.solution
        assert solution is not None and solution.type is T.ALTERNATIVE_FORM
        root, approximate = solution.children
        assert root.type is T.ROOT2 and root.children[0].value == "5"
        assert approximate.type is T.APPROXIMATE_SIGN
        assert approximate.children[0].value == "2.23607"

    def test_integer_power_is_unchanged(self) -> None:
        vertical = vertical_of("{5^2}")
        assert vertical.solution is not None and vertical.solution.value == "25"

    def test_exact_rational_power_is_unchanged(self) -> None:
        vertical = vertical_of("{4^0.5}")
        assert vertical.solution is not None and vertical.solution.value == "2"


class TestQuadraticWithoutRealRoots:
    @pytest.mark.parametrize("source", ["{=({x^2+2x+5},{0.5})}", "{=({x^-1+4x+3},{0})}"])
    def test_top_answer_is_not_in_the_reals(self, source: str) -> None:
        # Случаи quad_complex/14 и quad_pos/0: «x ∉ ℝ».
        vertical = vertical_of(source)
        solution = vertical.solution
        assert solution is not None and solution.type is T.ELEMENT_NOT_OF
        assert [child.value for child in solution.children] == ["x", "ℝ"]
        assert step_headers(vertical)[-1] == "expr_not_def_in_r"
        assert stage_keys(vertical)[-1] == "root_sqr_neg"

    def test_complex_roots_stay_a_method(self) -> None:
        result = solve_request(parse_protocol("{=({x^2+2x+5},{0.5})}").to_contract(), locale="ru")[
            "result"
        ]
        entries = result["groups"][0]["entries"]
        # the app's nine cards: the real-domain triple, the complex triple, the two
        # counting cards and the discriminant.
        assert len(entries) == 9
        answers = [CoreNode.from_contract(entry["result"]["solutionNode"]) for entry in entries]
        assert any(answer.type is T.LIST for answer in answers)
        assert CoreNode.from_contract(result["solution"]).type is T.ELEMENT_NOT_OF

    def test_zero_right_side_keeps_its_cards(self) -> None:
        result = solve_request(parse_protocol("{=({x^2+2x+5},{0})}").to_contract(), locale="ru")[
            "result"
        ]
        entries = result["groups"][0]["entries"]
        # Один из способов заканчивается «корень из отрицательного => x ∉ ℝ».
        endings = [
            entry["result"]["steps"][-1]["substeps"][-1]["description"]["type"]
            for entry in entries
            if entry["result"]["steps"]
        ]
        assert "root_sqr_neg" in endings
        # И верхний ответ сервиса по-прежнему «x ∉ ℝ».
        assert CoreNode.from_contract(result["solution"]).type is T.ELEMENT_NOT_OF


class TestUndefinedText:
    """Русский текст ответа: «Не определено», кириллицей и в среднем роде."""

    def test_russian_text(self) -> None:
        data = solve_request(
            parse_protocol("{frac({6},{0})}").to_contract(), locale="ru", render=True
        )
        assert data["result"]["solution"] == {"type": "TEXT", "value": "Не определено"}

    def test_russian_text_is_cyrillic(self) -> None:
        text = solve_request(
            parse_protocol("{frac({6},{0})}").to_contract(), locale="ru", render=True
        )["result"]["solution"]["value"]
        assert "e" not in text  # латинской «e» нет
        assert all(char == " " or "\u0400" <= char <= "\u04ff" for char in text)
        assert text.endswith("о")  # «…определено»: ответ об выражении

    def test_english_text(self) -> None:
        data = solve_request(
            parse_protocol("{frac({6},{0})}").to_contract(), locale="default", render=True
        )
        assert data["result"]["solution"] == {"type": "TEXT", "value": "Undefined"}

    def test_dictionary_text_is_overridden(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        assert explanations.render("undefined", [], "ru").text == "Не определено"
        assert explanations.render("undefined", [], "default").text == "Undefined"
