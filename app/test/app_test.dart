import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mymath_app/main.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/render/graph_view.dart';

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
    expect(find.byKey(const ValueKey('solve')), findsOneWidget);
  });

  testWidgets('подключена тёмная тема', (tester) async {
    await tester.pumpWidget(MyMathApp(baseUrl: 'http://test'));
    await tester.pump();
    final app = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(app.darkTheme, isNotNull);
    expect(app.themeMode, ThemeMode.system);
    expect(tester.takeException(), isNull);
  });

  testWidgets('у клавиш есть словесные метки для screen reader', (tester) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
    await tester.pump();
    expect(find.bySemanticsLabel('Дробь'), findsWidgets);
    expect(find.bySemanticsLabel('Плюс'), findsWidgets);
    handle.dispose();
    expect(tester.takeException(), isNull);
  });

  testWidgets('набор с клавиатуры и решение', (tester) async {
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
    await tester.pump();

    await _key(tester, '2');
    await _key(tester, '+');
    await _key(tester, '3');
    expect(tester.takeException(), isNull);

    await tester.tap(find.byKey(const ValueKey('solve')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('Сложите числа'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('выбранная команда уходит в action', (tester) async {
    Map<String, dynamic>? sent;
    final api = SolverApi(
      baseUrl: 'http://test',
      client: MockClient((request) async {
        sent = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          _solveBody,
          200,
          headers: const {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: api)));
    await tester.pump();

    await _key(tester, '2');
    await tester.tap(find.text('Разложить'));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('solve')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(sent?['action'], {'command': 'factor', 'args': <Object>[]});
    expect(tester.takeException(), isNull);
  });

  testWidgets('промежуток уходит в запрос', (tester) async {
    final view =
        TestWidgetsFlutterBinding.instance.platformDispatcher.views.first;
    view.physicalSize = const Size(2400, 2280);
    view.devicePixelRatio = 1;
    Map<String, dynamic>? sent;
    final api = SolverApi(
      baseUrl: 'http://test',
      client: MockClient((request) async {
        if (request.url.path.endsWith('/parse')) {
          final source = (jsonDecode(request.body) as Map)['source'] as String;
          final value = source.replaceAll(RegExp(r'[{}]'), '');
          return http.Response(
            jsonEncode({
              'node': {'type': 'CONSTANT', 'value': value},
            }),
            200,
            headers: const {'content-type': 'application/json; charset=utf-8'},
          );
        }
        sent = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          _solveBody,
          200,
          headers: const {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: api)));
    await tester.pump();

    await _key(tester, '2');
    await tester.tap(find.text('Промежуток'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.enterText(find.byType(TextField).at(0), '0');
    await tester.enterText(find.byType(TextField).at(1), '1');
    await tester.tap(find.text('Готово'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pump(const Duration(milliseconds: 300));

    await tester.tap(find.byKey(const ValueKey('solve')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(sent?['interval'], {
      'min': {'type': 'CONSTANT', 'value': '0'},
      'max': {'type': 'CONSTANT', 'value': '1'},
    });
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

  testWidgets('панель структур показывает систему и определители', (tester) async {
    // Широкий экран: все вкладки панелей помещаются без прокрутки.
    final view =
        TestWidgetsFlutterBinding.instance.platformDispatcher.views.first;
    view.physicalSize = const Size(2400, 2280);
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
    await tester.pump();

    await tester.tap(find.text('{}'));
    await tester.pump();
    expect(find.byKey(const ValueKey('key:|2×2|')), findsOneWidget);
    expect(find.byKey(const ValueKey('key:|3×3|')), findsOneWidget);
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

  testWidgets('шторка вектора шлёт команду с вторым вектором', (tester) async {
    final view =
        TestWidgetsFlutterBinding.instance.platformDispatcher.views.first;
    view.physicalSize = const Size(2400, 2280);
    view.devicePixelRatio = 1;
    Map<String, dynamic>? sent;
    final api = SolverApi(
      baseUrl: 'http://test',
      client: MockClient((request) async {
        sent = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          _solveBody,
          200,
          headers: const {'content-type': 'application/json; charset=utf-8'},
        );
      }),
    );
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: api)));
    await tester.pump();

    // Вектор ⟨1, 2⟩: шаблон, затем цифровая панель.
    await tester.tap(find.text('{}'));
    await tester.pump();
    await _key(tester, '⟨a,b⟩');
    await tester.tap(find.text('123'));
    await tester.pump();
    await _key(tester, '1');
    await _key(tester, '▼');
    await _key(tester, '2');

    // Шторка операций: второй вектор и скалярное произведение.
    await tester.tap(find.text('Вектор…'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.enterText(find.byType(TextField).at(0), '3, 4');
    await tester.tap(find.text('Скалярное'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(sent?['action']?['command'], 'vector_dot');
    final args = sent?['action']?['args'] as List<dynamic>?;
    expect(args, hasLength(1));
    expect((args!.first as Map)['type'], 'LIST');
    expect(tester.takeException(), isNull);
  });

  testWidgets('кнопка «График» показывает график', (tester) async {
    final view =
        TestWidgetsFlutterBinding.instance.platformDispatcher.views.first;
    view.physicalSize = const Size(2400, 2280);
    view.devicePixelRatio = 1;
    final api = SolverApi(
      baseUrl: 'http://test',
      client: MockClient(
        (request) async => http.Response(
          '{"variable":"x","xMin":-1,"xMax":1,"yMin":0,"yMax":1,'
          '"points":[[-1,1],[0,0],[1,1]]}',
          200,
          headers: const {'content-type': 'application/json; charset=utf-8'},
        ),
      ),
    );
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: api)));
    await tester.pump();
    await _key(tester, '1');
    await tester.tap(find.text('График'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(find.text('График y = f(x)'), findsOneWidget);
    expect(find.byType(GraphView), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('решённая задача попадает в блокнот', (tester) async {
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
    await tester.pump();

    await _key(tester, '2');
    await _key(tester, '+');
    await _key(tester, '3');
    await tester.tap(find.byKey(const ValueKey('solve')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    await tester.tap(find.byIcon(Icons.book_outlined));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(find.text('Блокнот'), findsOneWidget);
    expect(find.byType(Math), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('ссылка в пояснении открывает определение', (tester) async {
    final api = SolverApi(
      baseUrl: 'http://test',
      client: MockClient(
        (request) async => http.Response(
          '{"result":{"groups":[{"type":"VERTICAL","entries":[{"result":{"steps":[{"headers":[],"substeps":[{"description":{"type":"factorise_call"},"explanation":{"key":"factorise_call","text":"Factor","links":[{"label":"Factor","uuid":"1ceef362-dfb4-4ae6-ba5d-46dbd862a37b","definition":"Разложение на множители."}]}}]}]}}]}]}}',
          200,
          headers: const {'content-type': 'application/json; charset=utf-8'},
        ),
      ),
    );
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: api)));
    await tester.pump();
    await _key(tester, '2');
    await tester.tap(find.byKey(const ValueKey('solve')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    await tester.tap(find.text('Factor'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('Разложение на множители.'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
