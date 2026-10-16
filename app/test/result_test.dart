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
        theme: PhantoTheme.dark(),
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
}
