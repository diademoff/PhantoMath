"""the six methods for a 2x2 linear system .

Substitution, elimination by addition, comparison, Gauss-Jordan, Cramer's rule and the inverse
matrix, each ending with the same four rows (the ordered pair, the check, the simplified check and
the verdict). Applies to integer coefficients with a unique integer solution; any method whose
verified rule does not cover the system is left out, and anything else uses the general solver.

shortcut: the choice of the isolated variable, the elimination variable and the row operations is
inferred from three verified systems (x+y=3 / x-y=1, 2x+y=5 / x-y=1, y=2x / x+y=6); other
coefficient patterns are explained by the same rules.
"""

from __future__ import annotations

from collections.abc import Callable
from fractions import Fraction
from math import gcd

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .arithmetic import as_fraction, format_number
from .base import SolveContext, SolveError, SolveResult, Step, route
from .quadratic_cards import _SIGNS, _detail, _fraction_node, _num
from .sympy_bridge import from_sympy

_Eq = tuple[int, int, int]  # a x + b y = c


def _node(kind: T, *children: CoreNode) -> CoreNode:
    return CoreNode.node(kind, *children)


def _exact(numerator: int, denominator: int) -> int | Fraction:
    value = Fraction(numerator, denominator)
    return int(value) if value.denominator == 1 else value


def _var(name: str) -> CoreNode:
    return CoreNode.variable(name)


def _term(coefficient: int, name: str) -> CoreNode:
    size = abs(coefficient)
    return _var(name) if size == 1 else _node(T.MULTIPLY_IMPLICIT, _num(size), _var(name))


def _chain(items: list[tuple[int, CoreNode]]) -> CoreNode:
    """``+/- t1 +/- t2``: the first minus is a NEGATIVE node, later ones SUBTRACT."""
    if not items:
        return _num(0)  # 2y = 0 moved right: nothing left but 0
    sign, first = items[0]
    out = _node(T.NEGATIVE, first) if sign < 0 else first
    for sign, term in items[1:]:
        out = _node(T.SUBTRACT if sign < 0 else T.ADD, out, term)
    return out


def _linear(a: int, b: int, names: tuple[str, str]) -> CoreNode:
    items = [(1 if k > 0 else -1, _term(k, n)) for k, n in zip((a, b), names, strict=True) if k]
    return _chain(items)


def _equation(left: CoreNode, right: CoreNode) -> CoreNode:
    return _node(T.EQUALS, left, right)


def _system(*equations: CoreNode) -> CoreNode:
    return _node(T.SYSTEM, *equations)


def _coefficients(equation: CoreNode, names: tuple[str, str]) -> _Eq | None:
    """Integer ``(a, b, c)`` of a linear equation in the two names, or ``None``."""
    from .systems import _equation_form

    try:
        coefficients, constant = _equation_form(equation, {names[0]: 0, names[1]: 1})
    except SolveError:
        return None
    values = [*coefficients, -constant]
    if len(values) != 3 or any(Fraction(v).denominator != 1 for v in values):
        return None
    return int(values[0]), int(values[1]), int(values[2])


def _coefficients3(equation: CoreNode, names: tuple[str, ...]) -> tuple[int, int, int, int] | None:
    """Integer ``(a, b, c, d)`` of ``a x + b y + c z = d``, or ``None``."""
    from .systems import _equation_form

    try:
        coefficients, constant = _equation_form(equation, {n: i for i, n in enumerate(names)})
    except SolveError:
        return None
    values = [*coefficients, -constant]
    if len(values) != 4 or any(Fraction(v).denominator != 1 for v in values):
        return None
    return int(values[0]), int(values[1]), int(values[2]), int(values[3])


def _replace(node: CoreNode, name: str, replacement: CoreNode, parent: T | None = None) -> CoreNode:
    """Replace a variable, bracketing the replacement where the grammar needs it."""
    if node.type is T.VARIABLE and node.value == name:
        needs = replacement.type in (T.ADD, T.SUBTRACT, T.NEGATIVE) and parent in (
            T.SUBTRACT,
            T.MULTIPLY,
            T.MULTIPLY_IMPLICIT,
            T.NEGATIVE,
            T.POWER,
        )
        return _node(T.BRACKET, replacement) if needs else replacement
    if not node.children:
        return node
    kind = (
        T.MULTIPLY if node.type is T.MULTIPLY_IMPLICIT and replacement.type is T.CONSTANT else None
    )
    children = [
        _replace(child, name, replacement, node.type if index else None)
        if node.type is not T.SUBTRACT or index
        else _replace(child, name, replacement, None)
        for index, child in enumerate(node.children)
    ]
    # a bracket keeps the whole replacement together: 2(1+y), x-(5-2x)
    return CoreNode(type=kind or node.type, value=node.value, children=children)


def _solve_nested(equation: CoreNode, name: str, value: int | Fraction) -> SolveResult:
    """The one-unknown solution screen, with a one-step fallback if the solver cannot explain it."""
    from .equations import solve_methods

    try:
        return solve_methods(equation, [name])[0]
    except SolveError:
        answer = _equation(_var(name), _num(value))
        fallback = SolveResult()
        fallback.add_group("eq_linear", Step(equation, answer, "eq_linear", [_var(name)]))
        fallback.set_solution(answer)
        return fallback


def _contains(node: CoreNode, name: str) -> bool:
    return (node.type is T.VARIABLE and node.value == name) or any(
        _contains(child, name) for child in node.children
    )


def _det_rule() -> CoreNode:
    """``|a b; c d| = ad - bc``: the argument of the determinant row."""
    letters = [CoreNode.variable(v) for v in "abcd"]
    return _node(
        T.EQUALS,
        _node(T.DETERMINANT2, *letters),
        _node(
            T.SUBTRACT,
            _node(T.MULTIPLY, letters[0], letters[3]),
            _node(T.MULTIPLY, letters[1], letters[2]),
        ),
    )


# «Подробнее» строки: операция описывается поэлементно (её текст не повторяет
# подпись самого шага) .
_ROW_DETAIL = {
    "row_elim": "row_elim_add",
    "row_elim_out": "mul_row_add",
    "mat_divide_row": "mat_divide_row_element",
    "mat_mul_row": "mat_mul_row_element",
}

# ── микрошаги арифметики внутри карточек системы ────────────────────────────
# Решатель раскрывает каждую ячейку строки (и каждый определитель) до
# отдельных действий: «умножить на 1», «убрать скобки», «сложить числа».
# Эти шаги не решают систему заново — они только объясняют уже сделанное
# преобразование, поэтому ключи берутся из словаря как есть.


def _cell_value(node: CoreNode) -> Fraction:
    """Число из узла ячейки: константа, дробь или отрицание."""
    if node.type is T.CONSTANT:
        return as_fraction(node)
    if node.type is T.FRACTION:
        return as_fraction(node.children[0]) / as_fraction(node.children[1])
    if node.type is T.NEGATIVE:
        return -_cell_value(node.children[0])
    if node.type is T.BRACKET:
        return _cell_value(node.children[0])
    if node.type is T.POSITIVE:
        return _cell_value(node.children[0])
    raise SolveError(f"ячейка не число: {node.type}")


def _sign_rule(kind: T) -> CoreNode:
    """Аргумент отриц.×отриц. / отриц.÷отриц.: ``(−)·(−) = +``."""
    shown = T.FRACTION if kind is T.DIVIDE else T.MULTIPLY
    return _node(T.EQUALS, _node(shown, _SIGNS[1], _SIGNS[1]), _SIGNS[0])


def _sum_key(
    kind: T, left: Fraction, right: Fraction, total: Fraction
) -> tuple[str, list[CoreNode]]:
    """Ключ и аргументы сложения/вычитания чисел."""
    if kind is T.SUBTRACT:
        if total == 0 and left == right:
            return "sub_with_self_num", [_num(0)]
        if left == 0 or right == 0:
            return "add_with_zero", [_num(0)]
        if right < 0:
            return "calc_sum", []
        if left < 0 or left < right:
            return "calc_diff", []
        return "sub", []
    if total == 0 and left == -right:
        return "sub_with_self_num", [_num(0)]
    if left == 0 or right == 0:
        return "add_with_zero", [_num(0)]
    if (left < 0) != (right < 0):
        return "calc_sum", []
    return "add", []


def _div_key(left: Fraction, right: Fraction) -> tuple[str, list[CoreNode]]:
    if left == 0:
        return "div_zero", [_num(0)]
    if left == right:
        return "div_with_self", [_num(1)]
    if right == 1:
        return "div_with_one", [_num(1)]
    if right < 0 and left < 0:
        return "div_neg_neg", [_sign_rule(T.DIVIDE)]
    if (left / right).denominator == 1:
        return "quotient", []
    return "div_to_frac", []


def _has_bracket(node: CoreNode) -> bool:
    return node.type is T.BRACKET or any(_has_bracket(child) for child in node.children)


def _without_brackets(node: CoreNode) -> CoreNode:
    """Убрать скобки вокруг отрицательного числа: ``(-1)`` → ``-1``."""
    if node.type is T.BRACKET and len(node.children) == 1:
        inner = _without_brackets(node.children[0])
        if inner.type is T.CONSTANT and _cell_value(inner) < 0:
            return _node(T.NEGATIVE, _num(-_cell_value(inner)))
        return inner
    if not node.children:
        return node
    return CoreNode(
        type=node.type, value=node.value, children=[_without_brackets(c) for c in node.children]
    )


def _simplify_cell(
    node: CoreNode,
    emit: Callable[[CoreNode, CoreNode, str, list[CoreNode]], None],
    finish: Callable[[Fraction], CoreNode],
) -> CoreNode:
    """Свернуть числовое выражение ячейки, добавляя шаг на каждую операцию.

    Порядок — снизу вверх (сначала произведения, затем сумма).
    ``finish`` превращает итоговое число в узел матрицы (дробь
    остаётся дробью).
    """
    if node.type in (T.CONSTANT, T.FRACTION, T.VARIABLE):
        return node
    if node.type is T.BRACKET:
        return _node(T.BRACKET, _simplify_cell(node.children[0], emit, finish))
    if node.type is T.NEGATIVE and len(node.children) == 1:
        inner = _simplify_cell(node.children[0], emit, finish)
        if inner.type is T.NEGATIVE and len(inner.children) == 1:
            return inner.children[0]
        left = _node(T.NEGATIVE, inner)
        if inner.type is T.BRACKET and _cell_value(inner) < 0:
            right = finish(-_cell_value(inner))
            emit(left, right, "neg_neg_arg", [_SIGNS[1]])
            return right
        if inner.type in (T.CONSTANT, T.FRACTION):
            return finish(-_cell_value(inner))
        return left
    children = [_simplify_cell(child, emit, finish) for child in node.children]
    left = CoreNode(type=node.type, value=node.value, children=children)
    try:
        values = [_cell_value(child) for child in children]
    except SolveError:
        return left

    if node.type in (T.ADD, T.SUBTRACT) and len(values) == 2:
        first, second = values
        total = first + second if node.type is T.ADD else first - second
        key, args = _sum_key(node.type, first, second, total)
        if key in ("sub_with_self_num", "add_with_zero"):
            right = finish(total)
            emit(left, right, key, args)
            return right
        if _has_bracket(left):
            opened = _without_brackets(left)
            emit(left, opened, "remove_bracket", [])
            left = opened
            if node.type is T.ADD and first < 0 and second < 0:
                flipped = _node(T.SUBTRACT, _node(T.NEGATIVE, finish(-first)), finish(-second))
                emit(left, flipped, "pos_neg_arg", [_SIGNS[0]])
                left = flipped
                key, args = _sum_key(T.SUBTRACT, first, -second, total)
                right = finish(total)
                emit(left, right, key, args)
                return right
        right = finish(total)
        key, args = _sum_key(node.type, first, second, total)
        emit(left, right, key, args)
        return right

    if node.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) and len(values) >= 2:
        accumulated, total = children[0], values[0]
        for child, value in zip(children[1:], values[1:], strict=True):
            pair = _node(T.MULTIPLY, accumulated, child)
            product = total * value
            right = finish(product)
            if 0 in (total, value):
                emit(pair, right, "mul_with_zero", [_num(0)])
                accumulated, total = right, product
                continue
            if 1 in (total, value):
                if total == 1 and value == 1:
                    emit(pair, right, "mul_with_one", [_num(1)])
                    accumulated = right
                elif total == 1:
                    emit(pair, child, "mul_with_one", [_num(1)])
                    accumulated = child
                else:
                    emit(pair, accumulated, "mul_with_one", [_num(1)])
                total = product
                continue
            if -1 in (total, value):
                emit(pair, right, "mul_with_neg_one", [_num(-1)])
                accumulated, total = right, product
                continue
            if total < 0 and value < 0:
                positive = _node(T.MULTIPLY, finish(-total), finish(-value))
                emit(pair, positive, "mul_neg_neg", [_sign_rule(T.MULTIPLY)])
                left_key, left_args = (
                    ("mul_with_one", [_num(1)]) if 1 in (-total, -value) else ("mul", [])
                )
                emit(positive, right, left_key, left_args)
                accumulated, total = right, product
                continue
            emit(pair, right, "mul", [])
            accumulated, total = right, product
        return accumulated

    if node.type is T.DIVIDE and len(values) == 2:
        first, second = values
        if second == 0:
            return left
        total = first / second
        right = finish(total)
        if first == 0:
            emit(left, right, "div_zero", [_num(0)])
            return right
        if first < 0 and second < 0:
            positive = _node(T.DIVIDE, finish(-first), finish(-second))
            emit(left, positive, "div_neg_neg", [_sign_rule(T.DIVIDE)])
            left = positive
            if -first == -second:
                emit(left, right, "div_with_self", [_num(1)])
            elif (-first) % (-second) == 0:
                emit(left, right, "quotient", [])
            else:
                emit(left, right, "div_to_frac", [])
            return right
        if first == second:
            emit(left, right, "div_with_self", [_num(1)])
            return right
        if second == 1:
            emit(left, right, "div_with_one", [_num(1)])
            return right
        key, args = _div_key(first, second)
        emit(left, right, key, args)
        return right

    return left


def _algebraic_cell(value: CoreNode) -> CoreNode:
    """Операнд произведения: отрицательное число показывается в скобках."""
    number = _cell_value(value)
    if number < 0:
        return _node(T.BRACKET, value)
    return value


def _matrix_cells(node: CoreNode) -> list[list[CoreNode]]:
    return [list(row.children) for row in node.children]


def _matrix_node(node: CoreNode, cells: list[list[CoreNode]]) -> CoreNode:
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[_node(T.MATRIX_ROW, *row) for row in cells],
    )


def arithmetic_row_detail(
    before: CoreNode,
    after: CoreNode,
    key: str,
    args: list[CoreNode],
    finish: Callable[[Fraction], CoreNode],
) -> SolveResult | None:
    """Поэлементный разбор строки матрицы: раскрытие и арифметика по ячейкам."""
    cells = _matrix_cells(before)
    target_cells = _matrix_cells(after)
    changed = [
        row
        for row in range(len(cells))
        if any(
            not left.structural_eq(right)
            for left, right in zip(cells[row], target_cells[row], strict=True)
        )
    ]
    if len(changed) != 1:
        return None
    target = changed[0]
    try:
        if key in ("mul_row_add", "row_elim_add"):
            pivot = int(as_fraction(args[0])) - 1
            factor = Fraction(1) if key == "row_elim_add" else _cell_value(args[1])
            expanded = [
                _node(
                    T.ADD,
                    _node(
                        T.MULTIPLY,
                        _algebraic_cell(finish(factor)),
                        _algebraic_cell(cells[pivot][column]),
                    ),
                    _algebraic_cell(cells[target][column]),
                )
                for column in range(len(cells[target]))
            ]
        elif key == "mat_mul_row_element":
            factor = _cell_value(args[0])
            expanded = [
                _node(
                    T.MULTIPLY,
                    _algebraic_cell(finish(factor)),
                    _algebraic_cell(cell),
                )
                for cell in cells[target]
            ]
        elif key == "mat_divide_row_element":
            divisor = _cell_value(args[0])
            expanded = [
                _node(T.DIVIDE, _algebraic_cell(cell), _algebraic_cell(finish(divisor)))
                for cell in cells[target]
            ]
        else:
            return None
    except (SolveError, IndexError, ValueError):
        return None

    detail = SolveResult()
    current = [list(row) for row in cells]
    current[target] = list(expanded)
    expanded_node = _matrix_node(before, current)
    detail.add_group(key, Step(before, expanded_node, key, list(args)))
    previous = expanded_node

    for column in range(len(expanded)):

        def emit(
            left: CoreNode,
            right: CoreNode,
            step_key: str,
            step_args: list[CoreNode],
            column: int = column,
        ) -> None:
            nonlocal previous
            current[target][column] = right
            now = _matrix_node(before, current)
            detail.add_group(step_key, Step(previous, now, step_key, list(step_args)))
            previous = now

        current[target][column] = _simplify_cell(expanded[column], emit, finish)

    if not previous.structural_eq(after):
        # итоговая ячейка форматируется как в самой матрице (дробь — дробью)
        last = list(detail)[-1] if detail else None
        if last is not None:
            last.right = after
    detail.set_solution(after)
    return detail


def _det2_node(cells: list[int]) -> CoreNode:
    return _node(T.DETERMINANT2, *[_num(value) for value in cells])


def det3_detail(rows: list[list[int]], value: int) -> SolveResult:
    """Определитель 3×3 по строке: разложение, значения миноров, сумма."""
    cells = [cell for row in rows for cell in row]
    determinant = _node(T.DETERMINANT3, *[_num(cell) for cell in cells])
    line = max(range(3), key=lambda row: (sum(1 for cell in rows[row] if cell == 0), -row))
    terms: list[tuple[int, int, list[int], int]] = []
    for column in range(3):
        sign = 1 if (line + column) % 2 == 0 else -1
        minor_rows: list[list[int]] = [
            [rows[row][col] for col in range(3) if col != column] for row in range(3) if row != line
        ]
        minor_value = minor_rows[0][0] * minor_rows[1][1] - minor_rows[0][1] * minor_rows[1][0]
        terms.append(
            (
                rows[line][column],
                sign,
                [value for pair in minor_rows for value in pair],
                minor_value,
            )
        )

    def signed(node: CoreNode, sign: int) -> CoreNode:
        return _node(T.NEGATIVE, node) if sign < 0 else node

    nodes = [
        signed(_node(T.MULTIPLY, _num(element), _det2_node(minor)), sign)
        for element, sign, minor, _value in terms
    ]

    def rebuild(items: list[CoreNode]) -> CoreNode:
        return _chain([(1, item) for item in items])

    detail = SolveResult()
    detail.add_group(
        "det_evaluate",
        _plain(
            determinant,
            rebuild(nodes),
            "det_laplace_rule_row",
            [_num(line + 1)],
        ),
    )

    def emit(index: int, key: str, args: list[CoreNode], right: CoreNode) -> None:
        before = rebuild(nodes)
        nodes[index] = right
        detail.add_group(key, Step(before, rebuild(nodes), key, list(args)))

    for index, (element, sign, minor, minor_value) in enumerate(terms):
        if element == 0:
            emit(index, "mul_with_zero", [_num(0)], _num(0))
            continue
        if abs(element) == 1:
            value_node = _det2_node(minor)
            if element < 0:
                value_node = _node(T.NEGATIVE, value_node)
            emit(
                index,
                "mul_with_one" if element > 0 else "mul_with_neg_one",
                [_num(1) if element > 0 else _num(-1)],
                signed(value_node, sign),
            )
        if minor_value == 0:
            replacement: CoreNode = _num(0)
        elif minor_value < 0:
            replacement = _node(T.BRACKET, _node(T.NEGATIVE, _num(-minor_value)))
        else:
            replacement = _num(minor_value)
        if abs(element) == 1:
            term = replacement
            if element < 0:
                term = _node(T.NEGATIVE, term)
        else:
            term = _node(T.MULTIPLY, _num(element), replacement)
        emit(index, "det2_determinant_rule", [_det_rule()], signed(term, sign))

        def term_emit(
            left: CoreNode,
            right: CoreNode,
            key: str,
            args: list[CoreNode],
            index: int = index,
        ) -> None:
            emit(index, key, args, right)

        _simplify_cell(nodes[index], term_emit, _num)

    while len(nodes) > 1:
        first, second = nodes[0], nodes[1]
        left_value, right_value = _cell_value(first), _cell_value(second)
        total = left_value + right_value
        key, args = _sum_key(T.ADD, Fraction(left_value), Fraction(right_value), Fraction(total))
        before = rebuild(nodes)
        nodes = [_num(total), *nodes[2:]]
        detail.add_group(key, Step(before, rebuild(nodes), key, args))

    final = nodes[0] if nodes else _num(0)
    if not final.structural_eq(_num(value)):
        detail.add_group("calculate_short", Step(final, _num(value), "calculate_short"))
    detail.set_solution(_num(value))
    return detail


def det3_sarrus_detail(rows: list[list[int]], value: int) -> SolveResult:
    """Определитель 3×3 правилом Саррюса: расширенная сетка, шесть произведений, сумма."""
    cells = [cell for row in rows for cell in row]
    determinant = _node(T.DETERMINANT3, *[_num(cell) for cell in cells])
    extended = _node(
        T.DETERMINANT3_SARRUS,
        *[_num(cell) for cell in cells],
        *[_num(cell) for cell in (cells[0], cells[1], cells[3], cells[4], cells[6], cells[7])],
    )
    positive = ((0, 4, 8), (1, 5, 6), (2, 3, 7))
    negative = ((2, 4, 6), (0, 5, 7), (1, 3, 8))

    def product(indices: tuple[int, int, int]) -> CoreNode:
        return _node(T.MULTIPLY, *[_algebraic_cell(_num(cells[index])) for index in indices])

    def render(positives: list[CoreNode], negatives: list[CoreNode]) -> CoreNode:
        def chain(nodes: list[CoreNode]) -> CoreNode:
            items: list[tuple[int, CoreNode]] = []
            for node in nodes:
                try:
                    number = _cell_value(node)
                except SolveError:
                    items.append((1, node))
                    continue
                if number < 0:
                    items.append((-1, _num(-number)))
                else:
                    items.append((1, node))
            return _chain(items)

        return _node(T.SUBTRACT, chain(positives), chain(negatives))

    p_nodes = [product(indices) for indices in positive]
    n_nodes = [product(indices) for indices in negative]

    detail = SolveResult()
    detail.add_group("extend_grid", Step(determinant, extended, "det3_sarrus_extend"))
    detail.add_group(
        "det3_sarrus_rule_short",
        _plain(extended, render(p_nodes, n_nodes), "det3_sarrus_rule"),
    )

    def fold(nodes: list[CoreNode], position: int) -> None:
        def emit(
            left: CoreNode,
            right: CoreNode,
            key: str,
            args: list[CoreNode],
        ) -> None:
            before = render(p_nodes, n_nodes)
            nodes[position] = right
            after = render(p_nodes, n_nodes)
            if before.structural_eq(after):
                return
            detail.add_group(key, Step(before, after, key, list(args)))

        _simplify_cell(nodes[position], emit, _num)

    for position in range(len(p_nodes)):
        fold(p_nodes, position)
    for position in range(len(n_nodes)):
        fold(n_nodes, position)

    def total(nodes: list[CoreNode]) -> Fraction:
        result = Fraction(0)
        for node in nodes:
            result += _cell_value(node)
        return result

    def reduce(nodes: list[CoreNode]) -> Fraction:
        if len(nodes) <= 1:
            return _cell_value(nodes[0]) if nodes else Fraction(0)
        values = [_cell_value(node) for node in nodes]
        combined = sum(values, Fraction(0))
        before = render(p_nodes, n_nodes)
        nodes[:] = [_num(combined)]
        if combined == 0 and all(value == -values[0] for value in values[1:]):
            key, args = "sub_with_self_num", [_num(0)]
        elif 0 in values:
            key, args = "add_with_zero", [_num(0)]
        else:
            key, args = "sum", []
        detail.add_group(key, Step(before, render(p_nodes, n_nodes), key, args))
        return combined

    positive_total = reduce(p_nodes)
    negative_total = reduce(n_nodes)
    result = positive_total - negative_total
    if negative_total == 0:
        key, args = "add_with_zero", [_num(0)]
    elif positive_total == negative_total:
        key, args = "sub_with_self_remove_num", [_num(0)]
    else:
        key, args = "sum", []
    detail.add_group(
        key,
        Step(
            render(p_nodes, n_nodes),
            _num(result),
            key,
            args,
        ),
    )
    detail.set_solution(_num(value))
    return detail


def multiplication_detail(
    original: CoreNode, scaled: CoreNode, factor: int, key: str
) -> SolveResult:
    """Умножение уравнения: ``−2(x+y) = −2·3``, раскрытие скобки, произведение справа."""
    left, right = original.children
    product = _equation(
        _node(T.MULTIPLY, _num(factor), _node(T.BRACKET, left)),
        _node(T.MULTIPLY, _num(factor), right),
    )
    detail = SolveResult()
    detail.add_group(key, Step(original, product, key, [_num(factor)]))
    opened = _equation(scaled.children[0], product.children[1])
    detail.add_group("mul_bracket", Step(product, opened, "mul_bracket", [_num(factor)]))
    product_key = "mul_with_one" if abs(factor) == 1 else "mul"
    product_args = [_num(1)] if product_key == "mul_with_one" else []
    detail.add_group(product_key, Step(opened, scaled, product_key, product_args))
    detail.set_solution(scaled)
    return detail


def _reduces(numerator: int | Fraction, denominator: int | Fraction) -> bool:
    """Даёт ли дробь ``numerator/denominator`` отдельный шаг (деление на ±1 или сокращение)."""
    top, bottom = Fraction(numerator), Fraction(denominator)
    if bottom == 0 or top.denominator != 1 or bottom.denominator != 1:
        return False
    if abs(bottom.numerator) == 1:
        return True
    return gcd(abs(top.numerator), abs(bottom.numerator)) > 1


def two_solution_tail(
    result: SolveResult,
    before: CoreNode,
    originals: list[CoreNode],
    names: list[str],
    mappings: list[dict[sympy.Symbol, sympy.Expr]],
) -> None:
    """The two-pair check card: results, checks, verdict (the app's ``_pl`` rows)."""
    pairs: list[CoreNode] = []
    checks_list: list[CoreNode] = []
    simplified_list: list[CoreNode] = []
    details: list[SolveResult] = []
    for mapping in mappings:
        values = [from_sympy(mapping[sympy.Symbol(name)]) for name in names]
        pairs.append(
            _equation(
                _node(T.BRACKET, _node(T.LIST, *[_var(name) for name in names])),
                _node(T.BRACKET, _node(T.LIST, *values)),
            )
        )
        numbers = dict(zip(names, values, strict=True))
        checks = []
        for original in originals:
            filled = original
            for name, value in numbers.items():
                filled = _replace(filled, name, value)
            checks.append(filled)
        checked = _system(*checks)
        checks_list.append(checked)
        detail = check_detail(checks)
        simplified = detail.solution if detail.solution is not None else checked
        detail.set_solution(simplified)
        details.append(detail)
        simplified_list.append(simplified)
    found = _node(T.LIST, *pairs)
    result.add_group(
        "possible_sols",
        Step(before, found, "system_2x2_res_pl", [_node(T.LIST, *[_var(n) for n in names])]),
    )
    checked_system = _node(T.LIST, *checks_list)
    result.add_group(
        "solution_check_sols",
        Step(found, checked_system, "system_2x2_check_pl"),
    )
    detail = SolveResult()
    detail.add_group(
        "simplify_msg",
        *[
            Step(checked, simplified, "system_ver", subresult=nested)
            for checked, simplified, nested in zip(
                checks_list, simplified_list, details, strict=True
            )
        ],
    )
    verified = _node(T.LIST, *simplified_list)
    detail.set_solution(verified)
    result.add_group("simplify_msg", Step(checked_system, verified, "system_ver", subresult=detail))
    result.add_group("system_2x2_pairs_are_sol", Step(verified, found, "system_2x2_check_t_pl"))


def verification_tail(
    result: SolveResult,
    before: CoreNode,
    originals: list[CoreNode],
    names: list[str],
    values: list[CoreNode],
) -> None:
    """Хвост проверки 2×2: пара, подстановка, ``compare_solve_eq`` по строке, вердикт.

    Тот же хвост, что у карточек 2×2, но для системы, решённой общим путём
    (нелинейной или с дробными коэффициентами).
    """
    pair = _equation(
        _node(T.BRACKET, _node(T.LIST, *[_var(name) for name in names])),
        _node(T.BRACKET, _node(T.LIST, *values)),
    )
    result.add_group("possible_sol", Step(before, pair, "system_2x2_res", [pair]))
    numbers = dict(zip(names, values, strict=True))
    checks = []
    for original in originals:
        filled = original
        for name, value in numbers.items():
            filled = _replace(filled, name, value)
        checks.append(filled)
    checked = _system(*checks)
    result.add_group("solution_check_sol", Step(pair, checked, "system_2x2_check"))
    detail = check_detail(checks)
    done = detail.solution if detail.solution is not None else checked
    detail.set_solution(done)
    result.add_group("simplify_msg", Step(checked, done, "system_ver", subresult=detail))
    result.add_group(
        CoreRichText(type="system_2x2_pair_is_sol", args=[done]),
        Step(done, done, "system_2x2_check_t"),
    )


def _plain(left: CoreNode, right: CoreNode, key: str, args: list[CoreNode] | None = None) -> Step:
    """Шаг без «Подробнее»: пустой вложенный результат его и не показывает.

    Так учебные пакеты не прикрепляют к микрошагу свою карточку (у этой
    строки подробностей нет); пустой ``SolveResult`` в контракт не
    попадает.
    """
    step = Step(left, right, key, list(args or []))
    step.subresult = SolveResult()
    return step


def check_detail(checks: list[CoreNode]) -> SolveResult:
    """Проверка подстановкой: по строке на уравнение (``compare_solve_eq``)."""
    detail = SolveResult()
    current = list(checks)
    previous = _system(*current)
    for index, equation in enumerate(checks):
        if equation.type is not T.EQUALS or len(equation.children) != 2:
            continue
        sides = []
        for side in equation.children:
            try:
                sides.append(route(side, SolveContext(result=SolveResult())))
            except SolveError:
                sides.append(side)
        simplified = _equation(*sides)
        if simplified.structural_eq(current[index]):
            continue
        current[index] = simplified
        now = _system(*current)
        detail.add(Step(previous, now, "compare_solve_eq"))
        previous = now
    detail.set_solution(previous)
    return detail


def isolation_detail(
    original: CoreNode, isolated: CoreNode, other_name: str, coefficient: int
) -> SolveResult | None:
    """Перенос слагаемого: ``(x+y)-y = 3-y``, затем сокращение до ``x=…``."""
    if coefficient == 0 or original.type is not T.EQUALS or len(original.children) != 2:
        return None
    left, right = original.children
    term = _term(abs(coefficient), other_name)
    if coefficient > 0:
        moved_left = _node(T.SUBTRACT, left, term)
        moved_right = _node(T.SUBTRACT, right, term)
    else:
        moved_left = _node(T.ADD, left, term)
        moved_right = _node(T.ADD, right, term)
    middle = _equation(moved_left, moved_right)
    reduced = _equation(isolated.children[0], moved_right)
    detail = SolveResult()
    detail.add_group("rel_swap_right_var", Step(original, middle, "rel_swap_right_var"))
    detail.add_group("sub_with_self_remove_alg", Step(middle, reduced, "sub_with_self_remove_alg"))
    if not reduced.structural_eq(isolated):
        detail.add_group("add_with_zero", Step(reduced, isolated, "add_with_zero", [_num(0)]))
    detail.set_solution(isolated)
    return detail


def _det2_expansion(cells: tuple[int, int, int, int]) -> CoreNode:
    a, b, c, d = (_num(value) for value in cells)

    def bracketed(value: CoreNode) -> CoreNode:
        return _node(T.BRACKET, value) if _cell_value(value) < 0 else value

    return _node(
        T.SUBTRACT,
        _node(T.MULTIPLY, bracketed(a), bracketed(d)),
        _node(T.MULTIPLY, bracketed(b), bracketed(c)),
    )


def det2_detail(
    determinant: CoreNode,
    cells: tuple[int, int, int, int],
    value: int,
    left: CoreNode | None = None,
) -> SolveResult:
    """Определитель 2×2: формула, затем арифметика по слагаемым.

    ``left`` — левая часть уравнения (``det(A)``): тогда каждый шаг показан
    равенством, как в карточке обратной матрицы.
    """
    expanded = _det2_expansion(cells)

    def wrap(node: CoreNode) -> CoreNode:
        return _equation(left, node) if left is not None else node

    detail = SolveResult()
    detail.add_group(
        "det_evaluate",
        _plain(wrap(determinant), wrap(expanded), "det2_determinant_rule", [_det_rule()]),
    )

    def emit(before: CoreNode, after: CoreNode, key: str, args: list[CoreNode]) -> None:
        detail.add_group(key, Step(wrap(before), wrap(after), key, list(args)))

    final = _simplify_cell(expanded, emit, _num)
    if not final.structural_eq(_num(value)):
        detail.add_group(
            "calculate_short",
            Step(wrap(final), wrap(_num(value)), "calculate_short"),
        )
    detail.set_solution(wrap(_num(value)))
    return detail


def _terms_chain(terms: list[tuple[int, str]]) -> CoreNode:
    return _chain([(1 if k > 0 else -1, _term(k, name)) for k, name in terms])


def addition_detail(
    before: CoreNode,
    first: tuple[int, int, int],
    second: tuple[int, int, int],
    names: tuple[str, str],
    gone: int,
) -> SolveResult:
    """Сложение уравнений: раскрыть сумму, снять противоположные, свести подобные."""
    first_terms = [(k, name) for k, name in zip(first[:2], names, strict=True) if k]
    second_terms = [(k, name) for k, name in zip(second[:2], names, strict=True) if k]
    combined = _terms_chain(first_terms + second_terms)
    constant = first[2]
    if second[2] >= 0:
        right = _node(T.ADD, _num(constant), _num(second[2]))
        kind, right_value = T.ADD, second[2]
    else:
        right = _node(T.SUBTRACT, _num(constant), _num(-second[2]))
        kind, right_value = T.SUBTRACT, -second[2]
    added = _equation(combined, right)

    remaining = [(k, name) for k, name in first_terms + second_terms if name != names[gone]]
    reduced = _equation(_terms_chain(remaining) if remaining else _num(0), right)

    order: list[str] = []
    totals: dict[str, int] = {}
    for k, name in remaining:
        if name not in totals:
            order.append(name)
            totals[name] = 0
        totals[name] += k
    collected_terms = [(totals[name], name) for name in order if totals[name]]
    collected_left = _terms_chain(collected_terms) if collected_terms else _num(0)

    total = constant + second[2]
    key, args = _sum_key(kind, Fraction(constant), Fraction(right_value), Fraction(total))
    collected = _equation(collected_left, right)
    final = _equation(collected_left, _num(total))

    detail = SolveResult()
    detail.add_group("system_add_equations", _plain(before, added, "system_2x2_add_eqs"))
    detail.add_group("sub_with_self_remove_alg", Step(added, reduced, "sub_with_self_remove_alg"))
    if len(remaining) >= 2:
        detail.add_group("sum_suffix", Step(reduced, collected, "sum_suffix"))
        detail.add_group(key, Step(collected, final, key, args))
    else:
        detail.add_group(key, Step(reduced, final, key, args))
    detail.set_solution(final)
    return detail


class _Case:
    """One system: the original nodes, integer coefficients, the integer solution."""

    def __init__(self, node: CoreNode, names: tuple[str, str]) -> None:
        self.node, self.names = node, names
        self.originals = list(node.children)
        found = [_coefficients(e, names) for e in self.originals]
        if len(self.originals) != 2 or any(f is None for f in found):
            raise SolveError("not a 2x2 integer linear system")
        self.eqs: list[_Eq] = [f for f in found if f is not None]
        (a1, b1, c1), (a2, b2, c2) = self.eqs
        self.det = a1 * b2 - a2 * b1
        if self.det == 0:
            raise SolveError("degenerate system")
        x, y = Fraction(c1 * b2 - c2 * b1, self.det), Fraction(a1 * c2 - a2 * c1, self.det)
        self.integral = x.denominator == 1 and y.denominator == 1
        # verified with a fractional solution: 3x+2y=12, x-y=1 (all six cards)
        self.solution: tuple[Fraction | int, Fraction | int] = (
            (int(x), int(y)) if self.integral else (x, y)
        )
        self.standard_forms = [_equation(_linear(a, b, names), _num(c)) for a, b, c in self.eqs]
        self.is_standard = all(
            original.structural_eq(form)
            for original, form in zip(self.originals, self.standard_forms, strict=True)
        )

    # -- shared pieces ---------------------------------------------------

    def pair(self, values: tuple[CoreNode, CoreNode] | None = None) -> CoreNode:
        left = _node(T.BRACKET, _node(T.LIST, _var(self.names[0]), _var(self.names[1])))
        shown = values or (_num(self.solution[0]), _num(self.solution[1]))
        return _equation(left, _node(T.BRACKET, _node(T.LIST, *shown)))

    def answer(self) -> CoreNode:
        return _node(
            T.LIST,
            _equation(_var(self.names[0]), _num(self.solution[0])),
            _equation(_var(self.names[1]), _num(self.solution[1])),
        )

    def tail(self, result: SolveResult, before: CoreNode) -> None:
        """The ordered pair, its check, the simplified check and the verdict."""
        pair = self.pair()
        result.add_group("possible_sol", Step(before, pair, "system_2x2_res", [pair]))
        numbers = {n: _num(v) for n, v in zip(self.names, self.solution, strict=True)}
        checks = []
        for original in self.originals:
            filled = original
            for name, value in numbers.items():
                filled = _replace(filled, name, value)
            checks.append(filled)
        checked = _system(*checks)
        result.add_group("solution_check_sol", Step(pair, checked, "system_2x2_check"))
        detail = check_detail(checks)
        done = detail.solution if detail.solution is not None else checked
        detail.set_solution(done)
        result.add_group("simplify_msg", Step(checked, done, "system_ver", subresult=detail))
        result.add_group(
            CoreRichText(type="system_2x2_pair_is_sol", args=[done]),
            Step(done, done, "system_2x2_check_t"),
        )
        result.set_solution(self.answer())

    # -- the six methods ---------------------------------------------------

    def standardized(self, result: SolveResult) -> CoreNode:
        """Rewrite equations such as ``y = 2x`` as ``-2x + y = 0`` on a row of their own."""
        if self.is_standard:
            return self.node
        std = _system(*self.standard_forms)
        detail = SolveResult()
        for original, form in zip(self.originals, self.standard_forms, strict=True):
            if original.structural_eq(form):
                continue
            left, right = original.children
            intermediate = original
            if left.type is T.VARIABLE:
                # y = 2x → y − 2x = 0, then order the terms as -2x + y = 0
                intermediate = _equation(_node(T.SUBTRACT, left, right), _num(0))
            detail.add_group(
                "rel_move_left_var",
                Step(original, intermediate, "rel_move_left_var"),
            )
            if not intermediate.structural_eq(form):
                detail.add_group("var_order", Step(intermediate, form, "var_order"))
        detail.set_solution(std)
        result.add_group("simplify_msg", Step(self.node, std, "simplify", subresult=detail))
        return std

    def substitution(self) -> SolveResult | None:
        names = self.names
        result = SolveResult()
        start: CoreNode = self.node
        chosen: tuple[int, int] | None = None  # (equation, isolated variable index)
        for index, original in enumerate(self.originals):
            left, right = original.children
            for var_index, name in enumerate(names):
                if left.type is T.VARIABLE and left.value == name and not _contains(right, name):
                    chosen = (index, var_index)
        isolated: CoreNode
        if chosen is not None:
            index, var_index = chosen
            isolated = self.originals[index]
            expression = isolated.children[1]
            current = start
        else:
            picks = []
            for index, (a, b, _) in enumerate(self.eqs):
                # A coefficient of -1 works too: dividing by it flips the signs.
                units = [i for i, k in enumerate((a, b)) if abs(k) == 1]
                picks.append((index, units))
            exactly = [(i, u[0]) for i, u in picks if len(u) == 1]
            fallback = [(i, u[0]) for i, u in picks if u]
            candidates = exactly or fallback
            if not candidates:
                return None
            index, var_index = candidates[0]
            a, b, c = self.eqs[index]
            other = 1 - var_index
            # x = (c - k·other) / s with s = ±1, so the whole expression keeps s.
            sign = (a, b)[var_index]
            coefficient = (a, b)[other]
            items: list[tuple[int, CoreNode]] = []
            if c:
                items.append((1 if sign * c > 0 else -1, _num(abs(c))))
            if coefficient:
                term_sign = 1 if -sign * coefficient > 0 else -1
                items.append((term_sign, _term(coefficient, names[other])))
            expression = _chain(items) if items else _num(0)
            isolated = _equation(_var(names[var_index]), expression)
            replaced = [self.originals[0], self.originals[1]]
            replaced[index] = isolated
            current = _system(*replaced)
            other_name = names[1 - var_index]
            detail = isolation_detail(
                self.originals[index], isolated, other_name, (a, b)[1 - var_index]
            )
            if detail is None:
                detail = SolveResult()
                detail.add_group(
                    "rel_move_right_var",
                    Step(self.originals[index], isolated, "rel_move_right_var"),
                )
                detail.set_solution(isolated)
            result.add_group(
                "eq_solve_short",
                Step(start, current, "eq_linear", [_var(names[var_index])], subresult=detail),
            )
        name, other_name = names[var_index], names[1 - var_index]
        target = self.originals[1 - index]
        merged = _replace(target, name, expression)
        result.add_group(
            CoreRichText(type="substitute_value_of", args=[_var(name)]),
            Step(current, merged, "system_substitute_value", [_var(name), target]),
        )
        value = self.solution[1 - var_index]
        solved_one = _equation(_var(other_name), _num(value))
        nested = _solve_nested(merged, other_name, value)
        result.add_group(
            "eq_solve_short",
            Step(merged, solved_one, "eq_linear", [_var(other_name)], subresult=nested),
        )
        back = _replace(expression, other_name, _num(value))
        filled = _equation(_var(name), back)
        result.add_group(
            CoreRichText(type="substitute_value_of", args=[_var(other_name)]),
            Step(solved_one, filled, "system_substitute_value", [_var(other_name), isolated]),
        )
        final_value = self.solution[var_index]
        last = _equation(_var(name), _num(final_value))
        result.add_group(
            "eq_solve_short",
            Step(
                filled, last, "eq_linear", [_var(name)], subresult=_detail(back, _num(final_value))
            ),
        )
        self.tail(result, last)
        return result

    def _signed(self, coefficient: int, name: str) -> CoreNode:
        term = _term(coefficient, name)
        return term if coefficient > 0 else _node(T.NEGATIVE, term)

    def elimination(self) -> SolveResult | None:
        if not self.is_standard:
            # the standard form gets its own row, then the usual rows follow from it
            standard = SolveResult()
            std_node = self.standardized(standard)
            inner = _Case(std_node, self.names).elimination()
            if inner is None:
                return None
            standard.extend(inner)
            if inner.solution is not None:
                standard.set_solution(inner.solution)
            return standard
        names = self.names
        (a1, b1, c1), (a2, b2, c2) = self.eqs
        if b1 == -b2 and b1 != 0:
            gone, kept = 1, 0
        elif a1 == -a2 and a1 != 0:
            gone, kept = 0, 1
        else:
            return self._elimination_with_multiplication()
        coefficient = (a1 + a2, b1 + b2)[kept]
        total = c1 + c2
        if abs(coefficient) < 2:
            return None
        result = SolveResult()
        summed = _equation(_term(coefficient, names[kept]), _num(total))
        detail = addition_detail(self.node, self.eqs[0], self.eqs[1], names, gone)
        detail.set_solution(summed)
        result.add_group(
            "eliminate_variable", Step(self.node, summed, "system_2x2_sum", subresult=detail)
        )
        value = _exact(total, coefficient)
        divided = _equation(_var(names[kept]), _num(value))
        split = SolveResult()
        split.add_group(
            CoreRichText(type="eq_linear_div", args=[_num(coefficient)]),
            Step(summed, divided, "eq_linear_div", [_num(coefficient)]),
        )
        split.set_solution(divided)
        result.add_group(
            "divide_both_sides",
            Step(summed, divided, "eq_linear_div", [_num(coefficient)], subresult=split),
        )
        target = self.originals[1]
        merged = _replace(target, names[kept], _num(value))
        result.add_group(
            CoreRichText(type="substitute_value_of", args=[_var(names[kept])]),
            Step(divided, merged, "system_substitute_value", [_var(names[kept]), target]),
        )
        nested = _solve_nested(merged, names[gone], self.solution[gone])
        last = _equation(_var(names[gone]), _num(self.solution[gone]))
        result.add_group(
            "eq_solve_short",
            Step(merged, last, "eq_linear", [_var(names[gone])], subresult=nested),
        )
        self.tail(result, last)
        return result

    def _elimination_with_multiplication(self) -> SolveResult | None:
        """Multiply the second equation so one unknown cancels on addition (2x+3y=8, x+y=3)."""
        names = self.names
        (a1, b1, c1), (a2, b2, c2) = self.eqs
        pick = None
        # equal coefficients cancel once the second equation is multiplied by -1 (y = 2x, x + y = 6)
        for index, (p1, p2) in enumerate(((a1, a2), (b1, b2))):
            if p1 == p2 and p1 != 0:
                pick = (index, -1)
                break
        for index, (p1, p2) in enumerate(((a1, a2), (b1, b2))):
            if pick is None and p2 != 0 and p1 != 0 and p1 % p2 == 0 and p1 != p2:
                pick = (index, -p1 // p2)
                break
        if pick is None:
            return None
        gone, factor = pick
        negated = factor == -1 and (a1, b1)[gone] == (a2, b2)[gone]
        kept = 1 - gone
        scaled_eq = (a2 * factor, b2 * factor, c2 * factor)
        coefficient = (b1 + scaled_eq[1], a1 + scaled_eq[0])[gone]
        total = c1 + scaled_eq[2]
        if coefficient == 0:
            return None
        result = SolveResult()
        scaled = _equation(_linear(scaled_eq[0], scaled_eq[1], names), _num(scaled_eq[2]))
        after = _system(self.originals[0], scaled)
        multiply_key = "eq_mul_direct_one" if factor == -1 else "eq_mul_direct_eq"
        detail = multiplication_detail(self.originals[1], scaled, factor, multiply_key)
        result.add_group(
            "multiply_both_sides",
            Step(self.node, after, multiply_key, [_num(factor)], subresult=detail),
        )
        value = _exact(total, coefficient)
        found = _equation(_var(names[kept]), _num(value))
        summed = _equation(self._signed(coefficient, names[kept]), _num(total))
        summing = addition_detail(after, self.eqs[0], scaled_eq, names, gone)
        summing.set_solution(summed)
        result.add_group(
            "eliminate_variable", Step(after, summed, "system_2x2_sum", subresult=summing)
        )
        if coefficient != 1:
            split = SolveResult()
            split.add_group(
                CoreRichText(type="eq_linear_div", args=[_num(coefficient)]),
                Step(summed, found, "eq_linear_div", [_num(coefficient)]),
            )
            split.set_solution(found)
            result.add_group(
                "divide_both_sides",
                Step(summed, found, "eq_linear_div", [_num(coefficient)], subresult=split),
            )
        target = self.originals[0 if negated else 1]
        merged = _replace(target, names[kept], _num(value))
        result.add_group(
            CoreRichText(type="substitute_value_of", args=[_var(names[kept])]),
            Step(found, merged, "system_substitute_value", [_var(names[kept]), target]),
        )
        nested = _solve_nested(merged, names[gone], self.solution[gone])
        last = _equation(_var(names[gone]), _num(self.solution[gone]))
        result.add_group(
            "eq_solve_short",
            Step(merged, last, "eq_linear", [_var(names[gone])], subresult=nested),
        )
        self.tail(result, last)
        return result

    def _isolated(self, index: int, name: str) -> bool:
        """The original equation already reads ``name = expression`` (``y = 2x``)."""
        left, right = self.originals[index].children
        return left.type is T.VARIABLE and left.value == name and not _contains(right, name)

    def comparison(self) -> SolveResult | None:
        names = self.names
        pick = None
        for index in (0, 1):
            if all(abs(eq[index]) == 1 for eq in self.eqs):
                pick = index
                break
        if pick is None:  # one equation has the unit coefficient, the other a positive k > 1
            for index in (0, 1):
                column = sorted(abs(eq[index]) for eq in self.eqs)
                if column[0] == 1 and column[1] > 1 and all(eq[index] > 0 for eq in self.eqs):
                    pick = index
                    break
        if pick is None:  # the unit coefficient may also be -1: the sign is flipped on the way
            for index in (0, 1):
                column = sorted(abs(eq[index]) for eq in self.eqs)
                if column[0] == 1 and column[1] > 1:
                    pick = index
                    break
        if pick is None:
            return None
        if not self.is_standard and not all(
            original.structural_eq(form) or self._isolated(index, names[pick])
            for index, (original, form) in enumerate(
                zip(self.originals, self.standard_forms, strict=True)
            )
        ):
            return None
        other = 1 - pick
        result = SolveResult()
        forms: list[CoreNode] = []
        flips: list[bool] = []
        divides: list[int] = []
        for eq in self.eqs:
            sign = eq[pick]
            c, w = Fraction(eq[2], abs(sign)), Fraction(eq[other], abs(sign))
            items: list[tuple[int, CoreNode]] = []
            if c:
                items.append((1 if c * sign > 0 else -1, self._plain(abs(c))))
            if w:
                items.append(
                    (1 if -w * sign > 0 else -1, self._rational_term(abs(w), names[other]))
                )
            forms.append(_chain(items) if items else _num(0))
            flips.append(sign < 0)
            divides.append(abs(sign) if abs(sign) > 1 else 1)
        # page 1/2: move the other unknown right, one equation per page
        shown: list[CoreNode] = list(self.originals)
        pages = []
        previous: CoreNode = self.node
        for index, eq in enumerate(self.eqs):
            left = _var(names[pick])
            if eq[pick] < 0:
                left = _node(T.NEGATIVE, left)
                right = self._moved_right(eq, pick, other, negate=False)
            elif divides[index] > 1:
                left = _term(eq[pick], names[pick])
                right = self._moved_right(eq, pick, other, negate=False)
            else:
                right = forms[index]
            if self._isolated(index, names[pick]):  # already solved for it: no row of its own
                shown[index] = self.originals[index]
                continue
            shown[index] = _equation(left, right)
            now = _system(*shown)
            detail = isolation_detail(
                self.originals[index], shown[index], names[other], self.eqs[index][other]
            )
            if detail is None:
                detail = SolveResult()
                detail.add_group(
                    "rel_move_right_var",
                    Step(self.originals[index], shown[index], "rel_move_right_var"),
                )
                detail.set_solution(shown[index])
            pages.append(Step(previous, now, "rel_move_right_var", subresult=detail))
            previous = now
        result.add_group("rel_move_right_vars_msg", *pages)
        for index, flip in enumerate(flips):
            if not flip:
                continue
            from .systems import _linear_form

            before_equation = shown[index]
            fixed = _equation(_var(names[pick]), forms[index])
            shown[index] = fixed
            now = _system(*shown)
            detail = SolveResult()
            left, right = before_equation.children
            product = _equation(
                _node(T.MULTIPLY, _num(-1), _node(T.BRACKET, left)),
                _node(T.MULTIPLY, _num(-1), _node(T.BRACKET, right)),
            )
            detail.add_group(
                "eq_mul_direct_one",
                Step(before_equation, product, "eq_mul_direct_one", [_num(-1)]),
            )
            current_left = product.children[0]
            current_right = product.children[1]
            if left.type is T.NEGATIVE and left.children[0].type is T.VARIABLE:
                inner = left.children[0]
                positive = _equation(_node(T.MULTIPLY, _num(1), inner), current_right)
                detail.add_group(
                    "mul_neg_neg",
                    Step(
                        _equation(current_left, current_right),
                        positive,
                        "mul_neg_neg",
                        [_sign_rule(T.MULTIPLY)],
                    ),
                )
                simplified = _equation(inner, current_right)
                detail.add_group(
                    "mul_with_one",
                    Step(positive, simplified, "mul_with_one", [_num(1)]),
                )
                current_left = inner
            coefficients, constant = _linear_form(right, {names[pick]: 0, names[other]: 1})
            coefficient = coefficients[1]
            target = forms[index]
            if coefficient == -1:
                flipped_constant = -constant
                variable = _var(names[other])
                flipped_items: list[tuple[int, CoreNode]] = []
                if flipped_constant:
                    flipped_items.append(
                        (1 if flipped_constant > 0 else -1, _num(abs(flipped_constant)))
                    )
                flipped_items.append(
                    (1, _node(T.MULTIPLY, _num(-1), _node(T.BRACKET, _node(T.NEGATIVE, variable))))
                )
                opened = _node(T.EQUALS, current_left, _chain(flipped_items))
                detail.add_group(
                    "mul_bracket",
                    Step(
                        _equation(current_left, current_right),
                        opened,
                        "mul_bracket",
                        [_num(-1)],
                    ),
                )
                positive_term = _node(T.MULTIPLY, _num(1), variable)
                flipped_items[-1] = (1, positive_term)
                distributed = _node(T.EQUALS, current_left, _chain(flipped_items))
                detail.add_group(
                    "mul_neg_neg",
                    Step(opened, distributed, "mul_neg_neg", [_sign_rule(T.MULTIPLY)]),
                )
                final = _equation(current_left, target)
                detail.add_group(
                    "mul_with_one",
                    Step(distributed, final, "mul_with_one", [_num(1)]),
                )
            else:
                detail.add_group(
                    "mul_bracket",
                    Step(
                        _equation(current_left, current_right),
                        _equation(current_left, target),
                        "mul_bracket",
                        [_num(-1)],
                    ),
                )
            detail.set_solution(now)
            result.add_group(
                "multiply_both_sides",
                Step(previous, now, "eq_mul_direct_one", [_num(-1)], subresult=detail),
            )
            previous = now
        for index, divisor in enumerate(divides):
            if divisor == 1:
                continue
            shown[index] = _equation(_var(names[pick]), forms[index])
            now = _system(*shown)
            detail = SolveResult()
            detail.add_group(
                CoreRichText(type="eq_linear_div", args=[_num(divisor)]),
                Step(previous, now, "eq_linear_div", [_num(divisor)]),
            )
            detail.set_solution(now)
            result.add_group(
                "divide_both_sides",
                Step(previous, now, "eq_linear_div", [_num(divisor)], subresult=detail),
            )
            previous = now
        equal = _equation(forms[0], forms[1])
        result.add_group(
            "set_sides_equal",
            Step(
                previous,
                equal,
                "system_2x2_equalise",
                [_var(names[pick]), _var(names[other]), forms[0], forms[1]],
            ),
        )
        value = self.solution[other]
        solved_one = _equation(_var(names[other]), _num(value))
        nested = _solve_nested(equal, names[other], value)
        result.add_group(
            "eq_solve_short",
            Step(equal, solved_one, "eq_linear", [_var(names[other])], subresult=nested),
        )
        unit = next((i for i, d in enumerate(divides) if d == 1), 1)
        target = shown[unit]
        back = _replace(forms[unit], names[other], _num(value))
        filled = _equation(_var(names[pick]), back)
        result.add_group(
            CoreRichText(type="substitute_value_of", args=[_var(names[other])]),
            Step(solved_one, filled, "system_substitute_value", [_var(names[other]), target]),
        )
        final_value = self.solution[pick]
        last = _equation(_var(names[pick]), _num(final_value))
        result.add_group(
            "eq_solve_short",
            Step(
                filled,
                last,
                "eq_linear",
                [_var(names[pick])],
                subresult=_detail(back, _num(final_value)),
            ),
        )
        self.tail(result, last)
        return result

    @staticmethod
    def _plain(value: Fraction) -> CoreNode:
        return _num(value) if value.denominator == 1 else _fraction_node(value)

    @staticmethod
    def _rational_term(value: Fraction, name: str) -> CoreNode:
        """``|v| x`` for a rational ``v``: ``(3/2) y`` when it is not an integer."""
        if value.denominator == 1:
            return _term(int(value), name)
        return _node(T.MULTIPLY_IMPLICIT, _fraction_node(value), _var(name))

    def _moved_right(self, eq: _Eq, pick: int, other: int, negate: bool) -> CoreNode:
        """``c - w`` written for the side opposite a negative unknown (``1 - x``)."""
        c, w = eq[2], eq[other]
        items: list[tuple[int, CoreNode]] = []
        if c:
            items.append((1 if c > 0 else -1, _num(abs(c))))
        if w:
            items.append((1 if -w > 0 else -1, _term(w, self.names[other])))
        return _chain(items)

    def matrix_cell(self, value: int | Fraction) -> CoreNode:
        fraction = Fraction(value)
        return _num(fraction) if fraction.denominator == 1 else _fraction_node(fraction)

    def augmented(self, rows: list[list[int]] | list[list[Fraction]]) -> CoreNode:
        return _node(
            T.MATRIX_SPLIT_LAST,
            *[_node(T.MATRIX_ROW, *[self.matrix_cell(v) for v in row]) for row in rows],
        )

    def _row_detail(
        self, before: CoreNode, after: CoreNode, key: str, args: list[CoreNode]
    ) -> SolveResult:
        """Вложенный разбор строки: та же операция, но поэлементно."""
        detail = arithmetic_row_detail(before, after, key, args, self.matrix_cell)
        if detail is not None:
            return detail
        detail = SolveResult()
        detail.add_group("simplify_row", Step(before, after, key, list(args)))
        detail.set_solution(after)
        return detail

    def gauss(self) -> SolveResult | None:
        (a1, b1, c1), (a2, b2, c2) = self.eqs
        rows = [[a1, b1, c1], [a2, b2, c2]]
        names = self.names
        result = SolveResult()
        start = self.standardized(result)
        matrix = self.augmented(rows)
        result.add_group(
            "system_convert_eq_to_mat", Step(start, matrix, "system_write_coeffs_to_mat")
        )
        if a1 == a2 and a1 != 0:  # equal first column: subtract row 1 from row 2
            other = 0
            rows[1] = [y - x for x, y in zip(rows[0], rows[1], strict=True)]
            move = Step(matrix, self.augmented(rows), "row_elim_out", [_num(1), _num(-1), _num(2)])
        elif b1 == -b2 and b1 != 0:
            other = 0
            rows[1] = [x + y for x, y in zip(rows[0], rows[1], strict=True)]
            move = Step(matrix, self.augmented(rows), "row_elim", [_num(1), _num(2)])
        elif b1 == b2 and b1 != 0:  # equal columns: subtract row 1 from row 2 (y = 2x, x + y = 6)
            other = 0
            rows[1] = [y - x for x, y in zip(rows[0], rows[1], strict=True)]
            move = Step(matrix, self.augmented(rows), "row_elim_out", [_num(1), _num(-1), _num(2)])
        elif a1 == 1 and a2 != 0:
            other = 1
            factor = -a2
            rows[1] = [y + factor * x for x, y in zip(rows[0], rows[1], strict=True)]
            move = Step(
                matrix, self.augmented(rows), "row_elim_out", [_num(1), _num(factor), _num(2)]
            )
        elif a2 == 1 and a1 != 0:
            return self._gauss_unit_second_row() or self._gauss_generic()
        else:
            return self._gauss_generic()
        after = self.augmented(rows)
        move.right = after
        move.subresult = self._row_detail(matrix, after, _ROW_DETAIL[move.key], move.args)
        result.add_group("simplify_row", move)
        pivot = rows[1][other]
        if pivot == 0 or any(v % pivot for v in rows[1]):
            # The verified pattern needs integer rows; fractions are the general case.
            return self._gauss_generic()
        if pivot != 1:
            rows[1] = [v // pivot for v in rows[1]]
            divided = self.augmented(rows)
            result.add_group(
                "mat_divide_row_simple",
                Step(
                    after,
                    divided,
                    "mat_divide_row",
                    [_num(pivot)],
                    subresult=self._row_detail(
                        after, divided, "mat_divide_row_element", [_num(pivot)]
                    ),
                ),
            )
            after = divided
        c = rows[0][other]
        if c:
            rows[0] = [x - c * y for x, y in zip(rows[0], rows[1], strict=True)]
            final = self.augmented(rows)
            args = [_num(2), _num(-c), _num(1)]
            result.add_group(
                "simplify_row",
                Step(
                    after,
                    final,
                    "row_elim_out",
                    args,
                    subresult=self._row_detail(after, final, "mul_row_add", args),
                ),
            )
            after = final
        equations = []
        for row in rows:
            index = 0 if row[0] == 1 and row[1] == 0 else 1
            equations.append(_equation(_var(names[index]), _num(row[2])))
        listed = _system(*equations)
        result.add_group(
            "system_convert_mat_to_eq_short", Step(after, listed, "system_convert_mat_to_eq")
        )
        self.tail(result, listed)
        return result

    def _gauss_unit_second_row(self) -> SolveResult | None:
        """Gauss-Jordan when the second row has the unit pivot (2x+3y=8, x+y=3; 3x+2y=12, x-y=1)."""
        (a1, b1, c1), (a2, b2, c2) = self.eqs
        names = self.names
        pivot = b1 - a1 * b2
        if pivot == 0:
            return None
        result = SolveResult()
        start = self.standardized(result)
        rows: list[list[Fraction]] = [
            [Fraction(v) for v in (a1, b1, c1)],
            [Fraction(v) for v in (a2, b2, c2)],
        ]
        matrix = self.augmented(rows)
        result.add_group(
            "system_convert_eq_to_mat", Step(start, matrix, "system_write_coeffs_to_mat")
        )
        rows[0] = [x - a1 * y for x, y in zip(rows[0], rows[1], strict=True)]
        first = self.augmented(rows)
        args = [_num(2), _num(-a1), _num(1)]
        result.add_group(
            "simplify_row",
            Step(
                matrix,
                first,
                "row_elim_out",
                args,
                subresult=self._row_detail(matrix, first, "mul_row_add", args),
            ),
        )
        if pivot != 1:
            rows[0] = [v / pivot for v in rows[0]]
            divided = self.augmented(rows)
            result.add_group(
                "mat_divide_row_simple",
                Step(
                    first,
                    divided,
                    "mat_divide_row",
                    [_num(pivot)],
                    subresult=self._row_detail(
                        first, divided, "mat_divide_row_element", [_num(pivot)]
                    ),
                ),
            )
            first = divided
        rows[1] = [y - b2 * x for x, y in zip(rows[0], rows[1], strict=True)]
        second = self.augmented(rows)
        args = [_num(1), _num(-b2), _num(2)]
        result.add_group(
            "simplify_row",
            Step(
                first,
                second,
                "row_elim_out",
                args,
                subresult=self._row_detail(first, second, "mul_row_add", args),
            ),
        )
        listed = _system(
            _equation(_var(names[1]), self.matrix_cell(rows[0][2])),
            _equation(_var(names[0]), self.matrix_cell(rows[1][2])),
        )
        result.add_group(
            "system_convert_mat_to_eq_short", Step(second, listed, "system_convert_mat_to_eq")
        )
        self.tail(result, listed)
        return result

    def _gauss_divide(
        self,
        result: SolveResult,
        previous: CoreNode,
        rows: list[list[Fraction]],
        index: int,
        divisor: Fraction,
    ) -> CoreNode:
        """Divide a pivot row by its leading coefficient (fractions are fine)."""
        divided = self.augmented(rows)
        args = [self.matrix_cell(divisor)]
        result.add_group(
            "mat_divide_row_simple",
            Step(
                previous,
                divided,
                "mat_divide_row",
                args,
                subresult=self._row_detail(previous, divided, "mat_divide_row_element", args),
            ),
        )
        return divided

    def _gauss_eliminate(
        self,
        result: SolveResult,
        previous: CoreNode,
        rows: list[list[Fraction]],
        column: int,
        pivot_row: int,
        target: int,
    ) -> CoreNode:
        """Add a multiple of the pivot row to another row so ``column`` becomes 0."""
        factor = -rows[target][column] / rows[pivot_row][column]
        rows[target] = [
            value + factor * pivot
            for value, pivot in zip(rows[target], rows[pivot_row], strict=True)
        ]
        eliminated = self.augmented(rows)
        if factor == 1:
            key, args = "row_elim", [_num(pivot_row + 1), _num(target + 1)]
        else:
            key, args = (
                "row_elim_out",
                [_num(pivot_row + 1), self.matrix_cell(factor), _num(target + 1)],
            )
        result.add_group(
            "simplify_row",
            Step(
                previous,
                eliminated,
                key,
                args,
                subresult=self._row_detail(previous, eliminated, _ROW_DETAIL[key], args),
            ),
        )
        return eliminated

    def _gauss_generic(self) -> SolveResult | None:
        """Gauss-Jordan for every nonsingular integer 2x2 outside the verified patterns.

        The branches of :meth:`gauss` cover the hand-checked systems; any other
        ``det A != 0`` system still gets the same stages: write ``(A|b)``, reduce it to
        the identity with row operations, read the equations back. Fractions in the
        intermediate rows are allowed.
        """
        names = self.names
        result = SolveResult()
        start = self.standardized(result)
        rows: list[list[Fraction]] = [
            [Fraction(value) for value in self.eqs[0]],
            [Fraction(value) for value in self.eqs[1]],
        ]
        previous = self.augmented(rows)
        result.add_group(
            "system_convert_eq_to_mat", Step(start, previous, "system_write_coeffs_to_mat")
        )
        if rows[0][0] == 0:  # the first row has no x term: put the other one first
            rows[0], rows[1] = rows[1], rows[0]
            swapped = self.augmented(rows)
            result.add_group(
                "matrix_inv_reorder",
                Step(previous, swapped, "matrix_inv_swap_row", [_num(1), _num(2)]),
            )
            previous = swapped
        if rows[0][0] != 1:
            divisor = rows[0][0]
            rows[0] = [value / divisor for value in rows[0]]
            previous = self._gauss_divide(result, previous, rows, 0, divisor)
        if rows[1][0] != 0:
            previous = self._gauss_eliminate(result, previous, rows, 0, 0, 1)
        if rows[1][1] == 0:
            return None
        if rows[1][1] != 1:
            divisor = rows[1][1]
            rows[1] = [value / divisor for value in rows[1]]
            previous = self._gauss_divide(result, previous, rows, 1, divisor)
        if rows[0][1] != 0:
            previous = self._gauss_eliminate(result, previous, rows, 1, 1, 0)
        listed = _system(
            _equation(_var(names[0]), self.matrix_cell(rows[0][2])),
            _equation(_var(names[1]), self.matrix_cell(rows[1][2])),
        )
        result.add_group(
            "system_convert_mat_to_eq_short", Step(previous, listed, "system_convert_mat_to_eq")
        )
        self.tail(result, listed)
        return result

    def determinant(self, a: int, b: int, c: int, d: int) -> CoreNode:
        return _node(T.DETERMINANT2, *[_num(v) for v in (a, b, c, d)])

    def cramer(self) -> SolveResult | None:
        (a1, b1, c1), (a2, b2, c2) = self.eqs
        names = self.names
        result = SolveResult()
        start = self.standardized(result)
        letters = [_var("D"), _var("D_1"), _var("D_2")]
        dets = [(a1, b1, a2, b2), (c1, b1, c2, b2), (a1, c1, a2, c2)]
        listing = _node(
            T.LIST,
            *[_equation(sym, self.determinant(*d)) for sym, d in zip(letters, dets, strict=True)],
        )
        result.add_group("system_list_det", Step(start, listing, "system_2x2_cramer_rule"))
        values = [d[0] * d[3] - d[1] * d[2] for d in dets]
        pages = []
        current = listing
        for index, (_letter, d, value) in enumerate(zip(letters, dets, values, strict=True)):
            parts = list(listing.children)
            for j in range(index + 1):
                parts[j] = _equation(letters[j], _num(values[j]))
            nxt = _node(T.LIST, *parts)
            det_detail = det2_detail(self.determinant(*d), d, value)
            pages.append(Step(current, nxt, "det_evaluate", subresult=det_detail))
            current = nxt
        result.add_group("evaluate", *pages)
        found = _node(
            T.LIST,
            _equation(_var(names[0]), _num(self.solution[0])),
            _equation(_var(names[1]), _num(self.solution[1])),
        )
        formulas = _node(
            T.LIST,
            _equation(_var(names[0]), _node(T.FRACTION, letters[1], letters[0])),
            _equation(_var(names[1]), _node(T.FRACTION, letters[2], letters[0])),
        )
        rule = SolveResult()
        target = _var(f"{names[0]}, {names[1]}")
        condition = _node(T.NOT_EQUALS, letters[0], _num(0))
        applied = _node(
            T.LIST,
            *[
                _equation(_var(name), _node(T.FRACTION, _num(values[index + 1]), _num(values[0])))
                for index, name in enumerate(names)
            ],
        )
        reducible = [index for index in range(len(names)) if _reduces(values[index + 1], values[0])]
        if reducible:
            rule.add_group(
                "system_2x2_cramer_apply_rule",
                Step(
                    current,
                    applied,
                    "system_2x2_cramer_apply_rule",
                    [condition, target, formulas],
                ),
            )
            previous, parts = applied, list(applied.children)
            calculated = []
            for index in reducible:
                parts = list(parts)
                parts[index] = _equation(_var(names[index]), _num(self.solution[index]))
                now = _node(T.LIST, *parts)
                if abs(values[0]) == 1:
                    calculated.append(Step(previous, now, "div_with_one", [_num(values[0])]))
                else:
                    calculated.append(Step(previous, now, "calculate_direct"))
                previous = now
            rule.add_group("calculate_direct", *calculated)
        rule.set_solution(found)
        result.add_group(
            CoreRichText(type="find_arg", args=[_var(f"{names[0]}, {names[1]}")]),
            Step(
                current,
                found,
                "system_2x2_cramer_apply_rule",
                [condition, _var(f"{names[0]}, {names[1]}"), formulas],
                subresult=rule if reducible else None,
            ),
        )
        self.tail(result, found)
        return result

    def inverse(self) -> SolveResult | None:
        (a1, b1, c1), (a2, b2, c2) = self.eqs
        names = self.names
        result = SolveResult()
        start = self.standardized(result)

        def matrix(rows: list[list[CoreNode]]) -> CoreNode:
            return _node(T.MATRIX, *[_node(T.MATRIX_ROW, *r) for r in rows])

        coefficients = matrix([[_num(a1), _num(b1)], [_num(a2), _num(b2)]])
        unknowns = matrix([[_var(names[0])], [_var(names[1])]])
        constants = matrix([[_num(c1)], [_num(c2)]])
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
        det = self.det
        inverse_rows = [
            [self.matrix_cell(Fraction(b2, det)), self.matrix_cell(Fraction(-b1, det))],
            [self.matrix_cell(Fraction(-a2, det)), self.matrix_cell(Fraction(a1, det))],
        ]
        inverse = _equation(_var("A^-1"), matrix(inverse_rows))
        import sympy

        from .matrices import _det_node

        det_left = _det_node(sympy.Matrix([[a1, b1], [a2, b2]]))
        determinant = self.determinant(a1, b1, a2, b2)
        det_detail = det2_detail(determinant, (a1, b1, a2, b2), det, left=det_left)
        find = SolveResult()
        find.add_group(
            "matrix_det_rewrite",
            Step(identified, _equation(det_left, determinant), "matrix_det_rewrite"),
        )
        find.extend(det_detail)
        det_value = (
            det_detail.solution
            if det_detail.solution is not None
            else _equation(det_left, _num(det))
        )
        expansion = _det2_expansion((a1, b1, a2, b2))
        adjugate = matrix([[_num(a1), _num(-b1)], [_num(-a2), _num(b2)]])
        symbolic_rule = _equation(
            _var("A^-1"),
            _node(
                T.MULTIPLY,
                _node(
                    T.FRACTION,
                    _num(1),
                    _node(
                        T.SUBTRACT,
                        _node(T.MULTIPLY, _var("a"), _var("d")),
                        _node(T.MULTIPLY, _var("b"), _var("c")),
                    ),
                ),
                matrix(
                    [
                        [_var("d"), _node(T.NEGATIVE, _var("b"))],
                        [_node(T.NEGATIVE, _var("c")), _var("a")],
                    ]
                ),
            ),
        )
        formula = _equation(
            _var("A^-1"), _node(T.MULTIPLY, _node(T.FRACTION, _num(1), expansion), adjugate)
        )
        find.add_group(
            "matrix_inv_formula_apply",
            Step(
                det_value,
                formula,
                "matrix_inv_formula_apply",
                [_num(0), _num(a1), _num(b1), _num(a2), _num(b2), symbolic_rule],
            ),
        )

        def signed_number(value: int) -> CoreNode:
            cell = self.matrix_cell(abs(value))
            return _node(T.NEGATIVE, cell) if value < 0 else cell

        all_factors = (a1, b2, b1, a2)
        if -1 in all_factors:
            first_key, second_key = "mul_with_neg_one", "mul_with_neg_one"
        elif 1 in all_factors:
            first_key, second_key = "mul_with_one", "mul_with_one"
        else:
            first_key, second_key = "mul", "mul"
        first_args = (
            [_num(-1)]
            if first_key == "mul_with_neg_one"
            else [_num(1)]
            if first_key == "mul_with_one"
            else []
        )
        first_value = signed_number(a1 * b2)
        after_first = _equation(
            _var("A^-1"),
            _node(
                T.MULTIPLY,
                _node(
                    T.FRACTION,
                    _num(1),
                    _node(
                        T.SUBTRACT,
                        first_value,
                        _node(T.MULTIPLY, _num(b1), _num(a2)),
                    ),
                ),
                adjugate,
            ),
        )
        find.add_group(first_key, Step(formula, after_first, first_key, first_args))
        second_args = (
            [_num(-1)]
            if second_key == "mul_with_neg_one"
            else [_num(1)]
            if second_key == "mul_with_one"
            else []
        )
        second_value = signed_number(b1 * a2)
        after_second = _equation(
            _var("A^-1"),
            _node(
                T.MULTIPLY,
                _node(
                    T.FRACTION,
                    _num(1),
                    _node(T.SUBTRACT, first_value, second_value),
                ),
                adjugate,
            ),
        )
        find.add_group(second_key, Step(after_first, after_second, second_key, second_args))
        coefficient = self.matrix_cell(Fraction(1, det))
        scaled_formula = _equation(_var("A^-1"), _node(T.MULTIPLY, coefficient, adjugate))
        find.add_group("calculate_direct", Step(after_second, scaled_formula, "calculate_direct"))
        multiply_key = "matrix_mul_neg_one" if det == -1 else "matrix_mul_by"
        find.add_group(
            multiply_key,
            Step(scaled_formula, inverse, multiply_key, [coefficient]),
        )
        find.set_solution(inverse)
        result.add_group(
            "matrix_inv_find_smpl",
            Step(identified, inverse, "system_2x2_inv_matrix_find_inv", subresult=find),
        )
        product = _equation(unknowns, _node(T.MULTIPLY, matrix(inverse_rows), constants))
        result.add_group(
            "system_2x2_inv_matrix_sub_eq_smpl",
            Step(
                inverse,
                product,
                "system_2x2_inv_matrix_sub_eq",
                [inverse.children[1], unknowns, constants, _equation(letters[1], _var("A^-1 B"))],
            ),
        )
        solved = _equation(unknowns, matrix([[_num(self.solution[0])], [_num(self.solution[1])]]))
        detail = _product_detail((c1, c2), inverse_rows, self.solution)
        result.add_group("calculate_direct", Step(product, solved, "matrix_mul", subresult=detail))
        answer = self.answer()
        result.add_group("set_equations", Step(solved, answer, "matrix_eq_set_elements_equal"))
        self.tail(result, answer)
        return result


def _product_detail(
    constants: tuple[int, int],
    inverse_rows: list[list[CoreNode]],
    solution: tuple[Fraction | int, Fraction | int],
) -> SolveResult:
    """The «Подробнее» screen of «Умножьте матрицы» in the inverse-matrix card.

    The row ``matrix_mul`` gets a derivation of its own
    (case ``sys_lin``, «Решите с помощью обратной матрицы»: «Умножьте элементы
    строки 1 первой матрицы на элементы столбца 1 второй матрицы», «Вычислить»).
    Two rows: the row·column products, then their sums — so the student sees where
    the ordered pair comes from instead of a jump.
    """

    def matrix(rows: list[list[CoreNode]]) -> CoreNode:
        return _node(T.MATRIX, *[_node(T.MATRIX_ROW, *row) for row in rows])

    column = [[_num(value)] for value in constants]
    product = _node(T.MULTIPLY, matrix(inverse_rows), matrix(column))
    sums = [
        [_node(T.ADD, *[_node(T.MULTIPLY, inverse_rows[row][k], column[k][0]) for k in range(2)])]
        for row in range(2)
    ]
    detail = SolveResult()
    detail.add_group(
        "matrix_mul_row_col_simple",
        *[
            Step(product, matrix(sums), "matrix_mul_row_col", [_num(row + 1), _num(1)])
            for row in (0, 1)
        ],
    )
    state = [list(row) for row in sums]
    stages: list[Step] = []
    for row in range(2):
        before = matrix(state)
        state[row] = [_num(solution[row])]
        stages.append(Step(before, matrix(state), "matrix_mul_row_col_simple"))
    detail.add_group("calculate_short", *stages)
    detail.set_solution(matrix(state))
    return detail


def _empty_element(names: list[str]) -> CoreNode:
    return _node(T.ELEMENT_OF, _node(T.LIST, *[_var(name) for name in names]), CoreNode.empty())


def _degenerate_2x2(node: CoreNode, names: tuple[str, str]) -> tuple[list[_Eq], bool] | None:
    """Integer 2×2 system with ``det A = 0`` and whether it is dependent."""
    if len(node.children) != 2:
        return None
    found = [_coefficients(equation, names) for equation in node.children]
    if any(item is None for item in found):
        return None
    eqs = [item for item in found if item is not None]
    (a1, b1, c1), (a2, b2, c2) = eqs
    if a1 * b2 - a2 * b1 != 0:
        return None
    dependent = a1 * c2 == a2 * c1 and b1 * c2 == b2 * c1
    return eqs, dependent


def _degenerate_substitution(
    node: CoreNode, names: tuple[str, str], eqs: list[_Eq], dependent: bool
) -> SolveResult | None:
    """The substitution card for a dependent or inconsistent 2×2 system."""
    first, second = node.children
    a, b, c = eqs[0]
    var_index = 0 if abs(a) == 1 else 1 if abs(b) == 1 else None
    if var_index is None:
        return None
    other = 1 - var_index
    from .systems import _linear_form

    sign = (a, b)[var_index]
    coefficient = (a, b)[other]
    items: list[tuple[int, CoreNode]] = []
    constant = Fraction(c, sign) if sign else Fraction(c)
    if constant:
        items.append((1 if constant > 0 else -1, _num(abs(constant))))
    variable_coefficient = Fraction(-coefficient, sign) if sign else Fraction(0)
    if variable_coefficient:
        items.append(
            (
                1 if variable_coefficient > 0 else -1,
                _term(int(abs(variable_coefficient)), names[other]),
            )
        )
    expression = _chain(items) if items else _num(0)
    isolated = _equation(_var(names[var_index]), expression)
    detail = isolation_detail(first, isolated, names[other], int(coefficient))
    if detail is None:
        detail = SolveResult()
        detail.add_group("rel_move_right_var", Step(first, isolated, "rel_move_right_var"))
        detail.set_solution(isolated)
    replaced = _system(first, isolated)
    result = SolveResult()
    result.add_group(
        "eq_solve_short",
        Step(node, replaced, "eq_linear", [_var(names[var_index])], subresult=detail),
    )
    merged = _replace(second, names[var_index], expression)
    result.add_group(
        CoreRichText(type="substitute_value_of", args=[_var(names[var_index])]),
        Step(replaced, merged, "system_substitute_value", [_var(names[var_index]), second]),
    )
    left, right = merged.children
    left_form = _linear_form(left, {names[0]: 0, names[1]: 1})
    right_form = _linear_form(right, {names[0]: 0, names[1]: 1})
    remaining = left_form[0][other] - right_form[0][other]
    constant_difference = left_form[1] - right_form[1]
    if dependent and remaining == 0 and constant_difference == 0:
        identity = _equation(_num(0), _num(0))
        element = _node(T.ELEMENT_OF, _var(names[other]), _var("ℝ"))
        solve_detail = SolveResult()
        solve_detail.add_group(
            "sub_with_self_remove_alg",
            Step(merged, identity, "sub_with_self_remove_alg"),
        )
        solve_detail.add_group(
            "rel_el_of_r", Step(identity, element, "rel_el_of_r", [_var(names[other])])
        )
        solve_detail.set_solution(element)
        result.add_group(
            "eq_solve_short",
            Step(merged, element, "eq_linear", [_var(names[other])], subresult=solve_detail),
        )
        values = [expression if index == var_index else _var(names[other]) for index in range(2)]
        pair = _equation(
            _node(T.BRACKET, _node(T.LIST, *[_var(name) for name in names])),
            _node(T.BRACKET, _node(T.LIST, *values)),
        )
        answer = _node(
            T.LIST,
            _equation(_var(names[var_index]), expression),
            _node(T.ELEMENT_OF, _var(names[other]), _var("ℝ")),
        )
        any_detail = SolveResult()
        any_detail.add_group(
            "system_sub_pair",
            Step(element, first, "system_2x2_any_sol_init", [_var(names[var_index])]),
        )
        solve_one = isolation_detail(first, isolated, names[other], int(coefficient))
        any_detail.add_group(
            "eq_solve_short",
            Step(
                first,
                isolated,
                "eq_linear",
                [_var(names[var_index])],
                subresult=solve_one,
            ),
        )
        any_detail.add_group(
            "system_sub_pair",
            Step(
                isolated, pair, "system_2x2_any_sol_fin", [_node(T.LIST, *[_var(n) for n in names])]
            ),
        )
        any_detail.set_solution(pair)
        result.add_group(
            "system_2x2_sol_in_param",
            Step(
                element,
                answer,
                "system_2x2_any_sol",
                [_var(names[other]), _var(names[var_index])],
                subresult=any_detail,
            ),
        )
        result.set_solution(answer)
        return result
    contradiction = _equation(_num(left_form[1]), _num(right_form[1]))
    empty = _node(T.ELEMENT_OF, _var(names[other]), CoreNode.empty())
    solve_detail = SolveResult()
    solve_detail.add_group(
        "sub_with_self_remove_alg", Step(merged, contradiction, "sub_with_self_remove_alg")
    )
    solve_detail.add_group(
        "rel_el_of_zero", Step(contradiction, empty, "rel_el_of_zero", [_var(names[other])])
    )
    solve_detail.set_solution(empty)
    result.add_group(
        "eq_solve_short",
        Step(merged, empty, "eq_linear", [_var(names[other])], subresult=solve_detail),
    )
    total_empty = _empty_element(list(names))
    result.add_group(
        "system_no_sol",
        Step(empty, total_empty, "system_2x2_no_sol2", [_var(names[other])]),
    )
    result.set_solution(total_empty)
    return result


def _cramer_not_applicable_2x2(
    node: CoreNode, names: tuple[str, str], eqs: list[_Eq]
) -> SolveResult:
    """Cramer's rule card for ``det A = 0``: determinants, then «not applicable»."""
    (a1, b1, c1), (a2, b2, c2) = eqs
    letters = [_var("D"), _var("D_1"), _var("D_2")]
    cells = [(a1, b1, a2, b2), (c1, b1, c2, b2), (a1, c1, a2, c2)]
    determinants = [_node(T.DETERMINANT2, *[_num(value) for value in item]) for item in cells]
    listing = _node(
        T.LIST,
        *[_equation(letter, det) for letter, det in zip(letters, determinants, strict=True)],
    )
    result = SolveResult()
    result.add_group("system_list_det", Step(node, listing, "system_2x2_cramer_rule"))
    current = listing
    values = [item[0] * item[3] - item[1] * item[2] for item in cells]
    for index, (_letter, det, found) in enumerate(zip(letters, determinants, values, strict=True)):
        parts = list(current.children)
        for earlier in range(index + 1):
            parts[earlier] = _equation(letters[earlier], _num(values[earlier]))
        nxt = _node(T.LIST, *parts)
        detail = det2_detail(det, cells[index], found)
        result.add_group("evaluate", Step(current, nxt, "det_evaluate", subresult=detail))
        current = nxt
    formulas = [
        _equation(_var(names[0]), _node(T.FRACTION, letters[1], letters[0])),
        _equation(_var(names[1]), _node(T.FRACTION, letters[2], letters[0])),
    ]
    result.add_group(
        "system_cramer_does_not_apply",
        Step(
            current,
            _empty_element(list(names)),
            "system_2x2_cramer_not_applicable",
            [_equation(letters[0], _num(0)), *formulas],
        ),
    )
    result.set_solution(_empty_element(list(names)))
    return result


def _inverse_no_unique_2x2(node: CoreNode, names: tuple[str, str], eqs: list[_Eq]) -> SolveResult:
    """The inverse-matrix card for a singular system: A⁻¹ does not exist."""
    (a1, b1, c1), (a2, b2, c2) = eqs

    def matrix(rows: list[list[CoreNode]]) -> CoreNode:
        return _node(T.MATRIX, *[_node(T.MATRIX_ROW, *row) for row in rows])

    coefficients = matrix([[_num(a1), _num(b1)], [_num(a2), _num(b2)]])
    unknowns = matrix([[_var(names[0])], [_var(names[1])]])
    constants = matrix([[_num(c1)], [_num(c2)]])
    letters = (_var("A"), _var("X"), _var("B"))
    equation = _equation(_node(T.MULTIPLY, coefficients, unknowns), constants)
    symbolic = _equation(_node(T.MULTIPLY_IMPLICIT, letters[0], letters[1]), letters[2])
    identified = _equation(letters[0], coefficients)
    result = SolveResult()
    result.add_group(
        "system_2x2_inv_matrix_write_as_mat_eq_smpl",
        Step(
            node,
            equation,
            "system_2x2_inv_matrix_write_as_mat_eq",
            [symbolic, coefficients, unknowns, constants],
        ),
    )
    result.add_group(
        "matrix_identify",
        Step(equation, identified, "system_2x2_inv_matrix_identify", [letters[0]]),
    )
    find = SolveResult()
    find.add_group(
        "matrix_inv_find_smpl",
        Step(identified, None, "system_2x2_inv_matrix_find_inv"),
    )
    result.add_group(
        "matrix_inv_find_smpl",
        Step(identified, None, "system_2x2_inv_matrix_find_inv", subresult=find),
    )
    result.add_group(
        "system_2x2_inv_matrix_no_uniq_sol_smpl",
        Step(identified, None, "system_2x2_inv_matrix_no_uniq_sol"),
    )
    result.set_solution(_empty_element(list(names)))
    return result


def _degenerate_elimination(
    node: CoreNode, names: tuple[str, str], eqs: list[_Eq]
) -> SolveResult | None:
    """Elimination for an inconsistent system: multiply by −1, add, declare false."""
    first, second = node.children
    (a1, _b1, c1), (a2, b2, c2) = eqs
    scaled_eq = (-a2, -b2, -c2)
    scaled = _equation(_linear(scaled_eq[0], scaled_eq[1], names), _num(scaled_eq[2]))
    after = _system(first, scaled)
    result = SolveResult()
    result.add_group(
        "multiply_both_sides",
        Step(
            node,
            after,
            "eq_mul_direct_one",
            [_num(-1)],
            subresult=multiplication_detail(second, scaled, -1, "eq_mul_direct_one"),
        ),
    )
    gone = 0 if a1 == -scaled_eq[0] else 1
    detail = addition_detail(after, eqs[0], scaled_eq, names, gone)
    summed = _equation(
        _chain([(1, _term(abs(a1 + scaled_eq[0]), names[0]))]) if a1 + scaled_eq[0] else _num(0),
        _num(c1 + scaled_eq[2]),
    )
    detail.set_solution(summed)
    result.add_group("eliminate_variable", Step(after, summed, "system_2x2_sum", subresult=detail))
    total_empty = _empty_element(list(names))
    result.add_group(
        "rel_state_false",
        Step(summed, total_empty, "system_nxn_no_sol", [_var(name) for name in names]),
    )
    result.set_solution(total_empty)
    return result


def _gauss_param_2x2(node: CoreNode, names: tuple[str, str], eqs: list[_Eq]) -> SolveResult | None:
    """Gauss–Jordan for a dependent 2×2: identical row, one equation, parameter solution."""
    (a1, b1, c1), (a2, b2, c2) = eqs
    if a1 == 0 and b1 == 0:
        return None
    divisor = Fraction(a2, a1) if a1 else Fraction(b2, b1)
    if divisor == 0:
        return None

    def matrix(rows: list[list[Fraction]]) -> CoreNode:
        return _node(
            T.MATRIX_SPLIT_LAST,
            *[_node(T.MATRIX_ROW, *[_num(value) for value in row]) for row in rows],
        )

    second = matrix(
        [[Fraction(a2), Fraction(b2), Fraction(c2)], [Fraction(a1), Fraction(b1), Fraction(c1)]]
    )
    divided = matrix(
        [[Fraction(a1), Fraction(b1), Fraction(c1)], [Fraction(a1), Fraction(b1), Fraction(c1)]]
    )
    zeroed = matrix(
        [[Fraction(a1), Fraction(b1), Fraction(c1)], [Fraction(0), Fraction(0), Fraction(0)]]
    )
    single = matrix([[Fraction(a1), Fraction(b1), Fraction(c1)]])
    equation = _equation(_linear(a1, b1, names), _num(c1))
    result = SolveResult()
    result.add_group("system_convert_eq_to_mat", Step(node, second, "system_write_coeffs_to_mat"))
    if divisor != 1:
        detail = arithmetic_row_detail(
            second, divided, "mat_divide_row_element", [_num(divisor)], _num
        )
        result.add_group(
            "mat_divide_row_simple",
            Step(second, divided, "mat_divide_row", [_num(divisor)], subresult=detail),
        )
    result.add_group("matrix_remove_row", Step(divided, zeroed, "matrix_remove_identical"))
    result.add_group("remove_row", Step(zeroed, single, "delete_row"))
    result.add_group(
        "system_convert_mat_to_eq_eq_short",
        Step(single, equation, "system_convert_mat_to_eq_eq"),
    )
    var_index = 0 if a1 == 1 else 1 if b1 == 1 else None
    if var_index is None:
        result.set_solution(equation)
        return result
    other = 1 - var_index
    sign = (a1, b1)[var_index]
    coefficient = (a1, b1)[other]
    items: list[tuple[int, CoreNode]] = []
    constant = Fraction(c1, sign)
    if constant:
        items.append((1 if constant > 0 else -1, _num(abs(constant))))
    variable_coefficient = Fraction(-coefficient, sign)
    if variable_coefficient:
        items.append(
            (
                1 if variable_coefficient > 0 else -1,
                _term(int(abs(variable_coefficient)), names[other]),
            )
        )
    expression = _chain(items) if items else _num(0)
    solved = _equation(_var(names[var_index]), expression)
    result.add_group(
        "eq_solve_short",
        Step(equation, solved, "eq_linear", [_var(names[var_index])]),
    )
    answer = _node(
        T.LIST,
        solved,
        _node(T.ELEMENT_OF, _var(names[other]), _var("ℝ")),
    )
    result.add_group(
        "system_2x2_any_sol_inf_short",
        Step(solved, answer, "system_2x2_any_sol_param"),
    )
    result.set_solution(answer)
    return result


def degenerate_methods(node: CoreNode, variables: list[str]) -> list[SolveResult] | None:
    """The method set for a singular 2×2 integer system."""
    if len(variables) != 2 or len(node.children) != 2:
        return None
    ordered = sorted(variables)
    names: tuple[str, str] = (ordered[0], ordered[1])
    found = _degenerate_2x2(node, names)
    if found is None:
        return None
    eqs, dependent = found
    cards: list[SolveResult] = []
    substitution = _degenerate_substitution(node, names, eqs, dependent)
    if substitution is not None:
        substitution.header = "solve_using_substitution"
        cards.append(substitution)
    if not dependent:
        elimination = _degenerate_elimination(node, names, eqs)
        if elimination is not None:
            elimination.header = "system_2x2_solve_elimination_simple"
            cards.append(elimination)
    else:
        gauss = _gauss_param_2x2(node, names, eqs)
        if gauss is not None:
            gauss.header = "system_gauss_jordan_solve"
            cards.append(gauss)
    inverse = _inverse_no_unique_2x2(node, names, eqs)
    inverse.header = "system_2x2_inv_matrix_solve"
    cards.append(inverse)
    cramer = _cramer_not_applicable_2x2(node, names, eqs)
    cramer.header = "system_cramer_solve"
    cards.append(cramer)
    return cards or None


_METHOD_HEADERS = {
    # Every card names its own method: the switch title above the steps says which
    # one is shown, and Cramer's rule says so itself.
    "substitution": "solve_using_substitution",
    "elimination": "system_2x2_solve_elimination_simple",
    "comparison": "solve_using_comparison",
    "gauss": "system_gauss_jordan_solve",
    "cramer": "system_cramer_solve",
    "inverse": "system_2x2_inv_matrix_solve",
}


def methods(node: CoreNode, variables: list[str]) -> list[SolveResult] | None:
    """The cards the app shows for a 2x2 integer system, or ``None`` outside the family."""
    if len(variables) != 2 or len(node.children) != 2:
        return None
    try:
        first, second = sorted(variables)  # The app orders the unknowns alphabetically
        case = _Case(node, (first, second))
    except SolveError:
        return None
    builders = (
        ("substitution", case.substitution),
        ("elimination", case.elimination),
        ("comparison", case.comparison),
        ("gauss", case.gauss),
        ("cramer", case.cramer),
        ("inverse", case.inverse),
    )
    built = []
    for name, build in builders:
        card = build()
        if card is not None:
            card.header = _METHOD_HEADERS[name]
            built.append(card)
    return built or None


__all__ = ["methods"]
_ = (as_fraction, format_number, _SIGNS)
