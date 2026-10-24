"""Тесты карточек производных: правило на каждом шаге и производные высших порядков.

Производная сверяется с sympy, а не со строкой: карточка показывает формулы, и
проверять надо значение. У ``derivation_diff`` первый способ — карточка по
правилам, у команды ``nth_derivative`` — шаги повторного дифференцирования.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import sympy

from mymath_backend import CoreNode, CoreNodeType, load_explanations, service
from mymath_backend.input import parse_protocol
from mymath_backend.solver import SolveError, solve
from mymath_backend.solver.sympy_bridge import to_sympy

EXPLANATIONS = Path(__file__).resolve().parents[1] / "mymath_backend" / "data" / "explanations.json"


def cards(
    source: str, command: str | None = None, args: tuple[str, ...] = ()
) -> list[dict[str, Any]]:
    """The method cards of the vertical group, in the order the student sees them."""
    action = None
    if command:
        action = {
            "command": command,
            "args": [parse_protocol(item).to_contract() for item in args],
        }
    response = service.solve_request(
        parse_protocol(source).to_contract(), action, render=True, locale="ru"
    )
    return response["result"]["groups"][0]["entries"]


def keys_of(card: dict[str, Any]) -> list[str]:
    return [
        sub["description"]["type"] for step in card["result"]["steps"] for sub in step["substeps"]
    ]


def _variables(node: Any) -> set[str]:
    """The names of the variables of a contract tree."""
    if isinstance(node, dict):
        if node.get("type") == "VARIABLE":
            return {str(node.get("value"))}
        found: set[str] = set()
        for child in node.values():
            found |= _variables(child)
        return found
    if isinstance(node, list):
        return {name for child in node for name in _variables(child)}
    return set()


def answer(card: dict[str, Any]) -> sympy.Expr:
    return to_sympy(CoreNode.from_contract(card["result"]["solutionNode"]))


def derivative_of(source: str) -> sympy.Expr:
    node = parse_protocol(source)
    expression = to_sympy(node.children[1])
    variable = to_sympy(node.children[0])
    return sympy.diff(expression, variable)


DIFFERENTIATION_CASES = [
    (
        "{derivation_diff({x},{frac({1},{2})*root({3},{x^2})*cos({x})})}",
        [
            "lesson_calc_rule_product",
            "lesson_calc_part_first",
            "lesson_calc_part_second",
            "lesson_calc_compose_derivatives",
            "lesson_calc_simplify_result",
        ],
    ),
    (
        "{derivation_diff({x},{ln({root({5},{frac({1-x},{1+x})})})})}",
        [
            "lesson_calc_rule_chain",
            "lesson_calc_part_argument",
            "lesson_calc_compose_derivatives",
            "lesson_calc_simplify_result",
        ],
    ),
    (
        "{derivation_diff({x},{ln({frac({x^2+4},{root({3},{x-1})})})})}",
        [
            "lesson_calc_rule_chain",
            "lesson_calc_part_argument",
            "lesson_calc_compose_derivatives",
            "lesson_calc_simplify_result",
        ],
    ),
    (
        "{derivation_diff({x},{5*ln({x})+frac({2},{root({5},{x^7})})+atan({x})"
        "-log10({20})*2^x+tan({3})})}",
        [
            "lesson_calc_rule_sum",
            "lesson_calc_part_first",
            "lesson_calc_part_second",
            "lesson_calc_compose_derivatives",
        ],
    ),
    (
        "{derivation_diff({x},{(x^2+7x-1)*log({x},{3})})}",
        [
            "lesson_calc_rule_product",
            "lesson_calc_part_first",
            "lesson_calc_part_second",
            "lesson_calc_compose_derivatives",
            "lesson_calc_simplify_result",
        ],
    ),
    (
        "{derivation_diff({x},{-frac({acot({x})},{root({3},{x})})})}",
        [
            "lesson_calc_rule_constant_factor",
            "lesson_calc_part_argument",
            "lesson_calc_compose_derivatives",
            "lesson_calc_simplify_result",
        ],
    ),
    (
        "{derivation_diff({x},{frac({1},{acos({x})^2})})}",
        [
            "lesson_calc_rule_reciprocal",
            "lesson_calc_part_argument",
            "lesson_calc_compose_derivatives",
            "lesson_calc_simplify_result",
        ],
    ),
]


@pytest.mark.parametrize(("source", "expected"), DIFFERENTIATION_CASES)
def test_rule_card_is_one_rule_per_stage(source: str, expected: list[str]) -> None:
    entries = cards(source)
    assert len(entries) == 1, "одна карточка, без переключателя способов"
    card = entries[0]
    assert answer(card) is not None
    assert sympy.simplify(answer(card) - derivative_of(source)) == 0
    assert keys_of(card) == expected
    # Каждое правило со своей формулой, каждая часть раскрывается в «Подробнее».
    rule = next(
        sub
        for step in card["result"]["steps"]
        for sub in step["substeps"]
        if sub["description"]["type"] == expected[0]
    )
    assert rule["explanation"]["parts"], "у правила нет формулы"
    opened = [
        sub
        for step in card["result"]["steps"]
        for sub in step["substeps"]
        if sub["description"]["type"].startswith("lesson_calc_part_")
    ]
    assert opened and all(sub["subresult"] for sub in opened)


@pytest.mark.parametrize(
    "root",
    ["{root({3},{x})}", "{root({5},{x})}", "{root({3},{x^2})}", "{root({5},{x^7})}"],
)
def test_root_derivative_uses_the_index_of_the_root(root: str) -> None:
    """``(ⁿ√u)′`` depends on ``n``: the square-root rule is only the case ``n = 2``."""
    source = "{derivation_diff({x}," + root + ")}"
    card = cards(source)[0]
    assert sympy.simplify(answer(card) - derivative_of(source)) == 0
    assert "lesson_calc_rule" in " ".join(keys_of(card))


def test_a_letter_that_is_not_the_variable_is_a_constant() -> None:
    entries = cards("{derivation_diff({x},{C})}")
    assert len(entries) == 1
    assert keys_of(entries[0]) == ["derive_const"]
    assert answer(entries[0]) == 0


def high_derivative(source: str, order: int) -> dict[str, Any]:
    return cards(source, command="nth_derivative", args=(f"{{{order}}}",))[0]


THIRD = ["derive_higher_order", "derive_multi", "find_high_order_derivative"]

HIGHER_ORDER_CASES = [
    ("{\\e^(3x)}", 4, THIRD),
    ("{5^x}", 5, THIRD),
    ("{ln({2x-1})}", 10, THIRD),
    ("{frac({1},{x-2})}", 20, THIRD),
    ("{root2({x-2})}", 8, THIRD),
    ("{sin({x})}", 18, THIRD),
    ("{cos({x})}", 47, THIRD),
    ("{\\e^(-x)*cos({x})}", 3, THIRD),
    (
        "{frac({sin({2x})},{x})}",
        3,
        THIRD,
    ),
    ("{(2x^2-7)*ln({x-1})}", 5, THIRD),
    ("{\\e^(3x)*(2x-1)}", 7, THIRD),
    ("{sin({frac({x},{3})})^2}", 2, ["derive_higher_order", "second_derivative"]),
    ("{frac({x},{root2({x^2+1})})}", 2, ["derive_higher_order", "second_derivative"]),
]


@pytest.mark.parametrize(("source", "order", "expected"), HIGHER_ORDER_CASES)
def test_higher_derivative_value_and_steps(source: str, order: int, expected: list[str]) -> None:
    card = high_derivative(source, order)
    node = parse_protocol(source)
    expression = to_sympy(node)
    symbol = next(iter(expression.free_symbols), sympy.Symbol("x"))
    assert sympy.simplify(answer(card) - sympy.diff(expression, symbol, order)) == 0
    assert keys_of(card) == expected


def test_the_run_up_shows_the_first_derivatives() -> None:
    card = high_derivative("{\\e^(3x)}", 4)
    first = card["result"]["steps"][0]["substeps"][0]
    assert first["subresult"] is not None
    detail = [
        sub["description"]["type"]
        for step in first["subresult"]["steps"]
        for sub in step["substeps"]
    ]
    assert len(detail) == 4
    assert set(detail) == {"derive"}


def test_the_general_formula_is_written_for_n_then_used() -> None:
    card = high_derivative("{frac({1},{x-2})}", 20)
    keys = keys_of(card)
    assert keys == ["derive_higher_order", "derive_multi", "find_high_order_derivative"]
    pattern = card["result"]["steps"][-1]["substeps"][0]["subresult"]
    assert pattern is not None
    nested = [sub["description"]["type"] for step in pattern["steps"] for sub in step["substeps"]]
    assert nested == ["higher_order_pattern", "higher_order_substitute"]
    general = pattern["steps"][0]["substeps"][0]["left"]
    assert "n" in _variables(general), "в общей формуле должна стоять буква n"


def test_the_second_derivative_reaches_a_short_form() -> None:
    card = high_derivative("{sin({frac({x},{3})})^2}", 2)
    x = sympy.Symbol("x")
    assert sympy.simplify(answer(card) - sympy.cos(2 * x / 3) * sympy.Rational(2, 9)) == 0


def test_a_higher_derivative_needs_its_order() -> None:
    """Without ``n`` the command cannot know which derivative is wanted."""
    with pytest.raises(SolveError):
        solve(parse_protocol("{\\e^(3x)}"), command="nth_derivative", args=[])


def test_new_explanation_keys_exist() -> None:
    explanations = load_explanations(str(EXPLANATIONS))
    for key in (
        "lesson_calc_rule_root",
        "higher_order_pattern",
        "higher_order_substitute",
        "param_derivative_formula",
        "param_second_derivative_formula",
        "param_derivative_of",
        "param_derivative_substitute",
    ):
        assert key in explanations
    assert explanations.arity("higher_order_substitute") == 1
    assert explanations.arity("param_derivative_formula") == 2
    assert explanations.arity("param_second_derivative_formula") == 1
    assert explanations.arity("param_derivative_of") == 1


PARAMETRIC = [
    "{frac({derivation_diff({t},{cos({t})+t*sin({t})})},"
    "{derivation_diff({t},{frac({sin({t})},{1+sin({t})})})})}",
    "{frac({derivation_diff({t},{tan({t})^2})},{derivation_diff({t},{cos({t})^2})})}",
    "{frac({derivation_diff({t},{frac({derivation_diff({t},{tan({t})^2})},"
    "{derivation_diff({t},{cos({t})^2})})})},{derivation_diff({t},{cos({t})^2})})}",
    "{frac({derivation_diff({t},{frac({1},{2})*cos({3t})^4})},"
    "{derivation_diff({t},{sin({3t})^4})})}",
    "{frac({derivation_diff({t},{frac({derivation_diff({t},"
    "{frac({1},{2})*cos({3t})^4})},{derivation_diff({t},{sin({3t})^4})})})},"
    "{derivation_diff({t},{sin({3t})^4})})}",
    "{frac({derivation_diff({t},{ln({1+exp({2t})})})},{derivation_diff({t},{atan({\\e^t})})})}",
    "{frac({derivation_diff({t},{frac({derivation_diff({t},{ln({1+exp({2t})})})},"
    "{derivation_diff({t},{atan({\\e^t})})})})},{derivation_diff({t},{atan({\\e^t})})})}",
]

PARAMETRIC_KEYS = ["param_derivative_of", "param_derivative_of", "param_derivative_substitute"]


def _second_order(source: str) -> bool:
    """``y″_xx`` is sent as ``d/dt(y′_x) / d/dt(x)``: the numerator is a ratio again."""
    node = parse_protocol(source)
    numerator = node.children[0]
    expression = numerator.children[1]
    return expression.type in (CoreNodeType.FRACTION, CoreNodeType.DIVIDE)


def parametric_expected(source: str) -> sympy.Expr:
    """``y′_t / x′_t`` computed by sympy from the two parameter equations."""
    node = parse_protocol(source)
    top, bottom = node.children
    parameter = to_sympy(top.children[0])
    return sympy.simplify(
        sympy.diff(to_sympy(top.children[1]), parameter)
        / sympy.diff(to_sympy(bottom.children[1]), parameter)
    )


@pytest.mark.parametrize("source", PARAMETRIC)
def test_parametric_derivative_has_one_step_per_derivative(source: str) -> None:
    card = cards(source)[0]
    assert sympy.simplify(answer(card) - parametric_expected(source)) == 0
    formula = (
        "param_second_derivative_formula" if _second_order(source) else "param_derivative_formula"
    )
    assert keys_of(card) == [formula, *PARAMETRIC_KEYS]
    steps = [
        sub
        for step in card["result"]["steps"]
        for sub in step["substeps"]
        if sub["description"]["type"] == "param_derivative_of"
    ]
    assert len(steps) == 2
    assert steps[0].get("subresult"), "производная числителя раскрывается"
    header = card["result"]["steps"][0]["headers"][0]
    assert header["type"] == formula
    assert header["args"], "в формуле стоят производные, которые подставляем"


POINTS = [
    ("{evaluate_expr({derivation_diff({x},{x^3+3x^2-72x+90})},{5})}", "derive"),
    ("{evaluate_expr({derivation_diff({x},{frac({x^2},{x+2})})},{-4})}", "derive"),
    (
        "{evaluate_expr({derivation_diff({x},"
        "{frac({x^2*atan({5x})},{2})-frac({x},{10})+frac({1},{50})*atan({5x})})},"
        "{frac({1},{5})})}",
        "derive",
    ),
    (
        "{evaluate_expr({derivation_diff({x},"
        "{x*atan({2x})-frac({1},{4})*ln({1+4x^2})})},{frac({-root2({3})},{2})})}",
        "derive",
    ),
    ("{evaluate_expr({derivation_diff({x},{ln({x^2+root2({x^4+1})})})},{1})}", "derive"),
    (
        "{evaluate_expr({derivation_diff({x},{-ln({root2({x+1})-root2({x-1})})})},{root2({2})})}",
        "derive",
    ),
    (
        "{evaluate_expr({derivation_diff({x},{derivation_diff({x},"
        "{frac({x},{root2({x^2+1})})})})},{0})}",
        "find_high_order_derivative",
    ),
]


def point_expected(source: str) -> sympy.Expr:
    """Differentiate under all the derivative signs, then put the point in."""
    node = parse_protocol(source)
    notation, value = node.children
    order, expression = 0, notation
    while expression.type is CoreNodeType.DERIVATION1_DIFF:
        order += 1
        expression = expression.children[1]
    parameter = to_sympy(notation.children[0])
    derived = sympy.diff(to_sympy(expression), parameter, order)
    return sympy.simplify(derived.subs(parameter, to_sympy(value)))


@pytest.mark.parametrize(("source", "first"), POINTS)
def test_derivative_at_a_point_shows_the_derivative_then_the_value(source: str, first: str) -> None:
    card = cards(source)[0]
    assert sympy.simplify(answer(card) - point_expected(source)) == 0
    assert keys_of(card) == [first, "function_evaluate_value"]
    derivative_step = card["result"]["steps"][0]["substeps"][0]
    assert derivative_step["subresult"], "производная раскрыта по правилам"
