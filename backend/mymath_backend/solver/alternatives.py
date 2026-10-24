"""Alternative forms of an answer, as the app shows them under the solution.

A rational answer is also given as a decimal and, when improper, as a mixed number; an irrational
real one as a decimal approximation; an answer typed with decimals as a common fraction.
``x = 22/5`` becomes ``x = 4.4`` and ``x = 4 2/5``; a list of roots keeps its shape.
"""

from __future__ import annotations

from collections.abc import Callable

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .sympy_bridge import to_sympy

_PRECISION = 6


def _terminates(denominator: int) -> bool:
    for factor in (2, 5):
        while denominator % factor == 0:
            denominator //= factor
    return denominator == 1


def _decimal(value: sympy.Expr) -> CoreNode | None:
    """The decimal form of a real, non-integer number: exact when it terminates, else ``≈``."""
    if isinstance(value, sympy.Rational) and _terminates(int(value.q)):
        return CoreNode.constant(_exact(value))
    approximate = sympy.N(value, _PRECISION + 4)
    text = f"{float(approximate):.{_PRECISION}f}".rstrip("0").rstrip(".")
    return CoreNode.node(T.APPROXIMATE_SIGN, CoreNode.constant(text))


def _exact(value: sympy.Rational) -> str:
    """``22/5`` -> ``4.4``."""
    sign = "-" if value < 0 else ""
    top, bottom = abs(int(value.p)), int(value.q)
    digits = 0
    while bottom != 1 and digits < 30:
        top *= 10
        digits += 1
        if top % bottom == 0:
            break
    whole = top // bottom
    text = str(whole).rjust(digits + 1, "0")
    return sign + (text[:-digits] + "." + text[-digits:] if digits else text)


def _mixed(value: sympy.Expr) -> CoreNode | None:
    """``22/5`` -> ``4 2/5`` for an improper fraction."""
    if not (isinstance(value, sympy.Rational) and value.q > 1 and abs(value) > 1):
        return None
    whole, rest = divmod(abs(int(value.p)), int(value.q))
    if rest == 0:
        return None
    mixed = CoreNode.node(
        T.FRACTION_MIXED,
        CoreNode.constant(str(whole)),
        CoreNode.constant(str(rest)),
        CoreNode.constant(str(int(value.q))),
    )
    return CoreNode.node(T.NEGATIVE, mixed) if value < 0 else mixed


def _fraction(value: sympy.Expr) -> CoreNode | None:
    """A rational answer typed as a decimal gets its common fraction."""
    if isinstance(value, sympy.Rational) and value.q > 1:
        return CoreNode.constant(f"{int(value.p)}/{int(value.q)}")
    return None


def _real_value(node: CoreNode) -> sympy.Expr | None:
    try:
        value = to_sympy(node)
    except Exception:
        return None
    if not isinstance(value, sympy.Expr) or value.free_symbols:  # matrices, sets
        return None
    if not value.is_real or value.is_Integer:
        return None
    return value


def _mapped(solution: CoreNode, make: Callable[[sympy.Expr], CoreNode | None]) -> CoreNode | None:
    """Rebuild the answer with every value replaced by ``make(value)``; ``None`` if any fails."""
    if solution.type is T.LIST and solution.children:
        parts = [_mapped(child, make) for child in solution.children]
        return None if any(p is None for p in parts) else CoreNode.node(T.LIST, *parts)  # type: ignore[arg-type]
    if solution.type is T.EQUALS and len(solution.children) == 2:
        converted = _mapped(solution.children[1], make)
        return (
            None if converted is None else CoreNode.node(T.EQUALS, solution.children[0], converted)
        )
    value = _real_value(solution)
    return None if value is None else make(value)


def alternative_forms(solution: CoreNode, *, typed_decimal: bool) -> list[CoreNode]:
    """Alternative forms of ``solution``: decimal, mixed number, or common fraction."""
    makers: list[Callable[[sympy.Expr], CoreNode | None]] = []
    if typed_decimal:
        makers.append(_fraction)
    else:
        makers += [_decimal, _mixed]
    forms: list[CoreNode] = []
    for make in makers:
        form = _mapped(solution, make)
        # the typed-decimal answer is printed as a decimal later, so its fraction always differs
        if form is not None and (typed_decimal or not form.structural_eq(solution)):
            forms.append(form)
    return forms


__all__ = ["alternative_forms"]
