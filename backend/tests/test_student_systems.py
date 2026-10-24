"""Student-visible behaviour of systems of linear equations (FIX1–FIX3).

One small test per reported bug: the inverse-matrix step names A, X and B in the
template's order, Cramer's «Подробнее» never opens Gauss, coefficients entered
with the «Дробь» key behave like the «÷» ones and the fake Cramer/addition rows
are gone, a system of four equations is a Gauss card, and a Gauss row operation
never nests a copy of itself. FIX3 (P9/P10/P5/P11): 3×3 gets the matrix method
X = A⁻¹B, a −1 coefficient still gets substitution/comparison and every
nonsingular 2×2 gets Gauss, a system with a parameter is solved for the
parameter by its determinant, and explanation text never contains raw node names.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import sympy
from test_student_matrices import response, texts

from mymath_backend import CoreNode
from mymath_backend.input import parse_protocol
from mymath_backend.solver.sympy_bridge import to_sympy

FRACTION_SYSTEM = "{system({=({frac({x},{2})+frac({y},{3})},{1})},{=({x-y},{1})})}"
DIVISION_SYSTEM = "{system({=({x/2+y/3},{1})},{=({x-y},{1})})}"
FOUR_EQUATIONS = (
    "{system({=({x+y+z+w},{10})},{=({x-y+z-w},{-2})},{=({x+2y+3z+4w},{30})},{=({2x-y+3w},{12})})}"
)
INVERSE_SYSTEM = "{system({=({2x+y},{5})},{=({x+3y},{10})})}"
INCONSISTENT_2X2 = "{system({=({x+y},{2})},{=({x+y},{5})})}"
INCONSISTENT_3X3 = "{system({=({x+y+z},{1})},{=({2x+2y+2z},{3})},{=({x-y},{0})})}"
INCONSISTENT_4X3 = "{system({=({x+y+z},{1})},{=({x-y},{0})},{=({2x+z},{6})},{=({x+2y},{10})})}"
INCONSISTENT_3X2 = "{system({=({x+y},{3})},{=({x-y},{1})},{=({2x+y},{6})})}"
INFINITE_2EQ3U = "{system({=({x+y+z},{6})},{=({x+z},{3})})}"
INFINITE_2X2 = "{system({=({x+y},{2})},{=({2x+2y},{4})})}"
HOMOGENEOUS_RANK1 = "{system({=({x+y+z},{0})},{=({2x+2y+2z},{0})})}"
HOMOGENEOUS_TRIVIAL = "{system({=({x+y+z},{0})},{=({2x-y+3z},{0})},{=({x+4y+z},{0})})}"
INVERSE_3X3 = "{system({=({3x+2y-z},{4})},{=({x-y+2z},{1})},{=({2x+y+z},{5})})}"
FRACTION_SOLUTION = "{system({=({5x+3y},{7})},{=({2x-y},{1})})}"
GENERIC_GAUSS = "{system({=({x-y},{1})},{=({5x+3y},{7})})}"
PARAMETER_SLOPE = "{system({=({x+a*y},{1})},{=({x-y},{0})})}"
PARAMETER_BOTH = "{system({=({a*x+y},{1})},{=({x+a*y},{2})})}"


def entries(source: str) -> list[dict[str, Any]]:
    """Every method card of the vertical group."""
    return response(source)["result"]["groups"][0]["entries"]


def header_key(entry: dict[str, Any]) -> str:
    return entry["result"]["header"]["type"]


def substep_keys(value: Any) -> list[str]:
    """Every substep key in a contract tree, nested screens included."""
    if isinstance(value, dict):
        found = []
        if isinstance(value.get("description"), dict):
            found.append(value["description"]["type"])
        for child in value.values():
            found.extend(substep_keys(child))
        return found
    if isinstance(value, list):
        return [key for child in value for key in substep_keys(child)]
    return []


def node_kinds(value: Any) -> list[str]:
    """Every AST node type in a contract tree (explanations are not nodes)."""
    if isinstance(value, dict):
        found = [value["type"]] if "children" in value else []
        for child in value.values():
            found.extend(node_kinds(child))
        return found
    if isinstance(value, list):
        return [kind for child in value for kind in node_kinds(child)]
    return []


def first_step(entry: dict[str, Any]) -> dict[str, Any]:
    return entry["result"]["steps"][0]["substeps"][0]


def answer_values(source: str) -> dict[str, sympy.Expr]:
    """Our answer as ``{name: value}``."""
    solution = CoreNode.from_contract(entries(source)[0]["result"]["solutionNode"])
    parts = solution.children if solution.type.value == "LIST" else [solution]
    return {
        part.children[0].value: to_sympy(part.children[1])
        for part in parts
        if part.type.value == "EQUALS"
    }


def flat_substeps(card: dict[str, Any]) -> list[dict[str, Any]]:
    """Every substep of a card's result, flattened."""
    return [sub for step in card["result"]["steps"] for sub in step["substeps"]]


def result_keys(result: dict[str, Any]) -> list[str]:
    """Substep keys of a nested subresult."""
    return [sub["description"]["type"] for step in result["steps"] for sub in step["substeps"]]


def answer_parts(source: str) -> tuple[dict[str, sympy.Expr], set[str]]:
    """Assignments of the basic unknowns and the names of the free ones."""
    solution = CoreNode.from_contract(entries(source)[0]["result"]["solutionNode"])
    parts = solution.children if solution.type.value == "LIST" else [solution]
    equalities: dict[str, sympy.Expr] = {}
    free: set[str] = set()
    for part in parts:
        if part.type.value == "EQUALS":
            equalities[part.children[0].value] = to_sympy(part.children[1])
        elif part.type.value == "ELEMENT_OF":
            free.add(part.children[0].value)
            assert to_sympy(part.children[1]) == sympy.Symbol("ℝ")
        else:
            raise AssertionError(f"unexpected answer part {part.type.value}")
    return equalities, free


def equations_of(source: str) -> tuple[list[sympy.Expr], list[sympy.Symbol]]:
    node = parse_protocol(source)
    equations = [
        to_sympy(child.children[0]) - to_sympy(child.children[1]) for child in node.children
    ]
    symbols = sorted(set().union(*(equation.free_symbols for equation in equations)), key=str)
    return equations, list(symbols)


def _affine(
    values: list[sympy.Expr], names: list[sympy.Symbol]
) -> tuple[sympy.Matrix, sympy.Matrix]:
    """Base point and direction columns of a parametrized tuple."""
    free = [
        symbol
        for symbol in names
        if any(symbol in sympy.sympify(value).free_symbols for value in values)
    ]
    zero = dict.fromkeys(free, 0)
    base = sympy.Matrix([sympy.sympify(value).subs(zero) for value in values])
    columns = []
    for symbol in free:
        unit = {other: int(other == symbol) for other in free}
        direction = sympy.Matrix([sympy.sympify(value).subs(unit) for value in values]) - base
        if direction != sympy.zeros(direction.rows, 1):
            columns.append(direction)
    return base, sympy.Matrix.hstack(*columns) if columns else sympy.zeros(base.rows, 0)


def assert_answer_matches_linsolve(source: str) -> None:
    """The answer and ``sympy.linsolve`` describe the same affine solution set."""
    equations, symbols = equations_of(source)
    expected = sympy.linsolve(equations, symbols)
    assert expected != sympy.EmptySet
    equalities, free = answer_parts(source)
    assert set(equalities) | free == {symbol.name for symbol in symbols}
    ours = [equalities.get(symbol.name, symbol) for symbol in symbols]
    expected_values = list(next(iter(expected)))
    base_ours, directions_ours = _affine(ours, symbols)
    base_expected, directions_expected = _affine(expected_values, symbols)
    both = directions_ours.row_join(directions_expected)
    assert both.rank() == directions_ours.rank() == directions_expected.rank()
    assert both.row_join(base_ours - base_expected).rank() == directions_ours.rank()


def sympy_values(source: str) -> dict[str, sympy.Expr]:
    """The same system through ``sympy.linsolve`` (a unique solution expected)."""
    node = parse_protocol(source)
    equations = [
        sympy.Eq(to_sympy(child.children[0]), to_sympy(child.children[1]))
        for child in node.children
    ]
    symbols = sorted({s for eq in equations for s in eq.free_symbols}, key=str)
    found = sympy.linsolve(equations, symbols)
    assert len(found) == 1
    return {symbol.name: value for symbol, value in zip(symbols, next(iter(found)), strict=True)}


# ── P7: A·X = B, where A/X/B are the coefficient/variable/constant matrices ──


def test_inverse_matrix_step_names_axb_in_template_order() -> None:
    card = next(
        entry
        for entry in entries(INVERSE_SYSTEM)
        if header_key(entry) == "system_2x2_inv_matrix_solve"
    )
    step = first_step(card)
    assert step["description"]["type"] == "system_2x2_inv_matrix_write_as_mat_eq"
    symbolic, coefficients, unknowns, constants = [
        CoreNode.from_contract(arg) for arg in step["description"]["args"]
    ]
    assert symbolic.type.value == "EQUALS"  # A·X = B comes first
    assert to_sympy(coefficients) == sympy.Matrix([[2, 1], [1, 3]])
    assert to_sympy(unknowns) == sympy.Matrix([[sympy.Symbol("x")], [sympy.Symbol("y")]])
    assert to_sympy(constants) == sympy.Matrix([[5], [10]])
    text = step["explanation"]["text"]
    assert text.index("матрица коэффициентов") < text.index("столбец неизвестных")


# ── P6: Cramer's rule shows determinants, never Gauss row operations ─────────


def test_cramer_detail_is_not_the_gauss_lesson() -> None:
    card = next(
        entry
        for entry in entries("{system({=({x+y},{3})},{=({x-y},{1})})}")
        if header_key(entry) == "system_cramer_solve"
    )
    listing = first_step(card)
    assert listing["description"]["type"] == "system_2x2_cramer_rule"
    assert "DETERMINANT2" in node_kinds(listing["right"])
    assert "subresult" not in listing
    assert not any(key.startswith("lesson_disc_system") for key in substep_keys(card["result"]))


# ── P4: fractional coefficients behave like division and show real work ──────


def test_fraction_key_coefficients_get_the_same_methods_as_division() -> None:
    fraction = [header_key(entry) for entry in entries(FRACTION_SYSTEM)]
    division = [header_key(entry) for entry in entries(DIVISION_SYSTEM)]
    assert fraction == division
    assert "system_cramer_solve" in fraction


def test_fraction_system_cramer_lists_determinants_and_no_fake_addition() -> None:
    cards = entries(DIVISION_SYSTEM)
    keys = substep_keys(cards)
    assert "system_2x2_add_eqs" not in keys  # the fake addition card is gone
    cramer = next(entry for entry in cards if header_key(entry) == "system_cramer_solve")
    listing = first_step(cramer)
    assert "DETERMINANT2" in node_kinds(listing["right"])
    assert answer_values(DIVISION_SYSTEM) == sympy_values(DIVISION_SYSTEM)
    assert answer_values(FRACTION_SYSTEM) == sympy_values(FRACTION_SYSTEM)


# ── P3: four or more equations are solved with Gauss stages ──────────────────


def test_four_equations_use_a_gauss_card_with_reduction_stages() -> None:
    cards = entries(FOUR_EQUATIONS)
    assert len(cards) == 1
    assert header_key(cards[0]) == "system_gauss_jordan"
    keys = substep_keys(cards[0]["result"])
    assert "system_3x3_eliminate_var" not in keys
    assert "system_3x3_rem_vars" not in keys
    assert any(key.startswith("lesson_disc_") for key in keys)
    assert all("две пары" not in text for text in texts(cards[0]["result"]))
    assert answer_values(FOUR_EQUATIONS) == sympy_values(FOUR_EQUATIONS)


# ── P13: a Gauss row step's «Подробнее» is not the same line again ───────────


def test_gauss_row_detail_does_not_repeat_the_step() -> None:
    card = next(
        entry
        for entry in entries("{system({=({x+y},{3})},{=({x-y},{1})})}")
        if header_key(entry) == "system_gauss_jordan_solve"
    )
    row_keys = {"row_elim", "row_elim_out", "mat_divide_row"}
    checked = 0
    for step in card["result"]["steps"]:
        for sub in step["substeps"]:
            if sub["description"]["type"] not in row_keys or "subresult" not in sub:
                continue
            nested = [text for text in texts(sub["subresult"])]
            assert sub["explanation"]["text"] not in nested
            checked += 1
    assert checked  # at least one row operation carries a detail screen


# ── P2/FIX2: an inconsistent system shows 0 = c and the unequal ranks ───────


def test_inconsistent_system_shows_contradiction_and_ranks() -> None:
    for source in (INCONSISTENT_2X2, INCONSISTENT_3X3):
        cards = entries(source)
        assert len(cards) >= 2  # the Gauss consistency card plus the app's methods
        card = cards[0]
        assert header_key(card) == "system_gauss_jordan"
        keys = [sub["description"]["type"] for sub in flat_substeps(card)]
        assert any(key.startswith("lesson_disc_") for key in keys)
        assert "lesson_disc_system_contradiction_row" in keys
        assert "lesson_disc_system_rank_inconsistent" in keys
        contradiction = next(
            sub
            for sub in flat_substeps(card)
            if sub["description"]["type"] == "lesson_disc_system_contradiction_row"
        )
        equation = CoreNode.from_contract(contradiction["right"])
        assert equation.type.value == "EQUALS"
        zero, value = equation.children
        assert zero.type.value == "CONSTANT" and zero.value == "0"
        assert value.type.value == "CONSTANT" and value.value != "0"
        assert any("Кронекера–Капелли" in text for text in texts(card["result"]))


def test_every_inconsistent_case_gets_the_no_solutions_verdict() -> None:
    # ``verdictLatex`` shows «Решений нет» for an EMPTY answer (solver_api.dart).
    for source in (
        INCONSISTENT_2X2,
        INCONSISTENT_3X3,
        INCONSISTENT_4X3,
        INCONSISTENT_3X2,
        "{system({=({2x+3y},{6})},{=({4x+6y},{13})})}",
    ):
        card = entries(source)[0]
        assert header_key(card) == "system_gauss_jordan"
        answer = CoreNode.from_contract(card["result"]["solutionNode"])
        assert answer.type.value == "EMPTY"


# ── P1/FIX2: infinitely many solutions name the free unknowns ───────────────


def test_infinite_system_names_free_unknowns_and_every_unknown_in_answer() -> None:
    card = entries(INFINITE_2EQ3U)[0]
    assert header_key(card) == "system_gauss_jordan"
    keys = [sub["description"]["type"] for sub in flat_substeps(card)]
    assert "lesson_disc_system_rank_infinite" in keys
    assert "lesson_disc_system_free_unknowns_basic" in keys
    rank_step = next(
        sub
        for sub in flat_substeps(card)
        if sub["description"]["type"] == "lesson_disc_system_rank_infinite"
    )
    assert "бесконечно много решений" in rank_step["explanation"]["text"]
    equalities, free = answer_parts(INFINITE_2EQ3U)
    assert free == {"z"}  # the non-pivot (last) unknown
    assert set(equalities) == {"x", "y"}
    assert_answer_matches_linsolve(INFINITE_2EQ3U)


@pytest.mark.parametrize(
    "source, free_names",
    [
        # x = y/3 + 7/3: the fractional constant used to be cut to 2.
        ("{system({=({3x-y},{7})},{=({-6x+2y},{-14})})}", {"y"}),
        ("{system({=({4x+2y-3z},{1})},{=({-2x+4z},{2})})}", {"z"}),
        # w is the last unknown (x, y, z, w), not the first by alphabet.
        ("{system({=({2x-2y-5z+3w},{-13})},{=({2x-2y+7z+3w},{23})})}", {"y", "w"}),
    ],
)
def test_infinite_answer_keeps_fractions_and_textbook_unknown_order(
    source: str, free_names: set[str]
) -> None:
    _, free = answer_parts(source)
    assert free == free_names
    assert_answer_matches_linsolve(source)


def test_infinite_2x2_lists_the_free_unknown_in_the_answer() -> None:
    equalities, free = answer_parts(INFINITE_2X2)
    assert free == {"y"}
    assert set(equalities) == {"x"}
    assert_answer_matches_linsolve(INFINITE_2X2)


# ── P12/FIX2: homogeneous systems, the trivial case and the FSS ─────────────


def test_homogeneous_system_starts_with_consistency_fss_and_combination() -> None:
    card = entries(HOMOGENEOUS_RANK1)[0]
    assert header_key(card) == "system_gauss_jordan"
    substeps = flat_substeps(card)
    assert substeps[0]["description"]["type"] == "lesson_disc_system_homogeneous_first"
    keys = [sub["description"]["type"] for sub in substeps]
    assert "lesson_disc_system_rank_infinite" in keys
    assert "lesson_disc_system_homogeneous_fss" in keys
    assert "lesson_disc_system_homogeneous_general" in keys

    fss = next(
        sub
        for sub in substeps
        if sub["description"]["type"] == "lesson_disc_system_homogeneous_fss"
    )
    vectors = CoreNode.from_contract(fss["right"])
    assert vectors.type.value == "LIST" and len(vectors.children) == 2
    equations, symbols = equations_of(HOMOGENEOUS_RANK1)
    matrix, _ = sympy.linear_eq_to_matrix(equations, symbols)
    for vector in vectors.children:
        column = sympy.Matrix([to_sympy(cell) for cell in vector.children])
        assert matrix * column == sympy.zeros(matrix.rows, 1)

    general = next(
        sub
        for sub in substeps
        if sub["description"]["type"] == "lesson_disc_system_homogeneous_general"
    )
    assert general["right"]["type"] == "EQUALS"
    assert_answer_matches_linsolve(HOMOGENEOUS_RANK1)


def test_homogeneous_full_rank_says_the_trivial_solution() -> None:
    card = entries(HOMOGENEOUS_TRIVIAL)[0]
    substeps = flat_substeps(card)
    assert substeps[0]["description"]["type"] == "lesson_disc_system_homogeneous_first"
    keys = [sub["description"]["type"] for sub in substeps]
    assert "lesson_disc_system_rank_homogeneous_unique" in keys
    assert "lesson_disc_system_homogeneous_fss" not in keys
    assert answer_values(HOMOGENEOUS_TRIVIAL) == {
        "x": sympy.Integer(0),
        "y": sympy.Integer(0),
        "z": sympy.Integer(0),
    }


# ── FIX2 item 4: a uniquely solvable system keeps its verified cards ────────


def test_unique_system_keeps_its_row_cards() -> None:
    cards = entries("{system({=({x+y},{3})},{=({x-y},{1})})}")
    assert [header_key(card) for card in cards] == [
        "solve_using_substitution",
        "system_2x2_solve_elimination_simple",
        "solve_using_comparison",
        "system_gauss_jordan_solve",
        "system_cramer_solve",
        "system_2x2_inv_matrix_solve",
    ]
    keys = [key for card in cards for key in substep_keys(card["result"])]
    assert "lesson_disc_system_rank_infinite" not in keys
    assert "lesson_disc_system_rank_inconsistent" not in keys
    assert "lesson_disc_system_homogeneous_first" not in keys


def card_answer(card: dict[str, Any]) -> dict[str, sympy.Expr]:
    """The card's own answer as ``{name: value}``."""
    solution = CoreNode.from_contract(card["result"]["solutionNode"])
    parts = solution.children if solution.type.value == "LIST" else [solution]
    return {
        part.children[0].value: to_sympy(part.children[1])
        for part in parts
        if part.type.value == "EQUALS"
    }


# ── P9: the 3×3 matrix method X = A⁻¹B ──────────────────────────────────────


def test_three_by_three_system_gets_the_inverse_matrix_card() -> None:
    cards = entries(INVERSE_3X3)
    assert [header_key(card) for card in cards] == [
        "system_gauss_jordan",
        "system_cramer_solve",
        "system_2x2_inv_matrix_solve",
    ]
    card = cards[-1]
    keys = [sub["description"]["type"] for sub in flat_substeps(card)]
    assert keys[0] == "system_2x2_inv_matrix_write_as_mat_eq"
    assert "system_2x2_inv_matrix_identify" in keys
    assert "system_matrix_inv_det" in keys
    assert "system_2x2_inv_matrix_find_inv" in keys
    assert "system_2x2_inv_matrix_sub_eq" in keys
    assert "matrix_mul" in keys
    assert "matrix_eq_set_elements_equal" in keys
    # every card answers the same triple (0, 3, 2)
    for entry in cards:
        assert card_answer(entry) == sympy_values(INVERSE_3X3)
    assert card_answer(card) == {
        "x": sympy.Integer(0),
        "y": sympy.Integer(3),
        "z": sympy.Integer(2),
    }


def test_three_by_three_inverse_card_reuses_the_shared_inverse_screen() -> None:
    card = next(
        entry
        for entry in entries(INVERSE_3X3)
        if header_key(entry) == "system_2x2_inv_matrix_solve"
    )
    write = first_step(card)
    symbolic, coefficients, unknowns, constants = [
        CoreNode.from_contract(arg) for arg in write["description"]["args"]
    ]
    assert symbolic.type.value == "EQUALS"  # A·X = B comes first
    assert to_sympy(coefficients) == sympy.Matrix([[3, 2, -1], [1, -1, 2], [2, 1, 1]])
    assert to_sympy(unknowns) == sympy.Matrix(
        [[sympy.Symbol("x")], [sympy.Symbol("y")], [sympy.Symbol("z")]]
    )
    assert to_sympy(constants) == sympy.Matrix([[4], [1], [5]])
    inverse = next(
        sub
        for sub in flat_substeps(card)
        if sub["description"]["type"] == "system_2x2_inv_matrix_find_inv"
    )
    assert "matrix_inv_find_formula" in result_keys(inverse["subresult"])
    # the shared screen is now the adjugate formula, not a hidden Gaussian reduction
    screen = result_keys(inverse["subresult"])
    assert "lesson_disc_adj_det" in screen and "lesson_disc_adj_transpose" in screen
    product = next(sub for sub in flat_substeps(card) if sub["description"]["type"] == "matrix_mul")
    nested = result_keys(product["subresult"])
    assert "matrix_mul" in nested and "matrix_mul_row_col_simple" in nested


# ── P10: a −1 coefficient still gets every method ───────────────────────────


def test_minus_one_coefficient_gets_substitution_comparison_and_gauss() -> None:
    cards = entries(FRACTION_SOLUTION)
    assert [header_key(card) for card in cards] == [
        "solve_using_substitution",
        "system_2x2_solve_elimination_simple",
        "solve_using_comparison",
        "system_gauss_jordan_solve",
        "system_cramer_solve",
        "system_2x2_inv_matrix_solve",
    ]
    expected = {"x": sympy.Rational(10, 11), "y": sympy.Rational(9, 11)}
    for card in cards:
        assert card_answer(card) == expected


@pytest.mark.parametrize(
    "source",
    [
        FRACTION_SOLUTION,
        GENERIC_GAUSS,
        "{system({=({2x+3y},{1})},{=({4x-y},{5})})}",
        "{system({=({x},{1})},{=({2x+y},{5})})}",
    ],
)
def test_gauss_card_answers_every_nonsingular_integer_system(source: str) -> None:
    card = next(
        entry for entry in entries(source) if header_key(entry) == "system_gauss_jordan_solve"
    )
    assert card_answer(card) == sympy_values(source)


# ── P5: systems with a parameter are solved for the parameter ───────────────


def test_parameter_system_expresses_the_solution_in_the_parameter() -> None:
    card = entries(PARAMETER_SLOPE)[0]
    assert header_key(card) == "system_param_solve"
    a = sympy.Symbol("a")
    assert card_answer(card) == {"x": 1 / (1 + a), "y": 1 / (1 + a)}
    keys = [sub["description"]["type"] for sub in flat_substeps(card)]
    assert "system_param_det" in keys
    assert "system_param_unique" in keys
    special = [
        sub for sub in flat_substeps(card) if sub["description"]["type"] == "system_param_special"
    ]
    assert len(special) == 1
    assert CoreNode.from_contract(special[0]["subresult"]["solutionNode"]).type.value == "EMPTY"


def test_parameter_system_lists_every_special_value() -> None:
    card = entries(PARAMETER_BOTH)[0]
    det = next(
        sub for sub in flat_substeps(card) if sub["description"]["type"] == "system_param_det"
    )
    a = sympy.Symbol("a")
    # the step shows the determinant itself, then its value
    shown = CoreNode.from_contract(det["right"])
    assert shown.type.value == "EQUALS"
    assert shown.children[0].type.value == "DETERMINANT2"
    assert to_sympy(shown.children[1]) == a**2 - 1
    special = [
        sub for sub in flat_substeps(card) if sub["description"]["type"] == "system_param_special"
    ]
    assert len(special) == 2
    for sub in special:
        assert CoreNode.from_contract(sub["subresult"]["solutionNode"]).type.value == "EMPTY"
    # the general answer (a ≠ ±1) agrees with sympy.solve
    a_ = sympy.Symbol("a")
    values = card_answer(card)
    expected = sympy.solve(
        [
            sympy.Eq(a_ * sympy.Symbol("x") + sympy.Symbol("y"), 1),
            sympy.Eq(sympy.Symbol("x") + a_ * sympy.Symbol("y"), 2),
        ],
        [sympy.Symbol("x"), sympy.Symbol("y")],
        dict=True,
    )[0]
    assert sympy.simplify(values["x"] - expected[sympy.Symbol("x")]) == 0
    assert sympy.simplify(values["y"] - expected[sympy.Symbol("y")]) == 0


# ── P11: explanation text never leaks raw node names ────────────────────────


def test_default_renderer_is_human_readable() -> None:
    from mymath_backend import CoreNodeType as T
    from mymath_backend.explanations import _default_render_arg

    lhs = CoreNode.node(T.ADD, CoreNode.variable("x"), CoreNode.variable("y"))
    equals = CoreNode.node(T.EQUALS, lhs, CoreNode.constant("3"))
    assert _default_render_arg(equals) == "x + y = 3"
    listing = CoreNode.node(T.LIST, CoreNode.variable("x"), CoreNode.variable("y"))
    assert _default_render_arg(listing) == "x, y"
    matrix = CoreNode.node(
        T.MATRIX,
        CoreNode.node(T.MATRIX_ROW, CoreNode.constant("1"), CoreNode.constant("2")),
        CoreNode.node(T.MATRIX_ROW, CoreNode.constant("3"), CoreNode.constant("4")),
    )
    assert _default_render_arg(matrix) == "[1 2 ; 3 4]"
    determinant = CoreNode.node(
        T.DETERMINANT2,
        CoreNode.constant("a"),
        CoreNode.constant("b"),
        CoreNode.constant("c"),
        CoreNode.constant("d"),
    )
    assert _default_render_arg(determinant) == "|a b ; c d|"


@pytest.mark.parametrize(
    "source", [FRACTION_SOLUTION, INVERSE_3X3, PARAMETER_BOTH, INCONSISTENT_2X2]
)
def test_explanation_text_never_shows_raw_node_names(source: str) -> None:
    for text in texts(response(source)):
        assert not re.search(r"[A-Z_]{3,}\(", text), text


def test_equation_with_zero_right_side_moves_nothing_but_zero() -> None:
    # 2y = 0 left nothing to move: the card crashed on an empty sum (fuzz systems.py 14)
    result = response("{system({=({3x+y},{3})},{=({2y},{0})})}")["result"]
    answer = CoreNode.from_contract(result["solution"])
    pairs = {(eq.children[0].value, str(to_sympy(eq.children[1]))) for eq in answer.children}
    assert pairs == {("x", "1"), ("y", "0")}
