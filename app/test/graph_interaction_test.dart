import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/render/graph_view.dart';
import 'package:mymath_app/src/theme/phanto_theme.dart';

void main() {
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
          theme: PhantoTheme.dark(),
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
}
