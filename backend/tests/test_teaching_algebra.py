from __future__ import annotations

import re

import pytest
import sympy

from mymath_backend.ast import CoreNode
from mymath_backend.node_types import CoreNodeType as T
from mymath_backend.solver import absolute, commands, inequalities, powers, trigonometry
from mymath_backend.solver.base import SolveContext, SolveResult, Step
from mymath_backend.solver.sympy_bridge import from_sympy, to_sympy
from mymath_backend.solver.trig_equations import solve_trig_equation
from mymath_backend.teaching_algebra import ARTICLES, RULE_TOPICS, TEMPLATES, enrich


def n(value: object) -> CoreNode:
    return from_sympy(sympy.sympify(value))


def node(kind: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(kind, *children)


def details(step: Step) -> list[Step]:
    assert enrich(step) is not None
    assert step.subresult is not None
    return list(step.subresult)


def assert_expression_chain(steps: list[Step]) -> None:
    for step in steps:
        if step.left is not None and step.right is not None:
            assert not step.left.structural_eq(step.right)
            assert sympy.simplify(to_sympy(step.left) - to_sympy(step.right)) == 0
        assert step.key in TEMPLATES
        assert step.key.startswith("lesson_alg_")
        assert enrich(step) is None


@pytest.mark.parametrize(
    "left",
    [
        node(T.MULTIPLY, node(T.ADD, n("x"), n(2)), node(T.SUBTRACT, n("x"), n(3))),
        node(T.MULTIPLY, n(3), node(T.ADD, n("x"), n(4))),
        node(T.POWER, node(T.SUBTRACT, n("x"), n(2)), n(3)),
    ],
)
def test_actual_distribution(left: CoreNode) -> None:
    result = SolveResult()
    commands.expand(left, SolveContext(result, ["x"]), [])
    step = next(iter(result))
    old_left, old_right, old_key = step.left, step.right, step.key
    work = details(step)
    assert "lesson_alg_distribute" in [item.key for item in work]
    assert_expression_chain(work)
    assert (step.left, step.right, step.key) == (old_left, old_right, old_key)
    existing = step.subresult
    assert enrich(step) is None
    assert step.subresult is existing


def test_expansion_refuses_noop_and_trig_expansion() -> None:
    assert enrich(Step(n("x+1"), n("x+1"), "expand_msg")) is None
    left = node(T.SIN, n("2*x"))
    right = n(2 * sympy.sin(sympy.Symbol("x")) * sympy.cos(sympy.Symbol("x")))
    assert enrich(Step(left, right, "expand_msg")) is None


@pytest.mark.parametrize(
    "expression",
    ["6*x**3+9*x**2", "x**2+5*x+6", "2*x**2+7*x+3", "x**2-4", "x**2-2*x+1", "-2*x**2-10*x-12"],
)
def test_common_and_rational_quadratic_factoring(expression: str) -> None:
    left = n(expression)
    result = SolveResult()
    commands.factor(left, SolveContext(result, ["x"]), [])
    work = details(next(iter(result)))
    assert_expression_chain(work)
    assert any(item.key in ("lesson_alg_common", "lesson_alg_split") for item in work)


def test_no_fake_factoring_for_irreducible_or_opaque_polynomial() -> None:
    for expression in ("x**2+1", "x**3-1", "x**2-2"):
        left = n(expression)
        step = Step(left, n(sympy.factor(to_sympy(left), extension=True)), "factorise_call")
        assert enrich(step) is None
        assert step.subresult is None


def test_fraction_cancellation_keeps_original_domain() -> None:
    left = node(T.FRACTION, n("x**2-1"), n("x-1"))
    step = Step(left, n("x+1"), "simplify")
    work = details(step)
    condition = next(item for item in work if item.key == "lesson_alg_domain")
    assert condition.right is not None
    assert condition.right.type is T.NOT_EQUALS
    assert to_sympy(condition.right.children[0]) == sympy.Symbol("x") - 1
    assert condition.args == [condition.right]
    assert "lesson_alg_cancel" in [item.key for item in work]
    assert_expression_chain(work)


def test_fraction_restrictions_survive_pretranslation_cancellation() -> None:
    # The inner x/x has already become 1 by the time SymPy sees the outer quotient.
    inner = node(T.FRACTION, n("x"), n("x"))
    numerator = node(T.MULTIPLY, inner, n("x**2-1"))
    step = Step(node(T.FRACTION, numerator, n("x-1")), n("x+1"), "simplify")
    work = details(step)
    restrictions = [
        to_sympy(item.args[0].children[0]) for item in work if item.key == "lesson_alg_domain"
    ]
    assert sympy.Symbol("x") in restrictions
    assert sympy.Symbol("x") - 1 in restrictions


def test_fraction_rejects_sum_cancellation_and_wrong_answer() -> None:
    left = node(T.FRACTION, n("x+1"), n("x+2"))
    assert enrich(Step(left, n("1/2"), "simplify")) is None


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (node(T.ROOT2, n("4/9")), n("2/3")),
        (node(T.ROOT2, n(72)), n(6 * sympy.sqrt(2))),
        (node(T.ROOT, n(3), n(54)), n(3 * sympy.root(2, 3))),
        (node(T.POWER, n(16), n("3/4")), n(8)),
        (node(T.POWER, n(16), n("-3/4")), n("1/8")),
    ],
)
def test_roots_and_positive_rational_powers(left: CoreNode, right: CoreNode) -> None:
    work = details(Step(left, right, "root_simplify"))
    assert_expression_chain(work)
    assert any(item.key in ("lesson_alg_root_power", "lesson_alg_rational_power") for item in work)


def test_actual_root_solver_step() -> None:
    result = SolveResult()
    powers.solve_root(node(T.ROOT2, n("4/9")), SolveContext(result))
    assert_expression_chain(details(next(iter(result))))


def test_symbolic_and_negative_power_branches_are_not_invented() -> None:
    assert enrich(Step(node(T.ROOT2, n("x**2")), n("x"), "root_simplify")) is None
    assert enrich(Step(node(T.POWER, n(-8), n("1/3")), n(-2), "calculate_short")) is None


@pytest.mark.parametrize(
    "left",
    [node(T.LOG, n(8), n(2)), node(T.LOG10, n(1000)), node(T.LN, n(sympy.E)), node(T.LN, n(1))],
)
def test_log_definition_and_exact_substitution(left: CoreNode) -> None:
    result = SolveResult()
    powers.solve_logarithm(left, SolveContext(result))
    work = details(next(iter(result)))
    witness = work[0]
    assert witness.key == "lesson_alg_log_witness"
    assert witness.right is not None
    a, b = witness.right.children
    assert to_sympy(a) == to_sympy(b)
    assert {"lesson_alg_log_substitute", "lesson_alg_log_finish"} <= {item.key for item in work}
    assert_expression_chain(work)


def test_logarithm_rejects_bad_base_or_incorrect_exponent() -> None:
    assert enrich(Step(node(T.LOG, n(8), n(1)), n(3), "calculate_short")) is None
    assert enrich(Step(node(T.LOG, n(8), n(2)), n(4), "calculate_short")) is None


def identity(argument: CoreNode, other: CoreNode) -> CoreNode:
    return node(
        T.ADD, node(T.POWER, node(T.SIN, argument), n(2)), node(T.POWER, node(T.COS, other), n(2))
    )


def test_pythagorean_identity_has_rule_and_argument_application() -> None:
    left = identity(n("3*x"), n("3*x"))
    result = SolveResult()
    assert trigonometry.pythagorean_identity(left, SolveContext(result, ["x"])) is not None
    work = details(next(iter(result)))
    assert [item.key for item in work] == [
        "lesson_alg_pythagorean_rule",
        "lesson_alg_pythagorean_use",
    ]
    assert work[0].args[0].type is T.EQUALS
    assert_expression_chain(work)
    bad = Step(identity(n("x"), n("2*x")), n(1), "substitute_pythagorean_identity")
    assert enrich(bad) is None


@pytest.mark.parametrize(
    "left",
    [
        node(T.SIN, node(T.DEGREE, n(390))),
        node(T.SIN, n(13 * sympy.pi / 6)),
        node(T.COS, n(-sympy.pi / 3)),
        node(T.SIN, n(-sympy.pi / 6)),
    ],
)
def test_actual_trig_steps_explain_reduction_parity_and_exact_values(left: CoreNode) -> None:
    result = SolveResult()
    trigonometry.solve_function(left, SolveContext(result))
    keys: set[str] = set()
    for step in result:
        work = details(step)
        assert_expression_chain(work)
        keys.update(item.key for item in work)
    assert keys & {"lesson_alg_period", "lesson_alg_parity"}
    assert "lesson_alg_table" in keys


def test_opaque_trig_value_not_replaced_by_generic_filler() -> None:
    left = node(T.SIN, n(sympy.pi / 12))
    assert enrich(Step(left, n(sympy.sin(sympy.pi / 12)), "trig_table_calc")) is None


@pytest.mark.parametrize(
    ("kind", "coefficient", "rhs"),
    [
        (T.LESS_THAN, -2, 6),
        (T.LESS_THAN_EQUAL, -3, 6),
        (T.GREATER_THAN, 2, 8),
    ],
)
def test_actual_inequality_steps_reverse_only_negative_divisor(
    kind: T,
    coefficient: int,
    rhs: int,
) -> None:
    left = node(kind, n(f"{coefficient}*x"), n(rhs))
    result = SolveResult()
    inequalities.solve_inequality(left, SolveContext(result, ["x"]))
    step = list(result)[-1]
    assert step.subresult is not None
    work = list(step.subresult)
    assert work[0].key == ("ineq_linear_div_neg" if coefficient < 0 else "ineq_linear_div")
    assert work[0].right is not None
    assert step.right is not None
    assert work[0].right.type is step.right.type
    for item in work:
        assert item.left is not None and item.right is not None
        assert not item.left.structural_eq(item.right)
    if coefficient < 0:
        assert step.right.type is not kind


def test_absolute_equation_cases_are_real_branches() -> None:
    left = node(T.EQUALS, node(T.ABS, n("x-1")), n(2))
    result = absolute.solve_abs_equation(left, ["x"])
    assert result is not None
    step = next(item for item in result if item.key == "abs_separate")
    work = details(step)
    assert work[0].key == "lesson_alg_abs_nonnegative"
    assert work[-1].key == "lesson_alg_abs_or"
    assert work[-1].right is not None
    assert [to_sympy(branch.children[1]) for branch in work[-1].right.children] == [2, -2]


@pytest.mark.parametrize(
    ("kind", "key"),
    [
        (T.LESS_THAN, "lesson_alg_abs_and"),
        (T.GREATER_THAN, "lesson_alg_abs_or"),
        (T.GREATER_THAN_EQUAL, "lesson_alg_abs_or"),
    ],
)
def test_absolute_inequality_conjunction_versus_disjunction(kind: T, key: str) -> None:
    left = node(kind, node(T.ABS, n("x-1")), n(2))
    work = details(Step(left, None, "ineq_separate_abs"))
    assert work[-1].key == key
    cases = work[-1].right
    assert cases is not None
    for point in (-4, -1, 0, 1, 2, 3, 5):
        x = sympy.Symbol("x")
        values = [bool(to_sympy(branch).subs(x, point)) for branch in cases.children]
        derived = all(values) if kind is T.LESS_THAN else any(values)
        assert bool(to_sympy(left).subs(x, point)) == derived


@pytest.mark.parametrize(
    "expression", ["sin(x)-1/2", "2*sin(2*x+1)-1", "cos(3*x)-1/2", "tan(2*x)-1", "cot(x)-1"]
)
def test_simple_trig_equations_include_isolation_all_families_and_linear_argument(
    expression: str,
) -> None:
    left = node(T.EQUALS, n(expression), n(0))
    result = solve_trig_equation(left, ["x"])
    assert result is not None
    step = next(item for item in result if item.key == "trig_general_sol")
    work = details(step)
    assert "lesson_alg_families" in [item.key for item in work]
    assert step.subresult is not None and step.subresult.solution is not None
    answer = step.subresult.solution
    families = answer.children if answer.type is T.LIST else [answer]
    x, k = sympy.symbols("x k")
    for family in families:
        for index in (-2, -1, 0, 1, 2):
            root = to_sympy(family.children[1]).subs(k, index)
            assert sympy.simplify(sympy.sympify(expression).subs(x, root)) == 0


def test_nonlinear_trig_equation_is_explicitly_unsupported() -> None:
    left = node(T.EQUALS, node(T.SIN, n("x**2")), n(0))
    assert enrich(Step(left, None, "trig_general_sol")) is None


def test_every_authored_template_and_article_has_complete_metadata() -> None:
    for key, value in TEMPLATES.items():
        assert key in RULE_TOPICS
        assert RULE_TOPICS[key] in ARTICLES
        for locale in ("ru", "default"):
            text = value["templates"][locale]
            slots = {int(slot) for slot in re.findall(r"ARG(\d+)", text)}
            assert slots == set(range(1, value["arity"] + 1))
    fields = {"title", "summary", "formula", "conditions", "example", "mistake"}
    for article in ARTICLES.values():
        assert set(article) == {"ru", "en"}
        for text in article.values():
            assert set(text) == fields
            assert all(text.values())


def test_existing_subresult_is_never_overwritten() -> None:
    original = SolveResult()
    original.add(Step(n(1), n(2), "user_owned_example"))
    step = Step(n("x**2+5*x+6"), n("(x+2)*(x+3)"), "factorise_call", subresult=original)
    assert enrich(step) is None
    assert step.subresult is original
