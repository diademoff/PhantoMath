"""Every node type the solver emits for the corpus must be known to the Flutter app.

An unknown wire type becomes an empty text node in the app: a ``±`` or an ``i`` silently
vanishes from the formula. The Dart enum is read as text, so no Flutter toolchain is needed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from test_corpus import TASKS

from mymath_backend.input import parse_protocol
from mymath_backend.solver import solve

DART_MODEL = (
    Path(__file__).resolve().parents[2] / "app" / "lib" / "src" / "model" / "core_node.dart"
)
KNOWN = set(re.findall(r"\('([A-Z0-9_]+)'\)", DART_MODEL.read_text(encoding="utf-8")))
# result envelope and unit-less helper nodes that never reach a formula
NOT_FORMULA = {"VERTICAL"}


def _types(part: Any, found: set[str]) -> None:
    if isinstance(part, dict):
        kind = part.get("type")
        if isinstance(kind, str) and kind.isupper():
            found.add(kind)
        for value in part.values():
            _types(value, found)
    elif isinstance(part, list):
        for value in part:
            _types(value, found)


def test_the_app_draws_every_node_type_the_corpus_produces() -> None:
    missing: dict[str, str] = {}
    for name, task in TASKS:
        try:
            data = solve(
                parse_protocol(task["input"]),
                command=task.get("command"),
                args=[parse_protocol(arg) for arg in task.get("args", [])],
            )
        except Exception:
            continue
        found: set[str] = set()
        _types(data.to_contract(), found)
        for kind in found - KNOWN - NOT_FORMULA:
            missing.setdefault(kind, name)
    assert missing == {}, "node types unknown to app/lib/src/model/core_node.dart"
