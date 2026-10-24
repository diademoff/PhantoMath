"""Keys of the extrema/domain cards that our own cards emit.

Pins the keys of ``domain``, L'Hôpital and the chain/sum rows of the derivative card.
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


def _cards(proto: str, command: str | None = None) -> list[dict[str, Any]]:
    action = {"command": command, "args": []} if command else None
    data = service.solve_request(parse_protocol(proto).to_contract(), action, locale="ru")
    return data["result"]["groups"][0]["entries"]


def _key_entries(value: Any) -> list[tuple[str, int]]:
    """``(key, argument count)`` for every rich-text node, headers included."""
    if isinstance(value, dict):
        found: list[tuple[str, int]] = []
        if "args" in value and isinstance(value.get("type"), str) and "children" not in value:
            found.append((value["type"], len(value.get("args") or [])))
        for item in value.values():
            found.extend(_key_entries(item))
        return found
    if isinstance(value, list):
        result: list[tuple[str, int]] = []
        for item in value:
            result.extend(_key_entries(item))
        return result
    return []


def _card_keys(card: dict[str, Any]) -> list[tuple[str, int]]:
    return _key_entries(card["result"])


def _assert_key(card: dict[str, Any], key: str) -> None:
    entries = _card_keys(card)
    assert key in {name for name, _ in entries}, key
    declared = load_explanations(str(EXPLANATIONS)).arity(key)
    counts = {count for name, count in entries if name == key}
    assert counts == {declared}, f"{key}: {counts} != {declared}"


@pytest.mark.parametrize(
    ("proto", "key"),
    [
        ("{2x+3}", "domain_lin_real"),
        ("{x^2+1}", "domain_quad_real"),
        ("{x^3}", "domain_poly_real"),
        ("{x^2+1}", "domain_real"),
        ("{x^2+1}", "inflection_domain_find"),
        ("{x^2+1}", "extrema_domain_function"),
    ],
)
def test_domain_card_titles(proto: str, key: str) -> None:
    _assert_key(_cards(proto, "domain")[0], key)


def test_lhopital_card_names_the_two_child_limits() -> None:
    method = _cards("{lim({1},{(x^2-1)/(x-1)})}")[1]
    _assert_key(method, "limit_solve_pl_arg")


def test_chain_rule_card_names_the_rule() -> None:
    method = _cards("{derivation_diff({x},{sin({2x})})}")[-1]
    _assert_key(method, "derive_chain")


def test_sum_rule_card_takes_each_term() -> None:
    method = _cards("{derivation_diff({x},{3x^2+2x})}")[-1]
    _assert_key(method, "derive_each")


def test_keys_have_no_unrendered_placeholders() -> None:
    explanations = load_explanations(str(EXPLANATIONS))
    for key in (
        "domain_lin_real",
        "domain_quad_real",
        "domain_real",
        "inflection_domain_find",
        "extrema_domain_function",
        "limit_solve_pl_arg",
        "derive_chain",
        "derive_each",
    ):
        template = explanations.raw_template(key, DEFAULT_LOCALE) or ""
        used = {int(match) for match in re.findall(r"ARG(\d+)", template)}
        assert explanations.arity(key) == max(used, default=0), key
