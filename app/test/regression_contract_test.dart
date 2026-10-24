import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/editor/controller.dart';
import 'package:mymath_app/src/editor/kind.dart';

void main() {
  test('editor changes must preserve the public solver request', () async {
    final editor = EditorController();
    addTearDown(editor.dispose);
    editor.typeDigit('1');
    editor.typeDigit('2');
    editor.insertTemplate(ENodeKind.fraction);
    editor.typeDigit('3');
    Map<String, dynamic>? body;
    final api = SolverApi(
      baseUrl: 'http://test',
      client: MockClient((request) async {
        body = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response('{"result":{}}', 200);
      }),
    );
    addTearDown(api.close);
    await api.solve(editor.toCoreNode(), locale: 'ru', command: 'simplify');
    expect(body, {
      'node': {
        'type': 'FRACTION',
        'children': [
          {'type': 'CONSTANT', 'value': '12'},
          {'type': 'CONSTANT', 'value': '3'},
        ],
      },
      'locale': 'ru',
      'render': true,
      'action': {'command': 'simplify', 'args': <Object>[]},
    });
  });

  test('graph viewport and annotations survive the API boundary', () async {
    final api = SolverApi(
      baseUrl: 'http://test',
      client: MockClient((request) async {
        final body = jsonDecode(request.body) as Map;
        expect(body['xMin'], -2);
        expect(body['xMax'], 3);
        return http.Response(
          jsonEncode({
            'points': [
              [0, 1],
            ],
            'xMin': -2,
            'xMax': 3,
            'yMin': 0,
            'yMax': 4,
            'variable': 'x',
            'annotations': {
              'roots': [
                [1, 0],
              ],
              'maxima': [
                [0, 1],
              ],
              'verticalAsymptotes': [2],
              'horizontalAsymptotes': [0],
            },
          }),
          200,
        );
      }),
    );
    addTearDown(api.close);
    final editor = EditorController()..typeVariable('x');
    addTearDown(editor.dispose);
    final graph = await api.graph(editor.toCoreNode(), xMin: -2, xMax: 3);
    expect(graph.annotations.roots.single.x, 1);
    expect(graph.annotations.maxima.single.y, 1);
    expect(graph.annotations.verticalAsymptotes, [2]);
    expect(graph.annotations.horizontalAsymptotes, [0]);
  });
}
