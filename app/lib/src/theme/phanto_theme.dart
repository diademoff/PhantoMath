import 'package:flutter/material.dart';

/// Semantic roles: widgets must not select light-mode colors themselves.
abstract final class PhantoTheme {
  static ThemeData light() => _theme(Brightness.light);
  static ThemeData dark() => _theme(Brightness.dark);

  static ThemeData _theme(Brightness brightness) {
    final dark = brightness == Brightness.dark;
    final scheme = ColorScheme.fromSeed(
      seedColor: const Color(0xFF176B57),
      brightness: brightness,
    ).copyWith(
      primary: Color(dark ? 0xFF78D9B5 : 0xFF176B57),
      onPrimary: Color(dark ? 0xFF10271E : 0xFFFFFFFF),
      surface: Color(dark ? 0xFF1A211C : 0xFFFFFFFF),
      onSurface: Color(dark ? 0xFFEEF2EC : 0xFF202522),
      onSurfaceVariant: Color(dark ? 0xFFADB9AF : 0xFF626A65),
      outline: Color(dark ? 0xFF829388 : 0xFF7E8982),
      outlineVariant: Color(dark ? 0xFF35433A : 0xFFDCE3DD),
      error: Color(dark ? 0xFFFFB4AB : 0xFFB3261E),
    );
    final base = ThemeData(useMaterial3: true, colorScheme: scheme);
    return base.copyWith(
      scaffoldBackgroundColor: Color(dark ? 0xFF111512 : 0xFFF7F8F5),
      textTheme: base.textTheme.copyWith(
        headlineSmall: TextStyle(fontSize: 28, fontWeight: FontWeight.w600, color: scheme.onSurface, letterSpacing: -0.6),
        titleLarge: TextStyle(fontSize: 22, fontWeight: FontWeight.w600, color: scheme.onSurface),
        titleMedium: TextStyle(fontSize: 18, fontWeight: FontWeight.w600, color: scheme.onSurface),
        bodyLarge: TextStyle(fontSize: 16, height: 1.45, color: scheme.onSurface),
        bodyMedium: TextStyle(fontSize: 16, height: 1.45, color: scheme.onSurface),
        bodySmall: TextStyle(fontSize: 14, height: 1.4, color: scheme.onSurfaceVariant),
        labelLarge: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: scheme.onSurface),
        labelSmall: TextStyle(fontSize: 14, color: scheme.onSurfaceVariant),
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: Color(dark ? 0xFF111512 : 0xFFF7F8F5),
        foregroundColor: scheme.onSurface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        centerTitle: false,
      ),
      iconButtonTheme: IconButtonThemeData(style: IconButton.styleFrom(minimumSize: const Size(48, 48))),
      filledButtonTheme: FilledButtonThemeData(style: FilledButton.styleFrom(
        minimumSize: const Size(48, 52),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      )),
      outlinedButtonTheme: OutlinedButtonThemeData(style: OutlinedButton.styleFrom(
        minimumSize: const Size(48, 48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      )),
      textButtonTheme: TextButtonThemeData(style: TextButton.styleFrom(minimumSize: const Size(48, 48))),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: scheme.surface,
        surfaceTintColor: Colors.transparent,
        showDragHandle: true,
        shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      ),
      dialogTheme: DialogThemeData(backgroundColor: scheme.surface, surfaceTintColor: Colors.transparent),
      inputDecorationTheme: InputDecorationTheme(
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
        contentPadding: const EdgeInsets.all(16),
      ),
    );
  }
}

abstract final class PhMotion {
  static Duration duration(BuildContext context, [int milliseconds = 200]) =>
      MediaQuery.disableAnimationsOf(context) ? Duration.zero : Duration(milliseconds: milliseconds);
}

/// Own mark: an open mathematical bracket with a precise, quiet dot.
class PhantoMark extends StatelessWidget {
  const PhantoMark({super.key, this.size = 32});
  final double size;
  @override
  Widget build(BuildContext context) => ExcludeSemantics(
    child: CustomPaint(size: Size.square(size), painter: _MarkPainter(Theme.of(context).colorScheme.primary)),
  );
}

class _MarkPainter extends CustomPainter {
  const _MarkPainter(this.color);
  final Color color;
  @override
  void paint(Canvas canvas, Size size) {
    canvas.scale(size.width / 32, size.height / 32);
    canvas.drawPath(Path()..moveTo(13, 5)..lineTo(6, 5)..lineTo(6, 27)..lineTo(13, 27),
      Paint()..color = color..style = PaintingStyle.stroke..strokeWidth = 2.5..strokeCap = StrokeCap.round..strokeJoin = StrokeJoin.round);
    canvas.drawPath(Path()..moveTo(18, 8)..quadraticBezierTo(29, 8, 25, 16)..quadraticBezierTo(22, 21, 15, 19)..lineTo(15, 27),
      Paint()..color = color..style = PaintingStyle.stroke..strokeWidth = 2.5..strokeCap = StrokeCap.round);
    canvas.drawCircle(const Offset(23, 26), 1.8, Paint()..color = color);
  }
  @override
  bool shouldRepaint(_MarkPainter oldDelegate) => oldDelegate.color != color;
}
