"""Точка входа Python-программы, встроенной в приложение (serious_python).

Запускается в фоновом потоке при старте приложения и поднимает локальный
сервер решателя на ``127.0.0.1``. Словарь пояснений лежит внутри пакета
``mymath_backend`` (``data/explanations.json``).
"""

from __future__ import annotations

from mymath_backend import device

device.main()
