"""Системы: два линейных уравнения 2×2 или система неравенств.

Модуль зарегистрирован на узел ``SYSTEM``. Если среди элементов есть знак
отношения, это **система неравенств**: множества решений элементов (через
``solveset``) пересекаются, ответ — промежуток (шаг ``intersection_plural``).
Иначе — уравнения: система 2×2 линейных решается правилом Крамера
(``system_2x2_solve_elimination``), прочие (3×3 и выше, нелинейные, с
параметром) — через ``sympy.solve`` (шаг ``system_3x3_rem_vars`` или
``system_2x2_solve_substitution``). Параметрические решения пока не
поддерживаются.
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
    if node.type is T.DIVIDE:
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

    if len(node.children) == 2 and len(ctx.variables) == 2:
        try:
            return _cramer_2x2(node, ctx)
        except SolveError:
            pass
    return _general_system(node, ctx)


def _cramer_2x2(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Система 2×2 линейных уравнений правилом Крамера."""
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

    solution = CoreNode.node(
        T.LIST,
        CoreNode(
            type=T.EQUALS,
            children=[CoreNode.variable(first_var), CoreNode.constant(format_number(u))],
        ),
        CoreNode(
            type=T.EQUALS,
            children=[CoreNode.variable(second_var), CoreNode.constant(format_number(v))],
        ),
    )
    ctx.result.add(Step(left=node, right=None, key="system_2x2_cramer_rule"), [_HEADER])
    ctx.result.add(Step(left=node, right=solution, key="system_2x2_solve_elimination"), [_HEADER])
    return solution


def _addition_2x2(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Система 2×2 линейных способом сложения (исключение переменной).

    Уравнения домножаются так, чтобы коэффициенты при первой неизвестной
    совпали; сложение убирает её, оставшаяся неизвестная находится, вторая —
    подстановкой. Шаг ``system_2x2_add_eqs``.
    """
    first_var, second_var = ctx.variables
    index = {first_var: 0, second_var: 1}
    first = _equation_form(node.children[0], index)
    second = _equation_form(node.children[1], index)
    a1, b1 = first[0]
    a2, b2 = second[0]
    determinant = a1 * b2 - a2 * b1
    if determinant == 0:
        raise SolveError("система не имеет единственного решения")

    rhs1, rhs2 = -first[1], -second[1]
    u = (rhs1 * b2 - rhs2 * b1) / determinant
    v = (a1 * rhs2 - a2 * rhs1) / determinant
    solution = CoreNode.node(
        T.LIST,
        CoreNode(type=T.EQUALS, children=[CoreNode.variable(first_var), _constant(u)]),
        CoreNode(type=T.EQUALS, children=[CoreNode.variable(second_var), _constant(v)]),
    )
    ctx.result.add(Step(left=node, right=solution, key="system_2x2_add_eqs"), [_HEADER])
    return solution


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
    return solution


def system_methods(node: CoreNode, variables: list[str]) -> list[SolveResult]:
    """Способы решения системы: Крамер (2×2 линейная) и подстановка (sympy).

    Система неравенств решается единственным способом. Первый способ — основной,
    дальше — альтернативы (переключатель ``selectMethodText``).
    """
    if any(child.type in _RELATIONS for child in node.children):
        return [_run_system(node, variables, solve_system)]
    methods: list[SolveResult] = []
    if len(node.children) == 2 and len(variables) == 2:
        with contextlib.suppress(SolveError):
            methods.append(_run_system(node, variables, _cramer_2x2))
    methods.append(_run_system(node, variables, _general_system))
    if len(node.children) == 2 and len(variables) == 2:
        with contextlib.suppress(SolveError):
            methods.append(_run_system(node, variables, _addition_2x2))
    return methods


def _run_system(
    node: CoreNode, variables: list[str], action: Callable[[CoreNode, SolveContext], CoreNode]
) -> SolveResult:
    """Выполнить способ решения системы в отдельном накопителе."""
    result = SolveResult()
    ctx = SolveContext(result=result, variables=list(variables))
    result.set_solution(action(node, ctx))
    result.header = "system_solve_short"
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
    ctx.result.add(Step(left=node, right=answer, key="intersection_plural"), [_HEADER])
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
