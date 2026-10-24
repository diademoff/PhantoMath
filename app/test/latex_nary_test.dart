import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/render/latex.dart';

CoreNode c(String v) => CoreNode(type: CoreNodeType.constant, value: v);
CoreNode v(String v) => CoreNode(type: CoreNodeType.variable, value: v);
CoreNode n(CoreNodeType t, List<CoreNode> kids) =>
    CoreNode(type: t, children: kids);

void main() {
  moreCases();
  test('products and sums with three or more operands keep every operand', () {
    final product = n(CoreNodeType.multiply, [c('4'), v('a'), v('c')]);
    expect(nodeToLatex(product, LatexOptions.standard), contains('c'));
    expect(
      nodeToLatex(product, LatexOptions.standard).split(r'\cdot').length,
      3,
    );
    final sum = n(CoreNodeType.add, [c('1'), c('2'), c('3'), c('4')]);
    expect(
      nodeToLatex(sum, LatexOptions.standard).replaceAll(' ', ''),
      '1+2+3+4',
    );
    final difference = n(CoreNodeType.subtract, [c('9'), c('2'), c('3')]);
    expect(
      nodeToLatex(difference, LatexOptions.standard).replaceAll(' ', ''),
      '9-2-3',
    );
  });
}

void moreCases() {
  test('a system shows every equation, a chained inequality every part', () {
    final system = n(CoreNodeType.system, [
      n(CoreNodeType.greaterThan, [v('x'), c('-2')]),
      n(CoreNodeType.lessThan, [v('x'), c('3')]),
    ]);
    final latex = nodeToLatex(system, LatexOptions.standard);
    expect(latex, contains(r'\\'));
    expect(latex, contains('x > '));
    expect(latex, contains('x < '));
    final chained = n(CoreNodeType.lessThan, [c('1'), v('x'), c('3')]);
    expect(
      nodeToLatex(chained, LatexOptions.standard).replaceAll(' ', ''),
      '1<x<3',
    );
  });
}
