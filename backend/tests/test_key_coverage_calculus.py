"""Card-title keys of derivatives and limits.

Some explanation keys sit on the card itself (``derive_evaluate``,
``evaluate_using_lhopital``, …) rather than on a substep. This module checks that our
derivative/limit cards carry those keys without changing the substep rows asserted in
``test_step_depth_calculus``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from mymath_backend import load_explanations, service
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.input import parse_protocol

EXPLANATIONS = Path(__file__).resolve().parents[1] / "mymath_backend" / "data" / "explanations.json"


def _cards(proto: str) -> list[dict[str, Any]]:
    data = service.solve_request(parse_protocol(proto).to_contract(), locale="ru")
    return data["result"]["groups"][0]["entries"]


def _rich_text_keys(value: Any) -> set[str]:
    """Every ``CoreRichText`` key in a contract subtree (headers included)."""
    if isinstance(value, dict):
        found: set[str] = set()
        if "args" in value and isinstance(value.get("type"), str) and "children" not in value:
            found.add(value["type"])
        for item in value.values():
            found |= _rich_text_keys(item)
        return found
    if isinstance(value, list):
        result: set[str] = set()
        for item in value:
            result |= _rich_text_keys(item)
        return result
    return set()


def _card_keys(card: dict[str, Any]) -> set[str]:
    return _rich_text_keys(card["result"])


# (вход, индекс способа, ключ заголовка карточки)
CARD_TITLES: list[tuple[str, int, str]] = [
    ("{derivation_prime({cos({x})})}", -1, "derive_evaluate"),
    ("{derivation_prime({x^3})}", -1, "derive_evaluate"),
    ("{derivation_prime({abs({x})})}", -1, "derive_evaluate"),
    ("{derivation2_prime({x^3})}", -1, "derive_evaluate_higher_order"),
    ("{lim_left({0},{1/x})}", 0, "evaluate_of_common_function"),
    ("{lim_right({0},{1/x})}", 0, "evaluate_of_common_function"),
    ("{lim_right({0},{ln({x})})}", 0, "evaluate_of_common_function"),
    ("{lim({0},{sin({x})/x})}", 0, "evaluate_of_common_function"),
    ("{lim({0},{sin({x})/x})}", 1, "evaluate_using_lhopital"),
    ("{lim({1},{(x^2-1)/(x-1)})}", 0, "evaluate_using_transformations"),
    ("{lim({1},{(x^2-1)/(x-1)})}", 1, "evaluate_using_lhopital"),
    ("{lim({infty},{(2x+1)/(x-3)})}", 0, "evaluate_using_transformations"),
    ("{lim({infty},{(2x+1)/(x-3)})}", 0, "limit_poly_msg"),
    ("{lim({infty},{(2x+1)/(x-3)})}", 1, "evaluate_using_lhopital"),
    ("{lim({0},{tan({x})/x})}", 0, "evaluate_using_transformations"),
    ("{lim({0},{tan({x})/x})}", 1, "evaluate_using_lhopital"),
    ("{lim({3},{2x+1})}", 0, "limit_solve_const_msg"),
]


@pytest.mark.parametrize(
    ("proto", "method", "key"),
    CARD_TITLES,
    ids=[f"{case[0]}-{case[1]}-{case[2]}" for case in CARD_TITLES],
)
def test_card_carries_title(proto: str, method: int, key: str) -> None:
    cards = _cards(proto)
    card = cards[method]
    assert key in _card_keys(card), f"{proto}: {key}"


def test_every_title_exists_with_zero_arity() -> None:
    explanations = load_explanations(str(EXPLANATIONS))
    keys = {case[2] for case in CARD_TITLES}
    for key in keys:
        assert key in explanations, key
        assert explanations.arity(key) == 0, key
        template = explanations.raw_template(key, DEFAULT_LOCALE) or ""
        assert not re.search(r"ARG\d", template), key
