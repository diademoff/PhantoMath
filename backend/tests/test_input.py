"""Тесты разбора протокола Photomath.

Формат восстановлен в truth/08-input-protocol.md. Тесты сверяются с реальными
примерами структуры, а не с выдуманными: порядок аргументов и типы узлов
должны совпадать с тем, что ожидает нативный парсер.
"""

from __future__ import annotations

import pytest

from mymath_backend.ast import CoreNodeType
from mymath_backend.ast import CoreNodeType as T
from mymath_backend.input import ProtocolError, parse_json, parse_protocol


class TestLiterals:
    def test_number(self) -> None:
        node = parse_protocol("{42}")
        assert node.type is T.CONSTANT
        assert node.value == "42"

    def test_decimal(self) -> None:
        assert parse_protocol("{3.14}").value == "3.14"

    def test_variable(self) -> None:
        node = parse_protocol("{x}")
        assert node.type is T.VARIABLE
        assert node.value == "x"

    def test_empty_group(self) -> None:
        assert parse_protocol("{}").type is T.EMPTY


class TestEquations:
    def test_simple_equation(self) -> None:
        """{=({2x+3},{7})} — вершина EQUALS с двумя строками."""
        node = parse_protocol("{=({2x+3},{7})}")
        assert node.type is T.EQUALS
        assert len(node.children) == 2
        left, right = node.children
        assert left.type is T.ADD
        assert [c.type for c in left.children] == [T.MULTIPLY_IMPLICIT, T.CONSTANT]
        assert right.type is T.CONSTANT
        assert right.value == "7"

    def test_implicit_multiplication(self) -> None:
        """`2x` — число вплотную к имени; Photomath хранит это отдельно."""
        node = parse_protocol("{=({2x+3},{7})}").children[0]
        mul = node.children[0]
        assert mul.type is T.MULTIPLY_IMPLICIT
        assert mul.children[0].value == "2"
        assert mul.children[1].value == "x"

    def test_explicit_multiplication_keeps_operator(self) -> None:
        """`2*x` — знак на месте, тип остаётся MULTIPLY."""
        node = parse_protocol("{2*x}")
        assert node.type is T.MULTIPLY
        assert [c.value for c in node.children] == ["2", "x"]

    def test_implicit_multiplication_of_three_factors(self) -> None:
        """`2xy` — три множителя; порядок ассоциации не влияет на смысл."""
        node = parse_protocol("{2xy}")
        leaves = [n.value for n in node.find_all(T.CONSTANT) + node.find_all(T.VARIABLE)]
        assert leaves == ["2", "x", "y"]

    def test_system(self) -> None:
        source = " system({=({x+1},{3})},{=({x-1},{1})}) "
        node = parse_protocol(source)
        assert node.type is T.SYSTEM
        assert len(node.children) == 2
        assert all(c.type is T.EQUALS for c in node.children)
        assert node.children[1].children[1].value == "1"

    def test_whitespace_is_ignored(self) -> None:
        with_spaces = parse_protocol("  { = ( { 2 x + 3 } , { 7 } ) }  ")
        assert with_spaces.type is T.EQUALS


class TestKeywords:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("{sin({x})}", T.SIN),
            ("{log({x},{10})}", T.LOG),
            ("{frac({1},{2})}", T.FRACTION),
            ("{root({2},{8})}", T.ROOT),
            ("{root2({9})}", T.ROOT2),
            ("{abs({-x})}", T.ABS),
            ("{integral({1},{0},{x})}", T.INTEGRAL),
            ("{derivation({x})}", T.DERIVATION),
            ("{lim({x},{0})}", T.LIMIT),
            ("{definitesigma({1},{1},{n})}", T.SIGMA_DEFINITE),
            ("{choose({n},{2})}", T.CHOOSE),
            ("{factorial({5})}", T.FACTORIAL),
            ("{pow({2},{10})}", T.POWER),
        ],
    )
    def test_keyword_maps_to_node_type(self, source: str, expected: CoreNodeType) -> None:
        assert parse_protocol(source).type is expected

    def test_argument_count_preserved(self) -> None:
        node = parse_protocol("{frac({1},{2})}")
        assert len(node.children) == 2
        assert node.children[0].value == "1"
        assert node.children[1].value == "2"

    @pytest.mark.parametrize(
        ("symbol", "expected"),
        [
            ("+", T.ADD),
            ("-", T.SUBTRACT),
            ("*", T.MULTIPLY),
            ("/", T.DIVIDE),
            ("<=", T.LESS_THAN_EQUAL),
            (">=", T.GREATER_THAN_EQUAL),
            ("!=", T.NOT_EQUALS),
            ("^", T.POWER),
        ],
    )
    def test_symbol_table(self, symbol: str, expected: CoreNodeType) -> None:
        assert parse_protocol(f"{{2{symbol}3}}").type is expected

    def test_bare_sign_without_operand_is_error(self) -> None:
        with pytest.raises(ProtocolError, match="ожидался операнд"):
            parse_protocol("{-}")

    def test_letters_become_implicit_product(self) -> None:
        """Переменные однобуквенные: `xy` — это x·y, а не имя."""
        node = parse_protocol("{xy}")
        assert node.type is T.MULTIPLY_IMPLICIT
        assert [c.value for c in node.children] == ["x", "y"]

    def test_function_call_is_not_split(self) -> None:
        """`sin(` — вызов: много букв не значит произведение."""
        assert parse_protocol("{sin({x})}").type is T.SIN


class TestConstantsAndUnits:
    """Константы и обёртки: π, ∞, мнимая единица, единицы угла, комплексные."""

    @pytest.mark.parametrize("source", ["{pi}", "{\\pi}", "{π}"])
    def test_pi_is_constant(self, source: str) -> None:
        node = parse_protocol(source)
        assert node.type is T.CONSTANT
        assert node.value == "π"

    def test_number_times_pi(self) -> None:
        r"""`2\pi` — неявное умножение числа на константу."""
        node = parse_protocol("{2\\pi}")
        assert node.type is T.MULTIPLY_IMPLICIT
        assert [c.value for c in node.children] == ["2", "π"]

    @pytest.mark.parametrize("source", ["{infty}", "{\\infty}", "{∞}"])
    def test_infinity_is_constant(self, source: str) -> None:
        node = parse_protocol(source)
        assert node.type is T.CONSTANT
        assert node.value == "∞"

    def test_imaginary_unit_is_constant(self) -> None:
        r"""Мнимая единица — явный токен `\i` (CONSTANT_I в редакторе)."""
        node = parse_protocol("{\\i}")
        assert node.type is T.CONSTANT
        assert node.value == "i"

    def test_plain_i_stays_variable(self) -> None:
        node = parse_protocol("{i}")
        assert node.type is T.VARIABLE
        assert node.value == "i"

    def test_euler_number_is_constant(self) -> None:
        r"""Число Эйлера — явный токен `\e` (CONSTANT_E в редакторе)."""
        node = parse_protocol("{\\e}")
        assert node.type is T.CONSTANT
        assert node.value == "e"

    def test_plain_e_stays_variable(self) -> None:
        node = parse_protocol("{e}")
        assert node.type is T.VARIABLE
        assert node.value == "e"

    def test_natural_log_of_e(self) -> None:
        node = parse_protocol("{ln({\\e})}")
        assert node.type is T.LN
        assert node.children[0].type is T.CONSTANT
        assert node.children[0].value == "e"

    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("{deg({30})}", T.DEGREE),
            ("{radian({1})}", T.RADIAN),
            ("{real({1})}", T.REAL),
            ("{imag({1})}", T.IMAGINARY),
            ("{conj({1})}", T.CONJUGATE),
        ],
    )
    def test_wrapper_keywords(self, source: str, expected: CoreNodeType) -> None:
        assert parse_protocol(source).type is expected

    def test_degrees_inside_sine(self) -> None:
        node = parse_protocol("{sin({deg({30})})}")
        assert node.type is T.SIN
        assert node.children[0].type is T.DEGREE
        assert node.children[0].children[0].value == "30"


class TestErrors:
    def test_unknown_operator(self) -> None:
        with pytest.raises(ProtocolError, match="неизвестный оператор"):
            parse_protocol("{nonsense({x})}")

    def test_unclosed_brace(self) -> None:
        with pytest.raises(ProtocolError, match="строка кончилась"):
            parse_protocol("{=({x}")

    def test_unclosed_group(self) -> None:
        with pytest.raises(ProtocolError, match="не закрыта"):
            parse_protocol("{=({x},{1})")

    def test_trailing_garbage(self) -> None:
        with pytest.raises(ProtocolError, match="неожиданный хвост"):
            parse_protocol("{x} {y}")

    def test_empty_source(self) -> None:
        with pytest.raises(ProtocolError, match="пустая строка"):
            parse_protocol("   ")

    def test_garbage_token(self) -> None:
        with pytest.raises(ProtocolError, match="не удалось разобрать токен"):
            parse_protocol("{@}")

    def test_error_carries_position(self) -> None:
        with pytest.raises(ProtocolError) as err:
            parse_protocol("{=({2x+3},{7})} tail")
        assert "поз." in str(err.value)

    def test_deep_nesting_is_protocol_error(self) -> None:
        """600 скобок — ProtocolError, а не RecursionError наружу."""
        with pytest.raises(ProtocolError, match="глубокая"):
            parse_protocol("{" + "(" * 600 + "2+3" + ")" * 600 + "}")


class TestJsonInput:
    def test_same_tree_from_both_formats(self) -> None:
        """Протокол и AST-JSON обязаны давать одинаковое дерево."""
        from_protocol = parse_protocol("{=({2x+3},{7})}")
        from_json = parse_json(
            {
                "type": "EQUALS",
                "children": [
                    {
                        "type": "ADD",
                        "children": [
                            {
                                "type": "MULTIPLY_IMPLICIT",
                                "children": [
                                    {"type": "CONSTANT", "value": "2"},
                                    {"type": "VARIABLE", "value": "x"},
                                ],
                            },
                            {"type": "CONSTANT", "value": "3"},
                        ],
                    },
                    {"type": "CONSTANT", "value": "7"},
                ],
            }
        )
        assert from_json.structural_eq(from_protocol)

    def test_json_rejects_unknown_type(self) -> None:
        with pytest.raises(ValueError):
            parse_json({"type": "НЕТ_ТАКОГО", "value": "1"})


class TestUnaryMinus:
    def test_minus_binds_weaker_than_power(self) -> None:
        """-x^2 = -(x^2), а не (-x)^2."""
        node = parse_protocol("{-x^2}")
        assert node.type is T.NEGATIVE
        assert node.children[0].type is T.POWER

    def test_minus_in_exponent(self) -> None:
        """2^-x — знак в показателе."""
        node = parse_protocol("{2^-x}")
        assert node.type is T.POWER
        assert node.children[1].type is T.NEGATIVE

    def test_minus_before_product(self) -> None:
        node = parse_protocol("{-x*y}")
        assert node.type is T.MULTIPLY
        assert node.children[0].type is T.NEGATIVE
