"""Тесты полярной формы комплексного числа (L): команда ``polar``.

``z = r(cos φ + i sin φ)``, где ``r = |z|``, ``φ = arg z`` (шаг
``write_polar_form``).
"""

from __future__ import annotations

from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.solver import solve


def _vertical(source: str) -> CoreSolverVerticalResult:
    vertical = solve(parse_protocol(source), command="polar").result.vertical()
    assert vertical is not None
    return vertical


class TestPolar:
    def test_imaginary_unit(self) -> None:
        answer = _vertical("{\\i}").solution
        assert answer is not None and answer.type is T.MULTIPLY_IMPLICIT
        assert answer.children[1].type is T.BRACKET

    def test_general(self) -> None:
        answer = _vertical("{1+2*\\i}").solution
        assert answer is not None
        assert answer.children[0].type is T.ROOT2
        assert answer.children[1].children[0].type is T.ADD

    def test_real_number_has_angle_zero(self) -> None:
        # Действительное число — тоже комплексное: z = r(cos 0 + i sin 0).
        vertical = _vertical("{3}")
        answer = vertical.solution
        assert answer is not None and answer.type is T.MULTIPLY_IMPLICIT
        assert answer.children[0].value == "3"
        inner = answer.children[1].children[0]
        assert inner.type is T.ADD and inner.children[0].children[0].value == "0"
