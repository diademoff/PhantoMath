import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/main.dart';
import 'package:mymath_app/src/api/solver_startup.dart';
import 'package:mymath_app/src/editor/editor_view.dart';

void main() {
  test('startup is shared, fails honestly, and can retry', () async {
    var calls = 0;
    final gate = Completer<void>();
    final startup = SolverStartup(() {
      calls++;
      return calls == 1 ? gate.future : Future.value();
    });
    addTearDown(startup.dispose);
    final first = startup.ensureReady();
    expect(identical(first, startup.ensureReady()), isTrue);
    gate.completeError(StateError('failed'));
    await expectLater(first, throwsStateError);
    expect(startup.status, SolverStatus.failed);
    await startup.ensureReady();
    expect(startup.status, SolverStatus.ready);
    expect(calls, 2);
  });

  testWidgets('typing is available before solver startup completes', (tester) async {
    tester.view.physicalSize = const Size(1080, 2280);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final gate = Completer<void>();
    await tester.pumpWidget(BootstrapApp(start: () => gate.future));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('key:DIGIT_TWO')));
    await tester.pump();
    final editor = tester.widget<EditorView>(find.byType(EditorView)).controller;
    expect(editor.toCoreNode().value, '2');
    expect(find.text('Подготавливаем решатель…'), findsOneWidget);
    gate.complete();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(editor.toCoreNode().value, '2');
    expect(find.text('Готов к решению'), findsOneWidget);
  });
}
