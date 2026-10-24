import 'package:flutter_test/flutter_test.dart';

import 'support/card_rules.dart';

/// Fixed strings: every card rule on the text the student actually reads.
void main() {
  test('typed math is a formula part, not prose', () {
    expect(hasTypedMath('Выразим y; постоянная C = ±e^(C₀).'), isTrue);
    expect(hasTypedMath('Положим y = uv.'), isTrue);
    expect(hasTypedMath('Разделим переменные.'), isFalse);
    expect(hasTypedMath('Обозначим y′ и подставим.'), isFalse);
    expect(hasTypedMath('v′ + p v = 0'), isTrue);
    expect(hasTypedMath('α = −1, β = 2'), isTrue);
    expect(hasTypedMath('корень sqrt(x)'), isTrue);
    expect(hasTypedMath('предел ARG1'), isTrue);
    expect(hasTypedMath('вернулось None'), isTrue);
  });

  test('text-math is reported with the text', () {
    final problems = textProblems('Шаг 1', 'Положим y = uv.');
    expect(problems.map((p) => p.rule), ['text-math']);
    expect(problems.single.where, 'Шаг 1');
  });

  test('an untranslated latin word is english, a formula is not', () {
    expect(firstEnglishWord('Найдём предел limit функции'), 'limit');
    expect(firstEnglishWord('Подставим dx и dy'), isNull);
    expect(textProblems('x', 'Разделим переменные.'), isEmpty);
  });

  test('dot is only wrong before a non-number', () {
    expect(hasMisplacedDot(r'C \cdot e^{-x}'), isTrue);
    expect(hasMisplacedDot(r'x \cdot 2^{x}'), isFalse);
    expect(hasMisplacedDot(r'x \cdot -2'), isFalse);
    expect(hasMisplacedDot(r'C e^{-x}'), isFalse);
  });

  test('same left/right and a repeated formula part', () {
    expect(sameFormula(r'x+1', r'x+1'), isTrue);
    expect(sameFormula(r'x+1', r'x+2'), isFalse);
    expect(repeatsFormula(r'x+1', r'x+1', r'x+2'), isTrue);
    expect(repeatsFormula(r'x', r'x+1', r'x+2'), isFalse);
    final problems = stageFormulaProblems(
      'Шаг 1 Этап 1',
      left: r'x+1',
      right: r'x+1',
    );
    expect(problems.map((p) => p.rule), contains('same'));
  });

  test('a fallback heading and two equal neighbouring headings', () {
    expect(isFallbackHeading(''), isTrue);
    expect(isFallbackHeading('Преобразование'), isTrue);
    expect(isFallbackHeading('Выразим y'), isFalse);
    final problems = headingProblems([
      (where: 'Шаг 1', heading: 'Выразим y'),
      (where: 'Шаг 2', heading: 'Выразим y'),
      (where: 'Шаг 3', heading: ''),
    ]);
    expect(problems.map((p) => p.rule), ['heading', 'heading']);
    expect(problems.first.detail, contains('два шага подряд'));
  });

  test('a formula that does not parse is a tex-error', () {
    final problems = formulaProblems('ответ', r'\frac{1}');
    expect(problems.map((p) => p.rule), ['tex-error']);
    expect(formulaProblems('ответ', r'\frac{1}{2}'), isEmpty);
  });

  test('problems.txt line is tab separated', () {
    const problem = CardProblem('ответ', 'dot', '«C \\cdot e»');
    expect(problem.line('ode1'), 'ode1\tответ\tdot\t«C \\cdot e»');
  });
}
