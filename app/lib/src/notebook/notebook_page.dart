/// Экран блокнота: история решённых задач.
library;

import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';

import '../render/latex.dart';
import 'notebook.dart';

/// Страница истории.
class NotebookPage extends StatelessWidget {
  const NotebookPage({
    super.key,
    required this.notebook,
    this.latexOptions = LatexOptions.standard,
  });

  final Notebook notebook;

  /// Настройки отрисовки формул (разделитель, нотация бинома).
  final LatexOptions latexOptions;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Блокнот'),
        actions: [
          IconButton(
            tooltip: 'Очистить',
            onPressed: notebook.isEmpty ? null : () => _clear(context),
            icon: const Icon(Icons.delete_outline),
          ),
        ],
      ),
      body: AnimatedBuilder(
        animation: notebook,
        builder: (context, _) {
          final entries = notebook.entries;
          if (entries.isEmpty) {
            return const Center(
              child: Text('Пусто: решённые задачи появятся здесь'),
            );
          }
          return ListView.builder(
            padding: const EdgeInsets.all(12),
            itemCount: entries.length,
            itemBuilder: (context, index) {
              final entry = entries[index];
              return Card(
                margin: const EdgeInsets.symmetric(vertical: 4),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _Formula(latex: nodeToLatex(entry.problem, latexOptions)),
                      if (entry.solution != null) ...[
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            const Icon(Icons.arrow_forward, size: 16),
                            const SizedBox(width: 8),
                            Expanded(
                              child: _Formula(
                                latex: nodeToLatex(
                                  entry.solution!,
                                  latexOptions,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                      const SizedBox(height: 8),
                      _Metadata(entry: entry),
                    ],
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }

  /// Очистить историю с возможностью отмены (`clear_history_message` /
  /// `clear_history_undo` в оригинале показаны как «История очищена»/«Отменить»).
  Future<void> _clear(BuildContext context) async {
    final messenger = ScaffoldMessenger.of(context);
    final removed = await notebook.clear();
    messenger.showSnackBar(
      SnackBar(
        content: const Text('История очищена'),
        action: SnackBarAction(
          label: 'Отменить',
          onPressed: () => notebook.restore(removed),
        ),
      ),
    );
  }
}

/// Время и метаданные записи (вид результата, действие, язык).
class _Metadata extends StatelessWidget {
  const _Metadata({required this.entry});

  final NotebookEntry entry;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final chips = <String>[
      _time(entry.savedAt),
      if (entry.command != null) entry.command!,
      entry.locale,
    ];
    return Wrap(
      spacing: 8,
      runSpacing: 4,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        for (final chip in chips) Text(chip, style: theme.textTheme.labelSmall),
      ],
    );
  }

  String _time(DateTime value) {
    final local = value.toLocal().toIso8601String();
    return local.length >= 16
        ? local.substring(0, 16).replaceAll('T', ' ')
        : local;
  }
}

/// Формула с защитой от кривого LaTeX.
class _Formula extends StatelessWidget {
  const _Formula({required this.latex});

  final String latex;

  @override
  Widget build(BuildContext context) {
    if (latex.isEmpty) return const SizedBox.shrink();
    return Math.tex(
      latex,
      mathStyle: MathStyle.display,
      onErrorFallback: (error) => Text(latex),
    );
  }
}
