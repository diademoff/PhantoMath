"""Тесты резолвера объяснений на словаре пакета ``data/explanations.json``."""

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
from mymath_backend.service import explanations_path
from mymath_backend.teaching import TEMPLATES
from mymath_backend.teaching_registry import templates as pack_templates

EXPLANATIONS = explanations_path()


@pytest.fixture(scope="module")
def explanations() -> Explanations:
    return load_explanations(str(EXPLANATIONS))


class TestDictionary:
    def test_lessons_are_merged(self, explanations: Explanations) -> None:
        data = json.loads(EXPLANATIONS.read_text(encoding="utf-8"))
        assert set(explanations) == set(data) | set(TEMPLATES) | set(pack_templates())

    def test_every_key_has_russian_and_english(self) -> None:
        data = json.loads(EXPLANATIONS.read_text(encoding="utf-8"))
        missing = [
            key
            for key, entry in data.items()
            if not entry["templates"].get("ru") or not entry["templates"].get(DEFAULT_LOCALE)
        ]
        assert missing == []

    def test_only_two_languages(self, explanations: Explanations) -> None:
        assert explanations.locales() == {DEFAULT_LOCALE, "ru"}

    def test_arity_matches_template(self, explanations: Explanations) -> None:
        """Арность обязана совпадать с максимальным ARGn в обоих языках.

        Расхождение означало бы, что подстановка обрежет смысл предложения.
        """
        bad = []
        for key in explanations:
            for locale in (DEFAULT_LOCALE, "ru"):
                template = explanations.raw_template(key, locale) or ""
                found = [int(m) for m in re.findall(r"ARG(\d+)", template)]
                highest = max(found) if found else 0
                if highest > explanations.arity(key):
                    bad.append((key, locale, explanations.arity(key), highest))
        assert bad == []

    def test_russian_text_has_no_latin_lookalikes(self) -> None:
        """Слово, набранное латинской «e» среди кириллицы, выглядит верно, но не ищется."""
        data = json.loads(EXPLANATIONS.read_text(encoding="utf-8"))
        mixed = re.compile(r"[А-Яа-яЁё][a-zA-Z]|[a-zA-Z][А-Яа-яЁё]")
        bad = [key for key, entry in data.items() if mixed.search(entry["templates"]["ru"])]
        assert bad == []

    def test_undefined_reads_as_a_word(self, explanations: Explanations) -> None:
        assert explanations.render("undefined", [], "ru").text == "Не определено"
        assert explanations.render("undefined", [], DEFAULT_LOCALE).text == "Undefined"


class TestRendering:
    def test_plain_template_without_args(self, explanations: Explanations) -> None:
        out = explanations.render("abs_neg", [], "ru")
        assert out.locale == "ru"
        assert out.missing_key is False
        assert "модуль" in out.text.lower()

    def test_arg_substitution(self, explanations: Explanations) -> None:
        # conics_classify_circle: "… form ARG1: a [circle|…] with radius ARG2 and center ARG3"
        args = [CoreNode.variable("x"), CoreNode.constant("7"), CoreNode.constant("7")]
        out = explanations.render("conics_classify_circle", args, DEFAULT_LOCALE)
        assert "x" in out.text
        assert out.text.count("7") == 2
        assert "ARG" not in out.text

    def test_missing_arg_placeholder_is_kept(self, explanations: Explanations) -> None:
        """Аргумента нет — оставляем ARGn, чтобы дефект был виден, а не тих."""
        out = explanations.render("conics_classify_circle", [CoreNode.variable("x")])
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
        # conics_classify_circle содержит [circle|b56e7f77-…] без хвостовой метки.
        template = explanations.raw_template("conics_classify_circle", DEFAULT_LOCALE)
        assert template is not None and "|" in template
        out = explanations.render("conics_classify_circle")
        assert "|" not in out.text
        assert len(out.links) == 1
        assert re.fullmatch(r"[0-9a-f-]{36}", out.links[0].uuid)
        assert out.links[0].label in out.text

    def test_tail_label_removed_from_text(self, explanations: Explanations) -> None:
        """Метка в конце строки без ссылки убирается и возвращается отдельно.

        eq_irrational_simple_square заканчивается на "… both sides [265f2b38-…]".
        """
        out = explanations.render("eq_irrational_simple_square", [], DEFAULT_LOCALE)
        assert out.tail_label == "265f2b38-6af0-430d-a665-657c29a60866"
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
            "conics_classify_circle",
            [CoreNode.variable("x"), CoreNode.constant("7"), CoreNode.constant("7")],
            DEFAULT_LOCALE,
            render_arg=render,
        )
        assert "<VARIABLE:x>" in out.text
        assert out.text.count("<CONSTANT:7>") == 2

    def test_default_renderer_handles_fractions(self) -> None:
        from mymath_backend.explanations import _default_render_arg

        frac = CoreNode.node(CoreNodeType.FRACTION, CoreNode.constant(1), CoreNode.variable("x"))
        assert _default_render_arg(frac) == "1/x"
        sqrt = CoreNode.node(CoreNodeType.ROOT2, CoreNode.variable("x"))
        assert _default_render_arg(sqrt) == "sqrt(x)"

    def test_default_renderer_parenthesizes_compound_fraction_parts(self) -> None:
        from mymath_backend.explanations import _default_render_arg

        frac = CoreNode.node(
            CoreNodeType.FRACTION,
            CoreNode.node(CoreNodeType.ADD, CoreNode.variable("x"), CoreNode.constant("1")),
            CoreNode.node(CoreNodeType.SUBTRACT, CoreNode.variable("x"), CoreNode.constant("1")),
        )
        assert _default_render_arg(frac) == "(x + 1)/(x - 1)"

    def test_default_renderer_writes_plus_minus_as_a_sign(self) -> None:
        """The quadratic formula read «add_subtract(-b, …)» in a step title."""
        from mymath_backend.explanations import _default_render_arg

        b = CoreNode.variable("b")
        root = CoreNode.node(CoreNodeType.ROOT2, CoreNode.variable("D"))
        pair = CoreNode.node(CoreNodeType.ADD_SUBTRACT, b, root)
        assert _default_render_arg(pair) == "b ± sqrt(D)"
        assert _default_render_arg(CoreNode.node(CoreNodeType.ADD_SUBTRACT, root)) == "±sqrt(D)"

    def test_default_renderer_keeps_factorials_and_permutations(self) -> None:
        """«partial_permutation_…(n, r) = n/(n - r)» lost both the name and the «!»."""
        from mymath_backend.explanations import _default_render_arg

        n, r = CoreNode.variable("n"), CoreNode.variable("r")
        perm = CoreNode.node(CoreNodeType.PARTIAL_PERMUTATION_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT, n, r)
        diff = CoreNode.node(CoreNodeType.SUBTRACT, n, r)
        assert _default_render_arg(perm) == "P(n, r)"
        assert _default_render_arg(CoreNode.node(CoreNodeType.FACTORIAL, n)) == "n!"
        assert _default_render_arg(CoreNode.node(CoreNodeType.FACTORIAL, diff)) == "(n - r)!"

    def test_default_renderer_writes_sums_without_node_names(self) -> None:
        """The binomial theorem read «sigma_definite(k, 0, n, …)» in a step title."""
        from mymath_backend.explanations import _default_render_arg
        from mymath_backend.input import parse_protocol

        k, n = CoreNode.variable("k"), CoreNode.variable("n")
        term = CoreNode.node(CoreNodeType.POWER, CoreNode.variable("a"), k)
        sigma = CoreNode.node(CoreNodeType.SIGMA_DEFINITE, k, CoreNode.constant("0"), n, term)
        assert _default_render_arg(sigma) == "Σ(k=0..n) a^k"
        assert "sigma" not in _default_render_arg(parse_protocol("{sigma_def({1},{5},{n^2})}"))

    def test_default_renderer_keeps_function_argument(self) -> None:
        from mymath_backend.explanations import _default_render_arg

        sine = CoreNode.node(CoreNodeType.SIN, CoreNode.variable("u"))
        assert _default_render_arg(sine) == "sin(u)"

    def test_default_renderer_writes_limits_without_node_names(self) -> None:
        from mymath_backend.explanations import _default_render_arg

        limit = CoreNode.node(
            CoreNodeType.LIMIT,
            CoreNode.constant("0"),
            CoreNode.node(
                CoreNodeType.FRACTION,
                CoreNode.node(CoreNodeType.SIN, CoreNode.variable("u")),
                CoreNode.variable("u"),
            ),
        )
        assert _default_render_arg(limit) == "lim(x→0) sin(u)/u"
        right = CoreNode.node(
            CoreNodeType.LIMIT_RIGHT,
            CoreNode.constant("0"),
            CoreNode.node(CoreNodeType.FRACTION, CoreNode.constant("1"), CoreNode.variable("x")),
        )
        assert _default_render_arg(right) == "lim(x→0+) 1/x"


_MATH_RENDERINGS = {
    "sin",
    "cos",
    "tan",
    "cot",
    "tg",
    "ctg",
    "asin",
    "acos",
    "atan",
    "acot",
    "arcsin",
    "arccos",
    "arctg",
    "arcctg",
    "sinh",
    "cosh",
    "tanh",
    "coth",
    "sh",
    "ch",
    "th",
    "cth",
    "sech",
    "csch",
    "ln",
    "lg",
    "log",
    "exp",
    "abs",
    "sign",
    "sqrt",
    "root",
}
_RAW_NODE_TEXT = re.compile(
    r"\b("
    + "|".join(
        re.escape(name)
        for name in sorted(
            {node_type.value.lower() for node_type in CoreNodeType} - _MATH_RENDERINGS,
            key=len,
            reverse=True,
        )
    )
    + r")\("
)
_ATOM_PARENS = re.compile(r"\((?:\d+|[A-Za-z])\)/\((?:\d+|[A-Za-z])\)")


def _explanation_texts(value: object) -> list[str]:
    if isinstance(value, dict):
        texts: list[str] = []
        explanation = value.get("explanation")
        if isinstance(explanation, dict) and explanation.get("text"):
            texts.append(str(explanation["text"]))
        for item in value.values():
            texts.extend(_explanation_texts(item))
        return texts
    if isinstance(value, list):
        return [text for item in value for text in _explanation_texts(item)]
    return []


def test_sample_input_texts_have_no_raw_nodes() -> None:
    """Step headlines read as maths: no ``limit(…)``, ``(1)/(x)`` or ``fraction(…)``."""
    from mymath_backend import service
    from mymath_backend.input import parse_protocol

    path = Path(__file__).resolve().parent / "inputs.json"
    for task in json.loads(path.read_text(encoding="utf-8")):
        try:
            data = service.solve_request(
                parse_protocol(task["proto"]).to_contract(), locale=DEFAULT_LOCALE, render=True
            )
        except Exception:  # an unsupported task simply has no text to read
            continue
        for text in _explanation_texts(data):
            assert "limit(" not in text, (task["id"], text)
            assert not _ATOM_PARENS.search(text), (task["id"], text)
            assert not _RAW_NODE_TEXT.search(text), (task["id"], text)


@pytest.mark.parametrize(
    ("source", "text"),
    [
        ("{t=2^x}", "t = 2^x"),  # was «t = (2)^(x)» in the «подстановка» header
        ("{(x+1)^(n-1)}", "(x + 1)^(n - 1)"),
        ("{log({x},{2})}", "log₂(x)"),  # was «log(x, 2)»
        ("{log({x},{a})}", "log_a(x)"),
    ],
)
def test_plain_text_of_powers_and_logs_reads_as_written(source: str, text: str) -> None:
    from mymath_backend.explanations import _default_render_arg
    from mymath_backend.input import parse_protocol

    assert _default_render_arg(parse_protocol(source)) == text
