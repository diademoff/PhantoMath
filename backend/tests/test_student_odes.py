"""Student-visible differential equations: answers, cards, rules.

Each test uses the protocol the keyboard sends, including the system form of a
Cauchy problem (``y(0)`` arrives as ``y·(0)``, ``y′(0)`` as ``y′·(0)``). The
answer is checked independently: ``y`` is replaced by ``y(x)`` before
``to_sympy`` on both sides, ``checkodesol`` must accept the answer, and the
number of free constants must match the order (zero and the conditions for a
Cauchy problem).

The cards follow the integral cards' rules: a stage is a fact (no arrow) or a
transformation ``left → right``; consecutive transformations chain; a stage
never repeats itself; a text never repeats its own formula; the step heading is
«Решите уравнение» (the three steps of a special right side have distinct
headings). First-order cards cover the four Filippov methods; second-order
cards cover reduction of order, the characteristic equation with its three
cases, a special right side with the resonance multiplier and the Cauchy
problem.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pytest
import sympy

from mymath_backend import CoreNode, service
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import SolveError, solve
from mymath_backend.solver.diff_equations import is_diff_equation
from mymath_backend.solver.sympy_bridge import to_sympy

_DERIVATIVES = (T.PRIME, T.DERIVATION1, T.DERIVATION1_PRIME, T.DERIVATION2_PRIME)

_X = sympy.Symbol("x")
_Y = sympy.Symbol("y")
_C = sympy.Symbol("C")

FIRST_ORDER: list[tuple[str, str, list[str] | None]] = [
    ("fo01", "{=({prime({y})},{x*y})}", None),
    ("fo02", "{=({prime({y})},{frac({y},{x})})}", None),
    ("fo03", "{=({x*prime({y})},{y})}", None),
    ("fo04", "{=({prime({y})},{frac({1+y^2},{1+x^2})})}", None),
    ("fo05", "{=({prime({y})},{exp({x+y})})}", None),
    ("fo06", "{=({prime({y})*cos({x})},{y})}", None),
    ("fo07", "{=({prime({y})},{frac({y},{cos({x})})})}", None),
    ("fo09", "{=({prime({y})},{frac({-x},{y})})}", None),
    ("fo10", "{=({prime({y})},{frac({y},{x})+frac({x},{y})})}", None),
    ("fo11", "{=({prime({y})},{frac({x+y},{x})})}", None),
    ("fo12", "{=({x*prime({y})},{y+root2({x^2+y^2})})}", None),
    ("fo13", "{=({prime({y})},{frac({y+root2({x^2+y^2})},{x})})}", None),
    ("fo14", "{=({prime({y})+y},{x})}", None),
    ("fo15", "{=({prime({y})},{x-y})}", None),
    ("fo16", "{=({prime({y})-frac({2*y},{x})},{x^3})}", None),
    ("fo17", "{=({prime({y})},{x^3+frac({2*y},{x})})}", None),
    ("fo18", "{=({prime({y})+y*tan({x})},{cos({x})})}", None),
    ("fo19", "{=({prime({y})},{cos({x})-y*tan({x})})}", None),
    ("fo20", "{=({prime({y})},{2*x*y+x})}", None),
    ("fo21", "{=({prime({y})+y},{x*y^2})}", None),
    ("fo22", "{=({prime({y})},{x*y^2-y})}", None),
    ("fo23", "{=({prime({y})-frac({y},{x})},{-y^2})}", None),
    ("fo24", "{=({prime({y})},{frac({y},{x})-y^2})}", None),
    ("fo26", "{=({prime({y})},{frac({-2*x*y},{x^2+3*y^2})})}", None),
    ("fo27", "{=({prime({y})},{2*x})}", ["{0}", "{1}"]),
    ("fo28", "{=({prime({y})},{y})}", ["{0}", "{2}"]),
    ("fo29", "{=({prime({y})+y},{exp({x})})}", ["{0}", "{0}"]),
    ("fo30", "{=({prime({y})},{exp({x})-y})}", ["{0}", "{0}"]),
    ("fo31", "{=({prime({y})},{y^2})}", ["{1}", "{1}"]),
]

SECOND_ORDER: list[tuple[str, str, int, str]] = [
    ("so01", "{=({derivation2_prime({y})},{x})}", 0, "eq_solve_short"),
    ("so02", "{=({derivation2_prime({y})},{sin({x})})}", 0, "eq_solve_short"),
    ("so03", "{=({derivation2_prime({y})},{frac({1},{x})})}", 0, "eq_solve_short"),
    ("so04", "{=({x*derivation2_prime({y})},{prime({y})})}", 0, "eq_solve_short"),
    ("so05", "{=({derivation2_prime({y})},{frac({prime({y})},{x})})}", 0, "eq_solve_short"),
    ("so06", "{=({derivation2_prime({y})-3*prime({y})+2*y},{0})}", 0, "eq_solve_short"),
    ("so07", "{=({derivation2_prime({y})},{3*prime({y})-2*y})}", 0, "eq_solve_short"),
    ("so08", "{=({derivation2_prime({y})},{y})}", 0, "eq_solve_short"),
    ("so09", "{=({derivation2_prime({y})},{y})}", 0, "eq_solve_short"),
    ("so10", "{=({derivation2_prime({y})-2*prime({y})+y},{0})}", 0, "eq_solve_short"),
    ("so11", "{=({derivation2_prime({y})},{2*prime({y})-y})}", 0, "eq_solve_short"),
    ("so12", "{=({derivation2_prime({y})+y},{0})}", 0, "eq_solve_short"),
    ("so13", "{=({derivation2_prime({y})},{-y})}", 0, "eq_solve_short"),
    ("so14", "{=({derivation2_prime({y})+2*prime({y})+5*y},{0})}", 0, "eq_solve_short"),
    ("so15", "{=({derivation2_prime({y})},{-2*prime({y})-5*y})}", 0, "eq_solve_short"),
    (
        "so16",
        "{=({derivation2_prime({y})-3*prime({y})+2*y},{exp({x})})}",
        0,
        "lesson_calc_ode_step_homogeneous",
    ),
    (
        "so17",
        "{=({derivation2_prime({y})},{3*prime({y})-2*y+exp({x})})}",
        0,
        "lesson_calc_ode_step_homogeneous",
    ),
    (
        "so18",
        "{=({derivation2_prime({y})+y},{x})}",
        0,
        "lesson_calc_ode_step_homogeneous",
    ),
    (
        "so19",
        "{=({derivation2_prime({y})},{x-y})}",
        0,
        "lesson_calc_ode_step_homogeneous",
    ),
    (
        "so20",
        "{=({derivation2_prime({y})-y},{exp({2*x})})}",
        0,
        "lesson_calc_ode_step_homogeneous",
    ),
    (
        "so21",
        "{=({derivation2_prime({y})},{y+exp({2*x})})}",
        0,
        "lesson_calc_ode_step_homogeneous",
    ),
    (
        "so22",
        "{=({derivation2_prime({y})+y},{sin({x})})}",
        0,
        "lesson_calc_ode_step_homogeneous",
    ),
    (
        "so23",
        "{=({derivation2_prime({y})},{sin({x})-y})}",
        0,
        "lesson_calc_ode_step_homogeneous",
    ),
    (
        "so24",
        "{=({derivation2_prime({y})+4*y},{cos({2*x})})}",
        0,
        "lesson_calc_ode_step_homogeneous",
    ),
    (
        "so25",
        "{=({derivation2_prime({y})},{cos({2*x})-4*y})}",
        0,
        "lesson_calc_ode_step_homogeneous",
    ),
    (
        "so26",
        "{system({=({derivation2_prime({y})+y},{0})},{=({muli({y},{(0)})},{0})},"
        "{=({muli({prime({y})},{(0)})},{1})})}",
        2,
        "eq_solve_short",
    ),
    (
        "so27",
        "{system({=({derivation2_prime({y})+y},{0})},{=({muli({y},{(0)})},{0})})}",
        1,
        "eq_solve_short",
    ),
    (
        "so28",
        "{system({=({derivation2_prime({y})},{6*x})},{=({muli({y},{(0)})},{1})},"
        "{=({muli({prime({y})},{(0)})},{0})})}",
        2,
        "eq_solve_short",
    ),
    (
        "so29",
        "{system({=({derivation2_prime({y})},{6*x})},{=({muli({y},{(0)})},{1})})}",
        1,
        "eq_solve_short",
    ),
]


def vertical(source: str, args: list[str] | None = None) -> CoreSolverVerticalResult:
    """Решить протокол как задача из редактора (с командой при аргументах)."""
    node = parse_protocol(source)
    if args:
        result = solve(
            node,
            command="diff_eq",
            args=[parse_protocol(argument) for argument in args],
        )
    else:
        result = solve(node)
    vertical_result = result.result.vertical()
    assert vertical_result is not None and vertical_result.solution is not None
    return vertical_result


def step_keys(source: str, args: list[str] | None = None) -> list[str]:
    return [sub.description.type for step in vertical(source, args).steps for sub in step.substeps]


def answer(source: str, args: list[str] | None = None) -> CoreNode:
    return vertical(source, args).solution


def branches(solution: CoreNode) -> list[CoreNode]:
    return solution.children if solution.type is T.LIST else [solution]


def _order_of(node: CoreNode) -> int | None:
    if node.type is T.DERIVATION2_PRIME:
        order = 2
    elif node.type in (T.PRIME, T.DERIVATION1, T.DERIVATION1_PRIME):
        order = 1
    else:
        return None
    if node.children:
        nested = _order_of(node.children[0])
        if nested is not None:
            order += nested
    return order


def _dependent(node: CoreNode) -> str | None:
    current = node
    while current.type in _DERIVATIVES and current.children:
        current = current.children[0]
    if current.type in (T.VARIABLE, T.FUNCTION) and current.value:
        return current.value
    return None


def _subs_function(node: CoreNode, dep: str, ind: str) -> CoreNode:
    if node.type is T.VARIABLE and node.value == dep:
        return CoreNode(
            type=T.FUNCTION,
            value=dep,
            children=[CoreNode.variable(ind)],
        )
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[_subs_function(child, dep, ind) for child in node.children],
    )


def _variables(node: CoreNode) -> list[str]:
    seen: list[str] = []
    for item in node.walk():
        if item.type is T.VARIABLE and item.value and item.value not in seen:
            seen.append(item.value)
    return seen


def _problem(source: str) -> tuple[sympy.Eq, str, int, str]:
    """Уравнение задачи, зависимая/независимая переменная и условия Коши."""
    parsed = parse_protocol(source)
    if parsed.type is T.SYSTEM:
        rows = [row for row in parsed.children if row.type is T.EQUALS]
        equations = [
            row
            for row in rows
            if any(node.type in _DERIVATIVES for node in row.walk())
            and not (
                row.children[0].type is T.MULTIPLY_IMPLICIT
                or row.children[0].type is T.EVALUATE_EXPRESSION
            )
        ]
        assert len(equations) == 1
        parsed = equations[0]
    derivatives = [node for node in parsed.walk() if node.type in _DERIVATIVES]
    dep = next(name for name in (_dependent(node) for node in derivatives) if name)
    order = max(value for value in (_order_of(node) for node in derivatives) if value is not None)
    ind = next((name for name in _variables(parsed) if name != dep), "x")
    left = to_sympy(_subs_function(parsed.children[0], dep, ind))
    right = to_sympy(_subs_function(parsed.children[1], dep, ind))
    return sympy.Eq(sympy.together(left - right), 0), dep, order, ind


def _answer_equations(solution: CoreNode, dep: str, ind: str) -> Iterator[sympy.Eq]:
    xsym = sympy.Symbol(ind)
    yfun = sympy.Function(dep)
    for branch in branches(solution):
        value = to_sympy(branch)
        assert isinstance(value, sympy.Eq)
        left = value.lhs.subs(sympy.Symbol(dep), yfun(xsym))
        right = value.rhs.subs(sympy.Symbol(dep), yfun(xsym))
        yield sympy.Eq(left, right)


def _constants(solution: CoreNode, dep: str, ind: str) -> list[set[str]]:
    names: list[set[str]] = []
    for equation in _answer_equations(solution, dep, ind):
        names.append(
            {
                symbol.name
                for symbol in equation.free_symbols
                if isinstance(symbol, sympy.Symbol) and symbol.name not in (dep, ind)
            }
        )
    return names


def _check_ode(equation: sympy.Eq, solution_equation: sympy.Eq) -> bool:
    """``checkodesol`` on the answer or on an equivalent implicit form.

    The textbook writes ``y + √(x² + y²) = Cx²``; ``checkodesol`` only accepts
    the divided form ``(y + √(x² + y²))/x² = C``, so the shown answer and the
    checked answer may differ by multiplying by the right side.
    """
    try:
        if sympy.checkodesol(equation, solution_equation, solve_for_func=False)[0]:
            return True
    except (KeyError, TypeError, ValueError):
        pass
    left, right = solution_equation.lhs, solution_equation.rhs
    if right != 0 and sympy.Symbol("y") not in right.free_symbols:
        try:
            equivalent = sympy.Eq(left / right, 1)
            return bool(sympy.checkodesol(equation, equivalent, solve_for_func=False)[0])
        except (KeyError, TypeError, ValueError):
            return False
    return False


def assert_ode(
    source: str,
    order: int,
    constants: int,
    args: list[str] | None = None,
) -> CoreNode:
    """Ответ обращает уравнение в тождество, постоянных как у учебника."""
    equation, dep, computed_order, ind = _problem(source)
    assert computed_order == order
    solution = answer(source, args)
    results = []
    for solution_equation in _answer_equations(solution, dep, ind):
        results.append(_check_ode(equation, solution_equation))
    assert results and all(results), (source, solution.to_contract())
    counts = _constants(solution, dep, ind)
    assert all(len(names) == constants for names in counts), counts
    return solution


def _types(solution: CoreNode) -> list[T]:
    return [node.type for branch in branches(solution) for node in branch.walk()]


def _check_conditions(source: str, solution: CoreNode) -> None:
    """Подставить ``x₀`` (и производные) в явный ответ."""
    parsed = parse_protocol(source)
    conditions = []
    for row in parsed.children:
        lhs = row.children[0]
        if lhs.type is not T.MULTIPLY_IMPLICIT:
            continue
        factor = lhs.children[0]
        point = lhs.children[1]
        order = 0 if factor.type in (T.VARIABLE, T.FUNCTION) else _order_of(factor)
        assert order is not None
        point_node = point.children[0] if point.type is T.BRACKET else point
        conditions.append((order, to_sympy(point_node), to_sympy(row.children[1])))
    branch = branches(solution)[0]
    value = to_sympy(branch)
    assert isinstance(value, sympy.Eq)
    xsym = next(symbol for symbol in value.rhs.free_symbols if str(symbol) == "x")
    for order, x_zero, expected in conditions:
        derived = value.rhs if order == 0 else sympy.diff(value.rhs, xsym, order)
        assert sympy.simplify(derived.subs(xsym, x_zero) - expected) == 0


# ── prose names its formulas as parts (FIX1 B) ────────────────────────

_TYPED_MATH = re.compile(r"[A-Za-z\u0370-\u03ff]\s*[′'’]?\s*[=+<>]")

FORMULA_SENTENCES = [
    ("fo10", "{=({prime({y})},{frac({y},{x})+frac({x},{y})})}", "lesson_calc_ode_hom_substitute"),
    ("fo14", "{=({prime({y})+y},{x})}", "lesson_calc_ode_lin_substitute"),
    ("fo14", "{=({prime({y})+y},{x})}", "lesson_calc_ode_lin_choose_v"),
    ("fo21", "{=({prime({y})+y},{x*y^2})}", "lesson_calc_ode_bern_substitute"),
    ("fo22", "{=({prime({y})},{x*y^2-y})}", "lesson_calc_ode_bern_back"),
    ("so04", "{=({x*derivation2_prime({y})},{prime({y})})}", "lesson_calc_ode_reduce_substitute"),
    ("so04", "{=({x*derivation2_prime({y})},{prime({y})})}", "lesson_calc_ode_reduce_integrate"),
]


def _explanation(source: str, key: str) -> dict[str, Any]:
    """The rendered explanation of the first stage with `key`: text and parts."""

    def search(result: dict[str, Any]) -> dict[str, Any] | None:
        for step in result.get("steps") or []:
            for sub in step.get("substeps") or []:
                if sub["description"]["type"] == key:
                    return sub["explanation"]
                nested = sub.get("subresult")
                if isinstance(nested, dict):
                    found = search(nested)
                    if found is not None:
                        return found
        return None

    data = service.solve_request(parse_protocol(source).to_contract(), render=True, locale="ru")
    for group in data["result"]["groups"]:
        for entry in group.get("entries") or []:
            found = search(entry.get("result") or {})
            if found is not None:
                return found
    raise AssertionError(f"этапа {key} нет в карточке {source}")


def _formula_nodes(explanation: dict[str, Any]) -> list[dict[str, Any]]:
    return [part["node"] for part in explanation["parts"] if part.get("node")]


def _text_parts(explanation: dict[str, Any]) -> list[str]:
    return [part["text"] for part in explanation["parts"] if part.get("text")]


@pytest.mark.parametrize(
    ("name", "source", "key"),
    FORMULA_SENTENCES,
    ids=[row[0] + ":" + row[2] for row in FORMULA_SENTENCES],
)
def test_a_sentence_names_its_formula_as_a_part(name: str, source: str, key: str) -> None:
    """«Положим y = uv.» is prose plus a formula part, not typed mathematics."""
    explanation = _explanation(source, key)
    assert _formula_nodes(explanation), explanation
    assert _text_parts(explanation)
    for text in _text_parts(explanation):
        assert not _TYPED_MATH.search(text), (name, text)


def test_the_substitution_part_is_the_substitution() -> None:
    explanation = _explanation("{=({prime({y})+y},{x})}", "lesson_calc_ode_lin_substitute")
    node = _formula_nodes(explanation)[0]
    assert node["type"] == "EQUALS"
    assert node["children"][0] == {"type": "VARIABLE", "value": "y"}
    assert _text_parts(explanation)[0].strip() == "Положим"


def test_the_choose_v_part_is_the_general_rule() -> None:
    """The sentence names the rule with p, the stage below shows the problem's equation."""
    explanation = _explanation("{=({prime({y})+y},{x})}", "lesson_calc_ode_lin_choose_v")
    node = _formula_nodes(explanation)[0]
    assert node["type"] == "EQUALS" and node["children"][1]["value"] == "0"
    left = node["children"][0]
    assert any(item.get("value") == "p" for item in _walk_contract(left))


def _walk_contract(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for child in node.get("children") or []:
            yield from _walk_contract(child)
    elif isinstance(node, list):
        for child in node:
            yield from _walk_contract(child)


def test_the_lost_solution_is_named_without_its_formula() -> None:
    """«Особое решение…»: `y = 0` is the stage's own formula and is not repeated."""
    explanation = _explanation("{=({prime({y})},{x*y^2-y})}", "lesson_ode_singular_solution")
    assert explanation["text"] == "Особое решение (потеряно при делении на y)."
    assert _formula_nodes(explanation) == []
    note = vertical("{=({prime({y})},{x*y^2-y})}").steps[-1].substeps[-1]
    assert note.left is not None and note.left.children[1].value == "0"


def test_the_quadratic_formula_sentence_has_its_two_formulas() -> None:
    source = "{=({derivation2_prime({y})-3*prime({y})+2*y},{0})}"
    explanation = _explanation(source, "lesson_root_formula")
    nodes = _formula_nodes(explanation)
    assert [node["type"] for node in nodes] == ["EQUALS", "NOT_EQUALS"]
    assert _text_parts(explanation)[0].strip() == "Используем формулу корней для"
    assert "где" in _text_parts(explanation)[1]


def test_the_roots_sentence_names_d_zero_as_a_part() -> None:
    source = "{=({derivation2_prime({y})-3*prime({y})+2*y},{0})}"
    explanation = _explanation(source, "eq_quad_solve_in_r")
    assert [node["type"] for node in _formula_nodes(explanation)] == ["EQUALS"]
    assert _formula_nodes(explanation)[0]["children"][0]["value"] == "D"
    assert _text_parts(explanation)[-1].startswith(" они совпадают")


def test_the_discriminant_sentence_does_not_repeat_the_formula() -> None:
    """«Запишем D = b² − 4ac…» would repeat the stage's own left side."""
    source = "{=({derivation2_prime({y})-3*prime({y})+2*y},{0})}"
    explanation = _explanation(source, "eq_quad_disc")
    assert explanation["text"] == (
        "Подставим коэффициенты вместе с их знаками в формулу дискриминанта."
    )
    assert _formula_nodes(explanation) == []


# ── two nested integrals name their side (FIX1 C) ─────────────────────


def test_the_two_integrals_of_both_sides_have_their_own_headings() -> None:
    nested = _stage("{=({prime({y})},{x*y})}", "lesson_calc_ode_sep_integrate").subresult
    assert nested is not None
    headings = [step.step_headers[0].type for step in nested.steps]
    assert headings == [
        "lesson_calc_ode_integral_left",
        "lesson_calc_ode_integral_right",
    ]


def test_the_nested_integral_answer_is_written_as_in_the_book() -> None:
    """(x − 1)eˣ in the nested integral card of an ODE, not (x − 1)·eˣ."""
    answer = _stage("{=({prime({y})+y},{x})}", "lesson_calc_ode_lin_u").subresult.solution
    assert answer is not None
    assert any(node.type is T.MULTIPLY_IMPLICIT for node in answer.walk())
    assert not any(node.type is T.MULTIPLY for node in answer.walk())


def test_every_nested_integral_names_its_side() -> None:
    """A card whose «Подробнее» holds both sides never shows one heading twice."""
    sources = (
        "{=({prime({y})},{frac({y},{x})+frac({x},{y})})}",
        "{=({x*derivation2_prime({y})},{prime({y})})}",
    )
    for source in sources:
        for group in _card(source):
            for sub in group[1]:
                nested = sub.subresult
                if nested is None or len(nested.steps) < 2:
                    continue
                headings = [step.step_headers[0].type for step in nested.steps if step.step_headers]
                assert len(headings) == len(set(headings)), (source, headings)


# ── rules of a card ───────────────────────────────────────────────────


def _card(source: str, args: list[str] | None = None) -> list[tuple[list[str], list[CoreNode]]]:
    """Группы карточки: заголовки шага и подшаги по порядку."""
    vertical_result = vertical(source, args)
    return [
        ([header.type for header in step.step_headers], list(step.substeps))
        for step in vertical_result.steps
    ]


def _substeps(source: str, args: list[str] | None = None) -> list[CoreNode]:
    return [sub for _headers, substeps in _card(source, args) for sub in substeps]


def _stage(source: str, key: str, args: list[str] | None = None) -> CoreNode:
    stage = next(sub for sub in _substeps(source, args) if sub.description.type == key)
    return stage


def _assert_card_rules(
    source: str, args: list[str] | None = None, first: str = "eq_solve_short"
) -> None:
    groups = _card(source, args)
    headings = [headers[0] for headers, _ in groups if headers]
    assert headings and headings[0] == first
    assert all(len(headers) == 1 for headers, _ in groups if headers), groups
    assert len(headings) == len(set(headings)) or len(headings) == 1
    for headers, substeps in groups:
        if not headers:
            continue  # примечание об особом решении живёт без заголовка
        last_right: CoreNode | None = None
        for sub in substeps:
            assert sub.left is not None, sub.description
            left, right = sub.left, sub.right
            if right is None:
                last_right = None
            else:
                assert not left.structural_eq(right), sub.description
                if last_right is not None:
                    assert last_right.structural_eq(left), (source, sub.description, last_right)
                last_right = right
            for argument in sub.description.args if sub.description else []:
                assert not argument.structural_eq(left), (source, sub.description)
                assert right is None or not argument.structural_eq(right), (
                    source,
                    sub.description,
                )


class TestRightHandDerivative:
    """#1: ``y′`` справа — это производная, а не 1."""

    def test_second_order_with_prime_on_the_right(self) -> None:
        solution = assert_ode(
            "{=({derivation2_prime({y})},{3*prime({y})-2*y})}", order=2, constants=2
        )
        names = _constants(solution, "y", "x")[0]
        assert names == {"C1", "C2"}
        assert T.ROOT2 not in _types(solution)  # not the 3/2 + sin(√2x) bug

    def test_first_order_with_prime_on_the_right(self) -> None:
        assert_ode("{=({derivation2_prime({y})},{frac({prime({y})},{x})})}", 2, 2)


class TestDerivativeShapes:
    """#2: каждый узел производной, который может дать ввод, — это ОДУ."""

    @pytest.mark.parametrize(
        ("source", "order"),
        [
            ("{=({prime({y})},{y})}", 1),
            ("{=({prime({prime({y})})},{-y})}", 2),
            ("{=({derivation_prime({y})},{y})}", 1),
            ("{=({derivation2_prime({y})},{-y})}", 2),
        ],
    )
    def test_protocol_shapes(self, source: str, order: int) -> None:
        assert is_diff_equation(parse_protocol(source))
        assert_ode(source, order=order, constants=order)

    def test_derivation1_prime_node_without_a_protocol_token(self) -> None:
        node = CoreNode.node(
            T.EQUALS,
            CoreNode.node(T.DERIVATION1_PRIME, CoreNode.variable("y")),
            CoreNode.variable("y"),
        )
        assert is_diff_equation(node)
        vertical_result = solve(node).result.vertical()
        assert vertical_result is not None and vertical_result.solution is not None
        assert vertical_result.solution.type is T.EQUALS
        assert vertical_result.solution.children[0].value == "y"


class TestAnyArrangement:
    """#3: производная в любой части уравнения, решение ``Eq(lhs − rhs, 0)``."""

    @pytest.mark.parametrize(
        ("source", "order"),
        [
            ("{=({prime({y})+y},{x})}", 1),
            ("{=({x*prime({y})},{y})}", 1),
            ("{=({derivation2_prime({y})-3*prime({y})+2*y},{0})}", 2),
            ("{=({prime({y})*cos({x})},{y})}", 1),
            ("{=({x*derivation2_prime({y})},{prime({y})})}", 2),
        ],
    )
    def test_arrangement(self, source: str, order: int) -> None:
        assert is_diff_equation(parse_protocol(source))
        assert_ode(source, order=order, constants=order)

    def test_general_equation_solver_does_not_catch_it(self) -> None:
        solution = solve(parse_protocol("{=({prime({y})+y},{x})}")).result.vertical()
        assert solution is not None and solution.solution is not None
        # Не «x = 1 + y» из общего решателя уравнений.
        assert solution.solution.type is T.EQUALS
        assert solution.solution.children[0].value == "y"

    def test_sides_are_joined(self) -> None:
        solution = assert_ode("{=({derivation2_prime({y})+y},{sin({x})})}", 2, 2)
        # y″ + y = sin x: резонанс даёт x·cos x, свободный член не теряется.
        written = str(to_sympy(solution))
        assert "x*cos" in written or "x * cos" in written or "x/2" in written


class TestCauchySystem:
    """#4: задача Коши, набранная системой; значения — неявным произведением."""

    Y_ZERO = "{=({muli({y},{(0)})},{0})}"
    Y_PRIME_ZERO = "{=({muli({prime({y})},{(0)})},{1})}"
    ODE = "{=({derivation2_prime({y})},{0-y})}"

    def test_y_of_zero_is_an_implicit_product(self) -> None:
        parsed = parse_protocol(self.Y_ZERO)
        lhs = parsed.children[0]
        assert lhs.type is T.MULTIPLY_IMPLICIT
        assert lhs.children[0].type is T.VARIABLE and lhs.children[0].value == "y"
        assert lhs.children[1].type is T.BRACKET

        parsed = parse_protocol(self.Y_PRIME_ZERO)
        lhs = parsed.children[0]
        assert lhs.type is T.MULTIPLY_IMPLICIT
        assert lhs.children[0].type is T.PRIME
        assert lhs.children[1].type is T.BRACKET

    def test_two_conditions(self) -> None:
        source = f"{{system({self.ODE},{self.Y_ZERO},{self.Y_PRIME_ZERO})}}"
        solution = assert_ode(source, order=2, constants=0)
        _check_conditions(source, solution)
        assert "sin(x)" in str(to_sympy(solution)).replace(" ", "").replace("y(x)=", "")

    def test_one_condition_is_not_a_particular_solution(self) -> None:
        source = f"{{system({self.ODE},{self.Y_ZERO})}}"
        assert_ode(source, order=2, constants=1)
        keys = step_keys(source)
        assert keys[-1] == "lesson_calc_ode_conditions_answer"
        assert "diff_eq_find_particular" not in keys

    def test_command_args_still_work(self) -> None:
        solution = assert_ode("{=({prime({y})},{y})}", 1, 0, ["{0}", "{2}"])
        assert to_sympy(solution) == sympy.Eq(sympy.Symbol("y"), 2 * sympy.exp(sympy.Symbol("x")))
        assert (
            step_keys("{=({prime({y})},{y})}", ["{0}", "{2}"])[-1]
            == "lesson_calc_ode_condition_answer"
        )

    def test_first_order_system_condition(self) -> None:
        source = "{system({=({prime({y})},{y})},{=({muli({y},{(0)})},{2})})}"
        solution = assert_ode(source, order=1, constants=0)
        assert to_sympy(solution) == sympy.Eq(sympy.Symbol("y"), 2 * sympy.exp(sympy.Symbol("x")))


class TestAnswerForm:
    """#5: модуль в логарифме, действительная форма, имена постоянных."""

    def test_log_of_the_independent_variable_has_absolute_value(self) -> None:
        solution = assert_ode("{=({derivation2_prime({y})},{frac({1},{x})})}", 2, 2)
        logs = [
            node
            for node in solution.walk()
            if node.type is T.LN and node.children and node.children[0].type is T.ABS
        ]
        assert logs, solution.to_contract()

    def test_homogeneous_answer_keeps_absolute_value(self) -> None:
        solution = assert_ode("{=({prime({y})},{frac({x+y},{x})})}", 1, 1)
        assert any(node.type is T.LN and node.children[0].type is T.ABS for node in solution.walk())

    def test_log_of_a_linear_expression_has_absolute_value(self) -> None:
        solution = assert_ode("{=({prime({y})},{frac({1},{2*x+1})})}", 1, 1)
        logs = [
            node
            for node in solution.walk()
            if node.type is T.LN and node.children and node.children[0].type is T.ABS
        ]
        assert logs, solution.to_contract()

    def test_imaginary_root_pair_becomes_a_real_form(self) -> None:
        solution = assert_ode("{=({prime({y})*cos({x})},{y})}", 1, 1)
        assert T.ROOT2 not in _types(solution)
        expression = to_sympy(solution).rhs
        assert not expression.has(sympy.I)
        assert expression.has(sympy.tan(sympy.Symbol("x")))

    def test_first_order_constant_is_c(self) -> None:
        solution = assert_ode("{=({prime({y})},{x*y})}", 1, 1)
        assert _constants(solution, "y", "x") == [{"C"}]

    def test_higher_order_constants_are_c1_and_c2(self) -> None:
        solution = assert_ode("{=({derivation2_prime({y})+y},{0})}", 2, 2)
        assert _constants(solution, "y", "x") == [{"C1", "C2"}]

    def test_explicit_answer_is_preferred(self) -> None:
        solution = assert_ode("{=({prime({y})},{y})}", 1, 1)
        assert solution.type is T.EQUALS
        assert solution.children[0].type is T.VARIABLE
        assert solution.children[0].value == "y"

    def test_implicit_answer_when_no_explicit_one_exists(self) -> None:
        solution = assert_ode("{=({prime({y})},{frac({-2*x*y},{x^2+3*y^2})})}", 1, 1)
        # Точное уравнение: x²y + y³ = C, левая часть не ``y``.
        assert solution.type is T.EQUALS
        assert solution.children[0].type is not T.VARIABLE


class TestFirstOrderCards:
    """The first-order cards: stages, facts, chains and the textbook answers."""

    @pytest.mark.parametrize(
        ("name", "source", "args"), FIRST_ORDER, ids=[row[0] for row in FIRST_ORDER]
    )
    def test_card_rules(self, name: str, source: str, args: list[str] | None) -> None:
        assert_ode(source, 1, 0 if args else 1, args)
        _assert_card_rules(source, args)

    def test_separable_stages(self) -> None:
        assert step_keys(FIRST_ORDER[0][1]) == [
            "lesson_calc_ode_sep_derivative",
            "lesson_calc_ode_sep_separate",
            "lesson_calc_ode_sep_integrate",
            "lesson_calc_ode_sep_primitive",
            "lesson_calc_ode_sep_express_log",
        ]

    def test_separable_facts(self) -> None:
        substeps = _card(FIRST_ORDER[0][1])[0][1]
        derivative = substeps[0]
        assert derivative.left == CoreNode.node(
            T.EQUALS,
            CoreNode.node(T.PRIME, CoreNode.variable("y")),
            CoreNode.node(
                T.DERIVATION1_DIFF,
                CoreNode.variable("x"),
                CoreNode.variable("y"),
            ),
        )
        separated = substeps[1]
        assert separated.left == CoreNode.node(
            T.EQUALS,
            CoreNode.node(
                T.FRACTION,
                CoreNode.variable("dy"),
                CoreNode.variable("y"),
            ),
            CoreNode.node(
                T.MULTIPLY_IMPLICIT,
                CoreNode.variable("x"),
                CoreNode.variable("dx"),
            ),
        )
        assert substeps[2].subresult is not None

    def test_homogeneous_substitution_is_a_fact(self) -> None:
        substeps = _card(FIRST_ORDER[10][1])[0][1]  # fo12
        keys = [sub.description.type for sub in substeps]
        assert keys[:4] == [
            "lesson_calc_ode_hom_form",
            "lesson_calc_ode_hom_substitute",
            "lesson_calc_ode_hom_equation",
            "lesson_calc_ode_hom_reduce",
        ]
        fact = substeps[1]
        assert fact.right is None
        assert fact.left is not None and fact.left.type is T.LIST
        assert fact.left.children[0].children[1].children[0].value == "u"
        assert substeps[5].subresult is not None

    def test_linear_facts_and_nested_integrals(self) -> None:
        substeps = _card(FIRST_ORDER[13][1])[0][1]  # fo14
        keys = [sub.description.type for sub in substeps]
        assert keys == [
            "lesson_calc_ode_lin_substitute",
            "lesson_calc_ode_lin_insert",
            "lesson_calc_ode_lin_choose_v",
            "lesson_calc_ode_lin_v",
            "lesson_calc_ode_lin_v_value",
            "lesson_calc_ode_lin_u_equation",
            "lesson_calc_ode_lin_u",
            "lesson_calc_ode_lin_u_value",
            "lesson_calc_ode_lin_back",
            "lesson_calc_ode_lin_simplify",
        ]
        assert (
            substeps[0].right is None
            and substeps[0].left.children[0].children[1].children[0].value == "u"
        )
        assert substeps[4].left.children[1].type is T.EXP
        assert substeps[3].subresult is not None
        assert substeps[6].subresult is not None
        # y = uv → y = ((x − 1)eˣ + C)e^(−x) → y = x − 1 + Ce^(−x)
        assert substeps[8].left is not None and substeps[8].right is not None
        assert substeps[8].right.structural_eq(substeps[9].left)
        assert substeps[9].right is not None
        assert not substeps[8].right.structural_eq(substeps[9].right)

    def test_bernoulli_substitution_and_nested_linear_card(self) -> None:
        substeps = _card(FIRST_ORDER[20][1])[0][1]  # fo21
        keys = [sub.description.type for sub in substeps]
        assert keys == [
            "lesson_calc_ode_bern_divide",
            "lesson_calc_ode_bern_substitute",
            "lesson_calc_ode_bern_linear",
            "lesson_calc_ode_bern_back",
            "lesson_ode_singular_solution",
        ]
        fact = substeps[1]
        assert fact.right is None and fact.left.type is T.LIST
        assert fact.left.children[0].children[0].value == "z"
        nested = substeps[2].subresult
        assert nested is not None and len(nested.steps) == 1
        assert nested.steps[0].step_headers[0].type == "eq_solve_short"

    def test_exact_card(self) -> None:
        substeps = _card(FIRST_ORDER[23][1])[0][1]  # fo26
        assert [sub.description.type for sub in substeps] == [
            "lesson_calc_ode_ex_differential",
            "lesson_calc_ode_ex_pq",
            "lesson_calc_ode_ex_check",
            "lesson_calc_ode_ex_potential",
            "lesson_calc_ode_ex_answer",
        ]

    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("{=({prime({y})},{x*y})}", sympy.Eq(_Y, _C * sympy.exp(_X**2 / 2))),
            ("{=({prime({y})},{frac({y},{x})})}", sympy.Eq(_Y, _C * _X)),
            (
                "{=({prime({y})},{frac({1+y^2},{1+x^2})})}",
                sympy.Eq(sympy.atan(_Y), sympy.atan(_X) + _C),
            ),
            ("{=({prime({y})},{exp({x+y})})}", sympy.Eq(_Y, -sympy.log(_C - sympy.exp(_X)))),
            (
                "{=({prime({y})*cos({x})},{y})}",
                sympy.Eq(_Y, _C * (1 / sympy.cos(_X) + sympy.tan(_X))),
            ),
            ("{=({prime({y})},{frac({-x},{y})})}", sympy.Eq(_X**2 + _Y**2, _C)),
            (
                "{=({prime({y})},{2*x*y+x})}",
                sympy.Eq(_Y, _C * sympy.exp(_X**2) - sympy.Rational(1, 2)),
            ),
            (
                "{=({prime({y})},{frac({x+y},{x})})}",
                sympy.Eq(_Y, _X * (sympy.log(sympy.Abs(_X)) + _C)),
            ),
            ("{=({prime({y})+y},{x})}", sympy.Eq(_Y, _X - 1 + _C * sympy.exp(-_X))),
            (
                "{=({prime({y})-frac({2*y},{x})},{x^3})}",
                sympy.Eq(_Y, _X**4 / 2 + _C * _X**2),
            ),
            ("{=({prime({y})},{x*y^2-y})}", sympy.Eq(_Y, 1 / (_C * sympy.exp(_X) + _X + 1))),
            ("{=({prime({y})},{frac({y},{x})-y^2})}", sympy.Eq(_Y, 2 * _X / (_C + _X**2))),
            (
                "{=({prime({y})},{frac({-2*x*y},{x^2+3*y^2})})}",
                sympy.Eq(_X**2 * _Y + _Y**3, _C),
            ),
            (
                "{=({prime({y})},{frac({y},{x})+frac({x},{y})})}",
                sympy.Eq(_Y**2 / _X**2, 2 * (sympy.log(sympy.Abs(_X)) + _C)),
            ),
            (
                "{=({prime({y})},{frac({y+root2({x^2+y^2})},{x})})}",
                sympy.Eq(_Y + sympy.sqrt(_X**2 + _Y**2), _C * _X**2),
            ),
        ],
    )
    def test_answer_forms(self, source: str, expected: sympy.Eq) -> None:
        value = to_sympy(answer(source))
        assert isinstance(value, sympy.Eq)
        assert sympy.simplify(value.lhs - expected.lhs) == sympy.Integer(0)
        assert sympy.simplify(value.rhs - expected.rhs) == sympy.Integer(0)

    def test_cauchy_answer_form(self) -> None:
        value = to_sympy(answer("{=({prime({y})},{y^2})}", ["{1}", "{1}"]))
        assert isinstance(value, sympy.Eq)
        assert sympy.simplify(value.lhs - _Y) == sympy.Integer(0)
        assert sympy.simplify(value.rhs - 1 / (2 - _X)) == sympy.Integer(0)

    def test_step_heading_is_solve_the_equation(self) -> None:
        headers = vertical(FIRST_ORDER[0][1]).steps[0].step_headers
        assert [header.type for header in headers] == ["eq_solve_short"]

    def test_condition_is_a_separate_step(self) -> None:
        groups = _card(FIRST_ORDER[24][1], FIRST_ORDER[24][2])  # fo27
        assert [headers for headers, _ in groups] == [
            ["eq_solve_short"],
            ["lesson_calc_ode_condition_header"],
        ]
        keys = [sub.description.type for sub in groups[1][1]]
        assert keys == [
            "lesson_calc_ode_condition",
            "lesson_calc_ode_condition_value",
            "lesson_calc_ode_condition_answer",
        ]


class TestSecondOrderCards:
    """The second-order cards: stages, facts, the case, the constants system."""

    @pytest.mark.parametrize(
        ("name", "source", "conditions", "first"),
        SECOND_ORDER,
        ids=[row[0] for row in SECOND_ORDER],
    )
    def test_card_rules(self, name: str, source: str, conditions: int, first: str) -> None:
        assert_ode(source, 2, 2 - conditions)
        _assert_card_rules(source, first=first)

    @pytest.mark.parametrize(
        ("source", "header"),
        [
            (SECOND_ORDER[0][1], "lesson_calc_ode_header_reduction"),
            (SECOND_ORDER[3][1], "lesson_calc_ode_header_reduction"),
            (SECOND_ORDER[5][1], "lesson_calc_ode_header_constant"),
            (SECOND_ORDER[13][1], "lesson_calc_ode_header_constant"),
            (SECOND_ORDER[15][1], "lesson_calc_ode_header_special"),
            (SECOND_ORDER[21][1], "lesson_calc_ode_header_special"),
        ],
        ids=["reduction", "reducible", "constant", "complex", "special-exp", "special-trig"],
    )
    def test_header_names_the_method(self, source: str, header: str) -> None:
        card = vertical(source)
        assert card.header is not None
        assert card.header.type == header

    def test_reduction_stages_and_nested_integrals(self) -> None:
        source = SECOND_ORDER[0][1]  # y″ = x
        keys = [sub.description.type for sub in _substeps(source)]
        assert keys == [
            "diff_eq_solve_by_integration",
            "lesson_calc_ode_reduce_first",
            "lesson_calc_ode_reduce_second",
        ]
        first = _stage(source, "lesson_calc_ode_reduce_first")
        second = _stage(source, "lesson_calc_ode_reduce_second")
        assert first.subresult is not None and second.subresult is not None
        assert first.right is not None and second.left is not None
        assert first.right.structural_eq(second.left)

    def test_reducible_stages_and_nested_first_order_card(self) -> None:
        source = SECOND_ORDER[3][1]  # x·y″ = y′
        keys = [sub.description.type for sub in _substeps(source)]
        assert keys == [
            "lesson_ode_reduction_of_order",
            "lesson_calc_ode_reduce_substitute",
            "lesson_calc_ode_reduce_equation",
            "lesson_calc_ode_reduce_solution",
            "lesson_calc_ode_reduce_integrate",
        ]
        nested = _stage(source, "lesson_calc_ode_reduce_equation").subresult
        assert nested is not None
        assert nested.header is not None
        assert nested.header.type == "lesson_calc_ode_header_separable"
        nested_keys = [sub.description.type for step in nested.steps for sub in step.substeps]
        assert nested_keys[0] == "lesson_calc_ode_sep_derivative"
        # p′ = p/x: the nested card works in p, not in y.
        derivative = nested.steps[0].substeps[0]
        assert derivative.left is not None
        assert derivative.left.children[0].children[0].value == "p"

    def test_characteristic_equation_and_roots_are_facts(self) -> None:
        source = SECOND_ORDER[5][1]  # y″ − 3y′ + 2y = 0
        keys = [sub.description.type for sub in _substeps(source)]
        assert keys == [
            "lesson_ode_constant_coeff_homogeneous",
            "lesson_calc_ode_char_equation",
            "lesson_calc_ode_char_roots",
            "lesson_calc_ode_char_case_distinct",
            "lesson_calc_ode_char_general",
        ]
        equation = _stage(source, "lesson_calc_ode_char_equation")
        assert equation.right is None and equation.left is not None
        lam = sympy.Symbol("λ")
        left = to_sympy(equation.left)
        assert isinstance(left, sympy.Eq)
        assert sympy.simplify(left.lhs - (lam**2 - 3 * lam + 2)) == sympy.Integer(0)
        assert left.rhs == 0
        roots = _stage(source, "lesson_calc_ode_char_roots")
        assert roots.subresult is not None
        assert roots.left is not None and roots.left.structural_eq(equation.left)
        values = {to_sympy(branch.children[1]) for branch in branches(roots.right)}
        assert values == {sympy.Integer(1), sympy.Integer(2)}
        case = _stage(source, "lesson_calc_ode_char_case_distinct")
        assert case.left is not None and case.left.type is T.LIST
        assert [child.children[0].value for child in case.left.children] == ["y1", "y2"]

    def test_nested_quadratic_card(self) -> None:
        roots = _stage(SECOND_ORDER[5][1], "lesson_calc_ode_char_roots")
        nested = roots.subresult
        assert nested is not None and nested.header is not None
        assert nested.header.type == "lesson_calc_ode_header_characteristic"
        nested_keys = [sub.description.type for step in nested.steps for sub in step.substeps]
        assert "eq_quad_disc" in nested_keys
        assert "eq_quad_solve_in_r" in nested_keys

    def test_double_root_case(self) -> None:
        source = SECOND_ORDER[9][1]  # y″ − 2y′ + y = 0
        keys = [sub.description.type for sub in _substeps(source)]
        assert "lesson_calc_ode_char_case_double" in keys
        assert to_sympy(answer(source)) == sympy.Eq(
            _Y, (_C + sympy.Symbol("C2") * _X) * sympy.exp(_X)
        ).subs(_C, sympy.Symbol("C1"))

    def test_complex_root_case_is_named_with_alpha_and_beta(self) -> None:
        source = SECOND_ORDER[13][1]  # y″ + 2y′ + 5y = 0
        case = _stage(source, "lesson_calc_ode_char_case_complex")
        assert [to_sympy(argument) for argument in case.description.args] == [-1, 2]
        assert to_sympy(answer(source)) == sympy.Eq(
            _Y,
            sympy.exp(-_X) * (_C * sympy.cos(2 * _X) + sympy.Symbol("C2") * sympy.sin(2 * _X)),
        ).subs(_C, sympy.Symbol("C1"))

    def test_special_card_has_three_distinct_steps(self) -> None:
        source = SECOND_ORDER[15][1]  # y″ − 3y′ + 2y = eˣ
        groups = _card(source)
        assert [headers[0] for headers, _ in groups] == [
            "lesson_calc_ode_step_homogeneous",
            "lesson_calc_ode_step_particular",
            "lesson_calc_ode_step_general",
        ]
        keys = [sub.description.type for sub in groups[1][1]]
        assert keys == [
            "lesson_calc_ode_special_form_exp_resonance",
            "lesson_calc_ode_special_derivatives",
            "lesson_calc_ode_special_substitute",
            "lesson_calc_ode_special_equate",
            "lesson_calc_ode_special_solve",
            "lesson_calc_ode_special_particular",
        ]

    def test_resonance_multiplier_is_named(self) -> None:
        form = _stage(SECOND_ORDER[15][1], "lesson_calc_ode_special_form_exp_resonance")
        assert [to_sympy(argument) for argument in form.description.args[:2]] == [1, 1]
        assert form.description.args[2].type is T.VARIABLE
        assert form.description.args[2].value == "x"
        assert form.left is not None and form.right is None
        assert form.left.children[0].value == "ỹ"
        assert form.left.children[1].children[0].value == "x"

    def test_special_derivatives_and_coefficient_system(self) -> None:
        source = SECOND_ORDER[17][1]  # y″ + y = x
        derivatives = _stage(source, "lesson_calc_ode_special_derivatives")
        assert derivatives.left is not None and derivatives.left.type is T.LIST
        assert len(derivatives.left.children) == 2
        equate = _stage(source, "lesson_calc_ode_special_equate")
        assert equate.right is None and equate.left is not None
        assert equate.left.type is T.LIST
        assert [to_sympy(child.children[1]) for child in equate.left.children] == [1, 0]

    def test_special_answer_keeps_homogeneous_part_first(self) -> None:
        value = to_sympy(answer(SECOND_ORDER[21][1]))  # y″ + y = sin x
        assert isinstance(value, sympy.Eq)
        expected = (
            sympy.Symbol("C1") * sympy.cos(_X)
            + sympy.Symbol("C2") * sympy.sin(_X)
            - _X * sympy.cos(_X) / 2
        )
        assert sympy.simplify(value.rhs - expected) == sympy.Integer(0)

    def test_cauchy_constants_system(self) -> None:
        source = SECOND_ORDER[25][1]  # y″ + y = 0, y(0) = 0, y′(0) = 1
        groups = _card(source)
        assert groups[-1][0] == ["lesson_calc_ode_step_conditions"]
        keys = [sub.description.type for sub in groups[-1][1]]
        assert keys == [
            "lesson_calc_ode_conditions_system",
            "lesson_calc_ode_conditions_values",
            "lesson_calc_ode_conditions_answer",
        ]
        system = _stage(source, "lesson_calc_ode_conditions_system")
        assert system.left is not None and system.left.type is T.LIST
        assert len(system.left.children) == 2
        for equation in system.left.children:
            assert equation.type is T.EQUALS and len(equation.children) == 3
            assert equation.children[0].type is T.EVALUATE_EXPRESSION
        values = _stage(source, "lesson_calc_ode_conditions_values")
        assert values.left is not None and values.left.type is T.LIST
        assert [to_sympy(child.children[1]) for child in values.left.children] == [0, 1]
        assert to_sympy(answer(source)) == sympy.Eq(_Y, sympy.sin(_X))

    def test_cauchy_with_one_condition_keeps_one_constant(self) -> None:
        solution = assert_ode(SECOND_ORDER[26][1], 2, 1)
        assert _constants(solution, "y", "x") == [{"C1"}]

    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            (
                SECOND_ORDER[5][1],
                sympy.Eq(
                    _Y,
                    _C * sympy.exp(_X) + sympy.Symbol("C2") * sympy.exp(2 * _X),
                ).subs(_C, sympy.Symbol("C1")),
            ),
            (
                SECOND_ORDER[7][1],
                sympy.Eq(
                    _Y,
                    _C * sympy.exp(_X) + sympy.Symbol("C2") * sympy.exp(-_X),
                ).subs(_C, sympy.Symbol("C1")),
            ),
            (
                SECOND_ORDER[9][1],
                sympy.Eq(_Y, (_C + sympy.Symbol("C2") * _X) * sympy.exp(_X)).subs(
                    _C, sympy.Symbol("C1")
                ),
            ),
            (
                SECOND_ORDER[11][1],
                sympy.Eq(
                    _Y,
                    _C * sympy.cos(_X) + sympy.Symbol("C2") * sympy.sin(_X),
                ).subs(_C, sympy.Symbol("C1")),
            ),
            (
                SECOND_ORDER[13][1],
                sympy.Eq(
                    _Y,
                    sympy.exp(-_X)
                    * (_C * sympy.cos(2 * _X) + sympy.Symbol("C2") * sympy.sin(2 * _X)),
                ).subs(_C, sympy.Symbol("C1")),
            ),
            (
                SECOND_ORDER[15][1],
                sympy.Eq(
                    _Y,
                    _C * sympy.exp(_X)
                    + sympy.Symbol("C2") * sympy.exp(2 * _X)
                    - _X * sympy.exp(_X),
                ).subs(_C, sympy.Symbol("C1")),
            ),
            (
                SECOND_ORDER[17][1],
                sympy.Eq(
                    _Y,
                    _C * sympy.cos(_X) + sympy.Symbol("C2") * sympy.sin(_X) + _X,
                ).subs(_C, sympy.Symbol("C1")),
            ),
            (
                SECOND_ORDER[19][1],
                sympy.Eq(
                    _Y,
                    _C * sympy.exp(_X)
                    + sympy.Symbol("C2") * sympy.exp(-_X)
                    + sympy.exp(2 * _X) / 3,
                ).subs(_C, sympy.Symbol("C1")),
            ),
            (
                SECOND_ORDER[21][1],
                sympy.Eq(
                    _Y,
                    _C * sympy.cos(_X)
                    + sympy.Symbol("C2") * sympy.sin(_X)
                    - _X * sympy.cos(_X) / 2,
                ).subs(_C, sympy.Symbol("C1")),
            ),
            (
                SECOND_ORDER[23][1],
                sympy.Eq(
                    _Y,
                    _C * sympy.cos(2 * _X)
                    + sympy.Symbol("C2") * sympy.sin(2 * _X)
                    + _X * sympy.sin(2 * _X) / 4,
                ).subs(_C, sympy.Symbol("C1")),
            ),
            (SECOND_ORDER[27][1], sympy.Eq(_Y, _X**3 + 1)),
            (
                SECOND_ORDER[28][1],
                sympy.Eq(_Y, _X**3 + sympy.Symbol("C1") * _X + 1),
            ),
        ],
        ids=[
            "distinct",
            "distinct-negative",
            "double",
            "complex",
            "complex-alpha",
            "resonance",
            "polynomial",
            "exponential",
            "trig-resonance",
            "trig-resonance-2x",
            "cauchy-reduction",
            "cauchy-one-condition",
        ],
    )
    def test_answer_forms(self, source: str, expected: sympy.Eq) -> None:
        value = to_sympy(answer(source))
        assert isinstance(value, sympy.Eq)
        assert sympy.simplify(value.lhs - expected.lhs) == sympy.Integer(0)
        assert sympy.simplify(value.rhs - expected.rhs) == sympy.Integer(0)


class TestMethodNames:
    """#6, #14: метод назван по учебной рубрике."""

    @pytest.mark.parametrize(
        ("source", "header"),
        [
            ("{=({prime({y})},{x*y})}", "lesson_calc_ode_header_separable"),
            ("{=({prime({y})},{x*y+x})}", "lesson_calc_ode_header_separable"),
            ("{=({prime({y})},{frac({x+y},{x})})}", "lesson_calc_ode_header_homogeneous"),
            ("{=({prime({y})+y},{x})}", "lesson_calc_ode_header_linear"),
            ("{=({prime({y})},{x*y^2-y})}", "lesson_calc_ode_header_bernoulli"),
            (
                "{=({prime({y})},{frac({-2*x*y},{x^2+3*y^2})})}",
                "lesson_calc_ode_header_exact",
            ),
        ],
    )
    def test_first_order_method(self, source: str, header: str) -> None:
        solution = vertical(source)
        assert solution.header is not None
        assert solution.header.type == header

    @pytest.mark.parametrize(
        ("source", "key"),
        [
            ("{=({derivation2_prime({y})},{x})}", "diff_eq_solve_by_integration"),
            (
                "{=({derivation2_prime({y})},{frac({prime({y})},{x})})}",
                "lesson_ode_reduction_of_order",
            ),
            (
                "{=({derivation2_prime({y})-3*prime({y})+2*y},{0})}",
                "lesson_ode_constant_coeff_homogeneous",
            ),
            (
                "{=({derivation2_prime({y})+y},{sin({x})})}",
                "lesson_ode_constant_coeff_special",
            ),
            (
                "{=({derivation2_prime({y})+y},{sec({x})})}",
                "lesson_ode_variation_of_constants",
            ),
        ],
    )
    def test_higher_order_method(self, source: str, key: str) -> None:
        assert step_keys(source)[0] == key

    def test_exact_equation_is_not_a_timeout(self) -> None:
        source = "{=({prime({y})},{frac({-2*x*y},{x^2+3*y^2})})}"
        assert_ode(source, 1, 1)


class TestLostSingularSolution:
    """#7: потерянное при делении ``y = 0`` показывается отдельным шагом."""

    def test_bernoulli_loses_zero(self) -> None:
        assert_ode("{=({prime({y})},{x*y^2-y})}", 1, 1)
        keys = step_keys("{=({prime({y})},{x*y^2-y})}")
        assert keys[-1] == "lesson_ode_singular_solution"
        note = vertical("{=({prime({y})},{x*y^2-y})}").steps[-1].substeps[-1]
        assert note.left is not None and note.left.children[0].value == "y"
        assert note.left.children[1].value == "0"

    def test_separable_zero_is_in_the_family(self) -> None:
        assert "lesson_ode_singular_solution" not in step_keys("{=({prime({y})},{x*y})}")

    def test_yprime_equal_y_squared_loses_zero(self) -> None:
        assert "lesson_ode_singular_solution" in step_keys("{=({prime({y})},{y^2})}")


class TestRouting:
    def test_system_without_derivative_is_not_an_ode(self) -> None:
        assert not is_diff_equation(parse_protocol("{system({=({x+y},{3})},{=({x-y},{1})})}"))

    def test_system_of_two_odes_is_not_one_equation(self) -> None:
        source = "{system({=({prime({y})},{z})},{=({prime({z})},{-y})})}"
        assert not is_diff_equation(parse_protocol(source))

    def test_command_rejects_a_plain_equation(self) -> None:
        with pytest.raises(SolveError):
            solve(parse_protocol("{=({y},{x})}"), command="diff_eq")


def test_separation_keeps_the_number_with_dx() -> None:
    """y′ = 2x → dy = 2x dx; y′ = 2xy → dy/y = 2x dx; y′ = −y → dy/y = −dx."""
    plain = _stage("{=({prime({y})},{2x})}", "lesson_calc_ode_sep_separate").left
    assert plain is not None and plain.children[0].value == "dy"
    product = _stage("{=({prime({y})},{2xy})}", "lesson_calc_ode_sep_separate").left
    assert product is not None and product.children[0].type is T.FRACTION
    assert product.children[0].children[1].value == "y"
    minus = _stage("{=({prime({y})},{-y})}", "lesson_calc_ode_sep_separate").left
    assert minus is not None and minus.children[1].type is T.NEGATIVE


def test_direct_integration_writes_y_not_integral_of_one() -> None:
    """y′ = 2x: dy = 2x dx → y = ∫2x dx → y = x² + C (∫1 would be drawn with dx)."""
    source = "{=({prime({y})},{2x})}"
    integrate = _stage(source, "lesson_calc_ode_sep_integrate")
    assert integrate.right is not None and integrate.right.children[0].value == "y"
    keys = [sub.description.type for sub in _substeps(source)]
    assert "lesson_calc_ode_sep_express" not in keys
    assert "lesson_calc_ode_sep_express_rename" not in keys


def test_card_products_are_written_without_a_dot() -> None:
    """Products without a dot: y = x − 1 + Ce^(−x), u = (x − 1)eˣ + C, not C·e^(−x)."""
    source = "{=({add({prime({y})},{y})},{x})}"
    nodes = [answer(source)]
    for sub in _substeps(source):
        nodes += [node for node in (sub.left, sub.right) if node is not None]
    assert not [node for root in nodes for node in root.walk() if node.type is T.MULTIPLY]


def test_separation_writes_dx_over_x_and_the_constant_as_a_formula() -> None:
    """xy′ = y: dy/y = dx/x (not 1/x·dx); «C = ±e^(C₀)» carries e^(C₀) as a formula."""
    source = "{=({muli({x},{prime({y})})},{y})}"
    separated = _stage(source, "lesson_calc_ode_sep_separate").left
    assert separated is not None
    right = separated.children[1]
    assert right.type is T.FRACTION and right.children[0].value == "dx"
    express = _stage(source, "lesson_calc_ode_sep_express_log")
    assert [arg.type for arg in express.description.args] == [T.EXP]
