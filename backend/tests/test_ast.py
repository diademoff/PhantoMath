"""Тесты типов AST и сериализации в формат контракта.

Проверяем не только внутреннюю согласованность, но и то, что названия полей
и значения совпадают с разбором оригинала (truth/03-solver-contract.md).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mymath_backend import CoreColoredNode, CoreNode, CoreNodeType, is_known_type

TRUTH = Path(__file__).resolve().parents[2] / "truth" / "data"


class TestNodeTypes:
    def test_matches_apsk_enumeration(self) -> None:
        """143 значения и порядок совпадают с разбором APK."""
        original = json.loads((TRUTH / "enums.json").read_text(encoding="utf-8"))["node_types"]
        assert [t.value for t in CoreNodeType] == original
        assert len(original) == 143

    def test_survives_json_roundtrip_as_plain_string(self) -> None:
        assert json.loads(json.dumps({"type": CoreNodeType.FRACTION}))["type"] == "FRACTION"

    @pytest.mark.parametrize(
        ("value", "known"),
        [("FRACTION", True), ("frac", False), ("НЕТ", False), ("", False)],
    )
    def test_is_known_type(self, value: str, known: bool) -> None:
        assert is_known_type(value) is known


class TestCoreNode:
    def test_terminal_has_no_children(self) -> None:
        n = CoreNode.constant(42)
        assert n.value == "42"
        assert n.children == []

    def test_value_and_children_are_exclusive(self) -> None:
        """Терминал с потомками — ошибка формата, а не «лишние данные»."""
        with pytest.raises(ValueError, match="нельзя одновременно"):
            CoreNode(type=CoreNodeType.ADD, value="1", children=[CoreNode.constant(1)])

    def test_type_must_be_known(self) -> None:
        with pytest.raises(ValueError):
            CoreNode(type="НЕ_ИЗВЕСТЕН", value="1")

    def test_deep_json_is_value_error(self) -> None:
        """3000 уровней — ValueError, а не RecursionError наружу."""
        data: dict[str, object] = {"type": "CONSTANT", "value": "1"}
        for _ in range(3000):
            data = {"type": "ADD", "children": [data, {"type": "CONSTANT", "value": "1"}]}
        with pytest.raises(ValueError, match="глубокий"):
            CoreNode.from_contract(data)

    def test_walk_visits_depth_first(self) -> None:
        tree = CoreNode.node(
            CoreNodeType.EQUALS,
            CoreNode.node(CoreNodeType.ADD, CoreNode.variable("x"), CoreNode.constant(1)),
            CoreNode.constant(2),
        )
        types = [n.type for n in tree.walk()]
        assert types == [
            CoreNodeType.EQUALS,
            CoreNodeType.ADD,
            CoreNodeType.VARIABLE,
            CoreNodeType.CONSTANT,
            CoreNodeType.CONSTANT,
        ]
        assert len(tree.find_all(CoreNodeType.CONSTANT)) == 2

    def test_structural_eq_ignores_nothing(self) -> None:
        a = CoreNode.node(CoreNodeType.ADD, CoreNode.constant(1), CoreNode.variable("x"))
        b = CoreNode.node(CoreNodeType.ADD, CoreNode.constant(1), CoreNode.variable("x"))
        c = CoreNode.node(CoreNodeType.ADD, CoreNode.constant(1), CoreNode.variable("y"))
        assert a.structural_eq(b)
        assert not a.structural_eq(c)
        assert not a.structural_eq("не узел")


class TestContractSerialization:
    def test_terminal_contract_shape(self) -> None:
        """Gson опускает null-поля — проверяем тот же минимальный вид."""
        assert CoreNode.constant(7).to_contract() == {"type": "CONSTANT", "value": "7"}

    def test_branch_contract_shape(self) -> None:
        node = CoreNode.node(CoreNodeType.ADD, CoreNode.variable("x"), CoreNode.constant(1))
        assert node.to_contract() == {
            "type": "ADD",
            "children": [
                {"type": "VARIABLE", "value": "x"},
                {"type": "CONSTANT", "value": "1"},
            ],
        }

    def test_roundtrip_preserves_structure(self) -> None:
        node = CoreNode.node(
            CoreNodeType.FRACTION,
            CoreNode.constant(1),
            CoreNode.node(CoreNodeType.ADD, CoreNode.variable("x"), CoreNode.constant(2)),
        )
        assert CoreNode.from_contract(node.to_contract()).structural_eq(node)

    def test_colored_node_roundtrips_as_colored(self) -> None:
        """Полиморфизм: наличие color/crossed поднимает узел в CoreColoredNode."""
        original = CoreColoredNode(
            type=CoreNodeType.CONSTANT,
            value="9",
            color=0xFF00FF00,
            crossed=True,
        )
        payload = original.to_contract()
        assert payload["color"] == 0xFF00FF00
        assert payload["crossed"] is True

        restored = CoreNode.from_contract(payload)
        assert isinstance(restored, CoreColoredNode)
        assert restored.is_crossed() is True

    def test_plain_node_stays_plain(self) -> None:
        restored = CoreNode.from_contract(CoreNode.constant(3).to_contract())
        assert type(restored) is CoreNode

    def test_crossed_none_reads_as_false(self) -> None:
        assert CoreColoredNode(type=CoreNodeType.CONSTANT, value="1").is_crossed() is False
