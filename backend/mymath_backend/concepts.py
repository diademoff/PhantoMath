"""Определения понятий для ссылок ``[label|uuid]``.

Ссылки в текстах шагов ведут к понятиям: приложение открывает по ним
краткое определение. Ключ — ``uuid`` из ссылки, значение — определения на
русском и английском.

Заполнены понятия, которые реально встречаются в шагах наших модулей.
Неизвестный ``uuid`` даёт ``None``: клиент покажет заглушку.
"""

from __future__ import annotations

from .explanations import DEFAULT_LOCALE

# uuid -> {язык: определение}
CONCEPTS: dict[str, dict[str, str]] = {
    # Противоположные числа.
    "abe4fb87-e608-47bc-856b-32a86eab8ed0": {
        "ru": "Противоположные числа отличаются только знаком: a и −a.",
        "en": "Opposite numbers differ only in sign: a and −a.",
    },
    # Наибольший общий делитель.
    "fa98cb11-bf47-4a6c-810a-9be8f394c635": {
        "ru": "Наибольший общий делитель (НОД) — наибольшее число, на которое "
        "делятся и числитель, и знаменатель.",
        "en": "The greatest common factor is the largest number that divides both "
        "the numerator and the denominator.",
    },
    # Смешанное число.
    "426e9fa2-1d68-4f2b-b696-047415137ce6": {
        "ru": "Смешанное число — сумма целого числа и правильной дроби, например 2 1/3.",
        "en": "A mixed number is a whole number plus a proper fraction, e.g. 2 1/3.",
    },
    # Неправильная дробь.
    "8e8dc6e4-46c0-4ed1-a0a1-12d871dc5957": {
        "ru": "Неправильная дробь — дробь, у которой числитель больше знаменателя или равен ему.",
        "en": "An improper fraction has a numerator greater than or equal to its denominator.",
    },
    # Метод исключения.
    "b2922bdb-0061-4cc6-a569-54e1a384dfb4": {
        "ru": "Метод исключения — сложить или вычесть уравнения так, чтобы одна "
        "переменная исчезла.",
        "en": "The elimination method adds or subtracts equations so that one "
        "variable cancels out.",
    },
    # Определитель.
    "419b07e8-d928-4f89-9717-122abd031632": {
        "ru": "Определитель — число, характеризующее квадратную матрицу; для 2×2 это ad − bc.",
        "en": "A determinant is a number describing a square matrix; for 2×2 it is ad − bc.",
    },
    # Факториал.
    "dd47bca9-e49a-472b-a3d0-9ea5797a83f6": {
        "ru": "Факториал n! — произведение всех натуральных чисел от 1 до n; 0! = 1.",
        "en": "The factorial n! is the product of all integers from 1 to n; 0! = 1.",
    },
    # Биномиальный коэффициент.
    "9409d61e-ab00-46dc-ad25-3ee4e548db4a": {
        "ru": "Биномиальный коэффициент C(n, k) — число способов выбрать k "
        "элементов из n: n! / (k!(n−k)!).",
        "en": "The binomial coefficient C(n, k) is the number of ways to choose k "
        "items from n: n! / (k!(n−k)!).",
    },
    # Разложение на множители.
    "1ceef362-dfb4-4ae6-ba5d-46dbd862a37b": {
        "ru": "Разложение на множители — запись выражения в виде произведения множителей.",
        "en": "Factoring rewrites an expression as a product of factors.",
    },
}


def definition(uuid: str, locale: str = DEFAULT_LOCALE) -> str | None:
    """Определение понятия по uuid или ``None``, если его нет."""
    entry = CONCEPTS.get(uuid)
    if entry is None:
        return None
    if locale == "ru":
        return entry.get("ru")
    return entry.get("en")


__all__ = [
    "CONCEPTS",
    "definition",
]
