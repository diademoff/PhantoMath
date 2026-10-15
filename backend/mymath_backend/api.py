"""HTTP-слой: FastAPI-приложение поверх решателя.

Наружу отдаётся контракт Photomath (см. ``truth/03-solver-contract.md``),
поэтому фронт получает тот же JSON, что и в оригинальном приложении.

Эндпоинты:

``POST /api/v1/solve``
    Основной. Принимает AST-JSON (``CoreNode``) и возвращает
    ``CoreSolverData``.

``POST /api/v1/parse``
    Диагностика ввода: та же строка протокола Photomah, но ответом --
    разобранное дерево. Нужен для отладки фронта и для проверки, что
    мы читаем протокол так же, как оригинал.

``GET /api/v1/health``
    Проверка живости и того, загружен ли словарь объяснений.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .ast import CoreAction, CoreNode
from .concepts import definition as concept_definition
from .explanations import DEFAULT_LOCALE, Explanations, load_explanations
from .input import ProtocolError, parse_json, parse_protocol
from .solver import SolveError, solve

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
# mymath_backend/api.py -> mymath_backend -> backend -> корень репозитория
_DEFAULT_EXPLANATIONS = Path(__file__).resolve().parents[2] / "truth" / "data" / "explanations.json"


def _explanations_path() -> Path:
    """Путь к словарю: MYMATH_EXPLANATIONS имеет приоритет над умолчанием."""
    return Path(os.environ.get("MYMATH_EXPLANATIONS", str(_DEFAULT_EXPLANATIONS)))


@lru_cache(maxsize=1)
def explanations() -> Explanations:
    """Словарь объяснений; читается один раз за процесс."""
    return load_explanations(str(_explanations_path()))


def _explanations_loaded() -> bool:
    """Есть ли словарь. Без него ответы отдаются с ключами, но без текстов."""
    try:
        explanations()
    except OSError:
        return False
    return True


# ── схемы запросов и ответа ────────────────────────────────────────────


class SolveRequest(BaseModel):
    """Запрос на решение.

    ``node`` принимает AST-JSON формата контракта: ровно то, что
    ``CoreNode.to_contract`` отдаёт наружу, поэтому фронт может
    переиспользовать один и тот же тип на обеих сторонах.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    node: dict[str, Any] = Field(description="Выражение в формате CoreNode (AST-JSON)")
    action: CoreAction | None = Field(
        default=None,
        description="Действие над выражением (CoreAction): solve/factor/expand/simplify",
    )
    locale: str = Field(default=DEFAULT_LOCALE, description="Язык пояснений")
    render: bool = Field(
        default=True,
        description="Развернуть пояснения в текст; false — только ключи и узлы",
    )


class ParseRequest(BaseModel):
    """Запрос на разбор строки протокола Photomath."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(description="Строка протокола, например {=({2x+3},{7})}")


class ExplanationView(BaseModel):
    """Пояснение, готовое к показу."""

    key: str = Field(description="Ключ словаря")
    text: str = Field(description="Текст с подставленными аргументами")
    locale: str
    links: list[dict[str, str]] = Field(
        default_factory=list, description="Ссылки: метка и uuid способа/понятия"
    )
    tail_label: str | None = Field(default=None, description="Метка в конце строки")
    missing: bool = Field(default=False, description="Ключа нет ни в одном языке")


def _render_view(key: str, args: list[CoreNode], locale: str) -> dict[str, Any]:
    """Развернуть один ключ пояснения.

    Без словаря отдаём только ключ: ответ остаётся валидным, фронт покажет
    его как есть, а health сообщит о проблеме.
    """
    if not _explanations_loaded():
        return ExplanationView(
            key=key,
            text="",
            locale=normalize_locale(locale),
            links=[],
            tail_label=None,
            missing=True,
        ).model_dump()
    rendered = explanations().render(key, args, normalize_locale(locale))
    used_locale = normalize_locale(locale)
    return ExplanationView(
        key=key,
        text=rendered.text,
        locale=rendered.locale,
        links=[
            {
                "label": link.label,
                "uuid": link.uuid,
                "definition": concept_definition(link.uuid, used_locale) or "",
            }
            for link in rendered.links
        ],
        tail_label=rendered.tail_label,
        missing=rendered.missing_key,
    ).model_dump()


def _render_rich(rich: dict[str, Any], locale: str) -> dict[str, Any]:
    """Развернуть `CoreRichText` (`{"type","args"}`) в текстовую вьюху."""
    args = [CoreNode.from_contract(a) for a in rich.get("args", [])]
    return _render_view(rich["type"], args, locale)


def _attach_text(node: dict[str, Any], locale: str) -> dict[str, Any]:
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
            out[key] = [_attach_text(v, locale) if isinstance(v, dict) else v for v in value]
    nested = out.get("result")
    if isinstance(nested, dict):
        out["result"] = _attach_text(nested, locale)
    return out


def create_app() -> FastAPI:
    """Собрать приложение."""
    app = FastAPI(
        title="mymath-backend",
        version="0.1.0",
        description="Символьный решатель с пошаговым объяснением",
    )

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        """Живость сервиса и состояние словаря объяснений."""
        try:
            size = len(explanations())
        except OSError as err:
            return {"status": "degraded", "explanations": 0, "detail": str(err)}
        return {
            "status": "ok",
            "explanations": size,
            "locales": list(SUPPORTED_LOCALES),
        }

    @app.get("/")
    def index() -> dict[str, Any]:
        """Список эндпоинтов; открывается при заходе в корень."""
        return {
            "service": "mymath-backend",
            "endpoints": ["/api/v1/health", "/api/v1/parse", "/api/v1/solve", "/docs"],
        }

    @app.post("/api/v1/parse")
    def parse(payload: ParseRequest) -> dict[str, Any]:
        """Разобрать строку протокола Photomath в дерево."""
        try:
            node = parse_protocol(payload.source)
        except ProtocolError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err
        return {"node": node.to_contract()}

    @app.post("/api/v1/solve")
    def run_solve(payload: SolveRequest) -> dict[str, Any]:
        """Решить выражение."""
        try:
            node = parse_json(payload.node)
        except (ValueError, KeyError) as err:
            raise HTTPException(
                status_code=422, detail=f"не удалось разобрать узел: {err}"
            ) from err

        try:
            data = solve(node, command=payload.action.command if payload.action else None)
        except SolveError as err:
            # Задачу не решили -- это не поломка сервиса. Отвечаем 422 с
            # понятным текстом и ключом пояснения, если он есть.
            raise HTTPException(
                status_code=422,
                detail={"message": str(err), "explanation": err.explanation_key},
            ) from err

        out = data.to_contract()
        if payload.render:
            result = out.get("result")
            groups = result.get("groups") if isinstance(result, dict) else None
            if isinstance(groups, list):
                for index, group in enumerate(groups):
                    if isinstance(group, dict):
                        groups[index] = _attach_text(group, payload.locale)
        return out

    return app


app = create_app()
