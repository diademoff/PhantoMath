/// Live answer: unconstrained math scrolls horizontally, without intrinsic layout.
library;

import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';

class SolutionPreview extends StatelessWidget {
  const SolutionPreview({
    super.key,
    required this.latex,
    this.alternativeLatex,
  });

  final String latex;
  final String? alternativeLatex;

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
          Text('Ответ', style: Theme.of(context).textTheme.labelSmall),
          const SizedBox(height: 8),
          _Formula(latex: latex, fontSize: 24),
          if (alternativeLatex case final alternative?
              when alternative.isNotEmpty) ...[
            const SizedBox(height: 16),
            Text(
              'Альтернативная форма',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 8),
            _Formula(latex: alternative, fontSize: 20),
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

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    scrollDirection: Axis.horizontal,
    child: Math.tex(
      latex,
      mathStyle: MathStyle.display,
      textStyle: TextStyle(
        fontSize: fontSize,
        color: Theme.of(context).colorScheme.onSurface,
      ),
      onErrorFallback: (_) => Text(latex),
    ),
  );
}
