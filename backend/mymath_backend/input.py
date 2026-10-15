"""Приём выражения: инфиксный протокол Photomath и AST-JSON.

Два входных формата:

``parse_protocol``
    Строка, которую Photomath передаёт в ``nativeProcessExpression``.
    Восстановлена в ``truth/08-input-protocol.md``; это S-выражение, где
    строка (строка ввода) оборачивается в фигурные скобки, а вершина с
    аргументами записывается как ``имя({арг1},{арг2})``::

        {=({2x+3},{7})}                  2x + 3 = 7
         system({=({x+1},{3})},…)        система уравнений

``CoreNode.from_contract``
    AST-JSON в формате контракта — то, что приходит от нашего фронта.

Оба входа дают один и тот же :class:`~mymath_backend.ast.CoreNode`, дальше
работает решатель.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .ast import CoreNode
from .node_types import CoreNodeType
from .node_types import CoreNodeType as T

# ── Сопоставление словаря протокола с CoreNodeType ──────────────────────
# Ключи взяты из таблицы литералов парсера в libPhotoMathDist.so
# (truth/data/input-protocol.json). Значения — имена из CoreNodeType.
KEYWORD_TO_TYPE: dict[str, CoreNodeType] = {
    # арифметика и знаки
    "add": T.ADD,
    "add_sub": T.ADD_SUBTRACT,
    "add_sub_sign": T.ADD_SUBTRACT_SIGN,
    "sub": T.SUBTRACT,
    "mul": T.MULTIPLY,
    "muli": T.MULTIPLY_IMPLICIT,
    "div": T.DIVIDE,
    "neg": T.NEGATIVE,
    "pos": T.POSITIVE,
    "pow": T.POWER,
    "factorial": T.FACTORIAL,
    "percent": T.PERCENTAGE,
    "periodic": T.PERIODIC,
    "frac": T.FRACTION,
    "mfrac": T.FRACTION_MIXED,
    "root": T.ROOT,
    "root2": T.ROOT2,
    "rooti": T.ROOT2,
    "radicand": T.ROOT,
    # сравнение
    "eq": T.EQUALS,
    "neq": T.NOT_EQUALS,
    "lt": T.LESS_THAN,
    "lte": T.LESS_THAN_EQUAL,
    "gt": T.GREATER_THAN,
    "gte": T.GREATER_THAN_EQUAL,
    "approx": T.APPROXIMATE,
    "approx_sign": T.APPROXIMATE_SIGN,
    # функции
    "abs": T.ABS,
    "sin": T.SIN,
    "cos": T.COS,
    "tan": T.TAN,
    "cot": T.COT,
    "sec": T.SEC,
    "csc": T.CSC,
    "asin": T.ASIN,
    "acos": T.ACOS,
    "atan": T.ATAN,
    "acot": T.ACOT,
    "asec": T.ASEC,
    "acsc": T.ACSC,
    "sinh": T.SINH,
    "cosh": T.COSH,
    "tanh": T.TANH,
    "coth": T.COTH,
    "sech": T.SECH,
    "csch": T.CSCH,
    "asinh": T.ASINH,
    "acosh": T.ACOSH,
    "atanh": T.ATANH,
    "acoth": T.ACOTH,
    "asech": T.ASECH,
    "acsch": T.ACSCH,
    "log": T.LOG,
    "log10": T.LOG10,
    "ln": T.LN,
    "exp": T.EXP,
    "floor": T.FLOOR,
    "ceil": T.FLOOR,
    "gcd": T.ABS,
    "lcm": T.ABS,
    # единицы угла и комплексные -- постфиксные обёртки (1 ребёнок)
    "deg": T.DEGREE,
    "deg_min": T.DEGREE_MINUTE,
    "deg_min_sec": T.DEGREE_MINUTE_SECOND,
    "radian": T.RADIAN,
    "real": T.REAL,
    "imag": T.IMAGINARY,
    "conj": T.CONJUGATE,
    # исчисления
    "lim": T.LIMIT,
    "lim_left": T.LIMIT_LEFT,
    "lim_right": T.LIMIT_RIGHT,
    "lim_both": T.LIMIT,
    "integral": T.INTEGRAL,
    "integral_def": T.INTEGRAL_DEFINITE,
    "definiteintegral": T.INTEGRAL_DEFINITE,
    "derivation": T.DERIVATION,
    "derivation_prime": T.DERIVATION1,
    "derivation2_prime": T.DERIVATION2_PRIME,
    "derivation_diff": T.DERIVATION1_DIFF,
    "nderivation_diff": T.DERIVATION_DIFF,
    "nderivation": T.DERIVATION,
    "sigma_def": T.SIGMA_DEFINITE,
    "definitesigma": T.SIGMA_DEFINITE,
    "differential": T.DIFFERENTIAL,
    # комбинаторика
    "choose": T.CHOOSE,
    "choose_lsub_rsub": T.CHOOSE_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT,
    "permutation": T.PARTIAL_PERMUTATION_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT,
    "partial_permutation_lsub_rsub": T.PARTIAL_PERMUTATION_LEFT_SUBSCRIPT_RIGHT_SUBSCRIPT,
    "variation": T.VARIATION,
    # промежутки: «o» — открытый край, «c» — закрытый, порядок «слева-справа»
    "ooint": T.OPEN_OPEN_INTERVAL,
    "ocint": T.OPEN_CLOSED_INTERVAL,
    "coint": T.CLOSED_OPEN_INTERVAL,
    "ccint": T.CLOSED_CLOSED_INTERVAL,
    # столбиковые вычисления: токенов в нативном парсере нет — синтаксис наш
    "vert_add": T.VERTICAL_ADD,
    "vert_sub": T.VERTICAL_SUBTRACT,
    "vert_mul": T.VERTICAL_MULTIPLY,
    "horiz_mul": T.HORIZONTAL_MULTIPLY,
    "vert_div": T.VERTICAL_DIVIDE,
    "us_longdiv": T.US_LONGDIV,
    "ru_longdiv": T.RU_LONGDIV,
    # структуры
    "system": T.SYSTEM,
    "mat": T.MATRIX,
    "mat_s": T.MATRIX_SPLIT_LAST,
    "mat_row": T.MATRIX_ROW,
    "det": T.DETERMINANT,
    "det2": T.DETERMINANT2,
    "det3": T.DETERMINANT3,
    "det3s": T.DETERMINANT3_SARRUS,
    "det4": T.DETERMINANT4,
    "det5": T.DETERMINANT5,
    "set": T.SET,
    "list": T.LIST,
    "vert_list": T.VERTICAL_LIST,
    "sequence": T.SEQUENCE,
    "union": T.UNION,
    # Словарь протокола даёт `intsec`; `intersection` оставлен читаемым алиасом.
    "intsec": T.INTERSECTION,
    "intersection": T.INTERSECTION,
    # Отношения множеств: токенов в протоколе нет, имена наши (страница ввода).
    "elem_of": T.ELEMENT_OF,
    "elem_not_of": T.ELEMENT_NOT_OF,
    "setminus": T.DIFFERENCE,
    "subseteq": T.SUBSET_OR_EQUALS,
    "subset": T.PROPER_SUBSET,
    "nsubset": T.NOT_PROPER_SUBSET,
    "supseteq": T.SUPERSET_OR_EQUALS,
    "supset": T.PROPER_SUPERSET,
    "nsupset": T.NOT_PROPER_SUPERSET,
    "function": T.FUNCTION,
    "order": T.ORDER,
    "evaluate_expr": T.EVALUATE_EXPRESSION,
    "cond_expr": T.CONDITIONAL_EXPRESSION,
    "diff": T.DERIVATION,
    "sign": T.SIGN,
    "prime": T.PRIME,
    "no_reduce": T.APPROXIMATE,
}

# Знаки, которые парсер отдаёт отдельными токенами. Скобки сюда не входят:
# они задают структуру и разбираются в parse_bracket, а не как оператор.
SYMBOL_TO_TYPE: dict[str, CoreNodeType] = {
    "+": T.ADD,
    "-": T.SUBTRACT,
    "*": T.MULTIPLY,
    "/": T.DIVIDE,
    "=": T.EQUALS,
    "<": T.LESS_THAN,
    "<=": T.LESS_THAN_EQUAL,
    ">": T.GREATER_THAN,
    ">=": T.GREATER_THAN_EQUAL,
    "!=": T.NOT_EQUALS,
    "^": T.POWER,
}

NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
GREEK_RE = re.compile(r"^\\[a-zA-Z]+$")
IDENT_RE = re.compile(r"^[A-Za-zΑ-Ωα-ω][A-Za-z0-9Α-Ωα-ω]*$")

# Имена, которые протокол трактует как математические константы, а не буквы.
# ``pi``/``\pi`` -- число π, ``inf``/``infty``/``\infty`` -- бесконечность.
# Словарь проверяется раньше разбиения много-буквенного токена на переменные:
# иначе ``pi`` распалось бы на ``p·i``, а ``infty`` -- на ``i·n·f·t·y``.
CONSTANT_NAMES: dict[str, str] = {
    "π": "π",
    "pi": "π",
    "\\pi": "π",
    "∞": "∞",
    "inf": "∞",
    "infty": "∞",
    "\\infty": "∞",
    # Мнимая единица: в редакторе Photomath это отдельный оператор CONSTANT_I,
    # а в контракте — CONSTANT "i". Явный токен «\i», чтобы буква i осталась
    # переменной (решение пользователя).
    "\\i": "i",
    # Число Эйлера — оператор CONSTANT_E. Явный токен «\e» по той же причине:
    # буква e остаётся переменной.
    "\\e": "e",
}

# Знаки, которые разрывают имя токена. `_` сюда намеренно не входит:
# переменные с индексами пишутся как `a_1` и должны остаться одним токеном.
OPERATOR_CHARS = frozenset("+-*/=<>!^")
TWO_CHAR_OPERATORS = ("<=", ">=", "!=")
# `2x`, `2xy`, `2\pi`, `3(…)` — число вплотную к имени, константе или скобке.
IMPLICIT_MUL_RE = re.compile(r"^(\d+(?:\.\d+)?|\.\d+)([A-Za-zΑ-Ωα-ω\\(].*)$")


class ProtocolError(ValueError):
    """Строка не разбирается протоколом Photomath.

    В сообщении указывается позиция: у протокола нет номеров строк, поэтому
    иначе ошибку в длинной строке не найти.
    """


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str  # "{" | "}" | "," | "name" | "text"
    value: str
    pos: int


def _tokenize(source: str) -> list[_Token]:
    """Разбить строку на токены.

    Разделители структуры — фигурные скобки, запятая и круглые скобки.
    Внутри группы токены идут подряд и образуют инфиксную запись, поэтому
    ``2x+3`` должен распасться на ``2``, ``x``, ``+``, ``3``, а не остаться
    одним куском. Двухзначные знаки проверяются раньше однозначных.
    """
    tokens: list[_Token] = []
    i, n = 0, len(source)
    while i < n:
        ch = source[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "{},()":
            tokens.append(_Token(ch, ch, i))
            i += 1
            continue
        if source[i : i + 2] in TWO_CHAR_OPERATORS:
            tokens.append(_Token("name", source[i : i + 2], i))
            i += 2
            continue
        if ch in OPERATOR_CHARS:
            tokens.append(_Token("name", ch, i))
            i += 1
            continue
        j = i
        while (
            j < n
            and not source[j].isspace()
            and source[j] not in "{},()"
            and source[j] not in OPERATOR_CHARS
        ):
            j += 1
        if j == i:  # недостижимо при текущем наборе, но защищает от зацикливания
            raise ProtocolError(f"поз. {i}: не удалось выделить токен")
        chunk = source[i:j]
        implicit = IMPLICIT_MUL_RE.match(chunk)
        if implicit:
            # `2x` — число вплотную к имени: неявное умножение, отдельный токен.
            tokens.append(_Token("name", implicit.group(1), i))
            tokens.append(_Token("name", implicit.group(2), i + implicit.end(1)))
        else:
            tokens.append(_Token("name", chunk, i))
        i = j
    return tokens


class _Parser:
    """Рекурсивный спуск по токенам.

    Грамматика::

        expression := group | "system" "(" group ("," group)+ ")"
        group       := "{" ( name | group )* "}"
        name        := token [ "(" group ("," group)* ")" ]
    """

    def __init__(self, tokens: list[_Token]) -> None:
        self.tokens = tokens
        self.i = 0

    def peek(self) -> _Token | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self) -> _Token:
        tok = self.peek()
        if tok is None:
            raise ProtocolError("неожиданный конец строки")
        self.i += 1
        return tok

    def expect(self, value: str) -> _Token:
        tok = self.peek()
        if tok is None:
            raise ProtocolError(f"ожидалось {value!r}, но строка кончилась")
        self.take()
        if tok.value != value:
            raise ProtocolError(f"поз. {tok.pos}: ожидалось {value!r}, получено {tok.value!r}")
        return tok

    # -- правила -------------------------------------------------------

    def parse_expression(self) -> CoreNode:
        tok = self.peek()
        if tok is None:
            raise ProtocolError("пустая строка")
        if tok.value == "system":
            return self.parse_system()
        if tok.value != "{":
            raise ProtocolError(
                f"поз. {tok.pos}: выражение должно начинаться с '{{' "
                f"или с 'system(', получено {tok.value!r}"
            )
        return self.parse_group()

    def parse_system(self) -> CoreNode:
        self.take()  # 'system'
        self.expect("(")
        rows: list[CoreNode] = [self.parse_group()]
        while (tok := self.peek()) and tok.value == ",":
            self.take()
            rows.append(self.parse_group())
        self.expect(")")
        return CoreNode(type=T.SYSTEM, children=rows)

    def parse_group(self) -> CoreNode:
        """Разобрать ``{…}`` в один узел.

        Внутри группы токены идут подряд, без разделителей: они образуют
        инфиксную запись вида ``2x+3``. Знак внутри группы -- оператор между
        операндами, а не операнд. Два операнда подряд без знака -- неявное
        умножение: именно так приходит ``2x`` в ``2x+3``, и важно не склеить
        ``x`` с ``3`` через ``+``.
        """
        open_tok = self.expect("{")
        items = self._collect_items("}", open_tok)
        return _items_to_node(items, empty=CoreNode.empty())

    def _collect_items(self, terminator: str, open_tok: _Token) -> list[CoreNode | str]:
        """Собрать чередующийся список операндов и знаков до терминатора."""
        items: list[CoreNode | str] = []
        while True:
            tok = self.peek()
            if tok is None:
                raise ProtocolError(f"поз. {open_tok.pos}: не закрыта {open_tok.value!r}")
            if tok.value == terminator:
                self.take()
                return items
            if self._is_bare_sign(tok):
                self.take()
                items.append(tok.value)
                continue
            if tok.value == "(":
                items.append(self._parse_paren(items))
                continue
            if tok.value in CONSTANT_NAMES:
                self.take()
                if items and isinstance(items[-1], CoreNode):
                    items.append(IMPLICIT_MUL)
                items.append(CoreNode.constant(CONSTANT_NAMES[tok.value]))
                continue
            letters = self._take_split_identifier(tok)
            if letters is not None:
                for letter in letters:
                    if items and isinstance(items[-1], CoreNode):
                        items.append(IMPLICIT_MUL)
                    items.append(CoreNode.variable(letter))
                continue
            part = self.parse_name()
            if items and isinstance(items[-1], CoreNode):
                items.append(IMPLICIT_MUL)
            items.append(part)

    def _is_bare_sign(self, tok: _Token) -> bool:
        """Знак -- разделитель операндов, а не операнд.

        Вызов функции в протоколе записывается именем: ``sin({x})``. Знак перед
        скобкой -- это умножение на скобку: ``2*(3+4)``. Поэтому знаки не
        различаются по следующему токену.
        """
        return tok.value in SYMBOL_TO_TYPE

    def _take_split_identifier(self, tok: _Token) -> list[str] | None:
        r"""Разбить много-letter идентификатор на отдельные переменные.

        В Photomath переменные однобуквенные (``VARIABLE_A_LOW`` … ``VARIABLE_W_LOW``
        плюс греческие). Поэтому ``xy`` -- это не имя, а произведение ``x·y``.
        Много-letter токен оставляем целым, если за ним идёт ``(`` (это вызов
        функции вроде ``sin``) или он начинается с обратной косой черты
        (команда LaTeX вроде ``\\alpha``).
        """
        if not IDENT_RE.match(tok.value) or len(tok.value) < 2:
            return None
        nxt = self.tokens[self.i + 1] if self.i + 1 < len(self.tokens) else None
        if nxt is not None and nxt.value == "(":
            return None
        self.take()
        return list(tok.value)

    def _parse_paren(self, items: list[CoreNode | str]) -> CoreNode:
        """Разобрать ``( … )``.

        Круглые скобки несут два разных смысла, и смысл определяет то,
        что стояло перед ними:

        - после **знака отношения** (``=``, ``<``, …) -- список аргументов:
          ``=({2x+3},{7})``. Знак отношения не бывает инфиксным перед
          скобкой, поэтому двусмысленности нет;
        - после **арифметического** знака -- группировка, если внутри не
          фигурные скобки: ``2*(3+4)``; список аргументов, если скобки
          внутри есть: ``2*({3+4})``;
        - после операнда -- всегда группировка.
        """
        last = items[-1] if items else None
        nxt = self.tokens[self.i + 1] if self.i + 1 < len(self.tokens) else None
        if isinstance(last, str) and last in _PRECEDENCE:
            if last in _RELATIONAL:
                # Знак поглощается списком операндов: он уже не разделитель.
                items.pop()
                return self._parse_operand_list(last)
            if nxt is not None and nxt.value == "{":
                raise ProtocolError(
                    f"поз. {nxt.pos}: список операндов через фигурные скобки "
                    f"допустим только для знаков отношения, а не для {last!r}; "
                    f"скобки группировки пишутся круглыми: ({last}(…))"
                )
        return self.parse_bracket()

    def _parse_operand_list(self, sign: str) -> CoreNode:
        """Разобрать список операндов бинарного оператора ``sign( … , … )``."""
        self.take()  # '('
        args = [self.parse_group()]
        while (tok := self.peek()) and tok.value == ",":
            self.take()
            args.append(self.parse_group())
        self.expect(")")
        return CoreNode(type=_operator_type(sign), children=args)

    def parse_bracket(self) -> CoreNode:
        """Разобрать ``( … )`` как узел ``BRACKET``.

        В отличие от аргументов вершины, скобки содержат строку без фигурных
        скобок: ``2*(3+4)`` -- умножение на результат скобок. Отдельный тип
        ``BRACKET`` позволяет решателю сохранить скобки при копировании.
        """
        open_tok = self.take()
        items = self._collect_items(")", open_tok)
        inner = _items_to_node(items, empty=CoreNode.empty())
        return CoreNode(type=T.BRACKET, children=[inner])

    def parse_name(self) -> CoreNode:
        """Разобрать ``имя`` или ``имя({арг},{арг})``."""
        tok = self.take()
        if tok.kind != "name":
            raise ProtocolError(f"поз. {tok.pos}: ожидалось имя, получено {tok.value!r}")

        nxt = self.peek()
        has_args = nxt is not None and nxt.value == "("
        if has_args:
            self.take()
            args: list[CoreNode] = [self.parse_group()]
            while (a := self.peek()) and a.value == ",":
                self.take()
                args.append(self.parse_group())
            self.expect(")")
            return CoreNode(type=_resolve_type(tok.value), children=args)

        if tok.value in SYMBOL_TO_TYPE:
            return CoreNode(type=SYMBOL_TO_TYPE[tok.value], value=tok.value)
        return _leaf(tok.value, tok.pos)


def _resolve_type(name: str) -> CoreNodeType:
    """Тип узла по имени из словаря протокола."""
    if name in KEYWORD_TO_TYPE:
        return KEYWORD_TO_TYPE[name]
    if name in SYMBOL_TO_TYPE:
        return SYMBOL_TO_TYPE[name]
    raise ProtocolError(f"неизвестный оператор {name!r}")


# Приоритеты бинарных операторов, от слабого к сильному. Рядом с `*` стоит
# неявное умножение: в Photomath оно самостоятельный тип MULTIPLY_IMPLICIT,
# но связывает так же, как явный знак. `^` правоассоциативен.
_PRECEDENCE: dict[str, int] = {
    "=": 1,
    "<": 1,
    "<=": 1,
    ">": 1,
    ">=": 1,
    "!=": 1,
    "+": 2,
    "-": 2,
    "*": 3,
    "/": 3,
    "·": 4,  # неявное умножение
    "^": 5,
}
IMPLICIT_MUL = "·"
# Знаки отношения: в протоколе они всегда записываются со списком операндов
# в скобках, поэтому ``(`` после них однозначно означает аргументы.
_RELATIONAL = frozenset({"=", "<", "<=", ">", ">=", "!="})
_UNARY_PRECEDENCE = 4


def _items_to_node(items: list[CoreNode | str], empty: CoreNode) -> CoreNode:
    """Превратить собранные операнды и знаки в узел.

    Пустая группа даёт ``empty`` -- так помечается незаполненный слот.
    """
    if not items:
        return empty
    if len(items) == 1 and isinstance(items[0], CoreNode):
        return items[0]
    return _build_infix(items)


def _build_infix(items: list[CoreNode | str]) -> CoreNode:
    """Разбор по приоритетам (precedence climbing).

    ``items`` -- чередующийся список операндов и операторов; курсор один
    на оба, иначе разъезжаются позиции операндов и знаков.
    """
    pos = 0

    def parse_unary() -> CoreNode:
        nonlocal pos
        if pos + 1 < len(items) and items[pos] in ("-", "+"):
            op = items[pos]
            pos += 1
            # Унарный знак слабее степени: -x^2 = -(x^2), а не (-x)^2.
            operand = parse(_PRECEDENCE["^"])
            node_type = T.NEGATIVE if op == "-" else T.POSITIVE
            return CoreNode(type=node_type, children=[operand])
        if pos >= len(items) or isinstance(items[pos], str):
            raise ProtocolError(f"ожидался операнд, получено {items[pos : pos + 1]}")
        node = items[pos]
        assert isinstance(node, CoreNode)
        pos += 1
        return node

    def parse(min_prec: int) -> CoreNode:
        nonlocal pos
        left = parse_unary()
        while pos < len(items) and not isinstance(items[pos], CoreNode):
            op = items[pos]
            assert isinstance(op, str)
            prec = _PRECEDENCE[op]
            if prec < min_prec:
                break
            pos += 1
            # `^` правоассоциативен: 2^3^2 = 2^(3^2).
            right = parse(prec if op == "^" else prec + 1)
            left = CoreNode(type=_operator_type(op), children=[left, right])
        return left

    result = parse(1)
    if pos != len(items):
        raise ProtocolError(f"не разобрано выражение начиная с {items[pos:]!r}")
    return result


def _operator_type(op: str) -> CoreNodeType:
    """Тип узла для оператора инфиксной записи."""
    if op == IMPLICIT_MUL:
        return T.MULTIPLY_IMPLICIT
    node_type = SYMBOL_TO_TYPE.get(op)
    if node_type is None:
        raise ProtocolError(f"неизвестный оператор {op!r}")
    return node_type


def _leaf(text: str, pos: int) -> CoreNode:
    """Лист: число, переменная, константа или текст."""
    if NUMBER_RE.match(text):
        return CoreNode.constant(text)
    if text in CONSTANT_NAMES:
        # π и бесконечность -- константы. Проверяются раньше IDENT_RE, иначе
        # ``pi`` стало бы переменной, а ``\pi`` -- переменной с именем «\pi».
        return CoreNode.constant(CONSTANT_NAMES[text])
    if text in KEYWORD_TO_TYPE and text not in SYMBOL_TO_TYPE:
        # Имя функции без скобок: «забыли скобки» — трактуем как вызов с
        # пустым аргументом, чтобы не потерять узел молча.
        return CoreNode(type=KEYWORD_TO_TYPE[text], value=None)
    if IDENT_RE.match(text) or GREEK_RE.match(text):
        return CoreNode.variable(text)
    raise ProtocolError(f"поз. {pos}: не удалось разобрать токен {text!r}")


def parse_protocol(source: str) -> CoreNode:
    """Разобрать строку протокола Photomath в дерево узлов.

    >>> parse_protocol("{=({2x+3},{7})}").type.value
    'EQUALS'
    """
    tokens = _tokenize(source)
    if not tokens:
        raise ProtocolError("пустая строка")
    parser = _Parser(tokens)
    node = parser.parse_expression()
    if (leftover := parser.peek()) is not None:
        raise ProtocolError(
            f"поз. {leftover.pos}: неожиданный хвост {leftover.value!r} после разбора выражения"
        )
    return node


def parse_json(data: dict[str, object]) -> CoreNode:
    """Разобрать AST-JSON формата контракта.

    Тонкая обёртка над :meth:`CoreNode.from_contract`: контракт допускает
    поля ``color`` и ``crossed``, которые поднимают узел до
    ``CoreColoredNode``, и мы их сохраняем.
    """
    return CoreNode.from_contract(data)


__all__ = [
    "IDENT_RE",
    "KEYWORD_TO_TYPE",
    "NUMBER_RE",
    "SYMBOL_TO_TYPE",
    "ProtocolError",
    "parse_json",
    "parse_protocol",
]
