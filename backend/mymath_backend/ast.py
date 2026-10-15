"""AST выражения -- ``CoreNode`` из Photomath 7.10.0.

Дерево узлов переносит условие задачи и каждое промежуточное выражение
в объяснении. Формат совпадает с оригинальным: ``type`` -- имя элемента
``CoreNodeType``, ``value`` -- строка (null у не-терминалов), ``children`` --
список вложенных узлов.

Разбор: ``truth/03-solver-contract.md`` раздел 3.2.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .node_types import CoreNodeType

# ARGB: 0xAARRGGBB. Photomath отдаёт целое, а не отдельные каналы.
Color = Annotated[int, Field(ge=0, le=0xFFFFFFFF, description="Цвет ARGB")]


class CoreNode(BaseModel):
    """Узел выражения.

    Терминал -- ``value`` без потомков. Ветка -- ``type`` без ``value``.
    Пустой узел (тип ``EMPTY``) используется как заглушка при построении
    результата по шагам.
    """

    model_config = ConfigDict(populate_by_name=True, validate_assignment=True)

    type: CoreNodeType = Field(description="Тип узла, имя элемента CoreNodeType")
    value: str | None = Field(default=None, description="Текст терминала")
    children: list[CoreNode] = Field(default_factory=list, description="Потомки")

    @model_validator(mode="after")
    def _check_shape(self) -> Self:
        if self.value is not None and self.children:
            raise ValueError(
                f"узел типа {self.type}: нельзя одновременно иметь value "
                f"({self.value!r}) и потомков"
            )
        return self

    # -- обход ---------------------------------------------------------

    def walk(self) -> Iterator[CoreNode]:
        """Обойти поддерево в глубину, включая сам узел."""
        yield self
        for child in self.children:
            yield from child.walk()

    def find_all(self, node_type: CoreNodeType) -> list[CoreNode]:
        """Все узлы данного типа в поддереве."""
        return [n for n in self.walk() if n.type is node_type]

    # -- конструкторы ---------------------------------------------------

    @classmethod
    def constant(cls, value: str | int | float) -> CoreNode:
        """Числовой или символический терминал.

        ``value`` сериализуется строкой, как в оригинале: решатель не
        различает ``"3"`` и ``3`` на входе.
        """
        return cls(type=CoreNodeType.CONSTANT, value=str(value))

    @classmethod
    def variable(cls, name: str) -> CoreNode:
        """Переменная по имени."""
        return cls(type=CoreNodeType.VARIABLE, value=name)

    @classmethod
    def node(cls, node_type: CoreNodeType, *children: CoreNode) -> Self:
        """Ветка заданного типа."""
        return cls(type=node_type, children=list(children))

    @classmethod
    def empty(cls) -> CoreNode:
        """Заглушка ``EMPTY``."""
        return cls(type=CoreNodeType.EMPTY)

    # -- сравнение ------------------------------------------------------

    def structural_eq(self, other: object) -> bool:
        """Структурное равенство, игнорирующее порядок полей.

        Нужно решателю, чтобы сравнивать промежуточные выражения между
        шагами. Отличается от ``==`` из pydantic, который чувствителен
        к типам ``value`` (``"3"`` и ``3``).
        """
        if not isinstance(other, CoreNode):
            return False
        return (
            self.type == other.type
            and (self.value or "") == (other.value or "")
            and len(self.children) == len(other.children)
            and all(a.structural_eq(b) for a, b in zip(self.children, other.children, strict=True))
        )

    # -- сериализация ---------------------------------------------------

    def to_contract(self) -> dict[str, Any]:
        """Формат контракта из ``truth/03-solver-contract.md`` раздел 3.2.

        ``None``-поля опускаются, как это делает Gson по умолчанию.
        """
        out: dict[str, Any] = {"type": self.type.value}
        if self.value is not None:
            out["value"] = self.value
        if self.children:
            out["children"] = [c.to_contract() for c in self.children]
        return out

    @classmethod
    def from_contract(cls, data: dict[str, Any]) -> CoreNode:
        """Разобрать узел из формата контракта.

        ``color`` и ``crossed`` поднимаются в ``CoreColoredNode``, если
        присутствуют: именно так работает полиморфный адаптер оригинала
        (``CoreColoredNodeDeserializer``).
        """
        payload = dict(data)
        extra = {k: payload.pop(k) for k in ("color", "crossed") if k in payload}
        built: dict[str, Any] = {
            "type": payload["type"],
            "value": payload.get("value"),
            "children": [cls.from_contract(c) for c in payload.get("children", [])],
        }
        if not extra:
            return cls.model_validate(built)
        colored: CoreColoredNode = CoreColoredNode.model_validate({**built, **extra})
        return colored


class CoreColoredNode(CoreNode):
    """Узел с подсветкой и зачёркиванием.

    Решатель помечает так части выражения в промежуточных шагах:
    ``color`` выделяет значимую часть, ``crossed`` -- сокращаемую.
    Наш рендер использует это вместо полноценных анимаций.
    """

    color: Color | None = Field(default=None, description="Цвет ARGB или null")
    crossed: bool | None = Field(default=None, description="Зачёркнута ли часть")

    def is_crossed(self) -> bool:
        """Зачёркнута ли часть. ``None`` считается за ``False``."""
        return bool(self.crossed)

    def to_contract(self) -> dict[str, Any]:
        """Дополнить контракт полями ``color`` и ``crossed``.

        Gson в оригинале опускает null-поля, поэтому отсутствующую подсветку
        в JSON не пишем: фронт различает «серое поле» и «подсветку».
        """
        out = super().to_contract()
        if self.color is not None:
            out["color"] = self.color
        if self.crossed is not None:
            out["crossed"] = self.crossed
        return out


class CoreAction(BaseModel):
    """Действие над выражением -- ``c.a.a.m.k.a`` в оригинале.

    Описывает операцию с аргументами-узлами: ``{"command": ..., "args": [...]}``.
    Решатель возвращает действия в ``Entry.action``, а фронт использует их
    для переключения способа решения.
    """

    model_config = ConfigDict(populate_by_name=True)

    command: str = Field(description="Имя команды")
    args: list[CoreNode] = Field(default_factory=list, description="Аргументы-узлы")

    def to_contract(self) -> dict[str, Any]:
        """Формат контракта: ``command`` и ``args``."""
        return {"command": self.command, "args": [a.to_contract() for a in self.args]}


class CoreRichText(BaseModel):
    """Локализуемый фрагмент текста -- ``CoreRichText``.

    ``type`` -- не имя ресурса, а ключ словаря объяснений. На этапе показа
    он превращается в ресурс ``step_<type>``; у нас -- в запись
    ``explanations.json``. Аргументы подставляются в шаблон как ``ARG1``...
    ``ARGn`` (индекс ``ARGk`` соответствует ``args[k-1]``).

    Разбор: ``truth/04-explanations.md``.
    """

    model_config = ConfigDict(populate_by_name=True)

    type: str = Field(description="Ключ словаря объяснений, без префикса step_")
    args: list[CoreNode] = Field(default_factory=list, description="Аргументы шаблона")

    def to_contract(self) -> dict[str, Any]:
        """Формат контракта: ключ объяснения и его аргументы."""
        return {"type": self.type, "args": [a.to_contract() for a in self.args]}


CoreNode.model_rebuild()


__all__ = [
    "Color",
    "CoreAction",
    "CoreColoredNode",
    "CoreNode",
    "CoreNodeType",
    "CoreRichText",
    "Literal",
]
