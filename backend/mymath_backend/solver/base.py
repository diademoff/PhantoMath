"""Каркас решателя: шаги, ошибки, точка сборки результата.

Решатель получает дерево узлов и возвращает ``CoreSolverData``. Шаги
складываются в вертикальный результат в формате контракта решателя.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType
from ..results import (
    CoreSolverData,
    CoreSolverGroup,
    CoreSolverResult,
    CoreSolverVerticalResult,
    CoreSolverVerticalStep,
    CoreSolverVerticalSubstep,
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


class UndefinedError(SolveError):
    """Выражение не определено, и у решателя на это есть готовый ответ.

    Деление на ноль, факториал или перестановка вне области определения,
    корень из отрицательного числа — не повод для экрана ошибки: решатель
    отвечает «Не определено» и объясняет причину шагом с ключом ``key``.
    Ловится один раз в :func:`solve`; в отличие от прочих ``SolveError`` это
    не «не умею», а «ответ известен», поэтому промежуточные обработчики
    ошибок обязаны пропускать его дальше (см. ``methods_for``).

    ``header`` — заголовок шага (``expr_undefined`` для деления на ноль и
    факториала, ``expr_not_def_in_r`` для корня из отрицательного числа).
    """

    def __init__(
        self,
        message: str,
        key: str,
        *,
        explanation_args: Iterable[CoreNode] = (),
        header: str = "expr_undefined",
    ) -> None:
        """Ключ и аргументы пояснения; ``header`` — заголовок шага."""
        super().__init__(message, key)
        self.key = key
        self.explanation_args = list(explanation_args)
        self.header = header


def undefined_node() -> CoreNode:
    """Ответ «Не определено»: ``TEXT[TEXT_KEY("undefined")]``."""
    return CoreNode.node(CoreNodeType.TEXT, CoreNode(type=CoreNodeType.TEXT_KEY, value="undefined"))


def division_by_zero(node: CoreNode) -> CoreNode | None:
    """Дробь или деление с буквальным нулём в знаменателе, если она есть.

    Уравнение с такой частью не определено целиком (``sin x = 1/0``), даже
    если левая часть не сворачивается: Решатель отвечает «Не определено»,
    а не «корней нет».
    """
    for part in node.walk():
        if part.type not in (CoreNodeType.FRACTION, CoreNodeType.DIVIDE):
            continue
        if len(part.children) != 2:
            continue
        denominator = part.children[1]
        if denominator.type is not CoreNodeType.CONSTANT or denominator.value is None:
            continue
        try:
            if Fraction(str(denominator.value)) == 0:
                return part
        except (ValueError, ZeroDivisionError):
            continue
    return None


def undefined_data(problem: CoreNode, error: UndefinedError) -> CoreSolverData:
    """Собрать ответ «Не определено»: один шаг с причиной и текстом ответа.

    Шаг показывает исходное выражение целиком (``6/0``, а не только
    знаменатель) и ключ причины; накопленные до ошибки шаги
    отбрасываются, иначе студент видел бы арифметику несуществующего числа.
    """
    result = SolveResult()
    result.header = "simplify_msg"
    result.add_group(
        error.header,
        Step(
            left=problem,
            right=undefined_node(),
            key=error.key,
            args=error.explanation_args,
        ),
    )
    result.set_solution(undefined_node())
    return build_solver_data(problem, result)


@dataclass(slots=True)
class Step:
    """Один шаг решения: «было → стало» с пояснением.

    Не соответствует модели контракта напрямую: шаги строятся во внутреннем
    формате, а в контракт превращаются при сборке результата. Так можно
    накапливать шаги до того, как известно, появятся ли вложенные результаты.
    """

    left: CoreNode | None
    right: CoreNode | None
    key: str
    args: list[CoreNode] = field(default_factory=list)
    headers: list[CoreRichText] = field(default_factory=list)
    subresult: SolveResult | None = None


class SolveResult:
    """Накопитель шагов одного решения.

    Решатель наполняет его по ходу работы и в конце отдаёт в API. Хранит
    шаги в плоском списке, группируя в ``CoreSolverVerticalStep`` по
    явным заголовкам: шаг -- это набор подшагов под общим заголовком, и
    группировка задаётся решателем, а не форматом.
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

    def add_group(
        self, title: str | CoreRichText | Sequence[str | CoreRichText], *steps: Step
    ) -> None:
        """Explicit teaching boundary; identical titles never merge groups.

        A title is a dictionary key, or a ``CoreRichText`` when the label has arguments.
        """
        if steps:
            titles = [title] if isinstance(title, (str, CoreRichText)) else list(title)
            # a plain key as a title takes the arguments of the step that has the same key
            by_key = {step.key: step.args for step in reversed(steps)}
            heads = [
                CoreRichText(type=t, args=list(by_key.get(t, []))) if isinstance(t, str) else t
                for t in titles
            ]
            self._steps.append((heads, list(steps)))

    def extend(self, other: SolveResult) -> None:
        """Append the groups of another result (its solution is not taken)."""
        self._steps.extend((list(heads), list(steps)) for heads, steps in other._steps)

    def retitle(self, title: str | CoreRichText) -> None:
        """Rename the first group; later groups keep their own titles.

        A nested card taken from another method must say which part of the
        problem it solves («Интеграл левой части»), otherwise two of them in a
        row carry the same heading.
        """
        if not self._steps:
            return
        _heads, steps = self._steps[0]
        named = title if isinstance(title, CoreRichText) else CoreRichText(type=title)
        self._steps[0] = ([named], steps)

    def name_groups(self, title: str | CoreRichText) -> None:
        """Give every untitled group a heading, in this card and its details.

        The verified cards were grouped without headers, so the app showed the
        fallback «Преобразование» — a heading that tells the student nothing.
        A group that already has a title keeps it.
        """
        named = title if isinstance(title, CoreRichText) else CoreRichText(type=title)
        for index, (heads, _steps) in enumerate(self._steps):
            if not heads:
                self._steps[index] = ([named], _steps)
        for step in self:
            if step.subresult is not None:
                step.subresult.name_groups(named)

    def __len__(self) -> int:
        """Всего подшагов."""
        return sum(len(steps) for _, steps in self._steps)

    @property
    def groups(self) -> int:
        """Число групп шагов (заголовков) — то, что приложение рисует списком."""
        return len(self._steps)

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
        from ..teaching_registry import enrich

        for _, subs in self._steps:
            for sub in subs:
                # shortcut: calculus lessons are not attached, they re-split the verified
                # derivative rows; function evaluation has nothing to teach.
                if not sub.key.startswith(("function_", "derive", "find_derivative", "lesson_")):
                    enrich(sub)
        steps = [
            CoreSolverVerticalStep(
                step_headers=list(heads),
                substeps=[
                    CoreSolverVerticalSubstep(
                        description=CoreRichText(type=sub.key, args=list(sub.args)),
                        left=sub.left,
                        right=sub.right,
                        subresult=sub.subresult.to_vertical() if sub.subresult else None,
                    )
                    for sub in subs
                ],
            )
            for heads, subs in self._steps
        ]
        return CoreSolverVerticalResult(
            header=CoreRichText(type=self.header) if self.header else None,
            solution=self.solution,
            steps=steps,
        )

    def to_contract(self) -> dict[str, Any]:
        """Вертикальный результат целиком, готовый к отдаче."""
        return self.to_vertical().to_contract()


@dataclass(slots=True)
class SolveContext:
    """Состояние одного вызова решателя.

    Прокидывается по слоям, чтобы модули не зависели друг от друга и могли
    добавлять свои сервисы: локаль для чисел, подстановку, ссылку на
    накопленные шаги.
    """

    result: SolveResult
    variables: list[str] = field(default_factory=list)
    depth: int = 0  # > 0 while the operands of a larger expression are being folded

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

# Команда (``CoreAction``): узел, контекст и аргументы команды.
Command = Callable[[CoreNode, SolveContext, list[CoreNode]], CoreNode]

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


def fold_semantically(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Свернуть подвыражение, если это возможно без неизвестных.

    Считает в **служебном** накопителе: если свёртка не удалась (в поддереве
    есть переменная) или ничего не изменила, шаги не переносятся, и узел
    остаётся прежним. Только при успешной свёртке шаги переносятся в
    основной результат.

    Нужен модулям, которые могут **оставить** свой узел (``√(2+3)``,
    ``log₁₀(2+3)``, ``sin(1+1)``): подвыражение показывается как отдельный
    шаг (``2+3 = 5``), но если модуль решает сохранить узел, шаг не должен
    подменять собой ответ.
    """
    scratch = SolveResult()
    scratch_ctx = SolveContext(result=scratch, variables=list(ctx.variables))
    try:
        folded = route(node, scratch_ctx)
    except UndefinedError:
        # Неопределённая часть делает неопределённым всё выражение: это ответ,
        # а не повод оставить узел как есть.
        raise
    except SolveError:
        return node
    if folded.structural_eq(node):
        return node
    for step in scratch:
        ctx.result.add(step)
    return folded


def boolean_node(value: bool) -> CoreNode:
    """Ответ-истинность: ``TEXT[TEXT_KEY("true"/"false")]``.

    Первый ребёнок ``TEXT`` задаёт ключ текста, который клиент подставляет
    («Истина»/«Ложь»); ``TEXT_KEY`` — носитель ключа.
    """
    key = "true" if value else "false"
    return CoreNode.node(CoreNodeType.TEXT, CoreNode(type=CoreNodeType.TEXT_KEY, value=key))


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
        normalized_input_node_str=None,
        result=CoreSolverResult(
            problem=node,
            solution=vertical.solution,
            groups=[
                CoreSolverGroup(
                    type=ResultGroupType.VERTICAL,
                    description=None,
                    select_method_text=(
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
        result=result.to_vertical().to_contract(),
    )


__all__ = [
    "Command",
    "SolveContext",
    "SolveError",
    "SolveResult",
    "Solver",
    "Step",
    "UndefinedError",
    "boolean_node",
    "build_solver_data",
    "fold_semantically",
    "registered_types",
    "route",
    "solver_for",
    "undefined_data",
    "undefined_node",
]
