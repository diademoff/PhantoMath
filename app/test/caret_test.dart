import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/editor/controller.dart';
import 'package:mymath_app/src/editor/model.dart';
import 'package:mymath_app/src/editor/kind.dart';

void main() {
  test('character movement, insertion and deletion preserve a numeric token', () {
    final c = EditorController();
    addTearDown(c.dispose);
    for (final d in '123'.split('')) { c.typeDigit(d); }
    c.moveLeft();
    expect(c.cursor.textOffset, 2);
    c.typeDigit('9');
    expect(c.toCoreNode().value, '1293');
    c.backspace();
    expect(c.toCoreNode().value, '123');
    c.moveLeft();
    c.deleteForward();
    expect(c.toCoreNode().value, '13');
    c.moveRight();
    expect(c.cursor.textOffset, isNull);
    expect(c.cursor.offset, 1);
  });

  test('operator in the middle of a number splits at the caret', () {
    final c = EditorController()..typeDigit('1')..typeDigit('2');
    addTearDown(c.dispose);
    c.focus(const EdCursor(offset: 0, textOffset: 1));
    c.insertOperator(ENodeKind.add);
    expect(c.toCoreNode().children.map((n) => n.value), ['1', '2']);
  });

  test('arrows visit both fraction slots and next exits without deletion', () {
    final c = EditorController()..typeDigit('1')..insertTemplate(ENodeKind.fraction)..typeDigit('2');
    addTearDown(c.dispose);
    c.nextSlot();
    expect(c.cursor.steps, isEmpty);
    c.moveLeft();
    expect(c.cursor.steps.single.slot, 1);
    c.moveLeft();
    c.moveLeft();
    expect(c.cursor.steps.single.slot, 0);
    expect(c.toCoreNode().children.map((n) => n.value), ['1', '2']);
  });
}
