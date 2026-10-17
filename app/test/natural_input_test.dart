import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/editor/controller.dart';
import 'package:mymath_app/src/editor/kind.dart';
import 'package:mymath_app/src/model/core_node.dart';

void main() {
  test('cancelling a still-empty power preserves the existing base', () {
    final c = EditorController()
      ..typeDigit('5')
      ..insertTemplate(ENodeKind.power);
    c.backspace();
    expect(c.toCoreNode().value, '5');
    expect(c.cursor.steps, isEmpty);
  });
  test(
    'both deletion directions can erase an exponent without erasing its base',
    () {
      final c = EditorController()
        ..typeDigit('5')
        ..insertTemplate(ENodeKind.powerThree);
      c.moveLeft();
      c.moveLeft();
      c.deleteForward();
      expect(c.toCoreNode().value, '5');
      expect(c.cursor.steps, isEmpty);
    },
  );

  test('cube-root shortcut has an editable index like the general root', () {
    final c = EditorController()
      ..insertTemplate(ENodeKind.rootThree)
      ..typeDigit('8');
    expect(c.toCoreNode().children.map((n) => n.value), ['3', '8']);
    c.moveLeft();
    c.moveLeft();
    c.backspace();
    c.typeDigit('2');
    expect(c.toCoreNode().children.map((n) => n.value), ['2', '8']);
  });

  test(
    'a power of a factorial captures the whole operand, not the factorial sign',
    () {
      final c = EditorController()
        ..typeDigit('5')
        ..insertOperator(ENodeKind.factorial)
        ..insertTemplate(ENodeKind.powerTwo);
      expect(c.toCoreNode().type, CoreNodeType.power);
      expect(c.toCoreNode().children.first.type, CoreNodeType.factorial);
      expect(c.toCoreNode().children.first.children.single.value, '5');
    },
  );
  test('8 pi, 8 e and 8 infinity never become malformed numeric tokens', () {
    for (final symbol in ['π', 'e', '∞']) {
      final c = EditorController()
        ..typeDigit('8')
        ..typeDigit(symbol);
      expect(c.document.children, hasLength(2));
      expect(c.toCoreNode().type, CoreNodeType.multiplyImplicit);
      expect(c.toCoreNode().children.map((n) => n.value), ['8', symbol]);
    }
  });

  test('2x²+9x+6=8π can be typed without repairing the cursor', () {
    final c = EditorController()
      ..typeDigit('2')
      ..typeVariable('x')
      ..insertTemplate(ENodeKind.powerTwo);
    expect(c.cursor.steps, isEmpty);
    c.insertOperator(ENodeKind.add);
    c.typeDigit('9');
    c.typeVariable('x');
    c.insertOperator(ENodeKind.add);
    c.typeDigit('6');
    c.insertOperator(ENodeKind.equals);
    c.typeDigit('8');
    c.typeDigit('π');
    final node = c.toCoreNode();
    expect(node.type, CoreNodeType.equals);
    expect(node.children.last.type, CoreNodeType.multiplyImplicit);
    expect(node.children.last.children.last.value, 'π');
    expect(c.document.children[1].children[1].children.single.value, '2');
  });

  test(
    'backspace removes a square, not its base; exponent remains editable',
    () {
      final c = EditorController()
        ..typeDigit('5')
        ..insertTemplate(ENodeKind.powerTwo);
      c.moveLeft();
      expect(c.cursor.steps.last.slot, 1);
      c.backspace();
      expect(c.toCoreNode().value, '5');
      c.insertTemplate(ENodeKind.powerTwo);
      c.backspace();
      expect(c.toCoreNode().value, '5');
      c.insertTemplate(ENodeKind.powerTwo);
      c.moveLeft();
      c.typeDigit('3');
      expect(c.toCoreNode().children.last.value, '23');
    },
  );

  test(
    'a fresh square leaves an empty editable base, not an empty exponent',
    () {
      final c = EditorController()
        ..insertTemplate(ENodeKind.powerTwo)
        ..typeDigit('5');
      expect(c.toCoreNode().children.first.value, '5');
      expect(c.toCoreNode().children.last.value, '2');
    },
  );

  test('6 + fraction starts in numerator and never captures the plus', () {
    final c = EditorController()
      ..typeDigit('6')
      ..insertOperator(ENodeKind.add)
      ..insertTemplate(ENodeKind.fraction);
    expect(c.cursor.steps.last.slot, 0);
    c.typeDigit('3');
    c.nextSlot();
    c.typeDigit('4');
    c.nextSlot();
    final node = c.toCoreNode();
    expect(node.type, CoreNodeType.add);
    expect(node.children.first.value, '6');
    expect(node.children.last.children.map((n) => n.value), ['3', '4']);
  });

  test('fresh fraction and fraction after equals start with numerator', () {
    for (final prefix in [false, true]) {
      final c = EditorController();
      if (prefix) {
        c.typeVariable('x');
        c.insertOperator(ENodeKind.equals);
      }
      c.insertTemplate(ENodeKind.fraction);
      expect(c.cursor.steps.last.slot, 0);
    }
  });

  test('parentheses and radicals do not swallow a coefficient', () {
    for (final kind in [ENodeKind.bracket, ENodeKind.root2, ENodeKind.abs]) {
      final c = EditorController()
        ..typeDigit('2')
        ..insertTemplate(kind)
        ..typeDigit('3');
      expect(c.toCoreNode().type, CoreNodeType.multiplyImplicit);
      expect(c.toCoreNode().children.first.value, '2');
    }
  });

  test('prefilled logarithm base can be visited, deleted and changed', () {
    final c = EditorController()
      ..insertTemplate(ENodeKind.log10)
      ..typeDigit('8');
    expect(c.cursor.steps.last.slot, 0);
    c.moveLeft();
    c.moveLeft();
    expect(c.cursor.steps.last.slot, 1);
    c.backspace();
    c.backspace();
    c.typeDigit('2');
    expect(c.toCoreNode().type, CoreNodeType.log);
    expect(c.toCoreNode().children.map((n) => n.value), ['8', '2']);
  });

  test('custom log visits base then argument in visual order', () {
    final c = EditorController()
      ..insertTemplate(ENodeKind.log)
      ..typeDigit('3');
    c.nextSlot();
    c.typeDigit('9');
    c.nextSlot();
    expect(c.cursor.steps, isEmpty);
    expect(c.toCoreNode().children.map((n) => n.value), ['9', '3']);
  });

  test(
    'rectangular 4x5 matrix retains dimensions while editing every cell',
    () {
      final c = EditorController()..insertMatrix(4, 5);
      for (var i = 1; i <= 20; i++) {
        for (final d in '$i'.split('')) {
          c.typeDigit(d);
        }
        c.nextSlot();
      }
      expect(c.cursor.steps, isEmpty);
      final matrix = c.toCoreNode();
      expect(matrix.type, CoreNodeType.matrix);
      expect(matrix.children, hasLength(4));
      expect(matrix.children.every((r) => r.children.length == 5), isTrue);
      expect(matrix.children.last.children.last.value, '20');
    },
  );

  test('sum visits lower bound, upper bound, then summand', () {
    final c = EditorController()
      ..insertTemplate(ENodeKind.sigma)
      ..typeDigit('1');
    c.nextSlot();
    c.typeDigit('5');
    c.nextSlot();
    c.typeVariable('x');
    c.nextSlot();
    expect(c.toCoreNode().children.map((n) => n.value), ['x', '1', '5', 'x']);
    expect(c.cursor.steps, isEmpty);
  });

  test('left and right cross every nested slot and numeric character', () {
    final c = EditorController()
      ..typeDigit('1')
      ..typeDigit('2')
      ..insertTemplate(ENodeKind.fraction)
      ..insertTemplate(ENodeKind.root2)
      ..typeDigit('3')
      ..typeDigit('4');
    c.nextSlot();
    c.nextSlot();
    final end = c.cursor;
    var moves = 0;
    while (c.cursor.offset != 0 || c.cursor.steps.isNotEmpty) {
      final previous = c.cursor;
      c.moveLeft();
      expect(c.cursor, isNot(previous));
      expect(++moves, lessThan(30));
    }
    for (var i = 0; i < moves; i++) {
      c.moveRight();
    }
    expect(c.cursor, end);
  });
}
