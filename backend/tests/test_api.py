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


def var(name: str) -> dict:
    return {"type": "VARIABLE", "value": name}


def mul_implicit(a: dict, b: dict) -> dict:
    return {"type": "MULTIPLY_IMPLICIT", "children": [a, b]}


def equation(a: dict, b: dict) -> dict:
    return {"type": "EQUALS", "children": [a, b]}


class TestLocales:
    """Продукт поддерживает только русский и английский (truth/09-decisions.md)."""

    def test_health_lists_supported_locales(self, client: TestClient) -> None:
        assert client.get("/api/v1/health").json()["locales"] == ["ru", "en"]

    def test_english_maps_to_default(self, client: TestClient) -> None:
        body = solve(client, add(num("2"), num("3")), locale="en")
        view = body["result"]["groups"][0]["entries"][0]["result"]["steps"][0]["substeps"][0][
            "explanation"
        ]
        assert view["locale"] == "default"
        assert view["text"] == "Add the numbers"

    def test_dropped_locale_falls_back_to_english(self, client: TestClient) -> None:
        body = solve(client, add(num("2"), num("3")), locale="de")
        view = body["result"]["groups"][0]["entries"][0]["result"]["steps"][0]["substeps"][0][
            "explanation"
        ]
        assert view["locale"] == "default"

    def test_regional_russian_keeps_russian(self, client: TestClient) -> None:
        body = solve(client, add(num("2"), num("3")), locale="ru-RU")
        view = body["result"]["groups"][0]["entries"][0]["result"]["steps"][0]["substeps"][0][
            "explanation"
        ]
        assert view["locale"] == "ru"


class TestSolveEquations:
    def test_linear_equation_end_to_end(self, client: TestClient) -> None:
        node = equation(add(mul_implicit(num("2"), var("x")), num("3")), num("7"))
        body = solve(client, node, locale="ru")
        vertical = body["result"]["groups"][0]["entries"][0]["result"]
        assert vertical["solutionNode"]["type"] == "EQUALS"
        assert vertical["solutionNode"]["children"][1]["value"] == "2"
        keys = [
            sub["description"]["type"] for step in vertical["steps"] for sub in step["substeps"]
        ]
        assert keys == ["move", "eq_linar_divide_both_sides"]

    def test_step_header_has_rendered_text(self, client: TestClient) -> None:
        node = equation(add(mul_implicit(num("2"), var("x")), num("3")), num("7"))
        body = solve(client, node, locale="ru")
        steps = body["result"]["groups"][0]["entries"][0]["result"]["steps"]
        header = steps[0]["headers"][0]
        assert header["explanation"]["text"] == "Решите уравнение"
        assert header["explanation"]["locale"] == "ru"


class TestCommands:
    def test_factor(self, client: TestClient) -> None:
        node = add(
            add(
                {"type": "POWER", "children": [var("x"), num("2")]},
                mul_implicit(num("2"), var("x")),
            ),
            num("1"),
        )
        response = client.post(
            "/api/v1/solve",
            json={"node": node, "action": {"command": "factor", "args": []}},
        )
        assert response.status_code == 200, response.text
        vertical = response.json()["result"]["groups"][0]["entries"][0]["result"]
        keys = [s["description"]["type"] for st in vertical["steps"] for s in st["substeps"]]
        assert keys == ["factorise_call"]

    def test_unknown_command_is_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/solve",
            json={"node": num("1"), "action": {"command": "телепорт", "args": []}},
        )
        assert response.status_code == 422
        assert "команда" in response.json()["detail"]["message"]

    def test_link_returned_with_label_and_uuid(self, client: TestClient) -> None:
        """Ссылка в тексте шага приходит с меткой и uuid — для навигации."""
        node = add(
            add(
                {"type": "POWER", "children": [var("x"), num("2")]},
                mul_implicit(num("2"), var("x")),
            ),
            num("1"),
        )
        response = client.post(
            "/api/v1/solve",
            json={"node": node, "action": {"command": "factor", "args": []}, "locale": "default"},
        )
        substep = response.json()["result"]["groups"][0]["entries"][0]["result"]["steps"][0][
            "substeps"
        ][0]
        links = substep["explanation"]["links"]
        assert links and links[0]["label"] and links[0]["uuid"]
