"""A bare expression in several letters is expanded, factored or simplified, never an error."""

from __future__ import annotations

import pytest

from mymath_backend.input import parse_protocol
from mymath_backend.service import solve_request


def _answer(source: str) -> str:
    solution = solve_request(parse_protocol(source).to_contract(), locale="ru")["result"][
        "solution"
    ]
    return str(solution)


@pytest.mark.parametrize(
    ("source", "kind"),
    [
        ("{(a+b)^2}", "ADD"),  # expanded
        ("{a^2-b^2}", "MULTIPLY"),  # factored
        ("{frac({a^2-b^2},{a-b})}", "ADD"),  # cancelled
    ],
)
def test_two_letters_get_a_default_transformation(source: str, kind: str) -> None:
    assert f"'type': '{kind}'" in _answer(source)


def test_a_power_of_a_binomial_is_expanded_in_descending_degree() -> None:
    solution = solve_request(parse_protocol("{(x+1)^3}").to_contract(), locale="ru")["result"][
        "solution"
    ]
    leading = solution
    while leading["type"] in ("ADD", "SUBTRACT"):
        leading = leading["children"][0]
    assert leading == {
        "type": "POWER",
        "children": [{"type": "VARIABLE", "value": "x"}, {"type": "CONSTANT", "value": "3"}],
    }


def test_expanding_brackets_comes_with_a_lesson_screen() -> None:
    steps = solve_request(parse_protocol("{(a+b)^2}").to_contract(), locale="ru")["result"][
        "groups"
    ][0]["entries"][0]["result"]["steps"]
    headers = [
        sub["subresult"]["header"]["type"]
        for step in steps
        for sub in step["substeps"]
        if sub.get("subresult")
    ]
    assert "lesson_alg_expand" in headers


def test_a_polynomial_that_can_be_collected_is_simplified_not_solved() -> None:
    for source in ("{x^2*x^3}", "{3(x+2)-2(x-1)}", "{frac({x^5},{x^2})}"):
        solution = solve_request(parse_protocol(source).to_contract(), locale="ru")["result"][
            "solution"
        ]
        assert solution["type"] != "EQUALS", source


def test_decimals_in_give_decimals_out_and_rational_powers_are_exact() -> None:
    def value(source: str) -> str:
        return solve_request(parse_protocol(source).to_contract(), locale="ru")["result"][
            "solution"
        ]["value"]

    assert value("{0.1*0.2}") == "0.02"
    assert value("{1.5+2.25}") == "3.75"
    assert value("{8^(frac({2},{3}))}") == "4"


def test_decimal_input_keeps_a_surd_answer_exact_with_an_approximation() -> None:
    # The app (quad_negc/5): x² − x − 0.5 = 0 → (1 ± √3)/2, ≈ −0.366025, 1.36603.
    result = solve_request(parse_protocol("{=({x^2-x-0.5},{0})}").to_contract(), locale="ru")[
        "result"
    ]
    assert "0.5" not in str(result["solution"])
    assert "1/2" in str(result["solution"])
    assert any("APPROXIMATE_SIGN" in str(form) for form in result["alternativeForms"])


def test_answers_carry_alternative_forms() -> None:
    def forms(source: str) -> list[str]:
        result = solve_request(parse_protocol(source).to_contract(), locale="ru")["result"]
        return [str(f) for f in result.get("alternativeForms", [])]

    assert any("4.4" in f for f in forms("{=({5x},{22})}"))
    assert any("FRACTION_MIXED" in f for f in forms("{=({5x},{22})}"))
    assert any("15/4" in f for f in forms("{1.5+2.25}"))
    assert forms("{2+3}") == []


def test_a_matrix_answer_has_no_alternative_forms_and_does_not_fail() -> None:
    source = (
        "{mat({mat_row({1},{2})},{mat_row({3},{4})})+mat({mat_row({1},{0})},{mat_row({0},{1})})}"
    )
    result = solve_request(parse_protocol(source).to_contract(), locale="ru")["result"]
    assert result.get("alternativeForms", []) == []


def test_a_polynomial_over_a_number_is_cancelled_not_solved() -> None:
    result = solve_request(parse_protocol("{frac({2x+6},{4})}").to_contract(), locale="ru")[
        "result"
    ]
    solution = result["solution"]
    assert solution["type"] == "FRACTION"
    assert [c["type"] for c in solution["children"][0]["children"]] == ["VARIABLE", "CONSTANT"]


def test_letters_that_cancel_leave_a_number_instead_of_an_error() -> None:
    for source, value in (("{2(3x-2)-3(2x+3)}", "-13"), ("{x+6+x+1-2x-1}", "6")):
        result = solve_request(parse_protocol(source).to_contract(), locale="ru")["result"]
        assert result["solution"]["value"] == value
