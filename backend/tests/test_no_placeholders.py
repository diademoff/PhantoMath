"""No explanation shown to the student may still contain an ``ARGn`` placeholder.

A step or a row title whose template needs an argument that the solver did not pass reads
"Найдите ARG1" in the app. The corpus and the sample inputs (``inputs.json``) are rendered
with ``render=True`` and every explanation text, in headers, steps and nested screens, is checked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from test_corpus import TASKS

from mymath_backend import service
from mymath_backend.input import parse_protocol

INPUTS = Path(__file__).resolve().parent / "inputs.json"


def _leftovers(part: Any, where: str, found: dict[str, str]) -> None:
    if isinstance(part, dict):
        explanation = part.get("explanation")
        if isinstance(explanation, dict) and "ARG" in (explanation.get("text") or ""):
            found.setdefault(str(explanation.get("key")), where)
        for value in part.values():
            _leftovers(value, where, found)
    elif isinstance(part, list):
        for value in part:
            _leftovers(value, where, found)


def test_no_explanation_text_keeps_an_argument_placeholder() -> None:
    sources = [(name, task["input"], task.get("command")) for name, task in TASKS]
    sources += [
        (f"inputs/{task['id']}", task["proto"], None)
        for task in json.loads(INPUTS.read_text(encoding="utf-8"))
    ]
    found: dict[str, str] = {}
    for name, source, command in sources:
        try:
            response = service.solve_request(
                parse_protocol(source).to_contract(),
                {"command": command, "args": []} if command else None,
                render=True,
                locale="ru",
            )
        except Exception:
            continue
        _leftovers(response, name, found)
    assert found == {}, "templates rendered without their arguments (key: first task)"
