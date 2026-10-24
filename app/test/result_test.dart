import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/render/latex.dart';
import 'package:mymath_app/src/theme/phanto_theme.dart';
import 'package:mymath_app/src/ui/vertical_result.dart';

void main() {
  testWidgets('both sides of a transformation are visible without expansion', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: PhantoTheme.light(),
        home: Scaffold(
          body: VerticalResult(
            result: SolveResponse(
              solution: CoreNode(type: CoreNodeType.constant, value: '4'),
              steps: [
                SolveStep(
                  substeps: [
                    Substep(
                      left: CoreNode(type: CoreNodeType.constant, value: '2'),
                      right: CoreNode(type: CoreNodeType.constant, value: '4'),
                      text: 'Умножим на 2',
                    ),
                  ],
                ),
              ],
            ),
            latexOptions: LatexOptions.standard,
            onLink: (_) {},
            onCopy: (_) {},
          ),
        ),
      ),
    );
    expect(find.text('Ответ'), findsOneWidget);
    expect(find.text('Умножим на 2'), findsOneWidget);
    expect(find.byType(StepEquation), findsNWidgets(3));
    expect(tester.takeException(), isNull);
  });

  test(
    'a contradiction and an identity get a verdict instead of an empty answer',
    () {
      SolveResponse withKey(String key) => SolveResponse(
        steps: [
          SolveStep(substeps: [Substep(explanationKey: key)]),
        ],
      );
      expect(
        withKey('false_statement_solve').verdictLatex,
        contains('Решений нет'),
      );
      expect(withKey('solutions_inf_many').verdictLatex, contains('mathbb{R}'));
      expect(withKey('root_sqr_neg').verdictLatex, contains('Не определён'));
      expect(
        withKey('matrix_inv_det_zero').verdictLatex,
        contains('не существует'),
      );
      expect(
        withKey('limit_does_not_exist_msg').verdictLatex,
        contains('Предел не существует'),
      );
      expect(withKey('eq_trans').verdictLatex, isNull);
    },
  );

  testWidgets('the answer shows its alternative forms', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: PhantoTheme.light(),
        home: Scaffold(
          body: VerticalResult(
            result: SolveResponse(
              solution: CoreNode(type: CoreNodeType.constant, value: '22/5'),
              alternatives: [
                CoreNode(type: CoreNodeType.constant, value: '4.4'),
              ],
              steps: const [],
            ),
            latexOptions: LatexOptions.standard,
            onLink: (_) {},
            onCopy: (_) {},
          ),
        ),
      ),
    );
    // one answer at a time; the switch moves between the fraction and the decimal
    expect(find.byType(StepEquation), findsOneWidget);
    expect(find.text('Обыкновенная'), findsOneWidget);
    await tester.tap(find.text('Десятичная'));
    await tester.pumpAndSettle();
    expect(tester.widget<StepEquation>(find.byType(StepEquation)).latex, '4.4');
  });

  testWidgets('a huge number in the answer shrinks instead of scrolling', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: PhantoTheme.light(),
        home: Scaffold(
          body: SizedBox(
            width: 320,
            child: VerticalResult(
              result: SolveResponse(
                solution: CoreNode(
                  type: CoreNodeType.constant,
                  value: '1267650600228229401496703205376',
                ),
                steps: const [],
              ),
              latexOptions: LatexOptions.standard,
              onLink: (_) {},
              onCopy: (_) {},
            ),
          ),
        ),
      ),
    );
    expect(find.byType(SingleChildScrollView), findsNothing);
  });
}
