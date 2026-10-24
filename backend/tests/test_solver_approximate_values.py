"""Non-table angles and bare irrational roots get an approximate value.

``sin 2°`` answers ``≈ 0.0348995`` (six significant digits) with a ``calculate_short``
card; a bare ``√3`` keeps the exact form and adds ``≈ 1.73205``, like ``5^0.5``. Table
angles stay exact.
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import solve


def vertical_of(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source)).result.vertical()
    assert vertical is not None
    return vertical


def stage_keys(vertical: CoreSolverVerticalResult) -> list[str]:
    return [sub.description.type for step in vertical.steps for sub in step.substeps]


class TestApproximateAngle:
    @pytest.mark.parametrize(
        "source, expected",
        [
            ("{sin({deg({2})})}", "0.0348995"),
            ("{sin({deg({1})})}", "0.0174524"),
            ("{sin({deg({0.5})})}", "0.00872654"),
            ("{cos({deg({2})})}", "0.999391"),
            ("{cos({deg({0.5})})}", "0.999962"),
            ("{tan({deg({2})})}", "0.0349208"),
            ("{tan({deg({3})})}", "0.0524078"),
        ],
    )
    def test_six_significant_digits(self, source: str, expected: str) -> None:
        vertical = vertical_of(source)
        solution = vertical.solution
        assert solution is not None and solution.type is T.APPROXIMATE_SIGN
        assert solution.children[0].value == expected
        assert vertical.header is not None and vertical.header.type == "calculate_short"
        assert stage_keys(vertical) == ["calculate"]

    @pytest.mark.parametrize(
        "source, expected",
        [
            ("{sin({deg({30})})}", "1/2"),
            ("{cos({deg({60})})}", "1/2"),
            ("{tan({deg({45})})}", "1"),
            ("{sin({deg({0})})}", "0"),
        ],
    )
    def test_table_angles_stay_exact(self, source: str, expected: str) -> None:
        solution = vertical_of(source).solution
        assert solution is not None and solution.type is T.CONSTANT
        assert solution.value == expected


class TestBareIrrationalRoot:
    def test_root_three_gets_the_decimal_form(self) -> None:
        # The same answer node as 5^0.5: alt_form(√3, ≈ 1.73205).
        vertical = vertical_of("{root2({3})}")
        solution = vertical.solution
        assert solution is not None and solution.type is T.ALTERNATIVE_FORM
        root, approximate = solution.children
        assert root.type is T.ROOT2 and root.children[0].value == "3"
        assert approximate.type is T.APPROXIMATE_SIGN
        assert approximate.children[0].value == "1.73205"
        assert stage_keys(vertical) == ["calculate"]

    def test_perfect_square_stays_a_number(self) -> None:
        solution = vertical_of("{root2({16})}").solution
        assert solution is not None and solution.type is T.CONSTANT and solution.value == "4"

    def test_factor_is_still_pulled_out(self) -> None:
        solution = vertical_of("{root2({12})}").solution
        assert solution is not None and solution.type is T.MULTIPLY_IMPLICIT
        assert solution.children[1].type is T.ROOT2

    def test_root_inside_a_larger_expression_is_unchanged(self) -> None:
        solution = vertical_of("{root2({3})+1}").solution
        assert solution is not None and solution.type is T.ADD
        roots = [child for child in solution.children if child.type is T.ROOT2]
        assert roots and roots[0].children[0].value == "3"
