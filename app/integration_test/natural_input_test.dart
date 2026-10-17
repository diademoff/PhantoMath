import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:mymath_app/main.dart' as app;
import 'package:mymath_app/src/editor/editor_view.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/ui/solution_preview.dart';
import 'package:mymath_app/src/ui/vertical_result.dart';

Future<void> key(WidgetTester tester, String code) async {
  final finder = find.byKey(ValueKey('key:$code'));
  await tester.ensureVisible(finder);
  await tester.pump(const Duration(milliseconds: 60));
  await tester.tap(finder);
  await tester.pump(const Duration(milliseconds: 90));
}

Future<void> next(WidgetTester tester) async {
  final finder = find.text('Далее');
  await tester.ensureVisible(finder);
  await tester.tap(finder);
  await tester.pump(const Duration(milliseconds: 90));
}

Future<void> preview(WidgetTester tester) async {
  for (var i = 0; i < 120; i++) {
    await tester.pump(const Duration(milliseconds: 250));
    if (find.byType(SolutionPreview).evaluate().isNotEmpty) return;
  }
  fail(
    'No automatic answer. Texts: ${tester.widgetList<Text>(find.byType(Text)).map((t) => t.data).toList()}',
  );
}

Future<VerticalResult> details(WidgetTester tester) async {
  await tester.tap(find.byKey(const ValueKey('solve')));
  for (
    var i = 0;
    i < 120 && find.byType(VerticalResult).evaluate().isEmpty;
    i++
  ) {
    await tester.pump(const Duration(milliseconds: 250));
  }
  return tester.widget<VerticalResult>(find.byType(VerticalResult));
}

Future<void> clear(WidgetTester tester) async {
  if (find.byTooltip('Назад').evaluate().isNotEmpty) {
    await tester.tap(find.byTooltip('Назад'));
    await tester.pump();
  }
  await tester.tap(find.byTooltip('Очистить'));
  await tester.pump();
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets(
    'human keyboard: powers, fractions, pi, logs, sums, matrices and history',
    (tester) async {
      app.main();
      await tester.pump();
      await tester.pump(const Duration(seconds: 2));
      await key(tester, 'DIGIT_TWO');
      await key(tester, 'VARIABLE_X_LOW');
      await key(tester, 'OPERATOR_POWER_TWO');
      await key(tester, 'BASIC_INFIX_OPERATOR_PLUS');
      await key(tester, 'DIGIT_NINE');
      await key(tester, 'VARIABLE_X_LOW');
      await key(tester, 'BASIC_INFIX_OPERATOR_PLUS');
      await key(tester, 'DIGIT_SIX');
      await key(tester, 'BASIC_INFIX_OPERATOR_EQUALS');
      await key(tester, 'DIGIT_EIGHT');
      await key(tester, 'CONSTANT_PI');
      var editor = tester
          .widget<EditorView>(find.byType(EditorView))
          .controller;
      expect(editor.cursor.steps, isEmpty);
      expect(editor.toCoreNode().type, CoreNodeType.equals);
      expect(
        editor.toCoreNode().children.last.type,
        CoreNodeType.multiplyImplicit,
      );
      await preview(tester);
      var result = await details(tester);
      expect(
        result.result.steps
            .expand((g) => g.substeps)
            .map((s) => s.explanationKey),
        contains('eq_quad_disc'),
      );

      // Return the previous problem from history, with editable exponents.
      await tester.tap(find.byTooltip('Назад'));
      await tester.pump();
      await tester.tap(find.byTooltip('Блокнот'));
      await tester.pump(const Duration(milliseconds: 500));
      final edit = find.text('Редактировать').first;
      await tester.ensureVisible(edit);
      await tester.tap(edit);
      await tester.pump(const Duration(milliseconds: 500));
      editor = tester.widget<EditorView>(find.byType(EditorView)).controller;
      expect(editor.toCoreNode().type, CoreNodeType.equals);
      // Remove =8π from the restored task: roots of the expression, then its
      // real factorization, are meaningful without selecting an equation module.
      await key(tester, 'CONTROL_DELETE');
      await key(tester, 'CONTROL_DELETE');
      await key(tester, 'CONTROL_DELETE');
      expect(editor.toCoreNode().type, isNot(CoreNodeType.equals));
      await preview(tester);
      expect(find.text('Нули выражения: приравниваем его к 0'), findsOneWidget);
      final factor = find.text('Разложить на множители');
      await tester.ensureVisible(factor);
      await tester.tap(factor);
      for (
        var i = 0;
        i < 120 && find.byType(VerticalResult).evaluate().isEmpty;
        i++
      ) {
        await tester.pump(const Duration(milliseconds: 250));
      }
      result = tester.widget<VerticalResult>(find.byType(VerticalResult));
      expect(result.result.solution?.type, CoreNodeType.multiply);
      await clear(tester);

      // 5² -> 5, without losing the 5 or leaving a fixed decoration.
      await key(tester, 'DIGIT_FIVE');
      await key(tester, 'OPERATOR_POWER_TWO');
      await key(tester, 'CONTROL_DELETE');
      expect(editor.toCoreNode().value, '5');
      await key(tester, 'CONTROL_MOVE_LEFT');
      expect(editor.cursor.offset, 0);
      await key(tester, 'CONTROL_MOVE_RIGHT');
      expect(editor.cursor.offset, 1);
      await clear(tester);

      // 6 + 3/4, entered numerator first.
      await key(tester, 'DIGIT_SIX');
      await key(tester, 'BASIC_INFIX_OPERATOR_PLUS');
      await key(tester, 'OPERATOR_FRACTION');
      expect(editor.cursor.steps.last.slot, 0);
      await key(tester, 'DIGIT_THREE');
      await next(tester);
      await key(tester, 'DIGIT_FOUR');
      await next(tester);
      expect(editor.toCoreNode().children.first.value, '6');
      expect(editor.toCoreNode().children.last.children.map((n) => n.value), [
        '3',
        '4',
      ]);
      await preview(tester);
      await clear(tester);

      // Default log10 base is editable: log_2(8) = 3.
      await key(tester, 'HELPER_SHOW_SECONDARY_SHEET');
      await key(tester, 'OPERATOR_LOG10');
      await key(tester, 'DIGIT_EIGHT');
      await key(tester, 'CONTROL_MOVE_LEFT');
      await key(tester, 'CONTROL_MOVE_LEFT');
      expect(editor.cursor.steps.last.slot, 1);
      await key(tester, 'CONTROL_DELETE');
      await key(tester, 'CONTROL_DELETE');
      await key(tester, 'DIGIT_TWO');
      expect(editor.toCoreNode().children.map((n) => n.value), ['8', '2']);
      await preview(tester);
      await clear(tester);

      // sin²(x)+cos²(x), with an explanatory named identity.
      await key(tester, 'HELPER_SHOW_SECONDARY_SHEET');
      await key(tester, 'OPERATOR_SIN');
      await key(tester, 'VARIABLE_X_LOW');
      await next(tester);
      await key(tester, 'OPERATOR_POWER_TWO');
      await key(tester, 'BASIC_INFIX_OPERATOR_PLUS');
      await key(tester, 'HELPER_SHOW_SECONDARY_SHEET');
      await key(tester, 'OPERATOR_COS');
      await key(tester, 'VARIABLE_X_LOW');
      await next(tester);
      await key(tester, 'OPERATOR_POWER_TWO');
      await preview(tester);
      result = await details(tester);
      expect(result.result.solution?.value, '1');
      expect(
        result.result.steps
            .expand((g) => g.substeps)
            .map((s) => s.explanationKey),
        contains('substitute_pythagorean_identity'),
      );
      await clear(tester);

      // Sigma with explicit editable index x, bounds 1..5 and term x.
      await key(tester, 'HELPER_SHOW_SECONDARY_SHEET');
      await key(tester, 'OPERATOR_SIGMA_DEFINITE');
      await key(tester, 'DIGIT_ONE');
      await next(tester);
      await key(tester, 'DIGIT_FIVE');
      await next(tester);
      await key(tester, 'VARIABLE_X_LOW');
      await next(tester);
      await preview(tester);
      result = await details(tester);
      expect(result.result.solution?.value, '15');
      await clear(tester);

      // A larger, rectangular matrix entered cell by cell.
      await key(tester, 'HELPER_SHOW_SECONDARY_SHEET');
      await key(tester, 'OPERATOR_MATRIX');
      await tester.pump(const Duration(milliseconds: 400));
      for (var i = 0; i < 2; i++) {
        await tester.tap(find.byTooltip('Увеличить Строки'));
        await tester.pump();
      }
      await tester.tap(find.byTooltip('Увеличить Столбцы'));
      await tester.pump();
      await tester.tap(find.text('Вставить'));
      await tester.pump(const Duration(milliseconds: 400));
      for (var i = 0; i < 12; i++) {
        await key(tester, 'DIGIT_ONE');
        await next(tester);
      }
      final matrix = editor.toCoreNode();
      expect(matrix.children, hasLength(4));
      expect(matrix.children.every((r) => r.children.length == 3), isTrue);
      await preview(tester);
      expect(tester.takeException(), isNull);
    },
  );
}
