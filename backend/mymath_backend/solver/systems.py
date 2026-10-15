"""Системы двух линейных уравнений с двумя неизвестными.

Модуль зарегистрирован на узел ``SYSTEM``. Каждое уравнение приводится к
линейной форме ``a·u + b·v + c = 0``, система решается правилом Крамера.
Ответ — список ``x = …, y = …``.

Поддерживаются только линейные системы (произведение неизвестных, степени и
функции отклоняются) и только системы 2×2. Общий случай (метод Гаусса,
``n×n``, параметрические решения) — следующие модули.

Шаг один — ключ ``system_2x2_solve_elimination`` с заголовком
``system_solve_short``; при нулевом определителе система не имеет
единственного решения и это ошибка.
"""

from __future__ import annotations

from fractions import Fraction

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .arithmetic import as_fraction, format_number
from .base import SolveContext, SolveError, Step, solver_for

_HEADER = CoreRichText(type="system_solve_short")

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
    """Решить систему 2×2 линейных уравнений."""
    ctx.require(len(node.children) == 2, "поддерживаются системы из двух уравнений")
    ctx.require(
        len(ctx.variables) == 2,
        "поддерживаются системы с двумя неизвестными",
    )
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


__all__ = [
    "solve_system",
]
