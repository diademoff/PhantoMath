"""Тесты полного разбора конических сечений (F): команда ``conic_details``.

Шаги ``conics_identify``, ``conics_since_*`` и метки ``graph_rt_info_*``
(центр, радиус, вершины, сопряжённые вершины, фокусы, директриса, асимптоты).
"""

from __future__ import annotations

import pytest

from mymath_backend import CoreNode
from mymath_backend import CoreNodeType as T
from mymath_backend.input import parse_protocol
from mymath_backend.solver import SolveError, solve


def run(source: str) -> tuple[list[str], CoreNode]:
    vertical = solve(parse_protocol(source), command="conic_details").result.vertical()
    assert vertical is not None and vertical.solution is not None
    keys = [sub.description.type for step in vertical.steps for sub in step.substeps]
    return keys, vertical.solution


class TestConicDetails:
    def test_shifted_circle(self) -> None:
        keys, solution = run("{=({x^2+y^2-2x+4y-4},{0})}")
        assert keys == [
            "conics_identify",
            "conics_complete_square_both",
            "graph_rt_info_center",
            "conics_since_circle",
            "graph_rt_info_radius",
        ]
        assert solution.type is T.EQUALS

    def test_ellipse(self) -> None:
        keys, _ = run("{=({4x^2+9y^2},{36})}")
        assert "graph_rt_info_vertices" in keys
        assert "graph_rt_info_foci" in keys
        assert "graph_rt_info_co_vertices" in keys

    def test_hyperbola(self) -> None:
        keys, _ = run("{=({x^2-y^2},{1})}")
        assert "graph_rt_info_asymptotes" in keys

    def test_parabola(self) -> None:
        keys, _ = run("{=({x^2},{y})}")
        assert keys == [
            "conics_identify",
            "conics_since_parabola",
            "graph_rt_info_vertex",
            "graph_rt_info_focus",
            "graph_rt_info_directrix",
        ]

    def test_center_point(self) -> None:
        vertical = solve(
            parse_protocol("{=({x^2+y^2-2x+4y-4},{0})}"), command="conic_details"
        ).result.vertical()
        assert vertical is not None
        center_step = next(
            sub
            for step in vertical.steps
            for sub in step.substeps
            if sub.description is not None and sub.description.type == "graph_rt_info_center"
        )
        assert center_step.right is not None and center_step.right.type is T.LIST
        assert [child.value for child in center_step.right.children] == ["1", "-2"]

    def test_rotated_ellipse_is_solved(self) -> None:
        # Член xy больше не отказ: поворот осей даёт канонический вид и точки.
        keys, solution = run("{=({x^2+xy+y^2},{1})}")
        assert "conics_identify_std_form" in keys
        assert "conics_since_ellipse" in keys
        assert "graph_rt_info_foci" in keys
        assert solution.type is T.EQUALS


class TestRotated:
    """Повёрнутые коники (член ``xy``): поворот осей вместо отказа."""

    def test_rotated_ellipse_steps(self) -> None:
        keys, solution = run("{=({x^2+xy+y^2},{1})}")
        assert "conics_identify_std_form" in keys
        assert "conics_since_ellipse" in keys
        assert solution.type is T.EQUALS

    def test_rotated_hyperbola_has_asymptotes(self) -> None:
        keys, _ = run("{=({x^2+3xy-y^2},{1})}")
        assert "graph_rt_info_asymptotes" in keys
        assert "conics_since_hyperbola" in keys

    def test_rotated_parabola_has_directrix(self) -> None:
        keys, _ = run("{=({x^2+2xy+y^2+x},{0})}")
        assert "conics_since_parabola" in keys
        assert "graph_rt_info_directrix" in keys

    def test_imaginary_ellipse_rejected(self) -> None:
        with pytest.raises(SolveError, match="действительных точек"):
            run("{=({x^2+xy+y^2},{-1})}")
