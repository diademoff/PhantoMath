"""Ключи карточек матриц и определителей.

Сложение матриц, обратная матрица 4×4 методом Гаусса, матричное уравнение,
определитель с разложением по столбцу и проверка ``A·A⁻¹ = I``. Ключи —
только из существующего словаря.
"""

from __future__ import annotations

from mymath_backend.input import parse_protocol
from mymath_backend.results import (
    CoreSolverVerticalResult,
    CoreSolverVerticalStep,
    ResultGroupType,
)
from mymath_backend.solver import solve


def _entries(proto: str, command: str | None = None) -> list[CoreSolverVerticalResult]:
    data = solve(parse_protocol(proto), command=command)
    group = data.result.group(ResultGroupType.VERTICAL)
    assert group is not None
    return [
        CoreSolverVerticalResult.from_contract(entry.result)
        for entry in group.entries
        if entry.result and "steps" in entry.result
    ]


def _keys(vertical: CoreSolverVerticalResult) -> list[str]:
    keys: list[str] = []
    for step in vertical.steps:
        for sub in step.substeps:
            assert sub.description is not None
            keys.append(sub.description.type)
            if sub.subresult is not None:
                keys.extend(_keys(sub.subresult))
    return keys


def _headers(step: CoreSolverVerticalStep) -> list[str]:
    return [header.type for header in step.step_headers]


def _everything(vertical: CoreSolverVerticalResult) -> set[str]:
    found = set(_keys(vertical))
    for step in vertical.steps:
        found.update(_headers(step))
        for sub in step.substeps:
            if sub.subresult is not None:
                found.update(_everything(sub.subresult))
    return found


def test_matrix_addition_uses_the_pm_header() -> None:
    source = (
        "{mat({mat_row({1},{2})},{mat_row({3},{4})})+mat({mat_row({1},{0})},{mat_row({0},{1})})}"
    )
    vertical = _entries(source)[0]
    assert _headers(vertical.steps[0]) == ["matrix_add_elements_smpl"]
    assert vertical.steps[0].substeps[0].description.type == "matrix_add_elements"


def test_inverse_4x4_uses_the_gauss_card() -> None:
    source = (
        "{mat({mat_row({1},{2},{3},{4})},{mat_row({0},{1},{0},{0})},"
        "{mat_row({0},{0},{1},{0})},{mat_row({0},{0},{0},{1})})}"
    )
    keys = _keys(_entries(source, "matrix_inverse")[0])
    assert {
        "matrix_inv_use_notation",
        "matrix_inv_write_right",
        "matrix_inv_find_identity",
        "matrix_inv_right_is_inv",
    } <= set(keys)


def test_matrix_equation_writes_the_system_and_ordered_pairs() -> None:
    source = (
        "{=({mul({mat({mat_row({1},{2})},{mat_row({3},{4})})},"
        "{mat({mat_row({x},{z})},{mat_row({y},{w})})})},"
        "{mat({mat_row({5},{6})},{mat_row({7},{8})})})}"
    )
    entries = _entries(source, "matrix_equation")
    keys = _keys(entries[0])
    assert {
        "matrix_mul_row_col",
        "matrix_eq_set_elements_equal",
        "matrix_eq_write_as_system",
        "matrix_eq_ordered_pair_values",
        "system_solve",
    } <= set(keys)


def test_bare_matrix_adds_the_inverse_verification_card() -> None:
    entries = _entries("{mat({mat_row({1},{2})},{mat_row({3},{4})})}")
    assert len(entries) >= 2
    assert {
        "matrix_inv_eq",
        "matrix_inv_eq_mul_by_inv",
        "matrix_inv_eq_mul_by_inv_smpl",
        "matrix_inv_eq_set_identity",
        "matrix_inv_eq_set_identity_smpl",
        "matrix_mul_each_elem",
        "matrix_mul_row_col",
    } <= _everything(entries[1])


def test_singular_inverse_has_the_two_verdict_keys() -> None:
    entries = _entries("{mat({mat_row({1},{2})},{mat_row({2},{4})})}", "matrix_inverse")
    found = _everything(entries[0])
    assert {
        "matrix_inv_det_zero",
        "matrix_inv_doesnt_exist",
        "matrix_inv_no_inv",
    } <= found


def test_determinant_can_expand_along_a_column() -> None:
    # column 2 has two zeros, more than any row: the column expansion.
    source = "{det3({1},{0},{2},{3},{0},{4},{5},{1},{6})}"
    vertical = _entries(source)[0]
    keys = _keys(vertical)
    assert "det_laplace_rule_col" in keys
    headers = [header for step in vertical.steps for header in _headers(step)]
    assert "det_laplace_rule_col_simple" in headers
