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

from fractions import Fraction

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .arithmetic import as_fraction, format_number
from .base import SolveContext, SolveError, Step, solver_for
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
    ctx.result.add(Step(left=node, right=solution, key="system_2x2_solve_elimination"), [_HEADER])
    return solution


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
        raise SolveError("система не имеет решений")

    answers = [_solution_node(ctx.variables, mapping) for mapping in found]
    solution = answers[0] if len(answers) == 1 else CoreNode.node(T.LIST, *answers)
    key = "system_3x3_rem_vars" if len(ctx.variables) >= 3 else "system_2x2_solve_substitution"
    ctx.result.add(Step(left=node, right=solution, key=key), [_HEADER])
    return solution


def _solution_node(variables: list[str], mapping: dict[sympy.Symbol, sympy.Expr]) -> CoreNode:
    """Одно решение системы: ``x = …, y = …`` (или ``x = …``)."""
    parts: list[CoreNode] = []
    for name in variables:
        value = mapping.get(sympy.Symbol(name))
        if value is None:
            raise SolveError("параметрические решения системы пока не поддерживаются")
        parts.append(CoreNode.node(T.EQUALS, CoreNode.variable(name), from_sympy(value)))
    return CoreNode.node(T.LIST, *parts) if len(parts) > 1 else parts[0]


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
]
