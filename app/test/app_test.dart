import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mymath_app/main.dart';
import 'package:mymath_app/src/api/solver_api.dart';

/// Ответ бэкенда с одним шагом и итогом 5.
const String _solveBody = '''
{"result":{"solution":{"type":"CONSTANT","value":"5"},
 "groups":[{"type":"VERTICAL","entries":[{"result":{"steps":[
   {"headers":[],"substeps":[
     {"left":{"type":"ADD","children":[]},
      "right":{"type":"CONSTANT","value":"5"},
      "description":{"type":"add","args":[]},
      "explanation":{"key":"add","text":"Сложите числа"}}]}]}}]}]}}
''';

SolverApi _api() => SolverApi(
  baseUrl: 'http://test',
  client: MockClient(
    (request) async => http.Response(
      _solveBody,
      200,
      headers: const {'content-type': 'application/json; charset=utf-8'},
    ),
  ),
);

/// Нажать клавишу клавиатуры по её подписи.
Future<void> _key(WidgetTester tester, String label) async {
  await tester.tap(find.byKey(ValueKey('key:$label')));
  await tester.pump();
}

void main() {
  setUp(() {
    // Экран телефона: клавиатура должна помещаться без переполнения.
    final view =
        TestWidgetsFlutterBinding.instance.platformDispatcher.views.first;
    view.physicalSize = const Size(1080, 2280);
    view.devicePixelRatio = 3;
  });

  tearDown(() {
    final view =
        TestWidgetsFlutterBinding.instance.platformDispatcher.views.first;
    view.resetPhysicalSize();
    view.resetDevicePixelRatio();
  });

  testWidgets('экран целиком собирается без ошибок', (tester) async {
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(find.text('Решить'), findsOneWidget);
  });

  testWidgets('набор с клавиатуры и решение', (tester) async {
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
    await tester.pump();

    await _key(tester, '2');
    await _key(tester, '+');
    await _key(tester, '3');
    expect(tester.takeException(), isNull);

    await tester.tap(find.text('Решить'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('Сложите числа'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('переключение панелей показывает их клавиши', (tester) async {
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
    await tester.pump();

    expect(find.byKey(const ValueKey('key:7')), findsOneWidget);

    await tester.tap(find.text('f(x)'));
    await tester.pump();
    expect(find.byKey(const ValueKey('key:sin')), findsOneWidget);
    expect(find.byKey(const ValueKey('key:7')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('клавиша дроби поглощает набранное число', (tester) async {
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
    await tester.pump();

    await _key(tester, '7');
    await _key(tester, '⁄');
    // Числитель занят числом 7, курсор — в слоте знаменателя.
    expect(find.byKey(const ValueKey('slot:0.1')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
