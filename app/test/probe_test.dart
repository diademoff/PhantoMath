import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/main.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const String _solveBody = '''
{"result":{"solution":{"type":"CONSTANT","value":"5"},
 "groups":[{"type":"VERTICAL","entries":[{"result":{"steps":[
   {"headers":[],"substeps":[
     {"left":{"type":"ADD","children":[]},
      "right":{"type":"CONSTANT","value":"5"},
      "description":{"type":"add","args":[]},
      "explanation":{"key":"add","text":"Сложите числа"}}]}]}}]}]}}
''';

void main() {
  testWidgets('probe', (tester) async {
    final api = SolverApi(
      baseUrl: 'http://test',
      client: MockClient((request) async => http.Response(_solveBody, 200,
          headers: const {'content-type': 'application/json; charset=utf-8'})),
    );
    await tester.pumpWidget(MaterialApp(home: SolvePage(api: api)));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('key:DIGIT_TWO')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('key:BASIC_INFIX_OPERATOR_PLUS')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('key:DIGIT_THREE')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('solve')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    // ignore: avoid_print
    print('TEXT default: ${find.text('Сложите числа').evaluate().length}');
    // ignore: avoid_print
    print('TEXT rich: ${find.text('Сложите числа', findRichText: true).evaluate().length}');
    // ignore: avoid_print
    print('ExpansionTile: ${find.byType(ExpansionTile).evaluate().length}');
    // ignore: avoid_print
    print('all Text widgets: ${tester.widgetList<Text>(find.byType(Text)).map((t) => t.data).toList()}');
  });
}
