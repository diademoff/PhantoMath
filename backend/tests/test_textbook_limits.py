"""Textbook limits from the current batch: answers and the method cards.

Every case is a protocol input; the expected value is written here with sympy
primitives, independently of the solver's bridge.  The cards must name the
method (leading terms, a finite sum, a bounded factor, the second remarkable
limit, a power of limits, logarithms for ``∞^0``, a one-sided leading term) and
must render Russian text without missing keys or ``ARG`` leftovers.
"""

from __future__ import annotations

from typing import Any

import pytest
import sympy

from mymath_backend import CoreNode, service
from mymath_backend.input import parse_protocol
from mymath_backend.solver.sympy_bridge import to_sympy

X = sympy.Symbol("x")
N = sympy.Symbol("n")

# (protocol, expected value, header key, step keys that must be present)
CASES: list[tuple[str, sympy.Expr, str, list[str]]] = [
    (
        "{lim({0},{frac({3x*root2({x})-x+2*root2({x})},{x^4+7x^2+5x})})}",
        sympy.oo,
        "textbook_header_leading",
        ["lesson_calc_uncertainty_00", "textbook_leading_replace", "lesson_calc_limit_result"],
    ),
    (
        "{lim({inf},{sigma_def({k},{1},{n},{frac({1},{4^k})})})}",
        sympy.Rational(1, 3),
        "textbook_header_sum",
        [
            "textbook_sum_formula",
            "textbook_sum_limit",
            "textbook_sum_decay",
            "lesson_calc_limit_result",
        ],
    ),
    (
        "{lim({inf},{frac({sigma_def({k},{1},{n},{2k-1})},{3n^2})})}",
        sympy.Rational(1, 3),
        "textbook_header_sum",
        [
            "textbook_sum_formula",
            "textbook_sum_limit",
            "lesson_calc_uncertainty_inf",
            "lesson_calc_inf_deg_eq",
        ],
    ),
    (
        "{lim({inf},{(-1)^(n-1)*frac({2-n},{n^2+3})})}",
        0,
        "textbook_header_bounded",
        ["textbook_bounded_factor", "textbook_bounded_infinitesimal"],
    ),
    (
        "{lim({inf},{3x*sin({frac({1},{x})})})}",
        3,
        "textbook_header_leading",
        ["textbook_uncertainty_zero_inf", "textbook_leading_replace"],
    ),
    (
        "{lim({inf},{root({3},{2x-1})*atan({frac({1},{2*root2({x+1})})})})}",
        0,
        "textbook_header_leading",
        ["textbook_uncertainty_zero_inf", "textbook_leading_replace"],
    ),
    (
        "{lim({inf},{frac({root({3},{2-x-x^6})},{2x^3+x^2-5x+3})})}",
        0,
        "textbook_header_leading",
        ["lesson_calc_uncertainty_inf", "textbook_leading_replace", "lesson_calc_simplify"],
    ),
    (
        "{lim({inf},{root2({x^2+x+3})-root2({x^2-3x+1})})}",
        2,
        "lesson_calc_header_conjugate",
        ["lesson_calc_conjugate_multiply", "lesson_calc_conjugate_simplify"],
    ),
    (
        "{lim({1},{(1-x)*tan({frac({pi*x},{2})})})}",
        2 / sympy.pi,
        "textbook_header_leading",
        ["textbook_uncertainty_zero_inf", "textbook_leading_replace"],
    ),
    (
        "{lim({3},{(frac({19-4x},{5x-8}))^(frac({16-3x},{2x-6}))})}",
        sympy.exp(sympy.Rational(-9, 2)),
        "lesson_calc_header_second_remarkable",
        ["lesson_calc_uncertainty_1_inf", "textbook_second_power"],
    ),
    (
        "{lim({-inf},{(5-2x)*(ln({1-x})-ln({2-x}))})}",
        -2,
        "textbook_header_leading",
        ["textbook_uncertainty_zero_inf", "textbook_leading_replace"],
    ),
    (
        "{lim({1},{(5x-4)^(frac({x},{10(x-1)}))})}",
        sympy.exp(sympy.Rational(1, 2)),
        "lesson_calc_header_second_remarkable",
        ["lesson_calc_uncertainty_1_inf", "textbook_second_power"],
    ),
    (
        "{lim({inf},{(frac({2x+1},{x+3}))^x})}",
        sympy.oo,
        "textbook_header_power",
        ["textbook_power_base", "textbook_power_exponent"],
    ),
    (
        "{lim({inf},{(frac({x-2},{3x+4}))^(3x-1)})}",
        0,
        "textbook_header_power",
        ["textbook_power_base", "textbook_power_exponent"],
    ),
    (
        "{lim({inf},{(frac({x+2},{x^2+3x+5}))^(4x)})}",
        0,
        "textbook_header_power",
        ["textbook_power_base", "textbook_power_exponent"],
    ),
    (
        "{lim({inf},{(frac({x^2+1},{2x-3}))^(5x+1)})}",
        sympy.oo,
        "textbook_header_power",
        ["textbook_power_base", "textbook_power_exponent"],
    ),
    (
        "{lim_left({frac({pi},{2})},{frac({1},{cos({x})})})}",
        sympy.oo,
        "lesson_calc_header_one_sided",
        ["textbook_leading_replace", "lesson_calc_limit_result"],
    ),
    (
        "{lim_left({pi},{cot({x})^2})}",
        sympy.oo,
        "lesson_calc_header_one_sided",
        ["textbook_leading_replace", "lesson_calc_limit_result"],
    ),
    (
        "{lim({inf},{(\\e^x-1)^frac({1},{x})})}",
        sympy.E,
        "textbook_header_log_power",
        ["lesson_calc_uncertainty_inf_0", "textbook_take_log", "textbook_log_limit"],
    ),
    (
        "{lim({inf},{frac({sin({factorial({n})})},{n^2})})}",
        0,
        "textbook_header_bounded",
        ["textbook_bounded_factor", "textbook_bounded_infinitesimal"],
    ),
    (
        "{lim({inf},{2*\\e^(-n)*cos({(3n-5)/(1+n^3)})^2})}",
        0,
        "textbook_header_bounded",
        ["textbook_bounded_factor", "textbook_bounded_infinitesimal"],
    ),
    (
        "{lim({inf},{n^2*tan({frac({1},{2n+1})})})}",
        sympy.oo,
        "textbook_header_leading",
        ["textbook_uncertainty_zero_inf", "textbook_leading_replace"],
    ),
    (
        "{lim({inf},{(1-3n^2)*atan({frac({n},{3n^2-1})})^2})}",
        sympy.Rational(-1, 3),
        "textbook_header_leading",
        ["textbook_uncertainty_zero_inf", "textbook_leading_replace", "lesson_calc_simplify"],
    ),
    (
        "{lim({inf},{root({3},{x^3-3x^2})-x})}",
        -1,
        "textbook_header_leading",
        ["lesson_calc_uncertainty_inf_minus_inf", "textbook_leading_replace"],
    ),
    (
        "{lim({inf},{frac({1},{n+3})})}",
        0,
        "textbook_header_leading",
        ["textbook_leading_replace", "lesson_calc_limit_result"],
    ),
    (
        "{lim({frac({-pi},{6})},{muli({(root2({3})-2cos({x}))},{cot({x+frac({pi},{6})})})})}",
        -1,
        "textbook_header_leading",
        ["textbook_uncertainty_zero_inf", "textbook_leading_replace"],
    ),
    (
        "{lim({0},{cos({2x})^frac({1},{ln({1+sin({x})^2})})})}",
        sympy.exp(-2),
        "lesson_calc_header_second_remarkable",
        ["lesson_calc_uncertainty_1_inf", "textbook_second_power"],
    ),
    (
        "{lim({inf},{(frac({x-2},{x+1}))^(2x+3)})}",
        sympy.exp(-6),
        "lesson_calc_header_second_remarkable",
        ["lesson_calc_uncertainty_1_inf", "textbook_second_power"],
    ),
    (
        "{lim({0},{(1+tan({x}))^(frac({3},{x}))})}",
        sympy.exp(3),
        "lesson_calc_header_second_remarkable",
        ["lesson_calc_uncertainty_1_inf", "textbook_second_power"],
    ),
]


def _card(proto: str) -> dict[str, Any]:
    response = service.solve_request(
        parse_protocol(proto).to_contract(), None, render=True, locale="ru"
    )
    return response["result"]["groups"][0]["entries"][0]["result"]


def _keys(card: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for step in card["steps"]:
        for sub in step["substeps"]:
            found.append(sub["description"]["type"])
    return found


def _answer(card: dict[str, Any]) -> sympy.Expr:
    return to_sympy(CoreNode.from_contract(card["solutionNode"]))


def _texts(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, dict):
        explanation = value.get("explanation")
        if isinstance(explanation, dict):
            assert not explanation.get("missing"), explanation.get("key")
            text = explanation.get("text") or ""
            assert "ARG" not in text, (explanation.get("key"), text)
            if text:
                out.append(text)
        for child in value.values():
            out.extend(_texts(child))
    elif isinstance(value, list):
        for child in value:
            out.extend(_texts(child))
    return out


@pytest.mark.parametrize(("proto", "want", "header", "keys"), CASES)
def test_limit_answer_and_method(
    proto: str, want: sympy.Expr, header: str, keys: list[str]
) -> None:
    card = _card(proto)
    assert card["header"]["type"] == header
    ours = _answer(card)
    if want in (sympy.oo, -sympy.oo) or ours in (sympy.oo, -sympy.oo):
        assert ours == want
    else:
        assert sympy.simplify(ours - want) == 0
    found = _keys(card)
    for key in keys:
        assert key in found, (proto, key, found)


@pytest.mark.parametrize("proto", [case[0] for case in CASES])
def test_limit_card_text_is_complete(proto: str) -> None:
    card = _card(proto)
    texts = _texts(card)
    assert texts
    for text in texts:
        # ``_texts`` already rejects missing keys and ``ARG`` leftovers.
        assert "None" not in text
        assert "??" not in text
