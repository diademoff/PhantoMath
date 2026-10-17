from __future__ import annotations

from math import comb, factorial, perm

import pytest
import sympy

from mymath_backend.ast import CoreNode
from mymath_backend.node_types import CoreNodeType as T
from mymath_backend.solver.base import SolveResult, Step
from mymath_backend.solver.sympy_bridge import from_sympy, to_sympy
from mymath_backend.teaching_discrete import ARTICLES, TEMPLATES, enrich


def num(value: int) -> CoreNode:
    return CoreNode.constant(str(value))


def node(kind: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(kind, *children)


def value(part: CoreNode | None) -> sympy.Expr:
    assert part is not None
    if part.type is T.DETERMINANT:
        size = sympy.integer_nthroot(len(part.children), 2)[0]
        return sympy.Matrix(size, size, [to_sympy(c) for c in part.children]).det()
    if part.type is T.CHOOSE:
        return sympy.binomial(*[to_sympy(c) for c in part.children])
    if part.type in (T.PARTIAL_PERMUTATION_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT, T.VARIATION):
        n, k = [to_sympy(c) for c in part.children]
        return sympy.factorial(n) / sympy.factorial(n - k)
    return to_sympy(part)


def detail(step: Step) -> list[Step]:
    original = (step.left, step.right, step.key)
    assert enrich(step) is not None
    assert (step.left, step.right, step.key) == original
    assert step.subresult is not None
    children = list(step.subresult)
    assert children
    for child in children:
        assert child.key in TEMPLATES
        assert child.left is not None and child.right is not None
        assert not child.left.structural_eq(child.right)
        assert enrich(child) is None
    assert enrich(step) is None
    return children


@pytest.mark.parametrize("size", [2, 3, 4, 5, 6])
def test_determinants(size: int) -> None:
    matrix = sympy.Matrix(size, size, lambda r, c: (r + 1) ** c + (r == c))
    step = Step(from_sympy(matrix), from_sympy(matrix.det()), "matrix_det_rewrite")
    children = detail(step)
    for child in children:
        assert sympy.simplify(value(child.left) - value(child.right)) == 0
    assert any(child.key == "lesson_disc_det_expand" for child in children)
    if size == 3:
        assert sum(child.key == "lesson_disc_det_expand" for child in children) == 4


def test_flat_determinant_negative_fraction() -> None:
    matrix = sympy.Matrix([[sympy.Rational(-1, 2), 3], [2, 4]])
    step = Step(
        node(T.DETERMINANT2, *[from_sympy(x) for x in matrix]),
        from_sympy(matrix.det()),
        "det2_calc",
    )
    children = detail(step)
    assert value(children[-1].right) == -8


@pytest.mark.parametrize(
    "matrix", [sympy.Matrix([[0, 2], [3, 4]]), sympy.Matrix([[2, 1, 0], [1, 2, 1], [0, 1, 2]])]
)
def test_inverse_every_row_operation(matrix: sympy.Matrix) -> None:
    step = Step(from_sympy(matrix), from_sympy(matrix.inv()), "matrix_inv_right_is_inv")
    children = detail(step)
    for child in children:
        if child.key not in ("lesson_disc_swap", "lesson_disc_scale", "lesson_disc_eliminate"):
            continue
        before = value(child.left)
        args = [to_sympy(arg) for arg in child.args]
        row = int(args[0]) - 1
        if child.key == "lesson_disc_swap":
            before.row_swap(row, int(args[1]) - 1)
        elif child.key == "lesson_disc_scale":
            before[row, :] *= args[1]
        else:
            before[row, :] += args[2] * before[int(args[1]) - 1, :]
        assert before == value(child.right)
    reduced = value(children[-1].left)
    assert reduced[:, : matrix.cols] == sympy.eye(matrix.cols)
    assert reduced[:, matrix.cols :] == matrix.inv()


def test_matrix_product_actual_cells_and_missing_operand() -> None:
    first = sympy.Matrix([[1, -2, 3], [4, 5, 6]])
    second = sympy.Matrix([[7, 8], [9, 10], [11, 12]])
    answer = first * second
    missing = Step(from_sympy(first), from_sympy(answer), "matrix_mul")
    assert enrich(missing) is None
    step = Step(from_sympy(first), from_sympy(answer), "matrix_mul", [from_sympy(second)])
    children = detail(step)
    assert len(children) == 4
    for child in children:
        row, col = [int(to_sympy(arg)) - 1 for arg in child.args]
        assert value(child.left) == answer[row, col]
        assert value(child.right) == answer[row, col]
        assert child.left is not None and child.left.type is T.ADD


@pytest.mark.parametrize(
    "key,kind,n,k,answer",
    [
        ("factorial_calculate", T.FACTORIAL, 6, None, factorial(6)),
        ("factorial_calculate", T.FACTORIAL, 0, None, 1),
        ("choose_calculate", T.CHOOSE, 7, 3, comb(7, 3)),
        ("choose_calculate", T.CHOOSE, 7, 0, 1),
        (
            "permutation_calculate",
            T.PARTIAL_PERMUTATION_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT,
            7,
            3,
            perm(7, 3),
        ),
        ("variation_not_allowed_calculate", T.VARIATION, 7, 3, perm(7, 3)),
    ],
)
def test_counting_exact_products(key: str, kind: T, n: int, k: int | None, answer: int) -> None:
    children = [num(n)] if k is None else [num(n), num(k)]
    steps = detail(Step(node(kind, *children), num(answer), key))
    for child in steps:
        assert value(child.left) == answer
        assert value(child.right) == answer
    assert (
        any(
            part.type is T.MULTIPLY
            for step in steps
            if step.left is not None
            for part in step.left.walk()
        )
        if n > 1
        else True
    )


@pytest.mark.parametrize(
    "key",
    [
        "vector_dot",
        "vector_cross",
        "vector_length",
        "vector_add",
        "vector_subtract",
        "vector_scale",
    ],
)
def test_vector_coordinate_formulas(key: str) -> None:
    first = sympy.Matrix([1, -2, 3])
    second = sympy.Matrix([4, 5, -6])
    left = node(T.LIST, *[from_sympy(x) for x in first])
    arg = num(-2) if key == "vector_scale" else node(T.LIST, *[from_sympy(x) for x in second])
    answers = {
        "vector_dot": first.dot(second),
        "vector_cross": first.cross(second),
        "vector_length": sympy.sqrt(first.dot(first)),
        "vector_add": first + second,
        "vector_subtract": first - second,
        "vector_scale": first * -2,
    }
    answer = answers[key]
    right = (
        node(T.LIST, *[from_sympy(x) for x in answer])
        if isinstance(answer, sympy.MatrixBase)
        else from_sympy(answer)
    )
    children = detail(Step(left, right, key, [arg]))
    for child in children:
        assert sympy.simplify(value(child.left) - value(child.right)) == 0
    ambiguous = Step(left, right, "calculate_short")
    assert enrich(ambiguous) is None


@pytest.mark.parametrize(
    "kind,key,expected",
    [
        (T.UNION, "union", {1, 2, 3}),
        (T.INTERSECTION, "intersection", {2}),
        (T.DIFFERENCE, "set_difference", {1}),
    ],
)
def test_set_decisions(kind: T, key: str, expected: set[int]) -> None:
    left = node(kind, node(T.SET, num(1), num(2)), node(T.SET, num(2), num(3)))
    step = Step(left, from_sympy(sympy.FiniteSet(*expected)), key)
    children = detail(step)
    assert len(children) == 3
    for child in children:
        assert child.left is not None and child.right is not None
        element = int(to_sympy(child.left.children[0].children[0]))
        assert child.right.children[0].value == ("true" if element in expected else "false")


def test_mean_keeps_repeated_observations() -> None:
    children = detail(Step(node(T.MEAN, num(2), num(2), num(8)), num(4), "calculate_short"))
    assert children[0].args[0].value == "3"
    assert any(
        child.left is not None and child.left.type is T.ADD and len(child.left.children) == 3
        for child in children
    )
    for child in children:
        if child.key != "lesson_disc_mean":
            assert value(child.left) == value(child.right)


def test_retained_vector_marker_preserves_description() -> None:
    marker = CoreNode(type=T.TEXT_KEY, value="vector_dot")
    first = node(T.LIST, num(1), num(2))
    second = node(T.LIST, num(3), num(4))
    step = Step(first, num(11), "calculate_short", [second, marker])
    children = detail(step)
    assert step.key == "calculate_short" and step.args == [second, marker]
    assert value(children[-1].right) == 11


@pytest.mark.parametrize("kind", [T.ELEMENT_OF, T.ELEMENT_NOT_OF])
def test_membership_actual_element_comparisons(kind: T) -> None:
    step = Step(node(kind, num(2), node(T.SET, num(1), num(2), num(3))), None, "set_membership")
    children = detail(step)
    assert len(children) == 3
    assert step.subresult is not None and step.subresult.solution is not None
    assert step.subresult.solution.children[0].value == (
        "true" if kind is T.ELEMENT_OF else "false"
    )
    assert (
        sum(
            child.right is not None and child.right.children[0].value == "true"
            for child in children
        )
        == 1
    )


def test_proper_subset_checks_membership_and_inequality() -> None:
    first, second = node(T.SET, num(1)), node(T.SET, num(1), num(2))
    step = Step(node(T.PROPER_SUBSET, first, second), None, "set_inclusion")
    children = detail(step)
    assert len(children) == 2
    assert step.subresult is not None and step.subresult.solution is not None
    assert step.subresult.solution.children[0].value == "true"


def test_symbolic_set_membership_is_not_guessed() -> None:
    step = Step(
        node(T.ELEMENT_OF, CoreNode.variable("x"), node(T.SET, num(1))), None, "set_membership"
    )
    assert enrich(step) is None and step.subresult is None


def test_polynomial_substitution() -> None:
    x = CoreNode.variable("x")
    polynomial = node(T.ADD, node(T.POWER, x, num(2)), node(T.MULTIPLY, num(2), x), num(1))
    step = Step(node(T.EVALUATE_EXPRESSION, polynomial, num(-3)), num(4), "function_evaluate_expr")
    children = detail(step)
    assert children[0].right is not None
    assert not to_sympy(children[0].right).free_symbols
    assert value(children[-1].right) == 4


def test_system_reduced_matrix_matches_sympy() -> None:
    x, y = CoreNode.variable("x"), CoreNode.variable("y")
    equations = node(
        T.SYSTEM,
        node(T.EQUALS, node(T.ADD, x, y), num(3)),
        node(T.EQUALS, node(T.SUBTRACT, x, y), num(1)),
    )
    step = Step(equations, None, "system_2x2_add_eqs")
    children = detail(step)
    assert value(children[-1].right) == sympy.Matrix([[1, 0, 2], [0, 1, 1]])


def test_no_overwrite_and_invalid_or_bounded_inputs() -> None:
    existing = SolveResult()
    existing.add(Step(num(1), num(2), "existing"))
    step = Step(node(T.FACTORIAL, num(4)), num(24), "factorial_calculate", subresult=existing)
    assert enrich(step) is None and step.subresult is existing
    for left, key in [
        (node(T.FACTORIAL, num(100)), "factorial_calculate"),
        (node(T.CHOOSE, num(3), num(4)), "choose_calculate"),
        (node(T.LIST, num(1)), "vector_dot"),
    ]:
        unsupported = Step(left, None, key)
        assert enrich(unsupported) is None and unsupported.subresult is None


def test_theory_and_templates_have_complete_bilingual_contract() -> None:
    fields = {"title", "summary", "formula", "conditions", "example", "mistake"}
    for article in ARTICLES.values():
        assert set(article) == {"ru", "en"}
        for language in article.values():
            assert set(language) == fields and all(language.values())
    for key, template in TEMPLATES.items():
        assert key.startswith("lesson_disc_")
        assert set(template["templates"]) == {"ru", "default"}
        for text in template["templates"].values():
            for index in range(1, template["arity"] + 1):
                assert f"ARG{index}" in text
