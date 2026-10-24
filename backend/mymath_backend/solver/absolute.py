"""Модуль, знак и целая часть: точные значения и снятие знака.

Модуль зарегистрирован на узлы ``ABS``, ``SIGN`` и ``FLOOR`` -- три
элементарные функции одного аргумента:

* ``ABS`` -- модуль: ``|-5| = 5``, ``|π| = π``, ``|x²| = x²``;
* ``SIGN`` -- знак: ``sgn(5) = 1``, ``sgn(-3) = -1``, ``sgn(0) = 0``;
* ``FLOOR`` -- целая часть: ``⌊2.7⌋ = 2``, ``⌊-1.5⌋ = -2``, ``⌊π⌋ = 3``.

Значение считает sympy. Где он не справляется, помогают структурные
правила: модуль и знак выражения, заведомо неотрицательного (чётная
степень, корень, ``e^u``, произведение неотрицательных) снимаются.
Модуль такого выражения равен самому выражению; знак считается равным
``1`` **вне нуля** (в нуле знак был бы ``0``, и этот
случай здесь не отделяется).

Символьные аргументы без вывода о знаке (``|x|``, ``sgn(x)``) остаются
без изменений: точного значения у них нет.

Ключи шагов: ``abs`` / ``abs_pos`` (снятие модуля), ``find_sign``,
``calculate_floor``.
"""

from __future__ import annotations

from collections.abc import Iterable
from fractions import Fraction
from typing import Any

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .arithmetic import format_number
from .base import SolveContext, SolveError, SolveResult, Step, solver_for
from .sympy_bridge import from_sympy, to_sympy

# Узел -> функция sympy (она же применяется к значению и для проверки
# «осталась ли функция»). Ключ пояснения хранится отдельно.
_FUNCTIONS: dict[T, Any] = {
    T.ABS: sympy.Abs,
    T.SIGN: sympy.sign,
    T.FLOOR: sympy.floor,
}
_STEP_KEY: dict[T, str] = {
    T.ABS: "abs",
    T.SIGN: "find_sign",
    T.FLOOR: "calculate_floor",
}
_KEY_ABS_POSITIVE = "abs_pos"

# Ключи шагов уравнения с модулем.
_KEY_ABS_BRANCH = "eq_abs_branch"
_KEY_FINAL = "quad_final_single"
_KEY_NO_SOLUTION = "false_statement_solve"


@solver_for(*_FUNCTIONS)
def solve_value_function(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить модуль, знак или целую часть или оставить узел."""
    if len(node.children) != 1:
        raise SolveError("функция должна иметь один аргумент")
    argument = node.children[0]
    result = _resolve(node, argument)
    if result is None:
        return node
    key = _STEP_KEY[node.type]
    args: list[CoreNode] = []
    if node.type is T.ABS and result.structural_eq(argument):
        key = _KEY_ABS_POSITIVE
    elif node.type is T.ABS and _negative_number(argument):
        # |negative|: "the absolute value of any number is always positive" (worked out on |-5|)
        key = "abs_real"
    elif node.type is T.FLOOR:
        # The app names the row "calculate the value", not "floor" (worked out on floor(2.7))
        key = "calculate_direct"
    elif node.type is T.SIGN and _positive_number(argument) and result.value == "1":
        # sgn(positive) = 1: "if the expression is greater than 0, its sign is always 1"
        key = "sign_simp_gtz"
        args = [CoreNode.constant("0"), CoreNode.constant("1")]
    ctx.result.add(Step(left=node, right=result, key=key, args=args))
    return result


def _negative_number(node: CoreNode) -> bool:
    """Является ли узел отрицательным числом."""
    try:
        return bool(to_sympy(node).is_negative)
    except SolveError:
        return False


def _positive_number(node: CoreNode) -> bool:
    """Является ли узел положительным числом."""
    if node.type is not T.CONSTANT:
        return False
    try:
        return bool(to_sympy(node).is_positive)
    except SolveError:
        return False


def _resolve(node: CoreNode, argument: CoreNode) -> CoreNode | None:
    """Итоговое значение узла или ``None``, если он не упрощается."""
    value = _FUNCTIONS[node.type](to_sympy(argument))
    if not value.has(_FUNCTIONS[node.type]):
        # Значение вычислено полностью (число, π, …).
        return from_sympy(value)

    # Функция осталась: применяем структурные правила о неотрицательности.
    if node.type in (T.ABS, T.SIGN) and _nonnegative(argument):
        return argument if node.type is T.ABS else CoreNode.constant("1")

    candidate = from_sympy(value)
    # Частичное упрощение (например, ``|-x| = |x|``) принимаем, если узел
    # действительно изменился.
    return candidate if not candidate.structural_eq(node) else None


def _nonnegative(node: CoreNode) -> bool:
    """Заведомо ли выражение неотрицательно по своей структуре."""
    if node.type in (T.ABS, T.EXP, T.ROOT2):
        return True
    if node.type is T.ROOT and len(node.children) == 2:
        return True
    if node.type is T.POWER and len(node.children) == 2:
        exponent = _integer(node.children[1])
        if exponent is not None and exponent % 2 == 0:
            return True
    if node.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT):
        return all(_nonnegative(child) for child in node.children)
    if node.type in (T.BRACKET, T.POSITIVE) and node.children:
        return _nonnegative(node.children[0])
    if node.type is T.CONSTANT:
        try:
            return bool(to_sympy(node).is_nonnegative)
        except SolveError:
            return False
    return False


def _integer(node: CoreNode) -> int | None:
    """Целое значение константы или ``None``."""
    if node.type is not T.CONSTANT or node.value is None:
        return None
    try:
        return int(node.value.strip())
    except ValueError:
        return None


def solve_abs_equation(node: CoreNode, variables: list[str]) -> SolveResult | None:
    """Уравнение с модулем: ``|f(x)| = g(x)`` по ветвям, несколько модулей — через множество."""
    if len(variables) != 1:
        return None
    return _single_abs(node, variables) or _several_abs(node, variables[0])


def _single_abs(node: CoreNode, variables: list[str]) -> SolveResult | None:
    """Решить уравнение ``|f(x)| = g(x)`` или вернуть ``None``.

    Модуль заменяется двумя уравнениями (``f = g`` и ``f = -g``), их корни
    объединяются и проверяются подстановкой в исходное уравнение: ветвь
    ``f = -g`` подходит только при ``g ≥ 0``. Если правая часть —
    отрицательное число, решений нет. Не наш случай -- ``None``.
    """
    if len(variables) != 1:
        return None
    matched = _match_abs(node)
    if matched is None:
        return None
    abs_argument, other = matched
    var = variables[0]

    try:
        left = to_sympy(abs_argument)
        right = to_sympy(other)
    except SolveError:
        return None
    if right.is_number is True and right.is_negative:
        return _no_solution(node, var)
    if right.is_zero and (zero_card := _zero_abs_rows(node, abs_argument, var)) is not None:
        return zero_card

    targets = [right] if right.is_zero else [right, -right]
    symbol = sympy.Symbol(var)
    residual = sympy.Abs(left) - right
    candidates = _roots(left, targets, symbol)
    if not candidates:
        return None
    roots = [root for root in candidates if _satisfies(residual, symbol, root)]

    result = SolveResult()
    branch_node = _list_node(
        CoreNode.node(T.EQUALS, abs_argument, from_sympy(target)) for target in targets
    )
    if len(targets) == 2 and len(roots) == 2 and _linear_branches(abs_argument, targets, symbol):
        return _card_rows(node, abs_argument, targets, roots, var, branch_node)
    if (
        quadratic := _quadratic_abs_rows(node, abs_argument, targets, var, branch_node)
    ) is not None:
        return quadratic
    if (linear_right := _linear_right_abs_rows(node, variables)) is not None:
        return linear_right
    if (quadratic_right := _quadratic_right_abs_rows(node, variables)) is not None:
        return quadratic_right
    result.add(Step(left=node, right=branch_node, key=_KEY_ABS_BRANCH))
    if not roots:
        result.add(Step(left=branch_node, right=None, key=_KEY_NO_SOLUTION))
        result.set_solution(CoreNode.empty())
        return result

    solution = _solution_node(var, roots)
    result.add(Step(left=branch_node, right=solution, key=_KEY_FINAL))
    result.set_solution(solution)
    return result


def _zero_abs_rows(node: CoreNode, argument: CoreNode, var: str) -> SolveResult | None:
    """``|x + c| = 0``: the absolute value is linear and zero, so its argument is zero.

    Worked out for ``|x - 2| = 0``: ``eq_abs_as_linear`` under ``log_set_arg_zero``, then the
    ordinary constant-move card (the linear solver provides its detailed rows).
    """
    try:
        expression = to_sympy(argument)
    except SolveError:
        return None
    symbol = sympy.Symbol(var)
    if sympy.degree(expression, symbol) != 1:
        return None
    if sympy.expand(expression).coeff(symbol) != 1:
        return None
    equation = CoreNode.node(T.EQUALS, argument, CoreNode.constant("0"))
    from .equations import solve_methods

    try:
        linear = solve_methods(equation, [var])[0]
    except (IndexError, SolveError):
        return None
    result = SolveResult()
    result.add_group(
        CoreRichText(type="log_set_arg_zero", args=[CoreNode.constant("0")]),
        Step(node, equation, "eq_abs_as_linear", [argument, CoreNode.constant("0")]),
    )
    result.add_group(
        "rel_move_right_const_msg",
        Step(equation, linear.solution or equation, "rel_move_right_const_eq", subresult=linear),
    )
    result.set_solution(linear.solution or equation)
    return result


def _several_abs(node: CoreNode, var: str) -> SolveResult | None:
    """``|x| + |x - 2| = 2`` and other equations with several moduli: sympy's solution set.

    The set may be an interval (here ``[0, 2]``), so it is shown as a set, not as roots.
    """
    if node.type is not T.EQUALS or sum(1 for n in node.walk() if n.type is T.ABS) < 2:
        return None
    try:
        values = sympy.solveset(
            sympy.Eq(to_sympy(node.children[0]), to_sympy(node.children[1])),
            sympy.Symbol(var),
            sympy.S.Reals,
        )
        if isinstance(values, sympy.FiniteSet):
            answer = _solution_node(var, sorted(values.args, key=float))
        elif values == sympy.S.EmptySet:
            answer = CoreNode.empty()
        else:
            answer = from_sympy(values)
    except (SolveError, TypeError, ValueError, NotImplementedError):
        return None
    result = SolveResult()
    result.add(Step(left=node, right=None, key=_KEY_ABS_BRANCH))
    result.add(
        Step(left=node, right=answer if answer.type is not T.EMPTY else None, key=_KEY_FINAL)
    )
    result.set_solution(answer)
    return result


def _linear_branches(argument: CoreNode, targets: list[sympy.Expr], symbol: sympy.Symbol) -> bool:
    """Both ``argument = ±g`` are linear in the unknown (the family verified on device)."""
    try:
        expression = to_sympy(argument)
        return sympy.degree(expression, symbol) == 1 and all(t.is_number is True for t in targets)
    except (SolveError, sympy.PolynomialError, TypeError):
        return False


def _signs() -> tuple[CoreNode, CoreNode]:
    """The ``±`` arguments of a sign-splitting row."""
    from .quadratic_cards import _SIGNS

    return _SIGNS


def _quadratic_right_abs_rows(node: CoreNode, variables: list[str]) -> SolveResult | None:
    """``|x| = x^2 + c`` with ``c < 0``: two branches, factor each, intersect, count.

    Worked out for ``|x| = x^2 - 2``.
    """
    var = variables[0]
    matched = _match_abs(node)
    if matched is None:
        return None
    argument, other = matched
    if argument.type is not T.VARIABLE or argument.value != var:
        return None
    if not (
        other.type in (T.ADD, T.SUBTRACT)
        and len(other.children) == 2
        and other.children[0].type is T.POWER
        and other.children[0].children[0].type is T.VARIABLE
        and other.children[1].type is T.CONSTANT
    ):
        return None
    from . import quadratic_cards

    x = CoreNode.variable(var)
    eq, zero = CoreNode.node, CoreNode.constant("0")
    constant = int(other.children[1].value or 0) * (1 if other.type is T.ADD else -1)
    if constant >= 0:
        return None
    symbol = sympy.Symbol(var)
    plans = []
    for sign in (1, -1):
        # x = x^2 + c  ->  x^2 - x + c = 0;  -x = x^2 + c  ->  x^2 + x + c = 0
        b = -sign
        family = quadratic_cards._Family(var, 1, b, constant)
        if not family.d >= 0 or family.root**2 != family.d:
            return None
        scratch = SolveResult()
        rows = quadratic_cards._factor_rows(family, scratch, None)
        if rows is None:
            return None
        plans.append((sign, family, rows, scratch))
    result = SolveResult()
    abs_node = CoreNode.node(T.ABS, argument)
    shifted = eq(T.EQUALS, eq(T.SUBTRACT, abs_node, other), zero)
    swap = SolveResult()
    swap.add_group(
        "rel_swap_left_var",
        Step(
            node,
            eq(T.EQUALS, eq(T.SUBTRACT, abs_node, other), eq(T.SUBTRACT, other, other)),
            "rel_swap_left_var",
        ),
    )
    swap.add_group(
        "remove_opposites",
        Step(
            eq(T.EQUALS, eq(T.SUBTRACT, abs_node, other), eq(T.SUBTRACT, other, other)),
            shifted,
            "sub_with_self_remove_alg",
        ),
    )
    swap.set_solution(shifted)
    result.add_group("rel_move_left_msg", Step(node, shifted, "rel_move_left_var", subresult=swap))
    case_plus = eq(T.EQUALS, eq(T.SUBTRACT, x, other), zero)
    case_minus = eq(T.EQUALS, eq(T.SUBTRACT, eq(T.NEGATIVE, x), other), zero)
    conditions = (
        eq(T.GREATER_THAN_EQUAL, x, zero),
        eq(T.LESS_THAN, x, zero),
    )
    cases = eq(
        T.LIST,
        eq(T.LIST, case_plus, conditions[0]),
        eq(T.LIST, case_minus, conditions[1]),
    )
    result.add_group(
        "eq_separate_short",
        Step(shifted, cases, "eq_separate", [CoreNode.constant("2")]),
    )
    branches: list[CoreNode] = []
    accepted: list[CoreNode] = []
    for index, (sign, _family, rows, scratch) in enumerate(plans):
        product, bracket, second = rows
        factored = eq(T.EQUALS, product, zero)
        page = SolveResult()
        page.add_group(
            "rel_move_left_const",
            Step(cases.children[index], factored, "rel_move_left_const"),
        )
        page.add_group("var_order", Step(factored, factored, "var_order"))
        page.add_group("eq_linear_neg", Step(factored, factored, "eq_linear_neg"))
        for step in scratch:
            page.add(step)
        candidates = [
            eq(T.EQUALS, bracket, zero),
            eq(T.EQUALS, second, zero),
        ]
        listed = eq(T.LIST, *candidates)
        page.add_group(
            "eq_separate_short", Step(factored, listed, "quad_separate_zero_product", [zero])
        )
        solved: list[CoreNode] = []
        pages: list[Step] = []
        for case in candidates:
            value = sympy.solve(sympy.Eq(to_sympy(case.children[0]), 0), symbol)
            if len(value) != 1 or value[0].is_real is False:
                continue
            root_eq = eq(T.EQUALS, x, from_sympy(value[0]))
            solved.append(root_eq)
            pages.append(Step(listed, root_eq, "eq_linear", [x]))
        page.add_group("eq_solve_short_plural", *pages)
        branch = eq(T.LIST, *solved, conditions[index])
        page.set_solution(eq(T.LIST, *solved))
        branches.append(branch)
        for root_eq in solved:
            value = to_sympy(root_eq.children[1])
            if (sign > 0 and value >= 0) or (sign < 0 and value < 0):
                accepted.append(root_eq)
        result.add_group(
            "eq_solve_short_plural",
            Step(cases, branch, "eq_linear", [x], subresult=page),
        )
    branch_list = eq(T.LIST, *branches)
    result.add_group(
        "intersection",
        Step(branch_list, branch_list, "intersection"),
        Step(branch_list, branch_list, "intersection"),
    )
    answer = _list_node(sorted(accepted, key=lambda part: float(to_sympy(part.children[1]))))
    count = CoreNode.constant(str(len(accepted)))
    result.add_group(
        CoreRichText(type="solution_eq_num", args=[count]),
        Step(branch_list, answer, "solution_eq_num", [count]),
    )
    result.set_solution(answer)
    return result


def _linear_right_abs_rows(node: CoreNode, variables: list[str]) -> SolveResult | None:
    """``|x + a| = x`` with ``a < 0``: piecewise branch, condition, intersection, union.

    Worked out for ``|x - 1| = x``.
    """
    var = variables[0]
    matched = _match_abs(node)
    if matched is None:
        return None
    argument, other = matched
    if other.type is not T.VARIABLE or other.value != var:
        return None
    if not (
        argument.type in (T.ADD, T.SUBTRACT)
        and len(argument.children) == 2
        and argument.children[0].type is T.VARIABLE
        and argument.children[0].value == var
        and argument.children[1].type is T.CONSTANT
    ):
        return None
    a = int(argument.children[1].value or 0) * (1 if argument.type is T.ADD else -1)
    if a >= 0:
        return None
    x = CoreNode.variable(var)
    eq, zero = CoreNode.node, CoreNode.constant("0")
    abs_node = CoreNode.node(T.ABS, argument)
    shifted = eq(T.EQUALS, eq(T.SUBTRACT, abs_node, x), zero)
    result = SolveResult()
    swap = SolveResult()
    swap.add_group(
        "rel_swap_left_var",
        Step(
            node,
            eq(T.EQUALS, eq(T.SUBTRACT, abs_node, x), eq(T.SUBTRACT, x, x)),
            "rel_swap_left_var",
        ),
    )
    swap.add_group(
        "remove_opposites",
        Step(
            eq(T.EQUALS, eq(T.SUBTRACT, abs_node, x), eq(T.SUBTRACT, x, x)),
            shifted,
            "sub_with_self_alg",
            [zero],
        ),
    )
    swap.set_solution(shifted)
    result.add_group("rel_move_left_msg", Step(node, shifted, "rel_move_left_var", subresult=swap))
    case_plus = eq(T.EQUALS, eq(T.SUBTRACT, argument, x), zero)
    case_minus = eq(T.EQUALS, eq(T.SUBTRACT, eq(T.NEGATIVE, argument), x), zero)
    condition_plus = eq(T.GREATER_THAN_EQUAL, argument, zero)
    condition_minus = eq(T.LESS_THAN, argument, zero)
    cases = eq(
        T.LIST,
        eq(T.LIST, case_plus, condition_plus),
        eq(T.LIST, case_minus, condition_minus),
    )
    result.add_group(
        "eq_separate_short",
        Step(shifted, cases, "eq_separate", [CoreNode.constant("2")]),
    )
    empty = CoreNode.node(T.ELEMENT_OF, x, CoreNode.empty())
    plus_page = SolveResult()
    plus_page.add_group(
        "remove_opposites",
        Step(case_plus, eq(T.EQUALS, zero, zero), "sub_with_self_remove_alg"),
    )
    plus_page.add_group(
        "rel_el_of_zero", Step(eq(T.EQUALS, zero, zero), None, "rel_el_of_zero", [x])
    )
    plus_page.set_solution(empty)
    root = Fraction(-a, 2)
    root_value = (
        CoreNode.constant(str(root.numerator))
        if root.denominator == 1
        else from_sympy(sympy.Rational(root.numerator, root.denominator))
    )
    root_eq = CoreNode.node(T.EQUALS, x, root_value)
    minus_page = SolveResult()
    minus_page.add_group(
        "neg_neg", Step(case_minus, case_minus, "neg_neg_arg", [CoreNode.variable("-")])
    )
    minus_page.add_group("sum_suffix", Step(case_minus, case_minus, "sum_suffix"))
    minus_page.add_group(
        "rel_move_right_const_msg",
        Step(case_minus, root_eq, "rel_move_right_const_eq"),
    )
    minus_page.add_group(
        "divide_both_sides",
        Step(root_eq, root_eq, "eq_linear_div", [CoreNode.constant(format_number(Fraction(a)))]),
    )
    minus_page.set_solution(root_eq)
    condition_plus_page = SolveResult()
    condition_plus_page.add_group(
        "rel_swap_right_const",
        Step(condition_plus, condition_plus, "rel_swap_right_const"),
    )
    condition_plus_page.add_group(
        "remove_opposites", Step(condition_plus, condition_plus, "sub_with_self_remove_num")
    )
    condition_plus_page.add_group(
        CoreRichText(type="remove_zero", args=[zero]),
        Step(condition_plus, condition_plus, "add_with_zero", [zero]),
    )
    condition_plus_page.set_solution(condition_plus)
    condition_minus_page = SolveResult()
    condition_minus_page.add_group(
        "rel_swap_right_const",
        Step(condition_minus, condition_minus, "rel_swap_right_const"),
    )
    condition_minus_page.add_group(
        "remove_opposites", Step(condition_minus, condition_minus, "sub_with_self_remove_num")
    )
    condition_minus_page.add_group(
        CoreRichText(type="remove_zero", args=[zero]),
        Step(condition_minus, condition_minus, "add_with_zero", [zero]),
    )
    condition_minus_page.set_solution(condition_minus)
    branch_one = eq(T.LIST, empty, condition_plus)
    branch_two = eq(T.LIST, root_eq, condition_minus)
    branches = eq(T.LIST, branch_one, branch_two)
    result.add_group(
        "eq_solve_short_plural",
        Step(cases, branch_one, "eq_linear", [x], subresult=plus_page),
        Step(branch_one, branch_two, "ineq_linear", [x], subresult=condition_plus_page),
        Step(branch_two, branch_two, "eq_linear", [x], subresult=minus_page),
        Step(branch_two, branch_two, "ineq_linear", [x], subresult=condition_minus_page),
    )
    intersected_one = eq(T.LIST, empty, branch_two)
    intersected_two = eq(T.LIST, empty, root_eq)
    result.add_group(
        "intersection",
        Step(branches, intersected_one, "intersection"),
        Step(intersected_one, intersected_two, "intersection"),
    )
    result.add_group("union", Step(intersected_two, root_eq, "union"))
    result.set_solution(root_eq)
    return result


def _quadratic_abs_rows(
    node: CoreNode,
    argument: CoreNode,
    targets: list[sympy.Expr],
    var: str,
    branches: CoreNode,
) -> SolveResult | None:
    """``|x^2 + c| = k``: branch, then each quadratic branch as a flat four-row page.

    Worked out for ``|x^2 - 4| = 3``: move the constant right, compute the difference, take
    the square root and split the signs; the solution count closes the card.
    """
    if not (
        argument.type in (T.ADD, T.SUBTRACT)
        and len(argument.children) == 2
        and argument.children[0].type is T.POWER
        and argument.children[0].children[0].type is T.VARIABLE
        and argument.children[0].children[0].value == var
        and argument.children[0].children[1].type is T.CONSTANT
        and argument.children[0].children[1].value == "2"
        and argument.children[1].type is T.CONSTANT
    ):
        return None
    if not all(target.is_number is True for target in targets):
        return None
    symbol = sympy.Symbol(var)
    constant = int(to_sympy(argument.children[1]).p) * (1 if argument.type is T.ADD else -1)
    branch_roots: list[list[sympy.Expr]] = []
    for target in targets:
        value = sympy.simplify(target - constant)
        if value.is_negative:
            return None  # a branch without real roots uses another card
        found = sympy.solve(sympy.Eq(symbol**2, value), symbol)
        branch_roots.append(
            sorted((root for root in found if root.is_real is not False), key=float)
        )
    if any(len(found) != 2 for found in branch_roots):
        return None
    x = CoreNode.variable(var)
    square = CoreNode.node(T.POWER, x, CoreNode.constant("2"))
    result = SolveResult()
    result.add_group("eq_separate_short", Step(node, branches, _KEY_ABS_BRANCH))
    pages: list[Step] = []
    solved: list[CoreNode] = []
    for target, found in zip(targets, branch_roots, strict=True):
        case = CoreNode.node(T.EQUALS, argument, from_sympy(target))
        value = sympy.simplify(target - constant)
        value_node = from_sympy(value)
        moved = CoreNode.node(T.EQUALS, square, value_node)
        root_value = from_sympy(sympy.sqrt(value))
        rooted = CoreNode.node(T.EQUALS, x, CoreNode.node(T.ADD_SUBTRACT, root_value))
        listed = _list_node(CoreNode.node(T.EQUALS, x, from_sympy(root)) for root in found)
        page = SolveResult()
        page.add_group("rel_move_right_const_msg", Step(case, moved, "rel_move_right_const_eq"))
        page.add_group(
            "calculate_short",
            Step(
                moved,
                moved,
                "add"
                if from_sympy(target).type is T.CONSTANT and not str(target).startswith("-")
                else "calc_sum",
            ),
        )
        page.add_group("quad_sqrt_sides", Step(moved, rooted, "quad_sqrt_sides"))
        page.add_group(
            "quad_separate",
            Step(
                rooted,
                listed,
                "quad_separate_signs",
                list(_signs()),
            ),
        )
        page.set_solution(listed)
        pages.append(Step(branches, listed, "eq_linear", [x], subresult=page))
        solved.extend(listed.children if listed.type is T.LIST else [listed])
    result.add_group("eq_solve_short_plural", *pages)
    answer = _list_node(solved)
    count = CoreNode.constant(str(len(solved)))
    result.add_group(
        CoreRichText(type="solution_eq_num", args=[count]),
        Step(branches, answer, "solution_eq_num", [count]),
    )
    result.set_solution(answer)
    return result


def _card_rows(
    node: CoreNode,
    argument: CoreNode,
    targets: list[sympy.Expr],
    roots: list[sympy.Expr],
    var: str,
    branches: CoreNode,
) -> SolveResult:
    """The app: split by the definition, solve each linear case, count the roots."""
    from .equations import solve_methods

    result = SolveResult()
    x = CoreNode.variable(var)
    result.add_group("eq_separate_short", Step(node, branches, _KEY_ABS_BRANCH))
    solved = [CoreNode.node(T.EQUALS, x, from_sympy(root)) for root in roots]
    symbol = sympy.Symbol(var)
    pages = []
    for target in targets:
        root = sympy.solve(sympy.Eq(to_sympy(argument), target), symbol)[0]
        root_eq = CoreNode.node(T.EQUALS, x, from_sympy(root))
        case = CoreNode.node(T.EQUALS, argument, from_sympy(target))
        page = solve_methods(case, [var])[0]
        for step in page:  # verified page has no detail screens of its own
            step.subresult = None
        pages.append(Step(branches, root_eq, "eq_linear", [x], subresult=page))
    if argument.type is not T.VARIABLE:  # |x| = 3 needs no branch solving
        result.add_group("eq_solve_short_plural", *pages)
    solution = _list_node(solved)
    result.add_group(
        CoreRichText(type="solution_eq_num", args=[CoreNode.constant(str(len(solved)))]),
        Step(
            _list_node(solved),
            solution,
            "solution_eq_num",
            [CoreNode.constant(str(len(solved)))],
        ),
    )
    result.set_solution(solution)
    return result


def _satisfies(residual: sympy.Expr, symbol: sympy.Symbol, root: sympy.Expr) -> bool:
    """Обращается ли ``residual`` в ноль при данном корне."""
    try:
        value = sympy.simplify(residual.subs(symbol, root))
    except (TypeError, ValueError):
        return True
    result = value == 0
    if isinstance(result, bool):
        return result
    return result is sympy.true


def _match_abs(node: CoreNode) -> tuple[CoreNode, CoreNode] | None:
    """``(аргумент модуля, другая часть)`` или ``None``, если это не ``|…| = …``."""
    if node.type is not T.EQUALS or len(node.children) != 2:
        return None
    left, right = node.children
    if left.type is T.ABS and len(left.children) == 1:
        return left.children[0], right
    if right.type is T.ABS and len(right.children) == 1:
        return right.children[0], left
    return None


def _roots(left: sympy.Expr, targets: list[sympy.Expr], symbol: sympy.Symbol) -> list[sympy.Expr]:
    """Корни уравнений ``left = target`` без повторов и комплексных."""
    roots: list[sympy.Expr] = []
    for target in targets:
        try:
            found = sympy.solve(sympy.Eq(left, target), symbol)
        except (TypeError, ValueError, NotImplementedError):
            continue
        for root in found:
            if root.is_real is False:
                continue
            if any(sympy.simplify(root - known) == 0 for known in roots):
                continue
            roots.append(root)
    roots.sort(key=_sort_key)
    return roots


def _sort_key(root: sympy.Expr) -> float:
    """Ключ сортировки корней; нечисловые корни идут первыми."""
    try:
        return float(sympy.N(root))
    except (TypeError, ValueError):
        return 0.0


def _solution_node(var: str, roots: list[sympy.Expr]) -> CoreNode:
    """Ответ ``x = …`` или список таких равенств."""
    return _list_node(
        CoreNode.node(T.EQUALS, CoreNode.variable(var), from_sympy(root)) for root in roots
    )


def _list_node(equations: Iterable[CoreNode]) -> CoreNode:
    """Один узел из перечисления равенств."""
    items = list(equations)
    if len(items) == 1:
        return items[0]
    return CoreNode.node(T.LIST, *items)


def _no_solution(node: CoreNode, var: str) -> SolveResult:
    """Модуль не может быть равен отрицательному числу."""
    result = SolveResult()
    result.add(
        Step(
            left=node,
            right=None,
            key="rel_terminators_abs_no_sol",
            args=[CoreNode.variable(var), CoreNode.constant("0")],
        )
    )
    result.set_solution(CoreNode.empty())
    return result


__all__ = [
    "solve_abs_equation",
    "solve_value_function",
]
