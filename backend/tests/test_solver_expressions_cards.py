"""Bare expressions get factoring, expanding and cancelling cards."""

from __future__ import annotations

from mymath_backend.input import parse_protocol
from mymath_backend.service import solve_request


def _cards(source: str) -> list[list[str]]:
    result = solve_request(parse_protocol(source).to_contract(), locale="ru")["result"]
    return [
        [s["description"]["type"] for st in entry["result"]["steps"] for s in st["substeps"]]
        for group in result["groups"]
        for entry in group["entries"]
    ]


def test_brackets_expand_by_foil_and_by_the_distributive_property() -> None:
    cards = _cards("{(x+2)*(x-3)}")
    assert len(cards) == 2
    assert cards[0][0] == "mul_bracket_cross_each" and cards[1][0].startswith("mul_bracket_cross")


def test_difference_of_squares_is_factored_in_two_rows() -> None:
    assert ["write_as_num_arg", "using_factor"] in _cards("{x^2-9}")


def test_a_cancellable_fraction_has_a_simplify_and_an_excluded_values_card() -> None:
    cards = _cards("{frac({x^2-1},{x-1})}")
    assert cards[0] == ["using_factor", "frac_reduce_frac_alg"]
    assert cards[1][0] == "excluded_values_denom"


def test_a_square_of_a_sum_has_the_formula_and_the_product_cards() -> None:
    cards = _cards("{(x+3)^2}")
    assert cards[0][0] == "using_expand" and cards[1][0] == "write_as_product"


def test_a_square_of_a_sum_also_has_pascal_and_sigma_cards() -> None:
    cards = _cards("{(x+3)^2}")
    assert len(cards) == 4
    assert cards[2][0] == "expand_binomial_triangle" and cards[3] == ["expand_sigma"]


def test_a_square_of_a_difference_has_four_cards_ending_in_a_sum() -> None:
    cards = _cards("{(x-2)^2}")
    assert len(cards) == 4
    assert cards[0][0] == "using_expand" and cards[3] == ["sub_as_add", "expand_sigma"]


def test_like_terms_are_grouped_by_their_coefficients_then_added() -> None:
    assert _cards("{2x+3x}") == [["sum_suffix_add_detail", "add"]]


def test_sum_of_decimal_logs_joins_them_then_evaluates() -> None:
    assert _cards("{log10({2})+log10({5})}") == [["log_sum_resolve_plus", "log_same_base_arg"]]


def test_cube_of_x_plus_minus_one_has_five_cards_and_every_state_is_the_cube() -> None:
    import sympy

    from mymath_backend.solver.cube_cards import cube_methods
    from mymath_backend.solver.sympy_bridge import to_sympy

    x = sympy.Symbol("x")
    for source, sign in (("{(x+1)^3}", 1), ("{(x-1)^3}", -1)):
        cards = cube_methods(parse_protocol(source), "x")
        assert cards is not None and len(cards) == 5
        for card in cards:
            for step in card:
                for side in (step.left, step.right):
                    names = (
                        {n.value for n in side.walk() if n.type.value == "VARIABLE"}
                        if side
                        else set()
                    )
                    if side is None or names - {"x"}:
                        continue
                    if any(
                        n.type.value in ("CHOOSE_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT", "SIGMA_DEFINITE")
                        for n in side.walk()
                    ):
                        continue
                    assert sympy.expand(to_sympy(side) - (x + sign) ** 3) == 0, step.key


def test_derivative_of_a_power_times_a_factor_uses_the_power_rule_rows() -> None:
    assert _cards("{derivation_diff({x},{x^2})*sin({x})}") == [
        ["derive_table_desc", "sub", "pow_with_one"]
    ]


def test_sigma_card_carries_the_rewrite_using_sigma_header() -> None:
    result = solve_request(parse_protocol("{(x+3)^2}").to_contract(), locale="ru")["result"]
    headers = [
        (entry["result"].get("header") or {}).get("type")
        for group in result["groups"]
        for entry in group["entries"]
    ]
    assert "rewrite_using_sigma" in headers
