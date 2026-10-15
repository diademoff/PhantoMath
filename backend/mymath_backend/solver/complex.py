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
from .base import SolveContext, Step, solver_for
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
    "contains_imaginary",
    "solve_complex",
    "solve_imaginary_arithmetic",
]
