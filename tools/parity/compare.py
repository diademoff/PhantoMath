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
    """Per row, per stage: does Photomath offer a detail screen (expand button present)."""
    return [[bool(st["nested"]) for st in g["stages"]] for g in pm.get("walk", [])]


def our_shape(m: dict) -> list[list[bool]]:
    return [[bool(s["detail"]) for s in g["stages"]] for g in m["steps"]]


def pm_cards(pm: dict) -> list[tuple[str, list[list[bool]]]]:
    """Distinct captured cards (solution methods) as ``(label, shape)``; old captures have one."""
    cards = pm.get("cards") or []
    seen, out = set(), []
    for card in cards:
        if not isinstance(card, dict) or not card.get("walk"):
            continue
        label = (card.get("title", ""), card.get("subtitle", ""))
        shape = [[bool(st["nested"]) for st in g["stages"]] for g in card["walk"]]
        key = (label, str(shape))
        if key in seen:
            continue
        seen.add(key)
        out.append((" / ".join(x for x in label if x) or "—", shape))
    if not out and pm.get("walk"):
        out.append(("—", pm_shape(pm)))
    return out


def _covers(ours: list[list[bool]], pm: list[list[bool]]) -> bool:
    """Same rows and stages; our detail screens may exceed Photomath's, never fall short."""
    return len(ours) == len(pm) and all(
        len(o) == len(p) and all(a or not b for a, b in zip(o, p, strict=True))
        for o, p in zip(ours, pm, strict=True)
    )


def verdict(pm: dict, ours: dict) -> tuple[str, str]:
    cards = pm_cards(pm)
    if pm.get("error") or not cards:
        return "нет эталона", pm.get("error", "шаги конкурента не сняты")
    if ours.get("error") or not ours.get("methods"):
        return "пробел", ours.get("error", "нет шагов")
    mine = [our_shape(m) for m in ours["methods"]]
    unused = list(range(len(mine)))
    matched = 0
    for _label, shape in cards:
        hit = next((i for i in unused if _covers(mine[i], shape)), None)
        if hit is not None:
            unused.remove(hit)
            matched += 1
    note = "наши способы: " + "; ".join(_fmt(m) for m in mine)
    if matched == len(cards):
        return ("структура совпала", note) if len(cards) == 1 else (
            f"структура совпала ({matched} из {len(cards)})", note)
    if matched:
        return f"частично ({matched} из {len(cards)})", note
    return "структура отличается", note


def main() -> None:
    tasks = json.loads((HERE / "tasks.json").read_text())
    rows, by_section = [], defaultdict(list)
    for t in tasks:
        pm = load(HERE / "cap" / f"{t['id']}.json") or {"error": "не снято"}
        ours = load(HERE / "ours" / f"{t['id']}.json") or {"error": "не запущено"}
        v, note = verdict(pm, ours)
        pm_keys = "; ".join(f"{label}: {_fmt(shape)}" for label, shape in pm_cards(pm))
        by_section[t["section"]].append(v)
        rows.append(f"| {t['section']} | `{t['pm']}` | {v} | {pm_keys} | {note} |")
    total = sum(len(v) for v in by_section.values())
    full = sum(1 for v in by_section.values() for x in v if x.startswith("структура совпала"))
    partial = sum(1 for v in by_section.values() for x in v if x.startswith("частично"))
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
        f"Все способы совпали по структуре: {full} из {total} задач; частично: {partial}.",
        "",
        "| Раздел | Ввод (клавиши) | Итог | Шаги Photomath | Наши шаги |",
        "|---|---|---|---|---|",
        *rows,
        "",
    ]
    OUT.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
