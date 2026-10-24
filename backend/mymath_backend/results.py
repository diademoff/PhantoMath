"""Контракт ответа решателя -- структура ``CoreSolverData``.

Это публичный API решателя: фронт должен уметь отрисовать любой ответ,
который вернёт бэкенд. Описание: ``docs/ARCHITECTURE.md``.

Модели -- dataclasses, а не pydantic (см. ``mymath_backend/ast.py``).
Сериализация в контракт руками повторяет прежний ``model_dump``: у узлов
вертикальной ветки пустые ``children`` и ``subanimations`` **сохраняются**,
чтобы JSON не изменился для уже выпущенного клиента.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .ast import CoreAction, CoreNode, CoreNodeType, CoreRichText


class ResultGroupType(StrEnum):
    """Ветка результата -- ``ResultGroupType``.

    ``BOOKPOINT`` соответствует поиску задач по учебнику и в нашем scope
    не используется (вне: камера, bookpoint, professor, подписка).
    """

    VERTICAL = "VERTICAL"
    ANIMATION = "ANIMATION"
    GRAPH = "GRAPH"
    BOOKPOINT = "BOOKPOINT"


def _node_dump(node: CoreNode) -> dict[str, Any]:
    """Узел как в прежнем ``model_dump``: пустые ``children`` остаются.

    ``CoreNode.to_contract`` опускает пустые списки (как Gson), а вертикальная
    ветка раньше сериализовалась через pydantic и включала ``children: []``.
    Форма сохранена дословно.
    """
    out: dict[str, Any] = {"type": node.type.value}
    if node.value is not None:
        out["value"] = node.value
    out["children"] = [_node_dump(child) for child in node.children]
    if node.color is not None:
        out["color"] = node.color
    if node.crossed is not None:
        out["crossed"] = node.crossed
    return out


def _rich_from_contract(data: dict[str, Any]) -> CoreRichText:
    """``CoreRichText`` из контракта."""
    return CoreRichText(
        type=data["type"],
        args=[CoreNode.from_contract(arg) for arg in data.get("args", [])],
    )


@dataclass
class Entry:
    """Элемент группы: действие и его результат.

    ``result`` хранится в формате контракта (dict): конкретный тип
    определяется полем ``type`` группы (см.
    ``CoreSolverGroupSerializerDeserializer``).
    """

    action: CoreAction | None = None
    result: dict[str, Any] | None = None


@dataclass
class CoreSolverGroup:
    """Группа результатов одного вида.

    ``description`` и ``select_method_text`` -- локализуемые заголовки,
    например «Решить» и «Показать другой способ».
    """

    type: ResultGroupType
    description: CoreRichText | None = None
    select_method_text: CoreRichText | None = None
    entries: list[Entry] = field(default_factory=list)

    def to_contract(self) -> dict[str, Any]:
        """Формат контракта группы."""
        out: dict[str, Any] = {"type": self.type.value, "entries": []}
        for e in self.entries:
            action = e.action.to_contract() if e.action else None
            out["entries"].append({"action": action, "result": e.result})
        if self.description:
            out["description"] = self.description.to_contract()
        if self.select_method_text:
            out["selectMethodText"] = self.select_method_text.to_contract()
        return out


@dataclass
class CoreSolverVerticalSubstep:
    """Подшаг решения: «было → стало».

    ``left`` и ``right`` -- части выражения с подсветкой; ``description`` --
    пояснение; ``subresult`` -- вложенный раскрываемый результат.
    ``subanimations`` не заполняется: анимаций шагов нет.
    """

    description: CoreRichText | None = None
    left: CoreNode | None = None
    right: CoreNode | None = None
    subresult: CoreSolverVerticalResult | None = None
    subanimations: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_subresult(self) -> bool:
        """Раскрывается ли подшаг."""
        return self.subresult is not None

    def to_contract(self) -> dict[str, Any]:
        """Формат ``CoreSolverVerticalSubstep``."""
        out: dict[str, Any] = {}
        if self.description:
            out["description"] = self.description.to_contract()
        if self.left:
            out["left"] = _node_dump(self.left)
        if self.right:
            out["right"] = _node_dump(self.right)
        if self.subresult:
            out["subresult"] = self.subresult.to_contract()
        out["subanimations"] = list(self.subanimations)
        return out

    @classmethod
    def from_contract(cls, data: dict[str, Any]) -> CoreSolverVerticalSubstep:
        """Разобрать подшаг из контракта."""
        return cls(
            description=(
                _rich_from_contract(data["description"]) if data.get("description") else None
            ),
            left=CoreNode.from_contract(data["left"]) if data.get("left") else None,
            right=CoreNode.from_contract(data["right"]) if data.get("right") else None,
            subresult=(
                CoreSolverVerticalResult.from_contract(data["subresult"])
                if data.get("subresult")
                else None
            ),
            subanimations=list(data.get("subanimations", [])),
        )


@dataclass
class CoreSolverVerticalStep:
    """Шаг решения: набор подшагов под общим заголовком."""

    step_headers: list[CoreRichText] = field(default_factory=list)
    substeps: list[CoreSolverVerticalSubstep] = field(default_factory=list)

    @property
    def headline(self) -> CoreNode | None:
        """Выражение слева от первого подшага.

        Строка шага берётся из ``substeps[0].left``.
        """
        if not self.substeps:
            return None
        return self.substeps[0].left

    def to_contract(self) -> dict[str, Any]:
        """Формат ``CoreSolverVerticalStep``: поле ``headers``, не ``stepHeaders``."""
        return {
            "headers": [h.to_contract() for h in self.step_headers],
            "substeps": [s.to_contract() for s in self.substeps],
        }

    @classmethod
    def from_contract(cls, data: dict[str, Any]) -> CoreSolverVerticalStep:
        """Разобрать шаг из контракта."""
        return cls(
            step_headers=[_rich_from_contract(h) for h in data.get("headers", [])],
            substeps=[CoreSolverVerticalSubstep.from_contract(s) for s in data.get("substeps", [])],
        )


@dataclass
class CoreSolverVerticalResult:
    """Вертикальный результат: список шагов с пояснениями."""

    header: CoreRichText | None = None
    solution: CoreNode | None = None
    steps: list[CoreSolverVerticalStep] = field(default_factory=list)

    def to_contract(self) -> dict[str, Any]:
        """Вертикальный результат в формате контракта (``solutionNode``)."""
        out: dict[str, Any] = {}
        if self.header:
            out["header"] = self.header.to_contract()
        if self.solution:
            out["solutionNode"] = _node_dump(self.solution)
        out["steps"] = [step.to_contract() for step in self.steps]
        return out

    @classmethod
    def from_contract(cls, data: dict[str, Any]) -> CoreSolverVerticalResult:
        """Разобрать вертикальный результат из контракта."""
        return cls(
            header=_rich_from_contract(data["header"]) if data.get("header") else None,
            solution=(
                CoreNode.from_contract(data["solutionNode"]) if data.get("solutionNode") else None
            ),
            steps=[CoreSolverVerticalStep.from_contract(s) for s in data.get("steps", [])],
        )


@dataclass
class CoreSolverResult:
    """Результат решателя: условие, ответ и ветки представления."""

    problem: CoreNode | None = None
    solution: CoreNode | None = None
    groups: list[CoreSolverGroup] = field(default_factory=list)

    def group(self, group_type: ResultGroupType) -> CoreSolverGroup | None:
        """Первую группу заданного вида, если она есть."""
        return next((g for g in self.groups if g.type is group_type), None)

    def vertical(self) -> CoreSolverVerticalResult | None:
        """Вертикальную ветку -- основной вид результата."""
        group = self.group(ResultGroupType.VERTICAL)
        if group is None:
            return None
        for entry in group.entries:
            if entry.result and "steps" in entry.result:
                return CoreSolverVerticalResult.from_contract(entry.result)
        return None


@dataclass
class CoreNormalizedInput:
    """Нормализованный ввод: как решатель понял выражение."""

    node: CoreNode | None = None
    action: CoreAction | None = None


@dataclass
class CoreSolverDiagnostics:
    """Тайминги решателя. Для отладки и замеров производительности."""

    solver_request_time: int = 0
    solver_evaluation_time: int = 0
    animation_request_time: int = 0
    evaluation_time: int = 0

    def to_contract(self) -> dict[str, Any]:
        """Формат контракта: camelCase-имена."""
        return {
            "solverRequestTime": self.solver_request_time,
            "solverEvaluationTime": self.solver_evaluation_time,
            "animationRequestTime": self.animation_request_time,
            "evaluationTime": self.evaluation_time,
        }


@dataclass
class CoreSolverData:
    """Корень ответа решателя.

    Именно эту структуру возвращает ``nativeProcessExpression`` и именно
    её должен вернуть наш ``POST /solve``.
    """

    normalized_input: CoreNormalizedInput | None = None
    normalized_input_node_str: str | None = None
    result: CoreSolverResult | None = None
    diagnostics: CoreSolverDiagnostics | None = None

    def to_contract(self) -> dict[str, Any]:
        """Формат контракта для ответа сервера.

        Ключи в camelCase.
        """
        out: dict[str, Any] = {}
        if self.normalized_input:
            out["normalizedInput"] = {
                "node": self.normalized_input.node.to_contract()
                if self.normalized_input.node
                else None,
                "action": self.normalized_input.action.to_contract()
                if self.normalized_input.action
                else None,
            }
        if self.normalized_input_node_str is not None:
            out["normalizedInputNodeStr"] = self.normalized_input_node_str
        if self.result:
            out["result"] = {
                "problem": self.result.problem.to_contract() if self.result.problem else None,
                "solution": self.result.solution.to_contract() if self.result.solution else None,
                "groups": [g.to_contract() for g in self.result.groups],
            }
        if self.diagnostics:
            out["diagnostics"] = self.diagnostics.to_contract()
        return out


__all__ = [
    "CoreNodeType",
    "CoreNormalizedInput",
    "CoreSolverData",
    "CoreSolverDiagnostics",
    "CoreSolverGroup",
    "CoreSolverResult",
    "CoreSolverVerticalResult",
    "CoreSolverVerticalStep",
    "CoreSolverVerticalSubstep",
    "Entry",
    "ResultGroupType",
]
