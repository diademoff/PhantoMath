"""Точка входа Python-программы, встроенной в приложение (serious_python).

Запускается в фоновом потоке при старте приложения, поднимает локальный
сервер решателя на ``127.0.0.1`` и слушает его. Словарь объяснений лежит
рядом, в ``assets/explanations.json`` (его кладёт сюда ``make python-bundle``).

Программа блокирующая: ``serious_python`` держит поток, пока работает
``serve_forever``.
"""

from __future__ import annotations

import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPLANATIONS = os.path.join(_HERE, "assets", "explanations.json")
if os.path.exists(_EXPLANATIONS):
    os.environ.setdefault("MYMATH_EXPLANATIONS", _EXPLANATIONS)

from mymath_backend import device  # noqa: E402  (после установки переменной)

device.main()
