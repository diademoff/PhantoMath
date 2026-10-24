"""Ключи перестановки строк в обратной матрице.

Ключи ``matrix_inv_reorder``/``matrix_inv_swap`` появляются в карточке
обратной матрицы, когда для ведущего элемента нужен обмен строк.
"""

from __future__ import annotations

from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult, ResultGroupType
from mymath_backend.solver import solve


def _entries(proto: str) -> list[CoreSolverVerticalResult]:
    data = solve(parse_protocol(proto))
    group = data.result.group(ResultGroupType.VERTICAL)
    assert group is not None
    return [
        CoreSolverVerticalResult.from_contract(entry.result)
        for entry in group.entries
        if entry.result and "steps" in entry.result
    ]


def _keys(vertical: CoreSolverVerticalResult) -> set[str]:
    found: set[str] = set()
    for step in vertical.steps:
        found.update(header.type for header in step.step_headers)
        for sub in step.substeps:
            assert sub.description is not None
            found.add(sub.description.type)
            if sub.subresult is not None:
                found.update(_keys(sub.subresult))
    return found


def test_zero_pivot_inverse_reorders_rows() -> None:
    entries = _entries("{mat({mat_row({1},{2})},{mat_row({3},{0})})}")
    assert len(entries) >= 2
    found = _keys(entries[1])
    assert {
        "matrix_inv_reorder",
        "matrix_inv_reorder_rows",
        "matrix_inv_swap",
        "matrix_inv_swap_row",
    } <= found


def test_singular_inverse_keeps_the_verdict_keys() -> None:
    entries = _entries("{mat({mat_row({1},{2})},{mat_row({2},{4})})}")
    found = _keys(entries[1])
    assert {
        "matrix_inv_doesnt_exist",
        "matrix_inv_no_inv",
    } <= found
