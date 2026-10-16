/// Прогон на эмуляторе: настоящие кнопки, настоящий бэкенд по HTTP.
///
/// Запуск:
/// ```bash
/// cd backend && uv run uvicorn mymath_backend.api:app --host 0.0.0.0 --port 8000
/// cd app && flutter test integration_test/smoke_test.dart \
///   -d emulator-5554 --dart-define=MYMATH_API=http://10.0.2.2:8000
/// ```
///
/// Мигающий курсор не даёт `pumpAndSettle` завершиться, поэтому ожидание —
/// опросом дерева с фиксированными шагами времени.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:mymath_app/main.dart' as app;

Future<void> _tapKey(WidgetTester tester, String code) async {
  await tester.tap(find.byKey(ValueKey('key:$code')));
  await tester.pump();
}

/// Долгое нажатие: открывает выпадающее меню клавиши.
Future<void> _longPressKey(WidgetTester tester, String code) async {
  await tester.longPress(find.byKey(ValueKey('key:$code')));
  await tester.pump();
}

Future<void> _digits(WidgetTester tester, String digits) async {
  const names = {
    '0': 'DIGIT_ZERO',
    '1': 'DIGIT_ONE',
    '2': 'DIGIT_TWO',
    '3': 'DIGIT_THREE',
    '4': 'DIGIT_FOUR',
    '5': 'DIGIT_FIVE',
    '6': 'DIGIT_SIX',
    '7': 'DIGIT_SEVEN',
    '8': 'DIGIT_EIGHT',
    '9': 'DIGIT_NINE',
    '.': 'DIGIT_DOT',
  };
  for (final d in digits.split('')) {
    await _tapKey(tester, names[d]!);
  }
}

/// Ждать экрана результата или строки ошибки.
Future<bool> _waitSolved(WidgetTester tester) async {
  for (var i = 0; i < 60; i++) {
    await tester.pump(const Duration(milliseconds: 250));
    if (find.byTooltip('Назад').evaluate().isNotEmpty) return true;
    if (_errorText(tester) != null) return false;
  }
  return find.byTooltip('Назад').evaluate().isNotEmpty;
}

String? _errorText(WidgetTester tester) {
  for (final widget in tester.widgetList<Text>(find.byType(Text))) {
    final data = widget.data;
    if (data != null &&
        (data.contains('деление на ноль') ||
            data.contains('факториал') ||
            data.contains('не решен') ||
            data.contains('Задача не решена'))) {
      return data;
    }
  }
  return null;
}

Future<void> _backToEditor(WidgetTester tester) async {
  final back = find.byTooltip('Назад');
  if (back.evaluate().isNotEmpty) {
    await tester.tap(back);
    await tester.pump();
  }
}

Future<void> _clearEditor(WidgetTester tester) async {
  // Кнопку «Очистить» в углу иногда перекрывает оверлей перехода, поэтому
  // стираем клавишей ⌫: на пустом документе она no-op, лишние нажатия
  // безопасны.
  for (var i = 0; i < 40; i++) {
    await tester.tap(find.byKey(const ValueKey('key:CONTROL_DELETE')));
    await tester.pump();
  }
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  Future<void> shot(String name) async {
    // Только маркер в лог: скриншоты через takeScreenshot виснут на
    // программном GPU эмулятора, экраны смотрим отдельным screencap.
    // ignore: avoid_print
    print('STAGE $name done');
  }

  testWidgets('smoke: кнопки, решение, ошибки, система с ⏎', (tester) async {
    app.main();
    await tester.pump();
    await tester.pump(const Duration(seconds: 2));

    // 1. Арифметика: 2+3×4 = 14.
    await _digits(tester, '2');
    await _tapKey(tester, 'BASIC_INFIX_OPERATOR_PLUS');
    await _digits(tester, '3');
    await _tapKey(tester, 'BASIC_INFIX_OPERATOR_MULTIPLY');
    await _digits(tester, '4');
    await tester.tap(find.byKey(const ValueKey('solve')));
    expect(await _waitSolved(tester), isTrue, reason: 'арифметика не решилась');
    await shot('arithmetic');
    await _backToEditor(tester);
    await _clearEditor(tester);

    // 2. Уравнение: x+1=3.
    await _tapKey(tester, 'VARIABLE_X_LOW');
    await _tapKey(tester, 'BASIC_INFIX_OPERATOR_PLUS');
    await _digits(tester, '1');
    await _tapKey(tester, 'BASIC_INFIX_OPERATOR_EQUALS');
    await _digits(tester, '3');
    await tester.tap(find.byKey(const ValueKey('solve')));
    expect(await _waitSolved(tester), isTrue, reason: 'уравнение не решилось');
    await shot('equation');
    await _backToEditor(tester);
    await _clearEditor(tester);

    // 3. Ноль в отрицательной степени: 0^(−1) — ошибка, а не падение.
    // Степень xⁿ — в выпадающем меню клавиши x².
    await _digits(tester, '0');
    await _longPressKey(tester, 'OPERATOR_POWER_TWO');
    await _tapKey(tester, 'OPERATOR_POWER');
    await _tapKey(tester, 'BASIC_INFIX_OPERATOR_MINUS');
    await _digits(tester, '1');
    await tester.tap(find.byKey(const ValueKey('solve')));
    expect(await _waitSolved(tester), isFalse, reason: 'ожидалась ошибка');
    expect(find.text('деление на ноль'), findsOneWidget);
    await shot('zero_power_error');
    await _clearEditor(tester);

    // 4. Система через ⏎: x+y=3, x−y=1 (y — в меню клавиши x).
    await _tapKey(tester, 'VARIABLE_X_LOW');
    await _tapKey(tester, 'BASIC_INFIX_OPERATOR_PLUS');
    await _longPressKey(tester, 'VARIABLE_X_LOW');
    await _tapKey(tester, 'VARIABLE_Y_LOW');
    await _tapKey(tester, 'BASIC_INFIX_OPERATOR_EQUALS');
    await _digits(tester, '3');
    await _tapKey(tester, 'CONTROL_NEW_LINE');
    await _tapKey(tester, 'VARIABLE_X_LOW');
    await _tapKey(tester, 'BASIC_INFIX_OPERATOR_MINUS');
    await _longPressKey(tester, 'VARIABLE_X_LOW');
    await _tapKey(tester, 'VARIABLE_Y_LOW');
    await _tapKey(tester, 'BASIC_INFIX_OPERATOR_EQUALS');
    await _digits(tester, '1');
    await tester.tap(find.byKey(const ValueKey('solve')));
    expect(await _waitSolved(tester), isTrue, reason: 'система не решилась');
    await shot('system');
    await _backToEditor(tester);
    await _clearEditor(tester);

    // 5. Факториал: 5! = 120 (! — на расширенной панели).
    await _digits(tester, '5');
    await _tapKey(tester, 'HELPER_SHOW_SECONDARY_SHEET');
    await _tapKey(tester, 'BASIC_INFIX_OPERATOR_FACTORIAL');
    await tester.tap(find.byKey(const ValueKey('solve')));
    expect(await _waitSolved(tester), isTrue, reason: 'факториал не решился');
    await shot('factorial');
    await _backToEditor(tester);
    await _clearEditor(tester);

    // 6. Невалидный факториал: (2.5)! — ошибка, а не падение.
    await _digits(tester, '2.5');
    await _tapKey(tester, 'HELPER_SHOW_SECONDARY_SHEET');
    await _tapKey(tester, 'BASIC_INFIX_OPERATOR_FACTORIAL');
    await tester.tap(find.byKey(const ValueKey('solve')));
    expect(await _waitSolved(tester), isFalse, reason: 'ожидалась ошибка');
    expect(find.textContaining('факториал'), findsWidgets);
    await shot('factorial_error');
  });
}
