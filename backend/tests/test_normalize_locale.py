"""Тесты нормализации языка (`service.normalize_locale`).

Продукт поддерживает только два языка, поэтому функция обязана свести любой
вход к `ru` либо к английскому (`default`), в том числе регистр, пробелы и
диалекты вида `ru-RU`.
"""

from __future__ import annotations

from mymath_backend.explanations import DEFAULT_LOCALE
from mymath_backend.service import normalize_locale


class TestNormalizeLocale:
    def test_russian(self) -> None:
        assert normalize_locale("ru") == "ru"

    def test_uppercase_russian(self) -> None:
        assert normalize_locale("RU") == "ru"

    def test_russian_dialect_with_spaces(self) -> None:
        assert normalize_locale(" ru-RU ") == "ru"

    def test_english(self) -> None:
        assert normalize_locale("en") == DEFAULT_LOCALE

    def test_german_falls_back(self) -> None:
        assert normalize_locale("de") == DEFAULT_LOCALE

    def test_french_canadian_falls_back(self) -> None:
        assert normalize_locale("fr-CA") == DEFAULT_LOCALE

    def test_empty_falls_back(self) -> None:
        assert normalize_locale("") == DEFAULT_LOCALE
