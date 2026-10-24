import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/ui/formula_break.dart';

/// A formula that does not fit is broken across lines like a book, shrunk, or
/// (only as a last resort) scrolled; a short one stays a single `Math`.
void main() {
  const long =
      r'y = C_{1}\cos\left(x\right) + C_{2}\sin\left(x\right)'
      r' - \frac{x}{2}\cos\left(x\right)';
  const short = r'y = C';

  group('splitFormula', () {
    test('breaks before top-level relations and + / -', () {
      final parts = splitFormula(long);
      expect(parts.pieces.map((piece) => piece.latex), [
        'y',
        r'= C_{1}\cos\left(x\right)',
        // `{}` keeps a leading sign binary: «+ C₂», not the unary «+C₂».
        r'{}+ C_{2}\sin\left(x\right)',
        r'{}- \frac{x}{2}\cos\left(x\right)',
      ]);
      expect(parts.pieces.every((piece) => !piece.breaksLine), isTrue);
    });

    test('a ,\\quad list starts a line per item', () {
      final parts = splitFormula(
        r'y_{1} = e^{-x}\cos\left(2 x\right),\quad y_{2} = e^{-x}\sin\left(2 x\right)',
      );
      // The second item starts a line; its own relation may continue it.
      final starts = [
        for (var i = 0; i < parts.pieces.length; i++)
          if (i == 0 || parts.pieces[i].breaksLine) parts.pieces[i].latex,
      ];
      expect(starts, [r'y_{1}', r'y_{2}']);
      expect(parts.pieces.length, 4);
    });

    test(
      'a formula without top-level operators and a matrix are one piece',
      () {
        expect(splitFormula(r'\frac{1}{2}').breakable, isFalse);
        expect(
          splitFormula(r'\begin{matrix} 1 & 2 \\ 3 & 4 \end{matrix}').breakable,
          isFalse,
        );
        // A relation inside brackets or a fraction is not a line break.
        expect(splitFormula(r'\left(x + 1\right) = y').pieces.length, 2);
        expect(splitFormula(r'\frac{x + 1}{x - 1}').breakable, isFalse);
      },
    );
  });

  testWidgets('a long answer is broken and does not scroll', (tester) async {
    await tester.pumpWidget(
      _page(const BreakableFormula(latex: long, fontSize: 28)),
    );
    await tester.pumpAndSettle();
    final flow = tester.renderObject<RenderFormulaFlow>(
      find.byType(FormulaFlow),
    );
    expect(flow.fit, FormulaFit.broken);
    expect(flow.lines, greaterThanOrEqualTo(2));
    expect(flow.painted, greaterThanOrEqualTo(2));
    expect(find.byType(SingleChildScrollView), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a short answer stays a single Math', (tester) async {
    await tester.pumpWidget(
      _page(const BreakableFormula(latex: short, fontSize: 28)),
    );
    await tester.pumpAndSettle();
    final flow = tester.renderObject<RenderFormulaFlow>(
      find.byType(FormulaFlow),
    );
    expect(flow.fit, FormulaFit.single);
    expect(flow.lines, 1);
    expect(flow.painted, 1);
    expect(find.byType(SingleChildScrollView), findsNothing);
  });

  testWidgets('a piece that still does not fit is shrunk, not below 70 %', (
    tester,
  ) async {
    const unbreakable =
        r'\left(x + 1\right)\left(x + 2\right)\left(x + 3\right)\left(x + 4\right)';
    await tester.pumpWidget(_page(BreakableFormula(latex: unbreakable)));
    await tester.pumpAndSettle();
    final natural = tester
        .renderObject<RenderFormulaFlow>(find.byType(FormulaFlow))
        .size
        .width;
    expect(splitFormula(unbreakable).breakable, isFalse);

    await tester.pumpWidget(
      _page(
        SizedBox(
          width: natural * .85,
          child: const BreakableFormula(latex: unbreakable),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final flow = tester.renderObject<RenderFormulaFlow>(
      find.byType(FormulaFlow),
    );
    expect(flow.fit, FormulaFit.scaled);
    expect(flow.size.width, closeTo(natural * .85, 1));
    expect(find.byType(SingleChildScrollView), findsNothing);

    // Half the width would need less than 70 %: keep the scroll and hint it.
    await tester.pumpWidget(
      _page(
        SizedBox(
          width: natural * .5,
          child: const BreakableFormula(latex: unbreakable),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.renderObject<RenderFormulaFlow>(find.byType(FormulaFlow)).fit,
      FormulaFit.scrolled,
    );
    expect(find.byType(ScrollFade), findsOneWidget);
    expect(find.byType(SingleChildScrollView), findsOneWidget);
    expect(
      tester
          .state<ScrollableState>(find.byType(Scrollable).first)
          .position
          .maxScrollExtent,
      greaterThan(1),
    );
  });
}

Widget _page(Widget child) => MaterialApp(
  home: Scaffold(
    body: Align(
      alignment: Alignment.topLeft,
      child: Padding(padding: const EdgeInsets.all(16), child: child),
    ),
  ),
);
