/// Экран блокнота: история решённых задач.
library;

import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';

import '../render/latex.dart';
import 'notebook.dart';

/// Страница истории.
class NotebookPage extends StatelessWidget {
  const NotebookPage({super.key, required this.notebook});

  final Notebook notebook;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Блокнот'),
        actions: [
          IconButton(
            tooltip: 'Очистить',
            onPressed: notebook.isEmpty ? null : notebook.clear,
            icon: const Icon(Icons.delete_outline),
          ),
        ],
      ),
      body: AnimatedBuilder(
        animation: notebook,
        builder: (context, _) {
          final entries = notebook.entries;
          if (entries.isEmpty) {
            return const Center(child: Text('Пусто: решённые задачи появятся здесь'));
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
                      _Formula(latex: nodeToLatex(entry.problem)),
                      if (entry.solution != null) ...[
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            const Icon(Icons.arrow_forward, size: 16),
                            const SizedBox(width: 8),
                            Expanded(
                              child: _Formula(latex: nodeToLatex(entry.solution!)),
                            ),
                          ],
                        ),
                      ],
                      const SizedBox(height: 8),
                      Text(
                        _time(entry.savedAt),
                        style: Theme.of(context).textTheme.labelSmall,
                      ),
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

  String _time(DateTime value) {
    final local = value.toLocal().toIso8601String();
    return local.length >= 16 ? local.substring(0, 16).replaceAll('T', ' ') : local;
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
