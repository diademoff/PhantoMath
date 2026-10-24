"""Логика сервиса без HTTP-фреймворка.

Одна и та же она нужна двум фронтам:

* ``api.py`` -- FastAPI для десктопа и разработки;
* ``device.py`` -- локальный сервер на устройстве (stdlib ``http.server``),
  который запускается встроенным CPython (``serious_python``).

Здесь нет ни ``fastapi``, ни ``pydantic``: только решатель, словарь
объяснений и глоссарий. Так ядро остаётся переносимым и не тянет
``pydantic-core`` (Rust).

Функции бросают ``ProtocolError`` (разбор строки), ``ValueError``/``KeyError``
(разбор дерева/действия) и ``SolveError`` (задача не решилась); HTTP-коды
расставляет вызывающий.
"""

from __future__ import annotations

import os
import re
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import sympy

from .ast import CoreAction, CoreNode, CoreRichText
from .concepts import definition as concept_definition
from .explanations import DEFAULT_LOCALE, Explanations, load_explanations
from .graph import DEFAULT_SAMPLES
from .graph import sample as sample_graph
from .input import parse_json, parse_protocol
from .node_types import CoreNodeType as T
from .results import CoreSolverGroup, Entry, ResultGroupType
from .solver import SolveError, expression_cards, solve
from .solver.alternatives import alternative_forms
from .solver.base import build_solver_data
from .solver.complex import contains_imaginary
from .solver.equations import poly_of
from .solver.sympy_bridge import to_sympy
from .teaching import theory as base_theory
from .teaching_registry import theory as pack_theory

# Языки продукта: русский и английский. В данных английский хранится как `default`.
SUPPORTED_LOCALES: tuple[str, ...] = ("ru", "en")


def normalize_locale(locale: str) -> str:
    """Привести язык к поддерживаемому: `ru` или английский (`default`).

    Любой другой язык (в том числе диалект вида `ru-RU`) откатывается к
    английскому. Так решение «только ru/en» действует и для старых клиентов,
    а в словаре остаются все 9 языков как исследовательский артефакт.
    """
    base = locale.strip().lower().split("-")[0]
    if base == "ru":
        return "ru"
    return DEFAULT_LOCALE


# Словарь лежит в пакете; путь можно переопределить переменной окружения.
_DEFAULT_EXPLANATIONS = Path(__file__).resolve().parent / "data" / "explanations.json"


def explanations_path() -> Path:
    """Путь к словарю: MYMATH_EXPLANATIONS имеет приоритет над умолчанием."""
    return Path(os.environ.get("MYMATH_EXPLANATIONS", str(_DEFAULT_EXPLANATIONS)))


@lru_cache(maxsize=1)
def explanations() -> Explanations:
    """Словарь объяснений; читается один раз за процесс."""
    return load_explanations(str(explanations_path()))


def explanations_loaded() -> bool:
    """Есть ли словарь. Без него ответы отдаются с ключами, но без текстов."""
    try:
        explanations()
    except OSError:
        return False
    return True


def health() -> dict[str, Any]:
    """Живость сервиса и состояние словаря объяснений."""
    try:
        size = len(explanations())
    except OSError as err:
        return {"status": "degraded", "explanations": 0, "detail": str(err)}
    return {"status": "ok", "explanations": size, "locales": list(SUPPORTED_LOCALES)}


def theory(key: str, locale: str) -> dict[str, str] | None:
    """The offline article for a step key: the core topics first, then the subject packs."""
    return base_theory(key, locale) or pack_theory(key, locale)


def _render_view(key: str, args: list[CoreNode], locale: str) -> dict[str, Any]:
    """Развернуть один ключ пояснения.

    Без словаря отдаём только ключ: ответ остаётся валидным, фронт покажет
    его как есть, а health сообщит о проблеме.
    """
    used_locale = normalize_locale(locale)
    if not explanations_loaded():
        return {
            "key": key,
            "text": "",
            "locale": used_locale,
            "links": [],
            "tail_label": None,
            "missing": True,
        }
    rendered = explanations().render(key, args, used_locale)
    # Keep arguments as math trees instead of flattening fractions/roots into
    # debug strings. The plain text remains for older clients.
    marked = explanations().render(
        key, args, used_locale, render_arg=lambda n: f"\ufff0{args.index(n)}\ufff1"
    )
    parts: list[dict[str, Any]] = []
    for part in re.split(r"(\ufff0\d+\ufff1)", marked.text):
        if part.startswith("\ufff0") and part.endswith("\ufff1"):
            parts.append({"type": "math", "node": args[int(part[1:-1])].to_contract()})
        elif part:
            parts.append({"type": "text", "text": part})
    return {
        "key": key,
        "text": rendered.text,
        "locale": rendered.locale,
        "links": [
            {
                "label": link.label,
                "uuid": link.uuid,
                "definition": concept_definition(link.uuid, used_locale) or "",
            }
            for link in rendered.links
        ],
        "tail_label": rendered.tail_label,
        "missing": rendered.missing_key,
        "parts": parts,
        "theory": theory(key, used_locale),
    }


def _render_rich(rich: dict[str, Any], locale: str) -> dict[str, Any]:
    """Развернуть `CoreRichText` (`{"type","args"}`) в текстовую вьюху."""
    args = [CoreNode.from_contract(a) for a in rich.get("args", [])]
    return _render_view(rich["type"], args, locale)


def attach_text(node: dict[str, Any], locale: str, _path: str = "solution") -> dict[str, Any]:
    """Дописать тексты пояснений в узлы ответа.

    Мутирует копию ответа: фронт получает и дерево, и готовые строки,
    не разбирая шаблоны у себя. Исходный формат остаётся валидным --
    лишний ключ ``explanation`` просто игнорируется.
    """
    out = dict(node)
    if "substeps" in out or "description" in out:
        out.setdefault("id", _path)
    description = out.get("description")
    if isinstance(description, dict) and "type" in description:
        out["explanation"] = _render_rich(description, locale)
        if not out["explanation"].get("theory"):
            nested = out.get("subresult")
            if isinstance(nested, dict) and nested.get("header", {}).get("type") in (
                "lesson_fraction_sum",
                "lesson_fraction_product",
            ):
                out["explanation"]["theory"] = theory(
                    "lesson_fraction_sum", normalize_locale(locale)
                )
    # Заголовки шагов — тоже `CoreRichText`, но лежат списком, а не под
    # ключом `description`, поэтому разворачиваются отдельно.
    headers = out.get("headers")
    if isinstance(headers, list):
        out["headers"] = [
            {**h, "explanation": _render_rich(h, locale)}
            if isinstance(h, dict) and "type" in h
            else h
            for h in headers
        ]
    header = out.get("header")
    if isinstance(header, dict) and "type" in header:
        out["header"] = {**header, "explanation": _render_rich(header, locale)}
    # Подпись переключателя способов решения — тоже `CoreRichText`.
    select = out.get("selectMethodText")
    if isinstance(select, dict) and "type" in select:
        out["selectMethodText"] = {**select, "explanation": _render_rich(select, locale)}
    for key in ("children", "substeps", "steps", "entries"):
        value = out.get(key)
        if isinstance(value, list):
            out[key] = [
                attach_text(v, locale, f"{_path}/{key}/{i}") if isinstance(v, dict) else v
                for i, v in enumerate(value)
            ]
    # Вложенные результаты: `result` (группа) и `subresult` (раскрываемое
    # углублённое пояснение шага) — тоже `CoreSolverVerticalResult`.
    for key in ("result", "subresult"):
        nested = out.get(key)
        if isinstance(nested, dict):
            out[key] = attach_text(nested, locale, f"{_path}/{key}")
    return out


# ── операции сервиса ───────────────────────────────────────────────────


_CONSTANT_VARIABLES = frozenset({"e", "π", "pi", "i"})


def _polynomial_equation(node: CoreNode) -> CoreNode | None:
    """Для авто-действия искать нули многочлена с одной переменной."""
    variables = {
        n.value
        for n in node.walk()
        if n.type is T.VARIABLE and n.value and n.value not in _CONSTANT_VARIABLES
    }
    if len(variables) != 1:
        return None
    try:
        polynomial = poly_of(node, next(iter(variables)))
    except SolveError:
        return None
    if not polynomial or not 1 <= max(polynomial) <= 16:
        return None
    return CoreNode.node(T.EQUALS, node, CoreNode.constant("0"))


def parse(source: str) -> dict[str, Any]:
    """Разобрать строку протокола ввода в дерево."""
    return {"node": parse_protocol(source).to_contract()}


def graph(
    node_data: dict[str, Any],
    x_min: float = -10.0,
    x_max: float = 10.0,
    samples: int = DEFAULT_SAMPLES,
) -> dict[str, Any]:
    """Точки графика ``y = f(x)`` для отрисовки на клиенте."""
    return sample_graph(parse_json(node_data), x_min, x_max, samples)


_EXPRESSION_TYPES = frozenset(
    {
        T.ADD,
        T.SUBTRACT,
        T.MULTIPLY,
        T.MULTIPLY_IMPLICIT,
        T.POWER,
        T.FRACTION,
        T.NEGATIVE,
        T.BRACKET,
    }
)


_DERIVATIVE_NODES = (
    T.DERIVATION,
    T.DERIVATION1,
    T.DERIVATION1_DIFF,
    T.PRIME,
    T.DERIVATION1_PRIME,
    T.DERIVATION2_PRIME,
)


def _contains_derivative(node: CoreNode) -> bool:
    """Whether a derivative is written somewhere inside the expression."""
    return any(n.type in _DERIVATIVE_NODES for n in node.walk())


def _is_expression_to_transform(node: CoreNode) -> bool:
    """A bare expression with no equation to solve: several letters, or not a polynomial."""
    if _contains_derivative(node):
        # ``d²/dx²(3x²) − 2x`` is an expression to evaluate, not one to factor:
        # the auto-action works on the sympy value and returned the factored
        # ``−2(x − 3)`` instead of the derivative's ``6 − 2x``.
        return False
    names = {
        n.value
        for n in node.walk()
        if n.type is T.VARIABLE and n.value and n.value not in _CONSTANT_VARIABLES
    }
    if node.type not in _EXPRESSION_TYPES or not names:
        return False
    return len(names) >= 2 or _polynomial_equation(node) is None


def _is_bare_polynomial(node: CoreNode) -> bool:
    """Одночлен/многочлен без равенства: Решатель показывает разложение."""
    if node.type not in _EXPRESSION_TYPES:
        return False
    names = {
        n.value
        for n in node.walk()
        if n.type is T.VARIABLE and n.value and n.value not in _CONSTANT_VARIABLES
    }
    return len(names) == 1 and _polynomial_equation(node) is not None


_FRACTION_CONSTANT = re.compile(r"^(-?)(\d+)/(\d+)$")


def _has_decimal(node: CoreNode) -> bool:
    return any(n.type is T.CONSTANT and "." in (n.value or "") for n in node.walk())


_ROOT_TYPES = frozenset({T.ROOT.value, T.ROOT2.value})


def _has_root(part: Any) -> bool:  # noqa: ANN401
    if isinstance(part, dict):
        return part.get("type") in _ROOT_TYPES or any(_has_root(v) for v in part.values())
    return isinstance(part, list) and any(_has_root(v) for v in part)


def _decimalize(part: Any) -> None:  # noqa: ANN401
    """A problem typed with decimals gets decimals back: ``0.1*0.2`` is 0.02, not 1/50."""
    if isinstance(part, list):
        for item in part:
            _decimalize(item)
    elif isinstance(part, dict):
        if part.get("type") in _ROOT_TYPES or (part.get("type") and _has_root(part)):
            return  # The app keeps (1 − √3)/2 exact for x² − x − 0.5 = 0; ≈ is the alternative
        if part.get("type") == "CONSTANT":
            match = _FRACTION_CONSTANT.match(str(part.get("value") or ""))
            if match:
                sign, top, bottom = match.groups()
                denominator = int(bottom)
                while denominator % 2 == 0:
                    denominator //= 2
                while denominator % 5 == 0:
                    denominator //= 5
                if denominator == 1:
                    value = Fraction(int(top), int(bottom))
                    part["value"] = f"{sign}{float(value):.12g}"
        for item in part.values():
            _decimalize(item)


_COUNTED_OPERATIONS = frozenset(
    {
        T.ADD,
        T.SUBTRACT,
        T.MULTIPLY,
        T.MULTIPLY_IMPLICIT,
        T.DIVIDE,
        T.FRACTION,
        T.POWER,
        T.NEGATIVE,
    }
)


def _operations(node: CoreNode) -> int:
    return sum(1 for n in node.walk() if n.type in _COUNTED_OPERATIONS)


def _is_unsimplified(node: CoreNode) -> bool:
    """A one-letter polynomial that has fewer operations once sympy collects it: ``x^2 x^3``."""
    if _polynomial_equation(node) is None:
        return False
    return bool(sympy.count_ops(to_sympy(node)) < _operations(node))


def _over_a_number(node: CoreNode) -> bool:
    """``(2x+6)/4``: a polynomial divided by a number is cancelled, not solved for zeros."""
    if node.type not in (T.FRACTION, T.DIVIDE) or len(node.children) != 2:
        return False
    top, bottom = node.children

    def has_unknown(part: CoreNode) -> bool:
        return any(m.type is T.VARIABLE for m in part.walk())

    return has_unknown(top) and not has_unknown(bottom) and _polynomial_equation(node) is not None


def _is_bracket_product(node: CoreNode) -> bool:
    """``(2x-3)^3``, ``(x+1)(x+2)(x+3)``: brackets to multiply out, not an equation to solve."""
    if any(n.type is T.MATRIX for n in node.walk()):
        # ``A^(-1)`` is matrix arithmetic with its own cards; translating the matrix
        # power to sympy here would raise a raw error for the whole request.
        return False
    brackets = node.type in (T.MULTIPLY, T.MULTIPLY_IMPLICIT, T.POWER) and any(
        n.type is T.BRACKET for n in node.children
    )
    if contains_imaginary(node) or any(n.type is T.IMAGINARY for n in node.walk()):
        # complex products and squares have their own cards
        return False
    return brackets and sympy.expand(to_sympy(node)) != to_sympy(node)


def _default_command(node: CoreNode) -> CoreAction | None:
    """Expand if that changes it, else factor, else cancel: what a student wants of ``(a+b)^2``."""
    if _contains_derivative(node):
        # The derivative is evaluated by its own card; factoring the evaluated
        # value hides the answer (``6 − 2x`` shown as ``−2(x − 3)``).
        return None
    expression = to_sympy(node)
    if not expression.free_symbols:  # 2(3x-2)-3(2x+3): the letters cancel, a number is left
        return CoreAction(command="simplify")
    if node.type is T.FRACTION and (
        sympy.cancel(expression) != expression or sympy.count_ops(expression) < _operations(node)
    ):
        return CoreAction(command="simplify")
    if sympy.expand(expression) != expression:
        return CoreAction(command="expand")
    if sympy.factor(expression) != expression:
        return CoreAction(command="factor")
    return None  # nothing to do: the solver reports that there is no equation


def _resolve_text_keys(value: object, locale: str) -> object:
    """Развернуть ``TEXT[TEXT_KEY, args]`` в локализованный ``TEXT``.

    Ключи вида ``eq_quad_disc_solution_two`` есть в словаре объяснений; без
    разворота приложение показало бы сам ключ. Разворачиваем только в ответе
    сервиса: ``solve()`` и корпус продолжают работать с контрактным ``TEXT_KEY``.
    """
    if isinstance(value, dict):
        if value.get("type") == "TEXT":
            children = value.get("children") or []
            if children and isinstance(children[0], dict) and children[0].get("type") == "TEXT_KEY":
                key = str(children[0].get("value") or "")
                args = [parse_json(child) for child in children[1:]]
                rendered = explanations().render(key, args, locale)
                if not rendered.missing_key:
                    return {"type": "TEXT", "value": rendered.text}
        return {key: _resolve_text_keys(item, locale) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_text_keys(item, locale) for item in value]
    return value


def solve_request(
    node_data: dict[str, Any],
    action_data: dict[str, Any] | None = None,
    interval_data: dict[str, Any] | None = None,
    locale: str = DEFAULT_LOCALE,
    render: bool = True,
    definitions_data: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Решить выражение и вернуть ответ контракта.

    ``render=True`` дописывает тексты пояснений (ключ ``explanation``).
    ``definitions_data`` — определения функций (``f(x) = …``), которые
    подставляются в решаемое выражение.
    """
    node = parse_json(node_data)
    action = CoreAction.from_contract(action_data) if action_data else None
    interval = None
    if interval_data is not None:
        interval = (parse_json(interval_data["min"]), parse_json(interval_data["max"]))
    definitions = [parse_json(item) for item in (definitions_data or [])]

    shown = expression_cards.methods(node) if action is None else None
    if action is None and shown is None and _is_expression_to_transform(node):
        action = _default_command(node)
    if action is None and shown is None and _is_bare_polynomial(node):
        # Верхний ответ — разложение.
        action = CoreAction(command="factor")
    if action is None and shown is None and _is_bracket_product(node):
        action = CoreAction(command="expand")
    if action is None and shown is None and _over_a_number(node):
        action = CoreAction(command="factor")  # (2x+6)/4 -> (x+3)/2
    if action is None and shown is None and _is_unsimplified(node):
        action = CoreAction(command="simplify")
    # Expanding and cancelling replace the zero search; factoring keeps it (a requested
    # behaviour) and only supplies the rows of the factor group.
    cards = shown[1] if shown is not None else None
    equation = (
        _polynomial_equation(node)
        if cards is None and (action is None or action.command == "solve")
        else None
    )
    data = (
        build_solver_data(
            node,
            cards[0],
            alternatives=cards[1:],
            select_method_text="select_method" if len(cards) > 1 else None,
        )
        if cards
        else solve(
            equation or node,
            command=action.command if action else None,
            args=action.args if action else None,
            interval=interval,
            definitions=definitions,
        )
    )
    if (
        data.result is not None
        and node.type is T.EQUALS
        and data.result.solution is not None
        and contains_imaginary(data.result.solution)
    ):
        # верхний ответ «x ∉ ℝ», комплексные корни — в способах.
        names = sorted({n.value for n in node.walk() if n.type is T.VARIABLE and n.value})
        if names:
            data.result.solution = CoreNode.node(
                T.ELEMENT_NOT_OF,
                CoreNode.variable(names[0]),
                CoreNode.variable("ℝ"),
            )
    if equation is not None:
        # Исходное выражение сохраняется; трактовка «найти нули» видна
        # отдельным первым шагом, а не скрытым добавлением равенства.
        assert data.result is not None
        data.result.problem = node
        axis = sorted({n.value for n in node.walk() if n.type is T.VARIABLE and n.value})[0]
        for entry in data.result.groups[0].entries:
            if entry.result is not None:
                entry.result.setdefault("steps", []).insert(
                    0,
                    {
                        "headers": [],
                        "substeps": [
                            {
                                "description": {
                                    "type": "find_x_intercept",
                                    "args": [CoreNode.variable(axis).to_contract()],
                                },
                                "left": node.to_contract(),
                                "right": equation.to_contract(),
                                "subanimations": [],
                            }
                        ],
                    },
                )
        factored = solve(node, command="factor", definitions=definitions)
        assert factored.result is not None
        factor_rows = (
            shown[1][0].to_contract()
            if shown is not None and shown[0] == "factor"
            else factored.result.groups[0].entries[0].result
        )
        data.result.groups.append(
            CoreSolverGroup(
                type=ResultGroupType.VERTICAL,
                description=CoreRichText(type="factorise_call"),
                entries=[
                    Entry(
                        action=CoreAction(command="factor"),
                        result=factor_rows,
                    )
                ],
            )
        )
    out = data.to_contract()
    result_part = out.get("result")
    forms: list[CoreNode] = []
    if isinstance(result_part, dict) and isinstance(result_part.get("solution"), dict):
        try:
            solution = parse_json(result_part["solution"])
            exact = any(n.type in (T.ROOT, T.ROOT2) for n in solution.walk())
            forms = alternative_forms(solution, typed_decimal=_has_decimal(node) and not exact)
        except Exception:  # the extra forms are optional, the answer must still come
            forms = []
    if _has_decimal(node):
        _decimalize(out)
    if forms and isinstance(result_part, dict):
        result_part["alternativeForms"] = [form.to_contract() for form in forms]
    if render:
        result = out.get("result")
        groups = result.get("groups") if isinstance(result, dict) else None
        if isinstance(groups, list):
            for index, group in enumerate(groups):
                if isinstance(group, dict):
                    groups[index] = attach_text(group, locale, f"solution/groups/{index}")
    return cast(dict[str, Any], _resolve_text_keys(out, locale))


__all__ = [
    "SUPPORTED_LOCALES",
    "attach_text",
    "explanations",
    "explanations_loaded",
    "explanations_path",
    "graph",
    "health",
    "normalize_locale",
    "parse",
    "solve_request",
]
