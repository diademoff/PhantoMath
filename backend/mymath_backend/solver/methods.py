"""Реестр способов решения: общий механизм выбора метода.

Решатель умеет показывать несколько путей решения одной задачи и
переключаться между ними (``selectMethodText`` + отдельные записи
вертикальной ветки, см. ``docs/ARCHITECTURE.md``). Раньше
точка входа ``solve`` знала про способы жёстко: отдельно для уравнений
(``solve_methods``) и отдельно для систем (``system_methods``). Теперь
провайдеры регистрируются по типу узла, и добавить способ для нового типа --
это регистрация функции, а не правка ``solve``.

Провайдер принимает узел и список переменных и возвращает список
:class:`~mymath_backend.solver.base.SolveResult`: первый -- основной способ,
остальные -- альтернативы. Если способ неприменим, провайдер поднимает
:class:`~mymath_backend.solver.base.SolveError`; тогда пробуется следующий
провайдер того же типа, а если ни один не справился -- исключение
поднимается наружу (как и раньше: неподдерживаемое уравнение -- это
понятная ошибка, а не «модуль не реализован»).
"""

from __future__ import annotations

from collections.abc import Callable

from ..ast import CoreNode
from ..node_types import CoreNodeType
from .base import SolveError, SolveResult, UndefinedError

# Провайдер способов: узел и переменные -> способы решения.
MethodProvider = Callable[[CoreNode, list[str]], "list[SolveResult]"]

_MODULE_REGISTRY: dict[CoreNodeType, list[MethodProvider]] = {}


def method_provider(*node_types: CoreNodeType) -> Callable[[MethodProvider], MethodProvider]:
    """Зарегистрировать провайдер способов для указанных типов узлов."""

    def decorate(fn: MethodProvider) -> MethodProvider:
        for node_type in node_types:
            _MODULE_REGISTRY.setdefault(node_type, []).append(fn)
        return fn

    return decorate


def has_method_provider(node_type: CoreNodeType) -> bool:
    """Есть ли для типа узла хоть один провайдер способов."""
    return node_type in _MODULE_REGISTRY


def method_types() -> set[CoreNodeType]:
    """Типы узлов, для которых объявлены способы. Для тестов и отчётов."""
    return set(_MODULE_REGISTRY)


def methods_for(node: CoreNode, variables: list[str]) -> list[SolveResult] | None:
    """Способы решения узла или ``None``, если провайдеров нет.

    Первый непустой результат провайдера возвращается как есть. Если все
    провайдеры подняли :class:`SolveError`, последняя ошибка поднимается
    наружу -- так сохраняется прежнее поведение для неподдерживаемых задач.
    """
    providers = _MODULE_REGISTRY.get(node.type)
    if not providers:
        return None
    last_error: SolveError | None = None
    for provider in providers:
        try:
            methods = provider(node, variables)
        except UndefinedError:
            # Не «способ не подошёл», а готовый ответ: другой способ его не отменит.
            raise
        except SolveError as err:
            last_error = err
            continue
        if methods:
            return methods
    if last_error is not None:
        raise last_error
    return None


__all__ = [
    "MethodProvider",
    "has_method_provider",
    "method_provider",
    "method_types",
    "methods_for",
]
