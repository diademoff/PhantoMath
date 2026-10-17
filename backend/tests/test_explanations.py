"""Тесты резолвера объяснений.

Сверяются с реальными шаблонами, извлечёнными из resources.arsc:
truth/data/explanations.json. Формат шаблонов разобран в truth/04.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from mymath_backend import CoreNode, CoreNodeType
from mymath_backend.explanations import (
    DEFAULT_LOCALE,
    Explanations,
    load_explanations,
)
from mymath_backend.teaching import TEMPLATES
from mymath_backend.translations import SUPPLEMENTARY

TRUTH = Path(__file__).resolve().parents[2] / "truth" / "data"
EXPLANATIONS = TRUTH / "explanations.json"


@pytest.fixture(scope="module")
def explanations() -> Explanations:
    return load_explanations(str(EXPLANATIONS))


class TestCorpusIntegrity:
    def test_key_count(self, explanations: Explanations) -> None:
        artifact = json.loads(EXPLANATIONS.read_text(encoding="utf-8"))
        assert len(artifact) == 3252  # the research artifact remains intact
        assert set(explanations) == set(artifact) | set(TEMPLATES)

    def test_every_key_has_english(self, explanations: Explanations) -> None:
        without = [k for k in explanations if explanations.raw_template(k, DEFAULT_LOCALE) is None]
        assert without == []

    def test_nine_locales_present(self, explanations: Explanations) -> None:
        assert {
            DEFAULT_LOCALE,
            "de",
            "es",
            "fr",
            "it",
            "pl",
            "pt",
            "ru",
            "uk",
        } <= explanations.locales()

    def test_arity_matches_template(self, explanations: Explanations) -> None:
        """Арность из keys.txt обязана совпадать с максимальным ARGn.

        Расхождение означало бы, что подстановка обрежет смысл предложения.
        """
        bad = []
        for key in explanations:
            template = explanations.raw_template(key, DEFAULT_LOCALE) or ""
            found = [int(m) for m in re.findall(r"ARG(\d+)", template)]
            highest = max(found) if found else 0
            if highest != explanations.arity(key):
                bad.append((key, explanations.arity(key), highest))
        assert bad == []

    def test_corpus_matches_keys_txt(self, explanations: Explanations) -> None:
        """Все 3020 ключа из assets/keys.txt присутствуют в словаре."""
        keys_txt = Path("/tmp/opencode/mymath/apk/assets/keys.txt")
        if not keys_txt.exists():
            pytest.skip("keys.txt недоступен: нужен распакованный APK")
        from_apk = {
            line.split(";")[0]
            for line in keys_txt.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        assert len(from_apk) == 3020
        assert from_apk <= set(explanations.keys())


class TestSupplementary:
    """Наши переводы: заполняют пробелы, извлечённые данные не трогают.

    Русский шаблон есть не у всех ключей `arsc`, и продукт (только `ru`/`en`)
    молча показывал английский текст в русском шаге.
    """

    def test_russian_text_appears(self, explanations: Explanations) -> None:
        rendered = explanations.render("conics_identify_disc", [], "ru")
        assert rendered.locale == "ru"
        assert rendered.text == SUPPLEMENTARY["conics_identify_disc"]["ru"]

    def test_extracted_artifact_untouched(self) -> None:
        """Дополнение живёт в коде: файл-артефакт остаётся как извлекли."""
        raw = json.loads(EXPLANATIONS.read_text(encoding="utf-8"))
        assert "ru" not in raw["conics_identify_disc"]["templates"]

    def test_only_missing_locales_are_filled(self) -> None:
        raw = json.loads(EXPLANATIONS.read_text(encoding="utf-8"))
        problems: list[str] = []
        for key, templates in SUPPLEMENTARY.items():
            if key not in raw:
                problems.append(f"{key}: нет в извлечённом словаре")
                continue
            for locale, text in templates.items():
                if locale in raw[key]["templates"]:
                    problems.append(f"{key}/{locale}: язык уже есть в словаре")
                if not text.strip():
                    problems.append(f"{key}/{locale}: пустой текст")
        assert problems == []


class TestRendering:
    def test_plain_template_without_args(self, explanations: Explanations) -> None:
        out = explanations.render("abs_neg", [], "ru")
        assert out.locale == "ru"
        assert out.missing_key is False
        assert "модуль" in out.text.lower()

    def test_arg_substitution(self, explanations: Explanations) -> None:
        # abs_const_long: "Since ARG1, the [link] of ARG2 is ARG3", arity 3
        args = [CoreNode.variable("x"), CoreNode.constant("7"), CoreNode.constant("7")]
        out = explanations.render("abs_const_long", args, DEFAULT_LOCALE)
        assert "x" in out.text
        assert out.text.count("7") == 2
        assert "ARG" not in out.text

    def test_missing_arg_placeholder_is_kept(self, explanations: Explanations) -> None:
        """Аргумента нет — оставляем ARGn, чтобы дефект был виден, а не тих."""
        out = explanations.render("abs_const_long", [CoreNode.variable("x")])
        assert "ARG2" in out.text
        assert "ARG3" in out.text

    def test_locale_fallback_chain(self, explanations: Explanations) -> None:
        assert explanations.render("abs_neg", [], "ru").locale == "ru"
        assert explanations.render("abs_neg", [], "default").locale == DEFAULT_LOCALE
        # Неизвестный язык откатывается на английский, а не пропадает.
        assert explanations.render("abs_neg", [], "xx").locale == DEFAULT_LOCALE

    def test_regional_locale_falls_back_to_base(self, explanations: Explanations) -> None:
        assert explanations.render("abs_neg", [], "ru-RU").locale == "ru"

    def test_missing_key_is_reported_not_raised(self, explanations: Explanations) -> None:
        out = explanations.render("такого_ключа_нет")
        assert out.missing_key is True
        assert out.text == "?? step_такого_ключа_нет ??"


class TestLinkMarkup:
    def test_link_is_extracted_and_removed(self, explanations: Explanations) -> None:
        # abs_const_long содержит [absolute value|f20b5152-…] без хвостовой метки.
        template = explanations.raw_template("abs_const_long", DEFAULT_LOCALE)
        assert template is not None and "|" in template
        out = explanations.render("abs_const_long")
        assert "|" not in out.text
        assert len(out.links) == 1
        assert re.fullmatch(r"[0-9a-f-]{36}", out.links[0].uuid)
        assert out.links[0].label in out.text

    def test_tail_label_removed_from_text(self, explanations: Explanations) -> None:
        """Метка в конце строки без ссылки убирается и возвращается отдельно.

        abs_equals_itself заканчивается на "… must be ARG2 [5ce6258d-…]".
        """
        out = explanations.render(
            "abs_equals_itself", [CoreNode.variable("x"), CoreNode.variable("x")]
        )
        assert out.tail_label == "5ce6258d-e3bb-4de7-a03b-6cf41acbb948"
        assert not out.text.rstrip().endswith("]")
        assert out.links == ()

    def test_tail_and_link_can_coexist(self, explanations: Explanations) -> None:
        """abs_neg: ссылка в середине и хвостовая метка в конце."""
        out = explanations.render("abs_neg")
        assert len(out.links) == 1
        assert out.tail_label is not None
        assert "|" not in out.text


class TestCustomArgRenderer:
    def test_renderer_is_used_for_args(self, explanations: Explanations) -> None:
        def render(node: CoreNode) -> str:
            return f"<{node.type.value}:{node.value or ''}>"

        out = explanations.render(
            "abs_const_long",
            [CoreNode.variable("x"), CoreNode.constant("7"), CoreNode.constant("7")],
            DEFAULT_LOCALE,
            render_arg=render,
        )
        assert "<VARIABLE:x>" in out.text
        assert out.text.count("<CONSTANT:7>") == 2

    def test_default_renderer_handles_fractions(self) -> None:
        from mymath_backend.explanations import _default_render_arg

        frac = CoreNode.node(CoreNodeType.FRACTION, CoreNode.constant(1), CoreNode.variable("x"))
        assert _default_render_arg(frac) == "(1)/(x)"
        sqrt = CoreNode.node(CoreNodeType.ROOT2, CoreNode.variable("x"))
        assert _default_render_arg(sqrt) == "sqrt(x)"
