/// Ввод: формула с курсором.
///
/// Дерево редактора отрисовывается через `flutter_math` как LaTeX, в который
/// вставлен макрос курсора `\cursor{}`. Свой наборщик формул не пишем:
/// решение проекта — рендерить формулы готовым движком.
library;

import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';

import 'controller.dart';
import 'latex.dart';

/// Формула ввода с курсором.
class EditorView extends StatelessWidget {
  const EditorView({super.key, required this.controller, this.fontSize = 30});

  final EditorController controller;

  /// Размер формулы ввода.
  final double fontSize;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final latex = editorToLatex(controller.document, controller.cursor);
        return Container(
          width: double.infinity,
          constraints: const BoxConstraints(minHeight: 72),
          alignment: Alignment.centerLeft,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Math.tex(
              latex,
              mathStyle: MathStyle.display,
              textStyle: TextStyle(fontSize: fontSize),
              onErrorFallback: (error) => Text(
                latex,
                style: TextStyle(
                  fontSize: 16,
                  color: theme.colorScheme.error,
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}
