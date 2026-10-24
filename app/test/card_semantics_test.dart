import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/render/latex.dart';
import 'package:mymath_app/src/theme/phanto_theme.dart';
import 'package:mymath_app/src/ui/solution_preview.dart';
import 'package:mymath_app/src/ui/vertical_result.dart';

/// Every formula the student sees carries its LaTeX as a semantics label, so
/// `uiautomator dump` shows it as `content-desc` (see `tools/device/drive.py`).
void main() {
  const x = CoreNode(type: CoreNodeType.variable, value: 'x');
  const y = CoreNode(type: CoreNodeType.variable, value: 'y');
  const one = CoreNode(type: CoreNodeType.constant, value: '1');
  const sum = CoreNode(type: CoreNodeType.add, children: [x, one]);
  final stepLatex = nodeToLatex(sum, LatexOptions.standard);
  final inlineLatex = nodeToLatex(y, LatexOptions.standard);

  testWidgets('a step equation and an inline formula are semantics labels', (
    tester,
  ) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(
      MaterialApp(
        theme: PhantoTheme.light(),
        home: Scaffold(
          body: VerticalResult(
            latexOptions: LatexOptions.standard,
            onLink: (_) {},
            onCopy: (_) {},
            result: const SolveResponse(
              steps: [
                SolveStep(
                  id: 'group',
                  headers: ['Положим'],
                  substeps: [
                    Substep(
                      text: 'Положим y = uv.',
                      parts: [
                        ExplanationPart(text: 'Положим '),
                        ExplanationPart(node: y),
                        ExplanationPart(text: ' — короткая формула.'),
                      ],
                      left: x,
                      right: sum,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel(inlineLatex), findsOneWidget);
    expect(find.bySemanticsLabel(stepLatex), findsOneWidget);
    expect(tester.takeException(), isNull);
    handle.dispose();
  });

  testWidgets('the live answer carries its latex', (tester) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(
      MaterialApp(
        theme: PhantoTheme.light(),
        home: Scaffold(body: SolutionPreview(latex: stepLatex)),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel(stepLatex), findsOneWidget);
    expect(tester.takeException(), isNull);
    handle.dispose();
  });
}
