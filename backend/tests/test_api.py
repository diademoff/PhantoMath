"""Тесты HTTP-слоя.

Приложение собирается напрямую, без запуска сервера: TestClient из
starlette проверяет маршруты, коды ответов и форму ответа.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TRUTH = Path(__file__).resolve().parents[2] / "truth" / "data"
os.environ.setdefault("MYMATH_EXPLANATIONS", str(TRUTH / "explanations.json"))

# Импорт после установки переменной: путь к словарю читается при создании
# приложения, а он кешируется на уровне модуля.
from mymath_backend.api import create_app  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def add(a: dict, b: dict) -> dict:
    return {"type": "ADD", "children": [a, b]}


def num(value: str) -> dict:
    return {"type": "CONSTANT", "value": value}


def solve(client: TestClient, node: dict, **kwargs: object) -> dict:
    response = client.post("/api/v1/solve", json={"node": node, **kwargs})
    assert response.status_code == 200, response.text
    return response.json()


class TestHealth:
    def test_reports_explanations_loaded(self, client: TestClient) -> None:
        body = client.get("/api/v1/health").json()
        assert body["status"] == "ok"
        assert body["explanations"] == 3252


class TestParse:
    def test_roundtrip_protocol(self, client: TestClient) -> None:
        body = client.post("/api/v1/parse", json={"source": "{=({2x+3},{7})}"})
        assert body.status_code == 200
        node = body.json()["node"]
        assert node["type"] == "EQUALS"
        assert node["children"][0]["type"] == "ADD"

    def test_bad_protocol_is_400(self, client: TestClient) -> None:
        response = client.post("/api/v1/parse", json={"source": "{nonsense({x})}"})
        assert response.status_code == 400
        assert "неизвестный оператор" in response.json()["detail"]


class TestSolve:
    def test_value_and_steps(self, client: TestClient) -> None:
        body = solve(client, add(num("2"), num("3")))
        vertical = body["result"]["groups"][0]["entries"][0]["result"]
        assert vertical["solutionNode"]["value"] == "5"
        assert len(vertical["steps"]) == 1
        substep = vertical["steps"][0]["substeps"][0]
        assert substep["right"]["value"] == "5"
        assert substep["description"]["type"] == "add"

    def test_contract_keys_match_photomath(self, client: TestClient) -> None:
        """Названия полей повторяют оригинал: solutionNode, headers, description.

        ``subresult`` в ответе отсутствует, когда вложенного результата нет:
        так же ведёт себя Gson, опуская null-поля.
        """
        body = solve(client, add(num("2"), num("3")))
        result = body["result"]["groups"][0]["entries"][0]["result"]
        assert "solutionNode" in result
        assert "headers" in result["steps"][0]
        substep = result["steps"][0]["substeps"][0]
        assert "description" in substep
        assert "subresult" not in substep
        assert "left" in substep and "right" in substep

    def test_rendered_text_present(self, client: TestClient) -> None:
        body = solve(client, add(num("2"), num("3")), locale="ru")
        substep = body["result"]["groups"][0]["entries"][0]["result"]["steps"][0]["substeps"][0]
        view = substep["explanation"]
        assert view["key"] == "add"
        assert view["locale"] == "ru"
        assert view["text"] == "Сложите числа"
        assert view["missing"] is False

    def test_render_can_be_switched_off(self, client: TestClient) -> None:
        body = solve(client, add(num("2"), num("3")), render=False)
        substep = body["result"]["groups"][0]["entries"][0]["result"]["steps"][0]["substeps"][0]
        assert "explanation" not in substep

    def test_locale_fallback(self, client: TestClient) -> None:
        body = solve(client, add(num("2"), num("3")), locale="xx")
        substep = body["result"]["groups"][0]["entries"][0]["result"]["steps"][0]["substeps"][0]
        assert substep["explanation"]["locale"] == "default"

    def test_unknown_locale_still_renders(self, client: TestClient) -> None:
        body = solve(client, add(num("2"), num("3")), locale="fr")
        substep = body["result"]["groups"][0]["entries"][0]["result"]["steps"][0]["substeps"][0]
        assert substep["explanation"]["text"]


class TestSolveErrors:
    def test_unsupported_node_type_is_422(self, client: TestClient) -> None:
        """Неизвестный тип узла — ошибка запроса, а не 500."""
        response = client.post(
            "/api/v1/solve",
            json={"node": {"type": "ВЫДУМКА", "value": "1"}},
        )
        assert response.status_code == 422

    def test_unimplemented_math_is_422_with_message(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/solve",
            json={"node": {"type": "VARIABLE", "value": "x"}},
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "уравнени" in detail["message"]

    def test_division_by_zero_carries_explanation_key(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/solve",
            json={"node": {"type": "DIVIDE", "children": [num("5"), num("0")]}},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["explanation"] == "div_with_zero"

    def test_unknown_field_rejected(self, client: TestClient) -> None:
        response = client.post("/api/v1/solve", json={"node": num("1"), "мусор": 1})
        assert response.status_code == 422
