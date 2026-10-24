/// Live answer: the formula breaks across lines, a tall one scrolls.
///
/// Ответ не обрезается карточкой: длинная формула переносится по строкам
/// (см. `formula_break.dart`), а высокая (матрица 4×4, определитель 5×5)
/// ограничена долей экрана и прокручивается по вертикали.
library;

import 'package:flutter/material.dart';

import '../i18n.dart';
import 'formula_break.dart';

class SolutionPreview extends StatelessWidget {
  const SolutionPreview({
    super.key,
    required this.latex,
    this.alternatives = const [],
  });

  final String latex;

  /// LaTeX других форм ответа (десятичная, смешанное число, дробь).
  final List<String> alternatives;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colors.surfaceContainerLow,
        border: Border(left: BorderSide(color: colors.primary, width: 3)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            tr('Ответ', 'Answer'),
            style: Theme.of(context).textTheme.labelSmall,
          ),
          const SizedBox(height: 8),
          _Formula(latex: latex, fontSize: 24),
          if (alternatives.isNotEmpty) ...[
            const SizedBox(height: 16),
            Text(
              tr('Альтернативная форма', 'Alternative form'),
              style: Theme.of(context).textTheme.bodySmall,
            ),
            for (final alternative in alternatives) ...[
              const SizedBox(height: 8),
              _Formula(latex: alternative, fontSize: 20),
            ],
          ],
        ],
      ),
    );
  }
}

class _Formula extends StatelessWidget {
  const _Formula({required this.latex, required this.fontSize});
  final String latex;
  final double fontSize;

  /// Предел высоты ответа: выше — прокрутка, а не обрезка карточкой.
  ///
  /// Высокий ответ (матрица 4×4, определитель 5×5) не помещался в карточку и
  /// обрезался на второй строке; теперь карточка ограничена долей экрана, а
  /// сама формула прокручивается — как и горизонтально.
  static double _maxHeight(BuildContext context) =>
      (MediaQuery.sizeOf(context).height * .3).clamp(120.0, 280.0);

  @override
  Widget build(BuildContext context) => KeyedSubtree(
    key: ValueKey(latex),
    child: TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: MediaQuery.disableAnimationsOf(context)
          ? Duration.zero
          : const Duration(milliseconds: 220),
      curve: Curves.easeOutCubic,
      builder: (context, value, child) => Opacity(
        opacity: value,
        child: Transform.translate(
          offset: Offset(0, 8 * (1 - value)),
          child: child,
        ),
      ),
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: _maxHeight(context)),
        child: SingleChildScrollView(
          child: Semantics(
            container: true,
            label: latex,
            excludeSemantics: true,
            child: BreakableFormula(
              latex: latex,
              fontSize: fontSize,
              padding: EdgeInsets.zero,
            ),
          ),
        ),
      ),
    ),
  );
}
