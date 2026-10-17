"""Build truth/12-parity-matrix.md from cap/ (Photomath) and ours/ (PhantoMath)."""
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE.parents[1] / "truth" / "12-parity-matrix.md"


def load(p: Path):
    return json.loads(p.read_text()) if p.exists() else None


def _fmt(shape: list[list[bool]]) -> str:
    return " | ".join("".join("+" if x else "-" for x in g) for g in shape) or "—"


def pm_shape(pm: dict) -> list[list[bool]]:
    """Per group, per stage: does Photomath offer a detail screen (rows after «Решение»)."""
    return [[bool(st["nested"][st["nested"].index("Решение") + 1:])
             if "Решение" in st["nested"] else False for st in g["stages"]]
            for g in pm.get("walk", [])]


def our_shape(m: dict) -> list[list[bool]]:
    return [[bool(s["detail"]) for s in g["stages"]] for g in m["steps"]]


def verdict(pm: dict, ours: dict) -> tuple[str, str]:
    if pm.get("error") or not pm.get("walk"):
        return "нет эталона", pm.get("error", "шаги конкурента не сняты")
    if ours.get("error") or not ours.get("methods"):
        return "пробел", ours.get("error", "нет шагов")
    want = pm_shape(pm)
    best = None
    for i, m in enumerate(ours["methods"]):
        got = our_shape(m)
        note = f"способ {i + 1}: {_fmt(got)}"
        if got == want:
            return "структура совпала", note
        best = best or note
    return "структура отличается", best


def main() -> None:
    tasks = json.loads((HERE / "tasks.json").read_text())
    rows, by_section = [], defaultdict(list)
    for t in tasks:
        pm = load(HERE / "cap" / f"{t['id']}.json") or {"error": "не снято"}
        ours = load(HERE / "ours" / f"{t['id']}.json") or {"error": "не запущено"}
        v, note = verdict(pm, ours)
        want = pm_shape(pm)
        pm_keys = _fmt(want) + ": " + " → ".join(
            st["text"].split("\n")[0] for g in pm.get("walk", []) for st in g["stages"])
        by_section[t["section"]].append(v)
        rows.append(f"| {t['section']} | `{t['pm']}` | {v} | {pm_keys} | {note} |")
    total = sum(len(v) for v in by_section.values())
    done = sum(v.count("структура совпала") for v in by_section.values())
    lines = [
        "# 12. Матрица соответствия Photomath 7.10.0 ↔ PhantoMath",
        "",
        "Эталон: устройство Pixel 4a, Photomath 7.10.0 без входа (`tools/parity/pm.py`).",
        "Ключи эталона восстановлены сопоставлением текста шага с русскими шаблонами",
        "`truth/data/explanations.json`; неоднозначные тексты дают несколько кандидатов",
        "(`a/b`). Наша сторона — `tools/parity/ours.py`. Сравнивается структура: группы шагов, этапы в них и наличие вложенного разбора у каждого этапа",
        "(`+`/`-`; группы разделены `|`). Формулировки авторские и не сравниваются.",
        "«Совпало» — только то, что проверено на этих задачах; не вывод о разделе в целом.",
        "",
        f"Структура совпала в {done} из {total}.",
        "",
        "| Раздел | Ввод (клавиши) | Итог | Шаги Photomath | Наши шаги |",
        "|---|---|---|---|---|",
        *rows,
        "",
    ]
    OUT.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
