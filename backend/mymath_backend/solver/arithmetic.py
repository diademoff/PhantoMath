"""Вычисление арифметики по порядку действий.

Первый модуль решателя: считает выражения из чисел, знаков, скобок,
неявного умножения и степеней. Каждая операция добавляет шаг с ключом
объяснения из ``truth/data/explanations.json`` (``add``, ``sub``, ``mul``,
``div``, ``calculate_short``), поэтому тексты подставляются автоматически.

Покрыто: числовые константы, ``+ - * /``, неявное умножение, ``^``,
скобки ``BRACKET``, возведение отрицательного основания в нечётную степень.

Не покрыто (следующие модули): буквы, ``FRACTION`` как отдельный узел,
функции, уравнения, неравенства.

Известное упрощение: ``left`` шага -- сам свёртываемый узел, а не полное
выражение с уже посчитанной частью. Для арифметики это читаемо, но при
переходе к уравнениям придётся вести накопительную строку.
"""

from __future__ import annotations

from fractions import Fraction

from ..ast import CoreNode
from ..node_types import CoreNodeType
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step, route, solver_for

KEY_CALCULATE = "calculate_short"

# Ключ пояснения на операцию. Берём из словаря, чтобы не выдумывать формулировки.
# Для операций, у которых в словаре нет точной формулировки, берём
# calculate_short («Посчитать»): он честнее, чем чужой по смыслу ключ.
_EXPLANATION_KEY: dict[CoreNodeType, str] = {
    T.ADD: "add",
    T.SUBTRACT: "sub",
    T.MULTIPLY: "mul",
    T.MULTIPLY_IMPLICIT: "mul",
    T.DIVIDE: "div",
    T.POWER: KEY_CALCULATE,
    T.NEGATIVE: KEY_CALCULATE,
    T.POSITIVE: KEY_CALCULATE,
}

# Пояснения для вырожденных случаев: они отвечают на «а почему так?».
_KEY_DIV_ZERO = "div_with_zero"
_KEY_DIV_ONE = "div_with_one"
_KEY_ADD_ZERO = "add_with_zero"
_KEY_SUB_SELF = "sub_with_self"

_MAX_POWER = 4096
"""Потолок показателя степени.

Без него ``9^9^9`` уводит вычисление в бесконечный рост целых. Photomath
ограничивает вычисления на своей стороне; мы повторяем это явно, чтобы не
ловить ``MemoryError``.
"""

_BINARY_OPS = (T.ADD, T.SUBTRACT, T.MULTIPLY, T.MULTIPLY_IMPLICIT, T.DIVIDE, T.POWER)


def as_fraction(node: CoreNode) -> Fraction:
    """Числовое значение узла. Буквы не принимаются."""
    if node.type is not T.CONSTANT:
        raise SolveError(f"ожидалось число, получено {node.type}")
    text = (node.value or "").strip()
    if not text:
        raise SolveError("пустая константа")
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError) as err:
        raise SolveError(f"не удалось прочитать число {text!r}") from err


def format_number(value: Fraction) -> str:
    """Представить дробльную величину так, как это делает Photomath.

    Целые -- без дробной части, остальные -- числитель/знаменатель.
    """
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


def is_zero(node: CoreNode) -> bool:
    """Свёрнулось ли поддерево в ноль."""
    return node.type is T.CONSTANT and (node.value or "") == "0"


@solver_for(
    T.CONSTANT,
    T.VARIABLE,
    T.ADD,
    T.SUBTRACT,
    T.MULTIPLY,
    T.MULTIPLY_IMPLICIT,
    T.DIVIDE,
    T.POWER,
    T.NEGATIVE,
    T.POSITIVE,
    T.BRACKET,
)
def solve_arithmetic(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Свернуть поддерево в число, добавив шаг на каждую операцию.

    Обход идёт в глубину, поэтому сначала считаются вложенные операции и
    только потом внешняя. Это и есть порядок действий: степени, затем
    умножение и деление, затем сложение и вычитание.

    Возвращает константу со значением поддерева; скобки возвращаются как
    ``BRACKET`` с уже свёрнутым содержимым, чтобы сохранить видимость
    группировки в последующих шагах.
    """
    if node.type in (T.CONSTANT, T.VARIABLE):
        _check_leaf(node)
        return node

    # Дети сворачиваются через общий реестр: так арифметика складывается с
    # другими модулями (например, дробь сворачивается своим модулем).
    folded = [route(child, ctx) for child in node.children]

    if node.type is T.BRACKET:
        ctx.require(len(folded) == 1, "в скобках должно быть одно выражение")
        return CoreNode(type=T.BRACKET, children=folded)
    if not folded:
        raise SolveError(f"узел {node.type} без операндов")
    if not all(_is_settled(c) for c in folded):
        raise SolveError(f"после свёртки в {node.type} остались не-константы")

    values = [_value_of(c) for c in folded]
    result, key = _apply(node.type, values)
    constant = CoreNode.constant(format_number(result))
    from .fractions import addition_rows, product_detail, product_rows

    # Common-denominator rows only for fraction operands; decimals add as plain numbers.
    is_fraction = all(
        "/" in (c.value or "") or v.denominator == 1 for c, v in zip(folded, values, strict=True)
    )
    if is_fraction and (
        rows := addition_rows(node.type, values, constant)
        or product_rows(node.type, values, constant)
    ):
        for header, steps in rows:
            ctx.result.add_group(header, *steps)
        return constant
    detail = product_detail(node.type, values, constant)
    step = Step(
        left=CoreNode(node.type, children=folded),
        right=constant,
        key=key,
        args=_step_args(key, node, constant),
        subresult=detail,
    )
    # Photomath 7.10.0 on device: every operation is its own row (main step).
    ctx.result.add_group(detail.header if detail and detail.header else key, step)
    return constant


def _step_args(key: str, node: CoreNode, result: CoreNode) -> list[CoreNode]:
    """Аргументы ``ARG1…`` для вырожденных случаев.

    Шаблоны этих ключей требуют аргумент. Без него пользователь читал
    служебную метку: «Любое выражение, разделенное на ARG1, равно самому
    себе».
    """
    if key == _KEY_DIV_ONE:
        # «…разделенное на ARG1…» — делитель (последний операнд деления).
        return [node.children[-1]]
    if key == _KEY_SUB_SELF:
        # «Сумма двух противоположных чисел равна ARG1» — результат (ноль).
        return [result]
    if key == _KEY_ADD_ZERO:
        # «При добавлении или вычитании ARG1 величина не меняется» — ноль.
        return [CoreNode.constant("0")]
    return []


def _is_settled(node: CoreNode) -> bool:
    """Свёрнулось ли поддерево до значения.

    Скобки не мешают значению, но остаются узлом: ``2*(3+4)`` -- это
    умножение на результат скобок, а не на узел ``BRACKET``.
    """
    if node.type is T.CONSTANT:
        return True
    return (
        node.type is T.BRACKET and len(node.children) == 1 and node.children[0].type is T.CONSTANT
    )


def _value_of(node: CoreNode) -> Fraction:
    """Значение свёрнутого узла, со снятием скобок."""
    if node.type is T.BRACKET and len(node.children) == 1:
        return as_fraction(node.children[0])
    return as_fraction(node)


def _check_leaf(node: CoreNode) -> None:
    """Проверить, что лист действительно число, а не переменная."""
    if node.type is T.VARIABLE:
        raise SolveError("переменные в арифметике не вычисляются: нужен модуль уравнений")
    if not node.value:
        raise SolveError("константа без значения")


def _apply(op: CoreNodeType, values: list[Fraction]) -> tuple[Fraction, str]:
    """Вычислить операцию и выбрать ключ пояснения."""
    if op in (T.ADD, T.SUBTRACT, T.POSITIVE):
        total = values[0]
        for v in values[1:]:
            total = total + v if op is T.ADD else total - v
        if op is T.POSITIVE:
            return values[0], _KEY_ADD_ZERO
        if total == 0 and op is T.SUBTRACT:
            return total, _KEY_SUB_SELF
        return total, _EXPLANATION_KEY[op]

    if op in (T.MULTIPLY, T.MULTIPLY_IMPLICIT):
        product = Fraction(1)
        for v in values:
            product *= v
        if product == 1:
            return product, KEY_CALCULATE
        return product, _EXPLANATION_KEY[op]

    if op is T.NEGATIVE:
        return -values[0], _EXPLANATION_KEY[op]

    if op is T.DIVIDE:
        result = values[0]
        for v in values[1:]:
            if v == 0:
                raise SolveError("деление на ноль", explanation_key=_KEY_DIV_ZERO)
            result /= v
            if result == values[0] and v == 1:
                return result, _KEY_DIV_ONE
        return result, _EXPLANATION_KEY[op]

    if op is T.POWER:
        base, exponent = values[0], values[1]
        if exponent.denominator != 1 or abs(exponent.numerator) > _MAX_POWER:
            raise SolveError("показатель степени вне поддерживаемого диапазона")
        if base == 0 and exponent.numerator < 0:
            raise SolveError("деление на ноль", explanation_key=_KEY_DIV_ZERO)
        if base < 0 and exponent.numerator % 2 != 0:
            return Fraction(-((-base) ** exponent.numerator)), _EXPLANATION_KEY[op]
        return Fraction(base) ** exponent.numerator, _EXPLANATION_KEY[op]

    raise SolveError(f"операция {op} не реализована в арифметике")
