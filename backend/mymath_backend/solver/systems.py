"""Системы: два линейных уравнения 2×2 или система неравенств.

Модуль зарегистрирован на узел ``SYSTEM``. Если среди элементов есть знак
отношения, это **система неравенств**: множества решений элементов (через
``solveset``) пересекаются, ответ — промежуток (шаг ``intersection``).
Иначе — уравнения: система 2×2 линейных решается правилом Крамера
(``system_2x2_cramer_rule``), прочие (3×3 и выше, нелинейные) — через
``sympy.solve`` (шаг ``system_3x3_rem_vars`` или
``system_2x2_solve_substitution``). Линейная система с параметром (буква
вне ``x, y, z, w, t, u, v``) разбирается по ``det A``: при ``det A ≠ 0``
решение выражается через параметр, особые значения проверяются отдельно.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from fractions import Fraction

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .arithmetic import as_fraction, format_number
from .base import SolveContext, SolveError, SolveResult, Step, boolean_node, solver_for
from .methods import method_provider
from .sympy_bridge import from_sympy, to_sympy

_HEADER = CoreRichText(type="system_solve_short")

# Отношения: система из них — система неравенств.
_RELATIONS = (
    T.LESS_THAN,
    T.LESS_THAN_EQUAL,
    T.GREATER_THAN,
    T.GREATER_THAN_EQUAL,
    T.NOT_EQUALS,
)

# Линейная форма: коэффициенты при неизвестных и свободный член.
_Form = tuple[list[Fraction], Fraction]


def _zero_form(size: int) -> _Form:
    return [Fraction(0)] * size, Fraction(0)


def _add(left: _Form, right: _Form) -> _Form:
    coeffs = [a + b for a, b in zip(left[0], right[0], strict=True)]
    return coeffs, left[1] + right[1]


def _scale(form: _Form, factor: Fraction) -> _Form:
    return [coeff * factor for coeff in form[0]], form[1] * factor


def _linear_form(node: CoreNode, index: dict[str, int]) -> _Form:
    """Привести выражение к ``a·u + b·v + c``.

    Нелинейность (произведение неизвестных, степень, функция) отклоняется:
    это другой модуль.
    """
    size = len(index)
    if node.type is T.CONSTANT:
        return _zero_form(size)[0], as_fraction(node)
    if node.type is T.VARIABLE:
        if node.value is None or node.value not in index:
            raise SolveError(f"неизвестная переменная {node.value!r}")
        coeffs = [Fraction(0)] * size
        coeffs[index[node.value]] = Fraction(1)
        return coeffs, Fraction(0)
    if node.type is T.ADD:
        result = _zero_form(size)
        for child in node.children:
            result = _add(result, _linear_form(child, index))
        return result
    if node.type is T.SUBTRACT:
        if len(node.children) < 2:
            raise SolveError("вычитание без двух операндов")
        result = _linear_form(node.children[0], index)
        for child in node.children[1:]:
            result = _add(result, _scale(_linear_form(child, index), Fraction(-1)))
        return result
    if node.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT):
        product: _Form = ([Fraction(0)] * size, Fraction(1))
        for child in node.children:
            form = _linear_form(child, index)
            if any(coeff != 0 for coeff in form[0]):
                # Множитель с неизвестным допустим, только если в произведении
                # ещё нет неизвестного: иначе это степень выше первой.
                if any(coeff != 0 for coeff in product[0]):
                    raise SolveError("система нелинейная: произведение неизвестных")
                product = _scale(form, product[1])
            else:
                product = _scale(product, form[1])
        return product
    if node.type in (T.DIVIDE, T.FRACTION):
        form = _linear_form(node.children[0], index)
        divisor = _linear_form(node.children[1], index)
        if any(coeff != 0 for coeff in divisor[0]) or divisor[1] == 0:
            raise SolveError("деление на выражение с неизвестным в системе не поддерживается")
        return _scale(form, Fraction(1) / divisor[1])
    if node.type is T.POWER:
        base = _linear_form(node.children[0], index)
        if any(coeff != 0 for coeff in base[0]):
            raise SolveError("система нелинейная: степень неизвестного")
        exponent = node.children[1]
        if exponent.type is not T.CONSTANT:
            raise SolveError("нелинейная система: показатель с неизвестным")
        value = as_fraction(exponent)
        if value.denominator != 1:
            raise SolveError("нелинейная система: дробный показатель")
        return _zero_form(size)[0], base[1] ** value.numerator
    if node.type is T.NEGATIVE:
        return _scale(_linear_form(node.children[0], index), Fraction(-1))
    if node.type in (T.POSITIVE, T.BRACKET):
        return _linear_form(node.children[0], index)
    raise SolveError(f"уравнение системы с узлом {node.type} не решается")


def _equation_form(equation: CoreNode, index: dict[str, int]) -> _Form:
    """Линейная форма уравнения ``lhs = rhs`` как ``lhs - rhs``."""
    if equation.type is not T.EQUALS or len(equation.children) != 2:
        raise SolveError("в системе должны быть уравнения")
    lhs = _linear_form(equation.children[0], index)
    rhs = _linear_form(equation.children[1], index)
    return _add(lhs, _scale(rhs, Fraction(-1)))


@solver_for(T.SYSTEM)
def solve_system(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Решить систему уравнений или неравенств.

    Система неравенств — пересечение множеств решений. Система 2×2 линейных
    уравнений — правило Крамера. Прочие (3×3 и выше, нелинейные) — через
    sympy ``solve``.
    """
    if any(child.type in _RELATIONS for child in node.children):
        return _inequality_system(node, ctx)

    unknowns, parameters = _split_variables(ctx.variables)
    if parameters and unknowns:
        # Линейную систему с параметром разбираем по её определителю.
        with contextlib.suppress(SolveError):
            return _parameter_system(node, ctx)

    if len(node.children) == 2 and len(ctx.variables) == 2:
        try:
            return _cramer_2x2(node, ctx)
        except SolveError:
            pass
    return _general_system(node, ctx)


def _cramer_2x2(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Система 2×2 линейных уравнений правилом Крамера.

    Показываются сами определители ``D``, ``D₁``, ``D₂``, их значения и
    подстановка в формулы Крамера — коэффициенты могут быть и дробными.
    """
    first_var, second_var = ctx.variables
    index = {first_var: 0, second_var: 1}

    first = _equation_form(node.children[0], index)
    second = _equation_form(node.children[1], index)
    a1, b1 = first[0]
    a2, b2 = second[0]
    rhs1, rhs2 = -first[1], -second[1]

    determinant = a1 * b2 - a2 * b1
    if determinant == 0:
        raise SolveError("система не имеет единственного решения")

    u = (rhs1 * b2 - rhs2 * b1) / determinant
    v = (a1 * rhs2 - a2 * rhs1) / determinant

    letters = [CoreNode.variable(name) for name in ("D", "D_1", "D_2")]
    determinants = [
        (a1, b1, a2, b2),
        (rhs1, b1, rhs2, b2),
        (a1, rhs1, a2, rhs2),
    ]
    values = [cells[0] * cells[3] - cells[1] * cells[2] for cells in determinants]
    listing = CoreNode.node(
        T.LIST,
        *[
            CoreNode.node(T.EQUALS, letter, _determinant(*cells))
            for letter, cells in zip(letters, determinants, strict=True)
        ],
    )
    ctx.result.add(Step(left=node, right=listing, key="system_2x2_cramer_rule"), [_HEADER])

    current = listing
    for position, (_letter, cells, found) in enumerate(
        zip(letters, determinants, values, strict=True)
    ):
        parts = list(listing.children)
        for earlier in range(position + 1):
            parts[earlier] = CoreNode.node(T.EQUALS, letters[earlier], _constant(values[earlier]))
        nxt = CoreNode.node(T.LIST, *parts)
        detail = SolveResult()
        detail.add_group(
            "det_evaluate",
            Step(
                left=_determinant(*cells),
                right=_constant(found),
                key="det2_determinant_rule",
                args=[_determinant_rule()],
            ),
        )
        detail.set_solution(_constant(found))
        ctx.result.add(
            Step(left=current, right=nxt, key="det_evaluate", subresult=detail), [_HEADER]
        )
        current = nxt

    solution = CoreNode.node(
        T.LIST,
        CoreNode(type=T.EQUALS, children=[CoreNode.variable(first_var), _constant(u)]),
        CoreNode(type=T.EQUALS, children=[CoreNode.variable(second_var), _constant(v)]),
    )
    formulas = CoreNode.node(
        T.LIST,
        CoreNode(
            type=T.EQUALS,
            children=[
                CoreNode.variable(first_var),
                CoreNode.node(T.FRACTION, letters[1], letters[0]),
            ],
        ),
        CoreNode(
            type=T.EQUALS,
            children=[
                CoreNode.variable(second_var),
                CoreNode.node(T.FRACTION, letters[2], letters[0]),
            ],
        ),
    )
    rule = SolveResult()
    target = CoreNode.variable(f"{first_var}, {second_var}")
    rule.add_group(
        CoreRichText(type="find_arg", args=[target]),
        Step(left=current, right=solution, key="system_2x2_cramer_rule"),
    )
    rule.set_solution(solution)
    condition = CoreNode.node(T.NOT_EQUALS, letters[0], _constant(Fraction(0)))
    ctx.result.add(
        Step(
            left=current,
            right=solution,
            key="system_2x2_cramer_apply_rule",
            args=[condition, target, formulas],
            subresult=rule,
        ),
        [_HEADER],
    )
    return solution


def _determinant(a: Fraction, b: Fraction, c: Fraction, d: Fraction) -> CoreNode:
    return CoreNode.node(T.DETERMINANT2, _constant(a), _constant(b), _constant(c), _constant(d))


def _determinant_rule() -> CoreNode:
    """``|a b; c d| = ad - bc``: аргумент шага раскрытия определителя 2×2."""
    letters = [CoreNode.variable(name) for name in "abcd"]
    return CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.DETERMINANT2, *letters),
        CoreNode.node(
            T.SUBTRACT,
            CoreNode.node(T.MULTIPLY, letters[0], letters[3]),
            CoreNode.node(T.MULTIPLY, letters[1], letters[2]),
        ),
    )


def _constant(value: Fraction) -> CoreNode:
    return CoreNode.constant(format_number(value))


def _general_system(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Система 3×3 и выше или нелинейная — через ``sympy.solve``."""
    ctx.require(len(ctx.variables) >= 1, "в системе нет неизвестных")
    equations = []
    for child in node.children:
        ctx.require(
            child.type is T.EQUALS and len(child.children) == 2,
            "в системе должны быть уравнения",
        )
        equations.append(sympy.Eq(to_sympy(child.children[0]), to_sympy(child.children[1])))
    symbols = [sympy.Symbol(name) for name in ctx.variables]
    try:
        found = sympy.solve(equations, symbols, dict=True)
    except (TypeError, ValueError, NotImplementedError) as error:
        raise SolveError("система не решается") from error

    if not found:
        ctx.result.add(Step(left=node, right=None, key="system_no_sol"), [_HEADER])
        return CoreNode.empty()

    answers: list[CoreNode] = []
    parametric = False
    for mapping in found:
        parts = _solution_parts(ctx.variables, mapping)
        if not parts:
            ctx.result.add(Step(left=node, right=None, key="system_2x2_any_sol_param"), [_HEADER])
            return CoreNode.empty()
        if len(parts) < len(ctx.variables):
            parametric = True
        answers.append(CoreNode.node(T.LIST, *parts) if len(parts) > 1 else parts[0])

    solution = answers[0] if len(answers) == 1 else CoreNode.node(T.LIST, *answers)
    if parametric:
        key = "system_2x2_sol_in_param"
    elif len(ctx.variables) >= 3:
        key = "system_3x3_rem_vars"
        ctx.result.add(Step(left=node, right=None, key="system_3x3_eliminate_var"), [_HEADER])
    else:
        key = "system_2x2_solve_substitution"
    ctx.result.add(Step(left=node, right=solution, key=key), [_HEADER])
    if (
        len(node.children) == 2
        and len(ctx.variables) == 2
        and len(found) == 2
        and all(all(sympy.Symbol(name) in mapping for name in ctx.variables) for mapping in found)
    ):
        from .system_cards import two_solution_tail

        two_solution_tail(ctx.result, solution, list(node.children), ctx.variables, found)
    if len(node.children) == 2 and len(ctx.variables) == 2 and len(found) == 1:
        mapping = found[0]
        if all(sympy.Symbol(name) in mapping for name in ctx.variables):
            from .system_cards import verification_tail

            values = [from_sympy(mapping[sympy.Symbol(name)]) for name in ctx.variables]
            before = solution.children[-1] if solution.type is T.LIST else solution
            verification_tail(ctx.result, before, list(node.children), ctx.variables, values)
    return solution


# Неизвестные системы: любая другая буква линейной системы — параметр.
_UNKNOWNS = frozenset("xyzwtuv")


def _split_variables(variables: list[str]) -> tuple[list[str], list[str]]:
    """Разделить имена на неизвестные и параметры, сохраняя порядок.

    Неизвестные — ``x, y, z, w`` (и ``t, u, v``); остальные буквы линейной
    системы считаются параметрами, от которых зависят коэффициенты.
    """
    unknowns = [name for name in variables if name in _UNKNOWNS]
    parameters = [name for name in variables if name not in _UNKNOWNS]
    return unknowns, parameters


def _substitute_constant(node: CoreNode, name: str, value: CoreNode) -> CoreNode:
    """Заменить переменную константой, сохранив остальное дерево."""
    if node.type is T.VARIABLE and node.value == name:
        return value
    if not node.children:
        return node
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[_substitute_constant(child, name, value) for child in node.children],
    )


def _parameter_system(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Линейная система с одним параметром: определитель, Крамер и особые случаи.

    Учебник разбирает такую систему по ``det A``: при ``det A ≠ 0`` решение
    единственно и выражается через параметр (формулы Крамера); каждое значение,
    при котором ``det A = 0``, подставляется, и получившаяся числовая система
    классифицируется существующим путём ``_consistency_card`` (несовместна или
    бесконечно много решений). Ответ — общий случай ``det A ≠ 0``, а особые
    значения перечислены отдельными шагами.
    """
    unknowns, parameters = _split_variables(ctx.variables)
    ctx.require(bool(unknowns), "в системе нет неизвестных")
    ctx.require(len(parameters) == 1, "система с несколькими параметрами не поддерживается")
    parameter = parameters[0]
    ctx.require(
        all(child.type is T.EQUALS and len(child.children) == 2 for child in node.children),
        "в системе должны быть уравнения",
    )
    equations = [
        sympy.Eq(to_sympy(child.children[0]), to_sympy(child.children[1]))
        for child in node.children
    ]
    symbols = [sympy.Symbol(name) for name in unknowns]
    symbol = sympy.Symbol(parameter)
    try:
        matrix, rhs = sympy.linear_eq_to_matrix(equations, symbols)
    except (ValueError, NotImplementedError) as error:
        raise SolveError("система нелинейна относительно неизвестных") from error
    if any(entry.free_symbols - {symbol} for entry in matrix.row_join(rhs)):
        raise SolveError("коэффициенты системы зависят не только от параметра")
    determinant = sympy.expand(matrix.det())
    ctx.require(determinant != 0, "определитель системы равен нулю при всех значениях параметра")

    parameter_node = CoreNode.variable(parameter)
    # Сам определитель, а не только его значение: иначе непонятно, откуда взялось −1 − a.
    from .matrices import _det_node

    determinant_node = from_sympy(determinant)
    computed = CoreNode.node(T.EQUALS, _det_node(matrix), determinant_node)
    ctx.result.add(
        Step(left=node, right=computed, key="system_param_det", args=[parameter_node]),
        [_HEADER],
    )
    solution = matrix.solve(rhs)
    answer = CoreNode.node(
        T.LIST,
        *[
            CoreNode.node(
                T.EQUALS,
                CoreNode.variable(name),
                from_sympy(sympy.simplify(solution[index])),
            )
            for index, name in enumerate(unknowns)
        ],
    )
    roots = [root for root in sympy.solve(sympy.Eq(determinant, 0), symbol) if root.is_real]
    if roots:
        # Один корень читается как в учебнике («a ≠ −1»), несколько — как «det A ≠ 0».
        if len(roots) == 1:
            condition = CoreNode.node(T.NOT_EQUALS, parameter_node, from_sympy(roots[0]))
        else:
            condition = CoreNode.node(T.NOT_EQUALS, determinant_node, CoreNode.constant("0"))
        ctx.result.add(
            Step(left=node, right=answer, key="system_param_unique", args=[condition]),
            [_HEADER],
        )
    else:
        ctx.result.add(Step(left=node, right=answer, key="system_param_unique_always"), [_HEADER])
    for root in roots:
        root_node = from_sympy(root)
        substituted = _substitute_constant(node, parameter, root_node)
        with contextlib.suppress(SolveError):
            card = _consistency_card(substituted, unknowns)
            ctx.result.add(
                Step(
                    left=node,
                    right=None,
                    key="system_param_special",
                    args=[parameter_node, root_node],
                    subresult=card[0] if card is not None else None,
                ),
                [_HEADER],
            )
    ctx.result.set_solution(answer)
    return answer


@method_provider(T.SYSTEM)
def system_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """Способы решения системы: Крамер (2×2 линейная) и подстановка (sympy).

    Система неравенств решается единственным способом. Первый способ — основной,
    дальше — альтернативы (переключатель ``selectMethodText``).
    """
    if any(child.type in _RELATIONS for child in node.children):
        return [_run_system(node, variables, solve_system, "solve_algebraically")]

    unknowns, parameters = _split_variables(variables)
    if parameters and unknowns:
        with contextlib.suppress(SolveError):
            return [_run_system(node, variables, _parameter_system, "system_param_solve")]

    consistency = _consistency_card(node, variables)
    if consistency is not None and not consistency[1]:
        # Inconsistent or underdetermined: the Gauss–Jordan consistency card
        # stays first, followed by its own method set (substitution,
        # elimination, inverse, Cramer «not applicable») where we can build it.
        from . import system3_cards, system_cards

        extra: list[SolveResult] = []
        if len(node.children) == 2 and len(variables) == 2:
            extra = system_cards.degenerate_methods(node, variables) or []
        elif len(node.children) == 3 and len(variables) == 3:
            extra = system3_cards.degenerate_methods(node, variables) or []
        return [consistency[0], *extra]

    from . import system_cards

    shown: list[SolveResult] | None = None
    if (verified := system_cards.methods(node, variables)) is not None:
        shown = verified
    if shown is None and len(node.children) == 3 and len(variables) == 3:
        from . import system3_cards

        if cards := system3_cards.cramer_methods(node, variables):
            shown = cards
    if shown is None and len(node.children) > 3:
        card = _gauss_card(node, variables)
        if card is not None:
            shown = [card]
    if shown is None:
        methods: list[SolveResult] = []
        if len(node.children) == 2 and len(variables) == 2:
            with contextlib.suppress(SolveError):
                methods.append(_run_system(node, variables, _cramer_2x2, "system_cramer_solve"))
        methods.append(
            _run_system(node, variables, _general_system, "system_2x2_solve_substitution")
        )
        shown = methods
    if consistency is not None:
        # A homogeneous system keeps its verified alternative ways; the new
        # card is first because it names consistency, rank and the FSS.
        return [consistency[0], *shown]
    return shown


def _consistency_card(node: CoreNode, variables: list[str]) -> tuple[SolveResult, bool] | None:
    """Gauss–Jordan card for a linear system that is not uniquely solvable.

    ``(card, homogeneous)`` for an inconsistent or underdetermined system (and
    for every homogeneous one, whose trivial solution still needs the
    «однородная система всегда совместна» stage). ``None`` when the system is
    uniquely solvable and not homogeneous — those keep their verified cards —
    or when the augmented-matrix lesson cannot honestly handle the system.

    The stages are the existing augmented-matrix reduction (one row operation
    per stage), then the ranks and — for infinitely many solutions — the free
    unknowns and the basic unknowns expressed through them.
    """
    from ..teaching_discrete import system_lesson_full

    full = system_lesson_full(node)
    if full is None:
        return None
    lesson, reduced, symbols, columns = full
    names = [str(symbol) for symbol in symbols]
    if len(names) != len(variables):
        # A letter that is not one of the unknowns (a parameter) is left to the
        # previous path, which reports parameter systems as unsupported.
        return None

    homogeneous = all(reduced[row, columns] == 0 for row in range(reduced.rows))
    pivots, rank, rank_augmented = _system_ranks(reduced, columns)
    count = len(names)
    if rank == rank_augmented == count and not homogeneous:
        return None

    card = SolveResult()
    if homogeneous:
        card.add(Step(left=node, right=None, key="lesson_disc_system_homogeneous_first"))
    card.extend(lesson)

    if rank < rank_augmented:
        row, value = _contradiction_row(reduced, columns)
        row_node = from_sympy(reduced.row(row))
        value_node = from_sympy(value)
        contradiction = CoreNode.node(T.EQUALS, CoreNode.constant("0"), value_node)
        card.add(
            Step(
                left=row_node,
                right=contradiction,
                key="lesson_disc_system_contradiction_row",
                args=[CoreNode.constant(str(row + 1)), value_node],
            )
        )
        card.add(
            Step(
                left=None,
                right=None,
                key="lesson_disc_system_rank_inconsistent",
                args=[CoreNode.constant(str(rank)), CoreNode.constant(str(rank_augmented))],
            )
        )
        card.header = "system_gauss_jordan"
        card.set_solution(CoreNode.empty())
        return card, homogeneous

    if rank == count:
        card.add(
            Step(
                left=None,
                right=None,
                key="lesson_disc_system_rank_homogeneous_unique",
                args=[CoreNode.constant(str(count))],
            )
        )
        answer = CoreNode.node(
            T.LIST,
            *[
                CoreNode.node(T.EQUALS, CoreNode.variable(name), CoreNode.constant("0"))
                for name in names
            ],
        )
        card.header = "system_gauss_jordan"
        card.set_solution(answer)
        return card, homogeneous

    free_columns = [column for column in range(columns) if column not in _pivot_columns(pivots)]
    free_names = [names[column] for column in free_columns]
    free_list = _name_list(free_names)
    basic = _basic_expressions(reduced, columns, pivots, symbols)
    card.add(
        Step(
            left=None,
            right=None,
            key="lesson_disc_system_rank_infinite",
            args=[
                CoreNode.constant(str(rank)),
                CoreNode.constant(str(count)),
                free_list,
                CoreNode.constant(str(count - rank)),
            ],
        )
    )
    if basic:
        card.add(
            Step(
                left=None,
                right=CoreNode.node(
                    T.LIST,
                    *[
                        CoreNode.node(
                            T.EQUALS, CoreNode.variable(names[column]), from_sympy(expression)
                        )
                        for column, expression in sorted(basic.items())
                    ],
                ),
                key="lesson_disc_system_free_unknowns_basic",
                args=[free_list],
            )
        )

    if homogeneous:
        vectors = _fundamental_vectors(columns, free_columns, basic, symbols)
        card.add(
            Step(
                left=None,
                right=CoreNode.node(T.LIST, *vectors),
                key="lesson_disc_system_homogeneous_fss",
                args=[CoreNode.constant(str(len(vectors)))],
            )
        )
        combination = [
            CoreNode.node(T.MULTIPLY, CoreNode.variable(name), vector)
            for name, vector in zip(free_names, vectors, strict=True)
        ]
        card.add(
            Step(
                left=None,
                right=CoreNode.node(
                    T.EQUALS,
                    CoreNode.node(T.LIST, *[CoreNode.variable(name) for name in names]),
                    combination[0] if len(combination) == 1 else CoreNode.node(T.ADD, *combination),
                ),
                key="lesson_disc_system_homogeneous_general",
                args=[free_list],
            )
        )

    card.header = "system_gauss_jordan"
    card.set_solution(_general_answer(names, basic))
    return card, homogeneous


def _system_ranks(reduced: sympy.Matrix, columns: int) -> tuple[list[tuple[int, int]], int, int]:
    """Row/column pivots of the reduced augmented matrix and both ranks."""
    pivots: list[tuple[int, int]] = []
    for row in range(reduced.rows):
        for column in range(columns):
            if reduced[row, column] != 0:
                pivots.append((row, column))
                break
    rank = len(pivots)
    rank_augmented = rank
    for row in range(reduced.rows):
        if any(reduced[row, column] != 0 for column in range(columns)):
            continue
        if any(reduced[row, column] != 0 for column in range(columns, reduced.cols)):
            rank_augmented = rank + 1
            break
    return pivots, rank, rank_augmented


def _contradiction_row(reduced: sympy.Matrix, columns: int) -> tuple[int, sympy.Expr]:
    """First row ``0 = c`` with ``c != 0`` in the reduced augmented matrix."""
    for row in range(reduced.rows):
        if any(reduced[row, column] != 0 for column in range(columns)):
            continue
        for column in range(columns, reduced.cols):
            if reduced[row, column] != 0:
                return row, reduced[row, column]
    raise SolveError("ранги не равны, но противоречивой строки нет")


def _pivot_columns(pivots: list[tuple[int, int]]) -> set[int]:
    return {column for _, column in pivots}


def _basic_expressions(
    reduced: sympy.Matrix, columns: int, pivots: list[tuple[int, int]], symbols: list[sympy.Symbol]
) -> dict[int, sympy.Expr]:
    """Pivot unknown = (right side − free unknowns) / pivot coefficient."""
    basic: dict[int, sympy.Expr] = {}
    for row, pivot in pivots:
        expression = reduced[row, columns]
        for column in range(columns):
            if column != pivot and reduced[row, column] != 0:
                expression -= reduced[row, column] * symbols[column]
        basic[pivot] = sympy.simplify(expression / reduced[row, pivot])
    return basic


def _fundamental_vectors(
    columns: int,
    free_columns: list[int],
    basic: dict[int, sympy.Expr],
    symbols: list[sympy.Symbol],
) -> list[CoreNode]:
    """One vector per free unknown: it is 1, the other free unknowns are 0."""
    vectors: list[CoreNode] = []
    for free in free_columns:
        values = {symbols[column]: 0 for column in free_columns}
        values[symbols[free]] = 1
        components = [
            from_sympy(sympy.simplify(basic[column].subs(values)))
            if column in basic
            else _constant(Fraction(1) if column == free else Fraction(0))
            for column in range(columns)
        ]
        vectors.append(CoreNode.node(T.LIST, *components))
    return vectors


def _general_answer(names: list[str], basic: dict[int, sympy.Expr]) -> CoreNode:
    """Every unknown: basic ones as expressions, free ones as ``z ∈ ℝ``."""
    parts: list[CoreNode] = []
    for index, name in enumerate(names):
        if index in basic:
            parts.append(CoreNode.node(T.EQUALS, CoreNode.variable(name), from_sympy(basic[index])))
        else:
            parts.append(
                CoreNode.node(T.ELEMENT_OF, CoreNode.variable(name), CoreNode.variable("ℝ"))
            )
    if len(parts) == 1:
        return parts[0]
    return CoreNode.node(T.LIST, *parts)


def _name_list(names: list[str]) -> CoreNode:
    if len(names) == 1:
        return CoreNode.variable(names[0])
    return CoreNode.node(T.LIST, *[CoreNode.variable(name) for name in names])


def _gauss_card(node: CoreNode, variables: list[str]) -> SolveResult | None:
    """Карточка Гаусса для систем из четырёх и более уравнений.

    Этапы — само приведение расширенной матрицы (учебник называет это методом
    Гаусса, а «две пары уравнений» работают только для трёх уравнений); ответ
    считается тем же ``sympy``-путём, что и в общем случае.
    """
    from ..teaching_discrete import system_lesson

    try:
        answer = _general_system(
            node, SolveContext(result=SolveResult(), variables=list(variables))
        )
    except SolveError:
        return None
    if answer.type is T.EMPTY:
        return None
    lesson = system_lesson(node)
    if lesson is None:
        return None
    lesson.header = "system_gauss_jordan"
    lesson.set_solution(answer)
    return lesson


def _run_system(
    node: CoreNode,
    variables: list[str],
    action: Callable[[CoreNode, SolveContext], CoreNode],
    header: str = "system_solve_short",
) -> SolveResult:
    """Выполнить способ решения системы в отдельном накопителе.

    ``header`` — название способа: клиент показывает его над шагами, поэтому
    у каждого способа (Крамер, подстановка, сложение) оно своё.
    """
    result = SolveResult()
    ctx = SolveContext(result=result, variables=list(variables))
    result.set_solution(action(node, ctx))
    result.header = header
    return result


def _solution_parts(
    variables: list[str], mapping: dict[sympy.Symbol, sympy.Expr]
) -> list[CoreNode]:
    """Известные присваивания ``x = …``; свободные переменные пропускаются."""
    parts: list[CoreNode] = []
    for name in variables:
        value = mapping.get(sympy.Symbol(name))
        if value is not None:
            parts.append(CoreNode.node(T.EQUALS, CoreNode.variable(name), from_sympy(value)))
    return parts


def system_check(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Проверить, является ли набор значений решением системы.

    Аргументы команды — значения переменных по порядку их появления. Шаги
    ``system_2x2_check``/``system_3x3_check_sol`` и вердикт
    ``system_2x2_check_t_vert_arg``/``_f_vert_arg`` (или ``system_3x3_check_t``/
    ``_f``). Ответ — «Истина»/«Ложь».
    """
    if node.type is not T.SYSTEM:
        raise SolveError("проверка решения — у системы")
    if len(args) != len(ctx.variables):
        raise SolveError("нужно значение для каждой переменной")
    substitution = {
        sympy.Symbol(name): to_sympy(value) for name, value in zip(ctx.variables, args, strict=True)
    }

    satisfies = True
    for child in node.children:
        if child.type is not T.EQUALS or len(child.children) != 2:
            raise SolveError("в системе должны быть уравнения")
        left = to_sympy(child.children[0]).subs(substitution)
        right = to_sympy(child.children[1]).subs(substitution)
        holds = sympy.simplify(left - right) == 0
        if not (holds is True or holds is sympy.true):
            satisfies = False
            break

    answer = boolean_node(satisfies)
    if len(ctx.variables) == 2:
        ctx.result.add(Step(left=node, right=None, key="system_2x2_check"), [_HEADER])
        key = "system_2x2_check_t_vert_arg" if satisfies else "system_2x2_check_f_vert_arg"
        ctx.result.add(Step(left=node, right=answer, key=key, args=list(args)), [_HEADER])
    elif len(ctx.variables) == 3:
        ctx.result.add(Step(left=node, right=None, key="system_3x3_check_sol"), [_HEADER])
        key = "system_3x3_check_t" if satisfies else "system_3x3_check_f"
        ctx.result.add(Step(left=node, right=answer, key=key), [_HEADER])
    else:
        raise SolveError("проверка поддерживается для систем 2×2 и 3×3")
    return answer


def _inequality_system(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Система неравенств (и уравнений): пересечение множеств решений."""
    ctx.require(len(ctx.variables) == 1, "система неравенств: одна неизвестная")
    symbol = sympy.Symbol(ctx.variables[0])
    sets = [_relation_set(child, symbol) for child in node.children]
    combined = sets[0] if len(sets) == 1 else sympy.Intersection(*sets)
    answer = from_sympy(sympy.simplify(combined))
    ctx.result.add(Step(left=node, right=answer, key="intersection"), [_HEADER])
    return answer


def _relation_set(child: CoreNode, symbol: sympy.Symbol) -> sympy.Set:
    """Множество решений одного элемента системы."""
    if child.type is T.EQUALS and len(child.children) == 2:
        equation = sympy.Eq(to_sympy(child.children[0]), to_sympy(child.children[1]))
        return sympy.solveset(equation, symbol, sympy.S.Reals)
    if child.type in _RELATIONS and len(child.children) == 2:
        left = to_sympy(child.children[0])
        right = to_sympy(child.children[1])
        return sympy.solveset(_relation(child.type, left, right), symbol, sympy.S.Reals)
    raise SolveError("система содержит неподдерживаемый элемент")


def _relation(node_type: T, left: sympy.Expr, right: sympy.Expr) -> sympy.Rel:
    """Отношение как объект sympy."""
    if node_type is T.LESS_THAN:
        return sympy.Lt(left, right)
    if node_type is T.LESS_THAN_EQUAL:
        return sympy.Le(left, right)
    if node_type is T.GREATER_THAN:
        return sympy.Gt(left, right)
    if node_type is T.GREATER_THAN_EQUAL:
        return sympy.Ge(left, right)
    return sympy.Ne(left, right)


__all__ = [
    "solve_system",
    "system_check",
    "system_methods",
]
