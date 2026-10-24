import '../model/core_node.dart';

/// The accent red for the parts a step changes.
const int changeColor = 0xFFBF0C34;

/// The two formulas of a step with what changes coloured: the parts of
/// [before] that go away and the parts of [after] that appear.
///
/// A part is unchanged when the same subtree occurs on the other side
/// (`x² − 5x + 6 = 0` → `x² − 2x − 3x + 6 = 0` colours only −5x and −2x, −3x).
/// A node keeps its colour off when something inside it is a larger unchanged
/// part; otherwise the whole node is coloured, so `x²` lights up as one piece
/// rather than as a lone exponent. A step whose sides already carry colours
/// from the solver is left as it is.
(CoreNode, CoreNode) highlightChange(CoreNode before, CoreNode after) {
  if (_coloured(before) || _coloured(after)) return (before, after);
  final left = _subtrees(before);
  final right = _subtrees(after);
  return (_mark(before, right), _mark(after, left));
}

bool _coloured(CoreNode node) =>
    node.color != null || node.children.any(_coloured);

Set<String> _subtrees(CoreNode node, [Set<String>? into]) {
  final out = into ?? <String>{};
  out.add(node.toString());
  for (final child in node.children) {
    _subtrees(child, out);
  }
  return out;
}

/// Relations and lists are frames, never one changed piece: `x = 5` colours the 5.
const _frames = {
  CoreNodeType.equals,
  CoreNodeType.lessThan,
  CoreNodeType.lessThanEqual,
  CoreNodeType.greaterThan,
  CoreNodeType.greaterThanEqual,
  CoreNodeType.list,
  CoreNodeType.verticalList,
  CoreNodeType.system,
};

CoreNode _mark(CoreNode node, Set<String> other) {
  if (other.contains(node.toString())) return node;
  if (node.children.isEmpty ||
      (!_frames.contains(node.type) && !_keepsPart(node, other))) {
    return CoreNode(
      type: node.type,
      value: node.value,
      children: node.children,
      color: changeColor,
      crossed: node.crossed,
    );
  }
  return CoreNode(
    type: node.type,
    value: node.value,
    children: [for (final child in node.children) _mark(child, other)],
    crossed: node.crossed,
  );
}

/// Does [node] hold an unchanged part bigger than a single number or letter?
bool _keepsPart(CoreNode node, Set<String> other) => node.children.any(
  (child) =>
      (child.children.isNotEmpty && other.contains(child.toString())) ||
      _keepsPart(child, other),
);
