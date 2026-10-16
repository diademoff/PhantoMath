import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/render/latex.dart';
import 'package:mymath_app/src/settings/settings.dart';

CoreNode _num(String value) =>
    CoreNode(type: CoreNodeType.constant, value: value);

void main() {
  group('LatexOptions', () {
    test('десятичный разделитель: точка по умолчанию', () {
      final node = _num('1.5');
      expect(nodeToLatex(node), '1.5');
    });

    test('десятичный разделитель: запятая', () {
      final node = _num('1.5');
      const options = LatexOptions(decimalSeparator: DecimalSeparator.comma);
      expect(nodeToLatex(node, options), '1,5');
    });

    test('нотация биномиального коэффициента', () {
      final node = CoreNode(
        type: CoreNodeType.choose,
        children: [_num('n'), _num('k')],
      );
      expect(nodeToLatex(node), contains(r'\binom'));
      const stacked = LatexOptions(binomialNotation: BinomialNotation.notationTwo);
      expect(nodeToLatex(node, stacked), contains('C'));
    });

    test('функция как объект', () {
      CoreNode variable(String name) =>
          CoreNode(type: CoreNodeType.variable, value: name);
      final node = CoreNode(
        type: CoreNodeType.function,
        value: 'f',
        children: [variable('x')],
      );
      expect(nodeToLatex(node), r'f\left(x\right)');
      final inverse = CoreNode(
        type: CoreNodeType.functionInverse,
        value: 'f',
        children: [variable('x')],
      );
      expect(nodeToLatex(inverse), r'f^{-1}\left(x\right)');
    });

    test('отрезок и его длина', () {
      CoreNode variable(String name) =>
          CoreNode(type: CoreNodeType.variable, value: name);
      final segment = CoreNode(
        type: CoreNodeType.lineSegment,
        children: [variable('A'), variable('B')],
      );
      expect(nodeToLatex(segment), r'\overline{A B}');
      final length = CoreNode(
        type: CoreNodeType.lineSegmentLength,
        children: [variable('A'), variable('B')],
      );
      expect(nodeToLatex(length), r'\left|A B\right|');
    });

    test('настройки не влияют на вложенные вызовы', () {
      // Разделитель применяется и к детям, а не сбрасывается на умолчание.
      final node = CoreNode(
        type: CoreNodeType.add,
        children: [_num('1.5'), _num('2.5')],
      );
      const options = LatexOptions(decimalSeparator: DecimalSeparator.comma);
      expect(nodeToLatex(node, options), '1,5 + 2,5');
    });
  });
}
