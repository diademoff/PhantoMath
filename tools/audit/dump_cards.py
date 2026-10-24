"""Dump the solver's solution cards for ``app/test/card_transcript_test.dart``.

Usage::

    backend/.venv/bin/python tools/audit/dump_cards.py TASKS.json OUT.json [--locale ru]

``TASKS.json`` is a list of ``{id, proto, ...}``; a task without ``proto`` is
skipped. Every card is stored as ``{id, proto, response}`` (``{id, proto,
error}`` when the solver raises), exactly what the app receives from the
backend.  See ``make cards``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from mymath_backend import service
from mymath_backend.input import parse_protocol


def dump(tasks: Path, locale: str) -> list[dict]:
    out = []
    for task in json.loads(tasks.read_text(encoding="utf-8")):
        proto = task.get("proto")
        if not proto:
            continue
        item = {"id": task["id"], "proto": proto}
        try:
            item["response"] = service.solve_request(
                parse_protocol(proto).to_contract(), render=True, locale=locale
            )
        except Exception as error:  # noqa: BLE001  the corpus keeps unsolvable tasks
            item["error"] = f"{type(error).__name__}: {error}"
        out.append(item)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks", help="JSON list of tasks")
    parser.add_argument("out", help="JSON file to write")
    parser.add_argument("--locale", default="ru")
    args = parser.parse_args()
    cards = dump(Path(args.tasks), args.locale)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    errors = sum(1 for card in cards if "error" in card)
    print(f"{len(cards)} cards ({errors} errors) -> {target}")


if __name__ == "__main__":
    main()
