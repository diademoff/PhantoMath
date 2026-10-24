import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mymath_app/main.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/editor/editor_view.dart';
import 'package:mymath_app/src/editor/kind.dart';
import 'package:mymath_app/src/ui/solution_preview.dart';

http.Response answer(String value) => http.Response(
  jsonEncode({
    'result': {
      'solution': {'type': 'CONSTANT', 'value': value},
      'groups': [
        {
          'type': 'VERTICAL',
          'entries': [
            {
              'result': {'steps': []},
            },
          ],
        },
      ],
    },
  }),
  200,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

void main() {
  testWidgets(
    'opening steps during a live request awaits it instead of resubmitting',
    (tester) async {
      final pending = Completer<http.Response>();
      var requests = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: SolvePage(
            api: SolverApi(
              baseUrl: 'http://test',
              client: MockClient((request) {
                requests++;
                return pending.future;
              }),
            ),
          ),
        ),
      );
      final editor = tester
          .widget<EditorView>(find.byType(EditorView))
          .controller;
      editor.typeDigit('5');
      await tester.pump(const Duration(milliseconds: 500));
      expect(requests, 1);
      await tester.tap(find.byKey(const ValueKey('solve')));
      await tester.pump();
      expect(requests, 1);
      pending.complete(answer('5'));
      await tester.pump();
      expect(requests, 1);
      expect(find.text('Ответ'), findsOneWidget);
      expect(find.byType(SolutionPreview), findsNothing);
    },
  );
  testWidgets(
    'long exact roots in the live answer scroll without intrinsic layout',
    (tester) async {
      tester.view.physicalSize = const Size(320, 640);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ListView(
              children: const [
                SolutionPreview(
                  latex: r'x_1=\frac{-9-\sqrt{33+128\pi}}{4},\quad x_2=\frac{-9+\sqrt{33+128\pi}}{4}',
                ),
              ],
            ),
          ),
        ),
      );
      expect(tester.takeException(), isNull);
      expect(find.byType(SingleChildScrollView), findsWidgets);
    },
  );
  testWidgets(
    'answer appears without submit, details reuse it; arrows do not solve',
    (tester) async {
      var requests = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: SolvePage(
            api: SolverApi(
              baseUrl: 'http://test',
              client: MockClient((request) async {
                requests++;
                return answer('5');
              }),
            ),
          ),
        ),
      );
      final editor = tester
          .widget<EditorView>(find.byType(EditorView))
          .controller;
      editor.typeDigit('2');
      editor.insertOperator(ENodeKind.add);
      editor.typeDigit('3');
      await tester.pump(const Duration(milliseconds: 449));
      expect(requests, 0);
      await tester.pump(const Duration(milliseconds: 2));
      await tester.pump();
      expect(requests, 1);
      expect(find.byType(SolutionPreview), findsOneWidget);
      expect(find.text('Шаги решения'), findsOneWidget);
      expect(find.text('Другие действия'), findsNothing);
      expect(find.byTooltip('Все символы'), findsNothing);
      editor.moveLeft();
      editor.moveRight();
      await tester.pump(const Duration(milliseconds: 600));
      expect(requests, 1);
      await tester.tap(find.byKey(const ValueKey('solve')));
      await tester.pump();
      expect(requests, 1);
      expect(find.text('Ответ'), findsOneWidget);
      expect(find.text('Пояснить этапы'), findsNothing);
      // the steps screen: 2 + 3 has no other actions to offer
      expect(find.byTooltip('Назад'), findsOneWidget);
      expect(find.text('Другие действия'), findsNothing);
    },
  );

  testWidgets('incomplete templates and trailing operators do not submit', (
    tester,
  ) async {
    var requests = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: SolvePage(
          api: SolverApi(
            baseUrl: 'http://test',
            client: MockClient((request) async {
              requests++;
              return answer('1');
            }),
          ),
        ),
      ),
    );
    final editor = tester
        .widget<EditorView>(find.byType(EditorView))
        .controller;
    editor.typeDigit('6');
    editor.insertOperator(ENodeKind.add);
    editor.insertTemplate(ENodeKind.fraction);
    editor.typeDigit('3');
    await tester.pump(const Duration(seconds: 1));
    expect(requests, 0);
    editor.nextSlot();
    editor.typeDigit('4');
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pump();
    expect(requests, 1);
    editor.nextSlot();
    editor.insertOperator(ENodeKind.equals);
    await tester.pump(const Duration(seconds: 1));
    expect(requests, 1);
    expect(find.byType(SolutionPreview), findsNothing);
  });

  testWidgets('an old live response cannot replace an edited problem', (
    tester,
  ) async {
    final pending = <Completer<http.Response>>[];
    await tester.pumpWidget(
      MaterialApp(
        home: SolvePage(
          api: SolverApi(
            baseUrl: 'http://test',
            client: MockClient((request) {
              final completer = Completer<http.Response>();
              pending.add(completer);
              return completer.future;
            }),
          ),
        ),
      ),
    );
    final editor = tester
        .widget<EditorView>(find.byType(EditorView))
        .controller;
    editor.typeDigit('2');
    await tester.pump(const Duration(milliseconds: 500));
    expect(pending, hasLength(1));
    editor.typeDigit('3');
    await tester.pump(const Duration(milliseconds: 500));
    expect(pending, hasLength(2));
    pending[1].complete(answer('23'));
    await tester.pump();
    pending[0].complete(answer('2'));
    await tester.pump();
    expect(
      tester.widget<SolutionPreview>(find.byType(SolutionPreview)).latex,
      '23',
    );
  });
}
