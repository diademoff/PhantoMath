/// График `y = f(x)` по точкам от бэкенда.
///
/// Рисуем сами (`CustomPainter`): `CoreGraphResult` Photomath не воспроизводим,
/// а для отрисовки достаточно точек. Оси проводятся только если ноль попадает
/// в диапазон.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../api/solver_api.dart';

/// График функции.
class GraphView extends StatelessWidget {
  const GraphView({super.key, required this.data});

  final GraphData data;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: _GraphPainter(data),
      child: const SizedBox.expand(),
    );
  }
}

class _GraphPainter extends CustomPainter {
  _GraphPainter(this.data);

  final GraphData data;

  @override
  void paint(Canvas canvas, Size size) {
    if (data.points.isEmpty || size.isEmpty) return;

    final yLo = math.min(0.0, data.yMin);
    final yHi = math.max(0.0, data.yMax);
    final ySpan = yHi - yLo == 0 ? 1.0 : yHi - yLo;
    final xSpan = data.xMax - data.xMin == 0 ? 1.0 : data.xMax - data.xMin;
    double sx(double x) => (x - data.xMin) / xSpan * size.width;
    double sy(double y) => size.height - (y - yLo) / ySpan * size.height;

    final grid = Paint()
      ..color = const Color(0x14000000)
      ..strokeWidth = 1;
    for (var i = 1; i < 4; i++) {
      final x = size.width * i / 4;
      final y = size.height * i / 4;
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), grid);
      canvas.drawLine(Offset(0, y), Offset(size.width, y), grid);
    }

    final axis = Paint()
      ..color = const Color(0x66000000)
      ..strokeWidth = 1.5;
    if (data.xMin <= 0 && 0 <= data.xMax) {
      canvas.drawLine(Offset(sx(0), 0), Offset(sx(0), size.height), axis);
    }
    if (yLo <= 0 && 0 <= yHi) {
      canvas.drawLine(Offset(0, sy(0)), Offset(size.width, sy(0)), axis);
    }

    final curve = Paint()
      ..color = const Color(0xFF2C6BED)
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke
      ..strokeJoin = StrokeJoin.round;
    final path = Path();
    var started = false;
    for (final point in data.points) {
      final offset = Offset(sx(point.x), sy(point.y));
      if (started) {
        path.lineTo(offset.dx, offset.dy);
      } else {
        path.moveTo(offset.dx, offset.dy);
        started = true;
      }
    }
    canvas.drawPath(path, curve);
    _annotations(canvas, size, sx, sy);
  }

  /// Опорные точки: корни, пересечение с осью y, экстремумы, асимптоты.
  void _annotations(
    Canvas canvas,
    Size size,
    double Function(double) sx,
    double Function(double) sy,
  ) {
    final annotations = data.annotations;
    final asymptote = Paint()
      ..color = const Color(0x99C62828)
      ..strokeWidth = 1;
    for (final x in annotations.verticalAsymptotes) {
      final dx = sx(x);
      if (dx >= 0 && dx <= size.width) {
        _dashed(canvas, Offset(dx, 0), Offset(dx, size.height), asymptote);
      }
    }
    for (final y in annotations.horizontalAsymptotes) {
      final dy = sy(y);
      if (dy >= 0 && dy <= size.height) {
        _dashed(canvas, Offset(0, dy), Offset(size.width, dy), asymptote);
      }
    }

    final rootPaint = Paint()..color = const Color(0xFF2E7D32);
    for (final point in annotations.roots) {
      _dot(canvas, sx(point.x), sy(point.y), size, rootPaint);
    }
    final extremumPaint = Paint()..color = const Color(0xFF6A1B9A);
    for (final point in [...annotations.maxima, ...annotations.minima]) {
      _dot(canvas, sx(point.x), sy(point.y), size, extremumPaint);
    }
    final intercept = annotations.yIntercept;
    if (intercept != null) {
      _dot(
        canvas,
        sx(intercept.x),
        sy(intercept.y),
        size,
        Paint()..color = const Color(0xFFEF6C00),
      );
    }
  }

  void _dot(Canvas canvas, double dx, double dy, Size size, Paint paint) {
    if (dx < 0 || dx > size.width || dy < 0 || dy > size.height) return;
    canvas.drawCircle(Offset(dx, dy), 3, paint);
  }

  /// Пунктирная линия: у асимптот сплошная читалась бы как график.
  void _dashed(Canvas canvas, Offset from, Offset to, Paint paint) {
    const dash = 6.0;
    const gap = 4.0;
    final total = (to - from).distance;
    if (total == 0) return;
    final direction = (to - from) / total;
    var travelled = 0.0;
    while (travelled < total) {
      final end = math.min(travelled + dash, total);
      canvas.drawLine(
        from + direction * travelled,
        from + direction * end,
        paint,
      );
      travelled = end + gap;
    }
  }

  @override
  bool shouldRepaint(_GraphPainter oldDelegate) => oldDelegate.data != data;
}
