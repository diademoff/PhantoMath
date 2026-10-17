"""Логика сервиса без HTTP-фреймворка.

Одна и та же она нужна двум фронтам:

* ``api.py`` -- FastAPI для десктопа и разработки;
* ``device.py`` -- локальный сервер на устройстве (stdlib ``http.server``),
  который запускается встроенным CPython (``serious_python``).

Здесь нет ни ``fastapi``, ни ``pydantic``: только решатель, словарь
объяснений и глоссарий. Так ядро остаётся переносимым и не тянет
``pydantic-core`` (Rust).

Функции бросают ``ProtocolError`` (разбор строки), ``ValueError``/``KeyError``
(разбор дерева/действия) и ``SolveError`` (задача не решилась); HTTP-коды
расставляет вызывающий.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from .ast import CoreAction, CoreNode, CoreRichText
from .concepts import definition as concept_definition
from .explanations import DEFAULT_LOCALE, Explanations, load_explanations
from .graph import DEFAULT_SAMPLES
from .graph import sample as sample_graph
from .input import parse_json, parse_protocol
from .node_types import CoreNodeType as T
from .results import CoreSolverGroup, Entry, ResultGroupType
from .solver import SolveError, solve
from .solver.equations import poly_of

# Продукт поддерживает только два языка (решение пользователя, см.
# truth/09-decisions.md). В данных английский хранится как `default`.
SUPPORTED_LOCALES: tuple[str, ...] = ("ru", "en")


def normalize_locale(locale: str) -> str:
    """Привести язык к поддерживаемому: `ru` или английский (`default`).

    Любой другой язык (в том числе диалект вида `ru-RU`) откатывается к
    английскому. Так решение «только ru/en» действует и для старых клиентов,
    а в словаре остаются все 9 языков как исследовательский артефакт.
    """
    base = locale.strip().lower().split("-")[0]
    if base == "ru":
        return "ru"
    return DEFAULT_LOCALE


# Словарь лежит в truth/data рядом с пакетом. Путь можно переопределить
# переменной окружения, иначе бэкенд не запустится вне монорепозитория.
# mymath_backend/service.py -> mymath_backend -> backend -> корень репозитория
_DEFAULT_EXPLANATIONS = Path(__file__).resolve().parents[2] / "truth" / "data" / "explanations.json"


def explanations_path() -> Path:
    """Путь к словарю: MYMATH_EXPLANATIONS имеет приоритет над умолчанием."""
    return Path(os.environ.get("MYMATH_EXPLANATIONS", str(_DEFAULT_EXPLANATIONS)))


@lru_cache(maxsize=1)
def explanations() -> Explanations:
    """Словарь объяснений; читается один раз за процесс."""
    return load_explanations(str(explanations_path()))


def explanations_loaded() -> bool:
    """Есть ли словарь. Без него ответы отдаются с ключами, но без текстов."""
    try:
        explanations()
    except OSError:
        return False
    return True


def health() -> dict[str, Any]:
    """Живость сервиса и состояние словаря объяснений."""
    try:
        size = len(explanations())
    except OSError as err:
        return {"status": "degraded", "explanations": 0, "detail": str(err)}
    return {"status": "ok", "explanations": size, "locales": list(SUPPORTED_LOCALES)}


def _render_view(key: str, args: list[CoreNode], locale: str) -> dict[str, Any]:
    """Развернуть один ключ пояснения.

    Без словаря отдаём только ключ: ответ остаётся валидным, фронт покажет
    его как есть, а health сообщит о проблеме.
    """
    used_locale = normalize_locale(locale)
    if not explanations_loaded():
        return {
            "key": key,
            "text": "",
            "locale": used_locale,
            "links": [],
            "tail_label": None,
            "missing": True,
        }
    rendered = explanations().render(key, args, used_locale)
    return {
        "key": key,
        "text": rendered.text,
        "locale": rendered.locale,
        "links": [
            {
                "label": link.label,
                "uuid": link.uuid,
                "definition": concept_definition(link.uuid, used_locale) or "",
            }
            for link in rendered.links
        ],
        "tail_label": rendered.tail_label,
        "missing": rendered.missing_key,
    }


def _render_rich(rich: dict[str, Any], locale: str) -> dict[str, Any]:
    """Развернуть `CoreRichText` (`{"type","args"}`) в текстовую вьюху."""
    args = [CoreNode.from_contract(a) for a in rich.get("args", [])]
    return _render_view(rich["type"], args, locale)


def attach_text(node: dict[str, Any], locale: str) -> dict[str, Any]:
    """Дописать тексты пояснений в узлы ответа.

    Мутирует копию ответа: фронт получает и дерево, и готовые строки,
    не разбирая шаблоны у себя. Исходный формат остаётся валидным --
    лишний ключ ``explanation`` просто игнорируется.
    """
    out = dict(node)
    description = out.get("description")
    if isinstance(description, dict) and "type" in description:
        out["explanation"] = _render_rich(description, locale)
    # Заголовки шагов — тоже `CoreRichText`, но лежат списком, а не под
    # ключом `description`, поэтому разворачиваются отдельно.
    headers = out.get("headers")
    if isinstance(headers, list):
        out["headers"] = [
            {**h, "explanation": _render_rich(h, locale)}
            if isinstance(h, dict) and "type" in h
            else h
            for h in headers
        ]
    # Подпись переключателя способов решения — тоже `CoreRichText`.
    select = out.get("selectMethodText")
    if isinstance(select, dict) and "type" in select:
        out["selectMethodText"] = {**select, "explanation": _render_rich(select, locale)}
    for key in ("children", "substeps", "steps", "entries"):
        value = out.get(key)
        if isinstance(value, list):
            out[key] = [attach_text(v, locale) if isinstance(v, dict) else v for v in value]
    # Вложенные результаты: `result` (группа) и `subresult` (раскрываемое
    # углублённое пояснение шага) — тоже `CoreSolverVerticalResult`.
    for key in ("result", "subresult"):
        nested = out.get(key)
        if isinstance(nested, dict):
            out[key] = attach_text(nested, locale)
    return out


# ── операции сервиса ───────────────────────────────────────────────────


def _polynomial_equation(node: CoreNode) -> CoreNode | None:
    """Для авто-действия искать нули многочлена с одной переменной."""
    variables = {n.value for n in node.walk() if n.type is T.VARIABLE and n.value}
    if len(variables) != 1:
        return None
    try:
        polynomial = poly_of(node, next(iter(variables)))
    except SolveError:
        return None
    if not polynomial or not 1 <= max(polynomial) <= 16:
        return None
    return CoreNode.node(T.EQUALS, node, CoreNode.constant("0"))


def parse(source: str) -> dict[str, Any]:
    """Разобрать строку протокола Photomath в дерево."""
    return {"node": parse_protocol(source).to_contract()}


def graph(
    node_data: dict[str, Any],
    x_min: float = -10.0,
    x_max: float = 10.0,
    samples: int = DEFAULT_SAMPLES,
) -> dict[str, Any]:
    """Точки графика ``y = f(x)`` для отрисовки на клиенте."""
    return sample_graph(parse_json(node_data), x_min, x_max, samples)


def solve_request(
    node_data: dict[str, Any],
    action_data: dict[str, Any] | None = None,
    interval_data: dict[str, Any] | None = None,
    locale: str = DEFAULT_LOCALE,
    render: bool = True,
    definitions_data: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Решить выражение и вернуть ответ контракта.

    ``render=True`` дописывает тексты пояснений (ключ ``explanation``).
    ``definitions_data`` — определения функций (``f(x) = …``), которые
    подставляются в решаемое выражение.
    """
    node = parse_json(node_data)
    action = CoreAction.from_contract(action_data) if action_data else None
    interval = None
    if interval_data is not None:
        interval = (parse_json(interval_data["min"]), parse_json(interval_data["max"]))
    definitions = [parse_json(item) for item in (definitions_data or [])]

    equation = _polynomial_equation(node) if action is None or action.command == "solve" else None
    data = solve(
        equation or node,
        command=action.command if action else None,
        args=action.args if action else None,
        interval=interval,
        definitions=definitions,
    )
    if equation is not None:
        # Исходное выражение сохраняется; трактовка «найти нули» видна
        # отдельным первым шагом, а не скрытым добавлением равенства.
        assert data.result is not None
        data.result.problem = node
        for entry in data.result.groups[0].entries:
            if entry.result is not None:
                entry.result.setdefault("steps", []).insert(
                    0,
                    {
                        "headers": [],
                        "substeps": [
                            {
                                "description": {"type": "find_x_intercept", "args": []},
                                "left": node.to_contract(),
                                "right": equation.to_contract(),
                                "subanimations": [],
                            }
                        ],
                    },
                )
        factored = solve(node, command="factor", definitions=definitions)
        assert factored.result is not None
        data.result.groups.append(
            CoreSolverGroup(
                type=ResultGroupType.VERTICAL,
                description=CoreRichText(type="factorise_call"),
                entries=[
                    Entry(
                        action=CoreAction(command="factor"),
                        result=factored.result.groups[0].entries[0].result,
                    )
                ],
            )
        )
    out = data.to_contract()
    if render:
        result = out.get("result")
        groups = result.get("groups") if isinstance(result, dict) else None
        if isinstance(groups, list):
            for index, group in enumerate(groups):
                if isinstance(group, dict):
                    groups[index] = attach_text(group, locale)
    return out


__all__ = [
    "SUPPORTED_LOCALES",
    "attach_text",
    "explanations",
    "explanations_loaded",
    "explanations_path",
    "graph",
    "health",
    "normalize_locale",
    "parse",
    "solve_request",
]
