import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/render/latex.dart';
import 'package:mymath_app/src/settings/settings.dart';

CoreNode _num(String value) =>
    CoreNode(type: CoreNodeType.constant, value: value);

void main() {
  test('differential stands apart: 2x dx, not 2xdx', () {
    final x = CoreNode(type: CoreNodeType.variable, value: 'x');
    final dx = CoreNode(type: CoreNodeType.variable, value: 'dx');
    expect(
      nodeToLatex(
        CoreNode(
          type: CoreNodeType.multiplyImplicit,
          children: [
            CoreNode(
              type: CoreNodeType.multiplyImplicit,
              children: [_num('2'), x],
            ),
            dx,
          ],
        ),
      ),
      r'2 x\,dx',
    );
  });
  group('штрих производной', () {
    test('произведение и сумма в скобках', () {
      final product = CoreNode(
        type: CoreNodeType.multiplyImplicit,
        children: [
          CoreNode(
            type: CoreNodeType.power,
            children: [
              CoreNode(type: CoreNodeType.variable, value: 'x'),
              _num('2'),
            ],
          ),
          _num('3'),
        ],
      );
      expect(
        nodeToLatex(
          CoreNode(type: CoreNodeType.derivation2Prime, children: [product]),
        ),
        r"\left({x}^{2} 3\right)''",
      );
      final sum = CoreNode(
        type: CoreNodeType.add,
        children: [
          CoreNode(type: CoreNodeType.variable, value: 'x'),
          _num('1'),
        ],
      );
      expect(
        nodeToLatex(
          CoreNode(type: CoreNodeType.derivation1Prime, children: [sum]),
        ),
        r"\left(x + 1\right)'",
      );
    });

    test('одна переменная без скобок', () {
      final node = CoreNode(
        type: CoreNodeType.derivation2Prime,
        children: [CoreNode(type: CoreNodeType.variable, value: 'x')],
      );
      expect(nodeToLatex(node), "{x}''");
    });
  });

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

    test('система с дробями раздвигает строки, без дробей — нет', () {
      CoreNode equation(CoreNode left) =>
          CoreNode(type: CoreNodeType.equals, children: [left, _num('1')]);
      CoreNode system(CoreNode left) => CoreNode(
        type: CoreNodeType.system,
        children: [equation(left), equation(_num('2'))],
      );
      final fraction = CoreNode(
        type: CoreNodeType.fraction,
        children: [_num('10'), _num('11')],
      );
      expect(nodeToLatex(system(fraction)), contains(r'\\[0.4em]'));
      expect(nodeToLatex(system(_num('3'))), isNot(contains('[0.4em]')));
    });

    test('скобки в показателе — простые: 2^(x²−3x) без \\left', () {
      CoreNode op(CoreNodeType type, List<CoreNode> children) =>
          CoreNode(type: type, children: children);
      final x = CoreNode(type: CoreNodeType.variable, value: 'x');
      final exponent = op(CoreNodeType.bracket, [
        op(CoreNodeType.subtract, [
          op(CoreNodeType.power, [x, _num('2')]),
          x,
        ]),
      ]);
      expect(
        nodeToLatex(op(CoreNodeType.power, [_num('2'), exponent])),
        r'{2}^{({x}^{2} - x)}',
      );
    });

    test('скобки по приоритету: узлы sympy приходят без BRACKET', () {
      CoreNode op(CoreNodeType type, List<CoreNode> children) =>
          CoreNode(type: type, children: children);
      final x = CoreNode(type: CoreNodeType.variable, value: 'x');
      final xMinus1 = op(CoreNodeType.subtract, [x, _num('1')]);
      // (x − 1)², не x − 1²
      expect(
        nodeToLatex(op(CoreNodeType.power, [xMinus1, _num('2')])),
        r'{\left(x - 1\right)}^{2}',
      );
      // −2(x − 3), не −2x − 3
      final xMinus3 = op(CoreNodeType.subtract, [x, _num('3')]);
      expect(
        nodeToLatex(
          op(CoreNodeType.negative, [
            op(CoreNodeType.multiplyImplicit, [_num('2'), xMinus3]),
          ]),
        ),
        r'-2 \left(x - 3\right)',
      );
      // a − (b + c), но a + b − c без скобок
      final sum = op(CoreNodeType.add, [x, _num('1')]);
      expect(
        nodeToLatex(op(CoreNodeType.subtract, [_num('2'), sum])),
        r'2 - \left(x + 1\right)',
      );
      expect(
        nodeToLatex(op(CoreNodeType.subtract, [sum, _num('2')])),
        'x + 1 - 2',
      );
      // (−2)², 3·(−2): отрицательное число как операнд
      expect(
        nodeToLatex(op(CoreNodeType.power, [_num('-2'), _num('2')])),
        r'{\left(-2\right)}^{2}',
      );
      expect(
        nodeToLatex(op(CoreNodeType.multiply, [_num('3'), _num('-2')])),
        r'3 \cdot \left(-2\right)',
      );
      // d(x + 1)/dx
      expect(
        nodeToLatex(op(CoreNodeType.derivation1Diff, [x, sum])),
        r'\frac{d\,\left(x + 1\right)}{d\,x}',
      );
      // явная скобка не удваивается
      final bracket = op(CoreNodeType.bracket, [xMinus1]);
      expect(
        nodeToLatex(op(CoreNodeType.multiplyImplicit, [_num('2'), bracket])),
        r'2 \left(x - 1\right)',
      );
    });

    test('нотация биномиального коэффициента', () {
      final node = CoreNode(
        type: CoreNodeType.choose,
        children: [_num('n'), _num('k')],
      );
      expect(nodeToLatex(node), contains(r'\binom'));
      const stacked = LatexOptions(
        binomialNotation: BinomialNotation.notationTwo,
      );
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

  group('интеграл и дифференциал', () {
    CoreNode variable(String name) =>
        CoreNode(type: CoreNodeType.variable, value: name);

    CoreNode squared(String name) => CoreNode(
      type: CoreNodeType.power,
      children: [variable(name), _num('2')],
    );

    test('переменная берётся из подынтегрального выражения', () {
      final node = CoreNode(
        type: CoreNodeType.integral,
        children: [squared('t')],
      );
      expect(nodeToLatex(node), r'\int {t}^{2}\,dt');
    });

    test('e — константа, не переменная интегрирования: ∫eᵗ dt', () {
      final node = CoreNode(
        type: CoreNodeType.integral,
        children: [
          CoreNode(
            type: CoreNodeType.power,
            children: [variable('e'), variable('t')],
          ),
        ],
      );
      expect(nodeToLatex(node), endsWith(r'\,dt'));
    });

    test('без переменной — dx', () {
      final node = CoreNode(type: CoreNodeType.integral, children: [_num('1')]);
      expect(nodeToLatex(node), r'\int 1\,dx');
    });

    test('определённый интеграл — тоже по подынтегральному выражению', () {
      final node = CoreNode(
        type: CoreNodeType.integralDefinite,
        children: [_num('0'), _num('1'), squared('t')],
      );
      expect(nodeToLatex(node), r'\int_{0}^{1} {t}^{2}\,dt');
    });

    test('несколько переменных — dx, как у решателя по умолчанию', () {
      final node = CoreNode(
        type: CoreNodeType.integral,
        children: [
          CoreNode(
            type: CoreNodeType.multiplyImplicit,
            children: [variable('x'), variable('y')],
          ),
        ],
      );
      expect(nodeToLatex(node), endsWith(r'\,dx'));
    });

    test('табличная формула ∫tⁿ — по t, n — параметр', () {
      final node = CoreNode(
        type: CoreNodeType.integral,
        children: [
          CoreNode(
            type: CoreNodeType.power,
            children: [variable('t'), variable('n')],
          ),
        ],
      );
      expect(nodeToLatex(node), endsWith(r'\,dt'));
    });

    test('сумма под интегралом — в скобках', () {
      final sum = CoreNode(
        type: CoreNodeType.add,
        children: [variable('x'), _num('1')],
      );
      expect(
        nodeToLatex(CoreNode(type: CoreNodeType.integral, children: [sum])),
        r'\int \left(x + 1\right)\,dx',
      );
      expect(
        nodeToLatex(
          CoreNode(
            type: CoreNodeType.integralDefinite,
            children: [_num('0'), _num('1'), sum],
          ),
        ),
        r'\int_{0}^{1} \left(x + 1\right)\,dx',
      );
    });
  });

  group('ответы интегралов', () {
    CoreNode v(String name) =>
        CoreNode(type: CoreNodeType.variable, value: name);

    test('ln|x| без лишних скобок', () {
      final node = CoreNode(
        type: CoreNodeType.ln,
        children: [
          CoreNode(type: CoreNodeType.abs, children: [v('x')]),
        ],
      );
      expect(nodeToLatex(node), r'\ln\left|x\right|');
    });

    test('словесный ответ — текстом с пробелами', () {
      final node = CoreNode(
        type: CoreNodeType.text,
        value: 'Интеграл расходится',
      );
      expect(nodeToLatex(node), r'\text{Интеграл расходится}');
    });

    test('lim последовательности — по n, lim∫₁ᵇ — по b', () {
      final sequence = CoreNode(
        type: CoreNodeType.limit,
        children: [
          CoreNode(type: CoreNodeType.constant, value: '∞'),
          CoreNode(type: CoreNodeType.fraction, children: [_num('1'), v('n')]),
        ],
      );
      expect(nodeToLatex(sequence), startsWith(r'\lim_{n \to'));
      final improper = CoreNode(
        type: CoreNodeType.limit,
        children: [
          CoreNode(type: CoreNodeType.constant, value: '∞'),
          CoreNode(
            type: CoreNodeType.integralDefinite,
            children: [
              _num('1'),
              v('b'),
              CoreNode(
                type: CoreNodeType.fraction,
                children: [_num('1'), v('x')],
              ),
            ],
          ),
        ],
      );
      expect(nodeToLatex(improper), startsWith(r'\lim_{b \to'));
    });

    test('сумма под lim — в скобках: lim(1 − 1/b)', () {
      final node = CoreNode(
        type: CoreNodeType.limit,
        children: [
          CoreNode(type: CoreNodeType.constant, value: '∞'),
          CoreNode(
            type: CoreNodeType.subtract,
            children: [
              _num('1'),
              CoreNode(
                type: CoreNodeType.fraction,
                children: [_num('1'), v('b')],
              ),
            ],
          ),
        ],
      );
      expect(nodeToLatex(node), endsWith(r'} \left(1 - \frac{1}{b}\right)'));
    });
  });
}
