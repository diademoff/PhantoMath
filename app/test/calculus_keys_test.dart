/// Клавиши исчисления: односторонний предел, производная 2-го порядка,
/// курсор в поле точки и переменная предела.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/editor/controller.dart';
import 'package:mymath_app/src/editor/editor_view.dart';
import 'package:mymath_app/src/editor/kind.dart';
import 'package:mymath_app/src/editor/restore.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/ui/keyboard/ph_keyboard_spec.dart';

CoreNode _number(String value) =>
    CoreNode(type: CoreNodeType.constant, value: value);

CoreNode _variable(String name) =>
    CoreNode(type: CoreNodeType.variable, value: name);

Future<void> _pump(WidgetTester tester, EditorController controller) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(body: EditorView(controller: controller)),
    ),
  );
  // pumpAndSettle может не дождаться мигающего курсора.
  await tester.pump(const Duration(milliseconds: 300));
}

/// Набрать `lim_{точка} выражение` выбранного вида предела.
EditorController _limit(ENodeKind kind, String point, String expression) {
  final controller = EditorController()..insertTemplate(kind);
  for (final digit in point.split('')) {
    controller.typeDigit(digit);
  }
  controller.nextSlot();
  controller.typeVariable(expression);
  return controller;
}

void main() {
  group('односторонний предел', () {
    test('«Предел справа» даёт LIMIT_RIGHT', () {
      final node = _limit(ENodeKind.limitRight, '0', 'x').toCoreNode();
      expect(node.type, CoreNodeType.limitRight);
      expect(node.children[0].value, '0');
      expect(node.children[1].value, 'x');
    });

    test('«Предел слева» даёт LIMIT_LEFT', () {
      final node = _limit(ENodeKind.limitLeft, '0', 'x').toCoreNode();
      expect(node.type, CoreNodeType.limitLeft);
      expect(node.children[0].value, '0');
    });

    test('обычный «Предел» остаётся LIMIT', () {
      final node = _limit(ENodeKind.limit, '0', 'x').toCoreNode();
      expect(node.type, CoreNodeType.limit);
    });

    test('история сохраняет сторону предела', () {
      for (final type in [CoreNodeType.limitLeft, CoreNodeType.limitRight]) {
        final document = coreToEditor(
          CoreNode(type: type, children: [_number('0'), _variable('x')]),
        );
        final restored = EditorController(document: document);
        expect(restored.toCoreNode().type, type);
      }
    });

    test('долгое нажатие «Предел»: варианты дают свою сторону', () {
      final variants = extensionsOf('OPERATOR_LIMIT');
      expect(variants.map((key) => key.code), [
        'OPERATOR_LIMIT_LEFT_NODE',
        'OPERATOR_LIMIT_RIGHT_NODE',
      ]);
      expect(variants.map((key) => key.action!.kind), [
        ENodeKind.limitLeft,
        ENodeKind.limitRight,
      ]);
    });
  });

  group('курсор и подпись предела', () {
    test('после вставки курсор в поле точки, «Далее» — в функцию', () {
      for (final kind in [
        ENodeKind.limit,
        ENodeKind.limitLeft,
        ENodeKind.limitRight,
      ]) {
        final controller = EditorController()..insertTemplate(kind);
        expect(controller.cursor.steps.single.slot, 0);
        controller.nextSlot();
        expect(controller.cursor.steps.single.slot, 1);
      }
    });

    testWidgets('правосторонний предел рисует x→a⁺', (tester) async {
      final controller = _limit(ENodeKind.limitRight, '0', 'x');
      await _pump(tester, controller);
      expect(find.text('lim'), findsOneWidget);
      expect(find.text('x→'), findsOneWidget);
      expect(find.text('⁺'), findsOneWidget);
    });

    testWidgets('левосторонний предел рисует x→a⁻', (tester) async {
      final controller = _limit(ENodeKind.limitLeft, '0', 'x');
      await _pump(tester, controller);
      expect(find.text('⁻'), findsOneWidget);
    });

    testWidgets('последовательность рисует n→, а не x→', (tester) async {
      final controller = _limit(ENodeKind.limit, '0', 'n');
      await _pump(tester, controller);
      expect(find.text('n→'), findsOneWidget);
      expect(find.text('x→'), findsNothing);
      // Переменная уходит в запросе внутри выражения: решатель берёт её оттуда.
      expect(controller.toCoreNode().children[1].value, 'n');
    });
  });

  group('производная 2-го порядка', () {
    test('«Производная n-го порядка» даёт DERIVATION2_PRIME', () {
      final controller = EditorController()
        ..insertTemplate(ENodeKind.derivative2);
      controller.typeVariable('x');
      controller.insertTemplate(ENodeKind.power);
      controller.typeDigit('2');

      final node = controller.toCoreNode();
      expect(node.type, CoreNodeType.derivation2Prime);
      expect(node.children.single.type, CoreNodeType.power);
    });
    test('вложенная d/dx собирается как DERIVATION1(DERIVATION1)', () {
      final controller = EditorController()
        ..insertTemplate(ENodeKind.derivative)
        ..insertTemplate(ENodeKind.derivative);
      controller.typeVariable('x');

      final outer = controller.toCoreNode();
      expect(outer.type, CoreNodeType.derivation1);
      expect(outer.children.single.type, CoreNodeType.derivation1);
      expect(outer.children.single.children.single.value, 'x');
    });

    test('история восстанавливает d²/dx²', () {
      final document = coreToEditor(
        CoreNode(
          type: CoreNodeType.derivation2Prime,
          children: [_variable('x')],
        ),
      );
      final restored = EditorController(document: document);
      expect(restored.toCoreNode().type, CoreNodeType.derivation2Prime);
    });

    testWidgets('редактор рисует d²/dx²', (tester) async {
      final controller = EditorController()
        ..insertTemplate(ENodeKind.derivative2);
      controller.typeVariable('x');
      await _pump(tester, controller);
      expect(find.text('d²/dx²'), findsOneWidget);
    });

    test('долгое нажатие «Производная»: n-й порядок даёт d²/dx²', () {
      final variants = extensionsOf('OPERATOR_DERIVATIVE_X');
      final degree = variants.firstWhere(
        (key) => key.code == 'OPERATOR_DERIVATIVE_CUSTOM_DEGREE',
      );
      expect(degree.description, 'Производная n-го порядка');
      expect(degree.action!.kind, ENodeKind.derivative2);
    });
  });

  group('определённый интеграл', () {
    test('после вставки курсор в нижнем пределе, «Далее» ведёт к верхнему', () {
      final controller = EditorController()
        ..insertTemplate(ENodeKind.integralDefinite);
      // Как у предела: сначала нижний предел, затем верхний, затем функция.
      expect(controller.cursor.steps.single.slot, 0);
      controller.nextSlot();
      expect(controller.cursor.steps.single.slot, 1);
      controller.nextSlot();
      expect(controller.cursor.steps.single.slot, 2);
    });

    test(
      '∫₁^∞ dx/x² собирается как {integral_def({1},{inf},{frac({1},{x^2})})}',
      () {
        final controller = EditorController()
          ..insertTemplate(ENodeKind.integralDefinite);
        controller.typeDigit('1');
        controller.nextSlot();
        controller.typeDigit('∞');
        controller.nextSlot();
        controller.insertTemplate(ENodeKind.fraction);
        controller.typeDigit('1');
        controller.nextSlot();
        controller.typeVariable('x');
        controller.insertTemplate(ENodeKind.powerTwo);

        expect(
          controller.toCoreNode(),
          CoreNode(
            type: CoreNodeType.integralDefinite,
            children: [
              _number('1'),
              _number('∞'),
              CoreNode(
                type: CoreNodeType.fraction,
                children: [
                  _number('1'),
                  CoreNode(
                    type: CoreNodeType.power,
                    children: [_variable('x'), _number('2')],
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );

    test('π в пределе — константа π', () {
      final controller = EditorController()
        ..insertTemplate(ENodeKind.integralDefinite);
      controller.typeDigit('0');
      controller.nextSlot();
      controller.typeDigit('π');
      controller.nextSlot();
      controller.typeVariable('x');

      final node = controller.toCoreNode();
      expect(node.children[1], _number('π'));
    });

    test('π/2 с долгого нажатия «Пи» — дробь π/2', () {
      final half = extensionsOf('CONSTANT_PI')
          .firstWhere((key) => key.code == 'CONSTANT_HALF_PI');
      expect(half.action, isNotNull);
      expect(half.action!.kind, ENodeKind.halfPi);

      final controller = EditorController()
        ..insertTemplate(ENodeKind.integralDefinite);
      controller.typeDigit('0');
      controller.nextSlot();
      controller.insertTemplate(half.action!.kind!);
      controller.nextSlot();
      controller.typeVariable('x');

      // {integral_def({0},{frac({pi},{2})},{...})}
      expect(
        controller.toCoreNode().children[1],
        CoreNode(
          type: CoreNodeType.fraction,
          children: [_number('π'), _number('2')],
        ),
      );
    });
  });

  group('переменная интегрирования', () {
    test(
      'переменная не добавляет слот: протокол остаётся {integral({t^2})}',
      () {
        final controller = EditorController()
          ..insertTemplate(ENodeKind.integral);
        controller.typeVariable('t');
        controller.insertTemplate(ENodeKind.powerTwo);

        final node = controller.toCoreNode();
        expect(node.type, CoreNodeType.integral);
        expect(node.children.single.type, CoreNodeType.power);
        expect(node.children.single.children.first.value, 't');
      },
    );

    testWidgets('∫t² рисует dt, а не dx', (tester) async {
      final controller = EditorController()..insertTemplate(ENodeKind.integral);
      controller.typeVariable('t');
      controller.insertTemplate(ENodeKind.powerTwo);
      await _pump(tester, controller);
      expect(find.text(' dt'), findsOneWidget);
      expect(find.text(' dx'), findsNothing);
    });

    testWidgets('∫x² остаётся с dx', (tester) async {
      final controller = EditorController()..insertTemplate(ENodeKind.integral);
      controller.typeVariable('x');
      controller.insertTemplate(ENodeKind.powerTwo);
      await _pump(tester, controller);
      expect(find.text(' dx'), findsOneWidget);
    });

    testWidgets('пустое подынтегральное выражение — dx', (tester) async {
      final controller = EditorController()..insertTemplate(ENodeKind.integral);
      await _pump(tester, controller);
      expect(find.text(' dx'), findsOneWidget);
    });

    testWidgets('определённый интеграл берёт переменную из подынтегрального', (
      tester,
    ) async {
      final controller = EditorController()
        ..insertTemplate(ENodeKind.integralDefinite);
      controller.typeDigit('0');
      controller.nextSlot();
      controller.typeDigit('1');
      controller.nextSlot();
      controller.typeVariable('t');
      controller.insertTemplate(ENodeKind.powerTwo);
      await _pump(tester, controller);
      expect(find.text(' dt'), findsOneWidget);
      expect(find.text(' dx'), findsNothing);
    });
  });
}
