"""Build truth/12-parity-matrix.md from cap/ (Photomath) and ours/ (PhantoMath)."""
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE.parents[1] / "truth" / "12-parity-matrix.md"


def load(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def verdict(pm: dict, ours: dict) -> tuple[str, str]:
    if pm.get("error") or not pm.get("steps"):
        return "нет эталона", pm.get("error", "шаги конкурента не сняты")
    if ours.get("error") or not ours.get("methods"):
        return "пробел", ours.get("error", "нет шагов")
    pm_steps = [s for s in pm["steps"] if s["text"] != "Решение"]
    best = ("расхождение", "")
    for i, m in enumerate(ours["methods"]):
        ok = [s["key"] for s in m["steps"]]
        same = len(ok) == len(pm_steps) and all(
            k in p["keys"] for k, p in zip(ok, pm_steps))
        note = f"способ {i + 1}: " + " → ".join(ok)
        if same:
            return "совпало", note
        best = ("расхождение", note)
    return best


def main() -> None:
    tasks = json.loads((HERE / "tasks.json").read_text())
    rows, by_section = [], defaultdict(list)
    for t in tasks:
        pm = load(HERE / "cap" / f"{t['id']}.json") or {"error": "не снято"}
        ours = load(HERE / "ours" / f"{t['id']}.json") or {"error": "не запущено"}
        v, note = verdict(pm, ours)
        pm_keys = " → ".join(
            "/".join(s["keys"][:2]) or f"«{s['text']}»"
            for s in pm.get("steps", []) if s["text"] != "Решение")
        by_section[t["section"]].append(v)
        rows.append(f"| {t['section']} | `{t['pm']}` | {v} | {pm_keys} | {note} |")
    total = sum(len(v) for v in by_section.values())
    done = sum(v.count("совпало") for v in by_section.values())
    lines = [
        "# 12. Матрица соответствия Photomath 7.10.0 ↔ PhantoMath",
        "",
        "Эталон: устройство Pixel 4a, Photomath 7.10.0 без входа (`tools/parity/pm.py`).",
        "Ключи эталона восстановлены сопоставлением текста шага с русскими шаблонами",
        "`truth/data/explanations.json`; неоднозначные тексты дают несколько кандидатов",
        "(`a/b`). Наша сторона — `tools/parity/ours.py`. Сравниваются верхние шаги.",
        "«Совпало» — только то, что проверено на этих задачах; не вывод о разделе в целом.",
        "",
        f"Совпало {done} из {total}.",
        "",
        "| Раздел | Ввод (клавиши) | Итог | Шаги Photomath | Наши шаги |",
        "|---|---|---|---|---|",
        *rows,
        "",
    ]
    OUT.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
