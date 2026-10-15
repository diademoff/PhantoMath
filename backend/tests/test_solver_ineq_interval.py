"""Тесты неравенств на отрезке методом интервалов (B/R9).

Команда ``inequality_on_interval`` (границы — аргументы) решает любое
неравенство, включая тригонометрические, на отрезке; ответ — промежуток или
объединение (шаг ``ineq_solve_short``).
"""

from __future__ import annotations

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.solver import solve


def run(source: str, lower: str, upper: str) -> tuple[list[str], CoreNode]:
    vertical = solve(
        parse_protocol(source),
        command="inequality_on_interval",
        args=[parse_protocol(lower), parse_protocol(upper)],
    ).result.vertical()
    assert vertical is not None and vertical.solution is not None
    keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
    return keys, vertical.solution


class TestInequalityOnInterval:
    def test_trig_sine(self) -> None:
        # sin x > 1/2 на [0, 2π] -> (π/6, 5π/6).
        keys, solution = run("{gt({sin({x})},{frac({1},{2})})}", "{0}", "{2*pi}")
        assert keys == ["ineq_solve_short"]
        assert solution.type is T.OPEN_OPEN_INTERVAL
        assert solution.children[0].to_contract() == {
            "type": "FRACTION",
            "children": [{"type": "CONSTANT", "value": "π"}, {"type": "CONSTANT", "value": "6"}],
        }

    def test_trig_cosine(self) -> None:
        # cos x < 0 на [0, 2π] -> (π/2, 3π/2).
        _, solution = run("{lt({cos({x})},{0})}", "{0}", "{2*pi}")
        assert solution.type is T.OPEN_OPEN_INTERVAL
        assert solution.children[0].children[1].value == "2"

    def test_closed_endpoints(self) -> None:
        # x² ≤ 4 -> [−2, 2]; x² < 4 -> (−2, 2).
        _, closed = run("{lte({x^2},{4})}", "{-5}", "{5}")
        _, opened = run("{lt({x^2},{4})}", "{-5}", "{5}")
        assert closed.type is T.CLOSED_CLOSED_INTERVAL
        assert opened.type is T.OPEN_OPEN_INTERVAL

    def test_rational_pole(self) -> None:
        # 1/(x−2) > 0 на [−5, 5] -> (2, 5].
        _, solution = run("{gt({frac({1},{x-2})},{0})}", "{-5}", "{5}")
        assert solution.type is T.OPEN_CLOSED_INTERVAL
