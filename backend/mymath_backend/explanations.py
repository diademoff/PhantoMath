"""Тексты пояснений: ключ ``CoreRichText`` -> предложение на языке ученика.

Каждый шаг решателя называет ключ словаря и передаёт аргументы. Шаблон
подставляет вместо ``ARG1...ARGn`` отрендеренные аргументы и размечает ссылки
``[label|uuid]`` на определения понятий. Словарь — ``data/explanations.json``
(русский и английский) плюс тексты уроков из учебных пакетов.
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
from .node_types import CoreNodeType as T

DEFAULT_LOCALE = "default"
ARG_PATTERN = re.compile(r"ARG(\d+)")
LINK_PATTERN = re.compile(r"\[([^|\]]+)\|([0-9a-fA-F-]{36})]")
TAIL_LABEL_PATTERN = re.compile(r"\n?\[([^|\]]+)\]$")


@dataclass(frozen=True, slots=True)
class Link:
    """Кликабельная ссылка на определение понятия.

    ``label`` -- видимый текст, ``uuid`` -- идентификатор понятия
    (:mod:`mymath_backend.concepts`). В приложении подчёркивается и красится в акцентный цвет.
    """

    label: str
    uuid: str


@dataclass(frozen=True, slots=True)
class RenderedText:
    """Результат подстановки шаблона.

    ``text`` — текст без разметки. ``links`` — ссылки в порядке появления;
    они же разбивают ``text``, поэтому индексы в них -- смещения в строке.
    ``tail_label`` — метка в конце строки без ссылки; отделяется от текста
    и возвращается отдельным значением.
    """

    text: str
    links: tuple[Link, ...] = ()
    tail_label: str | None = None
    locale: str = DEFAULT_LOCALE
    missing_key: bool = False


class ExplanationNotFoundError(KeyError):
    """Ключа нет ни в одном языке."""


class Explanations:
    """Словарь объяснений с подстановкой аргументов.

    Загружается один раз и затем только читается. Путь к словарю передаётся
    явно: по умолчанию это ``data/explanations.json`` пакета.

    Формат файла::

        {"<ключ>": {"arity": 3,
                   "templates": {"default": "...", "ru": "...", ...}}}
    """

    __slots__ = ("_entries", "_fallbacks")

    def __init__(self, entries: dict[str, dict[str, Any]]) -> None:
        """Принять словарь в формате ``explanations.json``."""
        self._entries = entries
        self._fallbacks = self._build_fallbacks(self._entries)

    @staticmethod
    def _build_fallbacks(entries: dict[str, dict[str, Any]]) -> dict[str, str]:
        """Карта «язык -> ключ» для восстановления цепочки fallback'ов.

        Цепочка ``ru-RU -> ru -> default``: язык без шаблона уходит в английский.
        """
        out: dict[str, str] = {}
        for key, payload in entries.items():
            for locale in payload.get("templates", {}):
                out.setdefault(locale, key)
        return out

    @classmethod
    def from_file(cls, path: str | Path) -> Explanations:
        """Загрузить словарь из JSON-файла и тематических ``explanations_*.json`` рядом с ним.

        Ключ, определённый в двух файлах, — ошибка: тексты не должны тихо перекрывать друг друга.
        """
        from .teaching import TEMPLATES
        from .teaching_registry import templates

        main = Path(path)
        entries: dict[str, dict[str, Any]] = json.loads(main.read_text(encoding="utf-8"))
        for extra in sorted(main.parent.glob(f"{main.stem}_*.json")):
            more = json.loads(extra.read_text(encoding="utf-8"))
            clash = sorted(set(entries) & set(more))
            if clash:
                raise ValueError(f"{extra.name}: keys already defined: {', '.join(clash[:5])}")
            entries |= more
        return cls(entries | TEMPLATES | templates())

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


# Связки, которые в тексте читаются как знак между двумя операндами.
_INFIX_OPERATORS: dict[T, str] = {
    T.EQUALS: "=",
    T.APPROXIMATE: "≈",
    T.NOT_EQUALS: "≠",
    T.LESS_THAN: "<",
    T.LESS_THAN_EQUAL: "≤",
    T.GREATER_THAN: ">",
    T.GREATER_THAN_EQUAL: "≥",
    T.ELEMENT_OF: "∈",
    T.ELEMENT_NOT_OF: "∉",
    T.SUBSET_OR_EQUALS: "⊆",
    T.PROPER_SUBSET: "⊂",
    T.SUPERSET_OR_EQUALS: "⊇",
    T.PROPER_SUPERSET: "⊃",
    T.UNION: "∪",
    T.INTERSECTION: "∩",
    T.DIFFERENCE: "\\",
    T.ADD_SUBTRACT: "±",
}

# Размещения и сочетания: P(n, k), C(n, k), A(n, k).
_COMBINATORICS_NAMES: dict[T, str] = {
    T.PARTIAL_PERMUTATION_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT: "P",
    T.CHOOSE: "C",
    T.CHOOSE_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT: "C",
    T.VARIATION: "A",
}

# Перечисление в одну строку: «x, y» вместо «LIST(x,y)».
_LIST_TYPES = (T.LIST, T.SEQUENCE, T.VERTICAL_LIST)

# Матрица и её варианты с разделителем столбцов: строки через «;».
_MATRIX_TYPES = (T.MATRIX, T.MATRIX_SPLIT_LAST, T.MATRIX_SPLIT_CENTER)

# Определитель: размерность и плоские ячейки вокруг вертикальных чёрточек.
_DETERMINANT_SIZES: dict[T, int] = {
    T.DETERMINANT2: 2,
    T.DETERMINANT3: 3,
    T.DETERMINANT3_SARRUS: 3,
    T.DETERMINANT4: 4,
    T.DETERMINANT5: 5,
}


# Unary functions keep their name when the debug text is built (see
# ``_default_render_arg``): the argument alone is not the expression.
_FUNCTION_NAMES: dict[T, str] = {
    T.SIN: "sin",
    T.COS: "cos",
    T.TAN: "tg",
    T.COT: "ctg",
    T.ASIN: "arcsin",
    T.ACOS: "arccos",
    T.ATAN: "arctg",
    T.ACOT: "arcctg",
    T.SINH: "sh",
    T.COSH: "ch",
    T.TANH: "th",
    T.COTH: "cth",
    T.SECH: "sech",
    T.CSC: "csc",
    T.LN: "ln",
    T.LOG10: "lg",
    T.EXP: "exp",
    T.ABS: "abs",
    T.SIGN: "sign",
}


def _render_child_rows(rows: list[CoreNode]) -> str:
    """Строки матрицы/определителя: ячейки через пробел, строки через «;»."""
    rendered: list[str] = []
    for row in rows:
        cells = row.children if row.type is T.MATRIX_ROW else [row]
        rendered.append(" ".join(_default_render_arg(cell) for cell in cells))
    return " ; ".join(rendered)


def _render_part(node: CoreNode) -> str:
    """Операнд дроби/предела: скобки только вокруг составной части.

    ``(1)/(x)`` читалось как имена узлов, а не как дробь: атомы и функции
    пишутся без скобок (``1/x``, ``sin(u)``), составные — в скобках
    (``(x + 1)/(x - 1)``).
    """
    rendered = _default_render_arg(node)
    if node.type in (
        T.ADD,
        T.SUBTRACT,
        T.MULTIPLY,
        T.MULTIPLY_IMPLICIT,
        T.DIVIDE,
        T.FRACTION,
        T.EQUALS,
        T.NOT_EQUALS,
        T.LESS_THAN,
        T.LESS_THAN_EQUAL,
        T.GREATER_THAN,
        T.GREATER_THAN_EQUAL,
    ):
        return f"({rendered})"
    return rendered


def _variable_names(node: CoreNode) -> set[str]:
    """Names drawn as variables (``e``, ``π`` and ``i`` are constants)."""
    names: set[str] = set()

    def walk(current: CoreNode) -> None:
        if current.type is T.VARIABLE and current.value and current.value not in ("e", "π", "i"):
            names.add(current.value)
        for child in current.children:
            walk(child)

    walk(node)
    return names


_SUBSCRIPT_DIGITS = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def _power_part(node: CoreNode) -> str:
    """Base or exponent of a power: ``2^x``, ``x^2``, but ``(x + 1)^(n - 1)``."""
    text = _default_render_arg(node)
    if node.type in (T.VARIABLE, T.BRACKET) or (
        node.type is T.CONSTANT and text.replace(".", "").isalnum()
    ):
        return text
    return f"({text})"


def _default_render_arg(node: CoreNode) -> str:
    """Текстовый вывод узла для логов и тестов.

    Не заменяет рендер фронта: структуру (дробь, корень, индекс) передаёт
    только он. Здесь нужен человекочитаемый текст без имён узлов: ``EQUALS``
    становится «=», ``LIST`` — перечислением, ``MATRIX``/``DETERMINANT`` —
    строками ячеек, чтобы экранный диктор не читал ``EQUALS(x + y,3)``.
    """
    if node.type in (T.CONSTANT, T.VARIABLE, T.TEXT, T.TEXT_KEY, T.STRING):
        return node.value or ""
    if node.type is T.INTEGRAL and node.children:
        names = _variable_names(node.children[0])
        variable = names.pop() if len(names) == 1 else "x"
        body = _default_render_arg(node.children[0])
        if node.children[0].type in (T.ADD, T.SUBTRACT):
            body = f"({body})"
        return f"∫{body} d{variable}"
    if node.type is T.INTEGRAL_DEFINITE and len(node.children) == 3:
        lower, upper, definite_body = node.children
        names = _variable_names(definite_body)
        variable = names.pop() if len(names) == 1 else "x"
        rendered = _default_render_arg(definite_body)
        if definite_body.type in (T.ADD, T.SUBTRACT):
            rendered = f"({rendered})"
        return f"∫_{_default_render_arg(lower)}^{_default_render_arg(upper)} {rendered} d{variable}"
    if node.type is T.INTEGRAL_RIGHT_DASH and len(node.children) == 3:
        dash_body, lower, upper = node.children
        return (
            f"{_default_render_arg(dash_body)}|"
            f"_{_default_render_arg(lower)}^{_default_render_arg(upper)}"
        )
    if node.type is T.SIGMA_DEFINITE and len(node.children) in (3, 4):
        # Решатель пишет [индекс, от, до, слагаемое], редактор — [от, до, слагаемое] с индексом n.
        index = _default_render_arg(node.children[0]) if len(node.children) == 4 else "n"
        lower, upper, term = node.children[-3:]
        body = _default_render_arg(term)
        if term.type in (T.ADD, T.SUBTRACT):
            body = f"({body})"
        return f"Σ({index}={_default_render_arg(lower)}..{_default_render_arg(upper)}) {body}"
    if node.type in (T.LIMIT, T.LIMIT_LEFT, T.LIMIT_RIGHT) and len(node.children) >= 2:
        point, expression = node.children[0], node.children[1]
        side = "+" if node.type is T.LIMIT_RIGHT else "-" if node.type is T.LIMIT_LEFT else ""
        return f"lim(x→{_default_render_arg(point)}{side}) {_default_render_arg(expression)}"
    if node.type is T.FRACTION and len(node.children) == 2:
        num, den = node.children
        return f"{_render_part(num)}/{_render_part(den)}"
    if node.type is T.ROOT and len(node.children) == 2:
        idx, rad = node.children
        return f"root({_default_render_arg(idx)}, {_default_render_arg(rad)})"
    if node.type is T.ROOT2 and len(node.children) == 1:
        return f"sqrt({_default_render_arg(node.children[0])})"
    if node.type in (T.POWER,) and len(node.children) == 2:
        base, exp = node.children
        return f"{_power_part(base)}^{_power_part(exp)}"
    if node.type is T.LOG and len(node.children) == 2:
        value, base = node.children
        digits = _default_render_arg(base)
        index = digits.translate(_SUBSCRIPT_DIGITS) if digits.isdigit() else f"_{_power_part(base)}"
        return f"log{index}({_default_render_arg(value)})"
    if node.type is T.BRACKET and len(node.children) == 1:
        return f"({_default_render_arg(node.children[0])})"
    if node.type is T.NEGATIVE and len(node.children) == 1:
        return f"-{_default_render_arg(node.children[0])}"
    if node.type is T.ADD_SUBTRACT and len(node.children) == 1:
        return f"±{_default_render_arg(node.children[0])}"
    if node.type is T.FACTORIAL and len(node.children) == 1:
        inner = node.children[0]
        text = _default_render_arg(inner)
        return f"{text}!" if not inner.children else f"({text})!"
    if node.type in _COMBINATORICS_NAMES and len(node.children) == 2:
        n, k = (_default_render_arg(child) for child in node.children)
        return f"{_COMBINATORICS_NAMES[node.type]}({n}, {k})"
    if node.type is T.ADD:
        return " + ".join(_default_render_arg(child) for child in node.children)
    if node.type is T.SUBTRACT and len(node.children) >= 2:
        head, *rest = node.children
        return _default_render_arg(head) + "".join(
            f" - {_default_render_arg(child)}" for child in rest
        )
    if node.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT):
        return "·".join(_default_render_arg(child) for child in node.children)
    if node.type in _INFIX_OPERATORS and len(node.children) == 2:
        left, right = node.children
        sign = _INFIX_OPERATORS[node.type]
        return f"{_default_render_arg(left)} {sign} {_default_render_arg(right)}"
    if node.type in _LIST_TYPES:
        return ", ".join(_default_render_arg(child) for child in node.children)
    if node.type is T.SYSTEM:
        return ", ".join(_default_render_arg(child) for child in node.children)
    if node.type is T.SET:
        return "{" + ", ".join(_default_render_arg(child) for child in node.children) + "}"
    if node.type is T.MATRIX_ROW:
        return " ".join(_default_render_arg(child) for child in node.children)
    if node.type in _MATRIX_TYPES:
        return "[" + _render_child_rows(list(node.children)) + "]"
    if node.type is T.DETERMINANT and node.children:
        return "|" + _render_child_rows(list(node.children)) + "|"
    if node.type in _DETERMINANT_SIZES:
        size = _DETERMINANT_SIZES[node.type]
        cells = list(node.children)
        if len(cells) == size * size:
            rows = [
                CoreNode.node(T.MATRIX_ROW, *cells[start : start + size])
                for start in range(0, len(cells), size)
            ]
            body = _render_child_rows(rows)
        else:
            body = _render_child_rows(cells)
        return "|" + body + "|"
    # A function of one argument keeps its whole form: unwrapping it to the
    # argument said «x» for ``ln(cos x)`` and «e» for ``e^(−x²)``.
    if node.type in _FUNCTION_NAMES and node.children:
        name = _FUNCTION_NAMES[node.type]
        return f"{name}({_default_render_arg(node.children[0])})"
    if node.type is T.FUNCTION and node.children:
        return f"{node.value or 'f'}({_default_render_arg(node.children[0])})"
    if node.type in (T.DERIVATION1, T.PRIME, T.DERIVATION1_PRIME) and node.children:
        return f"({_default_render_arg(node.children[0])})'"
    if node.type is T.DERIVATION2_PRIME and node.children:
        return f"({_default_render_arg(node.children[0])})''"
    if node.type is T.DERIVATION1_DIFF and len(node.children) == 2:
        return (
            f"d/d{_default_render_arg(node.children[0])}({_default_render_arg(node.children[1])})"
        )
    if len(node.children) == 1:
        return _default_render_arg(node.children[0])
    if node.children:
        args = ", ".join(_default_render_arg(c) for c in node.children)
        # Имя узла строчными буквами: текст для чтения, а не имя типа.
        return f"{node.type.value.lower()}({args})"
    return node.type.value.lower()


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
