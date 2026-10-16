import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../api/solver_api.dart';
import '../model/core_node.dart';
import '../ui/vertical_result.dart';
import 'latex.dart';

typedef GraphSelection = ({String label, GraphPoint point, bool approximate});

List<GraphSelection> graphFeatures(GraphData data) => [
  for (final p in data.annotations.roots)
    (label: 'Корень', point: p, approximate: false),
  for (final p in data.annotations.maxima)
    (label: 'Максимум', point: p, approximate: false),
  for (final p in data.annotations.minima)
    (label: 'Минимум', point: p, approximate: false),
  if (data.annotations.yIntercept case final p?)
    (label: 'Пересечение с осью y', point: p, approximate: false),
];

String graphNumber(double value) => value == 0
    ? '0'
    : value.abs() >= 10000 || value.abs() < .001
    ? value.toStringAsExponential(2)
    : double.parse(value.toStringAsPrecision(5)).toString();

class GraphPage extends StatefulWidget {
  const GraphPage({super.key, required this.api, required this.node});
  final SolverApi api;
  final CoreNode node;
  @override
  State<GraphPage> createState() => _GraphPageState();
}

class _GraphPageState extends State<GraphPage> {
  final _view = GlobalKey<GraphViewState>();
  GraphData? _data;
  String? _error;
  bool _loading = true;
  int _generation = 0;
  Timer? _debounce;
  GraphSelection? _selection;
  Rect? _lastViewport;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load([Rect? viewport]) async {
    final generation = ++_generation;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await widget.api.graph(
        widget.node,
        xMin: viewport?.left ?? -10,
        xMax: viewport?.right ?? 10,
      );
      if (!mounted || generation != _generation) return;
      setState(() {
        _data = data;
        _loading = false;
      });
    } catch (error) {
      if (!mounted || generation != _generation) return;
      setState(() {
        _loading = false;
        _error = error is SolveFailure
            ? error.message
            : 'Не удалось построить график';
      });
    }
  }

  void _viewportChanged(Rect rect) {
    _lastViewport = rect;
    _generation++; // Invalidate a response as soon as a newer gesture starts.
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 220), () => _load(rect));
  }

  @override
  void dispose() {
    _debounce?.cancel();
    super.dispose();
  }

  void _details() {
    final data = _data;
    if (data == null) return;
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: SizedBox(
          height: MediaQuery.sizeOf(context).height * .65,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              Text(
                'Сведения о графике',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 12),
              StepEquation(latex: nodeToLatex(widget.node)),
              Text(
                'Точки кривой показаны приближённо. Список особых точек может быть неполным.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              for (final feature in graphFeatures(data))
                ListTile(
                  title: Text(feature.label),
                  subtitle: Text(
                    '(${graphNumber(feature.point.x)}; ${graphNumber(feature.point.y)})',
                  ),
                  onTap: () {
                    Navigator.pop(context);
                    _view.currentState?.focus(feature.point);
                    setState(() => _selection = feature);
                  },
                ),
              for (final x in data.annotations.verticalAsymptotes)
                ListTile(
                  title: const Text('Вертикальная асимптота'),
                  subtitle: Text('x = ${graphNumber(x)}'),
                ),
              for (final y in data.annotations.horizontalAsymptotes)
                ListTile(
                  title: const Text('Горизонтальная асимптота'),
                  subtitle: Text('y = ${graphNumber(y)}'),
                ),
              if (data.annotations.piecewise)
                const ListTile(title: Text('Кусочно-заданная функция')),
              if (data.annotations.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(16),
                  child: Text('Особые точки не предоставлены решателем.'),
                ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('График'),
      actions: [
        IconButton(
          tooltip: 'Закрыть',
          onPressed: () => Navigator.pop(context),
          icon: const Icon(Icons.close),
        ),
      ],
    ),
    body: SafeArea(
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: StepEquation(latex: nodeToLatex(widget.node)),
          ),
          Expanded(
            child: Stack(
              children: [
                if (_data case final data?)
                  Positioned.fill(
                    child: GraphView(
                      key: _view,
                      data: data,
                      onViewportChanged: _viewportChanged,
                      onSelect: (selection) =>
                          setState(() => _selection = selection),
                    ),
                  ),
                if (_data?.points.isEmpty == true &&
                    !_loading &&
                    _error == null)
                  const Center(
                    child: Text('На этом интервале нет точек графика'),
                  ),
                if (_loading)
                  Positioned(
                    top: 0,
                    left: 16,
                    right: 16,
                    child: Semantics(
                      label: 'Построение графика',
                      liveRegion: true,
                      child: const LinearProgressIndicator(minHeight: 2),
                    ),
                  ),
                if (_selection case final selection?)
                  Positioned(
                    left: 16,
                    top: 12,
                    right: 16,
                    child: IgnorePointer(
                      child: Material(
                        color: Theme.of(context).colorScheme.surface,
                        borderRadius: BorderRadius.circular(12),
                        child: Padding(
                          padding: const EdgeInsets.all(12),
                          child: Text(
                            '${selection.label}: ${selection.approximate ? '≈ ' : ''}(${graphNumber(selection.point.x)}; ${graphNumber(selection.point.y)})',
                          ),
                        ),
                      ),
                    ),
                  ),
                if (_error case final error?)
                  Align(
                    alignment: Alignment.center,
                    child: Material(
                      color: Theme.of(context).colorScheme.surface,
                      child: Padding(
                        padding: const EdgeInsets.all(24),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(error),
                            TextButton.icon(
                              onPressed: () => _load(_lastViewport),
                              icon: const Icon(Icons.refresh),
                              label: const Text('Повторить'),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Wrap(
              alignment: WrapAlignment.center,
              spacing: 8,
              children: [
                IconButton(
                  tooltip: 'Уменьшить',
                  onPressed: () => _view.currentState?.zoom(.5),
                  icon: const Icon(Icons.remove),
                ),
                IconButton(
                  tooltip: 'Увеличить',
                  onPressed: () => _view.currentState?.zoom(2),
                  icon: const Icon(Icons.add),
                ),
                TextButton.icon(
                  onPressed: () => _view.currentState?.recenter(),
                  icon: const Icon(Icons.center_focus_strong_outlined),
                  label: const Text('По центру'),
                ),
                TextButton(
                  onPressed: _data == null ? null : _details,
                  child: const Text('Сведения'),
                ),
              ],
            ),
          ),
        ],
      ),
    ),
  );
}

class GraphView extends StatefulWidget {
  const GraphView({
    super.key,
    required this.data,
    this.onViewportChanged,
    this.onSelect,
  });
  final GraphData data;
  final ValueChanged<Rect>? onViewportChanged;
  final ValueChanged<GraphSelection>? onSelect;
  @override
  State<GraphView> createState() => GraphViewState();
}

class GraphViewState extends State<GraphView> {
  late Rect viewport;
  late final Rect _home;
  late Rect _gesture;
  Offset _anchor = Offset.zero;
  Size _size = Size.zero;
  @override
  void initState() {
    super.initState();
    _home = _initial;
    viewport = _home;
  }

  Rect get _initial {
    final d = widget.data;
    final span = (d.yMax - d.yMin).abs();
    final pad = span < .001 ? 1.0 : span * .12;
    return Rect.fromLTRB(d.xMin, d.yMin - pad, d.xMax, d.yMax + pad);
  }

  void zoom(double factor) {
    final w = (viewport.width / factor).clamp(.000001, 1e6);
    final h = (viewport.height / factor).clamp(.000001, 1e6);
    setState(
      () => viewport = Rect.fromCenter(
        center: viewport.center,
        width: w,
        height: h,
      ),
    );
    widget.onViewportChanged?.call(viewport);
  }

  void recenter() {
    setState(() => viewport = _home);
    widget.onViewportChanged?.call(viewport);
  }

  void focus(GraphPoint p) {
    setState(
      () => viewport = Rect.fromCenter(
        center: Offset(p.x, p.y),
        width: viewport.width,
        height: viewport.height,
      ),
    );
    widget.onViewportChanged?.call(viewport);
  }

  Offset _screen(GraphPoint p) => Offset(
    (p.x - viewport.left) / viewport.width * _size.width,
    (viewport.bottom - p.y) / viewport.height * _size.height,
  );

  void _select(Offset position) {
    GraphSelection? selected;
    var distance = 28.0;
    for (final feature in [
      ...graphFeatures(widget.data),
      for (final p in widget.data.points)
        (label: 'Кривая', point: p, approximate: true),
    ]) {
      if (!feature.point.x.isFinite || !feature.point.y.isFinite) continue;
      final d = (_screen(feature.point) - position).distance;
      if (d < distance &&
          (selected == null || selected.approximate || !feature.approximate)) {
        distance = d;
        selected = feature;
      }
    }
    if (selected != null) widget.onSelect?.call(selected);
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      _size = constraints.biggest;
      return Semantics(
        label: 'Интерактивный график. Масштаб и особые точки доступны кнопками и в сведениях.',
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTapUp: (details) => _select(details.localPosition),
          onScaleStart: (details) {
            _gesture = viewport;
            _anchor = details.localFocalPoint;
          },
          onScaleUpdate: (details) {
            if (_size.isEmpty) return;
            final width = (_gesture.width / details.scale).clamp(.000001, 1e6);
            final height = (_gesture.height / details.scale).clamp(
              .000001,
              1e6,
            );
            final x = _gesture.left + _anchor.dx / _size.width * _gesture.width;
            final y =
                _gesture.bottom - _anchor.dy / _size.height * _gesture.height;
            final left = x - details.localFocalPoint.dx / _size.width * width;
            final bottom =
                y + details.localFocalPoint.dy / _size.height * height;
            setState(
              () => viewport = Rect.fromLTRB(
                left,
                bottom - height,
                left + width,
                bottom,
              ),
            );
          },
          onScaleEnd: (_) => widget.onViewportChanged?.call(viewport),
          child: RepaintBoundary(
            child: CustomPaint(
              painter: _GraphPainter(
                widget.data,
                viewport,
                Theme.of(context).colorScheme,
                MediaQuery.textScalerOf(context),
              ),
              child: const SizedBox.expand(),
            ),
          ),
        ),
      );
    },
  );
}

class _GraphPainter extends CustomPainter {
  _GraphPainter(this.data, this.viewport, this.colors, this.scaler);
  final GraphData data;
  final Rect viewport;
  final ColorScheme colors;
  final TextScaler scaler;
  double _step(double span) {
    final raw = span / 5;
    final power = math.pow(10, (math.log(raw) / math.ln10).floor()).toDouble();
    final n = raw / power;
    return (n <= 1
            ? 1
            : n <= 2
            ? 2
            : n <= 5
            ? 5
            : 10) *
        power;
  }

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty || viewport.width <= 0 || viewport.height <= 0) return;
    double sx(double x) => (x - viewport.left) / viewport.width * size.width;
    double sy(double y) =>
        (viewport.bottom - y) / viewport.height * size.height;
    canvas.save();
    canvas.clipRect(Offset.zero & size);
    canvas.drawRect(Offset.zero & size, Paint()..color = colors.surface);
    final grid = Paint()
      ..color = colors.outlineVariant
      ..strokeWidth = 1;
    void label(String text, Offset at) {
      final painter = TextPainter(
        text: TextSpan(
          text: text,
          style: TextStyle(fontSize: 12, color: colors.onSurfaceVariant),
        ),
        textDirection: TextDirection.ltr,
        textScaler: scaler,
      )..layout();
      painter.paint(
        canvas,
        Offset(
          at.dx.clamp(4, math.max(4, size.width - painter.width - 4)),
          at.dy.clamp(4, math.max(4, size.height - painter.height - 4)),
        ),
      );
      painter.dispose();
    }

    final dx = _step(viewport.width);
    final dy = _step(viewport.height);
    for (
      var x = (viewport.left / dx).ceil() * dx, count = 0;
      x <= viewport.right && count < 20;
      x += dx, count++
    ) {
      canvas.drawLine(Offset(sx(x), 0), Offset(sx(x), size.height), grid);
      label(graphNumber(x), Offset(sx(x) + 4, sy(0) + 4));
    }
    for (
      var y = (viewport.top / dy).ceil() * dy, count = 0;
      y <= viewport.bottom && count < 20;
      y += dy, count++
    ) {
      canvas.drawLine(Offset(0, sy(y)), Offset(size.width, sy(y)), grid);
      if (y.abs() > dy * .01) {
        label(graphNumber(y), Offset(sx(0) + 4, sy(y) + 4));
      }
    }
    final axis = Paint()
      ..color = colors.outline
      ..strokeWidth = 1.4;
    canvas.drawLine(Offset(sx(0), 0), Offset(sx(0), size.height), axis);
    canvas.drawLine(Offset(0, sy(0)), Offset(size.width, sy(0)), axis);
    void dashed(Offset a, Offset b) {
      final total = (b - a).distance;
      if (total <= 0) return;
      final direction = (b - a) / total;
      for (var t = 0.0; t < total; t += 10) {
        canvas.drawLine(
          a + direction * t,
          a + direction * math.min(t + 6, total),
          Paint()
            ..color = colors.onSurfaceVariant
            ..strokeWidth = 1.2,
        );
      }
    }

    for (final x in data.annotations.verticalAsymptotes) {
      dashed(Offset(sx(x), 0), Offset(sx(x), size.height));
    }
    for (final y in data.annotations.horizontalAsymptotes) {
      dashed(Offset(0, sy(y)), Offset(size.width, sy(y)));
    }
    final path = Path();
    GraphPoint? previous;
    for (final point in data.points) {
      if (!point.x.isFinite || !point.y.isFinite) {
        previous = null;
        continue;
      }
      final offset = Offset(sx(point.x), sy(point.y));
      final split =
          previous == null ||
          data.annotations.verticalAsymptotes.any(
            (a) => a >= previous!.x && a <= point.x,
          ) ||
          (sy(previous.y) - offset.dy).abs() > size.height * .8;
      if (split) {
        path.moveTo(offset.dx, offset.dy);
      } else {
        path.lineTo(offset.dx, offset.dy);
      }
      previous = point;
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = colors.primary
        ..strokeWidth = 2.5
        ..style = PaintingStyle.stroke,
    );
    for (final feature in graphFeatures(data)) {
      final p = Offset(sx(feature.point.x), sy(feature.point.y));
      final paint = Paint()
        ..color = colors.primary
        ..strokeWidth = 2;
      canvas.drawCircle(p, 6, Paint()..color = colors.surface);
      if (feature.label == 'Корень') {
        canvas.drawCircle(p, 4, paint..style = PaintingStyle.stroke);
      } else {
        canvas.drawPath(
          Path()
            ..moveTo(p.dx, p.dy - 5)
            ..lineTo(p.dx + 5, p.dy)
            ..lineTo(p.dx, p.dy + 5)
            ..lineTo(p.dx - 5, p.dy)
            ..close(),
          paint,
        );
      }
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(_GraphPainter oldDelegate) =>
      oldDelegate.data != data ||
      oldDelegate.viewport != viewport ||
      oldDelegate.colors != colors ||
      oldDelegate.scaler != scaler;
}
