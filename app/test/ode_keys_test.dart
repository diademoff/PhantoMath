/// Постфиксный штрих `y′`: клавиша, узел `PRIME`, протокол и подпись решения.
library;

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mymath_app/main.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/editor/controller.dart';
import 'package:mymath_app/src/editor/kind.dart';
import 'package:mymath_app/src/i18n.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/render/latex.dart';

/// Ответ бэкенда: одного шага достаточно, тест смотрит только на запрос.
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

/// Строка протокола ввода (`backend/mymath_backend/input.py`).
///
/// `bracket({0})` — имя узла `BRACKET` в протоколе ввода;
/// приложение шлёт тот же узел в AST-JSON (`MULTIPLY_IMPLICIT` + `BRACKET`).
/// Проверяем только то, что набирает тест: равенство, систему, неявное
/// произведение, скобки и штрих. Карта токенов — `KEYWORD_TO_TYPE`.
String _protocol(CoreNode node) {
  if (node.type == CoreNodeType.constant ||
      node.type == CoreNodeType.variable) {
    return '{${node.value}}';
  }
  final children = node.children.map(_protocol).join(',');
  if (node.type == CoreNodeType.system) return 'system($children)';
  final name = switch (node.type) {
    CoreNodeType.equals => '=',
    CoreNodeType.add => 'add',
    CoreNodeType.subtract => 'sub',
    CoreNodeType.multiply => 'mul',
    CoreNodeType.multiplyImplicit => 'muli',
    CoreNodeType.divide => 'div',
    CoreNodeType.bracket => 'bracket',
    CoreNodeType.prime => 'prime',
    CoreNodeType.derivation1 => 'derivation_prime',
    CoreNodeType.derivation2Prime => 'derivation2_prime',
    CoreNodeType.power => 'pow',
    CoreNodeType.sin => 'sin',
    _ => node.type.wire.toLowerCase(),
  };
  return '{$name($children)}';
}

/// Нажать клавишу клавиатуры по коду оператора (как `_key` в app_test).
///
/// Экраны переключаются тем же перебором, что в `tools/device/drive.py`:
/// «Функции», «Функции», «Буквы», «Буквы» покрывают все три экрана.
Future<void> _key(WidgetTester tester, String code) async {
  final finder = find.byKey(ValueKey('key:$code'));
  for (final toggle in const [
    null,
    'HELPER_SHOW_SECONDARY_SHEET',
    'HELPER_SHOW_SECONDARY_SHEET',
    'HELPER_XYZ_SHEET',
    'HELPER_XYZ_SHEET',
  ]) {
    if (finder.evaluate().isNotEmpty) {
      await tester.tap(finder);
      await tester.pump();
      return;
    }
    if (toggle == null) continue;
    await tester.tap(find.byKey(ValueKey('key:$toggle')));
    await tester.pump();
  }
  fail('на клавиатуре нет клавиши $code');
}

void main() {
  setUp(() {
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

  group('клавиша «Штрих»', () {
    test('оборачивает операнд слева в PRIME, курсор — за штрихом', () {
      final controller = EditorController()..typeVariable('y');
      controller.insertTemplate(ENodeKind.prime);

      final node = controller.toCoreNode();
      expect(node.type, CoreNodeType.prime);
      expect(node.children.single.type, CoreNodeType.variable);
      expect(node.children.single.value, 'y');
      expect(controller.cursor.steps, isEmpty, reason: 'курсор вышел из узла');
      expect(controller.cursor.offset, 1);

      // Так же набирается `y′(0)` и `y′ = …`: скобка и равно идут в тот же ряд.
      controller.insertTemplate(ENodeKind.bracket);
      controller.typeDigit('0');
      controller.closeBracket();
      expect(controller.toCoreNode().type, CoreNodeType.multiplyImplicit);
    });

    test('два нажатия дают PRIME(PRIME(y))', () {
      final controller = EditorController()..typeVariable('y');
      controller.insertTemplate(ENodeKind.prime);
      controller.insertTemplate(ENodeKind.prime);

      final node = controller.toCoreNode();
      expect(node.type, CoreNodeType.prime);
      expect(node.children.single.type, CoreNodeType.prime);
      expect(node.children.single.children.single.value, 'y');
    });

    test('с пустым операндом оставляет слот, как x²', () {
      final controller = EditorController()..insertTemplate(ENodeKind.prime);
      final node = controller.toCoreNode();
      expect(node.type, CoreNodeType.prime);
      expect(node.children.single.type, CoreNodeType.empty);
      expect(controller.cursor.steps, hasLength(1));

      controller.typeVariable('y');
      expect(controller.toCoreNode().children.single.value, 'y');
    });
  });

  group('протокол', () {
    test('y′ = xy → {=({prime({y})},{muli({x},{y})})}', () {
      final controller = EditorController()
        ..typeVariable('y')
        ..insertTemplate(ENodeKind.prime)
        ..insertOperator(ENodeKind.equals)
        ..typeVariable('x')
        ..typeVariable('y');
      expect(
        _protocol(controller.toCoreNode()),
        '{=({prime({y})},{muli({x},{y})})}',
      );
    });

    test('y″ − 3y′ + 2y = 0 → prime(prime(y)) без новых токенов', () {
      final controller = EditorController()
        ..typeVariable('y')
        ..insertTemplate(ENodeKind.prime)
        ..insertTemplate(ENodeKind.prime)
        ..insertOperator(ENodeKind.subtract)
        ..typeDigit('3')
        ..typeVariable('y')
        ..insertTemplate(ENodeKind.prime)
        ..insertOperator(ENodeKind.add)
        ..typeDigit('2')
        ..typeVariable('y')
        ..insertOperator(ENodeKind.equals)
        ..typeDigit('0');

      expect(
        _protocol(controller.toCoreNode()),
        '{=({add({sub({prime({prime({y})})},'
        '{muli({3},{prime({y})})})},{muli({2},{y})})},{0})}',
      );
    });

    test('y(0) = 1 в системе → y·(0), как читает бэкенд', () {
      final controller = EditorController()
        ..typeVariable('y')
        ..insertTemplate(ENodeKind.prime)
        ..insertOperator(ENodeKind.equals)
        ..typeVariable('x')
        ..typeVariable('y')
        ..newLine()
        ..typeVariable('y')
        ..insertTemplate(ENodeKind.bracket)
        ..typeDigit('0')
        ..closeBracket()
        ..insertOperator(ENodeKind.equals)
        ..typeDigit('1');

      expect(
        _protocol(controller.toCoreNode()),
        'system({=({prime({y})},{muli({x},{y})})},'
        '{=({muli({y},{bracket({0})})},{1})})',
      );
    });

    test('y′(0) = 0 в системе → PRIME(y)·(0)', () {
      final controller = EditorController()
        ..typeVariable('y')
        ..insertTemplate(ENodeKind.prime)
        ..insertTemplate(ENodeKind.bracket)
        ..typeDigit('0')
        ..closeBracket()
        ..insertOperator(ENodeKind.equals)
        ..typeDigit('0');

      expect(
        _protocol(controller.toCoreNode()),
        '{=({muli({prime({y})},{bracket({0})})},{0})}',
      );
    });

    test('Коши: y″ + y = 0, y(0) = 0, y′(0) = 1', () {
      final controller = EditorController()
        ..typeVariable('y')
        ..insertTemplate(ENodeKind.prime)
        ..insertTemplate(ENodeKind.prime)
        ..insertOperator(ENodeKind.add)
        ..typeVariable('y')
        ..insertOperator(ENodeKind.equals)
        ..typeDigit('0')
        ..newLine()
        ..typeVariable('y')
        ..insertTemplate(ENodeKind.bracket)
        ..typeDigit('0')
        ..closeBracket()
        ..insertOperator(ENodeKind.equals)
        ..typeDigit('0')
        ..newLine()
        ..typeVariable('y')
        ..insertTemplate(ENodeKind.prime)
        ..insertTemplate(ENodeKind.bracket)
        ..typeDigit('0')
        ..closeBracket()
        ..insertOperator(ENodeKind.equals)
        ..typeDigit('1');

      expect(
        _protocol(controller.toCoreNode()),
        'system({=({add({prime({prime({y})})},{y})},{0})},'
        '{=({muli({y},{bracket({0})})},{0})},'
        '{=({muli({prime({y})},{bracket({0})})},{1})})',
      );
    });
  });

  group('рендер', () {
    CoreNode variable(String name) =>
        CoreNode(type: CoreNodeType.variable, value: name);

    test('PRIME(PRIME(y)) — y″ одной группой', () {
      final node = CoreNode(
        type: CoreNodeType.prime,
        children: [
          CoreNode(type: CoreNodeType.prime, children: [variable('y')]),
        ],
      );
      expect(nodeToLatex(node), r"{y}''");
    });

    test('C1 и C2 рисуются как C₁ и C₂, C — без индекса', () {
      expect(nodeToLatex(variable('C1')), r'C_{1}');
      expect(nodeToLatex(variable('C2')), r'C_{2}');
      expect(nodeToLatex(variable('C')), 'C');
      // Только одна латинская буква и цифры: `x1` — тоже индекс, `C_1` — нет.
      expect(nodeToLatex(variable('x1')), r'x_{1}');
      expect(nodeToLatex(variable('C_1')), r'C\_1');
    });
  });

  group('подпись кнопки решения', () {
    testWidgets('уравнение с y′ — «Решить уравнение»', (tester) async {
      await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
      await tester.pump();

      await _key(tester, 'VARIABLE_Y_LOW');
      await _key(tester, 'OPERATOR_PRIME');
      await _key(tester, 'BASIC_INFIX_OPERATOR_PLUS');
      await _key(tester, 'VARIABLE_Y_LOW');
      await _key(tester, 'BASIC_INFIX_OPERATOR_EQUALS');
      await _key(tester, 'VARIABLE_X_LOW');

      expect(find.text('Решить уравнение'), findsOneWidget);
      expect(find.text('Решить'), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('система с y′ — тоже «Решить уравнение»', (tester) async {
      await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
      await tester.pump();

      await _key(tester, 'VARIABLE_Y_LOW');
      await _key(tester, 'OPERATOR_PRIME');
      await _key(tester, 'BASIC_INFIX_OPERATOR_EQUALS');
      await _key(tester, 'DIGIT_TWO');
      await _key(tester, 'VARIABLE_X_LOW');
      await _key(tester, 'CONTROL_NEW_LINE');
      await _key(tester, 'VARIABLE_Y_LOW');
      await _key(tester, 'OPERATOR_LEFT_BRACKET');
      await _key(tester, 'DIGIT_ZERO');
      await _key(tester, 'OPERATOR_RIGHT_BRACKET');
      await _key(tester, 'BASIC_INFIX_OPERATOR_EQUALS');
      await _key(tester, 'DIGIT_ONE');

      expect(find.text('Решить уравнение'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('смена языка решает задачу заново на новом языке', (
      tester,
    ) async {
      addTearDown(() => appLocale = 'ru');
      final locales = <String>[];
      final api = SolverApi(
        baseUrl: 'http://test',
        client: MockClient((request) async {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          if (body.containsKey('locale')) locales.add(body['locale'] as String);
          return http.Response(
            _solveBody,
            200,
            headers: const {'content-type': 'application/json; charset=utf-8'},
          );
        }),
      );
      await tester.pumpWidget(MaterialApp(home: SolvePage(api: api)));
      await tester.pump();
      Future<void> settle() async {
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 600));
      }

      await _key(tester, 'VARIABLE_X_LOW');
      await _key(tester, 'BASIC_INFIX_OPERATOR_EQUALS');
      await _key(tester, 'DIGIT_TWO');
      await settle();
      expect(locales, isNotEmpty);
      expect(locales.last, isNot('en'));

      await tester.tap(find.byTooltip('Настройки'));
      await settle();
      await tester.tap(find.byKey(const ValueKey('locale:en')));
      await settle();
      await tester.pageBack();
      await settle();

      // The answer cached in Russian is not reused: a new request goes out in English.
      expect(locales.last, 'en');
      expect(tester.takeException(), isNull);
    });

    testWidgets('по-английски — «Solve the equation»', (tester) async {
      addTearDown(() => appLocale = 'ru');
      await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
      await tester.pump();

      // Язык пояснений (Настройки → English): подпись кнопки следует за ним.
      Future<void> settle() async {
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 600));
      }

      await tester.tap(find.byTooltip('Настройки'));
      await settle();
      await tester.tap(find.byKey(const ValueKey('locale:en')));
      await settle();
      await tester.pageBack();
      await settle();

      await _key(tester, 'VARIABLE_Y_LOW');
      await _key(tester, 'OPERATOR_PRIME');
      await _key(tester, 'BASIC_INFIX_OPERATOR_EQUALS');
      await _key(tester, 'VARIABLE_X_LOW');

      expect(find.text('Solve the equation'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('у xy′ = y нет «Разложить на множители», у xy = y есть', (
      tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
      await tester.pump();

      await _key(tester, 'VARIABLE_X_LOW');
      await _key(tester, 'VARIABLE_Y_LOW');
      await _key(tester, 'OPERATOR_PRIME');
      await _key(tester, 'BASIC_INFIX_OPERATOR_EQUALS');
      await _key(tester, 'VARIABLE_Y_LOW');
      await tester.tap(find.text('Решить уравнение'));
      await tester.pumpAndSettle();
      // the steps screen is open; an ODE has no other actions to offer
      expect(find.byTooltip('Назад'), findsOneWidget);
      expect(find.text('Другие действия'), findsNothing);
      expect(find.text('Разложить на множители'), findsNothing);

      await tester.pumpWidget(
        MaterialApp(
          home: SolvePage(key: UniqueKey(), api: _api()),
        ),
      );
      await tester.pump();
      await _key(tester, 'VARIABLE_X_LOW');
      await _key(tester, 'VARIABLE_Y_LOW');
      await _key(tester, 'BASIC_INFIX_OPERATOR_EQUALS');
      await _key(tester, 'VARIABLE_Y_LOW');
      await tester.tap(find.text('Решить'));
      await tester.pumpAndSettle();
      expect(find.text('Разложить на множители'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('обычное уравнение остаётся «Решить»', (tester) async {
      await tester.pumpWidget(MaterialApp(home: SolvePage(api: _api())));
      await tester.pump();

      await _key(tester, 'VARIABLE_X_LOW');
      await _key(tester, 'BASIC_INFIX_OPERATOR_EQUALS');
      await _key(tester, 'DIGIT_ONE');

      expect(find.text('Решить'), findsOneWidget);
      expect(find.text('Решить уравнение'), findsNothing);
      expect(tester.takeException(), isNull);
    });
  });

  test('AST отправки: PRIME(y)·(0) — MULTIPLY_IMPLICIT(PRIME, BRACKET)', () {
    final controller = EditorController()
      ..typeVariable('y')
      ..insertTemplate(ENodeKind.prime)
      ..insertTemplate(ENodeKind.bracket)
      ..typeDigit('0')
      ..closeBracket();
    final node = controller.toCoreNode();
    expect(node.type, CoreNodeType.multiplyImplicit);
    expect(node.children[0].type, CoreNodeType.prime);
    expect(node.children[1].type, CoreNodeType.bracket);
    final json = jsonEncode(node.toJson());
    expect(json, contains('"type":"PRIME"'));
    expect(json, contains('"type":"MULTIPLY_IMPLICIT"'));
  });
}
