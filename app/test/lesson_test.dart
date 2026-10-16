import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/render/latex.dart';
import 'package:mymath_app/src/render/division_trace.dart';
import 'package:mymath_app/src/theme/phanto_theme.dart';
import 'package:mymath_app/src/ui/division_lesson.dart';
import 'package:mymath_app/src/ui/transformation_lesson.dart';

CoreNode n(String value) => CoreNode(type: CoreNodeType.constant, value: value);

void main() {
  test('only supported transformations get instructional frames', () {
    expect(
      transformationFrames(
        Substep(left: n('1'), right: n('2')),
        LatexOptions.standard,
      ),
      isEmpty,
    );
    final fraction = CoreNode(
      type: CoreNodeType.fraction,
      children: [n('6'), n('8')],
    );
    final frames = transformationFrames(
      Substep(
        left: fraction,
        right: CoreNode(
          type: CoreNodeType.fraction,
          children: [n('3'), n('4')],
        ),
      ),
      LatexOptions.standard,
    );
    expect(frames, hasLength(4));
    expect(frames[1].latex, contains(r'3\cdot 2'));
    expect(frames[2].latex, contains(r'\cancel{2}'));
  });

  testWidgets('division advances and replays without changing row geometry', (
    tester,
  ) async {
    final trace = DivisionTrace.fromNode(
      CoreNode(type: CoreNodeType.divide, children: [n('96'), n('4')]),
    )!;
    await tester.pumpWidget(
      MaterialApp(
        theme: PhantoTheme.dark(),
        home: DivisionLesson(trace: trace),
      ),
    );
    expect(find.text('Этап 1 из 8'), findsOneWidget);
    await tester.tap(find.text('Далее'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Этап 2 из 8'), findsOneWidget);
    await tester.tap(find.text('Повторить'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Этап 1 из 8'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
