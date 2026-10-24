"""Dump the solver's answers for the corpus and the sample inputs, for ``app/test/formula_audit_test.dart``.

Usage: ``backend/.venv/bin/python tools/audit/dump_contracts.py OUT.json`` and then
``CONTRACTS=OUT.json flutter test test/formula_audit_test.dart`` (see ``make audit``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from mymath_backend import service
from mymath_backend.input import parse_protocol


def main(target: str) -> None:
    out = []
    for path in sorted((ROOT / "backend" / "tests" / "corpus").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for task in data["tasks"]:
            action = None
            if task.get("command"):
                args = [parse_protocol(a).to_contract() for a in task.get("args", [])]
                action = {"command": task["command"], "args": args}
            try:
                response = service.solve_request(
                    parse_protocol(task["input"]).to_contract(), action, render=True, locale="ru"
                )
            except Exception:  # noqa: BLE001  unsolvable corpus tasks have nothing to draw
                continue
            out.append({"input": f"{data['module']}/{task['id']}", "response": response})
    for task in json.loads((ROOT / "backend" / "tests" / "inputs.json").read_text(encoding="utf-8")):
        try:
            response = service.solve_request(
                parse_protocol(task["proto"]).to_contract(), render=True, locale="ru"
            )
        except Exception:  # noqa: BLE001
            continue
        out.append({"input": f"inputs/{task['id']}", "response": response})
    Path(target).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"{len(out)} answers -> {target}")


if __name__ == "__main__":
    main(sys.argv[1])
