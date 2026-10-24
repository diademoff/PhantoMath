"""Тригонометрические уравнения.

Уравнение с одним неизвестным, в котором встречается прямая
тригонометрическая функция (``sin`` … ``csc``). Общее решение -- **серии**:
``x = π/6 + 2kπ``, ``x = 5π/6 + 2kπ``. Параметр серии -- переменная ``k``.
Если задан промежуток, из серий отбираются корни.

Простые уравнения (``sin x = c``, ``tan x = c``) собираются по
карточкам: два случая, обратная функция, её значение, период, линейное
уравнение для аргумента. Остальные уравнения решает ``sympy`` (``solveset``);
серии, отличающиеся на долю периода, сливаются в одну (``sin x - √3 cos x = 0``
-> ``x = π/3 + kπ``).

Период всегда записывается с параметром перед ``π``
(``2kπ``, ``kπ``, ``2kπ/3``, ``6kπ``), а не ``2π·k``.

Серии бывают и нелинейны по параметру (``sin(x²) = 0`` -> ``x = ±√(πk)``):
такие записываются как есть, формулой от ``k``.

Уравнение, которое ``solveset`` не берёт вовсе (``sin x = x`` -- там
``ConditionSet`` по самому неизвестному), не считается тригонометрическим:
решение продолжается обычным путём и попадает в численный модуль.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import lcm

import sympy

from ..ast import CoreNode, CoreRichText
from ..node_types import CoreNodeType as T
from .base import SolveError, SolveResult, Step
from .sympy_bridge import from_sympy, to_sympy

_TRIG = frozenset({T.SIN, T.COS, T.TAN, T.COT, T.SEC, T.CSC})

_PARAMETER = "k"
"""Имя параметра серии: ``x = π/6 + 2kπ``."""

_KEY_GENERAL = "trig_general_sol"
_KEY_INTERVAL = "trig_find_intervals_smpl"
_KEY_NO_SOLUTION = "false_statement_solve"
_KEY_INF_MANY = "solutions_inf_many"

_MAX_SERIES = 32
"""Потолок числа серий: защита от неожиданного множества решений."""

_MAX_PARAMETER = 64
"""Диапазон перебора параметра при нелинейных сериях и отборе корней."""

Interval = tuple[CoreNode, CoreNode]
"""Промежуток отбора корней: левая и правая границы."""

Family = tuple[sympy.Expr, sympy.Expr]
"""Одна серия: выражение от параметра и сам параметр."""


# ---------------------------------------------------------------------------
# Запись серий: k·π, а не π·k.
# ---------------------------------------------------------------------------


def _num(value: int) -> CoreNode:
    return CoreNode.constant(str(value))


def _k_pi(coefficient: sympy.Expr) -> CoreNode:
    """``k·π`` с коэффициентом впереди: ``2kπ``, ``kπ``, ``2kπ/3``, ``6kπ``.

    Решатель ставит параметр перед ``π`` (узлы ``muli(muli(2,k),π)`` и
    ``frac(muli(muli(2,k),π),3)``), а общий ``from_sympy`` пишет ``2π·k``.
    """
    rational = sympy.Rational(coefficient)
    numerator, denominator = abs(int(rational.p)), int(rational.q)
    k = CoreNode.variable(_PARAMETER)
    inner = k if numerator == 1 else CoreNode.node(T.MULTIPLY_IMPLICIT, _num(numerator), k)
    product = CoreNode.node(T.MULTIPLY_IMPLICIT, inner, CoreNode.constant("π"))
    if rational < 0:
        return CoreNode.node(T.NEGATIVE, product)
    if denominator == 1:
        return product
    return CoreNode.node(T.FRACTION, product, _num(denominator))


def _angle(value: sympy.Expr) -> CoreNode:
    """Угол узлом; минус у дроби выносится перед формулой (``-π/6``)."""
    node = from_sympy(value)
    if node.type is T.FRACTION and node.children[0].type is T.NEGATIVE:
        fraction = CoreNode.node(T.FRACTION, node.children[0].children[0], node.children[1])
        return CoreNode.node(T.NEGATIVE, fraction)
    if node.type is T.FRACTION and node.children[0].type is T.CONSTANT:
        text = node.children[0].value or ""
        if text.startswith("-"):
            fraction = CoreNode.node(T.FRACTION, CoreNode.constant(text[1:]), node.children[1])
            return CoreNode.node(T.NEGATIVE, fraction)
    return node


def _value(value: sympy.Expr) -> CoreNode:
    """Правое значение простого уравнения: ``1/2``, ``-√2/2``, ``1/3``."""
    if value.is_Rational and not value.is_Integer:
        numerator, denominator = int(value.p), int(value.q)
        fraction = CoreNode.node(T.FRACTION, _num(abs(numerator)), _num(denominator))
        return CoreNode.node(T.NEGATIVE, fraction) if numerator < 0 else fraction
    return _angle(value)


def _series(offset: sympy.Expr, period: sympy.Expr, *, keep_zero: bool = False) -> CoreNode:
    """Узел ``offset + period·k`` с периодом, записанным как ``2kπ``.

    ``period`` -- полный период серии (может быть отрицательным: тогда перед
    ``k·π`` стоит минус). ``keep_zero`` оставляет явный нуль: ``0 + 2kπ``.
    """
    ratio = sympy.simplify(abs(period) / sympy.pi)
    if ratio.is_Rational:
        kpart = _k_pi(ratio)
    else:  # pragma: no cover - у прямой функции период всегда кратен π
        kpart = from_sympy(abs(period) * sympy.Symbol(_PARAMETER))
    negative = bool(period < 0)
    if sympy.simplify(offset) == 0:
        if keep_zero:
            zero = _num(0)
            if negative:
                return CoreNode.node(T.SUBTRACT, zero, kpart)
            return CoreNode.node(T.ADD, zero, kpart)
        return CoreNode.node(T.NEGATIVE, kpart) if negative else kpart
    angle = _angle(offset)
    if negative:
        return CoreNode.node(T.SUBTRACT, angle, kpart)
    return CoreNode.node(T.ADD, angle, kpart)


def _series_add(left: CoreNode, right: sympy.Expr) -> CoreNode:
    """``left + right`` с сохранением знака правого слагаемого."""
    if sympy.simplify(right) > 0:
        return CoreNode.node(T.ADD, left, _angle(right))
    return CoreNode.node(T.SUBTRACT, left, _angle(-right))


# ---------------------------------------------------------------------------
# Точка входа.
# ---------------------------------------------------------------------------


def looks_trigonometric(node: CoreNode) -> bool:
    """Есть ли в уравнении прямая тригонометрическая функция."""
    return any(child.type in _TRIG for child in node.walk())


def unknown_of(node: CoreNode, variables: list[str]) -> str | None:
    """Неизвестное тригонометрического уравнения.

    Это переменная внутри тригонометрической функции; остальные буквы --
    параметры. Если внутри несколько разных букв (``sin x = cos y``),
    неизвестным становится та, что встречается в аргументах чаще; при равных
    счётах предпочтение ``x``, затем -- первая по порядку появления.
    """
    counts: dict[str, int] = {}
    for child in node.walk():
        if child.type not in _TRIG:
            continue
        for deeper in child.walk():
            if deeper.type is T.VARIABLE and deeper.value in variables:
                counts[deeper.value] = counts.get(deeper.value, 0) + 1
    if not counts:
        return None
    best = max(counts.values())
    top = [name for name, count in counts.items() if count == best]
    return "x" if "x" in top else top[0]


def solve_trig_equation(
    node: CoreNode, variables: list[str], interval: Interval | None = None
) -> SolveResult | None:
    """Решить тригонометрическое уравнение или вернуть ``None``.

    ``None`` означает «это не наше уравнение»: нет единственного
    неизвестного внутри тригонометрической функции или ``solveset`` не
    справился. Тогда вызывающий решает обычным путём.
    """
    result = _solve_trig(node, variables, interval)
    if result is not None:
        _drop_trivial_details(result)
    return result


def _drop_trivial_details(result: SolveResult) -> None:
    """Убрать экран «Подробнее», который одной строкой повторяет сам шаг."""
    for step in result:
        detail = step.subresult
        if detail is None:
            continue
        rows = list(detail)
        same = (
            len(rows) == 1
            and step.left is not None
            and step.right is not None
            and rows[0].left is not None
            and rows[0].right is not None
            and step.left.structural_eq(rows[0].left)
            and step.right.structural_eq(rows[0].right)
        )
        if same:
            step.subresult = None
        else:
            _drop_trivial_details(detail)


def _solve_trig(
    node: CoreNode, variables: list[str], interval: Interval | None = None
) -> SolveResult | None:
    var = unknown_of(node, variables)
    if var is None or not looks_trigonometric(node):
        return None

    symbol = sympy.Symbol(var)
    lhs, rhs = node.children
    if interval is None:
        out_of_range = _out_of_range(node, var)
        if out_of_range is not None:
            return out_of_range
        simple = _simple_rows(node, var)
        if simple is not None:
            return simple
        two_sided = _two_sided_rows(node, var)
        if two_sided is not None:
            return two_sided
        reducible = _reducible_rows(node, var)
        if reducible is not None:
            return reducible
    if interval is None and (
        (rows := _sin_cos_rows(node, var)) is not None or (rows := _tan_rows(node, var)) is not None
    ):
        return rows
    try:
        expression = to_sympy(lhs) - to_sympy(rhs)
        solution_set = sympy.solveset(expression, symbol, domain=sympy.S.Reals)
    except (SolveError, ValueError, TypeError):
        return None

    solution_set = _unwrap(solution_set, symbol)
    if solution_set is sympy.S.Reals:
        return _terminal(node, _KEY_INF_MANY)
    if solution_set is sympy.S.EmptySet:
        return _terminal(node, _KEY_NO_SOLUTION)

    families = _families(solution_set)
    if not families:
        return None

    series = [_linear(expression, parameter) for expression, parameter in families]
    if all(item is not None for item in series):
        ordered = sorted(
            _merge_series([item for item in series if item is not None]), key=_series_sort_key
        )
        general = _series_node(var, ordered, merge=False)
        # Аргумент «Запишите общее решение, используя ARG1» -- период серии.
        general_arg = _angle(ordered[0][0])
        selected = _select_interval(var, ordered, interval) if interval is not None else None
    else:
        general = _raw_node(var, families)
        first = sorted(families, key=_family_sort_key)[0]
        general_arg = from_sympy(_at_zero(first))
        selected = _select_raw(var, families, interval) if interval is not None else None

    result = SolveResult()
    restriction = _parameter_restriction(node, var, variables)
    if restriction is not None:
        result.add(Step(left=node, right=restriction, key="rel_restrictions_range"))
    result.add(Step(left=node, right=None, key="trig_find_period"))
    result.add(Step(left=node, right=general, key=_KEY_GENERAL, args=[general_arg]))
    result.set_solution(general)

    if selected is not None:
        if selected:
            node_selected = selected[0] if len(selected) == 1 else CoreNode.node(T.LIST, *selected)
            result.add(
                Step(
                    left=general,
                    right=node_selected,
                    key=_KEY_INTERVAL,
                    args=[CoreNode.variable(var)],
                )
            )
            result.set_solution(node_selected)
        else:
            result.add(Step(left=general, right=None, key=_KEY_NO_SOLUTION))
            result.set_solution(CoreNode.empty())

    return result


def _parameter_restriction(node: CoreNode, unknown: str, variables: list[str]) -> CoreNode | None:
    """Ограничение на параметр: ``sin x = a`` требует ``|a| ≤ 1``.

    Без него серии ``x = arcsin a + 2kπ`` выглядят определёнными и при ``a > 1``.
    """
    if node.type is not T.EQUALS or len(node.children) != 2:
        return None
    for trig, other in ((node.children[0], node.children[1]), (node.children[1], node.children[0])):
        if trig.type not in {T.SIN, T.COS}:
            continue
        if unknown not in {child.value for child in trig.walk() if child.type is T.VARIABLE}:
            continue
        names = {child.value for child in other.walk() if child.type is T.VARIABLE}
        if not (names - {unknown}):
            return None
        if other.type in {T.SIN, T.COS}:
            # Область значения самой тригонометрической функции уже [−1, 1].
            return None
        magnitude = CoreNode.node(T.ABS, other)
        return CoreNode.node(T.LESS_THAN_EQUAL, magnitude, CoreNode.constant(1))
    return None


def _unwrap(solution_set: sympy.Set, symbol: sympy.Symbol) -> sympy.Set:
    """Снять ограничения по параметрам: ``ConditionSet`` и ``Intersection``.

    ``ConditionSet`` с условием, не зависящим от неизвестного, -- это то же
    множество решений с оговоркой про параметры (``sin x = a`` требует
    ``|a| <= 1``): берём базовое множество. ``Intersection`` с ``Reals``
    размыкаем в ``FiniteSet`` из решений с параметрами.
    """
    if isinstance(solution_set, sympy.ConditionSet):
        if symbol in solution_set.condition.free_symbols:
            return solution_set
        return _unwrap(solution_set.base_set, symbol)
    if isinstance(solution_set, sympy.Intersection):
        parts = [part for part in solution_set.args if part is not sympy.S.Reals]
        if len(parts) == 1:
            return _unwrap(parts[0], symbol)
    return solution_set


def _terminal(node: CoreNode, key: str) -> SolveResult:
    """Ответ без узла: тождество или отсутствие решений."""
    result = SolveResult()
    result.add(Step(left=node, right=None, key=key))
    result.set_solution(CoreNode.empty())
    return result


def _out_of_range(node: CoreNode, var: str) -> SolveResult | None:
    """``sin x = 2``: вне области значений -- шаг ``trig_eq_interval_real``.

    Решатель не выводит серии, а показывает, что функция лежит в ``[-1, 1]``,
    и заключает, что действительных решений нет.
    """
    if node.type is not T.EQUALS or len(node.children) != 2:
        return None
    for trig, other in ((node.children[0], node.children[1]), (node.children[1], node.children[0])):
        if trig.type not in {T.SIN, T.COS} or len(trig.children) != 1:
            continue
        argument = trig.children[0]
        if argument.type is not T.VARIABLE or argument.value != var:
            continue
        try:
            value = to_sympy(other)
        except SolveError:
            return None
        if not (value.is_number and value.is_real) or abs(value) <= 1:
            return None
        interval = CoreNode.node(
            T.CLOSED_CLOSED_INTERVAL, CoreNode.constant("-1"), CoreNode.constant("1")
        )
        membership = CoreNode.node(T.ELEMENT_OF, trig, interval)
        result = SolveResult()
        result.add(
            Step(
                left=node,
                right=CoreNode.node(
                    T.ELEMENT_NOT_OF, CoreNode.variable(var), CoreNode.variable("ℝ")
                ),
                key="trig_eq_interval_real",
                args=[membership],
            )
        )
        result.set_solution(CoreNode.empty())
        return result
    return None


# ---------------------------------------------------------------------------
# Разбор уравнения вокруг одной функции: A·f(a·x + b) + B = 0.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Isolated:
    """Уравнение после выноса коэффициента и постоянной: ``f(u) = value``."""

    kind: T
    argument: CoreNode
    expression: sympy.Expr
    coefficient: sympy.Expr
    rest: sympy.Expr
    moved: sympy.Expr
    value: sympy.Expr
    value_node: CoreNode


def _isolated(node: CoreNode, var: str, kinds: tuple[T, ...]) -> _Isolated | None:
    """``A·f(u) + B = C`` с одной функцией ``f`` из ``kinds`` и линейным ``u``."""
    if node.type is not T.EQUALS or len(node.children) != 2:
        return None
    symbol = sympy.Symbol(var)
    for function_side, value_side in (
        (node.children[0], node.children[1]),
        (node.children[1], node.children[0]),
    ):
        trigs = [child for child in function_side.walk() if child.type in _TRIG]
        if len(trigs) != 1 or trigs[0].type not in kinds:
            continue
        if any(child.type in _TRIG for child in value_side.walk()):
            continue
        if any(child.type is T.VARIABLE and child.value == var for child in value_side.walk()):
            continue
        trig = trigs[0]
        if len(trig.children) != 1:
            continue
        try:
            total = to_sympy(function_side) - to_sympy(value_side)
            target = to_sympy(trig)
            coefficient = sympy.simplify(total.coeff(target))
            rest = sympy.simplify(total - coefficient * target)
            value = sympy.simplify(-rest / coefficient)
            argument = to_sympy(trig.children[0])
            other = to_sympy(value_side)
        except (SolveError, ValueError, TypeError, ZeroDivisionError):
            continue
        if coefficient == 0 or symbol in rest.free_symbols:
            continue
        if not (coefficient.is_number and argument.free_symbols <= {symbol}):
            continue
        if not value.is_number:
            continue
        linear = sympy.diff(argument, symbol)
        offset = sympy.simplify(argument - linear * symbol)
        if not (linear.is_Rational and linear > 0) or offset.free_symbols:
            continue
        constant = sympy.simplify(rest + other)
        return _Isolated(
            trig.type,
            trig.children[0],
            argument,
            coefficient,
            constant,
            sympy.simplify(other - constant),
            value,
            _value(value),
        )
    return None


def _prefix_rows(node: CoreNode, isolated: _Isolated) -> tuple[SolveResult, CoreNode]:
    """Вынести постоянную и коэффициент: ``2sin x + 1 = 0`` -> ``sin x = -1/2``.

    Решатель сначала переносит константу (``rel_move_right_const_eq``), затем
    делит на коэффициент функции (``eq_linear_div``). Возвращает накопленные
    строки и уравнение ``f(u) = value``, с которого продолжается карточка.
    """
    result = SolveResult()
    symbol = "x"
    function_node = CoreNode.node(isolated.kind, isolated.argument)
    function_expression = to_sympy(function_node)
    current = node
    if sympy.simplify(isolated.rest) != 0:
        moved = CoreNode.node(
            T.EQUALS,
            from_sympy(sympy.simplify(isolated.coefficient * function_expression)),
            _angle(isolated.moved),
        )
        detail = SolveResult()
        detail.add_group(
            "rel_move_right_const_msg",
            Step(current, moved, "rel_move_right_const_eq"),
        )
        detail.set_solution(moved)
        result.add_group(
            "rel_move_right_const_msg",
            Step(current, moved, "rel_move_right_const_eq", subresult=detail),
        )
        current = moved
    isolated_node = CoreNode.node(T.EQUALS, function_node, isolated.value_node)
    if sympy.simplify(isolated.coefficient) != 1:
        coefficient_node = _value(sympy.simplify(isolated.coefficient))
        detail = SolveResult()
        detail.add_group(
            "eq_solve_short",
            Step(current, isolated_node, "eq_linear_div", [coefficient_node]),
        )
        detail.set_solution(isolated_node)
        result.add_group(
            "eq_solve_short",
            Step(current, isolated_node, "eq_linear_div", [coefficient_node], subresult=detail),
        )
    _ = symbol
    return result, isolated_node


def _arcus_key(kind: T, value: sympy.Expr) -> str:
    """Ключ обратной функции по знаку значения."""
    if kind is T.COS or kind is T.COT:
        return "trig_arcus_first" if value > 0 else "trig_arcus_second"
    return "trig_arcus_first" if value > 0 else "trig_arcus_fourth"


def _member() -> CoreNode:
    return CoreNode.node(T.ELEMENT_OF, CoreNode.variable(_PARAMETER), CoreNode.variable("ℤ"))


def _calculate_rows(answer: CoreNode, var: str) -> Step:
    """Приблизительные значения серий: ``calculate``.

    Смещения серий заменяются десятичными приближениями (десять значащих
    цифр -- точнее, чем переносит окно проверки корней).
    """
    x = CoreNode.variable(var)
    children = list(answer.children) if answer.type in (T.LIST, T.VERTICAL_LIST) else [answer]
    # ``k ∈ ℤ`` -- условие строки, а не серия: в приближении оно остаётся как есть.
    tail = [child for child in children if child.type is not T.EQUALS]
    approximated: list[CoreNode] = []
    for equation in (child for child in children if child.type is T.EQUALS):
        right = equation.children[1]
        period = _period_of(right)
        offset = _offset_of(right)
        if period is None or offset is None or offset.free_symbols:
            return Step(left=answer, right=None, key="calculate")
        decimal = CoreNode.constant(f"{float(sympy.N(offset, 12)):.10g}")
        if period < 0:
            node = CoreNode.node(T.SUBTRACT, decimal, _k_pi(abs(period) / sympy.pi))
        else:
            node = CoreNode.node(T.ADD, decimal, _k_pi(period / sympy.pi))
        approximated.append(CoreNode.node(T.EQUALS, x, node))
    if len(approximated) == 1 and not tail:
        right = approximated[0]
    else:
        right = CoreNode.node(T.LIST, *approximated, *tail)
    return Step(left=answer, right=right, key="calculate")


def _period_of(node: CoreNode) -> sympy.Expr | None:
    """Период линейной серии ``offset + period·k`` или ``None``."""
    try:
        expression = to_sympy(node)
    except SolveError:
        return None
    k = sympy.Symbol(_PARAMETER)
    period = sympy.simplify(sympy.diff(expression, k))
    if period == 0 or not period.is_number:
        return None
    return period


def _offset_of(node: CoreNode) -> sympy.Expr | None:
    """Смещение линейной серии (значение при ``k = 0``)."""
    try:
        return sympy.simplify(to_sympy(node).subs(sympy.Symbol(_PARAMETER), 0))
    except SolveError:
        return None


# ---------------------------------------------------------------------------
# sin x = c и cos x = c: карточки по строкам.
# ---------------------------------------------------------------------------


_SIMPLE: dict[tuple[T, sympy.Expr], tuple[sympy.Expr, sympy.Expr]] = {}


def _simple_solution(kind: T, value: sympy.Expr) -> tuple[sympy.Expr, sympy.Expr] | None:
    """Смещение и период единственной серии особых значений (0, ±1)."""
    pi = sympy.pi
    table: dict[tuple[T, int], tuple[sympy.Expr, sympy.Expr]] = {
        (T.SIN, 0): (sympy.Integer(0), pi),
        (T.COS, 0): (pi / 2, pi),
        (T.TAN, 0): (sympy.Integer(0), pi),
        (T.SIN, 1): (pi / 2, 2 * pi),
        (T.SIN, -1): (3 * pi / 2, 2 * pi),
        (T.COS, 1): (sympy.Integer(0), 2 * pi),
        (T.COS, -1): (pi, 2 * pi),
    }
    if not value.is_Integer:
        return None
    return table.get((kind, int(value)))


def _simple_card(
    start: CoreNode,
    kind: T,
    value: sympy.Expr,
    solution: tuple[sympy.Expr, sympy.Expr],
    var: str,
    prefix: SolveResult,
) -> SolveResult:
    """Одна строка ``trig_eq_simple_solution`` (как для ``sin x = 0``)."""
    x, t = CoreNode.variable(var), CoreNode.variable("t")
    eq = CoreNode.node
    offset, period = solution
    series = _series(offset, period)
    answer = eq(T.EQUALS, x, series)
    generic = eq(T.EQUALS, eq(kind, t), _value(value))
    args = [generic, eq(T.EQUALS, t, series), eq(T.EQUALS, x, series), _member()]
    prefix.add(Step(left=start, right=answer, key="trig_eq_simple_solution", args=args))
    prefix.set_solution(answer)
    return prefix


def _simple_rows(node: CoreNode, var: str) -> SolveResult | None:
    """``sin x = 0``, ``cos x = ±1`` одной серией без двух случаев.

    Решатель не разводит такие уравнения на две серии: он сразу пишет
    ``x = kπ`` (или ``x = 2kπ``) шагом ``trig_eq_simple_solution``.
    """
    if node.type is not T.EQUALS or len(node.children) != 2:
        return None
    lhs, rhs = node.children
    if lhs.type not in {T.SIN, T.COS, T.TAN} or len(lhs.children) != 1:
        return None
    argument = lhs.children[0]
    if argument.type is not T.VARIABLE or argument.value != var:
        return None
    try:
        value = to_sympy(rhs)
    except SolveError:
        return None
    solution = _simple_solution(lhs.type, value)
    if solution is None:
        return None
    return _simple_card(node, lhs.type, value, solution, var, SolveResult())


def _lin(node: CoreNode) -> bool:
    """Аргумент -- сумма или разность (его надо брать в скобки)."""
    return node.type in (T.ADD, T.SUBTRACT)


def _sin_cos_rows(node: CoreNode, var: str) -> SolveResult | None:
    """``A·sin/cos(a·x + b) + B = 0`` по строкам.

    Две ветви (``x`` и ``π - x`` для синуса, ``2π - x`` для косинуса), обратная
    функция, её значение (если угол табличный), период, линейное уравнение для
    каждой ветви, приведение смещения и числа серий. Ветви продвигаются по
    одной строке за шаг; хвостовые преобразования
    (котельность, положительный период) идут попарно.
    """
    isolated = _isolated(node, var, (T.SIN, T.COS))
    if isolated is None:
        return None
    kind = isolated.kind
    value = isolated.value
    symbol = sympy.Symbol(var)
    linear = sympy.diff(isolated.expression, symbol)
    offset_argument = sympy.simplify(isolated.expression - linear * symbol)
    prefix, start = _prefix_rows(node, isolated)

    solution = _simple_solution(kind, value)
    if solution is not None:
        # Особые значения (0, ±1): одна серия, без двух случаев. Для аргумента
        # a·x + b она сразу решается как линейное уравнение.
        simple_offset = sympy.simplify((solution[0] - offset_argument) / linear)
        simple_period = sympy.simplify(solution[1] / linear)
        return _simple_card(start, kind, value, (simple_offset, simple_period), var, prefix)
    if abs(value) > 1:
        interval = CoreNode.node(
            T.CLOSED_CLOSED_INTERVAL, CoreNode.constant("-1"), CoreNode.constant("1")
        )
        membership = CoreNode.node(T.ELEMENT_OF, CoreNode.node(kind, isolated.argument), interval)
        prefix.add(
            Step(
                left=start,
                right=CoreNode.node(
                    T.ELEMENT_NOT_OF, CoreNode.variable(var), CoreNode.variable("ℝ")
                ),
                key="trig_eq_interval_real",
                args=[membership],
            )
        )
        prefix.set_solution(CoreNode.empty())
        return prefix

    sine = kind is T.SIN
    base = sympy.asin(value) if sine else sympy.acos(value)
    tabular = bool((base / sympy.pi).is_Rational)
    pi = sympy.pi
    negated_mirror = not sine and linear < 1
    shift = pi if sine else (0 if negated_mirror else 2 * pi)
    shift_node = (
        CoreNode.constant("π")
        if sine
        else CoreNode.node(T.MULTIPLY_IMPLICIT, _num(2), CoreNode.constant("π"))
    )
    argument_node = isolated.argument
    if negated_mirror:
        mirror_node = CoreNode.node(T.NEGATIVE, argument_node)
    else:
        mirror_node = CoreNode.node(
            T.SUBTRACT,
            shift_node,
            CoreNode.node(T.BRACKET, argument_node) if _lin(argument_node) else argument_node,
        )
    mirror_simplified = _angle(sympy.simplify(shift - isolated.expression))

    trimmed = abs(value) == 1  # зеркальная ветвь даёт те же углы
    branches: list[list[_Row]] = [
        _series_branch(
            kind,
            var,
            argument_node,
            isolated.expression,
            isolated.value_node,
            value,
            base,
            tabular,
            CoreNode.node(kind, argument_node),
        ),
    ]
    if not trimmed:
        branches.append(
            _series_branch(
                kind,
                var,
                mirror_node,
                shift - isolated.expression,
                isolated.value_node,
                value,
                base,
                tabular,
                CoreNode.node(kind, argument_node),
                simplify_to=mirror_simplified if offset_argument != 0 else None,
                canonical=not negated_mirror,
            )
        )

    result = prefix
    equations = [
        CoreNode.node(T.EQUALS, CoreNode.node(kind, argument_node), isolated.value_node),
        CoreNode.node(T.EQUALS, CoreNode.node(kind, mirror_node), isolated.value_node),
    ]
    if trimmed:
        equations = equations[:1]
    identity = CoreNode.node(
        T.EQUALS,
        CoreNode.node(kind, CoreNode.variable("t")),
        CoreNode.node(kind, CoreNode.node(T.SUBTRACT, shift_node, CoreNode.variable("t"))),
    )
    cases = _node_list(equations, [False] * len(equations))
    result.add_group(
        "eq_separate_short",
        Step(start, cases, "trig_eq_two_sollutions", [identity]),
    )

    answers, last_row = _run_branches(branches, equations, result)
    if not answers:
        return None
    ordered = sorted(answers, key=_answer_sort_key)
    answer = ordered[0] if len(ordered) == 1 else CoreNode.node(T.LIST, *ordered)
    count = _num(len(ordered))
    # Строка «Уравнение имеет N решений» начинается там, где кончилась
    # предыдущая (вместе с условием k ∈ ℤ), а заканчивается чистым ответом.
    result.add_group(
        CoreRichText(type="solution_eq_num", args=[count]),
        Step(
            last_row if last_row is not None else answer,
            None if last_row is not None and last_row.structural_eq(answer) else answer,
            "solution_eq_num",
            [count],
        ),
    )
    if not tabular:
        result.add_group("calculate_short", _calculate_rows(answer, var))
    result.set_solution(answer)
    return result


@dataclass(slots=True)
class _Row:
    """Одна будущая строка ветви: что сделать с её уравнением."""

    key: str
    value: CoreNode
    args: list[CoreNode] = field(default_factory=list)
    detail: SolveResult | None = None
    normal: bool = False
    phase: int = 0
    member: bool = False


def _run_branches(
    branches: list[list[_Row]], equations: list[CoreNode], result: SolveResult
) -> tuple[list[CoreNode], CoreNode | None]:
    """Провести ветви по их строкам: решённые ``x = …`` и последняя строка.

    Пока у нескольких ветвей есть строки, каждый шаг продвигает каждую на одну.
    Когда осталась одна ветвь, хвостовые преобразования идут по два.

    Период -- единственная операция, меняющая множество корней строки (из
    главного значения получается вся серия). Решатель добавляет его по
    ветвям: первый подшаг получает ``k`` первая ветвь, второй -- вторая. Строка
    с частично добавленным периодом -- ещё не всё множество корней, а его
    часть; проверка корней считает такие строки подмножеством.
    """
    current = list(equations)
    members = [False] * len(current)
    while any(branches):
        pending = [index for index, queue in enumerate(branches) if queue]
        periods = [index for index in pending if branches[index][0].phase == 1]
        behind = [index for index in pending if branches[index][0].phase == 0]
        if periods and behind:
            owners = behind
            chosen = [branches[index].pop(0) for index in owners]
            waiting: list[Step] = []
            for owner, row in zip(owners, chosen, strict=True):
                left = _node_list(current, members)
                current[owner] = row.value
                members[owner] = row.member
                waiting.append(
                    Step(
                        left=left,
                        right=_node_list(current, members),
                        key=row.key,
                        args=row.args,
                        subresult=row.detail,
                    )
                )
            result.add_group(_title(chosen[0].key), *waiting)
            continue
        if periods and len(periods) == len(pending):
            chosen = [branches[index].pop(0) for index in periods]
            steps: list[Step] = []
            for owner, row in zip(periods, chosen, strict=True):
                left = _node_list(current, members)
                current[owner] = row.value
                members[owner] = row.member
                steps.append(
                    Step(
                        left=left,
                        right=_node_list(current, members),
                        key=row.key,
                        args=row.args,
                        subresult=row.detail,
                    )
                )
            result.add_group(_title(chosen[0].key), *steps)
            continue
        if len(pending) > 1:
            owners = pending
            chosen = [branches[index].pop(0) for index in pending]
        else:
            index = pending[0]
            queue = branches[index]
            if queue[0].normal:
                chosen = [queue.pop(0)]
                if queue and queue[0].normal:
                    chosen.append(queue.pop(0))
            else:
                chosen = [queue.pop(0)]
            owners = [index] * len(chosen)
        steps = []
        for owner, row in zip(owners, chosen, strict=True):
            left = _node_list(current, members)
            current[owner] = row.value
            members[owner] = row.member
            steps.append(
                Step(
                    left=left,
                    right=_node_list(current, members),
                    key=row.key,
                    args=row.args,
                    subresult=row.detail,
                )
            )
        result.add_group(_title(chosen[0].key), *steps)

    answers: list[CoreNode] = []
    for equation in current:
        solved = _solved(equation)
        if solved is None:
            return [], None
        answers.append(solved)
    return answers, _node_list(current, members)


def _is_solved(node: CoreNode) -> bool:
    return node.type is T.EQUALS and node.children[0].type is T.VARIABLE


def _node_list(nodes: list[CoreNode], members: list[bool]) -> CoreNode:
    """Строка карточки: ветви и общее условие ``k ∈ ℤ``.

    Пока ветвь не доведена до ``x = …``, строка вертикальная: это ещё не
    множество корней, а промежуточная запись.
    """
    children = list(nodes)
    if any(members):
        children.append(_member())
    if len(children) == 1:
        return children[0]
    kind = T.LIST if all(_is_solved(node) for node in nodes) else T.VERTICAL_LIST
    return CoreNode.node(kind, *children)


def _solved(node: CoreNode) -> CoreNode | None:
    """Вынуть ``x = …`` из строки ``x = …``."""
    if node.type is T.EQUALS and node.children[0].type is T.VARIABLE:
        return node
    return None


def _answer_sort_key(node: CoreNode) -> float:
    offset = _offset_of(node.children[1]) if node.type is T.EQUALS else None
    try:
        return float(sympy.N(offset)) if offset is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _title(key: str) -> str:
    """Заголовок шага для строки: границы шагов остаются осмысленными."""
    return {
        "trig_eq_two_sollutions": "eq_separate_short",
        "trig_eq_isolate": "trig_eq_isolate_short",
        "simplify": "simplify_msg",
        "trig_arcus_first": "find_value",
        "trig_arcus_second": "find_value",
        "trig_arcus_fourth": "find_value",
        "trig_eq_fun_period": "add_period",
        "eq_linear": "eq_solve_short",
        "trig_eq_same_angle_period": "simplify_msg",
        "trig_eq_canonical_form_arg": "simplify_msg",
        "trig_eq_positive_period": "simplify_msg",
        "add_with_zero": "simplify_msg",
    }.get(key, "simplify_msg")


def _series_branch(
    kind: T,
    var: str,
    left_node: CoreNode,
    left_expression: sympy.Expr,
    value_node: CoreNode,
    value: sympy.Expr,
    base: sympy.Expr,
    tabular: bool,
    periodic_node: CoreNode,
    *,
    simplify_to: CoreNode | None = None,
    canonical: bool = True,
) -> list[_Row]:
    """Строки одной ветви: изоляция, аркус, период, линейное решение, приведение."""
    symbol = sympy.Symbol(var)
    x = CoreNode.variable(var)
    member = _member()
    rows: list[_Row] = []
    if simplify_to is not None:
        rows.append(
            _Row(
                "simplify",
                CoreNode.node(T.EQUALS, CoreNode.node(kind, simplify_to), value_node),
            )
        )
        left_node = simplify_to
    inverse_node = CoreNode.node(T.ASIN if kind is T.SIN else T.ACOS, value_node)
    rows.append(
        _Row(
            "trig_eq_isolate",
            CoreNode.node(T.EQUALS, left_node, inverse_node),
            [left_node],
        )
    )
    if tabular:
        rows.append(
            _Row(
                _arcus_key(kind, value),
                CoreNode.node(T.EQUALS, left_node, _angle(base)),
                [inverse_node],
            )
        )
    known = periodic_node
    period = 2 * sympy.pi
    rows.append(
        _Row(
            "trig_eq_fun_period",
            CoreNode.node(T.EQUALS, left_node, _series(base, period)),
            [known, _k_pi(sympy.Integer(2)), member],
            phase=1,
            member=True,
        )
    )

    coefficient = sympy.simplify(sympy.diff(left_expression, symbol))
    constant = sympy.simplify(left_expression - coefficient * symbol)
    if not (coefficient == 1 and constant == 0):
        solved_offset = sympy.simplify((base - constant) / coefficient)
        solved_period = sympy.simplify(period / coefficient)
        solved = _series(solved_offset, solved_period, keep_zero=(solved_offset == 0))
        detail = _solve_detail(left_node, coefficient, constant, base, _angle(base), period, var)
        rows.append(
            _Row(
                "eq_linear",
                CoreNode.node(T.EQUALS, x, solved),
                [x],
                detail,
                phase=2,
                member=True,
            )
        )
    return rows + _normal_rows(var, coefficient, constant, base, period, tabular, canonical)


def _normal_rows(
    var: str,
    coefficient: sympy.Expr,
    constant: sympy.Expr,
    base: sympy.Expr,
    period: sympy.Expr,
    tabular: bool,
    canonical: bool = True,
) -> list[_Row]:
    """Приведение смещения и знака периода после линейного решения."""
    x = CoreNode.variable(var)
    solved_offset = sympy.simplify((base - constant) / coefficient)
    solved_period = sympy.simplify(period / coefficient)
    rows: list[_Row] = []
    offset = solved_offset
    modulus = abs(solved_period)

    if tabular and canonical:
        reduced = sympy.simplify(sympy.Mod(offset, modulus))
        if sympy.simplify(reduced - offset) != 0:
            before = _angle(offset)
            offset = reduced
            rows.append(
                _Row(
                    "trig_eq_canonical_form_arg",
                    CoreNode.node(
                        T.EQUALS, x, _series(offset, solved_period, keep_zero=(offset == 0))
                    ),
                    [before],
                    _coterminal_detail(before, _angle(offset)),
                    normal=True,
                    phase=3,
                    member=True,
                )
            )
    else:
        pi_part = sympy.simplify(sympy.expand(offset).coeff(sympy.pi) * sympy.pi)
        if pi_part != 0:
            multiple = sympy.simplify(pi_part / modulus)
            if multiple.is_Integer and multiple != 0:
                offset = sympy.simplify(offset - multiple * modulus)
                rows.append(
                    _Row(
                        "trig_eq_same_angle_period",
                        CoreNode.node(T.EQUALS, x, _series(offset, solved_period)),
                        [_angle(sympy.simplify(multiple * modulus))],
                        normal=True,
                        phase=3,
                        member=True,
                    )
                )

    if solved_period < 0:
        solved_period = -solved_period
        rows.append(
            _Row(
                "trig_eq_positive_period",
                CoreNode.node(T.EQUALS, x, _series(offset, solved_period, keep_zero=(offset == 0))),
                [
                    CoreNode.node(
                        T.ELEMENT_OF,
                        CoreNode.node(T.NEGATIVE, CoreNode.variable(_PARAMETER)),
                        CoreNode.variable("ℤ"),
                    ),
                    _member(),
                ],
                normal=True,
                phase=3,
                member=True,
            )
        )
    if sympy.simplify(offset) == 0 and rows:
        rows.append(
            _Row(
                "add_with_zero",
                CoreNode.node(T.EQUALS, x, _series(offset, solved_period)),
                [_num(0)],
                normal=True,
                phase=3,
                member=True,
            )
        )
    return rows


def _coterminal_detail(before: CoreNode, after: CoreNode) -> SolveResult:
    """Экран «наименьший положительный котерминальный угол»."""
    detail = SolveResult()
    detail.add_group(
        "simplify_msg",
        Step(before, after, "trig_coterminal_formula", [before, after]),
    )
    detail.set_solution(after)
    return detail


def _solve_detail(
    left_node: CoreNode,
    coefficient: sympy.Expr,
    constant: sympy.Expr,
    base: sympy.Expr,
    base_node: CoreNode,
    period: sympy.Expr,
    var: str,
) -> SolveResult:
    """Экран линейного решения ``c·x + d = base + 2kπ``."""
    x = CoreNode.variable(var)
    kpart = _k_pi(sympy.simplify(period) / sympy.pi)
    detail = SolveResult()
    if coefficient == 1:
        moved = CoreNode.node(
            T.EQUALS,
            x,
            CoreNode.node(T.ADD, _series_add(base_node, -constant), kpart),
        )
        detail.add_group(
            "rel_move_right_const_msg",
            Step(
                CoreNode.node(T.EQUALS, left_node, CoreNode.node(T.ADD, base_node, kpart)),
                moved,
                "rel_move_right_const_eq",
            ),
        )
        summed = CoreNode.node(
            T.EQUALS, x, CoreNode.node(T.ADD, _angle(sympy.simplify(base - constant)), kpart)
        )
        detail.add_group("calc_sum", Step(moved, summed, "calc_sum"))
        detail.set_solution(summed)
        return detail

    negated = (
        CoreNode.node(T.NEGATIVE, x)
        if coefficient == -1
        else CoreNode.node(T.MULTIPLY_IMPLICIT, _value(sympy.simplify(coefficient)), x)
    )
    moved_rhs = CoreNode.node(T.ADD, _series_add(base_node, -constant), kpart)
    fixed = CoreNode.node(T.EQUALS, left_node, CoreNode.node(T.ADD, base_node, kpart))
    moved = CoreNode.node(T.EQUALS, negated, moved_rhs)
    detail.add_group("rel_move_right_const_msg", Step(fixed, moved, "rel_move_right_const_eq"))
    difference = sympy.simplify(base - constant)
    # Разность показываем отдельной строкой, только если её можно свернуть в
    # число, кратное π: иначе строка повторяет предыдущую.
    numeric = bool((difference / sympy.pi).is_Rational)
    if numeric:
        diffed = CoreNode.node(
            T.EQUALS,
            negated,
            CoreNode.node(T.ADD, _angle(difference), kpart),
        )
        detail.add_group("calc_diff", Step(moved, diffed, "calc_diff"))
        moved = diffed

    solved = CoreNode.node(
        T.EQUALS,
        x,
        _series(
            sympy.simplify((base - constant) / coefficient),
            sympy.simplify(period / coefficient),
            keep_zero=sympy.simplify((base - constant) / coefficient) == 0,
        ),
    )
    if coefficient == -1:
        detail.add_group("simplify_msg", Step(moved, solved, "eq_linear_neg"))
    elif coefficient > 0:
        axis = CoreNode.node(T.MULTIPLY_IMPLICIT, _value(sympy.simplify(coefficient)), x)
        difference = sympy.simplify(base - constant)
        if sympy.simplify(constant) != 0:
            moved_row = CoreNode.node(
                T.EQUALS, axis, CoreNode.node(T.ADD, _angle(difference), kpart)
            )
            detail.add_group(
                "rel_move_right_const_msg", Step(fixed, moved_row, "rel_move_right_const_eq")
            )
            detail.extend(_divide_rows(axis, x, coefficient, _angle(difference), kpart, solved))
            detail.set_solution(solved)
            return detail
        return _divide_rows(left_node, x, coefficient, _angle(difference), kpart, solved)
    else:
        detail.add_group(
            "simplify_msg",
            Step(moved, solved, "eq_linear_div", [_value(sympy.simplify(coefficient))]),
        )
    detail.set_solution(solved)
    return detail


def _divide_rows(
    left_node: CoreNode,
    x: CoreNode,
    coefficient: sympy.Expr,
    base_node: CoreNode,
    kpart: CoreNode,
    solved: CoreNode,
) -> SolveResult:
    """Экран деления линейного аргумента: ``2x = … -> x = …``.

    Строки: разделить обе части, сократить ``2x/2``, раскрыть
    скобку, перевести деление дроби в умножение, вычислить частное, умножить
    дроби.
    """
    eq = CoreNode.node
    coefficient_node = _value(sympy.simplify(coefficient))
    reciprocal = eq(T.FRACTION, _num(1), coefficient_node)
    fixed = eq(T.ADD, base_node, kpart)
    quotient = eq(T.DIVIDE, left_node, coefficient_node)
    bracket = eq(T.BRACKET, fixed)
    divided = eq(T.EQUALS, x, eq(T.DIVIDE, bracket, coefficient_node))
    distributed = eq(
        T.EQUALS,
        x,
        eq(T.ADD, eq(T.DIVIDE, base_node, coefficient_node), eq(T.DIVIDE, kpart, coefficient_node)),
    )
    after_fraction = eq(
        T.EQUALS,
        x,
        eq(
            T.ADD,
            eq(T.MULTIPLY, base_node, reciprocal),
            eq(T.DIVIDE, kpart, coefficient_node),
        ),
    )
    after_quotient = eq(
        T.EQUALS,
        x,
        eq(
            T.ADD,
            eq(T.MULTIPLY, base_node, reciprocal),
            _geared(kpart, coefficient),
        ),
    )
    detail = SolveResult()
    detail.add_group(
        "eq_solve_short",
        Step(
            eq(T.EQUALS, left_node, fixed),
            eq(T.EQUALS, quotient, eq(T.DIVIDE, bracket, coefficient_node)),
            "eq_linear_div",
            [coefficient_node],
        ),
    )
    detail.add_group(
        "simplify_msg",
        Step(
            eq(T.EQUALS, quotient, eq(T.DIVIDE, bracket, coefficient_node)),
            divided,
            "div_with_self",
            [_num(1)],
        ),
        Step(divided, distributed, "mul_bracket", [coefficient_node]),
    )
    detail.add_group(
        "frac_int_div",
        Step(distributed, after_fraction, "frac_int_div"),
        Step(after_fraction, after_quotient, "quotient"),
    )
    detail.add_group("frac_mul", Step(after_quotient, solved, "frac_mul"))
    detail.set_solution(solved)
    return detail


def _geared(kpart: CoreNode, coefficient: sympy.Expr) -> CoreNode:
    """``k·π``, поделённое на коэффициент (``2kπ/2 = kπ``)."""
    try:
        value = to_sympy(kpart) / coefficient
    except (SolveError, TypeError):
        return kpart
    if (value / sympy.pi).is_Rational:
        return _k_pi(sympy.simplify(value / sympy.pi))
    return from_sympy(value)


# ---------------------------------------------------------------------------
# Сводящиеся уравнения: подстановка, тождество, однородные, разложение.
# ---------------------------------------------------------------------------

_T = "t"


def _expr_of(node: CoreNode) -> sympy.Expr | None:
    try:
        return to_sympy(node.children[0]) - to_sympy(node.children[1])
    except (SolveError, ValueError, TypeError, IndexError):
        return None


def _single_atom(expression: sympy.Expr, var: str) -> sympy.Expr | None:
    """Единственная тригонометрическая функция с линейным аргументом."""
    symbol = sympy.Symbol(var)
    atoms = list(expression.atoms(sympy.sin, sympy.cos, sympy.tan, sympy.cot))
    if len(atoms) != 1:
        return None
    atom = atoms[0]
    if len(atom.args) != 1:
        return None
    argument = atom.args[0]
    if argument.free_symbols - {symbol}:
        return None
    slope = sympy.diff(argument, symbol)
    if not slope.is_number or slope == 0:
        return None
    return atom


def _poly_expression(expression: sympy.Expr, atom: sympy.Expr, var: str) -> sympy.Expr | None:
    """Квадратный многочлен от ``atom`` с числовыми коэффициентами."""
    rest = sympy.expand(expression.subs(atom, sympy.Symbol(_T)))
    if sympy.Symbol(var) in rest.free_symbols:
        return None
    try:
        poly = sympy.Poly(rest, sympy.Symbol(_T))
    except sympy.PolynomialError:
        return None
    if poly.degree() != 2:
        return None
    coefficients = poly.all_coeffs()
    if any(coefficient.free_symbols or not coefficient.is_real for coefficient in coefficients):
        return None
    if coefficients[0] == 0:
        return None
    return rest


def _replace_node(node: CoreNode, target: CoreNode, replacement: CoreNode) -> CoreNode:
    """Заменить поддерево, равное ``target`` (структурно)."""
    if node.structural_eq(target):
        return replacement
    if not node.children:
        return node
    return CoreNode(
        type=node.type,
        value=node.value,
        children=[_replace_node(child, target, replacement) for child in node.children],
    )


def _sin_squared(var: str) -> CoreNode:
    return CoreNode.node(T.POWER, CoreNode.node(T.SIN, CoreNode.variable(var)), _num(2))


def _one_minus_sin_squared(var: str) -> CoreNode:
    return CoreNode.node(T.SUBTRACT, _num(1), _sin_squared(var))


def _is_one_minus_sin_squared(node: CoreNode, var: str) -> bool:
    return node.structural_eq(_one_minus_sin_squared(var))


def _distribute_number(node: CoreNode, var: str) -> tuple[CoreNode, bool]:
    """``A·(1 − sin²x)`` -> ``A − A·sin²x``; вернуть узел и признак замены."""
    if node.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT) and len(node.children) == 2:
        factor, bracket = node.children
        if (
            factor.type is T.CONSTANT
            and bracket.type is T.BRACKET
            and _is_one_minus_sin_squared(bracket.children[0], var)
        ):
            return (
                CoreNode.node(
                    T.SUBTRACT,
                    factor,
                    CoreNode.node(T.MULTIPLY_IMPLICIT, factor, _sin_squared(var)),
                ),
                True,
            )
    changed = False
    children = []
    for child in node.children:
        replaced, did = _distribute_number(child, var)
        children.append(replaced)
        changed = changed or did
    if not changed:
        return node, False
    return CoreNode(type=node.type, value=node.value, children=children), True


def _additive_constants(node: CoreNode, sign: int = 1) -> list[tuple[int, CoreNode]]:
    """Числовые слагаемые уравнения с их знаками (для ``calc_diff``)."""
    if node.type is T.SUBTRACT and len(node.children) == 2:
        return _additive_constants(node.children[0], sign) + _additive_constants(
            node.children[1], -sign
        )
    if node.type is T.ADD:
        out: list[tuple[int, CoreNode]] = []
        for child in node.children:
            out += _additive_constants(child, sign)
        return out
    if node.type is T.CONSTANT:
        return [(sign, node)]
    return []


def _identity_prefix(node: CoreNode, var: str) -> tuple[SolveResult, CoreNode, sympy.Expr] | None:
    """``cos²x`` или ``cos 2x`` заменить на ``sin x``."""
    lhs, rhs = node.children
    symbol = sympy.Symbol(var)
    replacement: CoreNode | None = None
    atom: CoreNode | None = None
    for child in lhs.walk():
        if (
            child.type is T.POWER
            and len(child.children) == 2
            and child.children[0].type is T.COS
            and len(child.children[0].children) == 1
            and sympy.simplify(to_sympy(child.children[1])) == 2
            and sympy.simplify(to_sympy(child.children[0].children[0]) - symbol) == 0
        ):
            atom = child
            replacement = CoreNode.node(T.BRACKET, _one_minus_sin_squared(var))
            break
        if (
            child.type is T.COS
            and len(child.children) == 1
            and sympy.simplify(to_sympy(child.children[0]) - 2 * symbol) == 0
        ):
            atom = child
            doubled = CoreNode.node(
                T.MULTIPLY_IMPLICIT,
                _num(2),
                CoreNode.node(T.POWER, CoreNode.node(T.SIN, CoreNode.variable(var)), _num(2)),
            )
            replacement = CoreNode.node(T.SUBTRACT, _num(1), doubled)
            break
    if atom is None or replacement is None:
        return None
    rewritten_lhs = _replace_node(lhs, atom, replacement)
    expression = to_sympy(rewritten_lhs) - to_sympy(rhs)
    if list(expression.atoms(sympy.cos)):
        return None

    result = SolveResult()
    current = node
    expanded = CoreNode.node(T.EQUALS, rewritten_lhs, rhs)
    result.add_group(
        "using_expand",
        Step(
            current,
            expanded,
            "using_expand",
            [CoreNode.node(T.EQUALS, atom, replacement)],
        ),
    )
    current = expanded
    distributed, changed = _distribute_number(rewritten_lhs, var)
    if changed:
        multiplied = CoreNode.node(T.EQUALS, distributed, rhs)
        coefficient = next(
            (
                child.children[0]
                for child in rewritten_lhs.walk()
                if child.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT)
                and len(child.children) == 2
                and child.children[0].type is T.CONSTANT
                and child.children[1].type is T.BRACKET
            ),
            _num(1),
        )
        result.add_group(
            "mul_bracket",
            Step(current, multiplied, "mul_bracket", [coefficient]),
        )
        current = multiplied
        expression = to_sympy(distributed) - to_sympy(rhs)
        numeric = _additive_constants(distributed)
        if len(numeric) > 1:
            combined = sympy.expand(to_sympy(distributed))
            diffed = CoreNode.node(T.EQUALS, from_sympy(combined), rhs)
            if not diffed.structural_eq(current):
                result.add_group("calc_diff", Step(current, diffed, "calc_diff"))
                current = diffed
                expression = to_sympy(current.children[0]) - to_sympy(current.children[1])
    return result, current, expression


def _equation_card(equation: CoreNode, variables: list[str]) -> SolveResult | None:
    """Карточка обычного уравнения (квадратного) для экрана «Подробнее».

    Берём первый способ решения -- у решателя это разложение на множители;
    страницы учебных уроков (``lesson_*``) в этот экран не входят.
    """
    from .equations import solve_methods

    try:
        methods = solve_methods(equation, list(variables))
    except (SolveError, ValueError, TypeError, sympy.PolynomialError):
        return None
    if not methods:
        return None
    card = methods[0]
    _strip_details(card)
    return card


def _drop_noop_rows(result: SolveResult) -> None:
    """Убрать строки, где слева и справа одна и та же формула."""
    kept = []
    for heads, steps in result._steps:
        remaining = [
            step
            for step in steps
            if not (
                step.left is not None
                and step.right is not None
                and step.left.structural_eq(step.right)
            )
        ]
        if remaining:
            kept.append((heads, remaining))
    result._steps = kept


def _strip_details(result: SolveResult) -> None:
    """Оставить строки карточки: без вложенных экранов и без пустых строк."""
    for step in result:
        step.subresult = None
    kept = []
    for heads, steps in result._steps:
        remaining = [
            step
            for step in steps
            if not (
                step.left is not None
                and step.right is not None
                and step.left.structural_eq(step.right)
            )
        ]
        if remaining:
            kept.append((heads, remaining))
    result._steps = kept


def _descending_node(expression: sympy.Expr, name: str) -> CoreNode:
    """Многочлен по убыванию степени: ``-2t² + 3t + 2``."""
    symbol = sympy.Symbol(name)
    poly = sympy.Poly(sympy.expand(expression), symbol)
    node: CoreNode | None = None
    for degree in range(poly.degree(), -1, -1):
        coefficient = poly.coeff_monomial(symbol**degree)
        if coefficient == 0:
            continue
        term = from_sympy(abs(coefficient) * symbol**degree)
        if node is None:
            node = from_sympy(coefficient * symbol**degree)
        elif coefficient < 0:
            node = CoreNode.node(T.SUBTRACT, node, term)
        else:
            node = CoreNode.node(T.ADD, node, term)
    return node if node is not None else from_sympy(sympy.Integer(0))


def _replace_atom(equation: CoreNode, atom: sympy.Expr) -> CoreNode | None:
    """Заменить в уравнении функцию на ``t``, сохранив порядок слагаемых."""
    lhs, rhs = equation.children
    found = None
    for child in lhs.walk():
        if child.type in _TRIG:
            try:
                if sympy.simplify(to_sympy(child) - atom) == 0:
                    found = child
                    break
            except (SolveError, ValueError, TypeError):
                continue
    if found is None:
        return None
    replaced = _replace_node(lhs, found, CoreNode.variable(_T))
    return CoreNode.node(T.EQUALS, replaced, rhs)


def _solution_equations(solution: CoreNode | None, var: str) -> list[CoreNode]:
    if solution is None or solution.type is T.EMPTY:
        return []
    equations = solution.children if solution.type in (T.LIST, T.VERTICAL_LIST) else [solution]
    return [
        equation
        for equation in equations
        if equation.type is T.EQUALS
        and equation.children[0].type is T.VARIABLE
        and equation.children[0].value == var
    ]


def _not_real(var: str) -> CoreNode:
    return CoreNode.node(T.ELEMENT_NOT_OF, CoreNode.variable(var), CoreNode.variable("ℝ"))


def _data_row(items: list[CoreNode], *, tan_domain: CoreNode | None = None) -> CoreNode:
    """Строка карточки: найденные серии, ещё не решённые ветви, условие ``k ∈ ℤ``."""
    series = any(item.type is T.EQUALS for item in items)
    children = list(items)
    if series:
        children.append(_member())
    if tan_domain is not None:
        children.append(tan_domain)
        return CoreNode.node(T.LIST, *children)
    if len(children) == 1:
        return children[0]
    solved = all(item.type is T.EQUALS for item in items)
    kind = T.LIST if solved else T.VERTICAL_LIST
    return CoreNode.node(kind, *children)


def _series_term(equation: CoreNode) -> tuple[sympy.Expr, sympy.Expr] | None:
    try:
        expression = to_sympy(equation.children[1])
    except (SolveError, ValueError, TypeError):
        return None
    parameter = sympy.Symbol(_PARAMETER)
    if parameter not in expression.free_symbols:
        return None
    period = sympy.simplify(sympy.diff(expression, parameter))
    if period == 0:
        return None
    return period, sympy.simplify(expression.subs(parameter, 0))


def _tan_domain(var: str) -> CoreNode:
    """``x ≠ π/2 + kπ`` -- область определения тангенса."""
    return CoreNode.node(T.NOT_EQUALS, CoreNode.variable(var), _series(sympy.pi / 2, sympy.pi))


def _needs_approximation(series: list[tuple[sympy.Expr, sympy.Expr]]) -> bool:
    inverses = (sympy.asin, sympy.acos, sympy.atan, sympy.acot)
    return any(offset.atoms(*inverses) for _period, offset in series)


def _finish_reducible(
    result: SolveResult,
    var: str,
    branch_equations: list[CoreNode],
    *,
    tan_intersect: bool = False,
) -> SolveResult | None:
    """Решить ветви и свести их серии (объединение или пересечение с областью)."""
    x = CoreNode.variable(var)
    slots: list[list[CoreNode]] = [[equation] for equation in branch_equations]
    any_missing = False
    steps: list[Step] = []
    for index, equation in enumerate(branch_equations):
        items = [item for slot in slots for item in slot]
        left = _data_row(items)
        card = solve_trig_equation(equation, [var])
        solved = _solution_equations(card.solution if card is not None else None, var)
        if not solved:
            slots[index] = [_not_real(var)]
            any_missing = True
            if card is None:
                card = SolveResult()
                card.add(Step(equation, None, "solutions_inf_many"))
        else:
            slots[index] = solved
        items = [item for slot in slots for item in slot]
        has_series = any(item.type is T.EQUALS for item in items)
        row = _data_row(
            items, tan_domain=_tan_domain(var) if tan_intersect and has_series else None
        )
        steps.append(Step(left, row, "eq_linear", [x], subresult=card))
    result.add_group("eq_solve_short", *steps)

    items = [item for slot in slots for item in slot]
    current = _data_row(
        items,
        tan_domain=_tan_domain(var)
        if tan_intersect and any(item.type is T.EQUALS for item in items)
        else None,
    )
    series = [term for item in items if item.type is T.EQUALS if (term := _series_term(item))]
    if not series:
        return None
    merged = _merge_series(series)
    answer_equations = [
        CoreNode.node(T.EQUALS, x, _series(offset, period)) for period, offset in merged
    ]
    answer = (
        answer_equations[0]
        if len(answer_equations) == 1
        else CoreNode.node(T.LIST, *answer_equations)
    )
    if tan_intersect:
        result.add_group(
            "intersection",
            Step(
                current,
                _node_list(answer_equations, [True] * len(answer_equations)),
                "rel_restrictions_intersect",
            ),
        )
    elif any_missing or len(merged) < len(series):
        result.add_group(
            "union",
            Step(
                current,
                _node_list(answer_equations, [True] * len(answer_equations)),
                "union",
            ),
        )
    if len(answer_equations) > 1:
        count = _num(len(answer_equations))
        result.add_group(
            CoreRichText(type="solution_eq_num", args=[count]),
            Step(
                _node_list(answer_equations, [True] * len(answer_equations)),
                answer,
                "solution_eq_num",
                [count],
            ),
        )
    if _needs_approximation(merged):
        result.add_group("calculate_short", _calculate_rows(answer, var))
    result.set_solution(answer)
    return result


def _substitution_rows(
    node: CoreNode,
    var: str,
    atom: sympy.Expr,
    expression: sympy.Expr,
    *,
    prefix: SolveResult | None = None,
    current: CoreNode | None = None,
    tan_intersect: bool = False,
) -> SolveResult | None:
    """Подстановка ``t = f(x)``: квадратное уравнение в ``t``, обратная замена, ветви."""
    result = prefix if prefix is not None else SolveResult()
    current = current if current is not None else node
    t = sympy.Symbol(_T)
    substitution = CoreNode.node(T.EQUALS, CoreNode.variable(_T), from_sympy(atom))
    polynomial = sympy.expand(expression.subs(atom, t))
    t_equation = _replace_atom(current, atom) or CoreNode.node(
        T.EQUALS, from_sympy(polynomial), _num(0)
    )
    result.add_group("eq_solve_sub", Step(current, t_equation, "eq_solve_sub", [substitution]))
    ordered_node = _descending_node(polynomial, _T)
    ordered_equation = CoreNode.node(T.EQUALS, ordered_node, _num(0))
    t_card = _equation_card(ordered_equation, [_T])
    first = next(iter(t_card), None) if t_card is not None else None
    if (
        t_card is not None
        and first is not None
        and first.left is not None
        and not first.left.structural_eq(t_equation)
    ):
        ordered_card = SolveResult()
        ordered_card.add_group("eq_solve_short", Step(t_equation, first.left, "var_order"))
        ordered_card.extend(t_card)
        if t_card.solution is not None:
            ordered_card.set_solution(t_card.solution)
        t_card = ordered_card
    roots = _solution_equations(t_card.solution if t_card is not None else None, _T)
    if not roots:
        return None
    roots_row = CoreNode.node(T.VERTICAL_LIST, *roots)
    result.add_group(
        "eq_solve_short",
        Step(
            t_equation,
            roots_row,
            "eq_linear",
            [CoreNode.variable(_T)],
            subresult=t_card,
        ),
    )
    branches = [CoreNode.node(T.EQUALS, from_sympy(atom), root.children[1]) for root in roots]
    branches_row = CoreNode.node(T.VERTICAL_LIST, *branches)
    result.add_group("sub_msg_ret", Step(roots_row, branches_row, "sub_msg_ret", [substitution]))
    return _finish_reducible(result, var, branches, tan_intersect=tan_intersect)


def _move_page(node: CoreNode, moved: CoreNode) -> SolveResult:
    """Экран переноса слагаемого: прибавить его к обеим частям и сократить."""
    lhs, rhs = node.children
    moved_rhs = moved.children[1]
    addend = moved_rhs if moved_rhs is not None else _num(0)
    page = SolveResult()
    first = CoreNode.node(
        T.EQUALS, CoreNode.node(T.ADD, lhs, addend), CoreNode.node(T.ADD, rhs, addend)
    )
    second = CoreNode.node(T.EQUALS, moved.children[0], CoreNode.node(T.ADD, rhs, addend))
    page.add_group("eq_solve_short", Step(node, first, "rel_swap_right"))
    page.add_group("eq_solve_short", Step(first, second, "sub_with_self_remove_alg"))
    page.add_group("simplify_msg", Step(second, moved, "add_with_zero", [_num(0)]))
    page.set_solution(moved)
    return page


def _homogeneous_division_page(
    moved: CoreNode, tan_equation: CoreNode, var: str, tan_value: sympy.Expr
) -> SolveResult:
    """Экран деления на ``cos x``: исключить нули косинуса и перейти к тангенсу."""
    x = CoreNode.variable(var)
    cos_node = CoreNode.node(T.COS, x)
    sine_node = CoreNode.node(T.SIN, x)
    zero = CoreNode.node(T.EQUALS, cos_node, _num(0))
    domain_series = _series(sympy.pi / 2, sympy.pi)
    domain_row = CoreNode.node(T.LIST, CoreNode.node(T.EQUALS, x, domain_series), _member())
    ratio = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.FRACTION, sine_node, cos_node),
        _value(tan_value),
    )
    excluded = CoreNode.node(
        T.LIST,
        ratio,
        CoreNode.node(T.LIST, CoreNode.node(T.NOT_EQUALS, x, domain_series), _member()),
    )
    generic = CoreNode.node(
        T.EQUALS,
        CoreNode.node(
            T.FRACTION,
            CoreNode.node(T.SIN, CoreNode.variable(_T)),
            CoreNode.node(T.COS, CoreNode.variable(_T)),
        ),
        CoreNode.node(T.TAN, CoreNode.variable(_T)),
    )
    page = SolveResult()
    page.add_group(
        "trig_eq_find_restricted_zero",
        Step(moved, zero, "trig_eq_find_restricted_zero", [cos_node, _num(0)]),
    )
    page.add_group("eq_solve_short", Step(zero, domain_row, "eq_linear", [x]))
    page.add_group(
        "trig_eq_exclude_restricted",
        Step(domain_row, excluded, "trig_eq_exclude_restricted", [cos_node]),
    )
    page.add_group("using_trans", Step(excluded, tan_equation, "using_trans", [generic]))
    page.set_solution(tan_equation)
    return page


def _division_detail(node: CoreNode, var: str, divided: CoreNode) -> SolveResult:
    """Экран деления однородного уравнения на ``cos²x``."""
    x = CoreNode.variable(var)
    cos_squared = CoreNode.node(T.POWER, CoreNode.node(T.COS, x), _num(2))
    zero = CoreNode.node(T.EQUALS, cos_squared, _num(0))
    excluded = CoreNode.node(
        T.LIST, CoreNode.node(T.EQUALS, x, _series(sympy.pi / 2, sympy.pi)), _member()
    )
    detail = SolveResult()
    detail.add_group(
        "trig_eq_find_restricted_zero",
        Step(node, zero, "trig_eq_find_restricted_zero", [cos_squared, _num(0)]),
    )
    detail.add_group(
        "eq_solve_short",
        Step(zero, excluded, "eq_linear", [x]),
    )
    detail.add_group(
        "trig_eq_exclude_restricted",
        Step(excluded, divided, "trig_eq_exclude_restricted", [cos_squared]),
    )
    detail.set_solution(divided)
    return detail


def _homogeneous_rows(node: CoreNode, var: str, expression: sympy.Expr) -> SolveResult | None:
    """Однородное уравнение в ``sin x`` и ``cos x``: делим на степень ``cos x``."""
    symbol = sympy.Symbol(var)
    sine, cosine = sympy.sin(symbol), sympy.cos(symbol)
    if expression.atoms(sympy.sin, sympy.cos) - {sine, cosine}:
        return None
    try:
        poly = sympy.Poly(expression, sine, cosine)
    except sympy.PolynomialError:
        return None
    if not poly.is_homogeneous:
        return None
    degree = poly.total_degree()
    if degree not in (1, 2):
        return None
    coefficients: dict[int, sympy.Expr] = {}
    for (power_sine, power_cosine), coefficient in poly.terms():
        if power_sine + power_cosine != degree:
            return None
        if coefficient.free_symbols or not coefficient.is_real:
            return None
        coefficients[power_sine] = coefficient
    if sympy.simplify(expression.subs({sine: 1, cosine: 0})) == 0:
        return None
    cos_node = CoreNode.node(T.COS, CoreNode.variable(var))
    cos_squared = CoreNode.node(T.POWER, cos_node, _num(2))
    if degree == 1:
        a = coefficients.get(1, sympy.Integer(0))
        b = coefficients.get(0, sympy.Integer(0))
        if a == 0 or b == 0:
            return None
        tan_value = sympy.simplify(-b / a)
        result = SolveResult()
        moved = CoreNode.node(
            T.EQUALS, from_sympy(sympy.simplify(a * sine)), from_sympy(sympy.simplify(-b * cosine))
        )
        result.add_group(
            "rel_move_right",
            Step(node, moved, "rel_move_right", subresult=_move_page(node, moved)),
        )
        tan_equation = CoreNode.node(
            T.EQUALS, CoreNode.node(T.TAN, CoreNode.variable(var)), _value(tan_value)
        )
        result.add_group(
            "eq_solve_short",
            Step(
                moved,
                tan_equation,
                "eq_linear_div",
                [cos_node],
                subresult=_homogeneous_division_page(moved, tan_equation, var, tan_value),
            ),
        )
        base = sympy.atan(tan_value)
        tabular = bool((base / sympy.pi).is_Rational)
        isolated = _Isolated(
            T.TAN,
            CoreNode.variable(var),
            symbol,
            sympy.Integer(1),
            sympy.Integer(0),
            sympy.Integer(0),
            tan_value,
            _value(tan_value),
        )
        return _tan_equation_rows(
            result,
            tan_equation,
            var,
            isolated,
            sympy.Integer(1),
            sympy.Integer(0),
            tan_value,
            base,
            tabular,
            restriction=False,
        )
    coefficients.setdefault(0, sympy.Integer(0))
    coefficients.setdefault(1, sympy.Integer(0))
    tan_poly = (
        coefficients.get(2, sympy.Integer(0)) * sympy.tan(symbol) ** 2
        + coefficients.get(1, sympy.Integer(0)) * sympy.tan(symbol)
        + coefficients.get(0, sympy.Integer(0))
    )
    if coefficients.get(2, 0) == 0:
        return None
    tan_equation = CoreNode.node(T.EQUALS, from_sympy(tan_poly), _num(0))
    result = SolveResult()
    result.add_group(
        "eq_solve_short",
        Step(
            node,
            tan_equation,
            "eq_linear_div",
            [cos_squared],
            subresult=_division_detail(node, var, tan_equation),
        ),
    )
    return _substitution_rows(
        tan_equation,
        var,
        sympy.tan(symbol),
        to_sympy(tan_equation.children[0]),
        prefix=result,
        current=tan_equation,
        tan_intersect=True,
    )


def _factoring_rows(node: CoreNode, var: str, expression: sympy.Expr) -> SolveResult | None:
    """Разложение на множители: ``sin 2x = 2sin x cos x``, вынос общего множителя."""
    symbol = sympy.Symbol(var)
    result = SolveResult()
    current = node
    expanded = expression
    doubles = [
        atom
        for atom in expanded.atoms(sympy.sin, sympy.cos)
        if len(atom.args) == 1 and sympy.simplify(atom.args[0] - 2 * symbol) == 0
    ]
    if doubles:
        double = doubles[0]
        lhs = current.children[0]
        replaced: CoreNode | None = None
        for child in lhs.walk():
            if child.type in (T.SIN, T.COS) and sympy.simplify(to_sympy(child) - double) == 0:
                if double.func is sympy.sin:
                    call = CoreNode.node(
                        T.MULTIPLY_IMPLICIT,
                        CoreNode.node(
                            T.MULTIPLY_IMPLICIT,
                            _num(2),
                            CoreNode.node(T.SIN, CoreNode.variable(var)),
                        ),
                        CoreNode.node(T.COS, CoreNode.variable(var)),
                    )
                else:
                    call = CoreNode.node(
                        T.SUBTRACT,
                        CoreNode.node(
                            T.POWER, CoreNode.node(T.COS, CoreNode.variable(var)), _num(2)
                        ),
                        CoreNode.node(
                            T.POWER, CoreNode.node(T.SIN, CoreNode.variable(var)), _num(2)
                        ),
                    )
                replaced = _replace_node(lhs, child, call)
                result.add_group(
                    "using_expand",
                    Step(
                        current,
                        CoreNode.node(T.EQUALS, replaced, current.children[1]),
                        "using_expand",
                        [CoreNode.node(T.EQUALS, child, call)],
                    ),
                )
                current = CoreNode.node(T.EQUALS, replaced, current.children[1])
                expanded = to_sympy(replaced) - to_sympy(current.children[1])
                break
    factored = sympy.factor(sympy.expand(expanded))
    if not factored.is_Mul:
        return None
    factors = [factor for factor in factored.args if symbol in factor.free_symbols]
    if len(factors) < 2:
        return None
    product = _product_node(factors)
    factored_equation = CoreNode.node(T.EQUALS, product, _num(0))
    result.add_group(
        "extract_arg",
        Step(current, factored_equation, "extract_arg", [from_sympy(factors[0])]),
    )
    current = factored_equation
    branches = [CoreNode.node(T.EQUALS, from_sympy(factor), _num(0)) for factor in factors]
    branches_row = CoreNode.node(T.VERTICAL_LIST, *branches)
    result.add_group(
        "quad_separate_zero_product",
        Step(current, branches_row, "quad_separate_zero_product", [_num(0)]),
    )
    return _finish_reducible(result, var, branches)


def _product_node(factors: list[sympy.Expr]) -> CoreNode:
    """Произведение множителей; сумма берётся в скобки."""
    node = from_sympy(factors[0])
    for factor in factors[1:]:
        right = from_sympy(factor)
        if right.type in (T.ADD, T.SUBTRACT):
            right = CoreNode.node(T.BRACKET, right)
        node = CoreNode.node(T.MULTIPLY, node, right)
    return node


def _tan_substitution_rows(
    node: CoreNode, var: str, atom: sympy.Expr, expression: sympy.Expr
) -> SolveResult | None:
    """Подстановка для тангенса/котангенса: сначала область определения."""
    x = CoreNode.variable(var)
    domain = (
        _tan_domain(var)
        if atom.func is sympy.tan
        else CoreNode.node(T.NOT_EQUALS, x, _series(sympy.Integer(0), sympy.pi))
    )
    restricted = CoreNode.node(T.LIST, node, CoreNode.node(T.LIST, domain, _member()))
    result = SolveResult()
    result.add_group(
        "rel_restrictions_range",
        Step(node, restricted, "rel_restrictions_range"),
    )
    return _substitution_rows(
        restricted,
        var,
        atom,
        expression,
        prefix=result,
        current=restricted,
        tan_intersect=True,
    )


def _sine_cosine_product_rows(node: CoreNode, var: str) -> SolveResult | None:
    """``sin x·cos x = 0``: ``sin 2x / 2 = 0``."""
    expression = _expr_of(node)
    if expression is None:
        return None
    symbol = sympy.Symbol(var)
    if sympy.simplify(expression - sympy.sin(symbol) * sympy.cos(symbol)) != 0:
        return None
    x = CoreNode.variable(var)
    sine, cosine = CoreNode.node(T.SIN, x), CoreNode.node(T.COS, x)
    doubled = CoreNode.node(
        T.SIN, CoreNode.node(T.MULTIPLY_IMPLICIT, _num(2), CoreNode.variable(var))
    )
    half = CoreNode.node(T.FRACTION, doubled, _num(2))
    member = _member()
    result = SolveResult()
    first = CoreNode.node(T.EQUALS, half, _num(0))
    identity = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.MULTIPLY_IMPLICIT, sine, cosine),
        half,
    )
    result.add_group(
        "using_sim",
        Step(node, first, "using_sim", [identity], subresult=_product_transform_page(var)),
    )
    second = CoreNode.node(T.EQUALS, doubled, _num(0))
    result.add_group("simplify_msg", Step(first, second, "eq_linear_frac_zero", [_num(0)]))
    doubled_argument = CoreNode.node(T.MULTIPLY_IMPLICIT, _num(2), CoreNode.variable(var))
    periodic = CoreNode.node(T.EQUALS, doubled_argument, _k_pi(1))
    third = CoreNode.node(T.LIST, periodic, member)
    answer = CoreNode.node(T.EQUALS, x, _series(sympy.Integer(0), sympy.pi / 2))
    generic = CoreNode.node(T.EQUALS, CoreNode.node(T.SIN, CoreNode.variable(_T)), _num(0))
    result.add_group(
        "simplify_msg",
        Step(
            second,
            third,
            "trig_eq_simple_solution",
            [
                generic,
                CoreNode.node(T.EQUALS, CoreNode.variable(_T), _k_pi(1)),
                answer,
                member,
            ],
        ),
    )
    result.add_group(
        "eq_solve_short",
        Step(
            third,
            answer,
            "eq_linear_div",
            [_num(2)],
            subresult=_halving_page(third, answer, var),
        ),
    )
    result.set_solution(answer)
    return result


def _product_transform_page(var: str) -> SolveResult:
    """Экран ``sin x·cos x = ½·2·sin x·cos x = ½sin 2x``."""
    x = CoreNode.variable(var)
    sine, cosine = CoreNode.node(T.SIN, x), CoreNode.node(T.COS, x)
    doubled = CoreNode.node(
        T.SIN, CoreNode.node(T.MULTIPLY_IMPLICIT, _num(2), CoreNode.variable(var))
    )
    half = CoreNode.node(T.FRACTION, _num(1), _num(2))
    two = CoreNode.node(T.MULTIPLY, half, _num(2))
    product = CoreNode.node(T.MULTIPLY_IMPLICIT, sine, cosine)
    scaled = CoreNode.node(
        T.MULTIPLY_IMPLICIT, CoreNode.node(T.MULTIPLY_IMPLICIT, two, sine), cosine
    )
    half_doubled = CoreNode.node(T.MULTIPLY, half, doubled)
    page = SolveResult()
    page.add_group("simplify_msg", Step(product, scaled, "frac_sep_n", [half]))
    page.add_group(
        "simplify_msg",
        Step(
            scaled,
            half_doubled,
            "using_sim",
            [
                CoreNode.node(
                    T.EQUALS, doubled, CoreNode.node(T.MULTIPLY_IMPLICIT, _num(2), product)
                )
            ],
        ),
    )
    halved = CoreNode.node(T.FRACTION, doubled, _num(2))
    page.add_group("simplify_msg", Step(half_doubled, halved, "product"))
    page.set_solution(halved)
    return page


def _halving_page(third: CoreNode, answer: CoreNode, var: str) -> SolveResult:
    """Экран ``2x = kπ -> 2x/2 = kπ/2 -> x = kπ/2``."""
    equation = third.children[0]
    argument = equation.children[0]
    kpart = _k_pi(1)
    divided = CoreNode.node(
        T.EQUALS,
        CoreNode.node(T.DIVIDE, argument, _num(2)),
        CoreNode.node(T.DIVIDE, kpart, _num(2)),
    )
    reciprocal = CoreNode.node(T.FRACTION, _num(1), _num(2))
    halved = CoreNode.node(
        T.EQUALS, CoreNode.variable(var), CoreNode.node(T.MULTIPLY, kpart, reciprocal)
    )
    page = SolveResult()
    page.add_group("eq_solve_short", Step(equation, divided, "eq_linear_div", [_num(2)]))
    page.add_group("simplify_msg", Step(divided, halved, "div_with_self", [_num(1)]))
    page.add_group("simplify_msg", Step(halved, answer, "div_to_frac"))
    _drop_noop_rows(page)
    page.set_solution(answer)
    return page


def _reducible_rows(node: CoreNode, var: str) -> SolveResult | None:
    """Карточки уравнений, сводящихся к простейшим."""
    if node.type is not T.EQUALS or len(node.children) != 2:
        return None
    expression = _expr_of(node)
    if expression is None or expression.free_symbols - {sympy.Symbol(var)}:
        return None
    product = _sine_cosine_product_rows(node, var)
    if product is not None:
        return product
    identity = _identity_prefix(node, var)
    if identity is not None:
        prefix, current, rewritten = identity
        atom = _single_atom(rewritten, var)
        if atom is not None:
            polynomial = _poly_expression(rewritten, atom, var)
            if polynomial is not None:
                return _substitution_rows(
                    node, var, atom, rewritten, prefix=prefix, current=current
                )
    atom = _single_atom(expression, var)
    if atom is not None:
        polynomial = _poly_expression(expression, atom, var)
        if polynomial is not None:
            # Нет свободного члена -- решатель выносит общий множитель.
            if sympy.simplify(expression.subs(atom, 0)) == 0:
                factored = _factoring_rows(node, var, expression)
                if factored is not None:
                    return factored
            if atom.func in (sympy.tan, sympy.cot):
                return _tan_substitution_rows(node, var, atom, expression)
            return _substitution_rows(node, var, atom, expression)
    homogeneous = _homogeneous_rows(node, var, expression)
    if homogeneous is not None:
        return homogeneous
    return _factoring_rows(node, var, expression)


# ---------------------------------------------------------------------------
# tan x = c и cot x = c: карточки по строкам.
# ---------------------------------------------------------------------------


def _tan_rows(node: CoreNode, var: str) -> SolveResult | None:
    """``A·tan/cot(a·x + b) + B = 0`` по строкам.

    Сначала область определения (``x ≠ π/2 + kπ`` у тангенса, ``x ≠ kπ`` у
    котангенса), затем обратная функция и её значение (если угол табличный),
    период ``kπ``, линейное уравнение для аргумента и пересечение с областью.
    """
    isolated = _isolated(node, var, (T.TAN, T.COT))
    if isolated is None:
        return None
    symbol = sympy.Symbol(var)
    coefficient = sympy.simplify(sympy.diff(isolated.expression, symbol))
    constant = sympy.simplify(isolated.expression - coefficient * symbol)
    tangent = isolated.kind is T.TAN
    value = isolated.value
    # arccot выбирается в (0, π): acot(-1) = 3π/4,
    # а не -π/4 (главная ветвь sympy).
    base = sympy.atan(value) if tangent else sympy.pi / 2 - sympy.atan(value)
    tabular = bool((base / sympy.pi).is_Rational)
    prefix, start = _prefix_rows(node, isolated)
    return _tan_equation_rows(
        prefix, start, var, isolated, coefficient, constant, value, base, tabular
    )


def _tan_equation_rows(
    prefix: SolveResult,
    start: CoreNode,
    var: str,
    isolated: _Isolated,
    coefficient: sympy.Expr,
    constant: sympy.Expr,
    value: sympy.Expr,
    base: sympy.Expr,
    tabular: bool,
    restriction: bool = True,
) -> SolveResult:
    """Общие строки уравнения с тангенсом/котангенсом."""
    eq = CoreNode.node
    x = CoreNode.variable(var)
    member = _member()
    tangent = isolated.kind is T.TAN
    argument = isolated.argument
    pi = sympy.pi

    domain_offset = (pi / 2 - constant) / coefficient if tangent else -constant / coefficient
    domain_period = pi / coefficient
    domain_node = _series(domain_offset, domain_period)
    domain = eq(T.NOT_EQUALS, x, domain_node)
    restricted = eq(T.LIST, start, eq(T.LIST, domain, member))

    detail = SolveResult()
    detail.add_group(
        "trig_eq_exclude_restricted",
        Step(
            start,
            eq(T.LIST, eq(T.EQUALS, x, domain_node), member),
            "trig_eq_exclude_restricted",
            [argument],
        ),
    )
    detail.add_group(
        "rel_restrictions_range_complement",
        Step(
            eq(T.LIST, eq(T.EQUALS, x, domain_node), member),
            restricted,
            "rel_restrictions_range_complement",
        ),
    )
    detail.set_solution(domain)
    result = prefix
    if restriction:
        result.add_group(
            "rel_restrictions_range",
            Step(start, restricted, "rel_restrictions_range", subresult=detail),
        )

    inverse_node = eq(T.ATAN if tangent else T.ACOT, isolated.value_node)
    current = eq(T.EQUALS, argument, inverse_node)
    result.add_group(
        "trig_eq_isolate_short",
        Step(restricted if restriction else start, current, "trig_eq_isolate", [argument]),
    )
    if tabular:
        valued = eq(T.EQUALS, argument, _angle(base))
        result.add_group(
            "find_value", Step(current, valued, _arcus_key(isolated.kind, value), [inverse_node])
        )
        current = valued

    series_node = _series(base, pi)
    known = eq(isolated.kind, argument)
    if coefficient == 1 and constant == 0:
        period_row = eq(T.LIST, eq(T.EQUALS, argument, series_node), domain, member)
    else:
        period_row = eq(T.LIST, eq(T.EQUALS, argument, series_node), member)
    result.add_group(
        "add_period",
        Step(current, period_row, "trig_eq_fun_period", [known, _k_pi(1), member]),
    )
    current = period_row

    solved_offset = sympy.simplify((base - constant) / coefficient)
    solved_period = sympy.simplify(pi / coefficient)
    solved = _series(solved_offset, solved_period)
    solved_node = eq(T.LIST, eq(T.EQUALS, x, solved), member)
    if coefficient != 1 or constant != 0:
        axis = from_sympy(sympy.simplify(coefficient * sympy.Symbol(var)))
        kpart = _k_pi(1)
        moved_rhs = eq(T.ADD, _series_add(_angle(base), -constant), kpart)
        moved = eq(T.LIST, eq(T.EQUALS, axis, moved_rhs), member)
        detail_move = SolveResult()
        detail_move.add_group(
            "rel_move_right_const_msg",
            Step(current, moved, "rel_move_right_const_eq"),
        )
        detail_move.set_solution(moved)
        result.add_group(
            "rel_move_right_const_msg",
            Step(current, moved, "rel_move_right_const_eq", subresult=detail_move),
        )
        current = moved

        difference = sympy.simplify(base - constant)
        if (difference / pi).is_Rational:
            diffed = eq(T.LIST, eq(T.EQUALS, axis, eq(T.ADD, _angle(difference), kpart)), member)
            detail_diff = SolveResult()
            detail_diff.add_group("calc_diff", Step(moved, diffed, "calc_diff"))
            detail_diff.set_solution(diffed)
            result.add_group("calc_diff", Step(moved, diffed, "calc_diff", subresult=detail_diff))
            current = diffed

        detail_divide = _divide_rows(
            axis,
            x,
            coefficient,
            _angle(difference),
            kpart,
            eq(T.EQUALS, x, solved),
        )
        solved_with_domain = eq(T.LIST, eq(T.EQUALS, x, solved), domain, member)
        result.add_group(
            "eq_solve_short",
            Step(
                current,
                solved_with_domain,
                "eq_linear_div",
                [_value(sympy.simplify(coefficient))],
                subresult=detail_divide,
            ),
        )
        current = solved_with_domain

    result.add_group("intersection", Step(current, solved_node, "rel_restrictions_intersect"))
    result.set_solution(eq(T.EQUALS, x, solved))
    if not tabular:
        result.add_group("calculate_short", _calculate_rows(solved_node, var))
    return result


def _two_sided_rows(node: CoreNode, var: str) -> SolveResult | None:
    """``sin x = cos x``: разделить на ``cos x`` и свести к ``tan x = 1``.

    Решатель сначала показывает исключение нулей косинуса (вложенный экран
    ``eq_linear_div``), затем решает обычное уравнение для тангенса.
    """
    lhs, rhs = node.children
    if lhs.type is T.SIN and rhs.type is T.COS:
        sine, cosine = lhs, rhs
        tan_value = sympy.Integer(1)
    elif lhs.type is T.COS and rhs.type is T.SIN:
        sine, cosine = rhs, lhs
        tan_value = sympy.Integer(1)
    else:
        return None
    argument = sine.children[0] if len(sine.children) == 1 else None
    if (
        argument is None
        or argument.type is not T.VARIABLE
        or argument.value != var
        or len(cosine.children) != 1
        or not cosine.children[0].structural_eq(argument)
    ):
        return None
    x, k, pi = CoreNode.variable(var), sympy.Symbol(_PARAMETER), sympy.pi
    eq = CoreNode.node
    member = _member()
    tan = eq(T.TAN, x)
    rhs_node = _value(tan_value)
    tan_equation = eq(T.EQUALS, tan, rhs_node)
    cos_zero = eq(T.EQUALS, cosine, CoreNode.constant("0"))
    value = sympy.Integer(1)
    base = sympy.atan(value)
    domain = eq(T.NOT_EQUALS, x, _series(pi / 2, pi))
    cos_solution = eq(T.LIST, eq(T.EQUALS, x, _series(pi / 2, pi)), member)
    ratio = eq(T.EQUALS, eq(T.FRACTION, sine, cosine), rhs_node)
    excluded = eq(T.LIST, ratio, eq(T.LIST, domain, member))
    generic = eq(
        T.EQUALS,
        eq(T.FRACTION, eq(T.SIN, CoreNode.variable("t")), eq(T.COS, CoreNode.variable("t"))),
        eq(T.TAN, CoreNode.variable("t")),
    )
    detail = SolveResult()
    detail.add_group(
        "trig_eq_find_restricted_zero",
        Step(node, cos_zero, "trig_eq_find_restricted_zero", [cosine, CoreNode.constant("0")]),
    )
    detail.add_group("eq_linear", Step(cos_zero, cos_solution, "eq_linear", [x]))
    detail.add_group(
        "trig_eq_exclude_restricted",
        Step(cos_solution, excluded, "trig_eq_exclude_restricted", [cosine]),
    )
    detail.add_group("using_trans", Step(excluded, tan_equation, "using_trans", [generic]))
    detail.set_solution(tan_equation)
    result = SolveResult()
    result.add_group(
        "calculate_short",
        Step(node, tan_equation, "eq_linear_div", [cosine], subresult=detail),
    )
    isolated = _Isolated(
        T.TAN,
        argument,
        to_sympy(argument),
        sympy.Integer(1),
        sympy.Integer(0),
        value,
        value,
        rhs_node,
    )
    _ = k
    return _tan_equation_rows(
        result,
        tan_equation,
        var,
        isolated,
        sympy.Integer(1),
        sympy.Integer(0),
        value,
        base,
        True,
        restriction=False,
    )


# ---------------------------------------------------------------------------
# Общий путь: серии sympy, слияние серий, запись периода.
# ---------------------------------------------------------------------------


def _merge_series(
    series: list[tuple[sympy.Expr, sympy.Expr]],
) -> list[tuple[sympy.Expr, sympy.Expr]]:
    """Слить серии, отличающиеся на долю периода, в одну.

    ``π/2 + 2kπ``, ``7π/6 + 2kπ`` и ``11π/6 + 2kπ`` дают ``π/2 + 2kπ/3`` (t16): если
    смещения вместе образуют полную арифметическую прогрессию с шагом
    ``период/n``, набор серий записывается одной серией с меньшим периодом.
    Сливаются только такие объединения, которые не добавляют новых корней.
    """
    if len(series) < 2:
        return series
    ratios_period: list[sympy.Rational] = []
    ratios_offset: list[sympy.Rational] = []
    for period, offset in series:
        if period < 0:
            period = -period
        period_ratio = sympy.simplify(period / sympy.pi)
        offset_ratio = sympy.simplify(offset / sympy.pi)
        if not (period_ratio.is_Rational and offset_ratio.is_Rational):
            return series
        ratios_period.append(period_ratio)
        ratios_offset.append(offset_ratio)

    unit = 1
    for ratio in ratios_period + ratios_offset:
        unit = lcm(unit, int(ratio.q))
    periods = [int(ratio * unit) for ratio in ratios_period]
    offsets = [int(ratio * unit) for ratio in ratios_offset]
    full = 1
    for period in periods:
        full = lcm(full, period)

    residues: set[int] = set()
    for period, offset in zip(periods, offsets, strict=True):
        for step in range(0, full, period):
            residues.add((offset + step) % full)

    candidates: list[tuple[int, int, int, frozenset[int]]] = []
    for step in range(1, full + 1):
        if full % step:
            continue
        size = full // step
        for start in range(step):
            block = frozenset((start + index * step) % full for index in range(size))
            if block <= residues:
                candidates.append((size, step, start, block))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))

    best: list[tuple[int, int, int, frozenset[int]]] | None = None

    def search(
        uncovered: frozenset[int],
        chosen: list[tuple[int, int, int, frozenset[int]]],
    ) -> None:
        nonlocal best
        if best is not None and len(chosen) >= len(best):
            return
        if not uncovered:
            best = list(chosen)
            return
        pivot = min(uncovered)
        for candidate in candidates:
            if pivot not in candidate[3]:
                continue
            chosen.append(candidate)
            search(uncovered - candidate[3], chosen)
            chosen.pop()

    search(frozenset(residues), [])
    if not best or len(best) >= len(series):
        ordered = sorted(series, key=_series_sort_key)
        return ordered
    merged = [
        (sympy.Rational(step) * sympy.pi / unit, sympy.Rational(min(block)) * sympy.pi / unit)
        for _size, step, _start, block in best
    ]
    return sorted(merged, key=_series_sort_key)


def _families(solution_set: sympy.Set) -> list[tuple[sympy.Expr, sympy.Expr]]:
    """Разложить множество решений на серии ``(выражение, параметр)``."""
    images = solution_set.args if isinstance(solution_set, sympy.Union) else (solution_set,)
    if len(images) > _MAX_SERIES:
        return []

    families: list[tuple[sympy.Expr, sympy.Expr]] = []
    for image in images:
        if not isinstance(image, sympy.ImageSet):
            return []
        if len(image.lamda.variables) != 1:
            return []
        parameter = image.lamda.variables[0]
        families.append((sympy.expand(image.lamda.expr), parameter))
    return families


def _linear(
    expression: sympy.Expr, parameter: sympy.Symbol
) -> tuple[sympy.Expr, sympy.Expr] | None:
    """``(период, смещение)`` линейной серии ``period*k + offset`` или ``None``."""
    period = expression.coeff(parameter)
    if period == 0:
        return None
    offset = expression.subs(parameter, 0)
    if sympy.simplify(expression - (period * parameter + offset)) != 0:
        return None
    return period, offset


def _at_zero(family: Family) -> sympy.Expr:
    """Значение серии при параметре, равном нулю."""
    return sympy.simplify(family[0].subs(family[1], 0))


def _series_node(
    var: str,
    series: list[tuple[sympy.Expr, sympy.Expr]],
    *,
    merge: bool = True,
) -> CoreNode:
    """Узел общего решения: ``x = смещение + период·k`` (или список таких)."""
    ordered = _merge_series(series) if merge else sorted(series, key=_series_sort_key)
    equations = [
        CoreNode.node(T.EQUALS, CoreNode.variable(var), _series(offset, period))
        for period, offset in ordered
    ]
    if len(equations) == 1:
        return equations[0]
    return CoreNode.node(T.LIST, *equations)


def _raw_node(var: str, families: list[Family]) -> CoreNode:
    """Общее решение нелинейных серий: ``x = формула(от k)`` как есть."""
    parameter = sympy.Symbol(_PARAMETER)
    ordered = sorted(families, key=lambda family: _family_sort_key(family))
    equations = []
    for expression, source in ordered:
        right = from_sympy(expression.subs(source, parameter))
        equations.append(CoreNode.node(T.EQUALS, CoreNode.variable(var), right))
    if len(equations) == 1:
        return equations[0]
    return CoreNode.node(T.LIST, *equations)


def _series_sort_key(series: tuple[sympy.Expr, sympy.Expr]) -> float:
    try:
        return float(sympy.N(series[1]))
    except (TypeError, ValueError):
        return 0.0


def _family_sort_key(family: Family) -> float:
    return _series_sort_key((family[0], _at_zero(family)))


def _select_interval(
    var: str, series: list[tuple[sympy.Expr, sympy.Expr]], interval: Interval
) -> list[CoreNode] | None:
    """Отобрать корни линейных серий на промежутке или ``None``, если он нечисловой."""
    low, high = to_sympy(interval[0]), to_sympy(interval[1])
    if not (low.is_number and high.is_number):
        return None

    values: list[sympy.Expr] = []
    for period, offset in series:
        if not (period.is_number and offset.is_number):
            return None
        first = int(sympy.floor((low - offset) / period))
        last = int(sympy.ceiling((high - offset) / period))
        for index in range(first, last + 1):
            value = offset + period * index
            if not (low <= value <= high):
                continue
            if not any(sympy.simplify(value - existing) == 0 for existing in values):
                values.append(value)

    values.sort(key=lambda value: float(sympy.N(value)))
    return [CoreNode.node(T.EQUALS, CoreNode.variable(var), from_sympy(value)) for value in values]


def _select_raw(var: str, families: list[Family], interval: Interval) -> list[CoreNode] | None:
    """Отобрать корни нелинейных серий перебором параметра на промежутке."""
    low, high = to_sympy(interval[0]), to_sympy(interval[1])
    if not (low.is_number and high.is_number):
        return None

    values: list[sympy.Expr] = []
    for expression, parameter in families:
        for index in range(-_MAX_PARAMETER, _MAX_PARAMETER + 1):
            value = expression.subs(parameter, index)
            if not value.is_number:
                continue
            if not (low <= value <= high):
                continue
            if not any(sympy.simplify(value - existing) == 0 for existing in values):
                values.append(value)

    values.sort(key=lambda value: float(sympy.N(value)))
    return [CoreNode.node(T.EQUALS, CoreNode.variable(var), from_sympy(value)) for value in values]


__all__ = [
    "Interval",
    "looks_trigonometric",
    "solve_trig_equation",
    "unknown_of",
]
