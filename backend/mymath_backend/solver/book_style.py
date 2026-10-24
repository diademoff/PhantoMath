"""The book's way of writing products: ``Ce^{−x}``, ``(x − 1)eˣ``, ``2x``.

A dot between factors is only written before a number (``x·2ˣ``, ``2·3``):
the reader sees a product of a function and a letter without one. The cards
are built from SymPy expressions, where every product is ``MULTIPLY``; this
helper turns those into ``MULTIPLY_IMPLICIT`` before the student sees them.

Used by the differential-equation cards and by the textbook integral cards
(which also nest inside the ODE ones).
"""

from __future__ import annotations

import dataclasses

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveResult

__all__ = ["book_card", "book_products", "starts_with_number"]


def book_products(node: CoreNode | None) -> CoreNode | None:
    """``Ce^(−x)``, ``(x − 1)eˣ``, ``Cx`` without a dot; the dot stays before a digit or a minus."""
    if node is None or not node.children:
        return node
    children = [book_products(child) or child for child in node.children]
    kind = node.type
    if kind is T.MULTIPLY and len(children) == 2 and not starts_with_number(children[1]):
        kind = T.MULTIPLY_IMPLICIT
    return dataclasses.replace(node, type=kind, children=children)


def starts_with_number(node: CoreNode) -> bool:
    """Whether ``node`` reads as a number (``2``, ``−3``, ``2x``) and keeps the dot before it."""
    if node.type is T.NEGATIVE:
        return True
    if node.type is T.CONSTANT:
        return (node.value or "")[:1].isdigit()
    if node.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT, T.POWER) and node.children:
        return starts_with_number(node.children[0])
    return False


def book_card(card: SolveResult) -> SolveResult:
    """Write every formula of a card as in the book (stages, details and the answer)."""
    for step in card:
        step.left = book_products(step.left)
        step.right = book_products(step.right)
        # The formula parts of the stage text are written the same way.
        step.args = [book_products(arg) or arg for arg in step.args]
        if step.subresult is not None:
            book_card(step.subresult)
    if card.solution is not None:
        card.solution = book_products(card.solution) or card.solution
    return card
