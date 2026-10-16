import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/editor/controller.dart';
import 'package:mymath_app/src/editor/convert.dart';
import 'package:mymath_app/src/editor/editor_view.dart';
import 'package:mymath_app/src/editor/kind.dart';
import 'package:mymath_app/src/model/core_node.dart';

/// Набрать последовательность цифр.
void _digits(EditorController c, String digits) {
  for (final d in digits.split('')) {
    c.typeDigit(d);
  }
}

void main() {
  group('набор и правка', () {
    test('цифры сливаются в одно число', () {
      final c = EditorController();
      _digits(c, '123');
      expect(c.document.children, hasLength(1));
      expect(c.document.children.single.value, '123');
      expect(c.cursor.offset, 1);
    });

    test('точка присоединяется к числу, вторая начинает новое', () {
      final c = EditorController();
      _digits(c, '2');
      c.typeDigit('.');
      _digits(c, '5');
      expect(c.document.children.single.value, '2.5');
      c.typeDigit('.');
      expect(c.document.children, hasLength(2));
    });

    test('backspace удаляет по символу, затем по узлу', () {
      final c = EditorController();
      _digits(c, '12');
      c.backspace();
      expect(c.document.children.single.value, '1');
      c.backspace();
      expect(c.document.children, isEmpty);
    });

    test('clear очищает документ', () {
      final c = EditorController();
      _digits(c, '42');
      c.clear();
      expect(c.document.children, isEmpty);
      expect(c.cursor.offset, 0);
    });

    test('символьная константа не сливается с цифрой', () {
      final c = EditorController();
      c.typeDigit('π');
      _digits(c, '5');
      expect(c.document.children, hasLength(2));
      expect(c.toCoreNode().type, CoreNodeType.multiplyImplicit);
    });
  });

  group('шаблоны', () {
    test('дробь поглощает предыдущий операнд и ставит курсор в знаменатель', () {
      final c = EditorController();
      _digits(c, '12');
      c.insertTemplate(ENodeKind.fraction);
      // Курсор в знаменателе.
      expect(c.cursor.steps, hasLength(1));
      expect(c.cursor.steps.single.slot, 1);
      _digits(c, '3');
      final node = c.toCoreNode();
      expect(node.type, CoreNodeType.fraction);
      expect(node.children[0].value, '12');
      expect(node.children[1].value, '3');
    });

    test('степень поглощает основание', () {
      final c = EditorController();
      _digits(c, '2');
      c.insertTemplate(ENodeKind.power);
      _digits(c, '3');
      final node = c.toCoreNode();
      expect(node.type, CoreNodeType.power);
      expect(node.children[0].value, '2');
      expect(node.children[1].value, '3');
    });

    test('корень поглощает подкоренное и оставляет курсор внутри', () {
      final c = EditorController();
      _digits(c, '9');
      c.insertTemplate(ENodeKind.root2);
      final node = c.toCoreNode();
      expect(node.type, CoreNodeType.root2);
      expect(node.children.single.value, '9');
      // Курсор — в подкоренном выражении, за набранным числом.
      expect(c.cursor.steps, hasLength(1));
      expect(c.cursor.offset, 1);
    });

    test('скобка вставляется пустой, содержимое набирается внутри', () {
      final c = EditorController();
      c.insertTemplate(ENodeKind.bracket);
      _digits(c, '2');
      c.insertOperator(ENodeKind.add);
      _digits(c, '3');
      final node = c.toCoreNode();
      expect(node.type, CoreNodeType.bracket);
      final inner = node.children.single;
      expect(inner.type, CoreNodeType.add);
      expect(inner.children[0].value, '2');
      expect(inner.children[1].value, '3');
    });

    test('moveUp/moveDown ходят между слотами дроби', () {
      final c = EditorController();
      _digits(c, '1');
      c.insertTemplate(ENodeKind.fraction);
      expect(c.cursor.steps.single.slot, 1);
      c.moveUp();
      expect(c.cursor.steps.single.slot, 0);
      c.moveDown();
      expect(c.cursor.steps.single.slot, 1);
    });

    test('backspace в начале слота выходит наружу, не удаляя шаблон', () {
      final c = EditorController();
      c.insertTemplate(ENodeKind.fraction);
      expect(c.cursor.steps, hasLength(1));
      c.backspace();
      expect(c.cursor.steps, isEmpty);
      expect(c.document.children, hasLength(1)); // шаблон на месте
    });
  });

  group('преобразование в CoreNode', () {
    CoreNode solve(EditorController c) => editorToCoreNode(c.document);

    test('пустой документ даёт EMPTY', () {
      final c = EditorController();
      expect(solve(c).type, CoreNodeType.empty);
    });

    test('2x — неявное умножение', () {
      final c = EditorController();
      _digits(c, '2');
      c.typeVariable('x');
      final node = solve(c);
      expect(node.type, CoreNodeType.multiplyImplicit);
      expect(node.children[0].value, '2');
      expect(node.children[1].value, 'x');
    });

    test('приоритеты: 2+3*4', () {
      final c = EditorController();
      _digits(c, '2');
      c.insertOperator(ENodeKind.add);
      _digits(c, '3');
      c.insertOperator(ENodeKind.multiply);
      _digits(c, '4');
      final node = solve(c);
      expect(node.type, CoreNodeType.add);
      expect(node.children[0].value, '2');
      expect(node.children[1].type, CoreNodeType.multiply);
    });

    test('отношение слабее арифметики: 2+3=5', () {
      final c = EditorController();
      _digits(c, '2');
      c.insertOperator(ENodeKind.add);
      _digits(c, '3');
      c.insertOperator(ENodeKind.equals);
      _digits(c, '5');
      final node = solve(c);
      expect(node.type, CoreNodeType.equals);
      expect(node.children[0].type, CoreNodeType.add);
      expect(node.children[1].value, '5');
    });

    test('унарный минус', () {
      final c = EditorController();
      c.insertOperator(ENodeKind.subtract);
      _digits(c, '4');
      final node = solve(c);
      expect(node.type, CoreNodeType.negative);
      expect(node.children.single.value, '4');
    });

    test('постфиксный факториал', () {
      final c = EditorController();
      _digits(c, '5');
      c.insertOperator(ENodeKind.factorial);
      final node = solve(c);
      expect(node.type, CoreNodeType.factorial);
      expect(node.children.single.value, '5');
    });

    test('постфиксный градус оборачивает число', () {
      final c = EditorController();
      _digits(c, '30');
      c.insertOperator(ENodeKind.degree);
      final node = solve(c);
      expect(node.type, CoreNodeType.degree);
      expect(node.children.single.value, '30');
    });

    test('постфиксный радиан оборачивает число', () {
      final c = EditorController();
      _digits(c, '2');
      c.insertOperator(ENodeKind.radian);
      final node = solve(c);
      expect(node.type, CoreNodeType.radian);
      expect(node.children.single.value, '2');
    });

    test('sin(30°) собирается как SIN(DEGREE(30))', () {
      final c = EditorController();
      c.insertTemplate(ENodeKind.sin);
      _digits(c, '30');
      c.insertOperator(ENodeKind.degree);
      final node = solve(c);
      expect(node.type, CoreNodeType.sin);
      expect(node.children.single.type, CoreNodeType.degree);
      expect(node.children.single.children.single.value, '30');
    });

    test('обратная гиперболическая функция собирается', () {
      final c = EditorController();
      c.insertTemplate(ENodeKind.asinh);
      _digits(c, '1');
      final node = solve(c);
      expect(node.type, CoreNodeType.asinh);
      expect(node.children.single.value, '1');
    });

    test('вектор даёт список LIST', () {
      final c = EditorController();
      c.insertTemplate(ENodeKind.vector);
      c.typeDigit('3');
      c.moveDown();
      c.typeDigit('4');
      final node = c.toCoreNode();
      expect(node.type, CoreNodeType.list);
      expect(node.children.map((child) => child.value).toList(), ['3', '4']);
    });

    test('функция без аргумента не теряется', () {
      final c = EditorController();
      c.insertTemplate(ENodeKind.sin);
      // Курсор внутри аргумента — наберём x.
      c.typeVariable('x');
      final node = solve(c);
      expect(node.type, CoreNodeType.sin);
      expect(node.children.single.value, 'x');
    });
  });

  group('структуры: системы и определители', () {
    test('система собирается из двух уравнений', () {
      final c = EditorController();
      c.insertTemplate(ENodeKind.system2);
      c.typeVariable('x');
      c.insertOperator(ENodeKind.add);
      c.typeDigit('1');
      c.insertOperator(ENodeKind.equals);
      c.typeDigit('3');
      c.moveDown();
      c.typeVariable('x');
      c.insertOperator(ENodeKind.subtract);
      c.typeDigit('1');
      c.insertOperator(ENodeKind.equals);
      c.typeDigit('1');
      final node = c.toCoreNode();
      expect(node.type, CoreNodeType.system);
      expect(node.children, hasLength(2));
      expect(node.children.every((e) => e.type == CoreNodeType.equals), isTrue);
    });

    test('определитель 2×2 заполняется по слотам', () {
      final c = EditorController();
      c.insertTemplate(ENodeKind.determinant2);
      for (final digit in ['1', '2', '3', '4']) {
        c.typeDigit(digit);
        c.moveDown();
      }
      final node = c.toCoreNode();
      expect(node.type, CoreNodeType.determinant2);
      expect(node.children.map((e) => e.value).toList(), ['1', '2', '3', '4']);
    });

    test('матрица 2×2 собирается в MATRIX со строками', () {
      final c = EditorController();
      c.insertTemplate(ENodeKind.matrix2);
      for (final digit in ['1', '2', '3', '4']) {
        c.typeDigit(digit);
        c.moveDown();
      }
      final node = c.toCoreNode();
      expect(node.type, CoreNodeType.matrix);
      expect(node.children, hasLength(2));
      expect(node.children.every((r) => r.type == CoreNodeType.matrixRow), isTrue);
      expect(node.children[0].children.map((e) => e.value).toList(), ['1', '2']);
      expect(node.children[1].children.map((e) => e.value).toList(), ['3', '4']);
    });
  });

  group('вид редактора и тап по формуле', () {
    Future<void> pump(WidgetTester tester, EditorController c) async {
      await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: EditorView(controller: c))),
      );
      await tester.pump();
    }

    testWidgets('пустой документ показывает курсор', (tester) async {
      await pump(tester, EditorController());
      expect(find.byKey(const ValueKey('cursor')), findsOneWidget);
    });

    testWidgets('тап по пустому слоту ставит курсор в него', (tester) async {
      final c = EditorController();
      await pump(tester, c);
      await tester.tap(find.byKey(const ValueKey('slot:')));
      await tester.pump();
      expect(c.cursor.steps, isEmpty);
      expect(c.cursor.offset, 0);
    });

    testWidgets('тап по терминалу ставит курсор за ним', (tester) async {
      final c = EditorController();
      _digits(c, '2');
      c.insertOperator(ENodeKind.add);
      _digits(c, '3');
      c.moveLeft();
      await pump(tester, c);
      await tester.tap(find.text('2'));
      await tester.pump();
      expect(c.cursor.steps, isEmpty);
      expect(c.cursor.offset, 1);
    });

    testWidgets('тап по знаменателю дроби заводит курсор в него',
        (tester) async {
      final c = EditorController();
      _digits(c, '1');
      c.insertTemplate(ENodeKind.fraction);
      _digits(c, '3');
      await pump(tester, c);
      await tester.tap(find.text('3'));
      await tester.pump();
      expect(c.cursor.steps, hasLength(1));
      expect(c.cursor.steps.single.slot, 1);
      expect(c.cursor.offset, 1);
    });

    testWidgets('тап по числителю дроби заводит курсор в него', (tester) async {
      final c = EditorController();
      _digits(c, '1');
      c.insertTemplate(ENodeKind.fraction);
      await pump(tester, c);
      await tester.tap(find.text('1'));
      await tester.pump();
      expect(c.cursor.steps.single.slot, 0);
      expect(c.cursor.offset, 1);
    });

    testWidgets('тап по знаку ставит курсор за ним', (tester) async {
      final c = EditorController();
      _digits(c, '2');
      c.insertOperator(ENodeKind.add);
      _digits(c, '3');
      await pump(tester, c);
      await tester.tap(find.text('+'));
      await tester.pump();
      expect(c.cursor.offset, 2);
    });
  });

  group('быстрые клавиши', () {
    test('x² даёт POWER со степенью 2', () {
      final c = EditorController();
      _digits(c, '3');
      c.insertTemplate(ENodeKind.powerTwo);
      final node = editorToCoreNode(c.document);
      expect(node.type, CoreNodeType.power);
      expect(node.children, hasLength(2));
      expect(node.children[1].value, '2');
    });

    test('x³ даёт POWER со степенью 3', () {
      final c = EditorController();
      _digits(c, '2');
      c.insertTemplate(ENodeKind.powerThree);
      expect(editorToCoreNode(c.document).children[1].value, '3');
    });

    test('∛ даёт ROOT с показателем 3', () {
      final c = EditorController();
      c.insertTemplate(ENodeKind.rootThree);
      final node = editorToCoreNode(c.document);
      expect(node.type, CoreNodeType.root);
      expect(node.children[0].value, '3');
    });

    test('смешанное число собирается в FRACTION_MIXED', () {
      final c = EditorController();
      _digits(c, '1');
      c.insertTemplate(ENodeKind.mixedFraction);
      expect(editorToCoreNode(c.document).type, CoreNodeType.fractionMixed);
    });

    test('f(x) собирается в FUNCTION', () {
      final c = EditorController();
      c.insertTemplate(ENodeKind.functionF);
      c.typeVariable('x');
      final node = editorToCoreNode(c.document);
      expect(node.type, CoreNodeType.function);
      expect(node.value, 'f');
      expect(node.children.single.value, 'x');
    });

    test('g(x) собирается в FUNCTION с именем g', () {
      final c = EditorController();
      c.insertTemplate(ENodeKind.functionG);
      c.typeVariable('t');
      expect(editorToCoreNode(c.document).value, 'g');
    });

    test('f⁻¹(y) собирается в FUNCTION_INVERSE', () {
      final c = EditorController();
      c.insertTemplate(ENodeKind.functionInverseF);
      c.typeVariable('y');
      final node = editorToCoreNode(c.document);
      expect(node.type, CoreNodeType.functionInverse);
      expect(node.value, 'f');
      expect(node.children.single.value, 'y');
    });
  });
}
