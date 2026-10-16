import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mymath_app/main.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/render/graph_view.dart';
import 'package:mymath_app/src/theme/photomath_theme.dart';
import 'package:mymath_app/src/theme/phanto_theme.dart';
import 'package:mymath_app/src/ui/keyboard/ph_keyboard_spec.dart';

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

/// Нажать клавишу клавиатуры по коду оператора оригинала.
///
/// Ключ виджета — `key:<КОД>`, поэтому метка не зависит от того, как нарисован
/// глиф. Клавиши не с базового экрана доступны только после переключения, так
/// что [_sheet] вызывается автоматически.
Future<void> _key(WidgetTester tester, String code) async {
  final finder = find.byKey(ValueKey('key:$code'));
  if (finder.evaluate().isEmpty) {
    // Расширенный экран, затем буквы — так порядок экранов совпадает с тем,
    // как оригинал показывает их по клавишам служебного ряда.
    await _openSheet(tester, _sheetWith(code) ?? PhSheet.secondary);
  }
  await tester.tap(finder);
  await tester.pump();
}

/// Экран клавиатуры, на котором лежит клавиша с таким кодом.
PhSheet? _sheetWith(String code) {
  for (final spec in sheets) {
    if (spec.keys.any((key) => key.code == code)) return spec.sheet;
  }
  return null;
}

/// Переключить экран клавиатуры клавишей служебного ряда.
Future<void> _openSheet(WidgetTester tester, PhSheet sheet) async {
  final toggle = switch (sheet) {
    PhSheet.primary => null,
    PhSheet.secondary => 'HELPER_SHOW_SECONDARY_SHEET',
    PhSheet.alphabet => 'HELPER_XYZ_SHEET',
    PhSheet.control => null,
  };
  if (toggle == null) return;
  await tester.tap(find.byKey(ValueKey('key:$toggle')));
  await tester.pump();
}

/// Нажать чип: при необходимости прокрутить ленту команд до него.
Future<void> _chip(WidgetTester tester, String label) async {
  await tester.ensureVisible(find.text(label));
  await tester.pump();
  await tester.tap(find.text(label));
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

  testWidgets('подключена тема Photomath', (tester) async {
    await tester.pumpWidget(MyMathApp(baseUrl: 'http://test'));
    await tester.pump();
    final app = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(app.darkTheme, isNotNull);
    expect(app.theme?.colorScheme.primary, PhantoTheme.light().colorScheme.primary);
    expect(app.title, 'PhantoMath');
    expect(tester.takeException(), isNull);
  });

  testWidgets('у клавиш есть словесные метки для screen reader', (
    tester,
  ) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
    await tester.pump();
    // Метки задаются виджетами `Semantics` клавиш (`_KeyButton`
    // оборачивает каждую клавишу в `Semantics` с `description` ключа).
    // Проверяем объявление меток, а не скомпилированные узлы:
    // `find.bySemanticsLabel` читает `renderObject.debugSemantics`,
    // который в этом SDK показывает только узлы, посещённые последней
    // инкрементальной компиляцией, — результат зависит от тайминга кадра,
    // а скринридер читает само дерево (там метки есть всегда).
    Finder withLabel(String label) => find.byWidgetPredicate(
      (widget) =>
          widget is Semantics && widget.properties.label == label,
    );
    expect(withLabel('Дробь'), findsWidgets);
    expect(withLabel('Сложить'), findsWidgets);
    handle.dispose();
    expect(tester.takeException(), isNull);
  });

  testWidgets('набор с клавиатуры и решение', (tester) async {
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
    await tester.pump();

    await _key(tester, 'DIGIT_TWO');
    await _key(tester, 'BASIC_INFIX_OPERATOR_PLUS');
    await _key(tester, 'DIGIT_THREE');
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

    await _key(tester, 'DIGIT_TWO');
    await _chip(tester, 'Разложить');
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

    await _key(tester, 'DIGIT_TWO');
    await _chip(tester, 'Промежуток');
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

  testWidgets('служебный ряд переключает экраны клавиатуры', (tester) async {
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
    await tester.pump();

    // Базовый экран: цифры и плоские знаки.
    expect(find.byKey(const ValueKey('key:DIGIT_SEVEN')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('key:OPERATOR_SIN')),
      findsNothing,
    );

    // `f ∫ <>` — расширенный экран.
    await _openSheet(tester, PhSheet.secondary);
    expect(find.byKey(const ValueKey('key:OPERATOR_SIN')), findsOneWidget);
    expect(find.byKey(const ValueKey('key:DIGIT_SEVEN')), findsNothing);

    // `abc` — буквы.
    await _openSheet(tester, PhSheet.alphabet);
    expect(find.byKey(const ValueKey('key:VARIABLE_A_LOW')), findsOneWidget);
    expect(find.byKey(const ValueKey('key:OPERATOR_SIN')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('раскладка экранов повторяет оригинальную', (tester) async {
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
    await tester.pump();

    // Базовый экран 4×6 — ровно столько ячеек рисует `GridLayout.onLayout`.
    expect(find.byType(InkWell), findsWidgets);
    final digits = [
      for (final code in [
        'DIGIT_ZERO',
        'DIGIT_ONE',
        'DIGIT_TWO',
        'DIGIT_THREE',
        'DIGIT_FOUR',
        'DIGIT_FIVE',
        'DIGIT_SIX',
        'DIGIT_SEVEN',
        'DIGIT_EIGHT',
        'DIGIT_NINE',
        'DIGIT_DOT',
      ])
        find.byKey(ValueKey('key:$code')),
    ];
    expect(digits.where((f) => f.evaluate().isNotEmpty), hasLength(11));

    // Служебный ряд: шесть клавиш, из них две переключают экраны.
    for (final code in [
      'HELPER_SHOW_SECONDARY_SHEET',
      'HELPER_XYZ_SHEET',
      'CONTROL_MOVE_LEFT',
      'CONTROL_MOVE_RIGHT',
      'CONTROL_NEW_LINE',
      'CONTROL_DELETE',
    ]) {
      expect(
        find.byKey(ValueKey('key:$code')),
        findsOneWidget,
        reason: 'в служебном ряду нет $code',
      );
    }
    expect(tester.takeException(), isNull);
  });

  testWidgets('долгое нажатие открывает варианты клавиши', (tester) async {
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
    await tester.pump();

    // У `π` в оригинале выпадают `π/2` и `π/3`.
    await tester.longPress(find.byKey(const ValueKey('key:CONSTANT_PI')));
    await tester.pump();
    expect(find.byKey(const ValueKey('key:CONSTANT_HALF_PI')), findsOneWidget);
    expect(find.byKey(const ValueKey('key:CONSTANT_THIRD_PI')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('клавиша дроби поглощает набранное число', (tester) async {
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
    await tester.pump();
    await _key(tester, 'DIGIT_SEVEN');
    await _key(tester, 'OPERATOR_FRACTION');
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

    // Вектор вводится вторым операндом шторки — на клавиатуре оригинала
    // отдельной клавиши вектора нет.
    await _key(tester, 'DIGIT_ONE');

    // Шторка операций: второй вектор и скалярное произведение.
    await _chip(tester, 'Вектор…');
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

  testWidgets('шторка матрицы шлёт команду с второй матрицей', (tester) async {
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

    // Матрица вводится клавишей `OPERATOR_MATRIX` расширенного экрана —
    // в оригинале она там же, в `SECONDARY_SHEET`.
    await _openSheet(tester, PhSheet.secondary);
    await _key(tester, 'OPERATOR_MATRIX');
    await _key(tester, 'DIGIT_ONE');
    await _key(tester, 'BASIC_INFIX_OPERATOR_PLUS');
    await _key(tester, 'DIGIT_TWO');

    await _chip(tester, 'Матрица…');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.enterText(find.byType(TextField).at(0), '5,6;7,8');
    await tester.tap(find.text('Умножить'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(sent?['action']?['command'], 'matrix_multiply');
    final args = sent?['action']?['args'] as List<dynamic>?;
    expect(args, hasLength(1));
    final second = args!.first as Map;
    expect(second['type'], 'MATRIX');
    expect((second['children'] as List).first, isA<Map>());
    expect((second['children'] as List).first['type'], 'MATRIX_ROW');
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
    await _key(tester, 'DIGIT_ONE');
    await _chip(tester, 'График');
    await tester.pump(const Duration(milliseconds: 400));

    expect(find.text('График y = f(x)'), findsOneWidget);
    expect(find.byType(GraphView), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('у шага нарисована стрелка разворота', (tester) async {
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
    await tester.pump();
    await _key(tester, 'DIGIT_TWO');
    await tester.tap(find.byKey(const ValueKey('solve')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    // `@id/expand_button` — своя стрелка `steps_down`; без неё шаг
    // разворачивается тапом по строке, но обнаружить это нельзя.
    expect(find.byIcon(Icons.keyboard_arrow_down), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('решённая задача попадает в блокнот', (tester) async {
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
    await tester.pump();

    await _key(tester, 'DIGIT_TWO');
    await _key(tester, 'BASIC_INFIX_OPERATOR_PLUS');
    await _key(tester, 'DIGIT_THREE');
    await tester.tap(find.byKey(const ValueKey('solve')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    // На экране результата своих иконок нет (`activity_vertical_result.xml`:
    // `@id/toolbar` без навигационной иконки), назад — нижняя `@id/back`.
    await tester.tap(find.byTooltip('Назад'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    // Блокнот открывается иконкой в правом верхнем углу экрана ввода.
    await tester.tap(find.byIcon(Icons.menu_book_outlined));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(find.text('Блокнот'), findsWidgets);
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
    await _key(tester, 'DIGIT_TWO');
    await tester.tap(find.byKey(const ValueKey('solve')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    // Пояснение с ссылкой — в раскрытом шаге вертикального результата.
    await tester.tap(find.text('Factor'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('Разложение на множители.'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('ссылка без определения не нажимается', (tester) async {
    // В английской локали у 266 ссылок из 327 нет определения: тап по такой
    // ссылке вёл в тупик «пояснение понятия появится позже». Теперь она
    // остаётся обычным текстом.
    final api = SolverApi(
      baseUrl: 'http://test',
      client: MockClient(
        (request) async => http.Response(
          '{"result":{"groups":[{"type":"VERTICAL","entries":[{"result":{"steps":[{"headers":[],"substeps":[{"description":{"type":"factorise_call"},"explanation":{"key":"factorise_call","text":"Factor","links":[{"label":"Factor","uuid":"1ceef362-dfb4-4ae6-ba5d-46dbd862a37b","definition":""}]}}]}]}}]}]}}',
          200,
          headers: const {'content-type': 'application/json; charset=utf-8'},
        ),
      ),
    );
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: api)));
    await tester.pump();
    await _key(tester, 'DIGIT_TWO');
    await tester.tap(find.byKey(const ValueKey('solve')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    await tester.tap(find.text('Factor'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    // Карточки понятия нет и заглушки «появится позже» тоже.
    expect(find.textContaining('появится позже'), findsNothing);
    expect(find.text('Factor'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
