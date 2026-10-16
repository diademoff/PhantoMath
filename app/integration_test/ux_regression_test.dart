import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:integration_test/integration_test.dart';
import 'package:mymath_app/main.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/api/solver_startup.dart';
import 'package:mymath_app/src/editor/editor_view.dart';
import 'package:mymath_app/src/theme/phanto_theme.dart';

Future<void> key(WidgetTester tester, String code) async {
  final finder = find.byKey(ValueKey('key:$code'));
  await tester.ensureVisible(finder);
  await tester.tap(finder);
  await tester.pump();
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('device: input stays editable while the solver initializes', (
    tester,
  ) async {
    final gate = Completer<void>();
    await tester.pumpWidget(BootstrapApp(start: () => gate.future));
    await tester.pump();
    expect(find.text('Подготавливаем решатель…'), findsOneWidget);
    await key(tester, 'DIGIT_ONE');
    await key(tester, 'DIGIT_TWO');
    final editor = tester
        .widget<EditorView>(find.byType(EditorView))
        .controller;
    expect(editor.toCoreNode().value, '12');
    gate.complete();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('Готов к решению'), findsOneWidget);
    expect(editor.toCoreNode().value, '12');
  });

  testWidgets(
    'device: editing cancels a queued solve and explanations do not resubmit',
    (tester) async {
      final gate = Completer<void>();
      final startup = SolverStartup(() => gate.future);
      var requests = 0;
      Map<String, dynamic>? sent;
      final api = SolverApi(
        baseUrl: 'http://test',
        client: MockClient((request) async {
          requests++;
          sent = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(
            jsonEncode({
              'result': {
                'solution': {'type': 'CONSTANT', 'value': '23'},
                'groups': [
                  {
                    'type': 'VERTICAL',
                    'entries': [
                      {
                        'result': {
                          'steps': [
                            {
                              'headers': [],
                              'substeps': [
                                {
                                  'left': {'type': 'CONSTANT', 'value': '23'},
                                  'right': {'type': 'CONSTANT', 'value': '23'},
                                  'explanation': {
                                    'key': 'identity',
                                    'text': 'Число уже вычислено',
                                  },
                                },
                              ],
                            },
                          ],
                        },
                      },
                    ],
                  },
                ],
              },
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }),
      );
      await tester.pumpWidget(
        MaterialApp(
          theme: PhantoTheme.dark(),
          home: SolvePage(api: api, startup: startup),
        ),
      );
      await key(tester, 'DIGIT_TWO');
      await tester.tap(find.byKey(const ValueKey('solve')));
      await tester.pump();
      expect(find.text('Решаем…'), findsOneWidget);
      await key(tester, 'DIGIT_THREE');
      gate.complete();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(requests, 0, reason: 'stale input was submitted after startup');
      await tester.tap(find.byKey(const ValueKey('solve')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect((sent!['node'] as Map)['value'], '23');
      expect(requests, 1);
      await tester.tap(find.text('Пояснить этапы'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(
        requests,
        1,
        reason: 'explaining a step must never re-run the solver',
      );
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
      startup.dispose();
    },
  );
}
