/// Клавиша «Определитель»: ввод определителя 2…5, протокол `det2…det5`,
/// прокрутка высокого ответа и надстрочный показатель у матрицы.
library;

import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/editor/controller.dart';
import 'package:mymath_app/src/editor/editor_view.dart';
import 'package:mymath_app/src/editor/kind.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/ui/keyboard/math_keyboard.dart';
import 'package:mymath_app/src/ui/solution_preview.dart';

/// Протокол ввода: `{det3({1},…)}`.
///
/// Только то, что проверяет тест: листы и определители `det2…det5`. Карта
/// токенов — `backend/mymath_backend/input.py` (`KEYWORD_TO_TYPE`).
String _protocol(CoreNode node) {
  final children = node.children.map(_protocol).join(',');
  return switch (node.type) {
    CoreNodeType.determinant2 => '{det2($children)}',
    CoreNodeType.determinant3 => '{det3($children)}',
    CoreNodeType.determinant4 => '{det4($children)}',
    CoreNodeType.determinant5 => '{det5($children)}',
    CoreNodeType.constant || CoreNodeType.variable => '{${node.value}}',
    _ => '{${node.type.wire}($children)}',
  };
}

ENodeKind _determinantKind(int size) => switch (size) {
  2 => ENodeKind.determinant2,
  3 => ENodeKind.determinant3,
  4 => ENodeKind.determinant4,
  _ => ENodeKind.determinant5,
};

void main() {
  group('определитель в редакторе', () {
    test('размеры 2…5 дают det2…det5 без нового формата', () {
      const tokens = {2: 'det2', 3: 'det3', 4: 'det4', 5: 'det5'};
      for (final size in [2, 3, 4, 5]) {
        final editor = EditorController()
          ..insertTemplate(_determinantKind(size));
        final digits = [for (var i = 1; i <= size * size; i++) '$i'];
        for (final digit in digits) {
          editor.typeDigit(digit);
          editor.nextSlot();
        }
        final node = editor.toCoreNode();
        expect(
          node.children.map((cell) => cell.value),
          digits,
          reason: 'определитель $size×$size заполняется по строкам',
        );
        expect(
          _protocol(node),
          '{${tokens[size]}(${digits.map((d) => '{$d}').join(',')})}',
          reason: 'тот же протокол, что разбирает решатель',
        );
      }
    });

    test('3×3 сериализуется ровно как {det3(...)}', () {
      final editor = EditorController()..insertTemplate(ENodeKind.determinant3);
      for (final digit in '123456789'.split('')) {
        editor.typeDigit(digit);
        editor.nextSlot();
      }
      final node = editor.toCoreNode();
      expect(node.type, CoreNodeType.determinant3);
      expect(_protocol(node), '{det3({1},{2},{3},{4},{5},{6},{7},{8},{9})}');
    });
  });

  group('клавиша «Определитель»', () {
    Future<EditorController> pump(WidgetTester tester) async {
      final controller = EditorController();
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: MathKeyboard(controller: controller)),
        ),
      );
      await tester.pump();
      return controller;
    }

    testWidgets('стоит рядом с «Матрицей» и открывает диалог размера', (
      tester,
    ) async {
      await pump(tester);
      await tester.tap(
        find.byKey(const ValueKey('key:HELPER_SHOW_SECONDARY_SHEET')),
      );
      await tester.pump();

      final key = find.byKey(const ValueKey('key:OPERATOR_DETERMINANT'));
      expect(key, findsOneWidget);
      await tester.tap(key);
      await tester.pump();

      expect(find.text('Размер определителя'), findsOneWidget);
      // Тот же диалог, что у матрицы: те же кнопки и размер по умолчанию.
      expect(find.text('Отмена'), findsOneWidget);
      expect(find.text('Вставить'), findsOneWidget);
      expect(
        find.descendant(of: find.byType(AlertDialog), matching: find.text('2')),
        findsOneWidget,
      );
      expect(find.byTooltip('Увеличить Размер'), findsOneWidget);
    });

    testWidgets('вставляет определитель выбранного размера', (tester) async {
      final controller = await pump(tester);
      await tester.tap(
        find.byKey(const ValueKey('key:HELPER_SHOW_SECONDARY_SHEET')),
      );
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('key:OPERATOR_DETERMINANT')));
      await tester.pump();
      // 2×2 по умолчанию → 3×3.
      await tester.tap(find.byTooltip('Увеличить Размер'));
      await tester.pump();
      await tester.tap(find.text('Вставить'));
      await tester.pumpAndSettle();

      final node = controller.toCoreNode();
      expect(node.type, CoreNodeType.determinant3);
      expect(node.children, hasLength(9));
      expect(
        find.text('Строка 1, столбец 1'),
        findsOneWidget,
        reason: 'та же подсказка ячейки, что у матрицы',
      );
    });
  });

  group('P17: показатель у матрицы', () {
    testWidgets('−1 стоит наверху основания, а не на базовой линии', (
      tester,
    ) async {
      final editor = EditorController()..insertTemplate(ENodeKind.matrix2);
      for (final digit in '1234'.split('')) {
        editor.typeDigit(digit);
        editor.nextSlot();
      }
      expect(editor.cursor.steps, isEmpty, reason: 'курсор вышел из матрицы');
      editor.insertTemplate(ENodeKind.power);
      editor.insertOperator(ENodeKind.subtract);
      editor.typeDigit('1');

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: EditorView(controller: editor)),
        ),
      );
      await tester.pump();

      // Основание — матрица: её скобки выше показателя.
      final base = tester.getRect(find.text('['));
      final exponent = tester.getRect(find.text('−'));
      expect(
        exponent.center.dy,
        lessThan(base.center.dy - base.height * 0.2),
        reason: 'показатель должен быть надстрочным и у высокого основания',
      );
    });
  });

  group('P16: высокий ответ', () {
    testWidgets('прокручивается, а карточка ограничена', (tester) async {
      tester.view.physicalSize = const Size(400, 600);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      const answer =
          r'\begin{pmatrix}1&2&3&4\\5&6&7&8\\9&0&1&2\\'
          r'3&4&5&6\\7&8&9&0\\1&2&3&4\\5&6&7&8\\9&0&1&2\\'
          r'3&4&5&6\\7&8&9&0\end{pmatrix}';
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ListView(children: const [SolutionPreview(latex: answer)]),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);

      final answerBefore = tester.getRect(find.byType(Math));
      // Вертикальный ответ прокручивается и ограничен долей экрана; широкая
      // формула — горизонтально. Раньше был только горизонтальный скролл, и
      // высокая матрица обрезалась карточкой.
      final vertical = find.descendant(
        of: find.byType(SolutionPreview),
        matching: find.byWidgetPredicate(
          (widget) =>
              widget is SingleChildScrollView &&
              widget.scrollDirection == Axis.vertical,
        ),
      );
      expect(vertical, findsOneWidget);
      expect(
        tester.getRect(vertical).height,
        lessThanOrEqualTo(181),
        reason: 'карточка ограничена, а не растёт под высокий ответ',
      );
      final scrolled = tester
          .state<ScrollableState>(
            find
                .descendant(of: vertical, matching: find.byType(Scrollable))
                .first,
          )
          .position;
      expect(scrolled.pixels, 0);
      await tester.drag(vertical, const Offset(0, -60));
      await tester.pump();
      expect(
        scrolled.pixels,
        greaterThan(0),
        reason: 'высокий ответ прокручивается по вертикали',
      );
      expect(
        tester.getRect(find.byType(Math)).top,
        lessThan(answerBefore.top),
        reason: 'формула сдвинулась внутри карточки',
      );
    });
  });
}
