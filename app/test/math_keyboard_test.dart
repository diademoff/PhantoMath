/// Неподдержанные решателем клавиши видны, но приглушены.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/editor/controller.dart';
import 'package:mymath_app/src/ui/keyboard/math_keyboard.dart';

Finder get _dimmed => find.byWidgetPredicate(
  (widget) => widget is Opacity && widget.opacity == 0.35,
);

Future<void> _pump(WidgetTester tester) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(body: MathKeyboard(controller: EditorController())),
    ),
  );
  await tester.pump();
}

void main() {
  testWidgets('all primary keys are live', (tester) async {
    await _pump(tester);
    // Служебный ряд и базовый экран: перевод строки теперь вводит
    // разделитель, остальные клавиши были рабочими — приглушённых нет.
    expect(_dimmed, findsNothing);
  });

  testWidgets('dead a_n key is dimmed on secondary sheet', (tester) async {
    await _pump(tester);
    // Первый InkWell служебного ряда — тоггл `f ∫ <>` на вторичный экран.
    await tester.tap(find.byType(InkWell).first);
    await tester.pump();
    // Вторичный экран: только `aₙ` без действия.
    expect(_dimmed, findsOneWidget);
  });
}
