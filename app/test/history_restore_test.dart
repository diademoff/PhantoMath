import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/editor/convert.dart';
import 'package:mymath_app/src/editor/kind.dart';
import 'package:mymath_app/src/editor/model.dart';
import 'package:mymath_app/src/editor/restore.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/notebook/notebook.dart';
import 'package:mymath_app/src/notebook/notebook_page.dart';

CoreNode number(String value) =>
    CoreNode(type: CoreNodeType.constant, value: value);
CoreNode variable(String value) =>
    CoreNode(type: CoreNodeType.variable, value: value);
CoreNode op(CoreNodeType type, List<CoreNode> children) =>
    CoreNode(type: type, children: children);

// Parentheses added by restoration preserve the operator tree, but naturally
// appear as BRACKET nodes when the editable document is parsed again.
CoreNode withoutBrackets(CoreNode node) {
  if (node.type == CoreNodeType.bracket) {
    return withoutBrackets(node.children.single);
  }
  return CoreNode(
    type: node.type,
    value: node.value,
    children: node.children.map(withoutBrackets).toList(),
  );
}

void main() {
  final x = variable('x');
  final a = variable('a');
  final b = variable('b');
  final c = variable('c');
  final sum = op(CoreNodeType.add, [a, b]);

  group('history restoration', () {
    final fixtures = <String, CoreNode>{
      'number': number('12.50'),
      'symbolic constant': number('π'),
      'variable': x,
      'empty document': const CoreNode(type: CoreNodeType.empty),
      'fraction': op(CoreNodeType.fraction, [sum, number('3')]),
      'mixed fraction': op(CoreNodeType.fractionMixed, [
        number('1'),
        number('2'),
        number('3'),
      ]),
      'general power': op(CoreNodeType.power, [sum, number('2')]),
      'arbitrary exponent': op(CoreNodeType.power, [x, sum]),
      'indexed root': op(CoreNodeType.root, [number('3'), sum]),
      'square root': op(CoreNodeType.root2, [sum]),
      'logarithm': op(CoreNodeType.log, [x, number('2')]),
      'trigonometry': op(CoreNodeType.sin, [sum]),
      'definite integral': op(CoreNodeType.integralDefinite, [
        number('0'),
        number('1'),
        x,
      ]),
      'sum': op(CoreNodeType.sigmaDefinite, [number('1'), number('5'), x]),
      'vector': op(CoreNodeType.list, [a, b]),
      'two-line system': op(CoreNodeType.system, [
        op(CoreNodeType.equals, [x, number('1')]),
        op(CoreNodeType.lessThan, [x, number('2')]),
      ]),
      'three-line system': op(CoreNodeType.system, [
        op(CoreNodeType.equals, [a, number('1')]),
        op(CoreNodeType.equals, [b, number('2')]),
        op(CoreNodeType.equals, [c, number('3')]),
      ]),
      'function': CoreNode(
        type: CoreNodeType.function,
        value: 'g',
        children: [x],
      ),
      'inverse function': CoreNode(
        type: CoreNodeType.functionInverse,
        value: 'f',
        children: [x],
      ),
      'determinant': op(CoreNodeType.determinant2, [a, b, c, x]),
      'segment': op(CoreNodeType.lineSegment, [a, b]),
    };
    for (final fixture in fixtures.entries) {
      test('${fixture.key} survives history JSON and editor roundtrip', () {
        final saved = NotebookEntry(
          problem: fixture.value,
          savedAt: DateTime(2026, 10, 16),
        );
        final restored = NotebookEntry.fromJson(saved.toJson());
        expect(editorToCoreNode(coreToEditor(restored.problem)), fixture.value);
      });
    }

    test('powers and logarithm bases remain editable general slots', () {
      final power = coreToEditor(op(CoreNodeType.power, [x, number('2')]))
          .children
          .single;
      expect(power.kind, ENodeKind.power);
      expect(power.children, hasLength(2));
      final log = coreToEditor(op(CoreNodeType.log, [x, number('2')]))
          .children
          .single;
      expect(log.kind, ENodeKind.log);
      expect(log.children, hasLength(2));
      final changed = log.copyWith(
        children: [
          log.children.first,
          ENode.row([ENode.terminal(ENodeKind.constant, '7')]),
        ],
      );
      expect(
        editorToCoreNode(ENode.row([changed])),
        op(CoreNodeType.log, [x, number('7')]),
      );
    });

    test('operator precedence and associativity retain the original tree', () {
      final expressions = [
        op(CoreNodeType.multiply, [sum, c]),
        op(CoreNodeType.subtract, [
          a,
          op(CoreNodeType.subtract, [b, c]),
        ]),
        op(CoreNodeType.divide, [
          a,
          op(CoreNodeType.multiply, [b, c]),
        ]),
        op(CoreNodeType.multiply, [
          a,
          op(CoreNodeType.divide, [b, c]),
        ]),
        op(CoreNodeType.add, [
          a,
          op(CoreNodeType.add, [b, c]),
        ]),
        op(CoreNodeType.negative, [sum]),
        op(CoreNodeType.factorial, [sum]),
        op(CoreNodeType.factorial, [
          op(CoreNodeType.negative, [x]),
        ]),
        op(CoreNodeType.negative, [
          op(CoreNodeType.factorial, [x]),
        ]),
        op(CoreNodeType.multiplyImplicit, [sum, c]),
        op(CoreNodeType.multiplyImplicit, [
          a,
          op(CoreNodeType.negative, [b]),
        ]),
        op(CoreNodeType.multiplyImplicit, [
          a,
          op(CoreNodeType.positive, [b]),
        ]),
        op(CoreNodeType.multiplyImplicit, [
          a,
          op(CoreNodeType.multiplyImplicit, [b, c]),
        ]),
        op(CoreNodeType.lessThan, [
          a,
          op(CoreNodeType.equals, [b, c]),
        ]),
      ];
      for (final expression in expressions) {
        expect(
          withoutBrackets(editorToCoreNode(coreToEditor(expression))),
          withoutBrackets(expression),
          reason: expression.toString(),
        );
      }
      expect(
        coreToEditor(op(CoreNodeType.multiply, [sum, c])).children.first.kind,
        ENodeKind.bracket,
      );
    });

    for (final dimensions in [(1, 3), (2, 3), (3, 2), (3, 3)]) {
      test('rectangular ${dimensions.$1}×${dimensions.$2} matrix', () {
        final (rows, cols) = dimensions;
        final matrix = op(CoreNodeType.matrix, [
          for (var row = 0; row < rows; row++)
            op(CoreNodeType.matrixRow, [
              for (var col = 0; col < cols; col++)
                number('${row * cols + col}'),
            ]),
        ]);
        final restored = coreToEditor(matrix);
        expect(restored.children.single.kind, ENodeKind.matrix2);
        expect(restored.children.single.value, '$rows,$cols');
        expect(restored.children.single.children, hasLength(rows * cols));
        expect(editorToCoreNode(restored), matrix);
      });
    }

    test('unsupported nodes and malformed shapes fail explicitly', () {
      final unsupported = [
        const CoreNode(type: CoreNodeType.text, value: 'unknown'),
        op(CoreNodeType.set, [x]),
        op(CoreNodeType.power, [x]),
        op(CoreNodeType.add, [a, b, c]),
        op(CoreNodeType.matrix, []),
        op(CoreNodeType.matrix, [
          op(CoreNodeType.matrixRow, [a, b]),
          op(CoreNodeType.matrixRow, [c]),
        ]),
        op(CoreNodeType.matrix, [
          op(CoreNodeType.list, [a, b]),
        ]),
        const CoreNode(type: CoreNodeType.constant),
        CoreNode(type: CoreNodeType.function, value: 'h', children: [x]),
        op(CoreNodeType.sin, [
          const CoreNode(type: CoreNodeType.text, value: '?'),
        ]),
      ];
      for (final node in unsupported) {
        expect(() => coreToEditor(node), throwsUnsupportedError);
      }
    });
  });

  testWidgets('Редактировать pops the original problem, not its solution', (
    tester,
  ) async {
    final notebook = Notebook();
    addTearDown(notebook.dispose);
    final problem = op(CoreNodeType.add, [number('2'), number('3')]);
    await tester.runAsync(
      () => notebook.restore([
        NotebookEntry(
          problem: problem,
          solution: number('5'),
          savedAt: DateTime(2026, 10, 16),
        ),
      ]),
    );
    CoreNode? selected;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () async {
                selected = await Navigator.of(context).push<CoreNode>(
                  MaterialPageRoute<CoreNode>(
                    builder: (_) => NotebookPage(notebook: notebook),
                  ),
                );
              },
              child: const Text('Открыть историю'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Открыть историю'));
    await tester.pumpAndSettle();
    expect(find.text('Редактировать'), findsOneWidget);
    await tester.tap(find.text('Редактировать'));
    await tester.pumpAndSettle();
    expect(selected, same(problem));
    expect(find.byType(NotebookPage), findsNothing);
  });
}
