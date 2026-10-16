"""Локальный сервер решателя для встроенного Python (устройство).

Запускается в фоновом потоке внутри приложения (``serious_python``) и
отвечает приложению по ``http://127.0.0.1:<порт>`` тем же JSON-контрактом,
что и FastAPI (``api.py``). Здесь только стандартная библиотека: ``http.server``
и ``json`` -- ``fastapi``/``pydantic`` на устройстве не нужны.

Запуск::

    python -m mymath_backend.device      # порт из MYMATH_PORT (по умолчанию 8770)
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from . import service
from .explanations import DEFAULT_LOCALE
from .graph import DEFAULT_SAMPLES
from .input import ProtocolError
from .solver import SolveError

DEFAULT_PORT = 8770
"""Порт по умолчанию. Клиент подключается к нему на localhost."""

DEFAULT_HOST = "127.0.0.1"
"""Слушаем только петлю: наружу порт не выставлен."""


class _Handler(BaseHTTPRequestHandler):
    """Обработчик одного запроса: тонкая обёртка над :mod:`service`."""

    server_version = "mymath-device/0.1"

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        """Здоровье сервиса и список эндпоинтов."""
        if self.path == "/api/v1/health":
            self._send(200, service.health())
            return
        if self.path == "/":
            self._send(
                200,
                {
                    "service": "mymath-device",
                    "endpoints": [
                        "/api/v1/health",
                        "/api/v1/parse",
                        "/api/v1/solve",
                        "/api/v1/graph",
                    ],
                },
            )
            return
        self._send(404, {"detail": "not found"})

    def do_POST(self) -> None:
        """Разбор, решение и точки графика."""
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"detail": "неверный JSON"})
            return
        if not isinstance(payload, dict):
            self._send(400, {"detail": "тело запроса должно быть объектом"})
            return

        try:
            result = self._dispatch(payload)
        except ProtocolError as err:
            self._send(400, {"detail": str(err)})
            return
        except (ValueError, KeyError) as err:
            self._send(422, {"detail": f"не удалось разобрать узел: {err}"})
            return
        except SolveError as err:
            self._send(422, {"detail": {"message": str(err), "explanation": err.explanation_key}})
            return
        except Exception as err:  # последний рубеж
            # Неожиданное исключение раньше убивало поток обработки: ответ не
            # уходил вовсе, клиент получал обрыв соединения и не мог показать
            # пользователю ничего осмысленного. Теперь это 500 с текстом, а
            # трассировка остаётся в логе приложения.
            self._log_exception()
            self._send(
                500,
                {
                    "detail": {
                        "message": "внутренняя ошибка решателя",
                        "kind": type(err).__name__,
                    }
                },
            )
            return
        if result is None:
            self._send(404, {"detail": "not found"})
            return
        self._send(200, result)

    def _log_exception(self) -> None:
        """Напечатать трассировку: на устройстве stdout уходит в лог."""
        print("необработанное исключение в запросе:", file=sys.stderr, flush=True)
        traceback.print_exc(file=sys.stderr)

    def _dispatch(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Маршрутизация POST по пути."""
        if self.path == "/api/v1/parse":
            return service.parse(str(payload["source"]))
        if self.path == "/api/v1/graph":
            return service.graph(
                payload["node"],
                float(payload.get("xMin", -10.0)),
                float(payload.get("xMax", 10.0)),
                int(payload.get("samples", DEFAULT_SAMPLES)),
            )
        if self.path == "/api/v1/solve":
            return service.solve_request(
                payload["node"],
                action_data=payload.get("action"),
                interval_data=payload.get("interval"),
                locale=str(payload.get("locale", DEFAULT_LOCALE)),
                render=bool(payload.get("render", True)),
                definitions_data=payload.get("definitions"),
            )
        return None

    def log_message(self, format: str, *args: object) -> None:
        """Тишина в логах: на устройстве stdout уходит в лог приложения."""
        del format, args


def make_server(port: int = DEFAULT_PORT, host: str = DEFAULT_HOST) -> ThreadingHTTPServer:
    """Создать сервер (не запуская). Нужен тестам и точке входа."""
    return ThreadingHTTPServer((host, port), _Handler)


def serve(port: int = DEFAULT_PORT, host: str = DEFAULT_HOST) -> None:
    """Поднять сервер и слушать вечно (блокирует поток)."""
    httpd = make_server(port, host)
    print(f"mymath-device listening on http://{host}:{port}", flush=True)
    httpd.serve_forever()


def main() -> None:
    """Точка входа: порт из ``MYMATH_PORT``, иначе ``DEFAULT_PORT``."""
    serve(int(os.environ.get("MYMATH_PORT", str(DEFAULT_PORT))))


if __name__ == "__main__":
    main()


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "main",
    "make_server",
    "serve",
]
