"""Тесты локального сервера для устройства (stdlib ``http.server``).

Сервер поднимается на свободном порту в потоке, запросы идут через
``http.client``. Проверяются те же контракты, что и у FastAPI-слоя.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from pathlib import Path

import pytest

from mymath_backend import device

TRUTH = Path(__file__).resolve().parents[2] / "truth" / "data"
os.environ.setdefault("MYMATH_EXPLANATIONS", str(TRUTH / "explanations.json"))


@pytest.fixture(scope="module")
def port() -> Iterator[int]:
    """Запустить сервер на свободном порту и вернуть его номер."""
    httpd = device.make_server(0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_address[1]
    finally:
        httpd.shutdown()


def get(port: int, path: str) -> tuple[int, dict]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path)
    response = conn.getresponse()
    return response.status, json.loads(response.read())


def post(port: int, path: str, payload: dict) -> tuple[int, dict]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(
        "POST", path, body=json.dumps(payload), headers={"Content-Type": "application/json"}
    )
    response = conn.getresponse()
    return response.status, json.loads(response.read())


def num(value: str) -> dict:
    return {"type": "CONSTANT", "value": value}


class TestHealth:
    def test_health(self, port: int) -> None:
        status, body = get(port, "/api/v1/health")
        assert status == 200
        assert body["status"] == "ok"
        assert body["explanations"] > 0

    def test_index(self, port: int) -> None:
        status, body = get(port, "/")
        assert status == 200
        assert "/api/v1/solve" in body["endpoints"]

    def test_unknown_path(self, port: int) -> None:
        status, _ = get(port, "/nope")
        assert status == 404


class TestSolve:
    def test_arithmetic(self, port: int) -> None:
        status, body = post(
            port,
            "/api/v1/solve",
            {"node": {"type": "ADD", "children": [num("2"), num("3")]}},
        )
        assert status == 200
        vertical = body["result"]["groups"][0]["entries"][0]["result"]
        assert vertical["solutionNode"]["value"] == "5"

    def test_unsolvable_is_422(self, port: int) -> None:
        status, body = post(
            port,
            "/api/v1/solve",
            {"node": {"type": "DIVIDE", "children": [num("5"), num("0")]}},
        )
        assert status == 422
        assert body["detail"]["explanation"] == "div_with_zero"

    def test_render_adds_text(self, port: int) -> None:
        status, body = post(
            port,
            "/api/v1/solve",
            {"node": {"type": "ADD", "children": [num("2"), num("3")]}, "locale": "ru"},
        )
        assert status == 200
        substep = body["result"]["groups"][0]["entries"][0]["result"]["steps"][0]["substeps"][0]
        assert "explanation" in substep

    def test_bad_node_is_422(self, port: int) -> None:
        status, _ = post(port, "/api/v1/solve", {"node": {"type": "НЕТ"}})
        assert status == 422

    def test_unexpected_exception_is_500_not_dropped(
        self, port: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Неожиданное исключение — 500 с текстом, а не обрыв соединения.

        Раньше исключение вне ``SolveError``/``ValueError``/``ProtocolError``
        уносило поток обработки: ответ не уходил вовсе, и клиент получал
        ``ClientException`` вместо ошибки — показать пользователю было нечего.
        """

        def boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("внутренняя поломка")

        monkeypatch.setattr(device.service, "solve_request", boom)
        status, body = post(port, "/api/v1/solve", {"node": num("1")})
        assert status == 500
        assert body["detail"]["message"] == "внутренняя ошибка решателя"
        assert body["detail"]["kind"] == "RuntimeError"


class TestParseAndGraph:
    def test_parse(self, port: int) -> None:
        status, body = post(port, "/api/v1/parse", {"source": "{2+3}"})
        assert status == 200
        assert body["node"]["type"] == "ADD"

    def test_parse_error_is_400(self, port: int) -> None:
        status, _ = post(port, "/api/v1/parse", {"source": "{@"})
        assert status == 400

    def test_graph(self, port: int) -> None:
        status, body = post(
            port,
            "/api/v1/graph",
            {"node": {"type": "VARIABLE", "value": "x"}, "xMin": 0, "xMax": 1, "samples": 3},
        )
        assert status == 200
        assert len(body["points"]) == 3
