"""Student-visible determinant behaviour (solver batch 1).

Each test states, in solver terms, something a student should be able to see:
a bare square matrix is its determinant, the 2x2 detail is the ``ad - bc``
formula, the 3x3 method is named for what it computes, 4x4/5x5 expand along the
line with the most zeros, letters are handled, a determinant equation and a
singular inverse are verdicts rather than errors, and the theory link points at
determinants instead of the discriminant.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
import sympy

from mymath_backend import CoreNode, service
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.solver import solve
from mymath_backend.solver.base import SolveError, Step
from mymath_backend.solver.sympy_bridge import from_sympy, to_sympy
from mymath_backend.teaching_discrete import TEMPLATES, enrich

_DET_NODES = {
    T.DETERMINANT,
    T.DETERMINANT2,
    T.DETERMINANT3,
    T.DETERMINANT3_SARRUS,
    T.DETERMINANT4,
    T.DETERMINANT5,
}


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def row(*cells: CoreNode) -> CoreNode:
    return CoreNode.node(T.MATRIX_ROW, *cells)


def mat(*rows: CoreNode) -> CoreNode:
    return CoreNode.node(T.MATRIX, *rows)


def mat_proto(matrix: sympy.Matrix) -> str:
    rows = ",".join(
        "{mat_row(" + ",".join(f"{{{sympy.sstr(value)}}}" for value in matrix.row(i)) + ")}"
        for i in range(matrix.rows)
    )
    return "{mat(" + rows + ")}"


def det_proto(matrix: sympy.Matrix) -> str:
    flat = ",".join(f"{{{sympy.sstr(value)}}}" for value in matrix)
    return "{det(" + flat + ")}"


def response(source: str) -> dict[str, Any]:
    return service.solve_request(parse_protocol(source).to_contract(), render=True, locale="ru")


def vertical(source: str) -> Any:
    result = solve(parse_protocol(source)).result.vertical()
    assert result is not None
    return result


def solution_of(source: str) -> CoreNode:
    solution = vertical(source).solution
    assert solution is not None
    return solution


def step_keys(result: Any) -> list[str]:
    return [sub.description.type for step in result.steps for sub in step.substeps]


def texts(value: Any) -> Iterator[str]:
    """Every explanation text in a contract tree."""
    if isinstance(value, dict):
        explanation = value.get("explanation")
        if isinstance(explanation, dict) and explanation.get("text"):
            yield explanation["text"]
        for child in value.values():
            yield from texts(child)
    elif isinstance(value, list):
        for child in value:
            yield from texts(child)


def nodes(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)


def detail(step: Step) -> list[Step]:
    """The nested "Подробнее" steps of a determinant step."""
    assert enrich(step) is not None
    assert step.subresult is not None
    children = list(step.subresult)
    assert children
    for child in children:
        assert child.key in TEMPLATES
    return children


def det_value(part: CoreNode) -> sympy.Expr:
    size = sympy.integer_nthroot(len(part.children), 2)[0]
    return sympy.Matrix(size, size, [to_sympy(cell) for cell in part.children]).det()


def without_det(part: CoreNode) -> CoreNode:
    """Replace every nested determinant by its value: ``to_sympy`` has no det node."""
    if part.type in _DET_NODES:
        return from_sympy(det_value(part))
    if not part.children:
        return part
    return CoreNode(
        type=part.type,
        value=part.value,
        children=[without_det(child) for child in part.children],
    )


def value(part: CoreNode | None) -> sympy.Expr:
    assert part is not None
    if part.type in _DET_NODES:
        return det_value(part)
    return to_sympy(without_det(part))


# ── 1. a bare square matrix is its determinant ────────────────────────


@pytest.mark.parametrize(
    "matrix",
    [
        sympy.Matrix([[3, 5], [2, 4]]),
        sympy.Matrix([[1, 2, 3], [4, 5, 6], [7, 8, 10]]),
        sympy.Matrix([[2, 1, 0, 3], [1, 0, 2, 1], [3, 2, 1, 0], [0, 1, 2, 1]]),
        sympy.Matrix(
            [
                [1, 2, 3, 4, 5],
                [2, 1, 4, 3, 0],
                [3, 0, 1, 2, 4],
                [4, 3, 2, 1, 5],
                [5, 4, 3, 2, 1],
            ]
        ),
    ],
)
def test_bare_square_matrix_is_solved_as_its_determinant(matrix: sympy.Matrix) -> None:
    result = vertical(mat_proto(matrix))
    assert result.solution is not None
    assert to_sympy(result.solution) == matrix.det()
    assert "matrix_det_rewrite" in step_keys(result)


def test_bare_non_square_matrix_stays_a_matrix() -> None:
    result = vertical(mat_proto(sympy.Matrix([[1, 2], [3, 4], [5, 6]])))
    assert result.solution is not None and result.solution.type is T.MATRIX


# ── 2. the 2x2 detail is the ad - bc formula ──────────────────────────


def test_2x2_detail_uses_the_formula_not_a_first_row_expansion() -> None:
    matrix = sympy.Matrix([[3, 5], [2, 4]])
    children = detail(Step(from_sympy(matrix), from_sympy(matrix.det()), "det2_determinant_rule"))
    assert all(child.key != "lesson_disc_det_expand" for child in children)
    expansion = next(child for child in children if child.key == "lesson_disc_det2_expand")
    # the nested determinant keeps its row structure: a 2x2 node, not a flat column
    assert expansion.left is not None and expansion.left.type is T.DETERMINANT2
    assert expansion.right is not None and expansion.right.type is T.SUBTRACT
    for child in children:
        assert sympy.simplify(value(child.left) - value(child.right)) == 0


def test_2x2_difference_never_renders_as_a_sum_of_a_negative_product() -> None:
    matrix = sympy.Matrix([[3, 5], [2, 4]])
    children = detail(Step(from_sympy(matrix), from_sympy(matrix.det()), "det2_determinant_rule"))
    expansion = next(child for child in children if child.key == "lesson_disc_det2_expand")
    assert expansion.right is not None
    assert not any(
        part.type is T.ADD and any(grand.type is T.NEGATIVE for grand in part.children)
        for part in expansion.right.walk()
    )
    out = response(mat_proto(matrix))
    assert "первой строке" not in " ".join(texts(out))


# ── 3. the 3x3 method name matches the computation ────────────────────


def test_3x3_names_the_first_row_expansion_not_sarrus() -> None:
    matrix = sympy.Matrix([[1, 2, 3], [4, 5, 6], [7, 8, 10]])
    source = det_proto(matrix)
    assert to_sympy(solution_of(source)) == matrix.det()
    # the app: the 3x3 expands like a larger determinant (Laplace rows).
    keys = step_keys(vertical(source))
    assert keys[0] == "det_laplace_rule_row" and "det_evaluate" in keys
    assert "Саррюс" not in " ".join(texts(response(source)))
    children = detail(Step(from_sympy(matrix), from_sympy(matrix.det()), "det3_cofactor_eval"))
    # the three 2x2 minors, then the expansion with alternating signs + − +
    minors = [child for child in children if child.key == "lesson_disc_minor"]
    assert [to_sympy(arg) for child in minors for arg in child.args[1:]] == [1, 2, 3]
    expansion = next(child for child in children if child.key == "lesson_disc_det_expand")
    assert expansion.right is not None
    assert expansion.right.type is T.ADD  # (a·M1 − b·M2) + c·M3
    assert expansion.right.children[0].type is T.SUBTRACT


# ── 4. 4x4 and 5x5 expand along the line with the most zeros ──────────


def test_4x4_with_a_zero_column_expands_along_that_column() -> None:
    matrix = sympy.Matrix(
        [
            [2, 0, 0, 1],
            [3, 1, 0, 1],
            [4, 0, 1, 1],
            [5, 0, 0, 7],
        ]
    )
    source = det_proto(matrix)
    assert to_sympy(solution_of(source)) == matrix.det()
    keys = step_keys(vertical(source))
    assert keys[0] == "det_laplace_rule_col" and "det_evaluate" in keys
    children = detail(Step(from_sympy(matrix), from_sympy(matrix.det()), "det_laplace_rule_col"))
    assert any(child.key == "lesson_disc_det_expand_col" for child in children)
    for child in children:
        assert sympy.simplify(value(child.left) - value(child.right)) == 0


def test_4x4_and_5x5_minors_are_all_expanded() -> None:
    matrix = sympy.Matrix(
        [
            [1, 2, 3, 4, 5],
            [2, 1, 4, 3, 0],
            [3, 0, 1, 2, 4],
            [4, 3, 2, 1, 5],
            [5, 4, 3, 2, 1],
        ]
    )
    source = det_proto(matrix)
    assert to_sympy(solution_of(source)) == matrix.det()
    children = detail(Step(from_sympy(matrix), from_sympy(matrix.det()), "det_laplace_rule_row"))

    def nested(steps: list[Step]) -> Iterator[Step]:
        for step in steps:
            if step.subresult:
                yield from step.subresult
                yield from nested(list(step.subresult))

    below = list(nested(children))
    # every mini-order determinant is nested below its own minor stage and every
    # 3×3 inside reaches its 2×2 minors
    assert any(child.key == "lesson_disc_det_expand" for child in below)
    assert any(child.key == "lesson_disc_det2_expand" for child in below)
    for child in children:
        assert sympy.simplify(value(child.left) - value(child.right)) == 0


# ── 5. letters and functions ──────────────────────────────────────────


@pytest.mark.parametrize(
    "source,expected",
    [
        (
            "{det({a},{b},{c},{d})}",
            sympy.Symbol("a") * sympy.Symbol("d") - sympy.Symbol("b") * sympy.Symbol("c"),
        ),
        ("{det({x},{1},{1},{x})}", sympy.Symbol("x") ** 2 - 1),
        ("{det({x},{1},{2},{z})}", sympy.Symbol("x") * sympy.Symbol("z") - 2),
    ],
)
def test_symbolic_2x2_determinant(source: str, expected: sympy.Expr) -> None:
    assert sympy.simplify(to_sympy(solution_of(source)) - expected) == 0


def test_trigonometric_determinant_is_one_with_an_expanded_step_first() -> None:
    source = "{det({cos({a})},{0-sin({a})},{sin({a})},{cos({a})})}"
    result = vertical(source)
    assert to_sympy(result.solution) == 1
    # the expanded form is shown, then the simplification
    assert step_keys(result) == ["det2_determinant_rule", "simplify"]


def test_symbolic_3x3_determinant() -> None:
    # ``e`` and ``i`` are reserved (Euler's number and the imaginary unit):
    # the phone's «e» key sends a VARIABLE node but it means 2.718…
    matrix = sympy.Matrix(
        [
            [sympy.Symbol("a"), sympy.Symbol("b"), sympy.Symbol("c")],
            [sympy.Symbol("d"), sympy.Symbol("k"), sympy.Symbol("f")],
            [sympy.Symbol("g"), sympy.Symbol("h"), sympy.Symbol("j")],
        ]
    )
    source = "{det(" + ",".join(f"{{{sympy.sstr(v)}}}" for v in matrix) + ")}"
    assert sympy.simplify(to_sympy(solution_of(source)) - matrix.det()) == 0


# ── 6. an equation with a determinant ─────────────────────────────────


@pytest.mark.parametrize(
    "source,roots",
    [
        ("{=({det({x},{2},{3},{x})},{0})}", {-sympy.sqrt(6), sympy.sqrt(6)}),
        ("{=({mat({mat_row({x},{2})},{mat_row({3},{x})})},{0})}", {-sympy.sqrt(6), sympy.sqrt(6)}),
        (
            "{=({det({x},{1},{0},{1},{x},{1},{0},{1},{x})},{0})}",
            {sympy.Integer(0), -sympy.sqrt(2), sympy.sqrt(2)},
        ),
    ],
)
def test_determinant_equation(source: str, roots: set[sympy.Expr]) -> None:
    out = response(source)
    solution = out["result"]["solution"]
    assert solution is not None
    found = set()
    for child in solution["children"]:
        assert child["type"] == "EQUALS"
        found.add(sympy.simplify(to_sympy(CoreNode.from_contract(child["children"][1]))))
    assert found == roots
    first = out["result"]["groups"][0]["entries"][0]["result"]["steps"][0]["substeps"][0]
    assert first["description"]["type"] == "det_expand_equation"


def test_a_matrix_product_is_not_a_determinant_equation() -> None:
    # A·X = B and a numeric matrix are not determinant equations: only a square
    # determinant/matrix side carrying unknowns is expanded.
    from mymath_backend.solver.matrices import determinant_expansion

    a = mat(row(c("1"), c("2")), row(c("3"), c("4")))
    unknown = mat(
        row(CoreNode.variable("x"), CoreNode.variable("z")),
        row(CoreNode.variable("y"), CoreNode.variable("w")),
    )
    product = CoreNode.node(T.MULTIPLY, a, unknown)
    assert determinant_expansion(product) is None
    assert determinant_expansion(a) is None
    # control: a square matrix with an unknown does expand
    assert determinant_expansion(unknown) is not None


# ── 7. a singular inverse is a verdict ────────────────────────────────


def test_singular_inverse_is_a_verdict_with_the_determinant_shown() -> None:
    source = "{mat({mat_row({1},{2})},{mat_row({2},{4})})^(-1)}"
    out = response(source)
    solution = out["result"]["solution"]
    assert solution is not None and solution["type"] == "EMPTY"
    keys = [node["description"]["type"] for node in nodes(out) if "description" in node]
    assert "matrix_inv_det_zero" in keys
    assert keys.index("det2_determinant_rule") < keys.index("matrix_inv_det_zero")
    verdict = next(
        (node.get("explanation") or {}).get("text", "")
        for node in nodes(out)
        if (node.get("description") or {}).get("type") == "matrix_inv_det_zero"
    )
    assert "обратной матрицы нет" in verdict


# ── 8. the theory link is determinant theory ──────────────────────────


def test_determinant_steps_do_not_open_the_discriminant() -> None:
    assert service.theory("lesson_disc_minor", "ru")["id"] == "discrete:discrete_determinant"
    assert service.theory("lesson_disc_det2_expand", "ru")["id"] == "discrete:discrete_determinant"
    out = response("{det({2},{1},{3},{0},{4},{-1},{5},{2},{2})}")
    articles = [
        node["explanation"]["theory"]["id"]
        for node in nodes(out)
        if isinstance(node.get("explanation"), dict) and node["explanation"].get("theory")
    ]
    assert articles
    assert not any("discriminant" in article for article in articles)
    assert any("determinant" in article for article in articles)


def test_discriminant_steps_keep_the_discriminant_theory() -> None:
    assert service.theory("eq_quad_disc", "ru")["id"] == "discriminant"
    assert service.theory("lesson_disc_square", "ru")["id"] == "discriminant"
    assert service.theory("lesson_discriminant", "ru")["id"] == "discriminant"


# ── 9. the 3x3 detail is the textbook order ───────────────────────────


def test_3x3_expansion_writes_the_minors_as_determinants() -> None:
    matrix = sympy.Matrix([[1, 2, 3], [4, 5, 6], [7, 8, 10]])
    children = detail(Step(from_sympy(matrix), from_sympy(matrix.det()), "det3_cofactor_eval"))
    expansion = children[0]
    assert expansion.key == "lesson_disc_det_expand"
    assert expansion.left is not None and expansion.left.type is T.DETERMINANT3
    # the signs alternate: (t1 − t2) + t3
    assert expansion.right is not None and expansion.right.type is T.ADD
    assert expansion.right.children[0].type is T.SUBTRACT
    products = [
        part
        for part in expansion.right.walk()
        if part.type is T.MULTIPLY and any(cell.type is T.DETERMINANT2 for cell in part.children)
    ]
    assert len(products) == 3
    minors = [child for child in children if child.key == "lesson_disc_minor"]
    assert len(minors) == 3
    for minor in minors:
        assert minor.left is not None and minor.left.type is T.DETERMINANT2
        # the minor's own ad − bc arithmetic is that stage's nested detail
        assert minor.subresult is not None
        assert [child.key for child in minor.subresult] == [
            "lesson_disc_det2_expand",
            "lesson_disc_arithmetic",
        ]
    total = children[-1]
    assert total.key == "lesson_disc_arithmetic"
    assert total.left is not None and not any(part.type in _DET_NODES for part in total.left.walk())
    assert to_sympy(solution_of(det_proto(matrix))) == matrix.det()


# ── 10. a 4x4/5x5 keeps the same shape one level deeper ───────────────


def test_4x4_detail_is_shallow_and_names_the_line_with_zeros() -> None:
    matrix = sympy.Matrix([[2, 0, 0, 1], [3, 1, 0, 1], [4, 0, 1, 1], [5, 0, 0, 7]])
    out = response(det_proto(matrix))
    children = detail(Step(from_sympy(matrix), from_sympy(matrix.det()), "det_laplace_rule_col"))
    assert len(children) <= 6
    expansion = children[0]
    assert expansion.key == "lesson_disc_det_expand_col"
    # column 2 is the one with the most zeros, and the step says so
    assert expansion.args[0].value == "2"
    assert "нулей" in " ".join(texts(out))
    minors = [child for child in children if child.key == "lesson_disc_minor"]
    assert len(minors) == 1  # the zero terms are dropped, not written
    assert minors[0].left is not None and minors[0].left.type is T.DETERMINANT3
    assert minors[0].subresult is not None
    # the non-zero minor's nested detail is the 3x3 shape of item 1
    assert next(iter(minors[0].subresult)).key == "lesson_disc_det_expand"
    assert [child.key for child in minors[0].subresult].count("lesson_disc_minor") == 3
    assert children[-1].key == "lesson_disc_arithmetic"


def test_4x4_without_zeros_stays_within_six_stages() -> None:
    matrix = sympy.Matrix([[2, 1, 3, 4], [1, 0, 2, 3], [3, 2, 1, 0], [4, 1, 2, 5]])
    children = detail(Step(from_sympy(matrix), from_sympy(matrix.det()), "det_laplace_rule_row"))
    assert children[0].key.endswith(("_row", "_col"))
    assert 2 <= len(children) <= 6
    for child in children:
        assert sympy.simplify(value(child.left) - value(child.right)) == 0


# ── 11. matrix arithmetic shows each cell ─────────────────────────────


def stage_parts(out: dict[str, Any]) -> list[dict[str, Any]]:
    result = out["result"]["groups"][0]["entries"][0]["result"]
    return [sub for step in result["steps"] for sub in step["substeps"]]


def command(source: str, name: str, *args: str, locale: str = "ru") -> dict[str, Any]:
    return service.solve_request(
        parse_protocol(source).to_contract(),
        {"command": name, "args": [parse_protocol(arg).to_contract() for arg in args]},
        render=True,
        locale=locale,
    )


def test_matrix_product_shows_every_cell_as_row_times_column() -> None:
    first = "{mat({mat_row({1},{2})},{mat_row({3},{4})})}"
    second = "{mat({mat_row({5},{6})},{mat_row({7},{8})})}"
    out = command(first, "matrix_multiply", second)
    parts = stage_parts(out)
    assert [part["description"]["type"] for part in parts] == [
        "matrix_mul",
        "matrix_mul_row_col_simple",
        "matrix_mul_row_col_simple",
    ]
    sums = CoreNode.from_contract(parts[0]["right"])
    cell = sums.children[0].children[0]  # c11 = 1·5 + 2·7
    assert cell.type is T.ADD
    assert cell.children[0].type is T.MULTIPLY
    assert sympy.simplify(to_sympy(cell) - 19) == 0
    # one stage per row of the result, each row evaluated in turn
    first_row = CoreNode.from_contract(parts[1]["right"]).children[0]
    assert to_sympy(first_row.children[0]) == 19 and to_sympy(first_row.children[1]) == 22
    answer = CoreNode.from_contract(parts[-1]["right"])
    assert to_sympy(answer) == sympy.Matrix([[19, 22], [43, 50]])


def test_matrix_difference_is_elementwise_and_then_evaluated() -> None:
    first = "{mat({mat_row({1},{2})},{mat_row({3},{4})})}"
    second = "{mat({mat_row({5},{6})},{mat_row({7},{8})})}"
    out = command(first, "matrix_subtract", second)
    parts = stage_parts(out)
    assert parts[0]["description"]["type"] == "matrix_sub"
    differences = CoreNode.from_contract(parts[0]["right"])
    assert differences.children[0].children[0].type is T.SUBTRACT
    assert to_sympy(differences.children[0].children[0]) == -4
    assert {part["description"]["type"] for part in parts[1:]} == {"sub"}
    solution = out["result"]["solution"]
    assert solution is not None
    assert to_sympy(CoreNode.from_contract(solution)) == sympy.Matrix([[-4, -4], [-4, -4]])


def test_scalar_multiple_puts_the_factor_into_every_cell() -> None:
    matrix = "{mat({mat_row({1},{2})},{mat_row({3},{4})})}"
    out = command(matrix, "matrix_scale", "{3}")
    parts = stage_parts(out)
    assert parts[0]["description"]["type"] == "matrix_mul_scalar"
    products = CoreNode.from_contract(parts[0]["right"])
    assert products.children[0].children[0].type is T.MULTIPLY
    assert to_sympy(products.children[0].children[0]) == 3
    assert all(part["description"]["type"] == "mul" for part in parts[1:])
    assert len(parts) == 5


# ── 12. transpose names the rule ──────────────────────────────────────


def test_transpose_shows_rows_becoming_columns() -> None:
    matrix = "{mat({mat_row({1},{2})},{mat_row({3},{4})})}"
    out = command(matrix, "matrix_transpose")
    parts = stage_parts(out)
    assert [part["description"]["type"] for part in parts] == ["matrix_transpose"]
    assert to_sympy(CoreNode.from_contract(parts[0]["right"])) == sympy.Matrix([[1, 3], [2, 4]])
    assert "строки становятся столбцами" in " ".join(texts(out)).lower()


# ── 13. every system method says which method it is ───────────────────


def test_cramer_system_names_every_offered_method() -> None:
    out = response("system({=({2x+3y},{7})},{=({x-y},{1})})")
    group = out["result"]["groups"][0]
    assert group["selectMethodText"]["explanation"]["text"] == "Выберите способ"
    titles = [entry["result"]["header"]["explanation"]["text"] for entry in group["entries"]]
    assert len(titles) == 6
    assert len(set(titles)) == 6
    cramer = next(index for index, title in enumerate(titles) if "Крамера" in title)
    first = group["entries"][cramer]["result"]["steps"][0]["substeps"][0]
    assert first["description"]["type"] == "system_2x2_cramer_rule"


@pytest.mark.parametrize("op, kind", [("+", T.ADD), ("-", T.SUBTRACT), ("*", T.MULTIPLY)])
def test_matrix_arithmetic_starts_from_the_whole_expression(op: str, kind: T) -> None:
    a = "mat({mat_row({1},{2})},{mat_row({3},{4})})"
    b = "mat({mat_row({5},{6})},{mat_row({7},{8})})"
    first = vertical("{" + a + op + b + "}").steps[0].substeps[0]
    assert first.left is not None and first.left.type is kind  # not just A


def test_subtraction_without_zeros_has_no_remove_zero_header() -> None:
    a = "mat({mat_row({1},{2})},{mat_row({3},{4})})"
    b = "mat({mat_row({5},{6})},{mat_row({7},{8})})"
    data = vertical("{" + a + "-" + b + "}")
    assert all(h.type != "remove_zero" for step in data.steps for h in step.step_headers)


# ── 14. rank: row echelon form, one elementary operation per stage ─────

_ROW_OPERATIONS = {"matrix_inv_swap_row", "mat_divide_row", "mul_row_add", "mat_mul_row"}


def test_rank_reduces_to_echelon_form_one_operation_per_stage() -> None:
    source = "{mat({mat_row({2},{1})},{mat_row({1},{1})},{mat_row({0},{3})})}"
    out = command(source, "matrix_rank")
    parts = stage_parts(out)
    keys = [part["description"]["type"] for part in parts]
    assert keys[0] == "lesson_disc_rank_echelon"
    assert keys[-1] == "lesson_disc_rank_count"
    assert set(keys[1:-1]) <= _ROW_OPERATIONS
    for part in parts[1:-1]:
        before = sympy.Matrix(to_sympy(CoreNode.from_contract(part["left"])))
        after = to_sympy(CoreNode.from_contract(part["right"]))
        args = [to_sympy(CoreNode.from_contract(arg)) for arg in part["description"]["args"]]
        if part["description"]["type"] == "matrix_inv_swap_row":
            before.row_swap(int(args[0]) - 1, int(args[1]) - 1)
        elif part["description"]["type"] == "mat_divide_row":
            # the stage says what it divides by; the row is the one that changed
            divisor = args[0]
            changed = [
                row
                for row in range(before.rows)
                if any(before[row, col] != after[row, col] for col in range(before.cols))
            ]
            assert len(changed) == 1
            before[changed[0], :] = before[changed[0], :] / divisor
        else:
            # each elimination stage names its row, the factor and the target row
            source_row, factor, target = int(args[0]) - 1, args[1], int(args[2]) - 1
            before[target, :] = before[target, :] + factor * before[source_row, :]
        assert before == after
    assert to_sympy(CoreNode.from_contract(out["result"]["solution"])) == 2
    assert "ненулевых строк: 2" in " ".join(texts(out)).lower()


def test_rank_of_the_zero_matrix_is_zero() -> None:
    out = command("{mat({mat_row({0},{0},{0})},{mat_row({0},{0},{0})})}", "matrix_rank")
    parts = stage_parts(out)
    assert [part["description"]["type"] for part in parts] == [
        "lesson_disc_rank_echelon",
        "lesson_disc_rank_count",
    ]
    assert to_sympy(CoreNode.from_contract(out["result"]["solution"])) == 0
    assert "ненулевых строк: 0" in " ".join(texts(out)).lower()


@pytest.mark.parametrize(
    "matrix",
    [
        sympy.Matrix([[0]]),
        sympy.Matrix([[5]]),
        sympy.Matrix([[0, 0, 0]]),
        sympy.Matrix([[1, 2, 3], [2, 4, 6]]),
        sympy.Matrix([[1, 2], [2, 4], [0, 1]]),
        sympy.Matrix([[sympy.Rational(1, 2), 3], [2, 5]]),
        sympy.Matrix([[1, 2, 3, 4, 5], [0, 1, 1, 1, 1], [0, 0, 0, 0, 0], [0, 0, 0, 0, 1]]),
    ],
)
def test_rank_matches_sympy_for_any_shape_and_exact_fractions(matrix: sympy.Matrix) -> None:
    out = command(mat_proto(matrix), "matrix_rank")
    assert to_sympy(CoreNode.from_contract(out["result"]["solution"])) == matrix.rank()


def test_rank_keeps_a_fractional_elimination_exact() -> None:
    out = command("{mat({mat_row({2},{1})},{mat_row({1},{1})})}", "matrix_rank")
    parts = stage_parts(out)
    divides = [p for p in parts if p["description"]["type"] == "mat_divide_row"]
    divide = divides[-1]  # the second pivot is 1/2
    divisor = CoreNode.from_contract(divide["description"]["args"][0])
    assert to_sympy(divisor) == sympy.Rational(1, 2)  # second pivot needs 1/2, not a float


# ── 15. A·X = B and X·A = B ───────────────────────────────────────────

_A = "{mat({mat_row({1},{2})},{mat_row({3},{4})})}"
_B = "{mat({mat_row({5},{6})},{mat_row({7},{8})})}"


@pytest.mark.parametrize(
    "name, expected",
    [
        ("matrix_solve_left", sympy.Matrix([[-3, -4], [4, 5]])),  # A⁻¹B
        ("matrix_solve_right", sympy.Matrix([[-1, 2], [-2, 3]])),  # BA⁻¹
    ],
)
def test_solve_writes_the_formula_then_uses_the_inverse_and_the_product(
    name: str, expected: sympy.Matrix
) -> None:
    out = command(_A, name, _B)
    parts = stage_parts(out)
    keys = [part["description"]["type"] for part in parts]
    assert keys[0] in ("lesson_disc_solve_left", "lesson_disc_solve_right")
    assert keys[1] == "matrix_inv_find_smpl"  # no empty "по формуле" stage before Gauss
    assert "matrix_mul" in keys and "matrix_mul_row_col_simple" in keys
    assert keys[-1] == "lesson_disc_solve_answer"
    # stage 1 writes A·X = B (or X·A = B) and the formula X = A⁻¹B on the right
    formula = CoreNode.from_contract(parts[0]["right"])
    assert formula.type is T.EQUALS
    product = formula.children[1]
    assert product.type is T.MULTIPLY
    assert any(child.type is T.POWER for child in product.children)
    assert to_sympy(CoreNode.from_contract(out["result"]["solution"])) == expected
    assert to_sympy(CoreNode.from_contract(parts[-1]["right"])) == expected


def test_solve_left_multiplies_on_the_left_and_solve_right_on_the_right() -> None:
    left = command(_A, "matrix_solve_left", _B)
    right = command(_A, "matrix_solve_right", _B)
    first_left = CoreNode.from_contract(stage_parts(left)[0]["left"])
    first_right = CoreNode.from_contract(stage_parts(right)[0]["left"])
    assert first_left.children[0].type is T.MULTIPLY  # A·X
    assert first_left.children[0].children[0].type is T.MATRIX
    assert first_right.children[0].type is T.MULTIPLY  # X·A
    assert first_right.children[0].children[0].type is T.VARIABLE
    assert first_left.children[0].children[1].type is T.VARIABLE
    assert first_right.children[0].children[1].type is T.MATRIX


@pytest.mark.parametrize("name", ["matrix_solve_left", "matrix_solve_right"])
def test_solve_with_a_singular_coefficient_is_the_same_verdict_as_the_inverse(
    name: str,
) -> None:
    singular = "{mat({mat_row({1},{2})},{mat_row({2},{4})})}"
    out = command(singular, name, "{mat({mat_row({1},{0})},{mat_row({0},{1})})}")
    solution = out["result"]["solution"]
    assert solution is not None and solution["type"] == "EMPTY"
    keys = [node["description"]["type"] for node in nodes(out) if "description" in node]
    assert "matrix_inv_det_zero" in keys
    assert "обратной матрицы нет" in " ".join(texts(out))


@pytest.mark.parametrize(
    "name, second",
    [
        # A·X = B needs B with as many rows as A
        ("matrix_solve_left", "{mat({mat_row({1},{2})},{mat_row({3},{4})},{mat_row({5},{6})})}"),
        # X·A = B needs B with as many columns as A
        ("matrix_solve_right", "{mat({mat_row({1},{2},{3},{4})},{mat_row({5},{6},{7},{8})})}"),
    ],
)
def test_solve_size_mismatch_uses_the_existing_product_error(name: str, second: str) -> None:
    with pytest.raises(SolveError) as info:
        command(_A, name, second)
    assert info.value.explanation_key == "matrix_mul_diff_size_error"


def test_solve_with_a_non_square_coefficient_uses_the_inverse_error() -> None:
    with pytest.raises(SolveError) as info:
        command("{mat({mat_row({1},{2},{3})},{mat_row({4},{5},{6})})}", "matrix_solve_right", _B)
    assert info.value.explanation_key == "matrix_inv_undef"


# ── 16. every new step has a Russian and an English text ───────────────

_NEW_KEYS = (
    "lesson_disc_rank_echelon",
    "lesson_disc_rank_count",
    "lesson_disc_solve_left",
    "lesson_disc_solve_right",
    "lesson_disc_solve_answer",
)


@pytest.mark.parametrize("locale", ["ru", "en"])
def test_rank_and_solve_explanations_have_no_placeholders(locale: str) -> None:
    outputs = [
        command(_A, "matrix_rank", locale=locale),
        command(_A, "matrix_solve_left", _B, locale=locale),
        command(_A, "matrix_solve_right", _B, locale=locale),
    ]
    for out in outputs:
        for node in nodes(out):
            explanation = node.get("explanation")
            if not isinstance(explanation, dict):
                continue
            assert explanation.get("missing") is False, explanation.get("key")
            assert "?? step_" not in explanation.get("text", "")
            assert "ARG" not in explanation.get("text", "")
    if locale == "ru":
        assert "ненулевых строк" in " ".join(texts(outputs[0])).lower()
    else:
        assert "nonzero rows" in " ".join(texts(outputs[0])).lower()


def test_rank_and_solve_keys_exist_in_both_languages() -> None:
    for key in _NEW_KEYS:
        for locale in ("ru", "default"):
            template = service.explanations().raw_template(key, locale)
            assert template is not None and template.strip(), (key, locale)


# ── 17. «Обратная» is the adjugate formula; «Обратная (Гаусс)» stays Gauss ──

_A2 = sympy.Matrix([[2, 1], [5, 3]])
_A3 = sympy.Matrix([[1, 2, 3], [0, 1, 4], [5, 6, 0]])

_ADJ_KEYS = (
    "lesson_disc_adj_det",
    "lesson_disc_adj_cofactors",
    "lesson_disc_adj_cofactors_row",
    "lesson_disc_adj_transpose",
    "lesson_disc_adj_formula",
)


def cofactor_matrix(matrix: sympy.Matrix) -> sympy.Matrix:
    return sympy.Matrix(
        matrix.rows,
        matrix.cols,
        lambda i, j: (-1) ** (i + j) * matrix.minor_submatrix(i, j).det(),
    )


def nested_keys(part: dict[str, Any]) -> list[str]:
    assert isinstance(part.get("subresult"), dict)
    return [
        sub["description"]["type"]
        for step in part["subresult"]["steps"]
        for sub in step["substeps"]
    ]


def part_keys(out: dict[str, Any]) -> list[str]:
    return [part["description"]["type"] for part in stage_parts(out)]


def test_inverse_2x2_is_the_adjugate_formula_stage_by_stage() -> None:
    out = command(mat_proto(_A2), "matrix_inverse")
    assert part_keys(out) == [
        "matrix_inv_find_formula",
        "lesson_disc_adj_det",
        "lesson_disc_adj_cofactors",
        "lesson_disc_adj_transpose",
        "lesson_disc_adj_formula",
    ]
    parts = stage_parts(out)
    assert to_sympy(CoreNode.from_contract(parts[1]["right"])) == _A2.det()
    assert to_sympy(CoreNode.from_contract(parts[2]["right"])) == cofactor_matrix(_A2)
    # the minors of a 2×2 are the entries themselves
    assert to_sympy(CoreNode.from_contract(parts[2]["left"])) == sympy.Matrix([[3, 5], [1, 2]])
    assert to_sympy(CoreNode.from_contract(parts[3]["right"])) == cofactor_matrix(_A2).T
    # det A = 1: A⁻¹ = adj A at once, no «1·x» cell stages
    assert to_sympy(CoreNode.from_contract(parts[4]["right"])) == cofactor_matrix(_A2).T
    assert to_sympy(CoreNode.from_contract(out["result"]["solution"])) == _A2.inv()


def test_inverse_with_det_not_one_scales_the_adjugate_cell_by_cell() -> None:
    matrix = sympy.Matrix([[4, 7], [2, 6]])  # det A = 10
    out = command(mat_proto(matrix), "matrix_inverse")
    assert part_keys(out)[-6:] == ["lesson_disc_adj_formula", "matrix_mul_scalar", *["mul"] * 4]
    assert to_sympy(CoreNode.from_contract(out["result"]["solution"])) == matrix.inv()


def test_inverse_3x3_has_one_cofactor_stage_per_row() -> None:
    out = command(mat_proto(_A3), "matrix_inverse")
    assert part_keys(out) == [
        "matrix_inv_find_formula",
        "lesson_disc_adj_det",
        *["lesson_disc_adj_cofactors_row"] * 3,
        "lesson_disc_adj_transpose",
        "lesson_disc_adj_formula",
    ]
    parts = stage_parts(out)
    cofactors = cofactor_matrix(_A3)
    assert to_sympy(CoreNode.from_contract(parts[1]["right"])) == _A3.det()
    for row, part in enumerate(parts[2:5]):
        args = [to_sympy(CoreNode.from_contract(arg)) for arg in part["description"]["args"]]
        assert args == [row + 1]
        right = CoreNode.from_contract(part["right"])
        assert to_sympy(right) == cofactors[row, :]
        # every cofactor's minor is computed in the nested «Подробнее»
        assert nested_keys(part) == ["lesson_disc_minor"] * 3
        for minor in part["subresult"]["steps"][0]["substeps"]:
            assert isinstance(minor.get("subresult"), dict)
            assert {
                sub["description"]["type"]
                for step in minor["subresult"]["steps"]
                for sub in step["substeps"]
            } >= {"det2_determinant_rule", "mul"}
    assert to_sympy(CoreNode.from_contract(parts[5]["right"])) == cofactors.T
    assert to_sympy(CoreNode.from_contract(out["result"]["solution"])) == _A3.inv()


def test_inverse_by_adjugate_matches_sympy_for_every_size() -> None:
    matrices = [
        sympy.Matrix([[1, 2], [3, 4]]),
        sympy.Matrix([[2, 0, 1], [1, 3, 2], [0, 1, 1]]),
        sympy.Matrix([[2, 0, 0, 1], [3, 1, 0, 1], [4, 0, 1, 1], [5, 0, 0, 7]]),
        sympy.Matrix(
            [
                [2, 1, 0, 3, 1],
                [1, 0, 2, 1, 0],
                [3, 2, 1, 0, 2],
                [0, 1, 2, 1, 1],
                [1, 2, 0, 1, 3],
            ]
        ),
        # fractions in the input stay exact
        sympy.Matrix([[sympy.Rational(1, 2), 1], [3, sympy.Rational(-1, 3)]]),
    ]
    for matrix in matrices:
        out = command(mat_proto(matrix), "matrix_inverse")
        assert to_sympy(CoreNode.from_contract(out["result"]["solution"])) == matrix.inv()


def test_singular_inverse_command_keeps_the_det_zero_verdict() -> None:
    singular = sympy.Matrix([[1, 2], [2, 4]])
    out = command(mat_proto(singular), "matrix_inverse")
    assert out["result"]["solution"]["type"] == "EMPTY"
    assert part_keys(out)[-1] == "matrix_inv_det_zero"
    assert "обратной матрицы нет" in " ".join(texts(out))


def test_gauss_inverse_is_unchanged() -> None:
    out = command(mat_proto(_A2), "matrix_inverse_gauss")
    assert part_keys(out) == [
        "matrix_inv_use_notation",
        "matrix_inv_write_right",
        "matrix_inv_find_identity",
        "matrix_inv_right_is_inv",
    ]
    assert to_sympy(CoreNode.from_contract(out["result"]["solution"])) == _A2.inv()


def test_typed_matrix_power_minus_one_uses_the_same_adjugate_path() -> None:
    # {M^(-1)} is not a separate command: matrix_expression routes it to matrix_inverse.
    inner = mat_proto(_A2)[1:-1]
    out = response("{" + inner + "^(-1)}")
    keys = [node["description"]["type"] for node in nodes(out) if "description" in node]
    assert "lesson_disc_adj_det" in keys and "lesson_disc_adj_transpose" in keys
    assert to_sympy(CoreNode.from_contract(out["result"]["solution"])) == _A2.inv()


@pytest.mark.parametrize("locale", ["ru", "en"])
def test_adjugate_explanations_have_no_placeholders(locale: str) -> None:
    out = command(mat_proto(_A3), "matrix_inverse", locale=locale)
    for node in nodes(out):
        explanation = node.get("explanation")
        if not isinstance(explanation, dict):
            continue
        assert explanation.get("missing") is False, explanation.get("key")
        assert "?? step_" not in explanation.get("text", "")
        assert "ARG" not in explanation.get("text", "")
    if locale == "ru":
        assert "союзную матрицу" in " ".join(texts(out))
    else:
        assert "adjugate" in " ".join(texts(out))


def test_adjugate_keys_exist_in_both_languages() -> None:
    for key in _ADJ_KEYS:
        for locale in ("ru", "default"):
            template = service.explanations().raw_template(key, locale)
            assert template is not None and template.strip(), (key, locale)
    for key in _ADJ_KEYS:
        assert service.theory(key, "ru")["id"] == "discrete:discrete_matrix"
