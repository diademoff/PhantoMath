"""Резолвер объяснений: ``CoreRichText`` -> текст на нужном языке.

В оригинале цепочка такая (``c/a/a/l/g/c0.java``)::

    CoreRichText.type  ->  "step_" + type  ->  getIdentifier(...)  ->  getString(...)

То есть ``type`` -- не имя ресурса, а ключ словаря. Шаблон подставляет
``ARG1...ARGn`` отрендеренными аргументами и размечает ссылки
``[label|uuid]`` для переключения способа решения.

Словарь извлечён из ``resources.arsc`` -- там 3252 ключа на 9 языках.
Разбор: ``truth/04-explanations.md``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .ast import CoreNode
from .translations import SUPPLEMENTARY

DEFAULT_LOCALE = "default"
ARG_PATTERN = re.compile(r"ARG(\d+)")
LINK_PATTERN = re.compile(r"\[([^|\]]+)\|([0-9a-fA-F-]{36})]")
TAIL_LABEL_PATTERN = re.compile(r"\n?\[([^|\]]+)\]$")


@dataclass(frozen=True, slots=True)
class Link:
    """Кликабельная ссылка «показать другой способ решения».

    ``label`` -- видимый текст, ``uuid`` -- идентификатор альтернативного
    метода. В оригинале подчёркивается и красится в акцентный цвет.
    """

    label: str
    uuid: str


@dataclass(frozen=True, slots=True)
class RenderedText:
    """Результат подстановки шаблона.

    ``text`` — текст без разметки. ``links`` — ссылки в порядке появления;
    они же разбивают ``text``, поэтому индексы в них -- смещения в строке.
    ``tail_label`` — метка в конце строки без ссылки (в оригинале
    отделяется и возвращается отдельным значением).
    """

    text: str
    links: tuple[Link, ...] = ()
    tail_label: str | None = None
    locale: str = DEFAULT_LOCALE
    missing_key: bool = False


class ExplanationNotFoundError(KeyError):
    """Ключа нет ни в одном языке."""


def _with_supplementary(
    entries: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Дополнить извлечённый словарь нашими переводами.

    Заполняются только отсутствующие языки: данные из ``resources.arsc``
    остаются неприкосновенными (см. :mod:`mymath_backend.translations`).
    """
    if not SUPPLEMENTARY:
        return entries
    merged = dict(entries)
    for key, templates in SUPPLEMENTARY.items():
        payload = merged.get(key)
        if payload is None:
            continue
        current = payload.get("templates", {})
        missing = {locale: text for locale, text in templates.items() if locale not in current}
        if missing:
            merged[key] = {**payload, "templates": {**current, **missing}}
    return merged


class Explanations:
    """Словарь объяснений с подстановкой аргументов.

    Загружается один раз и затем только читается. Путь к словарю передаётся
    явно, чтобы не зашивать его в код: данные лежат в ``truth/data/``, но
    бэкенд должен работать и с любой копией.

    Формат файла (``truth/data/explanations.json``)::

        {"<ключ>": {"arity": 3,
                   "templates": {"default": "...", "ru": "...", ...}}}
    """

    __slots__ = ("_entries", "_fallbacks")

    def __init__(self, entries: dict[str, dict[str, Any]]) -> None:
        """Принять словарь в формате ``explanations.json``."""
        self._entries = _with_supplementary(entries)
        self._fallbacks = self._build_fallbacks(self._entries)

    @staticmethod
    def _build_fallbacks(entries: dict[str, dict[str, Any]]) -> dict[str, str]:
        """Карта «язык -> ключ» для восстановления цепочки fallback'ов.

        Оригинал отдаёт ``default`` только для конкретного языка; остальные
        языки отсутствуют молча. Мы достраиваем цепочку
        ``ru -> default``, ``de-RU -> ru -> default``.
        """
        out: dict[str, str] = {}
        for key, payload in entries.items():
            for locale in payload.get("templates", {}):
                out.setdefault(locale, key)
        return out

    @classmethod
    def from_file(cls, path: str | Path) -> Explanations:
        """Загрузить словарь из JSON-файла."""
        from .teaching import TEMPLATES

        return cls(json.loads(Path(path).read_text(encoding="utf-8")) | TEMPLATES)

    # -- доступ --------------------------------------------------------

    def __len__(self) -> int:
        """Число ключей в словаре."""
        return len(self._entries)

    def __contains__(self, key: object) -> bool:
        """Есть ли такой ключ."""
        return key in self._entries

    def __iter__(self) -> Iterator[str]:
        """Перебор ключей словаря."""
        return iter(self._entries)

    def keys(self) -> list[str]:
        """Все ключи словаря."""
        return list(self._entries)

    def locales(self) -> set[str]:
        """Все языки, встречающиеся хотя бы в одном шаблоне."""
        seen: set[str] = set()
        for payload in self._entries.values():
            seen.update(payload.get("templates", {}))
        return seen

    def arity(self, key: str) -> int:
        """Сколько аргументов ждёт ключ."""
        payload = self._entries.get(key)
        if payload is None:
            raise ExplanationNotFoundError(key)
        return int(payload.get("arity", 0))

    def raw_template(self, key: str, locale: str = DEFAULT_LOCALE) -> str | None:
        """Шаблон без подстановки, ``None`` если ключа или языка нет."""
        payload = self._entries.get(key)
        if payload is None:
            return None
        template = payload.get("templates", {}).get(locale)
        return template if isinstance(template, str) else None

    # -- подстановка ---------------------------------------------------

    def render(
        self,
        key: str,
        args: list[CoreNode] | None = None,
        locale: str = DEFAULT_LOCALE,
        render_arg: Callable[[CoreNode], str] | None = None,
    ) -> RenderedText:
        """Подставить аргументы в шаблон.

        ``render_arg`` — функция ``CoreNode -> str``. Если не передана,
        используется простой текстовый вывод (``_default_render_arg``),
        пригодный для логов и тестов, но не для показа пользователю:
        фронт подставит свои отрендеренные узлы вместо строк.

        Fallback: ``ru -> default``. Если языка нет и нет ``default``,
        берётся первый доступный язык по алфавиту, а в
        ``RenderedText.missing_key`` ставится ``True``.
        """
        template, used_locale = self._resolve(key, locale)
        if template is None:
            return RenderedText(
                text=f"?? step_{key} ??",
                locale=locale,
                missing_key=True,
            )

        render = render_arg or _default_render_arg
        used_args = args or []

        # Метки в конце строки убираются из текста и возвращаются отдельно.
        tail_label: str | None = None
        tail = TAIL_LABEL_PATTERN.search(template)
        if tail:
            template = template[: tail.start()]
            tail_label = tail.group(1)

        links: list[Link] = []

        def _take_link(m: re.Match[str]) -> str:
            links.append(Link(label=m.group(1), uuid=m.group(2)))
            return m.group(1)

        template = LINK_PATTERN.sub(_take_link, template)

        # Подстановка идёт после разбора ссылок, чтобы [label|uuid] не
        # конфликтовал с форматом аргументов.
        def _take_arg(m: re.Match[str]) -> str:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(used_args):
                return render(used_args[idx])
            return m.group(0)

        text = ARG_PATTERN.sub(_take_arg, template)

        return RenderedText(
            text=text, links=tuple(links), tail_label=tail_label, locale=used_locale
        )

    def _resolve(self, key: str, locale: str) -> tuple[str | None, str]:
        """Найти шаблон и язык по цепочке fallback'ов."""
        payload = self._entries.get(key)
        if payload is None:
            return None, locale
        templates = payload.get("templates", {})
        for candidate in self._fallback_chain(locale):
            if candidate in templates:
                return templates[candidate], candidate
        if templates:
            first = min(templates)
            return templates[first], first
        return None, locale

    @staticmethod
    def _fallback_chain(locale: str) -> list[str]:
        """``de-Latn-DE`` -> ``['de-Latn-DE', 'de-Latn', 'de', 'default']``."""
        chain = [locale]
        parts = locale.split("-")
        while len(parts) > 1:
            parts.pop()
            chain.append("-".join(parts))
        chain.append(DEFAULT_LOCALE)
        return chain


def _default_render_arg(node: CoreNode) -> str:
    """Текстовый вывод узла для логов и тестов.

    Не заменяет рендер фронта: структуру (дробь, корень, индекс) передаёт
    только он. Здесь нужен текст, пригодный для отладки и поиска по шаблону.
    """
    from .node_types import CoreNodeType as T

    if node.type in (T.CONSTANT, T.VARIABLE, T.TEXT, T.TEXT_KEY, T.STRING):
        return node.value or ""
    if node.type is T.FRACTION and len(node.children) == 2:
        num, den = node.children
        return f"({_default_render_arg(num)})/({_default_render_arg(den)})"
    if node.type is T.ROOT and len(node.children) == 2:
        idx, rad = node.children
        return f"root({_default_render_arg(idx)}, {_default_render_arg(rad)})"
    if node.type is T.ROOT2 and len(node.children) == 1:
        return f"sqrt({_default_render_arg(node.children[0])})"
    if node.type in (T.POWER,) and len(node.children) == 2:
        base, exp = node.children
        return f"({_default_render_arg(base)})^({_default_render_arg(exp)})"
    if node.type is T.BRACKET and len(node.children) == 1:
        return f"({_default_render_arg(node.children[0])})"
    if node.type is T.NEGATIVE and len(node.children) == 1:
        return f"-{_default_render_arg(node.children[0])}"
    if node.type is T.ADD:
        return " + ".join(_default_render_arg(child) for child in node.children)
    if node.type is T.SUBTRACT and len(node.children) >= 2:
        head, *rest = node.children
        return _default_render_arg(head) + "".join(
            f" - {_default_render_arg(child)}" for child in rest
        )
    if node.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT):
        return "·".join(_default_render_arg(child) for child in node.children)
    if len(node.children) == 1:
        return _default_render_arg(node.children[0])
    if node.children:
        args = ",".join(_default_render_arg(c) for c in node.children)
        return f"{node.type.value}({args})"
    return node.type.value


@lru_cache(maxsize=4)
def load_explanations(path: str) -> Explanations:
    """Загрузить словарь с кешированием по пути.

    Словарь большой (2.3 МБ) и неизменяемый в рамках процесса, поэтому
    повторные обращения не должны его перечитывать.
    """
    return Explanations.from_file(path)


__all__ = [
    "DEFAULT_LOCALE",
    "ExplanationNotFoundError",
    "Explanations",
    "Link",
    "RenderedText",
    "load_explanations",
]
