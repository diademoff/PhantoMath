"""HTTP-слой: FastAPI-приложение поверх логики сервиса.

Наружу отдаётся контракт Photomath (см. ``truth/03-solver-contract.md``),
поэтому фронт получает тот же JSON, что и в оригинальном приложении.

Вся работа -- в :mod:`mymath_backend.service`; этот модуль только разбирает
запрос pydantic-моделями и расставляет HTTP-коды. Так одна и та же логика
работает и на десктопе (FastAPI), и на устройстве (``device.py``), где
``fastapi``/``pydantic`` не нужны.

Эндпоинты:

``POST /api/v1/solve``
    Основной. Принимает AST-JSON (``CoreNode``) и возвращает
    ``CoreSolverData``.

``POST /api/v1/parse``
    Диагностика ввода: та же строка протокола Photomath, но ответом --
    разобранное дерево. Нужен для отладки фронта и для проверки, что
    мы читаем протокол так же, как оригинал.

``GET /api/v1/health``
    Проверка живости и того, загружен ли словарь объяснений.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import service
from .explanations import DEFAULT_LOCALE
from .graph import DEFAULT_SAMPLES
from .input import ProtocolError
from .solver import SolveError


class IntervalRequest(BaseModel):
    """Промежуток отбора корней: левая и правая границы в формате ``CoreNode``.

    Граница может быть не числом, а выражением (``π/2``), поэтому берём
    узел контракта, а не число.
    """

    model_config = ConfigDict(extra="forbid")

    min: dict[str, Any] = Field(description="Левая граница (CoreNode)")
    max: dict[str, Any] = Field(description="Правая граница (CoreNode)")


class SolveRequest(BaseModel):
    """Запрос на решение.

    ``node`` принимает AST-JSON формата контракта: ровно то, что
    ``CoreNode.to_contract`` отдаёт наружу, поэтому фронт может
    переиспользовать один и тот же тип на обеих сторонах.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    node: dict[str, Any] = Field(description="Выражение в формате CoreNode (AST-JSON)")
    action: dict[str, Any] | None = Field(
        default=None,
        description="Действие над выражением (CoreAction): solve/factor/expand/simplify",
    )
    interval: IntervalRequest | None = Field(
        default=None,
        description="Промежуток отбора корней тригонометрического уравнения",
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


class GraphRequest(BaseModel):
    """Запрос точек графика ``y = f(x)``."""

    model_config = ConfigDict(extra="forbid")

    node: dict[str, Any] = Field(description="Выражение f(x) в формате CoreNode")
    x_min: float = Field(default=-10.0, alias="xMin")
    x_max: float = Field(default=10.0, alias="xMax")
    samples: int = Field(default=DEFAULT_SAMPLES, description="Число точек на отрезке")


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
        return service.health()

    @app.get("/")
    def index() -> dict[str, Any]:
        """Список эндпоинтов; открывается при заходе в корень."""
        return {
            "service": "mymath-backend",
            "endpoints": [
                "/api/v1/health",
                "/api/v1/parse",
                "/api/v1/solve",
                "/api/v1/graph",
                "/docs",
            ],
        }

    @app.post("/api/v1/parse")
    def parse(payload: ParseRequest) -> dict[str, Any]:
        """Разобрать строку протокола Photomath в дерево."""
        try:
            return service.parse(payload.source)
        except ProtocolError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err

    @app.post("/api/v1/graph")
    def graph(payload: GraphRequest) -> dict[str, Any]:
        """Точки графика ``y = f(x)`` для отрисовки на клиенте."""
        try:
            return service.graph(payload.node, payload.x_min, payload.x_max, payload.samples)
        except (ValueError, KeyError) as err:
            raise HTTPException(
                status_code=422, detail=f"не удалось разобрать узел: {err}"
            ) from err
        except SolveError as err:
            raise HTTPException(status_code=422, detail=str(err)) from err

    @app.post("/api/v1/solve")
    def run_solve(payload: SolveRequest) -> dict[str, Any]:
        """Решить выражение."""
        interval = payload.interval.model_dump() if payload.interval else None
        try:
            return service.solve_request(
                payload.node,
                action_data=payload.action,
                interval_data=interval,
                locale=payload.locale,
                render=payload.render,
            )
        except (ValueError, KeyError) as err:
            raise HTTPException(
                status_code=422, detail=f"не удалось разобрать узел: {err}"
            ) from err
        except SolveError as err:
            # Задачу не решили -- это не поломка сервиса. Отвечаем 422 с
            # понятным текстом и ключом пояснения, если он есть.
            raise HTTPException(
                status_code=422,
                detail={"message": str(err), "explanation": err.explanation_key},
            ) from err

    return app


app = create_app()
