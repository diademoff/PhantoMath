"""Суммы (знак суммирования).

Модуль зарегистрирован на ``SIGMA_DEFINITE``. Дети, как в нативном решателе
(``c/a/a/l/h/v/k.java``): ``[индекс, нижний предел, верхний предел,
выражение]``. Принимается и форма редактора ``[нижний, верхний, выражение]``
с индексом ``n``.

Сумма вычисляется sympy; для числовых пределов выходит точное число, для
символьной верхней границы — формула. Результат переводится обратно в
``CoreNode`` мостом.

Шаг один — ``series_sigma_find_sub``.
"""

from __future__ import annotations

import sympy

from ..ast import CoreNode
from ..node_types import CoreNodeType as T
from .base import SolveContext, SolveError, Step, boolean_node, solver_for
from .sympy_bridge import from_sympy, to_sympy


def _parts(node: CoreNode) -> tuple[str, CoreNode, CoreNode, CoreNode]:
    """Разобрать узел в ``(имя индекса, нижний, верхний, выражение)``."""
    if len(node.children) == 4:
        index, lower, upper, expression = node.children
        if index.type is not T.VARIABLE or not index.value:
            raise SolveError("индекс суммы должен быть переменной")
        return index.value, lower, upper, expression
    if len(node.children) == 3:
        lower, upper, expression = node.children
        return "n", lower, upper, expression
    raise SolveError("сумма задаётся индексом, пределами и выражением")


@solver_for(T.SIGMA_DEFINITE)
def solve_series(node: CoreNode, ctx: SolveContext) -> CoreNode:
    """Вычислить сумму ряда."""
    index, lower, upper, expression = _parts(node)
    symbol = sympy.Symbol(index)
    value = sympy.summation(
        to_sympy(expression),
        (symbol, to_sympy(lower), to_sympy(upper)),
    )
    if value.has(sympy.Sum):
        raise SolveError("сумму не удалось вычислить")
    result = from_sympy(sympy.simplify(value))
    ctx.result.add(Step(left=node, right=result, key="series_sigma_find_sub"))
    return result


def convergence(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Определить, сходится ли ряд (сумма с бесконечным пределом).

    Сначала пробуется точная сумма (sympy). Если замкнутой суммы нет —
    применяется интегральный признак.
    """
    del args
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("сходимость определяется у ряда (суммы)")
    index, lower, upper, expression = _parts(node)
    symbol = sympy.Symbol(index)
    value = sympy.summation(to_sympy(expression), (symbol, to_sympy(lower), to_sympy(upper)))
    if value.has(sympy.Sum):
        return _integral_test(node, ctx, expression, lower, symbol)
    converges = value.is_finite is True
    answer = boolean_node(converges)
    ctx.result.add(Step(left=node, right=answer, key="convergent" if converges else "divergent"))
    return answer


def integral_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Интегральный признак сходимости (команда ``integral_test``)."""
    del args
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("интегральный признак применяется к ряду (сумме)")
    index, lower, _, expression = _parts(node)
    return _integral_test(node, ctx, expression, lower, sympy.Symbol(index))


def _integral_test(
    node: CoreNode,
    ctx: SolveContext,
    expression: CoreNode,
    lower: CoreNode,
    symbol: sympy.Symbol,
) -> CoreNode:
    """Интегральный признак: ``∫_N^∞ f(x) dx`` для ``f(x) = a(x)``."""
    variable = sympy.Symbol("t") if str(symbol) != "t" else sympy.Symbol("u")
    function = to_sympy(expression).subs(symbol, variable)
    boundary = to_sympy(lower)
    ctx.result.add(Step(left=node, right=None, key="series_integral_test"))
    ctx.result.add(Step(left=node, right=None, key="series_integral_test_use_smpl"))
    try:
        value = sympy.integrate(function, (variable, boundary, sympy.oo))
    except (TypeError, ValueError, NotImplementedError) as error:
        raise SolveError("интегральный признак не применим") from error
    if value.is_finite is True:
        key, converges = "series_integral_test_converges", True
    elif value in (sympy.oo, -sympy.oo, sympy.zoo) or value.is_finite is False:
        key, converges = "series_integral_test_diverges", False
    else:
        raise SolveError("интегральный признак не применим")
    answer = boolean_node(converges)
    ctx.result.add(Step(left=node, right=answer, key=key))
    return answer


def alt_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Признак Лейбница для знакочередующегося ряда (команда ``alt_test``)."""
    del args
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("признак Лейбница применяется к ряду (сумме)")
    index, _, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    term = to_sympy(expression)
    if not term.has((-sympy.Integer(1)) ** symbol):
        raise SolveError("ряд не знакочередующийся")

    magnitude = sympy.Abs(term)
    ctx.result.add(Step(left=node, right=None, key="series_alt_test"))
    decreasing = sympy.limit(magnitude.subs(symbol, symbol + 1) / magnitude, symbol, sympy.oo)
    limit = sympy.limit(magnitude, symbol, sympy.oo)
    if limit == 0 and decreasing.is_number and (decreasing <= 1) is sympy.true:
        answer = boolean_node(True)
        ctx.result.add(Step(left=node, right=answer, key="series_alt_test_converges"))
        return answer
    answer = boolean_node(False)
    ctx.result.add(
        Step(
            left=node,
            right=answer,
            key="series_nth_term_test_lim_nozero",
            args=[CoreNode.constant("0")],
        )
    )
    return answer


def ratio_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Признак Даламбера: сходимость ряда по пределу ``|aₙ₊₁/aₙ|``.

    Шаги ``series_ratio_test_use`` и ``series_ratio_test_lim_ltone``/
    ``_gtone``/``_inf``. Предел, равный ``1``, ответа не даёт — :class:`SolveError`.
    """
    del args
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("признак Даламбера применяется к ряду (сумме)")
    index, _, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    term = to_sympy(expression)
    if term == 0:
        raise SolveError("нулевой член ряда")
    ratio = sympy.simplify(sympy.Abs(term.subs(symbol, symbol + 1) / term))

    ctx.result.add(Step(left=node, right=None, key="series_ratio_test"))
    ctx.result.add(
        Step(left=node, right=None, key="series_ratio_test_use", args=[from_sympy(ratio)])
    )
    limit = sympy.limit(ratio, symbol, sympy.oo)
    if limit in (sympy.oo, -sympy.oo, sympy.zoo):
        key, answer = "series_ratio_test_lim_inf", boolean_node(False)
        args = [from_sympy(sympy.oo)]
    elif limit.is_number and (limit < 1) is sympy.true:
        key = "series_ratio_test_lim_ltone"
        answer, args = boolean_node(True), [CoreNode.constant("1")]
    elif limit.is_number and (limit > 1) is sympy.true:
        key, answer, args = (
            "series_ratio_test_lim_gtone",
            boolean_node(False),
            [CoreNode.constant("1")],
        )
    else:
        raise SolveError("признак Даламбера не даёт ответа")

    ctx.result.add(Step(left=node, right=answer, key=key, args=args))
    return answer


def root_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Радикальный признак (Коши): предел ``|aₙ|^(1/n)``.

    Шаги ``series_root_test``, ``series_root_test_use`` и
    ``series_root_test_lim_ltone``/``_gtone``/``_inf``. Предел ``1`` ответа не даёт.
    """
    del args
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("радикальный признак применяется к ряду (сумме)")
    index, _, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    term = to_sympy(expression)
    root = sympy.Abs(term) ** (sympy.Integer(1) / symbol)

    ctx.result.add(Step(left=node, right=None, key="series_root_test"))
    ctx.result.add(Step(left=node, right=None, key="series_root_test_use", args=[from_sympy(root)]))
    limit = sympy.limit(root, symbol, sympy.oo)
    if limit in (sympy.oo, -sympy.oo, sympy.zoo):
        key, answer, args_nodes = (
            "series_root_test_lim_inf",
            boolean_node(False),
            [from_sympy(sympy.oo)],
        )
    elif limit.is_number and (limit < 1) is sympy.true:
        key, answer, args_nodes = (
            "series_root_test_lim_ltone",
            boolean_node(True),
            [CoreNode.constant("1")],
        )
    elif limit.is_number and (limit > 1) is sympy.true:
        key, answer, args_nodes = (
            "series_root_test_lim_gtone",
            boolean_node(False),
            [CoreNode.constant("1")],
        )
    else:
        raise SolveError("радикальный признак не даёт ответа")
    ctx.result.add(Step(left=node, right=answer, key=key, args=args_nodes))
    return answer


def nth_term_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Необходимый признак сходимости: предел общего члена.

    Если предел отличен от нуля — ряд расходится (``series_nth_term_test_lim_nozero``);
    нулевой предел ответа не даёт (:class:`SolveError`).
    """
    del args
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("необходимый признак применяется к ряду (сумме)")
    index, _, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    term = to_sympy(expression)

    ctx.result.add(Step(left=node, right=None, key="series_nth_term_test"))
    ctx.result.add(
        Step(left=node, right=None, key="series_nth_term_test_use", args=[from_sympy(term)])
    )
    limit = sympy.limit(term, symbol, sympy.oo)
    if limit.is_number and limit != 0:
        answer = boolean_node(False)
        ctx.result.add(
            Step(
                left=node,
                right=answer,
                key="series_nth_term_test_lim_nozero",
                args=[CoreNode.constant("0")],
            )
        )
        return answer
    raise SolveError("необходимый признак сходимости не даёт ответа")


def radius_of_convergence(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Радиус сходимости степенного ряда ``Σ aₙ·xⁿ``.

    По признаку Даламбера ``R = lim |aₙ/aₙ₊₁|``. Шаги ``convergence_radius_find``,
    ``convergence_radius_limit`` и ``convergence_radius_conv``/``_conv_inf``.
    """
    del args
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("радиус сходимости — у степенного ряда (суммы)")
    index, _, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    variable = next((name for name in ctx.variables if name != index), None)
    if variable is None:
        raise SolveError("в степенном ряде нет переменной")
    xsym = sympy.Symbol(variable)

    term = to_sympy(expression)
    coefficient = sympy.simplify(term / xsym**symbol)
    if coefficient.has(xsym):
        raise SolveError("ряд не степенной: нужен вид aₙ·xⁿ")
    ratio = sympy.simplify(sympy.Abs(coefficient / coefficient.subs(symbol, symbol + 1)))

    ctx.result.add(Step(left=node, right=None, key="convergence_radius_find"))
    ctx.result.add(
        Step(left=node, right=None, key="convergence_radius_limit", args=[from_sympy(ratio)])
    )
    radius = sympy.limit(ratio, symbol, sympy.oo)
    if radius in (sympy.oo, -sympy.oo, sympy.zoo):
        answer = from_sympy(sympy.oo)
        key = "convergence_radius_conv_inf"
    else:
        answer = from_sympy(radius)
        key = "convergence_radius_conv"
    ctx.result.add(Step(left=node, right=answer, key=key, args=[from_sympy(xsym), answer]))
    return answer


def pseries_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Признак обобщённого гармонического ряда: ``Σ 1/nᵖ`` сходится при ``p > 1``."""
    del args
    index, _, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    term = sympy.simplify(to_sympy(expression))
    _, rest = term.as_coeff_Mul()
    if not isinstance(rest, sympy.Pow) or rest.base != symbol:
        raise SolveError("ряд не обобщённый гармонический")
    exponent = -rest.exp

    ctx.result.add(Step(left=node, right=None, key="series_pseries_test"))
    ctx.result.add(
        Step(
            left=node,
            right=None,
            key="series_pseries_test_use",
            args=[from_sympy(exponent)],
        )
    )
    converges = (exponent > 1) is sympy.true
    condition = CoreNode.node(
        T.GREATER_THAN if converges else T.LESS_THAN_EQUAL,
        from_sympy(exponent),
        CoreNode.constant("1"),
    )
    answer = boolean_node(converges)
    key = "series_pseries_test_converges" if converges else "series_pseries_test_diverges"
    ctx.result.add(Step(left=node, right=answer, key=key, args=[condition]))
    return answer


def geom_series_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Признак геометрического ряда: отношение соседних членов постоянно."""
    del args
    index, _, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    term = to_sympy(expression)
    if term == 0:
        raise SolveError("нулевой член ряда")
    ratio = sympy.simplify(term.subs(symbol, symbol + 1) / term)
    if ratio.has(symbol):
        raise SolveError("ряд не геометрический")

    ctx.result.add(Step(left=node, right=None, key="series_geom_series_test"))
    converges = (sympy.Abs(ratio) < 1) is sympy.true
    condition = CoreNode.node(
        T.LESS_THAN if converges else T.GREATER_THAN_EQUAL,
        from_sympy(sympy.Abs(ratio)),
        CoreNode.constant("1"),
    )
    answer = boolean_node(converges)
    key = "series_geom_series_test_converges" if converges else "series_geom_series_test_diverges"
    ctx.result.add(Step(left=node, right=answer, key=key, args=[condition]))
    return answer


def _series_converges(expression: CoreNode, symbol: sympy.Symbol, lower: CoreNode) -> bool | None:
    """Сходится ли ряд с данным общим членом (``None`` — не определить)."""
    term = to_sympy(expression)
    value = sympy.summation(term, (symbol, to_sympy(lower), sympy.oo))
    if not value.has(sympy.Sum):
        if value.is_finite is True:
            return True
        if value in (sympy.oo, -sympy.oo, sympy.zoo) or value.is_finite is False:
            return False
        return None
    variable = sympy.Symbol("t") if str(symbol) != "t" else sympy.Symbol("u")
    integral = sympy.integrate(term.subs(symbol, variable), (variable, to_sympy(lower), sympy.oo))
    if integral.is_finite is True:
        return True
    if integral in (sympy.oo, -sympy.oo, sympy.zoo) or integral.is_finite is False:
        return False
    return None


def _reference(node: CoreNode) -> tuple[CoreNode, sympy.Symbol]:
    """Ряд-эталон из аргумента команды."""
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("ряд-эталон — это сумма")
    index, _, _, expression = _parts(node)
    return expression, sympy.Symbol(index)


def direct_comparison_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Признак сравнения: почленное сравнение с рядом-эталоном (аргумент)."""
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("признак сравнения применяется к ряду (сумме)")
    ctx.require(len(args) == 1, "нужен ряд-эталон")
    index, lower, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    reference_expression, _ = _reference(args[0])
    reference_converges = _series_converges(reference_expression, sympy.Symbol(index), lower)
    ctx.require(reference_converges is not None, "ряд-эталон не исследован")

    ratio = sympy.limit(to_sympy(expression) / to_sympy(reference_expression), symbol, sympy.oo)
    ctx.require(ratio.is_number is True, "сравнение членов не установлено")
    if reference_converges:
        ctx.require(
            (ratio <= 1) is sympy.true,
            "сравнение членов не выполнено: aₙ не меньше bₙ",
        )
    else:
        ctx.require(
            (ratio >= 1) is sympy.true,
            "сравнение членов не выполнено: aₙ не больше bₙ",
        )
    ctx.result.add(Step(left=node, right=None, key="series_direct_comp_test"))
    ctx.result.add(Step(left=node, right=None, key="series_direct_comp_test_use", args=[args[0]]))
    if reference_converges:
        key, converges = "series_direct_comp_test_converges", True
    else:
        key, converges = "series_direct_comp_test_diverges", False
    answer = boolean_node(converges)
    ctx.result.add(Step(left=node, right=answer, key=key, args=[args[0]]))
    return answer


def limit_comparison_test(node: CoreNode, ctx: SolveContext, args: list[CoreNode]) -> CoreNode:
    """Предельный признак сравнения с рядом-эталоном (аргумент)."""
    if node.type is not T.SIGMA_DEFINITE:
        raise SolveError("предельный признак сравнения применяется к ряду (сумме)")
    ctx.require(len(args) == 1, "нужен ряд-эталон")
    index, lower, _, expression = _parts(node)
    symbol = sympy.Symbol(index)
    reference_expression, _ = _reference(args[0])
    reference_converges = _series_converges(reference_expression, symbol, lower)
    ctx.require(reference_converges is not None, "ряд-эталон не исследован")

    ratio = sympy.limit(to_sympy(expression) / to_sympy(reference_expression), symbol, sympy.oo)
    ctx.require(
        ratio.is_finite is True and ratio.is_positive is True,
        "предельное отношение не конечно и не положительно",
    )
    ctx.result.add(Step(left=node, right=None, key="series_limit_test"))
    if reference_converges:
        key, converges = "series_limit_test_converges", True
        ctx.result.add(
            Step(left=node, right=None, key="series_limit_test_use_conv", args=[args[0]])
        )
    else:
        key, converges = "series_limit_test_diverges", False
        ctx.result.add(Step(left=node, right=None, key="series_limit_test_use_div", args=[args[0]]))
    answer = boolean_node(converges)
    ctx.result.add(Step(left=node, right=answer, key=key, args=[args[0]]))
    return answer


__all__ = [
    "alt_test",
    "convergence",
    "direct_comparison_test",
    "geom_series_test",
    "integral_test",
    "limit_comparison_test",
    "nth_term_test",
    "pseries_test",
    "radius_of_convergence",
    "ratio_test",
    "root_test",
    "solve_series",
]
