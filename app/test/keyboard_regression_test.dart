import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/main.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/editor/editor_view.dart';
import 'package:mymath_app/src/model/core_node.dart';

void main() {
  testWidgets('variants reopen while entering successive system lines', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1080, 2280);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        home: SolvePage(api: SolverApi(baseUrl: 'http://test')),
      ),
    );
    Future<void> key(String code) async {
      await tester.tap(find.byKey(ValueKey('key:$code')));
      await tester.pump();
    }

    Future<void> y() async {
      await tester.longPress(find.byKey(const ValueKey('key:VARIABLE_X_LOW')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      await key('VARIABLE_Y_LOW');
      await tester.pump(const Duration(milliseconds: 400));
    }

    for (var row = 0; row < 2; row++) {
      await key('VARIABLE_X_LOW');
      await key(
        row == 0 ? 'BASIC_INFIX_OPERATOR_PLUS' : 'BASIC_INFIX_OPERATOR_MINUS',
      );
      await y();
      await key('BASIC_INFIX_OPERATOR_EQUALS');
      await key('DIGIT_THREE');
      if (row == 0) await key('CONTROL_NEW_LINE');
    }
    final editor = tester
        .widget<EditorView>(find.byType(EditorView))
        .controller;
    expect(editor.toCoreNode().type, CoreNodeType.system);
    expect(tester.takeException(), isNull);
  });
}
