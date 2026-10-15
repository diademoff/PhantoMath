"""Контракт ответа решателя -- структура ``CoreSolverData``.

Воспроизводит то, что Photomath отдаёт из
``nativeProcessExpression(ctx, str)``. Это наш публичный API: фронт должен
уметь отрисовать любой ответ, который вернёт бэкенд.

Разбор: ``truth/03-solver-contract.md``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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


class Entry(BaseModel):
    """Элемент группы: действие и его результат.

    ``result`` намеренно не типизирован: конкретный тип определяется полем
    ``type`` группы (см. ``CoreSolverGroupSerializerDeserializer``).
    """

    model_config = ConfigDict(populate_by_name=True)

    action: CoreAction | None = Field(default=None, description="Действие над выражением")
    result: dict[str, Any] | None = Field(
        default=None, description="Результат; тип задаётся типом группы"
    )


class CoreSolverGroup(BaseModel):
    """Группа результатов одного вида.

    ``description`` и ``selectMethodText`` -- локализуемые заголовки,
    например «Решить» и «Показать другой способ».
    """

    model_config = ConfigDict(populate_by_name=True)

    type: ResultGroupType = Field(description="Вид ветки результата")
    description: CoreRichText | None = Field(default=None)
    select_method_text: CoreRichText | None = Field(default=None, alias="selectMethodText")
    entries: list[Entry] = Field(default_factory=list)

    def to_contract(self) -> dict[str, Any]:
        """Формат контракта группы. ``selectMethodText`` — имя из оригинала."""
        out: dict[str, Any] = {"type": self.type.value, "entries": []}
        for e in self.entries:
            action = e.action.to_contract() if e.action else None
            out["entries"].append({"action": action, "result": e.result})
        if self.description:
            out["description"] = self.description.to_contract()
        if self.select_method_text:
            out["selectMethodText"] = self.select_method_text.to_contract()
        return out


class CoreSolverVerticalSubstep(BaseModel):
    """Подшаг решения: «было → стало».

    ``left`` и ``right`` -- части выражения с подсветкой; ``description`` --
    пояснение; ``subresult`` -- вложенный раскрываемый результат.
    ``subanimations`` не заполняется: полноценные анимации вне scope
    (см. ``truth/05-animation.md``, вариант B).
    """

    model_config = ConfigDict(populate_by_name=True)

    description: CoreRichText | None = Field(default=None)
    left: CoreNode | None = Field(default=None, description="Что было")
    right: CoreNode | None = Field(default=None, description="Что стало")
    subresult: CoreSolverVerticalResult | None = Field(default=None)
    subanimations: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def has_subresult(self) -> bool:
        """Раскрывается ли подшаг."""
        return self.subresult is not None


class CoreSolverVerticalStep(BaseModel):
    """Шаг решения: набор подшагов под общим заголовком."""

    model_config = ConfigDict(populate_by_name=True)

    step_headers: list[CoreRichText] = Field(
        default_factory=list,
        alias="headers",
        description="Заголовки шага; в JSON поле называется headers",
    )
    substeps: list[CoreSolverVerticalSubstep] = Field(default_factory=list)

    @property
    def headline(self) -> CoreNode | None:
        """Выражение слева от первого подшага.

        Так же считает оригинал (``CoreSolverVerticalStep.a()``): строка
        шага берётся из ``substeps[0].left``.
        """
        if not self.substeps:
            return None
        return self.substeps[0].left


class CoreSolverVerticalResult(BaseModel):
    """Вертикальный результат: список шагов с пояснениями."""

    model_config = ConfigDict(populate_by_name=True)

    header: CoreRichText | None = Field(default=None)
    solution: CoreNode | None = Field(default=None, alias="solutionNode")
    steps: list[CoreSolverVerticalStep] = Field(default_factory=list)


class CoreSolverResult(BaseModel):
    """Результат решателя: условие, ответ и ветки представления."""

    model_config = ConfigDict(populate_by_name=True)

    problem: CoreNode | None = Field(default=None, description="Исходное условие")
    solution: CoreNode | None = Field(default=None, description="Итоговый ответ")
    groups: list[CoreSolverGroup] = Field(default_factory=list)

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
                return CoreSolverVerticalResult.model_validate(entry.result)
        return None


class CoreNormalizedInput(BaseModel):
    """Нормализованный ввод: как решатель понял выражение."""

    model_config = ConfigDict(populate_by_name=True)

    node: CoreNode | None = Field(default=None)
    action: CoreAction | None = Field(default=None)


class CoreSolverDiagnostics(BaseModel):
    """Тайминги решателя. Для отладки и замеров производительности."""

    model_config = ConfigDict(populate_by_name=True)

    solver_request_time: int = Field(default=0, alias="solverRequestTime")
    solver_evaluation_time: int = Field(default=0, alias="solverEvaluationTime")
    animation_request_time: int = Field(default=0, alias="animationRequestTime")
    evaluation_time: int = Field(default=0, alias="evaluationTime")


class CoreSolverData(BaseModel):
    """Корень ответа решателя.

    Именно эту структуру возвращает ``nativeProcessExpression`` и именно
    её должен вернуть наш ``POST /solve``.
    """

    model_config = ConfigDict(populate_by_name=True)

    normalized_input: CoreNormalizedInput | None = Field(default=None, alias="normalizedInput")
    normalized_input_node_str: str | None = Field(default=None, alias="normalizedInputNodeStr")
    result: CoreSolverResult | None = Field(default=None, alias="result")
    diagnostics: CoreSolverDiagnostics | None = Field(default=None)

    def to_contract(self) -> dict[str, Any]:
        """Формат контракта для ответа сервера.

        Ключи повторяют оригинальные, включая camelCase-имена из Gson-аннотаций.
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
            out["diagnostics"] = self.diagnostics.model_dump(by_alias=True)
        return out


CoreSolverVerticalSubstep.model_rebuild()

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
