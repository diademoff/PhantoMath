"""Ключи карточек complex/conics/function.

Свойства комплексного числа перед степенью, классификация коник, сложение
в правой части при выделении квадрата и function_* карточки параболы.
Используются только существующие ключи словаря.
"""

from __future__ import annotations

from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult, ResultGroupType
from mymath_backend.solver import solve


def _entries(proto: str, command: str | None = None) -> list[CoreSolverVerticalResult]:
    data = solve(parse_protocol(proto), command=command)
    group = data.result.group(ResultGroupType.VERTICAL)
    assert group is not None
    return [
        CoreSolverVerticalResult.from_contract(entry.result)
        for entry in group.entries
        if entry.result and "steps" in entry.result
    ]


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


def test_complex_power_shows_conjugate_modulus_and_parts() -> None:
    # complex_power takes its exponent through action args.
    data = solve(
        parse_protocol("{1+\\i}"),
        command="complex_power",
        args=[parse_protocol("{2}")],
    )
    vertical = data.result.vertical()
    assert vertical is not None
    found = _keys(vertical)
    assert {
        "complex_conjugate_find",
        "complex_add_bars",
        "complex_mod_formula",
        "complex_find_parts_pair",
        "complex_number",
        "complex_pow_polar_moivre_simple",
    } <= found


def test_complex_quotient_has_the_simple_divide_header() -> None:
    entries = _entries("{frac({1+\\i},{1-\\i})}")
    assert any("complex_divide_step_simple" in _keys(entry) for entry in entries)


def test_conic_classification_keys() -> None:
    cases = {
        "{=({x^2+y^2},{1})}": "conics_classify_circle",
        "{=({x^2/4+y^2/9},{1})}": "conics_classify_ellipse",
        "{=({x^2-y^2},{1})}": "conics_classify_hyperbola",
        "{=({y^2},{4x})}": "conics_classify_parabola",
    }
    for source, key in cases.items():
        found = _keys(_entries(source, "conic_details")[0])
        assert key in found, source


def test_completion_of_the_square_adds_to_the_right() -> None:
    for source in ("{=({x^2+y^2},{1})}", "{=({x^2/4+y^2/9},{1})}"):
        assert "conics_add_right" in _keys(_entries(source, "conic_details")[0])


def test_ellipse_has_the_represents_header() -> None:
    found = _keys(_entries("{=({x^2/4+y^2/9},{1})}", "conic_details")[0])
    assert "conics_represents_ellipse" in found


def test_parabola_has_even_odd_and_intercept_cards() -> None:
    found = _keys(_entries("{=({y^2},{4x})}", "conic_details")[0])
    assert {
        "function",
        "function_determine_even_odd",
        "function_f_determine_even_odd",
        "function_substitute",
        "function_even",
        "function_num_inter_quad",
        "function_num_inter_quad_sub",
        "function_num_inter_quad_one",
        "function_num_inter_quad_one_smpl",
        "function_num_inter_quad_one_related",
    } <= found
