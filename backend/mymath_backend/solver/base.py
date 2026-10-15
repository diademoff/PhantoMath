"""Каркас решателя: шаги, ошибки, точка сборки результата.

Решатель получает дерево узлов и возвращает ``CoreSolverData``. Шаги
складываются в вертикальный результат того же формата, что отдаёт Photomath,
поэтому фронт не различает, кто ответил.

Формат шага взят из ``truth/03-solver-contract.md`` раздел 3.5.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType
from ..results import (
    CoreSolverData,
    CoreSolverGroup,
    CoreSolverResult,
    CoreSolverVerticalResult,
    CoreSolverVerticalStep,
    Entry,
    ResultGroupType,
)


class SolveError(Exception):
    """Задачу не удалось решить.

    Отличается от :class:`NotImplementedError`: пользователь должен увидеть
    понятное сообщение, а не 500. Внутри решателя поднимается только этот
    тип; всё остальное — ошибки разработки.
    """

    def __init__(self, message: str, explanation_key: str | None = None) -> None:
        """Сообщение для пользователя и, по возможности, ключ пояснения."""
        super().__init__(message)
        self.explanation_key = explanation_key


@dataclass(slots=True)
class Step:
    """Один шаг решения: «было → стало» с пояснением.

    Не соответствует модели Photomath напрямую: шаги строятся в нативном
    формате, а в контракт превращаются при сборке результата. Так можно
    накапливать шаги до того, как известно, появятся ли вложенные результаты.
    """

    left: CoreNode | None
    right: CoreNode | None
    key: str
    args: list[CoreNode] = field(default_factory=list)
    headers: list[CoreRichText] = field(default_factory=list)
    subresult: SolveResult | None = None

    def to_contract(self) -> dict[str, Any]:
        """Подшаг в формате ``CoreSolverVerticalSubstep``."""
        return {
            "description": CoreRichText(type=self.key, args=list(self.args)).to_contract(),
            "left": self.left.to_contract() if self.left else None,
            "right": self.right.to_contract() if self.right else None,
            "subresult": self.subresult.to_contract() if self.subresult else None,
        }


class SolveResult:
    """Накопитель шагов одного поражения.

    Решатель наполняет его по ходу работы и в конце отдаёт в API. Хранит
    шаги в плоском списке, группируя в ``CoreSolverVerticalStep`` по
    явным заголовкам: в оригинале шаг -- это набор подшагов под общим
    заголовком, и группировка задаётся решателем, а не форматом.
    """

    __slots__ = ("_steps", "header", "solution")

    def __init__(self, header: str | None = None) -> None:
        """Создать пустой накопитель; ``header`` -- ключ заголовка группы."""
        self._steps: list[tuple[list[CoreRichText], list[Step]]] = []
        self.solution: CoreNode | None = None
        self.header = header

    # -- наполнение ----------------------------------------------------

    def add(self, step: Step, headers: Iterable[CoreRichText] | None = None) -> None:
        """Добавить подшаг, при необходимости начав новый шаг.

        Заголовки определяют границу шага: пока заголовки те же, подшаги
        попадают в один шаг. Пустые заголовки просто продолжают текущий.
        """
        heads = list(headers or [])
        if self._steps and self._steps[-1][0] == heads:
            self._steps[-1][1].append(step)
        else:
            self._steps.append((heads, [step]))

    def set_solution(self, node: CoreNode) -> None:
        """Итоговый ответ."""
        self.solution = node

    def __len__(self) -> int:
        """Всего подшагов."""
        return sum(len(steps) for _, steps in self._steps)

    def __iter__(self) -> Iterator[Step]:
        """Подшаги по порядку следования."""
        for _, steps in self._steps:
            yield from steps

    def __bool__(self) -> bool:
        """Есть ли хотя бы один шаг."""
        return bool(self._steps)

    # -- сборка --------------------------------------------------------

    def to_vertical(self) -> CoreSolverVerticalResult:
        """Собрать вертикальный результат для контракта."""
        steps = [
            CoreSolverVerticalStep.model_validate(
                {
                    "headers": [h.to_contract() for h in heads],
                    "substeps": [s.to_contract() for s in subs],
                }
            )
            for heads, subs in self._steps
        ]
        return CoreSolverVerticalResult(
            header=CoreRichText(type=self.header) if self.header else None,
            solutionNode=self.solution,
            steps=steps,
        )

    def to_contract(self) -> dict[str, Any]:
        """Вертикальный результат целиком, готовый к отдаче."""
        return self.to_vertical().model_dump(by_alias=True, exclude_none=True)


@dataclass(slots=True)
class SolveContext:
    """Состояние одного вызова решателя.

    Прокидывается по слоям, чтобы модули не зависели друг от друга и могли
    добавлять свои сервисы: локаль для чисел, подстановку, ссылку на
    накопленные шаги.
    """

    result: SolveResult
    variables: list[str] = field(default_factory=list)

    def step(
        self,
        left: CoreNode | None,
        right: CoreNode | None,
        key: str,
        *args: CoreNode,
        headers: Iterable[CoreRichText] | None = None,
    ) -> None:
        """Короткая запись добавления шага в накоп��итель."""
        self.result.add(Step(left=left, right=right, key=key, args=list(args)), headers)

    def require(self, condition: bool, message: str, key: str | None = None) -> None:
        """Проверка с понятным сообщением вместо assert."""
        if not condition:
            raise SolveError(message, key)


Solver = Callable[[CoreNode, SolveContext], CoreNode]
"""Модуль решателя.

Принимает узел, дополняет контекст шагами и возвращает свёрнутое значение:
лист остаётся листом, а ``2*3`` превращается в константу ``6``. Решателю
нужен именно этот возврат, иначе родитель увидит несвёрнутое поддерево.

Модули регистрируются по типам узлов; порядок регистрации не важен --
маршрутизация идёт по ``CoreNode.type``.
"""

_MODULE_REGISTRY: dict[CoreNodeType, list[Solver]] = {}


def solver_for(*node_types: CoreNodeType) -> Callable[[Solver], Solver]:
    """Зарегистрировать модуль решателя на указанные типы узлов.

    Использование::

        @solver_for(CoreNodeType.ADD, CoreNodeType.SUBTRACT)
        def solve_add(node, ctx): ...
    """

    def decorate(fn: Solver) -> Solver:
        for node_type in node_types:
            _MODULE_REGISTRY.setdefault(node_type, []).append(fn)
        return fn

    return decorate


def route(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Передать узел зарегистрированному модулю и вернуть свёрнутое значение."""
    handlers = _MODULE_REGISTRY.get(node.type)
    if not handlers:
        raise SolveError(f"модуль решателя для типа {node.type} не реализован")
    folded = node
    for handler in handlers:
        folded = handler(folded, ctx)
    return folded


def registered_types() -> set[CoreNodeType]:
    """Типы узлов, для которых есть модуль. Для тестов и отчётов о покрытии."""
    return set(_MODULE_REGISTRY)


def build_solver_data(
    node: CoreNode,
    result: SolveResult,
    *,
    alternatives: Iterable[SolveResult] = (),
    select_method_text: str | None = None,
) -> CoreSolverData:
    """Собрать полный ответ из дерева и накопленных шагов.

    ``alternatives`` — другие способы решения того же условия. Они становятся
    отдельными записями вертикальной ветки, а ``select_method_text`` — подпись
    переключателя «показать другой способ».
    """
    entries = [_vertical_entry(result)]
    for alternative in alternatives:
        entries.append(_vertical_entry(alternative))
    vertical = result.to_vertical()
    return CoreSolverData(
        normalizedInputNodeStr=None,
        result=CoreSolverResult(
            problem=node,
            solution=vertical.solution,
            groups=[
                CoreSolverGroup(
                    type=ResultGroupType.VERTICAL,
                    description=None,
                    selectMethodText=(
                        CoreRichText(type=select_method_text) if select_method_text else None
                    ),
                    entries=entries,
                )
            ],
        ),
    )


def _vertical_entry(result: SolveResult) -> Entry:
    """Одна запись вертикальной ветки: все шаги одного способа."""
    return Entry(
        action=None,
        result=result.to_vertical().model_dump(by_alias=True, exclude_none=True),
    )


__all__ = [
    "SolveContext",
    "SolveError",
    "SolveResult",
    "Solver",
    "Step",
    "build_solver_data",
    "registered_types",
    "route",
    "solver_for",
]
