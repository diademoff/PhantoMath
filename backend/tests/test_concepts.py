"""Тесты глоссария понятий.

Определения — наши, короткие, на двух языках. Проверяем, что они есть для
всех заведённых uuid, что неизвестный uuid не падает и что ссылка из ответа
решателя получает определение.
"""

from __future__ import annotations

import re

from mymath_backend.concepts import CONCEPTS, definition

UUID = re.compile(r"^[0-9a-fA-F-]{36}$")


class TestConcepts:
    def test_every_uuid_is_uuid_and_has_both_locales(self) -> None:
        for uuid, entry in CONCEPTS.items():
            assert UUID.match(uuid), uuid
            assert entry.get("ru")
            assert entry.get("en")

    def test_lookup(self) -> None:
        uuid = "1ceef362-dfb4-4ae6-ba5d-46dbd862a37b"
        assert definition(uuid, "ru") is not None
        assert definition(uuid, "en") is not None
        assert definition(uuid, "ru") != definition(uuid, "en")

    def test_unknown_uuid(self) -> None:
        assert definition("00000000-0000-0000-0000-000000000000") is None
