/// Неподдержанные решателем клавиши видны, но приглушены.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/editor/controller.dart';
import 'package:mymath_app/src/ui/keyboard/photomath_keyboard.dart';

Finder get _dimmed =>
    find.byWidgetPredicate((widget) => widget is Opacity && widget.opacity == 0.35);

Future<void> _pump(WidgetTester tester) async {
  await tester.pumpWidget(
    MaterialApp(home: Scaffold(body: PhotomathKeyboard(controller: EditorController()))),
  );
  await tester.pump();
}

void main() {
  testWidgets('dead control key is dimmed on primary sheet', (tester) async {
    await _pump(tester);
    // Служебный ряд: перевод строки неподдержан (`_unsupported`), остальные
    // клавиши рабочие — приглушена ровно одна.
    expect(_dimmed, findsOneWidget);
  });

  testWidgets('dead a_n key is dimmed on secondary sheet', (tester) async {
    await _pump(tester);
    // Первый InkWell служебного ряда — тоггл `f ∫ <>` на вторичный экран.
    await tester.tap(find.byType(InkWell).first);
    await tester.pump();
    // Вторичный экран: `aₙ` без действия плюс перевод строки — приглушены две.
    expect(_dimmed, findsNWidgets(2));
  });
}
