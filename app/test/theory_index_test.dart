import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/theme/phanto_theme.dart';
import 'package:mymath_app/src/ui/theory_index.dart';

void main() {
  testWidgets('the reference lists articles and filters them by a query', (
    tester,
  ) async {
    final client = MockClient((request) async {
      expect(request.url.path, '/api/v1/theory');
      return http.Response.bytes(
        utf8.encode(
          jsonEncode([
            {
              'id': 'discriminant',
              'title': 'Дискриминант',
              'summary': 'Число корней.',
              'formula': 'D=b^2-4ac',
            },
            {
              'id': 'fractions',
              'title': 'Дроби',
              'summary': 'Основное свойство.',
              'formula': r'\frac{a}{b}',
            },
          ]),
        ),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    });
    await tester.pumpWidget(
      MaterialApp(
        theme: PhantoTheme.light(),
        home: TheoryIndexPage(
          api: SolverApi(baseUrl: 'http://x', client: client),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Дискриминант'), findsOneWidget);
    expect(find.text('Дроби'), findsOneWidget);

    await tester.enterText(find.byKey(const ValueKey('theory-search')), 'дроб');
    await tester.pumpAndSettle();
    expect(find.text('Дискриминант'), findsNothing);
    expect(find.text('Дроби'), findsOneWidget);
  });
}
