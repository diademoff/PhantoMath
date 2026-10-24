"""Регрессии ввода π, квадратной формулы и автоматического выбора действия."""

from __future__ import annotations

from typing import Any

import pytest
import sympy

from mymath_backend.ast import CoreNode
from mymath_backend.input import parse_protocol
from mymath_backend.node_types import CoreNodeType as T
from mymath_backend.service import solve_request
from mymath_backend.solver import SolveError, solve
from mymath_backend.solver.sympy_bridge import to_sympy


@pytest.mark.parametrize("source", ["{8pi}", "{8 pi}", "{8π}", r"{8\pi}", "{8 π}"])
def test_pi_text_is_exact(source: str) -> None:
    node = parse_protocol(source)
    assert node.type is T.MULTIPLY_IMPLICIT
    solution = solve(node).result.solution
    assert solution is not None
    assert to_sympy(solution) == 8 * sympy.pi


def test_pi_structured_and_approximation() -> None:
    node = CoreNode.node(T.MULTIPLY_IMPLICIT, CoreNode.constant("8"), CoreNode.constant("π"))
    exact = solve_request(node.to_contract())
    assert to_sympy(CoreNode.from_contract(exact["result"]["solution"])) == 8 * sympy.pi
    approximate = solve(node, command="approximate", args=[CoreNode.constant("4")]).result.solution
    assert approximate is not None
    assert approximate.type is T.APPROXIMATE
    assert abs(float(to_sympy(approximate.children[1])) - float(8 * sympy.pi)) < 0.001


@pytest.mark.parametrize("source", ["{8(2+1)}", "{8π(2+1)}"])
def test_number_and_pi_before_group(source: str) -> None:
    assert to_sympy(parse_protocol(source)) in (24, 24 * sympy.pi)


@pytest.mark.parametrize("argument", ["x", "t", "2x+1", "x+y", "x^2"])
@pytest.mark.parametrize("command", [None, "simplify"])
def test_identity_general_equal_arguments(argument: str, command: str | None) -> None:
    node = parse_protocol(f"{{cos({{{argument}}})^2+sin({{{argument}}})^2}}")
    data = solve(node, command=command)
    assert data.result.solution is not None
    assert data.result.solution.value == "1"
    vertical = data.result.vertical()
    assert vertical is not None
    sub = vertical.steps[0].substeps[0]
    assert sub.description is not None
    assert sub.description.type == "substitute_pythagorean_identity"
    assert len(sub.description.args) == 5
    rendered = solve_request(node.to_contract(), locale="ru")
    text = rendered["result"]["groups"][0]["entries"][0]["result"]["steps"][0]
    assert "основное тригонометрическое тождество" in text["substeps"][0]["explanation"]["text"]


@pytest.mark.parametrize(
    "source",
    [
        "{sin({x})^2+cos({y})^2}",
        "{sin({x})^2+cos({2x})^2}",
        "{sin({x})^2+sin({x})^2}",
        "{sin({x})^3+cos({x})^2}",
        "{sin({x})^2-cos({x})^2}",
    ],
)
def test_identity_has_no_false_matches(source: str) -> None:
    data = solve(parse_protocol(source), command="simplify")
    assert data.result.solution is not None
    assert to_sympy(data.result.solution) != 1
    vertical = data.result.vertical()
    assert vertical is not None
    assert all(
        sub.description.type != "substitute_pythagorean_identity"
        for step in vertical.steps
        for sub in step.substeps
        if sub.description
    )


@pytest.mark.parametrize(
    "source",
    [
        "{x^2-5x+6=0}",
        "{-2x^2+10x-12=0}",
        "{-x^2+2=0}",
        "{0.5x^2+4x+4=0}",
        "{0.5x^2+3x=4}",
        "{x^2/2-x=0}",
    ],
)
def test_quadratic_substitution_and_roots(source: str) -> None:
    node = parse_protocol(source)
    data = solve(node)
    vertical = data.result.vertical()
    assert vertical is not None and vertical.solution is not None
    steps = [sub for step in vertical.steps for sub in step.substeps]
    disc = steps[1].right
    calculated = steps[2].right
    assert disc is not None and calculated is not None
    assert sympy.simplify(to_sympy(disc.children[1]) - to_sympy(calculated.children[1])) == 0
    formula = steps[-1].left
    assert formula is not None and formula.type is T.LIST
    assert all(n.value not in ("a", "b", "c", "D") for n in formula.walk())
    residual = to_sympy(node.children[0]) - to_sympy(node.children[1])
    roots = vertical.solution.children if vertical.solution.type is T.LIST else [vertical.solution]
    values = [to_sympy(eq.children[1]) for eq in roots]
    assert values == sorted(values, key=lambda value: float(value))
    assert all(sympy.simplify(residual.subs(sympy.Symbol("x"), value)) == 0 for value in values)
    assert {sympy.simplify(to_sympy(eq.children[1])) for eq in formula.children} == set(values)


@pytest.mark.parametrize(
    "source",
    [
        "{x^2-5x+6}",
        "{x^3-x}",
        "{2t-6}",
        "{x^2+2x+1}",
    ],
)
def test_service_auto_polynomial_shows_factorization(source: str) -> None:
    """Голый многочлен показывает разложение, как в карточках (решение оператора)."""
    node = parse_protocol(source)
    result = solve_request(node.to_contract(), locale="ru")["result"]
    solution = CoreNode.from_contract(result["solution"])
    assert solution.type in {T.MULTIPLY, T.MULTIPLY_IMPLICIT, T.POWER}
    assert sympy.expand(to_sympy(solution)) == to_sympy(node)
    assert len(result["groups"]) == 1
    keys = [
        sub["description"]["type"]
        for entry in result["groups"][0]["entries"]
        for step in entry["result"]["steps"]
        for sub in step["substeps"]
    ]
    assert "find_x_intercept" not in keys


def test_service_explicit_action_does_not_find_roots() -> None:
    node = parse_protocol("{x^2-5x+6}")
    action: dict[str, Any] = {"command": "factor", "args": []}
    result = solve_request(node.to_contract(), action_data=action)["result"]
    assert len(result["groups"]) == 1
    assert CoreNode.from_contract(result["solution"]).type is T.MULTIPLY


def test_numeric_fallback_does_not_hide_domain_errors() -> None:
    with pytest.raises(SolveError):
        solve(parse_protocol("{acosh({0})}"))


def test_requested_quadratic_expression_shows_nontrivial_real_factors() -> None:
    node = parse_protocol("{2x^2+9x+6}")
    response = solve_request(node.to_contract(), locale="ru")
    solution = CoreNode.from_contract(response["result"]["solution"])
    assert solution.type is T.MULTIPLY
    assert sympy.expand(to_sympy(solution)) == to_sympy(node)


@pytest.mark.parametrize("source", ["{2x^2+9x+6=8π}", "{x^2=pi}"])
def test_quadratic_with_pi_is_exact_and_has_discriminant(source: str) -> None:
    node = parse_protocol(source)
    data = solve(node)
    vertical = data.result.vertical()
    assert vertical is not None and vertical.solution is not None
    steps = [sub for group in vertical.steps for sub in group.substeps]
    assert "eq_quad_disc" in [step.description.type for step in steps]
    residual = to_sympy(node.children[0]) - to_sympy(node.children[1])
    roots = vertical.solution.children if vertical.solution.type is T.LIST else [vertical.solution]
    assert all(
        sympy.simplify(residual.subs(sympy.Symbol("x"), to_sympy(eq.children[1]))) == 0
        for eq in roots
    )
    assert all(not to_sympy(eq.children[1]).has(sympy.Float) for eq in roots)
