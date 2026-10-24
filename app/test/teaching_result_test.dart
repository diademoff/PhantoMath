import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/render/latex.dart';
import 'package:mymath_app/src/theme/phanto_theme.dart';
import 'package:mymath_app/src/ui/vertical_result.dart';

const c = CoreNode(type: CoreNodeType.constant, value: '2');
const article = TheoryArticle(
  id: 'balance',
  title: 'Равносильные уравнения',
  summary: 'Выполняем одинаковое действие с обеими частями.',
  formula: r'A=B\Longleftrightarrow A-C=B-C',
  conditions: 'Делитель не равен нулю.',
  example: '2x = 4 → x = 2',
  mistake: 'Нельзя менять только одну часть.',
);
const nested = SolveResponse(
  header: 'Вычисление дроби',
  solution: c,
  steps: [
    SolveStep(
      id: 'nested',
      headers: ['Вычислим'],
      substeps: [
        Substep(left: c, right: c, text: 'Первое вычисление'),
        Substep(left: c, right: c, text: 'Второе вычисление'),
      ],
    ),
  ],
);
const lesson = SolveResponse(
  solution: c,
  steps: [
    SolveStep(
      id: 'collect',
      headers: ['Соберём слагаемые'],
      substeps: [
        Substep(id: 'a', left: c, right: c, text: 'Первый этап'),
        Substep(
          id: 'b',
          left: c,
          right: c,
          text: 'Второй этап',
          subresult: nested,
          theory: article,
        ),
      ],
    ),
    SolveStep(
      id: 'divide',
      headers: ['Выразим неизвестное'],
      substeps: [
        Substep(id: 'c', left: c, right: c, text: 'Разделим обе части'),
      ],
    ),
  ],
);

Widget page({SolveResponse result = lesson, double scale = 1}) => MaterialApp(
  theme: PhantoTheme.light(),
  builder: (context, child) => MediaQuery(
    data: MediaQuery.of(
      context,
    ).copyWith(textScaler: TextScaler.linear(scale), disableAnimations: true),
    child: child!,
  ),
  home: Scaffold(
    body: VerticalResult(
      result: result,
      latexOptions: LatexOptions.standard,
      onLink: (_) {},
      onCopy: (_) {},
    ),
  ),
);

Future<void> tap(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('one step is open, the others are rows with their titles', (
    tester,
  ) async {
    await tester.pumpWidget(page());
    await tester.pumpAndSettle();
    expect(find.text('Соберём слагаемые'), findsOneWidget);
    expect(find.text('Выразим неизвестное'), findsOneWidget);
    expect(find.text('1/2'), findsOneWidget);
    expect(find.text('Разделим обе части'), findsNothing);
    // «Далее» lives in the bottom bar, not in the card
    expect(find.text('Далее'), findsOneWidget);
  });
  testWidgets('short coefficients remain mathematical inline arguments', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 568);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      page(
        scale: 2,
        result: const SolveResponse(
          steps: [
            SolveStep(
              substeps: [
                Substep(
                  text: 'a = 2',
                  parts: [
                    ExplanationPart(text: 'Коэффициент a = '),
                    ExplanationPart(node: c),
                  ],
                ),
              ],
            ),
          ],
        ),
      ),
    );
    expect(find.byType(StepEquation), findsNothing);
    expect(
      find
          .byType(Text)
          .evaluate()
          .any((e) => (e.widget as Text).textSpan != null),
      isTrue,
    );
    expect(tester.takeException(), isNull);
  });
  testWidgets(
    'groups are steps, stages navigate; details and theory restore the stage',
    (tester) async {
      await tester.pumpWidget(page());
      expect(find.text('Первый этап'), findsOneWidget);
      expect(find.text('Второй этап'), findsNothing);
      expect(find.byKey(const ValueKey('step-details')), findsNothing);
      await tap(tester, find.byKey(const ValueKey('next-stage')));
      expect(find.text('2/2'), findsOneWidget);
      expect(find.text('Второй этап'), findsOneWidget);
      await tap(tester, find.byKey(const ValueKey('step-details')));
      expect(find.text('Подробный разбор'), findsOneWidget);
      expect(find.text('Вычисление дроби'), findsOneWidget);
      expect(find.text('Ответ'), findsOneWidget);
      expect(find.text('Первое вычисление'), findsOneWidget);
      await tap(tester, find.byKey(const ValueKey('next-stage')));
      expect(find.text('Второе вычисление'), findsOneWidget);
      await tester.pageBack();
      await tester.pumpAndSettle();
      expect(find.text('2/2'), findsOneWidget);
      await tap(tester, find.byKey(const ValueKey('step-theory')));
      expect(find.text('Почему так?'), findsOneWidget);
      expect(find.text(article.title), findsOneWidget);
      await tester.ensureVisible(find.text('Частая ошибка'));
      await tester.pumpAndSettle();
      expect(find.text(article.mistake), findsOneWidget);
      await tester.pageBack();
      await tester.pumpAndSettle();
      expect(find.text('Второй этап'), findsOneWidget);
      await tap(tester, find.byKey(const ValueKey('next-group')));
      expect(find.text('Разделим обе части'), findsOneWidget);
      expect(find.text('Второй этап'), findsNothing);
      await tap(tester, find.byKey(const ValueKey('solution-group:0')));
      expect(find.text('2/2'), findsOneWidget);
      await tap(tester, find.byKey(const ValueKey('previous-stage')));
      expect(find.text('Первый этап'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('switching methods resets the selected group and stage', (
    tester,
  ) async {
    await tester.pumpWidget(page());
    await tap(tester, find.byKey(const ValueKey('next-stage')));
    await tester.pumpWidget(
      page(
        result: const SolveResponse(
          steps: [
            SolveStep(
              id: 'other',
              substeps: [Substep(text: 'Другой способ')],
            ),
          ],
        ),
      ),
    );
    expect(find.text('Другой способ'), findsOneWidget);
    expect(find.text('Второй этап'), findsNothing);
    expect(find.byKey(const ValueKey('step-details')), findsNothing);
    expect(find.byKey(const ValueKey('step-theory')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('math arguments are rendered as trees, not debug text', (
    tester,
  ) async {
    await tester.pumpWidget(
      page(
        result: const SolveResponse(
          steps: [
            SolveStep(
              substeps: [
                Substep(
                  text: 'Divide by FRACTION()',
                  parts: [
                    ExplanationPart(text: 'Разделим на'),
                    ExplanationPart(
                      node: CoreNode(
                        type: CoreNodeType.fraction,
                        children: [
                          CoreNode(
                            type: CoreNodeType.constant,
                            value: '123456789012345678901234',
                          ),
                          c,
                        ],
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ],
        ),
      ),
    );
    expect(find.text('Разделим на'), findsOneWidget);
    expect(find.text('Divide by FRACTION()'), findsNothing);
    expect(find.byType(StepEquation), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('short formulas stay in the sentence (y|ₓ₌₀ is short)', (
    tester,
  ) async {
    const y = CoreNode(type: CoreNodeType.variable, value: 'y');
    const zero = CoreNode(type: CoreNodeType.constant, value: '0');
    await tester.pumpWidget(
      page(
        result: const SolveResponse(
          steps: [
            SolveStep(
              substeps: [
                Substep(
                  text: 'Используя начальное условие',
                  parts: [
                    ExplanationPart(text: 'Используя начальное условие '),
                    ExplanationPart(
                      node: CoreNode(
                        type: CoreNodeType.evaluateExpression,
                        children: [
                          y,
                          CoreNode(
                            type: CoreNodeType.equals,
                            children: [
                              CoreNode(type: CoreNodeType.variable, value: 'x'),
                              zero,
                            ],
                          ),
                        ],
                      ),
                    ),
                    ExplanationPart(text: ', подставьте '),
                    ExplanationPart(node: zero),
                    ExplanationPart(text: ' вместо '),
                    ExplanationPart(node: y),
                  ],
                ),
              ],
            ),
          ],
        ),
      ),
    );
    expect(find.byType(StepEquation), findsNothing);
    expect(
      find.textContaining('подставьте', findRichText: true),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });

  for (final size in [const Size(320, 568), const Size(740, 360)]) {
    testWidgets(
      'teaching navigation at $size with double text and reduced motion',
      (tester) async {
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        await tester.pumpWidget(page(scale: 2));
        await tap(tester, find.byKey(const ValueKey('next-stage')));
        await tap(tester, find.byKey(const ValueKey('step-theory')));
        await tester.scrollUntilVisible(
          find.text('Частая ошибка'),
          150,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        await tester.pageBack();
        await tester.pumpAndSettle();
        await tap(tester, find.byKey(const ValueKey('step-details')));
        await tap(tester, find.byKey(const ValueKey('next-stage')));
        expect(tester.takeException(), isNull);
      },
    );
  }

  test(
    'API retains the complete nested result, ids, theory and math arguments',
    () async {
      final api = SolverApi(
        baseUrl: 'http://test',
        client: MockClient(
          (request) async => http.Response(
            jsonEncode({
              'result': {
                'groups': [
                  {
                    'type': 'VERTICAL',
                    'entries': [
                      {
                        'result': {
                          'steps': [
                            {
                              'id': 'group',
                              'headers': [],
                              'substeps': [
                                {
                                  'id': 'stage',
                                  'description': {'type': 'add'},
                                  'explanation': {
                                    'text': 'Добавим 2',
                                    'parts': [
                                      {'type': 'text', 'text': 'Добавим '},
                                      {'type': 'math', 'node': c.toJson()},
                                    ],
                                    'theory': {
                                      'id': 'a',
                                      'title': 'Правило',
                                      'summary': 'Объяснение',
                                    },
                                  },
                                  'subresult': {
                                    'header': {
                                      'explanation': {'text': 'Детали'},
                                    },
                                    'solutionNode': c.toJson(),
                                    'steps': [
                                      {
                                        'headers': [],
                                        'substeps': [
                                          {
                                            'explanation': {'text': 'Вычислим'},
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
                      },
                    ],
                  },
                ],
              },
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          ),
        ),
      );
      addTearDown(api.close);
      final result = await api.solve(c);
      final step = result.steps.single.substeps.single;
      expect(result.steps.single.id, 'group');
      expect(step.id, 'stage');
      expect(step.subresult?.header, 'Детали');
      expect(step.subresult?.solution?.value, '2');
      expect(step.parts.last.node?.value, '2');
      expect(step.theory?.title, 'Правило');
    },
  );
}
