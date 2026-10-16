import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';
import '../api/solver_api.dart';
import '../model/core_node.dart';
import '../render/latex.dart';
import '../render/division_trace.dart';
import '../settings/settings.dart';
import 'division_lesson.dart';
import 'transformation_lesson.dart';

class VerticalResult extends StatelessWidget {
  const VerticalResult({super.key, required this.result, required this.latexOptions,
    required this.onLink, required this.onCopy, this.methodSwitcher, this.onBack, this.expandAll = false,
    this.problem, this.divisionMethod = DivisionMethod.ru});
  final SolveResponse result;
  final LatexOptions latexOptions;
  final void Function(ExplanationLink) onLink;
  final void Function(String) onCopy;
  final Widget? methodSwitcher;
  final VoidCallback? onBack;
  final bool expandAll;
  final CoreNode? problem;
  final DivisionMethod divisionMethod;

  @override
  Widget build(BuildContext context) {
    var number = 0;
    return ListView(padding: const EdgeInsets.fromLTRB(16, 12, 16, 24), children: [
      if (result.solution case final solution?) Container(
        padding: const EdgeInsets.all(20), margin: const EdgeInsets.only(bottom: 24),
        decoration: BoxDecoration(color: Theme.of(context).colorScheme.primaryContainer.withValues(alpha: .35),
          borderRadius: BorderRadius.circular(12)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Ответ', style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 12),
          Row(children: [Expanded(child: StepEquation(latex: nodeToLatex(solution, latexOptions), fontSize: 28)),
            IconButton(tooltip: 'Копировать ответ', onPressed: () => onCopy(nodeToLatex(solution, latexOptions)), icon: const Icon(Icons.copy_outlined))]),
        ]),
      ),
      ?methodSwitcher,
      if (problem != null && DivisionTrace.fromNode(problem!) != null) TextButton.icon(
        onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => DivisionLesson(
          trace: DivisionTrace.fromNode(problem!)!, method: divisionMethod, separator: latexOptions.decimalSeparator.symbol))),
        icon: const Icon(Icons.view_agenda_outlined), label: const Text('Деление столбиком')),
      if (result.steps.isEmpty) const Padding(padding: EdgeInsets.all(16),
        child: Text('Для этой задачи подробные шаги не предоставлены.')),
      for (final group in result.steps) ...[
        for (final header in group.headers.where((h) => h.isNotEmpty)) Padding(
          padding: const EdgeInsets.symmetric(vertical: 16), child: Text(header, style: Theme.of(context).textTheme.titleMedium)),
        for (final step in group.substeps) _Step(
          key: ValueKey('step:${number++}:$expandAll'), number: number, substep: step,
          latexOptions: latexOptions, onLink: onLink, onCopy: onCopy, expanded: expandAll),
      ],
    ]);
  }
}

class _Step extends StatelessWidget {
  const _Step({super.key, required this.number, required this.substep, required this.latexOptions,
    required this.onLink, required this.onCopy, this.expanded = false});
  final int number;
  final Substep substep;
  final LatexOptions latexOptions;
  final void Function(ExplanationLink) onLink;
  final void Function(String) onCopy;
  final bool expanded;

  Widget equation(CoreNode node) => StepEquation(latex: nodeToLatex(node, latexOptions));

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final frames = transformationFrames(substep, latexOptions);
    return Container(margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(color: colors.surface, borderRadius: BorderRadius.circular(12)),
      child: ExpansionTile(
        initiallyExpanded: expanded, maintainState: true,
        shape: const Border(), collapsedShape: const Border(),
        tilePadding: const EdgeInsets.all(16), childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        trailing: Icon(Icons.keyboard_arrow_down, color: colors.onSurfaceVariant),
        title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Шаг $number', style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 12),
          if (substep.left case final left?) equation(left),
          if (substep.right case final right?) ...[
            Padding(padding: const EdgeInsets.symmetric(vertical: 8), child: Icon(Icons.south, size: 18, color: colors.primary)),
            equation(right),
          ],
        ]),
        subtitle: substep.text == null || substep.text!.startsWith('step_') ? null : Padding(
          padding: const EdgeInsets.only(top: 12), child: ExplanationText(text: substep.text!, links: substep.links, onLink: onLink)),
        children: [
          if (frames.isNotEmpty) Align(alignment: Alignment.centerLeft, child: TextButton.icon(
            onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => TransformationLesson(frames: frames))),
            icon: const Icon(Icons.play_circle_outline), label: const Text('Показать преобразование'))),
          for (final group in substep.detail) ...[
            for (final header in group.headers.where((h) => h.isNotEmpty)) Text(header, style: Theme.of(context).textTheme.titleMedium),
            for (var i = 0; i < group.substeps.length; i++) _Step(number: i + 1, substep: group.substeps[i],
              latexOptions: latexOptions, onLink: onLink, onCopy: onCopy),
          ],
          for (final link in substep.links.where((l) => l.definition.isNotEmpty)) ListTile(
            contentPadding: EdgeInsets.zero, title: Text(link.label), trailing: const Icon(Icons.info_outline), onTap: () => onLink(link)),
          Align(alignment: Alignment.centerLeft, child: TextButton.icon(
            onPressed: substep.right == null && substep.left == null ? null : () => onCopy(nodeToLatex(substep.right ?? substep.left!, latexOptions)),
            icon: const Icon(Icons.copy_outlined, size: 20), label: const Text('Копировать шаг'))),
        ],
      ),
    );
  }
}

/// Long equations scroll instead of shrinking text below a readable size.
class StepEquation extends StatelessWidget {
  const StepEquation({super.key, required this.latex, this.fontSize = 22});
  final String latex;
  final double fontSize;
  @override
  Widget build(BuildContext context) => SingleChildScrollView(scrollDirection: Axis.horizontal,
    child: Padding(padding: const EdgeInsets.symmetric(vertical: 4), child: Math.tex(latex,
      mathStyle: MathStyle.display,
      textStyle: TextStyle(fontSize: fontSize, color: Theme.of(context).colorScheme.onSurface),
      onErrorFallback: (_) => Text(latex, style: Theme.of(context).textTheme.bodyLarge))));
}

class ExplanationText extends StatelessWidget {
  const ExplanationText({super.key, required this.text, required this.links, required this.onLink});
  final String text;
  final List<ExplanationLink> links;
  final void Function(ExplanationLink) onLink;
  @override
  Widget build(BuildContext context) {
    final spans = <InlineSpan>[];
    var cursor = 0;
    for (final link in links) {
      if (link.definition.isEmpty) continue;
      final at = text.indexOf(link.label, cursor);
      if (at < 0) continue;
      if (at > cursor) spans.add(TextSpan(text: text.substring(cursor, at)));
      spans.add(WidgetSpan(alignment: PlaceholderAlignment.middle, child: TextButton(
        onPressed: () => onLink(link), child: Text(link.label, style: const TextStyle(decoration: TextDecoration.underline)))));
      cursor = at + link.label.length;
    }
    if (cursor < text.length) spans.add(TextSpan(text: text.substring(cursor)));
    return Text.rich(TextSpan(children: spans), style: Theme.of(context).textTheme.bodyLarge);
  }
}
