"""Проводка определений функций через сервис (`definitions` в запросе)."""

from __future__ import annotations

from typing import Any

from mymath_backend.ast import CoreNode
from mymath_backend.node_types import CoreNodeType as T
from mymath_backend.results import CoreSolverVerticalResult
from mymath_backend.service import solve_request


def c(value: str) -> CoreNode:
    return CoreNode.constant(value)


def x() -> CoreNode:
    return CoreNode.variable("x")


def definition_contract() -> dict[str, Any]:
    body = CoreNode.node(T.ADD, CoreNode.node(T.MULTIPLY_IMPLICIT, c("2"), x()), c("1"))
    equation = CoreNode.node(T.EQUALS, CoreNode(type=T.FUNCTION, value="f", children=[x()]), body)
    return equation.to_contract()


def solution_of(response: dict[str, Any]) -> CoreNode | None:
    for group in response["result"]["groups"]:
        for entry in group["entries"]:
            vertical = CoreSolverVerticalResult.from_contract(entry["result"])
            if vertical.solution is not None:
                return vertical.solution
    return None


def test_definition_and_evaluation() -> None:
    definition = definition_contract()
    call = CoreNode(type=T.FUNCTION, value="f", children=[c("2")]).to_contract()
    response = solve_request(call, definitions_data=[definition], render=True)
    assert solution_of(response) is not None
    assert solution_of(response).value == "5"


def test_definition_alone() -> None:
    response = solve_request(definition_contract(), render=True)
    assert solution_of(response) is not None
    assert solution_of(response).type is T.EQUALS
