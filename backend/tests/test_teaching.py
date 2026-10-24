"""Teaching hierarchy, math correctness and additive service metadata."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
import sympy

from mymath_backend.ast import CoreNode
from mymath_backend.input import parse_protocol
from mymath_backend.service import solve_request
from mymath_backend.solver import solve
from mymath_backend.solver.base import SolveResult, Step
from mymath_backend.solver.sympy_bridge import to_sympy
from mymath_backend.teaching import ARTICLES


def nodes(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def response(source: str, locale: str = "ru") -> dict[str, Any]:
    return solve_request(parse_protocol(source).to_contract(), locale=locale)


def test_explicit_boundaries_are_not_inferred_from_title() -> None:
    result = SolveResult()
    for _ in range(2):
        result.add_group("lesson_roots", Step(None, CoreNode.constant("2"), "lesson_simplify"))
    assert len(result.to_vertical().steps) == 2


def test_square_of_an_integer_is_a_product_then_calculated() -> None:
    # 5^2 -> 5 x 5 -> 25 as two rows.
    steps = solve(parse_protocol("{5^2}")).result.groups[0].entries[0].result["steps"]
    assert [[sub["description"]["type"] for sub in step["substeps"]] for step in steps] == [
        ["pow_to_mul"],
        ["mul"],
    ]


@pytest.mark.parametrize("source", ["{2+3*4}", "{2*(3+4)}", "{100/4+6}"])
def test_arithmetic_operations_are_separate_main_steps(source: str) -> None:
    # one row (main step) per operation.
    steps = solve(parse_protocol(source)).result.groups[0].entries[0].result["steps"]
    assert [len(step["substeps"]) for step in steps] == [1, 1]


@pytest.mark.parametrize(
    "source", ["{2x+3=7}", "{3x+2=x-4}", "{2*(x+1)=8}", "{x/2=3}", "{-2x+3=7}", "{2x=3x}", "{2x=x}"]
)
def test_linear_detail_preserves_the_solution_at_every_equation(source: str) -> None:
    result = response(source)
    symbol = sympy.Symbol("x")
    original = parse_protocol(source)
    expected = sympy.solve(to_sympy(original.children[0]) - to_sympy(original.children[1]), symbol)
    equations = [item for item in nodes(result) if item.get("type") == "EQUALS"]
    assert len(equations) > 3
    for item in equations:
        node = CoreNode.from_contract(item)
        actual = sympy.solve(to_sympy(node.children[0]) - to_sympy(node.children[1]), symbol)
        assert actual == expected


@pytest.mark.parametrize(
    "source",
    [
        "{frac({1},{3})+frac({1},{6})}",
        "{frac({1},{3})-frac({5},{6})}",
        "{frac({6},{8})}",
        "{frac({-6},{-8})}",
        "{frac({2},{3})*frac({3},{5})}",
        "{frac({2},{3})/frac({4},{5})}",
        "{frac({frac({1},{3})},{frac({2},{5})})}",
    ],
)
def test_fraction_details_are_exact_equivalent_expressions(source: str) -> None:
    result = response(source)
    details = [
        item
        for item in nodes(result)
        if "description" in item and "left" in item and "right" in item
    ]
    assert len(details) >= 3
    for item in details:
        left = to_sympy(CoreNode.from_contract(item["left"]))
        right = to_sympy(CoreNode.from_contract(item["right"]))
        assert sympy.simplify(left - right) == 0


@pytest.mark.parametrize("source", ["{0.5x^2+4x+4=0}", "{-2x^2+3x+1=0}", "{2x^2+9x+6=8pi}"])
def test_quadratic_has_three_groups_and_real_arithmetic_details(source: str) -> None:
    result = response(source)
    vertical = result["result"]["groups"][0]["entries"][0]["result"]
    assert [step["headers"][0]["type"] for step in vertical["steps"]] == [
        "lesson_standard",
        "lesson_discriminant",
        "lesson_roots",
    ]
    assert len(vertical["steps"][1]["substeps"]) == 2
    root_detail = vertical["steps"][2]["substeps"][0]["subresult"]
    assert root_detail["header"]["explanation"]["text"] == "Найдём корни"
    assert [g["headers"][0]["type"] for g in root_detail["steps"]] == [
        "lesson_root_substitute",
        "lesson_root_minus",
        "lesson_root_plus",
    ]
    all_steps = list(nodes(vertical))
    root_steps = [
        s for s in all_steps if s.get("description", {}).get("type", "").startswith("lesson_root_")
    ]
    assert len(root_steps) >= 5
    original = parse_protocol(source)
    symbol = sympy.Symbol("x")
    residual = to_sympy(original.children[0]) - to_sympy(original.children[1])
    # Every concrete branch, including uncomputed fractions, is a root.
    for step in root_steps:
        if step["description"]["type"] == "lesson_root_formula":
            continue
        for side in ("left", "right"):
            eq = CoreNode.from_contract(step[side])
            assert sympy.simplify(residual.subs(symbol, to_sympy(eq.children[1]))) == 0


@pytest.mark.parametrize("source", ["{x^2-5x+6=0}", "{2x^2+3x-2=0}"])
def test_row_quadratics_keep_the_polynomial_through_factoring(source: str) -> None:
    result = response(source)
    factoring = result["result"]["groups"][0]["entries"][0]["result"]
    original = parse_protocol(source)
    expected = sympy.expand(to_sympy(original.children[0]) - to_sympy(original.children[1]))
    equations = [
        CoreNode.from_contract(sub[side])
        for step in factoring["steps"][:3]
        for sub in step["substeps"]
        for side in ("left", "right")
    ]
    for equation in equations:
        assert (
            sympy.expand(to_sympy(equation.children[0]) - to_sympy(equation.children[1]))
            == expected
        )
    # The two linear branches really are the roots of the original polynomial.
    symbol = sympy.Symbol("x")
    roots = [
        to_sympy(CoreNode.from_contract(item["right"]).children[1])
        for item in factoring["steps"][4]["substeps"]
    ]
    assert all(expected.subs(symbol, r) == 0 for r in roots) and len(set(roots)) == 2


@pytest.mark.parametrize("locale", ["ru", "en"])
def test_rendered_hierarchy_has_ids_math_arguments_and_offline_theory(locale: str) -> None:
    result = response("{x^2-5x+6=0}", locale)
    repeated = response("{x^2-5x+6=0}", locale)
    ids = [item["id"] for item in nodes(result) if "description" in item and "id" in item]
    assert len(ids) == len(set(ids))
    assert ids == [item["id"] for item in nodes(repeated) if "description" in item and "id" in item]
    explanations = [item["explanation"] for item in nodes(result) if "explanation" in item]
    assert explanations
    assert all(not e["missing"] and "ARG" not in e["text"] for e in explanations)
    assert any(p["type"] == "math" for e in explanations for p in e["parts"])
    articles = [e["theory"] for e in explanations if e["theory"]]
    assert articles and all(
        all(
            a.get(field)
            for field in ("title", "summary", "conditions", "formula", "example", "mistake")
        )
        for a in articles
    )
    assert all(set(entry) == {"ru", "en"} for entry in ARTICLES.values())


def test_raw_solver_contract_remains_readable_without_service_metadata() -> None:
    raw = solve(parse_protocol("{2x+3=7}")).to_contract()
    assert not any("theory" in item or "parts" in item for item in nodes(raw))


def test_ids_are_distinct_across_roots_and_factorization_groups() -> None:
    result = response("{x^2-5x+6}")
    ids = [item["id"] for item in nodes(result) if "description" in item and "id" in item]
    assert len(ids) == len(set(ids))
