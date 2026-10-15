#!/usr/bin/env python3
"""Сгенерировать mymath_backend/node_types.py из truth/data/enums.json.

Значения CoreNodeType переносятся дословно из разбора APK, чтобы наш AST
и контракт ответа оставались сопоставимыми с оригиналом Photomath.
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "backend" / "mymath_backend" / "node_types.py"
SRC = ROOT / "truth" / "data" / "enums.json"

HEADER = '''"""Тип узла математического выражения.

Значения перечисления воспроизводят ``CoreNodeType`` из Photomath 7.10.0
(``com/microblink/photomath/core/results/CoreNodeType.java``) -- 143 элемента,
перенесены дословно и в исходном порядке: от ``CONSTANT`` до ``STRING``.

Источник истины: ``truth/data/enums.json`` -> ``node_types``.
Формат сериализации: ``truth/03-solver-contract.md`` раздел 3.2.
"""

from __future__ import annotations

from enum import StrEnum


class CoreNodeType(StrEnum):
    """Тип узла выражения.

    В JSON сериализуется именем элемента перечисления, как это делает Gson
    в оригинале. ``StrEnum`` даёт прямое совпадение со строкой из ответа.
    """

'''

FOOTER = '''

ALL_NODE_TYPES: tuple[str, ...] = tuple(CoreNodeType)
"""Все 143 типа в исходном порядке.

Служит проверкой полноты: решатель должен уметь породить каждый тип узла,
иначе часть шагов и ключей объяснений останется недостижимой.
"""


def is_known_type(value: str) -> bool:
    """Известен ли решателю такой тип узла.

    Нужен для диагностики входа: неизвестный тип означает либо опечатку в
    формате, либо расхождение версий с оригиналом.
    """
    return value in ALL_NODE_TYPES
'''


def main() -> int:
    """Перегенерировать node_types.py; завершает работу с кодом 1 при расхождении."""
    names = json.loads(SRC.read_text(encoding="utf-8"))["node_types"]
    if len(names) != 143:
        raise SystemExit(f"ожидалось 143 значения, получено {len(names)}")
    # Имена уже валидны как идентификаторы: верхний регистр, цифры, подчёркивание.
    for n in names:
        if not n.isidentifier() or n.upper() != n:
            raise SystemExit(f"имя не является константой: {n!r}")
    width = max(len(n) for n in names)
    # Один элемент в строке с явным значением. Без "= ..." тело класса
    # перечисления трактует имя как обращение к переменной, а не как член.
    lines = [f'    {n:<{width}} = "{n}"' for n in names]
    body = "\n".join(lines)
    OUT.write_text(HEADER + body + "\n" + FOOTER, encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {len(names)} значений, {len(lines)} строк")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
