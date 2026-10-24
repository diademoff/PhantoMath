import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/render/graph_view.dart';
import 'package:mymath_app/src/theme/phanto_theme.dart';

void main() {
  numberFormat();
  const data = GraphData(
    points: [GraphPoint(-1, 1), GraphPoint(0, 0), GraphPoint(1, 1)],
    xMin: -2,
    xMax: 2,
    yMin: 0,
    yMax: 2,
    variable: 'x',
    annotations: GraphAnnotations(roots: [GraphPoint(0, 0)]),
  );
  testWidgets(
    'zoom, pan and recenter change viewport without changing graph data',
    (tester) async {
      final key = GlobalKey<GraphViewState>();
      Rect? requested;
      await tester.pumpWidget(
        MaterialApp(
          theme: PhantoTheme.light(),
          home: Scaffold(
            body: GraphView(
              key: key,
              data: data,
              onViewportChanged: (rect) => requested = rect,
            ),
          ),
        ),
      );
      final initial = key.currentState!.viewport;
      key.currentState!.zoom(2);
      await tester.pump();
      expect(requested!.width, initial.width / 2);
      await tester.drag(find.byType(GraphView), const Offset(50, 0));
      await tester.pump();
      expect(key.currentState!.viewport.center, isNot(initial.center));
      key.currentState!.recenter();
      await tester.pump();
      expect(key.currentState!.viewport, initial);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'the first window frames the roots and the vertex, not the whole range',
    (tester) async {
      final points = [
        for (var i = 0; i <= 200; i++)
          GraphPoint(
            -10 + i * .1,
            (-10 + i * .1) * (-10 + i * .1) - 5 * (-10 + i * .1) + 6,
          ),
      ];
      final parabola = GraphData(
        points: points,
        xMin: -10,
        xMax: 10,
        yMin: -.25,
        yMax: 156,
        variable: 'x',
        annotations: const GraphAnnotations(
          roots: [GraphPoint(2, 0), GraphPoint(3, 0)],
          yIntercept: GraphPoint(0, 6),
          minima: [GraphPoint(2.5, -.25)],
        ),
      );
      final key = GlobalKey<GraphViewState>();
      await tester.pumpWidget(
        MaterialApp(
          theme: PhantoTheme.light(),
          home: Scaffold(
            body: GraphView(key: key, data: parabola),
          ),
        ),
      );
      final view = key.currentState!.viewport;
      expect(view.left, greaterThan(-4));
      expect(view.right, lessThan(7));
      expect(
        view.bottom,
        lessThan(40),
      ); // the curve is ~24 at the window edge, not 156
    },
  );
}

void numberFormat() {
  test('graph numbers drop a pointless .0', () {
    expect(graphNumber(2.0), '2');
    expect(graphNumber(-3.0), '-3');
    expect(graphNumber(2.5), '2.5');
    expect(graphNumber(0.0), '0');
    expect(graphNumber(-0.25), '-0.25');
  });
}
