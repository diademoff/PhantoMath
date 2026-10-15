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
