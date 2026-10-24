"""Ключи карточек команд fraction/partial/matrix."""

from __future__ import annotations

from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult, ResultGroupType
from mymath_backend.solver import solve


def _vertical(source: str, command: str, args: list[str] | None = None) -> CoreSolverVerticalResult:
    vertical = solve(
        parse_protocol(source),
        command=command,
        args=[parse_protocol(arg) for arg in args or []],
    ).result.vertical()
    assert vertical is not None
    return vertical


def _keys(vertical: CoreSolverVerticalResult) -> set[str]:
    found: set[str] = set()
    for step in vertical.steps:
        found.update(header.type for header in step.step_headers)
        for sub in step.substeps:
            assert sub.description is not None
            found.add(sub.description.type)
            if sub.subresult is not None:
                found.update(_keys(sub.subresult))
    return found


def test_approximate_fraction_has_the_decimal_card() -> None:
    found = _keys(_vertical("{frac({1},{3})}", "approximate", ["{3}"]))
    assert {"frac_to_dec", "round3"} <= found


def test_mixed_number_conversion_cards() -> None:
    found = _keys(_vertical("{frac({7},{3})}", "to_mixed"))
    assert {"frac_to_dec", "frac_to_mfrac"} <= found


def test_conic_hyperbola_expands_variables_to_fractions() -> None:
    found = _keys(_vertical("{=({x^2-y^2},{1})}", "conic"))
    assert "frac_expand_var" in found


def test_asymptotes_have_the_partial_fraction_card() -> None:
    found = _keys(_vertical("{frac({1},{x^2-1})}", "asymptotes"))
    assert {
        "partial_frac_simple",
        "partial_frac_vars",
        "partial_frac_denom_plural",
        "partial_frac_denom_1_improved",
        "partial_frac_get_unknown_simple",
        "partial_frac_get_unknown",
        "partial_frac_sub_improved",
        "frac_expr_div",
        "frac_reduce_reduce_plural",
    } <= found


def test_inverse_scaling_by_a_negative_fraction() -> None:
    group = solve(parse_protocol("{mat({mat_row({1},{2})},{mat_row({3},{0.5})})}")).result.group(
        ResultGroupType.VERTICAL
    )
    assert group is not None
    entries = [
        CoreSolverVerticalResult.from_contract(entry.result)
        for entry in group.entries
        if entry.result and "steps" in entry.result
    ]
    assert any("frac_div_rec_neg_one" in _keys(entry) for entry in entries)
