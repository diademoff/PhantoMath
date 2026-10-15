import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/render/latex.dart';

/// Собрать узел «a op b».
CoreNode bin(CoreNodeType op, CoreNode a, CoreNode b) =>
    CoreNode(type: op, children: [a, b]);

final CoreNode c2 = CoreNode(type: CoreNodeType.constant, value: '2');
final CoreNode c3 = CoreNode(type: CoreNodeType.constant, value: '3');
final CoreNode cx = CoreNode(type: CoreNodeType.variable, value: 'x');

void main() {
  group('CoreNode', () {
    test('разбирает ответ бэкенда', () {
      final node = CoreNode.fromJson(jsonDecode('''
        {"type":"ADD","children":[
          {"type":"MULTIPLY_IMPLICIT","children":[
            {"type":"CONSTANT","value":"2"},
            {"type":"VARIABLE","value":"x"}]},
          {"type":"CONSTANT","value":"3"}]}
      ''') as Map<String, dynamic>);

      expect(node.type, CoreNodeType.add);
      expect(node.children.first.type, CoreNodeType.multiplyImplicit);
      expect(node.children.first.children.last.value, 'x');
    });

    test('неизвестный тип не роняет разбор', () {
      final node = CoreNode.fromJson({'type': 'ВЫДУМКА', 'value': '1'});
      expect(node.type, CoreNodeType.text);
      expect(node.value, '1');
      expect(CoreNode.hadUnknownTypeIn({'type': 'ВЫДУМКА'}), isTrue);
      expect(CoreNode.hadUnknownTypeIn({'type': 'ADD'}), isFalse);
    });

    test('равенство структурное', () {
      expect(bin(CoreNodeType.add, c2, c3), bin(CoreNodeType.add, c2, c3));
      expect(
        bin(CoreNodeType.add, c2, c3),
        isNot(bin(CoreNodeType.add, c2, cx)),
      );
    });

    test('тип переживает круг сериализации', () {
      const all = CoreNodeType.values;
      for (final type in all) {
        expect(CoreNodeType.fromWire(type.wire), type);
      }
    });

    test('разбирает подсветку и зачёркивание', () {
      final node = CoreNode.fromJson({
        'type': 'CONSTANT',
        'value': '8',
        'crossed': true,
        'color': 0xFFFF0000,
      });
      expect(node.crossed, isTrue);
      expect(node.color, 0xFFFF0000);
      expect(node.toJson()['crossed'], isTrue);
      expect(node.toJson()['color'], 0xFFFF0000);
    });
  });

  group('nodeToLatex', () {
    test('терминалы', () {
      expect(nodeToLatex(c2), '2');
      expect(nodeToLatex(cx), 'x');
    });

    test('экранирует служебные символы', () {
      final node = CoreNode(type: CoreNodeType.constant, value: r'a_b$c');
      expect(nodeToLatex(node), r'a\_b\$c');
    });

    test('дробь и корень', () {
      expect(nodeToLatex(bin(CoreNodeType.fraction, c2, c3)),
          r'\frac{2}{3}');
      expect(nodeToLatex(CoreNode(type: CoreNodeType.root2, children: [c2])),
          r'\sqrt{2}');
    });

    test('скобки разделяют операнды', () {
      final node = bin(
        CoreNodeType.add,
        bin(CoreNodeType.multiply, c2, c3),
        c2,
      );
      expect(nodeToLatex(node), r'2 \cdot 3 + 2');
    });

    test('неявное умножение не вставляет знак', () {
      final node = bin(CoreNodeType.multiplyImplicit, c2, cx);
      expect(nodeToLatex(node), r'2 x');
    });

    test('аргументы разводятся по разным местам шаблона', () {
      // Дробь: первый ребёнок в числитель, второй в знаменатель.
      expect(nodeToLatex(bin(CoreNodeType.fraction, c2, c3)), r'\frac{2}{3}');
      // Степень: основание и показатель на своих местах.
      expect(nodeToLatex(bin(CoreNodeType.power, c2, c3)), r'{2}^{3}');
    });

    test('пустой узел даёт пустую строку', () {
      expect(nodeToLatex(CoreNode(type: CoreNodeType.empty)), '');
    });

    test('единицы угла', () {
      expect(
        nodeToLatex(CoreNode(type: CoreNodeType.degree, children: [c2])),
        r'{2}^{\circ}',
      );
      expect(
        nodeToLatex(CoreNode(type: CoreNodeType.radian, children: [c2])),
        r'{2}\ \mathrm{rad}',
      );
    });

    test('промежутки', () {
      expect(
        nodeToLatex(bin(CoreNodeType.openOpenInterval, c2, c3)),
        r'\left(2, 3\right)',
      );
      expect(
        nodeToLatex(bin(CoreNodeType.openClosedInterval, c2, c3)),
        r'\left(2, 3\right]',
      );
      expect(
        nodeToLatex(bin(CoreNodeType.closedOpenInterval, c2, c3)),
        r'\left[2, 3\right)',
      );
      expect(
        nodeToLatex(bin(CoreNodeType.closedClosedInterval, c2, c3)),
        r'\left[2, 3\right]',
      );
    });

    test('множества и отношения', () {
      expect(
        nodeToLatex(CoreNode(type: CoreNodeType.set, children: [c2, c3])),
        r'\left\{ 2,\ 3 \right\}',
      );
      expect(
        nodeToLatex(CoreNode(type: CoreNodeType.union, children: [c2, c3])),
        r'2 \cup 3',
      );
      expect(
        nodeToLatex(CoreNode(type: CoreNodeType.intersection, children: [c2, c3])),
        r'2 \cap 3',
      );
      expect(
        nodeToLatex(bin(CoreNodeType.difference, c2, c3)),
        r'2 \setminus 3',
      );
      expect(nodeToLatex(bin(CoreNodeType.elementOf, c2, c3)), r'2 \in 3');
      expect(nodeToLatex(bin(CoreNodeType.elementNotOf, c2, c3)), r'2 \notin 3');
      expect(
        nodeToLatex(bin(CoreNodeType.subsetOrEquals, c2, c3)),
        r'2 \subseteq 3',
      );
    });

    test('текстовый ответ по ключу', () {
      final node = CoreNode(type: CoreNodeType.text, children: [
        CoreNode(type: CoreNodeType.textKey, value: 'true'),
      ]);
      expect(nodeToLatex(node), 'true');
    });

    test('гиперболические функции', () {
      expect(
        nodeToLatex(CoreNode(type: CoreNodeType.sech, children: [c2])),
        r'\mathrm{sech}\left(2\right)',
      );
      expect(
        nodeToLatex(CoreNode(type: CoreNodeType.asinh, children: [c2])),
        r'\mathrm{asinh}\left(2\right)',
      );
    });

    test('список решений через запятую', () {
      final node = CoreNode(
        type: CoreNodeType.list,
        children: [
          bin(CoreNodeType.equals, cx, c2),
          bin(CoreNodeType.equals, cx, c3),
        ],
      );
      final latex = nodeToLatex(node);
      expect(latex, contains(r',\quad '));
      expect(latex, contains(r'x = 2'));
      expect(latex, contains(r'x = 3'));
    });

    test('определитель рисуется матрицей', () {
      final node = CoreNode(
        type: CoreNodeType.determinant2,
        children: [c2, c3, c3, c2],
      );
      final latex = nodeToLatex(node);
      expect(latex, contains(r'\begin{vmatrix}'));
      expect(latex, contains(r'\end{vmatrix}'));
      expect(latex, contains('&'));
    });

    test('матрица рисуется pmatrix', () {
      final node = CoreNode(
        type: CoreNodeType.matrix,
        children: [
          CoreNode(type: CoreNodeType.matrixRow, children: [c2, c3]),
          CoreNode(type: CoreNodeType.matrixRow, children: [c3, c2]),
        ],
      );
      final latex = nodeToLatex(node);
      expect(latex, contains(r'\begin{pmatrix}'));
      expect(latex, contains(r'\end{pmatrix}'));
      expect(latex, contains('&'));
    });

    test('незавершённый узел даёт заглушку, а не пустоту', () {
      final node = CoreNode(type: CoreNodeType.add, children: [c2]);
      expect(nodeToLatex(node), contains(r'\square'));
    });

    test('подсветка и зачёркивание оборачивают формулу', () {
      final crossed = CoreNode(
        type: CoreNodeType.constant,
        value: '8',
        crossed: true,
      );
      expect(nodeToLatex(crossed), r'\cancel{8}');

      final colored = CoreNode(
        type: CoreNodeType.constant,
        value: 'x',
        color: 0xFFFF0000,
      );
      expect(nodeToLatex(colored), r'\textcolor{#ff0000}{x}');

      final both = CoreNode(
        type: CoreNodeType.constant,
        value: '8',
        crossed: true,
        color: 0xFF00FF00,
      );
      expect(nodeToLatex(both), r'\textcolor{#00ff00}{\cancel{8}}');
    });
  });

  group('nodeToLatex рендерится', () {
    testWidgets('формулы не вызывают ParseException в flutter_math', (
      tester,
    ) async {
      CoreNode cnst(String value) =>
          CoreNode(type: CoreNodeType.constant, value: value);
      final pi = cnst('π');
      final k = CoreNode(type: CoreNodeType.variable, value: 'k');
      final twoPi = bin(CoreNodeType.multiplyImplicit, c2, pi);
      final samples = <CoreNode>[
        bin(CoreNodeType.fraction, c2, c3),
        CoreNode(type: CoreNodeType.root2, children: [c2]),
        CoreNode(type: CoreNodeType.root, children: [c3, cnst('8')]),
        bin(CoreNodeType.power, cx, c2),
        CoreNode(type: CoreNodeType.sin, children: [cx]),
        CoreNode(type: CoreNodeType.asec, children: [c2]),
        CoreNode(type: CoreNodeType.sech, children: [c2]),
        CoreNode(type: CoreNodeType.asinh, children: [c2]),
        CoreNode(type: CoreNodeType.degree, children: [cnst('30')]),
        CoreNode(type: CoreNodeType.radian, children: [cx]),
        CoreNode(type: CoreNodeType.abs, children: [cx]),
        CoreNode(type: CoreNodeType.log, children: [cx, c2]),
        CoreNode(type: CoreNodeType.exp, children: [cx]),
        CoreNode(type: CoreNodeType.integralDefinite, children: [c2, c3, cx]),
        CoreNode(
          type: CoreNodeType.determinant2,
          children: [c2, c3, c3, c2],
        ),
        bin(CoreNodeType.openClosedInterval, c2, c3),
        bin(CoreNodeType.closedOpenInterval, c2, c3),
        CoreNode(type: CoreNodeType.set, children: [c2, c3]),
        bin(
          CoreNodeType.elementOf,
          c2,
          CoreNode(type: CoreNodeType.set, children: [c2, c3]),
        ),
        bin(CoreNodeType.difference, c2, c3),
        CoreNode(type: CoreNodeType.text, children: [
          CoreNode(type: CoreNodeType.textKey, value: 'true'),
        ]),
        // Микро-анимация: зачёркнутая часть.
        CoreNode(type: CoreNodeType.constant, value: '8', crossed: true),
        // Матрица со строками.
        CoreNode(
          type: CoreNodeType.matrix,
          children: [
            CoreNode(type: CoreNodeType.matrixRow, children: [c2, c3]),
            CoreNode(type: CoreNodeType.matrixRow, children: [c3, c2]),
          ],
        ),
        // Серия общего решения тригонометрического уравнения: x = π/6 + 2πk.
        bin(
          CoreNodeType.equals,
          cx,
          CoreNode(
            type: CoreNodeType.add,
            children: [
              bin(CoreNodeType.fraction, pi, cnst('6')),
              bin(CoreNodeType.multiply, twoPi, k),
            ],
          ),
        ),
      ];
      for (final node in samples) {
        final latex = nodeToLatex(node);
        String? error;
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: Math.tex(
                latex,
                onErrorFallback: (e) {
                  error = '$e';
                  return const SizedBox();
                },
              ),
            ),
          ),
        );
        await tester.pump();
        expect(error, isNull, reason: 'LaTeX: $latex');
      }
    });
  });

  group('SolverApi', () {
    test('разбирает успешный ответ', () async {
      final api = _apiWith(_response(
        '''{"result":{"solution":{"type":"CONSTANT","value":"14"},"groups":[{"type":"VERTICAL","entries":[{"result":{"steps":[{"headers":[],"substeps":[{"left":{"type":"ADD","children":[]},"right":{"type":"CONSTANT","value":"14"},"description":{"type":"add","args":[]},"explanation":{"key":"add","text":"Сложите числа"}}]}]}}]}]}}''',
        200,
      ));

      final answer = await api.solve(bin(CoreNodeType.add, c2, c3));
      expect(answer.solution?.value, '14');
      expect(answer.steps, hasLength(1));
      expect(answer.steps.single.substeps.single.text, 'Сложите числа');
      expect(answer.steps.single.substeps.single.explanationKey, 'add');
      api.close();
    });

    test('422 превращается в SolveFailure с ключом', () async {
      final api = _apiWith(_response(
        '{"detail":{"message":"деление на ноль","explanation":"div_with_zero"}}',
        422,
      ));

      await expectLater(
        api.solve(bin(CoreNodeType.divide, c2, c3)),
        throwsA(
          isA<SolveFailure>()
              .having((e) => e.message, 'message', 'деление на ноль')
              .having((e) => e.explanationKey, 'key', 'div_with_zero'),
        ),
      );
      api.close();
    });

    test('иной код ответа не выдаётся за нерешённую задачу', () async {
      final api = _apiWith(_response('oops', 500));
      await expectLater(
        api.solve(bin(CoreNodeType.add, c2, c3)),
        throwsA(isA<SolveFailure>().having(
          (e) => e.message,
          'message',
          contains('500'),
        )),
      );
      api.close();
    });

    test('тело ошибки без detail не приводит к падению', () async {
      final api = _apiWith(_response('не json', 422));
      await expectLater(
        api.solve(bin(CoreNodeType.add, c2, c3)),
        throwsA(isA<SolveFailure>().having(
          (e) => e.message,
          'message',
          'Задача не решена',
        )),
      );
      api.close();
    });

    test('разбирает несколько способов решения', () async {
      final api = _apiWith(_response(
        '''{"result":{"solution":{"type":"CONSTANT","value":"2"},"groups":[{"type":"VERTICAL","selectMethodText":{"type":"select_method"},"entries":[
          {"result":{"solutionNode":{"type":"CONSTANT","value":"2"},"steps":[{"headers":[],"substeps":[{"description":{"type":"eq_quad_solve_in_r"},"explanation":{"text":"формула"}}]}]}},
          {"result":{"solutionNode":{"type":"CONSTANT","value":"2"},"steps":[{"headers":[],"substeps":[{"description":{"type":"solve_by_factoring"},"explanation":{"text":"разложение"}}]}]}}
        ]}]}}''',
        200,
      ));

      final answer = await api.solve(bin(CoreNodeType.add, c2, c3));
      expect(answer.methods, hasLength(2));
      expect(answer.steps.single.substeps.single.text, 'формула');
      expect(answer.methods[1].steps.single.substeps.single.text, 'разложение');
      api.close();
    });

    test('разбирает ссылки в тексте пояснения', () async {
      final api = _apiWith(_response(
        '''{"result":{"groups":[{"type":"VERTICAL","entries":[{"result":{"steps":[
          {"headers":[],"substeps":[{"description":{"type":"factorise_call"},"explanation":{"key":"factorise_call","text":"Factor","links":[{"label":"Factor","uuid":"1ceef362-dfb4-4ae6-ba5d-46dbd862a37b","definition":"Разложение на множители."}]}}]}]}}]}]}}''',
        200,
      ));

      final answer = await api.solve(bin(CoreNodeType.add, c2, c3));
      final link = answer.steps.single.substeps.single.links.single;
      expect(link.label, 'Factor');
      expect(link.uuid, '1ceef362-dfb4-4ae6-ba5d-46dbd862a37b');
      expect(link.definition, 'Разложение на множители.');
      api.close();
    });

    test('разбирает точки графика', () async {
      final api = SolverApi(
        baseUrl: 'http://test',
        client: MockClient(
          (request) async => http.Response(
            '{"variable":"x","xMin":-1,"xMax":1,"yMin":0,"yMax":1,'
            '"points":[[-1,1],[0,0],[1,1]]}',
            200,
            headers: jsonHeaders,
          ),
        ),
      );

      final data = await api.graph(bin(CoreNodeType.add, c2, c3));
      expect(data.points, hasLength(3));
      expect(data.points[1].x, 0);
      expect(data.points[2].y, 1);
      expect(data.variable, 'x');
      api.close();
    });
  });
}

/// Ответы бэкенда — UTF-8. Без заголовка `http.Response` кодирует тело
/// в latin1 и падает на русском тексте пояснений.
const jsonHeaders = {'content-type': 'application/json; charset=utf-8'};

/// Ответ с явной кодировкой. Без заголовка `http.Response` считает тело
/// в latin1 и падает на русском тексте пояснений.
http.Response _response(String body, int status) =>
    http.Response(body, status, headers: jsonHeaders);

SolverApi _apiWith(http.Response response) => SolverApi(
  baseUrl: 'http://test',
  client: MockClient((request) async => response),
);
