"""Точка входа Python-программы, встроенной в приложение (serious_python).

Запускается в фоновом потоке при старте приложения, поднимает локальный
сервер решателя на ``127.0.0.1`` и слушает его. Словарь объяснений лежит
рядом, в ``assets/explanations.json`` (его кладёт сюда ``make python-bundle``).

``serious_python`` не задаёт ``__file__``, поэтому каталог приложения
ищем через ``sys.path`` (движок кладёт его нулевым элементом).
"""

from __future__ import annotations

import os
import sys


def _find_explanations() -> str | None:
    """Путь к словарю в каталоге приложения или ``None``."""
    for entry in sys.path:
        if not entry:
            continue
        candidate = os.path.join(entry, "assets", "explanations.json")
        if os.path.exists(candidate):
            return candidate
    return None


_explanations = _find_explanations()
if _explanations:
    os.environ.setdefault("MYMATH_EXPLANATIONS", _explanations)

from mymath_backend import device  # noqa: E402  (после установки переменной)

device.main()
