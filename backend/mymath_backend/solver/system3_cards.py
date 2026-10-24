"""the cards for a 3x3 linear system (worked out on x+y+z=6, x-y=-1, y+z=5).

Cramer's rule, Gauss-Jordan elimination and substitution, each ending with the ordered triple,
its check, the simplified check and the verdict. The inverse-matrix card X = A⁻¹B (FIX3) reuses
the verified 2x2 card's texts, ``solver/matrices.py``'s inverse and its cell-wise product.

shortcut: the pivot order of Gauss-Jordan and the choice of the isolated unknown in the
substitution card were decoded from that one system (unknowns are eliminated by how often they
occur, the sparsest row is the pivot, one equation holds the unknown to isolate); other systems are
explained by the same rules and every state is a valid step, but the app may order them
differently. The substitution card needs a unit coefficient and a two-unknown rest that cancels by
adding the equations or by adding them after multiplying one by -1.
"""

from __future__ import annotations

from fractions import Fraction

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, SolveResult, Step
from .quadratic_cards import _fraction_node, _num
from .sympy_bridge import from_sympy
from .system_cards import (
    _coefficients,
    _coefficients3,
    _empty_element,
    _equation,
    _node,
    _reduces,
    _replace,
    _system,
    _var,
    addition_detail,
    arithmetic_row_detail,
    check_detail,
    det3_detail,
    det3_sarrus_detail,
    isolation_detail,
)

_Row = list[Fraction]


def _determinant(rows: list[_Row]) -> CoreNode:
    return _node(T.DETERMINANT3, *[_num(v) for row in rows for v in row])


def _value(rows: list[_Row]) -> Fraction:
    (a, b, c), (d, e, f), (g, h, i) = rows
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def _cell(value: Fraction) -> CoreNode:
    return _num(value) if value.denominator == 1 else _fraction_node(value)


def _term(coefficient: Fraction, name: str) -> CoreNode:
    size = abs(coefficient)
    return _var(name) if size == 1 else _node(T.MULTIPLY_IMPLICIT, _cell(size), _var(name))


def _chain(items: list[tuple[int, CoreNode]]) -> CoreNode:
    sign, first = items[0]
    out = _node(T.NEGATIVE, first) if sign < 0 else first
    for sign, term in items[1:]:
        out = _node(T.SUBTRACT if sign < 0 else T.ADD, out, term)
    return out


def _linear(values: list[Fraction], names: tuple[str, ...]) -> CoreNode:
    """``a x + b y + c z`` with the signs written as the keyboard would."""
    items = [(1 if k > 0 else -1, _term(k, n)) for k, n in zip(values, names, strict=True) if k]
    if not items:
        raise SolveError("empty equation")
    return _chain(items)


def _standard(row: _Row, names: tuple[str, ...]) -> CoreNode:
    return _equation(_linear(row[:-1], names), _cell(row[-1]))


def _one_step(before: CoreNode, after: CoreNode, key: str, args: list[CoreNode]) -> SolveResult:
    detail = SolveResult()
    detail.add_group(key, Step(before, after, key, args))
    detail.set_solution(after)
    return detail


def _signed_constants(node: CoreNode) -> CoreNode:
    """``-(1)`` and the constant ``-1`` are the same number: compare them alike."""
    if node.type is T.NEGATIVE and node.children[0].type is T.CONSTANT:
        return CoreNode.constant("-" + (node.children[0].value or ""))
    return CoreNode(
        type=node.type, value=node.value, children=[_signed_constants(c) for c in node.children]
    )


def _flatten_terms(node: CoreNode) -> list[CoreNode]:
    if node.type is T.BRACKET and len(node.children) == 1:
        return _flatten_terms(node.children[0])
    if node.type is T.ADD:
        out: list[CoreNode] = []
        for child in node.children:
            out.extend(_flatten_terms(child))
        return out
    return [node]


def _add_chain(terms: list[CoreNode]) -> CoreNode:
    node = terms[0]
    for term in terms[1:]:
        node = _node(T.ADD, node, term)
    return node


def _sum_suffix_detail(before: CoreNode, after: CoreNode) -> SolveResult | None:
    """``y+y+z`` → ``1y+1y+z`` → ``(1+1)y+z`` → ``2y+z``."""
    if before.type is not T.SYSTEM or after.type is not T.SYSTEM:
        return None
    if len(before.children) != len(after.children):
        return None
    changed = [
        index
        for index, (old, new) in enumerate(zip(before.children, after.children, strict=True))
        if not old.structural_eq(new)
    ]
    if len(changed) != 1:
        return None
    index = changed[0]
    old, new = before.children[index], after.children[index]
    if old.type is not T.EQUALS or new.type is not T.EQUALS:
        return None
    terms = _flatten_terms(old.children[0])
    names = [term.value for term in terms if term.type is T.VARIABLE and term.value is not None]
    if len(names) == len(set(names)):
        return None
    duplicated = next(name for name in names if names.count(name) >= 2)
    positions = sorted(
        position
        for position, term in enumerate(terms)
        if term.type is T.VARIABLE and term.value == duplicated
    )
    if len(positions) != 2:
        return None
    variable = _var(duplicated)
    one = _num(1)

    def system_with(left: CoreNode) -> CoreNode:
        parts = list(before.children)
        parts[index] = _equation(left, old.children[1])
        return _system(*parts)

    first_terms = list(terms)
    first_terms[positions[0]] = _node(T.MULTIPLY, one, variable)
    second_terms = list(first_terms)
    second_terms[positions[1]] = _node(T.MULTIPLY, one, variable)
    grouped = list(second_terms)
    grouped[positions[0]] = _node(
        T.MULTIPLY,
        _node(T.BRACKET, _node(T.ADD, one, one)),
        variable,
    )
    grouped.pop(positions[1])
    final = list(grouped)
    final[positions[0]] = _term(Fraction(2), duplicated)

    stages = [
        ("sum_suffix_add_one", [_num(1)], _add_chain(first_terms)),
        ("sum_suffix_add_one", [_num(1)], _add_chain(second_terms)),
        ("sum_suffix_add_detail", [], _add_chain(grouped)),
        ("add", [], _add_chain(final)),
    ]
    detail = SolveResult()
    previous = before
    for key, args, left in stages:
        current = system_with(left)
        detail.add_group(key, Step(previous, current, key, list(args)))
        previous = current
    if not previous.children[index].structural_eq(new):
        return None
    detail.set_solution(previous)
    return detail


class _Case3:
    """Three equations in three unknowns with ``D != 0``."""

    def __init__(self, node: CoreNode, names: tuple[str, ...]) -> None:
        self.node, self.names = node, names
        found = [_coefficients3(e, names) for e in node.children]
        if len(node.children) != 3 or any(f is None for f in found):
            raise SolveError("not a 3x3 integer linear system")
        self.rows: list[_Row] = [[Fraction(v) for v in f] for f in found if f is not None]
        self.det = _value([row[:3] for row in self.rows])
        if self.det == 0:
            raise SolveError("degenerate system")
        minors = []
        for column in range(3):
            rows = [list(row[:3]) for row in self.rows]
            for index, row in enumerate(rows):
                row[column] = self.rows[index][3]
            minors.append(rows)
        self.minors = minors
        self.dets = [[row[:3] for row in self.rows], *minors]
        self.values = [_value(rows) for rows in self.dets]
        self.solution = [v / self.det for v in self.values[1:]]
        self.standard_forms = [_standard(row, names) for row in self.rows]
        self.is_standard = all(
            _signed_constants(original).structural_eq(_signed_constants(form))
            for original, form in zip(node.children, self.standard_forms, strict=True)
        )

    # -- shared rows -----------------------------------------------------------

    def answer(self) -> CoreNode:
        return _node(
            T.LIST,
            *[
                _equation(_var(name), _cell(value))
                for name, value in zip(self.names, self.solution, strict=True)
            ],
        )

    def start(self, result: SolveResult) -> CoreNode:
        """The system itself, or its standard form on a row of its own."""
        if self.is_standard:
            return self.node
        standard = _system(*self.standard_forms)
        result.add_group(
            "simplify_msg",
            Step(
                self.node,
                standard,
                "simplify",
                subresult=_one_step(self.node, standard, "simplify", []),
            ),
        )
        return standard

    def tail(self, result: SolveResult, before: CoreNode) -> None:
        triple = _equation(
            _node(T.BRACKET, _node(T.LIST, *[_var(n) for n in self.names])),
            _node(T.BRACKET, _node(T.LIST, *[_cell(v) for v in self.solution])),
        )
        result.add_group("possible_sol", Step(before, triple, "system_3x3_possible_sol", [triple]))
        numbers = {n: _cell(v) for n, v in zip(self.names, self.solution, strict=True)}
        checks = []
        for original in self.node.children:
            filled = original
            for name, value in numbers.items():
                filled = _replace(filled, name, value)
            checks.append(filled)
        checked = _system(*checks)
        result.add_group("solution_check_sol", Step(triple, checked, "system_3x3_check_sol"))
        detail = check_detail(checks)
        done = detail.solution if detail.solution is not None else checked
        detail.set_solution(done)
        result.add_group("simplify_msg", Step(checked, done, "system_ver", subresult=detail))
        result.add_group(
            CoreRichText(type="system_3x3_triple_is_sol", args=[done]),
            Step(done, done, "system_3x3_check_t"),
        )
        result.set_solution(self.answer())
        result.header = "system_cramer_solve"

    # -- Cramer ----------------------------------------------------------------

    def cramer(self) -> SolveResult:
        names, dets, values = self.names, self.dets, self.values
        result = SolveResult()
        letters = [_var("D"), _var("D_1"), _var("D_2"), _var("D_3")]
        listing = _node(
            T.LIST,
            *[_equation(sym, _determinant(rows)) for sym, rows in zip(letters, dets, strict=True)],
        )
        result.add_group("system_list_det", Step(self.node, listing, "system_3x3_cramer_rule"))

        def after(count: int) -> CoreNode:
            parts = list(listing.children)
            for j in range(count):
                parts[j] = _equation(letters[j], _cell(values[j]))
            return _node(T.LIST, *parts)

        def page(index: int, previous: CoreNode) -> Step:
            rows = [[int(v) for v in row] for row in dets[index]]
            if all(cell != 0 for row in rows for cell in row):
                detail = det3_sarrus_detail(rows, int(values[index]))
            else:
                detail = det3_detail(rows, int(values[index]))
            detail.set_solution(_cell(values[index]))
            return Step(previous, after(index + 1), "det_evaluate", subresult=detail)

        result.add_group("det_evaluate", page(0, listing))
        pages = [page(1, after(1)), page(2, after(2)), page(3, after(3))]
        list_names = ", ".join(names)
        formulas = _node(
            T.LIST,
            *[
                _equation(_var(name), _node(T.FRACTION, letters[index + 1], letters[0]))
                for index, name in enumerate(names)
            ],
        )
        answer = self.answer()
        rule = SolveResult()
        condition = _node(T.NOT_EQUALS, letters[0], _num(0))
        applied = _node(
            T.LIST,
            *[
                _equation(
                    _var(name),
                    _node(T.FRACTION, _cell(values[index + 1]), _cell(values[0])),
                )
                for index, name in enumerate(names)
            ],
        )
        reducible = [index for index in range(len(names)) if _reduces(values[index + 1], values[0])]
        if reducible:
            rule.add_group(
                "system_3x3_cramer_apply_rule",
                Step(
                    after(4),
                    applied,
                    "system_3x3_cramer_apply_rule",
                    [condition, _var(list_names), formulas],
                ),
            )
            previous, parts = applied, list(applied.children)
            calculated = []
            for index in reducible:
                parts = list(parts)
                parts[index] = _equation(_var(names[index]), _cell(self.solution[index]))
                now = _node(T.LIST, *parts)
                if abs(values[0]) == 1:
                    calculated.append(Step(previous, now, "div_with_one", [_cell(values[0])]))
                else:
                    calculated.append(
                        Step(
                            previous,
                            now,
                            "frac_reduce_frac_num",
                            [_cell(values[0])],
                        )
                    )
                previous = now
            rule.add_group("calculate_short", *calculated)
        rule.set_solution(answer)
        apply = Step(
            after(4),
            answer,
            "system_3x3_cramer_apply_rule",
            [condition, _var(list_names), formulas],
            subresult=rule if reducible else None,
        )
        result.add_group(
            [
                "det_evaluate",
                "det_evaluate",
                "det_evaluate",
                CoreRichText(type="find_arg", args=[_var(list_names)]),
            ],
            *pages,
            apply,
        )
        self.tail(result, answer)
        return result

    # -- inverse matrix --------------------------------------------------------

    def inverse(self) -> SolveResult | None:
        """``X = A⁻¹B``: the inverse and the product come from :mod:`solver.matrices`."""
        from .matrices import _multiply_rows, matrix_inverse

        names, rows = self.names, self.rows
        result = SolveResult()
        start = self.start(result)

        def matrix(cells: list[list[CoreNode]]) -> CoreNode:
            return _node(T.MATRIX, *[_node(T.MATRIX_ROW, *row) for row in cells])

        coefficients = matrix([[_cell(v) for v in row[:3]] for row in rows])
        unknowns = matrix([[_var(name)] for name in names])
        constants = matrix([[_cell(row[3])] for row in rows])
        letters = (_var("A"), _var("X"), _var("B"))
        equation = _equation(_node(T.MULTIPLY, coefficients, unknowns), constants)
        symbolic = _equation(_node(T.MULTIPLY_IMPLICIT, letters[0], letters[1]), letters[2])
        result.add_group(
            "system_2x2_inv_matrix_write_as_mat_eq_smpl",
            Step(
                start,
                equation,
                "system_2x2_inv_matrix_write_as_mat_eq",
                [symbolic, coefficients, unknowns, constants],
            ),
        )
        identified = _equation(letters[0], coefficients)
        result.add_group(
            "matrix_identify",
            Step(equation, identified, "system_2x2_inv_matrix_identify", [letters[0]]),
        )
        matrix_a = sympy.Matrix([[Fraction(v) for v in row[:3]] for row in rows])
        result.add_group(
            "system_matrix_inv_det",
            Step(identified, from_sympy(matrix_a.det()), "system_matrix_inv_det"),
        )
        inverse_a = matrix_a.inv()
        inverse_rows = [[from_sympy(inverse_a[i, j]) for j in range(3)] for i in range(3)]
        inverse = _equation(_var("A^-1"), matrix(inverse_rows))
        detail = SolveResult()
        matrix_inverse(coefficients, SolveContext(result=detail, variables=[]), [])
        if not detail:
            return None
        detail.set_solution(inverse)
        result.add_group(
            "matrix_inv_find_smpl",
            Step(identified, inverse, "system_2x2_inv_matrix_find_inv", subresult=detail),
        )
        product = _equation(unknowns, _node(T.MULTIPLY, matrix(inverse_rows), constants))
        result.add_group(
            "system_2x2_inv_matrix_sub_eq_smpl",
            Step(
                inverse,
                product,
                "system_2x2_inv_matrix_sub_eq",
                [
                    inverse.children[1],
                    unknowns,
                    constants,
                    _equation(letters[1], _var("A^-1 B")),
                ],
            ),
        )
        solved = _equation(unknowns, matrix([[_cell(v)] for v in self.solution]))
        mult = SolveResult()
        target = sympy.Matrix([Fraction(row[3]) for row in rows])
        answer = sympy.Matrix([Fraction(v) for v in self.solution])
        _multiply_rows(product, inverse_a, target, answer, SolveContext(result=mult, variables=[]))
        result.add_group("calculate_direct", Step(product, solved, "matrix_mul", subresult=mult))
        listed = self.answer()
        result.add_group("set_equations", Step(solved, listed, "matrix_eq_set_elements_equal"))
        self.tail(result, listed)
        return result

    # -- Gauss-Jordan ----------------------------------------------------------

    def _augmented(self, rows: list[_Row]) -> CoreNode:
        return _node(
            T.MATRIX_SPLIT_LAST,
            *[_node(T.MATRIX_ROW, *[_cell(v) for v in row]) for row in rows],
        )

    def gauss(self) -> SolveResult | None:
        """Unknowns that occur least often go first; the sparsest row is the pivot."""
        rows = [list(row) for row in self.rows]
        result = SolveResult()
        start = self.start(result)
        matrix = self._augmented(rows)
        result.add_group(
            "system_convert_eq_to_mat", Step(start, matrix, "system_write_coeffs_to_mat")
        )
        order = sorted(range(3), key=lambda c: (sum(1 for r in rows if r[c] != 0), c))
        pivots: dict[int, int] = {}
        for column in order:
            candidates = [r for r in range(3) if r not in pivots and rows[r][column] != 0]
            if not candidates:
                return None
            pivot = min(
                candidates,
                key=lambda r: (abs(rows[r][column]) != 1, sum(1 for v in rows[r][:3] if v != 0), r),
            )
            entry = rows[pivot][column]
            if entry != 1:
                before = self._augmented(rows)
                rows[pivot] = [v / entry for v in rows[pivot]]
                after = self._augmented(rows)
                key = "mat_mul_row" if entry == -1 else "mat_divide_row"
                simple = "mat_mul_row_simple" if entry == -1 else "mat_divide_row_simple"
                args = [_num(Fraction(-1) if entry == -1 else entry)]
                element = "mat_mul_row_element" if entry == -1 else "mat_divide_row_element"
                result.add_group(
                    simple,
                    Step(
                        before,
                        after,
                        key,
                        args,
                        subresult=arithmetic_row_detail(before, after, element, args, _cell),
                    ),
                )
            pivots[pivot] = column
            steps: list[Step] = []
            for target in range(3):
                if target == pivot or rows[target][column] == 0:
                    continue
                factor = -rows[target][column]
                before = self._augmented(rows)
                rows[target] = [
                    t + factor * p for t, p in zip(rows[target], rows[pivot], strict=True)
                ]
                after = self._augmented(rows)
                if factor == 1:
                    key, args = "row_elim", [_num(pivot + 1), _num(target + 1)]
                    element = "row_elim_add"
                else:
                    key, args = "row_elim_out", [_num(pivot + 1), _cell(factor), _num(target + 1)]
                    element = "mul_row_add"
                steps.append(
                    Step(
                        before,
                        after,
                        key,
                        args,
                        subresult=arithmetic_row_detail(before, after, element, args, _cell),
                    )
                )
            if steps:
                result.add_group(
                    "simplify_row" if len(steps) == 1 else "simplify_row_plural", *steps
                )
        listed = _node(
            T.LIST,
            *[
                _equation(_var(self.names[pivots_inverse]), _cell(rows[row][3]))
                for row, pivots_inverse in sorted(pivots.items())
            ],
        )
        result.add_group(
            "system_convert_mat_to_eq_short",
            Step(self._augmented(rows), listed, "system_convert_mat_to_eq"),
        )
        self.tail(result, listed)
        return result

    # -- substitution ----------------------------------------------------------

    def substitution(self) -> SolveResult | None:
        """Isolate an unknown from the sparsest equation, then solve the rest as a 2x2 system."""
        used = [sum(1 for v in row[:3] if v != 0) for row in self.rows]
        source = min(range(3), key=lambda i: (used[i], i))
        unit = [c for c in range(3) if abs(self.rows[source][c]) == 1]
        if not unit:
            return None
        pivot = unit[0]
        holders = [i for i in range(3) if i != source and self.rows[i][pivot] != 0]
        if len(holders) != 1:
            return None
        target = holders[0]
        spare = next(i for i in range(3) if i not in (source, target))
        names, rows = self.names, self.rows
        result = SolveResult()
        start = self.start(result)
        originals = list(start.children)
        sign = rows[source][pivot]  # +-1
        # u = (d - sum a_j v_j) / a_u
        items: list[tuple[int, CoreNode]] = []
        if rows[source][3] != 0:
            constant = rows[source][3] * sign
            items.append((1 if constant > 0 else -1, _cell(abs(constant))))
        for column in range(3):
            if column == pivot or rows[source][column] == 0:
                continue
            coefficient = -rows[source][column] * sign
            items.append((1 if coefficient > 0 else -1, _term(coefficient, names[column])))
        expression = _chain(items) if items else _num(0)
        isolated = _equation(_var(names[pivot]), expression)
        with_isolated = list(originals)
        with_isolated[source] = isolated
        solved_for = _system(*with_isolated)
        moved = [
            name
            for column, name in enumerate(names)
            if column != pivot and rows[source][column] != 0
        ]
        detail = None
        if len(moved) == 1:
            column = names.index(moved[0])
            detail = isolation_detail(
                originals[source], isolated, moved[0], int(rows[source][column])
            )
        if detail is None:
            detail = _one_step(originals[source], isolated, "rel_move_right_var", [])
        result.add_group(
            "eq_solve_short",
            Step(
                start,
                solved_for,
                "eq_linear",
                [_var(names[pivot])],
                subresult=detail,
            ),
        )
        merged = _replace(originals[target], names[pivot], expression)
        # keep the order of the remaining equations as written
        remaining = sorted((target, spare))
        sub_system = _system(*[merged if i == target else originals[i] for i in remaining])
        result.add_group(
            CoreRichText(type="substitute_value_of", args=[_var(names[pivot])]),
            Step(
                solved_for,
                sub_system,
                "system_substitute_value",
                [_var(names[pivot]), originals[target]],
            ),
        )
        # the two equations in the remaining unknowns
        others = [c for c in range(3) if c != pivot]
        reduced: list[_Row] = []
        for index in remaining:
            ratio = rows[index][pivot] / rows[source][pivot]
            reduced.append(
                [rows[index][c] - ratio * rows[source][c] for c in others]
                + [rows[index][3] - ratio * rows[source][3]]
            )
        pair_names: tuple[str, str] = (names[others[0]], names[others[1]])
        pair_nodes = [_standard(row, pair_names) for row in reduced]
        pair = _system(*pair_nodes)
        simplify = _sum_suffix_detail(sub_system, pair)
        if simplify is None:
            simplify = _one_step(sub_system, pair, "simplify", [])
        result.add_group(
            "simplify_msg",
            Step(sub_system, pair, "simplify", subresult=simplify),
        )
        written = [
            list(r) for r in reduced
        ]  # the equations as they are written, before any scaling
        current = pair
        columns = [(written[0][c], written[1][c]) for c in range(2)]
        equal_column = next((i for i, (p, q) in enumerate(columns) if p == q != 0), None)
        opposite_column = next((i for i, (p, q) in enumerate(columns) if p == -q != 0), None)
        if equal_column is not None and opposite_column is None:
            second = [-v for v in reduced[1]]
            scaled = _standard(second, pair_names)
            flipped = _system(pair_nodes[0], scaled)
            detail = SolveResult()
            detail.add_group(
                CoreRichText(type="eq_mul_direct", args=[_num(-1)]),
                Step(pair, flipped, "eq_mul_direct", [_num(-1)]),
            )
            detail.set_solution(flipped)
            result.add_group(
                "multiply_both_sides",
                Step(pair, flipped, "eq_mul_direct", [_num(-1)], subresult=detail),
            )
            current = flipped
            reduced[1] = second
        elif opposite_column is None:
            return None
        gone = equal_column if equal_column is not None else opposite_column
        assert gone is not None
        kept = 1 - gone
        total_coefficient = reduced[0][kept] + reduced[1][kept]
        total = reduced[0][2] + reduced[1][2]
        if total_coefficient == 0:
            return None
        summed = _equation(
            _term(total_coefficient, pair_names[kept])
            if total_coefficient > 0
            else _node(T.NEGATIVE, _term(total_coefficient, pair_names[kept])),
            _cell(total),
        )
        value = total / total_coefficient
        found = _equation(_var(pair_names[kept]), _cell(value))
        if total_coefficient == 1:
            summed = found
        sum_detail = None
        first_eq = _coefficients(current.children[0], pair_names)
        second_eq = _coefficients(current.children[1], pair_names)
        if first_eq is not None and second_eq is not None:
            sum_detail = addition_detail(current, first_eq, second_eq, pair_names, gone)
        if sum_detail is None:
            sum_detail = SolveResult()
            sum_detail.add_group("system_2x2_sum", Step(current, summed, "system_2x2_sum"))
        sum_detail.set_solution(summed)
        result.add_group(
            "eliminate_variable", Step(current, summed, "system_2x2_sum", subresult=sum_detail)
        )
        if total_coefficient != 1:
            divide = SolveResult()
            divide.add_group(
                CoreRichText(type="eq_linear_div", args=[_cell(total_coefficient)]),
                Step(summed, found, "eq_linear_div", [_cell(total_coefficient)]),
            )
            divide.set_solution(found)
            result.add_group(
                "divide_both_sides",
                Step(summed, found, "eq_linear_div", [_cell(total_coefficient)], subresult=divide),
            )
        # the kept unknown goes into the second remaining equation, the other one is solved
        holder = written[1] if written[1][gone] != 0 else written[0]
        other_value = (holder[2] - holder[kept] * value) / holder[gone]
        second_equation = pair_nodes[1] if written[1][gone] != 0 else pair_nodes[0]
        filled = _replace(second_equation, pair_names[kept], _cell(value))
        result.add_group(
            CoreRichText(type="substitute_value_of", args=[_var(pair_names[kept])]),
            Step(
                found, filled, "system_substitute_value", [_var(pair_names[kept]), second_equation]
            ),
        )
        solved_other = _equation(_var(pair_names[gone]), _cell(other_value))
        result.add_group(
            "eq_solve_short",
            Step(
                filled,
                solved_other,
                "eq_linear",
                [_var(pair_names[gone])],
                subresult=_one_step(filled, solved_other, "eq_linear", [_var(pair_names[gone])]),
            ),
        )
        # back to the isolated unknown
        values = {pair_names[kept]: value, pair_names[gone]: other_value}
        back = expression
        for name, number in values.items():
            back = _replace(back, name, _cell(number))
        filled_back = _equation(_var(names[pivot]), back)
        result.add_group(
            CoreRichText(type="substitute_value_of", args=[_var(pair_names[gone])]),
            Step(
                solved_other,
                filled_back,
                "system_substitute_value",
                [_var(pair_names[gone]), isolated],
            ),
        )
        final_value = self.solution[pivot]
        last = _equation(_var(names[pivot]), _cell(final_value))
        result.add_group(
            "calculate_short",
            Step(
                filled_back,
                last,
                "calculate_direct",
                subresult=_one_step(back, _cell(final_value), "calculate_direct", []),
            ),
        )
        self.tail(result, self.answer())
        return result


def _not_applicable_cramer(node: CoreNode, names: tuple[str, ...], rows: list[_Row]) -> SolveResult:
    """Cramer's rule for a singular 3×3: determinants, then «not applicable»."""
    letters = [_var("D"), _var("D_1"), _var("D_2"), _var("D_3")]
    dets = [[row[:3] for row in rows]]
    for column in range(3):
        minor = [list(row[:3]) for row in rows]
        for index, row in enumerate(minor):
            row[column] = rows[index][3]
        dets.append(minor)
    listing = _node(
        T.LIST,
        *[
            _equation(letter, _determinant(item))
            for letter, item in zip(letters, dets, strict=True)
        ],
    )
    result = SolveResult()
    result.add_group("system_list_det", Step(node, listing, "system_3x3_cramer_rule"))
    current = listing
    for index, item in enumerate(dets):
        parts = list(current.children)
        for earlier in range(index + 1):
            parts[earlier] = _equation(letters[earlier], _cell(_value(dets[earlier])))
        nxt = _node(T.LIST, *parts)
        values = [int(cell) for row in item for cell in row]
        if all(cell != 0 for cell in values):
            detail = det3_sarrus_detail(
                [[int(value) for value in row] for row in item], int(_value(item))
            )
        else:
            detail = det3_detail([[int(value) for value in row] for row in item], int(_value(item)))
        result.add_group("evaluate", Step(current, nxt, "det_evaluate", subresult=detail))
        current = nxt
    formulas = [
        _equation(_var(name), _node(T.FRACTION, letters[index + 1], letters[0]))
        for index, name in enumerate(names)
    ]
    result.add_group(
        "system_cramer_does_not_apply",
        Step(
            current,
            CoreNode.empty(),
            "system_3x3_cramer_not_applicable",
            [_equation(letters[0], _num(0)), _node(T.LIST, *formulas[:2]), formulas[2]],
        ),
    )
    result.set_solution(CoreNode.empty())
    return result


def degenerate_methods(node: CoreNode, variables: list[str]) -> list[SolveResult] | None:
    """The app's cards for a singular 3×3 integer system."""
    if len(variables) != 3 or len(node.children) != 3 or node.type is not T.SYSTEM:
        return None
    ordered = sorted(variables)
    names: tuple[str, ...] = (ordered[0], ordered[1], ordered[2])
    found = [_coefficients3(equation, names) for equation in node.children]
    if any(item is None for item in found):
        return None
    rows: list[_Row] = [[Fraction(value) for value in item] for item in found if item is not None]
    if _value([row[:3] for row in rows]) != 0:
        return None
    matrix = sympy.Matrix([[row[0], row[1], row[2]] for row in rows])
    constants = sympy.Matrix([row[3] for row in rows])
    inconsistent = matrix.row_join(constants).rank() > matrix.rank()
    cards: list[SolveResult] = []
    if inconsistent:
        card = SolveResult()
        card.header = "solve_algebraically"
        card.add_group(
            "system_no_sol",
            Step(node, _empty_element(list(names)), "system_nxn_invalid"),
        )
        card.set_solution(_empty_element(list(names)))
        cards.append(card)
    else:
        duplicate = None
        for index in (1, 2):
            if all(
                rows[index][column] * rows[0][3] == rows[0][column] * rows[index][3]
                for column in range(3)
            ):
                duplicate = index
                break
        if duplicate is not None:
            card = SolveResult()
            card.header = "solve_using_substitution"
            remaining = [
                equation for index, equation in enumerate(node.children) if index != duplicate
            ]
            card.add_group(
                "system_remove_double_eq",
                Step(
                    node,
                    _system(*remaining),
                    "system_remove_double_eq_arg",
                    [node.children[duplicate]],
                ),
            )
            card.set_solution(_system(*remaining))
            cards.append(card)
    cramer = _not_applicable_cramer(node, names, rows)
    cramer.header = "system_cramer_solve"
    cards.append(cramer)
    return cards or None


def cramer_methods(node: CoreNode, variables: list[str]) -> list[SolveResult] | None:
    """The cards for three equations in three unknowns with ``D != 0``, else ``None``.

    Substitution, Gauss-Jordan, Cramer's rule and the inverse matrix — each card
    that the verified rules can explain; the others are left out.
    """
    if len(variables) != 3 or len(node.children) != 3 or node.type is not T.SYSTEM:
        return None
    try:
        case = _Case3(node, tuple(sorted(variables)))
    except SolveError:
        return None
    builders = (
        ("system_subs_method_solve", case.substitution),
        ("system_gauss_jordan", case.gauss),
        ("system_cramer_solve", case.cramer),
        ("system_2x2_inv_matrix_solve", case.inverse),
    )
    cards = []
    for header, build in builders:
        card = build()
        if card is not None:
            card.header = header
            cards.append(card)
    return cards or None


__all__ = ["cramer_methods"]
