"""Тесты модуля систем 2×2.

Уравнения системы строятся узлами (``EQUALS``), ответ — список ``x = …, y = …``.
Проверяются решение, порядок неизвестных, нелинейность и вырожденный случай
(нулевой определитель).
"""

from __future__ import annotations

from pathlib import Path

from mymath_backend import CoreNode, load_explanations
from mymath_backend import CoreNodeType as T
from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.results import CoreSolverVerticalResult, ResultGroupType
from mymath_backend.solver import registered_types, solve

EXPLANATIONS = Path(__file__).resolve().parents[1] / "mymath_backend" / "data" / "explanations.json"


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def var(name: str) -> CoreNode:
    return CoreNode.variable(name)


def node(t: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(t, *children)


def eq(left: CoreNode, right: CoreNode) -> CoreNode:
    return node(T.EQUALS, left, right)


def system(*equations: CoreNode) -> CoreNode:
    return node(T.SYSTEM, *equations)


def solution_map(problem: CoreNode) -> dict[str, str]:
    vertical = solve(problem).result.vertical()
    assert vertical is not None and vertical.solution is not None
    assert vertical.solution.type is T.LIST
    out: dict[str, str] = {}
    for equation in vertical.solution.children:
        out[equation.children[0].value or ""] = equation.children[1].value or ""
    return out


def step_keys(problem: CoreNode) -> list[str]:
    vertical = solve(problem).result.vertical()
    assert vertical is not None
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


class TestSolve:
    def test_simple_system(self) -> None:
        problem = system(
            eq(node(T.ADD, var("x"), var("y")), c("3")),
            eq(node(T.SUBTRACT, var("x"), var("y")), c("1")),
        )
        assert solution_map(problem) == {"x": "2", "y": "1"}

    def test_coefficients(self) -> None:
        problem = system(
            eq(
                node(
                    T.ADD,
                    node(T.MULTIPLY_IMPLICIT, c("2"), var("x")),
                    node(T.MULTIPLY_IMPLICIT, c("3"), var("y")),
                ),
                c("12"),
            ),
            eq(node(T.SUBTRACT, var("x"), var("y")), c("1")),
        )
        assert solution_map(problem) == {"x": "3", "y": "2"}

    def test_fraction_solution(self) -> None:
        problem = system(
            eq(node(T.ADD, var("x"), var("y")), c("1")),
            eq(node(T.SUBTRACT, var("x"), var("y")), c("0")),
        )
        assert solution_map(problem) == {"x": "1/2", "y": "1/2"}

    def test_single_step_with_header(self) -> None:
        problem = system(
            eq(node(T.ADD, var("x"), var("y")), c("3")),
            eq(node(T.SUBTRACT, var("x"), var("y")), c("1")),
        )
        assert step_keys(problem)[:3] == ["eq_linear", "system_substitute_value", "eq_linear"]
        vertical = solve(problem).result.vertical()
        assert vertical is not None
        assert [h.type for h in vertical.steps[0].step_headers] == ["eq_solve_short"]


class TestUnsupported:
    def test_parametric_solution(self) -> None:
        # Вырожденная система: бесконечно много решений.
        problem = system(
            eq(node(T.ADD, var("x"), var("y")), c("1")),
            eq(
                node(
                    T.ADD,
                    node(T.MULTIPLY_IMPLICIT, c("2"), var("x")),
                    node(T.MULTIPLY_IMPLICIT, c("2"), var("y")),
                ),
                c("2"),
            ),
        )
        vertical = solve(problem).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.type is T.LIST
        assert [part.type for part in vertical.solution.children] == [T.EQUALS, T.ELEMENT_OF]
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        assert keys == [
            "lesson_disc_system_matrix",
            "lesson_disc_eliminate",
            "lesson_disc_system_rank_infinite",
            "lesson_disc_system_free_unknowns_basic",
        ]


class TestExtended:
    def test_nonlinear(self) -> None:
        # xy = 1, x + y = 2 -> (1, 1).
        problem = system(
            eq(node(T.MULTIPLY, var("x"), var("y")), c("1")),
            eq(node(T.ADD, var("x"), var("y")), c("2")),
        )
        vertical = solve(problem).result.vertical()
        assert vertical is not None and vertical.solution is not None

    def test_three_unknowns(self) -> None:
        problem = system(
            eq(node(T.ADD, node(T.ADD, var("x"), var("y")), var("z")), c("6")),
            eq(node(T.SUBTRACT, var("x"), var("y")), c("0")),
            eq(node(T.SUBTRACT, var("y"), var("z")), c("0")),
        )
        assert solution_map(problem) == {"x": "2", "y": "2", "z": "2"}

    def test_one_unknown(self) -> None:
        problem = system(
            eq(node(T.ADD, var("x"), c("1")), c("3")),
            eq(node(T.SUBTRACT, var("x"), c("1")), c("1")),
        )
        vertical = solve(problem).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.children[1].value == "2"

    def test_three_equations(self) -> None:
        # Три уравнения с двумя неизвестными: решается через sympy.
        problem = system(
            eq(node(T.ADD, var("x"), var("y")), c("3")),
            eq(node(T.SUBTRACT, var("x"), var("y")), c("1")),
            eq(node(T.ADD, var("x"), c("1")), c("3")),
        )
        assert solution_map(problem) == {"x": "2", "y": "1"}


class TestParametricAndCheck:
    def test_parametric(self) -> None:
        # x + y = 2 и 2x + 2y = 4 — бесконечно много решений (x = 2 − y, y ∈ ℝ).
        problem = system(
            eq(node(T.ADD, var("x"), var("y")), c("2")),
            eq(
                node(
                    T.ADD,
                    node(T.MULTIPLY_IMPLICIT, c("2"), var("x")),
                    node(T.MULTIPLY_IMPLICIT, c("2"), var("y")),
                ),
                c("4"),
            ),
        )
        vertical = solve(problem).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.type is T.LIST
        assert [part.type for part in vertical.solution.children] == [T.EQUALS, T.ELEMENT_OF]
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        assert keys == [
            "lesson_disc_system_matrix",
            "lesson_disc_eliminate",
            "lesson_disc_system_rank_infinite",
            "lesson_disc_system_free_unknowns_basic",
        ]

    def test_no_solution(self) -> None:
        problem = system(
            eq(node(T.ADD, var("x"), var("y")), c("1")),
            eq(node(T.ADD, var("x"), var("y")), c("2")),
        )
        vertical = solve(problem).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.type is T.EMPTY
        keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
        assert keys == [
            "lesson_disc_system_matrix",
            "lesson_disc_eliminate",
            "lesson_disc_system_contradiction_row",
            "lesson_disc_system_rank_inconsistent",
        ]

    def test_check_true(self) -> None:
        problem = system(
            eq(node(T.ADD, var("x"), var("y")), c("3")),
            eq(node(T.SUBTRACT, var("x"), var("y")), c("1")),
        )
        vertical = solve(problem, command="system_check", args=[c("2"), c("1")]).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.type is T.TEXT
        assert vertical.solution.children[0].value == "true"

    def test_check_false(self) -> None:
        problem = system(
            eq(node(T.ADD, var("x"), var("y")), c("3")),
            eq(node(T.SUBTRACT, var("x"), var("y")), c("1")),
        )
        vertical = solve(problem, command="system_check", args=[c("1"), c("1")]).result.vertical()
        assert vertical is not None and vertical.solution is not None
        assert vertical.solution.children[0].value == "false"


class TestMethods:
    def test_two_solution_methods(self) -> None:
        # six cards for a 2x2 integer system.
        problem = system(
            eq(node(T.ADD, var("x"), var("y")), c("3")),
            eq(node(T.SUBTRACT, var("x"), var("y")), c("1")),
        )
        data = solve(problem)
        group = data.result.group(ResultGroupType.VERTICAL)
        assert group is not None
        assert len(group.entries) == 6
        assert group.select_method_text is not None
        keys = []
        for entry in group.entries:
            vertical = CoreSolverVerticalResult.from_contract(entry.result)
            keys.append([sub.description.type for step in vertical.steps for sub in step.substeps])
        assert keys[0][0] == "eq_linear" and keys[1][0] == "system_2x2_sum"
        assert keys[3][0] == "system_write_coeffs_to_mat"
        assert keys[4][0] == "system_2x2_cramer_rule"
        assert keys[5][0] == "system_2x2_inv_matrix_write_as_mat_eq"


class TestExplanationKeys:
    def test_keys_exist(self) -> None:
        explanations = load_explanations(str(EXPLANATIONS))
        for key in ("system_2x2_solve_elimination", "system_solve_short"):
            assert key in explanations
            assert explanations.arity(key) == 0
            assert "ARG" not in (explanations.raw_template(key, DEFAULT_LOCALE) or "")


class TestRegistration:
    def test_registered(self) -> None:
        assert T.SYSTEM in registered_types()


def test_two_by_two_system_gives_every_card_and_the_right_pair() -> None:
    # x+y=3, 2x+y=5 style systems get up to six cards.
    problem = system(
        eq(node(T.ADD, node(T.MULTIPLY_IMPLICIT, c("2"), var("x")), var("y")), c("5")),
        eq(node(T.SUBTRACT, var("x"), var("y")), c("1")),
    )
    assert solution_map(problem) == {"x": "2", "y": "1"}
    group = solve(problem).result.group(ResultGroupType.VERTICAL)
    assert group is not None and len(group.entries) == 6


def test_inverse_matrix_card_opens_the_product_on_the_app_screen() -> None:
    # Case ``sys_lin``: the app's «Умножьте матрицы» row has a «Подробнее»
    # screen — the row·column products, then «Вычислить». The native rows stop at
    # ``matrix_mul`` without one, so the derivation has to be built here.
    problem = system(
        eq(node(T.ADD, var("x"), var("y")), c("3")),
        eq(node(T.SUBTRACT, var("x"), var("y")), c("1")),
    )
    group = solve(problem).result.group(ResultGroupType.VERTICAL)
    assert group is not None
    inverse = CoreSolverVerticalResult.from_contract(group.entries[5].result)
    product = next(
        sub
        for step in inverse.steps
        for sub in step.substeps
        if sub.description.type == "matrix_mul"
    )
    assert product.subresult is not None
    assert [sub.description.type for step in product.subresult.steps for sub in step.substeps] == [
        "matrix_mul_row_col",
        "matrix_mul_row_col",
        "matrix_mul_row_col_simple",
        "matrix_mul_row_col_simple",
    ]
    # The derivation ends on the ordered pair of the system.
    pair = product.subresult.solution
    assert [[cell.value for cell in row.children] for row in pair.children] == [["2"], ["1"]]


def test_system_needing_a_multiplication_gets_every_card() -> None:
    # 2x+3y=8, x+y=3 multiplies the second equation by -2.
    problem = system(
        eq(
            node(
                T.ADD,
                node(T.MULTIPLY_IMPLICIT, c("2"), var("x")),
                node(T.MULTIPLY_IMPLICIT, c("3"), var("y")),
            ),
            c("8"),
        ),
        eq(node(T.ADD, var("x"), var("y")), c("3")),
    )
    assert solution_map(problem) == {"x": "1", "y": "2"}
    group = solve(problem).result.group(ResultGroupType.VERTICAL)
    assert group is not None and len(group.entries) == 6


def test_system_with_an_isolated_unknown_gets_elimination_and_comparison_too() -> None:
    # y=2x, x+y=6 -> six cards; the unknowns are ordered x, y.
    problem = system(
        eq(var("y"), node(T.MULTIPLY_IMPLICIT, c("2"), var("x"))),
        eq(node(T.ADD, var("x"), var("y")), c("6")),
    )
    assert solution_map(problem) == {"x": "2", "y": "4"}
    group = solve(problem).result.group(ResultGroupType.VERTICAL)
    assert group is not None and len(group.entries) == 6


def test_system_with_a_fractional_solution_gets_all_six_cards() -> None:
    # 3x+2y=12, x-y=1 has the solution (14/5, 9/5) and six cards.
    problem = system(
        eq(
            node(
                T.ADD,
                node(T.MULTIPLY_IMPLICIT, c("3"), var("x")),
                node(T.MULTIPLY_IMPLICIT, c("2"), var("y")),
            ),
            c("12"),
        ),
        eq(node(T.SUBTRACT, var("x"), var("y")), c("1")),
    )
    assert solution_map(problem) == {"x": "14/5", "y": "9/5"}
    group = solve(problem).result.group(ResultGroupType.VERTICAL)
    assert group is not None and len(group.entries) == 6


def test_three_by_three_system_has_the_cramer_card() -> None:
    # x+y+z=6, x-y=-1, y+z=5 -> (1, 2, 3), Cramer's rule in 7 rows.
    problem = system(
        eq(node(T.ADD, node(T.ADD, var("x"), var("y")), var("z")), c("6")),
        eq(node(T.SUBTRACT, var("x"), var("y")), c("-1")),
        eq(node(T.ADD, var("y"), var("z")), c("5")),
    )
    assert solution_map(problem) == {"x": "1", "y": "2", "z": "3"}
    group = solve(problem).result.group(ResultGroupType.VERTICAL)
    assert group is not None
    shapes = [[len(s["substeps"]) for s in e.result["steps"]] for e in group.entries]
    assert [1, 1, 4, 1, 1, 1, 1] in shapes  # Cramer
    assert [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1] in shapes  # substitution, 13 rows
    assert [1, 1, 1, 1, 2, 1, 1, 1, 1, 1] in shapes  # Gauss-Jordan
