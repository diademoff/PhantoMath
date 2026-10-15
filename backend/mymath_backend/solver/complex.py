"""Комплексные числа.

Мнимая единица — константа ``i`` (**CONSTANT** ``"i"``). Модуль
зарегистрирован на ``REAL`` (``Re``), ``IMAGINARY`` (``Im``) и ``CONJUGATE``
(сопряжение): все три считаются через sympy мостом.

Арифметику с ``i`` берёт на себя тот же мост: выражение с ``i`` решается
``sympy.simplify`` (в ``solver/__init__.py`` есть отдельная ветка), поэтому
``(1+2i)(3−i)`` приводится к стандартному виду.

Ключи шагов: ``complex_rewrite`` (Re/Im), ``complex_conjugate`` (сопряжение),
``complex_convert_std_form`` (арифметика с ``i``).
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step, solver_for
from .sympy_bridge import from_sympy, to_sympy

_IMAGINARY = "i"

_KEY: dict[T, str] = {
    T.REAL: "complex_rewrite",
    T.IMAGINARY: "complex_rewrite",
    T.CONJUGATE: "complex_conjugate",
}


def contains_imaginary(node: CoreNode) -> bool:
    """Есть ли в выражении мнимая единица."""
    return any(
        item.type is T.CONSTANT and (item.value or "").strip() == _IMAGINARY for item in node.walk()
    )


def solve_imaginary_arithmetic(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Привести выражение с ``i`` к стандартному виду через sympy."""
    result = from_sympy(sympy.simplify(to_sympy(node)))
    ctx.result.add(Step(left=node, right=result, key="complex_convert_std_form"))
    return result


def complex_power(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Возвести комплексное число в целую степень (формула Муавра).

    Аргумент команды — целый показатель; шаг ``complex_pow_polar_moivre_simple``.
    """
    exponent = _integer_argument(args)
    value = to_sympy(node)
    if value.is_number is not True or value.is_real is True:
        raise SolveError("степень берётся у комплексного числа")
    result = from_sympy(sympy.simplify(value**exponent))
    ctx.result.add(Step(left=node, right=result, key="complex_pow_polar_moivre_simple"))
    return result


def complex_roots(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Извлечь корни n-й степени из комплексного числа.

    Аргумент — натуральная степень ``n``; ответ — множество из ``n`` корней
    (шаг ``complex_find_root_polar``).
    """
    degree = _integer_argument(args)
    if degree < 1:
        raise SolveError("степень корня — натуральное число")
    value = to_sympy(node)
    if value.is_number is not True:
        raise SolveError("корни извлекаются из числа")
    unknown = sympy.Symbol("_z")
    try:
        found = sympy.solve(sympy.Eq(unknown**degree, value), unknown)
    except (NotImplementedError, TypeError, ValueError) as error:
        raise SolveError("корни не выражаются") from error
    if not found:
        raise SolveError("корни не выражаются")
    answer = from_sympy(sympy.FiniteSet(*found))
    ctx.result.add(Step(left=node, right=answer, key="complex_find_root_polar"))
    return answer


def _integer_argument(args: list[CoreNode]) -> int:
    """Целый аргумент команды."""
    if len(args) != 1 or args[0].type is not T.CONSTANT or args[0].value is None:
        raise SolveError("нужен целый аргумент")
    text = args[0].value.strip()
    if not text.lstrip("-").isdigit():
        raise SolveError("нужен целый аргумент")
    return int(text)


@solver_for(T.REAL, T.IMAGINARY, T.CONJUGATE)
def solve_complex(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Re, Im или сопряжение комплексного числа."""
    ctx.require(len(node.children) == 1, "операция над комплексным числом")
    value = to_sympy(node.children[0])
    if node.type is T.REAL:
        computed = sympy.re(value)
    elif node.type is T.IMAGINARY:
        computed = sympy.im(value)
    else:
        computed = sympy.conjugate(value)

    result = from_sympy(sympy.simplify(computed))
    ctx.result.add(Step(left=node, right=result, key=_KEY[node.type]))
    return result


__all__ = [
    "complex_power",
    "complex_roots",
    "contains_imaginary",
    "solve_complex",
    "solve_imaginary_arithmetic",
]
