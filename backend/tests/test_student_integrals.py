"""Student-visible indefinite integrals (INT1).

The first card is the Demidovich method, named and with its formula:

* a table entry (``xⁿ``, ``1/x``, ``eˣ``, ``aˣ``, ``sin``, ``cos``, ``1/cos²x``,
  ``1/(1+x²)``, ``1/√(1−x²)``), the linear argument ``∫f(kx+b)dx = F(kx+b)/k``;
* linearity of a sum, the split with its signs, each piece's table integral
  behind its own «Подробнее»;
* substitution ``t = g(x)``, ``dt = g'(x)dx``, the integral in ``t``, its table
  integral, the back substitution and ``+ C``;
* the half-angle formula for ``sin²x``, ``sin³x = (1−cos²x)·sin x`` with
  ``t = cos x``, and ``∫tg x dx = −ln|cos x|``.

Every answer is checked with ``sympy.diff``; the verified card stays
as the second entry, so the parity structure is unchanged.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from itertools import pairwise
from typing import Any

import pytest
import sympy

from mymath_backend import CoreNode, service
from mymath_backend.input import parse_protocol
from mymath_backend.solver.integrals import _integral_method
from mymath_backend.solver.sympy_bridge import to_sympy

# Sample protocols, kept here so the tests
# do not depend on the git-ignored build/ tree.
PROTO = {
    "ind01_x3": "{integral({x^3})}",
    "ind02_recip": "{integral({frac({1},{x})})}",
    "ind03_exp": "{integral({exp({x})})}",
    "ind04_aexp": "{integral({2^x})}",
    "ind05_sin": "{integral({sin({x})})}",
    "ind06_cos": "{integral({cos({x})})}",
    "ind07_cos2": "{integral({frac({1},{cos({x})^2})})}",
    "ind08_atan": "{integral({frac({1},{1+x^2})})}",
    "ind09_asin": "{integral({frac({1},{root2({1-x^2})})})}",
    "ind10_linear": "{integral({3x^2-4x+5})}",
    "ind11_square_over_x": "{integral({frac({(x+1)^2},{x})})}",
    "ind12_sin3x": "{integral({sin({3x})})}",
    "ind13_exp2x": "{integral({exp({-2x})})}",
    "ind14_xexp": "{integral({x*exp({x^2})})}",
    "ind15_sin_cos2": "{integral({sin({x})*cos({x})^2})}",
    "ind16_ln_over_x": "{integral({frac({ln({x})},{x})})}",
    "ind17_x_over_x2p1": "{integral({frac({x},{x^2+1})})}",
    "ind18_1_over_2xp3": "{integral({frac({1},{2x+3})})}",
    "ind19_xexp_parts": "{integral({x*exp({x})})}",
    "ind20_xsin_parts": "{integral({x*sin({x})})}",
    "ind21_ln_parts": "{integral({ln({x})})}",
    "ind22_x2exp_parts": "{integral({x^2*exp({x})})}",
    "ind23_exp_sin_parts": "{integral({exp({x})*sin({x})})}",
    "ind24_atan_parts": "{integral({atan({x})})}",
    "ind25_rat_a2": "{integral({frac({1},{x^2-1})})}",
    "ind26_rat_xp3": "{integral({frac({x+3},{x^2-3x+2})})}",
    "ind27_rat_repeat": "{integral({frac({1},{x*(x+1)^2})})}",
    "ind28_complete_sq": "{integral({frac({1},{x^2+2x+5})})}",
    "ind29_sin2": "{integral({sin({x})^2})}",
    "ind30_sin3": "{integral({sin({x})^3})}",
    "ind31_tg": "{integral({tan({x})})}",
    "ind32_csc": "{integral({frac({1},{sin({x})})})}",
    "ind33_irrational": "{integral({x*root2({x+1})})}",
    "ind34_nonelem": "{integral({exp({-x^2})})}",
}

# INT2 cards that are not part of the INT1 task list.
EXTRA = {
    "xcos2_parts": "{integral({x*cos({2x})})}",
    "xln_parts": "{integral({x*ln({x})})}",
    "rat_division": "{integral({frac({x^3},{x^2-1})})}",
    "rat_ln_atan": "{integral({frac({2x+3},{x^2+1})})}",
    "square_ln_atan": "{integral({frac({x+2},{x^2+2x+5})})}",
    "pow5_back_sub": "{integral({x^2*(x^3+1)^5})}",
    "linear_power_back_sub": "{integral({(2x+1)^7})}",
    "cos2_half_angle": "{integral({cos({x})^2})}",
    "x_in_ln_sub": "{integral({frac({1},{x*ln({x})})})}",
    "ln_cube_over_x": "{integral({frac({ln({x})^3},{x})})}",
    "exp_over_one_plus_exp": "{integral({frac({exp({x})},{1+exp({x})})})}",
    "cos_exp_sin": "{integral({cos({x})*exp({sin({x})})})}",
    "x2_over_x3p1": "{integral({frac({x^2},{x^3+1})})}",
    "negative_linear": "{integral({exp({-x})})}",
    "linear_sub_order": "{integral({sin({3x})})}",
}
PROTO |= EXTRA

INDEFINITE = [
    "ind01_x3",
    "ind02_recip",
    "ind03_exp",
    "ind04_aexp",
    "ind05_sin",
    "ind06_cos",
    "ind07_cos2",
    "ind08_atan",
    "ind09_asin",
    "ind10_linear",
    "ind11_square_over_x",
    "ind12_sin3x",
    "ind13_exp2x",
    "ind14_xexp",
    "ind15_sin_cos2",
    "ind16_ln_over_x",
    "ind17_x_over_x2p1",
    "ind18_1_over_2xp3",
    "ind29_sin2",
    "ind30_sin3",
    "ind31_tg",
    "ind32_csc",
    "ind33_irrational",
]

INDEFINITE += [
    key
    for key in PROTO
    if key.startswith("ind") and key not in INDEFINITE and key != "ind34_nonelem"
]
INDEFINITE_PROTO = {key: PROTO[key] for key in INDEFINITE}

TABLE = ["ind02_recip", "ind03_exp", "ind04_aexp", "ind05_sin", "ind06_cos"]
TABLE += ["ind07_cos2", "ind08_atan", "ind09_asin"]

_RAW_NODE = re.compile(r"\b[A-Z][A-Z_0-9]{2,}\(")
_PLACEHOLDER = re.compile(r"\?\?\s*step_|ARG\d|\bNone\b")

TABLE_KEYS = ["lesson_calc_int_table_rule", "integrate_msg_addc"]
SUBSTITUTION_KEYS = [
    "lesson_calc_int_substitute",
    "lesson_calc_int_differential",
    "lesson_calc_int_rewrite",
    "lesson_calc_int_inner_table",
    "lesson_calc_int_back_sub",
    "integrate_msg_addc",
]


def response(source: str) -> dict[str, Any]:
    return service.solve_request(parse_protocol(source).to_contract(), render=True, locale="ru")


def cards(source: str) -> list[dict[str, Any]]:
    return response(source)["result"]["groups"][0]["entries"]


def first(source: str) -> dict[str, Any]:
    return cards(source)[0]


def header_key(card: dict[str, Any]) -> str:
    return (card["result"].get("header") or {}).get("type", "")


def header_text(card: dict[str, Any]) -> str:
    return ((card["result"].get("header") or {}).get("explanation") or {}).get("text", "")


def roots(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from roots(child)
    elif isinstance(value, list):
        for child in value:
            yield from roots(child)


def card_keys(card: dict[str, Any]) -> list[str]:
    """Top-level stage keys of a card (nested «Подробнее» excluded)."""
    return [
        sub["description"]["type"]
        for step in card["result"].get("steps") or []
        for sub in step.get("substeps") or []
    ]


def texts(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        explanation = value.get("explanation")
        if isinstance(explanation, dict) and explanation.get("text"):
            yield explanation["text"]
        for child in value.values():
            yield from texts(child)
    elif isinstance(value, list):
        for child in value:
            yield from texts(child)


def nodes_of(value: Any) -> Iterator[dict[str, Any]]:
    for node in roots(value):
        if isinstance(node.get("type"), str) and node["type"].isupper():
            yield node


def explanation_nodes(explanation: Any) -> Iterator[dict[str, Any]]:
    """Math nodes of a rendered explanation, in order."""
    if not isinstance(explanation, dict):
        return
    for part in explanation.get("parts") or []:
        if isinstance(part.get("node"), dict):
            yield from nodes_of(part["node"])


def answer_expression(card: dict[str, Any]) -> sympy.Expr:
    """The antiderivative of a card (the constant dropped)."""
    solution = card["result"]["solutionNode"]
    if solution["type"] == "LIST":
        solution = solution["children"][0]
    value = to_sympy(CoreNode.from_contract(solution))
    return value - sympy.Symbol("C") if value.has(sympy.Symbol("C")) else value


def integrand(source: str) -> sympy.Expr:
    return to_sympy(parse_protocol(source).children[-1])


def derivative_matches(source: str, card_index: int = 0) -> bool:
    answer = answer_expression(cards(source)[card_index])
    value = integrand(source)
    real = {symbol: sympy.Symbol(str(symbol), real=True) for symbol in answer.free_symbols}
    real |= {sympy.Symbol("x"): sympy.Symbol("x", real=True)}
    ours = answer.replace(lambda node: isinstance(node, sympy.Abs), lambda node: node.args[0]).subs(
        real
    )
    target = value.replace(
        lambda node: isinstance(node, sympy.Abs), lambda node: node.args[0]
    ).subs(real)
    return sympy.simplify(sympy.diff(ours, sympy.Symbol("x", real=True)) - target) == 0


def _equals(node: dict[str, Any], side: str) -> bool:
    """``node`` is ``EQUALS(VARIABLE side, …)``."""
    if node.get("type") != "EQUALS" or len(node.get("children") or []) != 2:
        return False
    left = node["children"][0]
    return left.get("type") == "VARIABLE" and left.get("value") == side


# ── 1. method choice ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("task_id", "method"),
    [
        ("ind02_recip", None),
        ("ind07_cos2", None),
        ("ind08_atan", None),
        ("ind09_asin", None),
        ("ind05_sin", None),
        ("ind12_sin3x", "integrate_using_substitution"),
        ("ind14_xexp", "integrate_using_substitution"),
        ("ind16_ln_over_x", "integrate_using_substitution"),
        ("ind17_x_over_x2p1", "integrate_using_substitution"),
        ("ind31_tg", "integrate_using_substitution"),
    ],
)
def test_method_choice_checks_table_and_substitution_before_parts(
    task_id: str, method: str | None
) -> None:
    expression = integrand(PROTO[task_id])
    assert _integral_method(expression, sympy.Symbol("x")) == method


def test_x_times_exp_and_log_over_x_are_not_by_parts() -> None:
    x = sympy.Symbol("x")
    for expression in (x * sympy.exp(x**2), sympy.log(x) / x):
        assert _integral_method(expression, x) == "integrate_using_substitution"
    assert _integral_method(x * sympy.exp(x), x) == "integrate_partial"


# ── 2. table integrals ────────────────────────────────────────────────


@pytest.mark.parametrize("task_id", TABLE)
def test_table_integral_names_the_entry_and_shows_its_formula(task_id: str) -> None:
    source = PROTO[task_id]
    card = first(source)
    assert header_key(card) == "lesson_calc_header_int_table"
    assert card_keys(card) == TABLE_KEYS
    assert derivative_matches(source)
    # The chip is arg-free (it must fit a phone), and the table entry with its
    # formula lives in the stage's theory article.
    step = _substep(card, "lesson_calc_int_table_rule")
    assert not step["description"].get("args")
    theory = (step.get("explanation") or {}).get("theory") or {}
    assert "∫" in theory.get("formula", "")


def test_power_rule_uses_the_general_formula_and_applies_n_on_the_detail() -> None:
    card = first(PROTO["ind01_x3"])
    keys = card_keys(card)
    assert "lesson_calc_int_table_rule" in keys
    step = next(
        sub
        for st in card["result"]["steps"]
        for sub in st["substeps"]
        if sub["description"]["type"] == "lesson_calc_int_table_rule"
    )
    assert step.get("subresult") is not None
    # The nested card states ∫xⁿ dx = xⁿ⁺¹/(n+1) as a formula, not as a chip ARG.
    detail = step["subresult"]
    formula = detail["steps"][0]["substeps"][0]
    assert any(
        node["type"] == "POWER" and node["children"][1].get("value") == "n"
        for node in nodes_of(formula.get("left"))
    )
    assert any(
        node["type"] == "VARIABLE" and node.get("value") == "n"
        for node in nodes_of(formula.get("right"))
    )
    # And n = 3 is applied on the card itself: x⁴/4.
    assert step["right"]["children"][0]["children"][1].get("value") == "4"


@pytest.mark.parametrize(
    ("source", "want"),
    [
        ("{integral({frac({1},{sin({x})^2})})}", -sympy.cot(sympy.Symbol("x"))),
        ("{integral({frac({1},{x^2+4})})}", sympy.atan(sympy.Symbol("x") / 2) / 2),
        ("{integral({frac({1},{root2({4-x^2})})})}", sympy.asin(sympy.Symbol("x") / 2)),
    ],
)
def test_more_table_entries_from_the_textbook(source: str, want: sympy.Expr) -> None:
    card = first(source)
    assert header_key(card) == "lesson_calc_header_int_table"
    assert answer_expression(card) == want or sympy.simplify(answer_expression(card) - want) == 0


# ── 3. linear argument ────────────────────────────────────────────────


@pytest.mark.parametrize("task_id", ["ind12_sin3x", "ind13_exp2x", "ind18_1_over_2xp3"])
def test_linear_argument_shows_the_rule_and_then_the_substitution(task_id: str) -> None:
    source = PROTO[task_id]
    card = first(source)
    assert header_key(card) == "lesson_calc_header_int_linear"
    keys = card_keys(card)
    assert keys[0] == "lesson_calc_int_linear_rule"
    assert set(SUBSTITUTION_KEYS) <= set(keys)
    assert derivative_matches(source)
    assert any("Линейный аргумент" in text for text in texts(card))
    # The new integral is an INTEGRAL node (the app draws dt), not text with «∫ … dt».
    assert any(
        node["type"] == "INTEGRAL"
        for sub in _substeps(card)
        if sub["description"]["type"] == "lesson_calc_int_rewrite"
        for node in nodes_of(sub.get("right"))
    )


# ── 4. substitution ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "task_id",
    [
        "ind14_xexp",
        "ind15_sin_cos2",
        "ind16_ln_over_x",
        "ind17_x_over_x2p1",
        "ind30_sin3",
        "ind31_tg",
        "ind32_csc",
        "ind33_irrational",
    ],
)
def test_substitution_card_has_t_dt_new_integral_table_back_and_c(task_id: str) -> None:
    source = PROTO[task_id]
    card = first(source)
    keys = card_keys(card)
    assert set(SUBSTITUTION_KEYS) <= set(keys)
    assert derivative_matches(source)
    # «Замена t = g(x)» and «dt = g'(x) dx» are EQUALS math nodes of the stage.
    assert any(
        _equals(node, "t")
        for sub in _substeps(card)
        if sub["description"]["type"] == "lesson_calc_int_substitute"
        for node in nodes_of(sub.get("left"))
    )
    assert any(
        _equals(node, "dt")
        for sub in _substeps(card)
        if sub["description"]["type"] == "lesson_calc_int_differential"
        for node in nodes_of(sub.get("left"))
    )
    # The table integral is behind «Подробнее».
    table = next(
        sub
        for sub in _substeps(card)
        if sub["description"]["type"] == "lesson_calc_int_inner_table"
    )
    assert table.get("subresult") is not None


def _substeps(card: dict[str, Any]) -> list[dict[str, Any]]:
    return [sub for step in card["result"]["steps"] for sub in step["substeps"]]


def test_irrational_substitution_names_the_root_and_expresses_dx() -> None:
    card = first(PROTO["ind33_irrational"])
    keys = card_keys(card)
    assert "lesson_calc_int_from_substitution" in keys
    assert "lesson_calc_int_dx_expr" in keys
    substitute = next(
        sub for sub in _substeps(card) if sub["description"]["type"] == "lesson_calc_int_substitute"
    )
    assert any(node["type"] == "ROOT2" for node in nodes_of(substitute["left"]))
    dx_step = next(
        sub for sub in _substeps(card) if sub["description"]["type"] == "lesson_calc_int_dx_expr"
    )
    assert any(_equals(node, "dx") for node in nodes_of(dx_step["left"]))


def test_half_angle_formula_is_named_before_linearity() -> None:
    card = first(PROTO["ind29_sin2"])
    assert header_key(card) == "lesson_calc_header_int_half_angle"
    keys = card_keys(card)
    assert keys[0] == "lesson_calc_int_half_angle"
    assert "lesson_calc_int_sum_rule" in keys
    assert derivative_matches(PROTO["ind29_sin2"])


def test_odd_sine_uses_the_identity_and_t_equals_cos_x() -> None:
    card = first(PROTO["ind30_sin3"])
    assert header_key(card) == "lesson_calc_header_int_identity"
    keys = card_keys(card)
    assert keys[0] == "lesson_calc_int_identity"
    assert "lesson_calc_int_substitute" in keys
    assert derivative_matches(PROTO["ind30_sin3"])


# ── 5. linearity ──────────────────────────────────────────────────────


def test_linearity_keeps_the_signs_and_opens_each_piece() -> None:
    source = PROTO["ind10_linear"]
    card = first(source)
    assert header_key(card) == "lesson_calc_header_int_sum"
    keys = card_keys(card)
    assert keys[0] == "lesson_calc_int_sum_rule"
    term_steps = [
        sub for sub in _substeps(card) if sub["description"]["type"] == "lesson_calc_int_term_table"
    ]
    assert len(term_steps) == 3
    assert all(step.get("subresult") for step in term_steps)
    split = card["result"]["steps"][0]["substeps"][0]["right"]
    integrals = [node for node in nodes_of(split) if node["type"] == "INTEGRAL"]
    assert len(integrals) == 3
    assert any(node["type"] == "SUBTRACT" for node in nodes_of(split))
    assert derivative_matches(source)
    constants = {
        node["children"][0].get("value")
        for node in nodes_of(split)
        if node["type"] == "MULTIPLY_IMPLICIT" and node["children"][0].get("type") == "CONSTANT"
    }
    # The book writes 3∫x²dx, without a dot before the integral.
    assert {"3", "4", "5"} <= constants


def test_square_over_x_is_expanded_before_the_split() -> None:
    source = PROTO["ind11_square_over_x"]
    card = first(source)
    keys = card_keys(card)
    assert keys[0] == "lesson_calc_int_expand"
    assert "lesson_calc_int_sum_rule" in keys
    assert len([key for key in keys if key == "lesson_calc_int_term_table"]) == 3
    assert derivative_matches(source)
    assert any(node["type"] == "LN" for node in nodes_of(card))


# ── 6. |·| in logarithms ──────────────────────────────────────────────


@pytest.mark.parametrize("task_id", ["ind18_1_over_2xp3", "ind31_tg", "ind32_csc"])
def test_logarithm_of_a_sign_changing_argument_gets_absolute_value(task_id: str) -> None:
    answer = cards(PROTO[task_id])[0]["result"]["solutionNode"]
    assert any(node["type"] == "ABS" for node in nodes_of(answer))


def test_positive_logarithm_argument_keeps_no_absolute_value() -> None:
    answer = cards(PROTO["ind17_x_over_x2p1"])[0]["result"]["solutionNode"]
    logarithms = [node for node in nodes_of(answer) if node["type"] == "LN"]
    assert logarithms
    assert not any(node["type"] == "ABS" for node in nodes_of(logarithms))


def test_tangent_answer_is_minus_log_of_absolute_cosine() -> None:
    card = first(PROTO["ind31_tg"])
    answer = card["result"]["solutionNode"]
    assert any(
        node["type"] == "LN" and node["children"][0].get("type") == "ABS"
        for node in nodes_of(answer)
    )


# ── 7. answers and + C ────────────────────────────────────────────────


@pytest.mark.parametrize("task_id", INDEFINITE)
def test_every_indefinite_answer_is_an_antiderivative_and_has_plus_c(task_id: str) -> None:
    source = PROTO[task_id]
    card = first(source)
    assert "integrate_msg_addc" in card_keys(card)
    solution = card["result"]["solutionNode"]
    assert solution["type"] == "LIST"
    assert derivative_matches(source)


def test_non_elementary_integral_is_an_answer_card() -> None:
    card = first(PROTO["ind34_nonelem"])
    assert header_key(card) == "lesson_calc_header_int_nonelementary"
    assert card_keys(card) == ["lesson_calc_int_nonelementary"]
    solution = card["result"]["solutionNode"]
    assert solution["type"] == "TEXT" and "элементарн" in solution["value"]


# ── book style and the second card (FIX1 D, E) ────────────────────────


def test_the_switcher_does_not_offer_a_copy_of_the_textbook_card() -> None:
    """«Способ 2» was the verified card: only the textbook one is offered (D).

    ``x³`` is the exception: its verified card carries the app's power-rule
    page (``integrate_msg`` with the two ``add`` rows), so it is deeper than
    the lesson and is offered as the second method (see the test below).
    """
    for task_id in ("ind02_recip", "ind12_sin3x", "ind21_ln_parts", "ind25_rat_a2"):
        assert len(cards(PROTO[task_id])) == 1, task_id


def test_a_definite_card_keeps_the_row_card_with_real_headings() -> None:
    """`tests/corpus`, the verified card and «find the total area» stay methods (D)."""
    expected = {
        # An algebraic integrand also gets the app's «find the total area».
        "{integral_def({0},{1},{x^2})}": 3,
        # A trigonometric one keeps the integration card only.
        "{integral_def({0},{pi},{sin({x})})}": 2,
    }
    for source, count in expected.items():
        entries = cards(source)
        assert len(entries) == count, source
        for entry in entries:
            for step in entry["result"]["steps"]:
                for header in step["headers"]:
                    text = (header.get("explanation") or {}).get("text", "")
                    assert text not in ("", "Преобразование"), source


def test_the_integral_answer_is_written_as_in_the_book() -> None:
    """(x − 1)eˣ, not (x − 1)·eˣ (the book writes no dot before a function)."""
    answer = first(PROTO["ind19_xexp_parts"])["result"]["solutionNode"]
    types = {node["type"] for node in nodes_of(answer)}
    assert "MULTIPLY_IMPLICIT" in types
    assert "MULTIPLY" not in types


def test_the_dot_stays_before_a_number() -> None:
    """x·2ˣ keeps the dot; x·eˣ loses it."""
    from mymath_backend.node_types import CoreNodeType
    from mymath_backend.solver.book_style import book_products

    x = CoreNode.variable("x")
    squared = CoreNode.node(CoreNodeType.POWER, CoreNode.constant("2"), x)
    assert (
        book_products(CoreNode.node(CoreNodeType.MULTIPLY, x, squared)).type
        is CoreNodeType.MULTIPLY
    )
    exponential = CoreNode.node(CoreNodeType.EXP, x)
    assert (
        book_products(CoreNode.node(CoreNodeType.MULTIPLY, x, exponential)).type
        is CoreNodeType.MULTIPLY_IMPLICIT
    )


# ── 8. the verified card stays for parity ───────────────────


@pytest.mark.parametrize(
    ("task_id", "legacy_keys"),
    [
        ("ind01_x3", ["integrate_msg", "integrate_msg_addc"]),
        ("ind02_recip", ["integrate", "integrate_calc", "integrate_msg_addc"]),
        (
            "ind12_sin3x",
            [
                "integrate",
                "integrate_differential_sub",
                "integrate_using_substitution",
                "integrate_calc",
                "integrate_msg_addc",
            ],
        ),
    ],
)
def test_row_card_still_builds_its_rows(task_id: str, legacy_keys: list[str]) -> None:
    from mymath_backend.solver.integrals import _legacy_card

    card = _legacy_card(parse_protocol(PROTO[task_id]), ["x"])
    assert [step.key for step in card] == legacy_keys


@pytest.mark.parametrize("task_id", ["ind02_recip", "ind12_sin3x", "ind21_ln_parts"])
def test_second_card_is_not_offered_when_it_repeats_the_lesson(task_id: str) -> None:
    """The switcher shows the textbook card only; «Способ 2» was a worse copy."""
    assert len(cards(PROTO[task_id])) == 1


def test_the_power_rule_page_is_offered_as_the_row_card() -> None:
    """∫x³ dx: the app's card adds the power-rule page the lesson does not show."""
    entries = cards(PROTO["ind01_x3"])
    assert len(entries) == 2
    assert card_keys(entries[1]) == ["integrate_msg", "integrate_msg_addc"]
    detail = entries[1]["result"]["steps"][0]["substeps"][0]["subresult"]
    assert [sub["description"]["type"] for step in detail["steps"] for sub in step["substeps"]] == [
        "integrate_msg",
        "add",
        "add",
    ]


def test_row_card_is_offered_where_it_adds_steps() -> None:
    """∫6x dx: four verified groups, two textbook ones — parity needs the second card."""
    entries = cards("{integral({6x})}")
    assert len(entries) == 2
    assert card_keys(entries[1]) == [
        "integrate_msg_mul_const",
        "integrate_msg",
        "simplify",
        "integrate_msg_addc",
    ]


# ── 9. text hygiene ───────────────────────────────────────────────────


@pytest.mark.parametrize("task_id", INDEFINITE)
def test_integral_cards_are_russian_and_complete(task_id: str) -> None:
    source = PROTO[task_id]
    data = response(source)
    for text in texts(data):
        assert not _RAW_NODE.search(text), text
        assert not _PLACEHOLDER.search(text), text
        if text and not re.search(r"[а-яА-Я]", text):
            assert not re.search(r"\b(the|this|use|find|since|evaluate)\b", text, re.I), text
    card = first(source)
    assert card["result"]["header"]["explanation"]["missing"] is False
    assert card["result"]["header"]["explanation"]["theory"] is not None


# ── 10. INT2: integration by parts ────────────────────────────────────

PARTS = [
    "ind19_xexp_parts",
    "ind20_xsin_parts",
    "ind21_ln_parts",
    "ind22_x2exp_parts",
    "ind24_atan_parts",
    "xcos2_parts",
    "xln_parts",
]


def _substep(card: dict[str, Any], key: str) -> dict[str, Any]:
    matches = [sub for sub in _substeps(card) if sub["description"]["type"] == key]
    assert matches, key
    return matches[-1]


@pytest.mark.parametrize("task_id", PARTS)
def test_by_parts_card_has_formula_u_dv_du_v_applied_and_remainder(task_id: str) -> None:
    source = PROTO[task_id]
    card = first(source)
    assert header_key(card) == "lesson_calc_header_int_parts"
    keys = card_keys(card)
    for key in (
        "lesson_calc_int_parts_formula",
        "lesson_calc_int_parts_choose",
        "lesson_calc_int_parts_differential",
        "lesson_calc_int_parts_apply",
        "integrate_msg_addc",
    ):
        assert key in keys
    assert derivative_matches(source)
    choose = _substep(card, "lesson_calc_int_parts_choose")
    differential = _substep(card, "lesson_calc_int_parts_differential")
    choose_nodes = list(nodes_of(choose.get("left")))
    differential_nodes = list(nodes_of(differential.get("left")))
    assert any(_equals(node, "u") for node in choose_nodes)
    assert any(_equals(node, "dv") for node in choose_nodes)
    assert any(_equals(node, "du") for node in differential_nodes)
    assert any(_equals(node, "v") for node in differential_nodes)
    applied = _substep(card, "lesson_calc_int_parts_apply")
    assert any(node["type"] == "INTEGRAL" for node in nodes_of(applied.get("right")))
    remainder = _substep(card, "lesson_calc_int_parts_remainder")
    assert remainder.get("subresult") is not None


@pytest.mark.parametrize(
    ("task_id", "want"),
    [
        ("ind19_xexp_parts", sympy.exp(sympy.Symbol("x")) * (sympy.Symbol("x") - 1)),
        (
            "ind20_xsin_parts",
            -sympy.Symbol("x") * sympy.cos(sympy.Symbol("x")) + sympy.sin(sympy.Symbol("x")),
        ),
        ("ind21_ln_parts", sympy.Symbol("x") * sympy.log(sympy.Symbol("x")) - sympy.Symbol("x")),
        (
            "xln_parts",
            sympy.Symbol("x") ** 2 * sympy.log(sympy.Symbol("x")) / 2 - sympy.Symbol("x") ** 2 / 4,
        ),
        (
            "xcos2_parts",
            sympy.Symbol("x") * sympy.sin(2 * sympy.Symbol("x")) / 2
            + sympy.cos(2 * sympy.Symbol("x")) / 4,
        ),
    ],
)
def test_by_parts_answers_use_demidovich_form(task_id: str, want: sympy.Expr) -> None:
    got = answer_expression(first(PROTO[task_id]))
    got = got.replace(lambda node: isinstance(node, sympy.Abs), lambda node: node.args[0])
    assert sympy.simplify(got - want) == 0


def test_second_by_parts_application_is_its_own_stage_group() -> None:
    card = first(PROTO["ind22_x2exp_parts"])
    keys = card_keys(card)
    assert keys.count("lesson_calc_int_parts_choose") == 2
    assert keys.count("lesson_calc_int_parts_differential") == 2
    assert keys.count("lesson_calc_int_parts_apply") == 2
    second = [
        sub
        for sub in _substeps(card)
        if sub["description"]["type"] == "lesson_calc_int_parts_choose"
    ][1]
    assert any(
        _equals(node, "u") and node["children"][1].get("type") in ("MULTIPLY", "MULTIPLY_IMPLICIT")
        for node in nodes_of(second.get("left"))
    )
    assert derivative_matches(PROTO["ind22_x2exp_parts"])


def test_cyclic_by_parts_names_i_and_doubles_it() -> None:
    source = PROTO["ind23_exp_sin_parts"]
    card = first(source)
    assert header_key(card) == "lesson_calc_header_int_parts"
    keys = card_keys(card)
    for key in (
        "lesson_calc_int_parts_cyclic_define",
        "lesson_calc_int_parts_cyclic_equation",
        "lesson_calc_int_parts_cyclic_move",
        "lesson_calc_int_parts_cyclic_value",
        "integrate_msg_addc",
    ):
        assert key in keys
    assert any("I" in text for text in texts(card))
    x = sympy.Symbol("x")
    want = sympy.exp(x) * (sympy.sin(x) - sympy.cos(x)) / 2
    assert sympy.simplify(answer_expression(card) - want) == 0
    # The equation has −I on the right; after moving it, 2I on the left.
    equation = _substep(card, "lesson_calc_int_parts_cyclic_equation")
    assert any(node["type"] == "SUBTRACT" for node in nodes_of(equation.get("left")))
    moved = _substep(card, "lesson_calc_int_parts_cyclic_move")
    assert any(node["type"] == "MULTIPLY_IMPLICIT" for node in nodes_of(moved.get("left")))


# ── 11. INT2: rational functions ──────────────────────────────────────

FRACTIONS = ["ind25_rat_a2", "ind26_rat_xp3", "ind27_rat_repeat"]


@pytest.mark.parametrize("task_id", FRACTIONS)
def test_fraction_card_shows_decomposition_coefficients_and_term_integrals(task_id: str) -> None:
    source = PROTO[task_id]
    card = first(source)
    assert header_key(card) == "lesson_calc_header_int_frac"
    keys = card_keys(card)
    for key in (
        "lesson_calc_int_frac_factor",
        "lesson_calc_int_frac_form",
        "lesson_calc_int_frac_equations",
        "lesson_calc_int_frac_coeffs",
        "lesson_calc_int_frac_numbers",
        "lesson_calc_int_sum_rule",
        "integrate_msg_addc",
    ):
        assert key in keys
    assert derivative_matches(source)
    form = _substep(card, "lesson_calc_int_frac_form")
    assert any(
        node["type"] == "VARIABLE" and node.get("value") in ("A", "B", "C")
        for node in nodes_of(form.get("left"))
    )
    coefficients = _substep(card, "lesson_calc_int_frac_coeffs")
    values = {
        node["children"][1].get("value")
        for node in nodes_of(coefficients.get("left"))
        if node["type"] == "EQUALS" and node["children"][1].get("type") == "CONSTANT"
    }
    assert values


def test_fraction_coefficients_are_the_textbook_numbers() -> None:
    card = first(PROTO["ind26_rat_xp3"])
    coefficients = _substep(card, "lesson_calc_int_frac_coeffs")
    values = {
        (node["children"][0].get("value"), node["children"][1].get("value"))
        for node in nodes_of(coefficients.get("left"))
        if node["type"] == "EQUALS"
    }
    assert values == {("A", "5"), ("B", "-4")}


def test_improper_fraction_is_divided_first() -> None:
    card = first(PROTO["rat_division"])
    assert header_key(card) == "lesson_calc_header_int_frac"
    assert card_keys(card)[0] == "lesson_calc_int_frac_divide"
    divide = _substep(card, "lesson_calc_int_frac_divide")
    # A fact: the division itself is the only formula of the stage.
    assert divide["left"]["type"] == "EQUALS"
    assert divide.get("right") is None
    assert "Выделим целую часть" in (divide.get("explanation") or {}).get("text", "")
    assert derivative_matches(PROTO["rat_division"])


def test_repeated_linear_factor_has_a_square_term() -> None:
    card = first(PROTO["ind27_rat_repeat"])
    keys = card_keys(card)
    assert keys.count("lesson_calc_int_term_table") == 3
    x = sympy.Symbol("x")
    want = sympy.log(x) - sympy.log(x + 1) + 1 / (x + 1)
    got = answer_expression(card).replace(
        lambda node: isinstance(node, sympy.Abs), lambda node: node.args[0]
    )
    assert sympy.simplify(got - want) == 0


def test_complete_square_names_t_and_brings_in_arctg() -> None:
    source = PROTO["ind28_complete_sq"]
    card = first(source)
    assert header_key(card) == "lesson_calc_header_int_square"
    keys = card_keys(card)
    assert "lesson_calc_int_frac_square" in keys
    assert "lesson_calc_int_substitute" in keys
    substitute = _substep(card, "lesson_calc_int_substitute")
    assert any(_equals(node, "t") for node in nodes_of(substitute.get("left")))
    x = sympy.Symbol("x")
    assert sympy.simplify(answer_expression(card) - sympy.atan((x + 1) / 2) / 2) == 0
    assert derivative_matches(source)


def test_linear_numerator_over_quadratic_splits_into_ln_and_arctg() -> None:
    for key, header in (
        ("square_ln_atan", "lesson_calc_header_int_square"),
        ("rat_ln_atan", "lesson_calc_header_int_frac"),
    ):
        source = PROTO[key]
        card = first(source)
        assert header_key(card) == header
        keys = card_keys(card)
        assert "lesson_calc_int_frac_split" in keys
        assert "lesson_calc_int_sum_rule" in keys
        assert derivative_matches(source)
    card = first(PROTO["square_ln_atan"])
    x = sympy.Symbol("x")
    want = sympy.log(x**2 + 2 * x + 5) / 2 + sympy.atan((x + 1) / 2) / 2
    assert sympy.simplify(answer_expression(card) - want) == 0


# ── 12. INT2: the operator's INT1 follow-ups ──────────────────────────


def test_back_substituted_power_is_not_expanded_in_the_answer() -> None:
    for key, exponent in (
        ("pow5_back_sub", "6"),
        ("linear_power_back_sub", "8"),
    ):
        source = PROTO[key]
        card = first(source)
        solution = card["result"]["solutionNode"]
        powers = [
            node
            for node in nodes_of(solution)
            if node["type"] == "POWER" and node["children"][1].get("value") == exponent
        ]
        assert powers, key
        assert all(any(child.get("type") == "ADD" for child in node["children"]) for node in powers)
        # The + C stage keeps the same back-substituted form.
        addc = _substep(card, "integrate_msg_addc")
        stage_powers = [
            node
            for node in nodes_of(addc.get("right"))
            if node["type"] == "POWER" and node["children"][1].get("value") == exponent
        ]
        assert stage_powers, key
        assert derivative_matches(source)


def test_rule_formulas_do_not_integrate_placeholder_letters() -> None:
    """Every ∫ under a formula draws the problem's variable, never u or dv."""
    for task_id in INDEFINITE:
        data = response(INDEFINITE_PROTO[task_id])
        card = data["result"]["groups"][0]["entries"][0]
        for sub in _substeps(card):
            for node in explanation_nodes(sub.get("explanation")):
                if node["type"] != "INTEGRAL" or not node.get("children"):
                    continue
                names = {
                    child.get("value")
                    for child in nodes_of(node["children"][0])
                    if child["type"] == "VARIABLE" and child.get("value") not in ("e", "π", "i")
                }
                # The app draws the sole variable, else x; both must be the
                # integration variable of the problem.
                assert len(names) <= 1 or "x" in names or "t" in names, (task_id, names)


def test_linearity_rule_is_written_in_the_theory_article() -> None:
    """The chip is arg-free: the rule ∫(f + g) = ∫f + ∫g is in its theory."""
    card = first(PROTO["ind10_linear"])
    rule = _substep(card, "lesson_calc_int_sum_rule")
    assert not rule["description"].get("args")
    theory = (rule.get("explanation") or {}).get("theory") or {}
    formula = theory.get("formula", "")
    assert "∫ (f(x) + g(x)) dx = ∫ f(x) dx + ∫ g(x) dx" in formula
    assert "∫ c f(x) dx = c ∫ f(x) dx" in formula


def test_integral_in_t_is_a_node_not_text_with_dt() -> None:
    card = first(PROTO["ind16_ln_over_x"])
    rewrite = _substep(card, "lesson_calc_int_rewrite")
    assert any(node["type"] == "INTEGRAL" for node in nodes_of(rewrite.get("right")))
    inner = _substep(card, "lesson_calc_int_inner_table")
    assert any(node["type"] == "INTEGRAL" for node in nodes_of(inner.get("left")))
    for text in texts(card):
        assert not re.search(r"∫\s*ARG", text), text


@pytest.mark.parametrize(
    "task_id",
    [
        "x_in_ln_sub",
        "ln_cube_over_x",
        "exp_over_one_plus_exp",
        "cos_exp_sin",
        "x2_over_x3p1",
    ],
)
def test_new_substitution_families_reach_the_textbook_card(task_id: str) -> None:
    source = PROTO[task_id]
    card = first(source)
    assert header_key(card) == "lesson_calc_header_int_substitution"
    keys = card_keys(card)
    for key in SUBSTITUTION_KEYS:
        assert key in keys
    assert derivative_matches(source)


def test_cosine_square_gets_the_half_angle_card() -> None:
    card = first(PROTO["cos2_half_angle"])
    assert header_key(card) == "lesson_calc_header_int_half_angle"
    assert card_keys(card)[0] == "lesson_calc_int_half_angle"
    assert derivative_matches(PROTO["cos2_half_angle"])


def test_differential_drops_a_unit_coefficient() -> None:
    card = first(PROTO["negative_linear"])
    differential = _substep(card, "lesson_calc_int_differential")
    equations = [node for node in nodes_of(differential.get("left")) if node["type"] == "EQUALS"]
    assert equations
    right = equations[0]["children"][1]
    assert right["type"] == "NEGATIVE"
    assert right["children"][0].get("value") == "dx"
    assert "1" not in json.dumps(right)


def test_substitution_argument_is_written_in_descending_order() -> None:
    for key, want in (
        ("pow5_back_sub", ("POWER", "ADD")),
        ("linear_sub_order", ("MULTIPLY", "ADD")),
        ("x_in_ln_sub", ("LN",)),
    ):
        card = first(PROTO[key])
        substitute = _substep(card, "lesson_calc_int_substitute")
        right = next(node for node in nodes_of(substitute.get("left")) if _equals(node, "t"))[
            "children"
        ][1]
        if right["type"] == "ADD":
            assert right["children"][0]["type"] == want[0], key
        else:
            assert right["type"] in (want[0], "MULTIPLY_IMPLICIT"), key


# ── 13. INT3: every stage moves; facts are facts ─────────────────────

DEFINITE = {
    "def01_x2": "{integral_def({0},{1},{x^2})}",
    "def02_sin": "{integral_def({0},{pi},{sin({x})})}",
    "def03_lnx_over_x": "{integral_def({1},{e},{frac({ln({x})},{x})})}",
    "def04_xexp2": "{integral_def({0},{1},{x*exp({x^2})})}",
    "def05_xexp_parts": "{integral_def({0},{1},{x*exp({x})})}",
    "def06_odd": "{integral_def({-1},{1},{x^3})}",
    "def08_improper_conv": "{integral_def({1},{inf},{frac({1},{x^2})})}",
    "def09_improper_div": "{integral_def({1},{inf},{frac({1},{x})})}",
    "def10_improper_discon": "{integral_def({0},{1},{frac({1},{root2({x})})})}",
    "def11_cos": "{integral_def({0},{frac({pi},{2})},{cos({x})})}",
    "def12_recip": "{integral_def({1},{2},{frac({1},{x})})}",
    "def13_xsin_parts": "{integral_def({0},{pi},{x*sin({x})})}",
    "def_even": "{integral_def({-1},{1},{x^2})}",
    "def_both_inf": "{integral_def({-inf},{inf},{frac({1},{1+x^2})})}",
    "def_imp_recip": "{integral_def({0},{1},{frac({1},{x})})}",
    "def_euler": "{integral_def({0},{inf},{exp({-x^2})})}",
}
PROTO |= DEFINITE

INT3_EXTRA = {
    "x2_over_xm1": "{integral({frac({x^2},{x-1})})}",
    "ln_square": "{integral({ln({x})^2})}",
    "x3_over_x2m1": "{integral({frac({x^3},{x^2-1})})}",
    "three_x_plus_one": "{integral({frac({3x+1},{x^2+4x+8})})}",
    "x_exp_negative": "{integral({x*exp({-x})})}",
}
PROTO |= INT3_EXTRA

ALL_PROTOCOLS = (
    [PROTO[task_id] for task_id in INDEFINITE]
    + [PROTO[key] for key in INT3_EXTRA]
    + list(DEFINITE.values())
)


def _contract(value: Any) -> CoreNode:
    return CoreNode.from_contract(value)


def _lesson_card(source: str) -> dict[str, Any]:
    return cards(source)[0]


def _all_substeps(card: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Every stage of the card and of its «Подробнее» screens."""
    for step in card["result"].get("steps") or []:
        for sub in step.get("substeps") or []:
            yield sub
            nested = sub.get("subresult")
            if isinstance(nested, dict):
                yield from _all_substeps({"result": nested})


@pytest.mark.parametrize("source", ALL_PROTOCOLS)
def test_no_stage_repeats_its_own_formula(source: str) -> None:
    """A stage with an arrow must move: ``left`` and ``right`` differ."""
    for sub in _all_substeps(_lesson_card(source)):
        left, right = sub.get("left"), sub.get("right")
        if left is None or right is None:
            continue
        assert not _contract(left).structural_eq(_contract(right)), sub["description"]["type"]


def _assert_chain(card: dict[str, Any], source: str) -> None:
    """Within one screen: the next transform starts where the previous one ended."""
    previous: dict[str, Any] | None = None
    for step in card["result"].get("steps") or []:
        for sub in step.get("substeps") or []:
            right = sub.get("right")
            if right is None:  # a fact does not move the chain
                continue
            if previous is not None:
                assert _contract(previous).structural_eq(_contract(sub["left"])), (
                    source,
                    sub["description"]["type"],
                )
            previous = right
            nested = sub.get("subresult")
            if isinstance(nested, dict):
                _assert_chain({"result": nested}, source)


@pytest.mark.parametrize("source", ALL_PROTOCOLS)
def test_transforming_stages_chain_through_facts(source: str) -> None:
    """The next transforming stage starts where the previous one ended."""
    _assert_chain(_lesson_card(source), source)


# ── 14. INT3: substitution, by parts, complete square ────────────────


def test_substitution_shows_facts_then_the_new_integral() -> None:
    card = _lesson_card(PROTO["ind12_sin3x"])
    keys = card_keys(card)
    assert keys == [
        "lesson_calc_int_linear_rule",
        "lesson_calc_int_substitute",
        "lesson_calc_int_differential",
        "lesson_calc_int_rewrite",
        "lesson_calc_int_inner_table",
        "lesson_calc_int_back_sub",
        "integrate_msg_addc",
    ]
    for key in ("lesson_calc_int_substitute", "lesson_calc_int_differential"):
        stage = _substep(card, key)
        assert stage.get("right") is None
        assert stage["left"]["type"] == "EQUALS"
    rewrite = _substep(card, "lesson_calc_int_rewrite")
    assert rewrite["left"]["type"] == "INTEGRAL"
    assert rewrite["right"]["type"] == "MULTIPLY_IMPLICIT"
    assert rewrite["right"]["children"][0]["value"] == "1/3"
    assert rewrite["right"]["children"][1]["type"] == "INTEGRAL"


def test_by_parts_chain_ends_with_the_textbook_answer() -> None:
    card = _lesson_card(PROTO["ind19_xexp_parts"])
    applied = _substep(card, "lesson_calc_int_parts_apply")
    assert any(node["type"] == "INTEGRAL" for node in nodes_of(applied["right"]))
    remainder = _substep(card, "lesson_calc_int_parts_remainder")
    assert _contract(applied["right"]).structural_eq(_contract(remainder["left"]))
    answer_stage = _substep(card, "lesson_calc_int_parts_answer")
    x = sympy.Symbol("x")
    assert sympy.simplify(to_sympy(_contract(answer_stage["right"])) - (x - 1) * sympy.exp(x)) == 0


def test_negative_exponential_keeps_the_remaining_integral_positive() -> None:
    source = PROTO["x_exp_negative"]
    card = _lesson_card(source)
    # The sign is in the formula: the remaining integral is ADD-ed, not SUBTRACT-ed.
    applied = _substep(card, "lesson_calc_int_parts_apply")
    assert applied["right"]["type"] == "ADD"
    assert any(node["type"] == "INTEGRAL" for node in nodes_of(applied["right"]))
    x = sympy.Symbol("x")
    want = -(x + 1) * sympy.exp(-x)
    got = answer_expression(card)
    assert sympy.simplify(got - want) == 0
    assert derivative_matches(source)


def test_complete_square_shows_the_denominator_and_a_lone_differential() -> None:
    card = _lesson_card(PROTO["ind28_complete_sq"])
    square = _substep(card, "lesson_calc_int_frac_square")
    assert square["left"]["type"] == "INTEGRAL"
    fraction = square["left"]["children"][0]
    assert fraction["type"] == "FRACTION" and fraction["children"][0]["value"] == "1"
    assert square["right"]["type"] == "INTEGRAL"
    assert square["right"]["children"][0]["type"] == "FRACTION"
    differential = _substep(card, "lesson_calc_int_differential")
    assert differential.get("right") is None
    assert differential["left"]["type"] == "EQUALS"
    assert [child["value"] for child in differential["left"]["children"]] == ["dt", "dx"]
    # arctg((x + 2)/2), not arctg(1 + x/2).
    answer = card["result"]["solutionNode"]
    arctangents = [node for node in nodes_of(answer) if node["type"] == "ATAN"]
    assert arctangents
    assert arctangents[0]["children"][0]["type"] == "FRACTION"


def test_split_numerator_writes_the_polynomial_descending() -> None:
    card = _lesson_card(PROTO["three_x_plus_one"])
    split = _substep(card, "lesson_calc_int_frac_split")
    assert split.get("right") is None
    formula = split["left"]
    assert formula["type"] == "EQUALS"
    assert formula["children"][0]["children"][0]["type"] == "MULTIPLY_IMPLICIT"
    assert formula["children"][1]["type"] == "SUBTRACT"
    assert "6x^2" not in json.dumps(formula)


def test_improper_rational_divides_before_partial_fractions() -> None:
    source = PROTO["x2_over_xm1"]
    card = _lesson_card(source)
    assert header_key(card) == "lesson_calc_header_int_frac"
    divide = _substep(card, "lesson_calc_int_frac_divide")
    assert divide.get("right") is None
    assert divide["left"]["type"] == "EQUALS"
    x = sympy.Symbol("x")
    want = x**2 / 2 + x + sympy.log(sympy.Abs(x - 1))
    got = answer_expression(card).replace(
        lambda node: isinstance(node, sympy.Abs), lambda node: node.args[0]
    )
    assert sympy.simplify(got - want.replace(sympy.Abs(x - 1), x - 1)) == 0
    # Division route: the answer has no constant term next to + C.
    divided = answer_expression(_lesson_card(PROTO["x3_over_x2m1"]))
    without_logs = divided.replace(lambda node: isinstance(node, sympy.log), lambda node: 0)
    assert sympy.simplify(without_logs).subs(x, 0) == 0


def test_log_squared_is_by_parts_twice() -> None:
    card = _lesson_card(PROTO["ln_square"])
    assert header_key(card) == "lesson_calc_header_int_parts"
    assert card_keys(card).count("lesson_calc_int_parts_apply") == 2
    x = sympy.Symbol("x")
    want = x * sympy.log(x) ** 2 - 2 * x * sympy.log(x) + 2 * x
    got = answer_expression(card).replace(
        lambda node: isinstance(node, sympy.Abs), lambda node: node.args[0]
    )
    assert sympy.simplify(got - want) == 0


# ── 15. INT3: definite integrals ─────────────────────────────────────


def _stage(card: dict[str, Any], key: str) -> dict[str, Any]:
    return _substep(card, key)


@pytest.mark.parametrize(
    "source",
    [
        PROTO["def01_x2"],
        PROTO["def02_sin"],
        PROTO["def05_xexp_parts"],
        PROTO["def12_recip"],
        PROTO["def13_xsin_parts"],
    ],
)
def test_newton_leibniz_card_has_formula_bounds_values_and_difference(source: str) -> None:
    card = _lesson_card(source)
    assert header_key(card) == "lesson_calc_header_int_newton"
    keys = card_keys(card)
    for key in (
        "lesson_calc_int_newton_formula",
        "lesson_calc_int_newton_primitive",
        "lesson_calc_int_newton_bounds",
        "lesson_calc_int_newton_subst",
        "lesson_calc_int_newton_upper",
        "lesson_calc_int_newton_lower",
        "lesson_calc_int_newton_calc",
    ):
        assert key in keys
    formula = _stage(card, "lesson_calc_int_newton_formula")
    assert formula.get("right") is None
    assert formula["left"]["type"] == "EQUALS"
    assert formula["left"]["children"][0]["type"] == "INTEGRAL_DEFINITE"
    # F(x) comes from the indefinite textbook card, without + C.
    primitive = _stage(card, "lesson_calc_int_newton_primitive")
    assert primitive.get("subresult") is not None
    assert "integrate_msg_addc" not in {
        sub["description"]["type"]
        for step in primitive["subresult"].get("steps") or []
        for sub in step.get("substeps") or []
    }
    bounds = _stage(card, "lesson_calc_int_newton_bounds")
    assert bounds["right"]["type"] == "INTEGRAL_RIGHT_DASH"
    upper = _stage(card, "lesson_calc_int_newton_upper")
    lower = _stage(card, "lesson_calc_int_newton_lower")
    assert upper["left"]["type"] == "EQUALS" and lower["left"]["type"] == "EQUALS"
    difference = _stage(card, "lesson_calc_int_newton_calc")
    assert difference["right"] is not None


@pytest.mark.parametrize(
    ("source", "want"),
    [
        (PROTO["def01_x2"], sympy.Rational(1, 3)),
        (PROTO["def02_sin"], sympy.Integer(2)),
        (PROTO["def03_lnx_over_x"], sympy.Rational(1, 2)),
        (PROTO["def12_recip"], sympy.log(2)),
        (PROTO["def05_xexp_parts"], sympy.Integer(1)),
        (PROTO["def13_xsin_parts"], sympy.pi),
    ],
)
def test_newton_leibniz_values(source: str, want: sympy.Expr) -> None:
    got = to_sympy(_contract(_lesson_card(source)["result"]["solutionNode"]))
    assert sympy.simplify(got - want) == 0


def test_definite_substitution_changes_the_limits() -> None:
    card = _lesson_card(PROTO["def04_xexp2"])
    assert header_key(card) == "lesson_calc_header_int_subst_limits"
    limits = [
        sub
        for sub in _substeps(card)
        if sub["description"]["type"] == "lesson_calc_int_newton_sub_limits"
    ]
    # Two facts: «x = 0, t = 0» and «x = 1, t = 1», not one four-row list.
    assert len(limits) == 2
    for stage in limits:
        assert stage.get("right") is None
        assert stage["left"]["type"] == "LIST"
        assert len(stage["left"]["children"]) == 2
    lower_x, lower_t = (child["children"][1]["value"] for child in limits[0]["left"]["children"])
    upper_x, upper_t = (child["children"][1]["value"] for child in limits[1]["left"]["children"])
    assert (lower_x, lower_t, upper_x, upper_t) == ("0", "0", "1", "1")
    rewrite = _stage(card, "lesson_calc_int_newton_sub_rewrite")
    assert rewrite["right"]["type"] == "MULTIPLY_IMPLICIT"
    assert rewrite["right"]["children"][1]["type"] == "INTEGRAL_DEFINITE"
    assert "lesson_calc_int_back_sub" not in card_keys(card)
    got = to_sympy(_contract(card["result"]["solutionNode"]))
    assert sympy.simplify(got - (sympy.E - 1) / 2) == 0
    # (e − 1)/2 as a single fraction, not e/2 − 1/2.
    assert card["result"]["solutionNode"]["type"] == "FRACTION"


def test_odd_function_card_comes_first_and_newton_second() -> None:
    entries = cards(PROTO["def06_odd"])
    assert header_key(entries[0]) == "lesson_calc_header_int_parity"
    assert header_key(entries[1]) == "lesson_calc_header_int_newton"
    odd = entries[0]["result"]["solutionNode"]
    assert odd["type"] == "CONSTANT" and odd["value"] == "0"
    fact = _substep(entries[0], "lesson_calc_int_parity_odd")
    assert fact.get("right") is None
    assert fact["left"]["type"] == "EQUALS"


def test_even_function_doubles_the_half_interval() -> None:
    card = _lesson_card(PROTO["def_even"])
    assert header_key(card) == "lesson_calc_header_int_parity"
    doubled = next(
        sub
        for sub in _substeps(card)
        if sub["description"]["type"] == "lesson_calc_int_parity_even_calc"
    )
    assert doubled["right"]["type"] == "MULTIPLY_IMPLICIT"
    assert doubled["right"]["children"][0]["value"] == "2"
    assert doubled["right"]["children"][1]["type"] == "INTEGRAL_DEFINITE"
    got = to_sympy(_contract(card["result"]["solutionNode"]))
    assert sympy.simplify(got - sympy.Rational(2, 3)) == 0


def test_improper_convergent_uses_a_limit_node() -> None:
    card = _lesson_card(PROTO["def08_improper_conv"])
    assert header_key(card) == "lesson_calc_header_int_improper"
    rewrite = _stage(card, "lesson_calc_int_imp_rewrite")
    assert rewrite["right"]["type"] == "LIMIT"
    assert rewrite["right"]["children"][1]["type"] == "INTEGRAL_DEFINITE"
    assert _stage(card, "lesson_calc_int_imp_value")["right"] is not None
    solution = card["result"]["solutionNode"]
    assert solution["type"] == "CONSTANT" and solution["value"] == "1"


def test_divergent_improper_integral_is_an_answer_card_with_the_reason() -> None:
    entries = cards(PROTO["def09_improper_div"])
    card = entries[0]
    assert header_key(card) == "lesson_calc_header_int_diverges"
    assert card_keys(card)[-1] == "lesson_calc_int_imp_diverges"
    diverges = _stage(card, "lesson_calc_int_imp_diverges")
    assert diverges.get("right") is None
    assert diverges["left"]["children"][1]["value"] == "∞"
    solution = card["result"]["solutionNode"]
    assert solution["type"] == "TEXT" and "расходится" in solution["value"]


def test_improper_discontinuity_approaches_from_the_right() -> None:
    card = _lesson_card(PROTO["def10_improper_discon"])
    rewrite = _stage(card, "lesson_calc_int_imp_rewrite")
    assert rewrite["right"]["type"] == "LIMIT_RIGHT"
    got = to_sympy(_contract(card["result"]["solutionNode"]))
    assert sympy.simplify(got - 2) == 0
    divergent = _lesson_card(PROTO["def_imp_recip"])
    assert header_key(divergent) == "lesson_calc_header_int_diverges"


def test_both_infinite_limits_for_an_even_integrand() -> None:
    card = _lesson_card(PROTO["def_both_inf"])
    rewrite = _stage(card, "lesson_calc_int_imp_rewrite")
    inner = rewrite["right"]["children"][1]
    assert inner["children"][0]["type"] == "NEGATIVE"
    got = to_sympy(_contract(card["result"]["solutionNode"]))
    assert sympy.simplify(got - sympy.pi) == 0


def test_euler_poisson_definite_integral_names_the_integral() -> None:
    card = _lesson_card(PROTO["def_euler"])
    assert header_key(card) == "lesson_calc_header_int_euler_poisson"
    fact = _stage(card, "lesson_calc_int_euler_poisson")
    assert fact.get("right") is None
    assert fact["left"]["type"] == "EQUALS"
    got = to_sympy(_contract(card["result"]["solutionNode"]))
    assert sympy.simplify(got - sympy.sqrt(sympy.pi) / 2) == 0


@pytest.mark.parametrize("task_id", ["def01_x2", "def02_sin", "def11_cos", "def06_odd"])
def test_no_duplicated_detail_on_the_row_definite_card(task_id: str) -> None:
    verified = cards(PROTO[task_id])[1]
    nested = [
        sub["description"]["type"]
        for step in verified["result"].get("steps") or []
        for sub in step.get("substeps") or []
        if sub.get("subresult")
    ]
    assert len(nested) <= 1, nested


# ── 16. INT5: one step per card, no echoed formulas, epsilon, order ────


def lesson_cards(source: str) -> list[dict[str, Any]]:
    """The textbook entries of a problem (the verified card excluded)."""
    return [
        entry for entry in cards(source) if header_key(entry).startswith("lesson_calc_header_int")
    ]


def step_headers(card: dict[str, Any]) -> list[tuple[str, ...]]:
    return [
        tuple(header["type"] for header in step.get("headers") or [])
        for step in card["result"].get("steps") or []
    ]


@pytest.mark.parametrize("source", ALL_PROTOCOLS)
def test_one_step_per_card_without_repeated_headings(source: str) -> None:
    """A card is «Вычислите интеграл» (+ «Прибавить C»), not a column of them."""
    entries = lesson_cards(source)
    assert entries, source
    for card in entries:
        headers = step_headers(card)
        # By parts twice may keep one step per application (distinct headings);
        # everything else is «Вычислите интеграл» plus «Прибавить C».
        application_steps = sum(
            1 for header in headers if "lesson_calc_header_int_parts_" in header[0]
        )
        assert len(headers) <= 2 + application_steps, (source, headers)
        for previous, current in pairwise(headers):
            assert previous != current, (source, headers)


def test_by_parts_puts_every_stage_in_one_step() -> None:
    card = first(PROTO["ind19_xexp_parts"])
    headers = step_headers(card)
    assert headers[0] == ("find_integral",)
    keys = card_keys(card)
    assert keys.count("lesson_calc_int_parts_apply") == 1
    assert len(card["result"]["steps"][0]["substeps"]) >= 5


def test_by_parts_twice_names_each_application() -> None:
    card = first(PROTO["ind22_x2exp_parts"])
    first_step, second_step = card["result"]["steps"][:2]
    assert first_step["headers"][0]["type"] == "lesson_calc_header_int_parts_first"
    assert second_step["headers"][0]["type"] == "lesson_calc_header_int_parts_second"
    card = first(PROTO["ind23_exp_sin_parts"])
    assert card["result"]["steps"][0]["headers"][0]["type"] == (
        "lesson_calc_header_int_parts_first"
    )
    assert card["result"]["steps"][1]["headers"][0]["type"] == (
        "lesson_calc_header_int_parts_second"
    )


@pytest.mark.parametrize("source", ALL_PROTOCOLS)
def test_no_text_arg_repeats_the_stage_formula(source: str) -> None:
    """When the formula shows the fact, the text only names the move."""
    for card in lesson_cards(source):
        for sub in _all_substeps(card):
            left, right = sub.get("left"), sub.get("right")
            for arg in (sub.get("description") or {}).get("args") or []:
                arg_node = _contract(arg)
                if left is not None:
                    assert not arg_node.structural_eq(_contract(left)), (
                        source,
                        sub["description"]["type"],
                        "left",
                    )
                if right is not None:
                    assert not arg_node.structural_eq(_contract(right)), (
                        source,
                        sub["description"]["type"],
                        "right",
                    )


@pytest.mark.parametrize("source", ALL_PROTOCOLS)
def test_table_and_linearity_chips_are_arg_free(source: str) -> None:
    """No «Табличный интеграл: ∫xⁿ dx = …» on a phone: the chip only names the move."""
    for card in lesson_cards(source):
        for sub in _all_substeps(card):
            key = sub["description"]["type"]
            args = sub["description"].get("args") or []
            if key in (
                "lesson_calc_int_term_table",
                "lesson_calc_int_inner_table",
                "lesson_calc_int_table_rule",
                "lesson_calc_int_sum_rule",
            ):
                assert not args, (source, key)


def test_improper_discontinuity_rule_uses_a_finite_bound_and_epsilon() -> None:
    card = _lesson_card(PROTO["def10_improper_discon"])
    formula = _stage(card, "lesson_calc_int_imp_formula")["left"]
    assert formula["type"] == "EQUALS"
    left, limit = formula["children"]
    assert left["type"] == "INTEGRAL_DEFINITE"
    assert limit["type"] == "LIMIT_RIGHT"
    inner = limit["children"][1]
    assert inner["type"] == "INTEGRAL_DEFINITE"
    lower = inner["children"][0]
    assert lower["type"] == "ADD"
    assert lower["children"][0]["value"] == "a"
    assert lower["children"][1] == {"type": "VARIABLE", "value": "ε", "children": []}
    # The old placeholder «eps» drew as italic e·p·s and must be gone.
    assert '"value": "eps"' not in json.dumps(card)


def test_improper_positive_endpoint_has_no_absolute_value() -> None:
    card = _lesson_card(PROTO["def10_improper_discon"])
    primitive = _stage(card, "lesson_calc_int_imp_primitive")
    values = primitive["right"]["children"][1]
    # 2√1 is evaluated in this same stage: 2 − 2√ε, not 2√1 − 2√ε.
    assert values["type"] == "SUBTRACT"
    assert values["children"][0] == {"type": "CONSTANT", "value": "2", "children": []}
    root = values["children"][1]
    assert root["type"] == "MULTIPLY_IMPLICIT"
    assert root["children"][1]["type"] == "ROOT2"
    assert root["children"][1]["children"][0]["value"] == "ε"
    assert not any(node["type"] == "ABS" for node in nodes_of(primitive["right"]))

    divergent = _lesson_card(PROTO["def09_improper_div"])
    primitive = _stage(divergent, "lesson_calc_int_imp_primitive")
    difference = primitive["right"]["children"][1]
    assert difference["type"] == "SUBTRACT"
    first, second = difference["children"]
    assert first["type"] == "LN" and first["children"][0]["value"] == "b"
    assert second["type"] == "LN" and second["children"][0]["value"] == "1"
    assert not any(node["type"] == "ABS" for node in nodes_of(difference))


def _polynomial_add(node: dict[str, Any]) -> dict[str, Any]:
    """The inner ``x + 1`` of a formula, not the outer sum of fractions."""
    return next(
        item
        for item in nodes_of(node)
        if item["type"] == "ADD" and any(child["type"] == "CONSTANT" for child in item["children"])
    )


def test_fraction_card_is_written_descending() -> None:
    card = _lesson_card(PROTO["ind25_rat_a2"])
    factored = _stage(card, "lesson_calc_int_frac_factor")["left"]["children"][1]
    assert _polynomial_add(factored)["children"][0]["value"] == "x"

    form = _stage(card, "lesson_calc_int_frac_form")["left"]["children"][1]
    denominators = [child["children"][1] for child in form["children"]]
    assert denominators[1]["type"] == "ADD"
    assert denominators[1]["children"][0]["value"] == "x"

    equations = _stage(card, "lesson_calc_int_frac_equations")["left"]["children"][1]
    assert _polynomial_add(equations)["children"][0]["value"] == "x"

    numbers = _stage(card, "lesson_calc_int_frac_numbers")["left"]["children"][1]
    assert _polynomial_add(numbers)["children"][0]["value"] == "x"

    answer = card["result"]["solutionNode"]
    for argument in nodes_of(answer):
        if argument["type"] != "ADD":
            continue
        kinds = {child["type"] for child in argument["children"]}
        if {"VARIABLE", "CONSTANT"} <= kinds:
            assert argument["children"][0]["type"] == "VARIABLE"

    # The table rule of 1/(x+1): the denominator and ln|·| keep the page order.
    for sub in _all_substeps(card):
        if sub["description"]["type"] != "lesson_calc_int_table_rule":
            continue
        rule = sub["left"]
        if rule["children"][0]["type"] != "INTEGRAL":
            continue
        body = rule["children"][0]["children"][0]
        if body["type"] == "FRACTION" and body["children"][1]["type"] == "ADD":
            assert body["children"][1]["children"][0]["value"] == "x"
            logarithm = rule["children"][1]["children"][0]
            assert logarithm["children"][0]["type"] == "ADD"
            assert logarithm["children"][0]["children"][0]["value"] == "x"


def test_parity_card_shows_the_concrete_check() -> None:
    odd = _lesson_card(PROTO["def06_odd"])
    check = _stage(odd, "lesson_calc_int_parity_odd")["left"]
    assert check["type"] == "EQUALS"
    assert len(check["children"]) == 4
    negative_x, minus_cube, minus_f = check["children"][1:]
    assert negative_x["type"] == "POWER" and negative_x["children"][1]["value"] == "3"
    assert negative_x["children"][0]["type"] == "NEGATIVE"
    assert minus_cube["type"] == "NEGATIVE"
    assert minus_f["type"] == "NEGATIVE" and minus_f["children"][0]["type"] == "FUNCTION"

    even = cards(PROTO["def_even"])[0]
    check = _stage(even, "lesson_calc_int_parity_even")["left"]
    assert check["type"] == "EQUALS" and len(check["children"]) == 4
    negative_x, same_square, same_f = check["children"][1:]
    assert negative_x["type"] == "POWER" and negative_x["children"][1]["value"] == "2"
    assert negative_x["children"][0]["type"] == "NEGATIVE"
    assert same_square["type"] == "POWER"
    assert same_f["type"] == "FUNCTION"
    # then ∫₋ₐᵃ = 2∫₀ᵃ and its Newton–Leibniz.
    rights = [sub.get("right") for sub in _substeps(even)]
    assert any(
        right is not None
        and right["type"] == "MULTIPLY_IMPLICIT"
        and right["children"][0].get("value") == "2"
        and right["children"][1]["type"] == "INTEGRAL_DEFINITE"
        for right in rights
    )
    assert any(
        node["type"] == "INTEGRAL_RIGHT_DASH"
        for right in rights
        if right is not None
        for node in nodes_of(right)
    )


# ── 16. INT6: theory of the method, improper fractions, the by-parts formula ──


def _theory_ids(value: Any) -> set[str]:
    """Every theory article id shown anywhere in a response."""
    found: set[str] = set()
    for node in roots(value):
        theory = node.get("theory") if isinstance(node, dict) else None
        if isinstance(theory, dict) and theory.get("id"):
            found.add(str(theory["id"]))
    return found


INT6_CARDS = [
    (
        "x e^x",
        "{integral({x*exp({x})})}",
        {"calculus:calculus_integral_parts", "calculus:calculus_integral_table"},
    ),
    (
        "sin 3x",
        "{integral({sin({3x})})}",
        {
            "calculus:calculus_linear_integral",
            "calculus:calculus_integral_substitution",
            "calculus:calculus_integral_table",
        },
    ),
    (
        "1/(x²−1)",
        "{integral({frac({1},{x^2-1})})}",
        {
            "calculus:calculus_integral_fractions",
            "calculus:calculus_integral_linearity",
            "calculus:calculus_integral_table",
        },
    ),
    (
        "∫₀¹ x²",
        "{integral_def({0},{1},{x^2})}",
        {"calculus:calculus_definite_integral", "calculus:calculus_integral_table"},
    ),
    (
        "∫₁^∞ dx/x²",
        "{integral_def({1},{inf},{frac({1},{x^2})})}",
        {"calculus:calculus_improper_integral", "calculus:calculus_integral_table"},
    ),
    (
        "∫₋₁¹ x³",
        "{integral_def({-1},{1},{x^3})}",
        {"calculus:calculus_integral_parity"},
    ),
    (
        "x e^(x²)",
        "{integral({x*exp({x^2})})}",
        {"calculus:calculus_integral_substitution", "calculus:calculus_integral_table"},
    ),
]


@pytest.mark.parametrize(("name", "source", "expected"), INT6_CARDS, ids=[c[0] for c in INT6_CARDS])
def test_every_stage_opens_the_theory_of_its_own_method(
    name: str, source: str, expected: set[str]
) -> None:
    card = first(source)
    assert _theory_ids(card) == expected, name


@pytest.mark.parametrize(("name", "source", "expected"), INT6_CARDS, ids=[c[0] for c in INT6_CARDS])
def test_integral_cards_never_open_a_limit_or_derivative_article(
    name: str, source: str, expected: set[str]
) -> None:
    # The lesson card is what the student reads first; the verified row
    # card of an improper integral names ``limit_solve`` (that is the app's
    # own wording), so it is allowed to open the limit article.
    for ident in _theory_ids(first(source)):
        assert not ident.endswith(("calculus_limit", "calculus_derivative")), (name, ident)
        assert ident != "calculus:calculus_integral", (name, ident)


def test_integral_method_articles_are_bilingual_textbook_articles() -> None:
    from mymath_backend.teaching_calculus import ARTICLES

    for topic in (
        "calculus_integral_table",
        "calculus_integral_linearity",
        "calculus_integral_substitution",
        "calculus_integral_parts",
        "calculus_integral_fractions",
        "calculus_improper_integral",
        "calculus_integral_parity",
    ):
        titles = {article["title"] for article in ARTICLES[topic].values()}
        assert len(titles) == 2, topic
        for article in ARTICLES[topic].values():
            assert all(article.values()), topic


def _flat_add_terms(node: dict[str, Any]) -> list[dict[str, Any]]:
    """The addends of a left-nested ADD chain, in page order."""
    if node.get("type") == "ADD" and len(node.get("children") or []) == 2:
        return _flat_add_terms(node["children"][0]) + _flat_add_terms(node["children"][1])
    return [node]


def test_improper_fraction_divides_in_page_order_and_has_no_stray_constant() -> None:
    card = _lesson_card("{integral({frac({x^2},{x-1})})}")
    assert header_key(card) == "lesson_calc_header_int_frac"
    divide = _stage(card, "lesson_calc_int_frac_divide")
    terms = _flat_add_terms(divide["left"]["children"][1])
    # x + 1 + 1/(x − 1): the polynomial first, then the fraction.
    assert terms[0]["type"] == "VARIABLE"
    assert terms[0]["value"] == "x"
    assert terms[-1]["type"] == "FRACTION"
    assert _theory_ids(card) == {
        "calculus:calculus_integral_fractions",
        "calculus:calculus_integral_linearity",
        "calculus:calculus_integral_table",
    }
    solution = answer_expression(card)
    x = sympy.Symbol("x")
    plain = solution.replace(lambda node: isinstance(node, sympy.Abs), lambda node: node.args[0])
    assert sympy.simplify(plain - (x**2 / 2 + x + sympy.log(x - 1))) == 0
    # No free numeric term before + C.
    assert not any(term.is_number for term in plain.as_ordered_terms())


def test_by_parts_formula_is_text_because_the_integral_node_has_no_differential_slot() -> None:
    card = _lesson_card(PROTO["ind19_xexp_parts"])
    formula = _stage(card, "lesson_calc_int_parts_formula")
    assert formula["left"]["type"] == "TEXT"
    assert "∫u dv" in formula["left"]["value"]


@pytest.mark.parametrize(
    ("source", "key"),
    [
        (PROTO["def01_x2"], "lesson_calc_int_newton_formula"),
        (PROTO["def08_improper_conv"], "lesson_calc_int_imp_formula"),
    ],
)
def test_newton_leibniz_and_improper_rule_formulas_are_formula_nodes(source: str, key: str) -> None:
    formula = _stage(_lesson_card(source), key)
    assert formula["left"]["type"] == "EQUALS"


# ── 17. INT7: complete square, short chips, decomposition order, parity, bounds ──


def response_in(source: str, locale: str) -> dict[str, Any]:
    return service.solve_request(parse_protocol(source).to_contract(), render=True, locale=locale)


def card_in(source: str, locale: str) -> dict[str, Any]:
    return response_in(source, locale)["result"]["groups"][0]["entries"][0]


def _flat_chain(node: dict[str, Any]) -> list[dict[str, Any]]:
    """The addends of an ADD/SUBTRACT chain, in page order (signs dropped)."""
    if node.get("type") in ("ADD", "SUBTRACT") and len(node.get("children") or []) == 2:
        return _flat_chain(node["children"][0]) + _flat_chain(node["children"][1])
    if node.get("type") == "NEGATIVE" and node.get("children"):
        return _flat_chain(node["children"][0])
    return [node]


def _stray_abs(node: Any, parent: str | None = None) -> bool:
    """An ``ABS`` that is not the argument of ``LN``."""
    if not isinstance(node, dict):
        return False
    kind = node.get("type")
    if kind == "ABS" and parent != "LN":
        return True
    return any(_stray_abs(child, kind) for child in node.get("children") or [])


def _integral_of(term: dict[str, Any]) -> dict[str, Any]:
    if term["type"] == "INTEGRAL":
        return term
    assert term["type"] in ("MULTIPLY", "MULTIPLY_IMPLICIT"), term
    return next(child for child in term["children"] if child["type"] == "INTEGRAL")


def _first_power(node: dict[str, Any]) -> dict[str, Any]:
    return next(item for item in nodes_of(node) if item["type"] == "POWER")


def _numeric(node: dict[str, Any]) -> str:
    """A coefficient as written: ``1/2``, ``3/2``, ``5``."""
    if node["type"] == "FRACTION":
        return f"{node['children'][0]['value']}/{node['children'][1]['value']}"
    return str(node.get("value"))


def _node_key(node: dict[str, Any]) -> tuple[Any, ...]:
    return (
        node.get("type"),
        node.get("value"),
        tuple(_node_key(child) for child in node.get("children") or []),
    )


SQUARE_CARDS = [
    ("{integral({frac({x+2},{x^2+2x+5})})}", "2", "2", "5", "1", None),
    ("{integral({frac({3x+1},{x^2+4x+8})})}", "4", "4", "8", "2", "5"),
]


@pytest.mark.parametrize(
    ("source", "derivative", "p", "q", "alpha", "second_coefficient"), SQUARE_CARDS
)
def test_complete_square_split_keeps_the_derivative_and_the_sign(
    source: str,
    derivative: str,
    p: str,
    q: str,
    alpha: str,
    second_coefficient: str | None,
) -> None:
    """½∫(2x + p)/Q dx + …: the ½ and 2x+p of «Разобьём числитель» are not lost."""
    card = first(source)
    split = _stage(card, "lesson_calc_int_sum_rule")
    right = split["right"]
    assert right["type"] in ("ADD", "SUBTRACT")
    first_piece, second_piece = right["children"]

    # ½|3/2 ∫(2x + p)/(x² + px + q) dx: page order, no ABS, no simplified ½ away.
    assert first_piece["type"] == "MULTIPLY_IMPLICIT"
    assert _numeric(first_piece["children"][0]) == ("1/2" if derivative == "2" else "3/2")
    integrand = _integral_of(first_piece)["children"][0]
    assert integrand["type"] == "FRACTION"
    numerator = integrand["children"][0]
    assert numerator["type"] == "ADD"
    assert numerator["children"][0]["type"] == "MULTIPLY_IMPLICIT"
    assert numerator["children"][0]["children"][0]["value"] == "2"
    assert numerator["children"][1]["value"] == derivative
    denominator = integrand["children"][1]
    power = _first_power(denominator)
    assert power["children"][0]["value"] == "x"
    assert power["children"][1]["value"] == "2"
    # x² + px + q in page order: no «5 + x² + 2x».
    assert denominator["type"] == "ADD"
    assert denominator["children"][1]["value"] == q
    inner = denominator["children"][0]
    assert inner["type"] == "ADD"
    assert inner["children"][0]["type"] == "POWER"
    linear = inner["children"][1]
    assert linear["type"] == "MULTIPLY_IMPLICIT"
    assert linear["children"][0]["value"] == p
    assert linear["children"][1]["value"] == "x"

    # ∫ dx/((x + α)² + β²): the completed square, not |Q|.
    integral = (
        _integral_of(second_piece)
        if second_piece["type"] in ("MULTIPLY", "MULTIPLY_IMPLICIT")
        else second_piece
    )
    if second_coefficient is not None:
        assert second_piece["children"][0]["value"] == second_coefficient
    body = integral["children"][0]
    assert body["type"] == "FRACTION" and body["children"][0]["value"] == "1"
    square = body["children"][1]
    power = _first_power(square)
    assert power["children"][0]["type"] == "ADD"
    assert power["children"][0]["children"][0]["value"] == "x"
    assert power["children"][0]["children"][1]["value"] == alpha
    assert any(node.get("value") == "4" for node in nodes_of(square))

    # No |·| anywhere in the stages of the card, except ln|·|.
    for sub in _all_substeps(card):
        for side in ("left", "right"):
            assert not _stray_abs(sub.get(side)), (side, sub["description"]["type"])
        for arg in sub["description"].get("args") or []:
            assert not _stray_abs(arg), ("arg", sub["description"]["type"])


@pytest.mark.parametrize(
    ("source", "polynomial"),
    [
        ("{integral({frac({x+2},{x^2+2x+5})})}", ("2", "2", "5")),
        ("{integral({frac({3x+1},{x^2+4x+8})})}", ("2", "4", "8")),
    ],
)
def test_complete_square_ln_stage_names_t_and_then_the_arctg(
    source: str, polynomial: tuple[str, str, str]
) -> None:
    card = first(source)
    keys = card_keys(card)
    ln_stage = _stage(card, "lesson_calc_int_frac_ln")
    assert "Замена" in ln_stage["explanation"]["text"]
    assert "числитель — производная знаменателя" in ln_stage["explanation"]["text"]
    args = ln_stage["description"]["args"]
    assert len(args) == 1
    equation = args[0]
    assert equation["type"] == "EQUALS"
    assert equation["children"][0] == {"type": "VARIABLE", "value": "t"}
    poly = equation["children"][1]
    power = _first_power(poly)
    assert power["children"][1]["value"] == polynomial[0]
    # The split stage hands over exactly what the ln stage starts from.
    split = _stage(card, "lesson_calc_int_sum_rule")
    assert CoreNode.from_contract(ln_stage["left"]).structural_eq(
        CoreNode.from_contract(split["right"])
    )
    # And the arctg stage follows.
    assert keys[keys.index("lesson_calc_int_frac_ln") + 1] == "lesson_calc_int_term_table"
    assert any(
        node["type"] == "ATAN"
        for node in nodes_of(_stage(card, "lesson_calc_int_term_table")["right"])
    )


@pytest.mark.parametrize(
    ("locale", "sum_text", "table_text"),
    [
        ("ru", "Линейность интеграла.", "Табличный интеграл."),
        ("en", "Linearity of the integral.", "Basic integral."),
    ],
)
def test_rule_chips_are_arg_free_and_short(locale: str, sum_text: str, table_text: str) -> None:
    linear = card_in(PROTO["ind10_linear"], locale)
    chip = _substep(linear, "lesson_calc_int_sum_rule")
    assert chip["description"].get("args") == []
    assert chip["explanation"]["text"] == sum_text

    table = card_in(PROTO["ind01_x3"], locale)
    chip = _substep(table, "lesson_calc_int_table_rule")
    assert chip["description"].get("args") == []
    assert chip["explanation"]["text"] == table_text


FRACTION_CARDS = [
    ("ind25_rat_a2", False),
    ("ind26_rat_xp3", False),
    ("ind27_rat_repeat", True),
]


@pytest.mark.parametrize(("task_id", "reordered"), FRACTION_CARDS)
def test_partial_fractions_keep_the_decomposition_order(task_id: str, reordered: bool) -> None:
    card = first(PROTO[task_id])
    form = _stage(card, "lesson_calc_int_frac_form")["left"]["children"][1]
    want = [_node_key(term["children"][1]) for term in _flat_chain(form)]

    split = _stage(card, "lesson_calc_int_sum_rule")["right"]
    got = [
        _node_key(_integral_of(term)["children"][0]["children"][1]) for term in _flat_chain(split)
    ]
    assert got == want, task_id

    keys = card_keys(card)
    # Only a real change (the double minus on the repeated root) keeps a reorder.
    assert ("lesson_calc_int_answer" in keys) is reordered, task_id
    term_tables = [key for key in keys if key == "lesson_calc_int_term_table"]
    assert len(term_tables) == len(want)


def test_parity_chip_only_names_the_check() -> None:
    odd = _substep(first(PROTO["def06_odd"]), "lesson_calc_int_parity_odd")
    assert odd["explanation"]["text"] == "Проверим нечётность функции."
    even = _substep(first(PROTO["def_even"]), "lesson_calc_int_parity_even")
    assert even["explanation"]["text"] == "Проверим чётность функции."


def test_definite_substitution_finds_the_primitive_then_substitutes() -> None:
    card = _lesson_card("{integral_def({0},{1},{x*exp({x^2})})}")
    keys = card_keys(card)
    primitive = _stage(card, "lesson_calc_int_newton_primitive")
    assert primitive["explanation"]["text"] == "Найдём первообразную."
    assert primitive["left"]["type"] == "MULTIPLY_IMPLICIT"
    assert primitive["left"]["children"][1]["type"] == "INTEGRAL_DEFINITE"
    assert primitive["right"]["type"] == "MULTIPLY_IMPLICIT"
    assert primitive["right"]["children"][1]["type"] == "INTEGRAL_RIGHT_DASH"

    bounds = _stage(card, "lesson_calc_int_newton_bounds")
    assert bounds["explanation"]["text"] == "Подставим пределы."
    assert CoreNode.from_contract(bounds["left"]).structural_eq(
        CoreNode.from_contract(primitive["right"])
    )
    # ½(e¹ − e⁰): the coefficient multiplies the whole difference.
    difference = bounds["right"]
    assert difference["type"] == "MULTIPLY_IMPLICIT"
    assert difference["children"][1]["type"] == "BRACKET"
    assert difference["children"][1]["children"][0]["type"] == "SUBTRACT"
    assert keys.index("lesson_calc_int_newton_primitive") < keys.index(
        "lesson_calc_int_newton_bounds"
    )
