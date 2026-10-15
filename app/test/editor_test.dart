import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/editor/controller.dart';
import 'package:mymath_app/src/editor/convert.dart';
import 'package:mymath_app/src/editor/kind.dart';
import 'package:mymath_app/src/editor/latex.dart';
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

  group('рендер с курсором', () {
    String latex(EditorController c) => editorToLatex(c.document, c.cursor);

    test('пустой документ — только курсор', () {
      expect(latex(EditorController()), contains(r'\cursor{}'));
    });

    test('курсор стоит в позиции вставки', () {
      final c = EditorController();
      _digits(c, '2');
      expect(latex(c), '2 \\cursor{}');
      c.moveLeft();
      expect(latex(c), '\\cursor{} 2');
    });

    test('курсор внутри слота дроби', () {
      final c = EditorController();
      _digits(c, '1');
      c.insertTemplate(ENodeKind.fraction);
      final out = latex(c);
      expect(out, startsWith(r'\frac{1}'));
      expect(out, contains(r'\cursor{}'));
    });

    test('символьные константы идут LaTeX-командами', () {
      final c = EditorController();
      c.typeDigit('π');
      expect(latex(c), contains(r'\pi'));
      c.typeDigit('∞');
      expect(latex(c), contains(r'\infty'));
    });

    testWidgets('макрос курсора понимается flutter_math', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Math.tex(
              r'2+\cursor{}3',
              onErrorFallback: (e) => const Text('ERR'),
            ),
          ),
        ),
      );
      await tester.pump();
      expect(find.text('ERR'), findsNothing);
      expect(find.byType(Math), findsOneWidget);
    });
  });
}
