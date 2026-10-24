"""Определители матриц.

Модуль зарегистрирован на ``DETERMINANT2``, ``DETERMINANT3``,
``DETERMINANT3_SARRUS``, ``DETERMINANT4``, ``DETERMINANT5`` и общий
``DETERMINANT``. Дети — элементы в порядке «по строкам» (``row = i / n``,
``col = i % n``).
Допустимы и строки ``MATRIX_ROW``: их элементы разворачиваются в тот же
порядок.

Определитель 2×2 берётся по формуле ``ad − bc``, больший — разложением по
строке или столбцу с наибольшим числом нулей (у 3×3 — по первой строке).
Элементы могут быть числами, буквами или функциями.

Ключи шагов: ``det2_calc`` / ``det2_determinant_rule`` (2×2),
``det3_cofactor_eval`` (3×3), ``det_laplace_rule_row`` /
``det_laplace_rule_col`` (4×4 и выше, с номером строки/столбца в ``args``).
"""

from __future__ import annotations

from fractions import Fraction
from math import isqrt

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .arithmetic import as_fraction, format_number, number_of
from .base import Command, SolveContext, SolveError, SolveResult, Step, route, solver_for
from .methods import method_provider
from .sympy_bridge import from_sympy, to_sympy

_DETERMINANTS = (
    T.DETERMINANT,
    T.DETERMINANT2,
    T.DETERMINANT3,
    T.DETERMINANT3_SARRUS,
    T.DETERMINANT4,
    T.DETERMINANT5,
)

_DET_TYPES = {
    2: T.DETERMINANT2,
    3: T.DETERMINANT3,
    4: T.DETERMINANT4,
    5: T.DETERMINANT5,
}

_MAX_SIZE = 6


def _elements(node: CoreNode) -> list[CoreNode]:
    """Плоский список элементов: строки ``MATRIX_ROW`` разворачиваются."""
    if node.children and all(child.type is T.MATRIX_ROW for child in node.children):
        return [element for row in node.children for element in row.children]
    return list(node.children)


def _determinant(values: list[Fraction], size: int) -> Fraction:
    """Определитель ``size × size`` разложением по первой строке."""
    if size == 1:
        return values[0]
    total = Fraction(0)
    for column in range(size):
        minor = [
            values[row * size + col]
            for row in range(1, size)
            for col in range(size)
            if col != column
        ]
        total += (1 if column % 2 == 0 else -1) * values[column] * _determinant(minor, size - 1)
    return total


def _det_node(matrix: sympy.Matrix) -> CoreNode:
    """A determinant node whose size the renderer can see (2×2 … 5×5)."""
    kind = _DET_TYPES.get(matrix.rows, T.DETERMINANT)
    return CoreNode.node(kind, *[from_sympy(cell) for cell in matrix])


def _numeric_values(elements: list[CoreNode], ctx: SolveContext) -> list[Fraction] | None:
    """Fold every cell to a number; ``None`` for letters/functions (no steps committed)."""
    scratch = SolveResult()
    scratch_ctx = SolveContext(result=scratch, variables=list(ctx.variables))
    values: list[Fraction] = []
    for element in elements:
        try:
            values.append(as_fraction(route(element, scratch_ctx)))
        except SolveError:
            return None
    for step in scratch:
        ctx.result.add(step)
    return values


def _line_for(size: int, matrix: sympy.Matrix) -> tuple[str, int, int]:
    """Row or column to expand along, matching the nested detail's choice."""
    from ..teaching_discrete import choose_line

    return choose_line(matrix) if size >= 4 else ("row", 0, 0)


def _rule_node() -> CoreNode:
    """``|a b; c d| = a·d − b·c``: the formula, never the already-computed answer."""
    eq = CoreNode.node
    letters = [CoreNode.variable(name) for name in "abcd"]
    return eq(
        T.EQUALS,
        eq(T.DETERMINANT2, *letters),
        eq(
            T.SUBTRACT,
            eq(T.MULTIPLY, letters[0], letters[3]),
            eq(T.MULTIPLY, letters[1], letters[2]),
        ),
    )


def _signed_sum(terms: list[tuple[int, CoreNode]]) -> CoreNode:
    """``a·m − b·m + c·m``: alternating signs, not ``a·m + −b·m``."""
    eq = CoreNode.node
    expression: CoreNode | None = None
    for sign, term in terms:
        if expression is None:
            expression = term if sign > 0 else eq(T.NEGATIVE, term)
        elif sign > 0:
            expression = eq(T.ADD, expression, term)
        else:
            expression = eq(T.SUBTRACT, expression, term)
    return expression if expression is not None else CoreNode.constant("0")


def _bracket(node: CoreNode) -> CoreNode:
    return CoreNode.node(T.BRACKET, node) if node.type in (T.ADD, T.SUBTRACT) else node


def _expanded_expression(matrix: sympy.Matrix) -> CoreNode:
    """The cofactor expansion as a node, keeping the minors' products visible."""
    eq = CoreNode.node
    size = matrix.rows
    if size == 2:
        return eq(
            T.SUBTRACT,
            eq(T.MULTIPLY, from_sympy(matrix[0, 0]), from_sympy(matrix[1, 1])),
            eq(T.MULTIPLY, from_sympy(matrix[0, 1]), from_sympy(matrix[1, 0])),
        )
    if size == 3:
        terms = [
            (
                1 if column % 2 == 0 else -1,
                eq(
                    T.MULTIPLY,
                    from_sympy(matrix[0, column]),
                    _bracket(_expanded_expression(matrix.minor_submatrix(0, column))),
                ),
            )
            for column in range(3)
        ]
        return _signed_sum(terms)
    return from_sympy(sympy.expand(matrix.det()))


def _num(value: Fraction) -> CoreNode:
    return CoreNode.constant(format_number(value))


def _mul(first: CoreNode, second: CoreNode) -> CoreNode:
    return CoreNode.node(T.MULTIPLY, first, second)


def _sub(first: CoreNode, second: CoreNode) -> CoreNode:
    return CoreNode.node(T.SUBTRACT, first, second)


def _neg(node: CoreNode) -> CoreNode:
    return CoreNode.node(T.NEGATIVE, node)


def _strip_sign(node: CoreNode) -> CoreNode:
    """A negative term's positive twin for ``a − x`` rows (the card drops the minus)."""
    text = node.value or ""
    if node.type is T.CONSTANT and text.startswith("-"):
        return CoreNode.constant(text[1:])
    if node.type is T.NEGATIVE and node.children:
        return node.children[0]
    if node.type is T.MULTIPLY:
        children = list(node.children)
        for index, child in enumerate(children):
            child_text = child.value or ""
            if child.type is T.CONSTANT and child_text.startswith("-"):
                children[index] = CoreNode.constant(child_text[1:])
                return CoreNode.node(T.MULTIPLY, *children)
            if child.type is T.NEGATIVE and child.children:
                children[index] = child.children[0]
                return CoreNode.node(T.MULTIPLY, *children)
    return node


def _render_chain(terms: list[tuple[CoreNode, Fraction]]) -> CoreNode:
    """``a − b + c`` rendered from terms whose signs live in their numeric values."""
    if not terms:
        return _num(Fraction(0))
    node, value = terms[0]
    expression = node if value >= 0 else _neg(_strip_sign(node))
    for node, value in terms[1:]:
        if value < 0:
            expression = _sub(expression, _strip_sign(node))
        else:
            expression = CoreNode.node(T.ADD, expression, node)
    return expression


def _scale_node(factor: Fraction, node: CoreNode) -> CoreNode:
    if factor == 1:
        return node
    if factor == -1:
        return _neg(node)
    return _mul(_num(factor), node)


def _product_detail(
    first: CoreNode, second: CoreNode, value: Fraction, *, subtract: bool = False
) -> SolveResult:
    """A product's own page: the sign message, then the product.

    ``subtract`` is the second product of ``ad − bc``: the card carries the outer minus
    into it and reasons about a negative times a positive.
    """
    eq = CoreNode.node
    first_value = as_fraction(first) if first.type is T.CONSTANT else Fraction(1)
    second_value = as_fraction(second) if second.type is T.CONSTANT else Fraction(1)
    if subtract and first_value > 0 and second_value > 0:
        key = "mul_neg_pos"
        source = _mul(_neg(first), second)
        target: CoreNode = _neg(_bracket(_mul(first, second)))
    elif first_value < 0 and second_value < 0:
        key = "mul_neg_neg"
        source = _mul(first, second)
        target = _mul(_strip_sign(first), _strip_sign(second))
    elif first_value < 0:
        key = "mul_neg_pos"
        source = _mul(first, second)
        target = _neg(_bracket(_mul(_strip_sign(first), second)))
    elif second_value < 0:
        key = "mul_pos_neg"
        source = _mul(first, second)
        target = _neg(_bracket(_mul(first, _strip_sign(second))))
    else:
        key = "mul"
        source = _mul(first, second)
        target = _mul(first, second)
    detail = SolveResult()
    letters = CoreNode.variable("a"), CoreNode.variable("b")
    positive = CoreNode.node(T.BRACKET, _mul(letters[0], letters[1]))
    if key == "mul":
        detail.add_group("multiply", Step(source, _num(value), "mul"))
    elif key == "mul_neg_neg":
        law = eq(
            T.EQUALS,
            _mul(_neg(letters[0]), _neg(letters[1])),
            _mul(letters[0], letters[1]),
        )
        detail.add_group("neg_mul_msg", Step(source, target, "mul_neg_neg", [law]))
        detail.add_group("multiply", Step(target, _num(value), "mul"))
    else:
        first_negative = key == "mul_neg_pos"
        law = eq(
            T.EQUALS,
            _mul(
                _neg(letters[0]) if first_negative else letters[0],
                letters[1] if first_negative else _neg(letters[1]),
            ),
            _neg(positive),
        )
        detail.add_group("neg_mul_msg", Step(source, target, key, [law]))
        detail.add_group("multiply", Step(target, _num(value), "mul"))
    detail.set_solution(_num(value))
    return detail


def _det2_detail(values: list[Fraction], cells: list[CoreNode], *, elaborate: bool) -> SolveResult:
    """A 2×2 determinant evaluated on its own page."""
    a, b, c, d = (cells[0], cells[1], cells[2], cells[3])
    second = _mul(b, c)
    expanded = _sub(_mul(a, d), second)
    first_value, second_value = values[0] * values[3], values[1] * values[2]
    total = first_value - second_value
    detail = SolveResult()
    detail.add_group(
        "det_evaluate",
        Step(
            _det_node(sympy.Matrix(2, 2, values)), expanded, "det2_determinant_rule", [_rule_node()]
        ),
    )
    current = expanded
    one = values[0] == 1 or values[3] == 1
    if one:
        nxt = _sub(d if values[0] == 1 else a, second)
        detail.add_group("multiply", Step(current, nxt, "mul_with_one", [_num(Fraction(1))]))
    else:
        nxt = _sub(_num(first_value), second)
        subresult = _product_detail(a, d, first_value) if elaborate else None
        detail.add_group("multiply", Step(current, nxt, "mul", subresult=subresult))
    current = nxt
    done = _sub(_num(first_value), _num(second_value))
    subresult = _product_detail(b, c, second_value, subtract=True) if elaborate else None
    detail.add_group("multiply", Step(current, done, "mul", subresult=subresult))
    if total < 0:
        diff_detail = None
        if elaborate:
            diff_detail = SolveResult()
            flipped = _neg(_sub(_num(second_value), _num(first_value)))
            diff_detail.add_group("extract_neg", Step(done, flipped, "add_sign_sub"))
            diff_detail.add_group("calculate_short", Step(flipped, _num(total), "sub"))
            diff_detail.set_solution(_num(total))
        detail.add_group(
            "calculate_short", Step(done, _num(total), "calc_diff", subresult=diff_detail)
        )
    else:
        detail.add_group("calculate_short", Step(done, _num(total), "sub"))
    detail.set_solution(_num(total))
    return detail


def _det2_arithmetic(
    ctx: SolveContext, values: list[Fraction], cells: list[CoreNode], expanded: CoreNode
) -> CoreNode:
    """The ``ad``, ``bc`` and ``ad − bc`` rows of a 2×2 determinant (the pages)."""
    a, b, c, d = cells
    first_value, second_value = values[0] * values[3], values[1] * values[2]
    total = first_value - second_value
    second = _mul(b, c)
    current = expanded
    # «ad» and «bc» are two pages of one row in the UI (case ``mat_det``:
    # row 3 = «Любое выражение, умноженное на 1» | «Умножьте числа»).
    pages: list[Step] = []
    if values[0] == 1 or values[3] == 1:
        current = _sub(d if values[0] == 1 else a, second)
        pages.append(Step(expanded, current, "mul_with_one", [_num(Fraction(1))]))
    else:
        current = _sub(_num(first_value), second)
        pages.append(Step(expanded, current, "mul", subresult=_product_detail(a, d, first_value)))
    done = _sub(_num(first_value), _num(second_value))
    pages.append(
        Step(current, done, "mul", subresult=_product_detail(b, c, second_value, subtract=True))
    )
    ctx.result.add_group("multiply", *pages)
    if total < 0:
        detail = SolveResult()
        flipped = _neg(_sub(_num(second_value), _num(first_value)))
        detail.add_group("extract_neg", Step(done, flipped, "add_sign_sub"))
        detail.add_group("calculate_short", Step(flipped, _num(total), "sub"))
        detail.set_solution(_num(total))
        ctx.result.add_group(
            "calculate_short", Step(done, _num(total), "calc_diff", subresult=detail)
        )
    else:
        ctx.result.add_group("calculate_short", Step(done, _num(total), "sub"))
    return _num(total)


def _has_zero_line(matrix: sympy.Matrix) -> bool:
    rows = [all(cell == 0 for cell in matrix.row(index)) for index in range(matrix.rows)]
    cols = [all(cell == 0 for cell in matrix.col(index)) for index in range(matrix.cols)]
    return any(rows) or any(cols)


def _pm_line(matrix: sympy.Matrix) -> tuple[str, int]:
    """The card expands along the line with the most zeros (ties: first row, then first column)."""
    size = matrix.rows
    best = ("row", 0, sum(1 for column in range(size) if matrix[0, column] == 0))
    for row in range(1, size):
        zeros = sum(1 for column in range(size) if matrix[row, column] == 0)
        if zeros > best[2]:
            best = ("row", row, zeros)
    for column in range(size):
        zeros = sum(1 for row in range(size) if matrix[row, column] == 0)
        if zeros > best[2]:
            best = ("col", column, zeros)
    return best[0], best[1]


def _laplace_parts(
    matrix: sympy.Matrix,
) -> tuple[str, int, list[tuple[Fraction, sympy.Matrix]]]:
    """``(row|col, index, [(signed factor, minor)])`` for the expansion line."""
    which, index = _pm_line(matrix)
    size = matrix.rows
    terms: list[tuple[Fraction, sympy.Matrix]] = []
    if which == "row":
        coords = [(index, column) for column in range(size)]
    else:
        coords = [(row, index) for row in range(size)]
    for row, column in coords:
        sign = -1 if (row + column) % 2 else 1
        factor = Fraction(matrix[row, column]) * sign
        terms.append((factor, matrix.minor_submatrix(row, column)))
    return which, index, terms


def _laplace_rows(
    result: SolveResult,
    node: CoreNode,
    values: list[Fraction],
    *,
    top: bool,
    solve_nested: bool = True,
) -> CoreNode:
    """The Laplace rows: the expansion, the products, the sum."""
    size = isqrt(len(values))
    matrix = sympy.Matrix(size, size, values)
    num0, num1 = _num(Fraction(0)), _num(Fraction(1))
    which, index, terms = _laplace_parts(matrix)
    key = "det_laplace_rule_row" if which == "row" else "det_laplace_rule_col"
    nodes = [
        _mul(_num(factor), _det_node(minor)) if factor != 1 else _det_node(minor)
        for factor, minor in terms
    ]
    term_values = [factor * Fraction(minor.det()) for factor, minor in terms]
    expanded = _render_chain(list(zip(nodes, term_values, strict=True)))
    result.add_group(
        "det_laplace_rule_col_simple" if which == "col" else "det_laplace_rule_row_simple",
        Step(node, expanded, key, [CoreNode.constant(str(index + 1))]),
    )

    current_nodes = list(nodes)
    current_values = list(term_values)
    current = expanded
    stages: list[Step] = []
    for position, (factor, minor) in enumerate(terms):
        if factor == 0:
            current_nodes[position] = num0
            current_values[position] = Fraction(0)
            nxt = _render_chain(list(zip(current_nodes, current_values, strict=True)))
            stages.append(Step(current, nxt, "mul_with_zero", [num0]))
            current = nxt
            continue
        if factor in (1, -1):
            current_nodes[position] = _det_node(minor) if factor == 1 else _neg(_det_node(minor))
            current_values[position] = term_values[position]
            nxt = _render_chain(list(zip(current_nodes, current_values, strict=True)))
            stages.append(
                Step(
                    current,
                    nxt,
                    "mul_with_one" if factor == 1 else "mul_with_neg_one",
                    [num1 if factor == 1 else _num(Fraction(-1))],
                )
            )
            current = nxt
        minor_values = [Fraction(cell) for cell in minor]
        value = Fraction(minor.det())
        nxt_node = _scale_node(factor, _num(value))
        if factor not in (1, -1):
            current_nodes[position] = nxt_node
        else:
            current_nodes[position] = (
                _num(term_values[position]) if factor == 1 else _neg(_num(-term_values[position]))
            )
        current_values[position] = term_values[position]
        nxt = _render_chain(list(zip(current_nodes, current_values, strict=True)))
        subresult = None
        if solve_nested:
            if minor.rows == 2:
                cells = [from_sympy(cell) for cell in minor]
                subresult = _det2_detail(minor_values, cells, elaborate=False)
            elif minor.rows >= 3 and not _has_zero_line(minor):
                subresult = _laplace_nested(minor)
        stages.append(Step(current, nxt, "det_evaluate", subresult=subresult))
        current = nxt
    result.add_group(["multiply", "evaluate"], *stages)

    products = [
        position for position, (factor, _minor) in enumerate(terms) if factor not in (0, 1, -1)
    ]
    if size == 3 and products and top:
        product_stages: list[Step] = []
        for position in products:
            factor, minor = terms[position]
            value = Fraction(minor.det())
            product_value = factor * value
            current_nodes[position] = _num(product_value)
            current_values[position] = product_value
            nxt = _render_chain(list(zip(current_nodes, current_values, strict=True)))
            product_stages.append(
                Step(
                    current,
                    nxt,
                    "mul",
                    subresult=_product_detail(_num(factor), _num(value), product_value),
                )
            )
            current = nxt
        result.add_group("multiply", *product_stages)

    total = Fraction(matrix.det())
    if top and size == 3:
        detail = SolveResult()
        positives = [
            (node, value)
            for node, value in zip(current_nodes, current_values, strict=True)
            if value > 0
        ]
        negatives = [
            (node, value)
            for node, value in zip(current_nodes, current_values, strict=True)
            if value < 0
        ]
        prefix = sum(value for _, value in positives)
        if negatives:
            drained = _sub(
                _render_chain(positives) if positives else num0,
                _strip_sign(negatives[0][0]),
            )
            detail.add_group("calc_sum", Step(current, drained, "sum_real_positive"))
            rest = prefix - abs(negatives[0][1])
            detail.add_group(
                "calculate_short",
                Step(drained, _num(total), "calc_diff" if rest < 0 else "sub"),
            )
        else:
            detail.add_group("calc_sum", Step(current, _num(total), "sum_real_positive"))
        detail.set_solution(_num(total))
        result.add_group("calculate_short", Step(current, _num(total), "sum", subresult=detail))
        return _num(total)

    zeros = [position for position, value in enumerate(current_values) if value == 0]
    first_is_nonzero = bool(current_values) and current_values[0] != 0
    if first_is_nonzero:
        detail = SolveResult()
        if top:
            detail.add_group(
                CoreRichText(type="remove_zero", args=[num0]),
                Step(current, _num(total), "add_with_zero", [num0]),
            )
        detail.set_solution(_num(total))
        result.add_group(
            "calc_sum",
            Step(
                current,
                _num(total),
                "sum_real_positive",
                subresult=detail if top else None,
            ),
        )
        return _num(total)
    final_stages: list[Step] = []
    for position in zeros:
        current_values[position] = Fraction(0)
        current_nodes[position] = num0
        nxt = _render_chain(list(zip(current_nodes, current_values, strict=True)))
        final_stages.append(Step(current, nxt, "add_with_zero", [num0]))
        current = nxt
    if len(products) == 1:
        position = products[0]
        factor, minor = terms[position]
        value = Fraction(minor.det())
        current_nodes[position] = _num(factor * value)
        current_values[position] = factor * value
        nxt = _render_chain(list(zip(current_nodes, current_values, strict=True)))
        final_stages.append(Step(current, nxt, "mul"))
        current = nxt
    result.add_group(["remove_zero_plural", "multiply"], *final_stages)
    return _num(total)


def _laplace_nested(matrix: sympy.Matrix) -> SolveResult:
    """One page of a larger determinant: its 3×3 minor expanded, without a third level."""
    several = SolveResult()
    values = [Fraction(cell) for cell in matrix]
    _laplace_rows(
        several,
        _det_node(matrix),
        values,
        top=False,
        solve_nested=False,
    )
    several.set_solution(_num(Fraction(matrix.det())))
    return several


def _sum_node(nodes: list[CoreNode]) -> CoreNode:
    if len(nodes) == 1:
        return nodes[0]
    return CoreNode.node(T.ADD, *nodes)


def _sarrus_card(node: CoreNode, cells: list[CoreNode], values: list[Fraction]) -> SolveResult:
    """The rule-of-Sarrus card for a numeric 3×3 determinant (the second method)."""
    eq, num = CoreNode.node, _num
    positive = ((0, 4, 8), (1, 5, 6), (2, 3, 7))
    negative = ((2, 4, 6), (0, 5, 7), (1, 3, 8))

    def product(indices: tuple[int, ...]) -> CoreNode:
        return CoreNode.node(T.MULTIPLY, *[cells[index] for index in indices])

    def term_value(indices: tuple[int, ...]) -> Fraction:
        result = Fraction(1)
        for index in indices:
            result *= values[index]
        return result

    p_nodes = [product(indices) for indices in positive]
    n_nodes = [product(indices) for indices in negative]
    p_values: list[Fraction] = [term_value(indices) for indices in positive]
    n_values: list[Fraction] = [term_value(indices) for indices in negative]

    def render(ps: list[CoreNode], ns: list[CoreNode]) -> CoreNode:
        return eq(T.SUBTRACT, _sum_node(ps), _sum_node(ns))

    extended = eq(T.DETERMINANT3_SARRUS, *cells)
    rule = render(p_nodes, n_nodes)
    card = SolveResult()
    card.add_group("extend_grid", Step(node, extended, "det3_sarrus_extend"))
    card.add_group("det3_sarrus_rule_short", Step(extended, rule, "det3_sarrus_rule"))

    current = rule
    steps: list[Step] = []
    reduced: list[tuple[str, int]] = []
    for kind, nodes, _term_values in (
        ("p", p_nodes, p_values),
        ("n", n_nodes, n_values),
    ):
        for position, indices in enumerate(positive if kind == "p" else negative):
            if 1 not in [values[index] for index in indices]:
                continue
            remaining = [cells[index] for index in indices if values[index] != 1]
            nodes[position] = CoreNode.node(T.MULTIPLY, *remaining)
            current = render(p_nodes, n_nodes)
            steps.append(Step(current, current, "mul_with_one", [num(Fraction(1))]))
            reduced.append((kind, position))
    # The step's own left/right are fixed below; rebuild from the original rule.
    current = rule
    stages: list[Step] = []
    for kind, position in reduced:
        nodes = p_nodes if kind == "p" else n_nodes
        term_values = p_values if kind == "p" else n_values
        indices = (positive if kind == "p" else negative)[position]
        remaining = [cells[index] for index in indices if values[index] != 1]
        nodes[position] = CoreNode.node(T.MULTIPLY, *remaining)
        following = render(p_nodes, n_nodes)
        stages.append(Step(current, following, "mul_with_one", [num(Fraction(1))]))
        current = following
        _ = term_values
    for kind, position in reduced:
        nodes = p_nodes if kind == "p" else n_nodes
        term_values = p_values if kind == "p" else n_values
        nodes[position] = num(term_values[position])
        following = render(p_nodes, n_nodes)
        stages.append(Step(current, following, "mul"))
        current = following
    for kind, nodes, term_values, indices_list in (
        ("p", p_nodes, p_values, positive),
        ("n", n_nodes, n_values, negative),
    ):
        for position, indices in enumerate(indices_list):
            if (kind, position) in reduced:
                continue
            detail = SolveResult()
            x, y, z = (cells[index] for index in indices)
            first = CoreNode.node(T.MULTIPLY, x, y)
            third = CoreNode.node(T.MULTIPLY, first, z)
            detail.add_group("multiply", Step(CoreNode.node(T.MULTIPLY, x, y, z), first, "mul"))
            detail.add_group("multiply", Step(first, num(term_values[position]), "mul"))
            nodes[position] = num(term_values[position])
            following = render(p_nodes, n_nodes)
            stages.append(Step(current, following, "product", subresult=detail))
            current = following
            _ = third
    card.add_group(["multiply", "calculate_short"], *stages)

    positive_total = sum(p_values, Fraction(0))
    negative_total = sum(n_values, Fraction(0))
    total = positive_total - negative_total
    negative_steps: list[Step] = []
    running: Fraction = n_values[0]
    for item_value in n_values[1:]:
        next_total = running + item_value
        negative_steps.append(
            Step(
                _sum_node([num(item) for item in [running, item_value]]),
                num(next_total),
                "add",
            )
        )
        running = next_total
    negative_detail = SolveResult()
    if negative_steps:
        negative_detail.add_group("calculate_short", *negative_steps)
    negative_detail.set_solution(num(negative_total))
    summed = eq(
        T.SUBTRACT, _sum_node([num(item_value) for item_value in p_values]), num(negative_total)
    )
    card.add_group(
        "calc_sum",
        Step(current, summed, "sum_real_positive", subresult=negative_detail),
    )
    final_detail = SolveResult()
    final_detail.add_group(
        "calc_sum",
        Step(summed, eq(T.SUBTRACT, num(positive_total), num(negative_total)), "sum_real_positive"),
    )
    final_detail.add_group(
        "calculate_short",
        Step(
            eq(T.SUBTRACT, num(positive_total), num(negative_total)),
            num(total),
            "calc_diff" if total < 0 else "sub",
        ),
    )
    final_detail.set_solution(num(total))
    card.add_group("calculate_short", Step(summed, num(total), "sum", subresult=final_detail))
    card.set_solution(num(total))
    return card


@method_provider(T.DETERMINANT3)
def determinant3_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """Numeric 3×3: the Laplace card and the rule-of-Sarrus card (the two methods)."""
    _ = variables
    elements = _elements(node)
    if len(elements) != 9:
        return []
    try:
        values = [number_of(element) for element in elements]
    except SolveError:
        return []
    matrix = sympy.Matrix(3, 3, values)
    if _has_zero_line(matrix):
        return []
    laplace = SolveResult()
    _laplace_rows(laplace, node, values, top=True)
    laplace.set_solution(_num(Fraction(matrix.det())))
    return [laplace, _sarrus_card(node, elements, values)]


@solver_for(*_DETERMINANTS)
def solve_determinant(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить определитель квадратной матрицы (числовой или буквенной)."""
    elements = _elements(node)
    size = isqrt(len(elements))
    ctx.require(
        size > 0 and size * size == len(elements),
        "определитель определён только для квадратной матрицы",
    )
    ctx.require(size <= _MAX_SIZE, "матрица слишком большая")

    values = _numeric_values(elements, ctx)
    if values is not None:
        if size == 2:
            expanded = _sub(_mul(elements[0], elements[3]), _mul(elements[1], elements[2]))
            ctx.result.add_group(
                "det_evaluate",
                Step(node, expanded, "det2_determinant_rule", [_rule_node()]),
            )
            return _det2_arithmetic(ctx, values, elements, expanded)
        if _has_zero_line(sympy.Matrix(size, size, values)):
            zero = CoreNode.constant("0")
            ctx.result.add_group("det_zero", Step(node, zero, "det_zero", [zero]))
            return zero
        return _laplace_rows(ctx.result, node, values, top=True)

    matrix = sympy.Matrix(size, size, [to_sympy(element) for element in elements])
    which, index, _ = _line_for(size, matrix)
    expanded = _expanded_expression(matrix)
    if size <= 2:
        key, args = "det2_determinant_rule", [_rule_node()]
    elif size == 3:
        key, args = "det3_cofactor_eval", []
    else:
        key = "det_laplace_rule_row" if which == "row" else "det_laplace_rule_col"
        args = [CoreNode.constant(str(index + 1))]
    ctx.result.add(Step(left=node, right=expanded, key=key, args=args))
    answer = from_sympy(sympy.simplify(matrix.det()))
    if not expanded.structural_eq(answer):
        ctx.result.add(Step(left=expanded, right=answer, key="simplify"))
    return answer


def lone_matrix_rows(node: CoreNode, ctx: SolveContext) -> CoreNode | None:
    """A bare square matrix (n ≥ 2) is solved as its determinant.

    The 2x2 rows are the ones the card shows: determinant
    notation, the ``ad - bc`` formula, the products (``x 1`` is dropped on its own
    page), then the difference. A larger square uses the determinant steps.
    """
    rows = node.children
    if node.type is not T.MATRIX or len(rows) < 2:
        return None
    size = len(rows)
    if any(len(r.children) != size for r in rows):
        return None  # non-square: the bare matrix stays a matrix
    cells = [cell for row in rows for cell in row.children]
    eq = CoreNode.node
    bar = eq(_DET_TYPES.get(size, T.DETERMINANT), *cells)
    ctx.result.add_group("use_appropriate_notation", Step(node, bar, "matrix_det_rewrite"))
    if size != 2:
        return route(bar, ctx)

    values = [number_of(cell) for cell in cells]
    expanded = _sub(_mul(cells[0], cells[3]), _mul(cells[1], cells[2]))
    ctx.result.add_group(
        "det_evaluate", Step(bar, expanded, "det2_determinant_rule", [_rule_node()])
    )
    return _det2_arithmetic(ctx, values, cells, expanded)


def _gauss_swap_inverse(node: CoreNode, matrix: sympy.Matrix, result: SolveResult) -> CoreNode:
    """Gauss–Jordan inverse with row reordering (the ``matrix_inv_reorder`` card)."""
    size = matrix.rows
    work = sympy.Matrix(matrix)
    swaps: list[tuple[int, int]] = []
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(work[row, column]))
        if pivot != column and work[pivot, column] != 0:
            work.row_swap(column, pivot)
            swaps.append((column, pivot))
    result.add(Step(left=node, right=None, key="matrix_inv_use_notation"))
    for first, second in swaps:
        inner = SolveResult()
        inner.add_group(
            "matrix_inv_swap",
            Step(
                from_sympy(matrix),
                from_sympy(work),
                "matrix_inv_swap_row",
                [CoreNode.constant(str(first + 1)), CoreNode.constant(str(second + 1))],
            ),
        )
        result.add_group(
            "matrix_inv_reorder",
            Step(
                node,
                from_sympy(work),
                "matrix_inv_reorder_rows",
                subresult=inner,
            ),
        )
    result.add(Step(left=node, right=None, key="matrix_inv_write_right"))
    result.add(Step(left=node, right=None, key="matrix_inv_find_identity"))
    answer = from_sympy(matrix.inv())
    result.add(Step(left=node, right=answer, key="matrix_inv_right_is_inv"))
    return answer


def _inverse_verdict_card(node: CoreNode) -> SolveResult:
    """A singular bare matrix: the inverse card is a verdict, not a matrix."""
    inner = SolveResult()
    inner.add_group("matrix_inv_doesnt_exist", Step(node, None, "matrix_inv_no_inv"))
    inner.set_solution(CoreNode.empty())
    card = SolveResult()
    card.add_group("use_appropriate_notation", Step(node, None, "matrix_inv_use_notation"))
    card.add_group(
        "matrix_inv_doesnt_exist",
        Step(node, None, "matrix_inv_doesnt_exist", subresult=inner),
    )
    card.set_solution(CoreNode.empty())
    return card


@method_provider(T.MATRIX)
def matrix_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """A bare square matrix: the determinant and the inverse cards (both are shown)."""
    rows = node.children
    if len(rows) < 2 or any(len(row.children) != len(rows) for row in rows):
        return []
    cells = [cell for row in rows for cell in row.children]
    try:
        values = [number_of(cell) for cell in cells]
    except SolveError:
        return []
    size = len(rows)
    matrix = sympy.Matrix(size, size, values)
    determinant = SolveResult()
    answer = lone_matrix_rows(node, SolveContext(result=determinant, variables=list(variables)))
    if answer is None:
        return []
    determinant.set_solution(answer)
    if matrix.det() == 0:
        return [determinant, _inverse_verdict_card(node)]
    inverse = SolveResult()
    if any(value == 0 for value in values):
        inverse_answer = _gauss_swap_inverse(node, matrix, inverse)
    else:
        inverse_answer = matrix_inverse(
            node, SolveContext(result=inverse, variables=list(variables)), []
        )
    inverse.set_solution(inverse_answer)
    # Verification card: A·A⁻¹ = I (the «solve the matrix equation» identity).
    identity = from_sympy(sympy.eye(size))
    product_matrix = from_sympy(matrix * to_sympy(inverse_answer))
    equation = CoreNode.node(T.EQUALS, product_matrix, identity)
    rowcol = SolveResult()
    rowcol.add_group(
        "matrix_mul_row_col_simple",
        *[
            Step(
                product_matrix,
                identity,
                "matrix_mul_row_col",
                [CoreNode.constant(str(row + 1)), CoreNode.constant(str(column + 1))],
            )
            for row in range(size)
            for column in range(size)
        ],
    )
    rowcol.set_solution(identity)
    inverse.add_group(
        ["matrix_inv_eq", "matrix_inv_eq_mul_by_inv_smpl"],
        Step(
            node,
            equation,
            "matrix_inv_eq_mul_by_inv",
            [inverse_answer],
            subresult=rowcol,
        ),
    )
    inverse.add_group(
        "matrix_inv_eq_set_identity_smpl",
        Step(equation, identity, "matrix_inv_eq_set_identity"),
    )
    return [determinant, inverse]


@solver_for(T.MATRIX, T.MATRIX_ROW)
def solve_matrix(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Матрица как значение не сворачивается: строки и ячейки остаются."""
    _ = ctx
    return node


# ── операции над матрицами (команды) ───────────────────────────────────
# Представление: ``MATRIX``, дети -- строки ``MATRIX_ROW``. Операции --
# команды, как у векторов: второй операнд приходит в ``action.args``.


def _to_matrix(node: CoreNode) -> sympy.Matrix:
    """Узел ``MATRIX`` в символьную матрицу sympy."""
    if node.type is not T.MATRIX or not node.children:
        raise SolveError("ожидалась матрица: узел MATRIX со строками")
    return to_sympy(node)


def _record(node: CoreNode, result: CoreNode, ctx: SolveContext, key: str) -> CoreNode:
    """Добавить шаг и вернуть результат."""
    ctx.result.add(Step(left=node, right=result, key=key))
    return result


def _second_matrix(args: list[CoreNode]) -> sympy.Matrix:
    """Второй операнд команды как матрица."""
    if not args:
        raise SolveError("для операции нужен второй операнд -- матрица")
    return _to_matrix(args[0])


def _cells(node: CoreNode) -> list[list[CoreNode]] | None:
    """Rows of a matrix whose cells are non-negative integers, else ``None``."""
    rows = [row.children if row.type is T.MATRIX_ROW else [row] for row in node.children]
    flat = [cell for row in rows for cell in row]
    if node.type is T.MATRIX and all(
        cell.type is T.CONSTANT and (cell.value or "").isdigit() for cell in flat
    ):
        return rows
    return None


def _matrix_of(rows: list[list[CoreNode]]) -> CoreNode:
    return CoreNode.node(T.MATRIX, *[CoreNode.node(T.MATRIX_ROW, *row) for row in rows])


def _sum_of_products(products: list[CoreNode]) -> CoreNode:
    """``1·5 + 2·7``: one cell of a matrix product as row·column."""
    if len(products) == 1:
        return products[0]
    return CoreNode.node(T.ADD, *products)


def _multiply_rows(
    node: CoreNode,
    left: sympy.Matrix,
    right: sympy.Matrix,
    answer: sympy.Matrix,
    ctx: SolveContext,
) -> CoreNode:
    """``A·B``: the product matrix with the row·column sums, then one stage per row."""
    expressions = [
        [
            _sum_of_products(
                [
                    CoreNode.node(T.MULTIPLY, from_sympy(left[i, k]), from_sympy(right[k, j]))
                    for k in range(left.cols)
                ]
            )
            for j in range(answer.cols)
        ]
        for i in range(answer.rows)
    ]
    rowcol = SolveResult()
    rowcol.add_group(
        "matrix_mul_row_col_simple",
        *[
            Step(
                node,
                _matrix_of(expressions),
                "matrix_mul_row_col",
                [CoreNode.constant(str(i + 1)), CoreNode.constant(str(j + 1))],
            )
            for i in range(answer.rows)
            for j in range(answer.cols)
        ],
    )
    rowcol.set_solution(_matrix_of(expressions))
    ctx.result.add_group(
        "matrix_mul",
        Step(node, _matrix_of(expressions), "matrix_mul", subresult=rowcol),
    )
    state = [row[:] for row in expressions]
    stages: list[Step] = []
    for i in range(answer.rows):
        before = _matrix_of(state)
        state[i] = [from_sympy(answer[i, j]) for j in range(answer.cols)]
        stages.append(Step(before, _matrix_of(state), "matrix_mul_row_col_simple"))
    ctx.result.add_group("calculate_short", *stages)
    return _matrix_of(state)


def _subtract_rows(
    node: CoreNode, left: list[list[CoreNode]], right: list[list[CoreNode]], ctx: SolveContext
) -> CoreNode:
    """``A − B``: every cell as a difference, then the cells evaluated in turn."""
    differences = [
        [CoreNode.node(T.SUBTRACT, a, b) for a, b in zip(r1, r2, strict=True)]
        for r1, r2 in zip(left, right, strict=True)
    ]
    state = [row[:] for row in differences]
    ctx.result.add_group("matrix_sub", Step(node, _matrix_of(differences), "matrix_sub"))
    zero = CoreNode.constant("0")
    stages = []
    for i, (r1, r2) in enumerate(zip(left, right, strict=True)):
        for j, (a, b) in enumerate(zip(r1, r2, strict=True)):
            before = _matrix_of(state)
            total = CoreNode.constant(str(int(a.value or 0) - int(b.value or 0)))
            state[i][j] = total
            plain = a.value != "0" and b.value != "0"
            stages.append(
                Step(
                    before,
                    _matrix_of(state),
                    "sub" if plain else "add_with_zero",
                    [] if plain else [zero],
                )
            )
    zeros = any(stage.key == "add_with_zero" for stage in stages)
    header: list[str | CoreRichText] | str = (
        ["calculate_short", CoreRichText(type="remove_zero", args=[zero])]
        if zeros
        else "calculate_short"
    )
    ctx.result.add_group(header, *stages)
    return _matrix_of(state)


def _scale_factor(node: CoreNode) -> CoreNode:
    """A factor of a scalar product: negatives are bracketed (``3·(−2)``)."""
    if node.type in (T.ADD, T.SUBTRACT, T.NEGATIVE) or (
        node.type is T.CONSTANT and (node.value or "").startswith("-")
    ):
        return CoreNode.node(T.BRACKET, node)
    return node


def _scale_cells(
    node: CoreNode, rows: list[list[CoreNode]], scalar: CoreNode, ctx: SolveContext
) -> CoreNode:
    """``k·A``: the scalar multiplied into every cell, then the cells evaluated.

    The cells and the scalar stay exact: an inverse's ``1/det A`` is a fraction
    and the cofactors may be negative, so the arithmetic goes through sympy.
    """
    products = [
        [CoreNode.node(T.MULTIPLY, _scale_factor(scalar), _scale_factor(cell)) for cell in row]
        for row in rows
    ]
    state = [row[:] for row in products]
    factor = to_sympy(scalar)
    try:
        scalar_value = as_fraction(scalar)
    except SolveError:
        scalar_value = None
    if scalar_value is not None and scalar_value < 0 and scalar_value.denominator != 1:
        ctx.result.add_group(
            CoreRichText(type="frac_div_rec_neg_one", args=[scalar]),
            Step(node, scalar, "frac_div_rec_neg_one", args=[scalar]),
        )
    ctx.result.add_group(
        CoreRichText(type="matrix_mul_each_elem", args=[scalar]),
        Step(node, _matrix_of(products), "matrix_mul_scalar", [scalar]),
    )
    stages = []
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            before = _matrix_of(state)
            state[i][j] = from_sympy(sympy.simplify(factor * to_sympy(cell)))
            stages.append(Step(before, _matrix_of(state), "mul"))
    ctx.result.add_group("calculate_short", *stages)
    return _matrix_of(state)


def _scalar_cell(args: list[CoreNode]) -> CoreNode | None:
    """A non-negative integer scalar argument, else ``None`` (cells stay literal)."""
    if not args:
        return None
    argument = args[0]
    if argument.type is T.CONSTANT and (argument.value or "").isdigit():
        return argument
    return None


def _add_rows(
    node: CoreNode, left: list[list[CoreNode]], right: list[list[CoreNode]], ctx: SolveContext
) -> CoreNode:
    """Write every cell as a sum, then evaluate the cells in turn."""
    sums = [
        [CoreNode.node(T.ADD, a, b) for a, b in zip(r1, r2, strict=True)]
        for r1, r2 in zip(left, right, strict=True)
    ]
    state = [row[:] for row in sums]
    ctx.result.add_group(
        "matrix_add_elements_smpl",
        Step(node, _matrix_of(sums), "matrix_add_elements"),
    )
    stages = []
    zero = CoreNode.constant("0")
    for i, (r1, r2) in enumerate(zip(left, right, strict=True)):
        for j, (a, b) in enumerate(zip(r1, r2, strict=True)):
            before = _matrix_of(state)
            total = CoreNode.constant(str(int(a.value or 0) + int(b.value or 0)))
            state[i][j] = total
            plain = a.value != "0" and b.value != "0"
            stages.append(
                Step(
                    before,
                    _matrix_of(state),
                    "add" if plain else "add_with_zero",
                    [] if plain else [zero],
                )
            )
    zeros = any(stage.key == "add_with_zero" for stage in stages)
    header: list[str | CoreRichText] | str = (
        ["calculate_short", CoreRichText(type="remove_zero", args=[zero])]
        if zeros
        else "calculate_short"
    )
    ctx.result.add_group(header, *stages)
    return _matrix_of(state)


def matrix_add(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Сложение матриц одного размера."""
    left, right = _to_matrix(node), _second_matrix(args)
    ctx.require(left.shape == right.shape, "матрицы разного размера", "matrix_diff_size_error")
    rows_left, rows_right = _cells(node), _cells(args[0])
    if rows_left is not None and rows_right is not None:
        return _add_rows(CoreNode.node(T.ADD, node, args[0]), rows_left, rows_right, ctx)
    return _record(node, from_sympy(left + right), ctx, "matrix_add_elements")


def matrix_subtract(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Вычитание матриц одного размера."""
    left, right = _to_matrix(node), _second_matrix(args)
    ctx.require(left.shape == right.shape, "матрицы разного размера", "matrix_diff_size_error")
    rows_left, rows_right = _cells(node), _cells(args[0])
    if rows_left is not None and rows_right is not None:
        return _subtract_rows(CoreNode.node(T.SUBTRACT, node, args[0]), rows_left, rows_right, ctx)
    return _record(node, from_sympy(left - right), ctx, "matrix_sub")


def matrix_multiply(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Умножение матриц: столбцы первой равны строкам второй."""
    left, right = _to_matrix(node), _second_matrix(args)
    ctx.require(
        left.shape[1] == right.shape[0],
        "число столбцов первой матрицы не равно числу строк второй",
        "matrix_mul_diff_size_error",
    )
    rows_left, rows_right = _cells(node), _cells(args[0])
    if rows_left is not None and rows_right is not None:
        return _multiply_rows(
            CoreNode.node(T.MULTIPLY, node, args[0]), left, right, left * right, ctx
        )
    return _record(node, from_sympy(left * right), ctx, "matrix_mul")


def matrix_scale(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Умножение матрицы на скаляр."""
    if not args:
        raise SolveError("для умножения на скаляр нужен скаляр")
    rows = _cells(node)
    scalar = _scalar_cell(args)
    if rows is not None and scalar is not None:
        return _scale_cells(CoreNode.node(T.MULTIPLY, scalar, node), rows, scalar, ctx)
    scalar_value = to_sympy(args[0])
    multiplier = _to_matrix(node) * scalar_value
    result = from_sympy(multiplier)
    ctx.result.add(Step(left=node, right=result, key="matrix_mul_scalar", args=[args[0]]))
    return result


def matrix_transpose(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Транспонирование матрицы: строки становятся столбцами."""
    _ = args
    return _record(node, from_sympy(_to_matrix(node).T), ctx, "matrix_transpose")


def matrix_inverse(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Обратная матрица по формуле через союзную (присоединённую) матрицу.

    Шаги Проскурякова: определитель, алгебраические дополнения (по строке
    матрицы), ``adj A = Cᵀ``, затем ``A⁻¹ = (1/det A)·adj A`` поэлементно.
    Вырожденная матрица — вердикт ``matrix_inv_det_zero``; метод Гаусса
    остаётся за командой ``matrix_inverse_gauss``.
    """
    _ = args
    matrix = _to_matrix(node)
    ctx.require(
        matrix.rows == matrix.cols,
        "обратная матрица определена только для квадратной",
        "matrix_inv_undef",
    )
    if matrix.det() == 0:
        # A singular matrix is a verdict, not an error: show the determinant and say
        # why the inverse does not exist.
        determinant = route(_det_node(matrix), ctx)
        verdict = SolveResult()
        verdict.add_group("matrix_inv_doesnt_exist", Step(node, None, "matrix_inv_no_inv"))
        verdict.set_solution(CoreNode.empty())
        ctx.result.add(
            Step(
                left=node,
                right=None,
                key="matrix_inv_det_zero",
                args=[determinant],
                subresult=verdict,
            )
        )
        return CoreNode.empty()
    if matrix.rows >= 4 and all(cell.is_number for cell in matrix):
        # the app: a 4x4 inverse is found by Gauss–Jordan row reduction.
        return matrix_inverse_gauss(node, ctx, [])
    ctx.result.add(Step(left=node, right=None, key="matrix_inv_find_formula"))
    if matrix.rows < 2 or not all(cell.is_number for cell in matrix):
        # A 1×1 or a symbolic matrix: the cofactor picture has no textbook shape here.
        return _record(node, from_sympy(matrix.inv()), ctx, "matrix_inv_find_smpl")
    return _adjugate_inverse(node, matrix, ctx)


def _determinant_stage(matrix: sympy.Matrix, ctx: SolveContext) -> tuple[CoreNode, SolveResult]:
    """``|A|`` with the determinant solver's own stages as the nested detail."""
    detail = SolveResult()
    detail.header = "lesson_disc_matrix"
    detail_ctx = SolveContext(result=detail, variables=list(ctx.variables))
    return route(_det_node(matrix), detail_ctx), detail


def _minor_node(matrix: sympy.Matrix, row: int, column: int) -> CoreNode:
    """The unsigned minor: a single entry for a 2×2, a smaller determinant above."""
    minor = matrix.minor_submatrix(row, column)
    if matrix.rows == 2:
        return from_sympy(minor[0, 0])
    return _det_node(minor)


def _adjugate_inverse(node: CoreNode, matrix: sympy.Matrix, ctx: SolveContext) -> CoreNode:
    """Textbook adjugate method: det A, cofactors by row, transpose, ``1/det A``."""
    size = matrix.rows
    determinant_node, determinant_detail = _determinant_stage(matrix, ctx)
    ctx.result.add(
        Step(
            left=_det_node(matrix),
            right=determinant_node,
            key="lesson_disc_adj_det",
            subresult=determinant_detail,
        )
    )

    def sign(row: int, column: int) -> int:
        return 1 if (row + column) % 2 == 0 else -1

    cofactors = sympy.Matrix(
        size,
        size,
        [
            sign(row, column) * matrix.minor_submatrix(row, column).det()
            for row in range(size)
            for column in range(size)
        ],
    )
    if size == 2:
        # A 2×2 minor is one entry, so the only work is the sign of (−1)^(i+j).
        ctx.result.add(
            Step(
                left=_matrix_of(
                    [
                        [from_sympy(matrix.minor_submatrix(i, j)[0, 0]) for j in range(size)]
                        for i in range(size)
                    ]
                ),
                right=from_sympy(cofactors),
                key="lesson_disc_adj_cofactors",
            )
        )
    else:
        for row in range(size):
            terms: list[CoreNode] = []
            row_detail = SolveResult()
            row_detail.header = "lesson_disc_matrix"
            for column in range(size):
                minor_node = _minor_node(matrix, row, column)
                terms.append(
                    minor_node if sign(row, column) > 0 else CoreNode.node(T.NEGATIVE, minor_node)
                )
                minor_detail = SolveResult()
                minor_detail.header = "lesson_disc_matrix"
                minor_value = route(
                    minor_node,
                    SolveContext(result=minor_detail, variables=list(ctx.variables)),
                )
                row_detail.add(
                    Step(
                        left=minor_node,
                        right=minor_value,
                        key="lesson_disc_minor",
                        args=[
                            CoreNode.constant(str(row + 1)),
                            CoreNode.constant(str(column + 1)),
                        ],
                        subresult=minor_detail,
                    )
                )
            ctx.result.add(
                Step(
                    left=_matrix_of([terms]),
                    right=_matrix_of([[from_sympy(cofactors[row, j]) for j in range(size)]]),
                    key="lesson_disc_adj_cofactors_row",
                    args=[CoreNode.constant(str(row + 1))],
                    subresult=row_detail,
                )
            )

    adjugate = cofactors.T
    ctx.result.add(
        Step(
            left=from_sympy(cofactors),
            right=from_sympy(adjugate),
            key="lesson_disc_adj_transpose",
        )
    )
    inverse = CoreNode.node(T.POWER, node, CoreNode.node(T.NEGATIVE, CoreNode.constant("1")))
    if matrix.det() == 1:
        # 1·adj A поклеточно — n² пустых этапов «1·x = x»: A⁻¹ = adj A сразу.
        ctx.result.add(
            Step(left=inverse, right=from_sympy(adjugate), key="lesson_disc_adj_formula")
        )
        return from_sympy(adjugate)
    scalar = from_sympy(sympy.simplify(sympy.Integer(1) / matrix.det()))
    formula = CoreNode.node(T.MULTIPLY, scalar, from_sympy(adjugate))
    ctx.result.add(Step(left=inverse, right=formula, key="lesson_disc_adj_formula"))
    rows = [[from_sympy(adjugate[i, j]) for j in range(size)] for i in range(size)]
    return _scale_cells(formula, rows, scalar, ctx)


def matrix_determinant(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Определитель матрицы."""
    _ = args
    matrix = _to_matrix(node)
    ctx.require(
        matrix.rows == matrix.cols,
        "определитель определён только для квадратной",
        "matrix_det_undef",
    )
    return _record(node, from_sympy(matrix.det()), ctx, "matrix_det_rewrite")


def _contains_variable(node: CoreNode) -> bool:
    """Есть ли в узле переменная (неизвестная матрица)."""
    return any(child.type is T.VARIABLE for child in node.walk())


def _matrix_product(lhs: CoreNode) -> tuple[sympy.Matrix, sympy.Matrix, bool] | None:
    """Разобрать ``A·X`` или ``X·A`` в ``(A, X, X-слева)`` или ``None``."""
    if lhs.type not in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) or len(lhs.children) != 2:
        return None
    first, second = lhs.children
    if _contains_variable(first) and not _contains_variable(second):
        return _to_matrix(second), _to_matrix(first), True
    if _contains_variable(second) and not _contains_variable(first):
        return _to_matrix(first), _to_matrix(second), False
    return None


def matrix_equation(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Решить матричное уравнение ``A·X = B`` (или ``X·A = B``).

    Неизвестная матрица ``X`` — та, что содержит переменные; коэффициентом
    ``A`` служит числовая матрица. Решение — ``X = A⁻¹B`` (или ``B·A⁻¹``);
    если ``A`` вырождена, решения нет.
    """
    del args
    if node.type is not T.EQUALS or len(node.children) != 2:
        raise SolveError("матричное уравнение — это равенство")
    left, right = node.children
    parsed = _matrix_product(left)
    if parsed is None:
        raise SolveError("нужно произведение числовой и неизвестной матриц")
    coefficient, unknown, unknown_on_left = parsed
    target = _to_matrix(right)
    ctx.require(
        coefficient.rows == coefficient.cols,
        "неизвестная матрица должна умножаться на квадратную",
        "matrix_inv_undef",
    )
    ctx.require(
        coefficient.shape[1] == unknown.rows and unknown.cols == target.cols,
        "несовместимые размеры матричного уравнения",
        "matrix_mul_diff_size_error",
    )

    determinant = coefficient.det()
    if determinant == 0:
        ctx.result.add(Step(left=node, right=None, key="matrix_eq_system_no_sol"))
        return CoreNode.empty()
    coefficient_inverse = coefficient.inv()
    solved = target * coefficient_inverse if unknown_on_left else coefficient_inverse * target
    answer = from_sympy(solved)
    if not unknown_on_left:
        # the app: write A·X, equate the elements, then solve the columns as systems.
        unknown_sympy = unknown
        unknown_node = left.children[0] if unknown_on_left else left.children[1]
        product_node = CoreNode.node(T.MULTIPLY, from_sympy(coefficient), unknown_node)
        product = coefficient * unknown_sympy
        product_matrix = _multiply_rows(product_node, coefficient, unknown_sympy, product, ctx)
        ctx.result.retitle("matrix_find_unknown")
        equations = [
            [
                CoreNode.node(
                    T.EQUALS,
                    from_sympy(product[row, column]),
                    from_sympy(target[row, column]),
                )
                for column in range(target.cols)
            ]
            for row in range(target.rows)
        ]
        equation_matrix = _matrix_of(equations)
        ctx.result.add(Step(product_matrix, equation_matrix, "matrix_eq_set_elements_equal"))
        system = CoreNode.node(T.SYSTEM, *[equation for row in equations for equation in row])
        ctx.result.add(Step(equation_matrix, system, "matrix_eq_write_as_system"))
        for column in range(target.cols):
            column_system = CoreNode.node(T.SYSTEM, *[row[column] for row in equations])
            attempt = SolveResult()
            scratch: SolveResult | None = attempt
            try:
                route(
                    column_system,
                    SolveContext(result=attempt, variables=list(ctx.variables)),
                )
            except SolveError:
                scratch = None
            pair = CoreNode.node(
                T.LIST,
                *[
                    CoreNode.node(
                        T.EQUALS,
                        from_sympy(unknown_sympy[row, column]),
                        from_sympy(solved[row, column]),
                    )
                    for row in range(unknown.rows)
                ],
            )
            if scratch is not None:
                scratch.set_solution(pair)
                ctx.result.add(Step(system, column_system, "system_solve", subresult=scratch))
            ctx.result.add(Step(system, pair, "matrix_eq_ordered_pair_values"))
        return answer
    ctx.result.add(
        Step(left=node, right=None, key="matrix_eq_mul", args=[from_sympy(coefficient_inverse)])
    )
    ctx.result.add(Step(left=node, right=answer, key="matrix_eq_set_elements_equal"))
    return answer


def matrix_inverse_gauss(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Обратная матрица методом Гаусса (элементарных преобразований).

    Строится расширенная матрица ``[A | E]`` и приводится к ступенчатому виду;
    правая половина — обратная матрица. Вырожденная матрица даёт ответ
    ``EMPTY`` (обратной не существует).
    """
    del args
    matrix = _to_matrix(node)
    size = matrix.rows
    ctx.require(
        matrix.rows == matrix.cols,
        "обратная матрица определена только для квадратной",
        "matrix_inv_undef",
    )
    augmented = matrix.row_join(sympy.eye(size))
    ctx.result.add(Step(left=node, right=None, key="matrix_inv_use_notation"))
    ctx.result.add(Step(left=node, right=None, key="matrix_inv_write_right"))
    ctx.result.add(Step(left=node, right=None, key="matrix_inv_find_identity"))
    reduced, pivots = augmented.rref()
    if tuple(pivots) != tuple(range(size)):
        ctx.result.add(Step(left=node, right=None, key="matrix_inv_no_inv"))
        return CoreNode.empty()
    answer = from_sympy(reduced[:, size:])
    ctx.result.add(Step(left=node, right=answer, key="matrix_inv_right_is_inv"))
    return answer


def _echelon(matrix: sympy.Matrix, ctx: SolveContext) -> sympy.Matrix:
    """Ступенчатый вид: одно записанное элементарное преобразование строк на этап."""
    current = sympy.Matrix(matrix)
    pivot_row = 0
    for column in range(current.cols):
        pivot = next(
            (row for row in range(pivot_row, current.rows) if current[row, column] != 0), None
        )
        if pivot is None:
            continue
        if pivot != pivot_row:
            before = from_sympy(current)
            current.row_swap(pivot, pivot_row)
            ctx.result.add(
                Step(
                    left=before,
                    right=from_sympy(current),
                    key="matrix_inv_swap_row",
                    args=[
                        CoreNode.constant(str(pivot + 1)),
                        CoreNode.constant(str(pivot_row + 1)),
                    ],
                )
            )
        divisor = current[pivot_row, column]
        if divisor != 1:
            before = from_sympy(current)
            current[pivot_row, :] = current[pivot_row, :] / divisor
            ctx.result.add(
                Step(
                    left=before,
                    right=from_sympy(current),
                    key="mat_divide_row",
                    args=[from_sympy(divisor)],
                )
            )
        for row in range(pivot_row + 1, current.rows):
            factor = -current[row, column]
            if factor == 0:
                continue
            before = from_sympy(current)
            current[row, :] = current[row, :] + current[pivot_row, :] * factor
            ctx.result.add(
                Step(
                    left=before,
                    right=from_sympy(current),
                    key="mul_row_add",
                    args=[
                        CoreNode.constant(str(pivot_row + 1)),
                        from_sympy(factor),
                        CoreNode.constant(str(row + 1)),
                    ],
                )
            )
        pivot_row += 1
        if pivot_row == current.rows:
            break
    return current


def matrix_rank(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Ранг матрицы: ступенчатый вид, затем число ненулевых строк.

    Годится для любой формы (в том числе для нулевой матрицы: ранг 0).
    """
    del args
    matrix = _to_matrix(node)
    ctx.require(all(cell.is_number for cell in matrix), "ранг вычисляется у числовой матрицы")
    ctx.result.add(Step(left=node, right=None, key="lesson_disc_rank_echelon"))
    reduced = _echelon(matrix, ctx)
    rank = sum(1 for row in reduced.tolist() if any(cell != 0 for cell in row))
    answer = CoreNode.constant(str(rank))
    ctx.result.add(
        Step(left=from_sympy(reduced), right=answer, key="lesson_disc_rank_count", args=[answer])
    )
    return answer


def _solve_matrix_equation(
    node: CoreNode, ctx: SolveContext, args: list[CoreNode], *, unknown_on_left: bool
) -> CoreNode:
    """``A·X = B`` → ``X = A⁻¹B`` или ``X·A = B`` → ``X = BA⁻¹``."""
    matrix = _to_matrix(node)
    target = _second_matrix(args)
    ctx.require(
        matrix.rows == matrix.cols,
        "обратная матрица определена только для квадратной",
        "matrix_inv_undef",
    )
    compatible = matrix.rows == target.rows if unknown_on_left else matrix.cols == target.cols
    ctx.require(
        compatible, "несовместимые размеры матричного уравнения", "matrix_mul_diff_size_error"
    )
    if matrix.det() == 0:
        # Как у обратной матрицы: вырожденная A — вердикт, а не ошибка.
        determinant = route(_det_node(matrix), ctx)
        verdict = SolveResult()
        verdict.add_group("matrix_inv_doesnt_exist", Step(node, None, "matrix_inv_no_inv"))
        verdict.set_solution(CoreNode.empty())
        ctx.result.add(
            Step(
                left=node,
                right=None,
                key="matrix_inv_det_zero",
                args=[determinant],
                subresult=verdict,
            )
        )
        return CoreNode.empty()

    unknown = CoreNode.variable("X")
    inverse = CoreNode.node(T.POWER, node, CoreNode.node(T.NEGATIVE, CoreNode.constant("1")))
    matrix_side = CoreNode.node(T.MULTIPLY, node, unknown)
    formula_side = CoreNode.node(T.MULTIPLY, inverse, args[0])
    if not unknown_on_left:
        matrix_side = CoreNode.node(T.MULTIPLY, unknown, node)
        formula_side = CoreNode.node(T.MULTIPLY, args[0], inverse)
    key = "lesson_disc_solve_left" if unknown_on_left else "lesson_disc_solve_right"
    ctx.result.add(
        Step(
            left=CoreNode.node(T.EQUALS, matrix_side, args[0]),
            right=CoreNode.node(T.EQUALS, unknown, formula_side),
            key=key,
        )
    )
    inverse_matrix = matrix.inv()
    ctx.result.add(Step(left=node, right=from_sympy(inverse_matrix), key="matrix_inv_find_smpl"))
    if unknown_on_left:
        answer = inverse_matrix * target
        _multiply_rows(formula_side, inverse_matrix, target, answer, ctx)
    else:
        answer = target * inverse_matrix
        _multiply_rows(formula_side, target, inverse_matrix, answer, ctx)
    result = from_sympy(answer)
    ctx.result.add(Step(left=unknown, right=result, key="lesson_disc_solve_answer"))
    return result


def matrix_solve_left(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Решить ``A·X = B``: ``X = A⁻¹·B``."""
    return _solve_matrix_equation(node, ctx, args, unknown_on_left=True)


def matrix_solve_right(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Решить ``X·A = B``: ``X = B·A⁻¹``."""
    return _solve_matrix_equation(node, ctx, args, unknown_on_left=False)


def _row_index(args: list[CoreNode], position: int, rows: int) -> int:
    """Индекс строки (1-based, как на экране) из аргумента команды."""
    if position >= len(args):
        raise SolveError("не указан номер строки")
    argument = args[position]
    if argument.type is not T.CONSTANT or argument.value is None:
        raise SolveError("номер строки — целое число")
    text = argument.value.strip()
    if not text.isdigit():
        raise SolveError("номер строки — целое число")
    row = int(text) - 1
    if not 0 <= row < rows:
        raise SolveError("строка вне матрицы")
    return row


def matrix_mul_row(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Умножить строку матрицы на число (элементарное преобразование)."""
    matrix = _to_matrix(node)
    row = _row_index(args, 0, matrix.rows)
    factor = to_sympy(args[1]) if len(args) > 1 else sympy.Integer(1)
    changed = sympy.Matrix(matrix)
    changed[row, :] = changed[row, :] * factor
    result = from_sympy(changed)
    ctx.result.add(Step(left=node, right=result, key="mat_mul_row", args=[from_sympy(factor)]))
    return result


def matrix_divide_row(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Разделить строку матрицы на число (элементарное преобразование)."""
    matrix = _to_matrix(node)
    row = _row_index(args, 0, matrix.rows)
    divisor = to_sympy(args[1]) if len(args) > 1 else sympy.Integer(1)
    if divisor == 0:
        raise SolveError("деление строки на ноль")
    changed = sympy.Matrix(matrix)
    changed[row, :] = changed[row, :] / divisor
    result = from_sympy(changed)
    ctx.result.add(Step(left=node, right=result, key="mat_divide_row", args=[from_sympy(divisor)]))
    return result


def matrix_add_row(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Прибавить к строке другую строку, умноженную на число."""
    matrix = _to_matrix(node)
    source = _row_index(args, 0, matrix.rows)
    factor = to_sympy(args[1]) if len(args) > 1 else sympy.Integer(1)
    target = _row_index(args, 2, matrix.rows)
    changed = sympy.Matrix(matrix)
    changed[target, :] = changed[target, :] + changed[source, :] * factor
    result = from_sympy(changed)
    ctx.result.add(
        Step(
            left=node,
            right=result,
            key="mul_row_add",
            args=[args[0], from_sympy(factor), args[2]],
        )
    )
    return result


_MATRIX_OPERATORS = (T.ADD, T.SUBTRACT, T.MULTIPLY, T.MULTIPLY_IMPLICIT, T.POWER)


def is_matrix_expression(node: CoreNode) -> bool:
    """``A + B``, ``A * B``, ``2 A``, ``A^-1``: arithmetic whose operands include a matrix."""
    return node.type in _MATRIX_OPERATORS and any(n.type is T.MATRIX for n in node.walk())


def matrix_expression(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Evaluate matrix arithmetic operand by operand, one recorded step per operation."""
    if node.type is T.MATRIX:
        return node
    if node.type is T.BRACKET and len(node.children) == 1:
        return matrix_expression(node.children[0], ctx)
    if node.type not in _MATRIX_OPERATORS or len(node.children) != 2:
        return node
    left, right = (matrix_expression(child, ctx) for child in node.children)
    if node.type is T.POWER:
        ctx.require(left.type is T.MATRIX, "в степень возводится матрица")
        exponent = (
            -as_fraction(right.children[0]) if right.type is T.NEGATIVE else as_fraction(right)
        )
        ctx.require(exponent.denominator == 1, "показатель степени матрицы должен быть целым")
        if exponent == -1:
            return matrix_inverse(left, ctx, [])
        ctx.require(exponent >= 1, "поддерживаются показатели -1 и натуральные")
        result = left
        for _ in range(int(exponent) - 1):
            result = matrix_multiply(result, ctx, [left])
        return result
    if left.type is T.MATRIX and right.type is T.MATRIX:
        operation = {
            T.ADD: matrix_add,
            T.SUBTRACT: matrix_subtract,
            T.MULTIPLY: matrix_multiply,
            T.MULTIPLY_IMPLICIT: matrix_multiply,
        }[node.type]
        return operation(left, ctx, [right])
    if node.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT):
        matrix, scalar = (left, right) if left.type is T.MATRIX else (right, left)
        ctx.require(matrix.type is T.MATRIX, "ожидалась матрица")
        return matrix_scale(matrix, ctx, [scalar])
    raise SolveError("с матрицей складываются и вычитаются только матрицы")


def determinant_expansion(node: CoreNode) -> CoreNode | None:
    """Expand a determinant (or a square matrix) with unknowns to a scalar node.

    ``None`` when the node is not a square determinant/matrix or carries no
    unknowns: those cases keep their own solver.
    """
    if node.type not in (*_DETERMINANTS, T.MATRIX):
        return None
    elements = _elements(node)
    size = isqrt(len(elements))
    if size < 1 or size * size != len(elements):
        return None
    try:
        matrix = sympy.Matrix(size, size, [to_sympy(element) for element in elements])
    except SolveError:
        return None
    if not any(cell.free_symbols for cell in matrix):
        return None
    return from_sympy(sympy.expand(matrix.det()))


MATRIX_COMMANDS: dict[str, Command] = {
    "matrix_add": matrix_add,
    "matrix_add_row": matrix_add_row,
    "matrix_subtract": matrix_subtract,
    "matrix_mul_row": matrix_mul_row,
    "matrix_divide_row": matrix_divide_row,
    "matrix_multiply": matrix_multiply,
    "matrix_scale": matrix_scale,
    "matrix_transpose": matrix_transpose,
    "matrix_inverse": matrix_inverse,
    "matrix_inverse_gauss": matrix_inverse_gauss,
    "matrix_determinant": matrix_determinant,
    "matrix_rank": matrix_rank,
    "matrix_solve_left": matrix_solve_left,
    "matrix_solve_right": matrix_solve_right,
    "matrix_equation": matrix_equation,
}


__all__ = [
    "MATRIX_COMMANDS",
    "determinant_expansion",
    "is_matrix_expression",
    "matrix_expression",
    "solve_determinant",
    "solve_matrix",
]
