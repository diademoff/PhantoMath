import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/render/highlight.dart';
import 'package:mymath_app/src/render/latex.dart';

CoreNode n(String v) => CoreNode(
  type: RegExp(r'^\d+$').hasMatch(v)
      ? CoreNodeType.constant
      : CoreNodeType.variable,
  value: v,
);
CoreNode op(CoreNodeType t, List<CoreNode> c) => CoreNode(type: t, children: c);
CoreNode times(String k, String x) =>
    op(CoreNodeType.multiplyImplicit, [n(k), n(x)]);
CoreNode square(String x) => op(CoreNodeType.power, [n(x), n('2')]);

void main() {
  test('only the changed terms are coloured on both sides', () {
    // x² − 5x + 6 = 0  →  x² − 2x − 3x + 6 = 0
    final before = op(CoreNodeType.equals, [
      op(CoreNodeType.add, [
        op(CoreNodeType.subtract, [square('x'), times('5', 'x')]),
        n('6'),
      ]),
      n('0'),
    ]);
    final after = op(CoreNodeType.equals, [
      op(CoreNodeType.add, [
        op(CoreNodeType.subtract, [
          square('x'),
          times('2', 'x'),
          times('3', 'x'),
        ]),
        n('6'),
      ]),
      n('0'),
    ]);
    final (left, right) = highlightChange(before, after);
    final l = nodeToLatex(left);
    final r = nodeToLatex(right);
    expect(l, contains(r'\textcolor{#bf0c34}{5 x}'));
    expect(r, contains(r'\textcolor{#bf0c34}{2 x}'));
    expect(r, contains(r'\textcolor{#bf0c34}{3 x}'));
    expect(r, isNot(contains(r'\textcolor{#bf0c34}{{x}^{2}}')));
    expect(r.endsWith('= 0'), isTrue);
  });

  test('a computed value is coloured whole, the frame is not', () {
    // 2x = 3·3 → 2x = 9
    final before = op(CoreNodeType.equals, [
      times('2', 'x'),
      op(CoreNodeType.multiply, [n('3'), n('3')]),
    ]);
    final after = op(CoreNodeType.equals, [times('2', 'x'), n('9')]);
    final (left, right) = highlightChange(before, after);
    expect(nodeToLatex(left), contains(r'\textcolor{#bf0c34}{3 \cdot 3}'));
    expect(nodeToLatex(right), '2 x = \\textcolor{#bf0c34}{9}');
  });

  test('a step that changes nothing and solver colours are left alone', () {
    final same = times('2', 'x');
    expect(highlightChange(same, same), (same, same));
    final coloured = CoreNode(
      type: CoreNodeType.constant,
      value: '1',
      color: 0xFF00FF00,
    );
    expect(highlightChange(coloured, n('2')), (coloured, n('2')));
  });
}
