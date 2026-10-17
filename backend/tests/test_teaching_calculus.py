"""Check actual lesson calculations, preservation, and unsupported boundaries."""

from __future__ import annotations

import pytest
import sympy

from mymath_backend.ast import CoreNode
from mymath_backend.node_types import CoreNodeType as T
from mymath_backend.solver.base import SolveResult, Step
from mymath_backend.solver.sympy_bridge import from_sympy, to_sympy
from mymath_backend.teaching_calculus import ARTICLES, RULE_TOPICS, TEMPLATES, enrich

X = sympy.Symbol("x")
Y = sympy.Symbol("y")


def n(kind: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(kind, *children)


def c(value: int) -> CoreNode:
    return CoreNode.constant(str(value))


def result(step: Step) -> SolveResult:
    assert enrich(step) is not None
    assert step.subresult is not None
    assert step.subresult.solution is not None
    for sub in step.subresult:
        assert sub.key.startswith("lesson_calc_")
        assert sub.key in TEMPLATES
        assert RULE_TOPICS[sub.key] in ARTICLES
        assert enrich(sub) is None
    return step.subresult


def check_derivative_detail(detail: SolveResult) -> None:
    """Evaluate all explicit derivative notations independently with SymPy."""

    def evaluate(node: CoreNode) -> sympy.Expr:
        if node.type is T.DERIVATION1_DIFF:
            index, expression = node.children
            return sympy.diff(evaluate(expression), sympy.Symbol(index.value or "x"))
        if not node.children:
            return to_sympy(node)
        converted = CoreNode(
            type=node.type,
            value=node.value,
            children=[from_sympy(evaluate(child)) for child in node.children],
        )
        return to_sympy(converted)

    for sub in detail:
        if sub.left is not None and sub.right is not None:
            assert sympy.simplify(evaluate(sub.left) - evaluate(sub.right)) == 0


@pytest.mark.parametrize(
    "expression",
    [
        X * sympy.sin(X),
        (X**2 + 1) / (X + 2),
        sympy.sin(X**2 + 1),
        (X + 1) ** 4,
        X**3 + 2 * X - 7,
        sympy.exp(3 * X),
        X * sympy.sin(X) * sympy.exp(X),
    ],
)
def test_derivative_rules_are_composed(expression: sympy.Expr) -> None:
    step = Step(
        n(T.DERIVATION1, from_sympy(expression)),
        from_sympy(sympy.diff(expression, X)),
        "find_derivative",
    )
    old = SolveResult()
    step.subresult = old
    detail = result(step)
    assert detail is not old
    assert detail.solution is not None
    assert sympy.simplify(to_sympy(detail.solution) - sympy.diff(expression, X)) == 0
    check_derivative_detail(detail)
    assert step.key == "find_derivative"


def test_explicit_variable_and_other_variables_constant() -> None:
    expression = X**2 * Y + sympy.sin(Y)
    step = Step(
        n(T.DERIVATION1_DIFF, CoreNode.variable("y"), from_sympy(expression)),
        from_sympy(sympy.diff(expression, Y)),
        "find_derivative_with_respect",
    )
    detail = result(step)
    check_derivative_detail(detail)
    assert detail.solution is not None
    assert to_sympy(detail.solution) == X**2 + sympy.cos(Y)
    for sub in detail:
        if sub.left and sub.left.type is T.DERIVATION1_DIFF:
            assert sub.left.children[0].value == "y"


@pytest.mark.parametrize("kind", [T.PRIME, T.DERIVATION1_PRIME])
def test_first_derivative_prime_notation(kind: T) -> None:
    step = Step(
        n(kind, from_sympy(sympy.sin(X**2))), from_sympy(2 * X * sympy.cos(X**2)), "find_derivative"
    )
    check_derivative_detail(result(step))


@pytest.mark.parametrize("expression", [X**3 + 2 * X - 5, sympy.Integer(7), 3 * Y**2, 0 * X])
def test_polynomial_integrals_include_arbitrary_constant(expression: sympy.Expr) -> None:
    variable = next(iter(sympy.sympify(expression).free_symbols), X)
    primitive = sympy.integrate(expression, variable)
    step = Step(n(T.INTEGRAL, from_sympy(expression)), from_sympy(primitive), "integrate_calc")
    original_answer = step.right
    detail = result(step)
    assert detail.solution is not None
    family = to_sympy(detail.solution)
    assert sympy.simplify(sympy.diff(family, variable) - expression) == 0
    assert sympy.Symbol("C") in family.free_symbols
    assert step.right is original_answer
    for sub in detail:
        if sub.key == "lesson_calc_power_integral":
            assert sub.left is not None and sub.right is not None
            assert (
                sympy.simplify(
                    sympy.diff(to_sympy(sub.right), variable) - to_sympy(sub.left.children[0])
                )
                == 0
            )


@pytest.mark.parametrize(("lower", "upper"), [(1, 2), (2, 1), (-2, 3), (2, 2)])
def test_definite_integral_has_actual_boundary_values(lower: int, upper: int) -> None:
    expression = X**2 + 2 * X
    expected = sympy.integrate(expression, (X, lower, upper))
    step = Step(
        n(T.INTEGRAL_DEFINITE, c(lower), c(upper), from_sympy(expression)),
        from_sympy(expected),
        "integrate_calc",
    )
    detail = result(step)
    assert detail.solution is not None
    assert sympy.simplify(to_sympy(detail.solution) - expected) == 0
    keys = {sub.key for sub in detail}
    assert {"lesson_calc_newton", "lesson_calc_upper", "lesson_calc_lower"} <= keys
    for sub in detail:
        if sub.key in {"lesson_calc_upper", "lesson_calc_lower", "lesson_calc_subtract"}:
            assert sub.left is not None and sub.right is not None
            assert sympy.simplify(to_sympy(sub.left) - to_sympy(sub.right)) == 0


def test_limit_factor_cancellation_retains_domain() -> None:
    x = CoreNode.variable("x")
    expression = n(T.FRACTION, n(T.SUBTRACT, n(T.POWER, x, c(2)), c(1)), n(T.SUBTRACT, x, c(1)))
    step = Step(n(T.LIMIT, c(1), expression), c(2), "limit_solve")
    detail = result(step)
    keys = {sub.key for sub in detail}
    assert {"lesson_calc_domain", "lesson_calc_factor", "lesson_calc_cancel"} <= keys
    assert detail.solution is not None
    assert to_sympy(detail.solution) == 2
    for sub in detail:
        if sub.key in {"lesson_calc_factor", "lesson_calc_cancel"}:
            assert sub.left is not None and sub.right is not None
            assert sympy.cancel(to_sympy(sub.left) - to_sympy(sub.right)) == 0


def test_limit_substitution_is_unsimplified_calculation() -> None:
    step = Step(n(T.LIMIT, c(3), from_sympy(X**2 + 2)), c(11), "limit_solve")
    detail = result(step)
    substitution = next(sub for sub in detail if sub.key == "lesson_calc_substitute")
    assert substitution.right is not None
    assert substitution.right.type is T.ADD
    assert to_sympy(substitution.right) == 11


def test_eager_sympy_cancellation_does_not_erase_original_domain() -> None:
    x = CoreNode.variable("x")
    step = Step(n(T.LIMIT, c(0), n(T.FRACTION, x, x)), c(1), "limit_solve")
    detail = result(step)
    condition = next(sub.right for sub in detail if sub.key == "lesson_calc_domain")
    assert condition is not None
    assert condition.type is T.NOT_EQUALS
    assert condition.children[0].structural_eq(x)


@pytest.mark.parametrize(
    "expression",
    [
        sympy.sin(2 * X + 1),
        3 * sympy.cos(3 * X),
        sympy.exp(-2 * X + 1),
    ],
)
def test_definite_linear_argument_integrals(expression: sympy.Expr) -> None:
    expected = sympy.integrate(expression, (X, 0, 1))
    step = Step(
        n(T.INTEGRAL_DEFINITE, c(0), c(1), from_sympy(expression)),
        from_sympy(expected),
        "integrate_calc",
    )
    detail = result(step)
    assert detail.solution is not None
    assert sympy.simplify(to_sympy(detail.solution) - expected) == 0
    assert any(sub.key == "lesson_calc_linear_integral" for sub in detail)


@pytest.mark.parametrize("count", [1, 3, 12])
def test_sigma_expands_every_term(count: int) -> None:
    k = sympy.Symbol("k")
    expression = k**2 + 1
    expected = sympy.summation(expression, (k, 1, count))
    step = Step(
        n(T.SIGMA_DEFINITE, CoreNode.variable("k"), c(1), c(count), from_sympy(expression)),
        from_sympy(expected),
        "series_sigma_find_sub",
    )
    detail = result(step)
    assert detail.solution is not None
    terms = [sub for sub in detail if sub.key == "lesson_calc_term"]
    assert len(terms) == count
    for integer, sub in enumerate(terms, 1):
        assert sub.left is not None and sub.right is not None
        assert to_sympy(sub.left) == to_sympy(sub.right) == integer**2 + 1
    assert to_sympy(detail.solution) == expected


@pytest.mark.parametrize(
    "step",
    [
        Step(n(T.INTEGRAL, from_sympy(sympy.exp(X**2))), None, "integrate_calc"),
        Step(n(T.INTEGRAL_DEFINITE, c(-1), c(1), from_sympy(1 / X)), None, "integrate_calc"),
        Step(n(T.LIMIT, c(0), from_sympy(1 / X)), None, "limit_solve"),
        Step(n(T.LIMIT, c(-1), from_sympy(sympy.log(X))), None, "limit_solve"),
        Step(n(T.LIMIT, c(0), from_sympy(sympy.sin(X) / X)), c(1), "limit_solve"),
        Step(
            n(T.SIGMA_DEFINITE, c(1), c(13), CoreNode.variable("n")), None, "series_sigma_find_sub"
        ),
        Step(
            n(T.SIGMA_DEFINITE, c(3), c(1), CoreNode.variable("n")), None, "series_sigma_find_sub"
        ),
        Step(
            n(T.DERIVATION1, from_sympy(X**X)),
            from_sympy(X**X * (sympy.log(X) + 1)),
            "find_derivative",
        ),
    ],
)
def test_unsupported_methods_keep_existing_work(step: Step) -> None:
    original = SolveResult()
    original.add(Step(c(1), c(1), "existing_user_work"))
    step.subresult = original
    assert enrich(step) is None
    assert step.subresult is original


def test_mismatched_answer_is_not_hidden() -> None:
    step = Step(n(T.DERIVATION1, from_sympy(X**2)), c(99), "find_derivative")
    assert enrich(step) is None
    assert step.subresult is None


def test_theory_is_bilingual_and_complete() -> None:
    for article in ARTICLES.values():
        assert set(article) == {"ru", "en"}
        for text in article.values():
            assert set(text) == {"title", "summary", "formula", "conditions", "example", "mistake"}
            assert all(text.values())
    assert set(RULE_TOPICS.values()) <= set(ARTICLES)
    for key, template in TEMPLATES.items():
        assert key.startswith("lesson_calc_")
        assert template["arity"] == 0
        assert set(template["templates"]) == {"ru", "default"}
