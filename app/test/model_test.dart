import 'dart:convert';

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
          r'\frac{$2$}{$3$}');
      expect(nodeToLatex(CoreNode(type: CoreNodeType.root2, children: [c2])),
          r'\sqrt{$2$}');
    });

    test('скобки разделяют операнды', () {
      final node = bin(
        CoreNodeType.add,
        bin(CoreNodeType.multiply, c2, c3),
        c2,
      );
      expect(nodeToLatex(node), r'$2$ \cdot $3$ + $2$');
    });

    test('неявное умножение не вставляет знак', () {
      final node = bin(CoreNodeType.multiplyImplicit, c2, cx);
      expect(nodeToLatex(node), r'$2$ $x$');
    });

    test('аргументы разводятся по разным местам шаблона', () {
      // Дробь: первый ребёнок в числитель, второй в знаменатель.
      expect(nodeToLatex(bin(CoreNodeType.fraction, c2, c3)), r'\frac{$2$}{$3$}');
      // Степень: основание и показатель на своих местах.
      expect(nodeToLatex(bin(CoreNodeType.power, c2, c3)), r'{$2$}^{$3$}');
    });

    test('пустой узел даёт пустую строку', () {
      expect(nodeToLatex(CoreNode(type: CoreNodeType.empty)), '');
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
      expect(latex, contains(r'$x$ = $2$'));
      expect(latex, contains(r'$x$ = $3$'));
    });

    test('незавершённый узел даёт заглушку, а не пустоту', () {
      final node = CoreNode(type: CoreNodeType.add, children: [c2]);
      expect(nodeToLatex(node), contains(r'\square'));
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
          {"headers":[],"substeps":[{"description":{"type":"factorise_call"},"explanation":{"key":"factorise_call","text":"Factor","links":[{"label":"Factor","uuid":"1ceef362-dfb4-4ae6-ba5d-46dbd862a37b"}]}}]}]}}]}]}}''',
        200,
      ));

      final answer = await api.solve(bin(CoreNodeType.add, c2, c3));
      final link = answer.steps.single.substeps.single.links.single;
      expect(link.label, 'Factor');
      expect(link.uuid, '1ceef362-dfb4-4ae6-ba5d-46dbd862a37b');
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
