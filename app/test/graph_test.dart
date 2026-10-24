import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/render/graph_view.dart';

void main() {
  testWidgets('график рисует опорные точки и асимптоты', (tester) async {
    const data = GraphData(
      points: [GraphPoint(-1, 1), GraphPoint(0, 1), GraphPoint(1, 1)],
      xMin: -2,
      xMax: 2,
      yMin: -1,
      yMax: 2,
      variable: 'x',
      annotations: GraphAnnotations(
        roots: [GraphPoint(0, 0)],
        yIntercept: GraphPoint(0, 1),
        maxima: [GraphPoint(0, 1)],
        verticalAsymptotes: [1.5],
        horizontalAsymptotes: [0],
      ),
    );
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: SizedBox(width: 300, height: 200, child: GraphView(data: data)),
        ),
      ),
    );
    expect(find.byType(GraphView), findsOneWidget);
  });

  test('GraphAnnotations.isEmpty', () {
    expect(const GraphAnnotations().isEmpty, isTrue);
    expect(const GraphAnnotations(roots: [GraphPoint(1, 0)]).isEmpty, isFalse);
    expect(const GraphAnnotations(piecewise: true).isEmpty, isTrue);
  });
}
