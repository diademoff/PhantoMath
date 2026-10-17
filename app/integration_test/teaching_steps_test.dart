import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:mymath_app/main.dart' as app;
import 'package:mymath_app/src/ui/vertical_result.dart';

Future<void> tap(WidgetTester tester, Finder finder) async {
  if (finder.evaluate().isEmpty &&
      find.byType(VerticalResult).evaluate().isNotEmpty) {
    // Like a person, scroll the vertical solution to mount off-screen groups;
    // ensureVisible alone cannot locate a lazily built card.
    final scrollable = find
        .descendant(
          of: find.byType(VerticalResult).last,
          matching: find.byType(Scrollable),
        )
        .first;
    await tester.scrollUntilVisible(finder, 220, scrollable: scrollable);
  }
  final opensHelp = finder.evaluate().any(
    (element) =>
        element.widget.key == const ValueKey('step-details') ||
        element.widget.key == const ValueKey('step-theory'),
  );
  await tester.ensureVisible(finder);
  await tester.pump(const Duration(milliseconds: 220));
  await tester.tap(finder);
  await tester.pump(const Duration(milliseconds: 300));
  if (opensHelp) await tester.pumpAndSettle();
}

Future<void> key(WidgetTester tester, String code) =>
    tap(tester, find.byKey(ValueKey('key:$code')));

Future<void> openSolution(WidgetTester tester) async {
  await tap(tester, find.byKey(const ValueKey('solve')));
  for (var i = 0; i < 120; i++) {
    await tester.pump(const Duration(milliseconds: 250));
    if (find.byType(VerticalResult).evaluate().isNotEmpty) return;
  }
  fail('Solution did not open');
}

Future<void> back(WidgetTester tester) async {
  await tester.pumpAndSettle();
  await tester.pageBack();
  await tester.pumpAndSettle();
}

Future<void> clear(WidgetTester tester) async {
  await tap(tester, find.byTooltip('Назад'));
  await tap(tester, find.byTooltip('Очистить'));
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets(
    'device: real fractions and equations have stages, nested details and offline theory',
    (tester) async {
      app.main();
      await tester.pump();
      await tester.pump(const Duration(seconds: 2));
      // 1/3 + 1/6, using the real editor and embedded Python.
      await key(tester, 'OPERATOR_FRACTION');
      await key(tester, 'DIGIT_ONE');
      await tap(tester, find.text('Далее'));
      await key(tester, 'DIGIT_THREE');
      await tap(tester, find.text('Далее'));
      await key(tester, 'BASIC_INFIX_OPERATOR_PLUS');
      await key(tester, 'OPERATOR_FRACTION');
      await key(tester, 'DIGIT_ONE');
      await tap(tester, find.text('Далее'));
      await key(tester, 'DIGIT_SIX');
      await tap(tester, find.text('Далее'));
      await openSolution(tester);
      final fraction = tester
          .widget<VerticalResult>(find.byType(VerticalResult))
          .result;
      // Photomath's model: common denominator (nested), sum of numerators, reduction (nested).
      expect(fraction.steps, hasLength(3));
      await tap(tester, find.byKey(const ValueKey('step-theory')));
      expect(find.text('Основное свойство дроби'), findsOneWidget);
      await back(tester);
      await tap(tester, find.byKey(const ValueKey('step-details')));
      expect(
        tester.widget<VerticalResult>(find.byType(VerticalResult)).result.steps,
        hasLength(3),
      );
      await back(tester);
      await clear(tester);

      // A balance operation is shown on both sides, not just a new final answer.
      await key(tester, 'DIGIT_TWO');
      await key(tester, 'VARIABLE_X_LOW');
      await key(tester, 'BASIC_INFIX_OPERATOR_PLUS');
      await key(tester, 'DIGIT_THREE');
      await key(tester, 'BASIC_INFIX_OPERATOR_EQUALS');
      await key(tester, 'DIGIT_SEVEN');
      await openSolution(tester);
      expect(
        find.text('Перенести константу в правую часть равенства'),
        findsOneWidget,
      );
      await tap(tester, find.byKey(const ValueKey('step-details')));
      final linear = tester
          .widget<VerticalResult>(find.byType(VerticalResult))
          .result;
      expect(linear.solution, isNotNull);
      expect(
        linear.steps
            .expand((s) => s.substeps)
            .any((s) => s.explanationKey == 'rel_swap_right_const'),
        isTrue,
      );
      await back(tester);
      await tap(tester, find.byKey(const ValueKey('step-theory')));
      expect(
        find.text('Равносильные преобразования уравнения'),
        findsOneWidget,
      );
      await back(tester);
      await clear(tester);

      // x² - 5x + 6 = 0
      await key(tester, 'VARIABLE_X_LOW');
      await key(tester, 'OPERATOR_POWER_TWO');
      await key(tester, 'BASIC_INFIX_OPERATOR_MINUS');
      await key(tester, 'DIGIT_FIVE');
      await key(tester, 'VARIABLE_X_LOW');
      await key(tester, 'BASIC_INFIX_OPERATOR_PLUS');
      await key(tester, 'DIGIT_SIX');
      await key(tester, 'BASIC_INFIX_OPERATOR_EQUALS');
      await key(tester, 'DIGIT_ZERO');
      await openSolution(tester);
      // Photomath's factoring method: six main steps, stages inside, detail screens.
      expect(
        tester.widget<VerticalResult>(find.byType(VerticalResult)).result.steps,
        hasLength(6),
      );
      await tap(tester, find.byKey(const ValueKey('solution-group:1')));
      expect(find.text('Этап 1 из 2'), findsOneWidget);
      await tap(tester, find.byKey(const ValueKey('next-stage')));
      await tester.pumpAndSettle();
      expect(find.text('Этап 2 из 2'), findsOneWidget);
      await tap(tester, find.byKey(const ValueKey('solution-group:4')));
      expect(find.text('Этап 1 из 2'), findsOneWidget);
      await tap(tester, find.byKey(const ValueKey('step-details')));
      expect(
        tester.widget<VerticalResult>(find.byType(VerticalResult)).result.steps,
        isNotEmpty,
      );
      await back(tester);
      expect(tester.takeException(), isNull);
    },
  );
}
