"""Student-visible limit cards (CALC1).

The first card for a limit is the textbook method, named and with its formula:
factor and cancel for ``0/0``, division by the highest power for ``∞/∞``, the
first/second remarkable limits, the conjugate of a root difference, the sign of
a one-sided limit, or the reason the limit does not exist.  L'Hôpital is always
an alternative card, never the first one when a textbook method applies.

Every answer is checked against ``sympy.limit`` (with ``dir`` for one-sided
limits); every card is checked for its header key, the named uncertainty, and
Russian text without raw node names or missing explanation keys.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pytest
import sympy
from test_student_matrices import response, texts

from mymath_backend import CoreNode
from mymath_backend.input import parse_protocol
from mymath_backend.node_types import CoreNodeType as T
from mymath_backend.solver.sympy_bridge import to_sympy

PROTO = {
    # Sample protocols, kept here so the tests do not
    # depend on the git-ignored build/ tree.
    "l01_inf_deg_lt": "{lim({inf},{frac({x+1},{x^2+1})})}",
    "l02_inf_deg_eq": "{lim({inf},{frac({2x^2+3x},{x^2-1})})}",
    "l03_inf_deg_gt": "{lim({inf},{frac({x^3+2x},{x^2+1})})}",
    "l04_00_cancel": "{lim({2},{frac({x^2-4},{x-2})})}",
    "l05_00_cancel_quad": "{lim({1},{frac({x^2-1},{x^2-3x+2})})}",
    "l06_00_cancel_cube": "{lim({1},{frac({x^3-1},{x-1})})}",
    "l07_conjugate_zero": "{lim({0},{frac({root2({x+1})-1},{x})})}",
    "l08_conjugate_inf": "{lim({inf},{root2({x^2+x})-x})}",
    "l09_sin3x": "{lim({0},{frac({sin({3x})},{x})})}",
    "l10_tgx": "{lim({0},{frac({tan({x})},{x})})}",
    "l11_one_minus_cos": "{lim({0},{frac({1-cos({x})},{x^2})})}",
    "l12_second_remarkable": "{lim({inf},{(1+frac({1},{x}))^x})}",
    "l13_second_remarkable_scaled": "{lim({inf},{(1+frac({2},{x}))^(3x)})}",
    "l14_second_remarkable_zero": "{lim({0},{(1+x)^frac({1},{x})})}",
    "l15_ln_one_plus_x": "{lim({0},{frac({ln({1+x})},{x})})}",
    "l16_exp_minus_one": "{lim({0},{frac({\\e^x-1},{x})})}",
    "l17_one_sided_right": "{lim_right({0},{frac({1},{x})})}",
    "l18_one_sided_left": "{lim_left({0},{frac({1},{x})})}",
    "l19_abs_right": "{lim_right({0},{frac({abs({x})},{x})})}",
    "l20_abs_two_sided": "{lim({0},{frac({abs({x})},{x})})}",
    "l21_inf_minus_inf": "{lim({inf},{root2({x^2+x})-x})}",
    "l22_sequence_ratio": "{lim({inf},{frac({n+1},{n})})}",
    "l23_sequence_root": "{lim({inf},{root({n},{n})})}",
    "l25_dne_oscillation": "{lim({0},{sin({frac({1},{x})})})}",
    "l26_dne_infinity": "{lim({inf},{sin({x})})}",
}

_RAW_NODE = re.compile(r"\b[A-Z][A-Z_0-9]{2,}\(")
_PLACEHOLDER = re.compile(r"\?\?\s*step_|ARG\d|\bNone\b")


def proto(task_id: str) -> str:
    return PROTO[task_id]


def cards(source: str) -> list[dict[str, Any]]:
    """Method cards of the vertical group, in the order the student sees them."""
    return response(source)["result"]["groups"][0]["entries"]


def first(source: str) -> dict[str, Any]:
    return cards(source)[0]


def header_key(card: dict[str, Any]) -> str:
    return card["result"]["header"]["type"]


def header_text(card: dict[str, Any]) -> str:
    return card["result"]["header"]["explanation"]["text"]


def substep_keys(value: Any) -> list[str]:
    """Every substep key of a contract tree, nested screens included."""
    if isinstance(value, dict):
        found = []
        if isinstance(value.get("description"), dict):
            found.append(value["description"]["type"])
        for child in value.values():
            found.extend(substep_keys(child))
        return found
    if isinstance(value, list):
        return [key for child in value for key in substep_keys(child)]
    return []


def card_keys(card: dict[str, Any]) -> list[str]:
    return substep_keys(card["result"])


def uncertainty(card: dict[str, Any]) -> str:
    """The visible text of the first substep (where the uncertainty is named)."""
    return card["result"]["steps"][0]["substeps"][0]["explanation"]["text"]


def answer(source: str) -> sympy.Expr:
    solution = first(source)["result"]["solutionNode"]
    return to_sympy(CoreNode.from_contract(solution))


def has_solution(source: str) -> bool:
    return bool(first(source)["result"].get("solutionNode"))


def expected(source: str) -> sympy.Expr:
    """Independent value from the same protocol node through sympy."""
    node = parse_protocol(source)
    point = to_sympy(node.children[0])
    expression = to_sympy(node.children[1])
    symbols = sorted(expression.free_symbols, key=str)
    symbol = symbols[0] if symbols else sympy.Symbol("x")
    if node.type is T.LIMIT_LEFT:
        return sympy.limit(expression, symbol, point, "-")
    if node.type is T.LIMIT_RIGHT:
        return sympy.limit(expression, symbol, point, "+")
    return sympy.limit(expression, symbol, point)


def _walk_nodes(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        if "type" in value and value["type"].isupper():
            yield value
        for child in value.values():
            yield from _walk_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_nodes(child)


def assert_answer(source: str) -> None:
    assert has_solution(source)
    ours, want = answer(source), expected(source)
    if ours in (sympy.oo, -sympy.oo) or want in (sympy.oo, -sympy.oo):
        assert ours == want
    else:
        assert sympy.simplify(ours - want) == 0


# ── 2. 0/0 rational: factor and cancel ────────────────────────────────


@pytest.mark.parametrize("task_id", ["l04_00_cancel", "l05_00_cancel_quad", "l06_00_cancel_cube"])
def test_zero_over_zero_rational_is_factored_before_lhopital(task_id: str) -> None:
    source = proto(task_id)
    result = cards(source)
    card = result[0]
    assert header_key(card) == "lesson_calc_header_factor"
    assert "0/0" in header_text(card)
    keys = card_keys(card)
    assert "lesson_calc_uncertainty_00" in keys
    assert "0/0" in uncertainty(card)
    assert "lesson_calc_factor" in keys
    assert "lesson_calc_cancel_factor" in keys
    assert "lesson_calc_substitute" in keys
    assert_answer(source)
    # L'Hôpital stays, but only as the alternative card.
    assert len(result) == 2
    assert header_key(result[1]) == "limit_lhopital_msg"
    assert "limit_lhopital_long" in card_keys(result[1])
    assert "\u2260" in next(text for text in texts(response(source)) if "Сократим" in text)


# ── 3. ∞/∞ rational and sequences in n ────────────────────────────────


@pytest.mark.parametrize(
    ("task_id", "degree_key"),
    [
        ("l01_inf_deg_lt", "lesson_calc_inf_deg_lt"),
        ("l02_inf_deg_eq", "lesson_calc_inf_deg_eq"),
        ("l03_inf_deg_gt", "lesson_calc_inf_deg_gt"),
        ("l22_sequence_ratio", "lesson_calc_inf_deg_eq"),
    ],
)
def test_infinity_over_infinity_divides_by_the_highest_power(task_id: str, degree_key: str) -> None:
    source = proto(task_id)
    card = first(source)
    assert header_key(card) == "lesson_calc_header_inf"
    assert "\u221e/\u221e" in header_text(card)
    keys = card_keys(card)
    assert "lesson_calc_uncertainty_inf" in keys
    assert "\u221e/\u221e" in uncertainty(card)
    assert "lesson_calc_divide_highest" in keys
    assert degree_key in keys
    assert_answer(source)


def test_sequence_in_n_has_no_lhopital_alternative() -> None:
    result = cards(proto("l22_sequence_ratio"))
    assert len(result) == 1
    assert header_key(result[0]) == "lesson_calc_header_inf"


def test_nth_root_sequence_is_shown_through_the_exponential() -> None:
    source = proto("l23_sequence_root")
    card = first(source)
    assert header_key(card) == "lesson_calc_header_sequence_root"
    keys = card_keys(card)
    assert "lesson_calc_uncertainty_inf_0" in keys
    assert "lesson_calc_sequence_root" in keys
    assert "lesson_calc_log_over_n" in keys
    assert_answer(source)


# ── 4. first remarkable limit and equivalents ─────────────────────────


@pytest.mark.parametrize(
    "task_id",
    [
        "l09_sin3x",
        "l10_tgx",
        "l15_ln_one_plus_x",
        "l16_exp_minus_one",
    ],
)
def test_first_remarkable_limit_is_named_first(task_id: str) -> None:
    source = proto(task_id)
    result = cards(source)
    card = result[0]
    assert header_key(card) == "lesson_calc_header_remarkable"
    keys = card_keys(card)
    assert "lesson_calc_uncertainty_00" in keys
    assert {"lesson_calc_first_remarkable", "lesson_calc_equivalents"} & set(keys)
    assert "limit_change_var" in keys
    assert_answer(source)
    assert len(result) == 2
    assert header_key(result[1]) == "limit_lhopital_msg"


def test_one_minus_cos_uses_equivalents_instead_of_an_empty_substitution() -> None:
    """(1 − cos x)/x² goes through 1 − cos u ~ u²/2, not through a no-op.

    Раньше первый замечательный предел давал этап «замена переменной», где
    слева и справа стояла одна и та же дробь: студент не видел, что изменилось.
    """
    source = proto("l11_one_minus_cos")
    card = first(source)
    assert header_key(card) == "lesson_calc_header_equivalents"
    keys = card_keys(card)
    assert "lesson_calc_equivalents_replace" in keys
    for step in card["result"]["steps"]:
        for sub in step["substeps"]:
            if sub["description"]["type"] == "limit_change_var":
                assert sub.get("left") != sub.get("right")
    assert answer(source) == sympy.Rational(1, 2)


def test_abs_over_x_opens_the_module_before_the_side_value() -> None:
    """The student first sees |x| = x (or −x), then the side limit.

    Порядок этапов раньше был обратным: готовое значение появлялось до того,
    как раскрыт модуль.
    """
    card = first(proto("l19_abs_right"))
    keys = card_keys(card)
    assert keys.index("lesson_calc_abs_right") < keys.index("limit_common_right")
    left = first("{lim_left({0},{frac({abs({x})},{x})})}")
    left_keys = card_keys(left)
    assert left_keys.index("lesson_calc_abs_left") < left_keys.index("limit_common_left")


def test_sin_3x_names_the_law_and_substitutes_3x() -> None:
    source = proto("l09_sin3x")
    card = first(source)
    assert any("Первый замечательный предел" in text for text in texts(response(source)))
    law_step = next(
        sub
        for step in card["result"]["steps"]
        for sub in step["substeps"]
        if sub["description"]["type"] == "lesson_calc_first_remarkable"
    )
    # The student sees the law as a math node: lim_{u→0} sin u / u = 1.
    math_parts = [
        part["node"] for part in law_step["explanation"]["parts"] if part.get("node") is not None
    ]
    assert any(node["type"] == "SIN" for node in _walk_nodes(math_parts))
    assert any(node["type"] == "LIMIT" for node in _walk_nodes(math_parts))
    assert answer(source) == 3


# ── 5. roots and the conjugate ────────────────────────────────────────


@pytest.mark.parametrize(
    "task_id", ["l07_conjugate_zero", "l08_conjugate_inf", "l21_inf_minus_inf"]
)
def test_root_difference_is_multiplied_by_the_conjugate(task_id: str) -> None:
    source = proto(task_id)
    card = first(source)
    assert header_key(card) == "lesson_calc_header_conjugate"
    keys = card_keys(card)
    assert "lesson_calc_conjugate_multiply" in keys
    assert "lesson_calc_conjugate_simplify" in keys
    assert "lesson_calc_uncertainty_00" in keys or "lesson_calc_uncertainty_inf_minus_inf" in keys
    text = uncertainty(card)
    assert "0/0" in text or "\u221e \u2212 \u221e" in text
    assert_answer(source)


def test_conjugate_card_shows_the_multiplication() -> None:
    card = first(proto("l07_conjugate_zero"))
    substeps = [sub for step in card["result"]["steps"] for sub in step["substeps"]]
    multiply = next(
        s for s in substeps if s["description"]["type"] == "lesson_calc_conjugate_multiply"
    )
    assert multiply.get("right") is not None
    assert multiply["right"]["type"] == "FRACTION"


# ── 6. second remarkable limit: 1^∞ ──────────────────────────────────


@pytest.mark.parametrize(
    "task_id",
    ["l12_second_remarkable", "l13_second_remarkable_scaled", "l14_second_remarkable_zero"],
)
def test_one_to_infinity_is_reduced_to_the_second_remarkable_limit(task_id: str) -> None:
    source = proto(task_id)
    card = first(source)
    assert header_key(card) == "lesson_calc_header_second_remarkable"
    keys = card_keys(card)
    assert "lesson_calc_uncertainty_1_inf" in keys
    assert "1^\u221e" in uncertainty(card)
    assert "lesson_calc_second_remarkable" in keys
    assert "limit_change_var" in keys
    assert_answer(source)


def test_scaled_second_remarkable_shows_the_power_six() -> None:
    source = proto("l13_second_remarkable_scaled")
    assert answer(source) == sympy.exp(6)
    assert any("e^6" in text for text in texts(response(source)))


# ── 7. one-sided limits ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("source", "side_key", "sign_key"),
    [
        (proto("l17_one_sided_right"), "limit_common_right", "lesson_calc_one_sided_sign_right"),
        (proto("l18_one_sided_left"), "limit_common_left", "lesson_calc_one_sided_sign_left"),
    ],
)
def test_one_sided_infinity_names_the_side_and_the_sign(
    source: str, side_key: str, sign_key: str
) -> None:
    card = first(source)
    assert header_key(card) == "lesson_calc_header_one_sided"
    keys = card_keys(card)
    assert side_key in keys
    assert sign_key in keys
    assert "lesson_calc_limit_result" in keys
    assert_answer(source)


def test_abs_over_x_opens_the_absolute_value_by_side() -> None:
    right = first(proto("l19_abs_right"))
    left = first("{lim_left({0},{frac({abs({x})},{x})})}")
    assert header_key(right) == "lesson_calc_header_one_sided"
    assert "lesson_calc_abs_right" in card_keys(right)
    assert "lesson_calc_abs_left" in card_keys(left)
    assert answer(proto("l19_abs_right")) == 1
    assert answer("{lim_left({0},{frac({abs({x})},{x})})}") == -1


def test_abs_over_x_never_uses_lhopital() -> None:
    # |x| is not differentiable at 0: no L'Hôpital card may claim otherwise.
    assert len(cards(proto("l19_abs_right"))) == 1
    assert "limit_lhopital_long" not in card_keys(first(proto("l19_abs_right")))


# ── 8. limits that do not exist ───────────────────────────────────────


@pytest.mark.parametrize(
    "source",
    [
        proto("l20_abs_two_sided"),
        proto("l25_dne_oscillation"),
        proto("l26_dne_infinity"),
        "{lim({0},{frac({1},{x})})}",
    ],
)
def test_nonexistent_limit_is_a_verdict_not_an_error(source: str) -> None:
    result = cards(source)  # no HTTP 422 / SolveError
    card = result[0]
    assert header_key(card) == "lesson_calc_header_dne"
    assert not has_solution(source)
    keys = card_keys(card)
    assert "limit_does_not_exist_msg" in keys
    assert any("Предел не существует" in text for text in texts(response(source)))


def test_two_sided_sign_jump_shows_both_one_sided_values() -> None:
    source = proto("l20_abs_two_sided")
    card = first(source)
    keys = card_keys(card)
    assert "limit_common_left" in keys and "limit_common_right" in keys
    assert "limit_does_not_exist" in keys
    texts_ = list(texts(response(source)))
    assert any("не существует" in text for text in texts_)


def test_oscillation_names_the_reason() -> None:
    card = first(proto("l25_dne_oscillation"))
    assert "lesson_calc_limit_oscillation" in card_keys(card)


# ── text and structure hygiene ────────────────────────────────────────


@pytest.mark.parametrize(
    "task_id",
    [
        "l04_00_cancel",
        "l02_inf_deg_eq",
        "l09_sin3x",
        "l07_conjugate_zero",
        "l13_second_remarkable_scaled",
        "l17_one_sided_right",
        "l19_abs_right",
        "l20_abs_two_sided",
    ],
)
def test_limit_cards_are_russian_and_complete(task_id: str) -> None:
    source = proto(task_id)
    for text in texts(response(source)):
        assert not _RAW_NODE.search(text), text
        assert not _PLACEHOLDER.search(text), text
        if text and not re.search(r"[а-яА-Я]", text):
            # formulas and the digamma-free maths are allowed, English prose is not
            assert not re.search(r"\b(the|this|use|find|since|evaluate)\b", text, re.I), text
    card = first(source)
    assert card["result"]["header"]["explanation"]["missing"] is False
    assert card["result"]["header"]["explanation"]["theory"] is not None


# ── CALC2: derivatives the textbook way ───────────────────────────────

DERIV = {
    "sum": "{derivation_diff({x},{x^3+2x^2-5x+1})}",
    "product": "{derivation_diff({x},{x*sin({x})})}",
    "quotient": "{derivation_diff({x},{frac({x^2+1},{x-1})})}",
    "sin_square": "{derivation_diff({x},{sin({x^2})})}",
    "exp_square": "{derivation_diff({x},{\\e^(-x^2)})}",
    "log_cos": "{derivation_diff({x},{ln({cos({x})})})}",
    "power_chain": "{derivation_diff({x},{(3x+1)^5})}",
    "root_chain": "{derivation_diff({x},{root2({1-x^2})})}",
    "logarithmic": "{derivation_diff({x},{x^x})}",
    "second": "{derivation2_prime({x^3-2x})}",
    "second_nested": "{derivation_prime({derivation_prime({x^3-2x})})}",
}


def _textbook(card: dict[str, Any]) -> dict[str, Any]:
    """The textbook card of an entry list (the last one: the app's card stays first)."""
    return next(
        entry
        for entry in card
        if (entry["result"].get("header") or {}).get("type", "").startswith("lesson_calc_")
    )


def _header(card: dict[str, Any]) -> str:
    return (card["result"].get("header") or {}).get("type", "")


def assert_derivative_answer(source: str) -> None:
    """Compare the textbook card's answer with ``sympy.diff`` of the same input."""
    node = parse_protocol(source)
    table = {
        T.DERIVATION1_DIFF: 1,
        T.DERIVATION1: 1,
        T.DERIVATION1_PRIME: 1,
        T.PRIME: 1,
        T.DERIVATION2_PRIME: 2,
    }
    order = table[node.type]
    if node.type is T.DERIVATION1_DIFF:
        symbol = sympy.Symbol(node.children[0].value or "x")
        expression = to_sympy(node.children[1])
    else:
        expression = to_sympy(node.children[0])
        symbols = sorted(expression.free_symbols, key=str)
        symbol = symbols[0] if symbols else sympy.Symbol("x")
    want = sympy.diff(expression, symbol, order)
    ours = _card_solution(_textbook(cards(source)))
    assert sympy.simplify(ours - want) == 0


def _where(card: dict[str, Any]) -> sympy.Expr | None:
    """The ``u = …`` node of the chain-rule stage, evaluated independently."""
    for step in card["result"]["steps"]:
        for sub in step["substeps"]:
            if sub["description"]["type"] != "lesson_calc_rule_chain":
                continue
            for part in sub["explanation"]["parts"]:
                node = part.get("node")
                if not node or node["type"] != "EQUALS":
                    continue
                left = node["children"][0]
                if left.get("type") == "VARIABLE" and left.get("value") == "u":
                    return to_sympy(CoreNode.from_contract(node["children"][1]))
    return None


def _solution(source: str) -> sympy.Expr:
    return answer(source)


def _card_solution(card: dict[str, Any]) -> sympy.Expr:
    return to_sympy(CoreNode.from_contract(card["result"]["solutionNode"]))


# 1. one path for both derivative inputs


@pytest.mark.parametrize(
    ("phone", "protocol"),
    [
        ("{derivation_prime({sin({x^2})})}", DERIV["sin_square"]),
        ("{derivation_prime({x*sin({x})})}", DERIV["product"]),
        ("{derivation_prime({frac({x^2+1},{x-1})})}", DERIV["quotient"]),
    ],
)
def test_phone_and_protocol_share_the_textbook_card(phone: str, protocol: str) -> None:
    ours = _textbook(cards(phone))
    theirs = _textbook(cards(protocol))
    assert _header(ours) == _header(theirs)
    assert card_keys(ours) == card_keys(theirs)
    assert sympy.simplify(_card_solution(ours) - _card_solution(theirs)) == 0


def test_phone_sees_the_textbook_card_first() -> None:
    phone = cards("{derivation_prime({x*sin({x})})}")
    assert _header(phone[0]) == "lesson_calc_header_deriv_product"


def test_protocol_keeps_the_card_as_an_alternative() -> None:
    # the verified derivation_diff structure
    # against our alternative card, which now carries its own title.
    protocol = cards(DERIV["product"])
    assert _header(protocol[0]) == "lesson_calc_header_deriv_product"
    assert any(_header(card) == "derive_evaluate" for card in protocol[1:])


# 2. named rules with formulas, one rule per stage


@pytest.mark.parametrize(
    ("source", "header", "rule_key", "part_keys"),
    [
        (
            DERIV["product"],
            "lesson_calc_header_deriv_product",
            "lesson_calc_rule_product",
            ["lesson_calc_part_first", "lesson_calc_part_second"],
        ),
        (
            DERIV["quotient"],
            "lesson_calc_header_deriv_quotient",
            "lesson_calc_rule_quotient",
            ["lesson_calc_part_numerator", "lesson_calc_part_denominator"],
        ),
        (
            DERIV["sum"],
            "lesson_calc_header_deriv_sum",
            "lesson_calc_rule_sum",
            ["lesson_calc_part_first", "lesson_calc_part_second"],
        ),
    ],
)
def test_rule_card_names_each_stage_and_opens_each_part(
    source: str, header: str, rule_key: str, part_keys: list[str]
) -> None:
    card = _textbook(cards(source))
    assert _header(card) == header
    keys = card_keys(card)
    assert rule_key in keys
    assert keys[-2:] == ["lesson_calc_compose_derivatives", "lesson_calc_simplify_result"]
    rule = next(
        sub
        for step in card["result"]["steps"]
        for sub in step["substeps"]
        if sub["description"]["type"] == rule_key
    )
    # The rule is shown with its formula as a math node, not only as prose.
    assert any(
        part.get("node", {}).get("type") == "EQUALS" for part in rule["explanation"]["parts"]
    )
    parts = [
        sub
        for step in card["result"]["steps"]
        for sub in step["substeps"]
        if sub["description"]["type"] in part_keys
    ]
    assert len(parts) == len(part_keys)
    assert all(part.get("subresult") for part in parts), "каждая часть раскрывается"
    assert_derivative_answer(source)


def test_power_and_table_cards_quote_their_table_formula() -> None:
    power = _textbook(cards("{derivation_diff({x},{x^5})}"))
    assert _header(power) == "lesson_calc_header_deriv_power"
    assert "lesson_calc_rule_power" in card_keys(power)
    sine = _textbook(cards("{derivation_diff({x},{sin({x})})}"))
    assert _header(sine) == "lesson_calc_header_deriv_table"
    assert "lesson_calc_rule_table" in card_keys(sine)
    law = next(
        sub
        for step in sine["result"]["steps"]
        for sub in step["substeps"]
        if sub["description"]["type"] == "lesson_calc_rule_table"
    )
    nodes = [part["node"] for part in law["explanation"]["parts"] if part.get("node")]
    assert any(node["type"] == "EQUALS" for node in nodes)
    assert any(node["type"] == "SIN" for node in _walk_nodes(nodes))
    assert any(node["type"] == "COS" for node in _walk_nodes(nodes))
    constant = _textbook(cards("{derivation_diff({x},{2x})}"))
    assert _header(constant) == "lesson_calc_header_deriv_constant_factor"
    assert "lesson_calc_rule_constant_factor" in card_keys(constant)
    reciprocal = _textbook(cards("{derivation_diff({x},{frac({1},{x})})}"))
    assert _header(reciprocal) == "lesson_calc_header_deriv_power"
    assert "lesson_calc_rule_reciprocal" in card_keys(reciprocal)
    root = _textbook(cards("{derivation_diff({x},{root2({x})})}"))
    assert "lesson_calc_rule_sqrt" in card_keys(root)


# 3. the chain rule, with u = g(x) named


@pytest.mark.parametrize(
    ("source", "inner"),
    [
        (DERIV["sin_square"], sympy.Symbol("x") ** 2),
        (DERIV["exp_square"], -(sympy.Symbol("x") ** 2)),
        (DERIV["log_cos"], sympy.cos(sympy.Symbol("x"))),
        (DERIV["power_chain"], 3 * sympy.Symbol("x") + 1),
        (DERIV["root_chain"], 1 - sympy.Symbol("x") ** 2),
    ],
)
def test_chain_rule_names_the_inner_function(source: str, inner: sympy.Expr) -> None:
    card = _textbook(cards(source))
    assert _header(card) == "lesson_calc_header_deriv_chain"
    assert _where(card) == inner
    assert "lesson_calc_part_argument" in card_keys(card)
    assert_derivative_answer(source)


# 4. x^x by logarithmic differentiation


def test_x_to_the_x_is_logarithmic_differentiation() -> None:
    card = _textbook(cards(DERIV["logarithmic"]))
    assert _header(card) == "lesson_calc_header_deriv_log"
    keys = card_keys(card)
    assert "lesson_calc_log_take" in keys
    assert "lesson_calc_log_differentiate" in keys
    assert "lesson_calc_log_solve" in keys
    x = sympy.Symbol("x")
    assert sympy.simplify(_card_solution(card) - x**x * (sympy.log(x) + 1)) == 0
    assert any("ln" in text for text in texts(response(DERIV["logarithmic"])))


# 5. the second derivative is (f′)′


@pytest.mark.parametrize("source", [DERIV["second"], DERIV["second_nested"]])
def test_second_derivative_shows_the_first_one(source: str) -> None:
    card = _textbook(cards(source))
    assert _header(card) == "lesson_calc_header_deriv_second"
    keys = card_keys(card)
    assert "lesson_calc_second_first" in keys
    assert "lesson_calc_second_again" in keys
    first = next(
        sub
        for step in card["result"]["steps"]
        for sub in step["substeps"]
        if sub["description"]["type"] == "lesson_calc_second_first"
    )
    assert first["subresult"] is not None
    nested = [
        sub["description"]["type"]
        for step in first["subresult"]["steps"]
        for sub in step["substeps"]
    ]
    assert "lesson_calc_rule_sum" in nested or "lesson_calc_rule_difference" in nested
    x = sympy.Symbol("x")
    assert sympy.simplify(_card_solution(card) - sympy.diff(x**3 - 2 * x, x, 2)) == 0


# 6. the final answer is simplified as the last stage


def test_quotient_answer_is_simplified_and_named_as_a_stage() -> None:
    source = DERIV["quotient"]
    card = _textbook(cards(source))
    assert "lesson_calc_simplify_result" in card_keys(card)
    x = sympy.Symbol("x")
    assert sympy.simplify(_card_solution(card) - (x**2 - 2 * x - 1) / (x - 1) ** 2) == 0
    assert sympy.simplify(_card_solution(card) - sympy.diff((x**2 + 1) / (x - 1), x)) == 0


# 7. the card header names the method


@pytest.mark.parametrize(
    ("source", "header"),
    [
        (DERIV["sum"], "lesson_calc_header_deriv_sum"),
        (DERIV["product"], "lesson_calc_header_deriv_product"),
        (DERIV["quotient"], "lesson_calc_header_deriv_quotient"),
        (DERIV["sin_square"], "lesson_calc_header_deriv_chain"),
        (DERIV["logarithmic"], "lesson_calc_header_deriv_log"),
        (DERIV["second"], "lesson_calc_header_deriv_second"),
    ],
)
def test_card_header_names_the_method(source: str, header: str) -> None:
    card = _textbook(cards(source))
    assert _header(card) == header
    assert card["result"]["header"]["explanation"]["text"]
    assert card["result"]["header"]["explanation"]["theory"] is not None


# 8. the plain-text fallback keeps the whole node


def test_text_fallback_keeps_the_whole_function() -> None:
    from mymath_backend.explanations import _default_render_arg

    x = CoreNode.variable("x")
    log_cos = CoreNode.node(T.LN, CoreNode.node(T.COS, x))
    assert _default_render_arg(log_cos) == "ln(cos(x))"
    exponent = CoreNode.node(T.NEGATIVE, CoreNode.node(T.POWER, x, CoreNode.constant("2")))
    power = CoreNode.node(T.POWER, CoreNode.constant("e"), exponent)
    assert _default_render_arg(power) != "e"


def test_chain_text_names_the_inner_function() -> None:
    # The old the app card is still reachable; its text must not say «cos(x)» → «x».
    legacy_text = [
        text
        for text in texts(response("{derivation_prime({ln({cos({x})})})}"))
        if "сложной функции" in text
    ]
    assert legacy_text
    assert any("cos(x)" in text for text in legacy_text)


# ── limits: equivalents in numerator and denominator ──────────────────


@pytest.mark.parametrize(
    ("source", "want"),
    [
        ("{lim({0},{frac({tan({2x})},{sin({5x})})})}", sympy.Rational(2, 5)),
        ("{lim({0},{frac({sin({x})},{2x})})}", sympy.Rational(1, 2)),
        ("{lim({0},{frac({x},{sin({x})})})}", 1),
        ("{lim({0},{frac({sin({x^2})},{x})})}", 0),
        ("{lim({0},{frac({\\e^(2x)-1},{x})})}", 2),
    ],
)
def test_equivalents_replace_both_numerator_and_denominator(source: str, want: sympy.Expr) -> None:
    result = cards(source)
    card = result[0]
    keys = card_keys(card)
    if _header(card) == "lesson_calc_header_equivalents":
        assert "lesson_calc_equivalents" in keys
        assert "lesson_calc_equivalents_replace" in keys
        assert "lesson_calc_limit_result" in keys
    # else the first-remarkable card already replaced the equivalent.
    assert not any("limit_lhopital" in key for key in keys), "Лопиталь не первый"
    assert has_solution(source)
    assert sympy.simplify(answer(source) - want) == 0
    assert result[0]["result"]["header"]["explanation"]["text"]
