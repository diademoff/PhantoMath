/// Предпросмотр решения над клавиатурой — `res/layout/fragment_editor.xml`
/// и `res/layout/layout_solver_vertical_solution.xml`, перенесены 1 в 1.
///
/// Раскладка оригинала (`layout_solver_vertical_solution.xml`):
///
/// * `solution_view`: 24sp, `boldTypeface`, операторы `photomath_black_40`
///   (`#66000000`), `showPreview`;
/// * `alternative_solution_text`: 14sp, **`textColorSecondary`** (`#7F7F7F`,
///   серый — не красный), `layout_marginTop=16dip`;
/// * `alternative_solution_view`: 20sp, `textColorPrimary`, `marginTop=8dip`;
/// * пунктир — отдельный `@id/solution_dotted_line` над блоком:
///   `drawable/dotted_line` (`<shape line>`, штрих `dashWidth=2dip`,
///   `dashGap=2dip`, цвет `photomath_gray_medium`), высота полосы 4dip,
///   `layout_marginTop=18dip`;
/// * блок `@id/solution_container`: `marginTop=16dip`, `marginStart=16dip`,
///   `marginEnd=8dip`; красная полоса `@id/solution_line` 6dip слева
///   на всю высоту блока (от `x=0`, текст начинается в 16dip от края —
///   6dip полосы + 10dip зазора).
library;

import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';

import '../theme/photomath_theme.dart';

/// Блок «Решение» над клавиатурой: ответ и альтернативная форма.
class SolutionPreview extends StatelessWidget {
  const SolutionPreview({
    super.key,
    required this.latex,
    this.alternativeLatex,
  });

  /// Основная формула ответа.
  final String latex;

  /// Альтернативная форма, если решатель её вернул.
  final String? alternativeLatex;

  @override
  Widget build(BuildContext context) {
    final alternative = alternativeLatex;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _DottedLine(),
        IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // `@id/solution_line`: 6dip красной полосы слева.
              const ColoredBox(
                color: PhColor.red,
                child: SizedBox(width: PhSize.accentBarWidth),
              ),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.only(
                    top: PhGap.blockTop,
                    bottom: PhGap.blockTop,
                    left: 10,
                    right: 8,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _Formula(latex: latex, fontSize: 24, bold: true),
                      if (alternative != null && alternative.isNotEmpty) ...[
                        const SizedBox(height: 16),
                        // `@id/alternative_solution_text`: 14sp,
                        // `textColorSecondary` (серый `#7F7F7F`).
                        const Text(
                          PhString.alternateForm,
                          style: TextStyle(
                            fontSize: 14,
                            color: PhColor.grayMedium,
                          ),
                        ),
                        const SizedBox(height: 8),
                        _Formula(latex: alternative, fontSize: 20),
                      ],
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// Формула блока решения.
class _Formula extends StatelessWidget {
  const _Formula({
    required this.latex,
    required this.fontSize,
    this.bold = false,
  });

  final String latex;
  final double fontSize;
  final bool bold;

  @override
  Widget build(BuildContext context) {
    if (latex.isEmpty) return const SizedBox.shrink();
    return Math.tex(
      latex,
      mathStyle: MathStyle.display,
      textStyle: TextStyle(
        fontSize: fontSize,
        fontWeight: bold ? FontWeight.bold : FontWeight.normal,
        color: PhColor.grayDark,
      ),
      onErrorFallback: (error) => Text(
        latex,
        style: TextStyle(
          fontSize: fontSize,
          fontWeight: bold ? FontWeight.bold : FontWeight.normal,
          color: PhColor.error,
        ),
      ),
    );
  }
}

/// Пунктирная линия над блоком решения — `@id/solution_dotted_line`.
 ///
 /// В оригинале это `<shape android:shape="line">` со штрихом
 /// `dashWidth=2dip`, `dashGap=2dip`, цвет `photomath_gray_medium`
 /// (`#7F7F7F`), `layout_marginTop=18dip`; высота вью 4dip.
class _DottedLine extends StatelessWidget {
  const _DottedLine();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 18, bottom: 0),
      child: SizedBox(height: 4, child: CustomPaint(painter: _DashedPainter())),
    );
  }
}

class _DashedPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = PhColor.grayMedium
      ..strokeWidth = 1;
    const dash = 2.0;
    const gap = 2.0;
    final y = (size.height / 2).roundToDouble() + 0.5;
    for (var x = 0.0; x < size.width; x += dash + gap) {
      canvas.drawLine(Offset(x, y), Offset(x + dash, y), paint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
