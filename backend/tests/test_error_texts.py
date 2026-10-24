"""Tests for user-facing error message translations."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from mymath_backend.error_texts import EXACT_MESSAGES, translate


def _collect_solve_error_messages() -> list[str]:
    """AST-walk the package and build sample SolveError messages.

    For f-strings the holes are filled with ``"x"`` so the regex entries are
    exercised. Variable-only arguments (``SolveError(message)``) are skipped:
    the runtime string they carry is already emitted by another constant raise
    and is covered transitively.
    """
    pkg = Path(__file__).resolve().parents[1] / "mymath_backend"
    messages: list[str] = []
    for path in sorted(pkg.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or not node.exc:
                continue
            exc = node.exc
            if not isinstance(exc, ast.Call):
                continue
            func = exc.func
            if not isinstance(func, ast.Name) or func.id != "SolveError":
                continue
            if not exc.args:
                continue
            arg0 = exc.args[0]
            text = _message_from_arg(arg0)
            if text is not None:
                messages.append(text)
    return messages


def _message_from_arg(arg: ast.expr) -> str | None:
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.JoinedStr):
        parts: list[str] = []
        for value in arg.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append("x")
            else:
                parts.append("x")
        return "".join(parts)
    return None


def test_all_solve_error_messages_translate_to_english() -> None:
    failures: list[str] = []
    for msg in _collect_solve_error_messages():
        translated = translate(msg, "en")
        if any("\u0400" <= ch <= "\u04ff" for ch in translated):
            failures.append(f"{msg!r} -> {translated!r}")
    if failures:
        pytest.fail("Untranslated Cyrillic in:\n" + "\n".join(failures))


def _collect_require_messages() -> list[str]:
    """Collect string literals passed to ``ctx.require(..., message, ...)``.

    These become :class:`SolveError` messages at runtime.
    """
    pkg = Path(__file__).resolve().parents[1] / "mymath_backend"
    messages: list[str] = []
    for path in sorted(pkg.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_require = (isinstance(func, ast.Attribute) and func.attr == "require") or (
                isinstance(func, ast.Name) and func.id == "require"
            )
            if not is_require:
                continue
            # ctx.require(condition, message, key) or require(condition, message, key)
            arg_index = 1
            if len(node.args) > arg_index:
                text = _message_from_arg(node.args[arg_index])
                if text is not None:
                    messages.append(text)
    return messages


def test_all_require_messages_translate_to_english() -> None:
    failures: list[str] = []
    for msg in _collect_require_messages():
        translated = translate(msg, "en")
        if any("\u0400" <= ch <= "\u04ff" for ch in translated):
            failures.append(f"{msg!r} -> {translated!r}")
    if failures:
        pytest.fail("Untranslated Cyrillic in require messages:\n" + "\n".join(failures))


def test_locale_ru_leaves_messages_unchanged() -> None:
    assert translate("деление на ноль", "ru") == "деление на ноль"
    assert translate("деление на ноль", "ru-RU") == "деление на ноль"
    assert translate("узел ADD не переводится в sympy", "ru") == "узел ADD не переводится в sympy"


def test_locale_non_ru_translates_constants() -> None:
    assert translate("деление на ноль", "en") == "Division by zero"
    assert translate("слишком глубокое выражение", "default") == "Expression is too deep"
    assert translate("матрица слишком большая", "en") == "Matrix is too large"


def test_locale_non_ru_translates_fstring_templates() -> None:
    assert (
        translate("узел ADD не переводится в sympy", "en")
        == "Node ADD cannot be converted to sympy"
    )
    assert translate("не удалось прочитать число '42'", "en") == "Could not read number '42'"


def test_recursive_translation_of_placeholder() -> None:
    assert (
        translate("не удалось разобрать узел: деление на ноль", "en")
        == "Could not parse node: Division by zero"
    )


def test_http_messages_translated() -> None:
    assert translate("неверный JSON", "en") == "Invalid JSON"
    assert translate("тело запроса должно быть объектом", "en") == "Request body must be an object"
    assert translate("внутренняя ошибка решателя", "en") == "Internal solver error"


def test_every_exact_message_has_english_value_without_cyrillic() -> None:
    for ru, en in EXACT_MESSAGES.items():
        assert not any("\u0400" <= ch <= "\u04ff" for ch in en), (
            f"English value for {ru!r} contains Cyrillic: {en!r}"
        )
