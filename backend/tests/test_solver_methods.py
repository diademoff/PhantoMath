"""Тесты общего механизма выбора способа решения (``solver/methods.py``).

Раньше ``solve`` знал про способы жёстко (уравнения и системы по отдельным
функциям). Теперь провайдеры регистрируются по типу узла; эти тесты
фиксируют и сам реестр, и наблюдаемое поведение: несколько записей
вертикальной ветки плюс подпись переключателя ``selectMethodText``.
"""

from __future__ import annotations

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.results import CoreSolverGroup, ResultGroupType
from mymath_backend.solver import solve
from mymath_backend.solver.methods import has_method_provider, method_types


def vertical(source: str) -> CoreSolverGroup:
    group = solve(parse_protocol(source)).result.group(ResultGroupType.VERTICAL)
    assert group is not None
    return group


class TestMethodRegistry:
    def test_registered_types(self) -> None:
        assert has_method_provider(T.EQUALS)
        assert has_method_provider(T.SYSTEM)
        assert T.EQUALS in method_types()

    def test_equation_with_alternatives(self) -> None:
        group = vertical("{=({x^2-5x+6},{0})}")
        # Квадратное с рациональными корнями: формула и разложение.
        assert len(group.entries) >= 2
        assert group.select_method_text is not None
        assert group.select_method_text.type == "select_method"

    def test_single_method_has_no_switcher(self) -> None:
        group = vertical("{=({x+1},{2})}")
        # Линейное с единичным коэффициентом — один способ, переключателя нет.
        assert len(group.entries) == 1
        assert group.select_method_text is None


class TestSystemMethods:
    def test_system_with_alternatives(self) -> None:
        def c(value: str) -> CoreNode:
            return CoreNode.constant(value)

        problem = CoreNode.node(
            T.SYSTEM,
            CoreNode.node(
                T.EQUALS,
                CoreNode.node(T.ADD, CoreNode.variable("x"), CoreNode.variable("y")),
                c("3"),
            ),
            CoreNode.node(
                T.EQUALS,
                CoreNode.node(T.SUBTRACT, CoreNode.variable("x"), CoreNode.variable("y")),
                c("1"),
            ),
        )
        group = solve(problem).result.group(ResultGroupType.VERTICAL)
        assert group is not None
        assert len(group.entries) >= 2
        assert group.select_method_text is not None
