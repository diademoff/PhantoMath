import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/main.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/editor/kind.dart';
import 'package:mymath_app/src/theme/phanto_theme.dart';
import 'package:mymath_app/src/ui/keyboard/math_keyboard.dart';

void main() {
  for (final size in [
    const Size(320, 568),
    const Size(360, 640),
    const Size(740, 360),
  ]) {
    for (final scale in [1.0, 2.0]) {
      testWidgets('adaptive $size text $scale, dark and reduced motion', (
        tester,
      ) async {
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        await tester.pumpWidget(
          MaterialApp(
            theme: PhantoTheme.light(),
            builder: (context, child) => MediaQuery(
              data: MediaQuery.of(context).copyWith(
                textScaler: TextScaler.linear(scale),
                disableAnimations: true,
              ),
              child: child!,
            ),
            home: SolvePage(api: SolverApi(baseUrl: 'http://test')),
          ),
        );
        await tester.pump();
        expect(tester.takeException(), isNull);
        final key = find.byKey(const ValueKey('key:DIGIT_TWO'));
        final grid = find
            .descendant(
              of: find.byType(MathKeyboard),
              matching: find.byType(Scrollable),
            )
            .last;
        await tester.scrollUntilVisible(key, 100, scrollable: grid);
        final rect = tester.getRect(key);
        expect(rect.width, greaterThanOrEqualTo(48));
        expect(rect.height, greaterThanOrEqualTo(48 - .001));
        final editor = tester
            .widget<MathKeyboard>(find.byType(MathKeyboard))
            .controller;
        editor.insertTemplate(ENodeKind.fraction);
        await tester.pump();
        expect(find.text('Числитель'), findsOneWidget);
        expect(tester.takeException(), isNull);
        editor.clear();
        editor.insertMatrix(4, 5);
        await tester.pump();
        expect(find.text('Строка 1, столбец 1'), findsOneWidget);
        expect(tester.takeException(), isNull);
        await tester.tap(find.byTooltip('Скрыть клавиатуру'));
        await tester.pump();
        expect(find.byKey(const ValueKey('key:DIGIT_TWO')), findsNothing);
        await tester.tap(find.byTooltip('Показать клавиатуру'));
        await tester.pump();
        expect(find.byType(MathKeyboard), findsOneWidget);
        expect(tester.takeException(), isNull);
      });
    }
  }
}
