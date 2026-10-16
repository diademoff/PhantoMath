"""Тесты развёртки пояснений (`service.attach_text`).

Проверяем, что тексты подставляются не только в шаги верхнего уровня, но и в
раскрываемое углублённое пояснение шага — вложенный ``subresult``.
"""

from __future__ import annotations

from typing import Any

from mymath_backend.service import attach_text


def _substep(key: str) -> dict[str, Any]:
    return {"description": {"type": key, "args": []}, "subanimations": []}


class TestAttachText:
    def test_recurses_into_subresult(self) -> None:
        node: dict[str, Any] = {
            "description": {"type": "function_evaluate_expr", "args": []},
            "substeps": [],
            "subresult": {"steps": [{"headers": [], "substeps": [_substep("add")]}]},
        }
        out = attach_text(node, "ru")
        nested = out["subresult"]["steps"][0]["substeps"][0]
        assert "explanation" in nested, "во вложенном шаге есть развёрнутый текст"
        assert nested["explanation"]["locale"] == "ru"
