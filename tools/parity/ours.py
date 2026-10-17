"""Run tasks.json through our solver; write ours/<id>.json (method -> step keys)."""
import json
import sys
from pathlib import Path

from mymath_backend import service
from mymath_backend.input import parse_protocol

HERE = Path(__file__).parent
OUT = HERE / "ours"


def _steps(result: dict) -> list[dict]:
    out = []
    for st in result.get("steps", []):
        for s in st["substeps"]:
            sub = s.get("subresult")
            out.append({
                "key": s["description"]["type"],
                "text": (s.get("explanation") or {}).get("text", ""),
                "headers": [(h.get("explanation") or {}).get("text", "") for h in st["headers"]],
                "detail": _steps(sub) if isinstance(sub, dict) else [],
                "theory": bool((s.get("explanation") or {}).get("theory")),
            })
    return out


def run(task: dict) -> dict:
    try:
        out = service.solve_request(parse_protocol(task["proto"]).to_contract(), render=True, locale="ru")
    except Exception as e:  # unsupported input is data, not a crash
        return {"id": task["id"], "error": f"{type(e).__name__}: {e}"}
    methods = [
        {"steps": _steps(e["result"])}
        for g in out["result"]["groups"] if g["type"] == "VERTICAL"
        for e in g["entries"] if e.get("result") and "steps" in e["result"]
    ]
    return {"id": task["id"], "methods": methods}


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for t in json.loads((HERE / "tasks.json").read_text()):
        if len(sys.argv) > 1 and t["id"] not in sys.argv[1:]:
            continue
        (OUT / f"{t['id']}.json").write_text(
            json.dumps(run(t), ensure_ascii=False, indent=1))
