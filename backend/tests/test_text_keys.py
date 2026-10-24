"""Разворачивание TEXT[TEXT_KEY] в локализованный текст.

Контракт шагов остаётся на TEXT_KEY (корпус и solve()), а сервис отдаёт
приложению готовый текст: иначе карточка «число решений» показывала бы
`eq_quad_disc_solution_two` вместо «2 действительных корня».
"""

from __future__ import annotations

from mymath_backend.service import _resolve_text_keys


def test_text_key_is_rendered_in_requested_locale() -> None:
    node = {
        "type": "TEXT",
        "children": [
            {"type": "TEXT_KEY", "value": "eq_quad_disc_solution_two"},
            {"type": "CONSTANT", "value": "2"},
        ],
    }
    assert _resolve_text_keys(node, "ru") == {
        "type": "TEXT",
        "value": "Действительных корней: 2",
    }
    assert _resolve_text_keys(node, "en") == {
        "type": "TEXT",
        "value": "2 real roots",
    }


def test_unknown_text_key_is_left_for_the_client() -> None:
    node = {"type": "TEXT", "children": [{"type": "TEXT_KEY", "value": "no_such_key"}]}
    assert _resolve_text_keys(node, "ru") == node


def test_nested_text_keys_are_resolved() -> None:
    node = {
        "type": "LIST",
        "children": [
            {
                "type": "TEXT",
                "children": [
                    {"type": "TEXT_KEY", "value": "eq_quad_disc_solution_two"},
                    {"type": "CONSTANT", "value": "2"},
                ],
            }
        ],
    }
    assert _resolve_text_keys(node, "ru")["children"][0] == {
        "type": "TEXT",
        "value": "Действительных корней: 2",
    }
